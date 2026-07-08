#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重新生成 Zettelkasten 卡片 - 测试新 template
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from claude_lit.generators.zettel_maker import ZettelMaker
from claude_lit.integrations.llm_provider import LLMProvider

def backup_existing_cards(paper_dir):
    """备份现有卡片"""
    if not paper_dir.exists():
        print(f"Error: {paper_dir} does not exist")
        return False

    backup_dir = paper_dir.parent / f"{paper_dir.name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Backing up {paper_dir} to {backup_dir}")

    shutil.copytree(paper_dir, backup_dir)
    print(f"Backup complete: {backup_dir}")

    return True

def load_paper_content(paper_id):
    """从知识库加载论文内容"""
    import sqlite3

    conn = sqlite3.connect('knowledge_base/index.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT file_path, title, authors, year, cite_key, abstract, keywords
        FROM papers
        WHERE id = ?
    """, (paper_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"Error: Paper ID {paper_id} not found")
        return None

    file_path, title, authors, year, cite_key, abstract, keywords = row

    # 读取 Markdown 文件
    md_path = Path(file_path)
    if not md_path.exists():
        print(f"Error: {md_path} does not exist")
        return None

    content = md_path.read_text(encoding='utf-8')

    return {
        'cite_key': cite_key,
        'title': title,
        'authors': authors,
        'year': year,
        'abstract': abstract,
        'keywords': keywords,
        'content': content,
        'file_path': str(md_path)
    }

def generate_zettelkasten_with_new_template(paper_data):
    """使用新 template 生成 Zettelkasten"""
    print("\n" + "=" * 70)
    print(f"Generating Zettelkasten for: {paper_data['cite_key']}")
    print("=" * 70)

    # 初始化 LLM Provider
    llm = LLMProvider(
        provider='auto',  # 自动选择可用的 provider
        model=None  # 使用默认模型
    )

    print(f"Using LLM: {llm.provider} / {llm.model}")

    # 初始化 ZettelMaker
    zettel_maker = ZettelMaker()

    # 准备 prompt template 路径
    prompt_template_path = Path("templates/prompts/zettelkasten_template.jinja2")

    if not prompt_template_path.exists():
        print(f"Error: {prompt_template_path} does not exist")
        return None

    # 读取 template
    from jinja2 import Template
    template = Template(prompt_template_path.read_text(encoding='utf-8'))

    # 准备 template 变量
    topic = paper_data['title']
    card_count = 20  # 保持与原始相同的数量
    detail_level = "comprehensive"  # 使用 comprehensive 模式

    # 生成 prompt
    prompt = template.render(
        topic=topic,
        card_count=card_count,
        detail_level=detail_level,
        paper_content=paper_data['content'][:15000],  # 限制内容长度
        cite_key=paper_data['cite_key']
    )

    print(f"\nPrompt length: {len(prompt)} chars")
    print(f"Requesting {card_count} cards...")

    # 调用 LLM 生成卡片
    print("\nCalling LLM...")
    response = llm.generate(prompt)

    if not response:
        print("Error: LLM returned empty response")
        return None

    print(f"LLM response length: {len(response)} chars")

    # 解析 LLM 输出
    print("\nParsing LLM output...")
    cards = zettel_maker.parse_llm_output(response)

    if not cards:
        print("Error: Failed to parse LLM output")
        # 保存原始输出以便调试
        debug_file = Path(f"output/debug_llm_output_{paper_data['cite_key']}.txt")
        debug_file.parent.mkdir(exist_ok=True, parents=True)
        debug_file.write_text(response, encoding='utf-8')
        print(f"Debug output saved to: {debug_file}")
        return None

    print(f"Parsed {len(cards)} cards")

    # 生成输出目录
    output_dir = Path("output/zettelkasten_notes") / f"zettel_{paper_data['cite_key']}_{datetime.now().strftime('%Y%m%d')}"

    # 如果目录已存在，先删除（已备份）
    if output_dir.exists():
        shutil.rmtree(output_dir)

    # 生成卡片文件
    print(f"\nGenerating cards to: {output_dir}")
    zettel_maker.generate_all_cards(
        cards=cards,
        cite_key=paper_data['cite_key'],
        paper_metadata={
            'title': paper_data['title'],
            'authors': paper_data['authors'],
            'year': paper_data['year'],
            'abstract': paper_data['abstract'],
            'keywords': paper_data['keywords']
        },
        output_dir=str(output_dir)
    )

    print(f"\nZettelkasten generation complete!")
    print(f"Output: {output_dir}")

    return output_dir

def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("Zettelkasten Regeneration Test - Phase 2.3")
    print("=" * 70)

    paper_id = 37  # Abbas-2022

    # 1. 备份现有卡片
    paper_dir = Path("output/zettelkasten_notes/zettel_Abbas-2022_20251104")
    if not backup_existing_cards(paper_dir):
        return

    # 2. 加载论文数据
    print("\nLoading paper data...")
    paper_data = load_paper_content(paper_id)
    if not paper_data:
        return

    print(f"Loaded: {paper_data['title']}")

    # 3. 使用新 template 生成卡片
    output_dir = generate_zettelkasten_with_new_template(paper_data)

    if output_dir:
        print("\n" + "=" * 70)
        print("Next steps:")
        print("=" * 70)
        print("1. Check the new cards in:", output_dir)
        print("2. Run analysis:")
        print("   python analyze_card_links.py")
        print("3. Compare before vs. after")

if __name__ == '__main__':
    main()
