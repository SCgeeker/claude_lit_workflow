# 程式碼範例目錄

本目錄示範 Claude Lit Workflow **現役工具**（`setup` / `slides` / `zettel` / `guide` / `mcp-server`）的用法。

> 知識管理（analyze / kb / embeddings / batch / quality / 向量搜索）已交由筆記 App 接管、暫停開發，
> 相關舊範例已移出 repo（見根目錄 `CLAUDE.md`「暫停功能」）。

---

## 目錄結構

```
examples/
├── quickstart/       # 環境設置與基本使用
├── slide_maker/      # uv run slides 範例
├── zettel/           # uv run zettel 範例
├── pdf_extraction/   # PDFExtractor 函式庫用法
├── configuration/    # config/settings.yaml 範例
└── README.md
```

---

## 快速開始（quickstart/）

```bash
bash examples/quickstart/setup_environment.sh   # uv sync → .env → guide → setup
bash examples/quickstart/basic_usage.sh         # setup / guide / slides / zettel 基本流程
```

## 投影片生成（slide_maker/）

```bash
bash examples/slide_maker/slide_maker_usage.sh
```

涵蓋 `--pdf` / `--url` / 主題三種來源、7 種學術風格、5 種詳細程度、3 種語言、多供應商與 PPTX 輸出。

## 原子卡片生成（zettel/）

```bash
bash examples/zettel/zettel_usage.sh
```

涵蓋詳細程度、`--citekey`（Zotero 場景）、`--slides-file`（結合編修後投影片）與多供應商。

## PDF 提取（pdf_extraction/）

```bash
python examples/pdf_extraction/extract_pdf.py
```

`PDFExtractor` 函式庫級用法：擷取標題、作者、摘要、章節結構（pdfplumber / PyPDF2）。

## 配置（configuration/）

```bash
cat examples/configuration/settings_example.yaml
```

展示 LLM 後端、PDF、slides、zettel 的預設值覆蓋（多數情況只需 `.env` 填 key）。

---

## 相關文檔

- **快速開始與指令總覽**: [README.md](../README.md) / [README.en.md](../README.en.md)
- **完整專案指引**: [CLAUDE.md](../CLAUDE.md)
- **行為規格**: [openspec/](../openspec/)
