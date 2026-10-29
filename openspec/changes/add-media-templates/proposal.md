# Proposal: add-media-templates

## Why

現有兩個 prompt 模板（`journal_club_template`、`zettelkasten_template`）是為**學術論文**設計的：
投影片骨架寫死「研究背景／方法／發現／討論」，卡片類型配比以論文為準，來源脈絡假設
`Introduction/Methods/Results`，引用格式為 `[[cite_key.pdf|作者 (年份)]]`。
唯一的例外是 `source_type == "web_url"` 的一段 if 分支。

使用者希望同一套流程也能處理：

| 媒體 | 與論文的根本差異 |
|------|----------------|
| 講演逐字稿 | 口語、不完整句、語音辨識錯誤、時間軸定位 |
| Podcast 逐字稿 | 多講者，觀點必須歸屬到人；對談離題多 |
| 網誌 | 主張／證據／修辭混雜，時效性 |
| 教科書 | 教學結構（目標→定義→例題→習題）、篇幅超過單次上限 |
| 主題專書 | 全書論證結構、作者主張 vs 轉述他人、篇幅超過單次上限 |

若每種媒體都複製一份完整模板，輸出協定（`===投影片N===`、`===CARD: id===`、欄位標籤）
會分散在 10+ 個檔案中，任一份漂移就會讓 `SlideMaker` / `ZettelMaker` 解析器或 grounding gate
靜默失效。

## What Changes

- **媒體類型與風格正交**：新增 `media_type` 參數（`paper`（預設）/ `lecture` / `podcast` / `blog` /
  `textbook` / `monograph`）。風格決定語氣與受眾，媒體決定閱讀方式、結構骨架、卡片類型、位置與引用格式。
- **資料驅動的 media profile**：新增 `templates/styles/media_profiles.yaml`，每種媒體一段設定
  （`reading_stance`、`slide_structure`、`slide_rules`、`card_type_weights`、`location_format`、
  `citation_format`、`core_rule`、`preprocess`、`grounding.cjk_policy` 等）。使用者調整媒體行為時
  只需編輯 YAML，cwd 覆蓋機制照常適用。
- **兩個通用模板**：新增 `media_slides_template.jinja2`、`media_zettel_template.jinja2`，
  由 profile 注入內容；**輸出協定與既有模板逐字相同**。`media_type=paper` 時仍走既有模板（零回歸）。
- **卡片類型擴充**：新增 `claim`（主張）與 `example`（例子）；解析器的 `類型` 欄本為自由字串、
  知識庫 `card_type` 為 TEXT 欄，不需 schema migration。
- **文字來源**：新增 `text` 來源（`.txt` / `.md` / `.srt` / `.vtt`；`.epub` 為選配），
  含逐字稿前處理（解析字幕、去除填充詞、合併講者段落、插入時間標記）。
- **長篇來源分章**：`textbook` / `monograph` 支援 `--chapter`（指定章節範圍）；cite_key 加章節後綴
  （`Author-Year-ch03`），避免同書不同章的卡片 ID 衝突。
- **grounding 的 CJK 政策依來源而定**：文字來源（txt/md/srt/vtt/epub）沒有 CID glyph 抽取問題，
  中文核心定位不到即 **erase**；PDF 來源維持現行 **quarantine**。
- **時間軸回映**：逐字稿來源的 grounding sidecar 新增 `timestamp`，由 `char_offset` 回映字幕時間軸，
  不依賴 LLM 自填的位置欄。
- CLI：`slides` / `zettel` 新增 `--media`、`--text`、`--chapter`、`--meta key=value`；
  MCP：`generate_slides` / `generate_zettel` 新增對應選填參數；`list_options` 回傳媒體目錄。

## Capabilities

### Modified Capabilities

- `slide-generation`：依 `media_type` 選擇模板與 profile；新增文字來源。
- `zettel-generation`：依 `media_type` 選擇模板與 profile；新增卡片類型、文字來源、分章 cite_key、
  依來源的 CJK 政策、逐字稿 timestamp sidecar。
- `cli`：新增 `--media` / `--text` / `--chapter` / `--meta` 旗標。

## Impact

- **新增**：`templates/styles/media_profiles.yaml`、`templates/prompts/media_slides_template.jinja2`、
  `templates/prompts/media_zettel_template.jinja2`（含套件內建版）、
  `src/claude_lit/extractors/text_extractor.py`（txt/md/srt/vtt/epub）、`src/claude_lit/extractors/chapters.py`、
  `src/claude_lit/api/media.py`（profile 載入、metadata 與 citation 渲染）、`src/claude_lit/cli/media_args.py`
- **修改**：`api/models.py`（`MediaType` enum、`text` 來源、`source_meta`、`chapter`）、
  `api/sources.py`（text 來源與前處理）、`api/prompts.py`（依媒體選模板）、`api/zettel.py`（CJK 政策、
  timestamp sidecar）、`generators/slide_maker.py`（可注入替代模板）、`cli/`、`mcp_server/`、
  `tests/unit/test_resources.py`（`SYNCED_RESOURCES` 加入新檔）
- **相依**：無新增（`.epub` 以標準庫 `zipfile` / `xml.etree` / `html.parser` 抽取）
- **相容性**：`media_type` 預設 `paper` → 既有指令、QuickAdd wrapper、MCP 呼叫行為完全不變
- **連帶修正**：grounding gate 以原文 span 改寫核心時不再套用 NFKC（原會把中文全形標點轉成半形）
- **Non-Goals**：音訊/影片直接轉錄（ASR）——使用者自備逐字稿（YouTube 字幕、Whisper、Podcast 平台逐字稿）；
  全書自動 map-reduce 摘要（列為後續 change）；掃描版書籍 OCR
