# -*- coding: utf-8 -*-
"""媒體類型（media profile）API

media_profiles.yaml 為單一真相來源：每種媒體的閱讀方式、結構骨架、卡片類型配比、
位置／引用格式與前處理步驟。paper 走既有論文模板（legacy），其餘走通用媒體模板。
"""

import re
from collections import defaultdict
from typing import Dict, Optional

import yaml

from claude_lit.resource_loader import resolve_resource

MEDIA_PROFILES_PATH = "templates/styles/media_profiles.yaml"
MEDIA_SLIDES_TEMPLATE = "templates/prompts/media_slides_template.jinja2"
MEDIA_ZETTEL_TEMPLATE = "templates/prompts/media_zettel_template.jinja2"

# citation_format 中 metadata 缺漏時殘留的空殼（如「()」「第章」「《》」）
_EMPTY_SHELLS = re.compile(r"\(\s*\)|（\s*）|第\s*章|《\s*》|〈\s*〉")


def load_media_catalog() -> dict:
    """讀取完整 media_profiles.yaml（含 card_type_catalog 與 media_types）"""
    path = resolve_resource(MEDIA_PROFILES_PATH)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def get_media_profile(media_type: str) -> dict:
    """取得單一媒體 profile；未知類型拋 ValueError。"""
    profiles = load_media_catalog().get("media_types", {})
    if media_type not in profiles:
        raise ValueError(f"未知的媒體類型：{media_type}（可用：{', '.join(profiles)}）")
    return profiles[media_type]


def is_legacy(media_type: str) -> bool:
    """paper（或 profile 標 template: legacy）沿用既有論文模板"""
    return media_type == "paper" or get_media_profile(media_type).get("template") == "legacy"


def list_media_types() -> Dict[str, str]:
    """媒體類型目錄（鍵 → 「名稱 - 說明」），供 list_options / CLI --help"""
    profiles = load_media_catalog().get("media_types", {})
    return {
        key: f"{info.get('name', key)} - {info.get('description', '')}"
        for key, info in profiles.items()
    }


def chapter_suffix(chapter: Optional[str]) -> str:
    """'3' → '-ch03'；'3-5' → '-ch03-05'（同書不同章的卡片 ID 不衝突）"""
    if not chapter:
        return ""
    from .models import parse_chapter_range

    start, end = parse_chapter_range(chapter)
    return f"-ch{start:02d}" if start == end else f"-ch{start:02d}-{end:02d}"


def render_citation(
    profile: dict,
    cite_key: str,
    source_meta: Optional[Dict[str, str]] = None,
    *,
    fallback: Optional[str] = None,
) -> str:
    """依 profile 的 citation_format 與 source_meta 渲染來源連結。

    缺漏欄位以空字串填補、清掉殘留空殼；顯示文字為空時退回 fallback（topic）或 cite_key。
    結果必含 `|`：ZettelMaker 以此判定為來源連結而不改寫成卡片 ID。
    """
    meta = defaultdict(str, {k: v for k, v in (source_meta or {}).items() if v})
    meta["cite_key"] = cite_key
    fmt = profile.get("citation_format") or "[[{cite_key}|{cite_key}]]"
    rendered = fmt.format_map(meta)

    m = re.fullmatch(r"\[\[([^|\]]*)\|([^\]]*)\]\]", rendered)
    if not m:
        return rendered
    target, display = m.group(1), m.group(2)
    display = re.sub(r"\s{2,}", " ", _EMPTY_SHELLS.sub("", display)).strip()
    return f"[[{target}|{display or fallback or cite_key}]]"


def build_media_context(
    media_type: str,
    *,
    cite_key: Optional[str] = None,
    source_meta: Optional[Dict[str, str]] = None,
    topic: Optional[str] = None,
) -> dict:
    """媒體模板所需的額外渲染變數（media、source_meta、citation、card_type_catalog）"""
    catalog = load_media_catalog()
    profile = catalog["media_types"][media_type]
    context = {
        "media": profile,
        "source_meta": {k: v for k, v in (source_meta or {}).items() if v},
        "card_type_catalog": catalog.get("card_type_catalog", {}),
    }
    if cite_key is not None:
        context["citation"] = render_citation(
            profile, cite_key, source_meta, fallback=topic
        )
    return context
