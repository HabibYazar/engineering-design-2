// API istemcisi — arayüzün backend ile konuştuğu tek yer.
//
// Neden tek dosya: her ekran kendi fetch çağrısını yazsaydı hata gösterimi,
// oturum jetonu ve sayı biçimlendirmesi ekran ekran farklılaşırdı. Burada
// toplanınca "backend kapalıysa ne gösterilecek" sorusu bir kez cevaplanıyor.

const API_BASE = ""; // Arayüz backend ile aynı sunucudan servis edildiği için boş.

/* ==================== oturum ==================== */

const auth = {
  get token() {
    return sessionStorage.getItem("atu-token");
  },
  get user() {
    try {
      return JSON.parse(sessionStorage.getItem("atu-user"));
    } catch {
      return null;
    }
  },
  save(loginResponse) {
    sessionStorage.setItem("atu-token", loginResponse.token);
    sessionStorage.setItem("atu-user", JSON.stringify(loginResponse));
  },
  clear() {
    sessionStorage.removeItem("atu-token");
    sessionStorage.removeItem("atu-user");
  },
  can(permission) {
    const u = auth.user;
    return !!u && Array.isArray(u.permissions) && u.permissions.includes(permission);
  },
};

/* ==================== hata tipi ==================== */

class ApiError extends Error {
  constructor(status, detail, url) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.url = url;
  }
  // Kullanıcıya gösterilecek metin. FastAPI doğrulama hataları dizi döner;
  // ham JSON yerine okunabilir bir cümleye çevriliyor.
  get userMessage() {
    if (Array.isArray(this.detail)) {
      return this.detail
        .map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`)
        .join(" · ");
    }
    return this.detail || `Sunucu ${this.status} döndürdü.`;
  }
}

/* ==================== çekirdek istek ==================== */

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (auth.token) headers["X-Session-Token"] = auth.token;

  let response;
  try {
    response = await fetch(API_BASE + path, { ...options, headers });
  } catch (networkError) {
    // Sunucu çalışmıyorsa fetch reddeder; bunu ayrı bir mesajla ayırt ediyoruz
    // ki kullanıcı "veri yok" ile "sunucu kapalı" durumunu karıştırmasın.
    throw new ApiError(
      0,
      "Sunucuya ulaşılamadı. Backend çalışıyor mu? (python main.py)",
      path
    );
  }

  if (response.status === 204) return null;

  let payload = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail = payload && payload.detail !== undefined ? payload.detail : payload;
    throw new ApiError(response.status, detail, path);
  }
  return payload;
}

const api = {
  get(path, params) {
    const query = params
      ? "?" +
        new URLSearchParams(
          Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
        )
      : "";
    return request(path + query);
  },
  post(path, body) {
    return request(path, { method: "POST", body: JSON.stringify(body) });
  },
  put(path, body) {
    return request(path, { method: "PUT", body: JSON.stringify(body) });
  },
  patch(path, body) {
    return request(path, { method: "PATCH", body: JSON.stringify(body) });
  },
  del(path) {
    return request(path, { method: "DELETE" });
  },
  upload(path, formData) {
    return request(path, { method: "POST", body: formData });
  },
};

/* ==================== biçimlendirme ==================== */
// Backend Decimal değerleri metin olarak döndürür ("486.00"). Bunları
// doğrudan ekrana basmak yerine burada sayıya çevirip biçimlendiriyoruz;
// böylece "47500000" yerine "$47,5M" görünüyor.

const num = (v) => (v === null || v === undefined || v === "" ? null : Number(v));

const fmt = {
  // Boş değeri sıfır gibi göstermemek için tek bir işaret kullanılıyor.
  empty: "—",

  int(v) {
    const n = num(v);
    return n === null || Number.isNaN(n) ? fmt.empty : Math.round(n).toLocaleString("tr-TR");
  },
  dec(v, digits = 2) {
    const n = num(v);
    return n === null || Number.isNaN(n)
      ? fmt.empty
      : n.toLocaleString("tr-TR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  },
  pct(v, digits = 1) {
    const n = num(v);
    return n === null || Number.isNaN(n) ? fmt.empty : fmt.dec(n, digits) + "%";
  },
  // SİSTEMDEKİ TEK PARA BİRİMİ USD'DİR.
  // Büyüklüğe göre otomatik ölçekler: milyonun üstü "$12,3M", binin üstü
  // "$45,2K", altı "$860". Her durumda $ işareti ve birim görünür; çıplak
  // sayı bırakılmaz.
  usd(v, digits = 1) {
    const n = num(v);
    if (n === null || Number.isNaN(n)) return fmt.empty;
    const sign = n < 0 ? "−" : "";
    const a = Math.abs(n);
    if (a >= 1_000_000) return sign + "$" + fmt.dec(a / 1_000_000, digits) + "M";
    if (a >= 1_000) return sign + "$" + fmt.dec(a / 1_000, digits) + "K";
    return sign + "$" + fmt.dec(a, 0);
  },
  // Mali tablolarda saklanan değer MİLYON USD'dir; olduğu gibi gösterilir.
  usdMillion(v, digits = 2) {
    const n = num(v);
    return n === null || Number.isNaN(n) ? fmt.empty : "$" + fmt.dec(n, digits) + "M";
  },
  // Kişi başına oranlar tam USD cinsindendir.
  usdPerPerson(v) {
    const n = num(v);
    return n === null || Number.isNaN(n) ? fmt.empty : "$" + fmt.dec(n, 0);
  },
  // Değişim oranı: işaret ve yön oku ile.
  delta(v, { goodWhenUp = true, suffix = "%" } = {}) {
    const n = num(v);
    if (n === null || Number.isNaN(n)) return { text: "", dir: "" };
    const up = n >= 0;
    return {
      text: (up ? "▲ +" : "▼ ") + fmt.dec(Math.abs(n), 1) + suffix,
      dir: up === goodWhenUp ? "up" : "down",
    };
  },
  esc(text) {
    return String(text ?? "").replace(/[&<>"']/g, (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
    );
  },
};

/* ==================== durum gösterimi ==================== */

const ui = {
  // Yükleniyor iskeleti. Ekran boş kalmasın diye her veri kutusu bununla başlar.
  loading(message = "Veriler yükleniyor…") {
    return `<div class="state loading"><span class="spinner"></span>${fmt.esc(message)}</div>`;
  },

  // Hata kutusu. Sebebi gizlemek yerine ne olduğunu ve ne yapılacağını yazar.
  error(err, retryHandlerId) {
    const isDown = err instanceof ApiError && err.status === 0;
    const isMissing = err instanceof ApiError && err.status === 404;
    const title = isDown
      ? "Sunucuya bağlanılamadı"
      : isMissing
      ? "Bu görünüm için veri bulunamadı"
      : "İstek başarısız";
    const hint = isDown
      ? "Backend'i başlatın: <code>python main.py</code> (veya run_project.ps1)."
      : isMissing
      ? "Ortak demo verisini yükleyin: <code>python seed_all_demo_data.py</code>."
      : "";
    return `<div class="state error">
        <b>${title}</b>
        <div class="msg">${fmt.esc(err.userMessage || err.message)}</div>
        ${hint ? `<div class="hint">${hint}</div>` : ""}
        ${retryHandlerId ? `<button class="ghost" id="${retryHandlerId}">Tekrar dene</button>` : ""}
      </div>`;
  },

  // Veri gerçekten boşsa (hata değil) gösterilir.
  empty(message = "Gösterilecek kayıt yok.") {
    return `<div class="state empty">${fmt.esc(message)}</div>`;
  },

  // Kısa bildirim.
  toast(message, kind = "success") {
    let area = document.getElementById("toastArea");
    if (!area) {
      area = document.createElement("div");
      area.id = "toastArea";
      area.className = "toast-area";
      document.body.appendChild(area);
    }
    const el = document.createElement("div");
    el.className = "toast toast-" + kind;
    el.innerHTML = fmt.esc(message);
    area.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  },
};

/* ==================== ekran yükleme yardımcısı ==================== */

// Bir kabı önce "yükleniyor" durumuna alır, veriyi çeker, sonra render eder.
// Hata olursa kırmızı kutu ve tekrar dene düğmesi basar.
async function load(containerId, fetcher, renderer) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = ui.loading();
  try {
    const data = await fetcher();
    el.innerHTML = "";
    renderer(data, el);
  } catch (err) {
    const retryId = containerId + "Retry";
    el.innerHTML = ui.error(err, retryId);
    const btn = document.getElementById(retryId);
    if (btn) btn.addEventListener("click", () => load(containerId, fetcher, renderer));
  }
}

/* ==================== ortak referans verisi ==================== */
// Fakülte/bölüm/program listeleri birçok ekranda açılır liste doldurmak için
// gerekiyor. Her ekranda yeniden çekmemek için bir kez alınıp saklanıyor.

const ref = {
  _cache: {},

  // Veritabanındaki fakülte/bölüm/program adları İngilizce ve modül kodlarıyla
  // eşleşiyor; değiştirmek modüller arası eşleşmeyi bozardı. Bu yüzden görünen
  // Türkçe adlar backend'deki sözlükten okunur ve listeler burada, TEK YERDE
  // çevrilir. Böylece hiçbir ekran kendi çeviri tablosunu taşımaz.
  async displayNames() {
    return (this._cache.displayNames ??= api
      .get("/api/reference/display-names")
      .catch(() => ({ faculties: {}, departments: {}, programs: {} })));
  },

  async _translate(rows, kind) {
    const names = await this.displayNames();
    const table = (names && names[kind]) || {};
    return rows.map((r) => ({ ...r, name: table[r.code] || r.name }));
  },

  /** Kod verilerek Türkçe ad döndürür; karşılığı yoksa yedek metni kullanır. */
  async orgName(code, fallback = "") {
    if (!code) return fallback;
    const names = await this.displayNames();
    for (const kind of ["programs", "departments", "faculties"]) {
      const hit = names && names[kind] && names[kind][code];
      if (hit) return hit;
    }
    return fallback || code;
  },

  async faculties() {
    return (this._cache.faculties ??= api
      .get("/api/faculties", { limit: 200 })
      .then((rows) => this._translate(rows, "faculties")));
  },
  async departments() {
    return (this._cache.departments ??= api
      .get("/api/departments", { limit: 200 })
      .then((rows) => this._translate(rows, "departments")));
  },
  async programs() {
    return (this._cache.programs ??= api
      .get("/api/programs", { limit: 200 })
      .then((rows) => this._translate(rows, "programs")));
  },
  async academicYears() {
    return (this._cache.years ??= api.get("/api/education-analytics/academic-years"));
  },
  clear() {
    this._cache = {};
  },
};

// Açılır liste üretir: kullanıcı kimlik yazmak yerine isim seçer.
function optionsHtml(rows, { valueKey = "id", labelKey = "name", selected = null } = {}) {
  return rows
    .map(
      (r) =>
        `<option value="${fmt.esc(r[valueKey])}"${
          String(r[valueKey]) === String(selected) ? " selected" : ""
        }>${fmt.esc(r[labelKey])}</option>`
    )
    .join("");
}

/* ==================== aşamalı gösterim bileşenleri ==================== */
// Yönetici ekranı, veritabanı dökümü gibi görünmemeli. Uzun formüller,
// ağırlık tabloları ve eksik veri listeleri ana ekranda yer almaz; bu
// yardımcılarla kapalı bölümlere taşınır.

const ux = {
  /**
   * Varsayılan olarak KAPALI açılır bölüm.
   * Ana ekranda yalnızca karar için gereken sonuç kalır; yöntem ve teknik
   * ayrıntı isteyen kullanıcı açar.
   */
  details(title, innerHtml, { open = false, hint = "" } = {}) {
    return `<details class="disclosure"${open ? " open" : ""}>
      <summary><span class="disclosure-title">${fmt.esc(title)}</span>${
        hint ? `<span class="disclosure-hint">${fmt.esc(hint)}</span>` : ""
      }</summary>
      <div class="disclosure-body">${innerHtml}</div>
    </details>`;
  },

  /**
   * Sekme yapısı. Sekmeye tıklanana kadar o sekmenin verisi ÇEKİLMEZ;
   * sayfa açılışında tüm detay endpoint'lerini çağırmamak için.
   */
  tabs(containerId, tabList) {
    const buttons = tabList
      .map(
        (t, i) =>
          `<button class="tab-btn${i === 0 ? " is-active" : ""}" data-tab="${t.key}">${fmt.esc(
            t.label
          )}</button>`
      )
      .join("");
    const panels = tabList
      .map(
        (t, i) =>
          `<div class="tab-panel${i === 0 ? " is-active" : ""}" data-panel="${t.key}" id="${containerId}-${t.key}"></div>`
      )
      .join("");
    return `<div class="tabs" id="${containerId}">
      <div class="tab-bar">${buttons}</div>${panels}</div>`;
  },

  /** Sekme davranışını bağlar. onShow(key) yalnızca ilk açılışta çağrılır. */
  bindTabs(containerId, onShow) {
    const root = document.getElementById(containerId);
    if (!root) return;
    const loaded = new Set();

    const activate = (key) => {
      root.querySelectorAll(".tab-btn").forEach((b) =>
        b.classList.toggle("is-active", b.dataset.tab === key)
      );
      root.querySelectorAll(".tab-panel").forEach((p) =>
        p.classList.toggle("is-active", p.dataset.panel === key)
      );
      if (!loaded.has(key)) {
        loaded.add(key);
        onShow(key, `${containerId}-${key}`);
      }
    };

    root.querySelectorAll(".tab-btn").forEach((b) =>
      b.addEventListener("click", () => activate(b.dataset.tab))
    );
    // İlk sekme hemen yüklenir.
    activate(root.querySelector(".tab-btn").dataset.tab);
  },

  /** Yükleme iskeleti — boş ekran yerine yapının önizlemesi. */
  skeleton(rows = 3) {
    return (
      `<div class="skeleton">` +
      Array.from({ length: rows }, () => `<div class="skeleton-row"></div>`).join("") +
      `</div>`
    );
  },

  /**
   * Durum rozeti. Renk ve ikon tek başına kullanılmaz; her zaman
   * yanında ne anlama geldiği yazar.
   */
  statusBadge(kind, text, tooltip = "") {
    const icons = {
      good: "✓",
      warning: "⚠",
      critical: "⚠",
      nodata: "—",
      info: "•",
    };
    return `<span class="status-badge status-${kind}"${
      tooltip ? ` title="${fmt.esc(tooltip)}"` : ""
    }><span class="status-icon">${icons[kind] || ""}</span>${fmt.esc(text)}</span>`;
  },

  /**
   * Sayı + ne olduğu. Çıplak "56,3" yerine "56 / 100" ve altında etiket.
   */
  scoreBlock(value, max, label, note = "") {
    const v = value === null || value === undefined ? null : Number(value);
    return `<div class="score-block">
      <div class="score-value">${
        v === null ? "Veri bulunamadı" : `${fmt.dec(v, 0)}<span class="score-max"> / ${max}</span>`
      }</div>
      <div class="score-label">${fmt.esc(label)}</div>
      ${note ? `<div class="score-note">${note}</div>` : ""}
    </div>`;
  },

  /** Uzun listelerde ilk N kayıt + "devamını göster". */
  limitedList(items, limit, renderRow, moreLabel = "Tümünü göster") {
    if (items.length <= limit) return items.map(renderRow).join("");
    const id = "more-" + Math.random().toString(36).slice(2, 8);
    return (
      items.slice(0, limit).map(renderRow).join("") +
      `<details class="disclosure inline"><summary><span class="disclosure-title">${fmt.esc(
        moreLabel
      )} (${items.length - limit} kayıt daha)</span></summary>` +
      `<div class="disclosure-body">${items.slice(limit).map(renderRow).join("")}</div></details>`
    );
  },
};

/* ==================== hiyerarşik organizasyon filtresi ==================== */
// Fakülte → Bölüm → Program sırası zorunludur. Üst seçim değişince alt
// seçimler sıfırlanır. Sonuçlar "Sonuçları Göster" düğmesine basılınca gelir;
// sayfa açılışında tüm programların hesaplanması beklenmez.

class OrgFilter {
  /**
   * @param {string} containerId  filtrenin çizileceği kap
   * @param {object} options      { withYear, years, defaultYear, onApply, level }
   *   level: "program" | "department" | "faculty"  (en alt seçilebilir seviye)
   */
  constructor(containerId, options) {
    this.containerId = containerId;
    this.opts = Object.assign(
      { withYear: true, years: [], defaultYear: null, level: "program" },
      options
    );
    this.state = { year: this.opts.defaultYear, facultyId: "", departmentId: "", programId: "" };
  }

  async render() {
    const el = document.getElementById(this.containerId);
    if (!el) return;

    const faculties = await ref.faculties();
    this.faculties = faculties;

    const yearField = this.opts.withYear
      ? `<label class="f">Akademik dönem
           <select data-org="year">${this.opts.years
             .map(
               (y) =>
                 `<option${y === this.state.year ? " selected" : ""}>${fmt.esc(y)}</option>`
             )
             .join("")}</select>
         </label>`
      : "";

    const departmentField =
      this.opts.level === "faculty"
        ? ""
        : `<label class="f">Bölüm
             <select data-org="department" disabled>
               <option value="">Önce fakülte seçin</option>
             </select>
           </label>`;

    const programField =
      this.opts.level === "program"
        ? `<label class="f">Program
             <select data-org="program" disabled>
               <option value="">Önce bölüm seçin</option>
             </select>
           </label>`
        : "";

    el.innerHTML = `
      <div class="org-filter">
        ${yearField}
        <label class="f">Fakülte
          <select data-org="faculty">
            <option value="">Üniversite geneli</option>
            ${optionsHtml(faculties)}
          </select>
        </label>
        ${departmentField}
        ${programField}
        <button class="primary" data-org="apply">Sonuçları Göster</button>
      </div>
      <div class="org-scope muted" data-org="scope"></div>`;

    this._bind(el);
    this._updateScopeLabel();
  }

  _bind(el) {
    const get = (name) => el.querySelector(`[data-org="${name}"]`);

    const yearSelect = get("year");
    if (yearSelect) {
      yearSelect.addEventListener("change", () => {
        this.state.year = yearSelect.value;
        this._updateScopeLabel();
      });
    }

    get("faculty").addEventListener("change", async (e) => {
      this.state.facultyId = e.target.value;
      // Üst seçim değişti: alt seçimler sıfırlanır.
      this.state.departmentId = "";
      this.state.programId = "";
      await this._fillDepartments(el);
      this._resetPrograms(el);
      this._updateScopeLabel();
    });

    const departmentSelect = get("department");
    if (departmentSelect) {
      departmentSelect.addEventListener("change", async (e) => {
        this.state.departmentId = e.target.value;
        this.state.programId = "";
        await this._fillPrograms(el);
        this._updateScopeLabel();
      });
    }

    const programSelect = get("program");
    if (programSelect) {
      programSelect.addEventListener("change", (e) => {
        this.state.programId = e.target.value;
        this._updateScopeLabel();
      });
    }

    get("apply").addEventListener("click", () => this.opts.onApply(this.value()));
  }

  async _fillDepartments(el) {
    const select = el.querySelector('[data-org="department"]');
    if (!select) return;
    if (!this.state.facultyId) {
      select.innerHTML = `<option value="">Önce fakülte seçin</option>`;
      select.disabled = true;
      return;
    }
    const all = await ref.departments();
    const rows = all.filter((d) => String(d.faculty_id) === String(this.state.facultyId));
    select.innerHTML =
      `<option value="">Fakültenin tamamı</option>` + optionsHtml(rows);
    select.disabled = false;
  }

  _resetPrograms(el) {
    const select = el.querySelector('[data-org="program"]');
    if (!select) return;
    select.innerHTML = `<option value="">Önce bölüm seçin</option>`;
    select.disabled = true;
  }

  async _fillPrograms(el) {
    const select = el.querySelector('[data-org="program"]');
    if (!select) return;
    if (!this.state.departmentId) {
      this._resetPrograms(el);
      return;
    }
    const all = await ref.programs();
    const rows = all.filter(
      (p) => String(p.department_id) === String(this.state.departmentId)
    );
    select.innerHTML = `<option value="">Bölümün tamamı</option>` + optionsHtml(rows);
    select.disabled = false;
  }

  _updateScopeLabel() {
    const el = document.getElementById(this.containerId);
    const target = el && el.querySelector('[data-org="scope"]');
    if (!target) return;
    const parts = [];
    if (this.state.year) parts.push(this.state.year);
    const faculty = this.faculties.find((f) => String(f.id) === String(this.state.facultyId));
    parts.push(faculty ? faculty.name : "Üniversite geneli");
    if (this.state.departmentId) parts.push("bölüm seçildi");
    if (this.state.programId) parts.push("program seçildi");
    target.textContent = "Seçim: " + parts.join(" › ");
  }

  value() {
    return {
      year: this.state.year,
      facultyId: this.state.facultyId ? Number(this.state.facultyId) : null,
      departmentId: this.state.departmentId ? Number(this.state.departmentId) : null,
      programId: this.state.programId ? Number(this.state.programId) : null,
    };
  }
}
