# Tasks: add-guide-cli

## 1. 使用說明生成

- [x] 1.1 失敗測試 `tests/unit/test_api_guide.py`：`build_usage_guide()` 含 slides/zettel/modern_academic/standard/範例；風格清單與 list_options 一致
- [x] 1.2 建立範本 `resources/templates/prompts/usage_guide.jinja2`（+ cwd 版 `templates/prompts/usage_guide.jinja2`，兩份一致）
- [x] 1.3 實作 `api/guide.py::build_usage_guide()`（resolve_resource 載範本 + 注入 list_options）

## 2. 指定 LLM 建議指令

- [x] 2.1 失敗測試：`suggest_command` mock call_llm→提示含說明與需求、provider_used 正確；provider 不可用→ProviderUnavailableError；nvidia 無 model→輕量模型
- [x] 2.2 實作 `GuideResult` model 與 `suggest_command()`（重用 call_llm、錯誤轉 ProviderUnavailableError、nvidia 預設 8b）
- [x] 2.3 `api/__init__.py` re-export build_usage_guide / suggest_command / GuideResult

## 3. CLI 與收尾

- [x] 3.1 失敗測試 `tests/integration/test_cli_thin.py`：guide 無參數印說明 exit 0；帶需求 mock suggest_command exit 0；provider 不可用 exit 1
- [x] 3.2 實作 `cli/guide.py`（位置參數 request、--provider、--model、UTF-8 防護）；pyproject 加 `guide` entry
- [x] 3.3 全套件綠（含 test_resources 兩份範本一致）；實測 `uv run guide`（印說明）與 `uv run guide "需求" --provider <可用>`
- [x] 3.4 README / CLAUDE.md 加 guide 說明；`openspec archive add-guide-cli`
