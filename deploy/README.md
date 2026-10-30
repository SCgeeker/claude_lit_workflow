# 雲端部署（網頁服務）

把 Claude Lit Workflow 部署到一台伺服器，從任何裝置的瀏覽器上傳文章、選模板、由伺服器端 LLM 生成投影片與卡片。
設計與取捨見 `openspec/changes/add-web-service/design.md`。

## 本機試用

```bash
uv sync --extra web
uv run web                      # http://127.0.0.1:8000（本機不需金鑰）
```

## VPS + Docker Compose + Caddy（推薦）

需求：一台 Linux 主機（≥1 vCPU / 2 GB RAM）、已安裝 Docker、一個網域（A 記錄指向主機）。

```bash
git clone https://github.com/SCgeeker/claude_lit_workflow.git
cd claude_lit_workflow/deploy
cp ../.env.example .env
```

編輯 `deploy/.env`：

| 變數 | 必填 | 說明 |
|------|------|------|
| `LIT_DOMAIN` | ✅ | 服務網域，如 `lit.example.com`（Caddy 自動申請 HTTPS 憑證） |
| `WEB_API_TOKEN` | ✅* | 存取金鑰，`python -c "import secrets; print(secrets.token_urlsafe(32))"` 產生 |
| `GOOGLE_API_KEY` 等 | ✅ | 至少一個 LLM 供應商金鑰（只存在伺服器，不會回傳給瀏覽器） |
| `WEB_TRUST_PROXY_AUTH` | | 改用 Caddy `basic_auth` 登入時設 `1`（*此時可不設 `WEB_API_TOKEN`） |
| `WEB_MAX_UPLOAD_MB` / `WEB_MAX_WORKERS` / `WEB_RETENTION_DAYS` / `WEB_DAILY_JOB_LIMIT` | | 上傳上限、並行數、保留天數、每日工作上限 |

```bash
docker compose up -d --build
docker compose logs -f lit       # 確認啟動
```

瀏覽 `https://lit.example.com/`，按右上「金鑰」輸入 `WEB_API_TOKEN`（只存在該瀏覽器）。

> 未設定任何驗證時，服務拒絕以 `0.0.0.0` 啟動（fail-closed）。

### 自訂模板

把 repo 的 `templates/` 掛進容器即生效（cwd 覆蓋機制）：在 `compose.yaml` 的 `lit.volumes` 取消註解
`- ../templates:/app/templates:ro`（由管理者掛載）。單次工作可在網頁「進階設定 → 覆蓋媒體設定檔」上傳自訂的
`media_profiles.yaml`；Jinja 模板不開放從網頁上傳——模板未經沙箱渲染，上傳等同在伺服器執行程式碼。

## 其他平台

| 平台 | 注意事項 |
|------|---------|
| Google Cloud Run 等容器平台 | 容器檔案系統是暫存的：`WEB_DATA_DIR` 須掛持久儲存；長時生成需確認請求逾時與「僅在請求期間配置 CPU」的設定，背景工作才不會被凍結 |
| Hugging Face Spaces（Docker Space） | 預設公開，請設為 private；金鑰放 Secrets；免費硬體會休眠且儲存非持久 |
| 學校／實驗室內網 | 搭配 VPN 或 Tailscale，可只在內網開放 |

各平台資源上限、逾時與價格變動快，部署前請以官方文件為準。

## 其他入口（共用同一部署與金鑰）

- **REST API**：`POST /api/jobs`（multipart：`file` + `params` JSON）→ `GET /api/jobs/{id}/events`（SSE 進度）→ `GET /api/jobs/{id}/download`（zip）
- **Obsidian QuickAdd 遠端模式**：`examples/quickadd/lit_remote.js`（本機不需安裝 uv）
- **MCP**：`https://lit.example.com/mcp`（Streamable HTTP，`Authorization: Bearer <WEB_API_TOKEN>`）

```bash
curl -H "Authorization: Bearer $TOKEN" \
     -F file=@ep42.srt \
     -F 'params={"kinds":["slides","zettel"],"media_type":"podcast","source_meta":{"show":"科學新聞"}}' \
     https://lit.example.com/api/jobs
```

## 資料與安全

- 每個工作的上傳檔與輸出存於 `WEB_DATA_DIR/jobs/{id}/`，**保留期（預設 7 天）後連同原始檔自動刪除**。
  教科書、專書多受著作權保護：服務只供上傳者本人取用結果，不提供公開分享連結。
- 服務模式不寫入伺服器知識庫（`add_to_kb=False`）。
- 錯誤訊息回傳前會移除金鑰字串。
