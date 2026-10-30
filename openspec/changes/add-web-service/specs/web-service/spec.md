# web-service Specification

## ADDED Requirements

### Requirement: 非同步 job API
服務 MUST 以 job 處理生成請求：`POST /api/jobs` 接受上傳檔或 URL 與參數，驗證通過後 MUST 立即回傳 `202` 與 `job_id`，生成在背景執行。參數 MUST 以核心 API 的 `SlideRequest` / `ZettelRequest` 驗證，驗證失敗 MUST 回傳 `422` 與欄位錯誤，且不建立 job。`GET /api/jobs/{id}` MUST 回傳狀態（`queued`、`running`、`succeeded`、`failed`、`cancelled`）、結果摘要與錯誤 `hint`。

#### Scenario: 建立投影片 job
- **WHEN** 以有效 PDF 與 `{"kinds": ["slides"], "style": "teaching"}` 呼叫 `POST /api/jobs`
- **THEN** 回傳 `202` 與 `job_id`，之後 `GET /api/jobs/{id}` 最終為 `succeeded`，結果含 `slide_count` 與輸出檔清單

#### Scenario: 參數非法不建立 job
- **WHEN** 以 `{"kinds": ["slides"], "slide_count": 500}` 呼叫
- **THEN** 回傳 `422`，且 job 目錄未被建立

#### Scenario: 生成失敗保留修復提示
- **WHEN** job 執行時核心 API 拋出含 `hint` 的 `LitWorkflowError`
- **THEN** job 狀態為 `failed`，回應含錯誤訊息與 `hint`，服務行程持續運作

### Requirement: 進度串流
`GET /api/jobs/{id}/events` MUST 以 Server-Sent Events 推送核心 API 的 `ProgressEvent`，並在 job 結束時推送終止事件。client 中途連線時 MUST 先回放該 job 已發生的事件。

#### Scenario: 中途連線回放
- **WHEN** job 已發出兩個進度事件後 client 才連上 events 端點
- **THEN** client 先收到這兩個事件，再收到後續事件與終止事件

### Requirement: job 隔離
每個 job MUST 使用獨立工作目錄存放上傳檔與輸出，MUST NOT 寫入服務行程 cwd 的 `output/`。job 的模板覆蓋檔 MUST 透過 per-job overlay 生效，MUST NOT 影響同時執行的其他 job。

#### Scenario: 並行 job 各用各的覆蓋檔
- **WHEN** 兩個 job 同時執行，job A 上傳自訂 `custom_slides.md`，job B 未上傳
- **THEN** 只有 job A 的提示詞含該自訂內容

### Requirement: 提示詞不得改寫輸出協定
使用者輸入的提示詞 MUST 只以 `custom_requirements` 注入模板既有的附加需求區塊，且長度 MUST 受上限限制（預設 2000 字元）；模板的輸出格式區塊 MUST NOT 因提示詞而被移除或替換。

#### Scenario: 提示詞超長
- **WHEN** `custom_requirements` 超過上限
- **THEN** 回傳 `422`，不建立 job

### Requirement: 驗證與金鑰隔離
所有 `/api/*` 與 `/mcp` 端點（`/api/health` 除外）MUST 要求有效的 bearer token 或通過反向代理驗證。服務綁定非 localhost 位址且未設定任何驗證時 MUST 拒絕啟動。LLM API key MUST NOT 出現在任何 API 回應、SSE 事件、job 檔案或錯誤訊息中。

#### Scenario: 未帶 token
- **WHEN** 未帶 token 呼叫 `POST /api/jobs`
- **THEN** 回傳 `401`

#### Scenario: 公開綁定未設驗證
- **WHEN** 以 `--host 0.0.0.0` 啟動且未設定 `WEB_API_TOKEN` 或反向代理驗證旗標
- **THEN** 服務拒絕啟動並提示設定方式

### Requirement: 上傳與下載邊界
上傳 MUST 檢查大小上限（預設 50 MB）與類型白名單（副檔名與檔頭），超限回傳 `413`、類型不符回傳 `415`。上傳檔 MUST 以 job 內固定名稱儲存，不使用使用者提供的檔名組路徑。下載端點 MUST 只允許 job 目錄內的檔案，指向其外的路徑（含 `..`）MUST 回傳 `404` 且不讀取檔案。

#### Scenario: 下載路徑穿越
- **WHEN** 呼叫 `GET /api/jobs/{id}/files/../../.env`
- **THEN** 回傳 `404`，檔案內容未被讀取

### Requirement: 結果可攜回筆記 App
`GET /api/jobs/{id}/download` MUST 回傳 zip，目錄結構與本機 CLI 的 `output/` 相同（`slides/`、`zettelkasten_notes/…/zettel_cards/`，含 grounding sidecar 與 `_needs_cjk_check/`）。

#### Scenario: zip 結構
- **WHEN** 下載一個 `kinds=["slides","zettel"]` 的成功 job
- **THEN** zip 內含 `slides/{來源檔名}_{style}_{date}.md` 與 `zettelkasten_notes/zettel_{cite_key}_{date}/` 下的卡片

### Requirement: 資料保留
job 目錄 MUST 在保留期限（預設 7 天，可設定）到期後刪除，包含上傳的原始檔。

#### Scenario: 過期清理
- **WHEN** 清理程序執行時某 job 完成時間早於保留期限
- **THEN** 該 job 目錄被刪除，`GET /api/jobs/{id}` 回傳 `404`

### Requirement: 自然語言參數提案
`POST /api/plan` MUST 以 LLM 將自然語言需求轉為參數提案並回傳；提案 MUST 只包含通過驗證的欄位（值不在可用選項內者剔除並列入 `warnings`），且 MUST NOT 建立 job 或執行生成。供應商無法呼叫時 MUST 回傳 `503` 與修復提示。

#### Scenario: 非法值被剔除
- **WHEN** LLM 回覆的提案含 `style: "fancy"` 與合法的 `media_type: "lecture"`
- **THEN** 回傳的 `params` 只含 `media_type`，`warnings` 說明 `fancy` 不是可用選項
