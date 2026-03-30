#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定助手 - 自動偵測可用的 LLM 提供者並提供設定建議

執行方式：
  uv run setup
  python setup.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from utils.config_loader import load_env_file


# ── LLM 提供者測試 ──────────────────────────────────────────────────────────

def test_google() -> tuple[bool, str]:
    """測試 Google Gemini 連線"""
    key = os.getenv('GOOGLE_API_KEY', '')
    if not key or 'your-' in key:
        return False, "未設定 GOOGLE_API_KEY"
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        model.generate_content("Hi", generation_config={"max_output_tokens": 5})
        return True, "gemini-2.0-flash-exp 可用"
    except ImportError:
        return False, "缺少套件 google-generativeai"
    except Exception as e:
        return False, f"連線失敗: {str(e)[:60]}"


def test_openai() -> tuple[bool, str]:
    """測試 OpenAI 連線"""
    key = os.getenv('OPENAI_API_KEY', '')
    if not key or 'your-' in key:
        return False, "未設定 OPENAI_API_KEY"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5
        )
        return True, "gpt-4o-mini 可用"
    except ImportError:
        return False, "缺少套件 openai"
    except Exception as e:
        return False, f"連線失敗: {str(e)[:60]}"


def test_anthropic() -> tuple[bool, str]:
    """測試 Anthropic Claude 連線"""
    key = os.getenv('ANTHROPIC_API_KEY', '')
    if not key or 'your-' in key:
        return False, "未設定 ANTHROPIC_API_KEY"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "Hi"}]
        )
        return True, "claude-haiku-4-5 可用"
    except ImportError:
        return False, "缺少套件 anthropic"
    except Exception as e:
        return False, f"連線失敗: {str(e)[:60]}"


def test_ollama() -> tuple[bool, str]:
    """測試 Ollama 本地服務連線"""
    url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
    try:
        import requests
        resp = requests.get(f"{url}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get('models', [])
            if models:
                names = [m['name'] for m in models[:3]]
                return True, f"{len(models)} 個模型可用: {', '.join(names)}"
            return True, "服務運行中（無已下載模型）"
        return False, f"HTTP {resp.status_code}"
    except ImportError:
        return False, "缺少套件 requests"
    except Exception as e:
        return False, f"無法連線 {url}: {str(e)[:50]}"


# ── 主程式 ──────────────────────────────────────────────────────────────────

PROVIDERS = [
    ('google',    'Google Gemini',    test_google),
    ('openai',    'OpenAI',           test_openai),
    ('anthropic', 'Anthropic Claude', test_anthropic),
    ('ollama',    'Ollama（本地）',    test_ollama),
]

# 優先順序：速度與成本平衡
PRIORITY = ['google', 'anthropic', 'openai', 'ollama']


def check_env_file() -> bool:
    """確認 .env 檔案存在"""
    env_path = Path('.env')
    if env_path.exists():
        return True
    print("\n  未找到 .env 檔案")
    print("  請執行以下指令建立：")
    print()
    print("    cp .env.example .env   # macOS / Linux")
    print("    copy .env.example .env # Windows")
    print()
    print("  再填入至少一個 LLM API key。")
    return False


def show_workflow():
    """顯示建議的使用流程"""
    print("""
  推薦工作流程：
  ─────────────────────────────────────────────────
  1. 準備 PDF 論文
  2. uv run slides --pdf paper.pdf       生成投影片
  3. （在筆記 App 中手動編修投影片）
  4. uv run zettel --pdf paper.pdf \\
          --slides-file output/slides.md  生成原子卡片
  5. 將 output/ 資料夾匯入筆記 App
  ─────────────────────────────────────────────────
""")


def suggest_env_update(recommended: str, current: str):
    """提示使用者更新 .env 設定"""
    if current == recommended or (current == 'auto' and recommended):
        print(f"  目前 DEFAULT_LLM_PROVIDER={current}，設定正常。")
    else:
        print(f"  目前設定: DEFAULT_LLM_PROVIDER={current}")
        print(f"  建議改為: DEFAULT_LLM_PROVIDER={recommended}")
        print(f"  請編輯 .env 檔案更新此設定。")


def main() -> int:
    load_env_file()

    print()
    print("=" * 60)
    print("  Claude Lit Workflow — 環境設定檢查")
    print("=" * 60)

    # 1. 確認 .env 存在
    if not check_env_file():
        return 1

    # 2. 測試各 LLM 提供者
    print("\n  正在測試 LLM 提供者連線...\n")
    available = []
    for key, name, test_fn in PROVIDERS:
        ok, msg = test_fn()
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {name:<22} {msg}")
        if ok:
            available.append(key)

    # 3. 給出建議
    print()
    if not available:
        print("  ❌ 沒有可用的 LLM 提供者。")
        print("  請在 .env 中設定至少一個 API key，再重新執行 uv run setup。")
        return 1

    recommended = next((p for p in PRIORITY if p in available), available[0])
    current = os.getenv('DEFAULT_LLM_PROVIDER', 'auto')

    print("=" * 60)
    print(f"  建議提供者: {recommended}")
    suggest_env_update(recommended, current)

    # 4. 自訂設定提示
    custom_slides = Path('config/custom_slides.md')
    custom_zettel = Path('config/custom_zettel.md')
    print()
    if custom_slides.exists() and custom_zettel.exists():
        print("  自訂需求檔案已就緒：")
        print(f"    config/custom_slides.md — 投影片風格與術語")
        print(f"    config/custom_zettel.md — 卡片撰寫規則")
        print("  （根據你的研究領域編輯這兩個檔案以獲得最佳輸出）")
    else:
        print("  ⚠️  找不到自訂需求檔案，將使用預設設定。")

    # 5. 工作流程說明
    show_workflow()

    print("=" * 60)
    print("  設定完成。可開始使用工具。")
    print("=" * 60)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
