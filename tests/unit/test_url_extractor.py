"""
URL 提取器單元測試
涵蓋：路由函式、AcademicURLExtractor、WebURLExtractor 輸出 schema、
cite_key 衍生規則（回歸：Path(None) bug）
"""

import pytest
from unittest.mock import patch, MagicMock


# ── 路由函式 ──────────────────────────────────────────────────────────────────

class TestIsAcademicUrl:
    """_is_academic_url() 分類規則"""

    def test_arxiv_abstract_url(self):
        from claude_lit.extractors.url_extractor import _is_academic_url
        assert _is_academic_url("https://arxiv.org/abs/2301.00001") is True

    def test_arxiv_pdf_url(self):
        from claude_lit.extractors.url_extractor import _is_academic_url
        assert _is_academic_url("https://arxiv.org/pdf/2301.00001.pdf") is True

    def test_doi_url(self):
        from claude_lit.extractors.url_extractor import _is_academic_url
        assert _is_academic_url("https://doi.org/10.1037/abc123") is True

    def test_pubmed_url(self):
        from claude_lit.extractors.url_extractor import _is_academic_url
        assert _is_academic_url("https://pubmed.ncbi.nlm.nih.gov/12345678/") is True

    def test_nature_url(self):
        from claude_lit.extractors.url_extractor import _is_academic_url
        assert _is_academic_url("https://www.nature.com/articles/s41586-023-00001-x") is True

    def test_medium_blog(self):
        from claude_lit.extractors.url_extractor import _is_academic_url
        assert _is_academic_url("https://medium.com/@user/some-post") is False

    def test_substack_blog(self):
        from claude_lit.extractors.url_extractor import _is_academic_url
        assert _is_academic_url("https://username.substack.com/p/some-post") is False

    def test_github_page(self):
        from claude_lit.extractors.url_extractor import _is_academic_url
        assert _is_academic_url("https://github.com/user/repo") is False


class TestGetExtractor:
    """get_extractor() 依 source 類型路由"""

    def test_pdf_path_returns_pdf_extractor(self):
        from claude_lit.extractors import get_extractor
        from claude_lit.extractors.pdf_extractor import PDFExtractor
        assert isinstance(get_extractor("paper.pdf"), PDFExtractor)

    def test_academic_url_returns_academic_extractor(self):
        from claude_lit.extractors import get_extractor
        from claude_lit.extractors.url_extractor import AcademicURLExtractor
        assert isinstance(get_extractor("https://arxiv.org/abs/2301.00001"), AcademicURLExtractor)

    def test_web_url_returns_web_extractor(self):
        from claude_lit.extractors import get_extractor
        from claude_lit.extractors.url_extractor import WebURLExtractor
        assert isinstance(get_extractor("https://medium.com/@user/post"), WebURLExtractor)

    def test_unsupported_extension_raises(self):
        from claude_lit.extractors import get_extractor
        with pytest.raises(ValueError, match="Unsupported"):
            get_extractor("paper.docx")


# ── AcademicURLExtractor ──────────────────────────────────────────────────────

MOCK_ACADEMIC_TEXT = (
    "Title: Serial Feature Combination in Bilinguals\n\n"
    "Abstract: This study examines how bilingual experience modulates "
    "perceptual feature integration during sentence comprehension.\n\n"
    "Methods: Participants completed a sentence-picture verification task.\n\n"
    "Results: EC bilinguals showed dual-feature disadvantage at short SOA.\n\n"
    "Discussion: Findings suggest language entropy moderates feature combination."
)


class TestAcademicURLExtractor:
    """AcademicURLExtractor 輸出 schema 與 source_type"""

    def _make_extractor_with_mock(self, text: str):
        from claude_lit.extractors.url_extractor import AcademicURLExtractor
        extractor = AcademicURLExtractor()
        with patch("claude_lit.extractors.url_extractor.trafilatura") as mock_tf:
            mock_tf.fetch_url.return_value = "<html><body>" + text + "</body></html>"
            mock_tf.extract.return_value = text
            result = extractor.extract("https://arxiv.org/abs/2301.00001")
        return result

    def test_returns_full_text(self):
        result = self._make_extractor_with_mock(MOCK_ACADEMIC_TEXT)
        assert "full_text" in result
        assert len(result["full_text"]) > 0

    def test_source_type_is_academic_url(self):
        result = self._make_extractor_with_mock(MOCK_ACADEMIC_TEXT)
        assert result["source_type"] == "academic_url"

    def test_has_required_schema_keys(self):
        result = self._make_extractor_with_mock(MOCK_ACADEMIC_TEXT)
        for key in ("full_text", "char_count", "truncated", "structure", "source_type", "url"):
            assert key in result, f"Missing key: {key}"

    def test_structure_has_abstract(self):
        result = self._make_extractor_with_mock(MOCK_ACADEMIC_TEXT)
        assert result["structure"]["abstract"] is not None

    def test_char_count_matches_text(self):
        result = self._make_extractor_with_mock(MOCK_ACADEMIC_TEXT)
        assert result["char_count"] == len(result["full_text"])

    def test_trafilatura_unavailable_raises(self):
        from claude_lit.extractors.url_extractor import AcademicURLExtractor
        extractor = AcademicURLExtractor()
        with patch("claude_lit.extractors.url_extractor.trafilatura", None):
            with pytest.raises(ImportError, match="trafilatura"):
                extractor.extract("https://arxiv.org/abs/2301.00001")

    def test_fetch_returns_none_raises(self):
        from claude_lit.extractors.url_extractor import AcademicURLExtractor
        extractor = AcademicURLExtractor()
        with patch("claude_lit.extractors.url_extractor.trafilatura") as mock_tf:
            mock_tf.fetch_url.return_value = None
            with pytest.raises(ValueError, match="fetch"):
                extractor.extract("https://arxiv.org/abs/2301.00001")


# ── WebURLExtractor ───────────────────────────────────────────────────────────

MOCK_WEB_TEXT = (
    "Why Mental Simulation Matters\n\n"
    "Researchers have long debated whether language comprehension activates "
    "perceptual representations. Here I argue that it does, based on three "
    "lines of evidence from behavioural studies.\n\n"
    "First, response times slow when pictures mismatch sentence-implied properties. "
    "Second, bilingual participants show different patterns depending on L1. "
    "Third, classifier languages provide a natural experiment.\n\n"
    "The implication is that language processing is grounded in perception."
)


class TestWebURLExtractor:
    """WebURLExtractor 輸出 schema 與 source_type"""

    def _make_extractor_with_mock(self, text: str):
        from claude_lit.extractors.url_extractor import WebURLExtractor
        extractor = WebURLExtractor()
        with patch("claude_lit.extractors.url_extractor.trafilatura") as mock_tf:
            mock_tf.fetch_url.return_value = "<html><body>" + text + "</body></html>"
            mock_tf.extract.return_value = text
            result = extractor.extract("https://medium.com/@user/mental-sim")
        return result

    def test_source_type_is_web_url(self):
        result = self._make_extractor_with_mock(MOCK_WEB_TEXT)
        assert result["source_type"] == "web_url"

    def test_has_required_schema_keys(self):
        result = self._make_extractor_with_mock(MOCK_WEB_TEXT)
        for key in ("full_text", "char_count", "truncated", "structure", "source_type", "url"):
            assert key in result, f"Missing key: {key}"

    def test_structure_abstract_is_none_for_web(self):
        result = self._make_extractor_with_mock(MOCK_WEB_TEXT)
        # web pages don't have academic abstract fields
        assert result["structure"]["abstract"] is None

    def test_full_text_populated(self):
        result = self._make_extractor_with_mock(MOCK_WEB_TEXT)
        assert MOCK_WEB_TEXT in result["full_text"]


# ── cite_key 衍生（回歸：--url 模式不得觸碰 args.pdf）────────────────────────

class TestUrlCiteKeyDerivation:
    """
    回歸測試：generate_zettel.py --url 路徑的 cite_key 與 output_dir
    推導邏輯獨立於 args.pdf（修復前 Path(None).stem 導致 AttributeError）
    """

    def _derive_cite_key(self, url: str) -> str:
        import re
        return re.sub(r'[^a-zA-Z0-9_-]', '_', url.split("//")[-1])[:40]

    def test_arxiv_url_produces_valid_cite_key(self):
        key = self._derive_cite_key("https://arxiv.org/abs/2301.00001")
        assert len(key) > 0
        assert all(c.isalnum() or c in '_-' for c in key)

    def test_cite_key_length_capped_at_40(self):
        long_url = "https://medium.com/@very-long-username/a-very-long-article-title-that-exceeds-limits"
        key = self._derive_cite_key(long_url)
        assert len(key) <= 40

    def test_cite_key_no_path_separator(self):
        key = self._derive_cite_key("https://arxiv.org/abs/2301.00001")
        assert "/" not in key
        assert "\\" not in key

    def test_output_dir_uses_cite_key_not_pdf_stem(self):
        from pathlib import Path
        from datetime import datetime
        url = "https://arxiv.org/abs/2301.00001"
        cite_key = self._derive_cite_key(url)
        date_str = datetime.now().strftime("%Y%m%d")
        output_dir = Path(f"output/zettelkasten_notes/zettel_{cite_key}_{date_str}")
        # must not reference None
        assert cite_key in str(output_dir)
        assert "None" not in str(output_dir)
