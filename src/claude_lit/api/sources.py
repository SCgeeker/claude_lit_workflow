# -*- coding: utf-8 -*-
"""內容來源解析（slides 與 zettel 共用）

支援四種來源：PDF 檔案、URL、知識庫論文（lazy import）、原始文字內容。
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from claude_lit.extractors import PDFExtractor, get_extractor

from .errors import ExtractionError, SourceNotFoundError


class SourceContent(BaseModel):
    """解析後的內容來源"""

    content: Optional[str] = None
    topic: Optional[str] = None
    source_type: str = "pdf"
    paper_data: Optional[Dict[str, Any]] = None  # from_kb 時的論文 metadata
    warnings: List[str] = []


def _load_kb_manager():
    """lazy import：只有 from_kb 來源才載入知識庫模組"""
    from claude_lit.knowledge_base import KnowledgeBaseManager

    return KnowledgeBaseManager()


def resolve_source(
    *,
    topic: Optional[str] = None,
    pdf: Optional[Path] = None,
    url: Optional[str] = None,
    from_kb: Optional[int] = None,
    content: Optional[str] = None,
    max_chars: int = 10000,
) -> SourceContent:
    """解析內容來源為統一的 SourceContent。

    Raises:
        SourceNotFoundError: PDF / 知識庫論文不存在
        ExtractionError: 抽取失敗
    """
    warnings: List[str] = []

    # 1. 知識庫論文
    if from_kb is not None:
        kb = _load_kb_manager()
        paper = kb.get_paper_by_id(from_kb)
        if not paper:
            raise SourceNotFoundError(
                f"找不到知識庫論文 ID {from_kb}",
                hint="使用 'uv run kb list' 查看所有論文",
            )
        md_path = Path(paper["file_path"])
        if md_path.exists():
            text = md_path.read_text(encoding="utf-8")
        else:
            warnings.append("找不到 Markdown 筆記，使用資料庫內容")
            authors_str = ", ".join(paper["authors"]) if paper["authors"] else "未知"
            abstract = paper["abstract"] or "無摘要"
            text = (
                f"# {paper['title']}\n\n作者：{authors_str}\n"
                f"年份：{paper['year'] or '未知'}\n\n## 摘要\n{abstract}"
            )
        return SourceContent(
            content=text,
            topic=topic or paper["title"],
            source_type="pdf",
            paper_data=paper,
            warnings=warnings,
        )

    # 2. PDF 檔案
    if pdf is not None:
        pdf_path = Path(pdf)
        if not pdf_path.exists():
            raise SourceNotFoundError(
                f"找不到 PDF 檔案：{pdf_path}",
                hint="請確認檔案路徑是否正確",
            )
        try:
            extractor = PDFExtractor(max_chars=max_chars)
            result = extractor.extract(str(pdf_path))
        except Exception as e:  # pdfplumber / PyPDF2 例外統一轉型
            raise ExtractionError(
                f"PDF 抽取失敗：{e}", hint="請確認 PDF 未加密且非純掃描影像"
            ) from e
        if result.get("truncated"):
            warnings.append(
                f"PDF 內容已截斷（{result.get('char_count', '?')} → {max_chars} 字元）"
            )
        return SourceContent(
            content=result["full_text"],
            topic=topic or result.get("title") or pdf_path.stem,
            source_type="pdf",
            warnings=warnings,
        )

    # 3. URL
    if url is not None:
        try:
            extractor = get_extractor(url)
            result = extractor.extract(url)
        except Exception as e:
            raise ExtractionError(
                f"URL 抽取失敗：{e}", hint="請確認網址可存取，或改用 PDF 來源"
            ) from e
        if result.get("truncated"):
            warnings.append(f"內容已截斷（{result.get('char_count', '?')} 字元）")
        return SourceContent(
            content=result["full_text"],
            topic=topic or result.get("structure", {}).get("title") or url,
            source_type=result.get("source_type", "url"),
            warnings=warnings,
        )

    # 4. 原始內容 / 純主題
    return SourceContent(content=content, topic=topic, source_type="pdf", warnings=warnings)
