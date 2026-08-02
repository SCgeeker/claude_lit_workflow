# cli Spec Delta

## ADDED Requirements

### Requirement: zettel CLI grounding 開關
`uv run zettel` MUST 預設啟用 grounding gate（對應 `ZettelRequest.ground=True`），並 MUST 提供 `--no-ground` 旗標關閉它（供批量重跑、除錯等情境）。旗標僅切換 `request.ground`，不改變其他行為。

#### Scenario: 預設啟用 grounding
- **WHEN** 執行 `uv run zettel --pdf paper.pdf`（未帶 `--no-ground`）
- **THEN** 傳入核心 API 的 `ZettelRequest.ground` 為 True

#### Scenario: --no-ground 關閉 grounding
- **WHEN** 執行 `uv run zettel --pdf paper.pdf --no-ground`
- **THEN** 傳入核心 API 的 `ZettelRequest.ground` 為 False，gate 不抹除任何卡片
