"""
Embedding Providers
支援多種 embedding 服務提供者
"""

from .gemini_embedder import GeminiEmbedder
from .ollama_embedder import OllamaEmbedder

__all__ = ['GeminiEmbedder', 'OllamaEmbedder']
