#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Gemini Embedding Provider
使用 Gemini Embedding-001 模型生成向量
"""

import os
import time
import numpy as np
from typing import List, Union

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class GeminiEmbedder:
    """Google Gemini Embedding Provider"""

    def __init__(self, api_key: str = None, model: str = "models/text-embedding-004"):
        """
        初始化 Gemini Embedder

        Args:
            api_key: Google API 金鑰（若未提供則從環境變數讀取）
            model: 模型名稱（默認：text-embedding-004）
        """
        if not GENAI_AVAILABLE:
            raise ImportError(
                "google-generativeai 未安裝。請執行：pip install google-generativeai"
            )

        # API 金鑰
        self.api_key = api_key or os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError(
                "未找到 Google API 金鑰。"
                "請設置環境變數 GOOGLE_API_KEY 或在初始化時提供 api_key 參數"
            )

        # 配置 API
        genai.configure(api_key=self.api_key)

        # 模型配置
        self.model = model
        self.dimension = 768  # Gemini text-embedding-004 默認維度
        self.max_tokens = 2048
        self.cost_per_1k_tokens = 0.00015

        # 速率限制配置（避免超過 API 限流）
        self.requests_per_minute = 60
        self.last_request_time = 0
        self.min_request_interval = 60.0 / self.requests_per_minute  # 約1秒

    def _rate_limit(self):
        """速率限制：確保不超過每分鐘請求數"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def embed(self, text: str, task_type: str = "retrieval_document") -> np.ndarray:
        """
        嵌入單個文本

        Args:
            text: 輸入文本
            task_type: 任務類型（retrieval_document/retrieval_query/等）

        Returns:
            NumPy 向量（dtype=float32）
        """
        self._rate_limit()

        try:
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type=task_type
            )

            # 提取 embedding
            embedding = result['embedding']
            return np.array(embedding, dtype=np.float32)

        except Exception as e:
            raise RuntimeError(f"Gemini API 調用失敗: {e}")

    def embed_batch(
        self,
        texts: List[str],
        task_type: str = "retrieval_document",
        batch_size: int = 100,
        show_progress: bool = True
    ) -> np.ndarray:
        """
        批次嵌入（支援大批量處理）

        Args:
            texts: 文本列表
            task_type: 任務類型
            batch_size: 每批次大小（Gemini 支援最多100個）
            show_progress: 是否顯示進度

        Returns:
            NumPy 向量矩陣（shape: [len(texts), dimension]）
        """
        if len(texts) == 0:
            return np.array([], dtype=np.float32)

        embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            batch_num = i // batch_size + 1

            if show_progress:
                print(f"  批次 {batch_num}/{total_batches}: {len(batch)} 個文本...")

            # 速率限制
            self._rate_limit()

            try:
                # Gemini 支援批次請求
                result = genai.embed_content(
                    model=self.model,
                    content=batch,
                    task_type=task_type
                )

                # 提取 embeddings
                batch_embeddings = result['embedding']

                # 處理返回格式
                if isinstance(batch_embeddings[0], list):
                    # 多個文本
                    embeddings.extend(batch_embeddings)
                else:
                    # 單個文本
                    embeddings.append(batch_embeddings)

            except Exception as e:
                print(f"  ❌ 批次 {batch_num} 失敗: {e}")
                # 失敗時返回零向量
                for _ in range(len(batch)):
                    embeddings.append([0.0] * self.dimension)

        return np.array(embeddings, dtype=np.float32)

    def estimate_cost(self, texts: Union[str, List[str]]) -> float:
        """
        估算成本

        Args:
            texts: 單個文本或文本列表

        Returns:
            預估成本（美元）
        """
        if isinstance(texts, str):
            texts = [texts]

        # 粗略估算 token 數（1 字 ≈ 1.3 tokens）
        total_chars = sum(len(text) for text in texts)
        total_tokens = total_chars * 1.3

        cost = (total_tokens / 1000) * self.cost_per_1k_tokens
        return cost

    def get_info(self) -> dict:
        """獲取提供者資訊"""
        return {
            'provider': 'google_gemini',
            'model': self.model,
            'dimension': self.dimension,
            'max_tokens': self.max_tokens,
            'cost_per_1k_tokens': self.cost_per_1k_tokens,
            'api_key_set': bool(self.api_key)
        }


if __name__ == "__main__":
    # 測試代碼
    print("Gemini Embedder 模組已載入")
    print("使用範例：")
    print("  embedder = GeminiEmbedder()")
    print("  embedding = embedder.embed('測試文本')")
