const REFRESH_MS = 15000;
let currentAsset = "";
let seen = new Set();

function tierClass(score) {
  if (score >= 55) return "hot";
  if (score >= 30) return "warm";
  return "cool";
}

function fmtAge(min) {
  if (min < 1) return "just now";
  if (min < 60) return `${Math.round(min)}m ago`;
  return `${(min / 60).toFixed(1)}h ago`;
}

function barRow(label, value, cls) {
  const pct = Math.round(Math.min(value, 1) * 100);
  return `<div class="barrow ${cls}"><span>${label}</span>
    <div class="track"><div class="fill" style="width:${pct}%"></div></div></div>`;
}

// pick the strongest-reacting instrument's market detail for the badge
function topMarket(b) {
  const m = b.market || {};
  let best = null;
  for (const [sym, d] of Object.entries(m)) {
    if (!best || (d.confirmation || 0) > (best.d.confirmation || 0)) best = { sym, d };
  }
  return best;
}

function card(ev) {
  const b = ev.breakdown || {};
  const tc = tierClass(ev.score);
  const isNew = !seen.has(ev.event_id);
  seen.add(ev.event_id);

  const syms = ev.instruments.slice(0, 4)
    .map(i => `<span class="tag sym" title="${i.name}">${i.symbol}</span>`).join("");

  const velo = (b.news_velocity || 0) > 0.05
    ? `<span class="tag velo">▲ ${ev.outlet_count} outlets, rising</span>` : "";
  const social = (b.social || 0) > 0.05
    ? `<span class="tag social">💬 attention ${(b.social * 100).toFixed(0)}</span>` : "";
  const impact = ev.market_impact > 0
    ? `<span class="tag impact">⚡ impact ${ev.market_impact.toFixed(2)}</span>` : "";

  // market confirmation badge: actual price move + volume spike in the contract
  const mk = topMarket(b);
  let confTag = "";
  if (mk && (mk.d.confirmation || 0) > 0.05) {
    const up = mk.d.price_pct >= 0;
    confTag = `<span class="tag conf ${up ? "up" : "down"}" title="${mk.sym} reaction · vol ${mk.d.volume_spike}×">`
      + `${up ? "▲" : "▼"} ${mk.sym} ${mk.d.price_pct > 0 ? "+" : ""}${mk.d.price_pct}% `
      + `· vol ${mk.d.volume_spike}×</span>`;
  }
  const trending = mk && mk.d.trending ? `<span class="tag fire">🔥 trending</span>` : "";

  const top = ev.articles[0] || {};
  const outletPills = ev.outlets.slice(0, 6).map(o => `<span>${o}</span>`).join("");

  return `<div class="card ${tc} ${isNew ? "flash" : ""}" data-id="${ev.event_id}">
    <div class="score ${tc}">
      <div class="num">${Math.round(ev.score)}</div>
      <label>score</label>
    </div>
    <div class="body">
      <div class="headline"><a href="${top.link || "#"}" target="_blank" rel="noopener">${ev.headline}</a></div>
      <div class="meta">
        ${syms}
        <span class="tag outlets">📰 ${ev.outlet_count} outlet${ev.outlet_count > 1 ? "s" : ""}</span>
        ${confTag}${trending}${social}${velo}${impact}
        <span class="tag">${fmtAge(ev.age_minutes)}</span>
      </div>
      <div class="outlet-pills">${outletPills}</div>
    </div>
    <div class="bars">
      ${barRow("outlets", b.breadth || 0, "b-breadth")}
      ${barRow("social", b.social || 0, "b-social")}
      ${barRow("confirm", b.confirmation || 0, "b-confirm")}
      ${barRow("impact", b.impact || 0, "b-impact")}
    </div>
  </div>`;
}

async function load() {
  try {
    const url = "/api/board?limit=40" + (currentAsset ? `&asset=${encodeURIComponent(currentAsset)}` : "");
    const res = await fetch(url);
    const data = await res.json();
    render(data);
  } catch (e) {
    console.error(e);
  }
}

function render(data) {
  const board = document.getElementById("board");
  document.getElementById("stat-events").textContent = data.total_tracked ?? 0;
  const outlets = new Set();
  data.events.forEach(e => e.outlets.forEach(o => outlets.add(o)));
  document.getElementById("stat-outlets").textContent = outlets.size;
  if (data.last_scan_ts) {
    const ago = Math.round((Date.now() / 1000 - data.last_scan_ts));
    document.getElementById("stat-scan").textContent = ago < 5 ? "now" : `${ago}s`;
  }

  if (!data.events.length) {
    // Distinguish "never scanned" (needs setup) from "scanned, nothing trending".
    if (!data.last_scan_ts || !data.scan_count) {
      board.innerHTML = `<div class="empty setup">
        <h2>No data yet — finish the live setup</h2>
        <ol>
          <li>Add a <b>KV store</b> in your Vercel project (Storage → Vercel KV / Upstash) so scans can be saved, then redeploy.</li>
          <li>Run a first scan: <button id="kick">⚡ Scan now</button> &nbsp;or open <code>/api/scan</code>.</li>
          <li>The daily Vercel Cron keeps it fresh after that (or ping <code>/api/scan</code> every couple of minutes for real-time).</li>
        </ol>
        <p class="muted">Until a KV store is connected the board can't persist between requests, so it stays empty.</p>
      </div>`;
      const kick = document.getElementById("kick");
      if (kick) kick.addEventListener("click", async () => {
        kick.textContent = "scanning…"; kick.disabled = true;
        try { await fetch("/api/scan", { method: "POST" }); } catch (e) {}
        load();
      });
      return;
    }
    board.innerHTML = `<div class="empty">Scanned, but nothing is trending right now. The board updates automatically.</div>`;
    return;
  }
  board.innerHTML = data.events.map(card).join("");
}

document.getElementById("refresh").addEventListener("click", async () => {
  await fetch("/api/scan", { method: "POST" });
  load();
});

document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    currentAsset = chip.dataset.asset;
    load();
  });
});

load();
setInterval(load, REFRESH_MS);
