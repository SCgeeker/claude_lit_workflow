# zettel-generation Specification

## Purpose
TBD - created by archiving change extract-core-api. Update Purpose after archive.
## Requirements
### Requirement: 可程式化 Zettel 卡片生成 API
系統 SHALL 提供 `generate_zettel(request: ZettelRequest, *, progress=None) -> ZettelResult` 純 Python API。此 API MUST NOT 依賴 argparse、MUST NOT 呼叫 `sys.exit`、MUST NOT 直接寫入 stdout。

#### Scenario: 從 PDF 生成標準數量卡片
- **WHEN** 以存在的 PDF 與 `detail="standard"`、`add_to_kb=False` 呼叫 `generate_zettel`（LLM 輸出被 mock 為含 12 張 `===CARD:===` 區塊）
- **THEN** 回傳 `ZettelResult`：輸出目錄含 12 個卡片 `.md` 檔與 1 個索引檔，`card_count == 12`，`card_files` 列出各卡片路徑

#### Scenario: 輸出目錄結構符合規範
- **WHEN** 生成完成
- **THEN** 輸出目錄符合 `output/zettelkasten_notes/zettel_{citekey}_{date}_{model}/`，內含 `zettel_index.md` 與 `zettel_cards/{citekey}-NNN.md`

### Requirement: cite_key 解析規則
系統 MUST 依序解析 cite_key：明確傳入值 > bib 檔解析 > DOI/CrossRef 自動解析；格式為 `Author-Year`。無法解析時 MUST 拋出 `CiteKeyMissingError`。

#### Scenario: 明確傳入 cite_key
- **WHEN** request 帶 `cite_key="Barsalou-1999"`
- **THEN** 所有卡片 ID 以 `Barsalou-1999-` 為前綴

#### Scenario: 缺少 cite_key 時失敗
- **WHEN** 無法從任何來源解析出 cite_key
- **THEN** 拋出 `CiteKeyMissingError`，`hint` 含手動指定 `--citekey` 的指引

### Requirement: 知識庫整合為選擇性行為
`add_to_kb=False` 時系統 MUST NOT 觸碰 SQLite 知識庫，MUST NOT import chromadb；kb / 向量相依 MUST 為函式內 lazy import。

#### Scenario: 不入庫時零 kb 副作用
- **WHEN** 以 `add_to_kb=False, embed=False` 呼叫 `generate_zettel`
- **THEN** 知識庫檔案（index.db）的修改時間不變，且 `sys.modules` 未載入 chromadb

#### Scenario: 入庫回報統計
- **WHEN** 以 `add_to_kb=True` 呼叫且入庫成功
- **THEN** `ZettelResult.kb_added` 回報新增筆數、`kb_skipped` 回報略過筆數

### Requirement: LLM 輸出解析容錯
卡片解析 MUST 容忍 LLM 輸出中的格式雜訊；當解析出的卡片數為 0 時 MUST 拋出 `LLMGenerationError`。

#### Scenario: 解析零卡片視為失敗
- **WHEN** LLM 輸出不含任何 `===CARD:===` 區塊
- **THEN** 拋出 `LLMGenerationError`，`hint` 建議更換模型或降低 detail

### Requirement: 進度回報
API SHALL 接受選填 `progress` callback；流程 MUST 依序發出 stage 涵蓋 `extract`、`prompt`、`llm`、`parse`、`write` 的 `ProgressEvent`（入庫時另有 `kb`、`embed`）。

#### Scenario: callback 收到階段事件
- **WHEN** 以 progress callback 呼叫 `generate_zettel`（LLM 被 mock）
- **THEN** callback 依序收到 `extract`→`prompt`→`llm`→`parse`→`write` 事件

### Requirement: Zettel prompt 渲染 API
系統 SHALL 提供 `render_zettel_prompt(request: ZettelRequest) -> str`，回傳渲染完成的完整 LLM 提示詞。

#### Scenario: 渲染含卡片數與 cite_key
- **WHEN** 以 `detail="standard"`、`cite_key="Test-2024"` 呼叫 `render_zettel_prompt`
- **THEN** 回傳字串含目標卡片數（12）與 `Test-2024` 的卡片 ID 規則指示

### Requirement: 模板資源解析
Zettel 卡片生成使用的 prompt 模板、卡片模板與索引模板 MUST 透過資源解析機制載入：明確傳入路徑 > cwd 使用者檔 > 套件內建（importlib.resources）。

#### Scenario: 安裝後無原始碼樹仍可生成
- **WHEN** 於 wheel 安裝環境（無 repo 原始碼樹）呼叫 `generate_zettel`（LLM 被 mock）
- **THEN** zettelkasten 模板與卡片/索引模板從套件內資源載入，卡片輸出正常

