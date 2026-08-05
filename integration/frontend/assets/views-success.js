// Akademik Başarı ve Sanayi/Bölgesel Katkı ekranları.
//
// Başarı ekranı genelden özele çalışır:
//   Üniversite → Fakülte → Bölüm → Program
// Fakülteye tıklandığında bölümler, bölüme tıklandığında programlar açılır.
// Bütün oranlar sunucuda ağırlıklı ortalamayla hesaplanır; burada hesap yoktur.

/* ==================================================================
   Akademik Başarı
   ================================================================== */

VIEWS["success"] = {
  title: "Akademik Başarı",
  subtitle: "Ders geçme, başarısızlık, öğrenci kaybı ve mezuniyet oranları",
  html: () => `
    <div class="card">
      <div class="filters">
        <label class="f">Akademik dönem <select id="acYear"></select></label>
        <button class="ghost" id="acApply">Uygula</button>
        <span class="muted">Tüm oranlar yüzde (%) cinsindendir.</span>
      </div>
      <div class="note" id="acBreadcrumb"></div>
    </div>

    <div id="acTiles"></div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Dönemlere göre başarı eğilimi</h3>
        <div class="note" id="acTrendScope">Üniversite geneli.</div>
        <div id="acTrend"></div>
      </div>
      <div class="card">
        <h3>Öğrenci sayısı ve öğretmen yükü ile ilişki</h3>
        <div class="note">
          Büyük programlarda başarı düşüyor mu? Akademisyen başına öğrenci
          arttıkça geçme oranı ne oluyor?
        </div>
        <div id="acCorrelation"></div>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>En başarılı birimler</h3>
        <div class="note">Ders geçme oranına göre ilk sıradakiler.</div>
        <div id="acTop"></div>
      </div>
      <div class="card">
        <h3>En düşük başarılı birimler</h3>
        <div class="note">Müdahale önceliği olan birimler.</div>
        <div id="acBottom"></div>
      </div>
    </div>

    <div class="card">
      <h3>Kırılım — fakülte → bölüm → program</h3>
      <div class="note">
        Satıra tıklayarak bir alt seviyeyi açabilirsiniz. Fakülte ve bölüm
        oranları ayrı saklanmaz; program satırlarından öğrenci sayısına göre
        <b>ağırlıklı ortalama</b> ile hesaplanır.
      </div>
      <div id="acDrill"></div>
    </div>`,

  async init() {
    const years = await api.get("/api/academic-success/academic-years");
    const sel = document.getElementById("acYear");
    sel.innerHTML = years.map((y) => `<option>${fmt.esc(y)}</option>`).join("");
    if (years.length) sel.value = years[years.length - 1];

    document.getElementById("acApply").addEventListener("click", () => {
      SUCCESS_SCOPE = { level: "university" };
      refreshSuccess();
    });
    refreshSuccess();
  },
};

// Seçili kırılım seviyesi. Drill-down bu nesne üzerinden yürür.
let SUCCESS_SCOPE = { level: "university" };

function successYear() {
  return document.getElementById("acYear").value;
}

// Başarı göstergelerinin ne anlama geldiği. Çıplak sayı bırakmamak için
// her kartın altında bu açıklama gösterilir.
const SUCCESS_HELP = {
  course_pass_rate: "Alınan derslerin yüzde kaçından geçildiği",
  course_fail_rate: "Alınan derslerin yüzde kaçından kalındığı",
  average_success_score: "100 üzerinden ortalama başarı puanı",
  dropout_rate: "Kaydını sildiren veya yenilemeyen öğrenci oranı",
  graduation_rate: "Kohortun yüzde kaçının mezun olduğu",
};

function successTiles(o, containerId) {
  const el = document.getElementById(containerId);
  el.className = "tiles";

  const card = (label, value, changeKey, help, goodWhenUp) => {
    const change = o[changeKey];
    let delta = "geçen dönem verisi yok";
    let dir = "";
    if (change !== null && change !== undefined) {
      const up = Number(change) >= 0;
      const improved = up === goodWhenUp;
      delta = `${up ? "▲ +" : "▼ "}${fmt.dec(Math.abs(Number(change)), 2)} puan · ${
        improved ? "iyileşme" : "kötüleşme"
      }`;
      dir = improved ? "up" : "down";
    }
    return `<div class="tile" title="${fmt.esc(help)}">
      <div class="label">${fmt.esc(label)}</div>
      <div class="value">${value}</div>
      <div class="delta ${dir}">${fmt.esc(delta)}</div>
    </div>`;
  };

  el.innerHTML =
    card("Ders geçme oranı", fmt.pct(o.course_pass_rate), "course_pass_rate_change",
         SUCCESS_HELP.course_pass_rate, true) +
    card("Ders başarısızlık oranı", fmt.pct(o.course_fail_rate), "course_pass_rate_change",
         SUCCESS_HELP.course_fail_rate, false) +
    card("Ortalama başarı puanı", fmt.dec(o.average_success_score, 1) + " / 100",
         "average_success_score_change", SUCCESS_HELP.average_success_score, true) +
    card("Öğrenci kaybı oranı", fmt.pct(o.dropout_rate), "dropout_rate_change",
         SUCCESS_HELP.dropout_rate, false) +
    card("Mezuniyet oranı", fmt.pct(o.graduation_rate), "graduation_rate_change",
         SUCCESS_HELP.graduation_rate, true) +
    `<div class="tile" title="Ölçüme dahil edilen öğrenci sayısı">
       <div class="label">Ölçülen öğrenci</div>
       <div class="value">${fmt.int(o.measured_student_count)}</div>
       <div class="delta">${fmt.int(o.graduate_count)} mezun</div>
     </div>`;
}

function refreshSuccess() {
  const year = successYear();
  const scope = SUCCESS_SCOPE;

  // --- Üst göstergeler: seçili kapsama göre ---
  const overviewFetch = () => {
    if (scope.level === "faculty") {
      return api
        .get("/api/academic-success/by-faculty", { academic_year: year })
        .then((rows) => rows.find((r) => r.faculty_id === scope.facultyId));
    }
    if (scope.level === "department") {
      return api
        .get("/api/academic-success/by-department", { academic_year: year })
        .then((rows) => rows.find((r) => r.department_id === scope.departmentId));
    }
    return api.get("/api/academic-success/overview", { academic_year: year });
  };

  load("acTiles", overviewFetch, (o, el) => {
    if (!o) {
      el.innerHTML = ui.empty("Seçilen birim için veri yok.");
      return;
    }
    el.id = "acTiles";
    successTiles(o, "acTiles");
  });

  // --- Breadcrumb (nerede olduğumuzu gösterir) ---
  const crumb = document.getElementById("acBreadcrumb");
  const parts = [`<a href="#" data-level="university">Üniversite geneli</a>`];
  if (scope.facultyName) parts.push(`<a href="#" data-level="faculty">${fmt.esc(scope.facultyName)}</a>`);
  if (scope.departmentName) parts.push(`<b>${fmt.esc(scope.departmentName)}</b>`);
  crumb.innerHTML = "Kapsam: " + parts.join(" › ");
  crumb.querySelectorAll("a[data-level]").forEach((a) =>
    a.addEventListener("click", (e) => {
      e.preventDefault();
      SUCCESS_SCOPE =
        a.dataset.level === "university"
          ? { level: "university" }
          : { level: "faculty", facultyId: scope.facultyId, facultyName: scope.facultyName };
      refreshSuccess();
    })
  );

  // --- Trend ---
  document.getElementById("acTrendScope").textContent =
    scope.level === "university"
      ? "Üniversite geneli."
      : `Kapsam: ${scope.departmentName || scope.facultyName}.`;

  load(
    "acTrend",
    () =>
      api.get("/api/academic-success/trend", {
        faculty_id: scope.level === "faculty" ? scope.facultyId : undefined,
        department_id: scope.level === "department" ? scope.departmentId : undefined,
      }),
    (rows, el) => {
      if (rows.length < 2) {
        el.innerHTML = ui.empty("Trend çizmek için en az iki dönem verisi gerekli.");
        return;
      }
      el.id = "acTrendChart";
      lineChart(
        "acTrendChart",
        rows.map((r) => r.academic_year),
        [
          { label: "Ders geçme oranı", color: "var(--primary)",
            values: rows.map((r) => Number(r.course_pass_rate)) },
          { label: "Mezuniyet oranı", color: "#0ca30c",
            values: rows.map((r) => Number(r.graduation_rate)) },
          { label: "Öğrenci kaybı oranı", color: "var(--critical, #c0392b)",
            values: rows.map((r) => Number(r.dropout_rate)) },
        ],
        {
          min: 0, max: 100,
          yfmt: (v) => Math.round(v),
          unitSuffix: "%",
          yAxisLabel: "Oran (%)",
          xAxisLabel: "Akademik dönem",
          periodNote: `${rows[0].academic_year} – ${rows[rows.length - 1].academic_year}`,
        }
      );
    }
  );

  // --- Korelasyon ---
  load(
    "acCorrelation",
    () => api.get("/api/academic-success/correlations", { academic_year: year }),
    (c, el) => {
      const bar = (label, value) => {
        if (value === null) return `<div class="note">${fmt.esc(label)}: hesaplanamadı</div>`;
        const v = Number(value);
        const pct = Math.min(100, Math.abs(v) * 100);
        const color = Math.abs(v) < 0.2 ? "var(--muted)" : v < 0 ? "var(--critical, #c0392b)" : "var(--primary)";
        return `<div class="meter">
          <div class="m-label"><span>${fmt.esc(label)}</span><b>r = ${fmt.dec(v, 2)}</b></div>
          <div class="track"><div class="fill" style="width:${pct}%;background:${color}"></div></div>
        </div>`;
      };
      el.innerHTML =
        bar("Öğrenci sayısı ↔ ders geçme oranı", c.student_count_vs_pass_rate) +
        bar("Akademisyen başına öğrenci ↔ ders geçme oranı", c.students_per_staff_vs_pass_rate) +
        `<ul class="plain">${c.interpretation.map((i) => `<li>${fmt.esc(i)}</li>`).join("")}</ul>` +
        `<div class="note"><b>Dikkat:</b> ${fmt.esc(c.caveat)}</div>` +
        `<div class="note muted">${c.program_count} program üzerinden hesaplandı. ` +
        `r değeri −1 ile +1 arasındadır; 0'a yakın olması ilişki olmadığını gösterir.</div>`;
    }
  );

  // --- Sıralamalar ---
  const rankLevel = scope.level === "university" ? "faculty" : "program";
  const rankTable = (rows, el, emptyMsg) => {
    if (!rows.length) return void (el.innerHTML = ui.empty(emptyMsg));
    el.innerHTML = table(
      ["Birim", "Geçme oranı", "Başarı puanı", "Öğrenci"],
      rows.map((r) => [
        fmt.esc(r.name),
        fmt.pct(r.course_pass_rate),
        fmt.dec(r.average_success_score, 1),
        fmt.int(r.measured_student_count),
      ])
    );
  };
  load(
    "acTop",
    () => api.get("/api/academic-success/rankings", { academic_year: year, level: rankLevel }),
    (r, el) => {
      rankTable(r.top, el, "Sıralanacak birim yok.");
      el.insertAdjacentHTML("beforeend", `<div class="note muted">${fmt.esc(r.note)}</div>`);
    }
  );
  load(
    "acBottom",
    () => api.get("/api/academic-success/rankings", { academic_year: year, level: rankLevel }),
    (r, el) => rankTable(r.bottom, el, "Sıralanacak birim yok.")
  );

  // --- Drill-down tablosu ---
  loadSuccessDrill(year);
}

function loadSuccessDrill(year) {
  const scope = SUCCESS_SCOPE;

  // Hangi seviyenin listeleneceği kapsama bağlı.
  const endpoint =
    scope.level === "university"
      ? ["/api/academic-success/by-faculty", { academic_year: year }]
      : scope.level === "faculty"
      ? ["/api/academic-success/by-department", { academic_year: year, faculty_id: scope.facultyId }]
      : ["/api/academic-success/by-program", { academic_year: year, department_id: scope.departmentId }];

  load(
    "acDrill",
    () => api.get(endpoint[0], endpoint[1]),
    (rows, el) => {
      if (!rows.length) return void (el.innerHTML = ui.empty("Bu kapsamda veri yok."));

      const isProgram = scope.level === "department";
      const headers = isProgram
        ? ["Program", "Öğrenci", "Geçme", "Kalma", "Başarı puanı", "Kayıp", "Mezuniyet", "Akademisyen başına"]
        : [scope.level === "university" ? "Fakülte" : "Bölüm",
           "Öğrenci", "Geçme", "Kalma", "Başarı puanı", "Kayıp", "Mezuniyet", "Değişim"];

      const body = rows.map((r) => {
        const pass = Number(r.course_pass_rate);
        const level = pass >= 85 ? "good" : pass >= 75 ? "info" : pass >= 65 ? "warning" : "critical";
        const nameCell = isProgram
          ? `<b>${fmt.esc(r.program_code)}</b><br><span class="muted">${fmt.esc(r.program_name)}</span>`
          : `<b>${fmt.esc(r.faculty_name || r.department_name)}</b>` +
            (r.program_count ? `<br><span class="muted">${r.program_count} program</span>` : "");
        const last = isProgram
          ? (r.students_per_staff === null ? fmt.empty : fmt.dec(r.students_per_staff, 1) + " öğr.")
          : (r.course_pass_rate_change === null
              ? fmt.empty
              : `${Number(r.course_pass_rate_change) >= 0 ? "▲ +" : "▼ "}${fmt.dec(
                  Math.abs(Number(r.course_pass_rate_change)), 2)} puan`);
        return [
          nameCell,
          fmt.int(r.measured_student_count),
          chip(level, fmt.pct(r.course_pass_rate)),
          fmt.pct(r.course_fail_rate),
          fmt.dec(r.average_success_score, 1),
          fmt.pct(r.dropout_rate),
          fmt.pct(r.graduation_rate),
          last,
        ];
      });

      el.innerHTML = table(headers, body);

      // Alt seviyeye inmek için satırları tıklanabilir yap.
      if (!isProgram) {
        el.querySelectorAll("tbody tr").forEach((tr, i) => {
          tr.style.cursor = "pointer";
          tr.title = "Alt kırılımı açmak için tıklayın";
          tr.addEventListener("click", () => {
            const row = rows[i];
            SUCCESS_SCOPE =
              scope.level === "university"
                ? { level: "faculty", facultyId: row.faculty_id, facultyName: row.faculty_name }
                : {
                    level: "department",
                    facultyId: row.faculty_id,
                    facultyName: row.faculty_name,
                    departmentId: row.department_id,
                    departmentName: row.department_name,
                  };
            refreshSuccess();
          });
        });
        el.insertAdjacentHTML("beforeend",
          `<div class="note">Bir satıra tıklayarak alt kırılımı açabilirsiniz.</div>`);
      }
    }
  );
}

/* ==================================================================
   Sanayi İş Birliği ve Bölgesel Katkı
   ================================================================== */

VIEWS["engagement"] = {
  title: "Sanayi ve Bölgesel Katkı",
  subtitle: "Ölçülebilir bileşenlerden hesaplanan iki kurumsal endeks",
  html: () => `
    <div class="card">
      <div class="filters">
        <label class="f">Akademik dönem <select id="enYear"></select></label>
        <button class="ghost" id="enApply">Uygula</button>
      </div>
      <div class="note">
        Bu iki gösterge daha önce elle girilen tek bir puandı ve neyi ölçtüğü
        belli değildi. Artık her bileşenin ham değeri, hedefi ve endekse katkısı
        ayrı ayrı görülebiliyor.
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Üniversite–sanayi iş birliği endeksi</h3>
        <div id="enIndustry"></div>
      </div>
      <div class="card">
        <h3>Bölgesel katkı endeksi</h3>
        <div id="enRegional"></div>
      </div>
    </div>

    <div class="card">
      <h3>Endekslerin yıllara göre gelişimi</h3>
      <div class="note">100 = stratejik plan hedefine tam ulaşıldı.</div>
      <div id="enTrend"></div>
    </div>

    <div class="card">
      <h3>Fakülte bazlı sanayi iş birliği</h3>
      <div class="note">Endeksin arkasındaki ham veri.</div>
      <div id="enFaculties"></div>
    </div>`,

  async init() {
    const years = await api.get("/api/academic-success/academic-years").catch(() => []);
    const sel = document.getElementById("enYear");
    sel.innerHTML = years.map((y) => `<option>${fmt.esc(y)}</option>`).join("");
    if (years.length) sel.value = years[years.length - 1];
    document.getElementById("enApply").addEventListener("click", refreshEngagement);
    refreshEngagement();
  },
};

function renderIndex(data, el, unitNote) {
  const pctOfTarget = Number(data.achievement_vs_target_percent);
  const level = pctOfTarget >= 100 ? "good" : pctOfTarget >= 85 ? "info" : pctOfTarget >= 70 ? "warning" : "critical";

  el.innerHTML =
    `<div class="kv">
       ${kv("Endeks değeri", `<b>${fmt.dec(data.index_value, 2)}</b>`)}
       ${kv("Hedef", fmt.dec(data.target_value, 2))}
       ${kv("Hedefe ulaşma", chip(level, fmt.pct(data.achievement_vs_target_percent)))}
     </div>
     ${data.weight_warning ? `<div class="state error">${fmt.esc(data.weight_warning)}</div>` : ""}
     <div class="note">${fmt.esc(unitNote)}</div>` +
    table(
      ["Bileşen", "Ölçülen", "Hedef", "Hedefin %'i", "Ağırlık", "Endekse katkı"],
      data.components.map((c) => [
        `<b>${fmt.esc(c.label)}</b>`,
        `${fmt.dec(c.value, c.unit === "milyon USD" ? 2 : 0)} <span class="muted">${fmt.esc(c.unit)}</span>`,
        fmt.dec(c.reference_value, c.unit === "milyon USD" ? 2 : 0),
        fmt.pct(c.achievement_percent),
        fmt.dec(c.weight, 2),
        `<b>${fmt.dec(c.contribution_to_index, 2)}</b>`,
      ])
    ) +
    `<div class="note muted">
       Endeks = Σ (bileşen ÷ hedef × 100 × ağırlık). Ağırlıklar toplamı
       ${fmt.dec(data.weight_total, 2)}. Endeks 100'ü aşabilir; bu hedefin
       aşıldığı anlamına gelir.
     </div>`;
}

function refreshEngagement() {
  const year = document.getElementById("enYear").value;

  load(
    "enIndustry",
    () => api.get("/api/engagement/industry-collaboration", { academic_year: year }),
    (d, el) => renderIndex(d, el, "Araştırma bütçesi milyon USD, diğerleri adet/kişi cinsindendir.")
  );

  load(
    "enRegional",
    () => api.get("/api/engagement/regional-contribution", { academic_year: year }),
    (d, el) => {
      renderIndex(d, el, `Bölge: ${d.region}. Bileşenler adet, kişi ve saat cinsindendir.`);
      el.insertAdjacentHTML(
        "afterbegin",
        `<div class="state empty">${fmt.esc(d.regional_employment_note)}` +
          (d.regional_employment_share_percent !== null
            ? ` Bölgesel istihdam payı: <b>${fmt.pct(d.regional_employment_share_percent)}</b>.`
            : "") +
          `</div>`
      );
    }
  );

  load(
    "enTrend",
    () => api.get("/api/engagement/trend"),
    (rows, el) => {
      if (rows.length < 2) return void (el.innerHTML = ui.empty("Trend için yeterli dönem yok."));
      el.id = "enTrendChart";
      lineChart(
        "enTrendChart",
        rows.map((r) => r.academic_year),
        [
          { label: "Sanayi iş birliği endeksi", color: "var(--primary)",
            values: rows.map((r) => Number(r.industry_collaboration_index)) },
          { label: "Bölgesel katkı endeksi", color: "var(--accent)",
            values: rows.map((r) => Number(r.regional_contribution_index)) },
        ],
        {
          min: 0, max: 120,
          yfmt: (v) => Math.round(v),
          yAxisLabel: "Endeks (100 = hedef)",
          xAxisLabel: "Akademik dönem",
          periodNote: `${rows[0].academic_year} – ${rows[rows.length - 1].academic_year}`,
        }
      );
    }
  );

  load(
    "enFaculties",
    () => api.get("/api/engagement/industry-collaboration", { academic_year: year }),
    (d, el) => {
      el.innerHTML = table(
        ["Fakülte", "Aktif iş birliği", "Ortak proje", "Araştırma bütçesi", "Staj yapan öğrenci", "Protokol"],
        d.by_faculty.map((r) => [
          fmt.esc(r.faculty_name),
          fmt.int(r.active_partnerships),
          fmt.int(r.joint_projects),
          fmt.usdMillion(r.funded_research_musd),
          fmt.int(r.intern_students),
          fmt.int(r.signed_protocols),
        ])
      );
    }
  );
}
