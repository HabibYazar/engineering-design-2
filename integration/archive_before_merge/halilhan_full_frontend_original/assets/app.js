// ABU Strategic Management & DSS — single-page application core.
// Hash-based router + persistent shell + shared render helpers.
// Views register themselves into VIEWS from assets/views-*.js.

const VIEWS = { login: { title: "Sign in" } };
const $ = id => document.getElementById(id);

/* ==================== theme (night mode) ==================== */
if (localStorage.getItem("abu-theme") === "dark") document.documentElement.dataset.theme = "dark";
const isDark = () => document.documentElement.dataset.theme === "dark";
function toggleTheme() {
  if (isDark()) {
    delete document.documentElement.dataset.theme;
    localStorage.removeItem("abu-theme");
  } else {
    document.documentElement.dataset.theme = "dark";
    localStorage.setItem("abu-theme", "dark");
  }
  const btn = $("themeToggle");
  if (btn) btn.textContent = isDark() ? "☀️" : "🌙";
}

/* ==================== navigation model ==================== */
const NAV = [
  { group: "Overview", items: [
    ["dashboard", "Executive Dashboard", "📊"],
    ["assistant", "AI Assistant", "✨"],
  ]},
  { group: "Analytics", items: [
    ["students", "Student Analytics", "🎓"],
    ["staff", "Academic Staff", "🧑‍🏫"],
    ["physical", "Physical Resources", "🏛️"],
    ["finance", "Financial Analysis", "💰"],
    ["sustainability", "Program Sustainability", "🌱"],
    ["kpi", "Performance & KPIs", "🎯"],
    ["rankings", "THE · QS · YÖK", "🏆"],
  ]},
  { group: "Planning", items: [
    ["scenarios", "Scenario Cockpit", "🧪"],
    ["alerts", "Early Warning", "⚠️"],
  ]},
  { group: "System", items: [
    ["structure", "University Structure", "🏫"],
    ["data-import", "Data Import", "📥"],
    ["users", "Users & Roles", "👥"],
  ]},
];

/* ==================== session ==================== */
const session = {
  get user() { try { return JSON.parse(sessionStorage.getItem("abu-user")); } catch { return null; } },
  signIn(name, role) { sessionStorage.setItem("abu-user", JSON.stringify({ name, role })); },
  signOut() { sessionStorage.removeItem("abu-user"); },
};

/* ==================== router ==================== */
function currentRoute() {
  const name = location.hash.replace(/^#\/?/, "") || "login";
  return VIEWS[name] ? name : "login";
}

function route() {
  const name = currentRoute();
  if (name !== "login" && !session.user) { location.hash = "#/login"; return; }
  if (name === "login" && session.user) { location.hash = "#/dashboard"; return; }
  const view = VIEWS[name];
  document.title = view.title + " — ABU DSS";
  name === "login" ? renderLogin() : renderApp(name, view);
}

/* ==================== login screen ==================== */
function renderLogin() {
  document.body.className = "login";
  document.body.innerHTML = `
    <form class="login-card" id="loginForm">
      <div class="logo">ABU</div>
      <div>
        <h1>Strategic University Management<br>&amp; Decision Support System</h1>
        <div class="sub">Ankara Bilim University · senior management portal</div>
      </div>
      <label class="f">Username <input id="loginUser" value="test" autocomplete="off"></label>
      <label class="f">Password <input type="password" value="1234"></label>
      <label class="f">Sign in as
        <select id="loginRole">
          <option>Rector — full access</option>
          <option>Dean — faculty scope</option>
          <option>Department Chair — department scope</option>
          <option>Analyst — read only</option>
        </select>
      </label>
      <button class="primary">Sign in</button>
      <div class="hint">Design prototype — authentication is mocked (Module 14 handles this in the backend).</div>
    </form>`;
  $("loginForm").addEventListener("submit", e => {
    e.preventDefault();
    const role = $("loginRole").value.split(" — ")[0];
    const name = $("loginUser").value.trim() || "test";
    session.signIn(name, role);
    location.hash = "#/dashboard";
  });
}

/* ==================== app shell (built once, content swaps) ==================== */
function ensureShell() {
  if ($("sidebar")) return;
  const user = session.user;
  document.body.className = "";
  document.body.innerHTML = `
    <aside id="sidebar">
      <div class="brand">
        <div class="logo">ABU</div>
        <div><b>Ankara Bilim University</b><span>Strategic Management &amp; DSS</span></div>
        <button id="themeToggle" class="theme-btn" title="Toggle night mode">${isDark() ? "☀️" : "🌙"}</button>
      </div>
      ${NAV.map(g => `<div class="group">${g.group}</div>` +
        g.items.map(([name, label, ico]) =>
          `<a href="#/${name}" data-route="${name}"><span class="ico">${ico}</span>${label}</a>`).join("")).join("")}
      <div class="foot">Design prototype · mock data<br>2025–26 academic year</div>
    </aside>
    <div id="backdrop"></div>
    <div class="main">
      <header id="topbar">
        <button id="menuBtn" class="menu-btn" aria-label="Open menu">☰</button>
        <div><h1 id="pageTitle"></h1><div class="sub" id="pageSub"></div></div>
        <div class="right">
          <span class="term">🗓 2025–26 · Fall</span>
          <div class="user">
            <div class="avatar">${user.name.split(/[\s.]+/).filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase()}</div>
            <div><b>${user.name}</b><span class="role">${user.role} · <a href="#" id="signOut">sign out</a></span></div>
          </div>
        </div>
      </header>
      <main class="content" id="view"></main>
    </div>
    <button class="chat-fab" id="chatFab" title="Ask the AI assistant">✨</button>
    <div class="chat-panel" id="chatPanel">
      <div class="head">
        <b>ABU Assistant</b>
        <a href="#/assistant">open full view</a>
        <button id="chatClose" aria-label="Close">✕</button>
      </div>
      <div class="thread" id="miniThread">
        <div class="bubble ai">Hi! Quick question about demand, finances or rankings? Ask here — or open the full view for detailed analyses.</div>
      </div>
      <div class="mini-suggest">
        <button data-q="Why has the occupancy rate of Computer Engineering declined over the last five years?">CENG decline?</button>
        <button data-q="If tuition fees increase 10%, how are revenue, scholarship cost and enrollment affected?">Tuition +10%?</button>
        <button data-q="Rank the faculties by research performance.">Rank faculties</button>
      </div>
      <div class="composer">
        <input id="miniQ" placeholder="Ask anything…">
        <button class="primary" id="miniSend">➤</button>
      </div>
    </div>`;
  $("signOut").addEventListener("click", e => {
    e.preventDefault();
    session.signOut();
    location.hash = "#/login";
  });
  $("themeToggle").addEventListener("click", toggleTheme);
  $("menuBtn").addEventListener("click", () => document.body.classList.toggle("menu-open"));
  $("backdrop").addEventListener("click", () => document.body.classList.remove("menu-open"));
  $("sidebar").addEventListener("click", e => {
    if (e.target.closest("a")) document.body.classList.remove("menu-open");
  });

  /* mini AI chat (reuses the assistant's scripted answers) */
  const esc = t => t.replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const miniBubble = (cls, html) => {
    const d = document.createElement("div");
    d.className = "bubble " + cls;
    d.innerHTML = html;
    $("miniThread").appendChild(d);
    $("miniThread").scrollTop = $("miniThread").scrollHeight;
    return d;
  };
  let miniBusy = false;
  const miniAsk = q => {
    if (miniBusy || !q.trim()) return;
    miniBusy = true;
    miniBubble("user", esc(q));
    const t = miniBubble("ai typing", "Analyzing…");
    const canned = typeof ASSISTANT_ANSWERS !== "undefined" &&
      ASSISTANT_ANSWERS.find(a => a.q.toLowerCase().slice(0, 18) === q.toLowerCase().slice(0, 18));
    setTimeout(() => {
      t.classList.remove("typing");
      t.innerHTML = canned ? canned.a
        : `No scripted answer for that in this prototype — try a suggestion below, or
           <a href="#/assistant">open the full assistant</a>.`;
      miniBusy = false;
      $("miniThread").scrollTop = $("miniThread").scrollHeight;
    }, 800);
  };
  $("chatFab").addEventListener("click", () => $("chatPanel").classList.toggle("open"));
  $("chatClose").addEventListener("click", () => $("chatPanel").classList.remove("open"));
  document.querySelectorAll("#chatPanel .mini-suggest button").forEach(b =>
    b.addEventListener("click", () => miniAsk(b.dataset.q)));
  $("miniSend").addEventListener("click", () => { miniAsk($("miniQ").value); $("miniQ").value = ""; });
  $("miniQ").addEventListener("keydown", e => {
    if (e.key === "Enter") { miniAsk($("miniQ").value); $("miniQ").value = ""; }
  });
}

function renderApp(name, view) {
  ensureShell();
  document.body.classList.remove("menu-open");
  // the floating chat is redundant on the full assistant screen
  const onAssistant = name === "assistant";
  $("chatFab").style.display = onAssistant ? "none" : "";
  if (onAssistant) $("chatPanel").classList.remove("open");
  document.querySelectorAll("#sidebar a[data-route]").forEach(a =>
    a.classList.toggle("active", a.dataset.route === name));
  $("pageTitle").innerHTML = view.title;
  $("pageSub").innerHTML = view.subtitle || "";
  const el = $("view");
  el.classList.remove("enter");
  el.innerHTML = view.html();
  view.init && view.init();
  requestAnimationFrame(() => el.classList.add("enter"));
  el.scrollTop = 0;
}

/* ==================== shared render helpers ==================== */
function tiles(id, arr) {
  $(id).innerHTML = arr.map(([label, value, delta, dir, accent]) =>
    `<div class="tile${accent ? " accent-" + accent : ""}"><div class="label">${label}</div><div class="value">${value}</div>` +
    (delta ? `<div class="delta ${dir || ""}">${delta}</div>` : "") + `</div>`).join("");
}

// Ring gauges (the donut charts from the ABU brief's reference designs).
function donuts(id, rows, opts = {}) {
  const R = 34, C = 2 * Math.PI * R;
  $(id).innerHTML = `<div class="donut-row">` + rows.map(([label, pct, color]) => `
    <div class="donut-box" title="${label}: ${pct}%">
      <svg viewBox="0 0 84 84" width="${opts.size || 92}" height="${opts.size || 92}">
        <circle cx="42" cy="42" r="${R}" fill="none" stroke="var(--track)" stroke-width="9"/>
        <circle cx="42" cy="42" r="${R}" fill="none" stroke="${color || "var(--primary)"}" stroke-width="9"
          stroke-linecap="round" stroke-dasharray="${(Math.min(pct, 100) / 100 * C).toFixed(1)} ${C.toFixed(1)}"
          transform="rotate(-90 42 42)"/>
        <text x="42" y="47" text-anchor="middle" class="donut-val">${pct}%</text>
      </svg>
      <div class="donut-label">${label}</div>
    </div>`).join("") + `</div>`;
}

function hbars(id, rows, opts = {}) {
  const max = opts.max || Math.max(...rows.map(r => r[1]), 1);
  $(id).innerHTML = rows.map(([name, value, color]) => `
    <div class="hbar" title="${name}: ${opts.fmt ? opts.fmt(value) : value}">
      <span class="name">${name}</span>
      <div class="track"><div class="fill" style="width:${(value / max * 100).toFixed(1)}%${color ? `;background:${color}` : ""}"></div></div>
      <span class="val">${opts.fmt ? opts.fmt(value) : value}</span>
    </div>`).join("");
}

function meters(id, rows) {
  $(id).innerHTML = rows.map(([name, pct, color]) => `
    <div class="meter">
      <div class="m-label"><span>${name}</span><b>${pct}%</b></div>
      <div class="track"><div class="fill" style="width:${Math.min(pct, 100)}%${color ? `;background:${color}` : ""}"></div></div>
    </div>`).join("");
}

function lineChart(id, labels, series, opts = {}) {
  const W = 560, H = opts.height || 200, L = 42, R = 14, T = 14, B = 26;
  const all = series.flatMap(s => s.values);
  const lo = opts.min ?? Math.min(...all) * 0.9;
  const hi = opts.max ?? Math.max(...all) * 1.05;
  const x = i => L + i * (W - L - R) / (labels.length - 1);
  const y = v => T + (hi - v) / (hi - lo) * (H - T - B);
  let s = "";
  for (let g = 0; g <= 4; g++) {
    const v = lo + (hi - lo) * g / 4;
    s += `<line class="grid" x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}"/>` +
         `<text x="${L - 6}" y="${y(v) + 3}" text-anchor="end">${opts.yfmt ? opts.yfmt(v) : Math.round(v)}</text>`;
  }
  labels.forEach((lab, i) => { s += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${lab}</text>`; });
  series.forEach(sr => {
    s += `<polyline fill="none" stroke="${sr.color}" stroke-width="2" points="${sr.values.map((v, i) => x(i) + "," + y(v)).join(" ")}"/>`;
    sr.values.forEach((v, i) => {
      s += `<circle cx="${x(i)}" cy="${y(v)}" r="3.5" fill="${sr.color}" stroke="var(--surface)" stroke-width="1.5"><title>${sr.label} · ${labels[i]}: ${opts.yfmt ? opts.yfmt(v) : v}</title></circle>`;
    });
  });
  $(id).innerHTML = `<svg class="chart" viewBox="0 0 ${W} ${H}">${s}</svg>`;
}

function chip(status, text) {
  const map = { good: "✓", warning: "!", critical: "▲", info: "•", neutral: "•" };
  return `<span class="chip ${status}">${map[status] || ""} ${text}</span>`;
}

const fmtUSD = n => "$" + (Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(1) + "M" : Math.round(n).toLocaleString("en-US"));
const fmtK = n => "$" + Math.round(n).toLocaleString("en-US");

/* ==================== boot ==================== */
window.addEventListener("hashchange", route);
document.addEventListener("DOMContentLoaded", route);
