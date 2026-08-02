#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zettelkasten 卡片生成命令行工具（薄殼）

參數解析與結果呈現在此層；編排邏輯在 src/api/zettel.py。
"""

import argparse
import sys
from pathlib import Path

# Windows cp950 防護：非 UTF-8 console 才重設（避免干擾 pytest capture）
try:
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 添加 src 到路徑


from claude_lit.api import LitWorkflowError, ZettelRequest, generate_zettel, list_options
from claude_lit.api.progress import ProgressEvent
from claude_lit.utils.config_loader import load_env_file

DETAIL_CHOICES = ['minimal', 'brief', 'standard', 'detailed', 'comprehensive']
LANGUAGE_CHOICES = ['chinese', 'english', 'bilingual']

_STAGE_ICONS = {
    'extract': '📄',
    'cross_link': '🔍',
    'prompt': '📋',
    'llm': '🤖',
    'parse': '📊',
    'write': '💾',
    'kb': '📥',
    'embed': '📊',
}


def _print_progress(event: ProgressEvent):
    icon = _STAGE_ICONS.get(event.stage, '⏳')
    print(f"{icon} {event.message}")


def load_custom_requirements(custom_file: str = None, default_file: str = None) -> str | None:
    """載入自訂需求：明確指定檔案 > 預設檔案"""
    if custom_file:
        path = Path(custom_file)
        if path.exists():
            print(f"📋 載入自訂需求：{path}")
            return path.read_text(encoding='utf-8')
        print(f"⚠️  警告：找不到自訂需求檔案 {path}")
        return None

    if default_file:
        path = Path(default_file)
        if path.exists():
            print(f"📋 載入預設需求：{path}")
            return path.read_text(encoding='utf-8')

    return None


def load_slides_content(slides_file: str) -> str | None:
    """載入投影片筆記內容（作為卡片生成參考）"""
    if not slides_file:
        return None

    path = Path(slides_file)
    if path.exists():
        content = path.read_text(encoding='utf-8')
        print(f"📊 載入投影片筆記：{path}")
        print(f"   （{len(content)} 字元，粗體標示將優先生成卡片）")
        return content
    print(f"⚠️  警告：找不到投影片筆記檔案 {path}")
    return None


def main():
    # 載入環境變數配置
    load_env_file()

    parser = argparse.ArgumentParser(
        description='Zettelkasten 卡片生成工具 - 從論文生成原子化知識卡片',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例用法：
  uv run zettel --pdf paper.pdf
  uv run zettel --from-kb 1
  uv run zettel --pdf paper.pdf --detail comprehensive
  uv run zettel --pdf paper.pdf --custom-file my_style.md
  uv run zettel --pdf paper.pdf --slides-file slides_output.md
  uv run zettel --pdf paper.pdf --no-add-to-kb
  uv run zettel --from-kb 1 --force
  uv run zettel --pdf paper.pdf --cross-link
        """
    )

    # 內容來源（互斥）
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument('--pdf', type=str, help='PDF 檔案路徑')
    source_group.add_argument('--url', type=str,
                              help='論文或網頁 URL（arXiv、DOI、出版商頁面或部落格）')
    source_group.add_argument('--from-kb', type=int, metavar='PAPER_ID',
                              help='從知識庫中的論文 ID 生成')

    parser.add_argument('--detail', type=str, default='standard',
                        choices=DETAIL_CHOICES, help='詳細程度（預設：standard）')
    parser.add_argument('--language', type=str, default='chinese',
                        choices=LANGUAGE_CHOICES, help='語言模式（預設：chinese）')
    parser.add_argument('--domain', type=str, default='Research',
                        help='領域代碼（如 NeuroPsy、AI，預設：Research）')
    parser.add_argument('--citekey', type=str, default=None,
                        help='手動指定 cite_key（Zotero bib 場景）')

    parser.add_argument('--custom-file', type=str, help='自訂需求檔案路徑（.txt 或 .md）')
    parser.add_argument('--no-custom', action='store_true', help='忽略預設自訂需求檔案')
    parser.add_argument('--slides-file', type=str, help='投影片筆記檔案路徑（作為卡片生成參考）')

    parser.add_argument('--no-add-to-kb', action='store_true', help='不將卡片加入知識庫（僅生成檔案）')
    parser.add_argument('--force', action='store_true', help='強制重新生成（刪除舊卡片後重新入庫）')
    parser.add_argument('--cross-link', action='store_true', help='啟用跨論文連結（查詢知識庫相關概念）')
    parser.add_argument('--no-embed', action='store_true', help='跳過向量嵌入（稍後用 uv run embeddings 補上）')
    parser.add_argument('--no-ground', action='store_true',
                        help='關閉 grounding 驗證（不抹除定位不到原文的卡片；供批量重跑/除錯）')

    parser.add_argument('--model', type=str, default=None, help='LLM 模型名稱（預設：自動選擇）')
    parser.add_argument('--llm-provider', type=str, default='auto',
                        choices=['auto', 'ollama', 'google', 'openai', 'anthropic', 'nvidia'],
                        help='LLM 提供者（預設：auto）')
    parser.add_argument('--selection-strategy', type=str, default='balanced',
                        choices=['balanced', 'quality_first', 'cost_first', 'speed_first'],
                        help='模型選擇策略（預設：balanced）')

    parser.add_argument('--output', type=str, help='輸出路徑（可選）')
    parser.add_argument('--list-options', action='store_true', help='列出所有可用選項')

    args = parser.parse_args()

    if args.list_options:
        catalog = list_options()
        print("\n📊 可用的詳細程度：")
        for key, desc in catalog.detail_levels.items():
            print(f"   • {key:15s} - {desc}")
        print("\n🌐 可用的語言模式：")
        for key, desc in catalog.languages.items():
            print(f"   • {key:15s} - {desc}")
        print()
        return 0

    print("=" * 70)
    print("🗂️  Zettelkasten 卡片生成工具")
    print("=" * 70)

    # 載入自訂需求與投影片筆記
    custom_requirements = None
    if not args.no_custom:
        custom_requirements = load_custom_requirements(
            custom_file=args.custom_file,
            default_file='config/custom_zettel.md',
        )
    slides_content = load_slides_content(args.slides_file)

    print(f"\n詳細程度：{args.detail}")
    print(f"語言：{args.language}")
    print(f"領域：{args.domain}")
    print(f"LLM 提供者：{args.llm_provider}")
    if args.no_add_to_kb:
        print(f"入庫：否")
    elif args.force:
        print(f"入庫：是（強制模式 - 將刪除舊卡片）")
    else:
        print(f"入庫：是")
    print(f"跨論文連結：{'是' if args.cross_link else '否'}")
    if custom_requirements:
        print(f"自訂需求：已載入（{len(custom_requirements)} 字元）")

    print("\n" + "=" * 70)

    try:
        request = ZettelRequest(
            pdf=args.pdf,
            url=args.url,
            from_kb=args.from_kb,
            detail=args.detail,
            language=args.language,
            domain=args.domain,
            cite_key=args.citekey,
            slides_content=slides_content,
            custom_requirements=custom_requirements,
            add_to_kb=not args.no_add_to_kb,
            force=args.force,
            cross_link=args.cross_link,
            embed=not args.no_embed,
            ground=not args.no_ground,
            provider=args.llm_provider,
            model=args.model,
            selection_strategy=args.selection_strategy,
            output_dir=args.output,
        )

        result = generate_zettel(request, progress=_print_progress)

        # 顯示結果
        print("\n" + "=" * 70)
        print("✅ Zettelkasten 原子筆記生成完成！")
        print("=" * 70)
        print(f"\n📁 輸出目錄：{result.output_dir}")
        print(f"📄 索引文件：{result.index_file}")
        print(f"🗂️  卡片數量：{result.card_count}")
        print(f"📝 詳細程度：{args.detail}")
        print(f"🌐 語言模式：{args.language}")
        print(f"🤖 使用 LLM：{result.provider_used}")

        print("\n📚 生成的卡片文件：")
        for i, card_file in enumerate(result.card_files[:5], 1):
            print(f"   {i}. {Path(card_file).name}")
        if len(result.card_files) > 5:
            print(f"   ... 以及其他 {len(result.card_files) - 5} 張卡片")

        if request.add_to_kb:
            print(f"\n📥 入庫：新增 {result.kb_added} 張卡片")
            if result.kb_skipped:
                print(f"   ⏭️  跳過 {result.kb_skipped} 張重複卡片")
            if result.embedded:
                print(f"   📊 嵌入 {result.embedded} 張卡片")

        for warning in result.warnings:
            print(f"⚠️  {warning}")

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
        print(f"\n❌ 未預期的錯誤：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
