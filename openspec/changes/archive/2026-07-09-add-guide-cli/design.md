# Design: add-guide-cli

## Context

系統已有 `SlideMaker.call_llm(prompt, provider=..., model=..., task_type=...)` 統一多供應商介面（含 NVIDIA），與 `list_options()` 單一真相來源。guide 只是在其上加一層「產生說明 → 送 LLM → 回建議」，不涉及生成流程本身。

## Goals / Non-Goals

**Goals:**
- 在任何 terminal（無 MCP client）以自然語言取得建議 CLI 指令
- 可指定要用哪個已設定的供應商
- 使用說明的風格清單與 list_options 同源，不重複維護
- 純建議、不自動執行（符合使用者選擇的「導出說明」語意）

**Non-Goals:**
- 不做 tool-calling agent（不自動調用 slides/zettel）
- 不做多輪 REPL（單次問答）
- 不做對話歷史 / session 管理

## Decisions

1. **重用 `call_llm`**：`suggest_command` 建 `SlideMaker(llm_provider=provider)` 後呼叫 `call_llm(prompt, model=..., provider=<明確或None>, task_type="guide")`。錯誤（RuntimeError / ValueError）轉 `ProviderUnavailableError`（hint 指向 `uv run setup`）——與既有 provider 錯誤慣例一致。

2. **使用說明用 jinja2 範本**：`resources/templates/prompts/usage_guide.jinja2` 描述骨架，渲染時注入 `list_options()` 的風格/詳細度/語言。骨架人工維護、清單自動同步。範本走 `resolve_resource`（cwd 覆蓋 > 套件內建），與其他模板一致；cwd 版與 resources 版由 test_resources 把關一致。

3. **NVIDIA 問答用輕量模型**：guide 是短問答，253B 太慢。`suggest_command` 內：`if provider == "nvidia" and not model: model = "meta/llama-3.1-8b-instruct"`。明確語意（guide 就是要快），不改動 slides/zettel 的 NVIDIA 分流。

4. **provider 驗證策略**：不預先跑 `check_providers()`（會全量打 API 拖慢）。直接嘗試 call_llm，失敗轉 ProviderUnavailableError。快、且錯誤訊息足夠。

5. **CLI 位置參數**：`guide [request]`，request 為選填位置參數。無 request → 印說明；有 request → suggest_command。`--provider` / `--model` 選填。

## Risks / Trade-offs

- [LLM 可能建議過時/錯誤參數] → 說明 prompt 明確列出合法 choices（來自 list_options + 固定參數清單）；輸出僅為建議，使用者確認後才執行
- [說明範本與實際 CLI 參數漂移] → 風格類清單自動同步；固定參數（--pdf/--style/--detail 等）人工維護，變動時同步更新範本（低頻）
- [guide task_type="guide" 對非 NVIDIA 無副作用] → call_llm 的 task_type 僅影響智能選擇與 NVIDIA 分流；guide 對其他 provider 無影響

## Migration Plan

純新增，無遷移。TDD：build_usage_guide（先）→ suggest_command（mock call_llm）→ CLI → 實測指定 provider → 範本兩份同步 → archive。
