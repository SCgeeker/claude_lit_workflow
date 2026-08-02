# CLAUDE.md

本文件為 Claude Code 提供專案指引。

## 專案概述

**Claude Lit Workflow** 是整合筆記 App 的論文工作流套件。
從 PDF 生成投影片與 Zettelkasten 原子卡片，輸出純 Markdown，可直接匯入 Obsidian 等筆記工具。

### 核心功能（活躍開發）

- **投影片生成** (`uv run slides`): PDF → Markdown 投影片（Obsidian Slides Extended 相容）
- **原子卡片生成** (`uv run zettel`): PDF / slides → Zettelkasten 卡片
- **設定助手** (`uv run setup`): 偵測 LLM 連線、給出設定建議
- **使用嚮導** (`uv run guide`): 導出工具使用說明，或用指定 LLM 依需求回覆建議指令
- **MCP server** (`uv run mcp-server`): 以 MCP 曝露工具給任何 LLM 平台（stdio + HTTP）

### 暫停功能

> 知識管理由筆記 App 接管，以下工具暫停開發。
> 根目錄入口腳本已歸檔（`archive/root_cli_scripts_20260708.zip`，git 歷史可查）；
> 核心模組保留於 `src/claude_lit/`（analyzers、knowledge_base、embeddings 等）。
> `slides --analyze-first` 依賴 analyze_paper.py，隨歸檔一併停用。

---

## 專案架構

```
claude_lit_workflow/
├── src/claude_lit/        # 正規 Python package（wheel 安裝即用）
│   ├── api/               # 核心 API（pydantic Request/Result、錯誤、進度）
│   ├── cli/               # CLI 薄殼（slides / zettel / setup_check）
│   ├── mcp_server/        # MCP server（stdio + Streamable HTTP）
│   ├── generators/        # SlideMaker / ZettelMaker
│   ├── extractors/        # PDF / URL 抽取
│   ├── resource_loader.py # 資源解析（cwd 覆蓋 > 套件內建）
│   ├── resources/         # 套件內建模板與預設設定
│   └── ...                # utils / knowledge_base / integrations（詳見 src/CLAUDE.md）
│
├── openspec/              # SDD 規格（specs = 行為真相來源）
├── pyproject.toml         # uv 專案配置（entry points 指向 claude_lit.*）
├── output/                # 輸出 → output/CLAUDE.md
├── templates/             # 模板（cwd 覆蓋層，可直接編輯）→ templates/CLAUDE.md
├── config/                # 配置（cwd 覆蓋層）→ config/CLAUDE.md
└── docs/                  # 本機文檔暫存（gitignore；僅 CLAUDE.md/TROUBLESHOOTING 隨 git）→ docs/CLAUDE.md
```

---

## CLI 指令

### 環境設置

```bash
uv sync
cp .env.example .env   # 填入 API key
uv run setup           # 確認 LLM 連線
```

### 核心指令

```bash
# 投影片生成
uv run slides --pdf paper.pdf
uv run slides --pdf paper.pdf --style modern_academic --detail comprehensive

# Zettel 卡片生成
uv run zettel --pdf paper.pdf
uv run zettel --pdf paper.pdf --slides-file output/slides/paper.md

# 設定檢查
uv run setup

# 使用嚮導（任何 terminal，不需 MCP client）
uv run guide                                       # 印出工具使用說明
uv run guide "把 paper.pdf 做成教學風格投影片" --provider nvidia

# MCP server（任何支援 MCP 的 LLM 平台皆可串接）
uv run mcp-server                                  # stdio
uv run mcp-server --transport http --port 8765     # Streamable HTTP
```

### 完整指令說明

執行 `uv run <指令> --help` 或 `uv run guide`（動態列出所有選項與風格）。使用總覽見 [README.md](README.md) / [README.en.md](README.en.md)。

---

## 技術棧

- **Python 3.10+** / **uv**
- **Jinja2**: Prompt 模板
- **LLM**: Gemini, OpenAI, Anthropic, Ollama

---

## 多 LLM 支援

| Provider | 模型 | 用途 |
|----------|------|------|
| **Google Gemini** | gemini-2.5-flash | 預設推薦 |
| **Anthropic** | claude-haiku-4-5 | 快速低成本 |
| **OpenAI** | gpt-4o-mini | 通用 |
| **Ollama** | llama3.2 | 本地運行 |
| **NVIDIA NIM** | meta/llama-3.1-8b-instruct（預設） | `--llm-provider nvidia`；大模型經 `NVIDIA_SLIDES_MODEL`/`NVIDIA_ZETTEL_MODEL` 或 `--model` 覆寫（如 nemotron-3-super-120b-a12b）。原 253b/qwen-thinking 已失效 |

---

## 開發規範

### 新增功能

1. 在 `src/` 中實作模組
2. 在 `pyproject.toml` 中定義 CLI 入口（如需要）
3. 更新 `README.md` / `README.en.md`（指令總覽）

### Citekey 規範

- 預設格式: `Author-Year`（如 `Barsalou-1999`）
- 支援 `--citekey` 手動傳入（Zotero bib 場景）
- 無 bib 檔時走 DOI / CrossRef 自動解析

### 輸出規範

```
output/
├── slides/
│   └── {citekey}_{date}.md
└── zettelkasten_notes/
    └── zettel_{citekey}_{date}_{model}/
        ├── zettel_index.md
        └── zettel_cards/
            ├── {citekey}-001.md
            ├── {citekey}-001.grounding.json   # grounding sidecar（provenance）
            ├── ...
            └── _needs_cjk_check/              # CJK 定位不到、隔離待審的卡片
                ├── {citekey}-cjk-001.md
                └── {citekey}-cjk-001.grounding.json
```

### Grounding gate（P3，預設啟用）

Zettel 生成在寫檔前驗證每張卡片的「核心」能否**逐字回溯**原文：

- **定位到** → 保留，並以原文 span 修正空格/換行連字；旁存 `{card_id}.grounding.json`（verdict、coverage、char_offset、來源指紋）。
- **定位不到** → **抹除**（不落地、不入庫）。
- **中文定位不到**（CJK，多為 CID glyph 抽取失敗）→ **隔離**至 `_needs_cjk_check/` 待人工審，不 erase 也不混入正常卡。

關閉：`uv run zettel ... --no-ground`；MCP `generate_zettel` 傳 `ground=false`。
`ZettelResult` 回報 `grounded` / `erased` / `flagged`。normalize 規則須與 vault `quote_check.py` 逐字同步（跨 repo 無 CI 強制）。

---

## 筆記 App 整合

本工具輸出純 Markdown，可整合任何支援 Markdown 的筆記系統。

```
Claude Lit Workflow          筆記 App（Obsidian / ProgramVerse / 其他）
────────────────────         ──────────────────────────────────────────
output/slides/*.md      →   簡報筆記（Obsidian Slides Extended）
output/zettelkasten_notes/
        └──► 匯入腳本  →    Annotation / Zettelkasten 資料夾
```

---

**版本**: 0.12.0
**更新日期**: 2026-07-08（MCP server + 正規 package 化，SDD 流程見 openspec/）
