# zettel-generation Spec Delta

## ADDED Requirements

### Requirement: 生成端 grounding gate（erase fail-closed）
系統 MUST 在卡片解析之後、寫檔之前，對每張卡片的 `核心`（core_summary）以 normalize 後的子字串／滑窗比對回原文來源，判定 verdict。verdict ∈ {DRIFTED_MAJOR, NOT_FOUND, NO_DESC} 的卡片 MUST 於寫檔前抹除（erase）：不得寫入輸出目錄、不得入庫、不得嵌入向量。gate 僅在 `ground=True` 且來源內容達可比對門檻時作用；`ground=False` 或來源內容不足時 MUST 跳過驗證並保留全部卡片。gate 後存活卡片為空時 MUST 拋出 `LLMGenerationError`。

#### Scenario: 核心可定位於原文則保留
- **WHEN** 卡片 `核心` 的 normalize 結果為原文的子字串，以 `ground=True` 生成
- **THEN** 該卡片被保留並寫入輸出目錄

#### Scenario: 核心無法定位則抹除
- **WHEN** 某卡片 `核心` 在原文中 normalize 後既非子字串、滑窗最佳比亦 <0.60（NOT_FOUND）
- **THEN** 該卡片不出現在 `card_files`、不寫入 `zettel_cards/`，且不計入 `card_count`

#### Scenario: 關閉 grounding 則全數保留
- **WHEN** 以 `ground=False` 生成（LLM 輸出 12 張卡）
- **THEN** 12 張全數寫入，gate 不抹除任何卡片

#### Scenario: 全部卡片被抹除視為失敗
- **WHEN** `ground=True` 且所有卡片核心皆無法定位於原文
- **THEN** 拋出 `LLMGenerationError`，不寫出空目錄

### Requirement: grounding 記錄以工具中立 sidecar 保存
每張存活卡片 MUST 產生 sidecar `{card_id}.grounding.json`，與其卡片並存（存活卡片於 `zettel_cards/`，隔離卡片於 `zettel_cards/_needs_cjk_check/`），含 `verdict`、`coverage`、`matched_span`、`char_offset`、`source_fingerprint`（至少 `pdf_name` 與 `sha1`，缺項留空不阻斷）。卡片 frontmatter MUST NOT 新增 grounding 欄位（保持 template-strict，供 Obsidian 以外的多介面選擇性消費）。

#### Scenario: 每張存活卡片有 sidecar
- **WHEN** 以 `ground=True` 從 PDF 生成且有卡片存活
- **THEN** 每張存活卡片旁存在 `{card_id}.grounding.json`，內含 `verdict` 與 `source_fingerprint`

#### Scenario: frontmatter 不含 grounding 欄位
- **WHEN** 檢視任一存活卡片的 `.md` frontmatter
- **THEN** 其 frontmatter 不含 `grounding` 鍵（記錄僅存在於 sidecar）

### Requirement: raw span 安全自動修正
當卡片核心與其命中的原文 raw span 僅差 normalize 級雜訊（空白塌陷、換行連字、彎/直引號、NFKC）時，系統 MUST 以原文 raw span 覆寫 `core_summary`，使寫入卡片的 description 永遠是原文樣貌。

#### Scenario: 換行連字被還原為原文樣貌
- **WHEN** 卡片核心為 `rational compre-hender`（換行連字），原文 raw span 為 `rational comprehender`
- **THEN** 寫入卡片的核心為 `rational comprehender`（原文 raw span），verdict 為 EXACT_NOSPACE 或 DRIFTED_MINOR

### Requirement: CJK 不可驗證卡片隔離待審（carve-out）
當卡片核心含 Han 字且無法於抽取文字中定位時，verdict MUST 記為 `CJK_UNVERIFIABLE`。此類卡片 MUST NOT 被抹除，亦 MUST NOT 混入正常卡片集：系統 MUST 將其寫入隔離區 `zettel_cards/_needs_cjk_check/`（含其 sidecar），並排除於 `card_files`、`card_count`、索引與知識庫/嵌入之外，於 `ZettelResult.flagged` 回報數量。此為 erase 政策的明確例外，避免在 P5（CJK 抽取偵測）未實作前誤刪真實中文卡片，同時不讓未驗證卡污染正常輸出。

#### Scenario: 中文核心定位不到則隔離待審
- **WHEN** 卡片核心為中文且不在抽取文字中，以 `ground=True` 生成
- **THEN** 該卡片寫入 `zettel_cards/_needs_cjk_check/`、不在 `card_files`、不計入 `card_count`、不入索引；其 sidecar `verdict` 為 `CJK_UNVERIFIABLE`；`ZettelResult.flagged` ≥ 1

## MODIFIED Requirements

### Requirement: 進度回報
API SHALL 接受選填 `progress` callback；流程 MUST 依序發出 stage 涵蓋 `extract`、`prompt`、`llm`、`parse`、`ground`、`write` 的 `ProgressEvent`（入庫時另有 `kb`、`embed`）。`ground` 階段 MUST 回報 grounding 統計（grounded / erased / flagged）。

#### Scenario: callback 收到階段事件
- **WHEN** 以 progress callback、`ground=True` 呼叫 `generate_zettel`（LLM 與來源被 mock 為可定位）
- **THEN** callback 依序收到 `extract`→`prompt`→`llm`→`parse`→`ground`→`write` 事件

### Requirement: 可程式化 Zettel 卡片生成 API
系統 SHALL 提供 `generate_zettel(request: ZettelRequest, *, progress=None) -> ZettelResult` 純 Python API。此 API MUST NOT 依賴 argparse、MUST NOT 呼叫 `sys.exit`、MUST NOT 直接寫入 stdout。`ZettelRequest.ground` 預設為 True（啟用 grounding gate）；`ZettelResult` MUST 回報 `grounded`、`erased`、`flagged` 統計。

#### Scenario: 從 PDF 生成標準數量卡片（隔離 grounding）
- **WHEN** 以存在的 PDF、`detail="standard"`、`add_to_kb=False`、`ground=False` 呼叫 `generate_zettel`（LLM 輸出被 mock 為含 12 張 `===CARD:===` 區塊）
- **THEN** 回傳 `ZettelResult`：輸出目錄含 12 個卡片 `.md` 檔與 1 個索引檔，`card_count == 12`，`card_files` 列出各卡片路徑

#### Scenario: 輸出目錄結構符合規範
- **WHEN** 生成完成
- **THEN** 輸出目錄符合 `output/zettelkasten_notes/zettel_{citekey}_{date}_{model}/`，內含 `zettel_index.md` 與 `zettel_cards/{citekey}-NNN.md`
