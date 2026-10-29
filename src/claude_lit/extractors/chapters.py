# -*- coding: utf-8 -*-
"""
長篇來源（教科書、專書）的章節切分

- strip_running_heads：移除重複出現的書眉／頁尾與純頁碼列
- find_chapters：辨識章標題（「第三章 標題」「Chapter 3 Title」），排除目錄與內文交叉引用
- select_chapters：取出指定章節範圍的文字
"""

import re
from collections import Counter
from typing import List, NamedTuple, Tuple

# 書眉判定：同一列（去頭尾頁碼後）出現至少此次數
_RUNNING_HEAD_MIN_REPEATS = 3
_MAX_HEAD_LEN = 80
# 目錄項目之間距離很短；章標題後的內容至少要這麼長才算真正的章開頭
_MIN_CHAPTER_CHARS = 500

_ZH_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}

# 中文：「第三章」後須接空白、標點或行尾（「第三章討論了…」是內文引用）
# 英文：「Chapter 3」後須為行尾、標點或大寫開頭（「Chapter 3 shows…」是內文引用）
_CHAPTER_HEAD = re.compile(
    r"^\s*(?:"
    r"第\s*(?P<zh>[0-9０-９零〇一二兩三四五六七八九十百]+)\s*章(?=$|[\s　:：.．、·—\-])"
    r"|(?:CHAPTER|Chapter)\s+(?P<en>\d+|[IVXLC]+|[ivxlc]+)\b(?=$|\s*[:.\-—]|\s+[A-Z\"“'‘(])"
    r")"
)


class Chapter(NamedTuple):
    number: int
    start: int  # 章標題列在文字中的位置
    heading: str


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
            and not _CHAPTER_HEAD.match(line)
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


def find_chapters(text: str) -> List[Chapter]:
    """找出各章的起點，依位置排序。

    同一章號可能出現在目錄、書眉與正文；取「其後內容夠長」的最早一處
    （目錄項目彼此緊鄰而被排除，書眉出現在正文之後而不會被選到）。
    """
    candidates: List[Tuple[int, int, str]] = []
    pos = 0
    for line in text.split("\n"):
        if len(line.strip()) <= _MAX_HEAD_LEN:
            m = _CHAPTER_HEAD.match(line)
            if m:
                number = _zh_to_int(m.group("zh")) if m.group("zh") else (
                    int(m.group("en")) if m.group("en").isdigit() else _roman_to_int(m.group("en"))
                )
                candidates.append((pos, number, line.strip()))
        pos += len(line) + 1

    by_number: dict = {}
    for i, (start, number, heading) in enumerate(candidates):
        next_start = candidates[i + 1][0] if i + 1 < len(candidates) else len(text)
        if next_start - start >= _MIN_CHAPTER_CHARS:
            by_number.setdefault(number, []).append(Chapter(number, start, heading))

    # 章號須隨位置遞增：每章取「位於前一章之後」的最早一處
    # （目錄最後一項後面常接長篇序言而通過長度門檻，靠這條排除）
    ordered: List[Chapter] = []
    for number in sorted(by_number):
        floor = ordered[-1].start if ordered else -1
        chapter = next((c for c in by_number[number] if c.start > floor), None)
        if chapter:
            ordered.append(chapter)
    return ordered


def select_chapters(text: str, start: int, end: int) -> Tuple[str, List[Chapter]]:
    """取出第 start 至第 end 章的文字；回傳 (文字, 全書偵測到的章節清單)。

    Raises:
        ValueError: 找不到第 start 章（訊息含偵測到的章號）
    """
    chapters = find_chapters(text)
    first = next((c for c in chapters if c.number == start), None)
    if first is None:
        found = ", ".join(str(c.number) for c in chapters) or "無"
        raise ValueError(f"找不到第 {start} 章（偵測到的章號：{found}）")
    after = next((c for c in chapters if c.number > end and c.start > first.start), None)
    return text[first.start:after.start if after else len(text)].strip(), chapters
