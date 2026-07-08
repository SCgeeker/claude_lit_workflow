# config/ - 配置檔

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
    model: "gemini-2.0-flash"
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
