// Yönetim Panosu — yönetici özeti.
//
// TASARIM İLKESİ
// --------------
// Pano bir ayrıntı sayfası değildir. İlk açılışta YALNIZCA üniversite geneli
// gösterilir; hiçbir fakülte, bölüm veya program listesi yüklenmez. Kullanıcı
// ayrıntıya "İnceleme kapsamı" seçicisiyle üniversite → fakülte → bölüm →
// program sırasıyla iner ve her seviyede yalnızca o seviyenin verisi çekilir.
//
// Bütün sayılar backend'den gelir; bu dosyada gömülü veri yoktur.

const CURRENT_YEAR = "2025-2026";

// Panonun o an baktığı kapsam. Tek bir yerde tutuluyor: iki ayrı yerde
// saklanan kapsam er ya da geç birbirinden ayrılır.
const scope = {
  facultyId: null,
  facultyName: null,
  departmentId: null,
  departmentName: null,
  programId: null,
  programName: null,

  get level() {
    if (this.programId) return "program";
    if (this.departmentId) return "department";
    if (this.facultyId) return "faculty";
    return "university";
  },

  /** Breadcrumb parçaları — başlıkta ve kapsam çubuğunda aynı kaynaktan gelir. */
  get trail() {
    const parts = ["Üniversite Geneli"];
    if (this.facultyName) parts.push(this.facultyName);
    if (this.departmentName) parts.push(this.departmentName);
    if (this.programName) parts.push(this.programName);
    return parts;
  },

  get label() {
    return this.trail.join(" › ");
  },

  reset() {
    this.facultyId = this.facultyName = null;
    this.departmentId = this.departmentName = null;
    this.programId = this.programName = null;
  },

  /** Analitik uç noktalarının beklediği sorgu parametreleri. */
  params(extra = {}) {
    const q = { ...extra };
    if (this.facultyId) q.faculty_id = this.facultyId;
    if (this.departmentId) q.department_id = this.departmentId;
    if (this.programId) q.academic_program_id = this.programId;
    return q;
  },
};

VIEWS["dashboard"] = {
  title: "Yönetim Panosu",
  subtitle: "Üniversite Geneli · 2025-2026 akademik yılı",
  html: () => `
    <div id="scopePicker"></div>
    <div id="dashBody"></div>
    <footer class="demo" id="dataNote"></footer>`,

  async init() {
    scope.reset();
    await renderScopePicker();
    await renderDashboard();

    document.getElementById("dataNote").innerHTML =
      "Tüm rakamlar veritabanından canlı okunur. Veri seti kurgusaldır ve " +
      "gerçek bir kurumun verisi değildir.";
  },
};

/* ==================================================================
   İnceleme kapsamı seçicisi
   ================================================================== */

async function renderScopePicker() {
  const el = document.getElementById("scopePicker");
  if (!el) return;

  const faculties = await ref.faculties();

  el.innerHTML = `
    <div class="scope-bar">
      <div class="scope-fields">
        <label class="f">İnceleme kapsamı
          <select data-scope="faculty">
            <option value="">Üniversite Geneli</option>
            ${optionsHtml(faculties)}
          </select>
        </label>
        <span data-scope="departmentSlot"></span>
        <span data-scope="programSlot"></span>
      </div>
      <button class="ghost" data-scope="reset" hidden>Üniversite Geneline Dön</button>
    </div>
    <div class="breadcrumb" data-scope="crumbs"></div>`;

  el.querySelector('[data-scope="faculty"]').addEventListener("change", (e) =>
    setScope({ facultyId: e.target.value ? Number(e.target.value) : null })
  );
  el.querySelector('[data-scope="reset"]').addEventListener("click", () => setScope({}));

  await refreshScopeControls();
}

/**
 * Kapsamı değiştirir ve panoyu yeniden çizer.
 * Üst seviye değişince alt seviyeler sıfırlanır: fakülte değiştiğinde eski
 * bölüm seçimi anlamsızdır ve yanlış veriyi gösterirdi.
 */
async function setScope({ facultyId = null, departmentId = null, programId = null }) {
  const faculties = await ref.faculties();
  scope.reset();

  if (facultyId) {
    const faculty = faculties.find((f) => f.id === facultyId);
    scope.facultyId = facultyId;
    scope.facultyName = faculty ? faculty.name : null;
  }
  if (facultyId && departmentId) {
    const department = (await ref.departments()).find((d) => d.id === departmentId);
    scope.departmentId = departmentId;
    scope.departmentName = department ? department.name : null;
  }
  if (departmentId && programId) {
    const program = (await ref.programs()).find((p) => p.id === programId);
    scope.programId = programId;
    scope.programName = program ? program.name : null;
  }

  await refreshScopeControls();
  await renderDashboard();
}

/**
 * Seçim alanlarını kapsamla eşitler.
 * Bölüm alanı fakülte seçilmeden, program alanı bölüm seçilmeden ÇİZİLMEZ —
 * pasif bir alan bile kullanıcıya "burada bir şey seçebilirim" izlenimi verir.
 */
async function refreshScopeControls() {
  const el = document.getElementById("scopePicker");
  if (!el) return;

  const facultySelect = el.querySelector('[data-scope="faculty"]');
  if (facultySelect) facultySelect.value = scope.facultyId || "";

  const departmentSlot = el.querySelector('[data-scope="departmentSlot"]');
  if (!scope.facultyId) {
    departmentSlot.innerHTML = "";
  } else {
    const rows = (await ref.departments()).filter((d) => d.faculty_id === scope.facultyId);
    departmentSlot.innerHTML = `
      <label class="f">Bölüm
        <select data-scope="department">
          <option value="">Fakültenin tamamı</option>
          ${optionsHtml(rows, { selected: scope.departmentId })}
        </select>
      </label>`;
    departmentSlot.querySelector("select").addEventListener("change", (e) =>
      setScope({
        facultyId: scope.facultyId,
        departmentId: e.target.value ? Number(e.target.value) : null,
      })
    );
  }

  const programSlot = el.querySelector('[data-scope="programSlot"]');
  if (!scope.departmentId) {
    programSlot.innerHTML = "";
  } else {
    const rows = (await ref.programs()).filter((p) => p.department_id === scope.departmentId);
    programSlot.innerHTML = `
      <label class="f">Program
        <select data-scope="program">
          <option value="">Bölümün tamamı</option>
          ${optionsHtml(rows, { selected: scope.programId })}
        </select>
      </label>`;
    programSlot.querySelector("select").addEventListener("change", (e) =>
      setScope({
        facultyId: scope.facultyId,
        departmentId: scope.departmentId,
        programId: e.target.value ? Number(e.target.value) : null,
      })
    );
  }

  el.querySelector('[data-scope="reset"]').hidden = scope.level === "university";

  // Breadcrumb: tıklanabilir üst seviyeler + pasif son seviye.
  const crumbs = el.querySelector('[data-scope="crumbs"]');
  const trail = scope.trail;
  crumbs.innerHTML = trail
    .map((part, i) => {
      const last = i === trail.length - 1;
      return last
        ? `<span class="crumb current">${fmt.esc(part)}</span>`
        : `<a href="#" class="crumb" data-crumb="${i}">${fmt.esc(part)}</a>`;
    })
    .join('<span class="crumb-sep">›</span>');
  crumbs.querySelectorAll("[data-crumb]").forEach((a) =>
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const depth = Number(a.dataset.crumb);
      if (depth === 0) setScope({});
      else if (depth === 1) setScope({ facultyId: scope.facultyId });
      else setScope({ facultyId: scope.facultyId, departmentId: scope.departmentId });
    })
  );

  const sub = document.getElementById("pageSub");
  if (sub) sub.textContent = `${scope.label} · ${CURRENT_YEAR} akademik yılı`;
}

/* ==================================================================
   Pano gövdesi — kapsam seviyesine göre farklı bölümler
   ================================================================== */

async function renderDashboard() {
  const body = document.getElementById("dashBody");
  if (!body) return;

  const universityOnly = scope.level === "university";

  body.innerHTML = `
    <div id="dashCards"></div>

    <div class="grid cols-3-2">
      <div class="card">
        <h3>Kurumsal eğilim</h3>
        <div class="note">Son yıllarda öğrenci doluluğu ve mezuniyet oranı.</div>
        <div id="dashTrend"></div>
      </div>
      <div class="card">
        <h3>En önemli gelişmeler</h3>
        <div class="note">Geçen yıla göre en belirgin değişimler.</div>
        <div id="dashHighlights"></div>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>${universityOnly ? "Gelir ve gider özeti" : "Mali durum"}</h3>
        <div class="note">Milyon USD · ${CURRENT_YEAR}</div>
        <div id="dashFinance"></div>
      </div>
      <div class="card">
        <h3>Öncelikli riskler</h3>
        <div class="note">Kural motorunun ürettiği aktif uyarılar.</div>
        <div id="dashRisks"></div>
      </div>
    </div>

    ${
      universityOnly
        ? `<div class="card">
             <h3>Fakülte karşılaştırması</h3>
             <div class="note">Bir fakülteye tıklayınca pano o fakülteye geçer.</div>
             <div id="dashFaculties"></div>
           </div>`
        : `<div class="card">
             <h3>${
               scope.level === "faculty"
                 ? "Fakülte içindeki bölümlerin mali karşılaştırması"
                 : "Birim ayrıntısı"
             }</h3>
             <div class="note">Milyon USD · tek satırda gelir, gider ve net.</div>
             <div id="dashUnits"></div>
           </div>`
    }`;

  // Kademeli yükleme: her bölüm kendi isteğini yapar, biri yavaşsa diğerleri bekler değil.
  loadSummaryCards();
  loadTrend();
  loadHighlights();
  loadFinance();
  loadRisks();
  if (universityOnly) loadFacultyComparison();
  else loadUnitComparison();
}

/* ---------------- A. Üst özet kartları ---------------- */

// Kart → gideceği ayrıntı sayfası. Panodaki her sayı bir kapıdır.
const CARD_ROUTES = {
  students: "students",
  staff: "staff",
  revenue: "finance",
  expenditure: "finance",
  success: "success",
  risks: "alerts",
};

async function loadSummaryCards() {
  await load(
    "dashCards",
    async () => {
      // Bir uç nokta cevap vermezse pano çökmesin; eksik kart "—" gösterir.
      const settle = (p) => p.then((v) => v).catch(() => null);
      const [students, staff, finance, success, alerts] = await Promise.all([
        settle(api.get("/api/student-analytics/overview", scope.params())),
        settle(
          api.get("/api/academic-staff/overview", {
            ...(scope.facultyId ? { faculty_id: scope.facultyId } : {}),
            ...(scope.departmentId ? { department_id: scope.departmentId } : {}),
          })
        ),
        settle(api.get(`/api/finance/${CURRENT_YEAR}/summary`)),
        settle(api.get("/api/academic-success/overview", { academic_year: CURRENT_YEAR })),
        settle(api.get("/api/early-warning/alerts", { academic_year: CURRENT_YEAR })),
      ]);
      return { students, staff, finance, success, alerts };
    },
    ({ students, staff, finance, success, alerts }, el) => {
      const criticalCount = Array.isArray(alerts)
        ? alerts.filter((a) => a.severity === "kritik" || a.severity === "yuksek").length
        : null;

      // Üniversite genelinde 6 kart; alt kapsamda mali toplamlar kurum geneline
      // ait olduğu için gösterilmez (yanlış okumaya yol açardı).
      const cards = [
        ["students", "Toplam öğrenci", students ? fmt.int(students.total_students) : fmt.empty,
          students ? `${fmt.int(students.active_students)} aktif` : ""],
        ["staff", "Akademik personel", staff ? fmt.int(staff.total_staff) : fmt.empty,
          staff ? `${fmt.int(staff.total_publication)} yayın` : ""],
      ];

      if (scope.level === "university") {
        cards.push(
          ["revenue", "Yıllık gelir", finance ? fmt.usdMillion(finance.total_revenue) : fmt.empty,
            finance ? `öğrenci başına ${fmt.usdPerPerson(finance.revenue_per_student_thousand_usd)}` : ""],
          ["expenditure", "Yıllık gider", finance ? fmt.usdMillion(finance.total_expenditure) : fmt.empty,
            finance ? `denge ${fmt.usdMillion(finance.balance)}` : ""],
          ["success", "Genel başarı oranı",
            success ? fmt.pct(success.course_pass_rate) : fmt.empty,
            success ? `mezuniyet ${fmt.pct(success.graduation_rate)}` : ""],
          ["risks", "Kritik risk sayısı",
            criticalCount === null ? fmt.empty : fmt.int(criticalCount),
            Array.isArray(alerts) ? `toplam ${alerts.length} uyarı` : ""]
        );
      } else {
        cards.push(
          ["success", "Doluluk oranı",
            students ? fmt.pct(students.average_occupancy_rate) : fmt.empty,
            students ? `mezuniyet ${fmt.pct(students.graduation_rate)}` : ""],
          ["risks", "Bu kapsamdaki uyarılar",
            criticalCount === null ? fmt.empty : fmt.int(criticalCount),
            "kritik ve yüksek"]
        );
      }

      el.className = "tiles clickable";
      el.innerHTML = cards
        .map(
          ([key, label, value, note]) =>
            `<a class="tile" href="#/${CARD_ROUTES[key]}" data-card="${key}">
               <div class="label">${fmt.esc(label)}</div>
               <div class="value">${value}</div>
               ${note ? `<div class="delta">${fmt.esc(note)}</div>` : ""}
               <span class="tile-go">ayrıntıya git →</span>
             </a>`
        )
        .join("");
    }
  );
}

/* ---------------- B. Kurumsal eğilim ---------------- */

async function loadTrend() {
  await load(
    "dashTrend",
    async () => {
      const [occupancy, graduation] = await Promise.all([
        api.get("/api/student-analytics/trends", scope.params({ metric: "occupancy-rate" })),
        api.get("/api/student-analytics/trends", scope.params({ metric: "graduation-rate" })),
      ]);
      return { occupancy, graduation };
    },
    ({ occupancy, graduation }, el) => {
      const points = occupancy.points || occupancy.data_points || [];
      if (!points.length) {
        el.innerHTML = ui.empty("Bu kapsam için eğilim verisi yok.");
        return;
      }
      const labels = points.map((p) => p.label || p.academic_year || String(p.year));
      const gradPoints = graduation.points || graduation.data_points || [];

      el.id = "dashTrendChart";
      // lineChart legend'ı KENDİSİ çiziyor. Eskiden bir de elle legend
      // ekleniyordu ve aynı açıklama iki kez görünüyordu.
      lineChart(
        "dashTrendChart",
        labels,
        [
          { label: "Doluluk oranı", color: "var(--primary)", values: points.map((p) => Number(p.value) || 0) },
          {
            label: "Mezuniyet oranı",
            color: "var(--accent)",
            values: labels.map((_, i) => Number(gradPoints[i]?.value) || 0),
          },
        ],
        {
          min: 0,
          max: 100,
          yfmt: (v) => Math.round(v) + "%",
          yAxisLabel: "Oran (%)",
          xAxisLabel: "Akademik yıl",
          unitSuffix: "%",
        }
      );
    }
  );
}

/* ---------------- C. En önemli gelişmeler ---------------- */

async function loadHighlights() {
  await load(
    "dashHighlights",
    async () => {
      const settle = (p) => p.then((v) => v).catch(() => null);
      const [finance, success, alerts] = await Promise.all([
        settle(api.get("/api/finance/trend")),
        settle(api.get("/api/academic-success/overview", { academic_year: CURRENT_YEAR })),
        settle(api.get("/api/early-warning/alerts", { academic_year: CURRENT_YEAR })),
      ]);
      return { finance, success, alerts };
    },
    ({ finance, success, alerts }, el) => {
      const good = [];
      const bad = [];

      const push = (list, text) => {
        if (list.length < 3) list.push(text);
      };

      // Mali gelişme
      if (Array.isArray(finance) && finance.length) {
        const last = finance[finance.length - 1];
        const change = Number(last.revenue_change_percent);
        if (Number.isFinite(change)) {
          const text = `Gelir geçen yıla göre ${fmt.pct(Math.abs(change))} ${
            change >= 0 ? "arttı" : "azaldı"
          }`;
          change >= 0 ? push(good, text) : push(bad, text);
        }
        const balance = Number(last.balance);
        if (Number.isFinite(balance)) {
          const text = `Gelir–gider dengesi ${fmt.usdMillion(last.balance)}`;
          balance >= 0 ? push(good, text) : push(bad, text);
        }
      }

      // Akademik gelişme
      if (success) {
        const passChange = Number(success.course_pass_rate_change);
        if (Number.isFinite(passChange) && Math.abs(passChange) >= 0.1) {
          const text = `Ders geçme oranı ${fmt.pct(Math.abs(passChange))} ${
            passChange >= 0 ? "yükseldi" : "geriledi"
          }`;
          passChange >= 0 ? push(good, text) : push(bad, text);
        }
        const dropChange = Number(success.dropout_rate_change);
        if (Number.isFinite(dropChange) && Math.abs(dropChange) >= 0.1) {
          const text = `Bırakma oranı ${fmt.pct(Math.abs(dropChange))} ${
            dropChange <= 0 ? "azaldı" : "arttı"
          }`;
          dropChange <= 0 ? push(good, text) : push(bad, text);
        }
      }

      // Risk tarafı
      if (Array.isArray(alerts)) {
        const byCategory = groupAlertsByCategory(alerts);
        byCategory.slice(0, 2).forEach((row) =>
          push(bad, `${row.category}: ${row.count} açık uyarı`)
        );
      }

      const list = (items, cls, emptyText) =>
        items.length
          ? `<ul class="plain highlight-list ${cls}">${items
              .map((t) => `<li>${fmt.esc(t)}</li>`)
              .join("")}</ul>`
          : `<div class="note">${fmt.esc(emptyText)}</div>`;

      el.innerHTML = `
        <h4 class="highlight-head good">Olumlu</h4>
        ${list(good, "good", "Bu dönem öne çıkan olumlu değişim ölçülmedi.")}
        <h4 class="highlight-head warn">Dikkat</h4>
        ${list(bad, "warn", "Dikkat gerektiren bir değişim bulunmuyor.")}`;
    }
  );
}

/* ---------------- Gelir ve gider ---------------- */

async function loadFinance() {
  if (scope.level === "university") {
    // Üniversite genelinde bölüm satırları YÜKLENMEZ; yalnızca kurumsal özet
    // ve beş yıllık eğilim çekilir.
    await load(
      "dashFinance",
      async () => {
        const [summary, trend] = await Promise.all([
          api.get(`/api/finance/${CURRENT_YEAR}/summary`),
          api.get("/api/finance/trend"),
        ]);
        return { summary, trend };
      },
      ({ summary, trend }, el) => {
        const last = trend[trend.length - 1] || {};
        const change = Number(last.revenue_change_percent);

        el.innerHTML = `
          <div class="mini-figures">
            <div><span>Toplam gelir</span><b>${fmt.usdMillion(summary.total_revenue)}</b></div>
            <div><span>Toplam gider</span><b>${fmt.usdMillion(summary.total_expenditure)}</b></div>
            <div><span>Net bütçe</span><b class="${
              Number(summary.balance) >= 0 ? "pos" : "neg"
            }">${fmt.usdMillion(summary.balance)}</b></div>
            <div><span>Geçen yıla göre gelir</span><b>${
              Number.isFinite(change) ? (change >= 0 ? "+" : "") + fmt.pct(change) : fmt.empty
            }</b></div>
          </div>
          <div id="dashFinanceChart"></div>`;

        lineChart(
          "dashFinanceChart",
          trend.map((r) => r.academic_year),
          [
            { label: "Gelir", color: "var(--primary)", values: trend.map((r) => Number(r.total_revenue)) },
            { label: "Gider", color: "var(--accent)", values: trend.map((r) => Number(r.total_expenditure)) },
          ],
          {
            height: 190,
            yfmt: (v) => "$" + v.toFixed(0) + "M",
            yAxisLabel: "Milyon USD",
            xAxisLabel: "Akademik yıl",
            unitSuffix: " milyon USD",
          }
        );
      }
    );
    return;
  }

  // Fakülte veya bölüm kapsamı: yalnızca ilgili birimlerin satırları.
  await load(
    "dashFinance",
    () => api.get(`/api/finance/${CURRENT_YEAR}/departments`),
    async (rows, el) => {
      const mine = await filterDepartmentRows(rows);
      if (!mine.length) {
        el.innerHTML = ui.empty("Bu kapsam için bütçe girilmemiş.");
        return;
      }
      const revenue = mine.reduce((a, r) => a + Number(r.revenue || 0), 0);
      const expenditure = mine.reduce((a, r) => a + Number(r.expenditure || 0), 0);
      el.innerHTML = `
        <div class="mini-figures">
          <div><span>Gelir</span><b>${fmt.usdMillion(revenue)}</b></div>
          <div><span>Gider</span><b>${fmt.usdMillion(expenditure)}</b></div>
          <div><span>Net</span><b class="${revenue - expenditure >= 0 ? "pos" : "neg"}">${fmt.usdMillion(
            revenue - expenditure
          )}</b></div>
          <div><span>Birim sayısı</span><b>${fmt.int(mine.length)}</b></div>
        </div>`;
    }
  );
}

/**
 * Kapsamdaki bölüm bütçesi satırlarını süzer.
 *
 * Süzme ADA göre değil KİMLİĞE göre yapılır: bütçe uç noktası birim adını
 * veritabanındaki haliyle döndürüyor, arayüz ise Türkçe karşılığını gösteriyor.
 * Ad karşılaştırması bu yüzden hiçbir satırı eşleştiremezdi.
 */
async function filterDepartmentRows(rows) {
  if (!Array.isArray(rows)) return [];
  if (scope.departmentId) return rows.filter((r) => r.department_id === scope.departmentId);
  if (scope.facultyId) {
    const ids = new Set(
      (await ref.departments())
        .filter((d) => d.faculty_id === scope.facultyId)
        .map((d) => d.id)
    );
    return rows.filter((r) => ids.has(r.department_id));
  }
  return rows;
}

/* ---------------- D. Öncelikli riskler ---------------- */

const SEVERITY_ORDER = { kritik: 0, yuksek: 1, yüksek: 1, orta: 2, dusuk: 3, düşük: 3 };
const SEVERITY_LABELS = {
  kritik: "Kritik",
  yuksek: "Yüksek",
  yüksek: "Yüksek",
  orta: "Orta",
  dusuk: "Düşük",
  düşük: "Düşük",
};
const DASHBOARD_RISK_LIMIT = 5;

/** Uyarıları kategoriye göre sayar; en kalabalık kategori başta. */
function groupAlertsByCategory(alerts) {
  const counts = new Map();
  alerts.forEach((a) => {
    const key = a.risk_category || "Diğer riskler";
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return [...counts.entries()]
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count);
}

async function loadRisks() {
  await load(
    "dashRisks",
    () => api.get("/api/early-warning/alerts", { academic_year: CURRENT_YEAR }),
    (alerts, el) => {
      const mine = scope.programName
        ? alerts.filter((a) => a.scope_name === scope.programName)
        : alerts;

      if (!mine.length) {
        el.innerHTML = ui.empty("Bu kapsam için açık uyarı yok.");
        return;
      }

      const categories = groupAlertsByCategory(mine);
      const sorted = [...mine].sort(
        (a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
      );
      const top = sorted.slice(0, DASHBOARD_RISK_LIMIT);

      const levelClass = (s) =>
        s === "kritik" ? "critical" : s === "yuksek" || s === "yüksek" ? "warning" : "info";

      el.innerHTML = `
        <table class="risk-summary"><tbody>${categories
          .map(
            (row) =>
              `<tr><td>${fmt.esc(row.category)}</td><td class="num">${fmt.int(row.count)}</td></tr>`
          )
          .join("")}</tbody></table>

        <h4>En kritik ${top.length} kayıt</h4>
        <ul class="plain risk-list">${top
          .map(
            (a) => `<li>
              <div class="risk-title">${fmt.esc(a.rule_name)}</div>
              <div class="risk-meta">
                <span>Etkilenen alan: <b>${fmt.esc(a.scope_name)}</b></span>
                <span>${chip(levelClass(a.severity), SEVERITY_LABELS[a.severity] || a.severity)}</span>
              </div>
            </li>`
          )
          .join("")}</ul>

        <a class="ghost-link" href="#/alerts" data-risk="all">Tüm ${mine.length} riski incele →</a>`;
    }
  );
}

/* ---------------- Fakülte karşılaştırması (üniversite geneli) ---------------- */

async function loadFacultyComparison() {
  await load(
    "dashFaculties",
    () => api.get("/api/student-analytics/by-faculty"),
    async (rows, el) => {
      if (!Array.isArray(rows) || !rows.length) {
        el.innerHTML = ui.empty("Fakülte verisi bulunamadı.");
        return;
      }
      const faculties = await ref.faculties();
      const nameById = new Map(faculties.map((f) => [f.id, f.name]));

      el.innerHTML = `<div class="table-wrap"><table>
        <thead><tr>
          <th>Fakülte</th><th class="num">Öğrenci</th>
          <th class="num">Doluluk</th><th class="num">Mezuniyet</th><th class="num">Bölüm</th>
        </tr></thead>
        <tbody>${rows
          .map(
            (r) => `<tr data-faculty="${r.faculty_id}" class="row-link">
              <td>${fmt.esc(nameById.get(r.faculty_id) || r.faculty_name)}</td>
              <td class="num">${fmt.int(r.total_students)}</td>
              <td class="num">${fmt.pct(r.average_occupancy_rate)}</td>
              <td class="num">${fmt.pct(r.graduation_rate)}</td>
              <td class="num">${fmt.int(r.department_count)}</td>
            </tr>`
          )
          .join("")}</tbody></table></div>`;

      el.querySelectorAll("[data-faculty]").forEach((tr) =>
        tr.addEventListener("click", () => setScope({ facultyId: Number(tr.dataset.faculty) }))
      );
    }
  );
}

/* ---------------- Bölüm karşılaştırması (fakülte kapsamı) ---------------- */

const UNIT_PREVIEW_LIMIT = 5;

async function loadUnitComparison() {
  await load(
    "dashUnits",
    () => api.get(`/api/finance/${CURRENT_YEAR}/departments`),
    async (rows, el) => {
      const mine = await filterDepartmentRows(rows);
      if (!mine.length) {
        el.innerHTML = ui.empty("Bu kapsam için bölüm bütçesi girilmemiş.");
        return;
      }
      const departments = await ref.departments();
      const nameById = new Map(departments.map((d) => [d.id, d.name]));
      const sorted = [...mine].sort((a, b) => Number(b.revenue) - Number(a.revenue));

      // Gelir ve gider aynı bölüm için AYRI SATIR değil, tek satırda yan yana
      // iki çubuk. Eskiden her bölüm iki satır kaplıyor ve liste ikiye katlanıyordu.
      const max = Math.max(
        ...sorted.map((r) => Math.max(Number(r.revenue) || 0, Number(r.expenditure) || 0)),
        1
      );
      const bar = (r) => {
        const name = nameById.get(r.department_id) || r.department_name;
        const revenue = Number(r.revenue) || 0;
        const expenditure = Number(r.expenditure) || 0;
        const net = revenue - expenditure;
        return `<div class="unit-row row-link" data-department="${r.department_id}"
                     title="${fmt.esc(name)} · gelir ${fmt.usdMillion(revenue)} · gider ${fmt.usdMillion(
                       expenditure
                     )}">
          <div class="unit-name">${fmt.esc(name)}</div>
          <div class="unit-bars">
            <div class="pair">
              <div class="track"><div class="fill rev" style="width:${(revenue / max) * 100}%"></div></div>
              <div class="track"><div class="fill exp" style="width:${(expenditure / max) * 100}%"></div></div>
            </div>
          </div>
          <div class="unit-figures">
            <span>Gelir ${fmt.usdMillion(revenue)}</span>
            <span>Gider ${fmt.usdMillion(expenditure)}</span>
            <span class="${net >= 0 ? "pos" : "neg"}">Net ${net >= 0 ? "+" : ""}${fmt.usdMillion(
              net
            )}</span>
          </div>
        </div>`;
      };

      el.innerHTML =
        `<div class="legend">
           <span><span class="swatch" style="background:var(--primary)"></span>Gelir</span>
           <span><span class="swatch" style="background:var(--accent)"></span>Gider</span>
         </div>` +
        sorted.slice(0, UNIT_PREVIEW_LIMIT).map(bar).join("") +
        (sorted.length > UNIT_PREVIEW_LIMIT
          ? ux.details(
              "Tüm bölümleri göster",
              sorted.slice(UNIT_PREVIEW_LIMIT).map(bar).join(""),
              { hint: `${sorted.length - UNIT_PREVIEW_LIMIT} bölüm daha` }
            )
          : "");

      el.querySelectorAll("[data-department]").forEach((row) =>
        row.addEventListener("click", () =>
          setScope({
            facultyId: scope.facultyId,
            departmentId: Number(row.dataset.department),
          })
        )
      );
    }
  );
}
