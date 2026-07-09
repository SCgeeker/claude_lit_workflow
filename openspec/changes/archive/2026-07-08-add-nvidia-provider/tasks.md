# Tasks: add-nvidia-provider

## 1. 偵測（providers.py）

- [x] 1.1 失敗測試 `test_api_providers.py`：`_check_nvidia` 佔位/未設定→不可用；有效 key + mock HTTP→可用；`check_providers()` 清單含 nvidia
- [x] 1.2 實作 `_check_nvidia()`（仿 `_check_google`，偵測用 `meta/llama-3.1-8b-instruct`，可經 `NVIDIA_TEST_MODEL` 覆寫）；加入 `PROVIDERS`（`PRIORITY` 不含 nvidia）

## 2. 生成與任務分流（slide_maker.py）

- [x] 2.1 失敗測試：`call_nvidia` 打正確 endpoint、帶 Bearer、缺 key 拋 ValueError（mock requests）
- [x] 2.2 失敗測試：任務分流——`call_llm(provider="nvidia", task_type="slides")`→nemotron；`task_type="zettelkasten"`→qwen thinking；明確 model 覆寫分流
- [x] 2.3 實作 `call_nvidia()`、模組常數 `NVIDIA_SLIDES_MODEL` / `NVIDIA_ZETTEL_MODEL`（可環境覆寫）、`_nvidia_default_model(task_type)`
- [x] 2.4 `call_llm` 加 nvidia 分派；`_detect_available_providers` 加 `NVIDIA_API_KEY`

## 3. API 與 CLI 接線

- [x] 3.1 `api/slides.py` 傳 `task_type="slides"`、`api/zettel.py` 傳 `task_type="zettelkasten"` 給 call_llm（含測試驗證分流生效）
- [x] 3.2 `cli/slides.py`、`cli/zettel.py` 的 `--llm-provider` choices 加 `nvidia`

## 4. config、文件、驗收

- [x] 4.1 `.env.example` 加 `NVIDIA_API_KEY`；`model_selection.yaml` 兩份加 NVIDIA 條目（test_resources 一致）
- [x] 4.2 README / CLAUDE.md 多 LLM 表格加 NVIDIA（附大模型 timeout 提醒）
- [x] 4.3 全套件綠；實測 `uv run setup` 顯示 NVIDIA 可用；`uv run slides --llm-provider nvidia`（或 mock）冒煙
- [x] 4.4 `openspec archive add-nvidia-provider`
