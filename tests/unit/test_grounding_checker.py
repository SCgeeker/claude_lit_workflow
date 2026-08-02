# -*- coding: utf-8 -*-
"""grounding_checker 純函式測試（P3 / add-grounding-gate Phase 1）

normalize：吸收不影響 grounding 的雜訊（換行連字、空白塌陷、彎引號、NFKC），
不動用字/語序。ground_card：把「核心」定位回原文，判 verdict、擷刻 raw span、
給 disposition（keep / quarantine / erase）。
"""

from claude_lit.checkers import grounding_checker as gc


class TestNormalize:
    def test_collapses_whitespace(self):
        assert gc.normalize("foo   bar\n\tbaz") == "foo bar baz"

    def test_joins_line_wrap_hyphen(self):
        # 換行連字：compre-\nhender → comprehender
        assert gc.normalize("rational compre-\nhender here") == "rational comprehender here"

    def test_curly_quotes_to_straight(self):
        assert gc.normalize("“quoted” and ‘q’") == '"quoted" and \'q\''

    def test_nfkc_fullwidth(self):
        # 全形字母經 NFKC → 半形
        assert gc.normalize("ＡＢＣ") == "ABC"

    def test_preserves_wording_and_order(self):
        assert gc.normalize("The Quick Brown Fox") == "The Quick Brown Fox"


class TestGroundCardKeep:
    def test_exact_substring(self):
        src = "Intro. AI surrogates are models that simulate humans. End."
        g = gc.ground_card("AI surrogates are models that simulate humans", src)
        assert g.verdict == gc.EXACT
        assert g.disposition == "keep"
        assert "AI surrogates are models" in g.matched_span

    def test_exact_nospace_source_space_collapse(self):
        # P4：原文 text-layer 空格塌陷（comprehensionasinference），核心有正常空格
        src = "Meaning is comprehensionasinference in this account."
        g = gc.ground_card("comprehension as inference", src)
        assert g.verdict == gc.EXACT_NOSPACE
        assert g.disposition == "keep"

    def test_line_wrap_hyphen_recovers_raw_span(self):
        # 核心帶連字但無換行；原文為換行連字 → 定位成功、raw span 為原文樣貌
        src = "We describe the rational compre-\nhender model in detail."
        g = gc.ground_card("rational compre-hender", src)
        assert g.disposition == "keep"
        assert g.verdict in (gc.EXACT_NOSPACE, gc.DRIFTED_MINOR)
        # matched_span 取自原文 raw（含換行連字），非 LLM 版
        assert "compre-" in g.matched_span and "\n" in g.matched_span

    def test_drifted_minor_kept(self):
        src = "the quick brown fox jumped over the lazy dog today"
        g = gc.ground_card("the quick brown fox jumps over the lazy dog", src)
        assert g.verdict == gc.DRIFTED_MINOR
        assert g.disposition == "keep"


class TestGroundCardErase:
    def test_not_found(self):
        src = "completely unrelated content about photosynthesis in plants"
        g = gc.ground_card("quantum chromodynamics predicts confinement of quarks", src)
        assert g.verdict == gc.NOT_FOUND
        assert g.disposition == "erase"

    def test_empty_is_no_desc(self):
        g = gc.ground_card("", "some source text")
        assert g.verdict == gc.NO_DESC
        assert g.disposition == "erase"

    def test_trailing_ellipsis_is_no_desc(self):
        src = "the definition of grounding is important here"
        g = gc.ground_card("the definition of grounding is...", src)
        assert g.verdict == gc.NO_DESC
        assert g.disposition == "erase"

    def test_placeholder_is_no_desc(self):
        g = gc.ground_card("（原文未明確說明此概念）", "source")
        assert g.verdict == gc.NO_DESC
        assert g.disposition == "erase"


class TestGroundCardCJK:
    def test_cjk_not_located_quarantined(self):
        # 中文核心不在抽取文字中（模擬 CID glyph 掉字）→ 隔離待審，不 erase
        src = "English only extracted text, the CJK glyphs were dropped."
        g = gc.ground_card("量詞「兩」用於成對的事物", src)
        assert g.verdict == gc.CJK_UNVERIFIABLE
        assert g.disposition == "quarantine"

    def test_cjk_located_is_kept(self):
        src = "論文指出：量詞「兩」用於成對的事物，例如兩隻手。"
        g = gc.ground_card("量詞「兩」用於成對的事物", src)
        assert g.disposition == "keep"
        assert g.verdict in (gc.EXACT, gc.EXACT_NOSPACE, gc.DRIFTED_MINOR)
