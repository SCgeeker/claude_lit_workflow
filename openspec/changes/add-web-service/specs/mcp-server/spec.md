# mcp-server Spec Delta

## ADDED Requirements

### Requirement: HTTP 傳輸的 token 驗證
以 Streamable HTTP 啟動（含掛載於網頁服務 `/mcp`）且設定 `WEB_API_TOKEN` 時，伺服器 MUST 拒絕未帶有效 bearer token 的請求（`401`）。stdio 模式不受影響。

#### Scenario: 無 token 被拒
- **WHEN** 已設定 `WEB_API_TOKEN`，client 未帶 token 連線 HTTP 端點
- **THEN** 回傳 `401`，不執行任何 tool

### Requirement: generate_zettel 接受直接內容
`generate_zettel` tool MUST 新增選填 `content`（字串）參數，作為 `pdf` / `url` 之外的內容來源（三者互斥）；`content` 來源 MUST 同樣經過 grounding gate，並以 `content` 本身作為比對原文。

#### Scenario: 以 content 生成
- **WHEN** client 以 `content="..."`、`cite_key="X-2025"` 呼叫 `generate_zettel`（核心 API 被 mock）
- **THEN** 核心 API 收到 `ZettelRequest.content` 等於該字串，且 `pdf`、`url` 為空
