#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
測試腳本：Zettelkasten 批次索引功能

用途：驗證 kb_manager.py 中的 Zettelkasten 方法
"""

import sys
import io
from pathlib import Path

# 強制 UTF-8 輸出（解決 Windows 編碼問題）
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from claude_lit.knowledge_base.kb_manager import KnowledgeBaseManager


def test_single_card_parsing():
    """測試 1：解析單張卡片"""
    print(f"\n{'='*60}")
    print("測試 1：解析單張 Zettelkasten 卡片")
    print(f"{'='*60}\n")

    kb = KnowledgeBaseManager()

    test_card = "output/zettelkasten_notes/zettel_Linguistics_20251029/zettel_cards/Linguistics-20251029-001.md"

    if not Path(test_card).exists():
        print(f"[SKIP] 測試卡片不存在: {test_card}")
        return False

    # 解析卡片
    result = kb.parse_zettel_card(test_card)

    if result:
        print(f"[OK] 卡片解析成功")
        print(f"   zettel_id: {result['zettel_id']}")
        print(f"   title: {result['title']}")
        print(f"   domain: {result['domain']}")
        print(f"   card_type: {result['card_type']}")
        print(f"   tags: {result['tags']}")
        print(f"   core_concept: {result.get('core_concept', 'N/A')[:50]}...")
        print(f"   links: {len(result['links'])} 組")
        for link in result['links']:
            print(f"      {link['relation_type']} → {link['target_ids']}")
        print()
        return True
    else:
        print(f"[ERROR] 卡片解析失敗")
        return False


def test_add_single_card():
    """測試 2：新增單張卡片到資料庫"""
    print(f"\n{'='*60}")
    print("測試 2：新增單張卡片到資料庫")
    print(f"{'='*60}\n")

    kb = KnowledgeBaseManager()

    test_card = "output/zettelkasten_notes/zettel_Linguistics_20251029/zettel_cards/Linguistics-20251029-001.md"

    if not Path(test_card).exists():
        print(f"[SKIP] 測試卡片不存在: {test_card}")
        return False

    # 解析並新增
    card_data = kb.parse_zettel_card(test_card)

    if not card_data:
        print(f"[ERROR] 卡片解析失敗")
        return False

    result = kb.add_zettel_card(card_data)

    if result['status'] == 'inserted':
        print(f"[OK] 卡片新增成功")
        print(f"   card_id: {result['card_id']}")
        print(f"   zettel_id: {card_data['zettel_id']}")
        print()

        # 驗證：從資料庫讀取
        retrieved = kb.get_zettel_by_id(card_data['zettel_id'])

        if retrieved:
            print(f"[OK] 資料庫驗證成功")
            print(f"   標題: {retrieved['title']}")
            print(f"   領域: {retrieved['domain']}")
            print(f"   標籤: {retrieved['tags']}")
            print()

            # 驗證連結
            links = kb.get_zettel_links(result['card_id'])
            print(f"[OK] 連結信息: {len(links)} 條")
            for link in links:
                print(f"   {link['relation_type']} → {link['target_zettel_id']}")
            print()
            return True
        else:
            print(f"[ERROR] 資料庫驗證失敗：無法讀取卡片")
            return False
    elif result['status'] == 'duplicate':
        print(f"[DUPLICATE] 卡片已存在: {result['message']}")
        return True  # 重複不算失敗
    else:
        print(f"[ERROR] 卡片新增失敗: {result['message']}")
        return False


def test_batch_indexing():
    """測試 3：批次索引整個資料夾"""
    print(f"\n{'='*60}")
    print("測試 3：批次索引 Zettelkasten 資料夾")
    print(f"{'='*60}\n")

    kb = KnowledgeBaseManager()

    test_folder = "output/zettelkasten_notes/zettel_Linguistics_20251029"

    if not Path(test_folder).exists():
        print(f"[SKIP] 測試資料夾不存在: {test_folder}")
        return False

    # 批次索引
    print(f"開始索引資料夾: {test_folder}\n")
    stats = kb.index_zettelkasten(test_folder, domain="Linguistics")

    print(f"\n{'='*60}")
    print(f"批次索引結果")
    print(f"{'='*60}")
    print(f"  總數: {stats['total']}")
    print(f"  成功: {stats['success']}")
    print(f"  失敗: {stats['failed']}")
    print(f"  跳過: {stats['skipped']}")
    print(f"  card_ids: {stats['cards'][:5]}{'...' if len(stats['cards']) > 5 else ''}")
    print()

    return stats['success'] > 0


def test_full_text_search():
    """測試 4：全文搜索功能"""
    print(f"\n{'='*60}")
    print("測試 4：全文搜索 Zettelkasten 卡片")
    print(f"{'='*60}\n")

    kb = KnowledgeBaseManager()

    # 搜索測試
    test_queries = [
        ("mass noun", None, None),
        ("語言", "Linguistics", None),
        ("concept", None, "concept")
    ]

    for query, domain, card_type in test_queries:
        print(f"搜索: query=\"{query}\"", end="")
        if domain:
            print(f", domain=\"{domain}\"", end="")
        if card_type:
            print(f", card_type=\"{card_type}\"", end="")
        print()

        results = kb.search_zettel(query, limit=5, domain=domain, card_type=card_type)

        if results:
            print(f"   [OK] 找到 {len(results)} 張卡片")
            for i, card in enumerate(results[:3], 1):
                print(f"   {i}. {card['zettel_id']}: {card['title'][:50]}")
        else:
            print(f"   [WARN] 無搜索結果")
        print()

    return True


def main():
    """主測試流程"""
    print(f"\n{'='*60}")
    print("Zettelkasten 索引功能測試套件")
    print(f"{'='*60}")

    tests = [
        ("單張卡片解析", test_single_card_parsing),
        ("資料庫插入驗證", test_add_single_card),
        ("批次索引", test_batch_indexing),
        ("全文搜索", test_full_text_search)
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
