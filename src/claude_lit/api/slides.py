# -*- coding: utf-8 -*-
"""投影片生成核心 API

編排：來源解析 → prompt 渲染 → LLM 呼叫 → 解析 → 輸出檔案。
呈現（print / emoji）一律不在此層；進度以 ProgressEvent 回報。
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from claude_lit.generators import SlideMaker

from .errors import LLMGenerationError, ProviderUnavailableError
from .models import SlideRequest, SlideResult
from .progress import ProgressCallback, ProgressEvent
from .sources import resolve_source

logger = logging.getLogger("claude_lit_workflow.api.slides")

# Windows / POSIX 檔名非法字元（含 URL 的 : /）與控制字元
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_filename(name: str, max_len: int = 80) -> str:
    """把 topic 轉為安全檔名：非法字元換底線、去頭尾點與空白、限長。

    URL 來源時 topic 可能是整串網址（含 : /），未清理會使路徑非法（WinError 123）。
    """
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("_", name).strip(". ")
    return cleaned[:max_len] or "slides"

# 依詳細程度動態估算 max_tokens（沿用原 SlideMaker.generate_slides 的參數）
_TOKENS_PER_SLIDE = {
    "minimal": 200,
    "brief": 350,
    "standard": 500,
    "detailed": 700,
    "comprehensive": 1000,
}
_MAX_TOKENS_CAP = 16000

# 投影片內容來源上限（Journal Club 格式限制）
_SLIDES_MAX_CHARS = 10000


def _compute_max_tokens(slide_count: int, detail: str) -> int:
    per_slide = _TOKENS_PER_SLIDE.get(detail, 500)
    return min(max(slide_count * per_slide + 1000, 4096), _MAX_TOKENS_CAP)


def generate_slides(
    request: SlideRequest,
    *,
    progress: Optional[ProgressCallback] = None,
    api_key: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> SlideResult:
    """生成投影片。

    Args:
        request: 生成請求
        progress: 進度 callback（可選）
        api_key: 覆寫 API 金鑰（CLI --api-key 用；不入 request model 以免經 MCP 曝露）
        ollama_url: 覆寫 Ollama URL

    Raises:
        SourceNotFoundError / ExtractionError / ProviderUnavailableError / LLMGenerationError
    """
    emit = progress or (lambda _e: None)

    maker_kwargs = {
        "llm_provider": request.provider,
        "selection_strategy": request.selection_strategy,
    }
    if api_key:
        maker_kwargs["api_key"] = api_key
    if ollama_url:
        maker_kwargs["ollama_url"] = ollama_url
    maker = SlideMaker(**maker_kwargs)

    # 1. 來源解析
    if request.pdf or request.url or request.from_kb:
        emit(ProgressEvent(stage="extract", message="正在抽取內容來源..."))
    source = resolve_source(
        topic=request.topic,
        pdf=request.pdf,
        url=request.url,
        from_kb=request.from_kb,
        content=request.content,
        max_chars=_SLIDES_MAX_CHARS,
    )
    topic = source.topic or "簡報"

    # 2. Prompt 渲染
    emit(ProgressEvent(stage="prompt", message="正在渲染提示詞..."))
    prompt = maker.generate_prompt(
        topic=topic,
        style=request.style.value,
        detail_level=request.detail.value,
        language=request.language.value,
        slide_count=request.slide_count,
        pdf_content=source.content,
        source_type=source.source_type,
        custom_requirements=request.custom_requirements,
    )

    # 3. LLM 呼叫
    max_tokens = _compute_max_tokens(request.slide_count, request.detail.value)
    emit(ProgressEvent(stage="llm", message="正在生成投影片內容..."))
    try:
        llm_output, used_provider = maker.call_llm(
            prompt, model=request.model, max_tokens=max_tokens, task_type="slides"
        )
    except RuntimeError as e:
        raise ProviderUnavailableError(
            f"LLM 呼叫失敗：{e}",
            hint="執行 uv run setup 檢查 LLM 供應商設定",
        ) from e

    # 4. 解析
    slides = maker.parse_slides(llm_output)
    if not slides:
        logger.info("LLM 原始輸出（前 800 字元）：%s", llm_output[:800])
        raise LLMGenerationError(
            "無法解析投影片內容（LLM 輸出不含可辨識的投影片結構）",
            hint="請更換模型或降低 detail 後重試",
        )

    # 5. 輸出檔案
    emit(ProgressEvent(stage="write", message="正在寫入輸出檔案..."))
    if request.output_path:
        base_name = str(Path(request.output_path).with_suffix(""))
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"output/{_sanitize_filename(topic)}_{request.style.value}_{timestamp}"

    output_files = []
    fmt = request.output_format.value
    if fmt in ("pptx", "both"):
        output_files.append(maker.create_pptx(slides, f"{base_name}.pptx", title=topic))
    if fmt in ("markdown", "both"):
        output_files.append(
            maker.create_markdown(slides, f"{base_name}.md", title=topic, style=request.style.value)
        )

    return SlideResult(
        output_files=[str(Path(f).resolve()) for f in output_files],
        topic=topic,
        slide_count=len(slides),
        style=request.style.value,
        detail=request.detail.value,
        language=request.language.value,
        output_format=fmt,
        provider_used=used_provider,
        model_used=request.model,
        preview=llm_output[:500],
        warnings=source.warnings,
    )
