# Ollama 後端設定與品質觀察

本專案的 `--llm-provider ollama` 背後**不是本機 Ollama**，是國網中心（NCHC）的遠端 GPU，跑
[CrystalMind](https://huggingface.co/SciMaker/CrystalMind/tree/main) 與
[GemmaPro](https://huggingface.co/SciMaker/GemmaPro/tree/main) 兩個 GGUF 模型。

後端的建置與維運不在本 repo，另見
[twcc-ollama-proxy](https://github.com/SCgeeker/twcc-ollama-proxy)。本文只寫**本專案這一端**要知道的事。

## 1. 後端遷移中（2026-07-26）

TWCC 於 **2026/8/31 停止服務**，後端正遷往晶創26（Nano4）。兩套並存：

| 後端 | 本地端點 | 狀態 |
|------|---------|------|
| TWCC CCS | `http://localhost:11434` | 至 2026/8/31 |
| Nano4（SSH 隧道） | `http://localhost:11435` | 已驗證，尚未日常使用 |

**待後端穩定後**再把 `.env` 的 `OLLAMA_URL` 改到 `11435`；在後端還會變動的階段不要動下游，
否則分不清問題出在哪一端。

改過去之後有個附帶好處：舊架構的 `twcc_proxy.py` 會佔用 `11434`，和本機 Ollama（Obsidian
Vault Search 的 embedding）衝突，建索引時必須先關掉 proxy。走 `11435` 之後兩者可並存。

## 2. `.env` 設定

```env
DEFAULT_LLM_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434     # Nano4 穩定後改 11435
OLLAMA_DEFAULT_MODEL=crystalmind      # 或 gemmapro / gemmapro-r
```

也可用 `--ollama-url` 逐次覆寫，不改 `.env`。

**模型名稱一律全小寫**：`crystalmind`（不是 `CrystalMind`）、`gemmapro`、`gemmapro-r`
（不是 `gemma-pro`）。

## 3. 前置步驟

兩套後端都**不是隨時可用**，用之前要先把後端拉起來：

- **TWCC**：另開視窗跑 `twcc_proxy.py`（見 twcc-ollama-proxy repo）。
- **Nano4**：登入後提交 Slurm job、再開一條 SSH 隧道，因雙因子認證需輸兩次 OTP；
  job 閒置 30 分鐘自動結束。步驟見工作區 `twcc-ollama-proxy/nano4/README.md`。

驗證後端活著：

```powershell
Invoke-RestMethod -Uri "http://localhost:11434/api/tags"
```

## 4. 使用範例

```powershell
# 從 PDF 生成中文投影片
uv run slides "論文主題" --pdf "C:\path\to\paper.pdf" `
  --llm-provider ollama --model crystalmind `
  --language chinese --format pptx

# 從 URL（arXiv / DOI）生成投影片
uv run slides --url https://arxiv.org/abs/1234.56789 `
  --llm-provider ollama --model crystalmind --format both

# 從 PDF 生成 Zettel 卡片
uv run zettel --pdf "C:\path\to\paper.pdf" `
  --llm-provider ollama --model crystalmind `
  --language chinese --domain NeuroPsy

# gemmapro-r（推理版）＋跨卡連結
uv run zettel --pdf "C:\path\to\paper.pdf" `
  --llm-provider ollama --model gemmapro-r `
  --detail detailed --cross-link
```

## 5. 模型選擇

| 模型 | 大小 | 特性 | 適用場景 |
|------|------|------|---------|
| `crystalmind` | 5.6G | 通用，格式穩定，無幻覺 | 一般投影片、快速摘要（**建議預設**） |
| `gemmapro` | 2.4G | 結構清晰，但有幻覺風險 | 快速草稿，配 `--detail standard` |
| `gemmapro-r` | 2.4G | 推理強化版 | 複雜概念抽取、Zettel 卡片 |

## 6. 輸出品質觀察（2026-03-21，TWCC 時期）

比較論文：Public Skepticism about the Use of AI in Scientific Research（Bretter-2026）
設定：`--style modern_academic --detail comprehensive --language chinese`

| 面向 | Gemini 2.5（基準） | gemmapro | crystalmind |
|------|-------------------|----------|-------------|
| 內容深度 | 每點 2-3 完整句 | 點列為主 | 適中 |
| 術語準確 | 中英對照完整 | 有中英但簡略 | 無對照 |
| 幻覺問題 | 無 | **有**（插入不相關認知科學概念） | 無 |
| 格式乾淨度 | 乾淨 | 有冗餘標籤（`**標題：**`／`**內容：**`） | 乾淨 |
| 原始輸出量 | ~12k tokens | ~3700 chars | ~3361 chars |

> 這是 **TWCC 時期**的觀察。Nano4 沿用同一組 Modelfile 模板，理論上輸出應一致，
> 但遷移完成後仍應重測確認 —— 尤其是幻覺與 meta-label 這兩項。

### 已知問題

- [ ] gemmapro 在 `comprehensive` 下有幻覺風險，待測 `standard` 是否改善
- [ ] gemmapro 輸出含 `**標題：**`／`**內容：**` meta-label，需 post-processing 清理
- [ ] 兩個模型輸出量都遠少於 Gemini，每張投影片內容較淺
- [x] `parse_slides()` 已加入三層 fallback（`===`、`**投影片 N：**`、`##`），可正常運作

樣本累積足夠後再決定是否加入 post-processing 清理格式污染。

## 7. 故障排除

| 症狀 | 判斷 |
|------|------|
| `Connection refused` / timeout | 後端沒起來。先確認 proxy／隧道是否在跑，再 `curl /api/tags` |
| `model not found` | 模型名稱大小寫或拼寫錯，見第 2 節 |
| 仍連到 `localhost:11434` | `.env` 未生效 —— 確認在專案根目錄、格式 `KEY=VALUE` 無空格，或改用 `--ollama-url` |
| 回應內容像亂碼 | 編碼問題，非模型問題。中文 I/O 一律 UTF-8，見 memory `global-utf8-llm-io` |

連線失敗時系統會自動 fallback 到其他 provider（Google／OpenAI／NVIDIA），所以「產出成功」
不代表「走的是 ollama」。要確認實際 provider 請看執行日誌。

## 8. 相關

- 後端 proxy／隧道：[twcc-ollama-proxy](https://github.com/SCgeeker/twcc-ollama-proxy)
- 備援 provider 設定：`.env.example`
