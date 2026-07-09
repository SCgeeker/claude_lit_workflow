#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
測試腳本：解析單張 Zettelkasten 卡片

用途：驗證 YAML frontmatter 和 Markdown 區塊的提取邏輯
"""

import sys
import io
import re
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional

# 強制 UTF-8 輸出（解決 Windows 編碼問題）
if sys.stdout.encoding != 'utf-8':
    pass  # 已移除 import 時的 stdout 劫持（會破壞 pytest capture / MCP stdio）
def parse_zettel_card(file_path: str) -> Optional[Dict]:
    """
    解析單張 Zettelkasten 卡片

    Args:
        file_path: 卡片文件路徑

    Returns:
        解析結果字典，失敗返回 None
    """
    print(f"\n{'='*60}")
    print(f"解析卡片: {Path(file_path).name}")
    print(f"{'='*60}\n")

    try:
        # 1. 讀取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        print("[OK] File read successfully")
        print(f"   File size: {len(content)} chars\n")

        # 2. 提取 YAML frontmatter
        yaml_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        if not yaml_match:
            print("[ERROR] Invalid Zettelkasten format (YAML frontmatter not found)")
            return None

        yaml_content = yaml_match.group(1)
        markdown_content = yaml_match.group(2)

        print("[OK] YAML frontmatter extracted")
        print(f"   YAML 長度: {len(yaml_content)} 字元")
        print(f"   Markdown 長度: {len(markdown_content)} 字元\n")

        # 3. 解析 YAML（處理不規範格式）
        try:
            # 先嘗試標準YAML解析
            metadata = yaml.safe_load(yaml_content)
            print("[OK] YAML parsed successfully")
        except yaml.YAMLError as e:
            print(f"[WARN] Standard YAML parsing failed: {str(e)[:100]}")
            print("[INFO] Trying fallback parsing...")

            # 回退：逐行解析（處理不規範的YAML）
            metadata = {}
            for line in yaml_content.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    # 處理特殊欄位
                    if key == 'tags':
                        # 解析標籤列表
                        value = value.strip('[]')
                        metadata[key] = [tag.strip() for tag in value.split(',')]
                    elif key == 'source':
                        # source欄位保持原樣（包含引號和括號）
                        metadata[key] = value
                    elif value == '':
                        metadata[key] = None
                    else:
                        metadata[key] = value

            print("[OK] Fallback parsing completed")

        print("   YAML fields:")
        for key, value in metadata.items():
            print(f"     - {key}: {value}")
        print()

        # 4. 初始化結果字典
        result = {
            'zettel_id': normalize_id(metadata.get('id', '')),
            'title': metadata.get('title', '').strip(),
            'content': content,
            'card_type': metadata.get('type', 'concept'),
            'domain': extract_domain_from_id(metadata.get('id', '')),
            'tags': metadata.get('tags', []),
            'source_info': metadata.get('source', ''),
            'file_path': str(Path(file_path).resolve()),
            'created_at': metadata.get('created', None),
        }

        print("[OK] 基本欄位提取完成")
        print(f"   zettel_id: {result['zettel_id']}")
        print(f"   title: {result['title']}")
        print(f"   domain: {result['domain']}")
        print(f"   card_type: {result['card_type']}")
        print(f"   tags: {result['tags']}")
        print()

        # 5. 提取核心概念
        core_match = re.search(r'>\s*\*\*核心\*\*:\s*"(.+?)"', markdown_content, re.DOTALL)
        result['core_concept'] = core_match.group(1).strip() if core_match else None

        if result['core_concept']:
            print("[OK] 核心概念提取成功")
            print(f"   內容: {result['core_concept'][:100]}...")
        else:
            print("[WARN]  未找到核心概念")
        print()

        # 6. 提取說明文字
        desc_match = re.search(r'## 說明\n(.+?)(?=\n##|\Z)', markdown_content, re.DOTALL)
        result['description'] = desc_match.group(1).strip() if desc_match else None

        if result['description']:
            print("[OK] 說明文字提取成功")
            print(f"   長度: {len(result['description'])} 字元")
            print(f"   前100字: {result['description'][:100]}...")
        else:
            print("[WARN]  未找到說明文字")
        print()

        # 7. 提取 AI 筆記
        ai_match = re.search(
            r'\*\*\[AI Agent\]\*\*:\s*(.+?)(?=\n\*\*\[Human\]|\n---|===|\Z)',
            markdown_content,
            re.DOTALL
        )
        result['ai_notes'] = ai_match.group(1).strip() if ai_match else None

        if result['ai_notes']:
            print("[OK] AI 筆記提取成功")
            print(f"   長度: {len(result['ai_notes'])} 字元")
            print(f"   前100字: {result['ai_notes'][:100]}...")
        else:
            print("[WARN]  未找到 AI 筆記")
        print()

        # 8. 提取人類筆記
        human_match = re.search(
            r'\*\*\[Human\]\*\*:\s*(.+?)(?=\n---|===|\Z)',
            markdown_content,
            re.DOTALL
        )
        result['human_notes'] = human_match.group(1).strip() if human_match else None

        if result['human_notes']:
            print("[OK] 人類筆記提取成功")
            print(f"   內容: {result['human_notes'][:100]}...")
        else:
            print("[WARN]  未找到人類筆記（或僅有 TODO 佔位符）")
        print()

        # 9. 提取連結信息
        result['links'] = extract_links_from_content(markdown_content)

        if result['links']:
            print(f"[OK] 連結信息提取成功 ({len(result['links'])} 組)")
            for link in result['links']:
                print(f"   {link['relation_type']} → {link['target_ids']}")
        else:
            print("[WARN]  未找到連結信息")
        print()

        return result

    except FileNotFoundError:
        print(f"[ERROR] 錯誤：文件不存在 - {file_path}")
        return None
    except Exception as e:
        print(f"[ERROR] 解析失敗：{e}")
        import traceback
        traceback.print_exc()
        return None


def normalize_id(zettel_id: str) -> str:
    """
    正規化 Zettel ID 格式

    修復錯誤格式：
    - CogSci20251028001 → CogSci-20251028-001
    - AI_20251029_005 → AI-20251029-005
    """
    # 移除底線和多餘空白
    zettel_id = zettel_id.replace('_', '-').strip()

    # 正則表達式匹配並重組
    match = re.match(r'^([A-Za-z]+)[-]?(\d{8})[-]?(\d{3})$', zettel_id)
    if match:
        domain, date, num = match.groups()
        normalized = f"{domain}-{date}-{num}"
        if normalized != zettel_id:
            print(f"   [INFO]  ID 正規化: {zettel_id} → {normalized}")
        return normalized
    else:
        print(f"   [WARN]  無法正規化 ID: {zettel_id}")
        return zettel_id


def extract_domain_from_id(zettel_id: str) -> str:
    """從 ID 提取領域代碼"""
    match = re.match(r'^([A-Za-z]+)-', zettel_id)
    return match.group(1) if match else 'Unknown'


def extract_links_from_content(markdown: str) -> List[Dict]:
    """
    提取連結網絡區塊的所有連結

    範例輸入：
    ## 連結網絡
    **導向** → [[Linguistics-20251029-002]], [[Linguistics-20251029-003]]
    **基於** → [[Linguistics-20251029-001]]

    返回：
    [
        {'relation_type': '導向', 'target_ids': ['Linguistics-20251029-002', ...]},
        {'relation_type': '基於', 'target_ids': ['Linguistics-20251029-001']}
    ]
    """
    links = []

    # 提取「連結網絡」區塊（改進：處理多個空行）
    network_match = re.search(r'## 連結網絡\s*\n(.+?)(?=\n##|\Z)', markdown, re.DOTALL)
    if not network_match:
        return links

    network_text = network_match.group(1)

    # 匹配每一行連結（改進：更寬容的空白處理）
    # 格式：**關係類型** → [[ID1]], [[ID2]]
    link_pattern = r'\*\*(基於|導向|相關|對比|上位|下位)\*\*\s*→\s*(.+?)(?=\n\s*\n|\n\*\*|\n##|\Z)'

    for match in re.finditer(link_pattern, network_text, re.DOTALL):
        relation_type = match.group(1)
        target_text = match.group(2)

        # 提取所有目標 ID（改進：支援多行）
        target_ids = re.findall(r'\[\[([A-Za-z]+-\d{8}-\d{3})\]\]', target_text)

        if target_ids:
            links.append({
                'relation_type': relation_type,
                'target_ids': target_ids
            })

    return links


def print_summary(result: Dict):
    """打印解析結果摘要"""
    print(f"\n{'='*60}")
    print("解析結果摘要")
    print(f"{'='*60}\n")

    print("[INFO] 基本信息:")
    print(f"   ID: {result['zettel_id']}")
    print(f"   標題: {result['title']}")
    print(f"   領域: {result['domain']}")
    print(f"   類型: {result['card_type']}")
    print(f"   標籤: {', '.join(result['tags'])}")
    print(f"   來源: {result['source_info']}")
    print()

    print("[CONTENT] 內容欄位:")
    fields = [
        ('核心概念', result.get('core_concept')),
        ('說明文字', result.get('description')),
        ('AI 筆記', result.get('ai_notes')),
        ('人類筆記', result.get('human_notes'))
    ]

    for name, value in fields:
        if value:
            length = len(value)
            print(f"   [OK] {name}: {length} 字元")
        else:
            print(f"   [ERROR] {name}: 缺失")
    print()

    print("[LINKS] 連結網絡:")
    if result.get('links'):
        for link in result['links']:
            print(f"   {link['relation_type']} → {len(link['target_ids'])} 個目標")
            for target in link['target_ids']:
                print(f"      - {target}")
    else:
        print("   （無連結）")
    print()

    # 統計
    total_fields = 8  # zettel_id, title, core_concept, description, ai_notes, human_notes, links, tags
    filled_fields = sum([
        bool(result.get('zettel_id')),
        bool(result.get('title')),
        bool(result.get('core_concept')),
        bool(result.get('description')),
        bool(result.get('ai_notes')),
        bool(result.get('human_notes')),
        bool(result.get('links')),
        bool(result.get('tags'))
    ])

    completeness = filled_fields / total_fields * 100

    print(f"[STATS] 完整度: {filled_fields}/{total_fields} 欄位 ({completeness:.1f}%)")
    print()


def save_result_to_json(result: Dict, output_file: str):
    """保存解析結果為 JSON 文件"""
    # 移除完整內容欄位（太長）
    result_copy = result.copy()
    result_copy['content'] = f"<已省略，共 {len(result['content'])} 字元>"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_copy, f, ensure_ascii=False, indent=2)

    print(f"[SAVE] 解析結果已保存到: {output_file}")


def main():
    """主函數"""
    print("\n" + "="*60)
    print("Zettelkasten 卡片解析測試")
    print("="*60)

    # 測試卡片路徑
    test_cards = [
        "output/zettelkasten_notes/zettel_Linguistics_20251029/zettel_cards/Linguistics-20251029-001.md",
        "output/zettelkasten_notes/zettel_Linguistics_20251029/zettel_cards/Linguistics-20251029-003.md",
    ]

    for card_path in test_cards:
        # 檢查文件是否存在
        if not Path(card_path).exists():
            print(f"\n[WARN]  測試卡片不存在: {card_path}")
            print("   請確認路徑或使用其他測試卡片")
            continue

        # 解析卡片
        result = parse_zettel_card(card_path)

        if result:
            # 打印摘要
            print_summary(result)

            # 保存為 JSON
            output_file = f"test_result_{Path(card_path).stem}.json"
            save_result_to_json(result, output_file)

            print(f"{'='*60}\n")
        else:
            print(f"\n[ERROR] 卡片解析失敗: {card_path}\n")

    print("測試完成！")


if __name__ == '__main__':
    main()
