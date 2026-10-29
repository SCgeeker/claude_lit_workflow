# slide-generation Spec Delta

## ADDED Requirements

### Requirement: 依媒體類型選擇投影片模板
系統 MUST 接受 `media_type` 參數（`paper`、`lecture`、`podcast`、`blog`、`textbook`、`monograph`，預設 `paper`）。`media_type=paper` 時 MUST 使用既有 `journal_club_template.jinja2`，渲染結果與本 change 之前逐字相同。其他值 MUST 使用 `media_slides_template.jinja2`，並注入 `media_profiles.yaml` 中對應 profile 的 `reading_stance`、`slide_structure`、`slide_rules`。兩種模板的輸出協定（`===標題頁===`、`===投影片N===`、`標題：`、`內容：`、`•`）MUST 相同，使既有解析器不需修改。

#### Scenario: 預設為論文且零回歸
- **WHEN** 以未指定 `media_type` 的 SlideRequest 渲染提示詞
- **THEN** 渲染結果與使用 `journal_club_template.jinja2` 的既有行為逐字相同

#### Scenario: 逐字稿使用講演骨架
- **WHEN** 以 `media_type=lecture` 渲染提示詞
- **THEN** 提示詞包含 lecture profile 的 `slide_structure` 各項，且不包含「研究背景、研究方法、主要發現」的論文架構要求

#### Scenario: 未知媒體類型被拒
- **WHEN** 以 `media_type=novel` 建立 SlideRequest
- **THEN** 驗證失敗並列出可用的媒體類型

### Requirement: 文字來源
SlideRequest MUST 接受 `text` 來源（`.txt`、`.md`、`.srt`、`.vtt`），與 `pdf`、`url`、`from_kb` 互斥。SRT/VTT MUST 在送入 LLM 前移除序號與時間碼列，並依 profile 的 `preprocess` 插入獨立成行的時間標記。

#### Scenario: SRT 前處理
- **WHEN** 以 `.srt` 檔作為 `text` 來源生成投影片
- **THEN** 送入 LLM 的內容不含 SRT 序號與 `-->` 時間碼列，且含 `[hh:mm:ss]` 獨立行標記
