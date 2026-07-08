# zettel-generation Spec Delta

## ADDED Requirements

### Requirement: 模板資源解析
Zettel 卡片生成使用的 prompt 模板、卡片模板與索引模板 MUST 透過資源解析機制載入：明確傳入路徑 > cwd 使用者檔 > 套件內建（importlib.resources）。

#### Scenario: 安裝後無原始碼樹仍可生成
- **WHEN** 於 wheel 安裝環境（無 repo 原始碼樹）呼叫 `generate_zettel`（LLM 被 mock）
- **THEN** zettelkasten 模板與卡片/索引模板從套件內資源載入，卡片輸出正常
