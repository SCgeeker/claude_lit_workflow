# knowledge_base/ - 知識庫

## 結構

```
knowledge_base/
├── index.db    # SQLite 資料庫
└── papers/     # Markdown 論文筆記
```

## 資料庫 Schema

### papers 表
```sql
- id (INTEGER PRIMARY KEY)
- title (TEXT)
- authors (TEXT)  -- JSON 陣列
- year (INTEGER)
- abstract (TEXT)
- keywords (TEXT) -- JSON 陣列
- file_path (TEXT)
- cite_key (TEXT UNIQUE)
- original_citekey (TEXT)  -- 待實作
- doi (TEXT UNIQUE)        -- 待實作
- created_at (DATETIME)
```

### 其他表
- `topics` - 主題分類
- `paper_topics` - 論文-主題關聯
- `citations` - 引用關係
- `papers_fts` - 全文搜索索引（FTS5）

## 論文筆記格式

```markdown
---
title: "論文標題"
authors: ["作者1", "作者2"]
year: 2024
keywords: ["關鍵詞1", "關鍵詞2"]
cite_key: Author-Year
---

## 摘要
...

## 內容
...
```

## CLI 操作（已暫停）

> `uv run kb`（analyze / kb / embeddings）已歸檔停用，知識管理改由筆記 App 接管，
> 見根目錄 `CLAUDE.md`「暫停功能」。以下指令暫不可用，保留供日後參考：

```bash
# uv run kb list           # 列出論文
# uv run kb search "query" # 搜索
# uv run kb stats          # 統計
```
