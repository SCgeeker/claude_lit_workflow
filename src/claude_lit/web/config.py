# -*- coding: utf-8 -*-
"""網頁服務設定（環境變數 → WebSettings）

| 環境變數 | 預設 | 說明 |
|---------|------|------|
| WEB_DATA_DIR | ./web_data | job 目錄根（上傳檔、輸出、job.json） |
| WEB_API_TOKEN | （空） | bearer token；網頁 UI、QuickAdd、MCP 共用 |
| WEB_TRUST_PROXY_AUTH | 0 | 1 = 由反向代理（Caddy basic_auth、Cloudflare Access…）負責驗證 |
| WEB_MAX_UPLOAD_MB | 50 | 單一上傳檔上限 |
| WEB_MAX_WORKERS | 2 | 同時執行的 job 數（其餘排隊） |
| WEB_RETENTION_DAYS | 7 | job 目錄保留天數（含上傳原始檔） |
| WEB_MAX_CUSTOM_CHARS | 2000 | 提示詞（custom_requirements）字數上限 |
| WEB_DAILY_JOB_LIMIT | 0 | 每日 job 數上限（0 = 不限） |
| WEB_ALLOWED_HOSTS | （空） | 掛載的 MCP 端點允許的 Host（逗號分隔，如 lit.example.com） |
"""

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import List, Optional

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _flag(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class WebSettings:
    data_dir: Path = Path("web_data")
    api_token: Optional[str] = None
    trust_proxy_auth: bool = False
    max_upload_mb: int = 50
    max_workers: int = 2
    retention_days: int = 7
    max_custom_chars: int = 2000
    daily_job_limit: int = 0
    allowed_hosts: List[str] = field(default_factory=list)
    enable_mcp: bool = True

    @classmethod
    def from_env(cls, **overrides) -> "WebSettings":
        env = os.environ
        settings = cls(
            data_dir=Path(env.get("WEB_DATA_DIR") or "web_data"),
            api_token=env.get("WEB_API_TOKEN") or None,
            trust_proxy_auth=_flag(env.get("WEB_TRUST_PROXY_AUTH")),
            max_upload_mb=int(env.get("WEB_MAX_UPLOAD_MB") or 50),
            max_workers=int(env.get("WEB_MAX_WORKERS") or 2),
            retention_days=int(env.get("WEB_RETENTION_DAYS") or 7),
            max_custom_chars=int(env.get("WEB_MAX_CUSTOM_CHARS") or 2000),
            daily_job_limit=int(env.get("WEB_DAILY_JOB_LIMIT") or 0),
            allowed_hosts=[h.strip() for h in (env.get("WEB_ALLOWED_HOSTS") or "").split(",") if h.strip()],
        )
        return replace(settings, **overrides)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def auth_configured(self) -> bool:
        return bool(self.api_token) or self.trust_proxy_auth


def is_local_host(host: str) -> bool:
    return host in _LOCAL_HOSTS


def startup_error(host: str, settings: WebSettings) -> Optional[str]:
    """公開綁定卻未設任何驗證時回傳錯誤訊息（fail-closed：拒絕啟動）"""
    if is_local_host(host) or settings.auth_configured:
        return None
    return (
        f"綁定 {host} 會對外公開，但未設定驗證。請設定 WEB_API_TOKEN（bearer token），"
        "或由反向代理負責驗證並設定 WEB_TRUST_PROXY_AUTH=1。"
    )
