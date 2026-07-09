#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成 Jones-2024 Zettelkasten (使用 Google Gemini)
"""

import shutil
from pathlib import Path
from datetime import datetime
from claude_lit.generators.zettel_maker import ZettelMaker
from claude_lit.generators.slide_maker import SlideMaker

def extract_paper_content(md_path):
    """从 MD 文件提取论文内容"""
    content = md_path.read_text(encoding='utf-8')

    import re
    title_match = re.search(r"title:\s*['\"]?(.+?)['\"]?\s*$", content, re.MULTILINE)
    title = title_match.group(1) if title_match else "Unknown"

    authors_match = re.search(r"authors:\s*(.+?)$", content, re.MULTILINE)
    authors = authors_match.group(1) if authors_match else "Unknown"

    year_match = re.search(r"year:\s*(\d{4})", content)
    year = int(year_match.group(1)) if year_match else None

    content_start = content.find('---', content.find('---') + 3) + 3
    full_content = content[content_start:].strip()

    return {
        'title': title,
        'authors': authors,
        'year': year,
        'content': full_content[:15000],
        'cite_key': md_path.stem
    }

def generate_zettel(paper_data):
    """生成 Zettelkasten"""
    print(f"\n{'='*70}")
    print(f"生成 Zettelkasten: {paper_data['cite_key']}")
    print(f"标题: {paper_data['title'][:60]}...")
    print(f"{'='*70}\n")

    # 初始化 SlideMaker (使用 Google Gemini)
    slide_maker = SlideMaker(llm_provider='google')
    print(f"LLM Provider: google")
    print(f"Model: gemini-2.0-flash-exp\n")

    # 准备 prompt
    from jinja2 import Template
    template_path = Path("templates/prompts/zettelkasten_template.jinja2")
    template = Template(template_path.read_text(encoding='utf-8'))

    prompt = template.render(
        topic=paper_data['title'],
        card_count=20,
        detail_level="comprehensive",
        paper_content=paper_data['content'],
        cite_key=paper_data['cite_key']
    )

    print(f"Prompt 长度: {len(prompt)} 字符")
    print(f"生成 20 张卡片 (comprehensive 模式)\n")

    # 调用 LLM
    print("正在调用 Google Gemini...")
    result = slide_maker.call_llm(prompt, provider='google', model='gemini-2.0-flash-exp')

    if not result:
        print("❌ LLM 返回空响应")
        return None

    response, provider = result
    print(f"✅ LLM 响应 ({provider}): {len(response)} 字符\n")

    # === 診斷日誌: 保存 LLM 原始輸出 ===
    debug_output_path = Path("llm_raw_output_jones2024.txt")
    debug_output_path.write_text(response, encoding='utf-8')
    print(f"🔍 診斷: LLM 原始輸出已保存到 {debug_output_path}\n")

    # 生成卡片文件
    output_dir = Path("output/zettelkasten_notes") / f"zettel_{paper_data['cite_key']}_{datetime.now().strftime('%Y%m%d')}_gemini"

    if output_dir.exists():
        shutil.rmtree(output_dir)

    print(f"生成卡片到: {output_dir}")

    zettel_maker = ZettelMaker()
    result = zettel_maker.generate_zettelkasten(
        llm_output=response,
        output_dir=output_dir,
        paper_info={
            'cite_key': paper_data['cite_key'],
            'title': paper_data['title'],
            'authors': paper_data['authors'],
            'year': paper_data['year']
        }
    )

    print(f"✅ 生成 {result['card_count']} 张卡片")
    print(f"\n✅ 生成完成: {output_dir}\n")

    return output_dir

def main():
    print("\n" + "="*70)
    print("生成 Jones-2024 Zettelkasten (Google Gemini)")
    print("="*70 + "\n")

    # 读取论文
    md_path = Path("knowledge_base/papers/Jones-2024.md")
    if not md_path.exists():
        print(f"❌ 文件不存在: {md_path}")
        return

    print(f"📄 读取论文: {md_path}")
    paper_data = extract_paper_content(md_path)
    print(f"✅ 提取成功")
    print(f"   标题: {paper_data['title']}")
    print(f"   作者: {paper_data['authors']}")
    print(f"   年份: {paper_data['year']}\n")

    # 生成卡片
    output_dir = generate_zettel(paper_data)

    if output_dir:
        print("="*70)
        print("下一步:")
        print("="*70)
        print("1. 查看生成的卡片:")
        print(f"   ls {output_dir}/zettel_cards/")
        print("2. 检查第一张卡片:")
        print(f"   cat \"{output_dir}/zettel_cards/Jones-2024-001.md\"")
        print("3. 分析连结数量:")
        print("   python analyze_card_links.py")

if __name__ == '__main__':
    main()
