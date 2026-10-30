/*
 * Claude Lit Workflow — Obsidian QuickAdd 遠端模式（呼叫雲端網頁服務，本機不需 uv）
 *
 * 安裝：
 *   1. 把本檔放進 vault（如 Scripts/lit_remote.js）
 *   2. QuickAdd → Manage Macros → 新增 Macro → User Scripts 選本檔
 *   3. 在 Macro 的腳本設定填入 Base URL（如 https://lit.example.com）、Token（WEB_API_TOKEN）、輸出資料夾
 *
 * 流程：選 vault 內的檔案（或輸入網址）→ 選產出與媒體類型 → 上傳 → 輪詢進度 → 把結果寫回 vault
 * （目錄結構與本機 output/ 相同：slides/…、zettelkasten_notes/…）。
 *
 * 核心邏輯 runRemote() 不依賴 Obsidian，可在 Node 以 fetch 測試；entry() 只負責接上 Obsidian API。
 */

const SOURCE_EXTENSIONS = ["pdf", "epub", "txt", "md", "srt", "vtt"];
const POLL_MS = 3000;
const MAX_WAIT_MS = 20 * 60 * 1000;

function joinUrl(base, path) {
  return base.replace(/\/+$/, "") + path;
}

/** 組 multipart/form-data（requestUrl 不支援 FormData，需自行編碼） */
function buildMultipart(fields, file) {
  const boundary = "----litRemote" + Math.random().toString(16).slice(2);
  const enc = new TextEncoder();
  const chunks = [];
  for (const [name, value] of Object.entries(fields)) {
    chunks.push(enc.encode(`--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`));
  }
  if (file) {
    const safeName = file.name.replace(/"/g, "_");
    chunks.push(enc.encode(
      `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${safeName}"\r\n` +
      `Content-Type: application/octet-stream\r\n\r\n`));
    chunks.push(new Uint8Array(file.data));
    chunks.push(enc.encode("\r\n"));
  }
  chunks.push(enc.encode(`--${boundary}--\r\n`));
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const body = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) { body.set(c, offset); offset += c.length; }
  return { body: body.buffer, contentType: `multipart/form-data; boundary=${boundary}` };
}

/**
 * @param deps.requestUrl  Obsidian requestUrl 相容函式（{url, method, headers, body, contentType, throw}）
 * @param deps.ask         互動：{ pickSource, pickKinds, pickMedia, askChapter, askPrompt }
 * @param deps.writeFile   (vaultPath, ArrayBuffer) => Promise
 * @param deps.notify      (message) => void
 * @param deps.sleep       (ms) => Promise
 */
async function runRemote(settings, deps) {
  const base = (settings["Base URL"] || "").trim();
  const token = (settings["Token"] || "").trim();
  const outputFolder = (settings["Output folder"] || "LitWorkflow").replace(/\/+$/, "");
  if (!base) throw new Error("請在腳本設定填入 Base URL");
  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  async function call(path, opts = {}) {
    const res = await deps.requestUrl({
      url: joinUrl(base, path), method: opts.method || "GET",
      headers: Object.assign({}, headers, opts.headers || {}),
      body: opts.body, contentType: opts.contentType, throw: false,
    });
    if (res.status === 401) throw new Error("金鑰錯誤或未設定（Token）");
    if (res.status >= 400) {
      let detail = "";
      try { const j = res.json; detail = [j.error, j.hint].filter(Boolean).join(" — "); } catch (e) {}
      throw new Error(`服務回應 ${res.status}${detail ? "：" + detail : ""}`);
    }
    return res;
  }

  const options = (await call("/api/options")).json;
  const source = await deps.ask.pickSource();               // { file: {name, data} } 或 { url }
  if (!source) return null;
  const kinds = await deps.ask.pickKinds();
  if (!kinds) return null;
  const mediaType = await deps.ask.pickMedia(options.media_types);
  if (!mediaType) return null;
  const params = { kinds, media_type: mediaType };
  if ((options.media_defaults[mediaType] || {}).chaptered) {
    const chapter = await deps.ask.askChapter();
    if (chapter) params.chapter = chapter;
  }
  const prompt = await deps.ask.askPrompt();
  if (prompt) params.custom_requirements = prompt;
  if (source.url) params.url = source.url;

  const { body, contentType } = buildMultipart({ params: JSON.stringify(params) }, source.file);
  const created = (await call("/api/jobs", { method: "POST", body, contentType })).json;
  deps.notify(`已送出（${created.job_id.slice(0, 8)}），生成中…`);

  const started = Date.now();
  let job;
  while (true) {
    job = (await call(`/api/jobs/${created.job_id}`)).json;
    if (["succeeded", "failed", "cancelled"].includes(job.status)) break;
    if (Date.now() - started > MAX_WAIT_MS) throw new Error("等待逾時；稍後可在網頁介面查看結果");
    await deps.sleep(POLL_MS);
  }
  if (job.status !== "succeeded") {
    const err = job.error ? [job.error.message, job.error.hint].filter(Boolean).join(" — ") : job.status;
    throw new Error(`生成未完成：${err}`);
  }

  const { files } = (await call(`/api/jobs/${job.id}/files`)).json;
  const written = [];
  for (const rel of files) {
    const res = await call(`/api/jobs/${job.id}/files/${rel.split("/").map(encodeURIComponent).join("/")}`);
    const target = `${outputFolder}/${rel}`;
    await deps.writeFile(target, res.arrayBuffer);
    written.push(target);
  }
  (job.warnings || []).forEach(w => deps.notify(`⚠️ ${w}`));
  deps.notify(`完成：寫入 ${written.length} 個檔案至 ${outputFolder}/`);
  return { job, written };
}

async function entry(params, settings) {
  const { app, quickAddApi, obsidian } = params;
  const vault = app.vault;

  async function ensureFolder(path) {
    const parts = path.split("/").slice(0, -1);
    let current = "";
    for (const part of parts) {
      current = current ? `${current}/${part}` : part;
      if (!(await vault.adapter.exists(current))) await vault.adapter.mkdir(current);
    }
  }

  const ask = {
    async pickSource() {
      const files = vault.getFiles().filter(f => SOURCE_EXTENSIONS.includes(f.extension));
      const choice = await quickAddApi.suggester(["🌐 輸入網址…", ...files.map(f => f.path)], [null, ...files]);
      if (choice === undefined) return null;
      if (choice === null) {
        const url = await quickAddApi.inputPrompt("網址（網誌、arXiv、DOI…）");
        return url ? { url } : null;
      }
      return { file: { name: choice.name, data: await vault.adapter.readBinary(choice.path) } };
    },
    pickKinds: () => quickAddApi.suggester(
      ["投影片", "原子卡片", "投影片 + 原子卡片"], [["slides"], ["zettel"], ["slides", "zettel"]]),
    pickMedia: catalog => quickAddApi.suggester(
      Object.entries(catalog).map(([k, v]) => `${k} — ${v}`), Object.keys(catalog)),
    askChapter: () => quickAddApi.inputPrompt("章節（如 3 或 3-5；留空處理全文）"),
    askPrompt: () => quickAddApi.inputPrompt("額外要求（選填）"),
  };

  try {
    const result = await runRemote(settings, {
      requestUrl: obsidian.requestUrl,
      ask,
      writeFile: async (path, data) => { await ensureFolder(path); await vault.adapter.writeBinary(path, data); },
      notify: msg => new obsidian.Notice(msg, 6000),
      sleep: ms => new Promise(r => setTimeout(r, ms)),
    });
    const slides = result && result.written.find(p => p.includes("/slides/") && p.endsWith(".md"));
    if (slides) await app.workspace.openLinkText(slides, "", true);
  } catch (e) {
    new obsidian.Notice(`❌ ${e.message}`, 10000);
  }
}

module.exports = {
  entry,
  settings: {
    name: "Claude Lit Workflow（遠端）",
    author: "claude_lit_workflow",
    options: {
      "Base URL": { type: "text", defaultValue: "", placeholder: "https://lit.example.com" },
      "Token": { type: "text", defaultValue: "", placeholder: "WEB_API_TOKEN" },
      "Output folder": { type: "text", defaultValue: "LitWorkflow", placeholder: "vault 內的輸出資料夾" },
    },
  },
  // 供 Node 測試
  runRemote,
  buildMultipart,
};
