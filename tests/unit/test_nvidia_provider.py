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


class TestCallNvidia:
    def test_endpoint_and_bearer_auth(self, nvidia_maker, monkeypatch):
        captured = {}

        class FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "生成內容"}}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["body"] = json or {}
            return FakeResp()

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


class TestNvidiaDefaultModel:
    def test_slides_default(self):
        assert sm_mod._nvidia_default_model("slides") == "nvidia/llama-3.1-nemotron-ultra-253b-v1"

    def test_zettel_default(self):
        assert sm_mod._nvidia_default_model("zettelkasten") == "qwen/qwen3-next-80b-a3b-thinking"

    def test_none_falls_back_to_slides(self):
        assert sm_mod._nvidia_default_model(None) == "nvidia/llama-3.1-nemotron-ultra-253b-v1"

    def test_env_override(self, monkeypatch):
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

    def test_slides_routes_to_nemotron(self, nvidia_maker, monkeypatch):
        assert self._run(nvidia_maker, monkeypatch, "slides") == \
            "nvidia/llama-3.1-nemotron-ultra-253b-v1"

    def test_zettel_routes_to_qwen_thinking(self, nvidia_maker, monkeypatch):
        assert self._run(nvidia_maker, monkeypatch, "zettelkasten") == \
            "qwen/qwen3-next-80b-a3b-thinking"

    def test_explicit_model_overrides_routing(self, nvidia_maker, monkeypatch):
        assert self._run(nvidia_maker, monkeypatch, "slides", model="meta/llama-3.1-8b-instruct") == \
            "meta/llama-3.1-8b-instruct"


class TestDetectNvidia:
    def test_nvidia_detected_when_key_set(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-key")
        maker = SlideMaker(llm_provider="nvidia")
        assert "nvidia" in maker._detect_available_providers()

    def test_nvidia_absent_when_key_unset(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        maker = SlideMaker(llm_provider="anthropic")
        assert "nvidia" not in maker._detect_available_providers()
