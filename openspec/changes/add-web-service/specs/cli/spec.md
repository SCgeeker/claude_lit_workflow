# cli Spec Delta

## ADDED Requirements

### Requirement: 網頁服務入口
系統 SHALL 提供 `uv run web` 入口（需安裝 `web` extra），支援 `--host`（預設 `127.0.0.1`）、`--port`、`--workers`（並行 job 上限）。未安裝 `web` extra 時 MUST 以提示安裝方式的錯誤訊息結束，而非 traceback。

#### Scenario: 未安裝 extra
- **WHEN** 未安裝 `web` extra 時執行 `uv run web`
- **THEN** 輸出提示 `uv sync --extra web` 的錯誤訊息並以非零碼結束

### Requirement: per-job 資源覆蓋層
資源解析 MUST 支援以 contextvar 設定的 overlay 目錄，解析順序為：明確傳入路徑 > overlay > cwd 覆蓋層 > 套件內建。未設定 overlay 時解析順序 MUST 與現行相同。

#### Scenario: overlay 優先於 cwd
- **WHEN** overlay 與 cwd 皆有 `templates/prompts/journal_club_template.jinja2`
- **THEN** `resolve_resource` 回傳 overlay 內的檔案

#### Scenario: 未設 overlay 行為不變
- **WHEN** 未設定 overlay 解析資源
- **THEN** 結果與本 change 之前相同（cwd 覆蓋 > 套件內建）
