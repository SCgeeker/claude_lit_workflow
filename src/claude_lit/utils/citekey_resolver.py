#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Citekey 解析與正規化模組

根據 CITEKEY_DESIGN_SPEC.md 實作：
- 三層識別符系統 (original_citekey, cite_key, doi)
- 多來源優先順序解析
- 自動生成 citekey
"""

import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


def normalize_citekey(citekey: str, german_umlaut: bool = True) -> str:
    """
    正規化 citekey（獨立函數，可直接匯入使用）

    處理：
    - 德語變音符號 (ü → ue, ö → oe, ä → ae, ß → ss)
    - Unicode 重音符號 (é → e, etc.)
    - 特殊字元移除
    - 空白正規化

    Args:
        citekey: 原始 citekey
        german_umlaut: 是否使用德語變音轉換（預設 True）

    Returns:
        正規化後的 citekey（ASCII 相容）

    Example:
        >>> normalize_citekey("Günther-2025a")
        'Guenther-2025a'
        >>> normalize_citekey("Créquit-2018")
        'Crequit-2018'
        >>> normalize_citekey("Müller-2020")
        'Mueller-2020'
    """
    if not citekey:
        return ""

    result = citekey

    # 德語變音符號轉換（必須在 NFD 正規化之前）
    if german_umlaut:
        umlaut_map = {
            'ü': 'ue', 'Ü': 'Ue',
            'ö': 'oe', 'Ö': 'Oe',
            'ä': 'ae', 'Ä': 'Ae',
            'ß': 'ss',
        }
        for char, replacement in umlaut_map.items():
            result = result.replace(char, replacement)

    # Unicode 正規化（NFD 分解，移除組合標記）- 處理其他重音
    result = unicodedata.normalize('NFD', result)
    result = ''.join(c for c in result if unicodedata.category(c) != 'Mn')

    # 移除特殊字元（保留字母、數字、連字符、底線）
    result = re.sub(r'[^\w\-]', '', result)

    return result


@dataclass
class CitykeyResult:
    """Citekey 解析結果"""
    cite_key: str                    # 正規化版本（用於檔案系統）
    original_citekey: Optional[str] = None  # 原始 citekey
    doi: Optional[str] = None        # DOI（如有）
    source: str = 'auto'             # 來源標記
    confidence: float = 1.0          # 信度
    metadata: Dict = field(default_factory=dict)  # 額外元數據


class CitykeyResolver:
    """
    Citekey 解析與正規化

    依優先順序處理：
    1. 手動指定
    2. BibTeX
    3. RIS
    4. DOI 查詢
    5. PDF 元數據
    6. 檔名推斷
    7. 自動生成
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化解析器

        Args:
            config: 配置選項（可選）
        """
        self.config = config or {}

        # 預設正規化設定
        self.separator = self.config.get('separator', '-')
        self.max_length = self.config.get('max_length', 50)
        self.lowercase = self.config.get('lowercase', False)
        self.remove_chars = self.config.get('remove_chars', "[]{}()#$%^&*+=|\\<>?/")

        # 常見停用詞（標題第一個實詞時排除）
        self.stop_words = {
            'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with',
            'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been'
        }

    def resolve(
        self,
        pdf_path: Optional[Path] = None,
        bib_entry: Optional[Dict] = None,
        ris_entry: Optional[Dict] = None,
        manual_citekey: Optional[str] = None,
        doi: Optional[str] = None,
        title: Optional[str] = None,
        authors: Optional[List[str]] = None,
        year: Optional[int] = None
    ) -> CitykeyResult:
        """
        依優先順序解析 citekey

        Args:
            pdf_path: PDF 檔案路徑
            bib_entry: BibTeX 條目（dict）
            ris_entry: RIS 條目（dict）
            manual_citekey: 手動指定的 citekey
            doi: DOI 字串
            title: 標題
            authors: 作者列表
            year: 年份

        Returns:
            CitykeyResult 包含正規化 citekey 和元數據
        """
        result_doi = doi

        # 優先順序 1: 手動指定
        if manual_citekey:
            return CitykeyResult(
                cite_key=self.normalize(manual_citekey),
                original_citekey=manual_citekey,
                doi=result_doi,
                source='manual',
                confidence=1.0
            )

        # 優先順序 2: BibTeX
        if bib_entry:
            original_key = bib_entry.get('cite_key') or bib_entry.get('ID', '')
            bib_doi = bib_entry.get('doi')
            if original_key:
                return CitykeyResult(
                    cite_key=self.normalize(original_key),
                    original_citekey=original_key,
                    doi=bib_doi or result_doi,
                    source='bibtex',
                    confidence=1.0,
                    metadata={'entry_type': bib_entry.get('ENTRYTYPE', 'misc')}
                )

        # 優先順序 3: RIS
        if ris_entry:
            original_key = ris_entry.get('id') or ris_entry.get('ID', '')
            ris_doi = ris_entry.get('doi') or ris_entry.get('DO', '')
            if original_key:
                return CitykeyResult(
                    cite_key=self.normalize(original_key),
                    original_citekey=original_key,
                    doi=ris_doi or result_doi,
                    source='ris',
                    confidence=0.95
                )

        # 優先順序 4: DOI
        if result_doi:
            generated_key = self._generate_from_doi(result_doi, authors, year)
            if generated_key:
                return CitykeyResult(
                    cite_key=generated_key,
                    original_citekey=None,
                    doi=result_doi,
                    source='doi',
                    confidence=0.9
                )

        # 優先順序 5: PDF 檔名推斷
        if pdf_path:
            inferred = self._infer_from_filename(pdf_path)
            if inferred:
                return CitykeyResult(
                    cite_key=inferred,
                    original_citekey=None,
                    doi=result_doi,
                    source='filename',
                    confidence=0.7
                )

        # 優先順序 6: 自動生成
        if authors or title:
            generated = self.generate(authors or [], year, title)
            return CitykeyResult(
                cite_key=generated,
                original_citekey=None,
                doi=result_doi,
                source='auto',
                confidence=0.5
            )

        # 最後手段：使用時間戳
        from datetime import datetime
        fallback = f"paper-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return CitykeyResult(
            cite_key=fallback,
            original_citekey=None,
            doi=result_doi,
            source='fallback',
            confidence=0.1
        )

    def normalize(self, citekey: str) -> str:
        """
        正規化 citekey（用於檔案系統）

        Args:
            citekey: 原始 citekey

        Returns:
            正規化後的 citekey
        """
        if not citekey:
            return ""

        result = citekey

        # 移除特殊字元
        for char in self.remove_chars:
            result = result.replace(char, '')

        # Unicode 正規化（處理重音符號）
        result = unicodedata.normalize('NFD', result)
        result = ''.join(c for c in result if unicodedata.category(c) != 'Mn')

        # 移除多餘空白，替換為分隔符
        result = re.sub(r'\s+', self.separator, result.strip())

        # 大小寫處理
        if self.lowercase:
            result = result.lower()

        # 長度限制
        if len(result) > self.max_length:
            result = result[:self.max_length]

        return result

    def generate(
        self,
        authors: List[str],
        year: Optional[int] = None,
        title: Optional[str] = None
    ) -> str:
        """
        自動生成 citekey

        格式: {first_author}-{year}

        Args:
            authors: 作者列表
            year: 年份
            title: 標題（備用）

        Returns:
            生成的 citekey
        """
        # 提取第一作者姓氏
        first_author = self._extract_last_name(authors[0]) if authors else None

        if not first_author and title:
            # 從標題提取第一個實詞
            first_author = self._extract_title_word(title)

        if not first_author:
            first_author = "Unknown"

        # 組合
        parts = [first_author]
        if year:
            parts.append(str(year))

        return self.separator.join(parts)

    def match_pdf_to_bib(
        self,
        pdf_path: Path,
        bib_entries: List[Dict],
        threshold: float = 0.8
    ) -> Optional[Dict]:
        """
        將 PDF 與書目條目配對（模糊匹配）

        Args:
            pdf_path: PDF 檔案路徑
            bib_entries: BibTeX/RIS 條目列表
            threshold: 相似度閾值

        Returns:
            匹配的條目，無匹配返回 None
        """
        from difflib import SequenceMatcher

        # 從檔名提取可能的 citekey
        inferred_key = self._infer_from_filename(pdf_path)
        if not inferred_key:
            return None

        inferred_lower = inferred_key.lower()

        best_match = None
        best_score = 0

        for entry in bib_entries:
            entry_key = entry.get('cite_key', '') or entry.get('ID', '') or entry.get('id', '')
            if not entry_key:
                continue

            entry_key_lower = entry_key.lower()

            # 計算相似度
            score = SequenceMatcher(None, inferred_lower, entry_key_lower).ratio()

            # 也檢查正規化版本
            normalized_inferred = self.normalize(inferred_key).lower()
            normalized_entry = self.normalize(entry_key).lower()
            score2 = SequenceMatcher(None, normalized_inferred, normalized_entry).ratio()

            score = max(score, score2)

            if score > best_score and score >= threshold:
                best_score = score
                best_match = entry

        return best_match

    def _extract_last_name(self, author: str) -> str:
        """
        從作者名稱提取姓氏

        支援格式：
        - "Last, First"
        - "First Last"
        - "First Middle Last"
        """
        if not author:
            return ""

        author = author.strip()

        # 格式: "Last, First"
        if ',' in author:
            return author.split(',')[0].strip()

        # 格式: "First Last" 或 "First Middle Last"
        parts = author.split()
        if parts:
            return parts[-1].strip()

        return author

    def _extract_title_word(self, title: str) -> str:
        """從標題提取第一個實詞"""
        if not title:
            return ""

        words = re.findall(r'\b[a-zA-Z]+\b', title)
        for word in words:
            if word.lower() not in self.stop_words:
                return word.capitalize()

        return words[0].capitalize() if words else ""

    def _infer_from_filename(self, pdf_path: Path) -> Optional[str]:
        """
        從檔名推斷 citekey

        支援格式：
        - "Author-Year.pdf"
        - "Author_Year.pdf"
        - "AuthorYear.pdf"
        - "@Author-Year.pdf" (Zotero ZotMoov)
        """
        stem = pdf_path.stem

        # 移除 @ 前綴 (ZotMoov)
        if stem.startswith('@'):
            stem = stem[1:]

        # 移除常見後綴
        stem = re.sub(r'[-_]?(annotated|notes|copy|\d+)$', '', stem, flags=re.IGNORECASE)

        # 檢查是否符合 Author-Year 或 Author_Year 格式
        match = re.match(r'^([A-Za-z]+)[-_]?(\d{4}[a-z]?)$', stem)
        if match:
            author, year = match.groups()
            return f"{author}{self.separator}{year}"

        # 檢查 AuthorYear 格式
        match = re.match(r'^([A-Za-z]+)(\d{4}[a-z]?)$', stem)
        if match:
            author, year = match.groups()
            return f"{author}{self.separator}{year}"

        # 直接使用檔名（正規化後）
        return self.normalize(stem) if stem else None

    def _generate_from_doi(
        self,
        doi: str,
        authors: Optional[List[str]] = None,
        year: Optional[int] = None
    ) -> Optional[str]:
        """
        從 DOI 生成 citekey

        如果有作者和年份資訊，使用標準格式
        否則使用 DOI 的最後部分
        """
        if authors and year:
            return self.generate(authors, year)

        # 從 DOI 提取（最後部分）
        # DOI 格式: 10.xxxx/identifier
        if '/' in doi:
            identifier = doi.split('/')[-1]
            # 清理特殊字元
            identifier = re.sub(r'[^\w\-]', '', identifier)
            return identifier[:self.max_length] if identifier else None

        return None


def main():
    """測試 Citekey 解析器"""
    import sys

    resolver = CitykeyResolver()

    # 測試案例
    print("=" * 60)
    print("Citekey Resolver 測試")
    print("=" * 60)

    # 測試 1: 手動指定
    result = resolver.resolve(manual_citekey="Barsalou-1999")
    print(f"\n[測試 1] 手動指定:")
    print(f"  輸入: Barsalou-1999")
    print(f"  結果: {result.cite_key} (來源: {result.source})")

    # 測試 2: BibTeX
    bib_entry = {
        'ID': 'barsalou1999perceptual',
        'ENTRYTYPE': 'article',
        'doi': '10.1017/S0140525X99002149'
    }
    result = resolver.resolve(bib_entry=bib_entry)
    print(f"\n[測試 2] BibTeX:")
    print(f"  輸入: {bib_entry['ID']}")
    print(f"  結果: {result.cite_key} (來源: {result.source})")
    print(f"  DOI: {result.doi}")

    # 測試 3: 自動生成
    result = resolver.resolve(
        authors=["Lawrence W. Barsalou", "Kyle Simmons"],
        year=1999,
        title="Perceptual symbol systems"
    )
    print(f"\n[測試 3] 自動生成:")
    print(f"  輸入: authors=['Lawrence W. Barsalou'], year=1999")
    print(f"  結果: {result.cite_key} (來源: {result.source})")

    # 測試 4: 檔名推斷
    result = resolver.resolve(pdf_path=Path("Barsalou-1999.pdf"))
    print(f"\n[測試 4] 檔名推斷:")
    print(f"  輸入: Barsalou-1999.pdf")
    print(f"  結果: {result.cite_key} (來源: {result.source})")

    # 測試 5: 正規化
    print(f"\n[測試 5] 正規化:")
    test_keys = [
        "barsalou1999perceptual",
        "Barsalou_1999",
        "Créquit-2018",
        "Author Name 2020"
    ]
    for key in test_keys:
        normalized = resolver.normalize(key)
        print(f"  {key} → {normalized}")

    print("\n" + "=" * 60)
    print("✅ 測試完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
