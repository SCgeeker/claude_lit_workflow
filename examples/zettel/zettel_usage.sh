#!/bin/bash
# Zettelkasten 原子卡片生成（uv run zettel）使用範例
# 輸出 output/zettelkasten_notes/zettel_{citekey}_{date}_{model}/，可直接匯入 Obsidian 等筆記 App

# === 基本用法 ===

# 從 PDF 生成原子卡片
uv run zettel --pdf paper.pdf

# 從 URL 生成
uv run zettel --url https://arxiv.org/abs/1234.56789

# === 詳細程度（卡片數量）===
# minimal(5) / brief(8) / standard(12) / detailed(20) / comprehensive(30+)
uv run zettel --pdf paper.pdf --detail comprehensive

# 語言模式（chinese / english / bilingual）與領域
uv run zettel --pdf paper.pdf --language bilingual --domain CogSci

# === 指定 citekey（Zotero 等文獻管理場景）===
# 未指定時自動從 DOI / CrossRef 解析
uv run zettel --pdf paper.pdf --citekey Barsalou-1999

# === 結合編修後的投影片（粗體標示優先生成卡片）===
# 建議流程：先生成並人工編修 slides，再餵給 zettel
uv run slides --pdf paper.pdf
uv run zettel --pdf paper.pdf --slides-file output/slides/paper.md

# === 自訂需求 ===
# 預設讀 config/custom_zettel.md；--no-custom 可略過
uv run zettel --pdf paper.pdf --custom-file my_style.md

# === 選擇 LLM 供應商 ===
uv run zettel --pdf paper.pdf --llm-provider google --model gemini-2.5-flash
uv run zettel --pdf paper.pdf --llm-provider ollama --model llama3.2
uv run zettel --pdf paper.pdf --llm-provider nvidia

# === 其他 ===
# 不入庫、僅生成檔案
uv run zettel --pdf paper.pdf --no-add-to-kb

# 強制重新生成（覆蓋舊卡片）
uv run zettel --pdf paper.pdf --force

# 列出所有可用選項
uv run zettel --list-options
