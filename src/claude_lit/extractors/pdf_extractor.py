"""
PDF提取器模組
基於Journal Club的PDF處理邏輯，支援結構化提取
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
import json

import logging

logger = logging.getLogger("claude_lit_workflow.extractors.pdf_extractor")

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False


class PDFExtractor:
    """PDF文本和結構提取器"""

    def __init__(self, max_chars: int = 50000, method: str = "pdfplumber"):
        """
        初始化PDF提取器

        Args:
            max_chars: 最大字元數限制
            method: 提取方法 ("pdfplumber" 或 "pypdf2")
        """
        self.max_chars = max_chars
        self.method = method

        if method == "pdfplumber" and not PDFPLUMBER_AVAILABLE:
            raise ImportError("pdfplumber not installed. Run: pip install pdfplumber")
        elif method == "pypdf2" and not PYPDF2_AVAILABLE:
            raise ImportError("PyPDF2 not installed. Run: pip install PyPDF2")

    def extract(self, pdf_path: str, extract_tables: bool = True) -> Dict[str, Any]:
        """
        提取PDF內容和結構

        Args:
            pdf_path: PDF文件路徑
            extract_tables: 是否提取表格（預設True）

        Returns:
            包含提取結果的字典
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        # 根據方法選擇提取函數
        if self.method == "pdfplumber":
            full_text = self._extract_with_pdfplumber(pdf_path)
        else:
            full_text = self._extract_with_pypdf2(pdf_path)

        # 提取表格（僅pdfplumber支援）
        tables = []
        if extract_tables and self.method == "pdfplumber":
            tables = self._extract_tables_with_pdfplumber(pdf_path)

        # 限制字元數
        if len(full_text) > self.max_chars:
            full_text = full_text[:self.max_chars]
            truncated = True
        else:
            truncated = False

        # 提取結構化信息
        structure = self._parse_structure(full_text)

        return {
            "file_path": str(pdf_path),
            "file_name": pdf_path.name,
            "full_text": full_text,
            "char_count": len(full_text),
            "truncated": truncated,
            "structure": structure,
            "tables": tables,
            "table_count": len(tables),
            "extraction_method": self.method
        }

    def _extract_with_pdfplumber(self, pdf_path: Path) -> str:
        """使用pdfplumber提取文字"""
        text_parts = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    def _extract_tables_with_pdfplumber(self, pdf_path: Path) -> List[Dict[str, Any]]:
        """
        使用pdfplumber提取PDF中的所有表格

        Returns:
            表格列表，每個表格包含:
            - page: 頁碼
            - index: 該頁表格索引
            - rows: 行數
            - cols: 列數
            - data: 原始表格數據
            - markdown: Markdown格式
        """
        tables = []

        if not PDFPLUMBER_AVAILABLE:
            return tables

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_tables = page.extract_tables()

                    if not page_tables:
                        continue

                    for table_idx, table_data in enumerate(page_tables):
                        if not table_data or len(table_data) < 2:
                            # 跳過空表格或只有一行的表格
                            continue

                        # 清理表格數據
                        cleaned_table = self._clean_table_data(table_data)

                        if cleaned_table:
                            markdown = self._table_to_markdown(cleaned_table)
                            tables.append({
                                'page': page_num,
                                'index': table_idx,
                                'rows': len(cleaned_table),
                                'cols': len(cleaned_table[0]) if cleaned_table else 0,
                                'data': cleaned_table,
                                'markdown': markdown
                            })
        except Exception as e:
            # 表格提取失敗不影響主流程
            logger.info(f"[警告] 表格提取失敗: {e}")

        return tables

    def _clean_table_data(self, table: List[List]) -> List[List[str]]:
        """
        清理表格數據
        - 移除空行空列
        - 處理 None 值
        - 合併多行文字
        """
        if not table:
            return []

        cleaned = []
        for row in table:
            if row is None:
                continue

            # 處理每個儲存格
            cleaned_row = []
            for cell in row:
                if cell is None:
                    cleaned_row.append('')
                elif isinstance(cell, str):
                    # 清理多餘空白和換行
                    cleaned_row.append(' '.join(cell.split()))
                else:
                    cleaned_row.append(str(cell))

            # 跳過完全空白的行
            if any(cell.strip() for cell in cleaned_row):
                cleaned.append(cleaned_row)

        return cleaned

    def _table_to_markdown(self, table: List[List[str]]) -> str:
        """
        將表格轉換為 Markdown 格式

        Args:
            table: 清理後的表格數據（二維列表）

        Returns:
            Markdown 格式的表格字串
        """
        if not table or len(table) < 1:
            return ''

        lines = []

        # 計算每列最大寬度（用於對齊）
        col_count = max(len(row) for row in table)
        col_widths = [3] * col_count  # 最小寬度3

        for row in table:
            for i, cell in enumerate(row):
                if i < col_count:
                    col_widths[i] = max(col_widths[i], len(cell))

        # 生成表頭（第一行）
        header = table[0]
        # 補齊列數
        while len(header) < col_count:
            header.append('')

        header_line = '| ' + ' | '.join(
            cell.ljust(col_widths[i]) for i, cell in enumerate(header)
        ) + ' |'
        lines.append(header_line)

        # 生成分隔線
        separator = '| ' + ' | '.join(
            '-' * col_widths[i] for i in range(col_count)
        ) + ' |'
        lines.append(separator)

        # 生成數據行
        for row in table[1:]:
            # 補齊列數
            while len(row) < col_count:
                row.append('')

            row_line = '| ' + ' | '.join(
                cell.ljust(col_widths[i]) for i, cell in enumerate(row)
            ) + ' |'
            lines.append(row_line)

        return '\n'.join(lines)

    def _extract_with_pypdf2(self, pdf_path: Path) -> str:
        """使用PyPDF2提取文字"""
        text_parts = []

        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    def _parse_structure(self, text: str) -> Dict[str, Any]:
        """
        解析論文結構

        識別：標題、作者、摘要、章節等
        """
        structure = {
            "title": self._extract_title(text),
            "authors": self._extract_authors(text),
            "abstract": self._extract_abstract(text),
            "sections": self._extract_sections(text),
            "keywords": self._extract_keywords(text),
            "references_found": self._has_references(text)
        }

        return structure

    def _extract_title(self, text: str) -> Optional[str]:
        """提取論文標題（通常在文檔最前面）"""
        lines = text.split('\n')
        # 取前10行中最長的非空行作為標題候選
        candidates = [line.strip() for line in lines[:10] if line.strip() and len(line.strip()) > 10]
        if candidates:
            return candidates[0]
        return None

    def _extract_authors(self, text: str) -> List[str]:
        """提取作者列表"""
        authors = []
        # 簡單的作者識別模式（可以進一步改進）
        author_patterns = [
            r'[A-Z][a-z]+\s+[A-Z][a-z]+',  # John Smith
            r'[A-Z]\.\s*[A-Z][a-z]+',       # J. Smith
        ]

        lines = text.split('\n')[:20]  # 只檢查前20行
        for line in lines:
            for pattern in author_patterns:
                matches = re.findall(pattern, line)
                authors.extend(matches)

        return list(set(authors))[:10]  # 最多返回10位作者，去重

    def _extract_abstract(self, text: str) -> Optional[str]:
        """提取摘要"""
        # 尋找Abstract或摘要標記
        abstract_patterns = [
            r'Abstract\s*[:\n]+(.*?)(?=\n\n[A-Z]|\nIntroduction|\n1\.)',
            r'摘要\s*[:\n]+(.*?)(?=\n\n|\n[一二三四五])',
            r'ABSTRACT\s*[:\n]+(.*?)(?=\n\n[A-Z]|\nINTRODUCTION)',
        ]

        for pattern in abstract_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                abstract = match.group(1).strip()
                # 限制摘要長度
                if len(abstract) > 2000:
                    abstract = abstract[:2000]
                return abstract

        return None

    def _extract_sections(self, text: str) -> List[Dict[str, str]]:
        """提取主要章節"""
        sections = []

        # 常見的章節標題模式
        section_patterns = [
            r'\n(Introduction|Background|Related Work|Methods|Methodology|Results|Discussion|Conclusion|References)\s*\n',
            r'\n([1-9]\.?\s+[A-Z][a-z]+.*?)\n',
            r'\n(摘要|簡介|背景|方法|結果|討論|結論|參考文獻)\s*\n',
        ]

        for pattern in section_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                section_title = match.group(1).strip()
                if 5 <= len(section_title) <= 100:  # 合理的標題長度
                    sections.append({
                        "title": section_title,
                        "position": match.start()
                    })

        # 按位置排序
        sections.sort(key=lambda x: x['position'])

        return sections[:20]  # 最多返回20個章節

    def _extract_keywords(self, text: str) -> List[str]:
        """提取關鍵詞"""
        keywords = []

        # 尋找Keywords或關鍵詞標記
        keyword_patterns = [
            r'Keywords?\s*[:\-]+(.*?)(?=\n\n|\n[A-Z])',
            r'關鍵詞\s*[:\-]+(.*?)(?=\n\n)',
        ]

        for pattern in keyword_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                keyword_text = match.group(1)
                # 分割關鍵詞（可能用逗號、分號或換行分隔）
                keywords = re.split(r'[,;，；\n]+', keyword_text)
                keywords = [kw.strip() for kw in keywords if kw.strip()]
                break

        return keywords[:10]  # 最多返回10個關鍵詞

    def _has_references(self, text: str) -> bool:
        """檢查是否包含參考文獻區域"""
        reference_indicators = [
            'References',
            'REFERENCES',
            'Bibliography',
            '參考文獻',
            'Reference List'
        ]

        return any(indicator in text for indicator in reference_indicators)

    def extract_to_json(self, pdf_path: str, output_path: Optional[str] = None) -> str:
        """
        提取PDF並輸出為JSON格式

        Args:
            pdf_path: PDF文件路徑
            output_path: JSON輸出路徑（可選）

        Returns:
            JSON字符串
        """
        result = self.extract(pdf_path)

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

        return json.dumps(result, ensure_ascii=False, indent=2)


def extract_pdf_text(pdf_path: str, max_chars: int = 50000) -> str:
    """
    簡化的PDF文字提取函數（與Journal Club兼容）

    Args:
        pdf_path: PDF文件路徑
        max_chars: 最大字元數

    Returns:
        提取的文字內容
    """
    extractor = PDFExtractor(max_chars=max_chars)
    result = extractor.extract(pdf_path)
    return result['full_text']


if __name__ == "__main__":
    # 測試代碼
    import sys

    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
        extractor = PDFExtractor()
        result = extractor.extract(pdf_file)

        print(f"=== PDF提取結果 ===")
        print(f"文件: {result['file_name']}")
        print(f"字元數: {result['char_count']:,}")
        print(f"截斷: {result['truncated']}")
        print(f"\n=== 結構信息 ===")
        print(f"標題: {result['structure']['title']}")
        print(f"作者: {', '.join(result['structure']['authors'])}")
        print(f"章節數: {len(result['structure']['sections'])}")
        print(f"關鍵詞: {', '.join(result['structure']['keywords'])}")
        print(f"\n=== 摘要 ===")
        print(result['structure']['abstract'][:500] if result['structure']['abstract'] else "未找到")

        # 顯示表格資訊
        print(f"\n=== 表格提取 ===")
        print(f"表格數量: {result['table_count']}")
        for i, table in enumerate(result['tables'], 1):
            print(f"\n--- 表格 {i} (頁 {table['page']}) ---")
            print(f"大小: {table['rows']} 行 × {table['cols']} 列")
            print("Markdown 預覽:")
            # 只顯示前10行
            md_lines = table['markdown'].split('\n')
            for line in md_lines[:10]:
                print(f"  {line}")
            if len(md_lines) > 10:
                print(f"  ... (共 {len(md_lines)} 行)")
    else:
        print("用法: python pdf_extractor.py <pdf_file_path>")
