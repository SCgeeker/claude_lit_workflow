# -*- coding: utf-8 -*-
"""使用嚮導 API

build_usage_guide：導出完整工具使用說明（風格清單來自 list_options，單一真相來源）。
suggest_command：把說明 + 需求送給指定的可用 LLM，回傳建議的 CLI 指令（單次問答，不執行）。
"""

from typing import Optional

from jinja2 import Template
from pydantic import BaseModel

from claude_lit.generators import SlideMaker
from claude_lit.resource_loader import resolve_resource

from .errors import ProviderUnavailableError
from .providers import list_options

# guide 為短問答，NVIDIA 用輕量模型（不用 253B）
_NVIDIA_GUIDE_MODEL = "meta/llama-3.1-8b-instruct"


class GuideResult(BaseModel):
    suggestion: str
    provider_used: str


def build_usage_guide() -> str:
    """組出完整工具使用說明；風格/詳細度/語言清單注入自 list_options()。"""
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
