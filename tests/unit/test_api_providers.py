# -*- coding: utf-8 -*-
"""api.providers 測試（spec: provider-setup）"""

import pytest

import claude_lit.api.providers as providers_mod
from claude_lit.api.providers import check_providers, list_options


@pytest.fixture
def all_unavailable(monkeypatch):
    """把所有供應商 check 函式 mock 為不可用"""
    fake = [
        ("google", "Google Gemini", lambda: (False, "未設定 GOOGLE_API_KEY")),
        ("openai", "OpenAI", lambda: (False, "未設定 OPENAI_API_KEY")),
        ("anthropic", "Anthropic Claude", lambda: (False, "未設定 ANTHROPIC_API_KEY")),
        ("ollama", "Ollama（本地）", lambda: (False, "無法連線")),
    ]
    monkeypatch.setattr(providers_mod, "PROVIDERS", fake)
    return fake


class TestCheckProviders:
    def test_only_google_available(self, monkeypatch):
        fake = [
            ("google", "Google Gemini", lambda: (True, "gemini-2.0-flash 可用")),
            ("openai", "OpenAI", lambda: (False, "未設定 OPENAI_API_KEY")),
            ("anthropic", "Anthropic Claude", lambda: (False, "未設定 ANTHROPIC_API_KEY")),
            ("ollama", "Ollama（本地）", lambda: (False, "無法連線")),
        ]
        monkeypatch.setattr(providers_mod, "PROVIDERS", fake)
        report = check_providers()

        by_name = {p.name: p for p in report.providers}
        assert by_name["google"].available is True
        assert "gemini" in by_name["google"].message
        assert all(not by_name[n].available for n in ("openai", "anthropic", "ollama"))
        assert report.recommended == "google"

    def test_none_available(self, all_unavailable):
        report = check_providers()
        assert report.recommended is None
        assert all(not p.available for p in report.providers)
        assert all(p.message for p in report.providers)

    def test_priority_prefers_google_over_ollama(self, monkeypatch):
        fake = [
            ("google", "Google Gemini", lambda: (True, "ok")),
            ("openai", "OpenAI", lambda: (False, "x")),
            ("anthropic", "Anthropic Claude", lambda: (False, "x")),
            ("ollama", "Ollama（本地）", lambda: (True, "ok")),
        ]
        monkeypatch.setattr(providers_mod, "PROVIDERS", fake)
        assert check_providers().recommended == "google"

    def test_placeholder_key_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "your-google-api-key")
        ok, msg = providers_mod._check_google()
        assert ok is False
        assert "未設定" in msg


class TestListOptions:
    def test_catalog_completeness(self):
        catalog = list_options()
        assert len(catalog.slide_styles) == 7  # 不含 zettelkasten
        assert len(catalog.detail_levels) == 5
        assert len(catalog.languages) == 3
        assert all(v for v in catalog.slide_styles.values())
        assert all(v for v in catalog.detail_levels.values())

    def test_style_keys_match_enum(self):
        from claude_lit.api.models import SlideStyle

        catalog = list_options()
        assert set(catalog.slide_styles.keys()) == {s.value for s in SlideStyle}


class TestRenderSlidesPrompt:
    def test_prompt_contains_content_and_style(self):
        from claude_lit.api.models import SlideRequest
        from claude_lit.api.prompts import render_slides_prompt

        req = SlideRequest(topic="測試主題", content="這是論文內容片段")
        prompt = render_slides_prompt(req)
        assert "測試主題" in prompt
        assert "這是論文內容片段" in prompt
        assert "現代學術" in prompt  # modern_academic 的風格名稱
