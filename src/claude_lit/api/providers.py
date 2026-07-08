# -*- coding: utf-8 -*-
"""LLM 供應商偵測與選項目錄 API

check_providers：逐一測試各供應商連線並回傳建議。
list_options：從 academic_styles.yaml 讀取風格 / 詳細程度 / 語言目錄（單一真相來源）。
"""

import os
from pathlib import Path
from typing import Tuple

from .models import OptionCatalog, ProviderReport, ProviderStatus
from .prompts import _load_styles_config


# 偵測用的預設 Gemini 模型；可經 GOOGLE_MODEL 環境變數覆寫，避免模型下架時需改碼
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _check_google() -> Tuple[bool, str]:
    key = os.getenv("GOOGLE_API_KEY", "")
    if not key or "your-" in key:
        return False, "未設定 GOOGLE_API_KEY"
    model_name = os.getenv("GOOGLE_MODEL") or DEFAULT_GEMINI_MODEL
    try:
        import google.generativeai as genai

        genai.configure(api_key=key)
        model = genai.GenerativeModel(model_name)
        model.generate_content("Hi", generation_config={"max_output_tokens": 5})
        return True, f"{model_name} 可用"
    except ImportError:
        return False, "缺少套件 google-generativeai"
    except Exception as e:
        return False, f"連線失敗: {str(e)[:60]}"


def _check_openai() -> Tuple[bool, str]:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or "your-" in key:
        return False, "未設定 OPENAI_API_KEY"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
        )
        return True, "gpt-4o-mini 可用"
    except ImportError:
        return False, "缺少套件 openai"
    except Exception as e:
        return False, f"連線失敗: {str(e)[:60]}"


def _check_anthropic() -> Tuple[bool, str]:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or "your-" in key:
        return False, "未設定 ANTHROPIC_API_KEY"
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "Hi"}],
        )
        return True, "claude-haiku-4-5 可用"
    except ImportError:
        return False, "缺少套件 anthropic"
    except Exception as e:
        return False, f"連線失敗: {str(e)[:60]}"


def _check_ollama() -> Tuple[bool, str]:
    url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        import requests

        resp = requests.get(f"{url}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            if models:
                names = [m["name"] for m in models[:3]]
                return True, f"{len(models)} 個模型可用: {', '.join(names)}"
            return True, "服務運行中（無已下載模型）"
        return False, f"HTTP {resp.status_code}"
    except ImportError:
        return False, "缺少套件 requests"
    except Exception as e:
        return False, f"無法連線 {url}: {str(e)[:50]}"


PROVIDERS = [
    ("google", "Google Gemini", _check_google),
    ("openai", "OpenAI", _check_openai),
    ("anthropic", "Anthropic Claude", _check_anthropic),
    ("ollama", "Ollama（本地）", _check_ollama),
]

# 優先順序：速度與成本平衡
PRIORITY = ["google", "anthropic", "openai", "ollama"]


def check_providers() -> ProviderReport:
    """檢查各 LLM 供應商可用性，回傳報告與建議供應商。"""
    statuses = []
    available = []
    for key, display_name, check_fn in PROVIDERS:
        ok, msg = check_fn()
        statuses.append(
            ProviderStatus(name=key, display_name=display_name, available=ok, message=msg)
        )
        if ok:
            available.append(key)

    recommended = next((p for p in PRIORITY if p in available), None)
    if recommended is None and available:
        recommended = available[0]

    return ProviderReport(
        providers=statuses,
        recommended=recommended,
        env_file_exists=Path(".env").exists(),
    )


def list_options() -> OptionCatalog:
    """回傳風格 / 詳細程度 / 語言目錄（鍵 → 「名稱 - 說明」）。"""
    config = _load_styles_config()

    slide_styles = {
        key: f"{info.get('name', key)} - {info.get('description', '')}"
        for key, info in config.get("styles", {}).items()
        if key != "zettelkasten"  # zettelkasten 為卡片生成內部風格，非投影片選項
    }
    detail_levels = {
        key: f"{info.get('name', key)} - {info.get('description', '')}"
        for key, info in config.get("detail_levels", {}).items()
    }
    languages = {
        key: info.get("name", key) for key, info in config.get("languages", {}).items()
    }
    return OptionCatalog(
        slide_styles=slide_styles, detail_levels=detail_levels, languages=languages
    )
