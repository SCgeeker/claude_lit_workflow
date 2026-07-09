#!/bin/bash
# 投影片生成（uv run slides）使用範例
# 現役 CLI：來源可用 --pdf / --url / 主題文字；輸出 Markdown（Obsidian Slides / Marp 相容）或 PPTX

# === 基本用法 ===

# 從 PDF 生成投影片
uv run slides --pdf paper.pdf

# 從 URL 生成（arXiv / DOI / 出版商頁 / 部落格）
uv run slides --url https://arxiv.org/abs/1234.56789 --style teaching

# 從主題文字生成（不帶來源）
uv run slides "深度學習應用" --style modern_academic --slides 15

# === 風格與詳細程度 ===

# 指定學術風格（classic_academic / modern_academic / clinical /
#   research_methods / literature_review / case_analysis / teaching）
uv run slides --pdf paper.pdf --style research_methods --detail detailed

# 語言模式（chinese / english / bilingual）與張數
uv run slides --pdf paper.pdf --language bilingual --slides 20

# === 選擇 LLM 供應商 ===

# Google Gemini（預設推薦）
uv run slides --pdf paper.pdf --llm-provider google --model gemini-2.5-flash

# OpenAI
uv run slides --pdf paper.pdf --llm-provider openai --model gpt-4o-mini

# Anthropic Claude
uv run slides --pdf paper.pdf --llm-provider anthropic --model claude-haiku-4-5

# 本地 Ollama
uv run slides --pdf paper.pdf --llm-provider ollama --model llama3.2

# NVIDIA NIM（預設 8b；大模型經 NVIDIA_SLIDES_MODEL 或 --model 覆寫）
uv run slides --pdf paper.pdf --llm-provider nvidia

# === 自訂需求與輸出 ===

# 命令行自訂需求
uv run slides --pdf paper.pdf --custom "請使用口語化表達"

# 自訂需求檔案（預設讀 config/custom_slides.md；--no-custom 可略過）
uv run slides --pdf paper.pdf --custom-file my_requirements.md

# 指定輸出路徑與 PPTX 格式
uv run slides --pdf paper.pdf --format pptx --output "output/my_presentation.pptx"

# 列出所有可用風格 / 詳細度 / 語言
uv run slides --list-options
