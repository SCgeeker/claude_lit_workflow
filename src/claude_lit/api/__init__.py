# -*- coding: utf-8 -*-
"""claude_lit_workflow 核心 API

CLI 與 MCP server 共用的可程式化介面。
"""

from .errors import (
    CiteKeyMissingError,
    ConfigError,
    ExtractionError,
    LitWorkflowError,
    LLMGenerationError,
    ProviderUnavailableError,
    SourceNotFoundError,
)
from .models import (
    DetailLevel,
    Language,
    OptionCatalog,
    OutputFormat,
    ProviderReport,
    ProviderStatus,
    SlideRequest,
    SlideResult,
    SlideStyle,
    ZettelRequest,
    ZettelResult,
)
from .guide import GuideResult, build_usage_guide, suggest_command
from .progress import ProgressCallback, ProgressEvent
from .prompts import render_slides_prompt, render_zettel_prompt
from .providers import check_providers, list_options
from .slides import generate_slides
from .zettel import generate_zettel

__all__ = [
    "generate_slides",
    "generate_zettel",
    "check_providers",
    "list_options",
    "build_usage_guide",
    "suggest_command",
    "GuideResult",
    "render_slides_prompt",
    "render_zettel_prompt",
    "CiteKeyMissingError",
    "ConfigError",
    "ExtractionError",
    "LitWorkflowError",
    "LLMGenerationError",
    "ProviderUnavailableError",
    "SourceNotFoundError",
    "DetailLevel",
    "Language",
    "OptionCatalog",
    "OutputFormat",
    "ProviderReport",
    "ProviderStatus",
    "SlideRequest",
    "SlideResult",
    "SlideStyle",
    "ZettelRequest",
    "ZettelResult",
    "ProgressCallback",
    "ProgressEvent",
]
