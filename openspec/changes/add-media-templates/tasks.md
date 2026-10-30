# Tasks: add-media-templates

## 1. Profile 與模板（由 drafts/ 落地）

- [x] 1.1 失敗測試 `tests/unit/test_media_templates.py`：每個 profile 渲染兩模板皆含全部協定標記；協定標記集合與 legacy 模板相同；`card_type_weights` 鍵 ⊆ `card_type_catalog`；`citation_format` 含 `|`
- [x] 1.2 將 `drafts/templates/` 三檔移入 `templates/` 與 `src/claude_lit/resources/templates/`（drafts/ 已移除）；`test_resources.SYNCED_RESOURCES` 加入
- [x] 1.3 `api/media.py`：`get_media_profile(name)`、`render_citation(profile, cite_key, source_meta)`（`format_map` + `defaultdict(str)`）

## 2. Request / 來源

- [x] 2.1 `api/models.py`：`MediaType` enum（paper/lecture/podcast/blog/textbook/monograph，預設 paper）；`SlideRequest`/`ZettelRequest` 加 `media_type`、`text: Optional[Path]`、`source_meta: dict`、`chapter: Optional[str]`；來源互斥規則納入 `text`
- [x] 2.2 失敗測試 `tests/unit/test_text_extractor.py`：txt/md 原樣；SRT/VTT 去序號與時間碼並產出 offset→時間 對照；`strip_fillers` 只移除獨立填充詞；`insert_time_markers` 標記獨立成行
- [x] 2.3 實作 `extractors/text_extractor.py`；`api/sources.py` 加 text 分支，依 profile `preprocess` 執行
- [x] 2.4 `chapter_split`（PDF 書籤優先、章標題 regex 後備，見 design §9）；`--chapter` 範圍解析；cite_key 加 `-chNN` 後綴

## 3. 生成編排

- [x] 3.1 `api/prompts.py`：`media_type != paper` 時改用媒體模板並注入 profile、`source_meta`、`citation`、`card_type_catalog`；`get_card_count` 不變
- [x] 3.2 `SlideMaker.generate_prompt` 支援傳入替代模板路徑與額外變數（不改既有預設）
- [x] 3.3 `grounding_checker.ground_card(..., cjk_policy="quarantine")`；`api/zettel.py` 依來源傳入 erase/quarantine
- [x] 3.4 逐字稿來源 sidecar 加 `timestamp`（由 `char_offset` 回映）
- [x] 3.5 測試：`media_type=paper` 渲染結果與修改前**逐字相同**（零回歸）

## 4. CLI / MCP / guide

- [x] 4.1 CLI `--media`、`--text`、`--chapter`、`--meta key=value`（可重複）、`--keep-fillers`；`--help` 列出媒體目錄
- [x] 4.2 MCP `generate_slides` / `generate_zettel` 加對應選填參數；`list_options` 回傳 `media_types`；新增 resource `styles://media-profiles`
- [x] 4.3 `usage_guide.jinja2` 加媒體類型段落，讓 `uv run guide` 能建議 `--media`

## 5. 收尾

- [x] 5.1 README / README.en 指令總覽加入媒體類型範例；`templates/CLAUDE.md` 說明 profile
- [ ] 5.2 以真實樣本各跑一次（一段 YouTube 字幕、一集 podcast 逐字稿、一篇網誌、一章教科書）並記錄 grounded/erased 比例 —— **待辦**：需有 LLM 金鑰的環境
- [x] 5.3 全套件綠（`test_wheel_smoke` 寫死 Windows venv 路徑，Linux 上無法執行；另以 `uv build` 確認新檔已打包）

## 6. 實作中追加

- [x] 6.1 grounding gate 改寫核心時改用 `join_span`（只接合換行連字、塌陷空白），不再套 NFKC——原先會把中文全形標點轉成半形，違反「核心逐字保留原文」
- [x] 6.2 CLI `--chapter` 用錯（非書籍媒體、範圍顛倒）以 exit 1 與訊息呈現，不丟 traceback
- [x] 6.3 dev-local 實測修正：`--chapter` 在「N. Title」專書上把行首的「Chapter 2.」交叉引用當成章標題、靜默取到全書結尾——改為 PDF 書籤優先、收緊標題判定、支援「N. Title」、章節邊界不可靠時拋錯；回歸測試以合成文字與 PyPDF2 產生的書籤 PDF 重現
