// Performans Göstergeleri ekranı.
//
// TASARIM İLKESİ: önceki sürümde 16 göstergenin tamamı, formülleri, veri
// kaynakları ve fakülte karşılaştırması aynı anda tek sayfada duruyordu.
// Ekran bir veritabanı dökümü gibi görünüyordu. Şimdi üç sekmeye ayrıldı ve
// her sekme YALNIZCA açıldığında veri çekiyor.
//
//   1. Genel Bakış          → karar için gereken özet
//   2. Müdahale Gerektirenler → hedefin altındaki göstergeler + eylem
//   3. Tüm Göstergeler      → aranabilir tablo, ayrıntı satır açılınca gelir
//
// Bu ekranda fakülte/bölüm filtresi YOKTUR: göstergelerin çoğu kurum
// düzeyindedir ve hepsi için bölüm kırılımı bulunmadığından zorunlu bir
// organizasyon filtresi sahte bir kırılım izlenimi verirdi.

VIEWS["kpi"] = {
  title: "Performans Göstergeleri",
  subtitle: "Stratejik hedeflere ulaşma durumu",
  html: () => `
    <div class="card">
      <div class="filters">
        <label class="f">Akademik dönem <select id="kpiYear"></select></label>
        <span class="muted">
          Kurum geneli göstergeler. Bölüm kırılımı yalnızca ölçümü bölüm
          düzeyinde toplanan göstergelerde bulunur.
        </span>
      </div>
    </div>

    ${ux.tabs("kpiTabs", [
      { key: "overview", label: "Genel Bakış" },
      { key: "attention", label: "Müdahale Gerektirenler" },
      { key: "all", label: "Tüm Göstergeler" },
    ])}`,

  async init() {
    const years = await api
      .get("/api/academic-success/academic-years")
      .catch(() => [CURRENT_YEAR]);
    const select = document.getElementById("kpiYear");
    select.innerHTML = years.map((y) => `<option>${fmt.esc(y)}</option>`).join("");
    select.value = years.includes(CURRENT_YEAR) ? CURRENT_YEAR : years[years.length - 1];

    // Dönem değişince açık sekme yeniden yüklenir; diğerleri dokunulmaz.
    select.addEventListener("change", () => {
      KPI_LOADED.clear();
      const active = document.querySelector("#kpiTabs .tab-btn.is-active");
      if (active) loadKpiTab(active.dataset.tab, `kpiTabs-${active.dataset.tab}`);
    });

    // Sekmeye tıklanana kadar o sekmenin verisi ÇEKİLMEZ.
    ux.bindTabs("kpiTabs", (key, panelId) => loadKpiTab(key, panelId));
  },
};

const KPI_LOADED = new Set();

function kpiYear() {
  return document.getElementById("kpiYear").value;
}

/** Durum → rozet türü. Veri eksikliği gri; riskli değil. */
function kpiStatusKind(status) {
  return (
    { hedefte: "good", gecikmeli: "warning", riskli: "critical", "veri eksik": "nodata" }[
      status
    ] || "info"
  );
}

function loadKpiTab(key, panelId) {
  if (KPI_LOADED.has(key)) return;
  KPI_LOADED.add(key);
  if (key === "overview") renderKpiOverview(panelId);
  if (key === "attention") renderKpiAttention(panelId);
  if (key === "all") renderKpiAll(panelId);
}

/* ================================================================== */
/* 1. Genel Bakış                                                      */
/* ================================================================== */

function renderKpiOverview(panelId) {
  const panel = document.getElementById(panelId);
  panel.innerHTML = ux.skeleton(3);

  load(
    panelId,
    () => api.get("/api/kpi/scorecard", { academic_year: kpiYear() }),
    (card, el) => {
      const overall = card.overall_achievement_percent;
      const overallKind =
        overall === null ? "nodata"
        : Number(overall) >= 90 ? "good"
        : Number(overall) >= 70 ? "warning"
        : "critical";

      // Ölçülen boyutlar sıralanır; ölçümü olmayanlar ayrı gösterilir.
      const measured = card.by_dimension.filter(
        (d) => d.average_achievement_percent !== null
      );
      const ranked = [...measured].sort(
        (a, b) =>
          Number(b.average_achievement_percent) - Number(a.average_achievement_percent)
      );
      const strongest = ranked.slice(0, 3);
      const weakest = ranked.slice(-3).reverse();
      const shownNames = new Set([...strongest, ...weakest].map((d) => d.dimension));
      const others = card.by_dimension.filter((d) => !shownNames.has(d.dimension));

      const dimensionRow = (d) => {
        const value = d.average_achievement_percent;
        const kind =
          value === null ? "nodata"
          : Number(value) >= 90 ? "good"
          : Number(value) >= 70 ? "warning"
          : "critical";
        const color =
          value === null ? "rgba(127,127,127,0.3)"
          : kind === "good" ? "#0ca30c"
          : kind === "warning" ? "var(--accent, #e08c00)"
          : "var(--critical, #c0392b)";
        return `<div class="criterion">
          <div class="criterion-name">${fmt.esc(d.dimension)}
            <small>${d.kpi_count} gösterge${
              d.no_data_count ? ` · ${d.no_data_count} tanesinin verisi yok` : ""
            }</small></div>
          <div class="criterion-track">
            <div class="criterion-fill" style="width:${
              value === null ? 0 : Math.min(100, Number(value))
            }%;background:${color}"></div>
          </div>
          <div class="criterion-value${value === null ? " is-missing" : ""}">${
            value === null ? "Veri yok" : fmt.pct(value, 0)
          }</div>
        </div>`;
      };

      el.innerHTML = `
        <div class="summary-strip">
          <div class="summary-item is-${overallKind}">
            <div class="label">Genel başarı</div>
            <div class="value">${overall === null ? "Hesaplanamadı" : fmt.pct(overall, 0)}</div>
            <div class="sub">${fmt.esc(card.overall_status)}</div>
          </div>
          <div class="summary-item is-good">
            <div class="label">Hedefte</div>
            <div class="value">${card.on_track_count}</div>
            <div class="sub">gösterge hedefine ulaştı</div>
          </div>
          <div class="summary-item is-warning">
            <div class="label">Gecikmeli</div>
            <div class="value">${card.delayed_count}</div>
            <div class="sub">hedefin biraz altında</div>
          </div>
          <div class="summary-item is-critical">
            <div class="label">Riskli</div>
            <div class="value">${card.at_risk_count}</div>
            <div class="sub">acil müdahale gerekiyor</div>
          </div>
          ${
            card.no_data_count
              ? `<div class="summary-item is-nodata">
                   <div class="label">Ölçüm bekleyen</div>
                   <div class="value">${card.no_data_count}</div>
                   <div class="sub">veri toplanmamış</div>
                 </div>`
              : ""
          }
        </div>

        <div class="note">${fmt.esc(card.average_basis_note || "")}</div>

        <div class="grid cols-2">
          <div class="card">
            <h3>En güçlü stratejik alanlar</h3>
            <div class="note">Hedefe ulaşma oranı en yüksek üç alan.</div>
            ${strongest.map(dimensionRow).join("") || ui.empty("Ölçülen alan yok.")}
          </div>
          <div class="card">
            <h3>En zayıf stratejik alanlar</h3>
            <div class="note">Önce bu alanlara odaklanılması önerilir.</div>
            ${weakest.map(dimensionRow).join("") || ui.empty("Ölçülen alan yok.")}
          </div>
        </div>

        ${
          others.length
            ? ux.details(
                "Diğer stratejik alanları göster",
                others.map(dimensionRow).join(""),
                { hint: `${others.length} alan daha` }
              )
            : ""
        }

        <div class="card">
          <h3>Fakülte karşılaştırması</h3>
          <div class="note">
            Yalnızca ölçümü fakülte düzeyinde toplanan göstergeler dikkate alınır.
            Bir fakülteye tıklayarak bölüm ve program kırılımına inebilirsiniz.
          </div>
          <div id="kpiFacultyChart"></div>
        </div>`;

      loadKpiFacultyChart();
    }
  );
}

function loadKpiFacultyChart() {
  load(
    "kpiFacultyChart",
    () => api.get("/api/kpi/faculty-comparison", { academic_year: kpiYear() }),
    (rows, el) => {
      if (!rows.length) {
        el.innerHTML = ui.empty(
          "Hiçbir gösterge için fakülte kırılımı girilmemiş. " +
            "Fakülte karşılaştırması yapılabilmesi için göstergelere fakülte " +
            "bazlı ölçüm eklenmelidir."
        );
        return;
      }
      el.id = "kpiFacultyBars";
      hbars(
        "kpiFacultyBars",
        rows.map((r) => {
          const v = Number(r.average_achievement_percent);
          return [
            r.faculty_name,
            v,
            v >= 90 ? "#0ca30c" : v >= 70 ? "var(--accent, #e08c00)" : "var(--critical, #c0392b)",
          ];
        }),
        {
          max: 120,
          fmt: (v) => fmt.pct(v, 0),
          valueLabel: "Hedefe ulaşma oranı (%)",
          legend: [
            ["Hedefte (%90+)", "#0ca30c"],
            ["Gecikmeli (%70–90)", "var(--accent, #e08c00)"],
            ["Riskli (%70 altı)", "var(--critical, #c0392b)"],
          ],
        }
      );
      el.insertAdjacentHTML(
        "beforeend",
        ux.details(
          "Fakülte detayını incele",
          table(
            ["Fakülte", "Ölçülen gösterge", "Ortalama başarı", "Ortalamanın üstünde"],
            rows.map((r) => [
              fmt.esc(r.faculty_name),
              fmt.int(r.measured_kpi_count),
              fmt.pct(r.average_achievement_percent),
              fmt.int(r.kpis_above_university_average),
            ])
          ) +
            `<p class="note muted">
               Bölüm ve program kırılımı yalnızca ölçümü o düzeyde toplanan
               göstergeler için anlamlıdır. Kurum düzeyinde toplanan göstergeler
               için bölüm verisi üretilmez.
             </p>`,
          { hint: "Ölçüm sayıları ve kırılım" }
        )
      );
    }
  );
}

/* ================================================================== */
/* 2. Müdahale Gerektirenler                                           */
/* ================================================================== */

function renderKpiAttention(panelId) {
  const panel = document.getElementById(panelId);
  panel.innerHTML = ux.skeleton(4);

  load(
    panelId,
    async () => {
      const [attention, missing] = await Promise.all([
        api.get("/api/kpi/attention", { academic_year: kpiYear() }),
        api.get("/api/kpi/missing-data", { academic_year: kpiYear() }).catch(() => []),
      ]);
      return { attention, missing };
    },
    ({ attention, missing }, el) => {
      if (!attention.length && !missing.length) {
        el.innerHTML = ui.empty(
          "Tüm göstergeler hedefinde. Müdahale gerektiren gösterge bulunmuyor."
        );
        return;
      }

      const card = (r) => {
        const kind = kpiStatusKind(r.status);
        const gap =
          r.achievement_percent === null
            ? null
            : 100 - Number(r.achievement_percent);
        return `<div class="card">
          <div class="section-head">
            <div>
              <h3 style="margin:0">${fmt.esc(r.name)}</h3>
              <div class="note">${fmt.esc(r.dimension)}</div>
            </div>
            ${ux.statusBadge(
              kind,
              r.status,
              kind === "critical"
                ? "Hedefin belirgin biçimde altında; acil müdahale gerekiyor."
                : "Hedefin biraz altında; iyileştirme planı gerekiyor."
            )}
          </div>

          <div class="kv">
            ${kv("Mevcut değer", `<b>${fmt.dec(r.current_value, 2)}</b> ${fmt.esc(r.unit || "")}`)}
            ${kv("Hedef", `${fmt.dec(r.target_value, 2)} ${fmt.esc(r.unit || "")}`)}
            ${kv("Hedefe ulaşma", fmt.pct(r.achievement_percent))}
            ${kv("Geçen döneme göre", fmt.esc(r.direction_label || "—"))}
          </div>

          <div class="state warn">
            <b>Sorun</b>
            <div class="msg">${fmt.esc(
              gap === null
                ? "Hedefe uzaklık hesaplanamadı."
                : `Gösterge hedefinin ${fmt.dec(gap, 1)} puan altında. ` +
                  (r.higher_is_better
                    ? "Değerin yükselmesi gerekiyor."
                    : "Değerin düşmesi gerekiyor.")
            )}</div>
          </div>

          ${
            r.corrective_action
              ? `<div class="state empty"><b>Önerilen eylem</b>
                   <div class="msg">${fmt.esc(r.corrective_action)}</div></div>`
              : ""
          }

          ${ux.details(
            "Hesaplama ayrıntısı",
            `<div class="kv">
               ${kv("Ne ölçer", fmt.esc(r.description || "—"))}
               ${kv("Formül", fmt.esc(r.formula || "—"))}
               ${kv("Veri kaynağı", fmt.esc(r.data_source || "—"))}
               ${kv("İyi yön", r.higher_is_better ? "▲ yükselmesi iyi" : "▼ düşmesi iyi")}
               ${kv("Hedefte eşiği", "%" + fmt.dec(r.on_track_threshold, 0))}
               ${kv("Risk eşiği", "%" + fmt.dec(r.at_risk_threshold, 0))}
             </div>`
          )}
        </div>`;
      };

      el.innerHTML =
        (attention.length
          ? `<div class="note">
               ${attention.length} gösterge hedefinin altında. En düşük başarıdan
               başlayarak sıralanmıştır.
             </div>` + attention.map(card).join("")
          : ui.empty("Hedefin altında ölçülen gösterge yok.")) +
        (missing.length
          ? `<div class="card">
               <h3>Ölçüm bekleyen göstergeler</h3>
               <div class="note">
                 ${ux.statusBadge("nodata", `${missing.length} gösterge`)}
                 Bunlar <b>riskli değildir</b>; henüz ölçüm yapılmamıştır ve
                 kurum ortalamasına dahil edilmemişlerdir.
               </div>
               ${ux.details(
                 "Listeyi göster",
                 `<ul class="plain">${missing
                   .map(
                     (r) =>
                       `<li><b>${fmt.esc(r.name)}</b>
                          <div class="note">${fmt.esc(r.description || "")}</div>
                          <div class="note muted">Beklenen kaynak: ${fmt.esc(
                            r.data_source || "—"
                          )}</div></li>`
                   )
                   .join("")}</ul>`
               )}
             </div>`
          : "");
    }
  );
}

/* ================================================================== */
/* 3. Tüm Göstergeler                                                  */
/* ================================================================== */

function renderKpiAll(panelId) {
  const panel = document.getElementById(panelId);
  panel.innerHTML = `
    <div class="card">
      <div class="filters">
        <label class="f">Stratejik alan <select id="kpiDim"><option value="">Tümü</option></select></label>
        <label class="f">Durum <select id="kpiStatus">
          <option value="">Tümü</option>
          <option value="hedefte">Hedefte</option>
          <option value="gecikmeli">Gecikmeli</option>
          <option value="riskli">Riskli</option>
          <option value="veri eksik">Ölçüm bekleyen</option>
        </select></label>
        <label class="f">Ara <input id="kpiSearch" type="search" placeholder="Gösterge adı"></label>
      </div>
    </div>
    <div id="kpiTable">${ux.skeleton(6)}</div>`;

  api
    .get("/api/kpi/dimensions")
    .then((dimensions) => {
      document.getElementById("kpiDim").innerHTML =
        `<option value="">Tümü</option>` +
        dimensions.map((d) => `<option>${fmt.esc(d)}</option>`).join("");
    })
    .catch(() => {});

  const refresh = () => refreshKpiTable();
  ["kpiDim", "kpiStatus"].forEach((id) =>
    document.getElementById(id).addEventListener("change", refresh)
  );
  document.getElementById("kpiSearch").addEventListener("input", () => {
    clearTimeout(window.__kpiSearchTimer);
    window.__kpiSearchTimer = setTimeout(refresh, 250);
  });

  refreshKpiTable();
}

function refreshKpiTable() {
  const dimension = document.getElementById("kpiDim").value || undefined;
  const status = document.getElementById("kpiStatus").value || undefined;
  const search = (document.getElementById("kpiSearch").value || "").toLowerCase();

  load(
    "kpiTable",
    () =>
      api.get("/api/kpi", {
        academic_year: kpiYear(),
        dimension,
        kpi_status: status,
      }),
    (rows, el) => {
      const filtered = search
        ? rows.filter((r) => r.name.toLowerCase().includes(search))
        : rows;

      if (!filtered.length) {
        el.innerHTML = ui.empty(
          search
            ? `"${search}" aramasına uyan gösterge bulunamadı.`
            : "Bu filtreye uyan gösterge yok."
        );
        return;
      }

      // Tabloda YALNIZCA dört sütun. Açıklama, formül ve kaynak satır
      // genişletilince görünür; hücrelere yığılmaz.
      const body = filtered
        .map(
          (r, index) => `
          <tr class="expandable" data-index="${index}">
            <td><b>${fmt.esc(r.name)}</b>
                <br><span class="muted">${fmt.esc(r.dimension)}</span></td>
            <td>${
              r.current_value === null
                ? `<span class="muted">Veri bulunamadı</span>`
                : `<b>${fmt.dec(r.current_value, 2)}</b> <span class="muted">${fmt.esc(r.unit || "")}</span>`
            }</td>
            <td>${fmt.dec(r.target_value, 2)}</td>
            <td>${
              r.achievement_percent === null
                ? `<span class="muted">—</span>`
                : fmt.pct(r.achievement_percent, 0)
            }</td>
            <td>${ux.statusBadge(kpiStatusKind(r.status), r.status)}</td>
          </tr>
          <tr class="row-detail hidden" data-detail="${index}">
            <td colspan="5">
              <div class="kv">
                ${kv("Ne ölçer", fmt.esc(r.description || "—"))}
                ${kv("Formül", fmt.esc(r.formula || "—"))}
                ${kv("Veri kaynağı", fmt.esc(r.data_source || "—"))}
                ${kv(
                  "Geçen dönem",
                  r.previous_value === null
                    ? "Geçen dönem verisi yok"
                    : fmt.dec(r.previous_value, 2)
                )}
                ${kv("Değişim", fmt.esc(r.direction_label || "—"))}
                ${kv("İyi yön", r.higher_is_better ? "▲ yükselmesi iyi" : "▼ düşmesi iyi")}
              </div>
              ${
                r.corrective_action
                  ? `<div class="note action">▸ ${fmt.esc(r.corrective_action)}</div>`
                  : ""
              }
            </td>
          </tr>`
        )
        .join("");

      el.innerHTML =
        `<div class="note">${filtered.length} gösterge · satıra tıklayarak ayrıntıyı açabilirsiniz</div>` +
        `<div class="table-wrap"><table>
          <thead><tr>
            <th>Gösterge</th><th>Mevcut</th><th>Hedef</th><th>Başarı</th><th>Durum</th>
          </tr></thead>
          <tbody>${body}</tbody>
        </table></div>`;

      el.querySelectorAll("tr.expandable").forEach((tr) => {
        tr.addEventListener("click", () => {
          const detail = el.querySelector(`tr[data-detail="${tr.dataset.index}"]`);
          detail.classList.toggle("hidden");
        });
      });
    }
  );
}
