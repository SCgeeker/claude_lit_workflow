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
└── styles/     # 學術風格定義、媒體類型定義
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
投影片生成 Prompt（`--media paper`，預設）

### prompts/media_slides_template.jinja2 / media_zettel_template.jinja2
非論文媒體（lecture / podcast / blog / textbook / monograph）的投影片與卡片 Prompt。
內容由 `styles/media_profiles.yaml` 注入（變數 `media`、`source_meta`、`citation`、`card_type_catalog`）。

**輸出協定不可改**：`===標題頁===`、`===投影片N===`、`===CARD: id===` 與各欄位標籤必須與論文模板一致，
`tests/unit/test_media_templates.py` 會斷言兩邊協定相同——解析器、grounding gate、匯入腳本都依賴它。

## 媒體類型

### styles/media_profiles.yaml

每種媒體一段 profile（與風格正交，可並用）：

| 欄位 | 用途 |
|------|------|
| `reading_stance` | 這類來源的閱讀方式與陷阱 |
| `slide_structure` / `slide_rules` | 建議簡報骨架與特有規則 |
| `card_type_weights` | 可用卡片類型與配比（鍵須在 `card_type_catalog` 中） |
| `core_rule` / `location_format` / `extra_card_rules` | 核心擷取、位置欄、卡片特有規則 |
| `citation_format` | 卡片來源連結，`{speaker}` 等由 `--meta` 填入；**必須含 `|`** |
| `preprocess` | 前處理步驟（`parse_subtitles`、`strip_fillers`、`merge_turns`、`insert_time_markers`、`strip_running_heads`、`chapter_split`） |
| `grounding.cjk_policy` | 只對 URL 來源生效（PDF 一律隔離、文字檔一律抹除） |
| `default_slide_count` / `recommended_styles` | 未指定 `--slides` 時的張數、guide 建議 |

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
