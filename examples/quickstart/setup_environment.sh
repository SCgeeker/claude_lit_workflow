#!/bin/bash
# 快速開始：環境設置

# 1. 同步依賴（使用 uv，推薦）
uv sync

# 2. 建立 .env 並填入至少一個供應商的 API key
cp .env.example .env        # Windows: copy .env.example .env
# 於 .env 填入，例如 GOOGLE_API_KEY=...

# 3. 驗證安裝（純離線，能印出使用說明即代表套件可正常匯入）
uv run guide

# 4. 驗證 LLM 連線（偵測 GOOGLE / ANTHROPIC / OPENAI / OLLAMA / NVIDIA）
uv run setup
