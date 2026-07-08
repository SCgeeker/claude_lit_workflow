"""
Embedding 模組
支援多種 embedding 提供者，統一管理向量生成和搜索
"""

from .embedding_manager import EmbeddingManager, create_manager
from .vector_db import VectorDatabase

__all__ = ['EmbeddingManager', 'create_manager', 'VectorDatabase']
