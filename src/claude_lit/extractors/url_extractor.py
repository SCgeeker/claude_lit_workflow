"""
URL 提取器模組
支援兩種 URL 來源類型：
  - AcademicURLExtractor：arXiv、DOI、學術出版商 HTML
  - WebURLExtractor：部落格、一般網頁
兩者均使用 trafilatura 取得並清理 HTML，輸出 schema 與 PDFExtractor 相容。
"""

from typing import Dict, Any, Optional

try:
    import trafilatura
    _TRAFILATURA_AVAILABLE = True
except ImportError:
    trafilatura = None
    _TRAFILATURA_AVAILABLE = False

_ACADEMIC_DOMAINS = [
    "arxiv.org",
    "doi.org",
    "pubmed.ncbi.nlm.nih.gov",
    "nature.com",
    "science.org",
    "springer.com",
    "wiley.com",
    "tandfonline.com",
    "sagepub.com",
    "journals.plos.org",
    "frontiersin.org",
    "psycnet.apa.org",
    "biorxiv.org",
    "medrxiv.org",
    "osf.io",
]


def _is_academic_url(url: str) -> bool:
    """True if URL belongs to a known academic domain."""
    return any(domain in url for domain in _ACADEMIC_DOMAINS)


class AcademicURLExtractor:
    """
    從學術網頁（arXiv、DOI、出版商 HTML）提取文字。
    嘗試解析 abstract / sections 等學術結構。
    """

    def __init__(self, max_chars: int = 40000):
        self.max_chars = max_chars

    def extract(self, url: str) -> Dict[str, Any]:
        """
        提取學術網頁內容。

        Returns:
            與 PDFExtractor.extract() 相容的 dict，額外包含 source_type 與 url
        """
        if trafilatura is None:
            raise ImportError(
                "trafilatura not installed. Run: uv add trafilatura"
            )

        raw_html = trafilatura.fetch_url(url)
        if raw_html is None:
            raise ValueError(f"無法 fetch URL（可能需要登入或網路問題）：{url}")

        full_text = trafilatura.extract(raw_html) or ""

        truncated = False
        if len(full_text) > self.max_chars:
            full_text = full_text[: self.max_chars]
            truncated = True

        structure = self._parse_academic_structure(full_text)

        return {
            "url": url,
            "full_text": full_text,
            "char_count": len(full_text),
            "truncated": truncated,
            "structure": structure,
            "source_type": "academic_url",
        }

    def _parse_academic_structure(self, text: str) -> Dict[str, Any]:
        """
        從純文字推斷學術結構（abstract / sections）。
        使用關鍵詞啟發法；品質低於 PDF 結構解析，但對 arXiv HTML 已足夠。
        """
        import re

        abstract: Optional[str] = None
        sections = []

        # 嘗試擷取 abstract
        abs_match = re.search(
            r"(?:abstract|摘要)[:\s]*(.{50,800}?)(?:\n\n|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if abs_match:
            abstract = abs_match.group(1).strip()

        # 嘗試識別章節標題（全大寫行、或典型學術章節名稱）
        section_headers = re.findall(
            r"^((?:Introduction|Methods?|Results?|Discussion|Conclusion|"
            r"Background|Related Work|References|引言|方法|結果|討論|結論).*)$",
            text,
            re.MULTILINE | re.IGNORECASE,
        )
        for header in section_headers:
            sections.append({"title": header.strip(), "content": ""})

        return {
            "abstract": abstract,
            "sections": sections,
            "title": None,
            "authors": [],
            "keywords": [],
        }


class WebURLExtractor:
    """
    從一般網頁（部落格、新聞、文件）提取文字。
    不做學術結構假設；structure 欄位保持最小化。
    """

    def __init__(self, max_chars: int = 30000):
        self.max_chars = max_chars

    def extract(self, url: str) -> Dict[str, Any]:
        """
        提取一般網頁內容。

        Returns:
            與 PDFExtractor.extract() 相容的 dict，source_type = "web_url"
        """
        if trafilatura is None:
            raise ImportError(
                "trafilatura not installed. Run: uv add trafilatura"
            )

        raw_html = trafilatura.fetch_url(url)
        if raw_html is None:
            raise ValueError(f"無法 fetch URL：{url}")

        full_text = trafilatura.extract(raw_html) or ""

        truncated = False
        if len(full_text) > self.max_chars:
            full_text = full_text[: self.max_chars]
            truncated = True

        return {
            "url": url,
            "full_text": full_text,
            "char_count": len(full_text),
            "truncated": truncated,
            "structure": {
                "abstract": None,
                "sections": [],
                "title": None,
                "authors": [],
                "keywords": [],
            },
            "source_type": "web_url",
        }
