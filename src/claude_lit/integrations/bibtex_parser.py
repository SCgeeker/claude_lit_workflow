#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BibTeX解析器
解析Zotero導出的.bib文件，提取論文元數據
"""

import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

try:
    import bibtexparser
    from bibtexparser.bparser import BibTexParser
    from bibtexparser.customization import convert_to_unicode
except ImportError:
    raise ImportError(
        "需要安装 bibtexparser 库。请运行: pip install bibtexparser"
    )


@dataclass
class BibTeXEntry:
    """BibTeX條目數據結構"""

    # 必需欄位
    entry_type: str  # article, inproceedings, book等
    cite_key: str    # BibTeX引用鍵（Zotero的唯一標識）
    title: str

    # 可選欄位
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    abstract: Optional[str] = None
    keywords: List[str] = field(default_factory=list)

    # 出版信息
    journal: Optional[str] = None
    booktitle: Optional[str] = None
    publisher: Optional[str] = None
    volume: Optional[str] = None
    number: Optional[str] = None
    pages: Optional[str] = None

    # 其他欄位
    note: Optional[str] = None
    file: Optional[str] = None  # Zotero附件路徑

    # 原始數據
    raw_entry: Dict = field(default_factory=dict)

    def __post_init__(self):
        """驗證必需欄位"""
        if not self.title:
            raise ValueError(f"BibTeX條目缺少標題: {self.cite_key}")

    def to_dict(self) -> Dict:
        """轉換為字典"""
        return {
            'entry_type': self.entry_type,
            'cite_key': self.cite_key,
            'title': self.title,
            'authors': self.authors,
            'year': self.year,
            'doi': self.doi,
            'url': self.url,
            'abstract': self.abstract,
            'keywords': self.keywords,
            'journal': self.journal,
            'booktitle': self.booktitle,
            'publisher': self.publisher,
            'volume': self.volume,
            'number': self.number,
            'pages': self.pages,
            'note': self.note,
            'file': self.file,
        }


class BibTeXParser:
    """
    BibTeX文件解析器
    支援Zotero導出的.bib格式
    """

    def __init__(self):
        """初始化解析器"""
        self.parser = BibTexParser(common_strings=True)
        # 禁用convert_to_unicode（Python 3.13兼容性問題）
        # self.parser.customization = convert_to_unicode
        self.parser.ignore_nonstandard_types = False

    def parse_file(self, bib_file: str) -> List[BibTeXEntry]:
        """
        解析BibTeX文件

        Args:
            bib_file: .bib文件路徑

        Returns:
            BibTeXEntry對象列表
        """
        bib_path = Path(bib_file)

        if not bib_path.exists():
            raise FileNotFoundError(f"BibTeX文件不存在: {bib_file}")

        # 讀取文件（處理UTF-8編碼）
        with open(bib_path, 'r', encoding='utf-8') as f:
            bib_content = f.read()

        # 解析
        try:
            bib_database = bibtexparser.loads(bib_content, parser=self.parser)
        except Exception as e:
            raise ValueError(f"BibTeX解析失敗: {e}")

        # 轉換為BibTeXEntry對象
        entries = []
        for entry in bib_database.entries:
            try:
                parsed_entry = self._parse_entry(entry)
                entries.append(parsed_entry)
            except Exception as e:
                print(f"⚠️  跳過條目 {entry.get('ID', 'unknown')}: {e}")
                continue

        return entries

    def _parse_entry(self, entry: Dict) -> BibTeXEntry:
        """
        解析單個BibTeX條目

        Args:
            entry: bibtexparser返回的條目字典

        Returns:
            BibTeXEntry對象
        """
        # 提取基本信息
        entry_type = entry.get('ENTRYTYPE', 'misc')
        cite_key = entry.get('ID', '')
        title = self._clean_text(entry.get('title', ''))

        # 解析作者
        authors = self._parse_authors(entry.get('author', ''))

        # 提取年份
        year = self._parse_year(entry.get('year', ''))

        # 提取關鍵詞
        keywords = self._parse_keywords(entry.get('keywords', ''))

        # 清理文本欄位
        abstract = self._clean_text(entry.get('abstract', ''))
        doi = entry.get('doi', None)
        url = entry.get('url', None)

        # 出版信息
        journal = self._clean_text(entry.get('journal', ''))
        booktitle = self._clean_text(entry.get('booktitle', ''))
        publisher = entry.get('publisher', None)
        volume = entry.get('volume', None)
        number = entry.get('number', None)
        pages = entry.get('pages', None)

        # Zotero特定欄位
        note = entry.get('note', None)
        file_field = entry.get('file', None)

        return BibTeXEntry(
            entry_type=entry_type,
            cite_key=cite_key,
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            url=url,
            abstract=abstract,
            keywords=keywords,
            journal=journal,
            booktitle=booktitle,
            publisher=publisher,
            volume=volume,
            number=number,
            pages=pages,
            note=note,
            file=file_field,
            raw_entry=entry
        )

    def _parse_authors(self, author_str: str) -> List[str]:
        """
        解析作者字串

        BibTeX格式: "Last1, First1 and Last2, First2"

        Args:
            author_str: 作者字串

        Returns:
            作者列表
        """
        if not author_str:
            return []

        # 分割 "and"
        authors = re.split(r'\s+and\s+', author_str, flags=re.IGNORECASE)

        # 清理每個作者名稱
        cleaned_authors = []
        for author in authors:
            # 移除大括號和LaTeX命令
            author = self._clean_text(author)
            author = author.strip()

            if author:
                cleaned_authors.append(author)

        return cleaned_authors

    def _parse_year(self, year_str: str) -> Optional[int]:
        """
        解析年份

        Args:
            year_str: 年份字串

        Returns:
            年份整數，解析失敗返回None
        """
        if not year_str:
            return None

        # 提取4位數字
        match = re.search(r'\b(19|20)\d{2}\b', str(year_str))
        if match:
            return int(match.group(0))

        return None

    def _parse_keywords(self, keywords_str: str) -> List[str]:
        """
        解析關鍵詞

        Zotero格式: "keyword1, keyword2; keyword3"

        Args:
            keywords_str: 關鍵詞字串

        Returns:
            關鍵詞列表
        """
        if not keywords_str:
            return []

        # 支援逗號或分號分隔
        keywords = re.split(r'[,;]\s*', keywords_str)

        # 清理並去重
        cleaned = []
        seen = set()
        for kw in keywords:
            kw = self._clean_text(kw).strip()
            if kw and kw.lower() not in seen:
                cleaned.append(kw)
                seen.add(kw.lower())

        return cleaned

    def _clean_text(self, text: str) -> str:
        """
        清理BibTeX文本
        - 移除大括號 {}
        - 移除LaTeX命令 \\textit{}, \\emph{}等
        - 處理特殊字元

        Args:
            text: 原始文本

        Returns:
            清理後的文本
        """
        if not text:
            return ""

        # 移除LaTeX命令（保留內容）
        # \textit{content} -> content
        text = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', text)

        # 移除單獨的大括號
        text = text.replace('{', '').replace('}', '')

        # 處理LaTeX特殊字元
        latex_chars = {
            r'\"a': 'ä', r'\"o': 'ö', r'\"u': 'ü',
            r"\'e": 'é', r"\'a": 'á', r"\'i": 'í',
            r'\~n': 'ñ', r'\^e': 'ê',
            r'--': '–', r'---': '—',
        }
        for latex, char in latex_chars.items():
            text = text.replace(latex, char)

        # 移除多餘空白
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text

    def find_entry_by_title(
        self,
        entries: List[BibTeXEntry],
        title: str,
        threshold: float = 0.8
    ) -> Optional[BibTeXEntry]:
        """
        根據標題查找條目（模糊匹配）

        Args:
            entries: BibTeX條目列表
            title: 目標標題
            threshold: 相似度閾值（0-1）

        Returns:
            匹配的條目，無匹配返回None
        """
        from difflib import SequenceMatcher

        title_lower = title.lower().strip()

        best_match = None
        best_score = 0

        for entry in entries:
            entry_title = entry.title.lower().strip()

            # 計算相似度
            score = SequenceMatcher(None, title_lower, entry_title).ratio()

            if score > best_score and score >= threshold:
                best_score = score
                best_match = entry

        return best_match

    def get_statistics(self, entries: List[BibTeXEntry]) -> Dict:
        """
        生成統計信息

        Args:
            entries: BibTeX條目列表

        Returns:
            統計字典
        """
        total = len(entries)

        # 統計類型
        types = {}
        for entry in entries:
            types[entry.entry_type] = types.get(entry.entry_type, 0) + 1

        # 統計欄位完整性
        with_abstract = sum(1 for e in entries if e.abstract)
        with_keywords = sum(1 for e in entries if e.keywords)
        with_doi = sum(1 for e in entries if e.doi)
        with_year = sum(1 for e in entries if e.year)

        return {
            'total_entries': total,
            'entry_types': types,
            'completeness': {
                'with_abstract': with_abstract,
                'with_keywords': with_keywords,
                'with_doi': with_doi,
                'with_year': with_year,
            },
            'completeness_percentage': {
                'abstract': (with_abstract / total * 100) if total > 0 else 0,
                'keywords': (with_keywords / total * 100) if total > 0 else 0,
                'doi': (with_doi / total * 100) if total > 0 else 0,
                'year': (with_year / total * 100) if total > 0 else 0,
            }
        }


def main():
    """測試BibTeX解析器"""
    import sys
    import io

    # 修復Windows終端UTF-8編碼
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    if len(sys.argv) < 2:
        print("使用方式: python bibtex_parser.py <bib_file>")
        sys.exit(1)

    bib_file = sys.argv[1]

    # 解析
    parser = BibTeXParser()
    print(f"📚 解析BibTeX文件: {bib_file}")

    try:
        entries = parser.parse_file(bib_file)
        print(f"✅ 成功解析 {len(entries)} 個條目\n")

        # 統計
        stats = parser.get_statistics(entries)
        print("📊 統計信息:")
        print(f"   總條目數: {stats['total_entries']}")
        print(f"\n   條目類型:")
        for entry_type, count in stats['entry_types'].items():
            print(f"     - {entry_type}: {count}")

        print(f"\n   元數據完整性:")
        comp = stats['completeness_percentage']
        print(f"     - 摘要: {comp['abstract']:.1f}%")
        print(f"     - 關鍵詞: {comp['keywords']:.1f}%")
        print(f"     - DOI: {comp['doi']:.1f}%")
        print(f"     - 年份: {comp['year']:.1f}%")

        # 顯示前3個條目
        print("\n📄 範例條目（前3個）:")
        for i, entry in enumerate(entries[:3], 1):
            print(f"\n   [{i}] {entry.cite_key}")
            print(f"       標題: {entry.title[:80]}...")
            print(f"       作者: {', '.join(entry.authors[:3])}")
            print(f"       年份: {entry.year or 'N/A'}")
            print(f"       類型: {entry.entry_type}")
            if entry.keywords:
                print(f"       關鍵詞: {', '.join(entry.keywords[:5])}")

    except Exception as e:
        print(f"❌ 解析失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
