# Claude Lit Workflow

**語言**：繁體中文 ｜ [English](README.en.md)

![License](https://img.shields.io/badge/license-MIT-blue) ![Python](https://img.shields.io/badge/python-3.10%2B-blue)

整合筆記 App 的論文工作流套件 — 從 PDF / URL / 主題生成學術投影片與 Zettelkasten 原子卡片，輸出純 Markdown，可直接匯入 Obsidian 等筆記工具。透過 CLI、MCP server 或 Obsidian QuickAdd 皆可驅動。

## 核心功能

- **投影片生成** — 7 種學術風格、5 種詳細程度、3 種語言，輸出 Obsidian Slides / Marp 相容 Markdown 或 PPTX
- **原子卡片生成** — Zettelkasten 原子化卡片，支援跨論文連結與知識庫整合
- **使用嚮導** — 用自然語言描述需求，由指定 LLM 回覆建議的 CLI 指令
- **MCP server** — 以 Model Context Protocol 曝露工具，任何支援 MCP 的 LLM 平台皆可呼叫（stdio + Streamable HTTP）
- **多供應商** — Google Gemini / OpenAI / Anthropic / Ollama / NVIDIA NIM

## 設計定位

```text
PDF / URL / 主題
  │
  ├─► uv run slides   →  Markdown 投影片（Obsidian Slides Extended 相容）
  │        （人工編修，深度理解）
  │
  └─► uv run zettel   →  output/zettelkasten_notes/{citekey}/
           （可搭配 --slides-file 使用編修後的投影片）
                │
                └──► 匯入筆記 App（Obsidian / ProgramVerse / 任何 Markdown App）
```

知識管理（搜索、連結、圖譜）由筆記 App 負責；本工具專注於**生成高品質 Markdown 內容**。

## 快速開始

```bash
git clone https://github.com/SCgeeker/claude_lit_workflow.git
cd claude_lit_workflow
uv sync

cp .env.example .env   # Windows: copy .env.example .env；填入至少一個 API key
uv run setup           # 自動偵測可用供應商，顯示設定建議
```

使用：

```bash
uv run slides --pdf paper.pdf                              # 從 PDF 生成投影片
uv run slides --url https://arxiv.org/abs/1234 --style teaching
uv run zettel --pdf paper.pdf --detail comprehensive      # 生成原子卡片
uv run zettel --pdf paper.pdf --slides-file output/slides/paper.md   # 結合編修後投影片
uv run zettel --pdf paper.pdf --no-ground                  # 關閉逐字回溯驗證（預設啟用）
```

> **Grounding gate（預設啟用）**：每張卡片的「核心」須能逐字回溯原文，定位不到即**抹除**、中文定位不到則**隔離**至 `_needs_cjk_check/` 待審；旁存 `{card_id}.grounding.json` 記錄溯源。以 `--no-ground` 關閉。

## LLM 供應商

在 `.env` 填入任一供應商的 API key：

| 供應商 | 環境變數 | 推薦模型 |
|--------|----------|----------|
| Google Gemini | `GOOGLE_API_KEY` | gemini-2.5-flash |
| Anthropic Claude | `ANTHROPIC_API_KEY` | claude-haiku-4-5 |
| OpenAI | `OPENAI_API_KEY` | gpt-4o-mini |
| Ollama（本地） | `OLLAMA_URL` | llama3.2 |
| NVIDIA NIM | `NVIDIA_API_KEY` | meta/llama-3.1-8b-instruct（預設，實測穩定） |

`--llm-provider auto` 自動選可用者。NVIDIA NIM（OpenAI 相容）以 `--llm-provider nvidia` 啟用，預設用實測穩定的 8b instruct；大模型可經 `NVIDIA_SLIDES_MODEL` / `NVIDIA_ZETTEL_MODEL` 或 `--model` 覆寫。

## CLI 指令總覽

| 指令 | 功能 |
|------|------|
| `uv run setup` | 偵測 LLM 連線，顯示設定建議 |
| `uv run guide` | 輸出工具使用說明（可貼給任何 LLM） |
| `uv run guide "需求" --provider X` | 用指定 LLM 依"需求"回覆建議的 CLI 指令 |
| `uv run slides --pdf paper.pdf` | 從 PDF 生成投影片 |
| `uv run zettel --pdf paper.pdf` | 從 PDF 生成原子卡片 |
| `uv run mcp-server` | 啟動 MCP server（stdio；`--transport http` 為 Streamable HTTP） |

完整參數：執行 `uv run <指令> --help`，或 `uv run guide` 印出所有選項與風格清單；行為規格見 `openspec/`。

## MCP Server

任何支援 MCP 的 LLM 平台（Claude Desktop / Claude Code / Cursor 等）皆可呼叫：

```bash
uv run mcp-server                                  # stdio（本機 client）
uv run mcp-server --transport http --port 8765     # Streamable HTTP（遠端平台）

# 註冊到 Claude Code：
claude mcp add lit-workflow -- uv --directory /path/to/claude_lit_workflow run mcp-server
```

提供 5 tools（generate_slides / generate_zettel / check_setup / list_options / read_output）、6 resources（模板、風格、自訂需求、脫敏設定）、2 prompts（渲染完成的提示詞）。生成由伺服器端 LLM 完成，API key 只存在伺服器行程、不經協定傳輸；長時生成會發 progress notification（建議 client timeout ≥ 360 秒）。

## 模板與設定（cwd 覆蓋機制）

套件內建一份預設模板與設定（`src/claude_lit/resources/`，隨 wheel 發佈）。執行時依序解析：**明確傳入路徑 > 目前工作目錄的 `templates/`、`config/` > 套件內建**。

- 在 repo 目錄工作時，直接編輯 `templates/`、`config/custom_*.md` 即生效，不需重裝。
- wheel 安裝到其他機器、無覆蓋檔時自動用套件內建版。
- 使用者自訂檔（`config/custom_slides.md`、`custom_zettel.md`）填入你的領域術語；`--no-custom` 跳過、`--custom-file` 指定其他檔案。

## 筆記 App 整合（Obsidian QuickAdd）

透過 Templater user script（`*_wrapper.js`）+ `workflow-config.json` 讓 Obsidian QuickAdd 直接觸發生成：

- **Program_verse** — slides + zettel + import + guide 完整流程
- **Ideaverse_Growing** — slides only，輸出至 vault 的 `+/`

wrapper 讀 config、以 suggester 收集參數、`exec("uv run …")` 呼叫本工具，並以 `PYTHONIOENCODING=utf-8` 確保中文無亂碼。

## Citekey（輸出檔名）

輸出檔名採 `Author-Year`（如 `Barsalou-1999`）。使用 Zotero 等文獻管理工具者，可用 `--citekey` 直接指定你習慣的 key：

```bash
uv run zettel --pdf paper.pdf --citekey Barsalou-1999
```

未指定時自動從 DOI / CrossRef 解析。

## 輸出格式

```text
output/
├── slides/
│   └── {citekey}_{date}.md
└── zettelkasten_notes/
    └── zettel_{citekey}_{date}_{model}/
        ├── zettel_index.md
        └── zettel_cards/{citekey}-NNN.md
```

## 技術棧

Python 3.10+ / uv ｜ pydantic ｜ Jinja2（Prompt 模板）｜ FastMCP（MCP server）｜ LLM：Gemini / OpenAI / Anthropic / Ollama / NVIDIA NIM

規格與變更歷史見 `openspec/`（SDD 流程，specs 為行為真相來源）。

## 授權

MIT License — 見 [LICENSE](LICENSE)。Copyright (c) 2025-2026 Sau-Chin Chen。

---

**版本**：0.12.0 ｜ **更新**：2026-07-09
