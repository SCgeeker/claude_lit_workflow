# Design: extract-core-api

## Context

三支 CLI（`make_slides.py` ~480 行、`generate_zettel.py` ~630 行、`setup.py`）的 `main()` 混雜編排邏輯：來源分支（pdf/url/from-kb/topic）、jinja2 prompt 渲染、cite_key 解析、跨論文連結查詢（`_query_related_cards`）、入庫與嵌入。核心類別 `SlideMaker`（含多供應商 `call_llm` 分派）與 `ZettelMaker`（卡片解析與輸出）已存在但以 `print()` 直接輸出。後續 change 要建 MCP server（stdio 傳輸不容許 stdout 污染）並打包為 wheel（`sys.path.insert` hack 需最終移除）。

## Goals / Non-Goals

**Goals:**
- CLI 與未來 MCP 共用單一核心 API 層（`src/api/`）
- pydantic 介面（之後 FastMCP 可直接轉 inputSchema）
- 核心層 stdout 淨空（print → logging / progress callback）
- 型別化例外含修復 hint
- CLI 對外行為零變化（回歸保護）

**Non-Goals:**
- 不做 MCP server（change 2）
- 不改 package 佈局、不刪 `sys.path.insert`（change 3）；新程式碼以可搬移的 import 風格集中於 `src/api/`，降低 change 3 觸及面
- 不重構暫停功能（analyze/kb/embeddings CLI 不動，僅 zettel 流程用到的 kb 呼叫改 lazy import）

## Decisions

1. **pydantic model 而非 kwargs 作為 API 介面**
   理由：pydantic 已在相依；enum/範圍/互斥驗證集中一處；change 2 的 FastMCP 直接重用欄位定義。替代方案 kwargs + 手動驗證：驗證邏輯分散、MCP schema 要重寫一遍，否決。

2. **例外階層而非 error codes**
   `LitWorkflowError(hint=...)` 基底 + 六個子類（SourceNotFound/Extraction/CiteKeyMissing/ProviderUnavailable/LLMGeneration/Config）。CLI 層 catch 後印 `❌ {e}` / `💡 {e.hint}` 並回傳 exit code；MCP 層由 FastMCP 轉 `isError=true`。hint 讓呼叫端 LLM 能自我修正參數。

3. **ProgressEvent callback 而非直接 logging**
   核心層發 `ProgressEvent(stage, message, current, total)`；CLI adapter 印 emoji 格式（UX 不變）、MCP adapter 之後轉 `ctx.report_progress`。純 logging 無法讓 CLI 保持現有互動輸出格式，否決。

4. **回傳檔案路徑清單 + metadata，不回傳完整內容**
   卡片可達 30+ 檔；`SlideResult.preview` 提供截斷預覽。呼叫端要全文時自行讀檔（MCP 於 change 2 另設 `read_output` tool）。

5. **`SlideMaker`/`ZettelMaker` 保留、不重寫**
   API 層是編排層（thin orchestration），把 CLI main() 的邏輯搬進來並呼叫既有類別；只對既有類別做 print → logging/callback 的最小修改。重寫核心類別風險高且無 spec 收益，否決。

6. **kb/chromadb lazy import**
   `sources.py` 與 `zettel.py` 中 kb 相關 import 移入函式內。`add_to_kb=False, embed=False` 時 chromadb 完全不載入（有測試斷言 `sys.modules`）。

## Risks / Trade-offs

- [搬移編排邏輯時行為漂移] → `tests/integration/test_cli_thin.py` 以 mock API 驗 CLI exit codes 與參數轉換；LLM 呼叫以 fixture mock 使核心測試可離線重複
- [print 改 logging 遺漏（含 `src/utils/model_monitor.py` 等間接相依）] → 測試以 `capsys` 斷言 API 呼叫期間 stdout 為空；grep 掃描核心路徑殘留 print
- [兩種 import 風格並存使新模組易踩雷] → `src/api/` 內部一律 `from utils.x import`（與 sys.path.insert 相容且 change 3 搬移時只改前綴）
- [Windows cp950 印 emoji 崩潰] → emoji 只存在 CLI 層，entry 統一 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`

## Migration Plan

實作採 TDD 順序：models/errors/progress（純新增）→ sources → slides → zettel → providers/prompts → CLI 薄殼化（最後一步，有回歸測試把關）。CLI 介面不變，無使用者遷移成本。回滾＝還原三支 CLI 腳本（API 層為純新增，不影響既有路徑）。

## Open Questions

- `ZettelRequest.cross_link` 依賴向量庫（chromadb）——`add_to_kb=False` 但 `cross_link=True` 的組合是否合法？決定：pydantic validator 禁止該組合，hint 說明需先入庫。
