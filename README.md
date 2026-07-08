# Claude Lit Workflow

整合筆記 App 的論文工作流套件 — 從 PDF 生成投影片與 Zettelkasten 原子卡片，輸出純 Markdown 可直接匯入 Obsidian 等筆記工具。

## 核心功能

- **投影片生成** — 7 種學術風格、5 種詳細程度，輸出 Obsidian Slides 相容格式
- **原子卡片生成** — Zettelkasten 原子化卡片，支援跨論文連結
- **自訂需求** — `config/custom_*.md` 定義領域術語與風格，自動載入

## 設計定位

```
PDF 論文
  │
  ├─► uv run slides   →  Markdown 投影片（Obsidian Slides Extended 相容）
  │        （人工編修，深度理解）
  │
  └─► uv run zettel   →  output/zettelkasten_notes/{citekey}/
           （可搭配 --slides-file 使用編修後的投影片）
                │
                └──► 匯入筆記 App（Obsidian / ProgramVerse / 任何 Markdown App）
```

知識管理（搜索、連結、圖譜）由筆記 App 負責；本工具只負責**生成高品質 Markdown 內容**。

## 快速開始

### 1. 安裝

```bash
git clone https://github.com/SCChen1005/claude_lit_workflow.git
cd claude_lit_workflow
uv sync
```

### 2. 設定 LLM

```bash
cp .env.example .env   # Windows: copy .env.example .env
# 編輯 .env，填入至少一個 API key
uv run setup           # 自動偵測可用提供者，顯示設定建議
```

### 3. 使用

```bash
# 生成投影片
uv run slides --pdf paper.pdf

# 生成原子卡片
uv run zettel --pdf paper.pdf

# 結合投影片生成卡片（推薦）
uv run zettel --pdf paper.pdf --slides-file output/slides/paper.md
```

## LLM 設定

在 `.env` 填入任一提供者的 API key：

| 提供者 | 環境變數 | 推薦模型 |
|--------|----------|---------|
| Google Gemini | `GOOGLE_API_KEY` | gemini-2.0-flash-exp |
| Anthropic Claude | `ANTHROPIC_API_KEY` | claude-haiku-4-5 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o-mini |
| Ollama（本地） | `OLLAMA_URL` | llama3.2 |

```bash
# .env 範例
GOOGLE_API_KEY=your-key
DEFAULT_LLM_PROVIDER=google   # 或 auto（自動偵測）
```

執行 `uv run setup` 確認連線狀態。

## CLI 指令總覽

| 指令 | 功能 |
|------|------|
| `uv run setup` | 偵測 LLM 連線，顯示設定建議 |
| `uv run slides --pdf paper.pdf` | 從 PDF 生成投影片 |
| `uv run zettel --pdf paper.pdf` | 從 PDF 生成原子卡片 |
| `uv run zettel --slides-file slides.md` | 結合已編修的投影片生成卡片 |

`--style`、`--detail`、`--llm-provider` 等詳細參數：[docs/CLI_GUIDE.md](docs/CLI_GUIDE.md)

## MCP Server

以 Model Context Protocol 曝露工具，任何支援 MCP 的 LLM 平台（Claude Desktop / Claude Code / Cursor 等）皆可呼叫。

### 啟動

```bash
uv run mcp-server                                  # stdio（本機 client）
uv run mcp-server --transport http --port 8765     # Streamable HTTP（遠端平台）
```

### 註冊到 Claude Code

```bash
claude mcp add lit-workflow -- uv --directory D:/core/research/claude_lit_workflow run mcp-server
```

### 提供的能力

| 類別 | 名稱 | 說明 |
|------|------|------|
| Tool | `generate_slides` | PDF/URL/主題 → 投影片（伺服器端 LLM 生成） |
| Tool | `generate_zettel` | PDF/URL → Zettel 卡片（預設不寫入本機知識庫） |
| Tool | `check_setup` / `list_options` | 供應商狀態 / 風格目錄 |
| Tool | `read_output` | 讀取 output/ 下的生成結果（限定邊界） |
| Resource | `template://` `styles://` `config://` | prompt 模板、風格定義、自訂需求、脫敏設定 |
| Prompt | `slides-prompt` / `zettel-prompt` | 渲染完成的完整提示詞，供呼叫端 LLM 自行生成 |

生成類工具可能需時數分鐘（LLM 呼叫 timeout 300 秒），伺服器會發 progress notification；建議 client 的 tool timeout 設 360 秒以上。API key 只存在伺服器行程的 `.env`，不經協定傳輸。

## 自訂需求

編輯以下檔案，定義你的研究領域術語與生成風格：

- `config/custom_slides.md` — 投影片風格、術語對照表
- `config/custom_zettel.md` — 卡片撰寫規則、術語對照表

系統自動載入；使用 `--no-custom` 可跳過。

## 輸出格式

```
output/
├── slides/
│   └── {citekey}_{date}.md          # Obsidian Slides 相容 Markdown
└── zettelkasten_notes/
    └── zettel_{citekey}_{date}_{model}/
        ├── zettel_index.md
        └── zettel_cards/
            ├── {citekey}-001.md
            ├── {citekey}-002.md
            └── ...
```

## 技術棧

- Python 3.10+ / uv
- Jinja2（Prompt 模板）
- LLM：Gemini / OpenAI / Anthropic / Ollama

## 授權

MIT License

---

**版本**: 0.11.0 | **更新**: 2026-03-30

---

## 迭代紀錄

### 2026-03-30 架構定位調整 + setup 工具

**調整**：
- 定位收斂為「筆記 App 的論文工作流外掛」，核心只有 `slides` + `zettel` 兩個工具
- `analyze_paper.py`、`kb_manage.py`、`generate_embeddings.py` 標記暫停開發（bib 檢索與知識管理由筆記 App 接管）
- 新增 `setup.py`（`uv run setup`）：自動偵測 LLM 提供者連線狀態，給出設定建議與工作流引導
- `.env.example` 移除個人伺服器資訊，改為通用本地設定
- `config/custom_slides.md`、`config/custom_zettel.md` 改為通用範本，術語對照表改為可填入的空白範例

### 2026-03-21 slides 粗體邏輯修正

**背景**：LLM 生成的 slides 粗體標記過多，影響後續 `zettel --slides-file` 的卡片生成品質。

**修改**：
- `templates/prompts/journal_club_template.jinja2`：粗體限定為論文關鍵詞及近義術語，每張投影片最多 1-2 個
- `config/custom_slides.md`：明確禁止以粗體標記一般結論
- `templates/prompts/zettelkasten_template.jinja2`：粗體從「必須對應卡片」改為「優先參考提示，原子性仍為主判斷」

**工作流程定位**：
```
slides 生成 → 人工編修（沉浸理解）→ zettel --slides-file → 匯入筆記 App
```

---

## 待討論項目

| 項目 | 說明 |
|------|------|
| Obsidian Slides Extended 格式驗證 | 確認目前 slides 輸出與 `---` 分隔符相容性；theme frontmatter 需求 |
| cite_key 雙場景文件 | 有 bib 檔（Zotero）用 `--citekey` 手傳；無 bib 檔走 DOI CrossRef 自動解析 |
