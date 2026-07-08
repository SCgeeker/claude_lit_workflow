#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOI 解析與查詢模組

功能：
- 從 PDF 文本/元數據提取 DOI
- 使用 CrossRef API 查詢元數據
- 生成 citekey 建議
"""

import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import requests


@dataclass
class DOIMetadata:
    """DOI 元數據結構"""
    doi: str
    title: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    publisher: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    abstract: Optional[str] = None
    subject: List[str] = field(default_factory=list)  # 學科分類
    url: Optional[str] = None
    issn: Optional[str] = None
    isbn: Optional[str] = None
    type: Optional[str] = None  # journal-article, book, etc.

    # 生成的 citekey
    suggested_citekey: Optional[str] = None

    def to_dict(self) -> Dict:
        """轉換為字典"""
        return {
            'doi': self.doi,
            'title': self.title,
            'authors': self.authors,
            'year': self.year,
            'journal': self.journal,
            'publisher': self.publisher,
            'volume': self.volume,
            'issue': self.issue,
            'pages': self.pages,
            'abstract': self.abstract,
            'subject': self.subject,
            'url': self.url,
            'type': self.type,
            'suggested_citekey': self.suggested_citekey,
        }


class DOIResolver:
    """
    DOI 解析與元數據查詢

    使用 CrossRef API (https://api.crossref.org)
    """

    # CrossRef API 端點
    CROSSREF_API = "https://api.crossref.org/works"

    # DOI 正則表達式模式
    DOI_PATTERNS = [
        # 標準 DOI 格式
        r'(?:doi[:\s]*)?(?:https?://(?:dx\.)?doi\.org/)?'
        r'(10\.\d{4,}/[^\s\]\)>"\';,]+)',
        # DOI 在括號或引號中
        r'DOI[:\s]+(10\.\d{4,}/[^\s\]\)>"\';,]+)',
    ]

    def __init__(self, email: Optional[str] = None, timeout: int = 30):
        """
        初始化 DOI 解析器

        Args:
            email: 聯繫郵箱（CrossRef 建議提供，可獲得更好的服務）
            timeout: 請求超時時間（秒）
        """
        self.email = email
        self.timeout = timeout
        self.session = requests.Session()

        # 設置 User-Agent（CrossRef 要求）
        user_agent = "claude-lit-workflow/0.8.0"
        if email:
            user_agent += f" (mailto:{email})"
        self.session.headers.update({
            'User-Agent': user_agent
        })

        # 速率限制（CrossRef 限制：50 req/sec）
        self._last_request_time = 0
        self._min_interval = 0.1  # 100ms 間隔

    def extract_doi_from_text(self, text: str) -> List[str]:
        """
        從文本中提取 DOI

        Args:
            text: 文本內容（PDF 文本、元數據等）

        Returns:
            找到的 DOI 列表（去重）
        """
        dois = set()

        for pattern in self.DOI_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # 清理 DOI
                doi = self._clean_doi(match)
                if doi:
                    dois.add(doi)

        return list(dois)

    def extract_doi_from_pdf(self, pdf_path: Path) -> Optional[str]:
        """
        從 PDF 文件提取 DOI

        嘗試順序：
        1. PDF 元數據
        2. 第一頁文本

        Args:
            pdf_path: PDF 文件路徑

        Returns:
            找到的 DOI，未找到返回 None
        """
        try:
            import pdfplumber
        except ImportError:
            print("⚠️  需要安裝 pdfplumber: pip install pdfplumber")
            return None

        try:
            with pdfplumber.open(pdf_path) as pdf:
                # 1. 檢查 PDF 元數據
                metadata = pdf.metadata or {}
                for key in ['doi', 'DOI', 'Subject', 'Keywords']:
                    if key in metadata and metadata[key]:
                        dois = self.extract_doi_from_text(str(metadata[key]))
                        if dois:
                            return dois[0]

                # 2. 檢查第一頁文本
                if pdf.pages:
                    first_page = pdf.pages[0]
                    text = first_page.extract_text() or ""
                    # 只檢查前 2000 字元（通常 DOI 在頭部）
                    dois = self.extract_doi_from_text(text[:2000])
                    if dois:
                        return dois[0]

        except Exception as e:
            print(f"⚠️  PDF DOI 提取失敗: {e}")

        return None

    def resolve(self, doi: str) -> Optional[DOIMetadata]:
        """
        從 CrossRef 查詢 DOI 元數據

        Args:
            doi: DOI 字串

        Returns:
            DOIMetadata 對象，查詢失敗返回 None
        """
        doi = self._clean_doi(doi)
        if not doi:
            return None

        # 速率限制
        self._rate_limit()

        try:
            url = f"{self.CROSSREF_API}/{doi}"
            response = self.session.get(url, timeout=self.timeout)

            if response.status_code == 404:
                print(f"⚠️  DOI 未找到: {doi}")
                return None

            response.raise_for_status()
            data = response.json()

            if data.get('status') != 'ok':
                return None

            return self._parse_crossref_response(data['message'])

        except requests.exceptions.Timeout:
            print(f"⚠️  CrossRef 請求超時: {doi}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"⚠️  CrossRef 請求失敗: {e}")
            return None
        except Exception as e:
            print(f"⚠️  DOI 解析錯誤: {e}")
            return None

    def resolve_batch(
        self,
        dois: List[str],
        delay: float = 0.2
    ) -> Dict[str, Optional[DOIMetadata]]:
        """
        批次查詢多個 DOI

        Args:
            dois: DOI 列表
            delay: 每次請求間隔（秒）

        Returns:
            DOI -> DOIMetadata 字典
        """
        results = {}

        for i, doi in enumerate(dois):
            print(f"  [{i+1}/{len(dois)}] 查詢 {doi}...", end=" ")
            result = self.resolve(doi)
            results[doi] = result

            if result:
                print(f"✓ {result.title[:40]}...")
            else:
                print("✗")

            if i < len(dois) - 1:
                time.sleep(delay)

        return results

    def _clean_doi(self, doi: str) -> Optional[str]:
        """
        清理 DOI 字串

        移除 URL 前綴、空白、尾部標點符號
        """
        if not doi:
            return None

        # 移除 URL 前綴
        doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
        doi = re.sub(r'^doi[:\s]*', '', doi, flags=re.IGNORECASE)

        # 移除空白
        doi = doi.strip()

        # 移除尾部標點符號（但保留 DOI 中可能的有效字元）
        doi = re.sub(r'[\s.,;:)\]>"\']+$', '', doi)

        # 驗證 DOI 格式
        if not re.match(r'^10\.\d{4,}/', doi):
            return None

        return doi

    def _parse_crossref_response(self, data: Dict) -> DOIMetadata:
        """
        解析 CrossRef API 回應

        Args:
            data: CrossRef 回應的 message 部分

        Returns:
            DOIMetadata 對象
        """
        # DOI
        doi = data.get('DOI', '')

        # 標題
        title_list = data.get('title', [])
        title = title_list[0] if title_list else ''

        # 作者
        authors = []
        for author in data.get('author', []):
            if 'family' in author:
                name = author.get('family', '')
                if 'given' in author:
                    name = f"{author['given']} {name}"
                authors.append(name)

        # 年份
        year = None
        date_parts = data.get('published-print', {}).get('date-parts', [[]])
        if not date_parts[0]:
            date_parts = data.get('published-online', {}).get('date-parts', [[]])
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        # 期刊
        container = data.get('container-title', [])
        journal = container[0] if container else None

        # 出版社
        publisher = data.get('publisher')

        # 卷/期/頁
        volume = data.get('volume')
        issue = data.get('issue')
        pages = data.get('page')

        # 摘要
        abstract = data.get('abstract', '')
        if abstract:
            # 移除 jats 標籤
            abstract = re.sub(r'<[^>]+>', '', abstract)
            abstract = abstract.strip()

        # 學科
        subject = data.get('subject', [])

        # URL
        url = data.get('URL')

        # 類型
        doc_type = data.get('type')

        # 生成 citekey
        suggested_citekey = self._generate_citekey(authors, year)

        return DOIMetadata(
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            publisher=publisher,
            volume=volume,
            issue=issue,
            pages=pages,
            abstract=abstract if len(abstract) > 10 else None,
            subject=subject,
            url=url,
            type=doc_type,
            suggested_citekey=suggested_citekey
        )

    def _generate_citekey(
        self,
        authors: List[str],
        year: Optional[int]
    ) -> Optional[str]:
        """
        從作者和年份生成 citekey

        格式: FirstAuthorLastName-Year
        """
        if not authors:
            return None

        # 提取第一作者姓氏
        first_author = authors[0]
        # 處理 "First Last" 格式
        parts = first_author.split()
        last_name = parts[-1] if parts else first_author

        # 移除特殊字元
        last_name = re.sub(r'[^\w]', '', last_name)

        if year:
            return f"{last_name}-{year}"
        else:
            return last_name

    def _rate_limit(self):
        """速率限制"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()


def main():
    """測試 DOI 解析器"""
    import sys
    import io

    # 修復 Windows 終端 UTF-8 編碼
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    resolver = DOIResolver()

    print("=" * 60)
    print("DOI Resolver 測試")
    print("=" * 60)

    # 測試 DOI
    test_dois = [
        "10.1017/S0140525X99002149",  # Barsalou 1999
        "10.1037/a0024587",           # 心理學論文
        "https://doi.org/10.1038/nature12373",  # Nature
    ]

    for doi in test_dois:
        print(f"\n🔍 查詢: {doi}")
        result = resolver.resolve(doi)

        if result:
            print(f"   ✅ 標題: {result.title[:60]}...")
            print(f"   作者: {', '.join(result.authors[:3])}")
            print(f"   年份: {result.year}")
            print(f"   期刊: {result.journal or 'N/A'}")
            print(f"   建議 citekey: {result.suggested_citekey}")
        else:
            print("   ❌ 未找到")

    # 測試 DOI 提取
    print("\n" + "-" * 60)
    print("DOI 提取測試")
    print("-" * 60)

    test_texts = [
        "This paper (doi:10.1037/a0024587) discusses...",
        "Available at https://doi.org/10.1038/nature12373",
        "DOI: 10.1016/j.cognition.2020.104328",
    ]

    for text in test_texts:
        dois = resolver.extract_doi_from_text(text)
        print(f"\n   文本: {text[:50]}...")
        print(f"   提取: {dois}")

    print("\n" + "=" * 60)
    print("✅ 測試完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
