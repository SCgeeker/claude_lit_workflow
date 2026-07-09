#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RIS 格式解析器
解析 EndNote/Zotero 導出的 .ris 文件，提取論文元數據

RIS 欄位對應：
- TY  - 文獻類型 (JOUR, BOOK, CONF...)
- AU  - 作者
- TI  - 標題
- T1  - 標題（替代欄位）
- PY  - 年份
- Y1  - 年份（替代欄位）
- DO  - DOI
- ID  - 識別符（citekey）
- AB  - 摘要
- KW  - 關鍵詞
- JO  - 期刊名稱
- JF  - 期刊全名
- VL  - 卷號
- IS  - 期號
- SP  - 起始頁
- EP  - 結束頁
- PB  - 出版社
- UR  - URL
- ER  - 結束標記
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Iterator
from dataclasses import dataclass, field


@dataclass
class RISEntry:
    """RIS 條目數據結構"""

    # 必需欄位
    entry_type: str  # TY: JOUR, BOOK, CONF 等
    title: str       # TI/T1

    # 識別符
    id: Optional[str] = None    # ID: citekey
    doi: Optional[str] = None   # DO: DOI

    # 作者與年份
    authors: List[str] = field(default_factory=list)  # AU
    year: Optional[int] = None  # PY/Y1

    # 摘要與關鍵詞
    abstract: Optional[str] = None   # AB
    keywords: List[str] = field(default_factory=list)  # KW

    # 出版資訊
    journal: Optional[str] = None    # JO/JF
    volume: Optional[str] = None     # VL
    issue: Optional[str] = None      # IS
    start_page: Optional[str] = None  # SP
    end_page: Optional[str] = None    # EP
    publisher: Optional[str] = None   # PB

    # 其他
    url: Optional[str] = None        # UR
    note: Optional[str] = None       # N1

    # 原始數據
    raw_entry: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """轉換為字典"""
        pages = None
        if self.start_page:
            pages = self.start_page
            if self.end_page:
                pages = f"{self.start_page}-{self.end_page}"

        return {
            'entry_type': self.entry_type,
            'id': self.id,
            'cite_key': self.id,  # 統一命名
            'title': self.title,
            'authors': self.authors,
            'year': self.year,
            'doi': self.doi,
            'abstract': self.abstract,
            'keywords': self.keywords,
            'journal': self.journal,
            'volume': self.volume,
            'issue': self.issue,
            'pages': pages,
            'publisher': self.publisher,
            'url': self.url,
            'note': self.note,
        }


class RISParser:
    """
    RIS 文件解析器
    支援 EndNote、Zotero、Mendeley 等導出的 .ris 格式
    """

    # RIS 文獻類型對應
    TYPE_MAPPING = {
        'JOUR': 'article',
        'BOOK': 'book',
        'CHAP': 'incollection',
        'CONF': 'inproceedings',
        'THES': 'phdthesis',
        'RPRT': 'techreport',
        'UNPB': 'unpublished',
        'ELEC': 'online',
        'GEN': 'misc',
    }

    def __init__(self):
        """初始化解析器"""
        self.encoding = 'utf-8'

    def parse_file(self, ris_file: str) -> List[RISEntry]:
        """
        解析 RIS 文件

        Args:
            ris_file: .ris 文件路徑

        Returns:
            RISEntry 對象列表
        """
        ris_path = Path(ris_file)

        if not ris_path.exists():
            raise FileNotFoundError(f"RIS 文件不存在: {ris_file}")

        # 嘗試不同編碼
        content = None
        for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'gbk']:
            try:
                with open(ris_path, 'r', encoding=encoding) as f:
                    content = f.read()
                self.encoding = encoding
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            raise ValueError(f"無法解碼 RIS 文件: {ris_file}")

        return self._parse_content(content)

    def parse_string(self, content: str) -> List[RISEntry]:
        """
        解析 RIS 字串

        Args:
            content: RIS 格式字串

        Returns:
            RISEntry 對象列表
        """
        return self._parse_content(content)

    def _parse_content(self, content: str) -> List[RISEntry]:
        """
        解析 RIS 內容

        Args:
            content: RIS 格式內容

        Returns:
            RISEntry 對象列表
        """
        entries = []
        current_entry = {}
        current_tag = None

        for line in content.splitlines():
            line = line.rstrip()

            if not line:
                continue

            # 檢查是否為 RIS 標籤行
            match = re.match(r'^([A-Z][A-Z0-9])\s+-\s*(.*)$', line)

            if match:
                tag, value = match.groups()
                current_tag = tag

                if tag == 'TY':
                    # 新條目開始
                    current_entry = {'TY': value.strip()}
                elif tag == 'ER':
                    # 條目結束
                    if current_entry:
                        try:
                            entry = self._create_entry(current_entry)
                            entries.append(entry)
                        except Exception as e:
                            print(f"⚠️  跳過條目: {e}")
                        current_entry = {}
                else:
                    # 處理多值欄位（如 AU, KW）
                    if tag in ['AU', 'A1', 'A2', 'KW']:
                        if tag not in current_entry:
                            current_entry[tag] = []
                        current_entry[tag].append(value.strip())
                    else:
                        current_entry[tag] = value.strip()
            else:
                # 續行（多行摘要等）
                if current_tag and current_tag in current_entry:
                    if isinstance(current_entry[current_tag], str):
                        current_entry[current_tag] += ' ' + line.strip()

        return entries

    def _create_entry(self, raw: Dict) -> RISEntry:
        """
        從原始數據創建 RISEntry

        Args:
            raw: 原始 RIS 欄位字典

        Returns:
            RISEntry 對象
        """
        # 文獻類型
        entry_type = raw.get('TY', 'GEN')

        # 標題（TI 或 T1）
        title = raw.get('TI') or raw.get('T1') or ''
        if not title:
            raise ValueError("RIS 條目缺少標題")

        # 識別符
        entry_id = raw.get('ID') or raw.get('AN')

        # DOI
        doi = raw.get('DO') or raw.get('DOI')
        if doi:
            # 清理 DOI（移除 URL 前綴）
            doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)

        # 作者（AU 或 A1）
        authors = raw.get('AU', []) or raw.get('A1', [])
        if isinstance(authors, str):
            authors = [authors]
        authors = [self._clean_author(a) for a in authors]

        # 年份（PY 或 Y1）
        year_str = raw.get('PY') or raw.get('Y1') or ''
        year = self._parse_year(year_str)

        # 摘要
        abstract = raw.get('AB') or raw.get('N2')

        # 關鍵詞
        keywords = raw.get('KW', [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',')]

        # 期刊（JO, JF, T2）
        journal = raw.get('JO') or raw.get('JF') or raw.get('T2')

        # 出版資訊
        volume = raw.get('VL')
        issue = raw.get('IS')
        start_page = raw.get('SP')
        end_page = raw.get('EP')
        publisher = raw.get('PB')

        # URL
        url = raw.get('UR') or raw.get('L1')

        # 備註
        note = raw.get('N1')

        return RISEntry(
            entry_type=entry_type,
            title=title,
            id=entry_id,
            doi=doi,
            authors=authors,
            year=year,
            abstract=abstract,
            keywords=keywords,
            journal=journal,
            volume=volume,
            issue=issue,
            start_page=start_page,
            end_page=end_page,
            publisher=publisher,
            url=url,
            note=note,
            raw_entry=raw
        )

    def _clean_author(self, author: str) -> str:
        """
        清理作者名稱

        RIS 格式可能是：
        - "Last, First"
        - "First Last"
        """
        if not author:
            return ""

        author = author.strip()

        # 移除多餘空白
        author = re.sub(r'\s+', ' ', author)

        return author

    def _parse_year(self, year_str: str) -> Optional[int]:
        """
        解析年份字串

        RIS 年份格式可能是：
        - "2024"
        - "2024/01/15"
        - "2024///"
        """
        if not year_str:
            return None

        # 提取四位數年份
        match = re.search(r'\b(19|20)\d{2}\b', str(year_str))
        if match:
            return int(match.group(0))

        return None

    def find_entry_by_title(
        self,
        entries: List[RISEntry],
        title: str,
        threshold: float = 0.8
    ) -> Optional[RISEntry]:
        """
        根據標題查找條目（模糊匹配）

        Args:
            entries: RIS 條目列表
            title: 目標標題
            threshold: 相似度閾值（0-1）

        Returns:
            匹配的條目，無匹配返回 None
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

    def find_entry_by_doi(
        self,
        entries: List[RISEntry],
        doi: str
    ) -> Optional[RISEntry]:
        """
        根據 DOI 查找條目

        Args:
            entries: RIS 條目列表
            doi: DOI

        Returns:
            匹配的條目，無匹配返回 None
        """
        doi_lower = doi.lower().strip()
        # 移除 URL 前綴
        doi_lower = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi_lower)

        for entry in entries:
            if entry.doi:
                entry_doi = entry.doi.lower().strip()
                entry_doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', entry_doi)
                if entry_doi == doi_lower:
                    return entry

        return None

    def get_statistics(self, entries: List[RISEntry]) -> Dict:
        """
        生成統計信息

        Args:
            entries: RIS 條目列表

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
        with_id = sum(1 for e in entries if e.id)

        return {
            'total_entries': total,
            'entry_types': types,
            'completeness': {
                'with_abstract': with_abstract,
                'with_keywords': with_keywords,
                'with_doi': with_doi,
                'with_year': with_year,
                'with_id': with_id,
            },
            'completeness_percentage': {
                'abstract': (with_abstract / total * 100) if total > 0 else 0,
                'keywords': (with_keywords / total * 100) if total > 0 else 0,
                'doi': (with_doi / total * 100) if total > 0 else 0,
                'year': (with_year / total * 100) if total > 0 else 0,
                'id': (with_id / total * 100) if total > 0 else 0,
            }
        }


def main():
    """測試 RIS 解析器"""
    import sys
    import io

    # 修復 Windows 終端 UTF-8 編碼
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # 測試用 RIS 內容
    test_ris = """
TY  - JOUR
AU  - Barsalou, Lawrence W.
TI  - Perceptual symbol systems
JO  - Behavioral and Brain Sciences
PY  - 1999
VL  - 22
IS  - 4
SP  - 577
EP  - 660
DO  - 10.1017/S0140525X99002149
ID  - barsalou1999perceptual
KW  - cognition
KW  - perception
KW  - symbols
AB  - This article presents a new approach to knowledge representation.
ER  -

TY  - JOUR
AU  - Smith, John
AU  - Doe, Jane
TI  - Another Test Article
PY  - 2024
DO  - 10.1234/test.2024
ER  -
"""

    parser = RISParser()
    print("=" * 60)
    print("RIS Parser 測試")
    print("=" * 60)

    try:
        entries = parser.parse_string(test_ris)
        print(f"\n✅ 成功解析 {len(entries)} 個條目\n")

        for i, entry in enumerate(entries, 1):
            print(f"\n[{i}] {entry.id or 'N/A'}")
            print(f"    標題: {entry.title[:60]}...")
            print(f"    作者: {', '.join(entry.authors[:3])}")
            print(f"    年份: {entry.year or 'N/A'}")
            print(f"    DOI: {entry.doi or 'N/A'}")
            print(f"    類型: {entry.entry_type}")
            if entry.keywords:
                print(f"    關鍵詞: {', '.join(entry.keywords[:5])}")

        # 統計
        stats = parser.get_statistics(entries)
        print(f"\n📊 統計信息:")
        print(f"   總條目數: {stats['total_entries']}")
        comp = stats['completeness_percentage']
        print(f"   有 ID: {comp['id']:.1f}%")
        print(f"   有 DOI: {comp['doi']:.1f}%")
        print(f"   有摘要: {comp['abstract']:.1f}%")

    except Exception as e:
        print(f"❌ 解析失敗: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)

    # 如果有命令行參數，解析文件
    if len(sys.argv) > 1:
        ris_file = sys.argv[1]
        print(f"\n📚 解析 RIS 文件: {ris_file}")
        try:
            entries = parser.parse_file(ris_file)
            print(f"✅ 成功解析 {len(entries)} 個條目")

            # 顯示前 5 個
            for i, entry in enumerate(entries[:5], 1):
                print(f"\n[{i}] {entry.title[:60]}...")
                print(f"    ID: {entry.id or 'N/A'}")
                print(f"    DOI: {entry.doi or 'N/A'}")

        except Exception as e:
            print(f"❌ 解析失敗: {e}")


if __name__ == "__main__":
    main()
