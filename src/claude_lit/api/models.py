# -*- coding: utf-8 -*-
"""核心 API 的 Request / Result models（pydantic v2）

驗證規則（enum、範圍、來源互斥）集中於此；
CLI 與 MCP server 共用同一組介面定義。
"""

import re
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class SlideStyle(str, Enum):
    classic_academic = "classic_academic"
    modern_academic = "modern_academic"
    clinical = "clinical"
    research_methods = "research_methods"
    literature_review = "literature_review"
    case_analysis = "case_analysis"
    teaching = "teaching"


class DetailLevel(str, Enum):
    minimal = "minimal"
    brief = "brief"
    standard = "standard"
    detailed = "detailed"
    comprehensive = "comprehensive"


class Language(str, Enum):
    chinese = "chinese"
    english = "english"
    bilingual = "bilingual"


class MediaType(str, Enum):
    """來源媒體類型（與 style 正交）；paper 走既有論文模板，其餘走 media_profiles.yaml"""

    paper = "paper"
    lecture = "lecture"
    podcast = "podcast"
    blog = "blog"
    textbook = "textbook"
    monograph = "monograph"


# 需以章為單位處理的長篇媒體（--chapter 只對這些有效）
CHAPTERED_MEDIA = (MediaType.textbook, MediaType.monograph)
_CHAPTER_PAT = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$")


def parse_chapter_range(chapter: str) -> tuple:
    """'3' → (3, 3)；'3-5' → (3, 5)。格式錯誤或起訖顛倒拋 ValueError。"""
    m = _CHAPTER_PAT.match(chapter or "")
    if not m:
        raise ValueError(f"chapter 格式應為單章（如 3）或範圍（如 3-5）：{chapter!r}")
    start = int(m.group(1))
    end = int(m.group(2) or start)
    if start < 1 or end < start:
        raise ValueError(f"chapter 範圍無效：{chapter!r}")
    return start, end


def _check_media_fields(media_type: "MediaType", chapter: Optional[str]) -> None:
    if chapter is None:
        return
    if media_type not in CHAPTERED_MEDIA:
        raise ValueError("chapter 只適用於 media_type=textbook 或 monograph")
    parse_chapter_range(chapter)


class OutputFormat(str, Enum):
    pptx = "pptx"
    markdown = "markdown"
    both = "both"


class SlideRequest(BaseModel):
    """投影片生成請求。內容來源：topic / pdf / url / from_kb / text / content 至少一項；
    pdf、url、from_kb、text 互斥。"""

    topic: Optional[str] = None
    pdf: Optional[Path] = None
    url: Optional[str] = None
    from_kb: Optional[int] = None
    text: Optional[Path] = None  # 文字來源：.txt / .md / .srt / .vtt / .epub
    content: Optional[str] = None  # 直接提供的原始內容（呼叫端已抽取）

    media_type: MediaType = MediaType.paper
    source_meta: Dict[str, str] = {}  # 講者、節目、集數等（填入標題頁與引用格式）
    chapter: Optional[str] = None  # textbook / monograph：單章 "3" 或範圍 "3-5"
    keep_fillers: bool = False  # 逐字稿保留填充詞（預設移除）

    style: SlideStyle = SlideStyle.modern_academic
    detail: DetailLevel = DetailLevel.standard
    language: Language = Language.chinese
    slide_count: int = Field(15, ge=3, le=60)
    output_format: OutputFormat = OutputFormat.markdown
    output_path: Optional[Path] = None

    provider: str = "auto"
    model: Optional[str] = None
    selection_strategy: str = "balanced"
    custom_requirements: Optional[str] = None  # 直接內容；檔案載入是 CLI 層的事

    @model_validator(mode="after")
    def _check_sources(self):
        exclusive = [s for s in (self.pdf, self.url, self.from_kb, self.text) if s is not None]
        if len(exclusive) > 1:
            raise ValueError("pdf、url、from_kb、text 只能擇一使用")
        if not any((self.topic, self.pdf, self.url, self.from_kb, self.text, self.content)):
            raise ValueError("請提供內容來源：topic、pdf、url、from_kb、text 或 content")
        _check_media_fields(self.media_type, self.chapter)
        return self


class SlideResult(BaseModel):
    output_files: List[str]
    topic: str
    slide_count: int
    style: str
    detail: str
    language: str
    output_format: str
    provider_used: str
    model_used: Optional[str] = None
    preview: str = ""
    warnings: List[str] = []


class ZettelRequest(BaseModel):
    """Zettel 卡片生成請求。內容來源：pdf / url / from_kb / text / content 恰一項。"""

    pdf: Optional[Path] = None
    url: Optional[str] = None
    from_kb: Optional[int] = None
    text: Optional[Path] = None  # 文字來源：.txt / .md / .srt / .vtt / .epub
    content: Optional[str] = None  # 直接提供的原文（遠端 MCP client 無法傳路徑時）；需搭配 cite_key

    media_type: MediaType = MediaType.paper
    source_meta: Dict[str, str] = {}
    chapter: Optional[str] = None  # textbook / monograph；cite_key 自動加 -chNN 後綴
    keep_fillers: bool = False

    detail: DetailLevel = DetailLevel.standard
    language: Language = Language.chinese
    domain: str = "Research"
    cite_key: Optional[str] = None  # 明確指定時優先使用
    slides_content: Optional[str] = None
    custom_requirements: Optional[str] = None

    add_to_kb: bool = True
    force: bool = False
    cross_link: bool = False
    embed: bool = True
    ground: bool = True  # 生成端 grounding gate：核心無法逐字回溯原文則抹除；CJK 定位不到則隔離

    provider: str = "auto"
    model: Optional[str] = None
    selection_strategy: str = "balanced"
    output_dir: Optional[Path] = None  # 卡片目錄（完整路徑，最優先）
    output_root: Optional[Path] = None  # 取代預設的 output/ 根目錄（網頁服務的 job 目錄）

    @model_validator(mode="after")
    def _check_sources_and_kb(self):
        sources = [
            s for s in (self.pdf, self.url, self.from_kb, self.text, self.content) if s is not None
        ]
        if len(sources) != 1:
            raise ValueError("內容來源：pdf、url、from_kb、text、content 必須恰好提供一項")
        _check_media_fields(self.media_type, self.chapter)
        if self.cross_link and not self.add_to_kb:
            raise ValueError("cross_link 需要知識庫支援，不能與 add_to_kb=False 併用")
        if not self.add_to_kb:
            # 嵌入依附於入庫流程；不入庫時自動關閉
            self.embed = False
        return self


class ZettelResult(BaseModel):
    output_dir: str
    index_file: str
    card_files: List[str]
    card_count: int
    cite_key: str
    provider_used: str
    kb_added: int = 0
    kb_skipped: int = 0
    embedded: int = 0
    grounded: int = 0   # 通過 grounding 而寫入的正常卡片數
    erased: int = 0     # grounding 定位不到而抹除的卡片數
    flagged: int = 0    # CJK 不可驗證、隔離待審的卡片數
    warnings: List[str] = []


class ProviderStatus(BaseModel):
    name: str  # google / openai / anthropic / ollama
    display_name: str
    available: bool
    message: str


class ProviderReport(BaseModel):
    providers: List[ProviderStatus]
    recommended: Optional[str] = None
    env_file_exists: bool = True


class OptionCatalog(BaseModel):
    """風格 / 詳細程度 / 語言目錄（鍵 → 繁中說明），來源為 academic_styles.yaml；
    媒體類型目錄來源為 media_profiles.yaml"""

    slide_styles: dict
    detail_levels: dict
    languages: dict
    media_types: dict = {}  # 媒體類型目錄，來源為 media_profiles.yaml
