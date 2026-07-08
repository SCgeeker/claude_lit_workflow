# Tasks: add-mcp-server

## 1. 相依與骨架

- [x] 1.1 `uv add "mcp>=1.9.0"`；確認 anyio 版本相容
- [x] 1.2 建立 `src/mcp_server/`（`__init__.py`、`server.py` FastMCP 實例、`__main__.py` 啟動器）
- [x] 1.3 撰寫失敗測試 `tests/unit/test_mcp_server.py`：in-memory session 的 `list_tools` 含五個 tool 且 schema 欄位齊全（TDD red）

## 2. Tools

- [x] 2.1 實作 `check_setup`、`list_options`（同步、無 LLM 呼叫）+ 測試綠
- [x] 2.2 失敗測試：`generate_slides` structured output、壞參數 isError、progress notification
- [x] 2.3 實作 `generate_slides`、`generate_zettel`（anyio.to_thread + progress 橋接 + LitWorkflowError → tool error 含 hint；zettel 預設 add_to_kb=False）
- [x] 2.4 失敗測試 + 實作 `read_output`（output/ 邊界、`..` 穿越拒絕、max_chars 截斷）

## 3. Resources 與 Prompts

- [x] 3.1 失敗測試：`list_resources` / `read_resource` 六個 URI；`config://settings` 不含金鑰
- [x] 3.2 實作六個 resources（模板原文、styles yaml、custom_*.md、脫敏 settings）
- [x] 3.3 失敗測試 + 實作 prompts：`slides-prompt`、`zettel-prompt`（重用 api.prompts.render_*）

## 4. 傳輸與收尾

- [x] 4.1 `__main__.py`：`--transport stdio|http --host --port`；stdio 淨空防護；pyproject 加 `mcp-server` script
- [x] 4.2 stdout 淨空回歸測試（tool 呼叫期間 capsys.out 為空）
- [x] 4.3 README 補 MCP 註冊說明（claude mcp add / HTTP 啟動 / timeout 建議）
- [x] 4.4 全測試綠；手動驗收：`uv run mcp-server --help`、MCP Inspector 或 Claude Code 實測 stdio
