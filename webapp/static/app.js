const logEl = document.getElementById("log");
function setLog(text) { logEl.textContent = text || ""; }

function setPre(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text || "";
}

let modelsRows = [];
let modelsColumns = [];
let sortState = { col: null, dir: "desc" };

window.addEventListener("error", (e) => {
  setLog("JS error: " + (e?.message || e));
});

// Always enforce Top-N on render and load (defensive)
function getTopN() {
  const n = parseInt(document.getElementById("topN")?.value, 10);
  if (!Number.isFinite(n) || n <= 0) return 15;
  return Math.max(1, Math.min(n, 200));
}

// Columns that should always display with exactly 2 decimals
const TWO_DEC_COLS = new Set(["score_v2", "vote_score", "avg_doc_score", "avg_vote"]);

// Preferred/clean column order (only show these when available)
const PREFERRED_COLS = [
  "rank",
  "canonical_model",
  "mentions",
  "unique_threads",
  "vote_score",
  "score_v2",
  "avg_doc_score",
  "avg_vote",
];

function isNumberLike(v) {
  if (v === null || v === undefined) return false;
  const n = Number(v);
  return Number.isFinite(n);
}

function formatCell(v, colName) {
  if (v === null || v === undefined) return "";
  if (isNumberLike(v)) {
    const n = Number(v);

    if (TWO_DEC_COLS.has(colName)) {
      return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    // keep integers clean
    if (Number.isInteger(n)) return n.toLocaleString();

    // default: up to 2 decimals for other numeric cols
    return n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }
  return String(v);
}

function pickColumnsFromData(columnsFromServer, rows) {
  const cols = columnsFromServer?.length
    ? columnsFromServer.slice()
    : (rows.length ? Object.keys(rows[0]) : []);

  // If we have enough preferred cols, show only those (cleaner UI)
  const preferred = PREFERRED_COLS.filter(c => cols.includes(c));
  if (preferred.length >= 3) return preferred;

  // fallback: show everything
  return cols;
}

function renderModelsTable() {
  const filter = (document.getElementById("modelFilter")?.value || "").trim().toLowerCase();
  const topN = getTopN();

  let rows = modelsRows.slice();

  // filter first
  if (filter) {
    rows = rows.filter(r =>
      Object.values(r).some(v => String(v ?? "").toLowerCase().includes(filter))
    );
  }

  // sort next
  if (sortState.col) {
    const col = sortState.col;
    const dir = sortState.dir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      const av = a[col];
      const bv = b[col];
      if (isNumberLike(av) && isNumberLike(bv)) return (Number(av) - Number(bv)) * dir;
      return String(av ?? "").localeCompare(String(bv ?? "")) * dir;
    });
  }

  // strict Top-N render cap (after sort/filter)
  const totalAfterFilter = rows.length;
  rows = rows.slice(0, topN);

  const thead = document.getElementById("modelsThead");
  const tbody = document.getElementById("modelsTbody");
  const meta = document.getElementById("modelsMeta");
  if (!thead || !tbody) return;

  thead.innerHTML = "";
  tbody.innerHTML = "";

  const trh = document.createElement("tr");
  modelsColumns.forEach(col => {
    const th = document.createElement("th");
    const arrow = (sortState.col === col) ? (sortState.dir === "asc" ? " ▲" : " ▼") : "";
    th.textContent = col + arrow;
    th.addEventListener("click", () => {
      if (sortState.col === col) {
        sortState.dir = (sortState.dir === "asc") ? "desc" : "asc";
      } else {
        sortState.col = col;
        sortState.dir = "desc";
      }
      renderModelsTable();
    });
    trh.appendChild(th);
  });
  thead.appendChild(trh);

rows.forEach(r => {
  const tr = document.createElement("tr");

  modelsColumns.forEach(col => {
    const td = document.createElement("td");
    const val = r[col];

    td.textContent = formatCell(val, col);

    if (isNumberLike(val)) td.classList.add("num");
    if (col === "canonical_model") td.classList.add("model");

    tr.appendChild(td);
  });

  tbody.appendChild(tr);
});

  if (meta) {
    // Example: "Showing 15 of 50 (Top N=15)" or "Showing 7 of 7 (Top N=15)"
    meta.textContent = `Showing ${rows.length} of ${totalAfterFilter} row(s) (Top N=${topN})`;
  }
}

async function readResponseAsJsonOrText(res) {
  const text = await res.text();
  try {
    return { ok: true, json: JSON.parse(text), raw: text };
  } catch {
    return { ok: false, json: null, raw: text };
  }
}

/* ---------------------------
   Tabs
---------------------------- */
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    const panel = document.getElementById(btn.dataset.tab);
    if (panel) panel.classList.add("active");
  });
});

/* ---------------------------
   Authorized scrape (PRAW)
---------------------------- */
const btnScrape = document.getElementById("btnScrape");
if (btnScrape) {
  btnScrape.addEventListener("click", async () => {
    setLog("Running scrape...");
    const payload = {
      subreddit: document.getElementById("subreddit")?.value?.trim() || "BudgetAudiophile",
      query: document.getElementById("query")?.value?.trim() || "",
      limit: parseInt(document.getElementById("limit")?.value, 10) || 25,
      debug: document.getElementById("scrapeDebug")?.checked || false
    };

    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    const parsed = await readResponseAsJsonOrText(res);
    if (!parsed.ok) {
      setLog(`Scrape failed: server returned non-JSON (HTTP ${res.status}).`);
      return;
    }
    const data = parsed.json;
    setLog(data.log || JSON.stringify(data, null, 2));
  });
}

/* ---------------------------
   Offline helper (No-API)
---------------------------- */
function normalizeRedditThreadUrl(url) {
  let u = (url || "").trim();
  if (!u) return null;

  u = u.replace(/^<|>$/g, "");
  if (u.startsWith("www.")) u = "https://" + u;
  if (u.startsWith("reddit.com")) u = "https://" + u;

  u = u.replace("old.reddit.com", "www.reddit.com");

  const short = u.match(/^https?:\/\/redd\.it\/([a-z0-9]+)\b/i);
  if (short) u = `https://www.reddit.com/comments/${short[1]}`;

  u = u.split("#")[0];
  return u;
}

function toRedditJsonUrl(threadUrl) {
  let u = normalizeRedditThreadUrl(threadUrl);
  if (!u) return null;

  u = u.split("?")[0];
  if (u.toLowerCase().endsWith(".json")) return u + "?raw_json=1";
  if (u.endsWith("/")) u = u.slice(0, -1);
  return u + ".json?raw_json=1";
}

async function openInBatches(urls, batchSize = 8, delayMs = 450) {
  for (let i = 0; i < urls.length; i += batchSize) {
    const batch = urls.slice(i, i + batchSize);
    batch.forEach(u => window.open(u, "_blank"));
    if (i + batchSize < urls.length) await new Promise(r => setTimeout(r, delayMs));
  }
}

let lastJsonLinks = [];

function refreshJsonButtons() {
  const has = lastJsonLinks.length > 0;
  const copyBtn = document.getElementById("btnCopyJson");
  const openBtn = document.getElementById("btnOpenJson");
  if (copyBtn) copyBtn.disabled = !has;
  if (openBtn) openBtn.disabled = !has;
}

function renderJsonLinks() {
  setPre("jsonLinks", lastJsonLinks.length ? lastJsonLinks.join("\n") : "");
  refreshJsonButtons();
}

function addUrlFromPaste(value) {
  const jsonUrl = toRedditJsonUrl(value);
  if (!jsonUrl) return setLog("That didn't look like a Reddit thread URL.");
  if (!lastJsonLinks.includes(jsonUrl)) {
    lastJsonLinks.push(jsonUrl);
    renderJsonLinks();
    setLog(`Added JSON link (${lastJsonLinks.length} total).`);
  } else {
    setLog("Duplicate link (already added).");
  }
}

const pasteBox = document.getElementById("urlPaste");
if (pasteBox) {
  pasteBox.addEventListener("paste", (e) => {
    const pasted = (e.clipboardData || window.clipboardData).getData("text");
    setTimeout(() => {
      addUrlFromPaste(pasted || pasteBox.value);
      pasteBox.value = "";
    }, 0);
  });

  pasteBox.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addUrlFromPaste(pasteBox.value);
      pasteBox.value = "";
    }
  });
}

const btnCopyJson = document.getElementById("btnCopyJson");
if (btnCopyJson) {
  btnCopyJson.addEventListener("click", async () => {
    if (!lastJsonLinks.length) return;
    await navigator.clipboard.writeText(lastJsonLinks.join("\n"));
    setLog(`Copied ${lastJsonLinks.length} JSON link(s) to clipboard.`);
  });
}

const btnOpenJson = document.getElementById("btnOpenJson");
if (btnOpenJson) {
  btnOpenJson.addEventListener("click", async () => {
    if (!lastJsonLinks.length) return;
    const batchSize = parseInt(document.getElementById("openBatchSize")?.value, 10) || 8;
    setLog(`Opening ${lastJsonLinks.length} JSON link(s) in batches of ${batchSize}...`);
    await openInBatches(lastJsonLinks, batchSize, 450);
    setLog("Opened JSON tabs. Save/copy JSON, then import below.");
  });
}

const btnClearUrls = document.getElementById("btnClearUrls");
if (btnClearUrls) {
  btnClearUrls.addEventListener("click", () => {
    lastJsonLinks = [];
    renderJsonLinks();
    setLog("Cleared URL list.");
  });
}

/* ---------------------------
   Offline: multi-file import
---------------------------- */
const btnImport = document.getElementById("btnImport");
if (btnImport) {
  btnImport.addEventListener("click", async () => {
    setLog("Importing JSON file(s)...");
    setPre("importSummary", "");

    try {
      const input = document.getElementById("jsonFiles");
      const files = input?.files;

      if (!files || files.length === 0) {
        setLog("Choose one or more JSON files first.");
        return;
      }

      const merge = document.getElementById("mergeOnImport")?.checked ? "1" : "0";
      const runAfter = document.getElementById("runPipelineAfterImport")?.checked;

      const form = new FormData();
      for (const f of files) form.append("file", f);
      form.append("merge", merge);

      const res = await fetch("/api/import_json", { method: "POST", body: form });
      const parsed = await readResponseAsJsonOrText(res);

      if (!parsed.ok) {
        setLog(`Import failed: server returned non-JSON (HTTP ${res.status}).`);
        setPre("importSummary", parsed.raw.slice(0, 4000));
        return;
      }

      const data = parsed.json;
      setPre("importSummary", JSON.stringify(data, null, 2));
      setLog(data.ok ? "Import complete." : `Import failed (HTTP ${res.status}).`);

      if (data.ok && runAfter) {
        setLog("Import complete. Running pipeline...");
        await runPipelineAndRefreshChart();
      }
    } catch (err) {
      setLog("Import crashed in the browser. Check DevTools Console for the error.");
      setPre("importSummary", String(err));
      console.error(err);
    }
  });
}

/* ---------------------------
   Pipeline
---------------------------- */
async function runPipelineAndRefreshChart() {
  const useV2 = document.getElementById("useV2")?.checked;

  const res = await fetch("/api/run_pipeline", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({use_v2: useV2})
  });

  const parsed = await readResponseAsJsonOrText(res);
  if (!parsed.ok) {
    setLog(`Pipeline failed: server returned non-JSON (HTTP ${res.status}).`);
    return;
  }

  const data = parsed.json;
  setLog(data.log || JSON.stringify(data, null, 2));

  if (data.ok) {
    const img = document.getElementById("scoreChart");
    if (img && data.chart_png) {
      img.src = `/charts/${data.chart_png}?ts=${Date.now()}`; // cache-bust
    }
  }
}

const btnPipeline = document.getElementById("btnPipeline");
if (btnPipeline) {
  btnPipeline.addEventListener("click", async () => {
    setLog("Running pipeline...");
    await runPipelineAndRefreshChart();
  });
}

const btnTopModels = document.getElementById("btnTopModels");
if (btnTopModels) {
  btnTopModels.addEventListener("click", async () => {
    setLog("Loading Top Models...");

    const n = getTopN();
    const useV2 = document.getElementById("useV2")?.checked ? "1" : "0";

    const res = await fetch(`/api/top_models?n=${encodeURIComponent(n)}&v2=${useV2}`);
    const parsed = await readResponseAsJsonOrText(res);

    if (!parsed.ok) {
      setLog(`Top models failed: server returned non-JSON (HTTP ${res.status}).`);
      return;
    }

    const data = parsed.json;
    if (!data.ok) {
      setLog(data.error || JSON.stringify(data, null, 2));
      return;
    }

    // STRICT: keep only Top N even if server returns more
    const serverRows = Array.isArray(data.rows) ? data.rows : [];
    modelsRows = serverRows.slice(0, n);

    // Clean/ordered columns
    modelsColumns = pickColumnsFromData(data.columns, modelsRows);

    // default sort preference
    const preferredSort = ["score_v2", "vote_score", "mentions"];
    sortState.col = preferredSort.find(c => modelsColumns.includes(c)) || (modelsColumns[0] || null);
    sortState.dir = "desc";

    renderModelsTable();
    setLog(`Loaded ${modelsRows.length} row(s) from ${data.csv} (Top N=${n})`);
  });
}

const filterEl = document.getElementById("modelFilter");
if (filterEl) filterEl.addEventListener("input", () => renderModelsTable());

// initialize
renderJsonLinks();
renderModelsTable();
