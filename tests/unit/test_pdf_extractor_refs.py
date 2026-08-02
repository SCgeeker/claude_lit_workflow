# -*- coding: utf-8 -*-
"""pdf_extractor 參考文獻剝除測試（② References 回收字元預算）

_strip_references 應在文件後段偵測獨立的 References/Bibliography 標題行並裁切，
把字元預算讓給正文；找不到或僅內文提及時不得誤砍。
"""

import pytest

from claude_lit.extractors.pdf_extractor import PDFExtractor


def _ext():
    return PDFExtractor(max_chars=200000)


def test_strip_references_cuts_at_heading():
    """後段出現獨立 References 標題行 → 裁掉其後的書目"""
    body = "Introduction. We study grounding in language comprehension. " * 200
    refs = "References\n" + "Smith, J. (2020). A paper. Journal of Foo, 1, 1-9.\n" * 60
    text = body + "\n" + refs
    stripped, did = _ext()._strip_references(text)
    assert did is True
    assert "Smith, J." not in stripped
    assert stripped.startswith("Introduction.")


def test_strip_references_bibliography_variant():
    body = "Body text about atomic notes. " * 300
    text = body + "\nBibliography\n" + "Doe, A. (2019). Bar. Baz Press.\n" * 40
    stripped, did = _ext()._strip_references(text)
    assert did is True
    assert "Doe, A." not in stripped


def test_strip_references_ignores_inline_mention():
    """內文句子裡出現 'references'（非獨立標題行）→ 不裁切"""
    text = "We build on prior references to grounding theory throughout. " * 200
    stripped, did = _ext()._strip_references(text)
    assert did is False
    assert stripped == text


def test_strip_references_no_section_returns_unchanged():
    text = "Plain body with no bibliography section whatsoever. " * 200
    stripped, did = _ext()._strip_references(text)
    assert did is False
    assert stripped == text


def test_strip_references_ignores_toc_early_match():
    """前段（如目錄）出現的 References 條目不應被當成書目起點裁掉整篇正文"""
    toc = "References\n"  # 目錄式早期出現，位於文件最前 20%
    body = "Real body content that must survive. " * 400
    text = toc + body
    stripped, did = _ext()._strip_references(text)
    assert "Real body content" in stripped


def test_extract_result_reflects_reference_trim(tmp_path, monkeypatch):
    """extract() 應在 max_chars 截斷前先剝除 references，並在 structure 標記 references_found"""
    body = "Methods and Results described in detail here. " * 100
    refs = "\nReferences\n" + "Author, X. (2021). Title. Venue.\n" * 30
    ext = PDFExtractor(max_chars=200000)
    monkeypatch.setattr(ext, "_extract_with_pdfplumber", lambda p: body + refs)
    monkeypatch.setattr(ext, "_extract_tables_with_pdfplumber", lambda p: [])

    fake_pdf = tmp_path / "x.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")
    result = ext.extract(str(fake_pdf), extract_tables=False)

    assert "Author, X." not in result["full_text"]
    assert result["structure"]["references_found"] is True
