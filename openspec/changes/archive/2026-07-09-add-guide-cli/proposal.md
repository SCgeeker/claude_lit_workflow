# Proposal: add-guide-cli

## Why

工具的 CLI 參數多（7 風格、5 詳細度、3 語言、多 provider、NVIDIA 任務分流），新使用者需查 docs 才知道怎麼下正確指令。提供一個 `uv run guide`，可在任何 terminal（不需 Claude Code / MCP client）導出完整的「工具使用說明」給任意 LLM 參考，或直接指定一個可用的 LLM，用自然語言描述需求、由該 LLM 回覆建議的 CLI 指令——降低上手門檻，且讓使用者能挑選要用哪個已設定的供應商來協助。

## What Changes

- 新增 `uv run guide` CLI 入口與 `claude_lit/api/guide.py` 核心：
  - `build_usage_guide() -> str`：組出完整工具使用說明（slides / zettel 用法、參數、風格/詳細度/語言清單、NVIDIA 分流、範例）；風格等清單來自 `list_options()`（單一真相來源）
  - `suggest_command(request_text, *, provider="auto", model=None) -> GuideResult`：把「使用說明 + 使用者需求」送給指定的可用 LLM（重用 `SlideMaker.call_llm` 的多 provider 分派），回傳建議的 CLI 指令與所用供應商
- `uv run guide`（無參數）→ 印出使用說明（可貼到任何 LLM 對話）
- `uv run guide "<需求>" [--provider X] [--model M]` → 用指定供應商回覆建議指令（單次問答；不自動執行）；供應商不可用時報錯並提示 `uv run setup`
- guide 對 NVIDIA 供應商未指定 model 時預設輕量 `meta/llama-3.1-8b-instruct`（問答不需 253B）
- 使用說明骨架以 jinja2 範本 `resources/templates/prompts/usage_guide.jinja2` 維護（cwd 覆蓋層 + 套件內建兩份）
- `pyproject.toml` 新增 `guide` entry point

## Capabilities

### New Capabilities

- `usage-guide`: 工具使用說明的導出，以及「指定 LLM + 自然語言需求 → 建議 CLI 指令」的單次問答行為

### Modified Capabilities

（無）

## Impact

- **新增**：`src/claude_lit/api/guide.py`、`src/claude_lit/cli/guide.py`、`resources/templates/prompts/usage_guide.jinja2`（+ cwd 版 `templates/prompts/usage_guide.jinja2`）、`tests/unit/test_api_guide.py`
- **修改**：`pyproject.toml`（guide entry）、`api/__init__.py`（re-export）、README / CLAUDE.md（guide 說明）
- **相依**：無新增（重用 call_llm、list_options、jinja2）
- **相容性**：純新增入口，既有 CLI / API / MCP 不受影響
