# -*- coding: utf-8 -*-
"""網頁服務 HTTP 層測試（spec: web-service）

Starlette TestClient；生成函式以假實作注入（見 test_web_jobs）。
"""

import io
import json
import time
import zipfile

import pytest
from starlette.testclient import TestClient

from claude_lit.api.errors import ProviderUnavailableError
from claude_lit.api.guide import PlanResult
from claude_lit.web import app as app_mod
from claude_lit.web.app import create_app
from claude_lit.web.config import WebSettings, startup_error
from claude_lit.web.jobs import JobManager
from claude_lit.web.storage import JobStorage

from .test_web_jobs import fake_slides, fake_zettel

TOKEN = "test-token-123456"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PDF_BYTES = b"%PDF-1.4 fake"


@pytest.fixture
def client(tmp_path):
    settings = WebSettings(data_dir=tmp_path, api_token=TOKEN, enable_mcp=False, max_upload_mb=1,
                           max_custom_chars=50)
    manager = JobManager(JobStorage(tmp_path), slides_fn=fake_slides, zettel_fn=fake_zettel,
                         max_custom_chars=50)
    with TestClient(create_app(settings, manager=manager)) as c:
        yield c


def _post_job(client, params=None, files=None, headers=AUTH):
    files = files if files is not None else {"file": ("paper.pdf", PDF_BYTES, "application/pdf")}
    return client.post("/api/jobs", data={"params": json.dumps(params or {})}, files=files, headers=headers)


def _wait(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if body["status"] in ("succeeded", "failed", "cancelled"):
            return body
        time.sleep(0.05)
    raise AssertionError("job 未結束")


class TestAuth:
    def test_health_and_index_public(self, client):
        assert client.get("/api/health").json() == {"status": "ok"}
        page = client.get("/")
        assert page.status_code == 200 and "<title>Claude Lit Workflow</title>" in page.text

    def test_api_requires_token(self, client):
        assert client.get("/api/options").status_code == 401
        assert _post_job(client, headers={}).status_code == 401
        assert client.get("/api/options", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/api/options", headers=AUTH).status_code == 200

    def test_trust_proxy_skips_token(self, tmp_path):
        settings = WebSettings(data_dir=tmp_path, trust_proxy_auth=True, enable_mcp=False)
        with TestClient(create_app(settings)) as c:
            assert c.get("/api/options").status_code == 200

    def test_public_bind_without_auth_refused(self):
        assert startup_error("0.0.0.0", WebSettings()) is not None
        assert startup_error("127.0.0.1", WebSettings()) is None
        assert startup_error("0.0.0.0", WebSettings(api_token="x" * 12)) is None
        assert startup_error("0.0.0.0", WebSettings(trust_proxy_auth=True)) is None


class TestOptions:
    def test_catalog_and_limits(self, client):
        body = client.get("/api/options", headers=AUTH).json()
        assert set(body["media_types"]) >= {"paper", "podcast", "textbook"}
        assert body["media_defaults"]["textbook"]["chaptered"] is True
        assert body["media_defaults"]["blog"]["default_slide_count"] == 8
        assert body["limits"]["max_custom_chars"] == 50
        assert "api_key" not in json.dumps(body).lower()


class TestJobs:
    def test_create_and_complete(self, client):
        r = _post_job(client, {"kinds": ["slides", "zettel"], "style": "teaching"})
        assert r.status_code == 202
        assert r.json()["status"] == "queued"
        job = _wait(client, r.json()["job_id"])
        assert job["status"] == "succeeded"
        assert job["results"]["slides"]["slide_count"] == 3
        assert "events" not in job and job["event_count"] >= 2

    def test_invalid_params_422_and_no_job(self, client, tmp_path):
        r = _post_job(client, {"slide_count": 500})
        assert r.status_code == 422
        assert any(d["field"] == "slide_count" for d in r.json()["details"])
        assert not list((tmp_path / "jobs").iterdir())

    def test_bad_params_json(self, client):
        r = client.post("/api/jobs", data={"params": "{not json"}, files={"file": ("a.pdf", PDF_BYTES)}, headers=AUTH)
        assert r.status_code == 422

    def test_prompt_too_long(self, client):
        assert _post_job(client, {"custom_requirements": "x" * 51}).status_code == 422

    def test_upload_too_large(self, client):
        big = b"%PDF" + b"0" * (2 * 1024 * 1024)
        r = _post_job(client, files={"file": ("big.pdf", big, "application/pdf")})
        assert r.status_code == 413

    def test_unsupported_type(self, client):
        assert _post_job(client, files={"file": ("a.docx", b"PK\x03\x04", "x")}).status_code == 415

    def test_magic_bytes_mismatch(self, client):
        assert _post_job(client, files={"file": ("fake.pdf", b"not a pdf", "application/pdf")}).status_code == 415

    def test_text_must_be_utf8(self, client):
        assert _post_job(client, files={"file": ("t.srt", b"\xff\xfe\x00bad", "text/plain")}).status_code == 415

    def test_override_not_allowed(self, client):
        files = {"file": ("a.pdf", PDF_BYTES), "override:config/settings.yaml": ("s.yaml", b"x: 1")}
        assert _post_job(client, files=files).status_code == 400

    def test_jinja_template_override_rejected(self, client):
        # 未沙箱化的 Jinja 模板可在伺服器執行任意程式碼，不開放覆蓋
        evil = b"{{ cycler.__init__.__globals__.os.popen('id').read() }}"
        rel = "templates/prompts/journal_club_template.jinja2"
        files = {"file": ("a.pdf", PDF_BYTES), f"override:{rel}": ("t.jinja2", evil)}
        assert _post_job(client, files=files).status_code == 400

    def test_media_profiles_override_accepted(self, client):
        rel = "templates/styles/media_profiles.yaml"
        files = {"file": ("a.pdf", PDF_BYTES), f"override:{rel}": ("m.yaml", b"media_types: {}")}
        assert _post_job(client, files=files).status_code == 202

    def test_custom_file_must_be_text(self, client):
        files = {"file": ("a.pdf", PDF_BYTES), "custom_file": ("c.pdf", PDF_BYTES)}
        assert _post_job(client, files=files).status_code == 415

    def test_url_source(self, client):
        r = client.post("/api/jobs", data={"params": json.dumps({"url": "https://example.org/post"})}, headers=AUTH)
        assert r.status_code == 202

    def test_unknown_job_404(self, client):
        assert client.get("/api/jobs/" + "0" * 32, headers=AUTH).status_code == 404
        assert client.get("/api/jobs/not-a-job", headers=AUTH).status_code == 404


class TestEventsAndFiles:
    def test_sse_replays_then_ends(self, client):
        job_id = _post_job(client).json()["job_id"]
        _wait(client, job_id)
        with client.stream("GET", f"/api/jobs/{job_id}/events", headers=AUTH) as r:
            assert r.headers["content-type"].startswith("text/event-stream")
            body = "".join(r.iter_text())
        progress = [json.loads(line[6:]) for line in body.splitlines()
                    if line.startswith("data: ") and '"seq"' in line]
        assert [e["stage"] for e in progress] == ["status", "extract", "write", "status"]
        assert "event: end" in body

    def test_sse_since_skips_seen(self, client):
        job_id = _post_job(client).json()["job_id"]
        _wait(client, job_id)
        with client.stream("GET", f"/api/jobs/{job_id}/events?since=3", headers=AUTH) as r:
            body = "".join(r.iter_text())
        assert body.count("event: progress") == 1

    def test_files_listing_download_and_zip(self, client):
        job_id = _post_job(client, {"kinds": ["slides", "zettel"]}).json()["job_id"]
        _wait(client, job_id)
        files = client.get(f"/api/jobs/{job_id}/files", headers=AUTH).json()["files"]
        slides = next(f for f in files if f.startswith("slides/"))
        r = client.get(f"/api/jobs/{job_id}/files/{slides}", headers=AUTH)
        assert r.status_code == 200 and "# 投影片" in r.text
        z = client.get(f"/api/jobs/{job_id}/download", headers=AUTH)
        assert z.headers["content-type"] == "application/zip"
        names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
        assert slides in names
        assert "zettelkasten_notes/zettel_X_20260101/zettel_cards/X-001.md" in names

    def test_path_traversal_404(self, client, tmp_path):
        (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
        job_id = _post_job(client).json()["job_id"]
        _wait(client, job_id)
        for path in ("../../../secret.txt", "..%2F..%2F..%2Fsecret.txt", "/etc/passwd"):
            r = client.get(f"/api/jobs/{job_id}/files/{path}", headers=AUTH)
            assert r.status_code == 404, path
            assert "secret" not in r.text


class TestPlan:
    def test_plan_returns_params(self, client, monkeypatch):
        monkeypatch.setattr(
            app_mod, "plan_request",
            lambda text, **kw: PlanResult(params={"media_type": "podcast"}, warnings=[], provider_used="google"),
        )
        r = client.post("/api/plan", json={"text": "把 podcast 做成卡片"}, headers=AUTH)
        assert r.status_code == 200 and r.json()["params"] == {"media_type": "podcast"}

    def test_plan_provider_unavailable(self, client, monkeypatch):
        def fail(text, **kw):
            raise ProviderUnavailableError("無法使用供應商", hint="執行 uv run setup")

        monkeypatch.setattr(app_mod, "plan_request", fail)
        r = client.post("/api/plan", json={"text": "x"}, headers=AUTH)
        assert r.status_code == 503 and r.json()["hint"] == "執行 uv run setup"

    def test_plan_validation(self, client):
        assert client.post("/api/plan", json={"text": ""}, headers=AUTH).status_code == 422
        assert client.post("/api/plan", json={"text": "x" * 51}, headers=AUTH).status_code == 422


class TestMcpMount:
    def test_mcp_requires_token_and_initializes(self, tmp_path):
        settings = WebSettings(data_dir=tmp_path, api_token=TOKEN)
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}
        headers = {**AUTH, "Accept": "application/json, text/event-stream", "Host": "lit.example.com"}
        with TestClient(create_app(settings)) as c:
            assert c.post("/mcp", json=init).status_code == 401
            r = c.post("/mcp", json=init, headers=headers)
            assert r.status_code == 200
            assert '"serverInfo"' in r.text
