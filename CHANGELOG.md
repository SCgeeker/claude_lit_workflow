# 變更日誌 (Changelog)

本文件記錄知識生產器 (Knowledge Production System) 的所有重要變更。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)，
版本號遵循 [語義化版本](https://semver.org/lang/zh-TW/)。

---

## [Unreleased]

> 0.7.0–0.12.0 期間專案定位轉向：核心收斂為 **slides / zettel / setup / guide / mcp-server**，
> 知識管理（analyze / kb / embeddings / 概念網絡）交由筆記 App 接管、已歸檔停用。
> 這段期間的詳細變更以 git 歷史與 `openspec/`（specs 為行為真相來源）為準，未逐條回填本檔。

### 近期（文檔收斂）
- 公開文檔收斂至雙語 README（`README.md` / `README.en.md`）+ `openspec/`
- `docs/`、`examples/` 收斂至現役工具，停用功能文檔與範例移出 repo
- 新增 `docs/LLM_BACKEND.md`（Ollama 後端設定與品質觀察）

---

## [0.6.0-alpha] - 2025-11-01

### 文檔更新
- 修正 CLAUDE.md 和 README.md 之間的不一致
- 統一版本號為 0.6.0-alpha
- 更新 LLM 模型名稱（Gemini, Claude）
- 更新配置範例（auto_select: true）

### 驗證
- ✅ 所有主要檔案均存在
- ✅ 新增模組檔案均存在
- ✅ 配置檔與文檔描述一致

---

## [0.5.0-alpha] - 2025-10-31

### 新增
- **智能 LLM 模型選擇系統** ⭐⭐⭐⭐⭐
  - 自動檢測可用模型（API keys、服務狀態）
  - 任務導向選擇（zettelkasten、academic_slides 等）
  - 策略模式（balanced、quality_first、cost_first、speed_first）
  - 成本控制與監控（會話、每日、每月限制）
  - 自動切換機制（接近成本限制時切換到免費模型）
  - 使用報告生成（每日、週報告）

### 新增文件
- `config/model_selection.yaml` (309 行) - 模型定義與映射配置
- `src/utils/model_monitor.py` (441 行) - 使用監控與成本追蹤
- `src/utils/usage_reporter.py` (321 行) - 報告生成器

### 改進
- `src/generators/slide_maker.py` - 整合智能選擇邏輯 (+200 行)
- `make_slides.py` - CLI 參數支援 (+100 行)

### 測試
- ✅ Claude 3 Haiku 成功整合
- ✅ Google Gemini 免費配額追蹤正常
- ✅ 自動模型選擇邏輯運作正常

---

## [0.4.0-alpha] - 2025-10-30

### 重構
- **KB Manager Agent 工作流程重新設計** ⭐⭐⭐
  - `batch_import` → `batch_import_papers`（批次導入論文）
  - `generate_notes` → `batch_generate_zettel`（批次生成 Zettelkasten）
  - `generate_slides` - 明確標註「只生成簡報」
  - `domain` 支援自定義領域名稱
  - 職責分離更清晰，避免混淆

### 改進
- `batch_processor.py` - 支援單個 PDF 文件路徑
- `workflows.yaml` - 重新命名、調整參數
- `instructions.md` - 新增流程 A 章節、更新流程 B

### 文檔
- `WORKFLOWS_REDESIGN_FEASIBILITY.md` - 完整可行性評估
- `KB_MANAGER_WORKFLOW_REVIEW.md` - 工作流程確認

---

## [0.3.0-alpha] - 2025-10-29

### 新增 (Phase 1 完成) ⭐⭐⭐⭐⭐
- **批次處理器 (Batch Processor)**
  - 檔案: `src/processors/batch_processor.py` (570 行)、`batch_process.py` (237 行)
  - ThreadPoolExecutor 平行處理（預設 3 個 worker）
  - 完整錯誤處理（skip/retry/stop 策略）
  - Windows 路徑支援（pathlib.Path）
  - Timeout 機制（300 秒/PDF）
  - 進度追蹤和報告生成

- **質量檢查器 (Quality Checker)**
  - 檔案: `src/checkers/quality_checker.py` (801 行)、`check_quality.py` (312 行)
  - 5 大檢查項目（標題、作者、年份、摘要、關鍵詞）
  - 290 行 YAML 規則 (`quality_rules.yaml`)
  - 質量評分系統（0-100 分，5 個等級）
  - 重複檢測（相似度演算法）
  - 自動修復架構（API 整合待實作）

- **檔案整理系統 (Session Organizer)**
  - 檔案: `src/utils/session_organizer.py` (397 行)、`cleanup_session.py`
  - 自動整理工作階段產生的檔案
  - 清理臨時檔案（.log、.tmp、cache）
  - 安全保護（不刪除重要目錄）
  - Dry-run 模式預覽變更

### 測試結果
- 批次處理器: 2 個 PDF 測試（1 成功、1 timeout）
- 質量檢查器: 30 篇論文完整檢查
  - 平均評分: 68.2/100
  - 發現 79 個問題（50 個嚴重、20 個警告）
  - 最常見問題: 缺少年份(100%)、關鍵詞不足(67%)、摘要缺失(53%)

### 已知限制
- 大型 PDF 可能超時（300 秒限制）
- 多個 worker 可能觸發 API rate limiting
- 建議 worker 數: 2-4 個

---

## [0.2.0-alpha] - 2025-10-28

### 新增
- **Markdown 簡報格式支援**（相容 Marp/reveal.js）
  - 通用學術風格 Markdown 模板
  - 支援 `--format markdown/pptx/both` 參數

- **Zettelkasten 原子筆記系統** ⭐⭐⭐⭐
  - 專用生成器 `zettel_maker.py`
  - 語義化 ID 格式（`領域-日期-序號`）
  - 雙檔案輸出（索引 + 獨立卡片）
  - 概念連結網絡（6 種關係類型）
  - Mermaid 圖表視覺化

### 改進
- **學術標準化改進**
  - 核心概念直接擷取原文（不翻譯）
  - AI/人類筆記明確標記
  - AI 筆記品質提升（批判性思考）
  - ID 格式自動修復

### 新增模板
- `templates/markdown/zettelkasten_card.jinja2` - 單張卡片模板
- `templates/markdown/zettelkasten_index.jinja2` - 索引與網絡圖
- `templates/markdown/academic_slides.jinja2` - 通用 Markdown 簡報
- `templates/prompts/zettelkasten_template.jinja2` - Zettelkasten 專用 Prompt

### 測試
- 成功測試 2 篇論文（Crockett-2025、Allassonnière-Tang-2021）
- 生成 4 個簡報（教學 MD、現代學術 PPTX+MD）
- 生成 2 套 Zettelkasten（共 24 張卡片）
- 格式穩定性: 100%

---

## [0.1.0-alpha] - 2025-10-27

### 新增
- **Slide-maker Skill 完整實作** ⭐⭐⭐⭐
  - 多 LLM 後端支持（Ollama/Gemini/OpenAI/Claude）
  - 8 種學術風格（新增 Zettelkasten）
  - 5 種詳細程度
  - 3 種語言模式
  - 智能排版系統（自動字體調整、防溢出）
  - 三種工作流模式（快速/知識驅動/重用）

### 修復
- 知識庫 Markdown 空白內容問題
- 投影片標題顯示「投影片 1」而非實際標題
- 文字內容溢出投影片邊界
- Google Gemini API 整合和模型名稱

### 測試結果
- 成功分析 Crockett-2025.pdf
- 生成 21 張高品質文獻回顧風格投影片
- 內容準確度大幅提升（幻覺內容 → 正確反映原文）
- 格式問題完全解決

---

## [0.0.1-alpha] - 2025-10-25

### 初始版本
- 專案架構建立
- PDF 提取器（pdf_extractor.py）
- 知識庫管理器（kb_manager.py）
- 基礎 CLI 工具
- Journal Club 模板整合

---

## 版本標籤說明

- **[Unreleased]**: 計畫中或開發中的功能
- **[X.Y.Z-alpha]**: 內部測試版本
  - X: 主版本號（重大變更）
  - Y: 次版本號（新增功能）
  - Z: 修訂號（錯誤修復）

## 優先級標示

- ⭐⭐⭐⭐⭐: 極高（核心功能、重大改進）
- ⭐⭐⭐⭐: 高（重要功能、顯著改進）
- ⭐⭐⭐: 中（有用功能、一般改進）
- ⭐⭐: 低（輔助功能、小改進）
- ⭐: 極低（美化、文檔更新）

---

**完整文檔**: 請參閱 [CLAUDE.md](CLAUDE.md)
**專案首頁**: 請參閱 [README.md](README.md)
