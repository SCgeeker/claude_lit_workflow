# Proposal: add-nvidia-provider

## Why

系統目前支援 Google / OpenAI / Anthropic / Ollama / OpenRouter，但缺少 NVIDIA NIM（`integrate.api.nvidia.com/v1`）。NVIDIA NIM 以 OpenAI 相容協定提供多個大型模型，其中 `nvidia/llama-3.1-nemotron-ultra-253b-v1`（253B，reasoning-optimized）專為學術寫作/文獻任務調校，`qwen/qwen3-next-80b-a3b-thinking`（顯式思考鏈）適合 Zettel 卡片的深度概念提取——正切合本工具的兩大生成情境。加入後使用者可用 `--llm-provider nvidia` 取得更高品質的學術生成，且此 provider 對任何串接本 MCP 的平台同樣可用。

## What Changes

- 新增 `SlideMaker.call_nvidia()`：打 NVIDIA NIM 的 OpenAI 相容 endpoint（`Bearer $NVIDIA_API_KEY`），實作仿既有 `call_openrouter`
- `call_llm` 分派與 `_detect_available_providers` 新增 `nvidia`（偵測 `NVIDIA_API_KEY`）
- **任務分流預設模型**：`--llm-provider nvidia` 未指定 `--model` 時，slides 情境預設 `nvidia/llama-3.1-nemotron-ultra-253b-v1`、zettel 情境預設 `qwen/qwen3-next-80b-a3b-thinking`（依 call_llm 的 task_type 決定）
- `providers.py` 新增 `_check_nvidia()`，納入 `check_providers()` 偵測清單與 `check_setup` / `uv run setup`
- CLI `--llm-provider` choices（slides.py / zettel.py）新增 `nvidia`
- API 層（slides / zettel）傳遞 `task_type` 給 `call_llm`，使任務分流生效
- `.env.example` 新增 `NVIDIA_API_KEY` 說明；`model_selection.yaml`（cwd + 套件內建兩份）新增 NVIDIA 模型條目

## Capabilities

### New Capabilities

（無——延伸既有 provider-setup capability）

### Modified Capabilities

- `provider-setup`: 「供應商偵測 API」requirement 的偵測清單新增 NVIDIA NIM；並新增「NVIDIA NIM 供應商生成」requirement（OpenAI 相容呼叫、任務分流預設模型、金鑰隔離）

## Impact

- **修改**：`src/claude_lit/generators/slide_maker.py`（call_nvidia、分派、偵測）、`src/claude_lit/api/providers.py`（_check_nvidia）、`src/claude_lit/api/slides.py` 與 `api/zettel.py`（傳 task_type）、`cli/slides.py`、`cli/zettel.py`（choices）
- **config**：`.env.example`、`config/model_selection.yaml` + `src/claude_lit/resources/config/model_selection.yaml`（兩份同步，test_resources 把關）
- **測試**：`tests/unit/test_api_providers.py`（_check_nvidia）、slide_maker 的 call_nvidia 與任務分流測試
- **相依**：無新增（用既有 `requests`）
- **相容性**：純新增 provider，既有 provider 與 CLI 行為不變；MCP `provider` 參數為自由字串，自動支援 `"nvidia"`
