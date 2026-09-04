// Analiz ekranları: Öğrenci, Personel, Fiziksel Kaynaklar, Finans,
// Sürdürülebilirlik, KPI ve Değerlendirme.
// Hiçbir ekranda gömülü veri yoktur; her sayı backend'den gelir.

/* ==================================================================
   Öğrenci Analitiği — Modül 2 (Habib) + Modül 3 (Begüm)
   ================================================================== */

VIEWS["students"] = {
  title: "Öğrenci Analitiği",
  subtitle: "Kayıt, doluluk, mezuniyet ve talep göstergeleri",
  html: () => `
    <div class="card">
      <h3>Kapsam seçin</h3>
      <div class="note">
        Fakülte seçtikten sonra bölüm, bölüm seçtikten sonra program
        seçebilirsiniz. Seçim yapmadan “Sonuçları Göster” derseniz üniversite
        geneli sonuçlar gelir.
      </div>
      <div id="stFilter"></div>
    </div>

    <div id="stTiles"></div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Program bazlı doluluk oranı</h3>
        <div class="note">Kontenjanın yüzde kaçının dolduğu.</div>
        <div id="stOccupancy"></div>
      </div>
      <div class="card">
        <h3>Burs ve uluslararasılaşma</h3>
        <div class="note">Burs, uluslararası öğrenci ve mezuniyet oranları.</div>
        <div id="stM3"></div>
      </div>
    </div>

    <div class="card">
      <h3>Program karnesi</h3>
      <div class="note">Doluluk, mezuniyet ve ayrılma oranları · en düşük dolulukan başlayarak.</div>
      <div id="stTable"></div>
    </div>

    <div class="card">
      <h3>Erken uyarı sinyalleri</h3>
      <div class="note">Öğrenci verisinden türeyen otomatik uyarılar.</div>
      <div id="stAlerts"></div>
    </div>`,

  async init() {
    const years = await ref.academicYears().catch(() => [CURRENT_YEAR]);
    ST_FILTER = new OrgFilter("stFilter", {
      withYear: true,
      years,
      defaultYear: years.includes(CURRENT_YEAR) ? CURRENT_YEAR : years[years.length - 1],
      level: "department",
      onApply: (scope) => refreshStudents(scope),
    });
    await ST_FILTER.render();
    // Üniversite geneli varsayılan görünüm olarak bir kez yüklenir.
    refreshStudents(ST_FILTER.value());
  },
};

let ST_FILTER = null;

function refreshStudents(scope) {
  const f = {
    academic_year: scope.year,
    faculty_id: scope.facultyId || undefined,
    department_id: scope.departmentId || undefined,
  };

  load(
    "stTiles",
    () => api.get("/api/student-analytics/overview", f),
    (o, el) => {
      el.className = "tiles";
      el.innerHTML = tileHtml([
        ["Toplam öğrenci", fmt.int(o.total_students)],
        ["Aktif", fmt.int(o.active_students)],
        ["Yeni kayıt", fmt.int(o.newly_enrolled_students)],
        ["Mezun", fmt.int(o.graduated_students)],
        ["Ayrılan", fmt.int(o.dropped_out_students)],
        ["Hazırlık", fmt.int(o.preparatory_school_students)],
        ["Ortalama GPA", fmt.dec(o.average_gpa, 2)],
        ["Mezuniyet oranı", fmt.pct(o.graduation_rate)],
      ]);
    }
  );

  load(
    "stOccupancy",
    () => api.get("/api/student-analytics/by-program", f),
    (rows, el) => {
      if (!rows.length) return void (el.innerHTML = ui.empty("Program verisi yok."));
      const sorted = [...rows].sort(
        (a, b) => Number(a.occupancy_rate) - Number(b.occupancy_rate)
      );
      el.id = "stOccBars";
      hbars(
        "stOccBars",
        sorted.map((r) => [
          r.program_code,
          Number(r.occupancy_rate) || 0,
          // Renk doluluk seviyesini anlatır: kırmızı = kritik.
          Number(r.occupancy_rate) < 60
            ? "var(--critical, #c0392b)"
            : Number(r.occupancy_rate) < 80
            ? "var(--accent)"
            : "var(--primary)",
        ]),
        { max: 100, fmt: (v) => fmt.pct(v) }
      );
    }
  );

  load(
    "stM3",
    () => api.get("/api/education-analytics/overview", { academic_year: f.academic_year }),
    (o, el) => {
      el.id = "stM3Rings";
      donuts("stM3Rings", [
        ["Uluslararası", Math.round(Number(o.international_student_percentage) || 0)],
        ["Burslu", Math.round(Number(o.scholarship_student_percentage) || 0), "var(--accent)"],
        ["Mezuniyet", Math.round(Number(o.graduation_rate) || 0), "#0ca30c"],
      ]);
      el.insertAdjacentHTML(
        "beforeend",
        `<div class="kv">
          ${kv("Hazırlık öğrencisi", fmt.int(o.preparatory_student_count))}
          ${kv("Ortalama GPA", fmt.dec(o.average_gpa, 2))}
          ${kv("Mezuniyet kohortu", fmt.int(o.graduation_cohort_size))}
          ${kv("Mezun istihdam oranı", fmt.pct(o.employment_rate))}
        </div>`
      );
    }
  );

  load(
    "stTable",
    () => api.get("/api/student-analytics/by-program", f),
    (rows, el) => {
      if (!rows.length) return void (el.innerHTML = ui.empty("Program verisi yok."));
      const sorted = [...rows].sort(
        (a, b) => Number(a.occupancy_rate) - Number(b.occupancy_rate)
      );
      el.innerHTML = table(
        ["Program", "Bölüm", "Kontenjan", "Yerleşen", "Doluluk", "Aktif", "Mezuniyet", "Ayrılma", "Durum"],
        sorted.map((r) => {
          const occ = Number(r.occupancy_rate);
          const level = occ < 60 ? "critical" : occ < 80 ? "warning" : "good";
          return [
            fmt.esc(r.program_name),
            fmt.esc(r.department_name),
            fmt.int(r.quota),
            fmt.int(r.enrolled_student_count),
            fmt.pct(r.occupancy_rate),
            fmt.int(r.active_student_count),
            fmt.pct(r.graduation_rate),
            fmt.pct(r.attrition_rate),
            chip(level, occ < 60 ? "kritik" : occ < 80 ? "izlenmeli" : "sağlıklı"),
          ];
        })
      );
    }
  );

  load(
    "stAlerts",
    () => api.get("/api/student-analytics/alerts", f),
    (alerts, el) => {
      if (!alerts.length)
        return void (el.innerHTML = ui.empty("Öğrenci verisinden uyarı üretilmedi."));
      el.innerHTML =
        `<ul class="plain">` +
        alerts
          .map((a) => {
            const sev = (a.severity || "").toLowerCase();
            const level =
              sev.includes("critical") || sev.includes("kritik")
                ? "critical"
                : sev.includes("high") || sev.includes("yüksek")
                ? "warning"
                : "info";
            return `<li>${chip(level, a.severity)}${fmt.esc(a.message || a.title)}
              ${a.scope_name ? `<span class="push" style="font-size:.72rem">${fmt.esc(a.scope_name)}</span>` : ""}</li>`;
          })
          .join("") +
        `</ul>`;
    }
  );
}

/* ==================================================================
   Akademik Personel — Modül 4 (Eda)
   ================================================================== */

VIEWS["staff"] = {
  title: "Akademik Personel",
  subtitle: "Yayın, atıf, ders yükü ve ağırlıklı performans puanı",
  html: () => `
    <div class="card">
      <h3>Kapsam seçin</h3>
      <div class="note">
        Fakülte ve bölüm seçerek kadroyu daraltabilir, seçim yapmadan
        üniversite genelini görebilirsiniz.
      </div>
      <div id="stfFilter"></div>
      <div class="filters" style="margin-top:12px">
        <label class="f">Karşılaştırma kırılımı <select id="stfGroup">
          <option value="department">Bölüme göre</option>
          <option value="faculty">Fakülteye göre</option>
          <option value="title">Unvana göre</option>
        </select></label>
      </div>
    </div>

    <div id="stfTiles"></div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Karşılaştırma</h3>
        <div class="note">Seçilen kırılımda ortalama performans puanı.</div>
        <div id="stfCompare"></div>
      </div>
      <div class="card">
        <h3>Unvan dağılımı</h3>
        <div class="note">Akademik kadro piramidi.</div>
        <div id="stfTitles"></div>
      </div>
    </div>

    <div class="card">
      <h3>Performans sıralaması</h3>
      <div class="note">
        Akademik üretim; yayın, atıf, ders yükü, danışmanlık, proje, patent ve
        topluma katkı kalemlerinin ağırlıklı toplamı olarak puanlanır.
      </div>
      <div id="stfRanking"></div>
      ${ux.details(
        "Puanlama nasıl yapılıyor?",
        `<table class="table"><thead><tr><th>Kalem</th><th>Ağırlık</th></tr></thead>
         <tbody>
           <tr><td>Patent</td><td>6</td></tr>
           <tr><td>Yayın</td><td>5</td></tr>
           <tr><td>Proje</td><td>4</td></tr>
           <tr><td>Danışmanlık</td><td>3</td></tr>
           <tr><td>Atıf</td><td>2</td></tr>
           <tr><td>Topluma katkı</td><td>2</td></tr>
           <tr><td>Ders yükü</td><td>1</td></tr>
         </tbody></table>
         <div class="note">Ağırlıklar yönetici tarafından güncellenebilir.</div>`,
        { hint: "Ağırlık tablosu" }
      )}
    </div>`,

  async init() {
    const trend = await api.get("/api/academic-staff/trend").catch(() => []);
    const years = trend.map((y) => y.academic_year);
    STF_FILTER = new OrgFilter("stfFilter", {
      withYear: years.length > 0,
      years,
      defaultYear: years[years.length - 1] || null,
      level: "department",
      onApply: (scope) => refreshStaff(scope),
    });
    await STF_FILTER.render();
    document
      .getElementById("stfGroup")
      .addEventListener("change", () => refreshStaff(STF_FILTER.value()));
    refreshStaff(STF_FILTER.value());
  },
};

let STF_FILTER = null;

function refreshStaff(scope) {
  const year = scope.year || undefined;
  const facultyId = scope.facultyId || undefined;
  const departmentId = scope.departmentId || undefined;
  const group = document.getElementById("stfGroup")?.value || "department";

  load(
    "stfTiles",
    () => api.get("/api/academic-staff/overview", { academic_year: year, faculty_id: facultyId, department_id: departmentId }),
    (o, el) => {
      el.className = "tiles";
      el.innerHTML = tileHtml([
        ["Akademik personel", fmt.int(o.total_staff)],
        ["Toplam yayın", fmt.int(o.total_publication)],
        ["Toplam atıf", fmt.int(o.total_citation)],
        ["Ortalama puan", fmt.dec(o.average_score, 1)],
        ["Ortalama ders yükü", fmt.dec(o.average_teaching_load_hours, 1) + " saat"],
        ["İdari görevli", fmt.int(o.staff_with_administrative_duty)],
        ["Sanayi iş birliği", fmt.int(o.staff_with_industry_collaboration)],
        [
          "Personel başına yayın",
          o.total_staff ? fmt.dec(o.total_publication / o.total_staff, 2) : fmt.empty,
        ],
      ]);
    }
  );

  load(
    "stfCompare",
    () => api.get(`/api/academic-staff/compare/${group}`, { academic_year: year }),
    (rows, el) => {
      if (!rows.length) return void (el.innerHTML = ui.empty("Karşılaştırma verisi yok."));
      el.innerHTML =
        `<div id="stfCompareBars"></div>` +
        table(
          ["Grup", "Personel", "Ort. yayın", "Ort. atıf", "Ort. puan"],
          rows.map((r) => [
            fmt.esc(r.group_key),
            fmt.int(r.staff_count),
            fmt.dec(r.average_publication, 1),
            fmt.dec(r.average_citation, 1),
            fmt.dec(r.average_score, 1),
          ])
        );
      hbars(
        "stfCompareBars",
        rows.map((r) => [r.group_key, Number(r.average_score) || 0]),
        { fmt: (v) => fmt.dec(v, 1) }
      );
    }
  );

  load(
    "stfTitles",
    () => api.get("/api/academic-staff/overview", { academic_year: year, faculty_id: facultyId, department_id: departmentId }),
    (o, el) => {
      el.id = "stfTitleBars";
      hbars(
        "stfTitleBars",
        o.title_distribution.map((t) => [t.title, t.count]),
        { fmt: (v) => fmt.int(v) + " kişi" }
      );
    }
  );

  load(
    "stfRanking",
    () => api.get("/api/academic-staff/ranking", { academic_year: year, faculty_id: facultyId, department_id: departmentId }),
    (rows, el) => {
      if (!rows.length) return void (el.innerHTML = ui.empty("Personel kaydı yok."));
      el.innerHTML = table(
        ["#", "Ad Soyad", "Unvan", "Bölüm", "Toplam puan", "Bant"],
        rows.slice(0, 10).map((r) => {
          const level =
            r.performance_band === "yüksek performans"
              ? "good"
              : r.performance_band === "beklenen performans"
              ? "info"
              : "warning";
          return [
            r.rank,
            fmt.esc(r.full_name),
            fmt.esc(r.title),
            fmt.esc(r.department_name),
            `<b>${fmt.dec(r.total_score, 1)}</b>`,
            chip(level, r.performance_band),
          ];
        })
      );
      // Uzun liste ana ekranı doldurmasın: kalanı açılır bölümde.
      if (rows.length > 10) {
        el.insertAdjacentHTML(
          "beforeend",
          ux.details(
            "Sıralamanın tamamını göster",
            table(
              ["#", "Ad Soyad", "Unvan", "Bölüm", "Toplam puan", "Bant"],
              rows.slice(10).map((r) => [
                r.rank,
                fmt.esc(r.full_name),
                fmt.esc(r.title),
                fmt.esc(r.department_name),
                `<b>${fmt.dec(r.total_score, 1)}</b>`,
                chip(
                  r.performance_band === "yüksek performans" ? "good"
                  : r.performance_band === "beklenen performans" ? "info" : "warning",
                  r.performance_band
                ),
              ])
            ),
            { hint: `${rows.length - 10} kayıt daha` }
          ) +
            ux.details(
              "Puan nasıl hesaplanıyor?",
              `<p class="note">
                 Ağırlıklı puan = yayın×5 + atıf×2 + ders yükü×1 + danışmanlık×3
                 + proje×4 + patent×6 + topluma katkı×2
               </p>
               <p class="note muted">
                 Ağırlıklar kurumsal puanlama politikasından gelir ve veriden
                 bağımsız olarak yönetilir.
               </p>`
            )
        );
      }
    }
  );
}

/* ==================================================================
   Fiziksel Kaynaklar — Modül 5 (Eda)
   ================================================================== */

VIEWS["physical"] = {
  title: "Fiziksel Kaynaklar",
  subtitle: "Derslik, laboratuvar ve ofis kapasitesi",
  html: () => `
    <div id="phTiles"></div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Tesis türüne göre kullanım</h3>
        <div id="phByType"></div>
      </div>
      <div class="card">
        <h3>Bölüm bazlı alan dağılımı</h3>
        <div class="note">Bölüme ait olmayan ortak alanlar ayrı grupta toplanır.</div>
        <div id="phByDept"></div>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Acil kapasite ihtiyacı</h3>
        <div class="note">Doluluk oranı %90'ın üzerinde olan mekânlar.</div>
        <div id="phOver"></div>
      </div>
      <div class="card">
        <h3>Değerlendirilmemiş kapasite</h3>
        <div class="note">Doluluk oranı %50'nin altında kalan mekânlar.</div>
        <div id="phUnder"></div>
      </div>
    </div>

    <div class="card">
      <h3>Büyüme projeksiyonu</h3>
      <div class="note">Öğrenci sayısı artarsa mevcut kapasite yeter mi?</div>
      <div class="filters">
        <label class="f">Beklenen artış (%)
          <input id="phGrowth" type="number" value="10" min="-50" max="200" step="5">
        </label>
        <button class="ghost" id="phRun">Hesapla</button>
      </div>
      <div id="phForecast"></div>
    </div>

    <div id="phPerPersonWrap"></div>`,

  async init() {
    load(
      "phTiles",
      () => api.get("/api/physical-resources/capacity/overview"),
      (o, el) => {
        el.className = "tiles";
        el.innerHTML = tileHtml([
          ["Mekân sayısı", fmt.int(o.total_facilities)],
          ["Toplam kapasite", fmt.int(o.total_capacity)],
          ["Kullanımdaki", fmt.int(o.total_occupied)],
          ["Genel doluluk", fmt.pct(o.overall_occupancy_percent)],
          ["Aşırı dolu", fmt.int(o.overcrowded_count)],
          ["Atıl kapasiteli", fmt.int(o.underutilized_count)],
        ]);
      }
    );

    load(
      "phByType",
      () => api.get("/api/physical-resources/capacity/by-type"),
      (rows, el) => {
        el.innerHTML = `<div id="phTypeBars"></div>` +
          table(
            ["Tür", "Adet", "Kapasite", "Dolu", "Kullanım"],
            rows.map((r) => [
              fmt.esc(TYPE_LABELS[r.facility_type] || r.facility_type),
              fmt.int(r.facility_count),
              fmt.int(r.total_capacity),
              fmt.int(r.total_occupied),
              fmt.pct(r.average_utilization_percent),
            ])
          );
        hbars(
          "phTypeBars",
          rows.map((r) => [
            TYPE_LABELS[r.facility_type] || r.facility_type,
            Number(r.average_utilization_percent) || 0,
          ]),
          { max: 100, fmt: (v) => fmt.pct(v) }
        );
      }
    );

    load(
      "phByDept",
      () => api.get("/api/physical-resources/capacity/by-department"),
      (rows, el) => {
        el.innerHTML = table(
          ["Birim", "Fakülte", "Mekân", "Kapasite", "Alan (m²)"],
          rows.map((r) => [
            fmt.esc(r.department_name),
            fmt.esc(r.faculty_name),
            fmt.int(r.facility_count),
            fmt.int(r.total_capacity),
            // Ölçüm girilmemişse 0 değil "—" gösterilir.
            r.total_area_square_meters === null ? fmt.empty : fmt.int(r.total_area_square_meters),
          ])
        );
      }
    );

    // Uzun mekân listeleri ana ekranı doldurmasın: ilk 5 satır görünür,
    // kalanı açılır bölümde. Veri gizlenmez, ertelenir.
    const facilityRows = (rows) =>
      rows.map((r) => [
        fmt.esc(r.name),
        fmt.esc(TYPE_LABELS[r.facility_type] || r.facility_type),
        fmt.esc(r.department_name || "Ortak kullanım"),
        fmt.int(r.capacity),
        fmt.int(r.occupied),
        fmt.pct(r.occupancy_percent),
      ]);
    const facilityHeaders = ["Mekân", "Tür", "Birim", "Kapasite", "Dolu", "Doluluk"];

    const facilityTable = (rows, el, emptyMsg) => {
      if (!rows.length) return void (el.innerHTML = ui.empty(emptyMsg));
      el.innerHTML = table(facilityHeaders, facilityRows(rows.slice(0, 5)));
      if (rows.length > 5) {
        el.insertAdjacentHTML(
          "beforeend",
          ux.details(
            "Tümünü göster",
            table(facilityHeaders, facilityRows(rows.slice(5))),
            { hint: `${rows.length - 5} mekân daha` }
          )
        );
      }
    };

    load(
      "phOver",
      () => api.get("/api/physical-resources/capacity/overcrowded"),
      (rows, el) => facilityTable(rows, el, "Aşırı dolu mekân yok.")
    );
    load(
      "phUnder",
      () => api.get("/api/physical-resources/capacity/underutilized"),
      (rows, el) => facilityTable(rows, el, "Atıl kapasiteli mekân yok.")
    );

    const runForecast = () =>
      load(
        "phForecast",
        () =>
          api.get("/api/physical-resources/capacity/forecast", {
            growth_percent: document.getElementById("phGrowth").value,
          }),
        (r, el) => {
          el.innerHTML = `
            <div class="kv">
              ${kv("Mevcut kapasite", fmt.int(r.current_capacity))}
              ${kv("Mevcut doluluk", fmt.int(r.current_occupied))}
              ${kv("Projeksiyon", fmt.dec(r.projected_occupied, 0))}
              ${kv("Projeksiyon doluluk", fmt.pct(r.projected_occupancy_percent))}
              ${kv("Kapasite açığı", r.shortfall > 0 ? fmt.dec(r.shortfall, 0) + " kişi" : "yok")}
            </div>
            <div class="state ${r.is_sufficient ? "empty" : "warn"}">
              ${chip(r.is_sufficient ? "good" : "critical", r.is_sufficient ? "yeterli" : "yetersiz")}
              ${fmt.esc(r.assessment)}
            </div>`;
        }
      );
    document.getElementById("phRun").addEventListener("click", runForecast);
    runForecast();

    document.getElementById("phPerPersonWrap").innerHTML = ux.details(
      "Kişi başına düşen kapasite",
      `<div id="phPerPerson">${ux.skeleton(2)}</div>`,
      { hint: "Öğrenci ve personel başına alan" }
    );
    load(
      "phPerPerson",
      () => api.get("/api/physical-resources/capacity/per-person"),
      (r, el) => {
        el.innerHTML = `
          <div class="kv">
            ${kv("Toplam kapasite", fmt.int(r.total_capacity))}
            ${kv("Toplam alan", r.total_area_square_meters === null ? fmt.empty : fmt.int(r.total_area_square_meters) + " m²")}
            ${kv("Aktif öğrenci", fmt.int(r.active_student_count))}
            ${kv("Aktif personel", fmt.int(r.active_staff_count))}
            ${kv("Öğrenci başına", fmt.dec(r.capacity_per_student, 3))}
            ${kv("Personel başına", fmt.dec(r.capacity_per_staff, 2))}
          </div>
          <div class="note">${fmt.esc(r.note)}</div>`;
      }
    );
  },
};

const TYPE_LABELS = {
  classroom: "Derslik",
  laboratory: "Laboratuvar",
  office: "Ofis",
  library: "Kütüphane",
  other: "Diğer",
};

/* ==================================================================
   Finansal Analiz — Modül 6 (Halil)
   ================================================================== */

VIEWS["finance"] = {
  title: "Finansal Analiz",
  subtitle: "Gelir, gider, bütçe gerçekleşmesi ve oran göstergeleri · tüm tutarlar USD",
  html: () => `
    <div class="card">
      <div class="filters">
        <label class="f">Mali dönem <select id="finPeriod"></select></label>
        <button class="ghost" id="finApply">Uygula</button>
      </div>
    </div>

    <div id="finTiles"></div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Gelir kalemleri</h3>
        <div class="note">Milyon USD · toplam içindeki payıyla birlikte.</div>
        <div id="finRevenue"></div>
      </div>
      <div class="card">
        <h3>Gider kalemleri</h3>
        <div class="note">Milyon USD · toplam içindeki payıyla birlikte.</div>
        <div id="finExpense"></div>
      </div>
    </div>

    <div class="card">
      <h3>Bölüm bütçeleri ve gerçekleşme</h3>
      <div class="note">
        Gerçekleşme oranı = gider / tahsis edilen bütçe.
        %100'e kadar bütçe içinde, %108'e kadar hafif aşım, üstü bütçe aşımı.
      </div>
      <div id="finDepartments"></div>
    </div>

    <div class="card">
      <h3>Son 5 yılda gelirlerimiz ve giderlerimiz ne kadar değişti?</h3>
      <div class="note">
        Tüm tutarlar <b>milyon USD</b>. İlk yıl için değişim oranı hesaplanmaz
        (karşılaştırma tabanı yoktur).
      </div>
      <div id="finFiveYear"></div>
      <div id="finTrend"></div>
    </div>`,

  async init() {
    const periods = await api.get("/api/finance/periods");
    const sel = document.getElementById("finPeriod");
    // Tutar girilmiş dönemler önce gelsin; boş planlama yılı varsayılan olmasın.
    sel.innerHTML = periods
      .map((p) => `<option value="${p.academic_year}">${p.academic_year}</option>`)
      .join("");
    const withData = periods.find((p) => p.total_students > 0);
    if (withData) sel.value = withData.academic_year;

    document.getElementById("finApply").addEventListener("click", () => refreshFinance());
    refreshFinance();
  },
};

function refreshFinance() {
  const year = document.getElementById("finPeriod").value;

  load(
    "finTiles",
    () => api.get(`/api/finance/${year}/summary`),
    (s, el) => {
      el.className = "tiles";
      el.innerHTML = tileHtml([
        ["Toplam gelir", fmt.usdMillion(s.total_revenue)],
        ["Toplam gider", fmt.usdMillion(s.total_expenditure)],
        ["Denge", fmt.usdMillion(s.balance), s.balance_status === "fazla" ? "▲ fazla" : "▼ açık",
          s.balance_status === "fazla" ? "up" : "down"],
        ["Öğrenci başına gelir", fmt.usdPerPerson(s.revenue_per_student_thousand_usd)],
        ["Öğrenci başına maliyet", fmt.usdPerPerson(s.cost_per_student_thousand_usd)],
        ["Mezun başına maliyet", fmt.usdMillion(s.cost_per_graduate_million_usd, 2)],
        ["Personel gideri payı", fmt.pct(s.personnel_expense_share_percent)],
        ["Burs yükü / gelir", fmt.pct(s.scholarship_impact_percent)],
      ]);
    }
  );

  const breakdown = (containerId, key) =>
    load(
      containerId,
      () => api.get(`/api/finance/${year}/summary`),
      (s, el) => {
        const rows = s[key];
        if (!rows.length) return void (el.innerHTML = ui.empty("Bu dönemde kalem girilmemiş."));
        el.innerHTML = `<div id="${containerId}Bars"></div>` +
          table(
            ["Kalem", "Tutar", "Pay"],
            rows.map((r) => [fmt.esc(r.category), fmt.usdMillion(r.amount), fmt.pct(r.share_percent)])
          );
        hbars(
          containerId + "Bars",
          rows.map((r) => [r.category, Number(r.amount) || 0,
            key === "revenue_breakdown" ? "var(--primary)" : "var(--accent)"]),
          {
            fmt: (v) => fmt.usdMillion(v),
            valueLabel: "Milyon USD",
            legend: [[key === "revenue_breakdown" ? "Gelir kalemi" : "Gider kalemi",
                      key === "revenue_breakdown" ? "var(--primary)" : "var(--accent)"]],
          }
        );
      }
    );
  breakdown("finRevenue", "revenue_breakdown");
  breakdown("finExpense", "expenditure_breakdown");

  load(
    "finDepartments",
    () => api.get(`/api/finance/${year}/departments`),
    (rows, el) => {
      if (!rows.length) return void (el.innerHTML = ui.empty("Bölüm bütçesi girilmemiş."));
      el.innerHTML = table(
        ["Bölüm", "Fakülte", "Öğrenci", "Gelir", "Gider", "Bütçe", "Denge", "Gerçekleşme", "Durum"],
        rows.map((r) => {
          const level =
            r.budget_status === "bütçe aşımı"
              ? "critical"
              : r.budget_status === "hafif aşım"
              ? "warning"
              : r.budget_status === "bütçe içinde"
              ? "good"
              : "neutral";
          return [
            fmt.esc(r.department_name),
            fmt.esc(r.faculty_name),
            fmt.int(r.student_count),
            fmt.usdMillion(r.revenue),
            fmt.usdMillion(r.expenditure),
            fmt.usdMillion(r.allocated_budget),
            fmt.usdMillion(r.balance),
            // Bütçe tanımsızsa oran gösterilmez.
            r.budget_realization_percent === null
              ? fmt.empty
              : fmt.pct(r.budget_realization_percent),
            chip(level, r.budget_status),
          ];
        })
      );
    }
  );

  load(
    "finTrend",
    () => api.get("/api/finance/trend"),
    (rows, el) => {
      el.innerHTML = `<div id="finTrendChart"></div>` +
        table(
          ["Dönem", "Gelir", "Gider", "Denge", "Gelir değişimi", "Gider değişimi"],
          rows.map((r) => [
            fmt.esc(r.academic_year),
            fmt.usdMillion(r.total_revenue),
            fmt.usdMillion(r.total_expenditure),
            fmt.usdMillion(r.balance),
            r.revenue_change_percent === null ? fmt.empty : fmt.pct(r.revenue_change_percent),
            r.expenditure_change_percent === null ? fmt.empty : fmt.pct(r.expenditure_change_percent),
          ])
        );
      // Tutarı sıfır olan planlama yılı grafiği bozmasın.
      const withData = rows.filter((r) => Number(r.total_revenue) > 0);
      if (withData.length > 1) {
        lineChart(
          "finTrendChart",
          withData.map((r) => r.academic_year),
          [
            { label: "Toplam gelir", color: "var(--primary)",
              values: withData.map((r) => Number(r.total_revenue)) },
            { label: "Toplam gider", color: "var(--accent)",
              values: withData.map((r) => Number(r.total_expenditure)) },
            { label: "Gelir–gider dengesi", color: "#0ca30c",
              values: withData.map((r) => Number(r.balance)) },
          ],
          {
            min: 0,
            yfmt: (v) => "$" + fmt.dec(v, 0) + "M",
            unitSuffix: " milyon USD",
            yAxisLabel: "Tutar (milyon USD)",
            xAxisLabel: "Mali dönem",
            periodNote: `${withData[0].academic_year} – ${withData[withData.length - 1].academic_year}`,
          }
        );
      }

      // 5 yıllık toplam değişim özeti: "gelirimiz ne kadar arttı" sorusunun
      // doğrudan cevabı. Hesap sunucudan gelen ilk ve son yıl toplamlarından
      // yapılır; ara yılların yüzdeleri çarpılmaz (bileşik hata olurdu).
      const box = document.getElementById("finFiveYear");
      if (box && withData.length > 1) {
        const first = withData[0], last = withData[withData.length - 1];
        const growth = (a, b) => ((Number(b) - Number(a)) / Number(a)) * 100;
        const revG = growth(first.total_revenue, last.total_revenue);
        const expG = growth(first.total_expenditure, last.total_expenditure);
        const card = (label, v1, v2, g, goodWhenUp) => `
          <div class="tile">
            <div class="label">${fmt.esc(label)}</div>
            <div class="value">${fmt.pct(g)}</div>
            <div class="delta ${(g >= 0) === goodWhenUp ? "up" : "down"}">
              ${fmt.usdMillion(v1)} → ${fmt.usdMillion(v2)}
            </div>
          </div>`;
        box.className = "tiles";
        box.innerHTML =
          card(`Gelir değişimi (${withData.length} dönem)`, first.total_revenue, last.total_revenue, revG, true) +
          card(`Gider değişimi (${withData.length} dönem)`, first.total_expenditure, last.total_expenditure, expG, false) +
          `<div class="tile">
             <div class="label">Denge değişimi</div>
             <div class="value">${fmt.usdMillion(Number(last.balance) - Number(first.balance))}</div>
             <div class="delta ${Number(last.balance) >= Number(first.balance) ? "up" : "down"}">
               ${fmt.usdMillion(first.balance)} → ${fmt.usdMillion(last.balance)}
             </div>
           </div>
           <div class="tile">
             <div class="label">Gelir mi gider mi daha hızlı arttı?</div>
             <div class="value">${revG > expG ? "Gelir" : "Gider"}</div>
             <div class="delta ${revG > expG ? "up" : "down"}">
               fark ${fmt.dec(Math.abs(revG - expG), 1)} puan
             </div>
           </div>`;
      }
    }
  );
}

/* ==================================================================
   THE · QS · YÖK Değerlendirme — Modül 10 (Habib)
   ================================================================== */

VIEWS["rankings"] = {
  title: "THE · QS · YÖK Değerlendirme",
  subtitle: "İç performans izleme ve veri hazırlık göstergeleri",
  html: () => `
    <div class="state warn">
      <b>Önemli:</b> Bu modül gerçek THE, QS veya YÖK sıralaması ÜRETMEZ.
      Hesaplananlar, kurumun bu çerçevelerdeki göstergeler için ne kadar veriye
      sahip olduğunu ve iç performansını gösteren kurum içi ölçümlerdir.
    </div>

    <div class="card">
      <h3>Değerlendirme çerçeveleri</h3>
      <div id="rkFrameworks"></div>
    </div>

    <div class="card">
      <h3>Son değerlendirmeler</h3>
      <div class="note">
        Uyum puanı = performans × veri hazırlık / 100. Veri eksikse performans
        puanı yüksek olsa bile uyum puanı düşer; eksik veri gizlenmez.
      </div>
      <div id="rkAssessments"></div>
    </div>

    <div class="card">
      <h3>Kıyaslama kurumları</h3>
      <div class="note">Karşılaştırma için tanımlanan referans kurumlar.</div>
      <div id="rkBenchmarks"></div>
    </div>`,

  async init() {
    load(
      "rkFrameworks",
      () => api.get("/api/ranking-evaluations/frameworks"),
      (rows, el) => {
        if (!rows.length) return void (el.innerHTML = ui.empty("Çerçeve tanımlı değil."));
        el.innerHTML = table(
          ["Kod", "Ad", "Metodoloji yılı", "Açıklama"],
          rows.map((r) => [
            `<b>${fmt.esc(r.code)}</b>`,
            fmt.esc(r.name),
            fmt.int(r.methodology_year),
            fmt.esc(r.description || "—"),
          ])
        );
      }
    );

    load(
      "rkAssessments",
      async () => {
        const [assessments, frameworks] = await Promise.all([
          api.get("/api/ranking-evaluations/assessments"),
          api.get("/api/ranking-evaluations/frameworks"),
        ]);
        return { assessments, frameworks };
      },
      ({ assessments, frameworks }, el) => {
        if (!assessments.length)
          return void (el.innerHTML = ui.empty("Henüz değerlendirme hesaplanmadı."));
        const byId = new Map(frameworks.map((f) => [f.id, f]));
        el.innerHTML = table(
          ["Çerçeve", "Yıl", "Performans", "Veri hazırlık", "Uyum", "Eksik gösterge", "Risk"],
          assessments.map((a) => {
            const risk = (a.risk_level || "").toLowerCase();
            const level =
              risk === "critical" || risk === "kritik"
                ? "critical"
                : risk === "high" || risk === "yüksek"
                ? "warning"
                : risk === "medium" || risk === "orta"
                ? "info"
                : "good";
            return [
              fmt.esc(byId.get(a.framework_id)?.code || `#${a.framework_id}`),
              fmt.esc(a.academic_year),
              fmt.dec(a.performance_score, 1),
              fmt.pct(a.readiness_score),
              fmt.dec(a.compliance_score, 1),
              `${fmt.int(a.missing_indicator_count)} eksik · ${fmt.int(a.partial_indicator_count)} kısmi`,
              chip(level, a.risk_level),
            ];
          })
        );
      }
    );

    load(
      "rkBenchmarks",
      () => api.get("/api/ranking-evaluations/benchmarks/institutions"),
      (rows, el) => {
        if (!rows.length) return void (el.innerHTML = ui.empty("Kıyaslama kurumu tanımlı değil."));
        el.innerHTML = table(
          ["Kurum", "Ülke", "Tür", "Not"],
          rows.map((r) => [
            fmt.esc(r.name),
            fmt.esc(r.country || "—"),
            fmt.esc(r.institution_type || "—"),
            fmt.esc(r.notes || r.description || "—"),
          ])
        );
      }
    );
  },
};

/* ==================================================================
   Ortak yardımcılar
   ================================================================== */

function tileHtml(rows) {
  return rows
    .map(
      ([label, value, delta, dir]) =>
        `<div class="tile"><div class="label">${fmt.esc(label)}</div>` +
        `<div class="value">${value}</div>` +
        (delta ? `<div class="delta ${dir || ""}">${fmt.esc(delta)}</div>` : "") +
        `</div>`
    )
    .join("");
}

function table(headers, rows) {
  if (!rows.length) return ui.empty();
  return `<div class="table-wrap"><table>
    <thead><tr>${headers.map((h) => `<th>${fmt.esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows
      .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
      .join("")}</tbody></table></div>`;
}

function kv(label, value) {
  return `<div class="kv-item"><span class="kv-label">${fmt.esc(label)}</span><b>${value}</b></div>`;
}

async function fillSelect(id, rows, { valueKey = "id", labelKey = "name" } = {}) {
  const sel = document.getElementById(id);
  if (!sel) return;
  sel.innerHTML =
    `<option value="">Tümü</option>` + optionsHtml(rows, { valueKey, labelKey });
}

async function fillYearSelect(id, defaultYear = CURRENT_YEAR) {
  const sel = document.getElementById(id);
  if (!sel) return;
  try {
    const years = await ref.academicYears();
    sel.innerHTML = years.map((y) => `<option>${fmt.esc(y)}</option>`).join("");
    if (years.includes(defaultYear)) sel.value = defaultYear;
    else if (years.length) sel.value = years[years.length - 1];
  } catch {
    // Yıl listesi alınamazsa en azından güncel yıl seçilebilir olsun.
    sel.innerHTML = `<option>${defaultYear}</option>`;
  }
}
