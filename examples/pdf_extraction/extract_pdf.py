#!/usr/bin/env python3
"""
PDF提取器使用範例
"""

from claude_lit.extractors import PDFExtractor

# 創建提取器實例
extractor = PDFExtractor(max_chars=50000)

# 提取PDF內容
result = extractor.extract("paper.pdf")

# 訪問提取結果
title = result['structure']['title']
authors = result['structure']['authors']
abstract = result['structure']['abstract']

print(f"標題: {title}")
print(f"作者: {', '.join(authors)}")
print(f"摘要: {abstract[:200]}...")
