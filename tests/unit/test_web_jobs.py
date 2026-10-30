# -*- coding: utf-8 -*-
"""網頁服務 job 核心測試（spec: web-service — 非同步 job、進度、隔離、保留期）

生成函式以假實作注入（不呼叫 LLM）；驗證狀態轉移、事件回放、錯誤 hint、slides→zettel 串接、
並行上限、overlay 隔離與過期清理。
"""

import threading
import time
from pathlib import Path

import pytest

from claude_lit.api.errors import SourceNotFoundError
from claude_lit.api.models import SlideResult, ZettelResult
from claude_lit.api.progress import ProgressEvent
from claude_lit.resource_loader import resolve_resource
from claude_lit.web.jobs import JobLimitExceeded, JobManager, JobParams
from claude_lit.web.storage import JobStorage

PDF = ("paper.pdf", ".pdf", b"%PDF-1.4 fake")


def _wait(manager, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = manager.get(job_id)
        if job.status in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} 未在 {timeout}s 內結束（{manager.get(job_id).status}）")


def fake_slides(request, progress=None, **kw):
    progress(ProgressEvent(stage="extract", message="抽取"))
    progress(ProgressEvent(stage="write", message="寫入"))
    out = Path(request.output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("# 投影片\n**關鍵詞**", encoding="utf-8")
    return SlideResult(
        output_files=[str(out.resolve())], topic="t", slide_count=3, style=request.style.value,
        detail="standard", language="chinese", output_format="markdown", provider_used="google",
    )


def fake_zettel(request, progress=None, **kw):
    progress(ProgressEvent(stage="ground", message="grounded 1/1"))
    cards = Path(request.output_root) / "zettelkasten_notes" / "zettel_X_20260101" / "zettel_cards"
    cards.mkdir(parents=True, exist_ok=True)
    (cards / "X-001.md").write_text(request.slides_content or "無投影片", encoding="utf-8")
    return ZettelResult(
        output_dir=str(cards.parent.resolve()), index_file=str((cards.parent / "zettel_index.md").resolve()),
        card_files=[str((cards / "X-001.md").resolve())], card_count=1, cite_key="X", provider_used="google",
    )


@pytest.fixture
def manager(tmp_path):
    m = JobManager(JobStorage(tmp_path), slides_fn=fake_slides, zettel_fn=fake_zettel)
    yield m
    m.shutdown()


class TestLifecycle:
    def test_slides_job_succeeds_with_events(self, manager):
        job = manager.create(JobParams(kinds=["slides"], style="teaching"), upload=PDF)
        assert job.status == "queued"
        job = _wait(manager, job.id)
        assert job.status == "succeeded"
        stages = [e["stage"] for e in job.events]
        assert stages == ["status", "extract", "write", "status"]
        assert [e["seq"] for e in job.events] == [1, 2, 3, 4]
        # 結果路徑相對於 job output/，不暴露伺服器目錄
        rel = job.results["slides"]["output_files"][0]
        assert rel.startswith("slides/paper_teaching_") and rel.endswith(".md")

    def test_events_replay_since(self, manager):
        job = _wait(manager, manager.create(JobParams(), upload=PDF).id)
        events, finished = manager.events_since(job.id, 2)
        assert finished
        assert [e["seq"] for e in events] == [3, 4]

    def test_slides_then_zettel_passes_slides_content(self, manager):
        job = _wait(manager, manager.create(JobParams(kinds=["zettel", "slides"]), upload=PDF).id)
        assert job.params.kinds == ["slides", "zettel"]  # 一律先投影片
        card = manager.storage.output_dir(job.id) / "zettelkasten_notes" / "zettel_X_20260101" / "zettel_cards" / "X-001.md"
        assert "**關鍵詞**" in card.read_text(encoding="utf-8")
        assert set(job.results) == {"slides", "zettel"}

    def test_zettel_is_isolated_from_cwd_and_kb(self, tmp_path, monkeypatch):
        captured = {}

        def capture(request, progress=None, **kw):
            captured["req"] = request
            return fake_zettel(request, progress=progress)

        monkeypatch.chdir(tmp_path)
        m = JobManager(JobStorage(tmp_path / "data"), zettel_fn=capture)
        try:
            job = _wait(m, m.create(JobParams(kinds=["zettel"]), upload=PDF).id)
        finally:
            m.shutdown()
        req = captured["req"]
        assert req.add_to_kb is False
        assert Path(req.output_root) == m.storage.output_dir(job.id)
        assert not (tmp_path / "output").exists()  # 不寫入 cwd 的 output/

    def test_failure_keeps_hint(self, tmp_path):
        def boom(request, progress=None, **kw):
            raise SourceNotFoundError("找不到 PDF", hint="請確認檔案")

        m = JobManager(JobStorage(tmp_path), slides_fn=boom)
        try:
            job = _wait(m, m.create(JobParams(), upload=PDF).id)
        finally:
            m.shutdown()
        assert job.status == "failed"
        assert job.error == {"message": "找不到 PDF", "hint": "請確認檔案"}

    def test_error_message_redacts_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-abcdefghijklmnop")

        def leak(request, progress=None, **kw):
            raise RuntimeError("401 invalid key sk-test-abcdefghijklmnop")

        m = JobManager(JobStorage(tmp_path), slides_fn=leak)
        try:
            job = _wait(m, m.create(JobParams(), upload=PDF).id)
        finally:
            m.shutdown()
        assert "abcdefghijklmnop" not in job.error["message"]
        assert "abcdefghijklmnop" not in (m.storage.job_dir(job.id) / "job.json").read_text(encoding="utf-8")


class TestValidation:
    def test_invalid_combo_creates_no_job_dir(self, manager):
        with pytest.raises(ValueError):
            manager.create(JobParams(media_type="lecture", chapter="3"), upload=PDF)
        assert manager.storage.job_ids() == []

    def test_requires_source(self, manager):
        with pytest.raises(ValueError, match="上傳"):
            manager.create(JobParams())

    def test_file_and_url_exclusive(self, manager):
        with pytest.raises(ValueError, match="擇一"):
            manager.create(JobParams(url="https://example.org"), upload=PDF)

    def test_custom_requirements_limit(self, tmp_path):
        m = JobManager(JobStorage(tmp_path), max_custom_chars=10, slides_fn=fake_slides)
        try:
            with pytest.raises(ValueError, match="10"):
                m.create(JobParams(custom_requirements="x" * 11), upload=PDF)
        finally:
            m.shutdown()

    def test_daily_limit(self, tmp_path):
        m = JobManager(JobStorage(tmp_path), daily_job_limit=1, slides_fn=fake_slides)
        try:
            m.create(JobParams(), upload=PDF)
            with pytest.raises(JobLimitExceeded):
                m.create(JobParams(), upload=PDF)
        finally:
            m.shutdown()

    def test_media_default_slide_count(self, manager):
        job = manager.create(JobParams(media_type="blog"), upload=("post.md", ".md", "# x".encode()))
        assert manager.build_requests(job)["slides"].slide_count == 8
        assert manager.build_requests(job)["slides"].text.name == "source.md"


class TestConcurrencyAndIsolation:
    def test_max_workers_queues_extra_jobs(self, tmp_path):
        release = threading.Event()
        running = []

        def slow(request, progress=None, **kw):
            running.append(1)
            release.wait(5)
            return fake_slides(request, progress=progress)

        m = JobManager(JobStorage(tmp_path), max_workers=1, slides_fn=slow)
        try:
            first = m.create(JobParams(), upload=PDF)
            second = m.create(JobParams(), upload=PDF)
            time.sleep(0.2)
            assert m.get(first.id).status == "running"
            assert m.get(second.id).status == "queued"
            release.set()
            assert _wait(m, second.id).status == "succeeded"
        finally:
            release.set()
            m.shutdown()

    def test_overlay_is_per_job(self, tmp_path):
        rel = "templates/styles/media_profiles.yaml"
        seen = {}

        def record(request, progress=None, **kw):
            seen[request.output_path.parent.parent.parent.name] = resolve_resource(rel).read_text(encoding="utf-8")
            return fake_slides(request, progress=progress)

        m = JobManager(JobStorage(tmp_path), max_workers=2, slides_fn=record)
        try:
            a = m.create(JobParams(), upload=PDF, overrides={rel: "# JOB-A 模板".encode()})
            b = m.create(JobParams(), upload=PDF)
            _wait(m, a.id), _wait(m, b.id)
        finally:
            m.shutdown()
        assert seen[a.id] == "# JOB-A 模板"
        assert seen[b.id] != "# JOB-A 模板"

    def test_custom_file_merged_into_requirements(self, manager):
        job = manager.create(JobParams(custom_requirements="多用類比"), upload=PDF, custom_text="領域術語表")
        req = manager.build_requests(job)["slides"]
        assert req.custom_requirements == "領域術語表\n\n多用類比"


class TestCancelAndRecovery:
    def test_cancel_running_job(self, tmp_path):
        started = threading.Event()
        proceed = threading.Event()

        def gated(request, progress=None, **kw):
            started.set()
            proceed.wait(5)
            progress(ProgressEvent(stage="llm", message="生成中"))  # 取消旗標於此生效
            return fake_slides(request, progress=progress)

        m = JobManager(JobStorage(tmp_path), slides_fn=gated)
        try:
            job = m.create(JobParams(), upload=PDF)
            started.wait(5)
            m.cancel(job.id)
            proceed.set()
            assert _wait(m, job.id).status == "cancelled"
        finally:
            proceed.set()
            m.shutdown()

    def test_restart_marks_unfinished_failed(self, tmp_path):
        block = threading.Event()
        m1 = JobManager(JobStorage(tmp_path), slides_fn=lambda r, progress=None, **kw: block.wait(5))
        job = m1.create(JobParams(), upload=PDF)
        time.sleep(0.1)
        m2 = JobManager(JobStorage(tmp_path))  # 模擬服務重啟
        restored = m2.get(job.id)
        block.set()
        m1.shutdown(), m2.shutdown()
        assert restored.status == "failed"
        assert "重新啟動" in restored.error["message"]


class TestRetention:
    def test_expired_jobs_deleted(self, manager):
        job = _wait(manager, manager.create(JobParams(), upload=PDF).id)
        assert manager.cleanup(7, now=job.finished_at + 6 * 86400) == []
        assert manager.cleanup(7, now=job.finished_at + 8 * 86400) == [job.id]
        assert not manager.storage.job_dir(job.id).exists()
        with pytest.raises(KeyError):
            manager.get(job.id)
