# Tasks: add-grounding-gate

## 1. grounding_checker 純函式（normalize + verdict + span）

- [x] 1.1 失敗測試 `tests/unit/test_grounding_checker.py`：
  - `normalize` 吸收空白塌陷、換行連字（`compre-\nhender`→`comprehender`）、彎/直引號、NFKC；不吸收用字/語序/實質標點
  - `ground_card` verdict 表：EXACT / EXACT_NOSPACE / DRIFTED_MINOR(≥0.85) / DRIFTED_MAJOR(≥0.60) / NOT_FOUND / NO_DESC（空/佔位符/結尾`...`）/ CJK_UNVERIFIABLE（Han 字定位不到）
  - 回傳含 coverage、matched raw span、char_offset
- [x] 1.2 實作 `src/claude_lit/checkers/grounding_checker.py`（`difflib.SequenceMatcher` 滑窗、門檻常數集中、raw offset 回映）

## 2. zettel_maker 相容擴充

- [x] 2.1 失敗測試（`tests/unit/test_zettel_maker.py` 增補）：`generate_zettelkasten(cards=<已解析清單>)` 跳過重新 parse、直接以傳入卡片寫檔；未傳 `cards` 時維持舊 parse 路徑；`canonicalize_card_ids` 可公開呼叫並回傳 001..M 連續 ID、丟棄斷鏈
- [x] 2.2 實作：`generate_zettelkasten` 加 `cards: Optional[List]=None`；`_canonicalize_card_ids` 對外公開為 `canonicalize_card_ids`

## 3. api/zettel gate 編排

- [x] 3.1 失敗測試 `tests/unit/test_zettel_grounding.py`（來源 mock 為含特定引文的文字）：
  - 核心可定位 → 保留 + 寫入
  - 核心 NOT_FOUND → 抹除（不在 card_files、不計 card_count）
  - `ground=False` → 12 張全保留
  - 全數抹除 → `LLMGenerationError`
  - 每張存活卡有 `{card_id}.grounding.json`（含 verdict + source_fingerprint）
  - frontmatter 不含 grounding 欄位
  - 換行連字核心 → 寫入為 raw span
  - 中文核心定位不到 → 隔離：寫入 `zettel_cards/_needs_cjk_check/`、不在 card_files、不計 card_count、不入索引；sidecar verdict=CJK_UNVERIFIABLE；`flagged`≥1
  - 只剩隔離卡而無正常卡 → `LLMGenerationError`
  - progress 序含 `ground`；ZettelResult 含 grounded/erased/flagged
- [x] 3.2 `api/models.py`：`ZettelRequest.ground: bool=True`；`ZettelResult` 加 `grounded`/`erased`/`flagged`
- [x] 3.3 實作 `api/zettel.py` 編排：parse(cite_key=None) → ground_cards（三分 KEEP/QUARANTINE/ERASE、raw span 覆寫）→ canonicalize(KEEP) → `generate_zettelkasten(cards=KEEP)` → 寫隔離卡至 `_needs_cjk_check/` → 寫 sidecar；emit `ground` 階段事件與統計；來源不足時跳過 + warning

## 4. CLI / MCP grounding 開關（薄透傳）

- [x] 4.1 失敗測試：`tests/integration/test_cli_thin.py` — `zettel --no-ground` → `request.ground is False`，預設 → True；`tests/unit/test_mcp_server.py` — `generate_zettel` 帶/不帶 `ground` → 透傳正確
- [x] 4.2 實作：`cli/` zettel 入口加 `--no-ground`（store_true）；MCP `generate_zettel` inputSchema 加選填 `ground`（預設 True），透傳至 `ZettelRequest.ground`

## 5. 既有 scenario 對齊 + 收尾

- [x] 5.1 MODIFY 對應測試：`test_progress_event_order` 期望序改為含 `ground`；`test_generates_12_cards` 等寫入管線測試加 `ground=False`
- [x] 5.2 全套件綠（unit + integration）；`test_resources` 確認無新增模板不一致
- [x] 5.3 README / CLAUDE.md 記錄 grounding gate 行為、erase 政策、`--no-ground` 開關與 sidecar `{card_id}.grounding.json` 格式（含隔離區 `_needs_cjk_check/`）；`docs/` 記錄 vault `quote_check.py` normalize 同步義務
- [x] 5.4 `openspec archive add-grounding-gate`
