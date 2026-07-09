#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自訂需求載入模組

支援從檔案或命令行載入自訂需求，整合到 LLM 提示語中。
"""

from pathlib import Path
from typing import Optional


def load_custom_requirements(
    custom_arg: Optional[str] = None,
    custom_file_arg: Optional[str] = None,
    default_file: Optional[str] = None,
    verbose: bool = True
) -> Optional[str]:
    """
    載入自訂需求

    優先順序：
    1. custom_file_arg（明確指定的檔案路徑）
    2. custom_arg（命令行字串）
    3. default_file（預設檔案，若存在）

    Args:
        custom_arg: 命令行直接輸入的字串（--custom "..."）
        custom_file_arg: 使用者指定的檔案路徑（--custom-file path）
        default_file: 預設檔案路徑（如 config/custom_slides.md）
        verbose: 是否輸出載入訊息

    Returns:
        自訂需求內容，或 None

    Examples:
        >>> # 從檔案載入
        >>> content = load_custom_requirements(custom_file_arg="my_style.md")

        >>> # 從命令行載入
        >>> content = load_custom_requirements(custom_arg="請使用口語化表達")

        >>> # 自動使用預設檔案
        >>> content = load_custom_requirements(default_file="config/custom_slides.md")
    """
    # 1. 明確指定的檔案（最高優先）
    if custom_file_arg:
        path = Path(custom_file_arg)
        if path.exists():
            content = path.read_text(encoding='utf-8').strip()
            if verbose:
                print(f"📋 載入自訂需求：{path}")
            return content if content else None
        else:
            if verbose:
                print(f"⚠️  警告：找不到自訂需求檔案 {path}")
            return None

    # 2. 命令行字串
    if custom_arg:
        if verbose:
            print(f"📋 使用命令行自訂需求（{len(custom_arg)} 字元）")
        return custom_arg.strip() if custom_arg.strip() else None

    # 3. 預設檔案
    if default_file:
        path = Path(default_file)
        if path.exists():
            content = path.read_text(encoding='utf-8').strip()
            if content:
                if verbose:
                    print(f"📋 載入預設需求：{path}")
                return content
            # 空檔案視為無需求
            return None

    return None


def format_custom_requirements_for_prompt(custom_requirements: Optional[str]) -> str:
    """
    將自訂需求格式化為可插入提示語的格式

    Args:
        custom_requirements: 自訂需求內容

    Returns:
        格式化後的字串，可直接插入提示語
    """
    if not custom_requirements:
        return ""

    return f"""
## 使用者特殊需求

請在生成內容時，額外遵循以下要求：

{custom_requirements}

"""
