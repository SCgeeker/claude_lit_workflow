#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投影片生成命令行工具（薄殼）

參數解析與結果呈現在此層；編排邏輯在 src/api/slides.py。
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Windows cp950 防護：非 UTF-8 console 才重設（避免干擾 pytest capture）
try:
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 添加src到路徑


from claude_lit.api import (
    LitWorkflowError,
    SlideRequest,
    generate_slides,
    list_options,
)
from claude_lit.api.progress import ProgressEvent
from claude_lit.utils.prompt_loader import load_custom_requirements
from claude_lit.utils.config_loader import load_env_file, get_ollama_url
from claude_lit.utils.logger import logger

STYLE_CHOICES = [
    'classic_academic', 'modern_academic', 'clinical', 'research_methods',
    'literature_review', 'case_analysis', 'teaching',
]
DETAIL_CHOICES = ['minimal', 'brief', 'standard', 'detailed', 'comprehensive']
LANGUAGE_CHOICES = ['chinese', 'english', 'bilingual']

# 進度階段 → CLI 呈現訊息
_STAGE_ICONS = {
    'extract': '📄',
    'prompt': '📋',
    'llm': '🤖',
    'write': '💾',
}


def _print_progress(event: ProgressEvent):
    icon = _STAGE_ICONS.get(event.stage, '⏳')
    print(f"{icon} {event.message}")


def print_available_options():
    """顯示所有可用選項（來源：api.list_options，單一真相來源）"""
    catalog = list_options()

    print("\n📚 可用的學術風格：")
    for key, desc in catalog.slide_styles.items():
        print(f"   • {key:20s} - {desc}")

    print("\n📊 可用的詳細程度：")
    for key, desc in catalog.detail_levels.items():
        print(f"   • {key:15s} - {desc}")

    print("\n🌐 可用的語言模式：")
    for key, desc in catalog.languages.items():
        print(f"   • {key:15s} - {desc}")
    print()


def _analyze_first_content(pdf_path: Path) -> str:
    """--analyze-first 工作流：先分析入庫，再讀結構化 Markdown。回傳內容字串。"""
    print(f"\n📄 步驟1：分析PDF並加入知識庫...")
    result = subprocess.run(
        [sys.executable, 'analyze_paper.py', str(pdf_path), '--add-to-kb', '--format', 'json'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    if result.returncode != 0:
        print(f"❌ analyze_paper.py 執行失敗：")
        print(result.stderr)
        raise LitWorkflowError("analyze_paper.py 執行失敗")

    print(f"✅ 論文已加入知識庫")

    import re
    file_hash = None
    for line in result.stdout.strip().split('\n'):
        if 'file_hash' in line.lower() or '文件雜湊' in line:
            match = re.search(r'([a-f0-9]{32})', line)
            if match:
                file_hash = match.group(1)

    print(f"\n📚 步驟2：從結構化內容生成投影片...")
    if file_hash:
        md_path = Path('knowledge_base') / 'papers' / f"{file_hash}.md"
        if md_path.exists():
            print(f"✅ 使用結構化Markdown內容")
            return md_path.read_text(encoding='utf-8')
        print(f"⚠️  找不到Markdown，回退到直接提取")
    else:
        print(f"⚠️  無法獲取file_hash，回退到直接提取")
    return None  # None → API 層自行從 PDF 抽取


def main():
    # 載入環境變數配置
    load_env_file()

    parser = argparse.ArgumentParser(
        description='投影片生成工具 - 支援7種學術風格、5種詳細程度、3種語言',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用方式：
  # 使用 uv（推薦）
  uv run slides <主題> [選項]

範例：
  uv run slides "深度學習應用" --style modern_academic --slides 15
  uv run slides --pdf paper.pdf --style modern_academic --detail comprehensive
  uv run slides "論文簡報" --from-kb 1 --style modern_academic
  uv run slides "深度學習" --pdf paper.pdf --format markdown
  uv run slides --list-options
        """
    )

    parser.add_argument('topic', nargs='?', help='簡報主題')
    parser.add_argument('--pdf', type=str, help='PDF文件路徑（可選）')
    parser.add_argument('--url', type=str, help='論文或網頁 URL（arXiv、DOI、出版商頁面或部落格）')
    parser.add_argument('--analyze-first', action='store_true',
                       help='先分析PDF並加入知識庫，再從結構化內容生成投影片')
    parser.add_argument('--from-kb', type=int, metavar='PAPER_ID',
                       help='從知識庫中已有的論文ID生成投影片（不需要--pdf）')
    parser.add_argument('--style', type=str, default='modern_academic',
                       choices=STYLE_CHOICES, help='學術風格（預設：modern_academic）')
    parser.add_argument('--detail', type=str, default='standard',
                       choices=DETAIL_CHOICES, help='詳細程度（預設：standard）')
    parser.add_argument('--language', type=str, default='chinese',
                       choices=LANGUAGE_CHOICES, help='語言模式（預設：chinese）')
    parser.add_argument('--slides', type=int, default=15, help='投影片數量（預設：15）')
    parser.add_argument('--output', type=str, help='輸出路徑（可選）')
    parser.add_argument('--format', type=str, default='markdown',
                       choices=['pptx', 'markdown', 'both'],
                       help='輸出格式：pptx(PowerPoint)、markdown或both（預設：markdown）')
    parser.add_argument('--model', type=str, default=None,
                       help='LLM模型名稱（預設：None，使用智能選擇）')
    parser.add_argument('--llm-provider', type=str, default='auto',
                       choices=['auto', 'ollama', 'google', 'openai', 'anthropic', 'nvidia'],
                       help='LLM提供者（預設：auto自動選擇）')
    parser.add_argument('--api-key', type=str,
                       help='API金鑰（Google/OpenAI/Anthropic用，或設置環境變數）')
    parser.add_argument('--ollama-url', type=str, default=get_ollama_url(),
                       help='Ollama API地址（預設：從環境變數或 http://localhost:11434）')
    parser.add_argument('--custom', type=str, help='自訂要求（命令行直接輸入）')
    parser.add_argument('--custom-file', type=str, help='自訂需求檔案路徑（.txt 或 .md）')
    parser.add_argument('--no-custom', action='store_true', help='忽略預設自訂需求檔案')
    parser.add_argument('--list-options', action='store_true',
                       help='列出所有可用的風格、詳細程度和語言選項')
    parser.add_argument('--selection-strategy', type=str, default='balanced',
                       choices=['balanced', 'quality_first', 'cost_first', 'speed_first'],
                       help='模型選擇策略（預設：balanced）')
    parser.add_argument('--usage-report', action='store_true', help='生成使用報告（每日和週報）')

    args = parser.parse_args()
    logger.info(f"Started slides generation. Topic: {args.topic}, PDF: {args.pdf}, KB: {args.from_kb}")

    if args.list_options:
        print_available_options()
        return 0

    # 參數邏輯檢查（訊息與 exit code 與舊版一致）
    if not args.topic and not args.from_kb and not args.pdf and not args.url:
        parser.print_help()
        print("\n❌ 錯誤：請提供簡報主題、--from-kb、--pdf 或 --url")
        print("💡 提示：使用 --list-options 查看所有可用選項")
        return 1

    if args.from_kb and (args.pdf or args.url):
        print("\n❌ 錯誤：--from-kb 不能與 --pdf / --url 同時使用")
        return 1

    if args.pdf and args.url:
        print("\n❌ 錯誤：--pdf 和 --url 不能同時使用")
        return 1

    if args.analyze_first and not args.pdf:
        print("\n❌ 錯誤：--analyze-first 需要配合 --pdf 使用")
        return 1

    print("=" * 70)
    print("📊 投影片生成工具")
    print("=" * 70)
    if args.topic:
        topic_display = args.topic
    elif args.from_kb:
        topic_display = "（從知識庫論文標題）"
    elif args.pdf:
        topic_display = f"（從 PDF 推斷：{Path(args.pdf).stem}）"
    else:
        topic_display = "（未指定）"
    print(f"\n主題：{topic_display}")
    print(f"風格：{args.style}")
    print(f"詳細程度：{args.detail}")
    print(f"語言：{args.language}")
    print(f"投影片數：{args.slides}")
    print(f"LLM提供者：{args.llm_provider}")
    if args.llm_provider == 'auto':
        print(f"選擇策略：{args.selection_strategy}")

    # 載入自訂需求
    custom_requirements = None
    if not args.no_custom:
        custom_requirements = load_custom_requirements(
            custom_arg=args.custom,
            custom_file_arg=args.custom_file,
            default_file='config/custom_slides.md',
            verbose=True,
        )
    elif args.custom:
        custom_requirements = args.custom
        print(f"📋 使用命令行自訂需求（{len(args.custom)} 字元）")

    print("\n" + "=" * 70)

    try:
        # --analyze-first：CLI 層先跑分析工作流，取得結構化內容
        content = None
        pdf_arg = args.pdf
        if args.analyze_first and args.pdf:
            pdf_path = Path(args.pdf)
            if not pdf_path.exists():
                print(f"\n❌ 錯誤：找不到PDF文件：{args.pdf}")
                return 1
            content = _analyze_first_content(pdf_path)
            if content is not None:
                pdf_arg = None  # 已有結構化內容，不需再抽取 PDF

        request = SlideRequest(
            topic=args.topic,
            pdf=pdf_arg,
            url=args.url,
            from_kb=args.from_kb,
            content=content,
            style=args.style,
            detail=args.detail,
            language=args.language,
            slide_count=args.slides,
            output_format=args.format,
            output_path=args.output,
            provider=args.llm_provider,
            model=args.model,
            selection_strategy=args.selection_strategy,
            custom_requirements=custom_requirements,
        )

        result = generate_slides(
            request,
            progress=_print_progress,
            api_key=args.api_key,
            ollama_url=args.ollama_url,
        )

        # 顯示結果
        print("\n" + "=" * 70)
        print("✅ 投影片生成完成！")
        print("=" * 70)

        print(f"\n📁 輸出文件：")
        for file in result.output_files:
            file_type = "PPTX" if file.endswith('.pptx') else "Markdown"
            print(f"   • {file_type}: {file}")

        print(f"📊 投影片數量：{result.slide_count}")
        print(f"🎨 學術風格：{result.style}")
        print(f"📝 詳細程度：{result.detail}")
        print(f"🌐 語言模式：{result.language}")
        print(f"📄 輸出格式：{result.output_format}")
        print(f"🤖 使用LLM：{result.provider_used}")

        for warning in result.warnings:
            print(f"⚠️  {warning}")

        if result.preview:
            print("\n💡 LLM輸出預覽：")
            print("-" * 70)
            print(result.preview[:300] + "...")
            print("-" * 70)

        if args.usage_report:
            _generate_usage_report()

        return 0

    except LitWorkflowError as e:
        print(f"\n❌ {e}")
        if e.hint:
            print(f"💡 提示：{e.hint}")
        return 1

    except ImportError as e:
        print(f"\n❌ 缺少必要的套件：{e}")
        print("💡 提示：請運行 uv sync")
        return 1

    except Exception as e:
        logger.critical(f"Unhandled exception in make_slides: {e}", exc_info=True)
        print(f"\n❌ 未預期的錯誤：{e}")
        import traceback
        traceback.print_exc()
        return 1


def _generate_usage_report():
    print("\n" + "=" * 70)
    print("📊 生成使用報告...")
    print("=" * 70)

    from claude_lit.utils.usage_reporter import UsageReporter
    from datetime import datetime

    reporter = UsageReporter()
    daily_report = reporter.generate_daily_report()
    print("\n今日使用報告：")
    print("-" * 70)
    print(daily_report)

    date_str = datetime.now().strftime('%Y%m%d')
    reporter.save_report(daily_report, f"daily_{date_str}.md")
    weekly_report = reporter.generate_weekly_report()
    reporter.save_report(weekly_report, f"weekly_{date_str}.md")
    print("\n✅ 報告已保存到 logs/model_usage/reports/ 目錄")


if __name__ == "__main__":
    sys.exit(main())
