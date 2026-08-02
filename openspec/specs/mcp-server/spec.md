# mcp-server Specification

## Purpose
TBD - created by archiving change add-mcp-server. Update Purpose after archive.
## Requirements
### Requirement: MCP 工具可被發現與呼叫
伺服器 SHALL 曝露五個 tools：`generate_slides`、`generate_zettel`、`check_setup`、`list_options`、`read_output`，各 tool 的 inputSchema MUST 定義必要欄位與型別；生成類 tool MUST 回傳結構化結果（檔案絕對路徑清單 + metadata），MUST NOT 回傳完整檔案內容。

#### Scenario: 工具清單可被發現
- **WHEN** MCP client 呼叫 `list_tools`
- **THEN** 回傳五個 tool，`generate_slides` 的 inputSchema 含 topic/pdf/url、style、detail、language、slide_count、output_format 欄位

#### Scenario: 呼叫 generate_slides 回傳結構化結果
- **WHEN** client 以有效參數呼叫 `generate_slides`（核心 API 被 mock）
- **THEN** 回傳的 structuredContent 含 `output_files`（絕對路徑清單）、`slide_count`、`provider_used`

#### Scenario: generate_zettel 預設不入庫
- **WHEN** client 呼叫 `generate_zettel` 未指定 `add_to_kb`
- **THEN** 傳給核心 API 的 request 中 `add_to_kb == False`

### Requirement: 錯誤以 tool error 回報且附修復提示
tool 執行失敗時伺服器 MUST 回傳 `isError=true` 的結果，訊息 MUST 包含核心 API 例外的 `hint`（如有）；伺服器行程 MUST NOT 因單一 tool 失敗而終止。

#### Scenario: 來源不存在
- **WHEN** client 以不存在的 PDF 路徑呼叫 `generate_slides`
- **THEN** 回傳 `isError=true`，訊息含錯誤描述與修復提示，且後續 tool 呼叫仍可正常執行

### Requirement: 長時生成回報進度
生成類 tool MUST 在 worker thread 執行（不阻塞事件迴圈）；當 client 提供 progressToken 時，伺服器 SHALL 將核心 API 的 ProgressEvent 轉為 MCP progress notification。

#### Scenario: 進度通知
- **WHEN** client 帶 progressToken 呼叫 `generate_zettel`（核心 API 被 mock 且發出進度事件）
- **THEN** client 收到至少一次 progress notification，最終收到結構化結果

### Requirement: MCP Resources 曝露模板與設定
伺服器 SHALL 曝露唯讀 resources：`template://prompts/journal-club`、`template://prompts/zettelkasten`（原始 jinja2 模板）、`styles://academic-styles`（風格目錄 YAML）、`config://custom-slides`、`config://custom-zettel`（自訂需求檔）、`config://settings`（脫敏設定）。`config://settings` 的內容 MUST NOT 包含任何 API key 或秘密值。

#### Scenario: 資源清單與讀取
- **WHEN** client 呼叫 `list_resources` 後逐一 `read_resource`
- **THEN** 六個 URI 皆可讀且內容非空

#### Scenario: 設定資源脫敏
- **WHEN** client 讀取 `config://settings`
- **THEN** 回傳內容不含 `API_KEY`、`api_key` 值或任何金鑰字串

### Requirement: MCP Prompts 提供渲染完成的提示詞
伺服器 SHALL 曝露 `slides-prompt` 與 `zettel-prompt` 兩個 prompts，接受來源與選項參數；`get_prompt` MUST 回傳以 jinja2 渲染完成的完整提示詞（含抽取的來源內容與風格指示），供呼叫端 LLM 自行生成內容。

#### Scenario: 取得 zettel prompt
- **WHEN** client 呼叫 `get_prompt("zettel-prompt", {"pdf_path": ..., "detail": "standard"})`
- **THEN** 回傳訊息含渲染後的論文內容與 12 張卡片的生成指示，且不含任何 API key

### Requirement: 輸出檔案存取邊界
`read_output` tool MUST 只允許讀取專案 `output/` 目錄下的檔案；任何指向其外的路徑（含 `..` 穿越）MUST 被拒絕並回傳錯誤。

#### Scenario: 路徑穿越被拒
- **WHEN** client 呼叫 `read_output` 且 path 為 `../.env`
- **THEN** 回傳 `isError=true`，且檔案內容未被讀取

#### Scenario: 正常讀取輸出
- **WHEN** client 呼叫 `read_output` 且 path 指向 output/ 下存在的 Markdown 檔
- **THEN** 回傳檔案文字內容（超過上限時截斷並標示）

### Requirement: 傳輸模式與金鑰隔離
伺服器 MUST 支援 stdio（預設）與 Streamable HTTP（`--transport http --host --port`）兩種啟動方式；API key MUST 只從伺服器行程的環境（.env）載入，MUST NOT 出現在任何 tool 結果、resource 內容或 prompt 訊息中。stdio 模式下伺服器 MUST NOT 向 stdout 寫入 JSON-RPC 以外的內容。

#### Scenario: stdio 淨空
- **WHEN** 以 in-memory session 執行任一 tool 呼叫
- **THEN** 過程中 stdout 無 JSON-RPC 以外的輸出（核心層訊息只進 logging/stderr）

### Requirement: generate_zettel 工具曝露 grounding 參數
MCP `generate_zettel` tool 的 inputSchema MUST 新增選填布林參數 `ground`（預設 True）。未指定時 MUST 啟用 grounding gate；`ground=false` 時 MUST 關閉。此參數僅透傳至核心 `ZettelRequest.ground`。

#### Scenario: 未指定 ground 預設啟用
- **WHEN** client 呼叫 `generate_zettel` 未指定 `ground`（核心 API 被 mock）
- **THEN** 核心 API 收到的 `ZettelRequest.ground` 為 True

#### Scenario: ground=false 關閉 grounding
- **WHEN** client 呼叫 `generate_zettel` 帶 `ground=false`
- **THEN** 核心 API 收到的 `ZettelRequest.ground` 為 False

