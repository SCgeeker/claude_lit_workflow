#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置載入工具
從環境變數或 .env 檔案載入 LLM 連線設定
"""

import os
from pathlib import Path
from typing import Optional


def load_env_file(env_path: Optional[str] = None) -> None:
    """
    載入 .env 檔案到環境變數
    
    Args:
        env_path: .env 檔案路徑（預設：CLAUDE_LIT_HOME 或目前工作目錄下的 .env）
    """
    if env_path is None:
        home = os.getenv("CLAUDE_LIT_HOME")
        env_path = Path(home or Path.cwd()) / ".env"
    
    env_path = Path(env_path)
    if not env_path.exists():
        return
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳過空行和註解
            if line and not line.startswith('#'):
                # 處理 key=value 格式
                if '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    # 移除引號（如果有）
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    # 只在環境變數未設定時才設定
                    if key not in os.environ:
                        os.environ[key] = value


def get_ollama_url() -> str:
    """
    獲取 Ollama URL
    
    Returns:
        Ollama API URL（優先使用環境變數，否則使用預設值）
    """
    return os.getenv('OLLAMA_URL', 'http://localhost:11434')


def get_ollama_default_model() -> str:
    """
    獲取預設 Ollama 模型
    
    Returns:
        預設模型名稱
    """
    return os.getenv('OLLAMA_DEFAULT_MODEL', 'gpt-oss:20b-cloud')


def get_default_llm_provider() -> str:
    """
    獲取預設 LLM 提供者
    
    Returns:
        預設提供者（auto/ollama/google/openai/anthropic）
    """
    return os.getenv('DEFAULT_LLM_PROVIDER', 'auto')
