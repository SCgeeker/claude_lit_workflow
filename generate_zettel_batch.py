#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批次生成 Zettelkasten 卡片
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import shutil

# UTF-8 編碼
if sys.platform == 'win32':
    import io
    pass  # 已移除 import 時的 stdout 劫持（會破壞 pytest capture / MCP stdio）
    pass  # 已移除 import 時的 stdout 劫持（會破壞 pytest capture / MCP stdio）


from claude_lit.generators.zettel_maker import ZettelMaker
from claude_lit.generators.slide_maker import SlideMaker
from claude_lit.utils.config_loader import load_env_file
from jinja2 import Template


def extract_paper_content(md_path):
    """從 MD 文件提取論文內容"""
    import re
    content = md_path.read_text(encoding='utf-8')

    title_match = re.search(r"title:\s*['\"]?(.+?)['\"]?\s*$", content, re.MULTILINE)
    title = title_match.group(1) if title_match else "Unknown"

    authors_match = re.search(r"authors:\s*(.+?)$", content, re.MULTILINE)
    authors = authors_match.group(1) if authors_match else "Unknown"

    year_match = re.search(r"year:\s*(\d{4})", content)
    year = int(year_match.group(1)) if year_match else None

    # 提取完整內容（跳過 frontmatter）
    content_start = content.find('---', content.find('---') + 3) + 3
    full_content = content[content_start:].strip()

    return {
        'title': title,
        'authors': authors,
        'year': year,
        'content': full_content[:18000],  # 限制內容長度
        'cite_key': md_path.stem
    }


def generate_zettel(paper_data, llm_provider='google', model='gemini-2.0-flash'):
    """使用 LLM 生成 Zettelkasten 卡片"""
    print(f"\n{'='*70}")
    print(f"生成 Zettelkasten: {paper_data['cite_key']}")
    print(f"標題: {paper_data['title'][:60]}...")
    print(f"{'='*70}\n")

    # 初始化 SlideMaker（用於呼叫 LLM）
    print(f"初始化 LLM...")
    print(f"  Provider: {llm_provider}")
    print(f"  Model: {model}\n")

    slide_maker = SlideMaker(
        llm_provider=llm_provider,
        selection_strategy='balanced'
    )

    # 載入 Zettelkasten prompt 模板
    template_path = Path("templates/prompts/zettelkasten_template.jinja2")
    template = Template(template_path.read_text(encoding='utf-8'))

    # 生成 prompt
    prompt = template.render(
        topic=paper_data['title'],
        card_count=20,
        detail_level="comprehensive",
        paper_content=paper_data['content'],
        cite_key=paper_data['cite_key'],
        language="chinese"
    )

    print(f"Prompt 長度: {len(prompt)} 字元")
    print(f"生成 20 張卡片 (comprehensive 模式)\n")

    # 呼叫 LLM
    print("正在呼叫 LLM（預計 30-60 秒）...")
    result = slide_maker.call_llm(prompt, model=model, max_tokens=8192)

    if not result:
        print("❌ LLM 返回空響應")
        return None

    response, provider = result
    print(f"✅ LLM 響應 ({provider}): {len(response)} 字元\n")

    # 確定 cite_key（用於目錄名稱）
    cite_key = paper_data['cite_key']
    # 將檔名轉換為標準 cite_key 格式
    if cite_key.startswith("BEHAVIORAL"):
        cite_key = "Barsalou-1999"
    elif cite_key.startswith("Issues"):
        cite_key = "Friedrich-2025"

    # 建立輸出目錄
    date_str = datetime.now().strftime('%Y%m%d')
    model_name = model.split('/')[-1].replace('-', '_').replace('.', '_')
    output_dir = Path("output/zettelkasten_notes") / f"zettel_{cite_key}_{date_str}_{model_name}"

    if output_dir.exists():
        shutil.rmtree(output_dir)

    print(f"生成卡片到: {output_dir}")

    # 使用 ZettelMaker 生成卡片文件
    zettel_maker = ZettelMaker()

    # 建構引用格式
    authors_short = paper_data['authors'].split(',')[0].split()[0] if paper_data['authors'] else "Unknown"
    year_str = str(paper_data['year']) if paper_data['year'] else "n.d."
    citation = f"[[{cite_key}.pdf|{authors_short} et al. ({year_str})]]"

    result = zettel_maker.generate_zettelkasten(
        llm_output=response,
        output_dir=output_dir,
        paper_info={
            'cite_key': cite_key,
            'title': paper_data['title'],
            'authors': paper_data['authors'],
            'year': paper_data['year'],
            'citation': citation
        }
    )

    print(f"✅ 生成 {result['card_count']} 張卡片\n")
    print(f"✅ 生成完成: {output_dir}\n")

    return output_dir


def main():
    # 載入環境變數配置
    load_env_file()
    
    print("\n" + "="*70)
    print("Zettelkasten 批次生成")
    print("="*70 + "\n")

    # 要處理的論文
    papers = [
        Path("knowledge_base/papers/BEHAVIORAL_AND_BRAIN_SCIENCES1999_22577660.md"),
        Path("knowledge_base/papers/Issues_in_Grounded.md")
    ]

    results = []

    for md_path in papers:
        if not md_path.exists():
            print(f"❌ 找不到文件: {md_path}")
            continue

        # 提取論文內容
        paper_data = extract_paper_content(md_path)

        # 生成 Zettel 卡片
        output_dir = generate_zettel(
            paper_data,
            llm_provider='google',
            model='gemini-2.0-flash'
        )

        if output_dir:
            results.append((paper_data['cite_key'], output_dir))

    # 總結
    print("\n" + "="*70)
    print("生成總結")
    print("="*70)

    for cite_key, output_dir in results:
        print(f"  ✅ {cite_key}: {output_dir}")

    print(f"\n共生成 {len(results)} 個 Zettelkasten 資料夾")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
