# -*- coding: utf-8 -*-
"""媒體類型生成流程測試（spec: slide-generation / zettel-generation — add-media-templates）

以真實文字檔來源 + mock LLM 驗證：模板選擇、文字來源前處理、CJK 政策、timestamp sidecar、
章節 cite_key，以及 paper 預設的零回歸。
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import claude_lit.api.prompts as prompts_mod
import claude_lit.api.zettel as zettel_mod
from claude_lit.api.errors import SourceNotFoundError
from claude_lit.api.models import MediaType, SlideRequest, ZettelRequest
from claude_lit.api.slides import generate_slides
from claude_lit.api.sources import SourceContent, resolve_source
from claude_lit.generators import SlideMaker

SRT = """1
00:00:01,000 --> 00:00:05,000
主持人：嗯，今天的主題是注意力，我們請到研究注意力十年的來賓。

2
00:12:30,000 --> 00:12:36,000
來賓 A：呃，我認為注意力其實是一種預測，而不是一盞探照燈。

3
00:12:37,000 --> 00:12:44,000
主持人：所以你的意思是，大腦一直在猜下一刻會看到什麼？

4
00:12:45,000 --> 00:12:58,000
來賓 A：沒錯，這是我十年研究的結論，也和預測處理理論一致。

5
00:13:00,000 --> 00:13:20,000
來賓 A：過去的教科書把注意力比喻成探照燈，只照亮被選中的區域，但這個比喻忽略了大腦主動產生預期的角色。

6
00:13:21,000 --> 00:13:40,000
主持人：那這個觀點對教育現場有什麼啟示？老師在課堂上應該怎麼引導學生的注意力？

7
00:13:41,000 --> 00:14:05,000
來賓 A：與其要求學生專心，不如先幫他們建立對接下來內容的預期，讓預測錯誤成為學習的起點。
"""

# 卡1 定位得到（逐字稿原句）；卡2 中文定位不到（杜撰）
PODCAST_OUTPUT = """
===CARD: P-001===
標題: 注意力即預測
類型: claim
核心: 我認為注意力其實是一種預測，而不是一盞探照燈。
標籤: 注意力, 預測處理

說明:
來賓 A 主張注意力是預測。

連結網絡:
- **對比** >< [[P-002]]

來源脈絡:
- **文獻**: [[P|科學新聞 EP42]]
- **位置**: 來賓 A，[00:12:30]
- **情境**: 回應主持人追問時提出。

個人筆記:

🤖 **AI**: 與 [[P-002]] 對照。

✍️ **Human**:

待解問題:
如何檢驗？
===

===CARD: P-002===
標題: 杜撰
類型: claim
核心: 注意力的本質是量子糾纏造成的意識跳躍
標籤: 杜撰

說明:
不存在於原文。

待解問題:
無。
===
"""


@pytest.fixture
def srt_file(tmp_path):
    f = tmp_path / "ep42.srt"
    f.write_text(SRT, encoding="utf-8")
    return f


@pytest.fixture
def capture_llm(monkeypatch):
    captured = {}

    def fake_call(self, prompt, **kw):
        captured["prompt"] = prompt
        return captured.get("output", PODCAST_OUTPUT), "google"

    monkeypatch.setattr(SlideMaker, "call_llm", fake_call)
    return captured


class TestRequestValidation:
    def test_default_media_is_paper(self, tmp_path):
        assert ZettelRequest(pdf=tmp_path / "a.pdf").media_type is MediaType.paper
        assert SlideRequest(topic="t").media_type is MediaType.paper

    def test_unknown_media_rejected(self):
        with pytest.raises(ValidationError, match="paper"):
            SlideRequest(topic="t", media_type="novel")

    def test_text_is_exclusive_source(self, tmp_path):
        with pytest.raises(ValidationError):
            ZettelRequest(pdf=tmp_path / "a.pdf", text=tmp_path / "a.srt")
        with pytest.raises(ValidationError):
            SlideRequest(url="https://x.org", text=tmp_path / "a.srt")
        assert ZettelRequest(text=tmp_path / "a.srt").text == tmp_path / "a.srt"

    def test_chapter_only_for_books(self, tmp_path):
        with pytest.raises(ValidationError, match="textbook"):
            ZettelRequest(text=tmp_path / "a.txt", media_type="lecture", chapter="3")
        with pytest.raises(ValidationError, match="範圍無效"):
            ZettelRequest(text=tmp_path / "a.txt", media_type="textbook", chapter="5-3")
        req = ZettelRequest(text=tmp_path / "a.txt", media_type="monograph", chapter="3-5")
        assert req.chapter == "3-5"


class TestTextSource:
    def test_srt_preprocessed_for_lecture(self, srt_file):
        src = resolve_source(text=srt_file, media_type="lecture", max_chars=10000)
        assert src.source_type == "transcript"
        assert "-->" not in src.content and "\n1\n" not in src.content
        assert "[00:12:30]\n" in src.content
        assert "嗯" not in src.content
        assert src.timeline

    def test_keep_fillers(self, srt_file):
        src = resolve_source(text=srt_file, media_type="lecture", keep_fillers=True, max_chars=10000)
        assert "嗯" in src.content

    def test_paper_media_no_markers(self, srt_file):
        src = resolve_source(text=srt_file, max_chars=10000)
        assert "[00:" not in src.content and "-->" not in src.content

    def test_missing_text_file(self, tmp_path):
        with pytest.raises(SourceNotFoundError):
            resolve_source(text=tmp_path / "nope.srt")

    def test_chapter_selection_and_missing_chapter(self, tmp_path):
        book = tmp_path / "book.md"
        body = "這是章節內容。" * 100
        book.write_text(f"第一章 緒論\n{body}\n第二章 方法\n{body}方法結尾\n第三章 結果\n{body}", encoding="utf-8")
        src = resolve_source(text=book, media_type="textbook", chapter="2", max_chars=100000)
        assert src.content.startswith("第二章 方法") and "第三章" not in src.content
        assert any("選取第 2 章" in w for w in src.warnings)
        with pytest.raises(SourceNotFoundError, match="第 9 章"):
            resolve_source(text=book, media_type="textbook", chapter="9", max_chars=100000)

    def test_truncation_hints_chapter_for_books(self, tmp_path):
        book = tmp_path / "book.txt"
        book.write_text("字" * 5000, encoding="utf-8")
        src = resolve_source(text=book, media_type="monograph", max_chars=1000)
        assert len(src.content) == 1000
        assert any("--chapter" in w for w in src.warnings)


class TestCiteKey:
    def test_text_stem_and_chapter_suffix(self, tmp_path):
        src = SourceContent(content="x")
        req = ZettelRequest(text=tmp_path / "Smith-2020.epub", media_type="textbook", chapter="3")
        assert prompts_mod.resolve_cite_key(req, src) == "Smith-2020-ch03"
        req = ZettelRequest(text=tmp_path / "b.pdf", cite_key="Lee-2019",
                            media_type="monograph", chapter="4-6")
        assert prompts_mod.resolve_cite_key(req, src) == "Lee-2019-ch04-06"


class TestZettelGeneration:
    def _gen(self, srt_file, tmp_path, **over):
        kw = dict(text=srt_file, media_type="podcast", add_to_kb=False, output_dir=tmp_path / "out",
                  source_meta={"show": "科學新聞", "episode": "EP42", "year": "2025"})
        kw.update(over)
        return zettel_mod.generate_zettel(ZettelRequest(**kw))

    def test_uses_media_template(self, srt_file, tmp_path, capture_llm):
        self._gen(srt_file, tmp_path)
        prompt = capture_llm["prompt"]
        assert "Podcast 逐字稿" in prompt
        assert "類型: [claim|concept|example|question]" in prompt
        assert "[[ep42|科學新聞 EP42 (2025)]]" in prompt
        assert "[00:12:30]" in prompt  # 前處理後的逐字稿進入 prompt

    def test_text_source_erases_unlocatable_cjk(self, srt_file, tmp_path, capture_llm):
        r = self._gen(srt_file, tmp_path)
        assert (r.grounded, r.erased, r.flagged) == (1, 1, 0)
        assert not (Path(r.output_dir) / "zettel_cards" / "_needs_cjk_check").exists()

    def test_claim_card_written_with_media_citation(self, srt_file, tmp_path, capture_llm):
        r = self._gen(srt_file, tmp_path)
        card = Path(r.card_files[0]).read_text(encoding="utf-8")
        assert "我認為注意力其實是一種預測，而不是一盞探照燈。" in card
        assert "[[ep42|科學新聞 EP42 (2025)]]" in card

    def test_sidecar_timestamp_from_offset(self, srt_file, tmp_path, capture_llm):
        r = self._gen(srt_file, tmp_path)
        sidecar = Path(r.output_dir) / "zettel_cards" / "ep42-001.grounding.json"
        rec = json.loads(sidecar.read_text(encoding="utf-8"))
        assert rec["verdict"] == "EXACT"
        assert rec["timestamp"] == "00:12:30"
        assert rec["source_fingerprint"]["text_name"] == "ep42.srt"
        assert rec["source_fingerprint"]["sha1"]

    def test_pdf_source_still_quarantines_cjk(self, tmp_path, capture_llm, monkeypatch):
        text = SRT.replace("-->", "")  # 夠長、含卡1 原句的「PDF 抽取文字」
        monkeypatch.setattr(
            zettel_mod, "resolve_source",
            lambda **kw: SourceContent(content=text, topic="T", source_type="pdf"),
        )
        pdf = tmp_path / "T.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        r = zettel_mod.generate_zettel(ZettelRequest(
            pdf=pdf, media_type="podcast", add_to_kb=False, output_dir=tmp_path / "out"))
        assert r.flagged == 1 and r.erased == 0

    def test_paper_text_source_also_erases(self, srt_file, tmp_path, capture_llm):
        # 文字來源的 CJK 政策與 media_type 無關
        r = self._gen(srt_file, tmp_path, media_type="paper", source_meta={})
        assert r.flagged == 0 and r.erased == 1


class TestSlidesGeneration:
    def test_lecture_slides_use_media_template(self, srt_file, tmp_path, capture_llm):
        capture_llm["output"] = "===標題頁===\n標題：注意力\n副標題：講演\n\n===投影片1===\n標題：論點\n內容：\n• 注意力是預測\n"
        result = generate_slides(SlideRequest(
            text=srt_file, media_type="lecture", source_meta={"speaker": "王小明"},
            output_path=tmp_path / "o.md",
        ))
        assert result.slide_count >= 1
        prompt = capture_llm["prompt"]
        assert "講演逐字稿" in prompt and "speaker：王小明" in prompt
        assert "Journal Club應包含" not in prompt


class TestPaperZeroRegression:
    """media_type=paper（預設）時渲染結果與既有模板逐字相同"""

    def test_slides_prompt_identical(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            prompts_mod, "resolve_source",
            lambda **kw: SourceContent(content="論文內容", topic="P", source_type="pdf"),
        )
        req = SlideRequest(topic="P", style="teaching")
        expected = SlideMaker(llm_provider=req.provider).generate_prompt(
            topic="P", style="teaching", detail_level="standard", language="chinese",
            slide_count=15, pdf_content="論文內容", source_type="pdf", custom_requirements=None,
        )
        assert prompts_mod.render_slides_prompt(req) == expected

    def test_zettel_prompt_uses_legacy_template(self, tmp_path):
        src = SourceContent(content="論文內容", topic="P", source_type="pdf")
        prompt = prompts_mod.render_zettel_prompt(
            ZettelRequest(pdf=tmp_path / "P.pdf"), source=src, cite_key="P-2024"
        )
        assert "閱讀此類來源的方式" not in prompt
        assert "類型: [concept|method|finding|question]" in prompt
        assert "[[P-2024.pdf|第一作者 (年份)]]" in prompt


class TestContentSourceAndOutputRoot:
    """ZettelRequest.content（遠端 MCP）與 output_root（網頁服務 job 目錄）"""

    CONTENT = SRT.replace("-->", "")  # 夠長、含卡1 原句

    def test_content_requires_cite_key(self, tmp_path, capture_llm):
        from claude_lit.api.errors import CiteKeyMissingError

        with pytest.raises(CiteKeyMissingError):
            zettel_mod.generate_zettel(ZettelRequest(content=self.CONTENT, add_to_kb=False,
                                                     output_dir=tmp_path / "o"))

    def test_content_is_grounding_source_and_text_policy(self, tmp_path, capture_llm):
        r = zettel_mod.generate_zettel(ZettelRequest(
            content=self.CONTENT, cite_key="Pod-2025", add_to_kb=False, output_dir=tmp_path / "o"))
        assert (r.grounded, r.erased, r.flagged) == (1, 1, 0)  # 直接提供的文字：中文杜撰抹除
        rec = json.loads((Path(r.output_dir) / "zettel_cards" / "Pod-2025-001.grounding.json").read_text(encoding="utf-8"))
        assert rec["source_fingerprint"]["sha1"]

    def test_content_exclusive_with_other_sources(self, tmp_path):
        with pytest.raises(ValidationError):
            ZettelRequest(content="x", pdf=tmp_path / "a.pdf")

    def test_output_root_replaces_default_output(self, tmp_path, capture_llm, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = zettel_mod.generate_zettel(ZettelRequest(
            content=self.CONTENT, cite_key="Pod-2025", add_to_kb=False, output_root=tmp_path / "job"))
        assert Path(r.output_dir).parent == (tmp_path / "job" / "zettelkasten_notes").resolve()
        assert not (tmp_path / "output").exists()
