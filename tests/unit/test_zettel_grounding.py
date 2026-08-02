# -*- coding: utf-8 -*-
"""生成端 grounding gate 測試（P3 / add-grounding-gate Phase 3）

以 mock 的來源與 LLM 輸出驗證：核心可定位 → 保留；定位不到 → 抹除；
中文定位不到 → 隔離；每張存活/隔離卡有 sidecar；frontmatter 不含 grounding 欄位。
"""

import json
from pathlib import Path

import pytest

import claude_lit.api.zettel as zettel_mod
from claude_lit.api.errors import LLMGenerationError
from claude_lit.api.models import ZettelRequest
from claude_lit.api.sources import SourceContent
from claude_lit.generators import SlideMaker

# 來源含卡 1 的核心逐字；夠長以通過 grounding 門檻
SOURCE = (
    "This study argues that grounded cognition ties meaning to sensorimotor "
    "systems, and reviews supporting evidence across multiple experiments. "
    "The results section reports reaction time data and discusses implications "
    "for theories of conceptual representation in the human brain at length."
)

# 卡1 可定位（keep）、卡2 英文定位不到（erase）、卡3 中文定位不到（quarantine）
LLM_OUTPUT = """
===CARD: A-001===
標題: Grounded cognition
類型: concept
核心: grounded cognition ties meaning to sensorimotor systems
標籤: cognition

說明:
說明一。

待解問題:
無。
===

===CARD: A-002===
標題: FTL signalling
類型: finding
核心: quantum entanglement enables faster-than-light signalling
標籤: physics

說明:
說明二。

待解問題:
無。
===

===CARD: A-003===
標題: 量詞
類型: concept
核心: 量詞「兩」用於成對的事物
標籤: linguistics

說明:
說明三。

待解問題:
無。
===
"""


@pytest.fixture
def fake_pdf(tmp_path, monkeypatch):
    pdf = tmp_path / "Test-2024.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake bytes for sha1")
    monkeypatch.setattr(
        zettel_mod, "resolve_source",
        lambda **kw: SourceContent(content=SOURCE, topic="Test Paper", source_type="pdf"),
    )
    return pdf


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setattr(
        SlideMaker, "call_llm", lambda self, prompt, **kw: (LLM_OUTPUT, "google")
    )


def _gen(pdf, tmp_path, **over):
    kw = dict(pdf=pdf, add_to_kb=False, output_dir=tmp_path / "out")
    kw.update(over)
    return zettel_mod.generate_zettel(ZettelRequest(**kw))


class TestGroundingGate:
    def test_keep_erase_quarantine_counts(self, fake_pdf, mock_llm, tmp_path):
        r = _gen(fake_pdf, tmp_path)
        assert r.grounded == 1          # 只有卡1 可定位
        assert r.erased == 1            # 卡2 抹除
        assert r.flagged == 1           # 卡3 隔離
        assert r.card_count == 1
        assert len(r.card_files) == 1

    def test_erased_card_absent_kept_card_present(self, fake_pdf, mock_llm, tmp_path):
        r = _gen(fake_pdf, tmp_path)
        stems = [Path(f).stem for f in r.card_files]
        assert stems == ["Test-2024-001"]
        # 卡2 的內容不應出現在任何存活卡檔
        joined = "\n".join(Path(f).read_text(encoding="utf-8") for f in r.card_files)
        assert "faster-than-light" not in joined

    def test_quarantine_written_separately(self, fake_pdf, mock_llm, tmp_path):
        r = _gen(fake_pdf, tmp_path)
        qdir = Path(r.output_dir) / "zettel_cards" / "_needs_cjk_check"
        assert qdir.is_dir()
        qcards = list(qdir.glob("*.md"))
        assert len(qcards) == 1
        # 隔離卡不進正常 card_files
        assert all("_needs_cjk_check" not in f for f in r.card_files)

    def test_sidecar_with_verdict_and_fingerprint(self, fake_pdf, mock_llm, tmp_path):
        r = _gen(fake_pdf, tmp_path)
        sidecar = Path(r.output_dir) / "zettel_cards" / "Test-2024-001.grounding.json"
        assert sidecar.exists()
        rec = json.loads(sidecar.read_text(encoding="utf-8"))
        assert rec["verdict"] == "EXACT"
        assert rec["source_fingerprint"]["pdf_name"] == "Test-2024.pdf"
        assert rec["source_fingerprint"]["sha1"]

    def test_quarantine_sidecar_verdict_cjk(self, fake_pdf, mock_llm, tmp_path):
        r = _gen(fake_pdf, tmp_path)
        qdir = Path(r.output_dir) / "zettel_cards" / "_needs_cjk_check"
        sidecars = list(qdir.glob("*.grounding.json"))
        assert len(sidecars) == 1
        rec = json.loads(sidecars[0].read_text(encoding="utf-8"))
        assert rec["verdict"] == "CJK_UNVERIFIABLE"

    def test_frontmatter_has_no_grounding_key(self, fake_pdf, mock_llm, tmp_path):
        r = _gen(fake_pdf, tmp_path)
        content = Path(r.card_files[0]).read_text(encoding="utf-8")
        # frontmatter 區塊（首個 --- 到第二個 ---）不得含 grounding 欄位
        head = content.split("---")[1] if content.startswith("---") else content
        assert "grounding" not in head

    def test_ground_false_keeps_all(self, fake_pdf, mock_llm, tmp_path):
        r = _gen(fake_pdf, tmp_path, ground=False)
        assert r.card_count == 3
        assert r.erased == 0 and r.flagged == 0

    def test_all_erased_raises(self, fake_pdf, monkeypatch, tmp_path):
        only_unmatched = """
===CARD: A-001===
標題: X
類型: finding
核心: quantum entanglement enables faster-than-light signalling
標籤: t

說明:
s
===
"""
        monkeypatch.setattr(
            SlideMaker, "call_llm", lambda self, prompt, **kw: (only_unmatched, "google")
        )
        with pytest.raises(LLMGenerationError):
            _gen(fake_pdf, tmp_path)

    def test_progress_includes_ground_stage(self, fake_pdf, mock_llm, tmp_path):
        events = []
        zettel_mod.generate_zettel(
            ZettelRequest(pdf=fake_pdf, add_to_kb=False, output_dir=tmp_path / "out"),
            progress=events.append,
        )
        stages = [e.stage for e in events]
        assert stages == ["extract", "prompt", "llm", "parse", "ground", "write"]


class TestSafeAutoCorrect:
    def test_line_wrap_hyphen_core_normalized_span_written(self, tmp_path, monkeypatch):
        src = (
            "In this paper we describe the rational compre-\nhender model, "
            "which processes linguistic input incrementally and predictively "
            "across a wide range of experimental conditions and materials. "
            "The model is evaluated against reading-time data and eye movement "
            "records collected from many participants over several sessions here."
        )
        out = """
===CARD: A-001===
標題: Rational comprehender
類型: concept
核心: rational compre-hender model
標籤: t

說明:
s
===
"""
        monkeypatch.setattr(
            zettel_mod, "resolve_source",
            lambda **kw: SourceContent(content=src, topic="T", source_type="pdf"),
        )
        monkeypatch.setattr(
            SlideMaker, "call_llm", lambda self, prompt, **kw: (out, "google")
        )
        pdf = tmp_path / "Test-2024.pdf"
        pdf.write_bytes(b"%PDF fake")
        r = _gen(pdf, tmp_path)
        assert r.card_count == 1
        card = Path(r.card_files[0]).read_text(encoding="utf-8")
        # 寫入的核心為接合後單行（去換行連字），不含斷行
        assert "rational comprehender model" in card
        # sidecar 保留 raw span（含原始換行連字）作為 provenance
        rec = json.loads(
            (Path(r.output_dir) / "zettel_cards" / "Test-2024-001.grounding.json").read_text(
                encoding="utf-8"
            )
        )
        assert "\n" in rec["matched_span"]
