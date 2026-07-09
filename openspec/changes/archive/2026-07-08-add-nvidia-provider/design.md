# Design: add-nvidia-provider

## Context

NVIDIA NIM 是 OpenAI 相容的 REST 服務。系統已有 `call_openrouter`（同為 OpenAI 相容、以 `requests.post` 實作），可直接作為 `call_nvidia` 的範本。provider 分派、偵測、CLI choices、config 的擴充點在 change extract-core-api / package-cli 後皆已就緒。

## Goals / Non-Goals

**Goals:**
- 以最小、與既有模式一致的方式加入 nvidia provider
- 任務分流：slides→nemotron-ultra-253b、zettel→qwen3-next-thinking，以確定性程式邏輯實現（非 LLM 判斷）
- 金鑰隔離、可離線測試（HTTP mock）

**Non-Goals:**
- 不做 model_selection.yaml 的 auto 智能選擇整合（provider=auto 時不自動選 NVIDIA，避免高成本 253B 被意外選中）；NVIDIA 為使用者明確選擇
- 不加 vision / embedding 模型（本工具無此需求）
- 不改 request/result schema（provider 本就是自由字串）

## Decisions

1. **`call_nvidia` 仿 `call_openrouter`**：`requests.post` 到 `https://integrate.api.nvidia.com/v1/chat/completions`，headers `Authorization: Bearer $NVIDIA_API_KEY`，body 為 OpenAI chat schema（`model` / `messages` / `max_tokens`）。缺 key 拋 `ValueError`，逾時/錯誤拋 `RuntimeError`——與既有 provider 錯誤慣例一致。

2. **任務分流以 task_type 驅動**：`call_llm` 已有 `task_type` 參數但 API 層目前未傳。改為：
   - `api/slides.py` 呼叫 `call_llm(..., task_type="slides")`
   - `api/zettel.py` 呼叫 `call_llm(..., task_type="zettelkasten")`
   - `call_llm` 的 nvidia 分支：`used_model = actual_model or _nvidia_default_model(task_type)`
   - `_nvidia_default_model(task_type)`：task_type 含 "zettel" → qwen thinking；否則 → nemotron ultra
   模型名集中為模組常數 `NVIDIA_SLIDES_MODEL` / `NVIDIA_ZETTEL_MODEL`，可經 `NVIDIA_SLIDES_MODEL` / `NVIDIA_ZETTEL_MODEL` 環境變數覆寫（沿用 Gemini 修復的可覆寫模式，避免模型更名時需改碼）。

3. **`_check_nvidia`**：仿 `_check_google`——送最小 chat 請求驗證連線；佔位判斷用 `nvapi-your` / `your-`。偵測用模型用輕量的 `meta/llama-3.1-8b-instruct`（253B 偵測太慢/貴），可經 `NVIDIA_TEST_MODEL` 覆寫。加入 `PROVIDERS` 清單；`PRIORITY` 不含 nvidia（成本考量，不設為自動建議首選；有其他可用者時不主動推薦 NVIDIA）。

4. **config 兩份同步**：`model_selection.yaml` 加 NVIDIA 條目（僅文件性/供未來 auto 用，priority 低）；cwd 版與 `resources/` 版必須一致（test_resources 斷言）。

## Risks / Trade-offs

- [253B 模型回應慢，可能超過 client timeout] → 生成類 MCP tool 已有 progress notification + 300s timeout；README 註明 NVIDIA 大模型建議加大 client timeout
- [_check_nvidia 真打 API 增加 setup 延遲] → 用 8B 輕量模型偵測；與其他 provider 偵測一致（都送最小請求）
- [PRIORITY 是否含 nvidia] → 不含：避免 auto 情境下 253B 成為預設建議造成非預期成本；使用者需明確 `--llm-provider nvidia`

## Migration Plan

純新增 provider，無遷移。回滾＝移除 call_nvidia / _check_nvidia / 分派分支與 config 條目。TDD 順序：_check_nvidia（先）→ call_nvidia + 任務分流（mock HTTP）→ CLI/API 接線 → 實測 NVIDIA_API_KEY 連線 → config/文件。
