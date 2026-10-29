# Design: add-web-service

## 1. 方案比較

目標：雲端部署 + 網頁輸入提示詞與檔案 + LLM 依模板產出。共評估四條路線：

| 方案 | 描述 | 優點 | 缺點 |
|------|------|------|------|
| **A. 自建 REST 服務 + 輕量網頁（採用）** | FastAPI 包裝 `claude_lit.api`，靜態 HTML/JS 前端 | 完整掌控模板、grounding、輸出目錄；同一 API 可服務網頁、QuickAdd、腳本 | 需自己做驗證、job 管理 |
| B. Gradio / Streamlit 單檔 app | 以 Python 元件拼 UI | 一天內可用；Hugging Face Spaces 原生支援 | UI 與 API 綁死，QuickAdd 等其他 client 難重用；長時任務與多人隔離要另外處理 |
| C. 遠端 MCP + 現成聊天 UI | 部署現有 `mcp-server --transport http`，以 Claude 網頁版、LibreChat、Open WebUI 等支援 MCP 的平台當 UI | 幾乎零前端工作；對話式體驗 | 聊天平台上傳的檔案通常**不會**傳給遠端 MCP tool（tool 只拿得到參數）；需要公開 HTTPS + 驗證；模板與參數由聊天 LLM 轉述，可控性較低 |
| D. 聊天平台的 function/pipeline 外掛 | 如 Open WebUI Functions | 與 C 類似但能拿到上傳檔 | 綁定單一平台的外掛 API |

**結論**：以 **A 為主幹**——REST job API 是可重用的核心資產（網頁 UI、遠端 QuickAdd、批次腳本都用它）。
**C 作為同一部署的附加入口**（成本低：既有 MCP server 補上 token 驗證與 `content` 參數即可）。
B 可作為 1–2 天的**概念驗證**，驗證完即以 A 取代，不進主線。

## 2. 架構

```
瀏覽器 / 手機 ─┐
QuickAdd 遠端 ─┼─HTTPS─► Caddy（TLS、Basic Auth 或 SSO）─► uvicorn: claude_lit.web.app
MCP client ────┘                                            │
                                                            ├─ /           靜態 UI
                                                            ├─ /api/*      REST + SSE
                                                            └─ /mcp        既有 FastMCP（Streamable HTTP，掛載）
                                                                  │
                                    JobRunner（ThreadPool, max_workers=N）
                                                                  │
                          claude_lit.api.generate_slides / generate_zettel（同步、不修改）
                                                                  │
                                       LLM providers（API key 只在伺服器環境變數）
                                                                  │
                     /data/jobs/{job_id}/{input/, output/, overlay/, job.json}
```

## 3. Job 模型

```
POST /api/jobs  (multipart)
  file?:        上傳檔（PDF；add-media-templates 後加 txt/md/srt/vtt/epub）
  url?:         或網址
  params:       JSON —— {kinds: ["slides","zettel"], media_type, style, detail, language,
                          slide_count, custom_requirements, provider, model, cite_key, source_meta}
  custom_file?: 選填的 custom_slides.md / custom_zettel.md 覆蓋檔
→ 202 {job_id, status: "queued"}
```

- 狀態：`queued → running → succeeded | failed | cancelled`；`job.json` 存參數、狀態、結果摘要
  （`SlideResult` / `ZettelResult` 序列化）、錯誤訊息與 `hint`。
- `kinds=["slides","zettel"]` 時依序執行，並把投影片 Markdown 當作 zettel 的 `slides_content`
  （等同 CLI 的 `--slides-file` 流程）。
- 進度：`progress_cb` 把 `ProgressEvent` 推入 job 的 asyncio queue；`GET /api/jobs/{id}/events`
  以 SSE 串流，斷線重連時先回放已發生的事件。
- 並行：同步核心 API 在 ThreadPool 中執行（與 MCP server 的 `_run_generation` 同一模式）；
  `max_workers` 預設 2，超出時排隊——LLM 呼叫是 I/O-bound，但限制並行可控制費用與 provider rate limit。
- 取消：job 執行前可取消；執行中僅標記，於下一個進度階段檢查並中止。

## 4. 兩個必須先解決的共用狀態

現有程式假設「一個行程 = 一個使用者 = 一個 cwd」。服務模式下必須拆除：

| 共用狀態 | 現況 | 服務模式的處理 |
|---------|------|--------------|
| 輸出目錄 | `OUTPUT_DIR = Path.cwd() / "output"` | 每個 job 明確傳 `SlideRequest.output_path` / `ZettelRequest.output_dir`（欄位已存在） |
| 資源覆蓋層 | `resolve_resource` 以 `Path.cwd()/templates` 覆蓋 | 新增 contextvar `overlay_dir`；解析順序變為 **explicit > overlay（job）> cwd > 套件內建**。不使用 `os.chdir`（行程內共用，執行緒不安全） |
| 自訂需求檔 | CLI 讀 `config/custom_*.md` | 服務層讀上傳的覆蓋檔或伺服器預設，轉成 `custom_requirements` 字串傳入（核心 API 本來就只收字串） |

`contextvars` 會隨 `ThreadPoolExecutor` 的 `contextvars.copy_context().run` 傳遞；JobRunner 必須用這個
方式提交，否則 worker thread 看不到 overlay。

## 5. 提示詞輸入的兩種模式

1. **表單模式（預設）**：使用者以下拉選單選模板參數，自由文字只作為 `custom_requirements`
   附加在模板的「額外要求／使用者特殊需求」區塊。**輸出協定永遠由模板控制**，提示詞無法改寫它——
   這保證解析器與 grounding gate 不會被一句「請用表格輸出」打壞。
2. **自然語言模式**：`POST /api/plan {text}` 把需求連同 `build_usage_guide()` 送給輕量 LLM，
   要求回傳**JSON 參數提案**（而非 `guide` 現在的 CLI 指令字串），以 pydantic 驗證後填回表單，
   使用者確認才建立 job。這是既有 `suggest_command` 的結構化版本；LLM 給出非法值時回報驗證錯誤並保留表單原值。

`custom_requirements` 設長度上限（預設 2000 字元），避免成為繞過模板的長篇覆寫。

## 6. 部署選項

| 選項 | 適合情境 | 注意事項 |
|------|---------|---------|
| **VPS + Docker Compose + Caddy（推薦起點）** | 個人或研究室；需要持久儲存、長時任務 | 自動 HTTPS（Caddy）；`/data` 掛 volume；最少 1 vCPU / 2 GB RAM（`pdfplumber`、`chromadb` 依賴佔記憶體） |
| Google Cloud Run 等容器平台 | 低使用量、希望閒置不計費 | 容器檔案系統是暫存的，job 目錄需放物件儲存（GCS/S3）；長時生成需確保請求逾時與背景執行設定足夠，或改用平台的 job 機制 |
| Hugging Face Spaces（Docker Space） | 示範、課堂短期使用 | 預設公開，需設為 private 並以 Secrets 存 API key；免費硬體會休眠、儲存非持久 |
| 學校 / 實驗室內網伺服器 | 有機構主機、資料不出校 | 搭配 VPN 或 Tailscale，可省去公開 HTTPS 與驗證的複雜度 |

各平台的資源上限、逾時與價格變動快，部署前以官方文件為準。

容器映像：`uv sync --extra web --no-dev`；Ollama 不放進同一容器（雲端以 API provider 為主；需要本地模型時
另起 Ollama 服務並以 `OLLAMA_HOST` 指向）。

## 7. 安全與資源上限

- **驗證**：第一版以反向代理把關（Caddy `basic_auth`、Cloudflare Access 或 Tailscale）；應用層另有
  `WEB_API_TOKEN`（bearer）供 QuickAdd / MCP 等程式 client 使用。啟動時若綁定非 localhost 且未設任何驗證，
  **拒絕啟動**（fail-closed）。
- **金鑰**：LLM API key 只在伺服器環境變數；`/api/options`、job 結果、錯誤訊息皆不回傳（沿用 MCP 的脫敏規則）。
  不支援使用者自帶金鑰（BYOK），避免在服務端保存他人金鑰。
- **上傳**：大小上限（預設 50 MB）、副檔名 + magic bytes 白名單、存檔名改為 job 內固定名稱（不信任使用者檔名，
  防路徑穿越）；下載端點只允許 job 目錄內的檔案（與 `read_output` 相同的邊界檢查）。
- **費用控制**：每個 token 每日 job 數上限；`slide_count` / `detail` 沿用 pydantic 範圍；
  抽取字數沿用 `_ZETTEL_MAX_CHARS` / `_SLIDES_MAX_CHARS`。
- **資料保留**：job 目錄 TTL（預設 7 天）後自動刪除。上傳的教科書、專書多受著作權保護——
  服務僅供上傳者本人取用結果，不提供公開分享連結。
- **提示詞注入**：上傳文件可能夾帶「忽略以上指示」之類文字；影響範圍限於該 job 的 LLM 輸出，
  且 grounding gate 會抹除無法回溯原文的卡片。服務端不依 LLM 輸出執行任何動作（無 tool 呼叫、無指令執行）。

## 8. 回到筆記 App

| 路徑 | 說明 |
|------|------|
| zip 下載 | 結構與本機 `output/` 相同，解壓到 vault 即可，匯入腳本照用 |
| 遠端 QuickAdd | wrapper 新增 `mode: "remote"`（`workflow-config.json` 設 `baseUrl` 與 token），以 `requestUrl` 呼叫 REST API，輪詢 job 狀態後把檔案寫進 vault |
| 同步資料夾（後續） | job 完成後把輸出推到使用者指定的 git repo 或 WebDAV/S3，由 Obsidian 同步外掛拉回 |

## 9. 分期

| 階段 | 內容 | 驗收 |
|------|------|------|
| P0 概念驗證（選做） | Gradio 單檔，本機跑 | 能上傳 PDF 產出投影片 |
| P1 MVP | job API、SSE、per-job 目錄與 overlay、靜態 UI、Docker + Caddy、token 驗證 | 手機瀏覽器上傳 PDF → 下載 zip，匯入 Obsidian 正常 |
| P2 | 自然語言模式 `/api/plan`、遠端 QuickAdd、MCP token 與 `content` 參數 | QuickAdd 遠端模式在無 uv 的電腦上可用 |
| P3 | 媒體類型（依賴 add-media-templates）、TTL 清理、每日額度 | 上傳 SRT 產出 podcast 卡片 |

## 10. 開放問題

- 多人使用（課堂）時，每人一個 token 是否足夠，或需要 OIDC 登入（Google Workspace 學校帳號）。
- job 狀態用檔案（`job.json`）或 SQLite：單機部署檔案即可；若要水平擴充需改外部儲存。
- 是否在 UI 內提供「重跑 grounding 被抹除的卡片」等進階操作。
