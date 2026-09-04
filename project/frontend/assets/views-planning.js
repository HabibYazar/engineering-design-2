// Planlama ekranları: Senaryo Analizi ve Erken Uyarı.
//
// ÖNEMLİ: Bu ekranda hiçbir hesap yapılmaz. Senaryo türleri, girdi alanları,
// sınırlar ve karşılaştırma tablosunun tamamı sunucudan gelir.
//
// Neden: önceki sürümde senaryo türleri ve alan adları burada elle yazılıydı
// ve backend şemasıyla uyuşmuyordu ("staff_count_change" gönderiliyordu ama
// backend "academic_staff_change" bekliyordu). Sonuçta hiçbir parametre
// uygulanmıyor, her senaryo aynı sonucu döndürüyordu — kullanıcı değeri
// değiştirdiğini sanıp aynı tabloyu görüyordu. Katalog sunucudan geldiği için
// bu uyumsuzluk artık mümkün değil.

/* ==================================================================
   Senaryo Analizi
   ================================================================== */

// Backend risk seviyelerinin kullanıcıya gösterilecek Türkçe karşılıkları.
// Ekranda "critical" gibi teknik değerler görünmemeli.
const RISK_LEVEL_LABELS = {
  low: "düşük",
  medium: "orta",
  high: "yüksek",
  critical: "kritik",
};

VIEWS["scenarios"] = {
  title: "Senaryo Analizi",
  subtitle: "What-if simülasyonu · değişikliğin mali, akademik ve kapasite etkileri",
  html: () => `
    <div class="card">
      <h3>1. Karşılaştırma tabanını seçin</h3>
      <div class="note">
        Senaryo, seçtiğiniz mali dönemin <b>gerçekleşen</b> gelir ve gider
        verisi üzerinden hesaplanır. Böylece senaryo sonuçları Finansal Analiz
        ekranındaki rakamlarla birebir aynı olur.
      </div>
      <div class="filters">
        <label class="f">Mali dönem <select id="scPeriod"></select></label>
        <span class="muted" id="scPeriodNote"></span>
      </div>
    </div>

    <div class="grid cols-3-2">
      <div class="card">
        <h3>2. Senaryoyu tanımlayın</h3>
        <label class="f">Senaryo türü <select id="scType"></select></label>
        <div class="note" id="scQuestion"></div>
        <div id="scInputs"></div>
        <div class="form-actions">
          <button class="primary" id="scPreview">Hesapla</button>
          <button class="ghost" id="scReset">Sıfırla</button>
        </div>
        <div class="note" id="scExplain"></div>
      </div>

      <div class="card">
        <h3>Mevcut durum (taban)</h3>
        <div class="note">Değişiklik uygulanmadan önceki değerler.</div>
        <div id="scBaseline"></div>
      </div>
    </div>

    <div id="scResult">${ui.empty("Bir senaryo seçip Hesapla düğmesine basın.")}</div>`,

  async init() {
    // Mali dönemler ve senaryo kataloğu sunucudan alınır.
    const [periodInfo, catalog] = await Promise.all([
      api.get("/api/scenarios/financial-periods"),
      api.get("/api/scenarios/catalog"),
    ]);
    SCENARIO_CATALOG = catalog;

    const periodSelect = document.getElementById("scPeriod");
    periodSelect.innerHTML = periodInfo.periods
      .map((p) => `<option value="${fmt.esc(p)}">${fmt.esc(p)}</option>`)
      .join("");
    if (periodInfo.default) periodSelect.value = periodInfo.default;
    document.getElementById("scPeriodNote").textContent = periodInfo.note;
    periodSelect.addEventListener("change", loadScenarioBaseline);

    const typeSelect = document.getElementById("scType");
    typeSelect.innerHTML = catalog
      .map((t) => `<option value="${fmt.esc(t.key)}">${fmt.esc(t.label)}</option>`)
      .join("");
    typeSelect.addEventListener("change", renderScenarioInputs);

    // Kalem bazlı senaryolar için gelir/gider kalem listesi.
    SCENARIO_CATEGORIES = await api
      .get("/api/scenarios/financial-categories")
      .catch(() => ({ revenue_categories: [], expenditure_categories: [] }));

    renderScenarioInputs();
    loadScenarioBaseline();

    document.getElementById("scPreview").addEventListener("click", runScenarioPreview);
    document.getElementById("scReset").addEventListener("click", () => {
      renderScenarioInputs();
      document.getElementById("scResult").innerHTML = ui.empty(
        "Bir senaryo seçip Hesapla düğmesine basın."
      );
    });
  },
};

let SCENARIO_CATALOG = [];
let SCENARIO_CATEGORIES = { revenue_categories: [], expenditure_categories: [] };

function selectedScenario() {
  const key = document.getElementById("scType").value;
  return SCENARIO_CATALOG.find((t) => t.key === key) || SCENARIO_CATALOG[0];
}

function renderScenarioInputs() {
  const spec = selectedScenario();
  if (!spec) return;

  document.getElementById("scQuestion").innerHTML =
    `<b>Örnek soru:</b> ${fmt.esc(spec.question)}`;
  document.getElementById("scExplain").textContent = spec.description;

  document.getElementById("scInputs").innerHTML = spec.fields
    .map((f) => {
      // Kalem seçimi gereken alanlar açılır liste olarak çizilir; kullanıcı
      // kalem adını elle yazmak zorunda kalmaz.
      if (f.type === "revenue_category" || f.type === "expense_category") {
        const options =
          f.type === "revenue_category"
            ? SCENARIO_CATEGORIES.revenue_categories
            : SCENARIO_CATEGORIES.expenditure_categories;
        return `<label class="f">${fmt.esc(f.label)}
          <select data-key="${f.name}" data-kind="text">
            ${options.map((o) => `<option value="${fmt.esc(o)}">${fmt.esc(o)}</option>`).join("")}
          </select></label>`;
      }
      const unit = f.unit ? ` (${fmt.esc(f.unit)})` : "";
      return `<label class="f">${fmt.esc(f.label)}${unit}
        <input type="number" data-key="${f.name}" data-kind="number"
               value="${f.default}" min="${f.min}" max="${f.max}" step="${f.step}">
      </label>`;
    })
    .join("");
}

async function loadScenarioBaseline() {
  const period = document.getElementById("scPeriod").value;
  // Taban değerleri, hiçbir değişiklik uygulanmamış bir önizlemeden okunur.
  // Böylece ekranda gösterilen taban ile hesapta kullanılan taban aynı olur.
  await load(
    "scBaseline",
    () => api.post(`/api/scenarios/preview?financial_period=${encodeURIComponent(period)}`, {}),
    (r, el) => {
      const m = r.result;
      el.innerHTML = `
        <div class="kv">
          ${kv("Mali dönem", fmt.esc(period))}
          ${kv("Öğrenci sayısı", fmt.int(m.baseline_student_count))}
          ${kv("Akademik personel", fmt.int(m.baseline_staff_count))}
          ${kv("Toplam gelir", fmt.usd(m.baseline_revenue))}
          ${kv("Toplam gider", fmt.usd(m.baseline_expenditure))}
          ${kv("Gelir–gider dengesi", fmt.usd(m.baseline_balance ?? (Number(m.baseline_revenue) - Number(m.baseline_expenditure)))) }
          ${kv("Öğrenci başına maliyet", fmt.usd(m.baseline_cost_per_student))}
          ${kv("Öğrenci / öğretim üyesi", fmt.dec(m.baseline_student_staff_ratio, 2))}
          ${kv("Derslik kapasitesi", fmt.int(m.baseline_classroom_capacity))}
          ${kv("Laboratuvar kapasitesi", fmt.int(m.baseline_laboratory_capacity))}
        </div>
        <div class="note">Tüm parasal değerler ${r.comparison.currency} cinsindendir.</div>`;
    }
  );
}

async function runScenarioPreview() {
  const spec = selectedScenario();
  const period = document.getElementById("scPeriod").value;

  // Girdiler katalogdaki alan adlarıyla toplanır; arayüzde ad uydurulmaz.
  const inputs = {};
  document.querySelectorAll("#scInputs [data-key]").forEach((el) => {
    inputs[el.dataset.key] =
      el.dataset.kind === "number" ? Number(el.value) : el.value;
  });

  await load(
    "scResult",
    () =>
      api.post(
        `/api/scenarios/preview?financial_period=${encodeURIComponent(period)}`,
        inputs
      ),
    (r, el) => {
      const cmp = r.comparison;
      const cur = cmp.currency;
      const level = r.risk_level;
      const levelClass =
        level === "critical" ? "critical"
        : level === "high" ? "warning"
        : level === "medium" ? "info"
        : "good";

      // Değer biçimlendirmesi birime göre yapılır; çıplak sayı bırakılmaz.
      const showValue = (m, key) => {
        const v = m[key];
        if (m.unit === "usd") return fmt.usd(v);
        if (m.unit === "percent") return fmt.pct(v);
        if (m.unit === "count") return fmt.int(v);
        return fmt.dec(v, 2);
      };
      const showDelta = (m) => {
        const sign = Number(m.absolute_change) > 0 ? "+" : "";
        const abs =
          m.unit === "usd" ? fmt.usd(m.absolute_change)
          : m.unit === "percent" ? fmt.dec(m.absolute_change, 2) + " puan"
          : m.unit === "count" ? fmt.int(m.absolute_change)
          : fmt.dec(m.absolute_change, 2);
        return sign + abs;
      };

      const groupTable = (rows, title, note) => {
        if (!rows.length) return "";
        return `<div class="card">
          <h3>${fmt.esc(title)}</h3>
          <div class="note">${fmt.esc(note)}</div>
          ${table(
            ["Gösterge", "Önceki değer", "Yeni değer", "Değişim", "Yüzde", "Yorum"],
            rows.map((m) => {
              const cls =
                m.is_favorable === true ? "good"
                : m.is_favorable === false ? "critical"
                : "info";
              const arrow = m.direction === "up" ? "▲" : m.direction === "down" ? "▼" : "—";
              const verdict =
                m.is_favorable === true ? "olumlu"
                : m.is_favorable === false ? "olumsuz"
                : "nötr";
              return [
                `<b>${fmt.esc(m.label)}</b><br><span class="muted">${fmt.esc(m.description)}</span>`,
                showValue(m, "baseline_value"),
                `<b>${showValue(m, "projected_value")}</b>`,
                `${arrow} ${showDelta(m)}`,
                m.percent_change === null ? fmt.empty : fmt.pct(m.percent_change, 2),
                m.direction === "flat" ? chip("neutral", "değişmedi") : chip(cls, verdict),
              ];
            })
          )}
        </div>`;
      };

      const highlights = cmp.most_significant
        .map((m) => {
          const cls =
            m.is_favorable === true ? "good"
            : m.is_favorable === false ? "critical"
            : "info";
          return `<div class="tile">
            <div class="label">${fmt.esc(m.label)}</div>
            <div class="value">${showValue(m, "projected_value")}</div>
            <div class="delta ${m.is_favorable === false ? "down" : "up"}">
              ${m.percent_change === null ? fmt.empty : fmt.pct(m.percent_change, 2)}
              · önceki ${showValue(m, "baseline_value")}
            </div>
          </div>`;
        })
        .join("");

      el.innerHTML = `
        <div class="card">
          <h3>Senaryo sonucu — ${fmt.esc(spec.label)}</h3>
          <div class="state ${level === "low" ? "empty" : "warn"}">
            ${chip(levelClass, "Genel risk: " + (RISK_LEVEL_LABELS[level] || level))}
            ${fmt.esc(r.recommendation || "")}
          </div>
          <h4>En çok değişen göstergeler</h4>
          <div class="tiles">${highlights}</div>
          <div class="note">
            Taban: <b>${fmt.esc(period)}</b> mali dönemi ·
            Para birimi: <b>${fmt.esc(cur)}</b> ·
            Bu bir <b>önizlemedir</b>, veritabanına kayıt yazılmamıştır.
          </div>
        </div>

        ${ux.details(
          "Mali etkinin tüm kalemleri",
          groupTable(cmp.financial, "Mali etki",
            "Gelir, gider, denge ve öğrenci başına maliyet üzerindeki etki. Tüm tutarlar " + cur + "."),
          { hint: cmp.financial.length + " kalem" }
        )}
        ${ux.details(
          "Akademik etkinin tüm kalemleri",
          groupTable(cmp.academic, "Akademik etki",
            "Öğrenci ve personel sayıları ile öğretim üyesi başına düşen öğrenci."),
          { hint: cmp.academic.length + " kalem" }
        )}
        ${ux.details(
          "Kapasite etkisinin tüm kalemleri",
          groupTable(cmp.capacity, "Kapasite etkisi",
            "Eş zamanlı talep, tüm öğrencilerin aynı anda derslikte olmadığı varsayımıyla hesaplanır."),
          { hint: cmp.capacity.length + " kalem" }
        )}

        ${
          r.risks.length
            ? `<div class="card"><h3>Dikkat edilmesi gerekenler</h3>
                ${ux.limitedList(
                  r.risks,
                  3,
                  (x) =>
                    `<li>${chip(
                      x.level === "critical" ? "critical"
                      : x.level === "high" ? "warning" : "info",
                      RISK_LEVEL_LABELS[x.level] || x.level
                    )}${fmt.esc(x.message || x.description || "")}</li>`,
                  "Diğer uyarıları göster"
                )}</div>`
            : `<div class="card"><h3>Dikkat edilmesi gerekenler</h3>${ui.empty(
                "Bu senaryoda hiçbir risk kuralı tetiklenmedi."
              )}</div>`
        }`;
    }
  );
}


/* ==================================================================
   Erken Uyarı Sistemi
   ================================================================== */

VIEWS["alerts"] = {
  title: "Erken Uyarı Sistemi",
  subtitle: "Kural motoru tabanlı otomatik risk tespiti",
  html: () => `
    <div class="card">
      <div class="filters">
        <label class="f">Akademik yıl <select id="alYear"></select></label>
        <label class="f">Şiddet <select id="alSeverity">
          <option value="">Tümü</option>
          <option value="kritik">Kritik</option>
          <option value="orta">Orta</option>
          <option value="düşük">Düşük</option>
        </select></label>
        <button class="ghost" id="alApply">Uygula</button>
      </div>
    </div>

    <div id="alSummary"></div>

    <div class="card">
      <h3>Açık uyarılar</h3>
      <div class="note">
        Her uyarı; hangi kuraldan, hangi ölçüme dayanarak ve hangi eşikle
        üretildiğini gösterir. "Kara kutu uyarı" bırakılmaz.
      </div>
      <div id="alList"></div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Uyarı kuralları</h3>
        <div class="note">
          Sistemin hangi durumda uyarı ürettiğini gösterir. Kurallar yönetici
          tarafından güncellenebilir.
        </div>
        <div id="alRules"></div>
      </div>
      <div class="card">
        <h3>Veri beklendiği için çalışmayan kurallar</h3>
        <div class="note">
          Bu kurallar tanımlı, ancak gerekli ölçüm henüz girilmediği için
          değerlendirilemiyor. Sonuç üretiyormuş gibi gösterilmez.
        </div>
        <div id="alPending"></div>
      </div>
    </div>`,

  async init() {
    await fillYearSelect("alYear");
    document.getElementById("alApply").addEventListener("click", () => refreshAlerts());
    refreshAlerts();

    load(
      "alRules",
      () => api.get("/api/early-warning/rules"),
      (rows, el) => {
        el.innerHTML = table(
          ["Kural", "Kapsam", "Şiddet eşikleri"],
          rows.map((r) => [
            `<b>${fmt.esc(r.rule_name || r.name)}</b><br><span class="muted">${fmt.esc(
              r.pdf_condition || r.description || ""
            )}</span>`,
            fmt.esc(r.scope || "—"),
            `<span class="muted">${fmt.esc(JSON.stringify(r.thresholds || {}))}</span>`,
          ])
        );
      }
    );

    load(
      "alPending",
      () => api.get("/api/early-warning/rules/pending"),
      (rows, el) => {
        if (!rows.length)
          return void (el.innerHTML = ui.empty("Tüm kurallar çalıştırılabiliyor."));
        el.innerHTML =
          `<ul class="plain">` +
          rows
            .map(
              (r) =>
                `<li>${chip("neutral", "veri bekliyor")}<b>${fmt.esc(
                  r.rule_name || r.name
                )}</b><div class="note">${fmt.esc(
                  r.missing_data || r.reason || r.pdf_condition || ""
                )}</div></li>`
            )
            .join("") +
          `</ul>`;
      }
    );
  },
};

function refreshAlerts() {
  const year = document.getElementById("alYear").value;
  const severity = document.getElementById("alSeverity").value || undefined;

  load(
    "alSummary",
    () => api.get("/api/early-warning/summary", { academic_year: year }),
    (s, el) => {
      const bySev = s.by_severity || {};
      // by_scope program kodu -> uyarı sayısı biçiminde gelir; kaç farklı
      // birimin etkilendiğini buradan sayıyoruz.
      const affectedUnits = Object.keys(s.by_scope || {}).length;
      const worst = (s.most_at_risk || [])[0];

      el.className = "";
      el.innerHTML =
        `<div class="tiles">` +
        tileHtml([
          ["Toplam uyarı", fmt.int(s.total_alerts)],
          ["Kritik", fmt.int(bySev["kritik"] || 0), "acil müdahale", "down"],
          ["Orta", fmt.int(bySev["orta"] || 0)],
          ["Düşük", fmt.int(bySev["düşük"] || 0)],
          ["Etkilenen birim", fmt.int(affectedUnits)],
          [
            "En riskli birim",
            worst ? fmt.esc(worst.scope_code) : fmt.empty,
            worst ? `${worst.alert_count} uyarı` : "",
            "down",
          ],
        ]) +
        `</div>` +
        ((s.most_at_risk || []).length
          ? `<div class="card"><h3>En çok uyarı alan birimler</h3>` +
            table(
              ["Birim", "Uyarı sayısı"],
              s.most_at_risk.map((r) => [
                `<code>${fmt.esc(r.scope_code)}</code>`,
                fmt.int(r.alert_count),
              ])
            ) +
            `</div>`
          : "");
    }
  );

  load(
    "alList",
    () => api.get("/api/early-warning/alerts", { academic_year: year, severity }),
    (rows, el) => {
      if (!rows.length) return void (el.innerHTML = ui.empty("Bu filtrede uyarı yok."));
      const order = { kritik: 0, orta: 1, düşük: 2 };
      const sorted = [...rows].sort(
        (a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9)
      );
      el.innerHTML =
        `<ul class="plain alerts">` +
        sorted
          .map((a) => {
            const level =
              a.severity === "kritik" ? "critical" : a.severity === "orta" ? "warning" : "info";
            return `<li>
              ${chip(level, a.severity)}
              <b>${fmt.esc(a.rule_name)}</b>
              ${a.scope_name ? `<span class="push" style="font-size:.72rem">${fmt.esc(a.scope_name)}</span>` : ""}
              <div class="note">${fmt.esc(a.message || "")}</div>
              <div class="note muted">
                Ölçülen: <b>${fmt.dec(a.observed_value, 2)}</b> ·
                Eşik: <b>${fmt.dec(a.threshold_value, 2)}</b> ·
                Kaynak: ${fmt.esc(a.data_source || "—")}
              </div>
              ${a.recommended_action ? `<div class="note action">▸ ${fmt.esc(a.recommended_action)}</div>` : ""}
            </li>`;
          })
          .join("") +
        `</ul>`;
    }
  );
}
