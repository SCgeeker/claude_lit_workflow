# slide-generation Spec Delta

## ADDED Requirements

### Requirement: 可程式化投影片生成 API
系統 SHALL 提供 `generate_slides(request: SlideRequest, *, progress=None) -> SlideResult` 純 Python API。此 API MUST NOT 依賴 argparse、MUST NOT 呼叫 `sys.exit`、MUST NOT 直接寫入 stdout。

#### Scenario: 從 PDF 生成 Markdown 投影片
- **WHEN** 以存在的 PDF 路徑與 `output_format="markdown"` 呼叫 `generate_slides`（LLM 已設定或被 mock）
- **THEN** 回傳 `SlideResult`，其 `output_files` 含至少一個存在的 `.md` 檔案絕對路徑，`slide_count > 0`，且執行期間 stdout 無任何輸出

#### Scenario: 從主題（無 PDF）生成投影片
- **WHEN** 只提供 `topic` 呼叫 `generate_slides`
- **THEN** 系統以主題為內容來源生成投影片並回傳 `SlideResult`

#### Scenario: 內容來源互斥驗證
- **WHEN** 建構 `SlideRequest` 時同時提供 `pdf` 與 `url`
- **THEN** pydantic 驗證失敗並拋出 `ValidationError`

### Requirement: 生成選項驗證
`SlideRequest` MUST 以 enum 驗證 `style`（7 種學術風格）、`detail`（5 種詳細程度）、`language`（3 種語言），並以範圍限制 `slide_count`（3–60）。

#### Scenario: 無效風格被拒絕
- **WHEN** 以 `style="nonexistent_style"` 建構 `SlideRequest`
- **THEN** 拋出 `ValidationError`，錯誤訊息列出合法選項

#### Scenario: 預設值
- **WHEN** 只提供內容來源、不指定選項
- **THEN** `style=modern_academic`、`detail=standard`、`language=chinese`、`output_format=markdown`

### Requirement: 型別化錯誤
API MUST 以 `LitWorkflowError` 子類例外回報失敗，例外 MUST 帶有 `hint` 屬性（給使用者的修復建議）。

#### Scenario: PDF 不存在
- **WHEN** 以不存在的 PDF 路徑呼叫 `generate_slides`
- **THEN** 拋出 `SourceNotFoundError`（而非 `sys.exit` 或回傳錯誤碼），且 `hint` 非空

#### Scenario: 無可用 LLM 供應商
- **WHEN** 環境中沒有任何可用的 LLM 供應商時呼叫 `generate_slides`
- **THEN** 拋出 `ProviderUnavailableError`，`hint` 指引執行 `uv run setup`

### Requirement: 進度回報
API SHALL 接受選填的 `progress` callback；生成流程 MUST 依序發出 `ProgressEvent`，其 `stage` 涵蓋至少 `extract`（有檔案來源時）、`prompt`、`llm`、`write`。

#### Scenario: callback 收到階段事件
- **WHEN** 以 progress callback 呼叫 `generate_slides`（LLM 被 mock）
- **THEN** callback 依序收到 stage 為 `prompt`、`llm`、`write` 的事件，每個事件含非空 `message`

#### Scenario: 無 callback 時靜默
- **WHEN** 不提供 progress callback 呼叫 `generate_slides`
- **THEN** 流程正常完成且 stdout 無輸出（核心層訊息只進 logging）

### Requirement: 投影片 prompt 渲染 API
系統 SHALL 提供 `render_slides_prompt(request: SlideRequest) -> str`，回傳以 jinja2 模板渲染完成的完整 LLM 提示詞。

#### Scenario: 渲染含論文內容與風格指示
- **WHEN** 以含 PDF 來源的 request 呼叫 `render_slides_prompt`
- **THEN** 回傳字串包含抽取的論文內容片段與所選風格、詳細度、語言的指示文字
