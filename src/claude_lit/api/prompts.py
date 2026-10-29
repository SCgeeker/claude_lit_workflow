# -*- coding: utf-8 -*-
"""Prompt 渲染 API

回傳渲染完成的完整 LLM 提示詞。
CLI 內部使用；change 2 的 MCP Prompts 直接重用這兩個函式。
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import yaml
from jinja2 import Template

from claude_lit.generators import SlideMaker
from claude_lit.resource_loader import resolve_resource

from . import media as media_api
from .errors import CiteKeyMissingError
from .models import SlideRequest, ZettelRequest
from .sources import SourceContent, resolve_source

# 抽取上限（單一真相；api.zettel 直接沿用本常數，勿另立字面量）。
# 120000 字元 ≈ 30k tokens，足以容納整篇論文（含長 review）全文，
# 涵蓋 Gemini 1M / Claude 200k / GPT-4o-mini 128k / NVIDIA llama-3.1-8b 128k。
_ZETTEL_MAX_CHARS = 120000
_SLIDES_MAX_CHARS = 50000  # 與 api.slides._SLIDES_MAX_CHARS 同步


def _load_styles_config() -> dict:
    styles_path = resolve_resource("templates/styles/academic_styles.yaml")
    return yaml.safe_load(styles_path.read_text(encoding="utf-8"))


def get_card_count(detail: str) -> int:
    """依詳細程度取得目標卡片數（來源：academic_styles.yaml zettelkasten 設定）"""
    config = _load_styles_config()
    return config["styles"]["zettelkasten"]["default_card_count"].get(detail, 12)


def source_kwargs(request, max_chars: int) -> dict:
    """Slide/ZettelRequest → resolve_source 參數（slides 與 zettel、prompt 與生成共用）

    呼叫端各自呼叫自己模組匯入的 resolve_source（測試以模組屬性替換來源）。
    """
    return dict(
        topic=getattr(request, "topic", None),
        pdf=request.pdf,
        url=request.url,
        from_kb=request.from_kb,
        text=request.text,
        content=getattr(request, "content", None),
        max_chars=max_chars,
        media_type=request.media_type.value,
        chapter=request.chapter,
        keep_fillers=request.keep_fillers,
    )


def _source_meta(request) -> dict:
    """使用者 metadata；指定章節時自動補上 chapter（供引用格式的 {chapter}）"""
    meta = dict(request.source_meta)
    if request.chapter and not meta.get("chapter"):
        meta["chapter"] = request.chapter
    return meta


def resolve_cite_key(request: ZettelRequest, source: SourceContent) -> str:
    """解析 cite_key：明確傳入 > 知識庫論文 > URL slug > PDF / 文字檔檔名；
    指定章節時加 -chNN 後綴（同書不同章的卡片 ID 不衝突）。

    Raises:
        CiteKeyMissingError: from_kb 論文缺 cite_key 時
    """
    return _resolve_base_cite_key(request, source) + media_api.chapter_suffix(request.chapter)


def _resolve_base_cite_key(request: ZettelRequest, source: SourceContent) -> str:
    if request.cite_key and request.cite_key.strip():
        return request.cite_key.strip()

    if request.from_kb is not None:
        paper = source.paper_data or {}
        cite_key = (paper.get("cite_key") or "").strip()
        if cite_key:
            return cite_key
        raise CiteKeyMissingError(
            f"論文 ID {paper.get('id', request.from_kb)} 缺少 cite_key",
            hint=(
                "請執行：1. uv run kb check-cite-keys "
                "2. uv run kb update-from-bib 'My Library.bib'，"
                "或以 --citekey 手動指定"
            ),
        )

    if request.url:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", request.url.split("//")[-1])[:40]

    if request.pdf:
        return Path(request.pdf).stem

    if request.text:
        return Path(request.text).stem

    raise CiteKeyMissingError("無法解析 cite_key", hint="請以 --citekey 手動指定")


def slides_template_options(request: SlideRequest) -> dict:
    """paper → {}（既有 journal_club_template）；其他媒體 → 媒體模板路徑與 profile 變數"""
    media_type = request.media_type.value
    if media_api.is_legacy(media_type):
        return {}
    return {
        "template_path": resolve_resource(media_api.MEDIA_SLIDES_TEMPLATE),
        "extra_context": media_api.build_media_context(
            media_type, source_meta=_source_meta(request)
        ),
    }


def render_slides_prompt(request: SlideRequest) -> str:
    """渲染投影片生成提示詞（paper：journal_club_template；其他：media_slides_template）"""
    source = resolve_source(**source_kwargs(request, _SLIDES_MAX_CHARS))
    maker = SlideMaker(llm_provider=request.provider)
    return maker.generate_prompt(
        topic=source.topic or "簡報",
        style=request.style.value,
        detail_level=request.detail.value,
        language=request.language.value,
        slide_count=request.slide_count,
        pdf_content=source.content,
        source_type=source.source_type,
        custom_requirements=request.custom_requirements,
        **slides_template_options(request),
    )


def zettel_citation(request: ZettelRequest, source: SourceContent, cite_key: str) -> Optional[str]:
    """媒體來源的卡片來源連結（paper 回傳 None，沿用既有格式）"""
    media_type = request.media_type.value
    if media_api.is_legacy(media_type):
        return None
    profile = media_api.get_media_profile(media_type)
    return media_api.render_citation(
        profile, cite_key, _source_meta(request), fallback=source.topic
    )


def render_zettel_prompt(
    request: ZettelRequest,
    *,
    source: Optional[SourceContent] = None,
    cite_key: Optional[str] = None,
    related_cards: Optional[List[dict]] = None,
) -> str:
    """渲染 Zettel 卡片生成提示詞（paper：zettelkasten_template；其他：media_zettel_template）

    source / cite_key / related_cards 可由呼叫端（generate_zettel）傳入以避免重複解析。
    """
    if source is None:
        source = resolve_source(**source_kwargs(request, _ZETTEL_MAX_CHARS))
    if cite_key is None:
        cite_key = resolve_cite_key(request, source)

    media_type = request.media_type.value
    extra_context: dict = {}
    if media_api.is_legacy(media_type):
        template_path = resolve_resource("templates/prompts/zettelkasten_template.jinja2")
    else:
        template_path = resolve_resource(media_api.MEDIA_ZETTEL_TEMPLATE)
        extra_context = media_api.build_media_context(
            media_type, cite_key=cite_key, source_meta=_source_meta(request), topic=source.topic
        )
    template = Template(template_path.read_text(encoding="utf-8"))

    return template.render(
        **extra_context,
        topic=source.topic,
        pdf_content=source.content,
        source_type=source.source_type,
        card_count=get_card_count(request.detail.value),
        domain=request.domain,
        date=datetime.now().strftime("%Y%m%d"),
        cite_key=cite_key,
        language=request.language.value,
        existing_related_cards=related_cards or [],
        custom_requirements=request.custom_requirements,
        slides_content=request.slides_content,
    )
