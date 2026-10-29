# Design: add-media-templates

## 1. 核心決策：協定不變、輸入框架可變

```
                    ┌──────────────────── media_profiles.yaml ────────────────────┐
                    │ reading_stance / slide_structure / card_type_weights /      │
                    │ location_format / citation_format / core_rule / preprocess  │
                    └──────────────┬──────────────────────────────────────────────┘
                                   │ 注入
 來源 ──► 前處理 ──► 內容 ──► media_*_template.jinja2 ──► LLM ──► 既有解析器 ──► grounding gate ──► 寫檔
 (pdf/url/text)  (依 profile)            │                          (不變)          (不變，CJK 政策依來源)
                                         └─ 輸出協定區塊：與既有模板逐字相同
```

LLM 輸出協定是解析器、grounding gate、Markdown 輸出模板、vault 匯入腳本共同依賴的**契約**。
所以媒體差異只能出現在「告訴 LLM 怎麼讀、怎麼組織」的部分，不能出現在「怎麼輸出」的部分。

### 考慮過的替代方案

| 方案 | 優點 | 否決理由 |
|------|------|---------|
| A. 每種媒體一份完整模板（10 檔） | 最直觀，好單獨編輯 | 輸出協定複製 10 份，漂移風險最高 |
| B. Jinja `{% extends %}` 繼承：base 放協定，子模板覆寫 block | 協定單一來源 | 現行程式用 `Template(text)` 無 loader；要支援 cwd 覆蓋需改成 `ChoiceLoader`，且使用者需懂 block 語法 |
| **C. YAML profile + 兩個通用模板（採用）** | 協定只有兩處（論文版、媒體版）；使用者改 YAML 即可；沿用現有 `Template(text)` 與 `resolve_resource` | 每段 profile 文字較長，YAML 可讀性略降 |

方案 C 仍有兩份協定（既有論文模板 + 媒體模板）。以測試防漂移（見 §7），並把「論文也改走媒體模板」
列為後續收斂工作——等媒體模板在實際使用中穩定後，`paper` profile 即可取代 legacy 模板。

## 2. Media profile 欄位

| 欄位 | 用途 | 注入位置 |
|------|------|---------|
| `source_label` | 「講演逐字稿」等稱呼 | 兩模板開頭 |
| `reading_stance` | 這類來源的閱讀方式與陷阱 | 兩模板 |
| `slide_structure` | 建議簡報骨架（可取捨） | slides |
| `slide_rules` | 媒體特有投影片規則 | slides 要求 7 |
| `card_type_weights` | 可用類型與配比 | zettel `類型:` 選項、類型定義、配比 |
| `core_rule` | 核心欄位逐字擷取規則 | zettel `核心:` 與要求 4 |
| `location_format` | `位置` 欄位格式 | zettel 來源脈絡 |
| `citation_format` | 來源連結，`str.format_map` 以 `source_meta` 渲染 | zettel `文獻` |
| `extra_card_rules` | 媒體特有卡片規則（選填） | zettel 要求 8 |
| `metadata_fields` | 建議使用者提供的 metadata | CLI 提示、標題頁 |
| `preprocess` | 前處理步驟名（程式端實作） | sources |
| `chunking` | `chapter` 表示以章為單位 | sources / CLI |
| `grounding.cjk_policy` | `erase` / `quarantine` | zettel gate |
| `recommended_styles` / `default_slide_count` | guide 與 Web UI 預設值 | guide / UI |

`citation_format` **必須含 `|`**：`ZettelMaker._rewrite_inline_links` 以 `|` 判定來源連結而不改寫，
否則會被誤判成卡片 ID 而退成純文字。缺漏的 metadata 以空字串填補（`defaultdict(str)`），不阻斷生成。

## 3. 各媒體的設計重點

### 講演逐字稿（lecture）
- **口語 ≠ 書面**：核心句保留口語原貌（含疑似誤聽字），修正寫在「說明」——這是 grounding 的必然要求：
  核心改寫就無法逐字回溯。
- **骨架依講演推進**，不套論文架構；鼓勵每個論點附上講者的例子／類比（`example` 卡）。
- 類型：concept 35 / claim 30 / example 20 / question 15。

### Podcast 逐字稿（podcast）
- **觀點歸屬**是首要問題：核心句不可跨講者拼接；「說明」第一句點明講者；主持人提問不算主張。
- **分歧建模**：兩位講者對立時各出一張 `claim` 卡，以「對比」互連——直接利用既有連結語義。
- 類型：claim 40 / concept 25 / example 20 / question 15。

### 網誌（blog）
- 承接既有 `web_url` 分支並正式化；強調主張／證據類型／修辭的區分與時效性。
- `blog` 可接 URL（沿用 `url_extractor`）或使用者存下的 Markdown。

### 教科書（textbook）
- 教學結構骨架：學習目標 → 先備知識 → 概念 → 原理 → 例題 → 迷思 → 小結 → 自我檢測。
- `question` 卡重新詮釋為**自我檢測題**（提示放「待解問題」，不給完整答案），對應主動回憶。
- 強調「基於」連結，反映先備知識順序；教科書少有作者個人主張，不使用 `claim`。
- 核心不擷取習題題幹（避免大量複製教材內容）。

### 主題專書（monograph）
- 以**論證地圖**為中心：本章在全書命題中的角色、前提 → 推論 → 結論。
- 區分作者主張與作者轉述的他人觀點——核心只擷取作者本人的論述句；轉述內容在「說明」標明原主人與作者態度。
- 類型：claim 35 / concept 35 / example 15 / question 15。

## 4. 文字來源與逐字稿前處理

新增 `TextExtractor`（`extractors/text_extractor.py`），回傳與 `PDFExtractor.extract()` 相容的 dict，
`source_type` 為 `text` / `transcript`。前處理步驟（以 profile `preprocess` 列出，程式端各為一個純函式）：

| 步驟 | 行為 | 注意 |
|------|------|------|
| `parse_subtitles` | SRT/VTT → 純文字，丟棄序號與時間碼列，**保留 offset→時間 對照表** | 對照表供 sidecar 回映 |
| `strip_fillers` | 移除白名單填充詞（嗯、呃、那個…；um、uh） | 僅在獨立出現時移除；`--keep-fillers` 可關閉 |
| `merge_turns` | 合併同一講者的連續字幕片段為段落 | 講者標籤保留在段首 |
| `insert_time_markers` | 每段（或每 N 秒）插入獨立一行的 `[hh:mm:ss]` | 標記**獨立成行**，避免 LLM 把它抄進核心句 |
| `strip_boilerplate` | 網誌頁首尾、訂閱提示 | 沿用 trafilatura 結果 |
| `chapter_split` / `strip_running_heads` | 依章標題切分；移除書眉頁碼 | 見 §5 |

**一致性原則**：送進 prompt 的內容與 grounding gate 比對的來源**是同一份前處理後文字**。
若前處理只套在 prompt 上，LLM 擷取的「乾淨句」會在原始逐字稿中定位失敗而被誤抹。

**時間軸回映**：grounding 回傳的 `char_offset` 經 offset→時間 對照表換算成 `timestamp`，寫入
`{card_id}.grounding.json`。這是比 LLM 自填 `位置` 更可靠的定位，可直接做成「跳到影片 12:30」的連結。

## 5. 長篇來源（教科書、專書）

`_ZETTEL_MAX_CHARS = 120000` 約可容納一篇長論文，但一本教科書常有 50–100 萬字元。
本 change 採**以章為單位**而非自動摘要：

- `--chapter 3` 或 `--chapter 3-5`：`chapter_split` 依章標題（`第 X 章`、`Chapter X`、EPUB 目錄、PDF 書籤）
  切分，只取指定範圍；超過上限時警告並建議縮小範圍。
- cite_key 加後綴：`Author-Year-ch03`；卡片 ID 成為 `Author-Year-ch03-001`，同書不同章不衝突；
  `citation_format` 的 `{chapter}` 自動填入。
- 全書導覽：使用者可對每章各跑一次，再以既有 `zettel_index` 彙整；
  自動 map-reduce（各章摘要 → 全書論證地圖）列為後續 change。

## 6. Grounding 政策調整

| 來源 | 中文核心定位不到 | 理由 |
|------|----------------|------|
| PDF | quarantine（現行） | 可能是 CID glyph 抽取失敗，不是 LLM 杜撰 |
| txt / md / srt / vtt / epub | **erase** | 文字來源沒有抽取失真，定位不到就是杜撰或改寫 |

實作：`ground_card` 增加 `cjk_policy` 參數（預設 `quarantine` 維持現行行為），`api/zettel.py`
依 `source_type` 與 profile 決定傳入值。

## 7. 防漂移

- `tests/unit/test_media_templates.py`：對每個 profile 渲染兩個模板，斷言含全部協定標記
  （`===標題頁===`、`===投影片1===`、`===CARD: {cite_key}-001===`、`類型:`、`核心:`、`說明:`、
  `連結網絡:`、`來源脈絡:`、`- **位置**:`、`- **情境**:`、`個人筆記:`、`待解問題:`）。
- 同一測試斷言 legacy 模板的協定標記與媒體模板相同集合——任一邊改了協定，測試失敗。
- 每個 profile 的 `card_type_weights` 鍵必須存在於 `card_type_catalog`；`citation_format` 必須含 `|`。
- `SYNCED_RESOURCES` 加入三個新檔，沿用 repo/套件內建一致性檢查。

## 8. 風格 × 媒體相容性

並非所有組合都合理（如 `clinical` × `podcast`）。不做硬性禁止，而以 profile 的 `recommended_styles`
作為 guide / Web UI 的預設與提示；使用者明確指定時照做。

## 9. 開放問題

- `strip_fillers` 白名單是否需依語言分開（中文「就是」「然後」常有實義，預設不移除）。
- 是否在 vault 端 `quote_check.py` 同步 `cjk_policy` 的來源區分（跨 repo，僅記錄義務）。
- EPUB 抽取是否納入預設依賴，或維持選配 extra。
