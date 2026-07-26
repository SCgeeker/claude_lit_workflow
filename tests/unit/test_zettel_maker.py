# -*- coding: utf-8 -*-
"""ZettelMaker.parse_llm_output 測試（回歸：LLM 卡片 ID 漂移）

不呼叫 LLM，直接餵入模擬輸出，可離線重複執行。
"""

import pytest

from claude_lit.generators.zettel_maker import ZettelMaker

# 模擬 gemma4:12b 實測輸出的 ID 漂移：補零消失、後段退化成別篇論文的 citekey，
# 連結指向不存在的卡片（Hart-2016-03）。
DRIFTED_OUTPUT = """
===CARD: Hart-2026-001===
標題: 確認主義
類型: concept
核心: 科學的目標是尋找支持假設的證據。
標籤: epistemology, confirmation

說明:
第一種傳統認為科學的目標是尋找支持或證實假設的證據。

連結:
導向 -> [[Hart-2026-02]]

待解問題:
歸納問題能否在此框架內解決？
===

===CARD: Hart-2026-02===
標題: 歸納問題
類型: concept
核心: 有限的觀察無法邏輯上保證普遍規律。
標籤: induction

說明:
再多的確認性觀察也無法保證普遍化的結論成立。

連結:
基於 -> [[Hart-2026-001]]
相關 <-> [[Hart-2016-03]]

待解問題:
無。
===

===CARD: Hart-2017===
標題: 嚴格測試
類型: concept
核心: 嚴格測試是證據能強力區分假設的測試。
標籤: severity

說明:
以貝氏語言表述，嚴格測試對應到高似然比。

連結:
基於 -> [[Hart-2026-001]]

待解問題:
如何量化區分力？
===
"""


@pytest.fixture
def maker():
    return ZettelMaker()


class TestCardIdCanonicalization:
    def test_ids_are_sequential_and_zero_padded(self, maker):
        """卡片 ID 須由 cite_key + 序號決定，不採信 LLM 自報的 ID"""
        cards = maker.parse_llm_output(DRIFTED_OUTPUT, cite_key="Hart-2026")
        assert [c["id"] for c in cards] == [
            "Hart-2026-001",
            "Hart-2026-002",
            "Hart-2026-003",
        ]

    def test_links_remapped_to_canonical_ids(self, maker):
        """卡內連結須跟著改寫，指向重編後的 ID"""
        cards = maker.parse_llm_output(DRIFTED_OUTPUT, cite_key="Hart-2026")
        # 卡 1 導向 LLM 的 Hart-2026-02（實為第 2 張）→ 應改寫為 Hart-2026-002
        assert cards[0]["derived_links"] == ["Hart-2026-002"]
        # 卡 3（LLM 自稱 Hart-2017）基於第 1 張
        assert cards[2]["foundation_links"] == ["Hart-2026-001"]

    def test_hallucinated_links_dropped(self, maker):
        """指向不存在卡片的幻覺連結須丟棄，不得寫進輸出"""
        cards = maker.parse_llm_output(DRIFTED_OUTPUT, cite_key="Hart-2026")
        assert cards[1]["related_links"] == []

    def test_without_cite_key_keeps_llm_ids(self, maker):
        """未提供 cite_key 時維持原行為（向後相容）"""
        cards = maker.parse_llm_output(DRIFTED_OUTPUT)
        assert [c["id"] for c in cards] == ["Hart-2026-001", "Hart-2026-02", "Hart-2017"]


# gemma4:12b 實測：章節標頭被寫成錯字變體（連結語系／來源脈索／個人筆目），
# 嚴格白名單比對認不得，整段落進「說明」，連結因此從未進入 links 欄位。
TYPO_HEADER_OUTPUT = """
===CARD: Hart-2026-001===
標題: 確認主義
類型: concept
核心: 科學的目標是尋找支持假設的證據。

說明:
第一種傳統認為科學的目標是尋找支持或證實假設的證據。

連結語系：
- **導向** -> [[Hart-2026-02]]

來源脈索:
- **位置**: Section 2.1

個人筆目:
🤖 **AI**: 與歸納問題密切相關。

待解問題:
歸納問題能否在此框架內解決？
===

===CARD: Hart-2026-02===
標題: 歸納問題
類型: concept
核心: 有限的觀察無法邏輯上保證普遍規律。

說明:
再多的確認性觀察也無法保證普遍化的結論成立。

連結語系：
- **基於** <- [[Hart-2026-001]]

待解問題:
無。
===
"""


class TestSectionHeaderVariants:
    def test_typo_headers_still_split_sections(self, maker):
        """章節標頭有錯字時仍須正確分段，不得整塊落進說明"""
        cards = maker.parse_llm_output(TYPO_HEADER_OUTPUT, cite_key="Hart-2026")
        assert "連結語系" not in cards[0]["detailed_explanation"]
        assert "個人筆目" not in cards[0]["detailed_explanation"]
        assert cards[0]["open_questions"].strip() == "歸納問題能否在此框架內解決？"

    def test_links_from_typo_header_are_canonicalized(self, maker):
        """錯字標頭下的連結仍須進 links 欄位並完成改寫"""
        cards = maker.parse_llm_output(TYPO_HEADER_OUTPUT, cite_key="Hart-2026")
        assert cards[0]["derived_links"] == ["Hart-2026-002"]
        assert cards[1]["foundation_links"] == ["Hart-2026-001"]


NOTE_LINK_OUTPUT = """
===CARD: Hart-2026-001===
標題: 確認主義
類型: concept
核心: 科學的目標是尋找支持假設的證據。

說明:
第一種傳統認為科學的目標是尋找支持或證實假設的證據。

個人筆記:
🤖 **AI**: 此點與 [[Hart-2026-02]] 相關，也牽涉 [[Hart-2018-杜姆_奎因問題]]。

待解問題:
無。
===

===CARD: Hart-2026-02===
標題: 歸納問題
類型: concept
核心: 有限的觀察無法邏輯上保證普遍規律。

說明:
再多的確認性觀察也無法保證普遍化的結論成立。

來源脈絡:
- **文獻**: [[Hart-2026.pdf|Hart & Franks (2026)]]

待解問題:
無。
===
"""


class TestFreeTextLinks:
    def test_note_links_remapped(self, maker):
        """個人筆記等自由文字內的連結也須改寫為正規 ID"""
        cards = maker.parse_llm_output(NOTE_LINK_OUTPUT, cite_key="Hart-2026")
        assert "[[Hart-2026-002]]" in cards[0]["personal_notes"]

    def test_dangling_note_links_become_plain_text(self, maker):
        """指向不存在卡片的連結須退成純文字，避免筆記 App 出現死連結"""
        cards = maker.parse_llm_output(NOTE_LINK_OUTPUT, cite_key="Hart-2026")
        assert "[[Hart-2018-杜姆_奎因問題]]" not in cards[0]["personal_notes"]
        assert "Hart-2018-杜姆_奎因問題" in cards[0]["personal_notes"]

    def test_source_file_link_preserved(self, maker):
        """來源文獻連結（含 .pdf 或顯示文字）不得被改動"""
        cards = maker.parse_llm_output(NOTE_LINK_OUTPUT, cite_key="Hart-2026")
        assert "[[Hart-2026.pdf|Hart & Franks (2026)]]" in cards[1]["source_context"]


class TestCardDelimiterStripped:
    def test_trailing_delimiter_not_in_content(self, maker):
        """卡片結尾的 === 分隔符不得殘留在內容欄位（回歸：20/20 卡片全中）"""
        cards = maker.parse_llm_output(DRIFTED_OUTPUT, cite_key="Hart-2026")
        for card in cards:
            assert not card["open_questions"].rstrip().endswith("===")
            assert "===" not in card["detailed_explanation"]
