# mcp-server Spec Delta

## ADDED Requirements

### Requirement: generate_zettel 工具曝露 grounding 參數
MCP `generate_zettel` tool 的 inputSchema MUST 新增選填布林參數 `ground`（預設 True）。未指定時 MUST 啟用 grounding gate；`ground=false` 時 MUST 關閉。此參數僅透傳至核心 `ZettelRequest.ground`。

#### Scenario: 未指定 ground 預設啟用
- **WHEN** client 呼叫 `generate_zettel` 未指定 `ground`（核心 API 被 mock）
- **THEN** 核心 API 收到的 `ZettelRequest.ground` 為 True

#### Scenario: ground=false 關閉 grounding
- **WHEN** client 呼叫 `generate_zettel` 帶 `ground=false`
- **THEN** 核心 API 收到的 `ZettelRequest.ground` 為 False
