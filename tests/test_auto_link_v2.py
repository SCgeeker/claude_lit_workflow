#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_link_zettel_papers_v2() 测试脚本

测试改进版自动关联算法的三层匹配策略：
1. cite_key 精确匹配
2. 作者-年份-关键词匹配
3. 标题模糊匹配（fallback）
"""

import sys
import io
from pathlib import Path

# 修复Windows终端UTF-8编码
if sys.platform == 'win32':
    pass  # 已移除 import 時的 stdout 劫持（會破壞 pytest capture / MCP stdio）
# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from claude_lit.knowledge_base import KnowledgeBaseManager
import sqlite3


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def get_current_stats(kb: KnowledgeBaseManager):
    """获取当前关联统计"""
    conn = sqlite3.connect(kb.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN paper_id IS NOT NULL THEN 1 ELSE 0 END) as linked
        FROM zettel_cards
    """)

    row = cursor.fetchone()
    conn.close()

    return {
        'total': row[0],
        'linked': row[1],
        'unlinked': row[0] - row[1],
        'rate': (row[1] / row[0] * 100) if row[0] > 0 else 0
    }


def main():
    """主测试流程"""
    print_header("auto_link_zettel_papers_v2() 测试")

    # 初始化知识库
    kb = KnowledgeBaseManager()

    # 显示初始状态
    print_header("初始状态")
    stats_before = get_current_stats(kb)
    print(f"\n总卡片数: {stats_before['total']}")
    print(f"已关联: {stats_before['linked']} ({stats_before['rate']:.1f}%)")
    print(f"未关联: {stats_before['unlinked']}")

    # 执行自动关联
    print_header("执行 auto_link_v2")
    stats = kb.auto_link_zettel_papers_v2()

    # 显示结果
    print_header("测试结果")

    stats_after = get_current_stats(kb)

    print("\n关联统计:")
    print(f"  总卡片数: {stats_after['total']}")
    print(f"  已关联: {stats_after['linked']} ({stats_after['rate']:.1f}%)")
    print(f"  未关联: {stats_after['unlinked']}")

    print("\n本次执行统计:")
    print(f"  成功关联: {stats['linked']}")
    print(f"  - cite_key 匹配: {stats['method_breakdown']['cite_key']}")
    print(f"  - 作者-年份匹配: {stats['method_breakdown']['author_year']}")
    print(f"  - 标题模糊匹配: {stats['method_breakdown']['fuzzy_match']}")

    # 性能评估
    print_header("性能评估")

    total_processed = stats['linked'] + stats['unmatched']
    if total_processed > 0:
        success_rate = stats['linked'] / total_processed * 100
        print(f"\n本次成功率: {success_rate:.1f}%")

        if success_rate >= 50:
            print("✅ 成功率达到 50% 以上")
        
        print(f"\n相比初始状态:")
        print(f"  - 改进前: {stats_before['rate']:.1f}%")
        print(f"  - 改进后: {stats_after['rate']:.1f}%")
        print(f"  - 提升: {stats_after['rate'] - stats_before['rate']:.1f}%")

    print("\n" + "=" * 70)
    print("测试完成！")


if __name__ == "__main__":
    main()
