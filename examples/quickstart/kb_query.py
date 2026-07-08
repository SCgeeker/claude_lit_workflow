#!/usr/bin/env python3
"""
快速開始：知識庫查詢範例
"""

from claude_lit.knowledge_base import KnowledgeBaseManager

kb = KnowledgeBaseManager()

# 搜索論文
results = kb.search_papers("deep learning medical")

# 查看統計
stats = kb.get_stats()
print(f"論文總數: {stats['total_papers']}")
