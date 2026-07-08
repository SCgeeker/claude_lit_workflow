"""
知識庫管理模組
混合式架構：Markdown文件 + SQLite索引
"""

import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Literal, TypedDict
from datetime import datetime
import re
import yaml


class ZettelAddResult(TypedDict):
    """add_zettel_card() 回傳結果結構"""
    status: Literal['inserted', 'duplicate', 'error']
    card_id: int
    message: str


class KnowledgeBaseManager:
    """知識庫管理器"""

    def __init__(self, kb_root: str = "knowledge_base", db_path: Optional[str] = None):
        """
        初始化知識庫管理器

        Args:
            kb_root: 知識庫根目錄
            db_path: 數據庫路徑（可選）
        """
        self.kb_root = Path(kb_root)
        self.kb_root.mkdir(parents=True, exist_ok=True)

        self.papers_dir = self.kb_root / "papers"
        self.papers_dir.mkdir(exist_ok=True)

        self.metadata_dir = self.kb_root / "metadata"
        self.metadata_dir.mkdir(exist_ok=True)

        self.db_path = db_path or str(self.kb_root / "index.db")
        self._init_database()

    def _init_database(self):
        """初始化SQLite數據庫"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 論文表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                title TEXT,
                authors TEXT,
                year INTEGER,
                abstract TEXT,
                keywords TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 主題表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 論文-主題關聯表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_topics (
                paper_id INTEGER,
                topic_id INTEGER,
                relevance REAL DEFAULT 1.0,
                FOREIGN KEY (paper_id) REFERENCES papers(id),
                FOREIGN KEY (topic_id) REFERENCES topics(id),
                PRIMARY KEY (paper_id, topic_id)
            )
        """)

        # 引用關係表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS citations (
                source_paper_id INTEGER,
                target_paper_id INTEGER,
                citation_type TEXT,
                FOREIGN KEY (source_paper_id) REFERENCES papers(id),
                FOREIGN KEY (target_paper_id) REFERENCES papers(id),
                PRIMARY KEY (source_paper_id, target_paper_id)
            )
        """)

        # Zettelkasten卡片表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS zettel_cards (
                card_id INTEGER PRIMARY KEY AUTOINCREMENT,
                zettel_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                core_concept TEXT,
                description TEXT,
                card_type TEXT DEFAULT 'concept',
                domain TEXT NOT NULL,
                tags TEXT,
                paper_id INTEGER,
                zettel_folder TEXT NOT NULL,
                source_info TEXT,
                file_path TEXT UNIQUE NOT NULL,
                ai_notes TEXT,
                human_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE SET NULL
            )
        """)

        # Zettelkasten連結表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS zettel_links (
                link_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_card_id INTEGER NOT NULL,
                target_zettel_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                context TEXT,
                is_cross_paper BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_card_id) REFERENCES zettel_cards(card_id) ON DELETE CASCADE
            )
        """)

        # 論文-Zettelkasten連結表（基於向量相似度）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS paper_zettel_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id INTEGER NOT NULL,
                card_id INTEGER NOT NULL,
                similarity REAL NOT NULL,
                method TEXT DEFAULT 'vector_similarity',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                FOREIGN KEY (card_id) REFERENCES zettel_cards(card_id) ON DELETE CASCADE,
                UNIQUE(paper_id, card_id)
            )
        """)

        # Zettelkasten索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zettel_cards_zettel_id ON zettel_cards(zettel_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zettel_cards_domain ON zettel_cards(domain)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zettel_cards_card_type ON zettel_cards(card_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zettel_cards_paper_id ON zettel_cards(paper_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zettel_cards_folder ON zettel_cards(zettel_folder)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zettel_links_source ON zettel_links(source_card_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zettel_links_target ON zettel_links(target_zettel_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_zettel_links_relation ON zettel_links(relation_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_zettel_links_paper ON paper_zettel_links(paper_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_zettel_links_card ON paper_zettel_links(card_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_paper_zettel_links_similarity ON paper_zettel_links(similarity)
        """)

        # 全文搜索表（FTS5） - Papers
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                title,
                authors,
                abstract,
                content,
                keywords,
                content='papers',
                content_rowid='id'
            )
        """)

        # 全文搜索表（FTS5） - Zettelkasten卡片
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS zettel_cards_fts USING fts5(
                title,
                content,
                core_concept,
                description,
                tags,
                ai_notes,
                human_notes,
                content='zettel_cards',
                content_rowid='card_id'
            )
        """)

        # FTS5觸發器 - 自動同步Zettelkasten卡片到全文搜索
        # INSERT觸發器
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS zettel_cards_ai AFTER INSERT ON zettel_cards BEGIN
                INSERT INTO zettel_cards_fts(rowid, title, content, core_concept, description, tags, ai_notes, human_notes)
                VALUES (new.card_id, new.title, new.content, new.core_concept, new.description, new.tags, new.ai_notes, new.human_notes);
            END;
        """)

        # DELETE觸發器
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS zettel_cards_ad AFTER DELETE ON zettel_cards BEGIN
                DELETE FROM zettel_cards_fts WHERE rowid = old.card_id;
            END;
        """)

        # UPDATE觸發器
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS zettel_cards_au AFTER UPDATE ON zettel_cards BEGIN
                DELETE FROM zettel_cards_fts WHERE rowid = old.card_id;
                INSERT INTO zettel_cards_fts(rowid, title, content, core_concept, description, tags, ai_notes, human_notes)
                VALUES (new.card_id, new.title, new.content, new.core_concept, new.description, new.tags, new.ai_notes, new.human_notes);
            END;
        """)

        # 擴展papers表（Zotero整合） - 使用ALTER TABLE添加新欄位
        # 檢查並添加zotero_key欄位
        cursor.execute("PRAGMA table_info(papers)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'zotero_key' not in columns:
            cursor.execute("""
                ALTER TABLE papers ADD COLUMN zotero_key TEXT
            """)
            # 為zotero_key創建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_papers_zotero_key ON papers(zotero_key)
            """)

        if 'source' not in columns:
            cursor.execute("""
                ALTER TABLE papers ADD COLUMN source TEXT DEFAULT 'manual'
            """)
            # 更新現有記錄的source為'manual'（如果為NULL）
            cursor.execute("""
                UPDATE papers SET source = 'manual' WHERE source IS NULL
            """)
            # 為source創建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source)
            """)

        if 'doi' not in columns:
            cursor.execute("""
                ALTER TABLE papers ADD COLUMN doi TEXT
            """)
            # 為doi創建唯一索引（允許NULL）
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi) WHERE doi IS NOT NULL
            """)

        if 'url' not in columns:
            cursor.execute("""
                ALTER TABLE papers ADD COLUMN url TEXT
            """)

        # 添加 cite_key 欄位（Citekey 系統）
        if 'cite_key' not in columns:
            cursor.execute("""
                ALTER TABLE papers ADD COLUMN cite_key TEXT
            """)
            # 為 cite_key 創建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_papers_cite_key ON papers(cite_key)
            """)

        # 添加 original_citekey 欄位（保存原始書目檔中的 citekey）
        if 'original_citekey' not in columns:
            cursor.execute("""
                ALTER TABLE papers ADD COLUMN original_citekey TEXT
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_papers_original_citekey ON papers(original_citekey)
            """)

        conn.commit()
        conn.close()

    def add_paper(self,
                  file_path: str,
                  title: str,
                  authors: List[str],
                  year: Optional[int] = None,
                  abstract: Optional[str] = None,
                  keywords: Optional[List[str]] = None,
                  content: Optional[str] = None,
                  cite_key: Optional[str] = None,
                  zotero_key: Optional[str] = None,
                  source: str = 'manual',
                  doi: Optional[str] = None,
                  url: Optional[str] = None) -> int:
        """
        新增論文到知識庫

        Args:
            file_path: Markdown文件路徑
            title: 論文標題
            authors: 作者列表
            year: 發表年份
            abstract: 摘要
            keywords: 關鍵詞列表
            content: 完整內容（用於全文搜索）
            cite_key: BibTeX cite_key（原始引用鍵）
            zotero_key: Zotero 內部 key
            source: 論文來源（manual/zotero/obsidian）
            doi: DOI
            url: 論文URL

        Returns:
            論文ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        authors_str = json.dumps(authors, ensure_ascii=False)
        keywords_str = json.dumps(keywords or [], ensure_ascii=False)

        try:
            cursor.execute("""
                INSERT INTO papers (file_path, title, authors, year, abstract, keywords,
                                   cite_key, zotero_key, source, doi, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (file_path, title, authors_str, year, abstract, keywords_str,
                  cite_key, zotero_key, source, doi, url))

            paper_id = cursor.lastrowid

            # 添加到全文搜索索引
            if content:
                cursor.execute("""
                    INSERT INTO papers_fts (rowid, title, authors, abstract, content, keywords)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (paper_id, title, ', '.join(authors), abstract or '', content, ', '.join(keywords or [])))

            conn.commit()
            return paper_id

        except sqlite3.IntegrityError as e:
            # UNIQUE 約束衝突，嘗試更新現有記錄
            error_msg = str(e).lower()

            # 判斷是哪個欄位衝突
            if 'doi' in error_msg and doi:
                # DOI 重複，根據 DOI 更新
                cursor.execute("""
                    UPDATE papers
                    SET title=?, authors=?, year=?, abstract=?, keywords=?,
                        cite_key=?, zotero_key=?, source=?, file_path=?, url=?, updated_at=CURRENT_TIMESTAMP
                    WHERE doi=?
                """, (title, authors_str, year, abstract, keywords_str,
                      cite_key, zotero_key, source, file_path, url, doi))
                cursor.execute("SELECT id FROM papers WHERE doi=?", (doi,))
            elif 'cite_key' in error_msg and cite_key:
                # cite_key 重複，根據 cite_key 更新
                cursor.execute("""
                    UPDATE papers
                    SET title=?, authors=?, year=?, abstract=?, keywords=?,
                        zotero_key=?, source=?, file_path=?, doi=?, url=?, updated_at=CURRENT_TIMESTAMP
                    WHERE cite_key=?
                """, (title, authors_str, year, abstract, keywords_str,
                      zotero_key, source, file_path, doi, url, cite_key))
                cursor.execute("SELECT id FROM papers WHERE cite_key=?", (cite_key,))
            else:
                # file_path 重複，根據 file_path 更新
                cursor.execute("""
                    UPDATE papers
                    SET title=?, authors=?, year=?, abstract=?, keywords=?,
                        cite_key=?, zotero_key=?, source=?, doi=?, url=?, updated_at=CURRENT_TIMESTAMP
                    WHERE file_path=?
                """, (title, authors_str, year, abstract, keywords_str,
                      cite_key, zotero_key, source, doi, url, file_path))
                cursor.execute("SELECT id FROM papers WHERE file_path=?", (file_path,))

            row = cursor.fetchone()
            if row:
                paper_id = row[0]
                conn.commit()
                return paper_id
            else:
                raise ValueError(f"無法更新論文記錄: {e}")

        finally:
            conn.close()

    def delete_paper(self, paper_id: int) -> bool:
        """
        刪除論文

        Args:
            paper_id: 論文 ID

        Returns:
            是否成功刪除
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 獲取論文資訊（用於刪除檔案）
            cursor.execute("SELECT file_path FROM papers WHERE id=?", (paper_id,))
            row = cursor.fetchone()

            if not row:
                return False

            file_path = row[0]

            # 刪除 FTS 索引
            cursor.execute("DELETE FROM papers_fts WHERE rowid=?", (paper_id,))

            # 刪除相關連結
            cursor.execute("DELETE FROM paper_topics WHERE paper_id=?", (paper_id,))
            cursor.execute("DELETE FROM citations WHERE source_paper_id=? OR target_paper_id=?", (paper_id, paper_id))

            # 刪除論文記錄
            cursor.execute("DELETE FROM papers WHERE id=?", (paper_id,))

            conn.commit()

            # 刪除 Markdown 檔案（可選）
            if file_path:
                md_path = Path(file_path)
                if md_path.exists():
                    md_path.unlink()

            return True

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

    def update_paper(self, paper_id: int, **kwargs) -> bool:
        """
        更新論文元數據

        Args:
            paper_id: 論文 ID
            **kwargs: 要更新的欄位
                - title: 標題
                - authors: 作者列表
                - year: 年份
                - abstract: 摘要
                - keywords: 關鍵詞列表
                - cite_key: Citekey
                - doi: DOI
                - url: URL

        Returns:
            是否成功更新
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 構建更新語句
            updates = []
            values = []

            field_mapping = {
                'title': 'title',
                'authors': 'authors',
                'year': 'year',
                'abstract': 'abstract',
                'keywords': 'keywords',
                'cite_key': 'cite_key',
                'doi': 'doi',
                'url': 'url',
            }

            for key, column in field_mapping.items():
                if key in kwargs and kwargs[key] is not None:
                    value = kwargs[key]
                    # JSON 序列化列表類型
                    if key in ['authors', 'keywords'] and isinstance(value, list):
                        value = json.dumps(value, ensure_ascii=False)
                    updates.append(f"{column}=?")
                    values.append(value)

            if not updates:
                return False

            # 添加更新時間
            updates.append("updated_at=CURRENT_TIMESTAMP")

            # 執行更新
            sql = f"UPDATE papers SET {', '.join(updates)} WHERE id=?"
            values.append(paper_id)
            cursor.execute(sql, values)

            # 更新 FTS 索引
            paper = self.get_paper_by_id(paper_id)
            if paper:
                cursor.execute("DELETE FROM papers_fts WHERE rowid=?", (paper_id,))
                cursor.execute("""
                    INSERT INTO papers_fts (rowid, title, authors, abstract, content, keywords)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    paper_id,
                    paper['title'],
                    ', '.join(paper['authors']),
                    paper.get('abstract') or '',
                    '',  # content
                    ', '.join(paper.get('keywords') or [])
                ))

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            raise e

        finally:
            conn.close()

    def search_papers(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        全文搜索論文

        Args:
            query: 搜索查詢
            limit: 返回結果數量限制

        Returns:
            匹配的論文列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.id, p.file_path, p.title, p.authors, p.year, p.abstract, p.keywords
            FROM papers p
            JOIN papers_fts fts ON p.id = fts.rowid
            WHERE papers_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "file_path": row[1],
                "title": row[2],
                "authors": json.loads(row[3]) if row[3] else [],
                "year": row[4],
                "abstract": row[5],
                "keywords": json.loads(row[6]) if row[6] else []
            })

        conn.close()
        return results

    def get_paper_by_id(self, paper_id: int) -> Optional[Dict[str, Any]]:
        """根據ID獲取論文信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, file_path, title, authors, year, abstract, keywords, created_at, updated_at,
                   zotero_key, source, doi, url, cite_key
            FROM papers
            WHERE id = ?
        """, (paper_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "id": row[0],
                "file_path": row[1],
                "title": row[2],
                "authors": json.loads(row[3]) if row[3] else [],
                "year": row[4],
                "abstract": row[5],
                "keywords": json.loads(row[6]) if row[6] else [],
                "created_at": row[7],
                "updated_at": row[8],
                "zotero_key": row[9],
                "source": row[10],
                "doi": row[11],
                "url": row[12],
                "cite_key": row[13]  # ⭐ 新增：原始 bibtex key
            }
        return None

    def get_paper_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        根據 DOI 獲取論文信息

        Args:
            doi: DOI 字串（支援帶或不帶 URL 前綴）

        Returns:
            論文信息字典，未找到返回 None
        """
        import re

        # 清理 DOI（移除 URL 前綴）
        doi_clean = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi.strip())

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, file_path, title, authors, year, abstract, keywords, created_at, updated_at,
                   zotero_key, source, doi, url, cite_key
            FROM papers
            WHERE doi = ? OR doi LIKE ?
        """, (doi_clean, f"%{doi_clean}%"))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "id": row[0],
                "file_path": row[1],
                "title": row[2],
                "authors": json.loads(row[3]) if row[3] else [],
                "year": row[4],
                "abstract": row[5],
                "keywords": json.loads(row[6]) if row[6] else [],
                "created_at": row[7],
                "updated_at": row[8],
                "zotero_key": row[9],
                "source": row[10],
                "doi": row[11],
                "url": row[12],
                "cite_key": row[13]
            }
        return None

    def get_paper_by_citekey(self, citekey: str) -> Optional[Dict[str, Any]]:
        """
        根據 citekey 獲取論文信息

        支援多種匹配方式：
        1. cite_key 精確匹配
        2. cite_key 模糊匹配（忽略大小寫和分隔符）
        3. Unicode 正規化匹配（處理 ü→u, é→e 等）

        Args:
            citekey: citekey 字串

        Returns:
            論文信息字典，未找到返回 None
        """
        from claude_lit.utils.citekey_resolver import normalize_citekey

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 精確匹配
        cursor.execute("""
            SELECT id, file_path, title, authors, year, abstract, keywords, created_at, updated_at,
                   zotero_key, source, doi, url, cite_key
            FROM papers
            WHERE cite_key = ? OR cite_key = ? COLLATE NOCASE
        """, (citekey, citekey))

        row = cursor.fetchone()

        if not row:
            # 模糊匹配（移除分隔符）
            citekey_normalized = citekey.replace('-', '').replace('_', '').lower()
            cursor.execute("""
                SELECT id, file_path, title, authors, year, abstract, keywords, created_at, updated_at,
                       zotero_key, source, doi, url, cite_key
                FROM papers
                WHERE REPLACE(REPLACE(LOWER(cite_key), '-', ''), '_', '') = ?
            """, (citekey_normalized,))
            row = cursor.fetchone()

        if not row:
            # Unicode 正規化匹配（處理特殊字元如 ü, é）
            query_normalized = normalize_citekey(citekey).lower()
            cursor.execute("""
                SELECT id, file_path, title, authors, year, abstract, keywords, created_at, updated_at,
                       zotero_key, source, doi, url, cite_key
                FROM papers
            """)
            for candidate in cursor.fetchall():
                db_citekey = candidate[13] or ''
                if normalize_citekey(db_citekey).lower() == query_normalized:
                    row = candidate
                    break

        conn.close()

        if row:
            return {
                "id": row[0],
                "file_path": row[1],
                "title": row[2],
                "authors": json.loads(row[3]) if row[3] else [],
                "year": row[4],
                "abstract": row[5],
                "keywords": json.loads(row[6]) if row[6] else [],
                "created_at": row[7],
                "updated_at": row[8],
                "zotero_key": row[9],
                "source": row[10],
                "doi": row[11],
                "url": row[12],
                "cite_key": row[13]
            }
        return None

    def update_cite_key(self, paper_id: int, cite_key: str) -> bool:
        """
        更新論文的 cite_key

        Args:
            paper_id: 論文ID
            cite_key: BibTeX cite_key

        Returns:
            是否成功更新
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE papers
                SET cite_key = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (cite_key, paper_id))

            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def list_papers_without_cite_key(self) -> List[Dict[str, Any]]:
        """
        列出所有缺少 cite_key 的論文

        Returns:
            論文列表（包含 id, title, authors, year, file_path）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, title, authors, year, file_path
            FROM papers
            WHERE cite_key IS NULL OR cite_key = ''
            ORDER BY id
        """)

        papers = []
        for row in cursor.fetchall():
            # Parse authors field safely
            authors = []
            if row[2] and row[2].strip():
                try:
                    authors = json.loads(row[2])
                except (json.JSONDecodeError, TypeError):
                    # If JSON parsing fails, treat as empty list
                    authors = []

            papers.append({
                'id': row[0],
                'title': row[1],
                'authors': authors,
                'year': row[3],
                'file_path': row[4]
            })

        conn.close()
        return papers

    def update_cite_keys_from_bib(self, bib_file: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        從 BibTeX 文件批量更新 cite_key

        Args:
            bib_file: .bib 文件路徑
            dry_run: 是否只模擬（不實際更新）

        Returns:
            更新結果統計
        """
        from claude_lit.integrations.bibtex_parser import BibTeXParser

        parser = BibTeXParser()
        entries = parser.parse_file(bib_file)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        updated = []
        not_found = []
        already_has_key = []

        for entry in entries:
            # 根據 title 和 year 匹配論文
            cursor.execute("""
                SELECT id, title, cite_key
                FROM papers
                WHERE title LIKE ? AND (year = ? OR year IS NULL)
            """, (f"%{entry.title[:50]}%", entry.year))

            matches = cursor.fetchall()

            if len(matches) == 0:
                not_found.append({
                    'cite_key': entry.cite_key,
                    'title': entry.title
                })
            elif len(matches) == 1:
                paper_id, title, existing_key = matches[0]

                if existing_key:
                    already_has_key.append({
                        'id': paper_id,
                        'title': title,
                        'existing_key': existing_key,
                        'new_key': entry.cite_key
                    })
                else:
                    if not dry_run:
                        cursor.execute("""
                            UPDATE papers
                            SET cite_key = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (entry.cite_key, paper_id))

                    updated.append({
                        'id': paper_id,
                        'title': title,
                        'cite_key': entry.cite_key
                    })
            else:
                # 多個匹配，需要人工處理
                not_found.append({
                    'cite_key': entry.cite_key,
                    'title': entry.title,
                    'reason': f'Multiple matches: {len(matches)}'
                })

        if not dry_run:
            conn.commit()
        conn.close()

        return {
            'total_entries': len(entries),
            'updated': updated,
            'not_found': not_found,
            'already_has_key': already_has_key,
            'success_count': len(updated),
            'not_found_count': len(not_found),
            'already_has_key_count': len(already_has_key)
        }

    def list_papers(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """列出所有論文"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, file_path, title, authors, year, keywords, created_at
            FROM papers
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "file_path": row[1],
                "title": row[2],
                "authors": json.loads(row[3]) if row[3] else [],
                "year": row[4],
                "keywords": json.loads(row[5]) if row[5] else [],
                "created_at": row[6]
            })

        conn.close()
        return results

    def add_topic(self, name: str, description: Optional[str] = None) -> int:
        """新增主題"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO topics (name, description)
                VALUES (?, ?)
            """, (name, description))
            topic_id = cursor.lastrowid
            conn.commit()
            return topic_id

        except sqlite3.IntegrityError:
            cursor.execute("SELECT id FROM topics WHERE name=?", (name,))
            topic_id = cursor.fetchone()[0]
            return topic_id

        finally:
            conn.close()

    def link_paper_to_topic(self, paper_id: int, topic_id: int, relevance: float = 1.0):
        """連結論文與主題"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO paper_topics (paper_id, topic_id, relevance)
                VALUES (?, ?, ?)
            """, (paper_id, topic_id, relevance))
            conn.commit()
        finally:
            conn.close()

    def link_paper_to_zettel(self, paper_id: int, card_id: int, similarity: float, method: str = 'vector_similarity'):
        """建立論文與Zettelkasten卡片的連結（基於向量相似度）

        Args:
            paper_id: 論文ID
            card_id: Zettelkasten卡片ID
            similarity: 相似度分數（0-1）
            method: 連結方法（默認為向量相似度）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO paper_zettel_links (paper_id, card_id, similarity, method)
                VALUES (?, ?, ?, ?)
            """, (paper_id, card_id, similarity, method))
            conn.commit()
        finally:
            conn.close()

    def get_paper_zettel_links(self, paper_id: int, min_similarity: float = 0.0) -> List[Dict[str, Any]]:
        """獲取論文的所有Zettelkasten連結

        Args:
            paper_id: 論文ID
            min_similarity: 最小相似度閾值

        Returns:
            連結列表，包含卡片信息和相似度
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                pzl.id,
                pzl.card_id,
                zc.zettel_id,
                zc.title,
                zc.core_concept,
                zc.card_type,
                zc.domain,
                pzl.similarity,
                pzl.method,
                pzl.created_at
            FROM paper_zettel_links pzl
            JOIN zettel_cards zc ON pzl.card_id = zc.card_id
            WHERE pzl.paper_id = ? AND pzl.similarity >= ?
            ORDER BY pzl.similarity DESC
        """, (paper_id, min_similarity))

        results = []
        for row in cursor.fetchall():
            results.append({
                'link_id': row[0],
                'card_id': row[1],
                'zettel_id': row[2],
                'title': row[3],
                'core_concept': row[4],
                'card_type': row[5],
                'domain': row[6],
                'similarity': row[7],
                'method': row[8],
                'created_at': row[9]
            })

        conn.close()
        return results

    def get_zettel_paper_links(self, card_id: int, min_similarity: float = 0.0) -> List[Dict[str, Any]]:
        """獲取Zettelkasten卡片的所有論文連結（反向查詢）

        Args:
            card_id: Zettelkasten卡片ID
            min_similarity: 最小相似度閾值

        Returns:
            連結列表，包含論文信息和相似度
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                pzl.id,
                pzl.paper_id,
                p.title,
                p.authors,
                p.year,
                pzl.similarity,
                pzl.method,
                pzl.created_at
            FROM paper_zettel_links pzl
            JOIN papers p ON pzl.paper_id = p.id
            WHERE pzl.card_id = ? AND pzl.similarity >= ?
            ORDER BY pzl.similarity DESC
        """, (card_id, min_similarity))

        results = []
        for row in cursor.fetchall():
            results.append({
                'link_id': row[0],
                'paper_id': row[1],
                'title': row[2],
                'authors': row[3],
                'year': row[4],
                'similarity': row[5],
                'method': row[6],
                'created_at': row[7]
            })

        conn.close()
        return results

    def delete_paper_zettel_link(self, paper_id: int, card_id: int):
        """刪除論文與Zettelkasten卡片的連結

        Args:
            paper_id: 論文ID
            card_id: Zettelkasten卡片ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                DELETE FROM paper_zettel_links
                WHERE paper_id = ? AND card_id = ?
            """, (paper_id, card_id))
            conn.commit()
        finally:
            conn.close()

    def get_papers_by_topic(self, topic_name: str) -> List[Dict[str, Any]]:
        """根據主題獲取論文"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.id, p.title, p.authors, p.year, pt.relevance
            FROM papers p
            JOIN paper_topics pt ON p.id = pt.paper_id
            JOIN topics t ON pt.topic_id = t.id
            WHERE t.name = ?
            ORDER BY pt.relevance DESC
        """, (topic_name,))

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "title": row[1],
                "authors": json.loads(row[2]) if row[2] else [],
                "year": row[3],
                "relevance": row[4]
            })

        conn.close()
        return results

    def add_citation(self, source_paper_id: int, target_paper_id: int, citation_type: str = "cites"):
        """添加引用關係"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO citations (source_paper_id, target_paper_id, citation_type)
                VALUES (?, ?, ?)
            """, (source_paper_id, target_paper_id, citation_type))
            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, int]:
        """獲取知識庫統計信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        # Papers 統計
        cursor.execute("SELECT COUNT(*) FROM papers")
        stats['total_papers'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM topics")
        stats['total_topics'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM citations")
        stats['total_citations'] = cursor.fetchone()[0]

        # Zettelkasten 統計
        cursor.execute("SELECT COUNT(*) FROM zettel_cards")
        stats['total_zettel_cards'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM zettel_links")
        stats['total_zettel_links'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT domain) FROM zettel_cards")
        stats['total_zettel_domains'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT zettel_folder) FROM zettel_cards")
        stats['total_zettel_folders'] = cursor.fetchone()[0]

        conn.close()
        return stats

    def create_markdown_note(self,
                            paper_data: Dict[str, Any],
                            output_path: Optional[str] = None) -> str:
        """
        創建Markdown格式的論文筆記

        Args:
            paper_data: 論文數據
            output_path: 輸出路徑（可選，自動生成）

        Returns:
            Markdown文件路徑
        """
        if output_path is None:
            # 自動生成文件名
            title_slug = re.sub(r'[^\w\s-]', '', paper_data.get('title', 'untitled')).strip()
            title_slug = re.sub(r'[-\s]+', '_', title_slug)[:50]
            output_path = self.papers_dir / f"{title_slug}.md"

        # 生成Markdown內容
        md_content = f"""---
title: {paper_data.get('title', 'Untitled')}
authors: {', '.join(paper_data.get('authors', []))}
year: {paper_data.get('year', 'N/A')}
keywords: {', '.join(paper_data.get('keywords', []))}
created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
---

# {paper_data.get('title', 'Untitled')}

## 基本信息

- **作者**: {', '.join(paper_data.get('authors', []))}
- **年份**: {paper_data.get('year', 'N/A')}
- **關鍵詞**: {', '.join(paper_data.get('keywords', []))}

## 摘要

{paper_data.get('abstract', '尚未提供摘要')}

## 研究背景

## 研究方法

## 主要結果

## 討論與結論

## 個人評論

## 相關文獻

## 完整內容

{paper_data.get('content', '尚未提供內容')}

## 引用

```
{paper_data.get('citation', '')}
```
"""

        # 寫入文件
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        return str(output_path)

    # ========== Zettelkasten 相關方法 ==========

    @staticmethod
    def normalize_id(zettel_id: str) -> str:
        """
        正規化 Zettel ID 格式

        修復錯誤格式：
        - CogSci20251028001 → CogSci-20251028-001
        - AI_20251029_005 → AI-20251029-005

        Args:
            zettel_id: 原始 Zettel ID

        Returns:
            正規化後的 ID
        """
        # 移除底線和多餘空白
        zettel_id = zettel_id.replace('_', '-').strip()

        # 正則表達式匹配並重組
        match = re.match(r'^([A-Za-z]+)[-]?(\d{8})[-]?(\d{3})$', zettel_id)
        if match:
            domain, date, num = match.groups()
            return f"{domain}-{date}-{num}"
        else:
            return zettel_id

    @staticmethod
    def extract_domain_from_id(zettel_id: str) -> str:
        """
        從 ID 提取領域代碼

        Args:
            zettel_id: Zettel ID (如 CogSci-20251028-001)

        Returns:
            領域代碼 (如 CogSci)
        """
        match = re.match(r'^([A-Za-z]+)-', zettel_id)
        return match.group(1) if match else 'Unknown'

    @staticmethod
    def parse_zettel_links(markdown_content: str) -> List[Dict]:
        """
        提取連結網絡區塊的所有連結

        範例輸入：
        ## 連結網絡
        **導向** → [[Barsalou-1999-002]], [[Barsalou-1999-003]]
        **基於** → [[Linguistics-20251029-001]]

        支援的 ID 格式：
        - Author-YYYY-001 (如 Barsalou-1999-001)
        - Author-YYYYa-001 (如 Barsalou-1999a-001)
        - Domain-YYYYMMDD-001 (如 Linguistics-20251029-001)
        - Multi-Word-Author-YYYY-001 (如 van-Rooij-2025-001)

        Args:
            markdown_content: Markdown內容

        Returns:
            連結列表，如:
            [
                {'relation_type': '導向', 'target_ids': ['Barsalou-1999-002', ...]},
                {'relation_type': '基於', 'target_ids': ['Linguistics-20251029-001']}
            ]
        """
        links = []

        # 提取「連結網絡」區塊（處理多個空行）
        network_match = re.search(r'## 連結網絡\s*\n(.+?)(?=\n##|\Z)', markdown_content, re.DOTALL)
        if not network_match:
            return links

        network_text = network_match.group(1)

        # 匹配每一行連結（寬容的空白處理）
        # 格式：**關係類型** → [[ID1]], [[ID2]]
        # 也支援 ↔ 符號（對比關係常用）
        link_pattern = r'\*\*(基於|導向|相關|對比|上位|下位)\*\*\s*[→↔]\s*(.+?)(?=\n\s*\n|\n\*\*|\n##|\Z)'

        for match in re.finditer(link_pattern, network_text, re.DOTALL):
            relation_type = match.group(1)
            target_text = match.group(2)

            # 提取所有目標 ID（支援多種格式）
            # 匹配: [[任意文字-數字序列-3位數字]]
            # 例如: [[Barsalou-1999-001]], [[van-Rooij-2025a-002]], [[Linguistics-20251029-003]]
            target_ids = re.findall(r'\[\[([A-Za-z][A-Za-z0-9-]*-\d{3,4}[a-z]?-\d{3})\]\]', target_text)

            # 也嘗試匹配 8 位日期格式
            if not target_ids:
                target_ids = re.findall(r'\[\[([A-Za-z][A-Za-z0-9-]*-\d{8}-\d{3})\]\]', target_text)

            if target_ids:
                links.append({
                    'relation_type': relation_type,
                    'target_ids': target_ids
                })

        return links

    def parse_zettel_card(self, file_path: str) -> Optional[Dict]:
        """
        解析單張 Zettelkasten 卡片

        Args:
            file_path: 卡片文件路徑

        Returns:
            解析結果字典，失敗返回 None
            {
                'zettel_id': str,
                'title': str,
                'content': str,
                'core_concept': str,
                'description': str,
                'card_type': str,
                'domain': str,
                'tags': List[str],
                'source_info': str,
                'file_path': str,
                'ai_notes': str,
                'human_notes': str,
                'links': List[Dict],
                'created_at': str
            }
        """
        try:
            # 1. 讀取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 2. 提取 YAML frontmatter
            yaml_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
            if not yaml_match:
                print(f"[ERROR] Invalid Zettelkasten format: {file_path}")
                return None

            yaml_content = yaml_match.group(1)
            markdown_content = yaml_match.group(2)

            # 3. 解析 YAML（處理不規範格式）
            try:
                # 先嘗試標準YAML解析
                metadata = yaml.safe_load(yaml_content)
            except yaml.YAMLError:
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
                            metadata[key] = [tag.strip() for tag in value.split(',')] if value else []
                        elif key == 'source':
                            # source欄位保持原樣
                            metadata[key] = value
                        elif value == '':
                            metadata[key] = None
                        else:
                            metadata[key] = value

            # 4. 初始化結果字典
            # 取得 zettel_id：優先使用 YAML 的 id 欄位，否則從檔名提取
            yaml_id = metadata.get('id', '')
            if not yaml_id:
                # 從檔名提取 zettel_id（例如 Adams-2020-002.md → Adams-2020-002）
                filename = Path(file_path).stem  # 移除 .md 副檔名
                yaml_id = filename

            result = {
                'zettel_id': self.normalize_id(yaml_id) if yaml_id else yaml_id,
                'title': metadata.get('title', '').strip(),
                'content': content,
                'card_type': metadata.get('type', 'concept'),
                'domain': self.extract_domain_from_id(yaml_id),
                'tags': metadata.get('tags', []),
                'source_info': metadata.get('source', ''),
                'file_path': str(Path(file_path).resolve()),
                'created_at': metadata.get('created', None),
            }

            # 5. 提取核心概念
            core_match = re.search(r'>\s*\*\*核心\*\*:\s*"(.+?)"', markdown_content, re.DOTALL)
            result['core_concept'] = core_match.group(1).strip() if core_match else None

            # 6. 提取說明文字
            desc_match = re.search(r'## 說明\n(.+?)(?=\n##|\Z)', markdown_content, re.DOTALL)
            result['description'] = desc_match.group(1).strip() if desc_match else None

            # 7. 提取 AI 筆記
            ai_match = re.search(
                r'\*\*\[AI Agent\]\*\*:\s*(.+?)(?=\n\*\*\[Human\]|\n---|===|\Z)',
                markdown_content,
                re.DOTALL
            )
            result['ai_notes'] = ai_match.group(1).strip() if ai_match else None

            # 8. 提取人類筆記
            human_match = re.search(
                r'\*\*\[Human\]\*\*:\s*(.+?)(?=\n---|===|\Z)',
                markdown_content,
                re.DOTALL
            )
            result['human_notes'] = human_match.group(1).strip() if human_match else None

            # 9. 提取連結信息
            result['links'] = self.parse_zettel_links(markdown_content)

            return result

        except FileNotFoundError:
            print(f"[ERROR] File not found: {file_path}")
            return None
        except Exception as e:
            print(f"[ERROR] Failed to parse {file_path}: {e}")
            return None

    def add_zettel_card(self, card_data: Dict) -> ZettelAddResult:
        """
        新增 Zettelkasten 卡片到資料庫

        Args:
            card_data: 卡片數據（parse_zettel_card的返回值）

        Returns:
            ZettelAddResult: 結構化結果
            - status: 'inserted' | 'duplicate' | 'error'
            - card_id: 卡片ID（inserted/duplicate時有效，error時為-1）
            - message: 操作描述訊息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        zettel_id = card_data.get('zettel_id', 'unknown')

        # 提取 zettel_folder 從 file_path
        file_path = Path(card_data['file_path'])
        zettel_folder = file_path.parent.parent.name  # 上兩層目錄名稱

        # 轉換 tags 為 JSON 字串
        tags_str = json.dumps(card_data.get('tags', []), ensure_ascii=False)

        try:
            cursor.execute("""
                INSERT INTO zettel_cards (
                    zettel_id, title, content, core_concept, description,
                    card_type, domain, tags, zettel_folder, source_info,
                    file_path, ai_notes, human_notes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                card_data['zettel_id'],
                card_data['title'],
                card_data['content'],
                card_data.get('core_concept'),
                card_data.get('description'),
                card_data['card_type'],
                card_data['domain'],
                tags_str,
                zettel_folder,
                card_data.get('source_info'),
                card_data['file_path'],
                card_data.get('ai_notes'),
                card_data.get('human_notes'),
                card_data.get('created_at')
            ))

            card_id = cursor.lastrowid

            # 驗證插入成功
            if cursor.rowcount != 1:
                conn.rollback()
                return ZettelAddResult(
                    status='error',
                    card_id=-1,
                    message=f'INSERT rowcount={cursor.rowcount}, expected 1'
                )

            # 插入連結信息
            for link in card_data.get('links', []):
                for target_id in link['target_ids']:
                    cursor.execute("""
                        INSERT INTO zettel_links (
                            source_card_id, target_zettel_id, relation_type
                        )
                        VALUES (?, ?, ?)
                    """, (card_id, target_id, link['relation_type']))

            conn.commit()
            return ZettelAddResult(
                status='inserted',
                card_id=card_id,
                message=f'Successfully inserted {zettel_id}'
            )

        except sqlite3.IntegrityError as e:
            # 區分「重複」與「其他約束錯誤」
            error_msg = str(e).lower()
            if 'unique constraint' in error_msg or 'zettel_id' in error_msg:
                # 重複卡片 - 查詢現有 card_id
                cursor.execute("SELECT card_id FROM zettel_cards WHERE zettel_id=?",
                              (card_data['zettel_id'],))
                result = cursor.fetchone()
                existing_id = result[0] if result else -1
                return ZettelAddResult(
                    status='duplicate',
                    card_id=existing_id,
                    message=f'Card {zettel_id} already exists (card_id={existing_id})'
                )
            else:
                # 其他約束錯誤
                return ZettelAddResult(
                    status='error',
                    card_id=-1,
                    message=f'IntegrityError: {e}'
                )

        except Exception as e:
            return ZettelAddResult(
                status='error',
                card_id=-1,
                message=f'Unexpected error: {e}'
            )

        finally:
            conn.close()

    def delete_zettel_cards_by_paper(self, paper_id: int) -> Dict:
        """
        刪除指定論文的所有 Zettel 卡片（用於重新生成）

        Args:
            paper_id: 論文 ID

        Returns:
            刪除結果:
            {
                'deleted_cards': int,      # 刪除的卡片數
                'deleted_links': int,      # 刪除的連結數
                'deleted_embeddings': int, # 刪除的向量嵌入數
                'zettel_ids': List[str]    # 被刪除的 zettel_id 列表
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        result = {
            'deleted_cards': 0,
            'deleted_links': 0,
            'deleted_embeddings': 0,
            'zettel_ids': []
        }

        try:
            # 1. 查詢該論文關聯的所有卡片
            cursor.execute("""
                SELECT zc.card_id, zc.zettel_id
                FROM zettel_cards zc
                JOIN paper_zettel_links pzl ON zc.card_id = pzl.card_id
                WHERE pzl.paper_id = ?
            """, (paper_id,))
            cards = cursor.fetchall()

            if not cards:
                return result

            card_ids = [c[0] for c in cards]
            result['zettel_ids'] = [c[1] for c in cards]

            # 2. 刪除連結（zettel_links 會因 CASCADE 自動刪除）
            cursor.execute("""
                SELECT COUNT(*) FROM zettel_links
                WHERE source_card_id IN ({})
            """.format(','.join('?' * len(card_ids))), card_ids)
            result['deleted_links'] = cursor.fetchone()[0]

            # 3. 刪除論文-卡片關聯
            cursor.execute("""
                DELETE FROM paper_zettel_links WHERE paper_id = ?
            """, (paper_id,))

            # 4. 刪除卡片（會觸發 CASCADE 刪除 zettel_links）
            cursor.execute("""
                DELETE FROM zettel_cards
                WHERE card_id IN ({})
            """.format(','.join('?' * len(card_ids))), card_ids)
            result['deleted_cards'] = cursor.rowcount

            conn.commit()

            # 5. 刪除向量嵌入（在 commit 後執行，因為是外部資料庫）
            try:
                from claude_lit.embeddings.vector_db import VectorDatabase
                vector_db = VectorDatabase()
                for zettel_id in result['zettel_ids']:
                    vector_db.delete_zettel(zettel_id)
                    result['deleted_embeddings'] += 1
            except Exception as e:
                # 向量嵌入刪除失敗不影響主流程
                print(f"  [WARN] 向量嵌入刪除失敗: {e}")

            return result

        except Exception as e:
            conn.rollback()
            print(f"[ERROR] 刪除卡片失敗: {e}")
            return result

        finally:
            conn.close()

    def delete_zettel_cards_by_citekey(self, cite_key: str) -> Dict:
        """
        根據 cite_key 刪除所有相關 Zettel 卡片（用於重新生成）

        Args:
            cite_key: 論文 cite_key（如 'Barsalou-1999'）

        Returns:
            刪除結果（同 delete_zettel_cards_by_paper）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        result = {
            'deleted_cards': 0,
            'deleted_links': 0,
            'deleted_embeddings': 0,
            'zettel_ids': []
        }

        try:
            # 1. 查詢所有以該 cite_key 開頭的卡片
            cursor.execute("""
                SELECT card_id, zettel_id FROM zettel_cards
                WHERE zettel_id LIKE ?
            """, (f"{cite_key}-%",))
            cards = cursor.fetchall()

            if not cards:
                return result

            card_ids = [c[0] for c in cards]
            result['zettel_ids'] = [c[1] for c in cards]

            # 2. 統計連結數
            cursor.execute("""
                SELECT COUNT(*) FROM zettel_links
                WHERE source_card_id IN ({})
            """.format(','.join('?' * len(card_ids))), card_ids)
            result['deleted_links'] = cursor.fetchone()[0]

            # 3. 刪除論文-卡片關聯
            cursor.execute("""
                DELETE FROM paper_zettel_links
                WHERE card_id IN ({})
            """.format(','.join('?' * len(card_ids))), card_ids)

            # 4. 刪除卡片
            cursor.execute("""
                DELETE FROM zettel_cards
                WHERE card_id IN ({})
            """.format(','.join('?' * len(card_ids))), card_ids)
            result['deleted_cards'] = cursor.rowcount

            conn.commit()

            # 5. 刪除向量嵌入
            try:
                from claude_lit.embeddings.vector_db import VectorDatabase
                vector_db = VectorDatabase()
                for zettel_id in result['zettel_ids']:
                    vector_db.delete_zettel(zettel_id)
                    result['deleted_embeddings'] += 1
            except Exception as e:
                print(f"  [WARN] 向量嵌入刪除失敗: {e}")

            return result

        except Exception as e:
            conn.rollback()
            print(f"[ERROR] 刪除卡片失敗: {e}")
            return result

        finally:
            conn.close()

    def index_zettelkasten(self, zettel_folder: str, domain: str = None) -> Dict:
        """
        批次索引 Zettelkasten 卡片資料夾

        Args:
            zettel_folder: Zettelkasten 資料夾路徑（包含 zettel_cards 子資料夾）
            domain: 領域代碼（可選，從卡片ID自動提取）

        Returns:
            索引結果統計:
            {
                'total': int,
                'inserted': int,    # 新插入的卡片數
                'duplicate': int,   # 重複（已存在）的卡片數
                'failed': int,      # 真正失敗的卡片數
                'skipped': int,     # 因領域不符跳過的卡片數
                'parse_error': int, # 解析失敗的卡片數
                'cards': List[int], # 成功插入的 card_ids
                'errors': List[str] # 錯誤訊息列表
            }
        """
        folder_path = Path(zettel_folder)
        cards_dir = folder_path / "zettel_cards"

        if not cards_dir.exists():
            print(f"[ERROR] Zettel cards directory not found: {cards_dir}")
            return {
                'total': 0, 'inserted': 0, 'duplicate': 0, 'failed': 0,
                'skipped': 0, 'parse_error': 0, 'cards': [], 'errors': []
            }

        # 查找所有 .md 文件
        card_files = list(cards_dir.glob("*.md"))

        stats = {
            'total': len(card_files),
            'inserted': 0,
            'duplicate': 0,
            'failed': 0,
            'skipped': 0,
            'parse_error': 0,
            'cards': [],
            'errors': []
        }

        for card_file in card_files:
            # 解析卡片
            card_data = self.parse_zettel_card(str(card_file))

            if card_data is None:
                stats['parse_error'] += 1
                stats['errors'].append(f"Parse error: {card_file.name}")
                print(f"[PARSE_ERROR] {card_file.name}")
                continue

            # 檢查領域是否匹配（如果指定了domain參數）
            if domain and card_data['domain'] != domain:
                stats['skipped'] += 1
                print(f"[SKIPPED] {card_file.name} (domain mismatch: {card_data['domain']} != {domain})")
                continue

            # 插入資料庫 - 使用新的結構化回傳
            result = self.add_zettel_card(card_data)

            if result['status'] == 'inserted':
                stats['inserted'] += 1
                stats['cards'].append(result['card_id'])
                print(f"[INSERTED] {card_file.name} → card_id={result['card_id']}")
            elif result['status'] == 'duplicate':
                stats['duplicate'] += 1
                print(f"[DUPLICATE] {card_file.name} ({result['message']})")
            else:  # error
                stats['failed'] += 1
                stats['errors'].append(f"{card_file.name}: {result['message']}")
                print(f"[FAILED] {card_file.name}: {result['message']}")

        # 輸出摘要
        print(f"\n=== 索引摘要 ===")
        print(f"總計: {stats['total']} | 新增: {stats['inserted']} | "
              f"重複: {stats['duplicate']} | 失敗: {stats['failed']} | "
              f"跳過: {stats['skipped']} | 解析錯誤: {stats['parse_error']}")

        return stats

    def search_zettel(self, query: str, limit: int = 20,
                      domain: str = None, card_type: str = None) -> List[Dict[str, Any]]:
        """
        全文搜索 Zettelkasten 卡片

        Args:
            query: 搜索查詢
            limit: 返回結果數量限制
            domain: 限制領域（可選）
            card_type: 限制卡片類型（可選）

        Returns:
            匹配的卡片列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 構建查詢條件
        where_clauses = []
        params = [query]

        if domain:
            where_clauses.append("c.domain = ?")
            params.append(domain)

        if card_type:
            where_clauses.append("c.card_type = ?")
            params.append(card_type)

        where_sql = " AND " + " AND ".join(where_clauses) if where_clauses else ""

        params.append(limit)

        cursor.execute(f"""
            SELECT c.card_id, c.zettel_id, c.title, c.core_concept,
                   c.description, c.card_type, c.domain, c.tags,
                   c.file_path, c.created_at
            FROM zettel_cards c
            JOIN zettel_cards_fts fts ON c.card_id = fts.rowid
            WHERE zettel_cards_fts MATCH ?{where_sql}
            ORDER BY rank
            LIMIT ?
        """, params)

        results = []
        for row in cursor.fetchall():
            results.append({
                "card_id": row[0],
                "zettel_id": row[1],
                "title": row[2],
                "core_concept": row[3],
                "description": row[4],
                "card_type": row[5],
                "domain": row[6],
                "tags": json.loads(row[7]) if row[7] else [],
                "file_path": row[8],
                "created_at": row[9]
            })

        conn.close()
        return results

    def get_zettel_by_id(self, zettel_id: str) -> Optional[Dict[str, Any]]:
        """
        根據 zettel_id 獲取卡片信息

        Args:
            zettel_id: Zettel ID (如 CogSci-20251028-001)

        Returns:
            卡片信息字典
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT card_id, zettel_id, title, content, core_concept, description,
                   card_type, domain, tags, paper_id, zettel_folder, source_info,
                   file_path, ai_notes, human_notes, created_at
            FROM zettel_cards
            WHERE zettel_id = ?
        """, (zettel_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "card_id": row[0],
                "zettel_id": row[1],
                "title": row[2],
                "content": row[3],
                "core_concept": row[4],
                "description": row[5],
                "card_type": row[6],
                "domain": row[7],
                "tags": json.loads(row[8]) if row[8] else [],
                "paper_id": row[9],
                "zettel_folder": row[10],
                "source_info": row[11],
                "file_path": row[12],
                "ai_notes": row[13],
                "human_notes": row[14],
                "created_at": row[15]
            }
        return None

    def sync_zettel_links(self, dry_run: bool = False) -> Dict[str, int]:
        """
        同步所有 Zettelkasten 卡片的連結資訊

        從卡片檔案重新解析連結，更新 zettel_links 表。

        Args:
            dry_run: 預覽模式（不實際寫入）

        Returns:
            統計結果: {total_cards, processed, links_added, errors}
        """
        result = {
            'total_cards': 0,
            'processed': 0,
            'links_added': 0,
            'errors': 0
        }

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 1. 獲取所有卡片
        cursor.execute("""
            SELECT card_id, zettel_id, file_path, content
            FROM zettel_cards
        """)
        cards = cursor.fetchall()
        result['total_cards'] = len(cards)

        if not dry_run:
            # 清空現有連結（重新建立）
            cursor.execute("DELETE FROM zettel_links")

        for card_id, zettel_id, file_path, content in cards:
            try:
                # 優先從檔案讀取（更準確）
                if file_path and Path(file_path).exists():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        markdown_content = f.read()
                elif content:
                    markdown_content = content
                else:
                    continue

                # 解析連結
                links = self.parse_zettel_links(markdown_content)

                if links:
                    result['processed'] += 1

                    for link in links:
                        for target_id in link['target_ids']:
                            result['links_added'] += 1
                            if not dry_run:
                                cursor.execute("""
                                    INSERT INTO zettel_links (
                                        source_card_id, target_zettel_id, relation_type
                                    ) VALUES (?, ?, ?)
                                """, (card_id, target_id, link['relation_type']))

            except Exception as e:
                result['errors'] += 1

        if not dry_run:
            conn.commit()

        conn.close()
        return result

    def get_zettel_links(self, card_id: int) -> List[Dict[str, Any]]:
        """
        獲取卡片的所有連結

        Args:
            card_id: 卡片 card_id

        Returns:
            連結列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT link_id, target_zettel_id, relation_type, context, is_cross_paper
            FROM zettel_links
            WHERE source_card_id = ?
        """, (card_id,))

        results = []
        for row in cursor.fetchall():
            results.append({
                "link_id": row[0],
                "target_zettel_id": row[1],
                "relation_type": row[2],
                "context": row[3],
                "is_cross_paper": bool(row[4])
            })

        conn.close()
        return results

    # ========== 卡片-論文關聯方法 ==========

    def link_zettel_to_paper(self, card_id: int, paper_id: int) -> bool:
        """
        手動關聯 Zettelkasten 卡片與論文

        Args:
            card_id: 卡片 card_id
            paper_id: 論文 paper_id

        Returns:
            成功返回 True
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # 更新卡片的 paper_id
            cursor.execute("""
                UPDATE zettel_cards
                SET paper_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE card_id = ?
            """, (paper_id, card_id))

            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            print(f"[ERROR] Failed to link card {card_id} to paper {paper_id}: {e}")
            return False

        finally:
            conn.close()

    def get_zettel_by_paper(self, paper_id: int) -> List[Dict[str, Any]]:
        """
        查詢論文的所有 Zettelkasten 卡片

        Args:
            paper_id: 論文 paper_id

        Returns:
            卡片列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT card_id, zettel_id, title, core_concept, description,
                   card_type, domain, tags, file_path, created_at
            FROM zettel_cards
            WHERE paper_id = ?
            ORDER BY zettel_id
        """, (paper_id,))

        results = []
        for row in cursor.fetchall():
            results.append({
                "card_id": row[0],
                "zettel_id": row[1],
                "title": row[2],
                "core_concept": row[3],
                "description": row[4],
                "card_type": row[5],
                "domain": row[6],
                "tags": json.loads(row[7]) if row[7] else [],
                "file_path": row[8],
                "created_at": row[9]
            })

        conn.close()
        return results

    def auto_link_zettel_papers(self, similarity_threshold: float = 0.7) -> Dict[str, int]:
        """
        自動關聯 Zettelkasten 卡片與論文

        策略：
        1. 從卡片的 source_info 提取標題和年份
        2. 在 papers 表中查找匹配的論文
        3. 使用模糊匹配（SequenceMatcher）計算相似度
        4. 相似度 >= threshold 則自動關聯

        Args:
            similarity_threshold: 相似度閾值（0.0-1.0）

        Returns:
            統計結果: {'linked': int, 'unmatched': int, 'skipped': int}
        """
        from difflib import SequenceMatcher

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 查詢所有未關聯的卡片
        cursor.execute("""
            SELECT card_id, zettel_id, source_info
            FROM zettel_cards
            WHERE paper_id IS NULL AND source_info IS NOT NULL
        """)

        unlinked_cards = cursor.fetchall()

        # 查詢所有論文
        cursor.execute("""
            SELECT id, title, year
            FROM papers
        """)

        papers = cursor.fetchall()

        stats = {
            'linked': 0,
            'unmatched': 0,
            'skipped': 0
        }

        for card_id, zettel_id, source_info in unlinked_cards:
            if not source_info:
                stats['skipped'] += 1
                continue

            # 提取 source_info 中的標題（移除引號和年份）
            # 格式: "Paper Title" (2025)
            title_match = re.match(r'"([^"]+)"\s*\((\d{4})\)', source_info)

            if not title_match:
                # 嘗試更寬鬆的匹配
                title_match = re.match(r'"([^"]+)"', source_info)
                if not title_match:
                    stats['skipped'] += 1
                    continue

            source_title = title_match.group(1).lower().strip()
            source_year = int(title_match.group(2)) if len(title_match.groups()) > 1 else None

            # 在論文中查找最佳匹配
            best_match = None
            best_score = 0.0

            for paper_id, paper_title, paper_year in papers:
                if not paper_title:
                    continue

                # 計算標題相似度
                title_sim = SequenceMatcher(None, source_title, paper_title.lower()).ratio()

                # 如果年份存在，則額外加權
                year_bonus = 0.1 if (source_year and paper_year and source_year == paper_year) else 0.0

                total_score = title_sim + year_bonus

                if total_score > best_score:
                    best_score = total_score
                    best_match = (paper_id, paper_title)

            # 如果最佳匹配超過閾值，則關聯
            if best_score >= similarity_threshold:
                cursor.execute("""
                    UPDATE zettel_cards
                    SET paper_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE card_id = ?
                """, (best_match[0], card_id))

                print(f"[LINK] {zettel_id} → Paper #{best_match[0]} (score={best_score:.2f})")
                stats['linked'] += 1
            else:
                print(f"[UNMATCH] {zettel_id}: '{source_info}' (best_score={best_score:.2f})")
                stats['unmatched'] += 1

        conn.commit()
        conn.close()

        return stats

    def auto_link_zettel_papers_v2(
        self,
        bib_file: str = None,
        similarity_threshold: float = 0.7
    ) -> Dict[str, Any]:
        """
        改進版自動關聯（多層匹配策略）

        策略：
        1. cite_key 精確匹配（從 zettel_id 或 papers 表提取）
        2. 文件名作者-年份匹配（如 "Ahrens2016" → 作者姓氏 + 年份）
        3. 標題模糊匹配（fallback）

        Args:
            bib_file: BibTeX 文件路徑（用於建立 cite_key 映射）
            similarity_threshold: 標題模糊匹配閾值（0.0-1.0）

        Returns:
            統計結果: {
                'linked': int,
                'unmatched': int,
                'skipped': int,
                'method_breakdown': {
                    'cite_key': int,
                    'author_year': int,
                    'fuzzy_match': int
                }
            }
        """
        from difflib import SequenceMatcher
        import re

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {
            'linked': 0,
            'unmatched': 0,
            'skipped': 0,
            'method_breakdown': {
                'cite_key': 0,
                'author_year': 0,
                'fuzzy_match': 0
            }
        }

        # 輔助函數：規範化 cite_key（支援多種格式）
        def normalize_cite_key(author: str, year: int) -> str:
            """將作者-年份規範化為 Zotero 格式: author-year"""
            return f"{author.lower()}-{year}"

        # Step 1: 建立 cite_key → paper_id 映射（支援多種格式）
        print("\n[BUILD] 建立 cite_key 映射...")
        cursor.execute("""
            SELECT id, cite_key
            FROM papers
            WHERE cite_key IS NOT NULL
        """)

        cite_key_to_paper_id = {}
        for paper_id, cite_key in cursor.fetchall():
            # 原始格式（如 "Yi-2009"）
            cite_key_to_paper_id[cite_key.lower()] = paper_id

            # 移除連字符格式（如 "Yi2009"）
            cite_key_normalized = cite_key.replace('-', '').replace('_', '').lower()
            cite_key_to_paper_id[cite_key_normalized] = paper_id

        print(f"[OK] 建立 {len(cite_key_to_paper_id)} 個 cite_key 映射（含格式變體）")

        # Step 2: 獲取所有未關聯的卡片
        cursor.execute("""
            SELECT card_id, zettel_id, source_info
            FROM zettel_cards
            WHERE paper_id IS NULL
        """)

        unlinked_cards = cursor.fetchall()
        print(f"\n[PROCESS] 處理 {len(unlinked_cards)} 張未關聯卡片...")

        # Step 3: 獲取所有論文（用於 fallback）
        cursor.execute("""
            SELECT id, title, year, cite_key
            FROM papers
        """)

        papers = cursor.fetchall()

        # Step 4: 逐卡片處理
        for card_id, zettel_id, source_info in unlinked_cards:
            matched = False
            match_method = None

            # 方法1: 從 source_info 或 zettel_id 提取 cite_key
            # 優先從 source_info 提取（更可靠）
            cite_key_candidates = []

            # 1a. 從 source_info 提取作者-年份（含可選後綴）
            # 支援格式: "Ahrens2016_xxx" 或 "Ahrens-2016a_xxx"
            if source_info:
                author_year_in_source = re.match(r'"([A-Za-z]+)[-_]?(\d{4})([a-z]?)', source_info)
                if author_year_in_source:
                    author = author_year_in_source.group(1)
                    year = author_year_in_source.group(2)
                    suffix = author_year_in_source.group(3) if len(author_year_in_source.groups()) > 2 else ''

                    # 生成多種可能的 cite_key 格式（含/不含後綴）
                    for sep in ['-', '', '_']:
                        for sfx in ['', suffix] if suffix else ['']:
                            cite_key_candidates.append(f"{author.lower()}{sep}{year}{sfx}")

                    # 常見格式優先（去重）
                    cite_key_candidates = list(dict.fromkeys(cite_key_candidates))

            # 1b. 從 zettel_id 提取（fallback）
            # 格式: zettel_Her2012a_20251029
            cite_key_match = re.search(r'zettel_([A-Za-z]+[-_]?\d{4}[a-z]?)', zettel_id)
            if cite_key_match:
                extracted = cite_key_match.group(1).lower()
                cite_key_candidates.append(extracted)
                cite_key_candidates.append(extracted.replace('-', '').replace('_', ''))

            # 嘗試匹配所有候選 cite_key
            for cite_key in cite_key_candidates:
                if cite_key in cite_key_to_paper_id:
                    paper_id = cite_key_to_paper_id[cite_key]

                    # 更新關聯
                    cursor.execute("""
                        UPDATE zettel_cards
                        SET paper_id = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE card_id = ?
                    """, (paper_id, card_id))

                    print(f"  [CITE_KEY] {zettel_id} → Paper #{paper_id} (cite_key={cite_key})")
                    stats['linked'] += 1
                    stats['method_breakdown']['cite_key'] += 1
                    matched = True
                    break

            if matched:
                continue  # 進入下一張卡片

            # 方法2: 從 source_info 提取作者-年份-關鍵詞進行匹配
            if not matched and source_info:
                # 嘗試從文件名提取作者、年份和關鍵詞
                # 支援格式: "Ahrens2016_xxx", "Ahrens-2016_xxx", "Ahrens_2016_xxx"
                author_year_match = re.match(r'"([A-Za-z]+)[-_]?(\d{4})_?(.+?)"', source_info)

                if author_year_match:
                    author_lastname = author_year_match.group(1).lower()
                    year = int(author_year_match.group(2))
                    keywords_str = author_year_match.group(3) if len(author_year_match.groups()) > 2 else ""

                    # 將駝峰式或底線分隔的關鍵詞轉換為列表
                    # Reference_Grammar → [reference, grammar]
                    # Mental_Simulation → [mental, simulation]
                    keywords = re.findall(r'[A-Z][a-z]+|[a-z]+', keywords_str)
                    keywords = [kw.lower() for kw in keywords if len(kw) > 2]

                    # 在 papers 表中查找匹配的論文
                    # 優先匹配年份，但如果沒有年份則只匹配作者姓氏
                    best_candidate = None
                    best_score = 0

                    for paper_id, paper_title, paper_year, paper_cite_key in papers:
                        if not paper_title:
                            continue

                        title_lower = paper_title.lower()
                        cite_key_lower = (paper_cite_key or '').lower()

                        # 計算匹配分數
                        score = 0

                        # 1. 作者姓氏匹配 (+0.3)
                        if author_lastname in title_lower or author_lastname in cite_key_lower:
                            score += 0.3

                        # 2. 關鍵詞匹配 (+0.1 per keyword, max +0.4)
                        keyword_match_count = sum(1 for kw in keywords if kw in title_lower)
                        score += min(keyword_match_count * 0.1, 0.4)

                        # 3. 年份匹配 (+0.3)
                        if paper_year and paper_year == year:
                            score += 0.3

                        # 至少需要作者匹配或2個以上關鍵詞匹配
                        if score < 0.2:
                            continue

                        if score > best_score:
                            best_score = score
                            best_candidate = paper_id

                    # 如果找到匹配（分數至少 0.2），則關聯
                    if best_candidate and best_score >= 0.2:
                        cursor.execute("""
                            UPDATE zettel_cards
                            SET paper_id = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE card_id = ?
                        """, (best_candidate, card_id))

                        print(f"  [AUTHOR_YEAR] {zettel_id} → Paper #{best_candidate} (author={author_lastname}, year={year}, score={best_score:.2f})")
                        stats['linked'] += 1
                        stats['method_breakdown']['author_year'] += 1
                        matched = True

            # 方法3: Fallback 到標題模糊匹配
            if not matched and source_info:
                # 從 source_info 提取標題
                title_match = re.match(r'"([^"]+)"\s*\((\d{4})\)', source_info)

                if not title_match:
                    title_match = re.match(r'"([^"]+)"', source_info)

                if title_match:
                    source_title = title_match.group(1).lower().strip()
                    source_year = int(title_match.group(2)) if len(title_match.groups()) > 1 else None

                    # 查找最佳匹配
                    best_match = None
                    best_score = 0.0

                    for paper_id, paper_title, paper_year, paper_cite_key in papers:
                        if not paper_title:
                            continue

                        # 計算標題相似度
                        title_sim = SequenceMatcher(None, source_title, paper_title.lower()).ratio()

                        # 年份加權
                        year_bonus = 0.1 if (source_year and paper_year and source_year == paper_year) else 0.0

                        total_score = title_sim + year_bonus

                        if total_score > best_score:
                            best_score = total_score
                            best_match = (paper_id, paper_title)

                    # 如果超過閾值，則關聯
                    if best_score >= similarity_threshold:
                        cursor.execute("""
                            UPDATE zettel_cards
                            SET paper_id = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE card_id = ?
                        """, (best_match[0], card_id))

                        print(f"  [FUZZY] {zettel_id} → Paper #{best_match[0]} (score={best_score:.2f})")
                        stats['linked'] += 1
                        stats['method_breakdown']['fuzzy_match'] += 1
                        matched = True

            # 如果仍未匹配
            if not matched:
                if source_info:
                    print(f"  [UNMATCH] {zettel_id}: {source_info[:50]}...")
                    stats['unmatched'] += 1
                else:
                    stats['skipped'] += 1

        conn.commit()
        conn.close()

        # 顯示統計
        print("\n" + "=" * 70)
        print("[STATS] 自動關聯統計")
        print("=" * 70)
        print(f"總卡片數: {len(unlinked_cards)}")
        print(f"成功關聯: {stats['linked']} ({stats['linked']/len(unlinked_cards)*100:.1f}%)" if len(unlinked_cards) > 0 else "成功關聯: 0")
        print(f"  - cite_key 匹配: {stats['method_breakdown']['cite_key']}")
        print(f"  - 作者-年份匹配: {stats['method_breakdown']['author_year']}")
        print(f"  - 標題模糊匹配: {stats['method_breakdown']['fuzzy_match']}")
        print(f"未匹配: {stats['unmatched']}")
        print(f"跳過: {stats['skipped']}")

        return stats

    def update_paper_from_zettel(self, paper_id: int) -> Dict[str, Any]:
        """
        從 Zettelkasten 卡片更新論文元數據

        功能：
        1. 統計論文的卡片數量
        2. 聚合卡片標籤補充論文 keywords
        3. 計算論文的知識完整度（基於卡片數量和類型）

        Args:
            paper_id: 論文 paper_id

        Returns:
            更新統計: {
                'card_count': int,
                'new_keywords': List[str],
                'completeness_score': float
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 1. 統計卡片數量和類型
        cursor.execute("""
            SELECT COUNT(*), card_type
            FROM zettel_cards
            WHERE paper_id = ?
            GROUP BY card_type
        """, (paper_id,))

        type_counts = {row[1]: row[0] for row in cursor.fetchall()}
        total_cards = sum(type_counts.values())

        # 2. 聚合卡片標籤
        cursor.execute("""
            SELECT tags
            FROM zettel_cards
            WHERE paper_id = ? AND tags IS NOT NULL
        """, (paper_id,))

        all_tags = set()
        for (tags_json,) in cursor.fetchall():
            if tags_json:
                tags = json.loads(tags_json)
                all_tags.update(tags)

        # 3. 獲取論文現有 keywords
        cursor.execute("""
            SELECT keywords
            FROM papers
            WHERE id = ?
        """, (paper_id,))

        row = cursor.fetchone()
        if row and row[0]:
            existing_keywords = set(json.loads(row[0]))
        else:
            existing_keywords = set()

        # 4. 找出新增的 keywords
        new_keywords = list(all_tags - existing_keywords)

        # 5. 更新論文 keywords（如果有新增）
        if new_keywords:
            updated_keywords = list(existing_keywords | all_tags)
            cursor.execute("""
                UPDATE papers
                SET keywords = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (json.dumps(updated_keywords, ensure_ascii=False), paper_id))

        # 6. 計算完整度分數
        # 評分標準：
        # - 基礎分: 每張卡片 +5 分
        # - 類型獎勵: 有 concept/method/finding 各 +10 分
        # - 連結獎勵: 有連結的卡片 +5 分
        # - 上限: 100 分

        score = min(100, total_cards * 5)

        if 'concept' in type_counts:
            score += 10
        if 'method' in type_counts:
            score += 10
        if 'finding' in type_counts:
            score += 10

        # 查詢連結數量
        cursor.execute("""
            SELECT COUNT(DISTINCT source_card_id)
            FROM zettel_links
            WHERE source_card_id IN (
                SELECT card_id FROM zettel_cards WHERE paper_id = ?
            )
        """, (paper_id,))

        linked_cards = cursor.fetchone()[0]
        score = min(100, score + linked_cards * 5)

        conn.commit()
        conn.close()

        return {
            'card_count': total_cards,
            'card_types': type_counts,
            'new_keywords': new_keywords,
            'completeness_score': score
        }

    def get_paper_zettel_stats(self) -> List[Dict[str, Any]]:
        """
        獲取所有論文的 Zettelkasten 統計

        Returns:
            統計列表: [{paper_id, title, card_count, linked_cards, completeness}, ...]
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                p.id,
                p.title,
                COUNT(z.card_id) as card_count,
                COUNT(DISTINCT l.source_card_id) as linked_cards
            FROM papers p
            LEFT JOIN zettel_cards z ON p.id = z.paper_id
            LEFT JOIN zettel_links l ON z.card_id = l.source_card_id
            GROUP BY p.id
            HAVING card_count > 0
            ORDER BY card_count DESC
        """)

        results = []
        for row in cursor.fetchall():
            paper_id, title, card_count, linked_cards = row

            # 計算簡單完整度評分
            completeness = min(100, card_count * 5 + linked_cards * 5)

            results.append({
                'paper_id': paper_id,
                'title': title,
                'card_count': card_count,
                'linked_cards': linked_cards,
                'completeness': completeness
            })

        conn.close()
        return results

    def get_papers_without_zettel(self) -> List[Dict[str, Any]]:
        """
        獲取沒有 Zettelkasten 卡片的論文（待建立卡片）

        Returns:
            論文列表: [{id, title, cite_key, authors, year}, ...]
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.id, p.title, p.cite_key, p.authors, p.year
            FROM papers p
            LEFT JOIN zettel_cards z ON p.id = z.paper_id
            LEFT JOIN paper_zettel_links pzl ON p.id = pzl.paper_id
            WHERE z.card_id IS NULL AND pzl.paper_id IS NULL
            ORDER BY p.id
        """)

        results = []
        for row in cursor.fetchall():
            paper_id, title, cite_key, authors, year = row
            results.append({
                'id': paper_id,
                'title': title,
                'cite_key': cite_key,
                'authors': json.loads(authors) if authors else [],
                'year': year
            })

        conn.close()
        return results

    def export_zettel_cards(self, paper_id: int, output_dir: str) -> Dict[str, Any]:
        """
        匯出論文的 Zettelkasten 卡片到指定目錄

        按照 EXPORT_FORMAT_SPEC.md 格式輸出：
        - zettel_index.md
        - zettel_cards/{citekey}-001.md ...

        Args:
            paper_id: 論文 ID
            output_dir: 輸出目錄

        Returns:
            匯出結果: {success, card_count, output_dir, files}
        """
        from pathlib import Path
        from datetime import datetime

        result = {
            'success': False,
            'card_count': 0,
            'output_dir': output_dir,
            'files': []
        }

        # 獲取論文資料
        paper = self.get_paper_by_id(paper_id)
        if not paper:
            result['error'] = f'找不到論文 (ID: {paper_id})'
            return result

        # 獲取卡片資料
        cards = self.get_zettel_by_paper(paper_id)
        if not cards:
            result['error'] = f'論文沒有 Zettelkasten 卡片'
            return result

        cite_key = paper.get('cite_key') or f"paper_{paper_id}"
        output_path = Path(output_dir)
        cards_dir = output_path / 'zettel_cards'
        cards_dir.mkdir(parents=True, exist_ok=True)

        # 生成索引檔
        index_content = self._generate_zettel_index(paper, cards, cite_key)
        index_file = output_path / 'zettel_index.md'
        index_file.write_text(index_content, encoding='utf-8')
        result['files'].append(str(index_file))

        # 匯出每張卡片
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for card in cards:
            # 從資料庫讀取完整內容
            cursor.execute("""
                SELECT content, ai_notes, human_notes, source_info
                FROM zettel_cards WHERE card_id = ?
            """, (card['card_id'],))
            row = cursor.fetchone()
            content, ai_notes, human_notes, source_info = row if row else ('', '', '', '')

            card_content = self._generate_zettel_card(
                card, content, ai_notes, human_notes, source_info, cite_key
            )
            card_file = cards_dir / f"{card['zettel_id']}.md"
            card_file.write_text(card_content, encoding='utf-8')
            result['files'].append(str(card_file))

        conn.close()

        result['success'] = True
        result['card_count'] = len(cards)
        return result

    def _generate_zettel_index(self, paper: Dict, cards: List[Dict], cite_key: str) -> str:
        """生成 zettel_index.md 內容"""
        from datetime import datetime

        authors_str = ', '.join(paper['authors'][:3]) if paper['authors'] else ''
        year = paper.get('year') or ''
        doi = paper.get('doi') or ''
        generated_date = datetime.now().strftime('%Y-%m-%d %H:%M')

        # YAML Frontmatter
        content = f'''---
title: "{cite_key}"
aliases:
  - "{cite_key}"
authors: "{authors_str}"
year: "{year}"
doi: "{doi}"
generated_date: "{generated_date}"
card_count: {len(cards)}
---

# {cite_key}

**{paper['title']}**

## 📚 卡片清單

'''
        # 卡片清單
        for i, card in enumerate(cards, 1):
            core = card.get('core_concept', '')[:80] or card.get('title', '')
            content += f'''### {i}. [{card['title']}](zettel_cards/{card['zettel_id']}.md)
- **ID**: `{card['zettel_id']}`
- **核心**: "{core}"

'''

        # 閱讀建議順序
        content += '## 📖 閱讀建議順序\n\n'
        for i, card in enumerate(cards, 1):
            content += f'{i}. [[{card["zettel_id"]}]] {card["title"]}\n'

        return content

    def _generate_zettel_card(self, card: Dict, content: str, ai_notes: str,
                               human_notes: str, source_info: str, cite_key: str) -> str:
        """生成單張卡片的 Markdown 內容"""
        title = card.get('title', 'Untitled')
        summary = card.get('core_concept', '')

        card_content = f'''---
title: "{title}"
description: |-
  "{summary}"
---

## 說明

{content or '（無內容）'}

## 連結網絡

（匯出時無法重建連結關係）

## 來源脈絡

- 📄 **文獻**: {cite_key}
- 📍 **位置**: {source_info or '未知'}

## 個人筆記

🤖 **AI**: {ai_notes or '（無）'}

✍️ **Human**: {human_notes or '（待填寫）'}

'''
        return card_content


if __name__ == "__main__":
    # 測試代碼
    kb = KnowledgeBaseManager()
    stats = kb.get_stats()
    print("知識庫統計:")
    print(f"  論文總數: {stats['total_papers']}")
    print(f"  主題總數: {stats['total_topics']}")
    print(f"  引用總數: {stats['total_citations']}")
    print(f"  Zettel卡片: {stats['total_zettel_cards']}")
    print(f"  Zettel連結: {stats['total_zettel_links']}")
    print(f"  Zettel領域: {stats['total_zettel_domains']}")
    print(f"  Zettel資料夾: {stats['total_zettel_folders']}")
