# 故障排除指南（Troubleshooting）

本文件收集 Claude Lit Workflow 現役工具（`setup` / `slides` / `zettel` / `guide` / `mcp-server`）的常見問題與解法。

**版本**: 0.12.0

---

## 目錄

- [環境與安裝](#環境與安裝)
- [LLM 連線](#llm-連線)
- [PDF 提取](#pdf-提取)
- [投影片 / 卡片生成](#投影片--卡片生成)
- [編碼與路徑（Windows）](#編碼與路徑windows)
- [MCP server](#mcp-server)

---

## 環境與安裝

### `uv run` 找不到指令

```bash
# 確認在專案根目錄、pyproject.toml 存在
ls pyproject.toml

# 重新同步依賴
uv sync
```

現役入口只有這五個：`setup`、`slides`、`zettel`、`guide`、`mcp-server`。
`analyze` / `kb` / `embeddings` 已歸檔停用，不在 wheel 內（見根目錄 `CLAUDE.md`）。

### ModuleNotFoundError

```bash
uv sync --reinstall
```

### Python 版本不符（SyntaxError）

需要 Python 3.10+：

```bash
python --version   # 應 >= 3.10
```

### 驗證安裝（不需 API key）

```bash
uv run guide       # 純離線：能印出使用說明即代表套件可正常匯入
```

---

## LLM 連線

### 先跑 setup 確認可用供應商

```bash
uv run setup       # 偵測 GOOGLE / ANTHROPIC / OPENAI / OLLAMA / NVIDIA 連線
```

### API key 未設定 / 無效

```bash
cp .env.example .env    # Windows: copy .env.example .env
# 於 .env 填入至少一個供應商的 key，例如：
# GOOGLE_API_KEY=...
```

`--llm-provider auto` 會自動挑可用者；也可用 `--llm-provider google|anthropic|openai|ollama|nvidia` 明確指定。

### Ollama 連線失敗

```bash
curl http://localhost:11434/api/tags   # 確認服務在跑
ollama serve                           # 未啟動時
ollama list                            # 確認模型已下載
```

### 配額用盡 / 逾時 → 切換供應商

```bash
uv run slides --pdf paper.pdf --llm-provider ollama    # 改用本地
uv run slides --pdf paper.pdf --llm-provider anthropic # 或換雲端供應商
```

> NVIDIA NIM 預設用實測穩定的 `meta/llama-3.1-8b-instruct`；大模型經 `NVIDIA_SLIDES_MODEL` / `NVIDIA_ZETTEL_MODEL` 或 `--model` 覆寫。

---

## PDF 提取

### 無法擷取文字

多為掃描版 PDF（文字嵌在圖片）。本工具不含 OCR，請先用外部工具（Adobe Acrobat、Tesseract）轉出文字層，或改用含文字層的版本。

### 內容被截斷

超長 PDF 會受字元上限限制。可在 `config/` 覆蓋層調整設定，並留意 LLM 的 token 上限。

---

## 投影片 / 卡片生成

### 內容與原文不符

先人工編修投影片，再把編修後的檔餵給 zettel，品質較穩：

```bash
uv run slides --pdf paper.pdf                                   # 生成、人工編修
uv run zettel --pdf paper.pdf --slides-file output/slides/paper.md
```

### 想控制數量 / 密度

```bash
uv run slides --pdf paper.pdf --detail minimal --slides 10
uv run zettel --pdf paper.pdf --detail comprehensive
```

### 指定 citekey（Zotero 等文獻管理場景）

`zettel` 支援 `--citekey` 直接指定輸出檔名的 key；未指定時自動從 DOI / CrossRef 解析：

```bash
uv run zettel --pdf paper.pdf --citekey Barsalou-1999
```

---

## 編碼與路徑（Windows）

### 中文亂碼 / `cp950` / `Big5` 錯誤

LLM 的所有輸入輸出一律以 UTF-8 處理，切勿依賴 Windows 預設 cp950：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
```

從 Obsidian QuickAdd 觸發時，wrapper 需以 `PYTHONIOENCODING=utf-8` 呼叫。
遇到 `UnicodeEncodeError` 時，先懷疑編碼設定，而非邏輯或連線。

### Windows 路徑

路徑含空白請加引號；程式內優先用正斜線或 `pathlib.Path`：

```python
from pathlib import Path
path = Path("D:/folder/file.pdf")
```

---

## MCP server

### 長時工具逾時

`generate_slides` / `generate_zettel` 可能耗時數分鐘，會發 progress notification。請將 client 的 tool timeout 設為 ≥ 360 秒。

### 啟動方式

```bash
uv run mcp-server                                  # stdio（本機 client）
uv run mcp-server --transport http --port 8765     # Streamable HTTP（遠端平台）
```

---

## 取得協助

1. 用 `uv run setup` 確認環境與連線
2. 用 `uv run guide` 查目前可用指令與選項
3. 到專案 GitHub 提交 issue，附上錯誤訊息與環境（Python 版本、OS、供應商）
