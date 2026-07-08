#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試語義搜索功能
"""

import sys
import io

import pytest

# 需要即時 Gemini embedding API；text-embedding-004 已棄用（404），屬暫停的 embeddings 功能
pytestmark = pytest.mark.skip(reason="需要即時 Gemini API 且嵌入模型已棄用；embeddings 功能暫停中")

from claude_lit.embeddings.providers import GeminiEmbedder
from claude_lit.embeddings.vector_db import VectorDatabase


def test_semantic_search():
    """測試語義搜索"""

    print("=" * 70)
    print("測試語義搜索功能")
    print("=" * 70)

    # 初始化
    embedder = GeminiEmbedder()
    vector_db = VectorDatabase()

    # 顯示統計
    stats = vector_db.get_stats()
    print(f"\n數據庫統計:")
    print(f"  論文向量數: {stats['papers_count']}")
    print(f"  Zettelkasten 向量數: {stats['zettel_count']}")
    print(f"  總計: {stats['total_count']}")

    # 測試查詢
    queries = [
        "深度學習 machine learning",
        "認知科學 cognitive science",
        "語言學 linguistics",
        "人工智慧 artificial intelligence"
    ]

    print("\n" + "=" * 70)
    print("測試論文搜索")
    print("=" * 70)

    for query in queries:
        print(f"\n查詢: {query}")

        # 生成查詢向量
        query_embedding = embedder.embed(query, task_type="retrieval_query")

        # 搜索論文
        results = vector_db.semantic_search_papers(
            query_embedding=query_embedding,
            n_results=3
        )

        if results['ids'] and len(results['ids'][0]) > 0:
            print(f"找到 {len(results['ids'][0])} 篇相關論文:")

            for i, (paper_id, distance) in enumerate(zip(results['ids'][0], results['distances'][0])):
                metadata = results['metadatas'][0][i]
                title = metadata.get('title', 'Unknown')
                similarity = 1 - distance  # 距離轉換為相似度

                print(f"  {i+1}. [{similarity:.2%}] {title}")
                print(f"     ID: {paper_id}")
        else:
            print("  未找到相關論文")

    print("\n" + "=" * 70)
    print("測試 Zettelkasten 搜索")
    print("=" * 70)

    for query in queries[:2]:  # 只測試前兩個查詢
        print(f"\n查詢: {query}")

        # 生成查詢向量
        query_embedding = embedder.embed(query, task_type="retrieval_query")

        # 搜索 Zettelkasten
        results = vector_db.semantic_search_zettel(
            query_embedding=query_embedding,
            n_results=3
        )

        if results['ids'] and len(results['ids'][0]) > 0:
            print(f"找到 {len(results['ids'][0])} 張相關卡片:")

            for i, (zettel_id, distance) in enumerate(zip(results['ids'][0], results['distances'][0])):
                metadata = results['metadatas'][0][i]
                title = metadata.get('title', 'Unknown')
                similarity = 1 - distance

                print(f"  {i+1}. [{similarity:.2%}] {title}")
                print(f"     ID: {zettel_id}")
        else:
            print("  未找到相關卡片")

    print("\n" + "=" * 70)
    print("✅ 測試完成")
    print("=" * 70)


if __name__ == "__main__":
    try:
        test_semantic_search()
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
