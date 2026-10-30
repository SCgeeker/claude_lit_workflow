# -*- coding: utf-8 -*-
"""api.guide 測試（spec: usage-guide）"""

import pytest

import claude_lit.api.guide as guide_mod
from claude_lit.api.errors import ProviderUnavailableError
from claude_lit.api.guide import GuideResult, build_usage_guide, suggest_command
from claude_lit.generators import SlideMaker


class TestBuildUsageGuide:
    def test_contains_core_tools_and_options(self):
        text = build_usage_guide()
        assert "uv run slides" in text
        assert "uv run zettel" in text
        assert "modern_academic" in text
        assert "standard" in text
        # 至少一則範例（--pdf 用法）
        assert "--pdf" in text

    def test_styles_consistent_with_list_options(self):
        from claude_lit.api.providers import list_options

        text = build_usage_guide()
        for style_key in list_options().slide_styles:
            assert style_key in text


class TestSuggestCommand:
    def _mock_call_llm(self, monkeypatch, capture):
        def fake(self, prompt, **kw):
            capture["prompt"] = prompt
            capture["kwargs"] = kw
            return ("建議：uv run slides --pdf paper.pdf --style teaching", "anthropic")
        monkeypatch.setattr(SlideMaker, "call_llm", fake)

    def test_prompt_includes_guide_and_request(self, monkeypatch):
        capture = {}
        self._mock_call_llm(monkeypatch, capture)
        result = suggest_command("把 paper.pdf 做成教學風格投影片", provider="anthropic")

        assert isinstance(result, GuideResult)
        assert result.provider_used == "anthropic"
        assert "uv run slides --pdf" in result.suggestion
        # 送出的提示含使用說明與需求
        assert "uv run zettel" in capture["prompt"]  # 說明的一部分
        assert "把 paper.pdf 做成教學風格投影片" in capture["prompt"]

    def test_provider_unavailable_raises(self, monkeypatch):
        def raise_runtime(self, prompt, **kw):
            raise RuntimeError("所有LLM提供者都不可用")
        monkeypatch.setattr(SlideMaker, "call_llm", raise_runtime)

        with pytest.raises(ProviderUnavailableError) as exc_info:
            suggest_command("需求", provider="google")
        assert "setup" in (exc_info.value.hint or "")

    def test_missing_key_valueerror_also_raises(self, monkeypatch):
        def raise_value(self, prompt, **kw):
            raise ValueError("NVIDIA_API_KEY not set")
        monkeypatch.setattr(SlideMaker, "call_llm", raise_value)

        with pytest.raises(ProviderUnavailableError):
            suggest_command("需求", provider="nvidia")

    def test_nvidia_defaults_to_light_model(self, monkeypatch):
        capture = {}
        self._mock_call_llm(monkeypatch, capture)
        suggest_command("需求", provider="nvidia")
        # guide 問答不用 253B，預設輕量 8b
        assert capture["kwargs"].get("model") == "meta/llama-3.1-8b-instruct"

    def test_explicit_model_preserved(self, monkeypatch):
        capture = {}
        self._mock_call_llm(monkeypatch, capture)
        suggest_command("需求", provider="nvidia", model="qwen/qwen3-next-80b-a3b-thinking")
        assert capture["kwargs"].get("model") == "qwen/qwen3-next-80b-a3b-thinking"


class TestPlanRequest:
    """自然語言需求 → 經驗證的參數提案（spec: web-service 自然語言模式）"""

    def _llm(self, monkeypatch, output, capture=None):
        def fake(self, prompt, **kw):
            if capture is not None:
                capture["prompt"] = prompt
            return (output, "google")
        monkeypatch.setattr(SlideMaker, "call_llm", fake)

    def test_valid_params_pass(self, monkeypatch):
        capture = {}
        self._llm(monkeypatch, '好的：\n```json\n{"kinds": ["slides", "zettel"], "media_type": "podcast",'
                               ' "style": "teaching", "slide_count": 12, "source_meta": {"show": "科學新聞"}}\n```',
                  capture)
        result = guide_mod.plan_request("把這集 podcast 做成教學投影片和卡片")
        assert result.params == {
            "kinds": ["slides", "zettel"], "media_type": "podcast", "style": "teaching",
            "slide_count": 12, "source_meta": {"show": "科學新聞"},
        }
        assert result.warnings == []
        assert "JSON" in capture["prompt"] and "podcast" in capture["prompt"]

    def test_invalid_values_dropped_with_warnings(self, monkeypatch):
        self._llm(monkeypatch, '{"style": "fancy", "slide_count": 500, "chapter": "3",'
                               ' "media_type": "lecture", "pdf": "/etc/passwd"}')
        result = guide_mod.plan_request("x")
        assert result.params == {"media_type": "lecture"}  # 未知欄位 pdf 直接忽略
        joined = " ".join(result.warnings)
        assert "fancy" in joined and "500" in joined and "chapter" in joined

    def test_unparseable_output(self, monkeypatch):
        self._llm(monkeypatch, "抱歉，我不確定")
        result = guide_mod.plan_request("x")
        assert result.params == {} and result.warnings

    def test_provider_error(self, monkeypatch):
        def fail(self, prompt, **kw):
            raise RuntimeError("no key")
        monkeypatch.setattr(SlideMaker, "call_llm", fail)
        with pytest.raises(ProviderUnavailableError):
            guide_mod.plan_request("x", provider="google")
