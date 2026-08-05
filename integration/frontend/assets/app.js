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
// Menü yapısı. Kullanıcıya iç geliştirme ifadeleri (modül numaraları, tablo
// veya endpoint adları) GÖSTERİLMEZ; yalnızca işi anlatan başlıklar kullanılır.
// İkonlar renkli emoji değil, tek renkli sade işaretlerdir: 16 ayrı emoji
// menüyü bir simge duvarına çeviriyor ve hangi sayfada olduğunu okumayı
// zorlaştırıyordu. Aynı aileden geometrik işaretler kullanılıyor.
const NAV = [
  { group: "Ana Sayfa", items: [
    ["dashboard", "Yönetim Panosu", "◧"],
    ["assistant", "Akıllı Asistan", "◍"],
  ]},
  { group: "Akademik Analizler", items: [
    ["students", "Öğrenci Analitiği", "◔"],
    ["success", "Akademik Başarı", "◈"],
    ["staff", "Akademik Personel", "◇"],
    ["sustainability", "Program Sürdürülebilirliği", "◎"],
  ]},
  { group: "Kaynak ve Finans", items: [
    ["physical", "Fiziksel Kaynaklar", "▤"],
    ["finance", "Finansal Analiz", "▦"],
  ]},
  { group: "Performans", items: [
    ["kpi", "Performans Göstergeleri", "◉"],
    ["engagement", "Sanayi ve Bölgesel Katkı", "◐"],
    ["rankings", "Değerlendirme ve Kıyaslama", "◆"],
  ]},
  { group: "Planlama", items: [
    ["scenarios", "Senaryo Analizi", "◑"],
    ["alerts", "Risk ve Erken Uyarı", "◭"],
  ]},
  { group: "Sistem", items: [
    ["structure", "Üniversite Yapısı", "▥"],
    ["data-import", "Veri Aktarımı", "▽"],
    ["users", "Kullanıcı ve Yetki", "◌"],
  ]},
];

/** Bir sayfanın hangi menü grubunda olduğunu döndürür. */
function navGroupOf(routeName) {
  const found = NAV.find((g) => g.items.some(([name]) => name === routeName));
  return found ? found.group : NAV[0].group;
}

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
  document.title = view.title + " — ABÜN Karar Destek Sistemi";
  name === "login" ? renderLogin() : renderApp(name, view);
}

/* ==================== giris ekrani ==================== */
// Kimlik dogrulama artik sahte degil: /api/auth/login endpoint'ine gercek
// istek gonderilir, jeton alinir ve yetkiler sunucudan gelir.
function renderLogin() {
  document.body.className = "login";
  document.body.innerHTML = `
    <form class="login-card" id="loginForm">
      <div class="logo">ABÜN</div>
      <div>
        <h1>Stratejik Üniversite Yönetimi<br>ve Karar Destek Sistemi</h1>
        <div class="sub">Ankara Bilim Üniversitesi · üst yönetim portalı</div>
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
        <div class="logo">ABÜN</div>
        <div><b>Ankara Bilim Üniversitesi</b><span>Stratejik Yönetim ve Karar Destek</span></div>
        <button id="themeToggle" class="theme-btn" title="Gece modu">${isDark() ? "☀️" : "🌙"}</button>
      </div>
      <nav id="navGroups">
        ${NAV.map(g =>
          `<div class="nav-group" data-group="${fmt.esc(g.group)}">
             <button class="nav-group-head" type="button" data-toggle="${fmt.esc(g.group)}"
                     aria-expanded="false">
               <span>${fmt.esc(g.group)}</span><span class="caret">▾</span>
             </button>
             <div class="nav-group-items">
               ${g.items.map(([name, label, ico]) =>
                 `<a href="#/${name}" data-route="${name}"><span class="ico">${ico}</span>${label}</a>`
               ).join("")}
             </div>
           </div>`).join("")}
      </nav>
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

  // Menü grupları akordeon: aynı anda yalnızca bir grup açık kalır. 16 bağlantı
  // birden görününce menü kaydırma gerektiriyor ve hiyerarşi kayboluyordu.
  $("navGroups").addEventListener("click", e => {
    const head = e.target.closest(".nav-group-head");
    if (!head) return;
    openNavGroup(head.dataset.toggle, { toggle: true });
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

/**
 * Bir menü grubunu açar. toggle=true ise açık grubu kapatır.
 * Diğer gruplar her durumda kapanır: aynı anda tek grup açık kalsın.
 */
function openNavGroup(groupName, { toggle = false } = {}) {
  const container = $("navGroups");
  if (!container) return;
  container.querySelectorAll(".nav-group").forEach(box => {
    const isTarget = box.dataset.group === groupName;
    const wasOpen = box.classList.contains("open");
    const shouldOpen = isTarget && !(toggle && wasOpen);
    box.classList.toggle("open", shouldOpen);
    const head = box.querySelector(".nav-group-head");
    if (head) head.setAttribute("aria-expanded", String(shouldOpen));
  });
}

function renderApp(name, view) {
  ensureShell();
  document.body.classList.remove("menu-open");
  document.querySelectorAll("#sidebar a[data-route]").forEach(a =>
    a.classList.toggle("active", a.dataset.route === name));
  // Kullanıcının bulunduğu grup otomatik açılır; kaybolmaz.
  openNavGroup(navGroupOf(name));
  $("pageTitle").innerHTML = view.title;
  $("pageSub").innerHTML = view.subtitle || "";
  const el = $("view");
  el.classList.remove("enter");
  el.innerHTML = view.html();
  // Ekranların init() fonksiyonu veri çekmek için async olabilir.
  // Hata yakalanmazsa ekran sessizce boş kalırdı; bu yüzden hem senkron
  // hem de asenkron hatalar burada bildirime dönüştürülüyor.
  try {
    const result = view.init && view.init();
    if (result && typeof result.catch === "function") {
      result.catch((err) =>
        ui.toast("Ekran yüklenirken hata: " + (err.userMessage || err.message), "error")
      );
    }
  } catch (err) {
    ui.toast("Ekran yüklenirken hata: " + (err.userMessage || err.message), "error");
  }
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
      <div class="donut-label">${label}</div>${opts.unit ? `<div class="donut-unit">${opts.unit}</div>` : ""}
    </div>`).join("") + `</div>`;
}

function hbars(id, rows, opts = {}) {
  // opts.valueLabel: çubukların neyi gösterdiği (ör. "Milyon USD").
  // Bu etiket olmadan kullanıcı çubuk uzunluğunun neyi ölçtüğünü bilemiyordu.
  const max = opts.max || Math.max(...rows.map(r => Number(r[1]) || 0), 1);
  const format = opts.fmt || (v => v);
  const header = opts.valueLabel
    ? `<div class="chart-caption">${fmt.esc(opts.valueLabel)}</div>` : "";
  const legend = opts.legend
    ? `<div class="legend">` + opts.legend.map(([label, color]) =>
        `<span><span class="swatch" style="background:${color}"></span>${fmt.esc(label)}</span>`
      ).join("") + `</div>` : "";
  $(id).innerHTML = header + rows.map(([name, value, color]) => `
    <div class="hbar" title="${fmt.esc(name)}: ${format(value)}${opts.valueLabel ? " (" + fmt.esc(opts.valueLabel) + ")" : ""}">
      <span class="name">${fmt.esc(name)}</span>
      <div class="track"><div class="fill" style="width:${((Number(value) || 0) / max * 100).toFixed(1)}%${color ? `;background:${color}` : ""}"></div></div>
      <span class="val">${format(value)}</span>
    </div>`).join("") + legend;
}

function meters(id, rows) {
  $(id).innerHTML = rows.map(([name, pct, color]) => `
    <div class="meter">
      <div class="m-label"><span>${name}</span><b>${pct}%</b></div>
      <div class="track"><div class="fill" style="width:${Math.min(pct, 100)}%${color ? `;background:${color}` : ""}"></div></div>
    </div>`).join("");
}

function lineChart(id, labels, series, opts = {}) {
  // Eksen adları, birim ve legend zorunlu hale getirildi: eksende ne olduğu
  // yazmayan bir grafik "52.2" gibi anlamsız sayılar gösteriyordu.
  const W = 620, H = opts.height || 230;
  const L = opts.yAxisLabel ? 62 : 48;   // sol boşluk: y ekseni adı için yer
  const R = 16, T = 16, B = opts.xAxisLabel ? 48 : 32;

  const all = series.flatMap(s => s.values).filter(v => Number.isFinite(v));
  if (!all.length) {
    document.getElementById(id).innerHTML = ui.empty("Grafik için veri yok.");
    return;
  }
  const lo = opts.min ?? Math.min(...all) * 0.9;
  const hi = opts.max ?? Math.max(...all) * 1.05;
  const x = i => L + i * (W - L - R) / Math.max(1, labels.length - 1);
  const y = v => T + (hi - v) / (hi - lo || 1) * (H - T - B);
  const fmtY = opts.yfmt || (v => Math.round(v));

  let svg = "";
  // Yatay ızgara + y ekseni değerleri
  for (let g = 0; g <= 4; g++) {
    const v = lo + (hi - lo) * g / 4;
    svg += `<line class="grid" x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}"/>` +
           `<text x="${L - 8}" y="${y(v) + 3}" text-anchor="end">${fmtY(v)}</text>`;
  }
  // X ekseni etiketleri
  labels.forEach((lab, i) => {
    svg += `<text x="${x(i)}" y="${H - (opts.xAxisLabel ? 26 : 10)}" text-anchor="middle">${fmt.esc(lab)}</text>`;
  });
  // Eksen adları
  if (opts.yAxisLabel) {
    svg += `<text class="axis-title" transform="rotate(-90 14 ${H / 2})" x="14" y="${H / 2}" ` +
           `text-anchor="middle">${fmt.esc(opts.yAxisLabel)}</text>`;
  }
  if (opts.xAxisLabel) {
    svg += `<text class="axis-title" x="${(L + W - R) / 2}" y="${H - 6}" ` +
           `text-anchor="middle">${fmt.esc(opts.xAxisLabel)}</text>`;
  }
  // Seriler
  series.forEach(sr => {
    const pts = sr.values.map((v, i) => Number.isFinite(v) ? `${x(i)},${y(v)}` : null).filter(Boolean);
    svg += `<polyline fill="none" stroke="${sr.color}" stroke-width="2.2" points="${pts.join(" ")}"/>`;
    sr.values.forEach((v, i) => {
      if (!Number.isFinite(v)) return;
      // Tooltip: seri adı + dönem + değer + birim. Çıplak sayı bırakılmıyor.
      const tip = `${sr.label} · ${labels[i]}: ${fmtY(v)}${opts.unitSuffix || ""}`;
      svg += `<circle cx="${x(i)}" cy="${y(v)}" r="3.8" fill="${sr.color}" ` +
             `stroke="var(--surface)" stroke-width="1.5"><title>${fmt.esc(tip)}</title></circle>`;
    });
  });

  const legend = `<div class="legend">` + series.map(sr =>
    `<span><span class="swatch" style="background:${sr.color}"></span>${fmt.esc(sr.label)}</span>`
  ).join("") + (opts.periodNote ? `<span class="period-note">${fmt.esc(opts.periodNote)}</span>` : "") + `</div>`;

  document.getElementById(id).innerHTML =
    `<svg class="chart" viewBox="0 0 ${W} ${H}">${svg}</svg>` + legend;
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
