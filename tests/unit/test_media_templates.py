# -*- coding: utf-8 -*-
"""媒體模板與 profile 測試（spec: slide-generation / zettel-generation — 依媒體類型選擇模板）

防漂移：媒體模板的輸出協定須與既有論文模板相同，解析器與 grounding gate 才能沿用。
"""

import pytest
from jinja2 import Template

from claude_lit.api import media as media_api
from claude_lit.api.models import MediaType
from claude_lit.resource_loader import resolve_resource

SLIDE_PROTOCOL = ("===標題頁===", "標題：", "副標題：", "===投影片1===", "內容：", "•")
CARD_PROTOCOL = (
    "===CARD: X-2025-001===", "標題:", "類型:", "核心:", "標籤:", "說明:", "連結網絡:",
    "來源脈絡:", "- **文獻**:", "- **位置**:", "- **情境**:", "個人筆記:", "🤖 **AI**:",
    "✍️ **Human**:", "待解問題:",
)

CATALOG = media_api.load_media_catalog()
MEDIA_KEYS = [k for k in CATALOG["media_types"] if not media_api.is_legacy(k)]


def _render(relpath: str, **context) -> str:
    return Template(resolve_resource(relpath).read_text(encoding="utf-8")).render(**context)


def _slides(media_type: str, **over) -> str:
    ctx = dict(
        topic="T", slide_count=10, style_name="s", style_description="d", detail_name="n",
        detail_description="d", detail_level="standard", language="chinese",
        pdf_content="內容", source_type="text", custom_requirements=None,
    )
    ctx.update(media_api.build_media_context(media_type, source_meta={"speaker": "王小明"}))
    ctx.update(over)
    return _render(media_api.MEDIA_SLIDES_TEMPLATE, **ctx)


def _cards(media_type: str, **over) -> str:
    ctx = dict(
        topic="T", pdf_content="內容", source_type="text", card_count=12, cite_key="X-2025",
        language="chinese", existing_related_cards=[], custom_requirements=None, slides_content=None,
    )
    ctx.update(media_api.build_media_context(media_type, cite_key="X-2025", topic="T"))
    ctx.update(over)
    return _render(media_api.MEDIA_ZETTEL_TEMPLATE, **ctx)


class TestCatalog:
    def test_enum_matches_profiles(self):
        assert set(CATALOG["media_types"]) == {m.value for m in MediaType}

    @pytest.mark.parametrize("media_type", MEDIA_KEYS)
    def test_card_types_defined(self, media_type):
        profile = CATALOG["media_types"][media_type]
        assert set(profile["card_type_weights"]) <= set(CATALOG["card_type_catalog"])

    @pytest.mark.parametrize("media_type", MEDIA_KEYS)
    def test_required_fields(self, media_type):
        profile = CATALOG["media_types"][media_type]
        for field in ("source_label", "reading_stance", "slide_structure", "slide_rules",
                      "card_type_weights", "core_rule", "location_format", "citation_format"):
            assert profile.get(field), f"{media_type} 缺 {field}"

    @pytest.mark.parametrize("media_type", MEDIA_KEYS)
    def test_citation_is_source_link(self, media_type):
        # ZettelMaker 以 `|` 判定來源連結；缺了會被當成卡片 ID 改寫成純文字
        citation = media_api.render_citation(CATALOG["media_types"][media_type], "X-2025", {})
        assert citation.startswith("[[X-2025|") and citation.endswith("]]")

    def test_list_media_types(self):
        catalog = media_api.list_media_types()
        assert list(catalog) == [m.value for m in MediaType]
        assert catalog["podcast"].startswith("Podcast 逐字稿")


class TestCitation:
    PODCAST = CATALOG["media_types"]["podcast"]

    def test_full_metadata(self):
        meta = {"show": "科學新聞", "episode": "EP42", "year": "2025"}
        assert media_api.render_citation(self.PODCAST, "K", meta) == "[[K|科學新聞 EP42 (2025)]]"

    def test_missing_fields_leave_no_empty_shells(self):
        assert media_api.render_citation(self.PODCAST, "K", {"show": "科學新聞"}) == "[[K|科學新聞]]"
        textbook = CATALOG["media_types"]["textbook"]
        assert media_api.render_citation(textbook, "K", {"authors": "Smith"}) == "[[K|Smith]]"

    def test_empty_display_falls_back(self):
        assert media_api.render_citation(self.PODCAST, "K", {}, fallback="第 42 集") == "[[K|第 42 集]]"
        assert media_api.render_citation(self.PODCAST, "K", {}) == "[[K|K]]"

    def test_chapter_suffix(self):
        assert media_api.chapter_suffix(None) == ""
        assert media_api.chapter_suffix("3") == "-ch03"
        assert media_api.chapter_suffix("3-5") == "-ch03-05"


class TestProtocolParity:
    """媒體模板與既有論文模板的輸出協定一致（任一邊改協定即失敗）"""

    @pytest.mark.parametrize("media_type", MEDIA_KEYS)
    def test_slides_protocol(self, media_type):
        prompt = _slides(media_type)
        for marker in SLIDE_PROTOCOL:
            assert marker in prompt, f"{media_type} 缺 {marker}"

    @pytest.mark.parametrize("media_type", MEDIA_KEYS)
    def test_cards_protocol(self, media_type):
        prompt = _cards(media_type)
        for marker in CARD_PROTOCOL:
            assert marker in prompt, f"{media_type} 缺 {marker}"

    def test_legacy_templates_share_protocol(self):
        legacy_slides = _render(
            "templates/prompts/journal_club_template.jinja2",
            topic="T", slide_count=10, style_name="s", style_description="d", detail_name="n",
            detail_description="d", detail_level="standard", language="chinese",
        )
        legacy_cards = _render(
            "templates/prompts/zettelkasten_template.jinja2",
            topic="T", card_count=12, cite_key="X-2025", language="chinese",
        )
        for marker in SLIDE_PROTOCOL:
            assert marker in legacy_slides
        for marker in CARD_PROTOCOL:
            assert marker in legacy_cards


class TestMediaContent:
    def test_lecture_uses_talk_structure(self):
        prompt = _slides("lecture")
        for section in CATALOG["media_types"]["lecture"]["slide_structure"]:
            assert section in prompt
        assert "研究背景、研究方法、主要發現" not in prompt
        assert "speaker：王小明" in prompt

    def test_podcast_card_types_and_attribution(self):
        prompt = _cards("podcast")
        assert "類型: [claim|concept|example|question]" in prompt
        assert "不可跨講者拼接" in prompt
        assert "[[X-2025|T]]" in prompt  # 無 metadata 時以 topic 為顯示文字

    def test_textbook_has_self_test_rules(self):
        prompt = _cards("textbook")
        assert "自我檢測" in prompt
        assert "claim" not in prompt.split("類型:")[1].split("\n")[0]

    def test_custom_requirements_appended(self):
        assert "請多用類比" in _cards("lecture", custom_requirements="請多用類比")
        assert "請多用類比" in _slides("lecture", custom_requirements="請多用類比")
