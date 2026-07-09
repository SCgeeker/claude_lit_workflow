# usage-guide Specification

## Purpose
TBD - created by archiving change add-guide-cli. Update Purpose after archive.
## Requirements
### Requirement: 導出工具使用說明
系統 SHALL 提供 `build_usage_guide() -> str`，回傳涵蓋 slides / zettel 工具用法、主要參數、可用風格/詳細度/語言、供應商與 NVIDIA 任務分流、範例指令的完整文字說明。風格/詳細度/語言清單 MUST 來自 `list_options()`（單一真相來源）。此函式 MUST NOT 直接寫入 stdout。

#### Scenario: 說明內容完整
- **WHEN** 呼叫 `build_usage_guide()`
- **THEN** 回傳字串同時包含 `uv run slides`、`uv run zettel`、7 種風格中至少 `modern_academic`、詳細度中至少 `standard`，以及至少一則範例指令

#### Scenario: 風格清單與 list_options 一致
- **WHEN** `list_options()` 的 slide_styles 含某風格鍵
- **THEN** 該風格鍵出現在 `build_usage_guide()` 的輸出中

### Requirement: 指定 LLM 建議指令
系統 SHALL 提供 `suggest_command(request_text, *, provider="auto", model=None) -> GuideResult`，將使用說明與使用者需求送給指定供應商的 LLM（重用既有多供應商呼叫），回傳建議的 CLI 指令文字與所用供應商。此為單次問答，MUST NOT 自動執行任何生成工具。

#### Scenario: 指定供應商回覆建議
- **WHEN** 以 `provider="anthropic"` 呼叫 `suggest_command("把 paper.pdf 做成教學風格投影片")`（LLM 呼叫被 mock）
- **THEN** 送給 LLM 的提示同時包含使用說明與該需求；回傳 `GuideResult`，其 `suggestion` 為 LLM 回覆、`provider_used == "anthropic"`

#### Scenario: 供應商不可用時報錯
- **WHEN** 指定的供應商無法呼叫（金鑰未設定或連線失敗）
- **THEN** 拋出 `ProviderUnavailableError`，`hint` 提示執行 `uv run setup`

#### Scenario: NVIDIA 問答用輕量模型
- **WHEN** 以 `provider="nvidia"` 且未指定 model 呼叫 `suggest_command`
- **THEN** 實際使用的模型為輕量模型（`meta/llama-3.1-8b-instruct`），而非 253B 大模型

### Requirement: guide CLI 入口
系統 SHALL 提供 `uv run guide` 命令。無需求參數時 MUST 印出 `build_usage_guide()` 的內容；帶需求參數時 MUST 以 `suggest_command` 回覆建議指令。CLI MUST 在非 UTF-8 終端重設 stdout 編碼（Windows 相容）。

#### Scenario: 無參數印出說明
- **WHEN** 執行 `guide`（無位置參數）
- **THEN** stdout 顯示使用說明，exit code 0

#### Scenario: 帶需求呼叫指定供應商
- **WHEN** 執行 `guide "需求" --provider anthropic`（suggest_command 被 mock）
- **THEN** 顯示 LLM 建議指令與所用供應商，exit code 0

#### Scenario: 供應商不可用回非零
- **WHEN** 執行 `guide "需求" --provider google` 但該供應商不可用
- **THEN** 顯示錯誤與 `uv run setup` 提示，exit code 1

