// Planlama ekranları: Senaryo Analizi (Modül 9) ve Erken Uyarı (Modül 11).

/* ==================================================================
   Senaryo Analizi — Modül 9 (Habib)
   ================================================================== */

VIEWS["scenarios"] = {
  title: "Senaryo Analizi",
  subtitle: "What-if simülasyonu, risk değerlendirmesi ve öneriler · Modül 9",
  html: () => `
    <div class="grid cols-3-2">
      <div class="card">
        <h3>Yeni simülasyon</h3>
        <div class="note">
          Hesaplama sunucuda Decimal ile yapılır; sonuçlar veritabanına
          yazılmadan önizlenir.
        </div>

        <label class="f">Senaryo türü <select id="scType"></select></label>
        <div id="scInputs"></div>
        <div class="form-actions">
          <button class="primary" id="scPreview">Önizle</button>
          <button class="ghost" id="scReset">Temizle</button>
        </div>
      </div>

      <div class="card">
        <h3>Aktif temel senaryo (baseline)</h3>
        <div class="note">Simülasyonun karşılaştırma tabanı.</div>
        <div id="scBaseline"></div>
      </div>
    </div>

    <div class="card">
      <h3>Simülasyon sonucu</h3>
      <div id="scResult">${ui.empty("Henüz simülasyon çalıştırılmadı.")}</div>
    </div>

    <div class="card">
      <h3>Kayıtlı senaryolar</h3>
      <div id="scList"></div>
    </div>`,

  async init() {
    // Senaryo türleri ve girdi alanları OpenAPI şemasından değil, sunucunun
    // döndürdüğü senaryo listesinden türetiliyor.
    const sel = document.getElementById("scType");
    sel.innerHTML = SCENARIO_TYPES.map(
      (t) => `<option value="${t.value}">${fmt.esc(t.label)}</option>`
    ).join("");
    sel.addEventListener("change", renderScenarioInputs);
    renderScenarioInputs();

    document.getElementById("scPreview").addEventListener("click", runScenarioPreview);
    document.getElementById("scReset").addEventListener("click", () => {
      renderScenarioInputs();
      document.getElementById("scResult").innerHTML = ui.empty(
        "Henüz simülasyon çalıştırılmadı."
      );
    });

    load(
      "scBaseline",
      () => api.get("/api/scenarios/baselines/active"),
      (b, el) => {
        el.innerHTML = `
          <div class="kv">
            ${kv("Ad", fmt.esc(b.name))}
            ${kv("Akademik yıl", fmt.esc(b.academic_year))}
            ${kv("Öğrenci sayısı", fmt.int(b.student_count))}
            ${kv("Yıllık ücret", fmt.moneyM(b.annual_tuition_fee, 2))}
            ${kv("Burs oranı", fmt.pct(b.scholarship_rate_percent))}
            ${kv("Öğretim üyesi", fmt.int(b.academic_staff_count))}
            ${kv("Derslik kapasitesi", fmt.int(b.classroom_capacity))}
            ${kv("Laboratuvar kapasitesi", fmt.int(b.laboratory_capacity))}
          </div>
          <div class="note">${fmt.esc(b.description || "")}</div>`;
      }
    );

    load(
      "scList",
      () => api.get("/api/scenarios"),
      (rows, el) => {
        if (!rows.length) return void (el.innerHTML = ui.empty("Kayıtlı senaryo yok."));
        el.innerHTML = table(
          ["Senaryo", "Tür", "Durum", "Oluşturulma"],
          rows.map((r) => [
            `<b>${fmt.esc(r.name)}</b><br><span class="muted">${fmt.esc(r.description || "")}</span>`,
            fmt.esc(SCENARIO_LABEL[r.scenario_type] || r.scenario_type),
            chip(r.status === "completed" ? "good" : "info", r.status),
            fmt.esc((r.created_at || "").slice(0, 10)),
          ])
        );
      }
    );
  },
};

// Senaryo türleri ve her türün gerektirdiği girdiler.
// Backend'in kabul ettiği alan adları birebir kullanılıyor.
const SCENARIO_TYPES = [
  {
    value: "tuition-change",
    label: "Öğrenim ücreti değişikliği",
    fields: [["tuition_change_percent", "Ücret değişimi (%)", 10, -50, 100]],
  },
  {
    value: "scholarship-change",
    label: "Burs politikası değişikliği",
    fields: [["scholarship_change_percent", "Burs oranı değişimi (puan)", 5, -50, 50]],
  },
  {
    value: "student-count-change",
    label: "Öğrenci sayısı değişikliği",
    fields: [["student_count_change_percent", "Öğrenci sayısı değişimi (%)", 10, -50, 100]],
  },
  {
    value: "new-program",
    label: "Yeni program açma",
    fields: [
      ["new_program_student_count", "Yeni program öğrenci sayısı", 80, 1, 2000],
      ["new_program_staff_count", "Gerekli öğretim üyesi", 6, 0, 200],
    ],
  },
  {
    value: "program-closure",
    label: "Program kapatma",
    fields: [["closing_program_student_count", "Kapatılan programın öğrenci sayısı", 60, 1, 2000]],
  },
  {
    value: "staff-change",
    label: "Öğretim üyesi sayısı değişikliği",
    fields: [["staff_count_change", "Öğretim üyesi değişimi (kişi)", 10, -200, 200]],
  },
  {
    value: "capacity-change",
    label: "Fiziksel kapasite değişikliği",
    fields: [
      ["classroom_capacity_change", "Derslik kapasitesi değişimi", 200, -5000, 5000],
      ["laboratory_capacity_change", "Laboratuvar kapasitesi değişimi", 50, -5000, 5000],
    ],
  },
];

const SCENARIO_LABEL = Object.fromEntries(SCENARIO_TYPES.map((t) => [t.value, t.label]));

function renderScenarioInputs() {
  const type = document.getElementById("scType").value;
  const spec = SCENARIO_TYPES.find((t) => t.value === type);
  document.getElementById("scInputs").innerHTML = spec.fields
    .map(
      ([key, label, def, min, max]) =>
        `<label class="f">${fmt.esc(label)}
           <input type="number" data-key="${key}" value="${def}" min="${min}" max="${max}" step="1">
         </label>`
    )
    .join("");
}

async function runScenarioPreview() {
  const type = document.getElementById("scType").value;
  const inputs = {};
  document.querySelectorAll("#scInputs input").forEach((i) => {
    inputs[i.dataset.key] = Number(i.value);
  });

  await load(
    "scResult",
    () => api.post("/api/scenarios/preview", { scenario_type: type, inputs }),
    (r, el) => {
      const c = r.computation || r;
      const risks = r.risks || [];
      const level = r.risk_level || c.risk_level;
      const levelClass =
        level === "critical" ? "critical" : level === "high" ? "warning" : level === "medium" ? "info" : "good";

      el.innerHTML = `
        <div class="state ${level === "low" ? "empty" : "warn"}">
          ${chip(levelClass, "risk: " + level)} ${fmt.esc(r.recommendation || "")}
        </div>

        <h4>Hesaplanan etkiler</h4>
        <div class="kv">
          ${Object.entries(c)
            .filter(([k, v]) => typeof v !== "object" && v !== null && k !== "risk_level")
            .map(([k, v]) => kv(SCENARIO_FIELD_LABELS[k] || k, formatScenarioValue(k, v)))
            .join("")}
        </div>

        <h4>Tespit edilen riskler (${risks.length})</h4>
        ${
          risks.length
            ? `<ul class="plain">${risks
                .map(
                  (x) =>
                    `<li>${chip(
                      x.level === "critical" ? "critical" : x.level === "high" ? "warning" : "info",
                      x.level
                    )}${fmt.esc(x.message || x.description)}</li>`
                )
                .join("")}</ul>`
            : ui.empty("Bu senaryoda risk kuralı tetiklenmedi.")
        }

        <div class="note">
          Bu bir önizlemedir; veritabanına kayıt yazılmamıştır.
          Hesaplamalar Decimal ile yapılır, float yuvarlaması yoktur.
        </div>`;
    }
  );
}

const SCENARIO_FIELD_LABELS = {
  baseline_revenue: "Mevcut gelir",
  projected_revenue: "Projeksiyon gelir",
  revenue_change: "Gelir değişimi",
  revenue_change_percent: "Gelir değişimi (%)",
  baseline_cost: "Mevcut maliyet",
  projected_cost: "Projeksiyon maliyet",
  cost_change: "Maliyet değişimi",
  baseline_student_count: "Mevcut öğrenci sayısı",
  projected_student_count: "Projeksiyon öğrenci sayısı",
  baseline_staff_count: "Mevcut öğretim üyesi",
  projected_staff_count: "Projeksiyon öğretim üyesi",
  student_staff_ratio: "Öğrenci / öğretim üyesi oranı",
  classroom_utilization_percent: "Derslik kullanım oranı",
  laboratory_utilization_percent: "Laboratuvar kullanım oranı",
  net_balance: "Net denge",
};

function formatScenarioValue(key, value) {
  if (key.includes("percent") || key.includes("utilization")) return fmt.pct(value);
  if (key.includes("count")) return fmt.int(value);
  if (key.includes("ratio")) return fmt.dec(value, 2);
  if (key.includes("revenue") || key.includes("cost") || key.includes("balance"))
    return fmt.moneyM(value, 2);
  return fmt.dec(value, 2);
}

/* ==================================================================
   Erken Uyarı — Modül 11 (Begüm)
   ================================================================== */

VIEWS["alerts"] = {
  title: "Erken Uyarı Sistemi",
  subtitle: "Kural motoru tabanlı otomatik risk tespiti · Modül 11",
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
        <h3>Tanımlı kurallar</h3>
        <div class="note">
          Kurallar <code>app/config/early_warning_rules.json</code> dosyasından okunur.
        </div>
        <div id="alRules"></div>
      </div>
      <div class="card">
        <h3>Henüz çalıştırılamayan kurallar</h3>
        <div class="note">
          Bu kurallar tanımlı ancak gerekli veri girilmediği için değerlendirilemiyor.
          Sonuç üretiyormuş gibi göstermek yerine burada açıkça listeleniyor.
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
