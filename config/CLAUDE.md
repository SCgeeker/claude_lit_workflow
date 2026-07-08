# config/ - 配置檔

## 定位：cwd 覆蓋層（package-cli 之後）

套件內建一份預設值（`src/claude_lit/resources/config/`：custom_slides.md、
custom_zettel.md、settings.yaml、model_selection.yaml，隨 wheel 發佈）。
解析順序：**明確傳入路徑 > 目前工作目錄的 `config/...` > 套件內建**。

- 在 repo 目錄執行時本目錄優先——`custom_slides.md` / `custom_zettel.md`
  是使用者依研究領域自訂的需求檔，照舊直接編輯即可
- `custom_figure_*.md`、`custom_table_*.md` 為進階自訂需求範本，僅供
  `--custom-file` 明確指定使用，不隨套件發佈
- MCP server 以 `config://custom-slides`、`config://custom-zettel`、
  `config://settings`（脫敏）resources 唯讀曝露這些檔案
- **管理規則**：修改四個有套件內建版的檔案後，需同步到
  `src/claude_lit/resources/config/`——`tests/unit/test_resources.py`
  斷言兩份一致，漂移時測試失敗提醒

## 主配置

### settings.yaml

```yaml
# PDF 提取設定
pdf:
  extraction_method: "pdfplumber"  # 或 "pypdf2"
  max_chars: 50000

# 知識庫設定
knowledge_base:
  root: "knowledge_base"
  db_name: "index.db"

# LLM 設定
llm:
  default_provider: "google"
  google:
    model: "gemini-2.5-flash"
  ollama:
    url: "http://localhost:11434"
    model: "llama3.3:70b"

# Citekey 設定（待實作）
citekey:
  auto_format: "{first_author}-{year}"
  normalize:
    separator: "-"
    lowercase: false
```

## 環境變數

在 `.env` 檔案設定 API 金鑰：

```bash
GOOGLE_API_KEY=your-key
OPENAI_API_KEY=your-key
ANTHROPIC_API_KEY=your-key
```
