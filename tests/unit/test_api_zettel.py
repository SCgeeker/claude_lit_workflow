# -*- coding: utf-8 -*-
"""api.zettel.generate_zettel 測試（spec: zettel-generation）"""

import sys
from pathlib import Path

import pytest

import claude_lit.api.zettel as zettel_mod
from claude_lit.api.errors import CiteKeyMissingError, LLMGenerationError
from claude_lit.api.models import ZettelRequest
from claude_lit.api.sources import SourceContent
from claude_lit.api.zettel import generate_zettel
from claude_lit.generators import SlideMaker

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_zettel_output.txt"


@pytest.fixture
def mock_llm(monkeypatch):
    output = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr(
        SlideMaker, "call_llm", lambda self, prompt, **kw: (output, "google")
    )
    return output


@pytest.fixture
def fake_pdf(tmp_path, monkeypatch):
    """建立假 PDF 並 mock 來源解析"""
    pdf = tmp_path / "Test-2024.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(
        zettel_mod,
        "resolve_source",
        lambda **kw: SourceContent(content="論文內容", topic="Test Paper", source_type="pdf"),
    )
    return pdf


class TestGenerateZettel:
    def test_generates_12_cards(self, mock_llm, fake_pdf, tmp_path, capsys):
        req = ZettelRequest(pdf=fake_pdf, add_to_kb=False, output_dir=tmp_path / "out")
        result = generate_zettel(req)

        assert result.card_count == 12
        assert len(result.card_files) == 12
        assert all(Path(f).exists() for f in result.card_files)
        assert Path(result.index_file).name == "zettel_index.md"
        assert Path(result.index_file).exists()
        # 輸出結構：output_dir/zettel_cards/*.md
        assert (Path(result.output_dir) / "zettel_cards").is_dir()
        # 核心層不得寫 stdout
        assert capsys.readouterr().out == ""

    def test_cite_key_from_pdf_stem(self, mock_llm, fake_pdf, tmp_path):
        req = ZettelRequest(pdf=fake_pdf, add_to_kb=False, output_dir=tmp_path / "out")
        result = generate_zettel(req)
        assert result.cite_key == "Test-2024"

    def test_passes_zettel_task_type(self, fake_pdf, tmp_path, monkeypatch):
        """zettel API 須傳 task_type='zettelkasten'（NVIDIA 任務分流依此選 qwen thinking）"""
        output = FIXTURE.read_text(encoding="utf-8")
        captured = {}
        monkeypatch.setattr(
            SlideMaker, "call_llm",
            lambda self, prompt, **kw: captured.update(kw) or (output, "nvidia"),
        )
        req = ZettelRequest(pdf=fake_pdf, add_to_kb=False, output_dir=tmp_path / "out")
        generate_zettel(req)
        assert captured.get("task_type") == "zettelkasten"

    def test_explicit_cite_key_wins(self, mock_llm, fake_pdf, tmp_path):
        req = ZettelRequest(
            pdf=fake_pdf, cite_key="Barsalou-1999", add_to_kb=False,
            output_dir=tmp_path / "out",
        )
        result = generate_zettel(req)
        assert result.cite_key == "Barsalou-1999"

    def test_from_kb_missing_cite_key(self, mock_llm, tmp_path, monkeypatch):
        monkeypatch.setattr(
            zettel_mod,
            "resolve_source",
            lambda **kw: SourceContent(
                content="x", topic="T", source_type="pdf",
                paper_data={"id": 1, "title": "T", "authors": [], "year": 2024,
                            "abstract": "", "file_path": "", "cite_key": ""},
            ),
        )
        req = ZettelRequest(from_kb=1, add_to_kb=False, output_dir=tmp_path / "out")
        with pytest.raises(CiteKeyMissingError) as exc_info:
            generate_zettel(req)
        assert "citekey" in (exc_info.value.hint or "").lower() or "cite" in (exc_info.value.hint or "").lower()

    def test_zero_cards_raises(self, fake_pdf, tmp_path, monkeypatch):
        monkeypatch.setattr(
            SlideMaker, "call_llm", lambda self, prompt, **kw: ("沒有任何卡片區塊", "google")
        )
        req = ZettelRequest(pdf=fake_pdf, add_to_kb=False, output_dir=tmp_path / "out")
        with pytest.raises(LLMGenerationError):
            generate_zettel(req)

    def test_no_kb_side_effects(self, mock_llm, fake_pdf, tmp_path):
        """add_to_kb=False：不觸碰知識庫、不載入 chromadb"""
        if "chromadb" in sys.modules:
            pytest.skip("chromadb 已被其他測試載入，無法驗證 lazy import")

        kb_db = Path("knowledge_base/index.db")
        mtime_before = kb_db.stat().st_mtime if kb_db.exists() else None

        req = ZettelRequest(pdf=fake_pdf, add_to_kb=False, output_dir=tmp_path / "out")
        result = generate_zettel(req)

        assert result.kb_added == 0 and result.embedded == 0
        assert "chromadb" not in sys.modules
        if mtime_before is not None:
            assert kb_db.stat().st_mtime == mtime_before

    def test_progress_event_order(self, mock_llm, fake_pdf, tmp_path):
        events = []
        req = ZettelRequest(pdf=fake_pdf, add_to_kb=False, output_dir=tmp_path / "out")
        generate_zettel(req, progress=events.append)
        stages = [e.stage for e in events]
        assert stages == ["extract", "prompt", "llm", "parse", "write"]

    def test_kb_stats_reported(self, mock_llm, fake_pdf, tmp_path, monkeypatch):
        class FakeKB:
            def parse_zettel_card(self, f):
                return {"zettel_id": Path(f).stem, "content": "c"}

            def add_zettel_card(self, data):
                # 模擬一張重複
                if data["zettel_id"].endswith("001"):
                    return {"status": "duplicate", "card_id": 0}
                return {"status": "inserted", "card_id": 1}

            def link_paper_to_zettel(self, *a):
                pass

        monkeypatch.setattr(zettel_mod, "_get_kb_manager", lambda: FakeKB())
        req = ZettelRequest(
            pdf=fake_pdf, add_to_kb=True, embed=False, output_dir=tmp_path / "out"
        )
        result = generate_zettel(req)
        assert result.kb_added == 11
        assert result.kb_skipped == 1


class TestRenderZettelPrompt:
    def test_prompt_contains_card_count_and_cite_key(self, fake_pdf):
        from claude_lit.api.prompts import render_zettel_prompt

        req = ZettelRequest(pdf=fake_pdf, cite_key="Test-2024", add_to_kb=False)
        prompt = render_zettel_prompt(
            req,
            source=SourceContent(content="論文內容", topic="Test Paper", source_type="pdf"),
        )
        assert "Test-2024" in prompt
        assert "12" in prompt  # standard → 12 張
