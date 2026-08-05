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
  async faculties() {
    return (this._cache.faculties ??= api.get("/api/faculties", { limit: 200 }));
  },
  async departments() {
    return (this._cache.departments ??= api.get("/api/departments", { limit: 200 }));
  },
  async programs() {
    return (this._cache.programs ??= api.get("/api/programs", { limit: 200 }));
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
