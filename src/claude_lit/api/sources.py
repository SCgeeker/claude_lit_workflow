# -*- coding: utf-8 -*-
"""內容來源解析（slides 與 zettel 共用）

支援五種來源：PDF 檔案、URL、知識庫論文（lazy import）、文字檔（txt/md/srt/vtt/epub）、
原始文字內容。依 media profile 的 preprocess 套用前處理（逐字稿清理、書眉移除、章節選取）；
送進 prompt 與 grounding gate 的都是本模組回傳的同一份 content。
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from claude_lit.extractors import PDFExtractor, TextExtractor, get_extractor
from claude_lit.extractors.chapters import select_chapters, strip_running_heads

from .errors import ExtractionError, SourceNotFoundError

# 文字來源的 source_type（無 PDF CID glyph 抽取失真；grounding 的 CJK 政策據此判定）
TEXT_SOURCE_TYPES = ("text", "transcript")

# 章節模式先抽全書再選章；此上限只防異常巨檔
_CHAPTER_SCAN_CHARS = 5_000_000


class SourceContent(BaseModel):
    """解析後的內容來源"""

    content: Optional[str] = None
    topic: Optional[str] = None
    source_type: str = "pdf"
    paper_data: Optional[Dict[str, Any]] = None  # from_kb 時的論文 metadata
    timeline: Optional[List[Tuple[int, float]]] = None  # 逐字稿：字元位置 → 秒數
    warnings: List[str] = []


def _preprocess_steps(media_type: str) -> set:
    if media_type == "paper":
        return set()
    from .media import get_media_profile

    return set(get_media_profile(media_type).get("preprocess", []))


def _finalize_long_text(
    text: str,
    *,
    steps: set,
    chapter: Optional[str],
    max_chars: int,
    has_timeline: bool,
    warnings: List[str],
) -> str:
    """書眉移除 → 章節選取 → 字數上限（截斷保留前段，timeline 位置不受影響）"""
    if "strip_running_heads" in steps and not has_timeline:
        text = strip_running_heads(text)
    if chapter:
        from .models import parse_chapter_range

        start, end = parse_chapter_range(chapter)
        try:
            text, _ = select_chapters(text, start, end)
        except ValueError as e:
            raise SourceNotFoundError(
                str(e), hint="確認章標題格式（如「第三章」「Chapter 3」），或改用不含 --chapter 的全文模式"
            ) from e
        label = f"第 {start} 章" if start == end else f"第 {start}–{end} 章"
        warnings.append(f"已選取{label}（{len(text)} 字元）")
    if len(text) > max_chars:
        original = len(text)
        text = text[:max_chars]
        hint = "；長篇書籍請以 --chapter 指定章節" if "chapter_split" in steps and not chapter else ""
        warnings.append(f"內容已截斷（{original} → {max_chars} 字元）{hint}")
    return text


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
    text: Optional[Path] = None,
    content: Optional[str] = None,
    max_chars: int = 10000,
    media_type: str = "paper",
    chapter: Optional[str] = None,
    keep_fillers: bool = False,
) -> SourceContent:
    """解析內容來源為統一的 SourceContent。

    Raises:
        SourceNotFoundError: PDF / 文字檔 / 知識庫論文 / 指定章節不存在
        ExtractionError: 抽取失敗
    """
    warnings: List[str] = []
    steps = _preprocess_steps(media_type)

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
        long_text = bool(chapter or "strip_running_heads" in steps)
        try:
            extractor = PDFExtractor(max_chars=_CHAPTER_SCAN_CHARS if long_text else max_chars)
            result = extractor.extract(str(pdf_path))
        except Exception as e:  # pdfplumber / PyPDF2 例外統一轉型
            raise ExtractionError(
                f"PDF 抽取失敗：{e}", hint="請確認 PDF 未加密且非純掃描影像"
            ) from e
        pdf_text = result["full_text"]
        if long_text:
            pdf_text = _finalize_long_text(
                pdf_text, steps=steps, chapter=chapter, max_chars=max_chars,
                has_timeline=False, warnings=warnings,
            )
        elif result.get("truncated"):
            warnings.append(
                f"PDF 內容已截斷（{result.get('char_count', '?')} → {max_chars} 字元）"
            )
        return SourceContent(
            content=pdf_text,
            topic=topic or result.get("title") or pdf_path.stem,
            source_type="pdf",
            warnings=warnings,
        )

    # 3. 文字檔（含逐字稿前處理）
    if text is not None:
        text_path = Path(text)
        if not text_path.exists():
            raise SourceNotFoundError(
                f"找不到文字檔：{text_path}", hint="請確認檔案路徑是否正確"
            )
        try:
            result = TextExtractor().extract(
                str(text_path),
                remove_fillers="strip_fillers" in steps and not keep_fillers,
                merge_turns="merge_turns" in steps,
                time_markers="insert_time_markers" in steps,
            )
        except ValueError as e:
            raise ExtractionError(str(e), hint="支援 .txt / .md / .srt / .vtt / .epub") from e
        except Exception as e:  # 編碼、EPUB 結構等例外統一轉型
            raise ExtractionError(
                f"文字檔抽取失敗：{e}", hint="請確認檔案為 UTF-8 文字或有效的 EPUB"
            ) from e
        body = _finalize_long_text(
            result["full_text"], steps=steps, chapter=chapter, max_chars=max_chars,
            has_timeline=bool(result.get("timeline")), warnings=warnings,
        )
        return SourceContent(
            content=body,
            topic=topic or result.get("title") or text_path.stem,
            source_type=result["source_type"],
            # 選章會切掉前段文字，timeline 位置隨之失準 → 不提供（不寫錯誤時間戳）
            timeline=None if chapter else result.get("timeline"),
            warnings=warnings,
        )

    # 4. URL
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

    # 5. 原始內容 / 純主題
    return SourceContent(content=content, topic=topic, source_type="pdf", warnings=warnings)
