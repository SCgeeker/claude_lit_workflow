# Tasks: add-web-service

## 1. 共用狀態拆除（先做，CLI/MCP 也受益）

- [x] 1.1 失敗測試 `tests/unit/test_resources.py` 增補：設定 overlay contextvar 時 overlay 優先於 cwd；未設定時順序不變；ThreadPool 以 `copy_context().run` 提交時 worker 可見 overlay
- [x] 1.2 `resource_loader.py`：`overlay_dir` contextvar 與 `use_overlay(path)` context manager
- [x] 1.3 確認 `generate_slides` / `generate_zettel` 在給定 `output_path` / `output_dir` 時不寫入 cwd 的 `output/`（補測試）；新增 `ZettelRequest.output_root`（保留預設命名、改根目錄）

## 2. Job 核心（不依賴 HTTP）

- [x] 2.1 失敗測試 `tests/unit/test_web_jobs.py`（核心 API mock）：建立 job → 狀態轉移；進度事件依序可讀並可回放；失敗時保存 `hint`；`kinds=["slides","zettel"]` 會把投影片內容傳給 zettel 的 `slides_content`；並行上限生效
- [x] 2.2 實作 `web/jobs.py`（JobRunner、JobStore 檔案版）、`web/storage.py`（job 目錄、上傳存檔、zip、TTL 清理）

## 3. HTTP 層

- [x] 3.1 失敗測試 `tests/unit/test_web_api.py`（Starlette TestClient）：各端點；未帶 token → 401；上傳超限 → 413；非白名單類型 → 415；下載路徑穿越 → 404；回應不含金鑰
- [x] 3.2 實作 `web/app.py`、`web/auth.py`；SSE 端點；`/api/options` 重用 `list_options`
- [x] 3.3 非 localhost 綁定且無驗證設定時拒絕啟動
- [x] 3.4 掛載既有 FastMCP Streamable HTTP 至 `/mcp`，套用同一 token 驗證

## 4. 網頁 UI

- [x] 4.1 `web/static/index.html`（無建置步驟）：上傳／URL、參數表單（選項來自 `/api/options`）、提示詞欄、進度條（SSE）、Markdown 預覽、下載
- [x] 4.2 手機寬度可用；中英文介面字串

## 5. 部署

- [x] 5.1 `pyproject.toml`：`web` optional extra、`web = "claude_lit.cli.web:main"` entry point
- [x] 5.2 `deploy/Dockerfile`、`deploy/compose.yaml`、`deploy/Caddyfile`、`deploy/README.md`（VPS 步驟、環境變數清單）——本機已 build 並執行容器（無驗證拒絕啟動、health、401、job 失敗訊息、healthcheck healthy、非 root）；`docker compose config` 與 `caddy validate` 通過
- [ ] 5.3 實機冒煙：VPS 上以手機上傳 PDF → 下載 zip → 匯入 Obsidian —— **待辦**：需要網域、主機與 LLM 金鑰；本機已以 Playwright 跑過桌機／手機寬度的完整 UI 流程（生成以假實作代替）

## 6. P2 擴充

- [x] 6.1 `/api/plan`：結構化參數提案（pydantic 驗證，非法值回報）
- [x] 6.2 QuickAdd 遠端模式 `examples/quickadd/lit_remote.js`（設定改用 QuickAdd 腳本設定而非 `workflow-config.json`）；核心流程已在 Node 對本機服務測過，Obsidian 內未實測
- [x] 6.3 `ZettelRequest.content` 與 MCP `generate_zettel(content=...)`
- [x] 6.4 README / README.en 加入「雲端部署」段落

## 7. 實作中追加

- [x] 7.1 錯誤訊息、警告與進度訊息回傳前移除金鑰（部分 LLM SDK 錯誤訊息會回顯金鑰片段）
- [x] 7.2 `mcp-server --transport http` 設 `WEB_API_TOKEN` 時亦需 bearer token（`_run_http_with_token`）
- [x] 7.3 服務重啟時，上次未完成的 job 標為 failed（不留下永遠 running 的工作）
- [x] 7.4 進階設定可上傳 per-job 覆蓋檔——僅限 `media_profiles.yaml`（yaml.safe_load、只當資料注入）；Jinja 模板不開放，因未沙箱化渲染等同遠端執行程式碼
- [x] 7.5 `citation_format` 只允許 `{欄位名}`（可經覆蓋檔修改，禁止屬性／索引存取）；`custom_file` 限 .md / .txt；覆蓋檔上限 256 KB
