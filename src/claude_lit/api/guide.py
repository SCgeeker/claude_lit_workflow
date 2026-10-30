# -*- coding: utf-8 -*-
"""使用嚮導 API

build_usage_guide：導出完整工具使用說明（風格清單來自 list_options，單一真相來源）。
suggest_command：把說明 + 需求送給指定的可用 LLM，回傳建議的 CLI 指令（單次問答，不執行）。
plan_request：suggest_command 的結構化版本——回傳經驗證的生成參數提案（網頁服務的自然語言模式）。
"""

import json
import re
from typing import Any, Dict, List, Optional

from jinja2 import Template
from pydantic import BaseModel

from claude_lit.generators import SlideMaker
from claude_lit.resource_loader import resolve_resource

from .errors import ProviderUnavailableError
from .models import DetailLevel, Language, MediaType, SlideStyle, parse_chapter_range
from .providers import list_options

# guide 為短問答，NVIDIA 用輕量模型（不用 253B）
_NVIDIA_GUIDE_MODEL = "meta/llama-3.1-8b-instruct"


class GuideResult(BaseModel):
    suggestion: str
    provider_used: str


class PlanResult(BaseModel):
    """自然語言需求 → 參數提案；params 只含通過驗證的欄位，其餘記於 warnings"""

    params: Dict[str, Any]
    warnings: List[str] = []
    provider_used: str


def build_usage_guide() -> str:
    """組出完整工具使用說明；風格/詳細度/語言/媒體類型清單注入自 list_options()。"""
    catalog = list_options()
    template_path = resolve_resource("templates/prompts/usage_guide.jinja2")
    template = Template(template_path.read_text(encoding="utf-8"))

    def _block(mapping: dict) -> str:
        return "\n".join(f"- `{k}` — {v}" for k, v in mapping.items())

    return template.render(
        slide_styles_keys=", ".join(catalog.slide_styles),
        detail_keys=", ".join(catalog.detail_levels),
        language_keys=", ".join(catalog.languages),
        slide_styles_block=_block(catalog.slide_styles),
        detail_block=_block(catalog.detail_levels),
        language_block=_block(catalog.languages),
        media_keys=", ".join(catalog.media_types),
        media_block=_block(catalog.media_types),
    )


def suggest_command(
    request_text: str,
    *,
    provider: str = "auto",
    model: Optional[str] = None,
) -> GuideResult:
    """用指定供應商的 LLM，依需求回覆建議的 CLI 指令（單次問答，不自動執行）。

    Raises:
        ProviderUnavailableError: 指定供應商無法呼叫（金鑰未設定或連線失敗）
    """
    guide = build_usage_guide()
    prompt = (
        f"{guide}\n\n"
        f"---\n\n"
        f"使用者需求：{request_text}\n\n"
        f"請根據上述工具說明，回覆使用者應執行的 CLI 指令（含完整參數）與簡短理由。"
        f"只建議指令，不要自己執行。"
    )

    # guide 短問答：NVIDIA 未指定 model 時用輕量模型
    effective_model = model
    if provider == "nvidia" and not effective_model:
        effective_model = _NVIDIA_GUIDE_MODEL

    maker = SlideMaker(llm_provider=provider)
    call_provider = None if provider == "auto" else provider
    try:
        suggestion, used = maker.call_llm(
            prompt, model=effective_model, provider=call_provider, task_type="guide"
        )
    except (RuntimeError, ValueError) as e:
        raise ProviderUnavailableError(
            f"無法使用供應商 {provider}：{e}",
            hint="執行 uv run setup 確認可用的 LLM 供應商",
        ) from e

    return GuideResult(suggestion=suggestion, provider_used=used)


# 參數提案可含的欄位與驗證（值須在 enum 內；不在清單的欄位一律忽略）
_ENUM_FIELDS = {
    "media_type": MediaType,
    "style": SlideStyle,
    "detail": DetailLevel,
    "language": Language,
}
_PLAN_FIELDS = (
    "kinds", "media_type", "style", "detail", "language", "slide_count", "chapter",
    "source_meta", "custom_requirements",
)
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _call_guide_llm(prompt: str, provider: str, model: Optional[str]):
    effective_model = model
    if provider == "nvidia" and not effective_model:
        effective_model = _NVIDIA_GUIDE_MODEL
    maker = SlideMaker(llm_provider=provider)
    call_provider = None if provider == "auto" else provider
    try:
        return maker.call_llm(
            prompt, model=effective_model, provider=call_provider, task_type="guide"
        )
    except (RuntimeError, ValueError) as e:
        raise ProviderUnavailableError(
            f"無法使用供應商 {provider}：{e}",
            hint="執行 uv run setup 確認可用的 LLM 供應商",
        ) from e


def _validate_plan(raw: Dict[str, Any]) -> tuple:
    params: Dict[str, Any] = {}
    warnings: List[str] = []
    for key, value in raw.items():
        if key not in _PLAN_FIELDS:
            continue
        if value in (None, "", [], {}):
            continue
        if key in _ENUM_FIELDS:
            allowed = [m.value for m in _ENUM_FIELDS[key]]
            if value not in allowed:
                warnings.append(f"{key}={value!r} 不是可用選項（{', '.join(allowed)}），已忽略")
                continue
        elif key == "kinds":
            kinds = [k for k in (value if isinstance(value, list) else [value]) if k in ("slides", "zettel")]
            if not kinds:
                warnings.append(f"kinds={value!r} 無效（slides / zettel），已忽略")
                continue
            value = kinds
        elif key == "slide_count":
            try:
                value = int(value)
            except (TypeError, ValueError):
                warnings.append(f"slide_count={value!r} 不是整數，已忽略")
                continue
            if not 3 <= value <= 60:
                warnings.append(f"slide_count={value} 超出 3–60，已忽略")
                continue
        elif key == "chapter":
            try:
                parse_chapter_range(str(value))
            except ValueError as e:
                warnings.append(f"{e}，已忽略")
                continue
            value = str(value)
        elif key == "source_meta":
            if not isinstance(value, dict):
                warnings.append("source_meta 須為物件，已忽略")
                continue
            value = {str(k): str(v) for k, v in value.items() if v not in (None, "")}
        elif key == "custom_requirements":
            value = str(value)
        params[key] = value
    if "chapter" in params and params.get("media_type") not in ("textbook", "monograph"):
        warnings.append("chapter 只適用於 textbook / monograph，已忽略")
        params.pop("chapter")
    return params, warnings


def plan_request(
    request_text: str,
    *,
    provider: str = "auto",
    model: Optional[str] = None,
) -> PlanResult:
    """依自然語言需求回傳生成參數提案（JSON），經驗證後供使用者確認；不執行生成。

    Raises:
        ProviderUnavailableError: 指定供應商無法呼叫
    """
    guide = build_usage_guide()
    prompt = (
        f"{guide}\n\n---\n\n"
        f"使用者需求：{request_text}\n\n"
        "請不要回覆 CLI 指令，改為只回覆一個 JSON 物件（不要其他文字），欄位如下，用不到的欄位省略：\n"
        '{"kinds": ["slides" 和/或 "zettel"], "media_type": "...", "style": "...", '
        '"detail": "...", "language": "...", "slide_count": 數字, "chapter": "3 或 3-5", '
        '"source_meta": {"speaker": "...", "year": "..."}, "custom_requirements": "使用者的額外要求"}\n'
        "各欄位的可用值見上方說明；檔案由使用者另行上傳，不需填寫路徑。"
    )
    output, used = _call_guide_llm(prompt, provider, model)

    match = _JSON_BLOCK.search(output or "")
    if not match:
        return PlanResult(params={}, warnings=["LLM 未回覆可解析的 JSON，請改用表單設定"], provider_used=used)
    try:
        raw = json.loads(match.group(0))
    except json.JSONDecodeError:
        return PlanResult(params={}, warnings=["LLM 回覆的 JSON 格式錯誤，請改用表單設定"], provider_used=used)
    if not isinstance(raw, dict):
        return PlanResult(params={}, warnings=["LLM 回覆的 JSON 不是物件，請改用表單設定"], provider_used=used)

    params, warnings = _validate_plan(raw)
    return PlanResult(params=params, warnings=warnings, provider_used=used)
