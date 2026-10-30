# -*- coding: utf-8 -*-
"""文字來源提取與章節切分測試（spec: slide-generation / zettel-generation — 文字來源、長篇分章）"""

import zipfile

import pytest

from claude_lit.extractors import TextExtractor, get_extractor
from claude_lit.extractors.chapters import find_chapters, select_chapters, strip_running_heads
from claude_lit.extractors.text_extractor import (
    Cue,
    build_transcript,
    parse_subtitles,
    parse_timestamped_text,
    strip_fillers,
    timestamp_at,
)

SRT = """1
00:00:01,000 --> 00:00:04,000
主持人：嗯，今天我們來談注意力。

2
00:12:30,000 --> 00:12:35,000
來賓 A：呃，我認為注意力其實是一種預測，

3
00:12:35,500 --> 00:12:39,000
而不是一盞探照燈。
"""

VTT = """WEBVTT

NOTE 這是註解區塊

intro
00:00:01.000 --> 00:00:03.000
<v Host>Welcome to the show.</v>

00:01:05.250 --> 00:01:08.000
<v Guest>Attention is <i>prediction</i>.</v>
"""


class TestSubtitleParsing:
    def test_srt_drops_index_and_timing(self):
        cues = parse_subtitles(SRT)
        assert [c.start for c in cues] == [1.0, 750.0, 755.5]
        assert cues[0].speaker == "主持人"
        assert cues[1].speaker == "來賓 A"
        assert cues[2].speaker is None  # 延續上一位講者，由 build_transcript 承接
        joined = " ".join(c.text for c in cues)
        assert "-->" not in joined
        assert "00:12" not in joined

    def test_vtt_header_note_voice_tags(self):
        cues = parse_subtitles(VTT)
        assert len(cues) == 2
        assert cues[0] == Cue(1.0, "Welcome to the show.", "Host")
        assert cues[1].speaker == "Guest"
        assert cues[1].text == "Attention is prediction."  # 行內標籤移除
        assert cues[1].start == 65.25

    def test_timestamped_text_same_and_next_line(self):
        raw = "[00:00:05] 開場白\n00:01:10\n第二段內容\n(1:02:03) 第三段"
        cues = parse_timestamped_text(raw)
        assert [(c.start, c.text) for c in cues] == [
            (5.0, "開場白"), (70.0, "第二段內容"), (3723.0, "第三段"),
        ]

    def test_plain_text_is_not_timestamped(self):
        assert parse_timestamped_text("會議 10:30 開始。\n沒有其他時間碼。") is None


class TestFillers:
    def test_removes_standalone_fillers(self):
        assert strip_fillers("嗯，今天我們來談。呃，這很重要。") == "今天我們來談。這很重要。"
        assert strip_fillers("Um, this is, uh, important.") == "this is, important."

    def test_keeps_meaningful_words(self):
        # 「就是」「然後」與詞內的 um（如 summary、umbrella）不移除
        assert strip_fillers("然後就是這樣") == "然後就是這樣"
        assert strip_fillers("a summary under the umbrella") == "a summary under the umbrella"


class TestBuildTranscript:
    def test_markers_on_own_line_and_merged_turns(self):
        text, timeline = build_transcript(parse_subtitles(SRT))
        lines = text.split("\n")
        assert "[00:00:01]" in lines and "[00:12:30]" in lines  # 標記獨立成行
        assert "來賓 A：我認為注意力其實是一種預測，而不是一盞探照燈。" in lines
        assert "嗯" not in text and "呃" not in text
        assert len(timeline) == 3

    def test_timeline_maps_offset_to_cue_start(self):
        text, timeline = build_transcript(parse_subtitles(SRT))
        assert timestamp_at(timeline, text.index("今天")) == "00:00:01"
        assert timestamp_at(timeline, text.index("我認為")) == "00:12:30"
        assert timestamp_at(timeline, text.index("而不是")) == "00:12:35"

    def test_flags_off(self):
        text, _ = build_transcript(
            parse_subtitles(SRT), remove_fillers=False, merge_turns=False, time_markers=False
        )
        assert "[00:" not in text
        assert "嗯" in text
        assert text.count("\n\n") == 2  # 每個片段各自成段


class TestTextExtractor:
    def test_srt_file(self, tmp_path):
        f = tmp_path / "ep42.srt"
        f.write_text(SRT, encoding="utf-8")
        r = TextExtractor().extract(str(f), remove_fillers=True, merge_turns=True, time_markers=True)
        assert r["source_type"] == "transcript"
        assert r["title"] == "ep42"
        assert r["timeline"]
        assert "[00:12:30]" in r["full_text"]

    def test_markdown_title_and_no_timeline(self, tmp_path):
        f = tmp_path / "post.md"
        f.write_text("# 為什麼 X 會失敗\n\n內文第一段。", encoding="utf-8")
        r = TextExtractor().extract(str(f))
        assert r["source_type"] == "text"
        assert r["title"] == "為什麼 X 會失敗"
        assert r["timeline"] is None
        assert r["full_text"].startswith("# 為什麼")

    def test_epub_spine_order(self, tmp_path):
        epub = tmp_path / "book.epub"
        with zipfile.ZipFile(epub, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr(
                "META-INF/container.xml",
                '<?xml version="1.0"?><container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                "</rootfiles></container>",
            )
            zf.writestr(
                "OEBPS/content.opf",
                '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>心智與世界</dc:title></metadata>'
                '<manifest><item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/>'
                '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>'
                '<spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>',
            )
            zf.writestr("OEBPS/ch1.xhtml", "<html><head><style>p{}</style></head>"
                        "<body><h1>第一章 緒論</h1><p>第一段。</p></body></html>")
            zf.writestr("OEBPS/ch2.xhtml", "<html><body><h1>第二章 方法</h1><p>第二段。</p></body></html>")
        r = TextExtractor().extract(str(epub))
        assert r["title"] == "心智與世界"
        text = r["full_text"]
        assert text.index("第一章 緒論") < text.index("第二章 方法")  # 依 spine 而非 manifest 順序
        assert "p{}" not in text
        assert "第一章 緒論\n" in text  # 區塊標籤換行

    def test_unsupported_suffix(self, tmp_path):
        f = tmp_path / "notes.docx"
        f.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError):
            TextExtractor().extract(str(f))

    def test_get_extractor_routes_text(self):
        assert isinstance(get_extractor("talk.srt"), TextExtractor)
        assert isinstance(get_extractor("book.epub"), TextExtractor)


BODY = "內容" * 400  # 800 字元：超過章節最短長度門檻


def _book(*lines):
    return "\n".join(lines)


class TestChapters:
    def test_toc_entries_and_cross_references_skipped(self):
        book = _book(
            "目錄", "第一章 緒論 1", "第二章 方法 20", "第三章 結果 40",
            "序言" + BODY,  # 目錄最後一項後接長篇序言
            "第一章 緒論", BODY,
            "第二章 方法", "第三章討論了更多細節", BODY,  # 內文引用（無分隔）不是章標題
            "Chapter 3 shows that the effect holds",  # 英文內文引用（小寫續句）
            "第三章　結果", BODY,
        )
        chapters = find_chapters(book)
        assert [c.number for c in chapters] == [1, 2, 3]
        assert chapters[0].start == book.index("第一章 緒論\n")
        assert chapters[2].heading == "第三章　結果"

    def test_english_and_roman_headings(self):
        book = _book("Chapter 1: Origins", BODY, "CHAPTER II", BODY, "Chapter 3 Methods", BODY)
        assert [c.number for c in find_chapters(book)] == [1, 2, 3]

    def test_select_range(self):
        book = _book("第一章 甲", "甲" * 600, "第二章 乙", "乙" * 600, "第三章 丙", "丙" * 600)
        text, _ = select_chapters(book, 2, 2)
        assert text.startswith("第二章 乙") and "丙" not in text
        text, _ = select_chapters(book, 2, 3)
        assert "乙" in text and "丙" in text and "甲" not in text

    def test_missing_chapter_lists_found(self):
        book = _book("第一章 甲", "甲" * 600)
        with pytest.raises(ValueError, match="偵測到的章號：1"):
            select_chapters(book, 4, 4)

    def test_strip_running_heads(self):
        book = _book(
            "第一章 緒論", "正文一", "心智與世界 12", "正文二", "13 心智與世界",
            "正文三", "心智與世界 14", "15", "正文四",
        )
        cleaned = strip_running_heads(book)
        assert "心智與世界" not in cleaned
        assert "\n15\n" not in cleaned
        assert "第一章 緒論" in cleaned and "正文四" in cleaned

    def test_repeated_chapter_heading_kept(self):
        # 書眉與章標題同字時不刪章標題
        book = _book("第一章 緒論", "a", "第一章 緒論", "b", "第一章 緒論", "c")
        assert strip_running_heads(book).count("第一章 緒論") == 3


def _summerfield_like_book():
    """模擬 dev-local 回報的專書：目錄與正文都用「N. Title」，第 5 章內文有一列以
    「Chapter 2.」開頭的交叉引用（斷行後剛好落在行首）"""
    body = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 30  # ~1700 字元
    toc = ["Contents", "1. Turing’s question", "2. The nature of intelligence",
           "3. The language of thought", "4. The structure of knowledge", "5. The problem of abstraction"]
    parts = toc + ["Preface", body]
    titles = toc[1:]
    for i, title in enumerate(titles, start=1):
        parts += [title, f"chapter-{i}-start", body]
        if i == 5:
            parts += ["Chapter 2. Recall his theory that the monkey has to ‘grasp the whole layout’ to",
                      "solve the problem.", body]
    parts += ["Bibliography", body]
    return "\n".join(parts)


class TestChapterRegression:
    """dev-local 回報：--chapter 2 在「N. Title」專書上靜默選到第 5 章交叉引用之後的全書內容"""

    def test_numbered_titles_detected_and_cross_reference_ignored(self):
        chapters = find_chapters(_summerfield_like_book())
        assert [c.number for c in chapters] == [1, 2, 3, 4, 5]
        assert chapters[1].heading == "2. The nature of intelligence"

    def test_selects_real_chapter_two(self):
        text, _ = select_chapters(_summerfield_like_book(), 2, 2)
        assert text.startswith("2. The nature of intelligence")
        assert "chapter-2-start" in text and "chapter-3-start" not in text

    def test_cross_reference_line_is_not_a_heading(self):
        from claude_lit.extractors.chapters import _heading_number

        line = "Chapter 2. Recall his theory that the monkey has to ‘grasp the whole layout’ to"
        assert _heading_number(line) is None
        assert _heading_number("Chapter 2. The Nature of Intelligence") == ("en", 2)
        assert _heading_number("Chapter 7") == ("en", 7)

    def test_numbered_list_items_are_not_headings(self):
        from claude_lit.extractors.chapters import _heading_number

        assert _heading_number("1. Participants were recruited online.") is None   # 句號結尾
        assert _heading_number("2. we then computed the mean") is None             # 小寫開頭
        assert _heading_number("3. The results suggest that, as expected, the") is None  # 未完句

    def test_explicit_chapter_style_wins_over_numbered_sections(self):
        body = "x" * 700
        book = "\n".join([
            "Chapter 1 Origins", "1. Introduction", body, "2. Methods", body,
            "Chapter 2 Growth", "1. Introduction", body, "2. Results", body,
        ])
        chapters = find_chapters(book)
        assert [(c.number, c.heading) for c in chapters] == [(1, "Chapter 1 Origins"), (2, "Chapter 2 Growth")]

    def test_single_detected_heading_raises(self):
        book = "Preface\n" + "x" * 3000 + "\nChapter 2. The Nature of Mind\n" + "y" * 3000
        with pytest.raises(ValueError, match="只偵測到 1 個章標題"):
            select_chapters(book, 2, 2)

    def test_gap_after_range_raises(self):
        body = "z" * 700
        book = _book("第一章 甲", body, "第二章 乙", body, "第四章 丁", body)  # 第三章標題沒抓到
        with pytest.raises(ValueError, match="不連續"):
            select_chapters(book, 2, 2)

    def test_oversized_selection_raises(self):
        book = _book("第一章 甲", "甲" * 600, "第二章 乙", "乙" * 600, "第三章 丙", "丙" * 600,
                     "第四章 丁", "丁" * 600, "第五章 戊", "戊" * 9000)  # 末章含大量書末內容
        with pytest.raises(ValueError, match="佔全文"):
            select_chapters(book, 5, 5)
        text, _ = select_chapters(book, 2, 2)  # 正常章節不受影響
        assert text.startswith("第二章 乙")


def _pdf_with_outline(path, page_count, outline):
    """以 PyPDF2 建立空白頁 PDF 並加書籤；outline：[(title, page, [children...])]"""
    import PyPDF2

    writer = PyPDF2.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)

    def add(items, parent=None):
        for title, page, children in items:
            node = writer.add_outline_item(title, page, parent=parent)
            add(children, node)

    add(outline)
    with open(path, "wb") as f:
        writer.write(f)
    return path


class TestPdfOutline:
    OUTLINE = [
        ("Title Page", 0, []), ("Contents", 1, []),
        ("Part I. Foundations", 2, [
            ("1. Turing’s question", 2, []),
            ("2. The nature of intelligence", 5, []),
        ]),
        ("Part II. Mechanisms", 9, [
            ("3. The language of thought", 9, []),
        ]),
        ("Bibliography", 14, []), ("Index", 17, []),
    ]

    def test_chapters_and_page_ranges(self, tmp_path):
        from claude_lit.extractors.chapters import pdf_outline_chapters

        pdf = _pdf_with_outline(tmp_path / "book.pdf", 20, self.OUTLINE)
        chapters = pdf_outline_chapters(pdf)
        assert [(c.number, c.start_page, c.end_page) for c in chapters] == [
            (1, 2, 5), (2, 5, 9), (3, 9, 14),  # 第 3 章止於 Bibliography，不含書末
        ]

    # dev-local 回報：Summerfield (2023) 的書籤是「N. 章 → N.M 節」，「2.1」被當成章號 2 →
    # 章號重複 → 書籤路徑整個放棄、退回文字判斷
    SECTIONED = [
        ("Title Page", 0, []), ("Contents", 1, []),
        ("1. Turing’s question", 3, [("1.1 Machines", 3, []), ("1.2 Minds", 6, [])]),
        ("2. The nature of intelligence", 10, [
            ("2.1 The polymathic principle", 10, []), ("2.2 Lab smarts and street smarts", 13, []),
        ]),
        ("3. The language of thought", 18, [("3.1 Symbols", 18, [])]),
        ("References", 25, []), ("Index", 28, []),
    ]

    def test_sections_are_not_chapters(self, tmp_path):
        from claude_lit.extractors.chapters import _outline_number, pdf_outline_chapters

        assert _outline_number("2.1 The polymathic principle") is None
        assert _outline_number("2. The nature of intelligence") == 2
        assert _outline_number("Chapter 2.1 Overview") is None
        pdf = _pdf_with_outline(tmp_path / "book.pdf", 30, self.SECTIONED)
        chapters = pdf_outline_chapters(pdf)
        assert [(c.number, c.start_page, c.end_page) for c in chapters] == [
            (1, 3, 10), (2, 10, 18), (3, 18, 25),  # 第 3 章止於 References
        ]

    def test_sectioned_outline_used_by_source(self, tmp_path, monkeypatch):
        from claude_lit.api import sources as sources_mod
        from claude_lit.api.errors import SourceNotFoundError
        from claude_lit.extractors.pdf_extractor import PDFExtractor

        pdf = _pdf_with_outline(tmp_path / "book.pdf", 30, self.SECTIONED)
        calls = []
        monkeypatch.setattr(PDFExtractor, "extract_page_range",
                            lambda self, path, start, end: calls.append((start, end)) or "內容")
        monkeypatch.setattr(PDFExtractor, "extract", lambda self, path: pytest.fail("不應退回全書抽取"))
        sources_mod.resolve_source(pdf=pdf, media_type="monograph", chapter="2", max_chars=10000)
        sources_mod.resolve_source(pdf=pdf, media_type="monograph", chapter="2-3", max_chars=10000)
        assert calls == [(10, 18), (10, 25)]
        with pytest.raises(SourceNotFoundError, match="書籤章號：1, 2, 3"):
            sources_mod.resolve_source(pdf=pdf, media_type="monograph", chapter="9", max_chars=10000)

    def test_parts_renumbering_within_level_returns_empty(self, tmp_path):
        from claude_lit.extractors.chapters import pdf_outline_chapters

        renumbered = [
            ("Part I", 0, [("1. Alpha", 0, []), ("2. Beta", 3, [])]),
            ("Part II", 6, [("1. Gamma", 6, []), ("2. Delta", 9, [])]),
        ]
        pdf = _pdf_with_outline(tmp_path / "parts.pdf", 12, renumbered)
        assert pdf_outline_chapters(pdf) == []  # 章號無法對應，改走文字判斷

    def test_no_numbered_outline_returns_empty(self, tmp_path):
        from claude_lit.extractors.chapters import pdf_outline_chapters

        pdf = _pdf_with_outline(tmp_path / "paper.pdf", 4, [("Introduction", 0, []), ("Methods", 2, [])])
        assert pdf_outline_chapters(pdf) == []

    def test_source_uses_outline_pages(self, tmp_path, monkeypatch):
        from claude_lit.api import sources as sources_mod
        from claude_lit.extractors.pdf_extractor import PDFExtractor

        pdf = _pdf_with_outline(tmp_path / "Summerfield-2023.pdf", 20, self.OUTLINE)
        calls = []
        monkeypatch.setattr(
            PDFExtractor, "extract_page_range",
            lambda self, path, start, end: calls.append((start, end)) or f"pages {start}-{end} 的內容",
        )
        monkeypatch.setattr(PDFExtractor, "extract", lambda self, path: pytest.fail("不應抽取全書"))
        src = sources_mod.resolve_source(pdf=pdf, media_type="monograph", chapter="2", max_chars=100000)
        assert calls == [(5, 9)]
        assert src.content == "pages 5-9 的內容"
        assert src.topic == "Summerfield-2023：2. The nature of intelligence"
        assert any("書籤" in w and "pp. 6–9" in w for w in src.warnings)

    def test_outline_missing_chapter_raises(self, tmp_path):
        from claude_lit.api import sources as sources_mod
        from claude_lit.api.errors import SourceNotFoundError

        pdf = _pdf_with_outline(tmp_path / "book.pdf", 20, self.OUTLINE)
        with pytest.raises(SourceNotFoundError, match="書籤章號：1, 2, 3"):
            sources_mod.resolve_source(pdf=pdf, media_type="monograph", chapter="7", max_chars=100000)
