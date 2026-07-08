# Tasks: extract-core-api

## 1. API 基礎結構（models / errors / progress）

- [x] 1.1 建立 `src/api/` 套件骨架（`__init__.py` 公開介面 re-export）
- [x] 1.2 撰寫失敗測試 `tests/unit/test_api_models.py`：來源互斥、slide_count 範圍、enum 錯值、預設值、cross_link 需 add_to_kb（TDD red）
- [x] 1.3 實作 `src/api/models.py`：SlideRequest/SlideResult/ZettelRequest/ZettelResult/ProviderStatus/ProviderReport/OptionCatalog（pydantic v2 + StrEnum + model_validator）
- [x] 1.4 實作 `src/api/errors.py`（LitWorkflowError 含 hint + 六個子類）與 `src/api/progress.py`（ProgressEvent + ProgressCallback）

## 2. 內容來源解析（共用）

- [x] 2.1 撰寫失敗測試：resolve_source 處理 pdf/url/topic/from_kb 與不存在來源（SourceNotFoundError）
- [x] 2.2 實作 `src/api/sources.py`：從兩支 CLI 抽出來源解析；kb import 改函式內 lazy import

## 3. slides API

- [x] 3.1 準備 fixture `tests/fixtures/sample_slides_output.txt`；撰寫失敗測試 `tests/unit/test_api_slides.py`（monkeypatch `SlideMaker.call_llm`；驗 SlideResult 欄位、輸出檔存在、progress 事件序列、capsys 斷言 stdout 為空）
- [x] 3.2 實作 `src/api/slides.py`：`generate_slides`，搬移 make_slides.py 編排邏輯
- [x] 3.3 `src/generators/slide_maker.py` 所有 print 改 logging / progress callback（含 `src/utils/model_monitor.py` 等間接路徑；grep 驗證無殘留）
- [x] 3.4 實作 `src/api/prompts.py::render_slides_prompt`（重用 `SlideMaker.generate_prompt`）+ 測試

## 4. zettel API

- [x] 4.1 準備 fixture `tests/fixtures/sample_zettel_output.txt`（12 張 `===CARD:===`）；撰寫失敗測試 `tests/unit/test_api_zettel.py`（卡片檔數、輸出結構、cite_key 規則、CiteKeyMissingError、零卡片 LLMGenerationError、add_to_kb=False 不觸碰 SQLite 且不載入 chromadb、progress 序列）
- [x] 4.2 實作 `src/api/zettel.py`：`generate_zettel`，搬移 generate_zettel.py 的 prompt 渲染、cite_key 解析、`_query_related_cards`、入庫/嵌入（全部 lazy import）
- [x] 4.3 `src/generators/zettel_maker.py` print 改 logging / callback
- [x] 4.4 實作 `render_zettel_prompt` + 測試

## 5. providers API

- [x] 5.1 撰寫失敗測試 `tests/unit/test_api_providers.py`：mock 各 SDK 驗 available/recommended、佔位 key 視為未設定、list_options 完整性（7/5/3 項）
- [x] 5.2 實作 `src/api/providers.py`：`check_providers`（搬自 setup.py 的 test_* 函式）、`list_options`（讀 `templates/styles/academic_styles.yaml`）

## 6. CLI 薄殼化與回歸

- [x] 6.1 撰寫回歸測試 `tests/integration/test_cli_thin.py`：mock API 層驗三支 CLI 的參數轉換與 exit codes
- [x] 6.2 `make_slides.py` 薄殼化（argparse → SlideRequest → API；emoji 呈現留在 CLI；stdout reconfigure utf-8）
- [x] 6.3 `generate_zettel.py` 薄殼化（同上）
- [x] 6.4 `setup.py` 薄殼化（呈現 `check_providers()` 結果）
- [x] 6.5 全測試綠 + 手動冒煙：`uv run slides --list-options`、`uv run setup`、`uv run zettel --help` 行為與現況一致
