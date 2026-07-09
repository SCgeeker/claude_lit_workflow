# -*- coding: utf-8 -*-
"""NVIDIA NIM provider 測試（spec: provider-setup — NVIDIA 生成與任務分流）"""

import pytest

import claude_lit.generators.slide_maker as sm_mod
from claude_lit.generators import SlideMaker


@pytest.fixture
def nvidia_maker(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-realLookingKey")
    maker = SlideMaker(llm_provider="nvidia")
    maker.model_monitor = None  # 避免測試寫入使用量檔
    return maker


def _fake_resp(message):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": message}]}
    return FakeResp()


class TestCallNvidia:
    def test_endpoint_and_bearer_auth(self, nvidia_maker, monkeypatch):
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["body"] = json or {}
            return _fake_resp({"content": "生成內容"})

        monkeypatch.setattr(sm_mod.requests, "post", fake_post)

        result = nvidia_maker.call_nvidia("prompt", model="meta/llama-3.1-8b-instruct")
        assert result == "生成內容"
        assert "integrate.api.nvidia.com" in captured["url"]
        assert captured["headers"]["Authorization"] == "Bearer nvapi-realLookingKey"
        assert captured["body"]["model"] == "meta/llama-3.1-8b-instruct"

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        maker = SlideMaker(llm_provider="anthropic")  # 任意可初始化的 provider
        with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
            maker.call_nvidia("prompt", model="meta/llama-3.1-8b-instruct")

    def test_content_preferred_over_reasoning(self, nvidia_maker, monkeypatch):
        """content 有值時優先用 content（不混入 reasoning 思考過程）"""
        monkeypatch.setattr(
            sm_mod.requests, "post",
            lambda *a, **k: _fake_resp({"content": "最終答案", "reasoning_content": "思考過程"}),
        )
        assert nvidia_maker.call_nvidia("p", model="m") == "最終答案"

    def test_reasoning_fallback_when_content_empty(self, nvidia_maker, monkeypatch):
        """reasoning 模型 content 為空時 fallback reasoning_content（避免 NoneType 崩潰）"""
        monkeypatch.setattr(
            sm_mod.requests, "post",
            lambda *a, **k: _fake_resp({"content": None, "reasoning_content": "推理型答案"}),
        )
        assert nvidia_maker.call_nvidia("p", model="m") == "推理型答案"

    def test_reasoning_fallback_when_content_blank_string(self, nvidia_maker, monkeypatch):
        monkeypatch.setattr(
            sm_mod.requests, "post",
            lambda *a, **k: _fake_resp({"content": "  ", "reasoning_content": "推理型答案"}),
        )
        assert nvidia_maker.call_nvidia("p", model="m") == "推理型答案"

    def test_both_empty_raises(self, nvidia_maker, monkeypatch):
        monkeypatch.setattr(
            sm_mod.requests, "post",
            lambda *a, **k: _fake_resp({"content": None, "reasoning_content": None}),
        )
        with pytest.raises(RuntimeError):
            nvidia_maker.call_nvidia("p", model="m")


class TestNvidiaDefaultModel:
    # 預設用實測穩定可用的 8b instruct（大模型 nemotron-253b/qwen-thinking 已 404/410 失效）；
    # 進階使用者可經 NVIDIA_SLIDES_MODEL / NVIDIA_ZETTEL_MODEL 覆寫成大模型
    _DEFAULT = "meta/llama-3.1-8b-instruct"

    def test_slides_default(self):
        assert sm_mod._nvidia_default_model("slides") == self._DEFAULT

    def test_zettel_default(self):
        assert sm_mod._nvidia_default_model("zettelkasten") == self._DEFAULT

    def test_none_falls_back_to_slides(self):
        assert sm_mod._nvidia_default_model(None) == self._DEFAULT

    def test_no_dead_models_referenced(self):
        """預設不得再指向已失效的模型"""
        for tt in ("slides", "zettelkasten", None):
            m = sm_mod._nvidia_default_model(tt)
            assert "253b" not in m
            assert "thinking" not in m

    def test_slides_env_override(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_SLIDES_MODEL", "nvidia/nemotron-3-super-120b-a12b")
        assert sm_mod._nvidia_default_model("slides") == "nvidia/nemotron-3-super-120b-a12b"

    def test_zettel_env_override(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_ZETTEL_MODEL", "custom/model-x")
        assert sm_mod._nvidia_default_model("zettelkasten") == "custom/model-x"


class TestTaskRouting:
    def _run(self, maker, monkeypatch, task_type, model=None):
        captured = {}
        monkeypatch.setattr(
            maker, "call_nvidia",
            lambda prompt, m, timeout=300, max_tokens=4096: captured.update(model=m) or "out",
        )
        monkeypatch.setattr(maker, "_detect_available_providers", lambda: ["nvidia"])
        result, provider = maker.call_llm("prompt", task_type=task_type, model=model)
        assert provider == "nvidia"
        return captured["model"]

    def test_slides_routes_to_default(self, nvidia_maker, monkeypatch):
        assert self._run(nvidia_maker, monkeypatch, "slides") == "meta/llama-3.1-8b-instruct"

    def test_zettel_routes_to_default(self, nvidia_maker, monkeypatch):
        assert self._run(nvidia_maker, monkeypatch, "zettelkasten") == "meta/llama-3.1-8b-instruct"

    def test_explicit_model_overrides_routing(self, nvidia_maker, monkeypatch):
        assert self._run(nvidia_maker, monkeypatch, "slides", model="nvidia/nemotron-3-super-120b-a12b") == \
            "nvidia/nemotron-3-super-120b-a12b"


class TestDetectNvidia:
    def test_nvidia_detected_when_key_set(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-key")
        maker = SlideMaker(llm_provider="nvidia")
        assert "nvidia" in maker._detect_available_providers()

    def test_nvidia_absent_when_key_unset(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        maker = SlideMaker(llm_provider="anthropic")
        assert "nvidia" not in maker._detect_available_providers()
