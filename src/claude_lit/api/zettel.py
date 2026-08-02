# -*- coding: utf-8 -*-
"""Zettelkasten 卡片生成核心 API

編排：來源解析 → cite_key → （跨論文連結）→ prompt → LLM → 解析 → 輸出 →
（入庫）→（向量嵌入）。知識庫與向量庫相依一律 lazy import。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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

    # 5. 解析
    emit(ProgressEvent(stage="parse", message="正在解析卡片..."))
    cards = zettel_maker.parse_llm_output(llm_output, cite_key=cite_key)
    if not cards:
        raise LLMGenerationError(
            "無法解析任何卡片（LLM 輸出不含 ===CARD:=== 區塊）",
            hint="請更換模型或降低 detail 後重試",
        )

    # 6. 輸出檔案
    emit(ProgressEvent(stage="write", message="正在寫入卡片檔案...", total=len(cards)))
    date_str = datetime.now().strftime("%Y%m%d")
    if request.output_dir:
        output_dir = Path(request.output_dir)
    else:
        output_dir = Path(f"output/zettelkasten_notes/zettel_{cite_key}_{date_str}")

    paper_info = _build_paper_info(request, source, cite_key)
    result = zettel_maker.generate_zettelkasten(
        llm_output=llm_output, output_dir=output_dir, paper_info=paper_info
    )

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
        warnings=warnings,
    )
