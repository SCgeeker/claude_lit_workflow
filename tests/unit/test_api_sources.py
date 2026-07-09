# -*- coding: utf-8 -*-
"""api.sources 內容來源解析測試（spec: slide-generation / zettel-generation）"""

import pytest

from claude_lit.api.errors import SourceNotFoundError
from claude_lit.api import sources as sources_mod
from claude_lit.api.sources import resolve_source


class TestResolveSource:
    def test_topic_only(self):
        src = resolve_source(topic="深度學習")
        assert src.topic == "深度學習"
        assert src.content is None
        assert src.source_type == "pdf"

    def test_raw_content(self):
        src = resolve_source(topic="t", content="# 論文全文")
        assert src.content == "# 論文全文"

    def test_pdf_not_found_raises_typed_error(self, tmp_path):
        missing = tmp_path / "nope.pdf"
        with pytest.raises(SourceNotFoundError) as exc_info:
            resolve_source(pdf=missing)
        assert exc_info.value.hint

    def test_pdf_extraction(self, tmp_path, monkeypatch):
        pdf = tmp_path / "Barsalou-1999.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        class FakeExtractor:
            def __init__(self, max_chars=10000):
                self.max_chars = max_chars

            def extract(self, path):
                return {
                    "full_text": "抽取的內容",
                    "char_count": 5,
                    "truncated": False,
                    "title": None,
                }

        monkeypatch.setattr(sources_mod, "PDFExtractor", FakeExtractor)
        src = resolve_source(pdf=pdf, max_chars=10000)
        assert src.content == "抽取的內容"
        # 未指定 topic 時從檔名推斷
        assert src.topic == "Barsalou-1999"
        assert not src.warnings

    def test_pdf_truncation_warning(self, tmp_path, monkeypatch):
        pdf = tmp_path / "p.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        class FakeExtractor:
            def __init__(self, max_chars=10000):
                pass

            def extract(self, path):
                return {"full_text": "x", "char_count": 99999, "truncated": True, "title": None}

        monkeypatch.setattr(sources_mod, "PDFExtractor", FakeExtractor)
        src = resolve_source(pdf=pdf)
        assert any("截斷" in w for w in src.warnings)

    def test_url_extraction(self, monkeypatch):
        class FakeUrlExtractor:
            def extract(self, url):
                return {
                    "full_text": "網頁內容",
                    "char_count": 4,
                    "truncated": False,
                    "source_type": "academic_url",
                    "structure": {"title": "Paper Title"},
                }

        monkeypatch.setattr(sources_mod, "get_extractor", lambda url: FakeUrlExtractor())
        src = resolve_source(url="https://arxiv.org/abs/1234")
        assert src.content == "網頁內容"
        assert src.topic == "Paper Title"
        assert src.source_type == "academic_url"

    def test_from_kb_not_found(self, monkeypatch):
        class FakeKB:
            def get_paper_by_id(self, pid):
                return None

        monkeypatch.setattr(sources_mod, "_load_kb_manager", lambda: FakeKB())
        with pytest.raises(SourceNotFoundError):
            resolve_source(from_kb=999)

    def test_from_kb_reads_markdown(self, tmp_path, monkeypatch):
        md = tmp_path / "note.md"
        md.write_text("# 筆記內容", encoding="utf-8")

        class FakeKB:
            def get_paper_by_id(self, pid):
                return {
                    "id": pid,
                    "title": "Test Paper",
                    "authors": ["A"],
                    "year": 2024,
                    "abstract": "abs",
                    "file_path": str(md),
                    "cite_key": "Test-2024",
                }

        monkeypatch.setattr(sources_mod, "_load_kb_manager", lambda: FakeKB())
        src = resolve_source(from_kb=1)
        assert src.content == "# 筆記內容"
        assert src.topic == "Test Paper"
        assert src.paper_data["cite_key"] == "Test-2024"
