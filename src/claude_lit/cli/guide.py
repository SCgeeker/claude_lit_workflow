#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用嚮導 CLI（薄殼）

  uv run guide                              # 印出完整工具使用說明（可貼到任何 LLM）
  uv run guide "把 paper.pdf 做成教學風格投影片" --provider nvidia
"""

import argparse
import sys

# Windows cp950 防護：非 UTF-8 console 才重設（避免干擾 pytest capture）
try:
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from claude_lit.api import LitWorkflowError, build_usage_guide, suggest_command
from claude_lit.utils.config_loader import load_env_file


def main():
    load_env_file()

    parser = argparse.ArgumentParser(
        prog="guide",
        description="工具使用嚮導：導出使用說明，或用指定 LLM 依需求回覆建議指令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  uv run guide                                          # 印出使用說明
  uv run guide "把 paper.pdf 做成教學風格投影片"
  uv run guide "從 PDF 生成完整原子卡片" --provider nvidia
        """,
    )
    parser.add_argument("request", nargs="?", help="自然語言需求（省略時只印出使用說明）")
    parser.add_argument(
        "--provider", type=str, default="auto",
        choices=["auto", "ollama", "google", "openai", "anthropic", "nvidia"],
        help="用哪個 LLM 供應商回覆建議（預設：auto）",
    )
    parser.add_argument("--model", type=str, default=None, help="指定模型名稱（可選）")
    args = parser.parse_args()

    # 無需求 → 印出使用說明
    if not args.request:
        print(build_usage_guide())
        return 0

    # 有需求 → 用指定供應商回覆建議指令
    print(f"🤔 正在請 {args.provider} 依你的需求建議指令...\n")
    try:
        result = suggest_command(args.request, provider=args.provider, model=args.model)
    except LitWorkflowError as e:
        print(f"\n❌ {e}")
        if e.hint:
            print(f"💡 提示：{e.hint}")
        return 1
    except Exception as e:
        print(f"\n❌ 未預期的錯誤：{e}")
        return 1

    print("=" * 70)
    print(f"🤖 {result.provider_used} 的建議：")
    print("=" * 70)
    print(result.suggestion)
    print("\n" + "-" * 70)
    print("💡 這是建議指令，請確認後自行複製執行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
