# Proposal: extract-core-api

## Why

slides / zettel / setup 三支 CLI 的編排邏輯（來源解析、prompt 渲染、LLM 呼叫、跨論文連結、入庫）散落在根目錄腳本的 `main()` 中，且核心層以 `print()` 直接輸出，導致無法被程式化呼叫。專案即將新增 MCP server（任何 LLM 平台皆可串接），MCP 與 CLI 必須共用同一層可呼叫的 Python API，且 MCP stdio 傳輸不容許 stdout 被污染——此重構是後續兩個 change（add-mcp-server、package-cli）的前置條件。

## What Changes

- 新增 `src/api/` 套件：以 pydantic v2 Request/Result models 為介面的核心 API
  - `generate_slides(request, *, progress=None) -> SlideResult`
  - `generate_zettel(request, *, progress=None) -> ZettelResult`
  - `check_providers() -> ProviderReport`、`list_options() -> OptionCatalog`
  - `render_slides_prompt(request) -> str`、`render_zettel_prompt(request) -> str`
- 新增型別化例外階層（`LitWorkflowError` 基底，含 `hint` 修復建議屬性），取代核心層的 `sys.exit` / 裸回傳
- 新增 `ProgressEvent` callback 機制：核心層進度回報與呈現層解耦（CLI 印 emoji、未來 MCP 轉 progress notification）
- `SlideMaker` / `ZettelMaker` 內部所有 `print()` 改為 logging 或 progress callback（stdout 淨空）
- 知識庫 / chromadb import 改為函式內 lazy import（無 kb 需求時不載入重相依）
- 三支 CLI（`make_slides.py`、`generate_zettel.py`、`setup.py`）薄殼化：argparse → Request model → API 呼叫 → 呈現結果；CLI 對外行為與 exit codes 不變
- CLI entry 加 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`（Windows cp950 防護）

## Capabilities

### New Capabilities

- `slide-generation`: 可程式化投影片生成 API 的行為契約——內容來源（pdf/url/topic/kb）、風格/詳細度/語言選項、輸出格式、進度回報、型別化錯誤
- `zettel-generation`: 可程式化 Zettelkasten 卡片生成 API 的行為契約——cite_key 解析規則、卡片解析與輸出結構、可選入庫/嵌入/跨論文連結、進度回報、型別化錯誤
- `provider-setup`: LLM 供應商偵測與選項列舉 API——各供應商可用性檢查、建議供應商、風格/詳細度/語言目錄

### Modified Capabilities

（無——本 change 建立首批 specs）

## Impact

- **新增**：`src/api/`（models、errors、progress、sources、slides、zettel、providers、prompts）
- **修改**：`make_slides.py`、`generate_zettel.py`、`setup.py`（薄殼化）；`src/generators/slide_maker.py`、`src/generators/zettel_maker.py`（print → logging/callback、progress 注入）
- **測試**：新增 `tests/unit/test_api_*.py`、`tests/integration/test_cli_thin.py`、`tests/fixtures/sample_*_output.txt`
- **相依**：無新增（pydantic 已在 pyproject 中）
- **實作中擴充（stdout 淨空的既有債）**：移除散布各模組在 import 時劫持 `sys.stdout/stderr` 的程式碼（`session_organizer`、`batch_processor`、`kb_manager_agent`、`zettel_format_fixer`、`zotero_sync`、8 個舊測試檔、2 支批次 CLI）——此劫持會關閉 pytest capture 與未來 MCP stdio 的底層串流；`utils/logger.py` console handler 改輸出 stderr；pyproject 新增 pytest `testpaths = ["tests"]`；2 個依賴即時 API / 暫停功能的舊測試標記 skip 並註明原因
- **相容性**：CLI 對外介面（參數、輸出檔路徑規格、exit codes）不變；`uv run slides/zettel/setup` 用法完全相同
