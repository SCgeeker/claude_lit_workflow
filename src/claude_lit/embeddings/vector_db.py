#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量數據庫封裝 (ChromaDB)
提供語義搜索和混合搜索功能
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import chromadb
from chromadb.config import Settings


class VectorDatabase:
    """ChromaDB 向量數據庫封裝"""

    def __init__(self, persist_directory: str = "chroma_db"):
        """
        初始化向量數據庫

        Args:
            persist_directory: ChromaDB 持久化目錄
        """
        self.persist_directory = persist_directory
        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        # 初始化 ChromaDB 客戶端
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # 創建或獲取 collections
        self.papers_collection = self.client.get_or_create_collection(
            name="papers",
            metadata={"description": "論文向量集合"}
        )

        self.zettel_collection = self.client.get_or_create_collection(
            name="zettelkasten",
            metadata={"description": "Zettelkasten 卡片向量集合"}
        )

    def upsert_papers(
        self,
        embeddings: np.ndarray,
        documents: List[str],
        ids: List[str],
        metadatas: List[Dict]
    ):
        """
        插入或更新論文向量

        Args:
            embeddings: 向量矩陣 (shape: [n, dim])
            documents: 文本列表
            ids: ID 列表
            metadatas: 元數據列表
        """
        # 轉換為列表格式
        if isinstance(embeddings, np.ndarray):
            embeddings = embeddings.tolist()

        self.papers_collection.upsert(
            embeddings=embeddings,
            documents=documents,
            ids=ids,
            metadatas=metadatas
        )

    def upsert_zettel(
        self,
        embeddings: np.ndarray,
        documents: List[str],
        ids: List[str],
        metadatas: List[Dict]
    ):
        """
        插入或更新 Zettelkasten 卡片向量

        Args:
            embeddings: 向量矩陣 (shape: [n, dim])
            documents: 文本列表
            ids: ID 列表
            metadatas: 元數據列表
        """
        # 轉換為列表格式
        if isinstance(embeddings, np.ndarray):
            embeddings = embeddings.tolist()

        self.zettel_collection.upsert(
            embeddings=embeddings,
            documents=documents,
            ids=ids,
            metadatas=metadatas
        )

    def semantic_search_papers(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        where: Optional[Dict] = None
    ) -> Dict:
        """
        語義搜索論文

        Args:
            query_embedding: 查詢向量 (shape: [dim])
            n_results: 返回結果數量
            where: 元數據過濾條件

        Returns:
            搜索結果字典，包含 ids, documents, metadatas, distances
        """
        # 轉換為列表格式
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.tolist()

        results = self.papers_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where
        )

        return results

    def semantic_search_zettel(
        self,
        query_embedding: np.ndarray,
        n_results: int = 10,
        where: Optional[Dict] = None
    ) -> Dict:
        """
        語義搜索 Zettelkasten 卡片

        Args:
            query_embedding: 查詢向量 (shape: [dim])
            n_results: 返回結果數量
            where: 元數據過濾條件

        Returns:
            搜索結果字典，包含 ids, documents, metadatas, distances
        """
        # 轉換為列表格式
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.tolist()

        results = self.zettel_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where
        )

        return results

    def get_paper_by_id(self, paper_id: str) -> Optional[Dict]:
        """
        根據 ID 獲取論文

        Args:
            paper_id: 論文 ID（格式：paper_{id}）

        Returns:
            論文數據（embedding, document, metadata）或 None
        """
        try:
            results = self.papers_collection.get(
                ids=[paper_id],
                include=["embeddings", "documents", "metadatas"]
            )

            if results['ids']:
                return {
                    'id': results['ids'][0],
                    'embedding': results['embeddings'][0],
                    'document': results['documents'][0],
                    'metadata': results['metadatas'][0]
                }
            return None

        except Exception as e:
            print(f"獲取論文失敗: {e}")
            return None

    def get_zettel_by_id(self, zettel_id: str) -> Optional[Dict]:
        """
        根據 ID 獲取 Zettelkasten 卡片

        Args:
            zettel_id: 卡片 ID（格式：zettel_{id}）

        Returns:
            卡片數據（embedding, document, metadata）或 None
        """
        try:
            results = self.zettel_collection.get(
                ids=[zettel_id],
                include=["embeddings", "documents", "metadatas"]
            )

            if results['ids']:
                return {
                    'id': results['ids'][0],
                    'embedding': results['embeddings'][0],
                    'document': results['documents'][0],
                    'metadata': results['metadatas'][0]
                }
            return None

        except Exception as e:
            print(f"獲取卡片失敗: {e}")
            return None

    def find_similar_papers(
        self,
        paper_id: str,
        n_results: int = 10,
        exclude_self: bool = True
    ) -> Dict:
        """
        尋找相似論文

        Args:
            paper_id: 論文 ID
            n_results: 返回結果數量
            exclude_self: 是否排除自己

        Returns:
            相似論文結果
        """
        # 獲取論文向量
        paper = self.get_paper_by_id(paper_id)
        if not paper:
            return {'ids': [], 'documents': [], 'metadatas': [], 'distances': []}

        # 搜索相似
        if exclude_self:
            n_results += 1

        results = self.semantic_search_papers(
            query_embedding=np.array(paper['embedding']),
            n_results=n_results
        )

        # 移除自己
        if exclude_self and results['ids'] and len(results['ids']) > 0:
            if paper_id in results['ids'][0]:
                idx = results['ids'][0].index(paper_id)
                # 只處理列表類型的結果
                for key in ['ids', 'documents', 'metadatas', 'distances']:
                    if key in results and results[key] and len(results[key]) > 0:
                        if isinstance(results[key][0], list):
                            results[key][0].pop(idx)

        return results

    def find_similar_zettel(
        self,
        zettel_id: str,
        n_results: int = 10,
        exclude_self: bool = True
    ) -> Dict:
        """
        尋找相似 Zettelkasten 卡片

        Args:
            zettel_id: 卡片 ID
            n_results: 返回結果數量
            exclude_self: 是否排除自己

        Returns:
            相似卡片結果
        """
        # 獲取卡片向量
        zettel = self.get_zettel_by_id(zettel_id)
        if not zettel:
            return {'ids': [], 'documents': [], 'metadatas': [], 'distances': []}

        # 搜索相似
        if exclude_self:
            n_results += 1

        results = self.semantic_search_zettel(
            query_embedding=np.array(zettel['embedding']),
            n_results=n_results
        )

        # 移除自己
        if exclude_self and results['ids'] and len(results['ids']) > 0:
            if zettel_id in results['ids'][0]:
                idx = results['ids'][0].index(zettel_id)
                # 只處理列表類型的結果
                for key in ['ids', 'documents', 'metadatas', 'distances']:
                    if key in results and results[key] and len(results[key]) > 0:
                        if isinstance(results[key][0], list):
                            results[key][0].pop(idx)

        return results

    def get_stats(self) -> Dict:
        """
        獲取數據庫統計信息

        Returns:
            統計信息字典
        """
        return {
            'papers_count': self.papers_collection.count(),
            'zettel_count': self.zettel_collection.count(),
            'total_count': self.papers_collection.count() + self.zettel_collection.count()
        }

    def delete_paper(self, paper_id: str):
        """刪除論文向量"""
        self.papers_collection.delete(ids=[paper_id])

    def delete_zettel(self, zettel_id: str):
        """刪除 Zettelkasten 卡片向量"""
        self.zettel_collection.delete(ids=[zettel_id])

    def reset_papers(self):
        """清空論文集合"""
        self.client.delete_collection("papers")
        self.papers_collection = self.client.create_collection(
            name="papers",
            metadata={"description": "論文向量集合"}
        )

    def reset_zettel(self):
        """清空 Zettelkasten 集合"""
        self.client.delete_collection("zettelkasten")
        self.zettel_collection = self.client.create_collection(
            name="zettelkasten",
            metadata={"description": "Zettelkasten 卡片向量集合"}
        )

    def reset_all(self):
        """清空所有集合"""
        self.reset_papers()
        self.reset_zettel()


if __name__ == "__main__":
    # 測試代碼
    print("VectorDatabase 模組已載入")
    print("\n使用範例：")
    print("  db = VectorDatabase()")
    print("  db.upsert_papers(embeddings, documents, ids, metadatas)")
    print("  results = db.semantic_search_papers(query_embedding)")
    print("  stats = db.get_stats()")
