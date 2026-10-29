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
