# cli Spec Delta

## ADDED Requirements

### Requirement: 媒體類型與文字來源旗標
`uv run slides` 與 `uv run zettel` MUST 支援 `--media {paper,lecture,podcast,blog,textbook,monograph}`（預設 `paper`）、`--text PATH`、`--chapter RANGE`、`--meta KEY=VALUE`（可重複，組成 `source_meta`）、`--keep-fillers`。旗標 MUST 只透傳至核心 Request，CLI 不含媒體邏輯。`--help` MUST 列出媒體類型與其說明（來源為 `media_profiles.yaml`）。

#### Scenario: 旗標透傳
- **WHEN** 執行 `uv run zettel --text ep42.srt --media podcast --meta show=科學新聞 --meta episode=EP42`
- **THEN** 核心 API 收到 `media_type=podcast`、`text=ep42.srt`、`source_meta={"show": "科學新聞", "episode": "EP42"}`

#### Scenario: 未指定 --media 行為不變
- **WHEN** 執行 `uv run slides --pdf paper.pdf`
- **THEN** 核心 API 收到 `media_type=paper`
