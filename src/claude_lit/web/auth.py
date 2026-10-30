# -*- coding: utf-8 -*-
"""驗證與金鑰脫敏

- BearerAuthMiddleware：/api/*（health 除外）與 /mcp 需 `Authorization: Bearer <WEB_API_TOKEN>`；
  WEB_TRUST_PROXY_AUTH=1 時由反向代理負責、不在應用層檢查。靜態 UI 本身不含資料，不需驗證。
- redact_secrets：錯誤訊息與警告回傳前移除金鑰（部分 LLM SDK 的錯誤訊息會回顯金鑰片段）。
"""

import hmac
import json
import os
import re
from typing import Optional

_SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
_SECRET_PATTERNS = re.compile(
    r"sk-[A-Za-z0-9_\-*]{8,}"        # OpenAI / Anthropic
    r"|AIza[0-9A-Za-z_\-]{20,}"      # Google
    r"|nvapi-[A-Za-z0-9_\-]{8,}"     # NVIDIA
)
_PUBLIC_PATHS = ("/api/health",)
_PROTECTED_PREFIXES = ("/api/", "/mcp")


def redact_secrets(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    for name, value in os.environ.items():
        if value and len(value) >= 8 and _SECRET_ENV.search(name) and value in text:
            text = text.replace(value, "***")
    return _SECRET_PATTERNS.sub("***", text)


def _requires_auth(path: str) -> bool:
    if path in _PUBLIC_PATHS:
        return False
    return any(path == p.rstrip("/") or path.startswith(p) for p in _PROTECTED_PREFIXES)


def token_matches(header_value: Optional[str], token: str) -> bool:
    scheme, _, supplied = (header_value or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied:
        return False
    return hmac.compare_digest(supplied.strip().encode(), token.encode())


class BearerAuthMiddleware:
    """純 ASGI middleware（同時保護掛載的 MCP 子應用，且不緩衝串流回應）"""

    def __init__(self, app, *, token: Optional[str], trust_proxy: bool = False):
        self.app = app
        self.token = token
        self.trust_proxy = trust_proxy

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or self.trust_proxy
            or not self.token
            or not _requires_auth(scope.get("path", ""))
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("latin-1")
        if token_matches(auth, self.token):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"error": "未授權：請提供有效的 bearer token"}, ensure_ascii=False).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"www-authenticate", b"Bearer"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
