# provider-setup Spec Delta

## ADDED Requirements

### Requirement: 供應商偵測 API
系統 SHALL 提供 `check_providers() -> ProviderReport`，逐一檢查 Google Gemini、OpenAI、Anthropic、Ollama、OpenRouter 的可用性，並回傳建議供應商。此 API MUST NOT 直接寫入 stdout。

#### Scenario: 僅一供應商可用
- **WHEN** 環境中僅 `GOOGLE_API_KEY` 有效（其餘未設定或為佔位字串）
- **THEN** 回傳的 `providers` 中 google 標記 `available=True` 且附模型名稱訊息，其餘 `available=False` 且附原因；`recommended == "google"`

#### Scenario: 全部不可用
- **WHEN** 無任何供應商可用
- **THEN** `recommended` 為 None，各供應商附設定指引訊息（如「未設定 GOOGLE_API_KEY」）

#### Scenario: 佔位 key 視為未設定
- **WHEN** API key 值含 `your-` 佔位模式
- **THEN** 該供應商 `available=False`，原因為未設定

### Requirement: 選項目錄 API
系統 SHALL 提供 `list_options() -> OptionCatalog`，回傳風格、詳細程度、語言的完整目錄（鍵值與繁中說明）。目錄內容 MUST 來自 `templates/styles/academic_styles.yaml`，MUST NOT 於 CLI 硬編碼。

#### Scenario: 目錄完整性
- **WHEN** 呼叫 `list_options()`
- **THEN** 回傳含 7 種投影片風格、5 種詳細程度、3 種語言，每項附非空說明文字

#### Scenario: CLI 與 API 目錄一致
- **WHEN** CLI 執行 `--list-options`
- **THEN** 顯示內容來自 `list_options()` 的回傳值（單一真相來源）
