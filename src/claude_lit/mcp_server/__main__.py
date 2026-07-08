# -*- coding: utf-8 -*-
"""MCP server 啟動器

  uv run mcp-server                                   # stdio（預設，本機 client）
  uv run mcp-server --transport http --port 8765      # Streamable HTTP（遠端平台）
"""

import argparse
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
        mcp.run(transport="streamable-http")
    else:
        # stdio：stdout 專屬 JSON-RPC；核心層訊息只走 logging（stderr / 檔案）
        mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
