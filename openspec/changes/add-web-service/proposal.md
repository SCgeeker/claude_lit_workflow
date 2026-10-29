# Proposal: add-web-service

## Why

目前驅動方式都綁在本機：`uv run slides/zettel`、Obsidian QuickAdd wrapper（`exec("uv run …")`）、
本機 MCP server。使用者希望：

1. 把工具**部署到雲端伺服器**，從任何裝置（含手機、沒裝 uv 的電腦、學生的電腦）使用；
2. 以**網頁 UI** 上傳文章檔案、輸入提示詞，讓 LLM 依模板產出投影片與卡片；
3. 產出能回到筆記 App（Obsidian 等）。

核心 API（`claude_lit.api`）已經是 UI 中立的：pydantic Request/Result、`ProgressEvent` 進度回報、
`LitWorkflowError` 附修復提示。缺的是**一層可遠端呼叫、可上傳檔案、可處理長時任務的服務層**。

## What Changes

- **新增 REST + SSE 服務層 `claude_lit.web`**（FastAPI）：
  - 工作（job）模型：上傳 → 建立 job → 背景執行 → 以 SSE 推送 `ProgressEvent` → 下載結果
  - 端點：`POST /api/jobs`、`GET /api/jobs/{id}`、`GET /api/jobs/{id}/events`（SSE）、
    `GET /api/jobs/{id}/files`、`GET /api/jobs/{id}/download`（zip）、`GET /api/options`、
    `POST /api/plan`（自然語言 → 參數提案）、`GET /api/health`
  - 每個 job 有獨立工作目錄（上傳檔 + 輸出），不寫共用 `output/`
- **新增網頁 UI**（同一行程以靜態檔提供，無前端建置步驟）：
  - 上傳檔案（PDF、以及 add-media-templates 之後的 txt/md/srt/vtt/epub）或貼上 URL
  - 選擇產出（投影片 / 卡片 / 兩者）、媒體類型、風格、詳細程度、語言
  - 提示詞欄位：作為 `custom_requirements` 附加；或切換「自然語言模式」，由 LLM 提出參數、使用者確認後執行
  - 即時進度、Markdown 預覽、單檔與 zip 下載
- **資源解析支援 per-job 覆蓋層**：`resolve_resource` 新增可選的 `overlay_dir`（以 contextvar 傳遞），
  讓同一行程中並行的 job 各自使用使用者上傳的 `custom_slides.md` / 模板，而不靠 `chdir`。
- **新增 CLI 入口** `uv run web`（`--host`、`--port`、`--workers`），以及 `Dockerfile` + `compose.yaml`
  範例（含 Caddy 反向代理與 HTTPS）。
- **選配：遠端模式的 QuickAdd wrapper**——QuickAdd 以 Obsidian `requestUrl` 呼叫同一套 REST API，
  把結果直接寫進 vault；本機沒裝 uv 也能用。
- **既有 MCP server 補強（同一部署共用）**：Streamable HTTP 加上 bearer token 驗證；
  `generate_zettel` 補上 `content` 參數，讓無法傳路徑的遠端 MCP client 可直接送文字。

## Capabilities

### New Capabilities

- `web-service`：REST/SSE job API、上傳與工作目錄隔離、驗證、資源上限、網頁 UI、部署設定。

### Modified Capabilities

- `cli`：新增 `uv run web`；資源解析順序新增 per-job 覆蓋層（最高優先，僅服務模式使用）。
- `mcp-server`：HTTP 傳輸加 bearer token；`generate_zettel` 新增 `content` 參數。

## Impact

- **新增**：`src/claude_lit/web/`（`app.py`、`jobs.py`、`storage.py`、`auth.py`、`static/`）、
  `src/claude_lit/cli/web.py`、`deploy/Dockerfile`、`deploy/compose.yaml`、`deploy/Caddyfile`、
  `tests/unit/test_web_*.py`
- **修改**：`resource_loader.py`（overlay contextvar）、`pyproject.toml`（`web` optional extra 與 entry point）、
  `api/models.py`（`ZettelRequest.content`）、`mcp_server/`（token 驗證）
- **相依**：選配 extra `web = ["fastapi", "uvicorn[standard]", "python-multipart", "sse-starlette"]`；
  核心安裝不受影響
- **相容性**：CLI、QuickAdd（本機模式）、stdio MCP 行為完全不變；`overlay_dir` 未設定時解析順序與現行相同
- **依賴另一個 change**：上傳逐字稿 / EPUB 需要 `add-media-templates` 的 `text` 來源；
  在它完成前，Web UI 只開放 PDF 與 URL
- **Non-Goals**：多租戶 SaaS（計費、組織管理）；瀏覽器端模板編輯器（第一版只開放上傳覆蓋檔）；
  知識庫 / 向量嵌入（服務模式固定 `add_to_kb=False`，與 MCP 預設一致）；ASR 音訊轉錄
