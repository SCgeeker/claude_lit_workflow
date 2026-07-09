# -*- coding: utf-8 -*-
"""核心 API 的 Request / Result models（pydantic v2）

驗證規則（enum、範圍、來源互斥）集中於此；
CLI 與 MCP server 共用同一組介面定義。
"""

from enum import Enum
from pathlib import Path
from typing import List, Optional

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


class OutputFormat(str, Enum):
    pptx = "pptx"
    markdown = "markdown"
    both = "both"


class SlideRequest(BaseModel):
    """投影片生成請求。內容來源：topic / pdf / url / from_kb / content 至少一項；
    pdf、url、from_kb 互斥。"""

    topic: Optional[str] = None
    pdf: Optional[Path] = None
    url: Optional[str] = None
    from_kb: Optional[int] = None
    content: Optional[str] = None  # 直接提供的原始內容（呼叫端已抽取）

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
        exclusive = [s for s in (self.pdf, self.url, self.from_kb) if s is not None]
        if len(exclusive) > 1:
            raise ValueError("pdf、url、from_kb 只能擇一使用")
        if not any((self.topic, self.pdf, self.url, self.from_kb, self.content)):
            raise ValueError("請提供內容來源：topic、pdf、url、from_kb 或 content")
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
    """Zettel 卡片生成請求。內容來源：pdf / url / from_kb 恰一項。"""

    pdf: Optional[Path] = None
    url: Optional[str] = None
    from_kb: Optional[int] = None

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

    provider: str = "auto"
    model: Optional[str] = None
    selection_strategy: str = "balanced"
    output_dir: Optional[Path] = None

    @model_validator(mode="after")
    def _check_sources_and_kb(self):
        sources = [s for s in (self.pdf, self.url, self.from_kb) if s is not None]
        if len(sources) != 1:
            raise ValueError("內容來源：pdf、url、from_kb 必須恰好提供一項")
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
    """風格 / 詳細程度 / 語言目錄（鍵 → 繁中說明），來源為 academic_styles.yaml"""

    slide_styles: dict
    detail_levels: dict
    languages: dict
