# CLI 操作指南

**版本**: 0.10.0
**更新日期**: 2025-11-29

本指南說明如何使用 `uv run` 操作 claude-lit-workflow 的各項工具。

---

## 環境設置

### 首次安裝

```bash
cd D:\core\research\claude_lit_workflow

# 安裝 uv（如果尚未安裝）
# Windows PowerShell:
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 同步專案依賴
uv sync
```

### 驗證安裝

```bash
# 測試 CLI 是否可用
uv run analyze --help
uv run kb --help
uv run slides --help
```

---

## 💡 推薦 LLM 模型 (2025-12 更新)

根據最新的性能與成本分析，本專案推薦使用以下 Google Gemini 模型設定：

| 模型代號 | 適用場景 | 成本 (Input/Output) | 性能特點 |
|:---------|:---------|:--------------------|:---------|
| **gemini-2.5-flash** | 預設主力 (Default) | $0.10 / $0.40 (per 1M) | 極速、極低成本，適合大多數摘要與分析任務 |
| **gemini-2.5-pro** | 高品質需求 (High Quality) | $1.25 / $10.00 (per 1M) | 具備更強的推理能力，適合「研究方法」分析或複雜論文 |
| **gemini-2.0-flash-exp** | 開發測試 (Dev) | 免費 (配額限制) | 實驗性質，僅供開發測試，不建議生產環境使用 |

> **建議配置**: 將 `config/model_selection.yaml` 更新為上述模型以獲得最佳體驗。

---

## 指令速查表

### 可用指令

| 指令 | 功能 | 狀態 |
|------|------|------|
| `uv run analyze` | 論文分析與入庫 | ✅ 可用 |
| `uv run kb` | 知識庫管理 | ✅ 可用 |
| `uv run slides` | 投影片生成 | ✅ 可用 |
| `uv run embeddings` | 向量嵌入生成 | ✅ 可用 |
| `uv run zettel` | Zettelkasten 卡片生成 | ✅ 可用 |

---

## analyze - 論文分析

分析 PDF 論文並加入知識庫。

### 基本使用

```bash
# 分析論文（僅顯示結果）
uv run analyze paper.pdf

# 分析並加入知識庫
uv run analyze paper.pdf --add-to-kb

# 輸出 JSON 格式
uv run analyze paper.pdf --format json --output-json result.json
```

### 書目檔整合

```bash
# 指定 BibTeX 檔案（自動取得 citekey）
uv run analyze paper.pdf --bib library.bib --add-to-kb

# 指定 RIS 檔案
uv run analyze paper.pdf --ris references.ris --add-to-kb

# 手動指定 citekey（覆蓋書目檔）
uv run analyze paper.pdf --citekey "Barsalou-1999" --add-to-kb

# 指定 DOI（優先從 CrossRef 取得權威元數據）
uv run analyze paper.pdf --doi "10.1017/S0140525X99002149" --add-to-kb
```

### DOI 優先查詢

當提供 DOI 時，系統會優先從 CrossRef 取得權威元數據：

```bash
# DOI 資料優先於 PDF 提取和本地書目檔
uv run analyze paper.pdf --doi "10.xxxx/xxxxx" --add-to-kb

# 流程：DOI → CrossRef 查詢 → 使用權威資料
# 若 CrossRef 查詢失敗，則使用 BibTeX/RIS 作為 fallback
```

### 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `<pdf_path>` | PDF 檔案路徑 | 必填 |
| `--add-to-kb` | 加入知識庫 | False |
| `--format` | 輸出格式 (markdown/json/both) | markdown |
| `--output-json` | JSON 輸出路徑 | - |
| `--bib` | BibTeX 檔案路徑 | - |
| `--ris` | RIS 檔案路徑 | - |
| `--citekey` | 手動指定 citekey | - |
| `--doi` | 指定 DOI（優先查詢 CrossRef）| - |
| `--validate` | 驗證元數據品質 | False |
| `--auto-fix` | 自動修復缺失元數據 | False |
| `--min-score` | 最低質量分數 (配合 --validate) | 60 |
| `--max-chars` | 最大讀取字元數 | 50000 |

---

## kb - 知識庫管理

管理和查詢知識庫。

### 基本查詢

```bash
# 顯示知識庫統計
uv run kb stats
uv run kb stat    # 別名

# 列出所有論文
uv run kb list
uv run kb list --limit 20

# 關鍵詞搜索
uv run kb search "embodied cognition"
uv run kb search "視覺模擬" --limit 10
```

### 語義搜索

```bash
# 語義搜索（需先執行 embeddings）
uv run kb semantic-search "認知科學的基礎理論"

# 尋找相似論文
uv run kb similar 42  # 依 paper_id

# 混合搜索（關鍵詞 + 語義）
uv run kb hybrid-search "grounded cognition"
```

### 論文管理

```bash
# 查看單篇論文詳情
uv run kb get 42                                    # 依 ID
uv run kb get Barsalou-1999                         # 依 citekey
uv run kb get --doi "10.1017/S0140525X99002149"     # 依 DOI
uv run kb get --citekey "Barsalou-1999"             # 明確指定 citekey

# 刪除論文
uv run kb delete 42
uv run kb delete 42 --force    # 跳過確認

# 更新論文元數據（Preprint 正式發表、修正錯誤等）
uv run kb update 42 --refresh                       # 從 DOI 重新取得
uv run kb update 42 --year 2025                     # 手動更新年份
uv run kb update 42 --set-doi "10.new/xxx" --refresh  # 設置新 DOI 並刷新
```

### 更新論文（kb update）

適用情境：
- Preprint 正式發表後更新 DOI 和元數據
- 修正錯誤的書目資訊
- 補充缺失的年份或作者

```bash
# 從現有 DOI 重新取得元數據
uv run kb update 42 --refresh
uv run kb update --doi "10.xxx" --refresh

# Preprint → 正式發表
uv run kb update 42 --set-doi "10.published/xxx" --refresh

# 手動更新特定欄位
uv run kb update 42 --title "正式發表標題"
uv run kb update 42 --authors "作者A, 作者B"
uv run kb update 42 --year 2025
uv run kb update 42 --set-citekey "Author-2025"

# 組合使用
uv run kb update 42 --set-doi "10.new/xxx" --refresh --set-citekey "Author-2025"
```

### 匯入 Zettel 卡片

將現有的 Zettelkasten 資料夾匯入知識庫。

```bash
# 匯入單一資料夾（自動使用配置檔中的預設 BibTeX）
uv run kb import-zettel output/zettelkasten_notes/zettel_Barsalou-1999_20250101

# 指定 BibTeX 檔案（覆蓋預設值）
uv run kb import-zettel output/zettelkasten_notes/zettel_Barsalou-1999_20250101 --bib "path/to/library.bib"

# 預覽模式（不實際寫入）
uv run kb import-zettel output/zettelkasten_notes/zettel_Barsalou-1999_20250101 --dry-run

# 批次匯入所有 Zettel 資料夾
uv run kb import-zettel-all

# 批次匯入並指定 BibTeX
uv run kb import-zettel-all --bib "path/to/library.bib"

# 批次匯入並生成向量嵌入
uv run kb import-zettel-all --embed
```

**配置預設 BibTeX 路徑**（`config/settings.yaml`）：

```yaml
knowledge_base:
  bibliography:
    default_bib: "D:\\path\\to\\My Library.bib"
```

匯入功能說明：
- 自動解析 `zettel_index.md` 取得 cite_key 和元數據
- 根據 cite_key 自動關聯到知識庫中的論文
- **Unicode 正規化比對**：自動匹配 `Créquit-2018` ↔ `Crequit-2018`（支援 é→e, ü→ue 等）
- 若知識庫無對應論文但 BibTeX 有，自動從 BibTeX 新增論文
- 重複的卡片會自動跳過（依 zettel_id 判斷）
- 可選擇生成向量嵌入供語義搜索使用

### 向量資料庫管理

管理 ChromaDB 向量資料庫，確保與 SQLite 同步。

```bash
# 檢查向量庫狀態
uv run kb vector-status
uv run kb vector-status --verbose

# 重置向量庫（清空後需重新生成）
uv run kb vector-reset                    # 重置全部
uv run kb vector-reset --type papers      # 只重置論文
uv run kb vector-reset --type zettel      # 只重置 Zettel
uv run kb vector-reset --force            # 跳過確認

# 同步向量庫（補齊缺失的向量）
uv run kb vector-sync                     # 同步全部
uv run kb vector-sync --type papers       # 只同步論文
uv run kb vector-sync --dry-run           # 預覽模式

# 清理孤立向量（SQLite 已刪除但向量還在）
uv run kb vector-cleanup
uv run kb vector-cleanup --dry-run        # 預覽模式
```

建議工作流程：
1. `vector-status` - 檢查同步狀態
2. `vector-cleanup` - 清理孤立向量
3. `vector-sync` 或 `uv run embeddings` - 補齊缺失向量

### 子指令一覽

| 子指令 | 說明 | 狀態 |
|--------|------|------|
| `stats` / `stat` | 顯示統計 | ✅ |
| `list` | 列出論文 | ✅ |
| `search` | 關鍵詞搜索 | ✅ |
| `semantic-search` | 語義搜索 | ✅ |
| `similar` | 相似論文/卡片 | ✅ |
| `hybrid-search` | 混合搜索 | ✅ |
| `get` / `show` | 查看詳情 | ✅ |
| `delete` | 刪除論文 | ✅ |
| `update` | 更新元數據 | ✅ |
| `export-zettel` | 匯出 Zettel 卡片 | ✅ |
| `import-zettel` | 匯入 Zettel 資料夾 | ✅ |
| `import-zettel-all` | 批次匯入所有 Zettel | ✅ |
| `auto-link` | 自動建立卡片連結 | ✅ |
| `check-llm` | 檢查 LLM 狀態 | ✅ |
| `vector-status` | 檢查向量庫狀態 | ✅ |
| `vector-reset` | 重置向量庫 | ✅ |
| `vector-sync` | 同步向量庫 | ✅ |
| `vector-cleanup` | 清理孤立向量 | ✅ |
| `visualize-network` | 概念網絡 | ✅ (Phase 2.2) |

---

## slides - 投影片生成

生成學術風格投影片。

### 基本使用

```bash
# 從 PDF 生成投影片
uv run slides "論文主題" --pdf paper.pdf

# 從知識庫論文生成
uv run slides "知覺符號系統" --from-kb 42

# 先分析再生成（推薦）
uv run slides "Embodied Cognition" --pdf paper.pdf --analyze-first
```

### 風格與格式

```bash
# 指定學術風格
uv run slides "主題" --pdf paper.pdf --style modern_academic

# 指定詳細程度
uv run slides "主題" --pdf paper.pdf --detail comprehensive

# 指定語言
uv run slides "主題" --pdf paper.pdf --language chinese
uv run slides "主題" --pdf paper.pdf --language bilingual

# 指定投影片數量
uv run slides "主題" --pdf paper.pdf --slides 20
```

### LLM 選擇

```bash
# 使用 Gemini（預設）
uv run slides "主題" --pdf paper.pdf --llm-provider google

# 使用 Ollama 本地模型
uv run slides "主題" --pdf paper.pdf --llm-provider ollama --model llama3.3

# 使用 OpenAI
uv run slides "主題" --pdf paper.pdf --llm-provider openai --model gpt-4

# 使用詳細參數
uv run slides "主題" --pdf paper.pdf --selection-strategy quality_first --usage-report

```

### 自訂需求

```bash
# 使用自訂需求檔案
uv run slides "主題" --pdf paper.pdf --custom-file my_requirements.md

# 使用命令行自訂需求
uv run slides "主題" --pdf paper.pdf --custom "請使用口語化表達"

# 忽略預設需求檔案（config/custom_slides.md）
uv run slides "主題" --pdf paper.pdf --no-custom
```

### 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `<topic>` | 簡報主題 | 必填 |
| `--pdf` | PDF 檔案路徑 | - |
| `--from-kb` | 知識庫論文 ID | - |
| `--analyze-first` | 先分析再生成 | False |
| `--style` | 學術風格 | modern_academic |
| `--detail` | 詳細程度 | standard |
| `--language` | 語言 | chinese |
| `--slides` | 投影片數量 | 15 |
| `--custom` | 命令行自訂需求 | - |
| `--custom-file` | 自訂需求檔案路徑 | - |
| `--no-custom` | 忽略預設需求檔案 | False |
| `--llm-provider` | LLM 提供者 | auto |
| `--model` | 模型名稱 | - |
| `--output` | 輸出路徑 | 自動生成 |
| `--selection-strategy` | 模型選擇策略 | balanced |
| `--usage-report` | 生成使用報告 | False |
| `--api-key` | API 金鑰 | - |
| `--ollama-url` | Ollama URL | http://localhost:11434 |

### 可用風格

| 風格 | 說明 |
|------|------|
| `classic_academic` | 經典學術 |
| `modern_academic` | 現代學術（推薦）|
| `clinical` | 臨床導向 |
| `research_methods` | 研究方法 |
| `literature_review` | 文獻回顧 |
| `case_analysis` | 案例分析 |
| `teaching` | 教學導向 |

### 詳細程度

| 程度 | 說明 |
|------|------|
| `minimal` | 極簡（2-3 點/張）|
| `brief` | 簡要（3-4 點/張）|
| `standard` | 標準（4-5 點/張）|
| `detailed` | 詳細（5-6 點/張）|
| `comprehensive` | 完整（6-8 點/張）|



---

## embeddings - 向量嵌入

生成知識庫的向量嵌入（用於語義搜索）。

### 基本使用

```bash
# 生成所有論文的嵌入
uv run embeddings

# 指定 Embedder
uv run embeddings --provider gemini    # 使用 Gemini（推薦）
uv run embeddings --provider ollama    # 使用 Ollama 本地

# 僅處理論文
uv run embeddings --papers-only

# 僅處理 Zettel 卡片
uv run embeddings --zettel-only

# 指定處理數量（測試用）
uv run embeddings --limit 10

# 自動確認（無人值守模式）
uv run embeddings --yes
```

### 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `--provider` | Embedder 提供者 | gemini |
| `--papers-only` | 僅處理論文 | False |
| `--zettel-only` | 僅處理 Zettel | False |
| `--limit` | 處理數量限制 | - |
| `--stats` | 僅顯示統計 | False |
| `--yes` / `-y` | 自動確認 | False |

---

## zettel - Zettelkasten 卡片生成

從論文生成原子化知識卡片（Zettelkasten 方法）。

### 基本使用

```bash
# 從 PDF 生成卡片（自動入庫）
uv run zettel --pdf paper.pdf

# 從知識庫論文生成
uv run zettel --from-kb 42

# 指定詳細程度
uv run zettel --pdf paper.pdf --detail comprehensive

# 使用自訂需求檔案
uv run zettel --pdf paper.pdf --custom-file my_style.md

# 不入庫（僅生成檔案）
uv run zettel --pdf paper.pdf --no-add-to-kb

# 啟用跨論文連結
uv run zettel --pdf paper.pdf --cross-link

# 強制重新生成（覆蓋舊卡片）
uv run zettel --from-kb 42 --force
```

### LLM 選擇

```bash
# 使用 Gemini（預設）
uv run zettel --pdf paper.pdf --llm-provider google

# 使用 Ollama 本地模型
uv run zettel --pdf paper.pdf --llm-provider ollama --model llama3.3

# 使用 OpenAI
uv run zettel --pdf paper.pdf --llm-provider openai --model gpt-4
```

### 自訂需求

```bash
# 使用自訂需求檔案
uv run zettel --pdf paper.pdf --custom-file my_requirements.md

# 忽略預設需求檔案（config/custom_zettel.md）
uv run zettel --pdf paper.pdf --no-custom
```

### 參數說明

| 参数 | 说明 | 预设值 |
|------|------|--------|
| `--pdf` | PDF 檔案路徑（與 --from-kb 二擇一）| - |
| `--from-kb` | 知識庫論文 ID（與 --pdf 二擇一）| - |
| `--detail` | 詳細程度 | standard |
| `--language` | 語言模式 | chinese |
| `--domain` | 領域代碼 | Research |
| `--custom-file` | 自訂需求檔案路徑 | - |
| `--no-custom` | 忽略預設需求檔案 | False |
| `--no-add-to-kb` | 不加入知識庫 | False |
| `--cross-link` | 啟用跨論文連結 | False |
| `--force` | 強制重新生成 | False |
| `--no-embed` | 跳過向量嵌入 | False |
| `--llm-provider` | LLM 提供者 | auto |
| `--model` | 模型名稱 | - |
| `--selection-strategy` | 模型選擇策略 | balanced |
| `--output` | 輸出路徑 | 自動生成 |

### 詳細程度

| 程度 | 說明 |
|------|------|
| `minimal` | 極簡（5 張卡片）|
| `brief` | 簡要（8 張卡片）|
| `standard` | 標準（12 張卡片）|
| `detailed` | 詳細（20 張卡片）|
| `comprehensive` | 完整（30+ 張卡片）|

### 輸出結構

生成的卡片會自動保存至：

```
output/zettelkasten_notes/
└── zettel_{citekey}_{date}/
    ├── zettel_index.md        # 索引文件
    └── zettel_cards/
        ├── {citekey}-001.md   # 原子卡片
        ├── {citekey}-002.md
        └── ...
```

---

## 常用工作流程

### 流程 A：單篇論文完整處理

```bash
# 1. 分析並入庫（使用 DOI 取得正確元數據）
uv run analyze paper.pdf --doi "10.xxxx/xxxxx" --add-to-kb

# 2. 生成 Zettel 卡片
uv run zettel --from-kb <paper_id>

# 3. 生成投影片（可選）
uv run slides "論文主題" --from-kb <paper_id>

# 4. 更新向量嵌入（可選）
uv run embeddings --incremental
```

### 流程 B：知識庫查詢

```bash
# 1. 關鍵詞搜索
uv run kb search "visual simulation"

# 2. 語義搜索（更智能）
uv run kb semantic-search "視覺模擬如何影響語言理解"

# 3. 查看詳情
uv run kb get <paper_id>
```

### 流程 C：Preprint 更新為正式發表

```bash
# 1. 查看現有 Preprint 資訊
uv run kb get <paper_id>

# 2. 更新 DOI 並從 CrossRef 取得正式發表資訊
uv run kb update <paper_id> --set-doi "10.published/xxx" --refresh

# 3. 確認更新結果
uv run kb get <paper_id>
```

### 流程 D：批次處理多篇論文

```bash
# 1. 準備：將 PDF 和 .bib 放在同一資料夾

# 2. 逐一處理（目前方式）
for pdf in ./papers/*.pdf; do
    uv run analyze "$pdf" --add-to-kb
done

# 3. 批次生成 Zettel
uv run zettel --from-kb <paper_id>  # 對每篇論文執行

# 4. 更新嵌入
uv run embeddings
```

---

## 待實作功能一覽

| 功能 | 說明 | 優先級 |
|------|------|--------|
| `--from-bib` 批次 | 從書目檔批次處理 | P2 |

---

## 故障排除

### 問題：uv run 找不到指令

```bash
# 確認 pyproject.toml 存在
ls pyproject.toml

# 重新同步
uv sync
```

### 問題：ModuleNotFoundError

```bash
# 重新安裝依賴
uv sync --reinstall
```

### 問題：中文顯示亂碼

```powershell
# Windows PowerShell 設定 UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
```

### 問題：LLM 連接失敗

```bash
# 檢查 API Key
echo $GOOGLE_API_KEY

# 測試 Ollama
curl http://localhost:11434/api/tags

# 切換 LLM 提供者
uv run slides "主題" --pdf paper.pdf --llm-provider ollama
```

---

## 相關文件

- [QUICKSTART.md](QUICKSTART.md) - 快速開始
- [CITEKEY_DESIGN_SPEC.md](CITEKEY_DESIGN_SPEC.md) - Citekey 設計規格
- [CLAUDE.md](../CLAUDE.md) - 完整專案文件
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - 故障排除指南

---

## 版本歷史

| 版本 | 日期 | 說明 |
|------|------|------|
| 0.10.1 | 2025-11-29 | import-zettel 新增 --bib 參數、配置檔預設 bib 路徑、Unicode 正規化比對 |
| 0.10.0 | 2025-11-29 | 新增 zettel CLI、自訂需求檔案、import-zettel 指令 |
| 0.9.0 | 2025-11-28 | 新增 RIS/DOI 支援、kb update、DOI 優先查詢 |
| 0.8.0 | 2025-11-27 | 初版，建立 uv 整合 |

---

*本指南由 Claude Code 協助生成*
