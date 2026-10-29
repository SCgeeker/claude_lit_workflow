# -*- coding: utf-8 -*-
"""slides / zettel 共用的媒體類型旗標（--media / --text / --chapter / --meta / --keep-fillers）

只做參數宣告與字串轉換；媒體邏輯在 api.media / api.sources。
"""

import argparse
from typing import Dict, List, Optional

from claude_lit.api.media import get_media_profile, list_media_types
from claude_lit.api.models import CHAPTERED_MEDIA, MediaType, parse_chapter_range

MEDIA_CHOICES = [m.value for m in MediaType]


def _media_help() -> str:
    try:
        catalog = list_media_types()
    except Exception:  # 目錄讀不到不阻斷 --help
        catalog = {}
    entries = "、".join(f"{key}={desc.split(' - ')[0]}" for key, desc in catalog.items())
    return f"來源媒體類型（預設：paper）：{entries}" if entries else "來源媒體類型（預設：paper）"


def add_text_source_argument(group) -> None:
    group.add_argument('--text', type=str,
                       help='文字來源：逐字稿或文章（.txt / .md / .srt / .vtt / .epub）')


def add_media_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--media', type=str, default='paper', choices=MEDIA_CHOICES,
                        help=_media_help())
    parser.add_argument('--chapter', type=str, metavar='RANGE',
                        help='教科書／專書的章節（如 3 或 3-5；僅 --media textbook / monograph）')
    parser.add_argument('--meta', action='append', default=[], metavar='KEY=VALUE',
                        help='來源資訊，可重複（如 --meta speaker=王小明 --meta year=2025）')
    parser.add_argument('--keep-fillers', action='store_true',
                        help='逐字稿保留填充詞（嗯、呃、um、uh；預設移除）')


def chapter_error(media: str, chapter: Optional[str]) -> Optional[str]:
    """--chapter 用錯時回傳錯誤訊息（交由 CLI 以 exit 1 呈現，而非 traceback）"""
    if chapter is None:
        return None
    if media not in {m.value for m in CHAPTERED_MEDIA}:
        return "--chapter 只適用於 --media textbook 或 monograph"
    try:
        parse_chapter_range(chapter)
    except ValueError as e:
        return str(e)
    return None


def parse_meta(parser: argparse.ArgumentParser, items: List[str]) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition('=')
        if not sep or not key.strip():
            parser.error(f"--meta 格式應為 KEY=VALUE：{item!r}")
        meta[key.strip()] = value.strip()
    return meta


def default_slide_count(media: str, explicit: Optional[int]) -> int:
    """未指定 --slides 時：論文 15 張，其他媒體用 profile 的 default_slide_count"""
    if explicit is not None:
        return explicit
    if media == MediaType.paper.value:
        return 15
    return int(get_media_profile(media).get('default_slide_count', 15))


def print_media_types(catalog: Dict[str, str]) -> None:
    print("\n🎙️  可用的媒體類型（--media）：")
    for key, desc in catalog.items():
        print(f"   • {key:15s} - {desc}")
