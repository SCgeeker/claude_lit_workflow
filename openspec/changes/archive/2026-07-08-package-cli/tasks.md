# Tasks: package-cli

## 1. 資源層（先行，與現佈局相容）

- [x] 1.1 失敗測試 `tests/unit/test_resources.py`：resolve_resource 三層解析順序、套件內建載入、repo 版與內建版一致
- [x] 1.2 建立 `claude_lit` 骨架、`resource_loader.py`、複製 templates/config 預設檔到 `claude_lit/resources/`

## 2. 搬移與 import 改寫

- [x] 2.1 `git mv` 全部 `src/<pkg>` → `src/claude_lit/<pkg>`
- [x] 2.2 批次改寫 import（src 內、tests、根目錄腳本）；刪除全部 `sys.path.insert`
- [x] 2.3 `SlideMaker`/`ZettelMaker`/`api.prompts`/`api.providers`/`config_loader` 改走 resource_loader / cwd
- [x] 2.4 失敗測試 `tests/unit/test_imports.py`：全子模組 import、無 sys.path.insert 殘留；全套件測試綠

## 3. CLI 與 entry points

- [x] 3.1 三支 CLI 移入 `claude_lit/cli/`；根目錄三支腳本刪除
- [x] 3.2 `pyproject.toml`：packages、scripts 更新；暫停工具 entry 移除
- [x] 3.3 CLI 冒煙：`uv run slides --list-options`、`uv run setup`、`uv run zettel --help`、`uv run mcp-server --help`

## 4. wheel 驗收

- [x] 4.1 `tests/integration/test_wheel_smoke.py`（@pytest.mark.slow）：uv build → 臨時 venv 安裝 → `slides --list-options`、`mcp-server --help` exit 0
- [x] 4.2 全套件綠；README / CLAUDE.md 更新（暫停工具入口變更、版本號）
