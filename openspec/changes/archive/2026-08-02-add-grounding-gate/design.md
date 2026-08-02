# Design: add-grounding-gate

## Context

`generate_zettel`（`api/zettel.py`）目前流程：resolve_source → cite_key → render prompt → `call_llm` → `parse_llm_output`（step 5，僅用於 zero-card 檢查）→ `generate_zettelkasten`（step 6，**內部重新 parse `llm_output`** 並 canonicalize，寫檔）。

兩個既有事實決定架構：
1. **雙重 parse**：step 5 的 `cards` 與 step 6 內部的 `cards` 各自獨立；真正落地的是 step 6 那份。gate 要讓「過濾後的卡片」落地，必須讓 step 6 使用 gate 過濾後的清單，而非重新 parse。
2. **決定性 ID**：`_canonicalize_card_ids` 依實際張數重編 001..M 並丟棄斷鏈（前序 commit 2552a3f）。因此「erase 若干卡」是安全的——存活卡片重新連續編號、指向被刪卡的連結自動清除。

## Goals / Non-Goals

**Goals:**
- 寫檔前抹除無法逐字回溯原文的卡片（erase fail-closed）。
- 存活卡片的 description 一律覆寫為原文 raw span（provenance 擷刻 + P4 空格/連字修正）。
- grounding 記錄以工具中立 sidecar 保存，服務 Obsidian 以外的多介面。
- normalize 與 verdict 邏輯與 vault `quote_check.py` 對齊（本 repo 為權威）。

**Non-Goals:**
- 不做單卡重生（A.5 選項 A）；fail-closed 一律 erase。
- 不做 CJK 抽取修復（P5）；CJK 定位不到者標 `CJK_UNVERIFIABLE` 隔離待審，不 erase。
- 不做 >120000 字元文件分段（P1 殘留）。
- 不改 frontmatter 結構（template-strict）。

## Decisions

1. **插入點與流程重排**（`api/zettel.py`）：
   ```
   parse_llm_output(llm_output, cite_key=None)      # 延後 canonicalize
     → ground_cards(cards, source.content)           # 三分：KEEP / QUARANTINE(CJK) / ERASE
     → canonicalize_card_ids(KEEP, cite_key)         # 正常卡 001..M 連續、斷鏈丟棄
     → generate_zettelkasten(cards=KEEP)             # 正常輸出（跳過重新 parse）
     → 寫 QUARANTINE → zettel_cards/_needs_cjk_check/（ID 命名空間 {cite_key}-cjk-NNN）
     → 每張卡（KEEP + QUARANTINE）寫並存的 {card_id}.grounding.json
   ```
   `generate_zettelkasten` 加 `cards: Optional[List]=None`；傳入時跳過 parse/canonicalize，直接寫。舊呼叫（僅傳 llm_output）維持相容。QUARANTINE 卡不進主序號、不入索引/kb/embed，僅落地待審。

2. **gate 何時作用**：`request.ground` 為 True **且** `source.content` 長度達可比對門檻（避免 mock/極短來源誤刪全部）時才驗證；否則跳過並 emit warning「來源內容不足，跳過 grounding」。寫入管線的既有測試以 `ground=False` 明確隔離。

3. **verdict 與門檻**（鏡射 quote_check，常數集中可調）：
   - `normalize(Q) in normalize(S)` → `EXACT`（coverage 1.0）
   - 去空白後 in → `EXACT_NOSPACE`
   - `SequenceMatcher` 滑窗最佳比 ≥0.85 → `DRIFTED_MINOR`；≥0.60 → `DRIFTED_MAJOR`；否則 `NOT_FOUND`
   - 空 / 佔位符 / 結尾 `...` → `NO_DESC`（接 P9）
   - 含 Han 字且定位不到 → `CJK_UNVERIFIABLE`
   - **KEEP（正常輸出）**：EXACT / EXACT_NOSPACE / DRIFTED_MINOR
   - **QUARANTINE（隔離待審）**：CJK_UNVERIFIABLE
   - **ERASE（不落地）**：DRIFTED_MAJOR / NOT_FOUND / NO_DESC

4. **raw span 覆寫（安全自動修正）**：保留且非 CJK_UNVERIFIABLE 時，把 normalize 命中位置映回原文 raw offset，取真實 raw span。若 `normalize(core)==normalize(raw_span)`，以 raw span 覆寫 `core_summary`——只差雜訊，零 grounding 風險，順手修好空格/換行連字。

5. **sidecar schema**（工具中立，A.6）：
   ```json
   {
     "card_id": "Vigly-2025-015",
     "verdict": "EXACT_NOSPACE",
     "coverage": 1.0,
     "matched_span": "…原文真實樣貌…",
     "char_offset": [1234, 1301],
     "source_fingerprint": {"pdf_name": "Vigly-2025.pdf", "sha1": "…"}
   }
   ```
   與卡片同存於 `zettel_cards/`。frontmatter 不動。任何消費端（Obsidian importer / 其他 MCP client）可選擇性讀取；缺 sidecar 不影響卡片本身可用。

6. **normalize 單一真相 / 跨 repo 同步**：normalize 定義在本 repo `grounding_checker.py`，為權威。vault `quote_check.py` 無法被本 repo import（不同 repo），故不做程式強制；改以 reference memory 記錄「兩端 normalize 必須逐字一致」的同步義務，任一端改動時手動對齊。

7. **全數 erase 的處理**：gate 後 KEEP 為空 → 拋 `LLMGenerationError`（hint：來源與模型可能不匹配，或來源抽取品質差），不寫空目錄。（QUARANTINE 不算 KEEP；若只剩隔離卡而無正常卡，同樣視為失敗。）

8. **CLI/MCP 為薄透傳**：核心 `ZettelRequest.ground` 預設 True。`cli/` 的 zettel 入口加 `--no-ground`（`store_true` → `ground=False`）；MCP `generate_zettel` inputSchema 加選填 `ground`（預設 True）。兩層都只把值塞進 request，不含任何 gate 邏輯——gate 的真相唯一在 `api/zettel.py`。

## Risks / Trade-offs

- **[誤刪真卡]** DRIFTED 門檻過嚴可能刪掉「原文有、但抽取層空格塌陷」的真卡 → 由 EXACT_NOSPACE 與 DRIFTED_MINOR 兩層吸收空格/雜訊；CJK 另走 carve-out。門檻為可調常數，可依實測放寬。
- **[卡數變少]** erase 使某些論文出不滿 card_count → 已與 P2「上限化」決策一致，接受。統計欄回報 erased 數，透明可見。
- **[normalize 兩端漂移]** 跨 repo 無法 CI 強制 → 以 memory 記錄同步義務；本 repo sidecar 帶 verdict，vault 重驗時可比對而非盲信。
- **[source_fingerprint 的 sha1]** 需讀 PDF 位元組算 hash → 只在有 `request.pdf` 路徑時計算；URL/from_kb 來源以可得欄位（url / paper_id）替代，缺 pdf_name 時留空不阻斷。

## Migration Plan

純新增 + 相容擴充，無資料遷移。TDD 順序：
1. `grounding_checker.normalize` + `ground_card`（verdict 表、滑窗、raw span）— 純函式先行。
2. `generate_zettelkasten(cards=...)` 相容擴充 + 公開 `canonicalize_card_ids`。
3. `api/zettel.py` 編排（ground 旗標、erase、canonicalize 重排、sidecar、ground 階段事件、統計欄）。
4. MODIFY 既有 scenario 對應測試（progress 序加 ground；12 卡測試加 ground=False）。
5. 全套件綠 + README/CLAUDE.md 記錄 grounding 行為與 sidecar 格式 → `openspec archive add-grounding-gate`。
