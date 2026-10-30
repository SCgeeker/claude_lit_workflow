# -*- coding: utf-8 -*-
"""MCP server 啟動器

  uv run mcp-server                                   # stdio（預設，本機 client）
  uv run mcp-server --transport http --port 8765      # Streamable HTTP（遠端平台）

HTTP 模式設定 WEB_API_TOKEN 時，所有請求須帶 `Authorization: Bearer <token>`。
"""

import argparse
import os
import sys
from pathlib import Path

# Windows cp950 防護（僅影響 argparse 說明文字；stdio 協定走 stdout.buffer + UTF-8）
try:
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 與 CLI 相同的路徑設定（change package-cli 時移除）



def main() -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-server",
        description="claude-lit-workflow MCP server（stdio / Streamable HTTP）",
    )
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio",
        help="傳輸方式（預設：stdio）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 監聽位址（預設：127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765, help="HTTP 監聽埠（預設：8765）")
    args = parser.parse_args()

    from claude_lit.mcp_server.server import mcp

    if args.transport == "http":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        token = os.environ.get("WEB_API_TOKEN") or None
        if not token:
            if args.host not in ("127.0.0.1", "localhost", "::1"):
                print("⚠️  HTTP 對外綁定但未設定 WEB_API_TOKEN：任何人都能呼叫工具", file=sys.stderr)
            mcp.run(transport="streamable-http")
            return 0
        _run_http_with_token(mcp, args.host, args.port, token)
    else:
        # stdio：stdout 專屬 JSON-RPC；核心層訊息只走 logging（stderr / 檔案）
        mcp.run(transport="stdio")
    return 0


def _run_http_with_token(mcp, host: str, port: int, token: str) -> None:
    """Streamable HTTP + bearer token（token 已防 DNS rebinding，故關閉僅限 localhost 的 Host 檢查）"""
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    from claude_lit.web.auth import BearerAuthMiddleware

    mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = BearerAuthMiddleware(mcp.streamable_http_app(), token=token)
    print(f"🔑 MCP Streamable HTTP（bearer token）：http://{host}:{port}/mcp", file=sys.stderr)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    sys.exit(main())
