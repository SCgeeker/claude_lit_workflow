#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
測試腳本：卡片-論文關聯功能

用途：驗證 kb_manager.py 中的卡片-論文關聯方法
"""

import sys
import io
from pathlib import Path

# 強制 UTF-8 輸出（解決 Windows 編碼問題）
if sys.stdout.encoding != 'utf-8':
    pass  # 已移除 import 時的 stdout 劫持（會破壞 pytest capture / MCP stdio）
from claude_lit.knowledge_base.kb_manager import KnowledgeBaseManager


def test_manual_linking():
    """測試 1：手動關聯卡片與論文"""
    print(f"\n{'='*60}")
    print("測試 1：手動關聯卡片與論文")
    print(f"{'='*60}\n")

    kb = KnowledgeBaseManager()

    # 假設 card_id=1, paper_id=2 存在
    card_id = 1
    paper_id = 2

    # 執行手動關聯
    success = kb.link_zettel_to_paper(card_id, paper_id)

    if success:
        print(f"[OK] 成功關聯 card_id={card_id} → paper_id={paper_id}")

        # 驗證：查詢卡片
        card = kb.get_zettel_by_id("Linguistics-20251029-001")
        if card and card.get('paper_id') == paper_id:
            print(f"[OK] 驗證成功：卡片的 paper_id 已更新為 {paper_id}")
        else:
            print(f"[ERROR] 驗證失敗：卡片的 paper_id 不正確")
            return False

        # 驗證：查詢論文的卡片
        cards = kb.get_zettel_by_paper(paper_id)
        print(f"[OK] 論文 #{paper_id} 有 {len(cards)} 張關聯卡片")
        for card in cards[:3]:
            print(f"   - {card['zettel_id']}: {card['title'][:40]}")

        return True
    else:
        print(f"[ERROR] 關聯失敗")
        return False


def test_auto_linking():
    """測試 2：自動關聯卡片與論文"""
    print(f"\n{'='*60}")
    print("測試 2：自動關聯卡片與論文（基於 source_info 匹配）")
    print(f"{'='*60}\n")

    kb = KnowledgeBaseManager()

    # 先顯示現有論文和卡片
    papers = kb.list_papers(limit=5)
    print(f"現有論文 (前5篇):")
    for paper in papers:
        print(f"  #{paper['id']}: {paper['title'][:50]}")
    print()

    # 查詢未關聯的卡片
    import sqlite3
    conn = sqlite3.connect(kb.db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT card_id, zettel_id, source_info
        FROM zettel_cards
        WHERE paper_id IS NULL
        LIMIT 5
    """)
    unlinked = cursor.fetchall()
    conn.close()

    print(f"未關聯的卡片 (前5張):")
    for card_id, zettel_id, source_info in unlinked:
        print(f"  {zettel_id}: {source_info}")
    print()

    # 執行自動關聯
    print("執行自動關聯 (相似度閾值=0.5)...\n")
    stats = kb.auto_link_zettel_papers(similarity_threshold=0.5)

    print(f"\n{'='*60}")
    print(f"自動關聯結果")
    print(f"{'='*60}")
    print(f"  成功關聯: {stats['linked']}")
    print(f"  無匹配: {stats['unmatched']}")
    print(f"  跳過: {stats['skipped']}")
    print()

    return stats['linked'] > 0 or stats['unmatched'] > 0


def test_paper_metadata_update():
    """測試 3：從卡片更新論文元數據"""
    print(f"\n{'='*60}")
    print("測試 3：從卡片更新論文元數據")
    print(f"{'='*60}\n")

    kb = KnowledgeBaseManager()

    # 找一個有關聯卡片的論文
    import sqlite3
    conn = sqlite3.connect(kb.db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT paper_id
        FROM zettel_cards
        WHERE paper_id IS NOT NULL
        LIMIT 1
    """)
    result = cursor.fetchone()
    conn.close()

    if not result:
        print("[SKIP] 沒有已關聯的論文")
        return False

    paper_id = result[0]

    print(f"更新論文 #{paper_id} 的元數據...\n")

    # 執行更新
    update_stats = kb.update_paper_from_zettel(paper_id)

    print(f"[OK] 更新完成")
    print(f"   卡片數量: {update_stats['card_count']}")
    print(f"   卡片類型: {update_stats['card_types']}")
    print(f"   新增關鍵詞: {update_stats['new_keywords'][:5] if update_stats['new_keywords'] else '無'}")
    print(f"   完整度評分: {update_stats['completeness_score']}/100")
    print()

    return True


def test_paper_zettel_overview():
    """測試 4：論文-卡片統計總覽"""
    print(f"\n{'='*60}")
    print("測試 4：論文-卡片統計總覽")
    print(f"{'='*60}\n")

    kb = KnowledgeBaseManager()

    # 獲取所有論文的 Zettelkasten 統計
    stats_list = kb.get_paper_zettel_stats()

    if not stats_list:
        print("[WARN] 沒有論文有關聯的 Zettelkasten 卡片")
        return False

    print(f"共有 {len(stats_list)} 篇論文有關聯的 Zettelkasten 卡片\n")

    # 顯示前 10 篇
    print(f"{'Paper ID':<10} {'Cards':<8} {'Links':<8} {'完整度':<10} {'Title':<50}")
    print(f"{'-'*10} {'-'*8} {'-'*8} {'-'*10} {'-'*50}")

    for stat in stats_list[:10]:
        paper_id = stat['paper_id']
        title = stat['title'][:47] + '...' if len(stat['title']) > 50 else stat['title']
        card_count = stat['card_count']
        linked_cards = stat['linked_cards']
        completeness = stat['completeness']

        print(f"{paper_id:<10} {card_count:<8} {linked_cards:<8} {completeness:<10} {title:<50}")

    print()

    return True


def main():
    """主測試流程"""
    print(f"\n{'='*60}")
    print("卡片-論文關聯功能測試套件")
    print(f"{'='*60}")

    tests = [
        ("手動關聯", test_manual_linking),
        ("自動關聯", test_auto_linking),
        ("元數據更新", test_paper_metadata_update),
        ("統計總覽", test_paper_zettel_overview)
    ]

    results = {}

    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"[ERROR] {name} 測試失敗：{e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    # 總結
    print(f"\n{'='*60}")
    print("測試總結")
    print(f"{'='*60}")

    for name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}")

    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)

    print(f"\n總計: {passed_count}/{total_count} 通過")

    if passed_count == total_count:
        print("\n全部測試通過！")
    else:
        print("\n部分測試失敗，請檢查上方錯誤信息")


if __name__ == '__main__':
    main()
