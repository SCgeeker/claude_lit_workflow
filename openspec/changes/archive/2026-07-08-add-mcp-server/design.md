# Design: add-mcp-server

## Context

核心 API（`src/api/`）已提供 pydantic 介面、型別化例外（含 hint）、ProgressEvent callback，且核心層 stdout 已淨空——MCP 化的前置條件皆已就緒。目標是在其上加一層薄的 MCP 介面，不重複任何編排邏輯。

## Goals / Non-Goals

**Goals:**
- 官方 MCP Python SDK（FastMCP）實作 tools / resources / prompts 三類 primitive
- stdio + Streamable HTTP 雙傳輸，一套程式碼
- 伺服器端生成（API key 隔離於伺服器行程）；prompts 額外提供呼叫端自行生成的第二路徑
- in-memory client session 測試（不需真實傳輸）

**Non-Goals:**
- 不做 job queue / 非同步任務輪詢（單次 tool call 內完成，配 progress notification）
- 不做 MCP resources 的動態註冊（每次生成的輸出檔不註冊為 resource；用 `read_output` tool 存取）
- 不做認證 / 多租戶（HTTP 模式假設可信網路；正式部署的存取控制留待後續 change）
- `save_zettel_output` tool（呼叫端生成內容的解析存檔）列為未來擴充，本版不實作——先觀察 prompts 路徑的實際使用情況

## Decisions

1. **模組命名 `src/mcp_server/`**（不可用 `mcp/`）：避免遮蔽官方 SDK 的 `mcp` 套件。
2. **tool 參數攤平為個別欄位**而非傳整個 pydantic model：攤平的 inputSchema 對呼叫端 LLM 更易理解；內部組回 `SlideRequest`/`ZettelRequest` 重用驗證。pydantic `ValidationError` 由 FastMCP 轉為 tool error。
3. **同步核心 API 用 `anyio.to_thread.run_sync` 包**：LLM 呼叫阻塞可達 300s；worker thread 避免卡住事件迴圈。ProgressEvent 以 thread-safe 方式橋接：callback 將事件放入 list，或用 `anyio.from_thread.run_sync` 呼叫 `ctx.report_progress`。實作採後者（即時通知）。
4. **錯誤策略**：捕捉 `LitWorkflowError`，重新拋出 `Exception(f"{message}（提示：{hint}）")` 讓 FastMCP 標記 isError；不讓伺服器崩潰。
5. **`read_output` 路徑防護**：`Path(path).resolve()` 後檢查 `is_relative_to(OUTPUT_DIR.resolve())`；拒絕即拋錯。
6. **`config://settings` 脫敏**：只回傳 settings.yaml 的白名單欄位（pdf、llm 的 provider/model 名稱），不透傳原始檔案。
7. **啟動器**：`__main__.py` 用 argparse 解析 `--transport stdio|http --host --port`；stdio 模式先 `load_env_file()` 再 `mcp.run(transport="stdio")`；HTTP 用 `transport="streamable-http"` 並設定 `mcp.settings.host/port`。

## Risks / Trade-offs

- [client tool timeout < 300s 生成時間] → progress notification 讓支援的 client 重置 timeout；README 註明建議 timeout ≥ 360s
- [第三方庫仍可能 print 到 stdout] → stdio 啟動時以 `contextlib.redirect_stdout(sys.stderr)` 包住 lifespan 外的初始化；測試以 capsys 斷言 tool 呼叫期間 stdout 淨空
- [in-memory 測試與真實 stdio 行為差異] → 手動驗收補：`claude mcp add` 實測 + MCP Inspector 驗 HTTP
- [mcp SDK 版本 API 變動] → 鎖 `mcp>=1.9.0`；測試用官方 `create_connected_server_and_client_session`

## Migration Plan

純新增，無遷移。回滾＝刪除 `src/mcp_server/` 與 pyproject 兩行。
