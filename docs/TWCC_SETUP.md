# TWCC LLM 設定指南

本指南說明如何配置專案連接到部署在 TWCC 容器中的 Ollama LLM 服務。

## 1. 環境變數配置

### 方法一：創建 `.env` 檔案（推薦）

在專案根目錄創建 `.env` 檔案：

```env
OLLAMA_URL=http://203.145.216.205:59055
OLLAMA_DEFAULT_MODEL=crystalmind
```

### 方法二：使用命令行參數

每次執行時指定 `--ollama-url` 參數：

```bash
uv run slides "主題" --ollama-url http://203.145.216.205:59055 --model crystalmind
```

## 2. 測試連線

### PowerShell 測試

```powershell
Invoke-RestMethod -Uri "http://203.145.216.205:59055/api/tags" -Method Get
```

### curl 測試

```bash
curl http://203.145.216.205:59055/api/tags
```

**預期結果**：返回可用模型列表，包含 `crystalmind`、`gemma-pro` 等。

## 3. 使用範例

### 生成投影片

```bash
# 基本用法（使用 .env 配置）
uv run slides "深度學習應用" --style modern_academic --slides 15

# 指定模型
uv run slides "深度學習應用" --model crystalmind --slides 15

# 從 PDF 生成
uv run slides --pdf paper.pdf --style research_methods
```

### 生成 Zettelkasten 卡片

```bash
# 從 PDF 生成（自動入庫）
uv run zettel --pdf paper.pdf --detail comprehensive

# 從知識庫論文生成
uv run zettel --from-kb 1 --detail standard

# 指定模型
uv run zettel --pdf paper.pdf --model crystalmind
```

### 批次生成卡片

```bash
# 批次處理（會自動使用 .env 配置）
python generate_zettel_batch.py
```

## 4. 可用模型

根據 TWCC 部署指南，以下模型可用：

| 模型名稱 | 說明 | 推薦用途 |
|---------|------|---------|
| `crystalmind` | 自定義模型 | 通用學術內容生成 |
| `gemma-pro` | Gemma Pro 模型 | 高品質文本生成 |
| `gemma-pro-r` | Gemma Pro R 模型 | 研究導向內容 |

## 5. 故障排除

### 連線失敗

**症狀**：`Connection refused` 或 `timeout` 錯誤

**解決方法**：

1. 確認 TWCC 容器正在運行
2. 檢查 `OLLAMA_URL` 環境變數是否正確
3. 測試連線：`curl http://203.145.216.205:59055/api/tags`
4. 確認防火牆未阻擋連線

### 模型未找到

**症狀**：`model not found` 錯誤

**解決方法**：

1. 查看可用模型：`curl http://203.145.216.205:59055/api/tags`
2. 確認模型名稱拼寫正確（**必須全小寫**）
3. 使用正確的模型名稱：`crystalmind`（不是 `CrystalMind`）

### 環境變數未生效

**症狀**：工具仍使用 `http://localhost:11434`

**解決方法**：

1. 確認 `.env` 檔案位於專案根目錄
2. 檢查檔案內容格式正確（`KEY=VALUE`，無空格）
3. 重新啟動命令行終端
4. 或使用 `--ollama-url` 參數強制指定

## 6. 注意事項

> **重要提醒**
>
> - 確保 TWCC 容器正在運行，否則連線會失敗
> - 模型名稱必須全小寫（例如 `crystalmind` 而非 `CrystalMind`）
> - 不使用時請在 TWCC 面板停止容器以節省運算額度

> **安全建議**
>
> - 將 `.env` 加入 `.gitignore` 避免提交敏感資訊
> - 如果 TWCC IP 變更，需更新 `.env` 中的 `OLLAMA_URL`

## 7. 進階配置

### 使用多個 LLM 提供者

`.env` 檔案可同時配置多個 LLM 提供者：

```env
# TWCC Ollama
OLLAMA_URL=http://203.145.216.205:59055
OLLAMA_DEFAULT_MODEL=crystalmind

# Google Gemini（備用）
GOOGLE_API_KEY=your_google_api_key

# 預設提供者
DEFAULT_LLM_PROVIDER=ollama
```

### 自動 Fallback

如果 TWCC Ollama 連線失敗，系統會自動嘗試其他可用的 LLM 提供者（如 Google、OpenAI）。

## 8. 相關文件

- [TWCC LLM 部署指南](../../workout/cardsbox/Ideaverse_Growing/Atlas/PKM/03_Tools/AI/TWCC_LLM_Deployment_Guide.md)
- [專案 README](../README.md)
