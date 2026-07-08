# -*- coding: utf-8 -*-
"""api.slides.generate_slides 測試（spec: slide-generation）

LLM 呼叫以 monkeypatch mock，測試可離線重複執行。
"""

from pathlib import Path

import pytest

from claude_lit.api.errors import LLMGenerationError, ProviderUnavailableError, SourceNotFoundError
from claude_lit.api.models import SlideRequest
from claude_lit.api.slides import generate_slides
from claude_lit.generators import SlideMaker

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_slides_output.txt"


@pytest.fixture
def mock_llm(monkeypatch):
    """mock SlideMaker.call_llm 回傳 fixture 內容"""
    output = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(
        SlideMaker, "call_llm", lambda self, prompt, **kw: (output, "google")
    )
    return output


class TestGenerateSlides:
    def test_topic_to_markdown(self, mock_llm, tmp_path, capsys):
        req = SlideRequest(
            topic="測試主題",
            output_format="markdown",
            output_path=tmp_path / "out.md",
        )
        result = generate_slides(req)

        assert result.slide_count == 3
        assert result.provider_used == "google"
        assert len(result.output_files) == 1
        out_file = Path(result.output_files[0])
        assert out_file.exists() and out_file.suffix == ".md"
        # 核心層不得寫 stdout
        assert capsys.readouterr().out == ""

    def test_result_metadata(self, mock_llm, tmp_path):
        req = SlideRequest(topic="t", output_path=tmp_path / "o.md")
        result = generate_slides(req)
        assert result.style == "modern_academic"
        assert result.detail == "standard"
        assert result.language == "chinese"
        assert result.preview  # llm 輸出預覽非空

    def test_passes_slides_task_type(self, tmp_path, monkeypatch):
        """slides API 須傳 task_type='slides'（NVIDIA 任務分流依此選 nemotron）"""
        output = FIXTURE.read_text(encoding="utf-8")
        captured = {}
        monkeypatch.setattr(
            SlideMaker, "call_llm",
            lambda self, prompt, **kw: captured.update(kw) or (output, "nvidia"),
        )
        req = SlideRequest(topic="t", output_path=tmp_path / "o.md")
        generate_slides(req)
        assert captured.get("task_type") == "slides"

    def test_progress_events_in_order(self, mock_llm, tmp_path):
        events = []
        req = SlideRequest(topic="t", output_path=tmp_path / "o.md")
        generate_slides(req, progress=events.append)
        stages = [e.stage for e in events]
        # topic-only：無 extract，依序 prompt → llm → write
        assert [s for s in stages if s in ("prompt", "llm", "write")] == [
            "prompt",
            "llm",
            "write",
        ]
        assert all(e.message for e in events)

    def test_pdf_source_emits_extract(self, mock_llm, tmp_path, monkeypatch):
        import claude_lit.api.slides as slides_mod

        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        from claude_lit.api.sources import SourceContent

        monkeypatch.setattr(
            slides_mod,
            "resolve_source",
            lambda **kw: SourceContent(content="內容", topic="p", source_type="pdf"),
        )
        events = []
        req = SlideRequest(pdf=pdf, output_path=tmp_path / "o.md")
        generate_slides(req, progress=events.append)
        assert events[0].stage == "extract"

    def test_pdf_not_found(self):
        req = SlideRequest(pdf="D:/nonexistent/x.pdf")
        with pytest.raises(SourceNotFoundError):
            generate_slides(req)

    def test_provider_unavailable(self, tmp_path, monkeypatch):
        def raise_runtime(self, prompt, **kw):
            raise RuntimeError("所有LLM提供者都不可用")

        monkeypatch.setattr(SlideMaker, "call_llm", raise_runtime)
        req = SlideRequest(topic="t", output_path=tmp_path / "o.md")
        with pytest.raises(ProviderUnavailableError) as exc_info:
            generate_slides(req)
        assert "setup" in (exc_info.value.hint or "")

    def test_unparseable_llm_output(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            SlideMaker, "call_llm", lambda self, prompt, **kw: ("純文字無任何結構", "google")
        )
        req = SlideRequest(topic="t", output_path=tmp_path / "o.md")
        with pytest.raises(LLMGenerationError):
            generate_slides(req)
