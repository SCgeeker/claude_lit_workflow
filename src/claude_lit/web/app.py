# -*- coding: utf-8 -*-
"""網頁服務 ASGI app（Starlette）

    /                       靜態 UI
    /api/health             健康檢查（不需驗證）
    /api/options            風格 / 詳細程度 / 語言 / 媒體類型目錄與服務上限
    /api/plan               自然語言需求 → 參數提案（不執行）
    /api/jobs               POST 建立 job（multipart）
    /api/jobs/{id}          狀態與結果摘要
    /api/jobs/{id}/events   進度（Server-Sent Events，連線時先回放已發生事件）
    /api/jobs/{id}/files    輸出檔清單；/files/{path} 單檔
    /api/jobs/{id}/download 全部輸出（zip，結構與本機 output/ 相同）
    /api/jobs/{id}/cancel   取消
    /mcp                    既有 MCP server（Streamable HTTP），與 /api 共用 token
"""

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Optional

import anyio
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route

from claude_lit.api import list_options
from claude_lit.api.errors import ProviderUnavailableError
from claude_lit.api.guide import plan_request

from .auth import BearerAuthMiddleware, redact_secrets
from .config import WebSettings
from .jobs import PROVIDERS, JobLimitExceeded, JobManager, parse_params
from .storage import TEXT_SUFFIXES, OVERRIDABLE_RESOURCES, JobStorage, UploadRejected, check_upload

logger = logging.getLogger("claude_lit_workflow.web.app")

STATIC_DIR = Path(__file__).parent / "static"
_CLEANUP_INTERVAL_SECONDS = 3600
_SSE_POLL_SECONDS = 0.3
_SSE_KEEPALIVE_SECONDS = 15
_OVERRIDE_PREFIX = "override:"
_MULTIPART_SLACK = 1024 * 1024  # 欄位與邊界的額外位元組


def _error(message: str, status: int, **extra) -> JSONResponse:
    return JSONResponse({"error": message, **extra}, status_code=status)


def _validation_details(e: ValidationError) -> list:
    return [
        {"field": ".".join(str(p) for p in err.get("loc", ())), "message": err.get("msg", "")}
        for err in e.errors()
    ]


def _configure_mcp(settings: WebSettings):
    """取得既有 FastMCP 的 Streamable HTTP 子應用，並依部署設定 DNS rebinding 防護。

    FastMCP 預設只接受 localhost Host 標頭（防 DNS rebinding）；經反向代理以網域存取時必須放行。
    已有 token / 代理驗證時，rebinding 攻擊拿不到憑證，故未指定 WEB_ALLOWED_HOSTS 時關閉此檢查。
    """
    from mcp.server.transport_security import TransportSecuritySettings

    from claude_lit.mcp_server.server import mcp

    if settings.allowed_hosts:
        hosts = settings.allowed_hosts + ["127.0.0.1:*", "localhost:*"]
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=[f"https://{h}" for h in settings.allowed_hosts]
            + ["http://127.0.0.1:*", "http://localhost:*"],
        )
    elif settings.auth_configured:
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    else:
        security = mcp.settings.transport_security
    mcp.settings.transport_security = security
    # session manager 只能 run() 一次；每個 app 重新建立（private 屬性，mcp>=1.9 皆同）
    mcp._session_manager = None
    return mcp, mcp.streamable_http_app()


def create_app(
    settings: Optional[WebSettings] = None,
    *,
    manager: Optional[JobManager] = None,
) -> Starlette:
    settings = settings or WebSettings.from_env()
    storage = manager.storage if manager else JobStorage(settings.data_dir)
    manager = manager or JobManager(
        storage,
        max_workers=settings.max_workers,
        max_custom_chars=settings.max_custom_chars,
        daily_job_limit=settings.daily_job_limit,
    )

    # ── handlers ────────────────────────────────────────────────────────────

    async def index(request: Request):
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")

    async def health(request: Request):
        return JSONResponse({"status": "ok"})

    async def options(request: Request):
        from claude_lit.api.media import load_media_catalog

        catalog = list_options().model_dump()
        profiles = load_media_catalog().get("media_types", {})
        catalog["media_defaults"] = {
            key: {
                "default_slide_count": info.get("default_slide_count", 15),
                "recommended_styles": info.get("recommended_styles", []),
                "accepted_inputs": info.get("accepted_inputs", []),
                "chaptered": info.get("chunking") == "chapter",
            }
            for key, info in profiles.items()
        }
        catalog["providers"] = list(PROVIDERS)
        catalog["overridable_templates"] = list(OVERRIDABLE_RESOURCES)
        catalog["limits"] = {
            "max_upload_mb": settings.max_upload_mb,
            "max_custom_chars": settings.max_custom_chars,
            "daily_job_limit": settings.daily_job_limit,
            "retention_days": settings.retention_days,
        }
        return JSONResponse(catalog)

    async def plan(request: Request):
        try:
            body = await request.json()
        except Exception:
            return _error("請以 JSON 傳送 {\"text\": \"需求描述\"}", 400)
        text = (body or {}).get("text", "").strip() if isinstance(body, dict) else ""
        if not text:
            return _error("text 不可為空", 422)
        if len(text) > settings.max_custom_chars:
            return _error(f"需求描述超過 {settings.max_custom_chars} 字元上限", 422)
        provider = body.get("provider") or "auto"
        if provider not in PROVIDERS:
            return _error(f"provider 須為 {', '.join(PROVIDERS)}", 422)
        try:
            result = await anyio.to_thread.run_sync(
                lambda: plan_request(text, provider=provider, model=body.get("model"))
            )
        except ProviderUnavailableError as e:
            return _error(redact_secrets(str(e)), 503, hint=e.hint)
        return JSONResponse(result.model_dump())

    async def create_job(request: Request):
        length = int(request.headers.get("content-length") or 0)
        if length > settings.max_upload_bytes + _MULTIPART_SLACK:
            return _error(f"請求超過上傳上限（{settings.max_upload_mb} MB）", 413)
        try:
            form = await request.form(max_files=16, max_fields=32, max_part_size=1024 * 1024)
        except Exception as e:
            return _error(f"無法解析表單：{e}", 400)

        try:
            params = parse_params(form.get("params"))
        except ValidationError as e:
            return _error("參數驗證失敗", 422, details=_validation_details(e))
        except ValueError as e:
            return _error(str(e), 422)

        try:
            upload = None
            source = form.get("file")
            if source is not None and hasattr(source, "read"):
                data = await source.read()
                suffix = check_upload(source.filename, data, settings.max_upload_bytes)
                upload = (source.filename, suffix, data)

            custom_text = None
            custom = form.get("custom_file")
            if custom is not None and hasattr(custom, "read"):
                raw = await custom.read()
                suffix = check_upload(custom.filename or "custom.md", raw, settings.max_upload_bytes)
                if suffix not in TEXT_SUFFIXES:
                    raise UploadRejected("自訂需求檔須為 .md 或 .txt", 415)
                custom_text = raw.decode("utf-8-sig")

            overrides = {}
            for key, value in form.multi_items():
                if key.startswith(_OVERRIDE_PREFIX) and hasattr(value, "read"):
                    relpath = key[len(_OVERRIDE_PREFIX):]
                    if relpath not in OVERRIDABLE_RESOURCES:
                        return _error(f"不可覆蓋的資源：{relpath}", 400)
                    overrides[relpath] = await value.read()
        except UploadRejected as e:
            return _error(str(e), e.status)

        try:
            job = manager.create(params, upload=upload, custom_text=custom_text, overrides=overrides)
        except JobLimitExceeded as e:
            return _error(str(e), 429)
        except UploadRejected as e:
            return _error(str(e), e.status)
        except ValidationError as e:
            return _error("參數驗證失敗", 422, details=_validation_details(e))
        except ValueError as e:
            return _error(str(e), 422)
        return JSONResponse({"job_id": job.id, "status": job.status}, status_code=202)

    def _job_or_404(request: Request):
        try:
            return manager.get(request.path_params["job_id"])
        except KeyError:
            return None

    async def get_job(request: Request):
        job = _job_or_404(request)
        if job is None:
            return _error("找不到工作", 404)
        return JSONResponse(job.public())

    async def cancel_job(request: Request):
        job = _job_or_404(request)
        if job is None:
            return _error("找不到工作", 404)
        return JSONResponse(manager.cancel(job.id).public())

    async def job_events(request: Request):
        job = _job_or_404(request)
        if job is None:
            return _error("找不到工作", 404)
        try:
            since = int(request.query_params.get("since") or request.headers.get("last-event-id") or 0)
        except ValueError:
            since = 0

        async def stream():
            seq = since
            idle = 0.0
            while True:
                events, finished = manager.events_since(job.id, seq)
                for ev in events:
                    seq = ev["seq"]
                    yield f"id: {seq}\nevent: progress\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if finished and not events:
                    summary = json.dumps(manager.get(job.id).public(), ensure_ascii=False)
                    yield f"event: end\ndata: {summary}\n\n"
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(_SSE_POLL_SECONDS)
                idle = 0.0 if events else idle + _SSE_POLL_SECONDS
                if idle >= _SSE_KEEPALIVE_SECONDS:
                    idle = 0.0
                    yield ": keepalive\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def list_files(request: Request):
        job = _job_or_404(request)
        if job is None:
            return _error("找不到工作", 404)
        return JSONResponse({"files": storage.list_outputs(job.id)})

    async def get_file(request: Request):
        job = _job_or_404(request)
        if job is None:
            return _error("找不到工作", 404)
        try:
            path = storage.resolve_output(job.id, request.path_params["path"])
        except FileNotFoundError:
            return _error("找不到檔案", 404)
        media_type = "text/markdown; charset=utf-8" if path.suffix == ".md" else None
        return FileResponse(path, media_type=media_type)

    async def download(request: Request):
        job = _job_or_404(request)
        if job is None:
            return _error("找不到工作", 404)
        data = await anyio.to_thread.run_sync(storage.zip_outputs, job.id)
        return Response(
            data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="lit_{job.id[:8]}.zip"'},
        )

    routes = [
        Route("/", index),
        Route("/api/health", health),
        Route("/api/options", options),
        Route("/api/plan", plan, methods=["POST"]),
        Route("/api/jobs", create_job, methods=["POST"]),
        Route("/api/jobs/{job_id}", get_job),
        Route("/api/jobs/{job_id}/cancel", cancel_job, methods=["POST"]),
        Route("/api/jobs/{job_id}/events", job_events),
        Route("/api/jobs/{job_id}/files", list_files),
        Route("/api/jobs/{job_id}/files/{path:path}", get_file),
        Route("/api/jobs/{job_id}/download", download),
    ]

    mcp = None
    if settings.enable_mcp:
        mcp, mcp_app = _configure_mcp(settings)
        routes.append(Mount("/", app=mcp_app))  # 子應用自帶 /mcp 路由

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async def cleanup_loop():
            while True:
                removed = manager.cleanup(settings.retention_days)
                if removed:
                    logger.info("清理過期 job：%d 個", len(removed))
                await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)

        task = asyncio.create_task(cleanup_loop())
        try:
            if mcp is not None:
                async with mcp.session_manager.run():
                    yield
            else:
                yield
        finally:
            task.cancel()
            manager.shutdown()

    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.manager = manager
    app.state.settings = settings
    app.add_middleware(BearerAuthMiddleware, token=settings.api_token, trust_proxy=settings.trust_proxy_auth)
    return app
