# -*- coding: utf-8 -*-
"""Card 層 grounding 驗證：把 LLM 的「核心」定位回原文，判 verdict 並擷刻 raw span。

與 checkers/quality_checker.py 平行，但作用在 **card 層**（core_summary）而非論文
metadata。`normalize()` 為本 repo 對 grounding 正規化的**權威定義**；vault 端
quote_check.py 的 normalize 須向此逐字收斂（跨 repo 無法 import，見 memory
grounding-normalize-cross-repo）。

verdict 分三種處置（disposition）：
- keep       ：EXACT / EXACT_NOSPACE / DRIFTED_MINOR —— 正常輸出，擷刻 raw span
- quarantine ：CJK_UNVERIFIABLE —— 含 Han 字但定位不到，隔離待審（不 erase）
- erase      ：DRIFTED_MAJOR / NOT_FOUND / NO_DESC —— 不落地
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, NamedTuple, Optional, Tuple

# --- verdict 常數 ---
EXACT = "EXACT"
EXACT_NOSPACE = "EXACT_NOSPACE"
DRIFTED_MINOR = "DRIFTED_MINOR"
DRIFTED_MAJOR = "DRIFTED_MAJOR"
NOT_FOUND = "NOT_FOUND"
NO_DESC = "NO_DESC"
CJK_UNVERIFIABLE = "CJK_UNVERIFIABLE"

# --- 門檻（可調參數）---
MINOR_THRESHOLD = 0.85
MAJOR_THRESHOLD = 0.60

_PLACEHOLDER_PAT = re.compile(
    r"原文未明確|未明確說明|無法(從原文)?確定|placeholder|待補|TODO", re.IGNORECASE
)
_CJK_PAT = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_SQUASH_PAT = re.compile(r"[\s\-‐-―−]+")
_SQUASH_CHAR = re.compile(r"[\s\-‐-―−]")


class Grounding(NamedTuple):
    """單張卡片的 grounding 判定結果。"""

    verdict: str
    coverage: float
    matched_span: Optional[str]          # 原文 raw span（keep 類才有）
    char_offset: Optional[Tuple[int, int]]  # raw source 的 [start, end)
    disposition: str                     # "keep" | "quarantine" | "erase"


def _normalize_indexed(raw: str) -> Tuple[str, List[int]]:
    """正規化並回傳 (norm, idx)，idx[k] 為 norm[k] 對映的 raw 起始索引。

    只吸收不影響 grounding 的雜訊，且與 `normalize()` 共用同一實作（單一真相）：
    - 換行連字接合（`compre-\\nhender` → `comprehender`）
    - 空白塌陷（連續空白 → 單一空格）
    - 彎引號 → 直引號
    - NFKC（全形 → 半形等）
    """
    norm_chars: List[str] = []
    idx: List[int] = []
    i = 0
    n = len(raw or "")
    prev_space = False

    while i < n:
        c = raw[i]

        # 換行連字：'-' 後接 (空白* 換行 空白*) → 整段吞掉（接合斷字）
        if c == "-":
            j = i + 1
            while j < n and raw[j] in " \t":
                j += 1
            if j < n and raw[j] in "\r\n":
                while j < n and raw[j] in " \t\r\n":
                    j += 1
                i = j
                prev_space = False
                continue

        # 空白塌陷（前導空白不輸出）
        if c.isspace():
            if not prev_space and norm_chars:
                norm_chars.append(" ")
                idx.append(i)
                prev_space = True
            i += 1
            continue
        prev_space = False

        # 彎引號正規化
        if c in "‘’":
            norm_chars.append("'")
            idx.append(i)
            i += 1
            continue
        if c in "“”":
            norm_chars.append('"')
            idx.append(i)
            i += 1
            continue

        # NFKC（逐字；展開成多字時全部映到同一 raw index）
        nf = unicodedata.normalize("NFKC", c)
        for ch in nf:
            norm_chars.append(ch)
            idx.append(i)
        i += 1

    # 去尾端空白並同步 idx
    end = len(norm_chars)
    while end > 0 and norm_chars[end - 1] == " ":
        end -= 1
    return "".join(norm_chars[:end]), idx[:end]


def normalize(text: str) -> str:
    """grounding 正規化的權威定義（見 _normalize_indexed）。"""
    return _normalize_indexed(text or "")[0]


def _squash(text: str) -> str:
    """移除空白與各式連字號，供「僅差空格/連字」的比對。"""
    return _SQUASH_PAT.sub("", text)


def _raw_span(raw: str, idx: List[int], ns: int, ne: int) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    """把 norm 空間的 [ns, ne) 映回 raw span。"""
    if ns is None or ne is None or not idx:
        return None, None
    start = idx[ns]
    end = idx[ne] if ne < len(idx) else len(raw)
    return raw[start:end], (start, end)


def _find_nospace_span(sq: str, sn: str) -> Tuple[Optional[int], Optional[int]]:
    """在 sn 中找「去空白/連字後等於 sq」的最短區段，回傳 norm 空間的 (start, end)。

    用於 EXACT_NOSPACE：精準把去雜訊的命中位置映回 norm offset（再由呼叫端映回 raw），
    比 _best_window 的等長滑窗可靠。
    """
    kept_chars: List[str] = []
    kept_idx: List[int] = []
    for k, ch in enumerate(sn):
        if not _SQUASH_CHAR.match(ch):
            kept_chars.append(ch)
            kept_idx.append(k)
    squashed = "".join(kept_chars)
    pos = squashed.find(sq)
    if pos < 0:
        return None, None
    start = kept_idx[pos]
    end = kept_idx[pos + len(sq) - 1] + 1
    return start, end


def _best_window(qn: str, sn: str) -> Tuple[float, Optional[int], Optional[int]]:
    """在 sn 中找與 qn 最相似的等長窗，回傳 (ratio, start, end)（norm 空間）。

    以 qn 前段當 probe 蒐集候選起點，避免對整段來源做 O(n*m) 全掃；
    probe 找不到時退回粗網格。
    """
    L = len(qn)
    if L == 0 or not sn:
        return 0.0, None, None

    probe = qn[: min(24, L)]
    starts = [m.start() for m in re.finditer(re.escape(probe), sn)]
    if not starts:
        step = max(1, L // 4)
        starts = list(range(0, max(1, len(sn) - L + 1), step))

    best = (0.0, None, None)
    for s in starts:
        window = sn[s : s + L]
        ratio = SequenceMatcher(None, qn, window).ratio()
        if ratio > best[0]:
            best = (ratio, s, s + L)
    return best


def ground_card(core_summary: Optional[str], source_content: Optional[str]) -> Grounding:
    """判定單張卡片核心相對原文的 grounding。"""
    core = (core_summary or "").strip()

    # NO_DESC：空 / 佔位符 / 尾綴省略號（接 P9）
    if (
        not core
        or core.endswith("...")
        or core.endswith("…")
        or _PLACEHOLDER_PAT.search(core)
    ):
        return Grounding(NO_DESC, 0.0, None, None, "erase")

    qn = normalize(core)
    if not qn:
        return Grounding(NO_DESC, 0.0, None, None, "erase")

    sn, sidx = _normalize_indexed(source_content or "")
    has_cjk = bool(_CJK_PAT.search(core))

    if not sn:
        # 無可比對來源：CJK 走隔離，其餘視為 NOT_FOUND
        if has_cjk:
            return Grounding(CJK_UNVERIFIABLE, 0.0, None, None, "quarantine")
        return Grounding(NOT_FOUND, 0.0, None, None, "erase")

    # EXACT：normalize 後為子字串
    pos = sn.find(qn)
    if pos >= 0:
        span, off = _raw_span(source_content, sidx, pos, pos + len(qn))
        return Grounding(EXACT, 1.0, span, off, "keep")

    # EXACT_NOSPACE：僅差空白/連字（精準映回命中位置）
    sq = _squash(qn)
    if sq:
        ns, ne = _find_nospace_span(sq, sn)
        if ns is not None:
            span, off = _raw_span(source_content, sidx, ns, ne)
            return Grounding(EXACT_NOSPACE, 1.0, span, off, "keep")

    # 滑窗最佳比 → DRIFTED / CJK / NOT_FOUND
    ratio, ns, ne = _best_window(qn, sn)
    if ratio >= MINOR_THRESHOLD:
        span, off = _raw_span(source_content, sidx, ns, ne)
        return Grounding(DRIFTED_MINOR, ratio, span, off, "keep")

    # 含 Han 字但定位不到 → 隔離待審（在 erase 判定之前）
    if has_cjk:
        return Grounding(CJK_UNVERIFIABLE, ratio, None, None, "quarantine")

    if ratio >= MAJOR_THRESHOLD:
        return Grounding(DRIFTED_MAJOR, ratio, None, None, "erase")
    return Grounding(NOT_FOUND, ratio, None, None, "erase")


def same_text_up_to_spacing(a: str, b: str) -> bool:
    """兩字串是否僅差 normalize 級雜訊（空白/連字/引號/NFKC）。

    供 api 層決定「安全自動修正」：僅在此為真時才以 raw span 覆寫 core_summary。
    """
    return _squash(normalize(a)) == _squash(normalize(b))
