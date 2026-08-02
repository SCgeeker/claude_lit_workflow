# -*- coding: utf-8 -*-
"""Zettelkasten 卡片生成核心 API

編排：來源解析 → cite_key → （跨論文連結）→ prompt → LLM → 解析 → 輸出 →
（入庫）→（向量嵌入）。知識庫與向量庫相依一律 lazy import。
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from claude_lit.checkers import grounding_checker as gc
from claude_lit.generators import SlideMaker
from claude_lit.generators.zettel_maker import ZettelMaker

from .errors import LLMGenerationError, ProviderUnavailableError
from .models import ZettelRequest, ZettelResult
from .progress import ProgressCallback, ProgressEvent
from .prompts import _ZETTEL_MAX_CHARS, get_card_count, render_zettel_prompt, resolve_cite_key
from .sources import resolve_source

logger = logging.getLogger("claude_lit_workflow.api.zettel")

# 抽取上限見 api.prompts._ZETTEL_MAX_CHARS（單一真相，import 沿用）。
# 每張卡片約 500-700 tokens；comprehensive(30張) 需 ~22000，上限 32000 防截斷
_TOKENS_PER_CARD = 700
_MAX_TOKENS_CAP = 32000

# grounding 門檻：來源短於此字元數視為不足以逐字比對，跳過 gate（避免 stub 誤刪全部）
_MIN_GROUND_SOURCE_CHARS = 200
_QUARANTINE_SUBDIR = "_needs_cjk_check"


def _source_fingerprint(request: "ZettelRequest") -> dict:
    """來源指紋（供 sidecar 偵測版本漂移）。PDF 才有 sha1；URL 記 url。"""
    fp: dict = {"pdf_name": None, "sha1": None}
    if request.pdf:
        p = Path(request.pdf)
        fp["pdf_name"] = p.name
        try:
            fp["sha1"] = hashlib.sha1(p.read_bytes()).hexdigest()
        except Exception:  # 讀不到不阻斷 grounding
            pass
    elif request.url:
        fp["url"] = request.url
    return fp


def _ground_cards(cards: List[dict], source_content: str) -> Tuple[List[dict], List[dict], dict]:
    """對每張卡片判 grounding，三分為 (keep, quarantine, grounding_by_obj)；erase 直接丟棄。

    keep 卡若核心與 raw span 僅差 normalize 雜訊，就地以「接合後單行」覆寫 core_summary
    （去換行連字/塌陷空白），使寫入 description 為原文可逐字回溯的樣貌；sidecar 另存 raw span。
    """
    grounding_by_obj: dict = {}
    kept: List[dict] = []
    quarantined: List[dict] = []
    for card in cards:
        core = card.get("core_summary", "")
        g = gc.ground_card(core, source_content)
        grounding_by_obj[id(card)] = g
        if g.disposition == "keep":
            if g.matched_span and gc.same_text_up_to_spacing(core, g.matched_span):
                card["core_summary"] = gc.normalize(g.matched_span)
            kept.append(card)
        elif g.disposition == "quarantine":
            quarantined.append(card)
        # erase：不落地
    return kept, quarantined, grounding_by_obj


def _assign_quarantine_ids(cards: List[dict], cite_key: str) -> None:
    """隔離卡給獨立 ID 命名空間 {cite_key}-cjk-NNN，並清掉連結（與正常卡序脫鉤）。"""
    for i, card in enumerate(cards, start=1):
        card["id"] = f"{cite_key}-cjk-{i:03d}"
        for field in ("foundation_links", "derived_links", "related_links", "contrast_links"):
            if field in card:
                card[field] = []


def _write_grounding_sidecar(directory: Path, card: dict, grounding, fingerprint: dict) -> None:
    """把單張卡片的 grounding 記錄寫成工具中立 sidecar {card_id}.grounding.json。"""
    if grounding is None:
        return
    record = {
        "card_id": card["id"],
        "verdict": grounding.verdict,
        "coverage": round(grounding.coverage, 4),
        "matched_span": grounding.matched_span,
        "char_offset": list(grounding.char_offset) if grounding.char_offset else None,
        "source_fingerprint": fingerprint,
    }
    (directory / f"{card['id']}.grounding.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get_kb_manager():
    """lazy import：只有入庫 / from_kb 時載入知識庫模組"""
    from claude_lit.knowledge_base import KnowledgeBaseManager

    return KnowledgeBaseManager()


def _query_related_cards(paper_content: str, cite_key: str, limit: int = 10) -> List[dict]:
    """查詢知識庫中相關卡片（跨論文連結用）；向量庫相依 lazy import，失敗回傳空清單。"""
    try:
        from claude_lit.integrations.vector_db import VectorDatabase
        from claude_lit.integrations.embedder import get_embedder

        query_text = (paper_content or "")[:1000]
        if not query_text:
            return []

        vector_db = VectorDatabase()
        embedder = get_embedder(provider="google")
        query_embedding = embedder.embed(query_text, task_type="retrieval_query")
        results = vector_db.semantic_search_zettel(
            query_embedding=query_embedding, n_results=limit * 2
        )
        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        related_cards = []
        for i, zettel_id in enumerate(results["ids"][0]):
            if zettel_id.startswith(cite_key):
                continue
            metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
            related_cards.append(
                {
                    "zettel_id": zettel_id,
                    "title": metadata.get("title", "Unknown"),
                    "core_concept": metadata.get("core_concept", ""),
                    "card_type": metadata.get("card_type", "concept"),
                    "source_paper": zettel_id.split("-")[0] if "-" in zettel_id else "Unknown",
                }
            )
            if len(related_cards) >= limit:
                break
        return related_cards
    except Exception as e:
        logger.warning("無法查詢相關卡片：%s", e)
        return []


def _build_paper_info(request: ZettelRequest, source, cite_key: str) -> dict:
    if source.paper_data:
        paper = source.paper_data
        return {
            "title": paper["title"],
            "authors": ", ".join(paper.get("authors", []) or []),
            "year": paper.get("year", datetime.now().year),
            "paper_id": request.from_kb or "",
            "cite_key": paper.get("cite_key", ""),
            "citation": paper["title"],
        }
    return {
        "title": source.topic,
        "authors": "",
        "year": datetime.now().year,
        "paper_id": "",
        "cite_key": cite_key,
        "citation": source.topic,
    }


def _add_cards_to_kb(request: ZettelRequest, cite_key: str, card_files: List[str], warnings: List[str]):
    """卡片入庫；回傳 (added, skipped)"""
    kb = _get_kb_manager()
    paper_id = request.from_kb

    if request.force:
        if paper_id:
            delete_result = kb.delete_zettel_cards_by_paper(paper_id)
        else:
            delete_result = kb.delete_zettel_cards_by_citekey(cite_key)
        logger.info("強制模式：刪除 %s 張舊卡片", delete_result.get("deleted_cards", 0))

    added = 0
    skipped = 0
    for card_file in card_files:
        card_data = kb.parse_zettel_card(card_file)
        if not card_data:
            continue
        add_result = kb.add_zettel_card(card_data)
        if add_result["status"] == "inserted":
            added += 1
            if paper_id and add_result["card_id"] > 0:
                kb.link_paper_to_zettel(paper_id, add_result["card_id"], 1.0)
        elif add_result["status"] == "duplicate":
            skipped += 1
    return added, skipped


def _embed_cards(cite_key: str, card_files: List[str], warnings: List[str]) -> int:
    """向量嵌入；失敗記 warning 不中斷（可稍後 uv run embeddings 補上）"""
    try:
        from claude_lit.integrations.vector_db import VectorDatabase
        from claude_lit.integrations.embedder import get_embedder

        kb = _get_kb_manager()
        vector_db = VectorDatabase()
        embedder = get_embedder(provider="google")

        embedded = 0
        for card_file in card_files:
            card_data = kb.parse_zettel_card(card_file)
            if card_data and card_data.get("content"):
                embedding = embedder.embed(
                    card_data["content"][:2000], task_type="retrieval_document"
                )
                vector_db.upsert_zettel(
                    embeddings=[embedding],
                    documents=[card_data["content"][:2000]],
                    ids=[card_data["zettel_id"]],
                    metadatas=[
                        {
                            "title": card_data.get("title", ""),
                            "core_concept": card_data.get("core_concept", ""),
                            "card_type": card_data.get("card_type", "concept"),
                            "cite_key": cite_key,
                        }
                    ],
                )
                embedded += 1
        return embedded
    except Exception as e:
        warnings.append(f"向量嵌入失敗：{e}（可稍後執行 uv run embeddings 補上）")
        return 0


def generate_zettel(
    request: ZettelRequest,
    *,
    progress: Optional[ProgressCallback] = None,
    api_key: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> ZettelResult:
    """生成 Zettelkasten 原子卡片。

    Raises:
        SourceNotFoundError / ExtractionError / CiteKeyMissingError /
        ProviderUnavailableError / LLMGenerationError
    """
    emit = progress or (lambda _e: None)
    warnings: List[str] = []

    maker_kwargs = {
        "llm_provider": request.provider,
        "selection_strategy": request.selection_strategy,
    }
    if api_key:
        maker_kwargs["api_key"] = api_key
    if ollama_url:
        maker_kwargs["ollama_url"] = ollama_url
    maker = SlideMaker(**maker_kwargs)
    zettel_maker = ZettelMaker()

    # 1. 來源與 cite_key
    emit(ProgressEvent(stage="extract", message="正在抽取內容來源..."))
    source = resolve_source(
        pdf=request.pdf,
        url=request.url,
        from_kb=request.from_kb,
        max_chars=_ZETTEL_MAX_CHARS,
    )
    warnings.extend(source.warnings)
    cite_key = resolve_cite_key(request, source)
    card_count = get_card_count(request.detail.value)

    # 2. 跨論文連結
    related_cards: List[dict] = []
    if request.cross_link:
        emit(ProgressEvent(stage="cross_link", message="正在查詢知識庫相關概念..."))
        related_cards = _query_related_cards(source.content, cite_key, limit=10)

    # 3. Prompt
    emit(ProgressEvent(stage="prompt", message="正在渲染提示詞..."))
    zettel_prompt = render_zettel_prompt(
        request, source=source, cite_key=cite_key, related_cards=related_cards
    )

    # 4. LLM
    max_tokens = min(max(card_count * _TOKENS_PER_CARD + 1000, 4096), _MAX_TOKENS_CAP)
    emit(ProgressEvent(stage="llm", message=f"正在生成 {card_count} 張原子筆記卡片..."))
    try:
        llm_output, used_provider = maker.call_llm(
            zettel_prompt, model=request.model, max_tokens=max_tokens, task_type="zettelkasten"
        )
    except RuntimeError as e:
        raise ProviderUnavailableError(
            f"LLM 呼叫失敗：{e}",
            hint="執行 uv run setup 檢查 LLM 供應商設定",
        ) from e

    # 5. 解析（延後 canonicalize：先不編 ID，待 grounding 過濾後再對存活卡片編號）
    emit(ProgressEvent(stage="parse", message="正在解析卡片..."))
    cards = zettel_maker.parse_llm_output(llm_output, cite_key=None)
    if not cards:
        raise LLMGenerationError(
            "無法解析任何卡片（LLM 輸出不含 ===CARD:=== 區塊）",
            hint="請更換模型或降低 detail 後重試",
        )

    # 5.5 grounding gate（三分 KEEP / QUARANTINE / ERASE；erase 不落地）
    total_parsed = len(cards)
    quarantined: List[dict] = []
    grounding_by_obj: dict = {}
    grounded = erased = flagged = 0
    if request.ground:
        if source.content and len(source.content) >= _MIN_GROUND_SOURCE_CHARS:
            cards, quarantined, grounding_by_obj = _ground_cards(cards, source.content)
            erased = total_parsed - len(cards) - len(quarantined)
            if not cards:
                raise LLMGenerationError(
                    "所有卡片均無法逐字回溯原文（grounding 全數抹除）",
                    hint="來源抽取品質或模型可能不佳；可加 --no-ground 略過驗證後人工檢查",
                )
            zettel_maker.canonicalize_card_ids(cards, cite_key)
            _assign_quarantine_ids(quarantined, cite_key)
            grounded, flagged = len(cards), len(quarantined)
            if erased:
                warnings.append(f"grounding 抹除 {erased} 張無法逐字回溯原文的卡片")
            if flagged:
                warnings.append(
                    f"{flagged} 張含中文且定位不到，已隔離至 {_QUARANTINE_SUBDIR}/ 待審"
                )
        else:
            zettel_maker.canonicalize_card_ids(cards, cite_key)
            grounded = len(cards)
            warnings.append("來源內容不足，跳過 grounding 驗證")
        emit(ProgressEvent(
            stage="ground",
            message=f"grounded {grounded}/{total_parsed}，erased {erased}，flagged {flagged}",
        ))
    else:
        zettel_maker.canonicalize_card_ids(cards, cite_key)

    # 6. 輸出檔案
    emit(ProgressEvent(stage="write", message="正在寫入卡片檔案...", total=len(cards)))
    date_str = datetime.now().strftime("%Y%m%d")
    if request.output_dir:
        output_dir = Path(request.output_dir)
    else:
        output_dir = Path(f"output/zettelkasten_notes/zettel_{cite_key}_{date_str}")

    paper_info = _build_paper_info(request, source, cite_key)
    result = zettel_maker.generate_zettelkasten(
        cards=cards, output_dir=output_dir, paper_info=paper_info
    )

    # 6.5 grounding sidecar + 隔離卡輸出
    if grounding_by_obj:
        cards_dir = Path(result["output_dir"]) / "zettel_cards"
        fingerprint = _source_fingerprint(request)
        for card in cards:
            _write_grounding_sidecar(cards_dir, card, grounding_by_obj.get(id(card)), fingerprint)
        if quarantined:
            qdir = cards_dir / _QUARANTINE_SUBDIR
            qdir.mkdir(parents=True, exist_ok=True)
            for card in quarantined:
                zettel_maker.create_card_file(card, qdir, paper_info)
                _write_grounding_sidecar(qdir, card, grounding_by_obj.get(id(card)), fingerprint)

    # URL 來源：寫入 _source.json 標記（供匯入腳本偵測 --allow-missing-bib）
    if request.url:
        source_marker = Path(result["output_dir"]) / "_source.json"
        source_marker.write_text(
            json.dumps({"source_type": source.source_type, "url": request.url}, ensure_ascii=False),
            encoding="utf-8",
        )

    # 7. 入庫
    kb_added = 0
    kb_skipped = 0
    if request.add_to_kb:
        emit(ProgressEvent(stage="kb", message="正在將卡片加入知識庫..."))
        kb_added, kb_skipped = _add_cards_to_kb(request, cite_key, result["card_files"], warnings)

    # 8. 向量嵌入
    embedded = 0
    if request.embed and request.add_to_kb:
        emit(ProgressEvent(stage="embed", message="正在生成向量嵌入..."))
        embedded = _embed_cards(cite_key, result["card_files"], warnings)

    return ZettelResult(
        output_dir=str(Path(result["output_dir"]).resolve()),
        index_file=str(Path(result["index_file"]).resolve()),
        card_files=[str(Path(f).resolve()) for f in result["card_files"]],
        card_count=result["card_count"],
        cite_key=cite_key,
        provider_used=used_provider,
        kb_added=kb_added,
        kb_skipped=kb_skipped,
        embedded=embedded,
        grounded=grounded,
        erased=erased,
        flagged=flagged,
        warnings=warnings,
    )
