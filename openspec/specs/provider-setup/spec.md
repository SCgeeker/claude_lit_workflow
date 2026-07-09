# provider-setup Specification

## Purpose
TBD - created by archiving change extract-core-api. Update Purpose after archive.
## Requirements
### Requirement: 供應商偵測 API
系統 SHALL 提供 `check_providers() -> ProviderReport`，逐一檢查 Google Gemini、OpenAI、Anthropic、Ollama、OpenRouter、NVIDIA NIM 的可用性，並回傳建議供應商。此 API MUST NOT 直接寫入 stdout。

#### Scenario: 僅一供應商可用
- **WHEN** 環境中僅 `GOOGLE_API_KEY` 有效（其餘未設定或為佔位字串）
- **THEN** 回傳的 `providers` 中 google 標記 `available=True` 且附模型名稱訊息，其餘 `available=False` 且附原因；`recommended == "google"`

#### Scenario: 全部不可用
- **WHEN** 無任何供應商可用
- **THEN** `recommended` 為 None，各供應商附設定指引訊息（如「未設定 GOOGLE_API_KEY」）

#### Scenario: 佔位 key 視為未設定
- **WHEN** API key 值含 `your-` 佔位模式
- **THEN** 該供應商 `available=False`，原因為未設定

#### Scenario: NVIDIA NIM 納入偵測
- **WHEN** 呼叫 `check_providers()`
- **THEN** 回傳的 `providers` 清單含 name 為 `nvidia`、display_name 含「NVIDIA」的項目；`NVIDIA_API_KEY` 未設定或含 `nvapi-your` 佔位時 `available=False` 且原因為未設定

### Requirement: 選項目錄 API
系統 SHALL 提供 `list_options() -> OptionCatalog`，回傳風格、詳細程度、語言的完整目錄（鍵值與繁中說明）。目錄內容 MUST 來自 `templates/styles/academic_styles.yaml`，MUST NOT 於 CLI 硬編碼。

#### Scenario: 目錄完整性
- **WHEN** 呼叫 `list_options()`
- **THEN** 回傳含 7 種投影片風格、5 種詳細程度、3 種語言，每項附非空說明文字

#### Scenario: CLI 與 API 目錄一致
- **WHEN** CLI 執行 `--list-options`
- **THEN** 顯示內容來自 `list_options()` 的回傳值（單一真相來源）

### Requirement: NVIDIA NIM 供應商生成
系統 SHALL 支援以 NVIDIA NIM（OpenAI 相容 endpoint `https://integrate.api.nvidia.com/v1`）作為 LLM 供應商。呼叫 MUST 以 `NVIDIA_API_KEY` 進行 Bearer 認證；金鑰 MUST 只從環境載入，MUST NOT 出現在回傳內容中。

#### Scenario: 指定 nvidia 供應商生成
- **WHEN** 以 `provider="nvidia"` 呼叫生成 API（HTTP 層被 mock）
- **THEN** 請求送往 NVIDIA NIM endpoint、帶 `Authorization: Bearer <NVIDIA_API_KEY>`，回傳生成內容與 `provider_used == "nvidia"`

#### Scenario: 缺少金鑰時不可用
- **WHEN** 未設定 `NVIDIA_API_KEY` 而嘗試以 nvidia 生成
- **THEN** 拋出明確錯誤（訊息指出需設定 `NVIDIA_API_KEY`），不得靜默失敗

### Requirement: NVIDIA 任務分流預設模型
當使用者選擇 nvidia 供應商但未指定模型時，系統 SHALL 依生成任務自動選擇預設模型：投影片任務用 `nvidia/llama-3.1-nemotron-ultra-253b-v1`，Zettel 卡片任務用 `qwen/qwen3-next-80b-a3b-thinking`。使用者明確指定的 `--model` MUST 優先於任務分流預設。

#### Scenario: slides 任務預設模型
- **WHEN** 以 `provider="nvidia"` 生成投影片且未指定 model
- **THEN** 實際使用的模型為 `nvidia/llama-3.1-nemotron-ultra-253b-v1`

#### Scenario: zettel 任務預設模型
- **WHEN** 以 `provider="nvidia"` 生成 Zettel 卡片且未指定 model
- **THEN** 實際使用的模型為 `qwen/qwen3-next-80b-a3b-thinking`

#### Scenario: 明確 model 覆寫分流
- **WHEN** 以 `provider="nvidia"`、`model="meta/llama-3.1-8b-instruct"` 生成
- **THEN** 實際使用的模型為 `meta/llama-3.1-8b-instruct`（不套用任務分流預設）

