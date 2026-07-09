# cli Specification

## Purpose
TBD - created by archiving change package-cli. Update Purpose after archive.
## Requirements
### Requirement: 可安裝套件
系統 MUST 能以 `uv build` 產出 wheel，並在無原始碼樹的乾淨虛擬環境中安裝後正常執行 console scripts（`slides`、`zettel`、`setup`、`mcp-server`）。原始碼 MUST NOT 依賴 `sys.path` 操作或原始碼樹相對路徑。

#### Scenario: wheel 冒煙
- **WHEN** 以 wheel 安裝到乾淨 venv 後執行 `slides --list-options` 與 `mcp-server --help`
- **THEN** 兩者 exit code 0，無 ImportError，選項清單正常顯示

#### Scenario: 無 sys.path hack 殘留
- **WHEN** 掃描 `src/claude_lit/` 原始碼
- **THEN** 不存在任何 `sys.path.insert` 呼叫

### Requirement: 資源解析順序
套件內建模板與設定 MUST 以 `importlib.resources` 載入；當 cwd 存在同名使用者檔（`templates/...`、`config/...`）時 MUST 優先使用 cwd 版本；明確傳入的路徑參數優先於一切。

#### Scenario: 套件內建可載入
- **WHEN** 在無 cwd 覆蓋檔的目錄初始化 SlideMaker（不給 template_path）
- **THEN** 從套件內資源成功載入 journal_club 模板與 academic_styles.yaml

#### Scenario: cwd 使用者檔覆蓋
- **WHEN** cwd 存在 `templates/prompts/journal_club_template.jinja2`
- **THEN** 資源解析回傳 cwd 版本而非套件內建

### Requirement: CLI 入口與編碼防護
console scripts MUST 由 `claude_lit.cli.*` 提供；CLI 入口 MUST 在非 UTF-8 stdout 時重設為 UTF-8（errors=replace），確保 Windows cp950 環境下含 emoji 與中文的輸出不會崩潰。

#### Scenario: 全模組可 import
- **WHEN** 逐一 import `claude_lit` 的所有子模組
- **THEN** 無 ImportError（重相依模組允許以 optional-dependency 缺席訊息失敗除外）

