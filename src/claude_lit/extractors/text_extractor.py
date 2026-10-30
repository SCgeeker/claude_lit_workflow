# -*- coding: utf-8 -*-
"""
文字來源提取器：.txt / .md / .srt / .vtt / .epub

逐字稿前處理（解析字幕、移除填充詞、合併講者段落、插入時間標記）在此完成，
並產出 timeline（字元位置 → 秒數）供 grounding sidecar 把 char_offset 回映成時間戳。
送進 prompt 與送進 grounding gate 的必須是**同一份**前處理後文字。
"""

import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
from urllib.parse import unquote
from xml.etree import ElementTree

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".srt", ".vtt", ".epub"}
SUBTITLE_SUFFIXES = {".srt", ".vtt"}

# 段落合併上限：超過即換段（避免整集 podcast 擠成一段）
_MAX_PARAGRAPH_CHARS = 500


class Cue(NamedTuple):
    """單一字幕片段"""

    start: float  # 秒
    text: str
    speaker: Optional[str] = None


Timeline = List[Tuple[int, float]]  # [(字元位置, 秒數)]，依位置遞增


# ── 時間碼 ───────────────────────────────────────────────────────────────────

_TIMECODE = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"
_CUE_TIMING = re.compile(rf"^\s*{_TIMECODE}\s*-->\s*{_TIMECODE}")
_LINE_TIMESTAMP = re.compile(rf"^\s*[\[(]?{_TIMECODE}[\])]?(?:\s+(.*?))?\s*$")
# Transistor 等平台：「[講者] (0:20 - 0:29)」講者標籤後接時間範圍，內容在下一列
_SPEAKER_RANGE = re.compile(
    rf"^\s*\[([^\]\d][^\]]{{0,39}})\]\s*\(\s*{_TIMECODE}\s*[-–]\s*{_TIMECODE}\s*\)\s*(.*?)\s*$"
)


def _to_seconds(h: Optional[str], m: str, s: str, frac: Optional[str]) -> float:
    seconds = int(h or 0) * 3600 + int(m) * 60 + int(s)
    if frac:
        seconds += int(frac.ljust(3, "0")) / 1000
    return float(seconds)


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def timestamp_at(timeline: Optional[Timeline], offset: int) -> Optional[str]:
    """回傳涵蓋 offset 的字幕片段起始時間（hh:mm:ss）；無 timeline 回傳 None。"""
    if not timeline:
        return None
    current = None
    for pos, seconds in timeline:
        if pos > offset:
            break
        current = seconds
    if current is None:
        current = timeline[0][1]
    return format_timestamp(current)


# ── 講者標籤 ─────────────────────────────────────────────────────────────────

_VTT_VOICE = re.compile(r"<v(?:\.[^\s>]+)?\s+([^>]+)>")
_TAGS = re.compile(r"<[^>]+>")
# 「主持人：」「Speaker 1:」；標籤內不得有句讀，英文最多 3 個詞
_SPEAKER_PREFIX = re.compile(r"^\s*([^\s:：，。,.!?！？][^:：，。,.!?！？]{0,19})[:：]\s*(.+)$")


def _split_speaker(text: str) -> Tuple[Optional[str], str]:
    m = _SPEAKER_PREFIX.match(text)
    if not m:
        return None, text
    label = m.group(1).strip()
    if label.isascii() and len(label.split()) > 3:
        return None, text
    return label, m.group(2).strip()


def _clean_cue_text(raw: str) -> Tuple[Optional[str], str]:
    speaker = None
    voice = _VTT_VOICE.search(raw)
    if voice:
        speaker = voice.group(1).strip()
    text = " ".join(_TAGS.sub("", raw).split())
    if speaker is None:
        speaker, text = _split_speaker(text)
    return speaker, text


# ── 字幕解析 ─────────────────────────────────────────────────────────────────


def parse_subtitles(raw: str) -> List[Cue]:
    """解析 SRT / WebVTT：丟棄序號、時間碼列、WEBVTT 標頭與 NOTE/STYLE 區塊。"""
    cues: List[Cue] = []
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿"))
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip()]
        timing_idx = next((i for i, line in enumerate(lines) if _CUE_TIMING.match(line)), None)
        if timing_idx is None:
            continue  # WEBVTT 標頭、NOTE、STYLE 或空區塊
        m = _CUE_TIMING.match(lines[timing_idx])
        start = _to_seconds(*m.groups()[:4])
        speaker, text = _clean_cue_text(" ".join(lines[timing_idx + 1:]))
        if text:
            cues.append(Cue(start, text, speaker))
    return cues


def parse_timestamped_text(raw: str) -> Optional[List[Cue]]:
    """解析「時間碼開頭」的純文字逐字稿（YouTube / podcast 平台複製格式）。

    支援時間碼與文字同列（`[00:12:30] 文字`）、時間碼獨立成列且文字在下一列，
    以及講者標籤加時間範圍（`[Kristin] (0:20 - 0:29)`，Transistor 格式）。
    少於 2 個時間碼時視為一般文字，回傳 None。
    """
    cues: List[Cue] = []
    pending: Optional[float] = None
    pending_speaker: Optional[str] = None
    buffer: List[str] = []

    def flush():
        if pending is not None and buffer:
            speaker, text = _clean_cue_text(" ".join(buffer))
            if text:
                cues.append(Cue(pending, text, pending_speaker or speaker))

    stamps = 0
    for line in raw.replace("\r\n", "\n").split("\n"):
        ranged = _SPEAKER_RANGE.match(line)
        if ranged:
            flush()
            stamps += 1
            pending = _to_seconds(*ranged.groups()[1:5])
            pending_speaker = ranged.group(1).strip()
            buffer = [ranged.group(10)] if ranged.group(10) else []
            continue
        m = _LINE_TIMESTAMP.match(line)
        if m:
            flush()
            stamps += 1
            pending = _to_seconds(*m.groups()[:4])
            pending_speaker = None
            buffer = [m.group(5)] if m.group(5) else []
        elif line.strip():
            buffer.append(line.strip())
    flush()
    return cues if stamps >= 2 else None


# ── 填充詞 ───────────────────────────────────────────────────────────────────

# 只移除獨立出現的填充詞（句首、標點或空白之後）；「就是」「然後」常有實義，不移除
_ZH_FILLERS = re.compile(r"(?:^|(?<=[\s，。！？、：,.!?:]))(?:嗯|呃|欸|唔)+[，,、。…\s]*")
_EN_FILLERS = re.compile(r"(?i)(?<![\w'])(?:u+m+|u+h+|e+r+m+|h+m+)(?![\w'])[,.]?\s*")


def strip_fillers(text: str) -> str:
    text = _ZH_FILLERS.sub("", text)
    text = _EN_FILLERS.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


# ── 逐字稿組裝 ───────────────────────────────────────────────────────────────


_CJK_CHAR = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")


def _join_separator(previous: str, following: str) -> str:
    """片段接合：任一側是中日文字或全形標點時不加空白（「預測，而不是」），否則加一個空白"""
    if _CJK_CHAR.match(previous[-1]) or _CJK_CHAR.match(following[0]):
        return ""
    return " "


def build_transcript(
    cues: List[Cue],
    *,
    remove_fillers: bool = True,
    merge_turns: bool = True,
    time_markers: bool = True,
) -> Tuple[str, Timeline]:
    """字幕片段 → 段落化文字 + timeline。

    - merge_turns：同一講者的連續片段併為一段（換講者或超過長度上限才換段）
    - time_markers：每段前插入**獨立成行**的 `[hh:mm:ss]`，避免 LLM 把它抄進核心句
    - timeline 記錄每個片段在最終文字中的起始位置，供 char_offset 回映時間
    """
    paragraphs: List[dict] = []
    for cue in cues:
        text = strip_fillers(cue.text) if remove_fillers else cue.text
        if not text:
            continue
        current = paragraphs[-1] if paragraphs else None
        speaker = cue.speaker or (current["speaker"] if current else None)
        new_paragraph = (
            current is None
            or not merge_turns
            or speaker != current["speaker"]
            or current["length"] >= _MAX_PARAGRAPH_CHARS
        )
        if new_paragraph:
            paragraphs.append({"speaker": speaker, "start": cue.start, "parts": [], "length": 0})
            current = paragraphs[-1]
        current["parts"].append((cue.start, text))
        current["length"] += len(text)

    out: List[str] = []
    timeline: Timeline = []
    pos = 0

    def emit(chunk: str):
        nonlocal pos
        out.append(chunk)
        pos += len(chunk)

    for para in paragraphs:
        if time_markers:
            emit(f"[{format_timestamp(para['start'])}]\n")
        if para["speaker"]:
            sep = ": " if para["speaker"].isascii() else "："
            emit(f"{para['speaker']}{sep}")
        previous = ""
        for start, text in para["parts"]:
            if previous:
                emit(_join_separator(previous, text))
            timeline.append((pos, start))
            emit(text)
            previous = text
        emit("\n\n")
    return "".join(out).rstrip() + "\n", timeline


# ── EPUB ─────────────────────────────────────────────────────────────────────

_BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "section", "article", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "pre", "table",
}


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).split("\n")]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _html_to_text(markup: str) -> str:
    parser = _HTMLText()
    parser.feed(markup)
    return parser.text()


def extract_epub(path: Path) -> Tuple[str, Optional[str]]:
    """依 OPF spine 順序串接各章 XHTML 為純文字；回傳 (text, title)。只用標準庫。"""
    ns = {
        "c": "urn:oasis:names:tc:opendocument:xmlns:container",
        "opf": "http://www.idpf.org/2007/opf",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    with zipfile.ZipFile(path) as zf:
        container = ElementTree.fromstring(zf.read("META-INF/container.xml"))
        rootfile = container.find(".//c:rootfile", ns).get("full-path")
        opf = ElementTree.fromstring(zf.read(rootfile))
        base = posixpath.dirname(rootfile)

        title_el = opf.find(".//dc:title", ns)
        title = title_el.text.strip() if title_el is not None and title_el.text else None
        manifest = {
            item.get("id"): item.get("href")
            for item in opf.findall(".//opf:manifest/opf:item", ns)
        }
        texts = []
        for itemref in opf.findall(".//opf:spine/opf:itemref", ns):
            href = manifest.get(itemref.get("idref"))
            if not href:
                continue
            member = posixpath.normpath(posixpath.join(base, unquote(href)))
            try:
                markup = zf.read(member).decode("utf-8", errors="replace")
            except KeyError:
                continue
            chunk = _html_to_text(markup)
            if chunk:
                texts.append(chunk)
    return "\n\n".join(texts), title


# ── 提取器 ───────────────────────────────────────────────────────────────────

_MD_TITLE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


class TextExtractor:
    """文字來源提取器；回傳與 PDFExtractor.extract() 相容的 dict（另含 timeline）。

    不截斷：章節選取與字數上限統一由 api.sources 處理。
    """

    def extract(
        self,
        path: str,
        *,
        remove_fillers: bool = False,
        merge_turns: bool = False,
        time_markers: bool = False,
    ) -> Dict[str, Any]:
        file_path = Path(path)
        suffix = file_path.suffix.lower()
        if suffix not in TEXT_SUFFIXES:
            raise ValueError(
                f"不支援的文字檔格式：{suffix!r}（支援：{', '.join(sorted(TEXT_SUFFIXES))}）"
            )

        title: Optional[str] = None
        timeline: Optional[Timeline] = None
        source_type = "text"

        if suffix == ".epub":
            text, title = extract_epub(file_path)
        else:
            raw = file_path.read_text(encoding="utf-8-sig", errors="replace")
            cues = parse_subtitles(raw) if suffix in SUBTITLE_SUFFIXES else parse_timestamped_text(raw)
            if cues:
                text, timeline = build_transcript(
                    cues,
                    remove_fillers=remove_fillers,
                    merge_turns=merge_turns,
                    time_markers=time_markers,
                )
                source_type = "transcript"
            else:
                text = strip_fillers(raw) if remove_fillers else raw
                if suffix in (".md", ".markdown"):
                    m = _MD_TITLE.search(raw)
                    title = m.group(1).strip() if m else None

        return {
            "full_text": text,
            "title": title or file_path.stem,
            "char_count": len(text),
            "truncated": False,
            "source_type": source_type,
            "timeline": timeline,
        }
