#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速測試：檢查 Zettelkasten 解析是否正常
（添加了實時輸出和進度顯示）
"""

import sys
import io
import time
from pathlib import Path

# 強制 UTF-8 輸出
if sys.stdout.encoding != 'utf-8':
    pass  # 已移除 import 時的 stdout 劫持（會破壞 pytest capture / MCP stdio）
def print_flush(msg):
    """強制刷新輸出"""
    print(msg, flush=True)

def main():
    print_flush("\n" + "="*60)
    print_flush("快速測試：Zettelkasten 卡片解析")
    print_flush("="*60 + "\n")

    # 測試卡片路徑
    test_card = Path("output/zettelkasten_notes/zettel_Linguistics_20251029/zettel_cards/Linguistics-20251029-001.md")

    print_flush(f"[1/4] 檢查測試卡片是否存在...")
    if not test_card.exists():
        print_flush(f"❌ 測試卡片不存在: {test_card}")
        return
    print_flush(f"✅ 找到測試卡片: {test_card.name}\n")

    print_flush(f"[2/4] 讀取卡片內容...")
    try:
        with open(test_card, 'r', encoding='utf-8') as f:
            content = f.read()
        print_flush(f"✅ 讀取成功 ({len(content)} 字元)\n")
    except Exception as e:
        print_flush(f"❌ 讀取失敗: {e}")
        return

    print_flush(f"[3/4] 檢查文件格式...")
    if content.startswith('---'):
        print_flush("✅ YAML frontmatter 存在")
    else:
        print_flush("❌ 缺少 YAML frontmatter")
        return

    if '## 連結網絡' in content:
        print_flush("✅ 連結網絡區塊存在")
    else:
        print_flush("⚠️ 未找到連結網絡區塊")

    if '**核心**:' in content or '**[AI Agent]**:' in content:
        print_flush("✅ 核心概念和 AI 筆記存在\n")
    else:
        print_flush("⚠️ 缺少部分區塊\n")

    print_flush(f"[4/4] 測試知識庫解析器...")
    try:
        # 導入知識庫管理器
        sys.path.insert(0, str(Path(__file__).parent))
        from claude_lit.knowledge_base import KnowledgeBaseManager

        print_flush("✅ 知識庫模組導入成功")

        kb = KnowledgeBaseManager()
        print_flush("✅ 知識庫管理器初始化成功")

        # 測試解析
        result = kb.parse_zettel_card(str(test_card))

        if result:
            print_flush("\n✅ 解析成功！\n")
            print_flush("解析結果摘要:")
            print_flush(f"  - zettel_id: {result.get('zettel_id', 'N/A')}")
            print_flush(f"  - title: {result.get('title', 'N/A')[:50]}")
            print_flush(f"  - domain: {result.get('domain', 'N/A')}")
            print_flush(f"  - tags: {len(result.get('tags', []))} 個")
            print_flush(f"  - links: {len(result.get('links', []))} 組")
        else:
            print_flush("\n❌ 解析失敗（返回 None）")

    except ImportError as e:
        print_flush(f"❌ 無法導入知識庫模組: {e}")
    except Exception as e:
        print_flush(f"❌ 解析錯誤: {e}")
        import traceback
        traceback.print_exc()

    print_flush("\n" + "="*60)
    print_flush("測試完成")
    print_flush("="*60 + "\n")

if __name__ == '__main__':
    start_time = time.time()
    main()
    elapsed = time.time() - start_time
    print_flush(f"總耗時: {elapsed:.2f} 秒")
