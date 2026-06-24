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

function card(ev) {
  const b = ev.breakdown || {};
  const tc = tierClass(ev.score);
  const isNew = !seen.has(ev.event_id);
  seen.add(ev.event_id);

  const syms = ev.instruments.slice(0, 4)
    .map(i => `<span class="tag sym" title="${i.name}">${i.symbol}</span>`).join("");

  const velo = (b.outlets_per_min || 0) > 0
    ? `<span class="tag velo">▲ ${b.outlets_per_min}/min pickup</span>` : "";
  const impact = ev.market_impact > 0
    ? `<span class="tag impact">⚡ impact ${ev.market_impact.toFixed(2)}</span>` : "";
  const views = b.views ? `<span class="tag">👁 ${b.views.toLocaleString()} views</span>` : "";

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
        <span class="tag">${ev.article_count} articles</span>
        ${velo}${impact}${views}
        <span class="tag">${fmtAge(ev.age_minutes)}</span>
      </div>
      <div class="outlet-pills">${outletPills}</div>
    </div>
    <div class="bars">
      ${barRow("breadth", b.breadth || 0, "b-breadth")}
      ${barRow("velocity", b.velocity || 0, "b-velocity")}
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
    board.innerHTML = `<div class="empty">No trending market-moving news right now. Scanning…</div>`;
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
