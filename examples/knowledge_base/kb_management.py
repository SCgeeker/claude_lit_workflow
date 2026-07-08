#!/usr/bin/env python3
"""
知識庫管理範例
"""

from claude_lit.knowledge_base import KnowledgeBaseManager

kb = KnowledgeBaseManager()

# 新增論文
paper_id = kb.add_paper(
    file_path="papers/smith_2024.md",
    title="Deep Learning for Medical Diagnosis",
    authors=["John Smith", "Jane Doe"],
    year=2024,
    keywords=["deep learning", "medical"],
    content="完整內容..."
)

# 全文搜索
results = kb.search_papers("deep learning", limit=10)

# 主題管理
topic_id = kb.add_topic("深度學習")
kb.link_paper_to_topic(paper_id, topic_id)

# 創建Markdown筆記
md_path = kb.create_markdown_note(paper_data)

print(f"論文ID: {paper_id}")
print(f"主題ID: {topic_id}")
print(f"筆記路徑: {md_path}")
