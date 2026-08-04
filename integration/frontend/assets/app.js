// Stratejik Universite Yonetimi ve Karar Destek Sistemi - SPA cekirdegi.
// Kabuk, yonlendirici ve ortak cizim yardimcilari burada; ekranlar
// assets/views-*.js dosyalarindan VIEWS kaydina kendini ekler.
// Kimlik dogrulama ve butun veri cagrilari assets/api.js uzerinden yapilir.
// Hash-based router + persistent shell + shared render helpers.
// Views register themselves into VIEWS from assets/views-*.js.

const VIEWS = { login: { title: "Giriş" } };
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
// Menu yapisi. Parantez icindeki numaralar proje tanimindaki modul
// numaralaridir; sunumda hangi ekranin hangi moduldan geldigi gorulsun diye
// bilincli olarak gosteriliyor.
const NAV = [
  { group: "Genel Bakış", items: [
    ["dashboard", "Yönetim Panosu", "📊"],
    ["assistant", "Akıllı Asistan", "✨"],
  ]},
  { group: "Analiz", items: [
    ["students", "Öğrenci Analitiği (M2·M3)", "🎓"],
    ["staff", "Akademik Personel (M4)", "🧑‍🏫"],
    ["physical", "Fiziksel Kaynaklar (M5)", "🏛️"],
    ["finance", "Finansal Analiz (M6)", "💰"],
    ["sustainability", "Program Sürdürülebilirliği (M7)", "🌱"],
    ["kpi", "Performans ve KPI (M8)", "🎯"],
    ["rankings", "THE · QS · YÖK (M10)", "🏆"],
  ]},
  { group: "Planlama", items: [
    ["scenarios", "Senaryo Analizi (M9)", "🧪"],
    ["alerts", "Erken Uyarı (M11)", "⚠️"],
  ]},
  { group: "Sistem", items: [
    ["structure", "Üniversite Yapısı (M1)", "🏫"],
    ["data-import", "Veri Aktarımı (M13)", "📥"],
    ["users", "Kullanıcı ve Yetki (M14)", "👥"],
  ]},
];

/* ==================== session ==================== */
// Oturum bilgisi api.js icindeki auth nesnesinden okunur. Burada ayri bir
// kopya tutulmuyor; iki yerde saklanan oturum er ya da gec birbirinden ayrilir.
const session = {
  get user() {
    const u = auth.user;
    if (!u) return null;
    return { name: u.full_name || u.username, role: u.role, raw: u };
  },
  signOut() {
    // Sunucudaki oturumu da kapatiyoruz; yalnizca tarayicidan silmek
    // sunucu tarafinda acik oturum birakirdi.
    if (auth.token) api.post("/api/auth/logout", { token: auth.token }).catch(() => {});
    auth.clear();
    ref.clear();
  },
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
  document.title = view.title + " — ATÜ Karar Destek Sistemi";
  name === "login" ? renderLogin() : renderApp(name, view);
}

/* ==================== giris ekrani ==================== */
// Kimlik dogrulama artik sahte degil: /api/auth/login endpoint'ine gercek
// istek gonderilir, jeton alinir ve yetkiler sunucudan gelir.
function renderLogin() {
  document.body.className = "login";
  document.body.innerHTML = `
    <form class="login-card" id="loginForm">
      <div class="logo">ATÜ</div>
      <div>
        <h1>Stratejik Üniversite Yönetimi<br>ve Karar Destek Sistemi</h1>
        <div class="sub">Ankara Teknoloji Üniversitesi · üst yönetim portalı</div>
      </div>
      <label class="f">Kullanıcı adı <input id="loginUser" value="admin" autocomplete="username"></label>
      <label class="f">Parola <input id="loginPass" type="password" value="demo1234" autocomplete="current-password"></label>
      <div id="loginError"></div>
      <button class="primary" id="loginBtn">Giriş yap</button>
      <div class="hint">
        Demo hesapları: <b>admin</b> · <b>dekan.muh</b> · <b>baskan.ceng</b> · <b>ogretim.uyesi</b><br>
        Parola hepsinde <b>demo1234</b>. Yetkiler role göre sunucudan gelir.
      </div>
    </form>`;

  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("loginBtn");
    const box = $("loginError");
    box.innerHTML = "";
    btn.disabled = true;
    btn.textContent = "Giriş yapılıyor…";
    try {
      const result = await api.post("/api/auth/login", {
        username: $("loginUser").value.trim(),
        password: $("loginPass").value,
      });
      auth.save(result);
      ref.clear();
      location.hash = "#/dashboard";
    } catch (err) {
      // Hata gizlenmez; kullanicinin ne yapacagini bilmesi icin sebebi yazilir.
      box.innerHTML = ui.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Giriş yap";
    }
  });
}

/* ==================== uygulama kabugu (bir kez kurulur) ==================== */
function ensureShell() {
  if ($("sidebar")) return;
  const user = session.user;
  const initials = (user.name || "?")
    .split(/[\s.]+/).filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase();

  document.body.className = "";
  document.body.innerHTML = `
    <aside id="sidebar">
      <div class="brand">
        <div class="logo">ATÜ</div>
        <div><b>Ankara Teknoloji Üniversitesi</b><span>Stratejik Yönetim ve Karar Destek</span></div>
        <button id="themeToggle" class="theme-btn" title="Gece modu">${isDark() ? "☀️" : "🌙"}</button>
      </div>
      ${NAV.map(g => `<div class="group">${g.group}</div>` +
        g.items.map(([name, label, ico]) =>
          `<a href="#/${name}" data-route="${name}"><span class="ico">${ico}</span>${label}</a>`).join("")).join("")}
      <div class="foot">Gerçek API'ye bağlı · SQLite<br>2025–2026 akademik yılı</div>
    </aside>
    <div id="backdrop"></div>
    <div class="main">
      <header id="topbar">
        <button id="menuBtn" class="menu-btn" aria-label="Menüyü aç">☰</button>
        <div><h1 id="pageTitle"></h1><div class="sub" id="pageSub"></div></div>
        <div class="right">
          <span class="term" id="apiStatus" title="Backend durumu">● bağlanıyor…</span>
          <div class="user">
            <div class="avatar">${initials}</div>
            <div><b>${fmt.esc(user.name)}</b><span class="role">${fmt.esc(user.role)} · <a href="#" id="signOut">çıkış</a></span></div>
          </div>
        </div>
      </header>
      <main class="content" id="view"></main>
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

  // Backend gercekten ayakta mi? Ust barda canli durum gosterilir; boylece
  // bos bir ekran gorunce "veri mi yok, sunucu mu kapali" sorusu kalmaz.
  refreshApiStatus();
}

async function refreshApiStatus() {
  const el = $("apiStatus");
  if (!el) return;
  try {
    const health = await api.get("/health");
    el.textContent = "● API bağlı";
    el.className = "term ok";
    el.title = `Sürüm ${health.version || "?"} · veritabanı ${health.database || "hazır"}`;
  } catch {
    el.textContent = "● API kapalı";
    el.className = "term bad";
    el.title = "Backend çalışmıyor. python main.py ile başlatın.";
  }
}

function renderApp(name, view) {
  ensureShell();
  document.body.classList.remove("menu-open");
  document.querySelectorAll("#sidebar a[data-route]").forEach(a =>
    a.classList.toggle("active", a.dataset.route === name));
  $("pageTitle").innerHTML = view.title;
  $("pageSub").innerHTML = view.subtitle || "";
  const el = $("view");
  el.classList.remove("enter");
  el.innerHTML = view.html();
  // Ekranlarin init() fonksiyonu veri cekmek icin async olabilir;\n  // hata yakalanmazsa sessizce kaybolmasin diye burada raporlaniyor.\n  try {\n    const result = view.init && view.init();\n    if (result && typeof result.catch === 'function') {\n      result.catch(err => ui.toast('Ekran yuklenirken hata: ' + (err.userMessage || err.message), 'error'));\n    }\n  } catch (err) {\n    ui.toast('Ekran yuklenirken hata: ' + (err.userMessage || err.message), 'error');\n  }
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
