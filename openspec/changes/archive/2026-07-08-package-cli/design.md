# Design: package-cli

## Context

change 1、2 已把新程式碼集中在 `src/api/` 與 `src/mcp_server/` 並採可搬移的 import 風格；本 change 做一次性佈局轉換，使 wheel 安裝即用。

## Goals / Non-Goals

**Goals:**
- `src/claude_lit/` 正規 package、absolute imports、零 sys.path hack
- 資源（模板/預設設定）隨 wheel 發佈，cwd 使用者檔可覆蓋
- wheel 冒煙測試把關

**Non-Goals:**
- 不發佈到 PyPI（本 change 只保證可安裝性）
- 不重構暫停模組的內部邏輯（只改 import 前綴）
- chromadb 移 optional extra：**不做**——kb 相關 import 已全部 lazy（change 1），uvx 冷啟動不受影響；相依瘦身留待實際需求出現

## Decisions

1. **一次性 `git mv src/<pkg> src/claude_lit/<pkg>`**：保留 git 歷史；import 改寫用腳本批次處理（模式固定：`from src.X` → `from claude_lit.X`；`from X import`（X ∈ 頂層模組名清單）→ `from claude_lit.X import`）。
2. **資源用「複製」而非「搬移」**：repo 的 `templates/`、`config/` 原地保留，作為 cwd 覆蓋層（使用者照舊編輯 `config/custom_slides.md`）；套件內建為 `claude_lit/resources/` 下的副本。單一真相來源問題以測試防護：測試斷言兩份預設檔內容一致，修改時同步。
3. **`resource_loader.py` 介面**：`resolve_resource(relpath: str, explicit: Path|None = None) -> Path`——explicit > `Path.cwd()/relpath` > 套件內建（`importlib.resources.files("claude_lit") / "resources" / relpath`，必要時 `as_file` 落地暫存）。`SlideMaker`/`ZettelMaker`/`api.prompts`/`api.providers` 的預設路徑全改走此函式。
4. **`.env` 載入**：`config_loader.load_env_file` 改為找 `Path.cwd()/.env`（原為原始碼樹相對路徑）；`CLAUDE_LIT_HOME` 環境變數可覆蓋工作目錄。輸出目錄 `output/` 同樣以 cwd 為基準（維持現行為）。
5. **CLI 殼**：`claude_lit/cli/slides.py` 等直接搬移現有薄殼內容（去掉 sys.path hack 與 `from src.utils.logger` 混用），`setup.py` 改名 `setup_check.py`（script 名保留 `setup`）。
6. **暫停 CLI（analyze_paper.py 等根目錄腳本）**：保留在根目錄、改 import 前綴為 `claude_lit.*`，entry points 移除。

## Risks / Trade-offs

- [批次改寫誤傷字串/註解中的模組名] → 改寫後全套件測試 + `test_imports.py` 全模組 import 掃描
- [雙份預設資源漂移] → `test_resources.py` 斷言 repo 版與套件版內容一致
- [knowledge_base/index.db 等資料路徑] → 資料一律 cwd 相對（不入 wheel），行為不變
- [`mcp.settings` 等既有註冊（claude mcp add 的路徑）] → README 的註冊指令不變（`uv --directory ... run mcp-server` 照常可用）

## Migration Plan

1. 建立 `claude_lit/` 骨架與 `resource_loader.py`（含測試，先綠）
2. `git mv` 搬移 + 批次 import 改寫 + 刪 sys.path hack → 全套件測試綠
3. CLI 殼與 entry points 切換 → CLI 冒煙
4. wheel build + 乾淨 venv 冒煙測試
回滾：git revert 單一 commit（搬移與改寫在同一 commit 完成）。
