# -*- coding: utf-8 -*-
"""CLI 薄殼回歸測試：參數轉換與 exit codes 與舊版一致（API 層以 mock 取代）"""

import sys

import pytest

import claude_lit.cli.slides as make_slides_mod
import claude_lit.cli.zettel as generate_zettel_mod
import claude_lit.cli.setup_check as setup_mod
import claude_lit.cli.guide as guide_mod
from claude_lit.api.guide import GuideResult
from claude_lit.api.models import (
    ProviderReport,
    ProviderStatus,
    SlideResult,
    ZettelResult,
)


def _fake_slide_result(**overrides):
    base = dict(
        output_files=["output/test.md"],
        topic="t",
        slide_count=3,
        style="modern_academic",
        detail="standard",
        language="chinese",
        output_format="markdown",
        provider_used="google",
        preview="預覽",
    )
    base.update(overrides)
    return SlideResult(**base)


def _fake_zettel_result(**overrides):
    base = dict(
        output_dir="output/zettel_x",
        index_file="output/zettel_x/zettel_index.md",
        card_files=[f"output/zettel_x/zettel_cards/X-{i:03d}.md" for i in range(1, 13)],
        card_count=12,
        cite_key="X-2024",
        provider_used="google",
    )
    base.update(overrides)
    return ZettelResult(**base)


class TestSlidesCli:
    def test_success_exit_0(self, monkeypatch, capsys):
        captured = {}

        def fake_generate(request, **kw):
            captured["request"] = request
            return _fake_slide_result()

        monkeypatch.setattr(make_slides_mod, "generate_slides", fake_generate)
        monkeypatch.setattr(sys, "argv", ["slides", "測試主題", "--style", "teaching", "--slides", "10"])
        assert make_slides_mod.main() == 0

        req = captured["request"]
        assert req.topic == "測試主題"
        assert req.style.value == "teaching"
        assert req.slide_count == 10
        assert "投影片生成完成" in capsys.readouterr().out

    def test_no_source_exit_1(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["slides"])
        assert make_slides_mod.main() == 1
        assert "❌" in capsys.readouterr().out

    def test_pdf_url_conflict_exit_1(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["slides", "--pdf", "a.pdf", "--url", "http://x"])
        assert make_slides_mod.main() == 1

    def test_list_options_exit_0(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["slides", "--list-options"])
        assert make_slides_mod.main() == 0
        out = capsys.readouterr().out
        assert "modern_academic" in out
        assert "comprehensive" in out

    def test_api_error_exit_1_with_hint(self, monkeypatch, capsys):
        from claude_lit.api.errors import SourceNotFoundError

        def fake_generate(request, **kw):
            raise SourceNotFoundError("找不到 PDF", hint="確認路徑")

        monkeypatch.setattr(make_slides_mod, "generate_slides", fake_generate)
        monkeypatch.setattr(sys, "argv", ["slides", "--pdf", "x.pdf"])
        assert make_slides_mod.main() == 1
        out = capsys.readouterr().out
        assert "找不到 PDF" in out
        assert "確認路徑" in out


class TestZettelCli:
    def test_success_exit_0(self, monkeypatch, capsys):
        captured = {}

        def fake_generate(request, **kw):
            captured["request"] = request
            return _fake_zettel_result()

        monkeypatch.setattr(generate_zettel_mod, "generate_zettel", fake_generate)
        monkeypatch.setattr(
            sys, "argv",
            ["zettel", "--pdf", "p.pdf", "--detail", "detailed", "--no-add-to-kb", "--no-custom"],
        )
        assert generate_zettel_mod.main() == 0

        req = captured["request"]
        assert str(req.pdf) == "p.pdf"
        assert req.detail.value == "detailed"
        assert req.add_to_kb is False
        assert "Zettelkasten 原子筆記生成完成" in capsys.readouterr().out

    def test_missing_source_exit_2(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["zettel"])
        with pytest.raises(SystemExit) as exc_info:
            generate_zettel_mod.main()
        assert exc_info.value.code == 2  # argparse required group

    def test_citekey_passthrough(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            generate_zettel_mod, "generate_zettel",
            lambda request, **kw: captured.update(request=request) or _fake_zettel_result(),
        )
        monkeypatch.setattr(
            sys, "argv",
            ["zettel", "--pdf", "p.pdf", "--citekey", "Barsalou-1999", "--no-custom", "--no-add-to-kb"],
        )
        assert generate_zettel_mod.main() == 0
        assert captured["request"].cite_key == "Barsalou-1999"

    def test_ground_default_true(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            generate_zettel_mod, "generate_zettel",
            lambda request, **kw: captured.update(request=request) or _fake_zettel_result(),
        )
        monkeypatch.setattr(
            sys, "argv", ["zettel", "--pdf", "p.pdf", "--no-custom", "--no-add-to-kb"]
        )
        assert generate_zettel_mod.main() == 0
        assert captured["request"].ground is True

    def test_no_ground_disables(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            generate_zettel_mod, "generate_zettel",
            lambda request, **kw: captured.update(request=request) or _fake_zettel_result(),
        )
        monkeypatch.setattr(
            sys, "argv",
            ["zettel", "--pdf", "p.pdf", "--no-ground", "--no-custom", "--no-add-to-kb"],
        )
        assert generate_zettel_mod.main() == 0
        assert captured["request"].ground is False


class TestSetupCli:
    def _report(self, recommended):
        return ProviderReport(
            providers=[
                ProviderStatus(name="google", display_name="Google Gemini",
                               available=recommended == "google", message="msg"),
            ],
            recommended=recommended,
        )

    def test_available_exit_0(self, monkeypatch, capsys, tmp_path):
        monkeypatch.setattr(setup_mod, "check_providers", lambda: self._report("google"))
        monkeypatch.setattr(setup_mod, "check_env_file", lambda: True)
        assert setup_mod.main() == 0
        assert "建議提供者: google" in capsys.readouterr().out

    def test_none_available_exit_1(self, monkeypatch, capsys):
        monkeypatch.setattr(setup_mod, "check_providers", lambda: self._report(None))
        monkeypatch.setattr(setup_mod, "check_env_file", lambda: True)
        assert setup_mod.main() == 1
        assert "沒有可用的 LLM 提供者" in capsys.readouterr().out


class TestGuideCli:
    def test_no_request_prints_guide(self, monkeypatch, capsys):
        monkeypatch.setattr(guide_mod, "build_usage_guide", lambda: "使用說明內容 uv run slides")
        monkeypatch.setattr(sys, "argv", ["guide"])
        assert guide_mod.main() == 0
        assert "使用說明內容" in capsys.readouterr().out

    def test_request_calls_suggest(self, monkeypatch, capsys):
        captured = {}

        def fake_suggest(text, **kw):
            captured["text"] = text
            captured["kw"] = kw
            return GuideResult(suggestion="uv run slides --pdf x.pdf", provider_used="anthropic")

        monkeypatch.setattr(guide_mod, "suggest_command", fake_suggest)
        monkeypatch.setattr(sys, "argv", ["guide", "把 pdf 做成投影片", "--provider", "anthropic"])
        assert guide_mod.main() == 0
        assert captured["text"] == "把 pdf 做成投影片"
        assert captured["kw"]["provider"] == "anthropic"
        out = capsys.readouterr().out
        assert "uv run slides --pdf x.pdf" in out
        assert "anthropic" in out

    def test_provider_unavailable_exit_1(self, monkeypatch, capsys):
        from claude_lit.api.errors import ProviderUnavailableError

        def fake_suggest(text, **kw):
            raise ProviderUnavailableError("無法使用供應商 google", hint="執行 uv run setup")

        monkeypatch.setattr(guide_mod, "suggest_command", fake_suggest)
        monkeypatch.setattr(sys, "argv", ["guide", "需求", "--provider", "google"])
        assert guide_mod.main() == 1
        out = capsys.readouterr().out
        assert "無法使用供應商" in out
        assert "setup" in out
