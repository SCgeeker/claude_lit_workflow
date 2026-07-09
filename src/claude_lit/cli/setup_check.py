#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定助手（薄殼）- 自動偵測可用的 LLM 提供者並提供設定建議

偵測邏輯在 src/api/providers.py；此層只負責呈現。

執行方式：
  uv run setup
"""

import os
import sys
from pathlib import Path

# Windows cp950 防護：非 UTF-8 console 才重設（避免干擾 pytest capture）
try:
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


from claude_lit.api import check_providers
from claude_lit.utils.config_loader import load_env_file


def check_env_file() -> bool:
    """確認 .env 檔案存在"""
    if Path('.env').exists():
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
    report = check_providers()
    for status in report.providers:
        icon = "✅" if status.available else "❌"
        print(f"  {icon}  {status.display_name:<22} {status.message}")

    # 3. 給出建議
    print()
    if not report.recommended:
        print("  ❌ 沒有可用的 LLM 提供者。")
        print("  請在 .env 中設定至少一個 API key，再重新執行 uv run setup。")
        return 1

    current = os.getenv('DEFAULT_LLM_PROVIDER', 'auto')
    print("=" * 60)
    print(f"  建議提供者: {report.recommended}")
    suggest_env_update(report.recommended, current)

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
