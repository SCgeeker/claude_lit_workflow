# -*- coding: utf-8 -*-
"""api.models / api.errors / api.progress 驗證規則測試（spec: slide-generation, zettel-generation）"""

import pytest
from pydantic import ValidationError

from claude_lit.api.errors import (
    CiteKeyMissingError,
    ConfigError,
    ExtractionError,
    LitWorkflowError,
    LLMGenerationError,
    ProviderUnavailableError,
    SourceNotFoundError,
)
from claude_lit.api.models import (
    DetailLevel,
    Language,
    OutputFormat,
    SlideRequest,
    SlideStyle,
    ZettelRequest,
)
from claude_lit.api.progress import ProgressEvent


class TestSlideRequest:
    def test_requires_at_least_one_source(self):
        with pytest.raises(ValidationError):
            SlideRequest()

    def test_topic_only_is_valid(self):
        req = SlideRequest(topic="深度學習應用")
        assert req.topic == "深度學習應用"

    def test_pdf_and_url_mutually_exclusive(self):
        with pytest.raises(ValidationError):
            SlideRequest(pdf="paper.pdf", url="https://example.com")

    def test_from_kb_exclusive_with_pdf(self):
        with pytest.raises(ValidationError):
            SlideRequest(from_kb=1, pdf="paper.pdf")

    def test_defaults(self):
        req = SlideRequest(topic="t")
        assert req.style == SlideStyle.modern_academic
        assert req.detail == DetailLevel.standard
        assert req.language == Language.chinese
        assert req.output_format == OutputFormat.markdown
        assert req.slide_count == 15
        assert req.provider == "auto"

    def test_invalid_style_rejected_with_options_listed(self):
        with pytest.raises(ValidationError) as exc_info:
            SlideRequest(topic="t", style="nonexistent_style")
        # pydantic enum 錯誤訊息列出合法選項
        assert "modern_academic" in str(exc_info.value)

    @pytest.mark.parametrize("count", [2, 61])
    def test_slide_count_range(self, count):
        with pytest.raises(ValidationError):
            SlideRequest(topic="t", slide_count=count)

    def test_seven_slide_styles(self):
        assert len(SlideStyle) == 7


class TestZettelRequest:
    def test_requires_one_source(self):
        with pytest.raises(ValidationError):
            ZettelRequest()

    def test_pdf_and_url_mutually_exclusive(self):
        with pytest.raises(ValidationError):
            ZettelRequest(pdf="p.pdf", url="https://example.com")

    def test_defaults(self):
        req = ZettelRequest(pdf="p.pdf")
        assert req.detail == DetailLevel.standard
        assert req.language == Language.chinese
        assert req.domain == "Research"
        assert req.add_to_kb is True
        assert req.embed is True
        assert req.cross_link is False

    def test_cross_link_requires_add_to_kb(self):
        with pytest.raises(ValidationError):
            ZettelRequest(pdf="p.pdf", add_to_kb=False, cross_link=True)

    def test_embed_normalized_off_when_no_kb(self):
        req = ZettelRequest(pdf="p.pdf", add_to_kb=False, embed=True)
        assert req.embed is False

    def test_explicit_cite_key(self):
        req = ZettelRequest(pdf="p.pdf", cite_key="Barsalou-1999")
        assert req.cite_key == "Barsalou-1999"


class TestErrors:
    def test_hierarchy(self):
        for cls in (
            SourceNotFoundError,
            ExtractionError,
            CiteKeyMissingError,
            ProviderUnavailableError,
            LLMGenerationError,
            ConfigError,
        ):
            assert issubclass(cls, LitWorkflowError)

    def test_hint_attribute(self):
        err = SourceNotFoundError("找不到 PDF", hint="請確認路徑")
        assert err.hint == "請確認路徑"
        assert "找不到 PDF" in str(err)

    def test_hint_defaults_to_none(self):
        assert LitWorkflowError("x").hint is None


class TestProgressEvent:
    def test_fields(self):
        ev = ProgressEvent(stage="llm", message="正在生成", current=1, total=3)
        assert ev.stage == "llm"
        assert ev.current == 1

    def test_current_total_optional(self):
        ev = ProgressEvent(stage="extract", message="抽取中")
        assert ev.current is None and ev.total is None
