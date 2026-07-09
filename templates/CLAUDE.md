# templates/ - 模板庫

## 定位：cwd 覆蓋層（package-cli 之後）

套件內建一份預設模板（`src/claude_lit/resources/templates/`，隨 wheel 發佈）。
執行時的解析順序：**明確傳入路徑 > 目前工作目錄的 `templates/...` > 套件內建**。

- 在 repo 目錄下執行 `uv run slides/zettel` 時，**本目錄優先生效**——直接編輯這裡即可調整 prompt 與輸出格式，不需重新安裝
- wheel 安裝到其他機器、工作目錄沒有 `templates/` 時，自動使用套件內建版
- **管理規則**：修改 `prompts/*.jinja2`、`styles/academic_styles.yaml`、`markdown/*.jinja2` 後，需同步到 `src/claude_lit/resources/templates/` 再發佈——`tests/unit/test_resources.py` 會斷言兩份內容一致，漂移時測試失敗提醒

## 結構

```
templates/
├── prompts/    # LLM Prompt 模板
└── styles/     # 學術風格定義
```

## Prompt 模板

### prompts/zettelkasten_template.jinja2
Zettelkasten 卡片生成 Prompt

**變數**:
- `topic` - 論文主題
- `card_count` - 卡片數量
- `detail_level` - 詳細程度
- `paper_content` - 論文內容
- `cite_key` - 引用鍵
- `language` - 語言

### prompts/journal_club_template.jinja2
投影片生成 Prompt

## 學術風格

### styles/academic_styles.yaml

8 種風格：
- `classic_academic` - 經典學術
- `modern_academic` - 現代學術（預設）
- `clinical` - 臨床導向
- `research_methods` - 研究方法
- `literature_review` - 文獻回顧
- `case_analysis` - 案例分析
- `teaching` - 教學導向
- `zettelkasten` - 原子化筆記

5 種詳細程度：
- `minimal` / `brief` / `standard` / `detailed` / `comprehensive`

3 種語言：
- `chinese` / `english` / `bilingual`
