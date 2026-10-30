# -*- coding: utf-8 -*-
"""claude-lit-workflow 網頁服務（REST + SSE job API 與靜態網頁 UI）

核心 API（claude_lit.api）不修改；本層負責上傳、job 隔離、驗證、資源上限與進度串流。
需安裝 web extra：uv sync --extra web
"""
