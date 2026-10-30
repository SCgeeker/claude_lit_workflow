# -*- coding: utf-8 -*-
"""
長篇來源（教科書、專書）的章節切分

- pdf_outline_chapters：PDF 有書籤（outline）時，依書籤頁碼取章節範圍（最可靠，優先使用）
- strip_running_heads：移除重複出現的書眉／頁尾與純頁碼列
- find_chapters：從文字辨識章標題（「第三章 標題」「Chapter 3 Title」「3. Title」），
  排除目錄、內文交叉引用與編號清單
- select_chapters：取出指定章節範圍的文字；章節邊界不可靠時拋錯，不靜默取到全書結尾
"""

import re
from collections import Counter
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

# 書眉判定：同一列（去頭尾頁碼後）出現至少此次數
_RUNNING_HEAD_MIN_REPEATS = 3
_MAX_HEAD_LEN = 80
# 目錄項目之間距離很短；章標題後的內容至少要這麼長才算真正的章開頭
_MIN_CHAPTER_CHARS = 500
# 章標題的標題部分：字數與詞數上限（超過多半是內文句子）
_MAX_TITLE_CHARS = 60
_MAX_TITLE_WORDS = 10
# 選取比例防呆：單章（或範圍）佔全文超過「預期比例 × 倍數」且超過此下限時視為切錯
_MIN_SUSPICIOUS_SHARE = 0.4
_SHARE_TOLERANCE = 2.5

_ZH_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}

# 句尾常見的功能詞：標題不會以這些詞結尾，內文斷行常會（「…the whole layout’ to」）
_CONTINUATION_WORDS = {
    "a", "an", "the", "to", "of", "and", "or", "in", "on", "at", "for", "with", "by",
    "that", "which", "is", "are", "was", "as", "from", "but", "his", "her", "its", "their",
}

# 中文：「第三章」後須接空白、標點或行尾（「第三章討論了…」是內文引用）
_ZH_HEAD = re.compile(r"^\s*第\s*([0-9０-９零〇一二兩三四五六七八九十百]+)\s*章(?=$|[\s　:：.．、·—\-])(.*)$")
_EN_HEAD = re.compile(r"^\s*(?:CHAPTER|Chapter)\s+(\d+|[IVXLC]+|[ivxlc]+)\b(.*)$")
_NUM_HEAD = re.compile(r"^\s*(\d{1,2})\.\s+(.+)$")


class Chapter(NamedTuple):
    number: int
    start: int  # 章標題列在文字中的位置
    heading: str


class OutlineChapter(NamedTuple):
    number: int
    title: str
    start_page: int  # 0-based，含
    end_page: int    # 0-based，不含


def _zh_to_int(token: str) -> int:
    token = token.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if token.isdigit():
        return int(token)
    total, current = 0, 0
    for ch in token:
        if ch == "百":
            total += (current or 1) * 100
            current = 0
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        else:
            current = _ZH_DIGITS[ch]
    return total + current


def _roman_to_int(token: str) -> int:
    values = [_ROMAN[c] for c in token.lower()]
    total = 0
    for i, v in enumerate(values):
        total += -v if i + 1 < len(values) and v < values[i + 1] else v
    return total


def _looks_like_title(text: str) -> bool:
    """章標題的標題部分：短、大寫或非拉丁字開頭、不像一句沒寫完的內文"""
    text = text.strip()
    if not text or len(text) > _MAX_TITLE_CHARS:
        return False
    words = text.split()
    if len(words) > _MAX_TITLE_WORDS:
        return False
    first = text.lstrip("\"“'‘(")[:1]
    if first.isalpha() and first.isascii() and not first.isupper():
        return False
    if text[-1] in ",;" or re.search(r"[.!?]\s+\S", text):  # 句中斷句 → 是句子不是標題
        return False
    return words[-1].lower().strip("\"”'’") not in _CONTINUATION_WORDS


def _heading_number(line: str) -> Optional[Tuple[str, int]]:
    """判斷一列是否為章標題；是則回傳 (樣式, 章號)。樣式：zh / en / num"""
    if len(line.strip()) > _MAX_HEAD_LEN:
        return None
    m = _ZH_HEAD.match(line)
    if m:
        return "zh", _zh_to_int(m.group(1))
    m = _EN_HEAD.match(line)
    if m:
        rest = m.group(2).strip()
        rest = re.sub(r"^[:.\-—]\s*", "", rest)
        if not rest or _looks_like_title(rest):
            token = m.group(1)
            return "en", int(token) if token.isdigit() else _roman_to_int(token)
        return None
    m = _NUM_HEAD.match(line)
    if m and _looks_like_title(m.group(2)) and not m.group(2).rstrip().endswith("."):
        return "num", int(m.group(1))
    return None


def _strip_page_numbers(line: str) -> str:
    return re.sub(r"^\s*\d+\s+|\s+\d+\s*$", "", line).strip()


def strip_running_heads(text: str) -> str:
    """移除重複的書眉／頁尾（去頭尾頁碼後完全相同、出現 ≥3 次的短列）與純頁碼列。

    章標題列不移除（即使重複出現），避免書眉與章標題同字時連標題一起刪掉。
    """
    lines = text.split("\n")
    keys = [_strip_page_numbers(line) for line in lines]
    counts = Counter(k for k in keys if k and len(k) <= _MAX_HEAD_LEN)
    kept = []
    for line, key in zip(lines, keys):
        if re.fullmatch(r"\s*\d{1,4}\s*", line):
            continue
        if (
            key
            and counts.get(key, 0) >= _RUNNING_HEAD_MIN_REPEATS
            and _heading_number(line) is None
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


def _order_chapters(candidates: List[Tuple[int, int, str]], text_len: int) -> List[Chapter]:
    """同一章號可能出現在目錄、書眉與正文；取「其後內容夠長、且位於前一章之後」的最早一處"""
    by_number: dict = {}
    for i, (start, number, heading) in enumerate(candidates):
        next_start = candidates[i + 1][0] if i + 1 < len(candidates) else text_len
        if next_start - start >= _MIN_CHAPTER_CHARS:
            by_number.setdefault(number, []).append(Chapter(number, start, heading))

    ordered: List[Chapter] = []
    for number in sorted(by_number):
        floor = ordered[-1].start if ordered else -1
        chapter = next((c for c in by_number[number] if c.start > floor), None)
        if chapter:
            ordered.append(chapter)
    return ordered


def find_chapters(text: str) -> List[Chapter]:
    """找出各章的起點，依位置排序。

    明示「章」的樣式（第 X 章、Chapter N）優先；偵測不到至少兩章時才退回「N. 標題」樣式
    （此樣式易與節次、編號清單混淆，只作為後備）。
    """
    candidates: dict = {"zh": [], "en": [], "num": []}
    pos = 0
    for line in text.split("\n"):
        found = _heading_number(line)
        if found:
            style, number = found
            candidates[style].append((pos, number, line.strip()))
        pos += len(line) + 1

    explicit = sorted(candidates["zh"] + candidates["en"])
    chapters = _order_chapters(explicit, len(text))
    if len(chapters) >= 2:
        return chapters
    numbered = _order_chapters(candidates["num"], len(text))
    return numbered if len(numbered) >= 2 else chapters


def select_chapters(text: str, start: int, end: int) -> Tuple[str, List[Chapter]]:
    """取出第 start 至第 end 章的文字；回傳 (文字, 全書偵測到的章節清單)。

    Raises:
        ValueError: 章節邊界不可靠——找不到第 start 章、只偵測到一章、範圍之後的章號不連續，
            或選取量佔全文比例異常（多半是把內文交叉引用誤當章標題）。訊息含偵測到的章號。
    """
    chapters = find_chapters(text)
    found = ", ".join(str(c.number) for c in chapters) or "無"
    if len(chapters) < 2:
        raise ValueError(f"只偵測到 {len(chapters)} 個章標題，無法可靠切章（偵測到的章號：{found}）")
    first = next((c for c in chapters if c.number == start), None)
    if first is None:
        raise ValueError(f"找不到第 {start} 章（偵測到的章號：{found}）")

    later = [c for c in chapters if c.number > end and c.start > first.start]
    if later and later[0].number != end + 1:
        raise ValueError(
            f"第 {end} 章之後的章號不連續（下一個偵測到的是第 {later[0].number} 章），"
            f"章節結尾無法確定（偵測到的章號：{found}）"
        )
    selected = text[first.start:later[0].start if later else len(text)].strip()

    share = len(selected) / max(len(text), 1)
    expected = (end - start + 1) / len(chapters)
    if share > max(_MIN_SUSPICIOUS_SHARE, expected * _SHARE_TOLERANCE):
        raise ValueError(
            f"選取的章節佔全文 {share:.0%}，遠高於預期，可能把內文引用誤當章標題"
            f"（偵測到的章號：{found}）"
        )
    return selected, chapters


# ── PDF 書籤 ─────────────────────────────────────────────────────────────────

_OUTLINE_TITLE = re.compile(
    r"^\s*(?:"
    r"第\s*(?P<zh>[0-9０-９零〇一二兩三四五六七八九十百]+)\s*章"
    r"|(?:chapter\s+)(?P<word>\d+|[ivxlc]+)\b"
    r"|(?P<num>\d{1,2})(?:[.:]|\s)\s*\S"
    r")",
    re.IGNORECASE,
)


def _outline_number(title: str) -> Optional[int]:
    m = _OUTLINE_TITLE.match(title or "")
    if not m:
        return None
    if m.group("zh"):
        return _zh_to_int(m.group("zh"))
    if m.group("word"):
        token = m.group("word")
        return int(token) if token.isdigit() else _roman_to_int(token)
    return int(m.group("num"))


def pdf_outline_chapters(pdf_path: Path, max_depth: int = 2) -> List[OutlineChapter]:
    """讀取 PDF 書籤中帶章號的項目（最多兩層，容納「Part → Chapter」結構）與其頁碼範圍。

    章的結尾頁 = 書籤順序中下一個同層或更上層項目的起始頁（如下一章、Bibliography、Index）。
    帶章號的書籤少於兩個、或讀取失敗時回傳空清單（呼叫端改用文字判斷）。
    """
    try:
        import PyPDF2

        reader = PyPDF2.PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        entries: List[Tuple[int, str, int]] = []  # (depth, title, page)

        def walk(items, depth):
            for item in items:
                if isinstance(item, list):
                    if depth < max_depth:
                        walk(item, depth + 1)
                    continue
                try:
                    page = reader.get_destination_page_number(item)
                except Exception:
                    continue
                entries.append((depth, str(item.title or "").strip(), page))

        walk(reader.outline, 1)
    except Exception:
        return []

    chapters: List[OutlineChapter] = []
    for i, (depth, title, page) in enumerate(entries):
        number = _outline_number(title)
        if number is None:
            continue
        end = next((p for d, _, p in entries[i + 1:] if d <= depth and p > page), page_count)
        chapters.append(OutlineChapter(number, title, page, end))

    numbers = [c.number for c in chapters]
    if len(chapters) < 2 or len(set(numbers)) != len(numbers):
        return []  # 章號重複多半是各部（Part）各自重編，或書籤不是章節目錄
    return chapters


def select_outline_chapters(
    chapters: List[OutlineChapter], start: int, end: int
) -> Optional[Tuple[int, int, str]]:
    """依書籤取第 start–end 章的頁碼範圍 (起始頁, 結束頁, 標題)；找不到起始章回傳 None"""
    first = next((c for c in chapters if c.number == start), None)
    last = next((c for c in chapters if c.number == end), None)
    if first is None or last is None or last.start_page < first.start_page:
        return None
    return first.start_page, last.end_page, first.title
