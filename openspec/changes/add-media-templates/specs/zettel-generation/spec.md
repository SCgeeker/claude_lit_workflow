# zettel-generation Spec Delta

## ADDED Requirements

### Requirement: 依媒體類型選擇卡片模板
系統 MUST 接受 `media_type` 參數（同 slide-generation）。`media_type=paper` 時 MUST 使用既有 `zettelkasten_template.jinja2`，結果與本 change 之前逐字相同。其他值 MUST 使用 `media_zettel_template.jinja2`，注入 profile 的 `reading_stance`、`card_type_weights`、`core_rule`、`location_format`、`extra_card_rules`，以及依 `citation_format` 與 `source_meta` 渲染的 `citation`。輸出協定（`===CARD: {id}===` 與各欄位標籤）MUST 與既有模板相同。

#### Scenario: Podcast 卡片類型
- **WHEN** 以 `media_type=podcast` 渲染提示詞
- **THEN** `類型:` 選項為 `claim|concept|example|question`，且提示詞要求核心句不可跨講者拼接

#### Scenario: claim 卡可被解析與 grounding
- **WHEN** LLM 輸出 `類型: claim` 的卡片，且其核心句逐字出現在逐字稿中
- **THEN** 解析後 `card_type == "claim"`，grounding verdict 為 `EXACT`，卡片被保留

#### Scenario: citation metadata 缺漏不阻斷
- **WHEN** `source_meta` 缺少 `citation_format` 所需欄位（如 `episode`）
- **THEN** 缺漏欄位以空字串渲染，生成照常進行，且 citation 仍含 `|`

### Requirement: CJK 政策依來源類型決定
grounding gate 對「含 Han 字且定位不到」的核心 MUST 依來源決定處置：PDF 來源 MUST 隔離至 `_needs_cjk_check/`（現行行為）；文字來源（txt/md/srt/vtt/epub）MUST 抹除（erase）。

#### Scenario: 文字來源中文杜撰被抹除
- **WHEN** 以 `.txt` 來源生成，某卡片中文核心在原文中定位不到
- **THEN** 該卡片被抹除，不寫入 `_needs_cjk_check/`，計入 `erased`

#### Scenario: PDF 來源維持隔離
- **WHEN** 以 PDF 來源生成，某卡片中文核心定位不到
- **THEN** 該卡片寫入 `_needs_cjk_check/`，計入 `flagged`

### Requirement: 逐字稿 sidecar 記錄時間戳
來源為 SRT/VTT 時，每張存活卡片的 `{card_id}.grounding.json` MUST 含 `timestamp`（`hh:mm:ss`），由 grounding 的 `char_offset` 經字幕時間軸對照表換算，MUST NOT 取自 LLM 填寫的 `位置` 欄。

#### Scenario: 時間戳回映
- **WHEN** 以 `.srt` 來源生成，某卡片核心位於第 12 分 30 秒的字幕段
- **THEN** 該卡片 sidecar 的 `timestamp` 為 `00:12:30`（依該段起始時間）

### Requirement: 長篇來源分章處理
`media_type` 為 `textbook` 或 `monograph` 時，系統 MUST 接受 `chapter` 參數（單章 `3` 或範圍 `3-5`），只抽取指定章節；cite_key MUST 加 `-chNN` 後綴（如 `Smith-2020-ch03`），使同書不同章的卡片 ID 不衝突。抽取後內容超過上限時 MUST 回報警告。

#### Scenario: 章節 cite_key
- **WHEN** 以 `media_type=textbook`、`cite_key=Smith-2020`、`chapter=3` 生成
- **THEN** 卡片 ID 為 `Smith-2020-ch03-001` 起連續編號

### Requirement: 改寫核心時保留原文字元
grounding gate 以原文 span 修正核心（僅差空白／換行連字）時，寫入卡片的核心 MUST 只接合換行連字並塌陷空白，MUST NOT 套用 NFKC 或引號正規化；`normalize()` 僅用於比對。

#### Scenario: 中文全形標點保留
- **WHEN** 卡片核心「我認為注意力其實是一種預測，而不是一盞探照燈。」逐字出現在原文
- **THEN** 寫入卡片的核心保留全形「，」與「。」，不被轉為半形
