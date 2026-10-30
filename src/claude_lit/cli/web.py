#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
網頁服務啟動器（薄殼）

  uv run web                                  # 本機 http://127.0.0.1:8000
  WEB_API_TOKEN=... uv run web --host 0.0.0.0  # 對外（須設定驗證，否則拒絕啟動）

設定以環境變數提供（見 claude_lit.web.config）；本層只處理啟動參數與依賴檢查。
"""

import argparse
import sys

try:
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _missing_web_dependency() -> str | None:
    try:
        import multipart  # noqa: F401  python-multipart
        import starlette  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as e:
        return e.name or str(e)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="web",
        description="claude-lit-workflow 網頁服務：上傳文章、選模板、由伺服器端 LLM 生成投影片與卡片",
    )
    parser.add_argument("--host", default="127.0.0.1", help="監聽位址（預設：127.0.0.1）")
    parser.add_argument("--port", type=int, default=8000, help="監聽埠（預設：8000）")
    parser.add_argument("--workers", type=int, default=None,
                        help="同時執行的工作數（預設：WEB_MAX_WORKERS 或 2）")
    parser.add_argument("--data-dir", default=None, help="工作資料目錄（預設：WEB_DATA_DIR 或 ./web_data）")
    parser.add_argument("--no-mcp", action="store_true", help="不掛載 /mcp 端點")
    args = parser.parse_args()

    missing = _missing_web_dependency()
    if missing:
        print(f"❌ 缺少網頁服務依賴：{missing}")
        print("💡 提示：請執行 uv sync --extra web")
        return 1

    from pathlib import Path

    from claude_lit.utils.config_loader import load_env_file
    from claude_lit.web.config import WebSettings, startup_error

    load_env_file()
    overrides = {}
    if args.workers:
        overrides["max_workers"] = args.workers
    if args.data_dir:
        overrides["data_dir"] = Path(args.data_dir)
    if args.no_mcp:
        overrides["enable_mcp"] = False
    settings = WebSettings.from_env(**overrides)

    error = startup_error(args.host, settings)
    if error:
        print(f"❌ {error}")
        return 1

    import uvicorn

    from claude_lit.web.app import create_app

    print(f"🌐 網頁服務：http://{args.host}:{args.port}/（資料目錄：{settings.data_dir.resolve()}）")
    if settings.api_token:
        print("🔑 已啟用 bearer token 驗證（WEB_API_TOKEN）")
    elif settings.trust_proxy_auth:
        print("🔑 驗證交由反向代理（WEB_TRUST_PROXY_AUTH=1）")
    uvicorn.run(create_app(settings), host=args.host, port=args.port, proxy_headers=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
