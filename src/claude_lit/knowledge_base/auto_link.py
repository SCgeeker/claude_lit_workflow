"""
自動連結功能（基於向量相似度）
Auto-linking Papers to Zettelkasten Cards using Vector Similarity
"""

import numpy as np
from typing import Dict, List, Optional
from pathlib import Path
import sys

# 添加專案根目錄到路徑
project_root = Path(__file__).parent.parent.parent


from claude_lit.embeddings.vector_db import VectorDatabase
from claude_lit.knowledge_base.kb_manager import KnowledgeBaseManager


def auto_link_v2(
    paper_id: int,
    threshold: float = 0.6,
    max_links: int = 5,
    kb_root: str = "knowledge_base",
    chroma_db_path: str = "chroma_db"
) -> Dict:
    """
    基於向量相似度自動建立論文與 Zettelkasten 卡片的連結

    Args:
        paper_id: 論文 ID
        threshold: 相似度閾值（0-1），默認 0.6
        max_links: 最多建立幾個連結，默認 5
        kb_root: 知識庫根目錄
        chroma_db_path: ChromaDB 持久化目錄

    Returns:
        {
            'paper_id': int,
            'paper_title': str,
            'links_created': int,
            'links': [
                {
                    'card_id': int,
                    'zettel_id': str,
                    'similarity': float,
                    'title': str,
                    'core_concept': str
                }
            ]
        }

    Raises:
        ValueError: 如果論文不存在或沒有對應向量
        Exception: 其他錯誤
    """
    # 1. 初始化知識庫和向量資料庫
    kb = KnowledgeBaseManager(kb_root=kb_root)
    vector_db = VectorDatabase(persist_directory=chroma_db_path)

    # 2. 獲取論文信息
    paper = kb.get_paper_by_id(paper_id)
    if not paper:
        raise ValueError(f"論文 ID {paper_id} 不存在")

    paper_title = paper.get('title', '未知標題')

    # 3. 獲取論文向量
    paper_vector_id = f"paper_{paper_id}"
    try:
        paper_data = vector_db.get_paper_by_id(paper_vector_id)
        if not paper_data:
            raise ValueError(f"論文 {paper_id} 沒有對應的向量嵌入，請先執行 generate_embeddings.py")

        paper_embedding = np.array(paper_data['embedding'])
    except Exception as e:
        raise ValueError(f"無法獲取論文向量：{str(e)}")

    # 4. 搜索相似的 Zettelkasten 卡片
    # 多取一些以防過濾後不足
    search_limit = max_links * 3 if max_links * 3 <= 50 else 50

    results = vector_db.semantic_search_zettel(
        query_embedding=paper_embedding,
        n_results=search_limit
    )

    # 5. 過濾：相似度 >= threshold
    candidates = []

    if results and 'ids' in results and len(results['ids']) > 0:
        ids = results['ids'][0] if isinstance(results['ids'][0], list) else results['ids']
        distances = results['distances'][0] if isinstance(results['distances'][0], list) else results['distances']
        metadatas = results['metadatas'][0] if isinstance(results['metadatas'][0], list) else results['metadatas']

        for zettel_id, distance, metadata in zip(ids, distances, metadatas):
            # ChromaDB 使用距離（距離越小越相似），我們轉換為相似度
            # 假設使用 cosine distance，相似度 = 1 - distance
            similarity = 1.0 - distance

            if similarity >= threshold:
                candidates.append({
                    'zettel_id': zettel_id,
                    'similarity': similarity,
                    'title': metadata.get('title', ''),
                    'core_concept': metadata.get('core_concept', '')
                })

    # 6. 按相似度排序並取前 max_links 個
    candidates.sort(key=lambda x: x['similarity'], reverse=True)
    top_candidates = candidates[:max_links]

    # 7. 建立連結到數據庫
    links_created = 0
    linked_cards = []

    for candidate in top_candidates:
        # 提取 card_id from zettel_id
        # zettel_id 格式：zettel_CogSci-20251029-001（向量DB）
        # 數據庫中存儲的格式：CogSci-20251029-001（沒有 zettel_ 前綴）
        try:
            # 移除 zettel_ 前綴
            db_zettel_id = candidate['zettel_id'].replace('zettel_', '')

            # 使用 zettel_id 查詢 card_id
            import sqlite3
            conn = sqlite3.connect(kb.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT card_id, title, core_concept
                FROM zettel_cards
                WHERE zettel_id = ?
            """, (db_zettel_id,))

            result = cursor.fetchone()
            conn.close()

            if result:
                card_id, title, core_concept = result

                # 建立連結
                kb.link_paper_to_zettel(
                    paper_id=paper_id,
                    card_id=card_id,
                    similarity=candidate['similarity']
                )

                links_created += 1
                linked_cards.append({
                    'card_id': card_id,
                    'zettel_id': candidate['zettel_id'],
                    'similarity': candidate['similarity'],
                    'title': title or candidate['title'],
                    'core_concept': core_concept or candidate['core_concept']
                })

        except Exception as e:
            print(f"警告：無法建立連結到 {candidate['zettel_id']}：{str(e)}")
            continue

    # 8. 返回結果
    return {
        'paper_id': paper_id,
        'paper_title': paper_title,
        'links_created': links_created,
        'links': linked_cards,
        'threshold': threshold,
        'candidates_found': len(candidates)
    }


def auto_link_all_papers(
    threshold: float = 0.6,
    max_links: int = 5,
    kb_root: str = "knowledge_base",
    chroma_db_path: str = "chroma_db",
    verbose: bool = True
) -> Dict:
    """
    為知識庫中的所有論文批次建立連結

    Args:
        threshold: 相似度閾值
        max_links: 每篇論文最多建立的連結數
        kb_root: 知識庫根目錄
        chroma_db_path: ChromaDB 目錄
        verbose: 是否顯示詳細進度

    Returns:
        {
            'total_papers': int,
            'processed': int,
            'failed': int,
            'total_links_created': int,
            'results': List[Dict]
        }
    """
    kb = KnowledgeBaseManager(kb_root=kb_root)

    # 獲取所有論文
    import sqlite3
    conn = sqlite3.connect(kb.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM papers ORDER BY id")
    papers = cursor.fetchall()
    conn.close()

    total_papers = len(papers)
    processed = 0
    failed = 0
    total_links_created = 0
    results = []

    for paper_id, title in papers:
        if verbose:
            print(f"[{processed + 1}/{total_papers}] 處理論文 {paper_id}: {title[:50]}...")

        try:
            result = auto_link_v2(
                paper_id=paper_id,
                threshold=threshold,
                max_links=max_links,
                kb_root=kb_root,
                chroma_db_path=chroma_db_path
            )

            processed += 1
            total_links_created += result['links_created']
            results.append(result)

            if verbose:
                print(f"  ✅ 成功建立 {result['links_created']} 個連結")

        except Exception as e:
            failed += 1
            if verbose:
                print(f"  ❌ 失敗：{str(e)}")

    return {
        'total_papers': total_papers,
        'processed': processed,
        'failed': failed,
        'total_links_created': total_links_created,
        'average_links_per_paper': total_links_created / processed if processed > 0 else 0,
        'results': results
    }


if __name__ == "__main__":
    """測試自動連結功能"""
    import argparse

    parser = argparse.ArgumentParser(description="自動建立論文-Zettelkasten連結")
    parser.add_argument("paper_id", type=int, nargs='?', help="論文 ID（留空則處理所有論文）")
    parser.add_argument("--threshold", type=float, default=0.6, help="相似度閾值（默認：0.6）")
    parser.add_argument("--max-links", type=int, default=5, help="最多建立幾個連結（默認：5）")
    parser.add_argument("--all", action="store_true", help="為所有論文建立連結")

    args = parser.parse_args()

    if args.all or args.paper_id is None:
        print("=" * 60)
        print("批次自動連結所有論文")
        print("=" * 60)
        result = auto_link_all_papers(
            threshold=args.threshold,
            max_links=args.max_links,
            verbose=True
        )
        print("\n" + "=" * 60)
        print("批次處理完成")
        print("=" * 60)
        print(f"總論文數：{result['total_papers']}")
        print(f"成功處理：{result['processed']}")
        print(f"失敗數量：{result['failed']}")
        print(f"總連結數：{result['total_links_created']}")
        print(f"平均每篇：{result['average_links_per_paper']:.2f} 個連結")

    else:
        print("=" * 60)
        print(f"自動連結論文 {args.paper_id}")
        print("=" * 60)
        result = auto_link_v2(
            paper_id=args.paper_id,
            threshold=args.threshold,
            max_links=args.max_links
        )

        print(f"\n論文：{result['paper_title']}")
        print(f"建立連結：{result['links_created']} 個")
        print(f"候選總數：{result['candidates_found']} 個（>= {args.threshold} 相似度）")
        print("\n連結詳情：")
        print("-" * 60)

        for i, link in enumerate(result['links'], 1):
            print(f"{i}. [{link['similarity']:.1%}] {link['title']}")
            print(f"   ID: {link['zettel_id']}")
            print(f"   核心概念: {link['core_concept'][:100]}...")
            print()
