# -*- coding: utf-8 -*-
"""job 模型與執行器

上傳 → 建立 job（驗證參數，不合法則不建立）→ ThreadPool 背景執行核心 API →
ProgressEvent 存入 job 事件（SSE 端點輪詢、斷線可回放）→ 結果寫入 job output/。

同步核心 API 在 worker thread 執行（與 MCP server 的 _run_generation 同一模式）；
提交時以 contextvars.copy_context().run 帶入 per-job 資源覆蓋層。
"""

import contextvars
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from claude_lit.api import generate_slides as api_generate_slides
from claude_lit.api import generate_zettel as api_generate_zettel
from claude_lit.api.errors import LitWorkflowError
from claude_lit.api.models import (
    DetailLevel,
    Language,
    MediaType,
    OutputFormat,
    SlideRequest,
    SlideStyle,
    ZettelRequest,
)
from claude_lit.api.progress import ProgressEvent
from claude_lit.resource_loader import use_overlay

from .auth import redact_secrets
from .storage import JobStorage, safe_stem

logger = logging.getLogger("claude_lit_workflow.web.jobs")

PROVIDERS = ("auto", "google", "openai", "anthropic", "ollama", "nvidia")
TERMINAL = ("succeeded", "failed", "cancelled")
_MAX_CUSTOM_FILE_CHARS = 20000


class JobParams(BaseModel):
    """網頁 / REST client 可設定的生成參數（來源檔另以上傳提供）"""

    kinds: List[Literal["slides", "zettel"]] = Field(default_factory=lambda: ["slides"], min_length=1)
    url: Optional[str] = None
    media_type: MediaType = MediaType.paper
    style: SlideStyle = SlideStyle.modern_academic
    detail: DetailLevel = DetailLevel.standard
    language: Language = Language.chinese
    slide_count: Optional[int] = Field(None, ge=3, le=60)
    output_format: OutputFormat = OutputFormat.markdown
    custom_requirements: Optional[str] = None
    provider: str = "auto"
    model: Optional[str] = None
    cite_key: Optional[str] = None
    domain: str = "Research"
    source_meta: Dict[str, str] = {}
    chapter: Optional[str] = None
    keep_fillers: bool = False
    ground: bool = True

    @field_validator("kinds")
    @classmethod
    def _unique_kinds(cls, v):
        # 依序執行；slides 一定在 zettel 之前（投影片內容作為 zettel 參考）
        return [k for k in ("slides", "zettel") if k in v]

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, v):
        if v not in PROVIDERS:
            raise ValueError(f"provider 須為 {', '.join(PROVIDERS)}")
        return v


class JobCancelled(Exception):
    """執行中被取消（於下一個進度階段中止）"""


class JobLimitExceeded(Exception):
    """超過每日 job 數上限"""


class Job(BaseModel):
    id: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    params: JobParams
    input_name: Optional[str] = None  # 使用者原始檔名（僅顯示用）
    input_suffix: Optional[str] = None
    has_custom_file: bool = False
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    events: List[Dict[str, Any]] = []
    results: Dict[str, Any] = {}
    error: Optional[Dict[str, Optional[str]]] = None
    warnings: List[str] = []

    def public(self) -> dict:
        data = self.model_dump(mode="json", exclude={"events"})
        data["event_count"] = len(self.events)
        return data


def _source_slug(job: Job) -> str:
    if job.input_name:
        return safe_stem(job.input_name)
    if job.params.url:
        parsed = urlparse(job.params.url)
        return safe_stem((parsed.netloc + parsed.path).replace("/", "_"), fallback="web")
    return "source"


class JobManager:
    """job 生命週期管理（記憶體索引 + 每個 job 一個 job.json）"""

    def __init__(
        self,
        storage: JobStorage,
        *,
        max_workers: int = 2,
        max_custom_chars: int = 2000,
        daily_job_limit: int = 0,
        slides_fn: Optional[Callable] = None,
        zettel_fn: Optional[Callable] = None,
    ):
        self.storage = storage
        self.max_custom_chars = max_custom_chars
        self.daily_job_limit = daily_job_limit
        self._slides_fn = slides_fn
        self._zettel_fn = zettel_fn
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}
        self._cancel: Dict[str, threading.Event] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="lit-job")
        self._recover()

    # ── 生成函式（預設為核心 API；測試可注入）────────────────────────────────

    @property
    def slides_fn(self) -> Callable:
        return self._slides_fn or api_generate_slides

    @property
    def zettel_fn(self) -> Callable:
        return self._zettel_fn or api_generate_zettel

    # ── 持久化 ──────────────────────────────────────────────────────────────

    def _job_file(self, job_id: str) -> Path:
        return self.storage.job_dir(job_id) / "job.json"

    def _save(self, job: Job) -> None:
        path = self._job_file(job.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def _recover(self) -> None:
        """載入既有 job；上次行程中斷時仍在 queued / running 的標為 failed"""
        for job_id in self.storage.job_ids():
            path = self._job_file(job_id)
            if not path.exists():
                continue
            try:
                job = Job.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("無法載入 job %s：%s", job_id, e)
                continue
            if job.status not in TERMINAL:
                job.status = "failed"
                job.error = {"message": "服務重新啟動，執行中的工作已中斷", "hint": "請重新送出"}
                job.finished_at = time.time()
                self._save(job)
            self._jobs[job_id] = job

    # ── 建立 / 查詢 ─────────────────────────────────────────────────────────

    def jobs_created_today(self) -> int:
        today = datetime.now().date()
        with self._lock:
            return sum(1 for j in self._jobs.values() if datetime.fromtimestamp(j.created_at).date() == today)

    def build_requests(self, job: Job) -> Dict[str, BaseModel]:
        """job 參數 → 核心 API Request（建立前驗證、執行時使用同一份）"""
        p = job.params
        job_dir = self.storage.job_dir(job.id)
        output = job_dir / "output"
        source: Dict[str, Any] = {}
        if job.input_suffix:
            path = job_dir / "input" / f"source{job.input_suffix}"
            source = {"pdf": path} if job.input_suffix == ".pdf" else {"text": path}
        elif p.url:
            source = {"url": p.url}
        common = dict(
            media_type=p.media_type,
            source_meta=p.source_meta,
            chapter=p.chapter,
            keep_fillers=p.keep_fillers,
            language=p.language,
            detail=p.detail,
            provider=p.provider,
            model=p.model,
            custom_requirements=self._custom_requirements(job),
        )
        requests: Dict[str, BaseModel] = {}
        if "slides" in p.kinds:
            slide_count = p.slide_count or self._default_slide_count(p.media_type)
            name = f"{_source_slug(job)}_{p.style.value}_{datetime.fromtimestamp(job.created_at):%Y%m%d}"
            requests["slides"] = SlideRequest(
                **source, **common,
                style=p.style,
                slide_count=slide_count,
                output_format=p.output_format,
                output_path=output / "slides" / f"{name}.md",
            )
        if "zettel" in p.kinds:
            requests["zettel"] = ZettelRequest(
                **source, **common,
                domain=p.domain,
                cite_key=p.cite_key,
                ground=p.ground,
                add_to_kb=False,  # 服務模式不寫伺服器知識庫（與 MCP 預設一致）
                output_root=output,
            )
        return requests

    @staticmethod
    def _default_slide_count(media_type: MediaType) -> int:
        if media_type == MediaType.paper:
            return 15
        from claude_lit.api.media import get_media_profile

        return int(get_media_profile(media_type.value).get("default_slide_count", 15))

    def _custom_requirements(self, job: Job) -> Optional[str]:
        parts = []
        if job.has_custom_file:
            path = self.storage.job_dir(job.id) / "input" / "custom.md"
            if path.exists():
                parts.append(path.read_text(encoding="utf-8"))
        if job.params.custom_requirements:
            parts.append(job.params.custom_requirements)
        return "\n\n".join(parts) or None

    def create(
        self,
        params: JobParams,
        *,
        upload: Optional[tuple] = None,  # (原始檔名, 副檔名, bytes)；已通過 check_upload
        custom_text: Optional[str] = None,
        overrides: Optional[Dict[str, bytes]] = None,
    ) -> Job:
        """驗證並建立 job、排入執行。驗證失敗拋 ValueError，且不建立 job 目錄。"""
        if params.custom_requirements and len(params.custom_requirements) > self.max_custom_chars:
            raise ValueError(f"提示詞超過 {self.max_custom_chars} 字元上限")
        if custom_text and len(custom_text) > _MAX_CUSTOM_FILE_CHARS:
            raise ValueError(f"自訂需求檔超過 {_MAX_CUSTOM_FILE_CHARS} 字元上限")
        if upload is None and not params.url:
            raise ValueError("請上傳檔案或提供 url")
        if upload is not None and params.url:
            raise ValueError("上傳檔案與 url 只能擇一")
        if self.daily_job_limit and self.jobs_created_today() >= self.daily_job_limit:
            raise JobLimitExceeded(f"已達每日 {self.daily_job_limit} 個工作上限")

        job = Job(
            id=uuid.uuid4().hex,
            params=params,
            input_name=upload[0] if upload else None,
            input_suffix=upload[1] if upload else None,
            has_custom_file=bool(custom_text),
        )
        self.build_requests(job)  # 參數組合不合法 → pydantic ValidationError（ValueError）

        self.storage.create(job.id)
        try:
            if upload:
                self.storage.save_input(job.id, upload[1], upload[2])
            if custom_text:
                (self.storage.job_dir(job.id) / "input" / "custom.md").write_text(custom_text, encoding="utf-8")
            for relpath, data in (overrides or {}).items():
                self.storage.save_override(job.id, relpath, data)
        except Exception:
            self.storage.delete(job.id)
            raise

        with self._lock:
            self._jobs[job.id] = job
            self._cancel[job.id] = threading.Event()
            self._save(job)
            snapshot = job.model_copy(deep=True)  # 回傳建立當下狀態（queued），worker 隨後才改動
        ctx = contextvars.copy_context()
        self._executor.submit(ctx.run, self._run, job.id)
        return snapshot

    def get(self, job_id: str) -> Job:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            return self._jobs[job_id]

    def events_since(self, job_id: str, seq: int) -> tuple:
        """回傳 (seq 之後的事件, job 是否已結束)"""
        with self._lock:
            job = self.get(job_id)
            return [e for e in job.events if e["seq"] > seq], job.status in TERMINAL

    def cancel(self, job_id: str) -> Job:
        with self._lock:
            job = self.get(job_id)
            if job.status == "queued":
                self._finish(job, "cancelled")
            elif job.status == "running":
                self._cancel[job_id].set()
                self._event(job, "cancel", "已要求取消，將於下一個階段中止")
            return job

    def finished_times(self) -> Dict[str, float]:
        with self._lock:
            return {j.id: j.finished_at for j in self._jobs.values() if j.status in TERMINAL}

    def cleanup(self, retention_days: int, now: Optional[float] = None) -> List[str]:
        removed = self.storage.cleanup_expired(retention_days, self.finished_times(), now=now)
        with self._lock:
            for job_id in removed:
                self._jobs.pop(job_id, None)
                self._cancel.pop(job_id, None)
        return removed

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ── 執行 ────────────────────────────────────────────────────────────────

    def _event(self, job: Job, stage: str, message: str, **extra) -> None:
        with self._lock:
            event = {"seq": len(job.events) + 1, "stage": stage, "message": message, "time": time.time()}
            event.update({k: v for k, v in extra.items() if v is not None})
            job.events.append(event)
            self._save(job)

    def _finish(self, job: Job, status: str, error: Optional[dict] = None) -> None:
        with self._lock:
            job.status = status
            job.error = {k: redact_secrets(v) for k, v in error.items()} if error else None
            job.warnings = [redact_secrets(w) for w in job.warnings]
            job.finished_at = time.time()
            self._event(job, "status", status)

    def _relativize(self, job: Job, value: Any) -> Any:
        """結果中的伺服器絕對路徑 → job output/ 內的相對路徑（不對外暴露伺服器目錄結構）"""
        out = str(self.storage.output_dir(job.id).resolve())
        if isinstance(value, str) and value.startswith(out):
            return value[len(out):].lstrip("/\\").replace("\\", "/")
        if isinstance(value, list):
            return [self._relativize(job, v) for v in value]
        if isinstance(value, dict):
            return {k: self._relativize(job, v) for k, v in value.items()}
        return value

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                return  # 已在排隊時取消
            job.status = "running"
            job.started_at = time.time()
            self._event(job, "status", "running")
        cancel_flag = self._cancel[job_id]

        def progress(kind: str):
            def callback(ev: ProgressEvent):
                if cancel_flag.is_set():
                    raise JobCancelled()
                self._event(
                    job, ev.stage, redact_secrets(ev.message),
                    kind=kind, current=ev.current, total=ev.total,
                )
            return callback

        try:
            with use_overlay(self.storage.job_dir(job_id) / "overlay"):
                requests = self.build_requests(job)
                slides_md: Optional[str] = None
                if "slides" in requests:
                    result = self.slides_fn(requests["slides"], progress=progress("slides"))
                    job.results["slides"] = self._relativize(job, result.model_dump(mode="json"))
                    job.warnings.extend(result.warnings)
                    md_files = [f for f in result.output_files if f.endswith(".md")]
                    if md_files and Path(md_files[0]).exists():
                        slides_md = Path(md_files[0]).read_text(encoding="utf-8")
                if "zettel" in requests:
                    zreq = requests["zettel"]
                    if slides_md:
                        zreq = zreq.model_copy(update={"slides_content": slides_md})
                    result = self.zettel_fn(zreq, progress=progress("zettel"))
                    job.results["zettel"] = self._relativize(job, result.model_dump(mode="json"))
                    job.warnings.extend(result.warnings)
            self._finish(job, "succeeded")
        except JobCancelled:
            self._finish(job, "cancelled")
        except LitWorkflowError as e:
            self._finish(job, "failed", {"message": str(e), "hint": e.hint})
        except Exception as e:  # 單一 job 失敗不影響服務
            logger.exception("job %s 失敗", job_id)
            self._finish(job, "failed", {"message": f"未預期的錯誤：{e}", "hint": None})


def parse_params(raw: Optional[str]) -> JobParams:
    """multipart 的 params 欄位（JSON 字串）→ JobParams；格式錯誤拋 ValueError"""
    if not raw:
        return JobParams()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"params 不是有效的 JSON：{e}") from e
    if not isinstance(data, dict):
        raise ValueError("params 須為 JSON 物件")
    return JobParams.model_validate(data)
