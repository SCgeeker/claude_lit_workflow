# Proposal: add-mcp-server

## Why

核心 API（change extract-core-api）已可程式化呼叫，但只有本機 CLI 能使用。將工具以 Model Context Protocol 曝露後，任何支援 MCP 的 LLM 平台（Claude Desktop / Claude Code / Cursor / ChatGPT 等，以及任何可透過 HTTP 串接的服務）都能直接呼叫投影片與 Zettel 卡片生成，不受平台限制。

## What Changes

- 新增 `src/mcp_server/` 套件：基於官方 MCP Python SDK（FastMCP）的伺服器
  - **Tools**：`generate_slides`、`generate_zettel`、`check_setup`、`list_options`、`read_output`
  - **Resources**：prompt 模板（`template://`）、風格目錄（`styles://`）、自訂需求檔與脫敏設定（`config://`）
  - **Prompts**：`slides-prompt`、`zettel-prompt`（渲染完成的完整提示詞，供呼叫端 LLM 自行生成的第二路徑）
- 傳輸：stdio（預設，本機 client）與 Streamable HTTP（`--transport http`，遠端平台）
- 生成模式：伺服器端生成——工具內部沿用核心 API 呼叫已設定的 LLM；API key 只存在伺服器行程，不經協定傳輸
- long-running 生成以 worker thread 執行並回報 MCP progress notification
- `pyproject.toml` 新增 `mcp>=1.9.0` 相依與 `mcp-server` 入口
- `README.md` 補 MCP 註冊與啟動說明

## Capabilities

### New Capabilities

- `mcp-server`: MCP 伺服器的行為契約——tools / resources / prompts 三類 primitive 的清單與 schema、傳輸模式、進度通知、錯誤回報、金鑰隔離、輸出檔案存取邊界

### Modified Capabilities

（無——本 change 只新增 MCP 介面層，核心 API 行為不變）

## Impact

- **新增**：`src/mcp_server/__init__.py`、`server.py`、`__main__.py`；`tests/unit/test_mcp_server.py`
- **修改**：`pyproject.toml`（`mcp>=1.9.0`、`[project.scripts] mcp-server`）、`README.md`
- **相依**：新增 `mcp`（官方 SDK，含 FastMCP 與 Streamable HTTP）
- **相容性**：CLI 與核心 API 不受影響；MCP 的 `generate_zettel` 預設 `add_to_kb=False`（比 CLI 保守，避免遠端呼叫意外寫入本機知識庫）
