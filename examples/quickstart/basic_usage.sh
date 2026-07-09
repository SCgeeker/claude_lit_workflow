#!/bin/bash
# 快速開始：基本使用（現役 5 工具：setup / slides / zettel / guide / mcp-server）

# 1. 確認 LLM 連線（填好 .env 後）
uv run setup

# 2. 查看目前可用指令與選項（純離線，不需 API key）
uv run guide

# 3. 用自然語言請 LLM 建議指令
uv run guide "把 paper.pdf 做成教學風格投影片" --provider google

# 4. 從 PDF 生成投影片
uv run slides --pdf paper.pdf --style modern_academic

# 5. 從 PDF 生成 Zettelkasten 原子卡片
uv run zettel --pdf paper.pdf --detail standard

# 6. 建議流程：先編修投影片，再據以生成卡片
uv run slides --pdf paper.pdf
uv run zettel --pdf paper.pdf --slides-file output/slides/paper.md
