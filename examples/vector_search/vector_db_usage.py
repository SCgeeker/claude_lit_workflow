#!/usr/bin/env python3
"""
向量數據庫使用範例
"""

from claude_lit.embeddings.vector_db import VectorDatabase
import numpy as np

db = VectorDatabase(persist_directory="chroma_db")

# === 插入/更新論文向量 ===
embeddings = np.random.rand(2, 768).tolist()  # 示例向量
texts = ["論文內容1", "論文內容2"]
ids = ["paper_1", "paper_2"]
metadatas = [
    {"title": "論文1", "year": 2023},
    {"title": "論文2", "year": 2024}
]

db.upsert_papers(
    embeddings=embeddings,
    documents=texts,
    ids=ids,
    metadatas=metadatas
)

# === 語義搜索論文 ===
query_vec = np.random.rand(768).tolist()
results = db.semantic_search_papers(
    query_embedding=query_vec,
    n_results=10,
    where={"year": {"$gte": 2020}}  # 可選過濾條件
)
print(f"搜索結果: {len(results['ids'][0])} 篇論文")

# === 尋找相似論文 ===
similar = db.find_similar_papers(
    paper_id="paper_1",
    n_results=5,
    exclude_self=True
)
print(f"相似論文: {len(similar['ids'][0])} 篇")

# === 統計信息 ===
stats = db.get_stats()
print(f"\n數據庫統計:")
print(f"  論文向量數: {stats['papers_count']}")
print(f"  Zettelkasten 向量數: {stats['zettel_count']}")
