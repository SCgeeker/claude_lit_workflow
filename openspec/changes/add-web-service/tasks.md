# Tasks: add-web-service

## 1. 共用狀態拆除（先做，CLI/MCP 也受益）

- [ ] 1.1 失敗測試 `tests/unit/test_resources.py` 增補：設定 overlay contextvar 時 overlay 優先於 cwd；未設定時順序不變；ThreadPool 以 `copy_context().run` 提交時 worker 可見 overlay
- [ ] 1.2 `resource_loader.py`：`overlay_dir` contextvar 與 `use_overlay(path)` context manager
- [ ] 1.3 確認 `generate_slides` / `generate_zettel` 在給定 `output_path` / `output_dir` 時不寫入 cwd 的 `output/`（補測試）

## 2. Job 核心（不依賴 HTTP）

- [ ] 2.1 失敗測試 `tests/unit/test_web_jobs.py`（核心 API mock）：建立 job → 狀態轉移；進度事件依序可讀並可回放；失敗時保存 `hint`；`kinds=["slides","zettel"]` 會把投影片內容傳給 zettel 的 `slides_content`；並行上限生效
- [ ] 2.2 實作 `web/jobs.py`（JobRunner、JobStore 檔案版）、`web/storage.py`（job 目錄、上傳存檔、zip、TTL 清理）

## 3. HTTP 層

- [ ] 3.1 失敗測試 `tests/unit/test_web_api.py`（FastAPI TestClient）：各端點；未帶 token → 401；上傳超限 → 413；非白名單類型 → 415；下載路徑穿越 → 404；回應不含金鑰
- [ ] 3.2 實作 `web/app.py`、`web/auth.py`；SSE 端點；`/api/options` 重用 `list_options`
- [ ] 3.3 非 localhost 綁定且無驗證設定時拒絕啟動
- [ ] 3.4 掛載既有 FastMCP Streamable HTTP 至 `/mcp`，套用同一 token 驗證

## 4. 網頁 UI

- [ ] 4.1 `web/static/index.html`（無建置步驟）：上傳／URL、參數表單（選項來自 `/api/options`）、提示詞欄、進度條（SSE）、Markdown 預覽、下載
- [ ] 4.2 手機寬度可用；中英文介面字串

## 5. 部署

- [ ] 5.1 `pyproject.toml`：`web` optional extra、`web = "claude_lit.cli.web:main"` entry point
- [ ] 5.2 `deploy/Dockerfile`、`deploy/compose.yaml`、`deploy/Caddyfile`、`deploy/README.md`（VPS 步驟、環境變數清單）
- [ ] 5.3 實機冒煙：VPS 上以手機上傳 PDF → 下載 zip → 匯入 Obsidian

## 6. P2 擴充

- [ ] 6.1 `/api/plan`：結構化參數提案（pydantic 驗證，非法值回報）
- [ ] 6.2 QuickAdd 遠端模式 wrapper 範例與 `workflow-config.json` 欄位說明
- [ ] 6.3 `ZettelRequest.content` 與 MCP `generate_zettel(content=...)`
- [ ] 6.4 README / README.en 加入「雲端部署」段落
