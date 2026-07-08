#!/usr/bin/env python3
"""
向量嵌入器使用範例
"""

from claude_lit.embeddings.providers import GeminiEmbedder, OllamaEmbedder

# === Google Gemini Embedder ===
print("=== Gemini Embedder ===")
gemini_embedder = GeminiEmbedder()

# 單個文本嵌入
embedding = gemini_embedder.embed("深度學習應用", task_type="retrieval_document")
print(f"嵌入維度: {len(embedding)}")

# 批次嵌入
texts = ["文本1", "文本2", "文本3"]
embeddings = gemini_embedder.embed_batch(texts, batch_size=100)
print(f"批次嵌入數量: {len(embeddings)}")

# 成本估算
cost = gemini_embedder.estimate_cost(texts)
print(f"預估成本: ${cost:.6f}")

# === Ollama Embedder ===
print("\n=== Ollama Embedder ===")
ollama_embedder = OllamaEmbedder()

# 檢查服務狀態
info = ollama_embedder.get_info()
print(f"服務可用: {info['service_available']}")
print(f"模型: {info['model']}")

# 嵌入文本
if info['service_available']:
    embedding = ollama_embedder.embed("測試文本")
    print(f"嵌入維度: {len(embedding)}")
