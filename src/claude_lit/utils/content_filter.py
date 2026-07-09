"""
Content Filter for Zettelkasten Cards

This module provides utilities to separate AI-generated content from human notes
in Zettelkasten cards, ensuring that vector embeddings and relation finding
only use AI-generated content.

Design Philosophy:
- Preserve AI analysis: Core concepts, descriptions, and AI insights
- Filter human notes: Personal thoughts, TODO markers, and HTML comments
- Robust parsing: Handle various markdown formats and edge cases

Usage:
    from claude_lit.utils.content_filter import extract_ai_content, remove_human_notes

    ai_only = extract_ai_content(card_content)
    embeddings = generate_embedding(ai_only)
"""

import re
from typing import Optional


def extract_ai_content(content: str) -> str:
    """
    Extract AI-generated content from a Zettelkasten card.

    This function removes the human notes section (marked with **[Human]**: or HTML comments)
    and returns only the AI-generated analysis.

    Args:
        content: Full markdown content of a Zettelkasten card

    Returns:
        AI-generated content only, with human notes removed

    Examples:
        >>> content = '''## 核心概念
        ... AI generated text
        ...
        ... ## 個人筆記
        ... **[AI Agent]**: AI analysis
        ... **[Human]**: (TODO) User notes
        ... '''
        >>> ai_content = extract_ai_content(content)
        >>> '**[Human]**:' not in ai_content
        True
    """
    if not content:
        return ""

    # Strategy 1: Split at "## 個人筆記" section and extract AI part
    if "## 個人筆記" in content or "## 个人笔记" in content:
        # Find the personal notes section
        match = re.search(r'##\s*(個人筆記|个人笔记)', content)
        if match:
            # Get content before personal notes
            before_personal = content[:match.start()].strip()

            # Now extract AI notes from the personal notes section
            after_personal = content[match.start():]
            ai_notes = _extract_ai_notes_from_personal_section(after_personal)

            if ai_notes:
                return f"{before_personal}\n\n{ai_notes}"
            else:
                return before_personal

    # Strategy 2: Remove **[Human]**: markers and everything after
    result = _remove_human_markers(content)

    # Strategy 3: Remove HTML comments
    result = _remove_html_comments(result)

    return result.strip()


def remove_human_notes(content: str) -> str:
    """
    Remove human notes from card content while preserving structure.

    This is an alias for extract_ai_content() for clearer semantics.

    Args:
        content: Full markdown content

    Returns:
        Content with human notes removed
    """
    return extract_ai_content(content)


def _extract_ai_notes_from_personal_section(personal_section: str) -> str:
    """
    Extract AI Agent notes from the personal notes section.

    Args:
        personal_section: The "## 個人筆記" section and everything after

    Returns:
        Only the AI Agent's notes, or empty string if none found
    """
    # Look for **[AI Agent]**: content
    # Pattern: **[AI Agent]**: (content) **[Human]**:
    pattern = r'\*\*\[AI Agent\]\*\*:\s*(.+?)(?=\*\*\[Human\]\*\*:|##|$)'
    match = re.search(pattern, personal_section, re.DOTALL)

    if match:
        ai_notes = match.group(1).strip()
        # Remove duplicate [AI Agent] markers if present
        ai_notes = re.sub(r'\*\*\[AI Agent\]\*\*:\s*', '', ai_notes)
        # Remove **[Human]**: markers that might have been captured
        ai_notes = re.sub(r'\*\*\[Human\]\*\*:\s*.*', '', ai_notes, flags=re.DOTALL)
        ai_notes = ai_notes.strip()

        if ai_notes and ai_notes != "（待填寫）":  # Filter out placeholder
            return f"## AI 深度分析\n\n{ai_notes}"

    return ""


def _remove_human_markers(content: str) -> str:
    """
    Remove **[Human]**: markers and everything after them.

    Args:
        content: Full content string

    Returns:
        Content with human markers removed
    """
    # Pattern: **[Human]**: and everything after until next heading or end
    # Be greedy to capture all human content
    patterns = [
        r'\*\*\[Human\]\*\*:.*',  # Remove [Human] marker and all after
        r'\(TODO\)',               # Remove TODO markers
    ]

    result = content
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.DOTALL | re.MULTILINE)

    return result


def _remove_html_comments(content: str) -> str:
    """
    Remove HTML comments from markdown content.

    Args:
        content: Content with potential HTML comments

    Returns:
        Content without HTML comments
    """
    # Remove <!-- ... --> comments
    return re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)


def is_human_edited(content: str) -> bool:
    """
    Check if a card has been edited by a human.

    Args:
        content: Card content to check

    Returns:
        True if human content is present (not just TODO)
    """
    # Look for **[Human]**: followed by actual content (not just TODO)
    human_pattern = r'\*\*\[Human\]\*\*:\s*(?!\(TODO\))(.+)'
    match = re.search(human_pattern, content, re.DOTALL)

    if match:
        human_content = match.group(1).strip()
        # Check if there's actual content (not just HTML comments)
        human_content_clean = _remove_html_comments(human_content).strip()
        return len(human_content_clean) > 0

    return False


def get_human_notes(content: str) -> Optional[str]:
    """
    Extract only the human-written notes from a card.

    Args:
        content: Full card content

    Returns:
        Human notes if present, None otherwise
    """
    # Pattern: **[Human]**: (content) until next ## or end
    pattern = r'\*\*\[Human\]\*\*:\s*(.+?)(?=##|$)'
    match = re.search(pattern, content, re.DOTALL)

    if match:
        human_notes = match.group(1).strip()
        # Remove TODO markers and HTML comments
        human_notes = re.sub(r'\(TODO\)', '', human_notes)
        human_notes = _remove_html_comments(human_notes)
        human_notes = human_notes.strip()

        if human_notes:
            return human_notes

    return None


def split_ai_and_human_content(content: str) -> tuple[str, Optional[str]]:
    """
    Split card content into AI and human parts.

    Args:
        content: Full card content

    Returns:
        Tuple of (ai_content, human_content)
        human_content is None if no human notes present
    """
    ai_content = extract_ai_content(content)
    human_content = get_human_notes(content)

    return ai_content, human_content


# Test functionality when run directly
if __name__ == "__main__":
    # Test case 1: Standard format
    test_content_1 = """---
title: "Test Card"
---

## 核心概念
AI generated concept

## 說明
AI generated explanation

## 個人筆記

**[AI Agent]**: **[AI Agent]**: This is AI analysis with critical thinking.

**[Human]**: (TODO) <!-- 請在此處添加您的個人思考 -->
"""

    print("Test 1: Standard format")
    print("=" * 60)
    ai_only = extract_ai_content(test_content_1)
    print("AI content:")
    print(ai_only)
    print("\nHuman edited:", is_human_edited(test_content_1))
    print()

    # Test case 2: Human has added notes
    test_content_2 = """## 核心概念
AI concept

## 個人筆記

**[AI Agent]**: AI critical analysis

**[Human]**: I think this is very interesting and relates to my research on X.
"""

    print("Test 2: Human edited")
    print("=" * 60)
    ai_only = extract_ai_content(test_content_2)
    print("AI content:")
    print(ai_only)
    print("\nHuman edited:", is_human_edited(test_content_2))
    human_notes = get_human_notes(test_content_2)
    print("Human notes:", human_notes)
    print()

    # Test case 3: No personal notes section
    test_content_3 = """## 核心概念
Pure AI content with no personal notes section.

## 連結網絡
Some links here.
"""

    print("Test 3: No personal notes")
    print("=" * 60)
    ai_only = extract_ai_content(test_content_3)
    print("AI content:")
    print(ai_only)
    print("\nHuman edited:", is_human_edited(test_content_3))
