# Proposal: package-cli

## Why

目前的打包設定是壞的：`[tool.hatch.build.targets.wheel] packages = ["src"]` 只打包 `src/`，但 `[project.scripts]` 指向根目錄模組且程式碼依賴 `sys.path.insert` hack 與 `Path(__file__).parent.parent.parent` 相對路徑找模板——wheel 安裝到乾淨環境後 console scripts 與資源載入全部失效。要讓工具（含 MCP server）在任何機器上以 `uvx` / `pipx` 安裝即用，必須一次性轉為正規 package 佈局。

## What Changes

- **BREAKING（原始碼佈局）**：`src/*` 全部子模組搬移為 `src/claude_lit/` 正規 package；全面改為 absolute import（`from claude_lit.generators import ...`）；刪除所有 `sys.path.insert` hack
- 根目錄三支 CLI 腳本移入 `claude_lit/cli/`（`slides.py`、`zettel.py`、`setup_check.py`）；刪除根目錄 `make_slides.py`、`generate_zettel.py`、`setup.py`（entry points 取代；`setup.py` 檔名另有與 setuptools 撞名的風險）
- `templates/` 與 `config/` 預設檔複製進 `claude_lit/resources/`，新增 `claude_lit/resource_loader.py`：解析順序＝明確參數 > cwd 使用者檔（repo 內的 `templates/`、`config/` 即 cwd 覆蓋）> 套件內建（importlib.resources）
- `pyproject.toml`：`packages = ["src/claude_lit"]`、scripts 全改 `claude_lit.cli.*` 與 `claude_lit.mcp_server.__main__`；暫停工具（analyze/kb/embeddings）的 entry 移除（程式碼保留，改以 `python xxx.py` 執行）
- 全 tests/ import 路徑批次更新
- 新增 wheel 冒煙測試（build → 乾淨 venv 安裝 → CLI 與 mcp-server 可執行）

## Capabilities

### New Capabilities

- `cli`: 命令列介面與可安裝性的行為契約——entry points、uvx/pipx 安裝即用、資源解析順序、Windows 編碼防護

### Modified Capabilities

- `slide-generation`: 模板與風格設定的載入從「原始碼樹相對路徑」改為「資源解析順序（cwd 覆蓋 > 套件內建）」
- `zettel-generation`: 同上（zettelkasten 模板與卡片/索引模板）

## Impact

- **搬移**：`src/{api,generators,extractors,utils,knowledge_base,integrations,embeddings,analyzers,checkers,processors,agents,mcp_server}` → `src/claude_lit/`
- **新增**：`claude_lit/cli/`、`claude_lit/resource_loader.py`、`claude_lit/resources/{templates,config}/`、`tests/unit/test_resources.py`、`tests/unit/test_imports.py`、`tests/integration/test_wheel_smoke.py`
- **刪除**：根目錄 `make_slides.py`、`generate_zettel.py`、`setup.py`
- **修改**：`pyproject.toml`、全部 tests、`analyze_paper.py` 等暫停 CLI 的 import 前綴
- **相容性**：`uv run slides / zettel / setup / mcp-server` 用法不變；repo 內的 `templates/`、`config/` 仍可編輯且優先於套件內建（cwd 覆蓋）；暫停工具的 `uv run analyze/kb/embeddings` 入口移除（**BREAKING**，改用 `uv run python analyze_paper.py`）
