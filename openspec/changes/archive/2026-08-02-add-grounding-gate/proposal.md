# Proposal: add-grounding-gate

## Why

卡片生成缺陷報告 P3：生成階段**完全沒有** verbatim grounding 驗證。prompt 教了「核心必須逐字擷取原文」，但沒有一行程式在寫檔前驗證它。所有 grounding 缺陷（自我指涉摘要、杜撰卡、與原文矛盾、`...` 截斷、跨卡重複引文）原封出貨，只能靠 vault 端 `quote_check.py` 在數週後、匯入之後才發現。

本 change 在生成 pipeline 內、**寫檔之前**加一道 grounding gate：把 LLM 的 `核心` 只當**查詢鍵**去原文定位，找不到就抹除（erase）該卡；找到就用原文真實 span 覆寫 description（provenance 擷刻）。這把 grounding 從「事後可重推的猜測」升級成「生成當下釘死的事實」，並同時吃掉 P4（空格/連字損壞）與 P9（`...` 截斷、跨卡重複引文）。

P1（截斷）與 P2（硬配額）已於前序 commit 拆除主要引信；gate 是接住殘餘杜撰的**最後一道總閘**。

**兩個已拍板政策**（使用者決定）：
- **fail-closed = erase**：定位不到原文的卡片直接抹除，不標記出貨、不硬留（與 P2「上限化」一致，誠實優先）。
- **記錄存 sidecar**：grounding 記錄存成工具中立的 `{card_id}.grounding.json`，**不塞 frontmatter**。因本 MCP 要服務 Obsidian 以外的多個介面/消費端，記錄須是任何 client 都能選擇性讀取的機器格式。

## What Changes

- 新增 `src/claude_lit/checkers/grounding_checker.py`（與 `quality_checker.py` 平行，作用在 **card 層**）：
  - `normalize(text)`：空白塌陷、換行連字接合、彎/直引號正規化、NFKC；**只吸收不影響 grounding 的雜訊**。此為本 repo 對 grounding normalize 的權威定義，vault `quote_check.py` 應向此收斂（跨 repo 無法 import，以 reference 記錄同步義務）。
  - `ground_card(core_summary, source_content)` → verdict + coverage + matched raw span + char_offset。verdict：`EXACT` / `EXACT_NOSPACE` / `DRIFTED_MINOR`(≥0.85) / `DRIFTED_MAJOR`(≥0.60) / `NOT_FOUND` / `NO_DESC` / `CJK_UNVERIFIABLE`（門檻為可調常數）。
- `api/zettel.py` 插入 gate（parse 之後、write 之前）：
  - 解析改為**延後 canonicalize**（先不編 ID）→ gate 過濾 → 對存活卡片才 canonicalize（001..M 連續，斷鏈自動丟棄）。
  - **erase 政策**：verdict ∈ {DRIFTED_MAJOR, NOT_FOUND, NO_DESC} 的卡片不寫檔、不入庫。（保留門檻：EXACT / EXACT_NOSPACE / DRIFTED_MINOR≥0.85 保留。）
  - **CJK 隔離待審**：核心含 Han 字且定位不到 → `CJK_UNVERIFIABLE`，**不 erase 也不混入正常卡片集**，寫入隔離區 `zettel_cards/_needs_cjk_check/`，排除於 card_files/索引/kb 之外，待 P5 或人工審過再收編。
  - **安全自動修正**：LLM 版與 raw span 僅差 normalize 雜訊時，以 raw span 覆寫 core_summary（修好空格/連字，同時解 P4）。
  - 全數被 erase → 拋 `LLMGenerationError`。
- `generators/zettel_maker.py`：`generate_zettelkasten` 新增 `cards=` 參數，可接受已解析/過濾/編號的卡片，**跳過內部重新 parse**（現行為 llm_output 重複解析，與 api 層 gate 過濾脫節）；公開 `canonicalize_card_ids`。
- **sidecar 輸出**：每張卡片旁寫 `{card_id}.grounding.json`（存活卡片於 `zettel_cards/`，隔離卡片於 `zettel_cards/_needs_cjk_check/`），含 verdict、coverage、matched_span、char_offset、source_fingerprint{pdf_name, sha1}。frontmatter **不新增** grounding 欄位。
- `api/models.py`：`ZettelRequest` 新增 `ground: bool = True`（核心 API 預設啟用）；`ZettelResult` 新增 `grounded` / `erased` / `flagged` 統計。
- **CLI/MCP 開關**：`uv run zettel` 加 `--no-ground` 旗標；MCP `generate_zettel` tool 加選填 `ground` 布林參數（預設 True）。兩者僅透傳 `request.ground`。
- 進度：parse 與 write 之間新增 `ground` 階段 `ProgressEvent`，回報 `X/N grounded，erased M，flagged K`。

## Capabilities

### Modified Capabilities

- `zettel-generation`: 新增生成端 grounding gate（erase fail-closed）、sidecar provenance 記錄、raw span 安全覆寫、CJK 隔離待審、`ground` 階段與統計；既有進度序與「標準數量卡片」scenario 隨之調整。
- `cli`: `uv run zettel` 新增 `--no-ground` 開關（預設啟用 grounding）。
- `mcp-server`: `generate_zettel` tool 新增選填 `ground` 參數（預設 True）。

## Impact

- **新增**：`src/claude_lit/checkers/grounding_checker.py`、`tests/unit/test_grounding_checker.py`、`tests/unit/test_zettel_grounding.py`
- **修改**：`api/zettel.py`（gate 編排）、`api/models.py`（ground 旗標 + 統計欄）、`generators/zettel_maker.py`（cards 參數 + 公開 canonicalize）、`cli/`（zettel `--no-ground`）、`mcp_server/`（generate_zettel `ground` 參數）、`api/__init__.py`（如需 re-export）
- **相依**：無新增（`difflib.SequenceMatcher`、`hashlib`、`unicodedata`、`json` 皆標準庫）
- **相容性**：
  - `ground=True` 為預設 → 真實生成行為改變（會 erase 定位不到的卡）。這是本 change 的目的。
  - 既有寫入管線測試（如 `test_generates_12_cards`）改以 `ground=False` 隔離；grounding 行為由新增 scenario 覆蓋。
  - `generate_zettelkasten(llm_output=...)` 舊呼叫維持相容（`cards` 未傳時走原 parse 路徑）。
- **未涵蓋（明列 Non-Goal）**：P5 CJK 抽取偵測（gate 只能標 `CJK_UNVERIFIABLE`）、P1 超過 120000 字元文件的分段餵入、vault `quote_check.py` 的實際收斂（本 change 只定義權威 normalize 並記錄同步義務）。
