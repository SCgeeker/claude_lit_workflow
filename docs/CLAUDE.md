# docs/ - 專案文檔

> 本目錄現為**本機開發暫存區**，`.gitignore` 已排除整個 `docs/`。
> 只有下列策展文檔隨 git 同步、對外發佈；其餘（session 紀錄、階段報告、停用功能設計稿等）僅存在於本機，不 push。

## 隨 repo 發佈的文檔

| 文檔 | 說明 |
|------|------|
| `CLAUDE.md` | 本說明（docs/ 目錄用途）|
| `TROUBLESHOOTING.md` | 故障排除（僅涵蓋現役 slides / zettel / setup / guide / mcp-server）|

## 真相來源

- **使用說明**：根目錄 `README.md`（繁）/ `README.en.md`（英）為單一真相來源
- **行為規格**：`openspec/`（SDD，specs 為行為真相來源）
- **指令選項**：`uv run <指令> --help` 或 `uv run guide`（動態列出，不再維護獨立 CLI 文檔）

## 維護指引

- 開發過程的 session 紀錄、階段報告、實驗筆記直接寫在 `docs/` 本機即可，會被 gitignore，不會誤入 repo。
- 若某份文檔要對外發佈，於 `.gitignore` 以 `!docs/<檔名>` 明確納入，並在上表登記。
