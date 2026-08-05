// Genel bakış ekranları: Yönetim Panosu ve Akıllı Asistan.
// Bütün sayılar backend'den gelir; bu dosyada gömülü veri yoktur.

const CURRENT_YEAR = "2025-2026";

/* ==================================================================
   Yönetim Panosu
   ================================================================== */

VIEWS["dashboard"] = {
  title: "Yönetim Panosu",
  subtitle: "Kurum geneli konsolide görünüm · fakülte ve bölüm kırılımı",
  html: () => `
    <div id="headline"></div>

    <div class="grid cols-3-2">
      <div class="card">
        <h3>Öğrenci sayısı — program doluluk eğilimi</h3>
        <div class="note">Yıllara göre doluluk ve mezuniyet oranı.</div>
        <div id="trend"></div>
      </div>
      <div class="card">
        <h3>KPI karnesi</h3>
        <div class="note">Stratejik göstergelerin hedefe ulaşma oranı.</div>
        <div id="kpiRings"></div>
        <h4>En zayıf stratejik boyutlar</h4>
        <ul class="plain" id="weakDims"></ul>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Bölüm bazlı gelir ve gider</h3>
        <div class="note">Milyon USD · ${CURRENT_YEAR}</div>
        <div class="legend">
          <span><span class="swatch" style="background:var(--primary)"></span>Gelir</span>
          <span><span class="swatch" style="background:var(--accent)"></span>Gider</span>
        </div>
        <div id="facChart"></div>
      </div>
      <div class="card">
        <h3>Kritik riskler ve erken uyarılar</h3>
        <div class="note">Kural motorundan gelen aktif uyarılar.</div>
        <div id="risks"></div>
      </div>
    </div>

    <div class="card">
      <h3>Kırılım — fakülte → bölüm</h3>
      <div class="note">Fakülte satırına tıklayınca bölümleri açılır.</div>
      <div id="drill"></div>
    </div>

    <footer class="demo" id="dataNote"></footer>`,

  async init() {
    loadHeadline();
    loadTrend();
    loadKpiRings();
    loadFacultyFinance();
    loadRisks();
    loadDrilldown();

    document.getElementById("dataNote").innerHTML =
      "Tüm rakamlar SQLite veritabanından canlı okunur. Veri seti kurgusaldır " +
      "(integration/shared_demo_data/ altındaki varsayımlardan üretilmiştir) ve " +
      "gerçek bir kurumun verisi değildir.";
  },
};

// --- Üst gösterge kartları: 5 farklı modülden derlenir ---
async function loadHeadline() {
  await load(
    "headline",
    async () => {
      // Bir modül veri döndürmezse tüm pano çökmesin diye her çağrı ayrı
      // ele alınıyor; eksik gösterge "—" olarak görünür.
      const settle = (p) => p.then((v) => v).catch(() => null);
      const [students, finance, capacity, kpi, staff] = await Promise.all([
        settle(api.get("/api/student-analytics/overview")),
        settle(api.get(`/api/finance/${CURRENT_YEAR}/summary`)),
        settle(api.get("/api/physical-resources/capacity/overview")),
        settle(api.get("/api/kpi/scorecard", { academic_year: CURRENT_YEAR })),
        settle(api.get("/api/academic-staff/overview")),
      ]);
      return { students, finance, capacity, kpi, staff };
    },
    ({ students, finance, capacity, kpi, staff }, el) => {
      const activeShare =
        students && students.total_students
          ? ((students.active_students + students.newly_enrolled_students) /
              students.total_students) *
            100
          : null;

      const rows = [
        ["Toplam öğrenci", students ? fmt.int(students.total_students) : fmt.empty,
          students ? `${fmt.int(students.active_students)} aktif · ${fmt.int(students.newly_enrolled_students)} yeni` : "", ""],
        ["Aktif öğrenci oranı", fmt.pct(activeShare), students ? `${fmt.int(students.dropped_out_students)} ayrılan` : "", ""],
        ["Akademik personel", staff ? fmt.int(staff.total_staff) : fmt.empty,
          staff ? `${fmt.int(staff.total_publication)} yayın` : "", ""],
        ["Toplam gelir", finance ? fmt.usdMillion(finance.total_revenue) : fmt.empty,
          finance ? `öğrenci başına ${fmt.usdPerPerson(finance.revenue_per_student_thousand_usd)}` : "", ""],
        ["Toplam gider", finance ? fmt.usdMillion(finance.total_expenditure) : fmt.empty,
          finance ? `personel payı ${fmt.pct(finance.personnel_expense_share_percent)}` : "", ""],
        ["Gelir–gider dengesi", finance ? fmt.usdMillion(finance.balance) : fmt.empty,
          finance ? (finance.balance_status === "fazla" ? "▲ fazla" : "▼ açık") : "",
          finance && finance.balance_status === "fazla" ? "up" : "down"],
        ["Mekân doluluk oranı", capacity ? fmt.pct(capacity.overall_occupancy_percent) : fmt.empty,
          capacity ? `${capacity.overcrowded_count} aşırı dolu · ${capacity.underutilized_count} atıl` : "", ""],
        ["KPI genel başarı", kpi ? fmt.pct(kpi.overall_achievement_percent) : fmt.empty,
          kpi ? `${kpi.at_risk_count} riskli gösterge` : "",
          kpi && kpi.overall_status === "hedefte" ? "up" : "down"],
      ];

      el.className = "tiles";
      el.innerHTML = rows
        .map(
          ([label, value, delta, dir]) =>
            `<div class="tile"><div class="label">${fmt.esc(label)}</div>` +
            `<div class="value">${value}</div>` +
            (delta ? `<div class="delta ${dir}">${fmt.esc(delta)}</div>` : "") +
            `</div>`
        )
        .join("");
    }
  );
}

// --- Doluluk ve mezuniyet oranı eğilimi ---
// Modül 2'nin trend endpoint'i tek metrik döndürür; iki seri için iki çağrı
// yapılıyor. Tek çağrıda birleştirmek backend'i değiştirmeyi gerektirirdi.
async function loadTrend() {
  await load(
    "trend",
    async () => {
      const [occupancy, graduation] = await Promise.all([
        api.get("/api/student-analytics/trends", { metric: "occupancy-rate" }),
        api.get("/api/student-analytics/trends", { metric: "graduation-rate" }),
      ]);
      return { occupancy, graduation };
    },
    ({ occupancy, graduation }, el) => {
      const points = occupancy.points || occupancy.data_points || [];
      if (!points.length) {
        el.innerHTML = ui.empty("Trend verisi üretilemedi.");
        return;
      }
      const labels = points.map((p) => p.label || p.academic_year || String(p.year));
      const gradPoints = graduation.points || graduation.data_points || [];

      el.id = "trendChart";
      lineChart(
        "trendChart",
        labels,
        [
          {
            label: "Doluluk oranı",
            color: "var(--primary)",
            values: points.map((p) => Number(p.value) || 0),
          },
          {
            label: "Mezuniyet oranı",
            color: "var(--accent)",
            values: labels.map((_, i) => Number(gradPoints[i]?.value) || 0),
          },
        ],
        { min: 0, max: 100, yfmt: (v) => Math.round(v) + "%" }
      );
      el.insertAdjacentHTML(
        "beforeend",
        `<div class="legend">
           <span><span class="swatch" style="background:var(--primary)"></span>Doluluk oranı</span>
           <span><span class="swatch" style="background:var(--accent)"></span>Mezuniyet oranı</span>
         </div>`
      );
    }
  );
}

// --- KPI halkaları ---
async function loadKpiRings() {
  await load(
    "kpiRings",
    () => api.get("/api/kpi/scorecard", { academic_year: CURRENT_YEAR }),
    (card, el) => {
      const total = card.total_kpis || 1;
      el.id = "kpiRingBox";
      donuts("kpiRingBox", [
        ["Hedefte", Math.round((card.on_track_count / total) * 100), "#0ca30c"],
        ["Gecikmeli", Math.round((card.delayed_count / total) * 100), "var(--accent)"],
        ["Riskli", Math.round((card.at_risk_count / total) * 100), "var(--critical, #c0392b)"],
      ]);
      el.insertAdjacentHTML(
        "beforeend",
        `<div class="note">${card.total_kpis} gösterge · genel başarı ${fmt.pct(
          card.overall_achievement_percent
        )} (${fmt.esc(card.overall_status)})</div>`
      );

      const weak = document.getElementById("weakDims");
      if (weak) {
        weak.innerHTML = card.by_dimension
          .slice(0, 4)
          .map((d) => {
            const level = Number(d.average_achievement_percent) < 70 ? "critical" : "warning";
            return `<li>${chip(level, fmt.pct(d.average_achievement_percent))}${fmt.esc(
              d.dimension
            )} <span class="push" style="font-size:.72rem">${d.kpi_count} gösterge</span></li>`;
          })
          .join("");
      }
    }
  );
}

// --- Bölüm bazlı gelir/gider ---
async function loadFacultyFinance() {
  await load(
    "facChart",
    () => api.get(`/api/finance/${CURRENT_YEAR}/departments`),
    (rows, el) => {
      if (!rows.length) {
        el.innerHTML = ui.empty("Bölüm bütçesi girilmemiş.");
        return;
      }
      const top = rows.slice(0, 6);
      const bars = [];
      top.forEach((r) => {
        bars.push([`${r.department_name} — gelir`, Number(r.revenue), "var(--primary)"]);
        bars.push([`${r.department_name} — gider`, Number(r.expenditure), "var(--accent)"]);
      });
      el.id = "facBars";
      hbars("facBars", bars, { fmt: (v) => fmt.usdMillion(v) });
    }
  );
}

// --- Erken uyarılar ---
async function loadRisks() {
  await load(
    "risks",
    () => api.get("/api/early-warning/alerts", { academic_year: CURRENT_YEAR }),
    (alerts, el) => {
      if (!alerts.length) {
        el.innerHTML = ui.empty("Bu dönem için açık uyarı yok.");
        return;
      }
      // Önce kritik olanlar gösterilsin.
      const order = { kritik: 0, yüksek: 1, orta: 2, düşük: 3 };
      const sorted = [...alerts].sort(
        (a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9)
      );
      const levelClass = (s) =>
        s === "kritik" ? "critical" : s === "orta" ? "warning" : "info";

      el.innerHTML =
        `<ul class="plain">` +
        sorted
          .slice(0, 6)
          .map(
            (a) =>
              `<li>${chip(levelClass(a.severity), a.severity)}${fmt.esc(a.rule_name)}
                 ${a.scope_name ? `<span class="push" style="font-size:.72rem">${fmt.esc(a.scope_name)}</span>` : ""}
               </li>`
          )
          .join("") +
        `</ul>
         <div class="note">Toplam ${alerts.length} uyarı · <a href="#/alerts">tümünü gör →</a></div>`;
    }
  );
}

// --- Fakülte → bölüm kırılımı ---
async function loadDrilldown() {
  await load(
    "drill",
    async () => {
      const settle = (p) => p.then((v) => v).catch(() => []);
      const [faculties, departments, budgets, byDept] = await Promise.all([
        ref.faculties(),
        ref.departments(),
        settle(api.get(`/api/finance/${CURRENT_YEAR}/departments`)),
        settle(api.get("/api/student-analytics/by-department")),
      ]);
      return { faculties, departments, budgets, byDept };
    },
    ({ faculties, departments, budgets, byDept }, el) => {
      const budgetByDept = new Map(budgets.map((b) => [b.department_id, b]));
      const studentsByDept = new Map(
        (Array.isArray(byDept) ? byDept : []).map((d) => [d.department_id, d])
      );

      // Fakülte toplamları bölümlerden türetilir; ayrı bir yerde saklanan
      // toplam ile bölüm toplamının ayrışması riski böylece ortadan kalkar.
      const groups = faculties.map((f) => {
        const children = departments.filter((d) => d.faculty_id === f.id);
        const sum = (fn) =>
          children.reduce((acc, d) => {
            const v = fn(d);
            return acc + (Number.isFinite(v) ? v : 0);
          }, 0);
        return {
          faculty: f,
          children,
          students: sum((d) => Number(studentsByDept.get(d.id)?.total_students)),
          revenue: sum((d) => Number(budgetByDept.get(d.id)?.revenue)),
          expenditure: sum((d) => Number(budgetByDept.get(d.id)?.expenditure)),
        };
      });

      const open = new Set();
      const cell = (v) => (v ? fmt.usdMillion(v) : fmt.empty);

      const render = () => {
        el.innerHTML = `<div class="table-wrap"><table><thead><tr>
            <th>Birim</th><th>Öğrenci</th><th>Gelir</th><th>Gider</th>
            <th>Denge</th><th>Bütçe durumu</th></tr></thead><tbody>${groups
              .map((g, i) => {
                let html = `<tr data-i="${i}" style="cursor:pointer;font-weight:600">
                  <td>${open.has(i) ? "▾ " : "▸ "}${fmt.esc(g.faculty.name)}</td>
                  <td>${g.students ? fmt.int(g.students) : fmt.empty}</td>
                  <td>${cell(g.revenue)}</td><td>${cell(g.expenditure)}</td>
                  <td>${g.revenue || g.expenditure ? fmt.usdMillion(g.revenue - g.expenditure) : fmt.empty}</td>
                  <td>${g.children.length} bölüm</td></tr>`;
                if (open.has(i)) {
                  html += g.children
                    .map((d) => {
                      const b = budgetByDept.get(d.id);
                      const s = studentsByDept.get(d.id);
                      const status = b ? b.budget_status : null;
                      const level =
                        status === "bütçe aşımı"
                          ? "critical"
                          : status === "hafif aşım"
                          ? "warning"
                          : status === "bütçe içinde"
                          ? "good"
                          : "neutral";
                      return `<tr class="sub">
                        <td>${fmt.esc(d.name)}</td>
                        <td>${s ? fmt.int(s.total_students) : fmt.empty}</td>
                        <td>${b ? fmt.usdMillion(b.revenue) : fmt.empty}</td>
                        <td>${b ? fmt.usdMillion(b.expenditure) : fmt.empty}</td>
                        <td>${b ? fmt.usdMillion(b.balance) : fmt.empty}</td>
                        <td>${b ? chip(level, status) : fmt.empty}</td></tr>`;
                    })
                    .join("");
                }
                return html;
              })
              .join("")}</tbody></table></div>`;

        el.querySelectorAll("tr[data-i]").forEach((tr) =>
          tr.addEventListener("click", () => {
            const i = Number(tr.dataset.i);
            open.has(i) ? open.delete(i) : open.add(i);
            render();
          })
        );
      };
      render();
    }
  );
}

/* ==================================================================
   Akıllı Asistan — altyapı hazır, dil modeli BAĞLI DEĞİL
   ================================================================== */

VIEWS["assistant"] = {
  title: "Akıllı Asistan",
  subtitle: "Doğal dille soru sorma altyapısı · dil modeli henüz bağlı değil",
  html: () => `
    <div class="card">
      <h3>Durum</h3>
      <div id="assistantStatus">${ui.loading("Asistan durumu sorgulanıyor…")}</div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Bu ekran şu anda ne yapıyor?</h3>
        <p class="note">
          Asistan katmanının <b>veri erişimi ve bağlam hazırlama</b> bölümü çalışır durumda.
          Aşağıdaki düğmeye bastığınızda sistem, sorunuza cevap üretmek için hangi
          kurumsal verileri toplayacağını gösterir. Bu veriler gerçek veritabanından okunur.
        </p>
        <p class="note">
          <b>Cevap üretilmez.</b> Bir dil modeli (LLM) bağlı olmadığı için sistem
          uydurma bir cevap yazmaz. Model bağlandığında aynı bağlam modele gönderilecektir.
        </p>
        <label class="f">Örnek soru
          <select id="assistantSample"></select>
        </label>
        <label class="f">Kendi sorunuz
          <input id="assistantQuestion" placeholder="Örn: Hangi programların doluluk oranı düşüyor?">
        </label>
        <button class="primary" id="assistantRun">Bağlamı hazırla</button>
      </div>

      <div class="card">
        <h3>Hazırlanan bağlam</h3>
        <div class="note">Soruya göre toplanan kurumsal veri özeti.</div>
        <div id="assistantContext">${ui.empty("Henüz soru gönderilmedi.")}</div>
      </div>
    </div>

    <div class="card">
      <h3>Model bağlandığında ne olacak?</h3>
      <div id="assistantArchitecture"></div>
    </div>`,

  async init() {
    // Durum bilgisi sunucudan gelir; arayüzde sabit yazmak yerine backend'in
    // gerçek yapılandırmasını göstermek daha dürüst.
    await load(
      "assistantStatus",
      () => api.get("/api/assistant/status"),
      (status, el) => {
        const enabled = status.enabled;
        el.innerHTML = `
          <div class="tiles">
            <div class="tile"><div class="label">Asistan</div>
              <div class="value">${enabled ? "Etkin" : "Devre dışı"}</div>
              <div class="delta ${enabled ? "up" : "down"}">ASSISTANT_ENABLED=${enabled}</div></div>
            <div class="tile"><div class="label">Dil modeli sağlayıcı</div>
              <div class="value">${fmt.esc(status.provider || "seçilmedi")}</div>
              <div class="delta">LLM_PROVIDER</div></div>
            <div class="tile"><div class="label">Model</div>
              <div class="value">${fmt.esc(status.model || "seçilmedi")}</div>
              <div class="delta">LLM_MODEL</div></div>
            <div class="tile"><div class="label">API anahtarı</div>
              <div class="value">${status.api_key_configured ? "tanımlı" : "tanımsız"}</div>
              <div class="delta">kaynak koda yazılmaz</div></div>
          </div>
          <div class="state ${enabled ? "empty" : "warn"}">
            ${fmt.esc(status.message)}
          </div>`;
      }
    );

    // Örnek sorular da sunucudan gelir.
    try {
      const samples = await api.get("/api/assistant/sample-questions");
      const sel = document.getElementById("assistantSample");
      sel.innerHTML =
        `<option value="">— seçiniz —</option>` +
        samples
          .map((s) => `<option value="${fmt.esc(s.question)}">${fmt.esc(s.question)}</option>`)
          .join("");
      sel.addEventListener("change", () => {
        if (sel.value) document.getElementById("assistantQuestion").value = sel.value;
      });
    } catch (err) {
      ui.toast("Örnek sorular alınamadı: " + err.userMessage, "error");
    }

    document.getElementById("assistantRun").addEventListener("click", async () => {
      const question = document.getElementById("assistantQuestion").value.trim();
      if (!question) {
        ui.toast("Önce bir soru yazın veya örneklerden seçin.", "error");
        return;
      }
      await load(
        "assistantContext",
        () => api.post("/api/assistant/prepare-context", { question }),
        (ctx, el) => {
          el.innerHTML = `
            <div class="state warn"><b>Cevap üretilmedi.</b>
              <div class="msg">${fmt.esc(ctx.notice)}</div></div>
            <h4>Sorunun eşleştiği konu</h4>
            <p class="note">${fmt.esc(ctx.matched_topic || "genel")}</p>
            <h4>Toplanan veri (${ctx.context_items.length} başlık)</h4>
            <div class="table-wrap"><table><thead><tr>
              <th>Kaynak modül</th><th>Gösterge</th><th>Değer</th></tr></thead><tbody>
              ${ctx.context_items
                .map(
                  (i) =>
                    `<tr><td>${fmt.esc(i.source_module)}</td><td>${fmt.esc(
                      i.label
                    )}</td><td>${fmt.esc(i.value)}</td></tr>`
                )
                .join("")}
            </tbody></table></div>`;
        }
      );
    });

    await load(
      "assistantArchitecture",
      () => api.get("/api/assistant/architecture"),
      (arch, el) => {
        el.innerHTML = `
          <p class="note">${fmt.esc(arch.summary)}</p>
          <div class="table-wrap"><table><thead><tr>
            <th>Bileşen</th><th>Sorumluluk</th><th>Durum</th></tr></thead><tbody>
            ${arch.components
              .map(
                (c) =>
                  `<tr><td><code>${fmt.esc(c.file)}</code></td><td>${fmt.esc(
                    c.responsibility
                  )}</td><td>${chip(
                    c.status === "hazır" ? "good" : "warning",
                    c.status
                  )}</td></tr>`
              )
              .join("")}
          </tbody></table></div>
          <h4>Bağlamak için yapılması gerekenler</h4>
          <ol class="plain">${arch.next_steps
            .map((s) => `<li>${fmt.esc(s)}</li>`)
            .join("")}</ol>`;
      }
    );
  },
};
