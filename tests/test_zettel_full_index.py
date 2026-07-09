#!/usr/bin/env python3
"""
全量測試：索引所有 Zettelkasten 卡片到知識庫
"""
import sys
import io
from pathlib import Path
from datetime import datetime
import json

# ========== 防止卡住措施 1：強制 UTF-8 編碼 ==========
if sys.platform == 'win32' and sys.stdout.encoding != 'utf-8':
    pass  # 已移除 import 時的 stdout 劫持（會破壞 pytest capture / MCP stdio）
    pass  # 已移除 import 時的 stdout 劫持（會破壞 pytest capture / MCP stdio）
from claude_lit.knowledge_base import KnowledgeBaseManager

def main():
    print("=" * 70)
    print("全量 Zettelkasten 索引測試")
    print("=" * 70)
    print(f"測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    kb = KnowledgeBaseManager()

    # ========== 階段 1：掃描所有 Zettelkasten 資料夾 ==========
    print("[階段 1] 掃描 Zettelkasten 資料夾...")
    zettel_root = Path("output/zettelkasten_notes")

    if not zettel_root.exists():
        print(f"❌ 錯誤：資料夾不存在 {zettel_root}")
        return

    # 查找所有 zettel_* 資料夾
    zettel_folders = sorted([d for d in zettel_root.iterdir() if d.is_dir() and d.name.startswith('zettel_')])

    print(f"✅ 發現 {len(zettel_folders)} 個 Zettelkasten 資料夾\n")

    # ========== 階段 2：批次索引所有卡片 ==========
    print("[階段 2] 批次索引所有卡片...")
    print("-" * 70)

    total_stats = {
        'total_folders': len(zettel_folders),
        'total_cards': 0,
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'folders_success': 0,
        'folders_failed': 0,
        'errors': []
    }

    # ========== 防止卡住措施 2：容錯處理，不中斷 ==========
    for i, folder in enumerate(zettel_folders, 1):
        print(f"\n[{i}/{len(zettel_folders)}] 處理: {folder.name}")

        try:
            # 提取領域（如果可能）
            # 格式：zettel_Linguistics_20251029 或 zettel_Her2012a_20251029
            parts = folder.name.split('_')
            domain = None
            if len(parts) >= 2:
                if parts[1] in ['Linguistics', 'CogSci', 'AI']:
                    domain = parts[1]

            # 索引這個資料夾
            stats = kb.index_zettelkasten(str(folder), domain=domain)

            # 更新統計
            total_stats['total_cards'] += stats['total']
            total_stats['success'] += stats['success']
            total_stats['failed'] += stats['failed']
            total_stats['skipped'] += stats['skipped']

            if stats['success'] > 0:
                total_stats['folders_success'] += 1
                print(f"  ✅ 成功: {stats['success']}/{stats['total']} 張卡片")
            else:
                total_stats['folders_failed'] += 1
                print(f"  ❌ 失敗: 無卡片成功索引")

        except Exception as e:
            print(f"  ❌ 錯誤: {e}")
            total_stats['folders_failed'] += 1
            total_stats['errors'].append({
                'folder': folder.name,
                'error': str(e)
            })
            # 不中斷，繼續處理下一個資料夾
            continue

    # ========== 階段 3：自動關聯論文 ==========
    print("\n" + "=" * 70)
    print("[階段 3] 自動關聯卡片與論文...")
    print("-" * 70)

    try:
        link_stats = kb.auto_link_zettel_papers(similarity_threshold=0.7)
        print(f"✅ 關聯完成:")
        print(f"  - 已關聯: {link_stats['linked']}")
        print(f"  - 未匹配: {link_stats['unmatched']}")
        print(f"  - 跳過: {link_stats['skipped']}")
        total_stats['linking'] = link_stats
    except Exception as e:
        print(f"❌ 自動關聯失敗: {e}")
        total_stats['linking'] = {'error': str(e)}

    # ========== 階段 4：測試搜索功能 ==========
    print("\n" + "=" * 70)
    print("[階段 4] 測試搜索功能...")
    print("-" * 70)

    test_queries = [
        "mass noun",
        "語言學",
        "classifier",
        "mental simulation",
        "concept"
    ]

    search_results = {}
    for query in test_queries:
        try:
            results = kb.search_zettel(query, limit=5)
            search_results[query] = len(results)
            print(f"  查詢 '{query}': 找到 {len(results)} 個結果")

            # 顯示前2個結果
            for i, result in enumerate(results[:2], 1):
                print(f"    {i}. [{result['zettel_id']}] {result['title'][:50]}")

        except Exception as e:
            print(f"  ❌ 查詢 '{query}' 失敗: {e}")
            search_results[query] = -1

    total_stats['search_results'] = search_results

    # ========== 階段 5：生成測試報告 ==========
    print("\n" + "=" * 70)
    print("[階段 5] 生成測試報告")
    print("=" * 70)

    success_rate = (total_stats['success'] / total_stats['total_cards'] * 100) if total_stats['total_cards'] > 0 else 0

    report = f"""
📊 全量 Zettelkasten 索引測試報告
{'=' * 70}

⏱️  測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📁 資料夾統計:
  - 總資料夾數: {total_stats['total_folders']}
  - 成功處理: {total_stats['folders_success']}
  - 處理失敗: {total_stats['folders_failed']}

📝 卡片統計:
  - 總卡片數: {total_stats['total_cards']}
  - 成功索引: {total_stats['success']} ({success_rate:.1f}%)
  - 索引失敗: {total_stats['failed']}
  - 已跳過: {total_stats['skipped']}

🔗 論文關聯:
  - 已關聯: {total_stats['linking'].get('linked', 0)}
  - 未匹配: {total_stats['linking'].get('unmatched', 0)}
  - 跳過: {total_stats['linking'].get('skipped', 0)}

🔍 搜索測試:
  - 總查詢數: {len(test_queries)}
  - 成功查詢: {sum(1 for v in search_results.values() if v >= 0)}
  - 平均結果數: {sum(v for v in search_results.values() if v >= 0) / len(search_results):.1f}

✅ 驗收標準檢查:
  - 成功率 >95%: {'✅ PASS' if success_rate >= 95 else f'❌ FAIL ({success_rate:.1f}%)'}
  - 總卡片數 >600: {'✅ PASS' if total_stats['total_cards'] >= 600 else f'❌ FAIL ({total_stats["total_cards"]})'}
  - 搜索功能正常: {'✅ PASS' if all(v >= 0 for v in search_results.values()) else '❌ FAIL'}
  - 論文關聯 >0: {'✅ PASS' if total_stats['linking'].get('linked', 0) > 0 else '❌ FAIL'}

"""

    if total_stats['errors']:
        report += f"\n⚠️  錯誤列表 ({len(total_stats['errors'])} 個):\n"
        for err in total_stats['errors'][:10]:
            report += f"  - {err['folder']}: {err['error']}\n"

    print(report)

    # 保存報告
    report_file = f"ZETTEL_INDEX_TEST_REPORT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n💾 報告已保存: {report_file}")

    # 保存JSON統計
    json_file = report_file.replace('.md', '.json')
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(total_stats, f, ensure_ascii=False, indent=2)

    print(f"💾 JSON統計已保存: {json_file}")

    print("\n" + "=" * 70)
    print("測試完成！")
    print("=" * 70)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  測試被用戶中斷")
    except Exception as e:
        print(f"\n\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
