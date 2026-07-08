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

from .errors import CiteKeyMissingError
from .models import SlideRequest, ZettelRequest
from .sources import SourceContent, resolve_source

_ZETTEL_MAX_CHARS = 40000
_SLIDES_MAX_CHARS = 10000


def _load_styles_config() -> dict:
    styles_path = resolve_resource("templates/styles/academic_styles.yaml")
    return yaml.safe_load(styles_path.read_text(encoding="utf-8"))


def get_card_count(detail: str) -> int:
    """依詳細程度取得目標卡片數（來源：academic_styles.yaml zettelkasten 設定）"""
    config = _load_styles_config()
    return config["styles"]["zettelkasten"]["default_card_count"].get(detail, 12)


def resolve_cite_key(request: ZettelRequest, source: SourceContent) -> str:
    """解析 cite_key：明確傳入 > 知識庫論文 > URL slug > PDF 檔名。

    Raises:
        CiteKeyMissingError: from_kb 論文缺 cite_key 時
    """
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

    raise CiteKeyMissingError("無法解析 cite_key", hint="請以 --citekey 手動指定")


def render_slides_prompt(request: SlideRequest) -> str:
    """渲染投影片生成提示詞（journal_club_template.jinja2）"""
    source = resolve_source(
        topic=request.topic,
        pdf=request.pdf,
        url=request.url,
        from_kb=request.from_kb,
        content=request.content,
        max_chars=_SLIDES_MAX_CHARS,
    )
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
    )


def render_zettel_prompt(
    request: ZettelRequest,
    *,
    source: Optional[SourceContent] = None,
    cite_key: Optional[str] = None,
    related_cards: Optional[List[dict]] = None,
) -> str:
    """渲染 Zettel 卡片生成提示詞（zettelkasten_template.jinja2）

    source / cite_key / related_cards 可由呼叫端（generate_zettel）傳入以避免重複解析。
    """
    if source is None:
        source = resolve_source(
            pdf=request.pdf,
            url=request.url,
            from_kb=request.from_kb,
            max_chars=_ZETTEL_MAX_CHARS,
        )
    if cite_key is None:
        cite_key = resolve_cite_key(request, source)

    template_path = resolve_resource("templates/prompts/zettelkasten_template.jinja2")
    template = Template(template_path.read_text(encoding="utf-8"))

    return template.render(
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
