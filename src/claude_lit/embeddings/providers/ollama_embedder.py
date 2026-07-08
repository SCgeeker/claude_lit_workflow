#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama Embedding Provider
使用本地 Ollama 服務的 Qwen3-Embedding-4B 模型生成向量
"""

import time
import requests
import numpy as np
from typing import List, Union


class OllamaEmbedder:
    """Ollama Embedding Provider (Local/Free Fallback)"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3-embedding:4b",
        timeout: int = 120
    ):
        """
        初始化 Ollama Embedder

        Args:
            base_url: Ollama 服務 URL（默認：localhost:11434）
            model: 模型名稱（默認：qwen3-embedding:4b）
            timeout: API 超時時間（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout

        # 模型配置
        self.dimension = 2560  # Qwen3-Embedding-4B 維度
        self.max_tokens = 8192
        self.cost_per_1k_tokens = 0.0  # 本地模型免費

        # 速率限制配置（避免本地資源耗盡）
        self.requests_per_minute = 20  # 保守估計
        self.last_request_time = 0
        self.min_request_interval = 60.0 / self.requests_per_minute

        # 檢查服務可用性
        self._check_service()

    def _check_service(self):
        """檢查 Ollama 服務是否運行"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()

            # 檢查模型是否已下載
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]

            if self.model not in model_names:
                print(f"⚠️  模型 {self.model} 未安裝")
                print(f"   請執行: ollama pull {self.model}")

        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"無法連接到 Ollama 服務（{self.base_url}）\n"
                "請確認 Ollama 已啟動: ollama serve"
            )
        except Exception as e:
            raise RuntimeError(f"Ollama 服務檢查失敗: {e}")

    def _rate_limit(self):
        """速率限制：確保不超過每分鐘請求數"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def embed(self, text: str) -> np.ndarray:
        """
        嵌入單個文本

        Args:
            text: 輸入文本

        Returns:
            NumPy 向量（dtype=float32）
        """
        self._rate_limit()

        try:
            response = requests.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": text
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            # 提取 embedding
            data = response.json()

            # Ollama API 返回格式: {"embeddings": [[...]]}
            if 'embeddings' in data and len(data['embeddings']) > 0:
                embedding = data['embeddings'][0]
            elif 'embedding' in data:
                embedding = data['embedding']
            else:
                raise ValueError(f"無效的 API 響應格式: {data.keys()}")

            return np.array(embedding, dtype=np.float32)

        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Ollama API 超時（{self.timeout}秒）\n"
                "建議：縮短文本長度或增加 timeout 參數"
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ollama API 調用失敗: {e}")

    def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 10,
        show_progress: bool = True
    ) -> np.ndarray:
        """
        批次嵌入（逐個處理，本地模型不支援真批次）

        Args:
            texts: 文本列表
            batch_size: 每批次大小（用於進度顯示）
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

            # Ollama 不支援批次 API，需逐個處理
            for text in batch:
                try:
                    emb = self.embed(text)
                    embeddings.append(emb)
                except Exception as e:
                    if show_progress:
                        print(f"  ⚠️  文本嵌入失敗: {str(e)[:50]}...")
                    # 失敗時返回零向量
                    embeddings.append(np.zeros(self.dimension, dtype=np.float32))

        return np.array(embeddings, dtype=np.float32)

    def estimate_cost(self, texts: Union[str, List[str]]) -> float:
        """
        估算成本（本地模型永遠為 $0）

        Args:
            texts: 單個文本或文本列表

        Returns:
            預估成本（美元）
        """
        return 0.0  # 本地部署，無成本

    def estimate_time(self, texts: Union[str, List[str]]) -> float:
        """
        估算處理時間（基於實測性能）

        Args:
            texts: 單個文本或文本列表

        Returns:
            預估時間（秒）
        """
        if isinstance(texts, str):
            texts = [texts]

        # 基於實測：8.58 秒/文本（CPU推理）
        avg_time_per_text = 8.6
        rate_limit_overhead = len(texts) * self.min_request_interval

        return len(texts) * avg_time_per_text + rate_limit_overhead

    def get_info(self) -> dict:
        """獲取提供者資訊"""
        return {
            'provider': 'ollama',
            'model': self.model,
            'dimension': self.dimension,
            'max_tokens': self.max_tokens,
            'cost_per_1k_tokens': self.cost_per_1k_tokens,
            'base_url': self.base_url,
            'timeout': self.timeout,
            'service_available': self._is_service_available()
        }

    def _is_service_available(self) -> bool:
        """檢查服務當前是否可用"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return response.status_code == 200
        except:
            return False


if __name__ == "__main__":
    # 測試代碼
    print("Ollama Embedder 模組已載入")
    print("使用範例：")
    print("  embedder = OllamaEmbedder()")
    print("  embedding = embedder.embed('測試文本')")
    print()
    print("注意事項：")
    print("  1. 需要先啟動 Ollama: ollama serve")
    print("  2. 需要下載模型: ollama pull qwen3-embedding:4b")
    print("  3. CPU推理較慢（~8.6秒/文本）")
