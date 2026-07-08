"""
提取器模組
支援多種格式的文檔內容提取：PDF、學術 URL、一般網頁 URL
"""

from pathlib import Path
from .pdf_extractor import PDFExtractor, extract_pdf_text
from .url_extractor import AcademicURLExtractor, WebURLExtractor, _is_academic_url


def get_extractor(source: str):
    """
    依 source 類型路由至對應 Extractor。

    Args:
        source: 檔案路徑或 URL

    Returns:
        PDFExtractor | AcademicURLExtractor | WebURLExtractor

    Raises:
        ValueError: 不支援的副檔名
    """
    if source.startswith("http://") or source.startswith("https://"):
        if _is_academic_url(source):
            return AcademicURLExtractor()
        return WebURLExtractor()

    suffix = Path(source).suffix.lower()
    if suffix == ".pdf":
        return PDFExtractor()

    raise ValueError(f"Unsupported source format: {suffix!r}. Supported: .pdf, http/https URLs")


__all__ = [
    "PDFExtractor",
    "extract_pdf_text",
    "AcademicURLExtractor",
    "WebURLExtractor",
    "get_extractor",
]
