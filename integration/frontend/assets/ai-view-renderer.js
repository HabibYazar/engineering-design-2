// Dinamik sonuç penceresi çizici.
//
// TASARIM İLKESİ
// --------------
// Bu dosya YALNIZCA backend'in ürettiği `ui_spec` nesnesini çizer. Modelin
// serbest metninden sayı ayıklamaz, hiçbir hesap yapmaz ve modelin gönderdiği
// hiçbir kodu çalıştırmaz.
//
// SAYININ KAYNAĞI
// ---------------
// Her sayısal bileşen `source_metric_ids` taşır: "<metrik>.<baseline|
// scenario|change>". Çizim sırasında bu adresler `structured_result` içinde
// çözülür ve bileşenin taşıdığı sayıyla karşılaştırılır. Uyuşmazlık varsa
// KAYNAK ESAS ALINIR ve konsola uyarı yazılır. Böylece ui_spec bozulsa bile
// ekrana yanlış sayı çıkamaz.
//
// GÜVENLİK
// --------
// 1. Bileşen kayıt defteri KAPALIDIR. Tanımlı olmayan bir `type` çizilmez.
// 2. Bütün metinler `fmt.esc()` ile kaçırılır; ham HTML basılmaz.
// 3. Tema yalnızca sabit belirteçlerden oluşur ve KAPSAMLI (scoped) CSS
//    değişkenlerine çevrilir: `.ai-generated-view[data-view-id="…"]`.
//    body, html, *, #sidebar gibi seçicilere stil yazılamaz.
// 4. Bir grafiğin hatası yalnızca o kartı etkiler; panel çalışmaya devam eder.

/** İzin verilen tema belirteçleri. Listede olmayan değer yok sayılır. */
const AI_THEME_TOKENS = {
  accent: {
    indigo: "#6366f1",
    teal: "#14b8a6",
    amber: "#f59e0b",
    slate: "#64748b",
    rose: "#f43f5e",
  },
  density: { compact: "10px", comfortable: "16px" },
  card_radius: { sharp: "4px", soft: "14px", round: "22px" },
  chart_emphasis: { low: "0.6", normal: "0.9", high: "1" },
  risk_emphasis: { low: "0.6", normal: "0.9", high: "1" },
};

// RENGİN ANLAMI SABİTTİR. Aynı renk iki grafikte farklı şey anlatamaz.
const AI_TONES = {
  baseline: "var(--ai-baseline)",   // mavi
  scenario: "var(--ai-scenario)",   // turuncu
  capacity: "var(--ai-capacity)",   // gri
  positive: "var(--ai-positive)",   // yeşil
  warning: "var(--ai-warning)",     // amber
  critical: "var(--ai-critical)",   // kırmızı
  info: "var(--ai-info)",           // indigo
};

const AI_TONE_OF_LEVEL = {
  critical: "critical",
  warning: "warning",
  info: "info",
  positive: "positive",
};

// Seviye adının METİN karşılığı. Renk tek başına anlam taşımamalı.
const AI_LEVEL_TEXT = {
  critical: "Kritik",
  warning: "Yüksek",
  info: "İzlenmeli",
  positive: "Uygun",
};

// Gelişmiş bir grafik çizilemezse hangi basit türe düşeceği.
const AI_FALLBACK_CHAIN = {
  dumbbell_chart: "horizontal_comparison_bar",
  slope_chart: "dumbbell_chart",
  bullet_chart: "grouped_bar_chart",
  radial_gauge: "progress_ring",
  semi_circle_gauge: "radial_gauge",
  gauge_group: "grouped_bar_chart",
  waterfall_chart: "grouped_bar_chart",
  forecast_line_chart: "line_chart",
  stacked_area_chart: "line_chart",
  heatmap: "grouped_bar_chart",
  risk_matrix: "risk_summary_card",
  treemap: "horizontal_comparison_bar",
  radar_chart: "grouped_bar_chart",
  horizontal_comparison_bar: "bar_chart",
  grouped_bar_chart: "bar_chart",
};

// Sabit ikon sözlüğü. Model ikon ÇİZEMEZ, yalnızca adını seçebilir.
const AI_ICONS = {
  students: "M12 3 2 8l10 5 10-5-10-5Zm0 9L4 8m8 4 8-4M6 11v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5",
  staff: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-8 8a8 8 0 0 1 16 0",
  money: "M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
  classroom: "M3 5h18v11H3zM3 20h18M8 16v4M16 16v4",
  laboratory: "M9 3v6l-5 9a2 2 0 0 0 1.7 3h12.6a2 2 0 0 0 1.7-3l-5-9V3M8 3h8M7 15h10",
  metric: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  warning: "M12 3 2 20h20L12 3Zm0 6v5m0 3v.5",
  comment: "M4 5h16v11H8l-4 4V5Z",
  program: "M4 4h16v16H4zM8 9h8M8 13h5",
  university: "M12 3 2 8h20L12 3ZM5 10v8M9 10v8M15 10v8M19 10v8M3 21h18",
  formula: "M5 5h14M9 5v14M15 5v14M5 19h14",
  assumption: "M12 3a7 7 0 0 0-4 12.7V18h8v-2.3A7 7 0 0 0 12 3ZM9 21h6",
  source: "M4 6h16M4 12h16M4 18h10",
  code: "m8 7-5 5 5 5m8-10 5 5-5 5",
  raw: "M6 3h9l5 5v13H6zM15 3v5h5",
  detail: "M4 6h16M4 12h16M4 18h16",
};

/**
 * Pencere kimliğini CSS'e girmeden önce beyaz listeden geçirir.
 *
 * Kaçırma (escaping) burada YETMEZ: `<style>` içeriği ham metin olarak
 * ayrıştırılır, dolayısıyla `"] * { … }` gibi bir kimlik seçiciyi kırıp
 * genel CSS üretebilirdi. Harf, rakam, tire ve alt çizgi dışındaki her
 * karakter atılır.
 */
function aiSafeId(viewId) {
  const cleaned = String(viewId || "").replace(/[^A-Za-z0-9_-]/g, "");
  return cleaned || "aiv-unknown";
}

/**
 * Tema belirteçlerinden KAPSAMLI CSS üretir.
 *
 * Seçici her zaman `[data-view-id]` ile sınırlıdır ve gövdesinde yalnızca
 * `--ai-` ile başlayan değişken tanımları bulunur; başka bir özellik
 * yazılamaz.
 */
function aiScopedStyle(viewId, theme = {}) {
  const pick = (group, value, fallback) =>
    AI_THEME_TOKENS[group][value] !== undefined
      ? AI_THEME_TOKENS[group][value]
      : AI_THEME_TOKENS[group][fallback];

  return (
    `.ai-generated-view[data-view-id="${aiSafeId(viewId)}"]{` +
    `--ai-accent:${pick("accent", theme.accent, "indigo")};` +
    `--ai-gap:${pick("density", theme.density, "comfortable")};` +
    `--ai-card-radius:${pick("card_radius", theme.card_radius, "soft")};` +
    `--ai-chart-opacity:${pick("chart_emphasis", theme.chart_emphasis, "normal")};` +
    `--ai-risk-opacity:${pick("risk_emphasis", theme.risk_emphasis, "normal")};` +
    `--ai-baseline:#3b82f6;` +
    `--ai-scenario:#f97316;` +
    `--ai-capacity:#94a3b8;` +
    `--ai-positive:#22c55e;` +
    `--ai-warning:#f59e0b;` +
    `--ai-critical:#ef4444;` +
    `--ai-info:#6366f1;` +
    `}`
  );
}

/* ================================================================== */
/* Sayının kaynağı — structured_result çözümlemesi                     */
/* ================================================================== */

/** structured_result'ı "anahtar.alan" ile sorgulanabilir hâle getirir. */
// Çizim boyunca geçerli kaynak dizini. İç içe bileşenler (accordion,
// gauge grubu) de aynı doğrulamadan geçsin diye burada tutulur.
let AI_CURRENT_SOURCE = null;

function aiSourceIndex(structured) {
  const index = {};
  const metrics = (structured && structured.metrics) || [];
  metrics.forEach((metric) => {
    if (!metric || !metric.key) return;
    ["baseline", "scenario", "change"].forEach((field) => {
      if (metric[field] !== null && metric[field] !== undefined) {
        index[metric.key + "." + field] = Number(metric[field]);
      }
    });
  });
  return index;
}

/**
 * Bir adresi çözer. "a|b" biçimindeki adres iki kaynağın farkıdır.
 * Kaynak bulunamazsa `undefined` döner — çağıran ui_spec değerini kullanır.
 */
function aiResolve(address, index, derivation) {
  if (!address || !index) return undefined;
  if (address.indexOf("|") !== -1) {
    const [left, right] = address.split("|");
    if (index[left] === undefined || index[right] === undefined) return undefined;
    return derivation === "sum" ? index[left] + index[right] : index[left] - index[right];
  }
  return index[address];
}

/**
 * Bileşenin sayılarını kaynağa göre DOĞRULAR ve gerekirse düzeltir.
 *
 * ui_spec ile structured_result çeliştiğinde kaynak kazanır: pencere
 * tanımı bir sunum katmanıdır, doğruluk otoritesi değildir.
 */
function aiVerifiedComponent(component, index) {
  if (!index) return component;
  const copy = JSON.parse(JSON.stringify(component));
  let corrections = 0;

  (copy.series || []).forEach((series) => {
    (series.values || []).forEach((value, i) => {
      const resolved = aiResolve(
        (series.source_metric_ids || [])[i], index, series.derivation
      );
      if (resolved === undefined) return;
      if (value === null || Math.abs(Number(value) - resolved) > 0.005) {
        series.values[i] = resolved;
        corrections++;
      }
    });
  });

  (copy.markers || []).forEach((marker) => {
    const resolved = aiResolve(marker.source_metric_id, index);
    if (resolved !== undefined && Math.abs(marker.value - resolved) > 0.005) {
      marker.value = resolved;
      corrections++;
    }
  });

  // `data` sözlüğü ADLA eşleşir, sırayla değil. Sıra tabanlı bir eşleşme
  // alan adları farklı olan bileşenlerde (kapasite / mevcut / senaryo)
  // sessizce yanlış kaynağa bağlanır ve doğru sayıyı "düzelterek" bozardı.
  const map = copy.data_source_ids || {};
  Object.keys(copy.data || {}).forEach((name) => {
    if (copy.data[name] === null || copy.data[name] === undefined) return;
    const resolved = aiResolve(map[name], index, "difference");
    if (resolved === undefined) return;
    if (Math.abs(Number(copy.data[name]) - resolved) > 0.005) {
      copy.data[name] = resolved;
      corrections++;
    }
  });

  if (corrections) {
    console.warn(
      "Pencere tanımındaki sayı structured_result ile uyuşmuyordu; " +
      "kaynak değer kullanıldı:", copy.id || copy.type, corrections
    );
  }
  return copy;
}

/* ================================================================== */
/* Biçimlendirme                                                       */
/* ================================================================== */

function aiNum(value, digits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (digits === undefined) digits = Number.isInteger(number) ? 0 : 2;
  return number.toLocaleString("tr-TR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function aiSigned(value, digits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return (number > 0 ? "+" : "") + aiNum(number, digits);
}

function aiIcon(name, extraClass = "") {
  const path = AI_ICONS[name];
  if (!path) return "";
  return (
    `<svg class="ai-icon ${extraClass}" viewBox="0 0 24 24" aria-hidden="true" ` +
    `fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" ` +
    `stroke-linejoin="round"><path d="${path}"/></svg>`
  );
}

function aiToneColor(tone) {
  return AI_TONES[tone] || AI_TONES.baseline;
}

/** Grafik kartı kabuğu: başlık, alt başlık, birim, gövde. */
function aiChartShell(c, body, extra = "") {
  const unit = c.unit
    ? `<span class="ai-chart-unit">${fmt.esc(c.unit)}</span>` : "";
  // `data-ai-type` FALLBACK SONRASI türü taşır: bir grafik başka türe
  // düştüğünde testler ve hata ayıklama bunu görebilsin.
  return `<figure class="ai-chart" data-ai-type="${fmt.esc(c.type)}">
    <figcaption class="ai-chart-head">
      <div>
        <h5 class="ai-chart-title">${fmt.esc(c.title || "")}</h5>
        ${c.subtitle ? `<p class="ai-chart-sub">${fmt.esc(c.subtitle)}</p>` : ""}
      </div>
      ${unit}
    </figcaption>
    <div class="ai-chart-body">${body}</div>
    ${extra}
    ${c.note ? `<p class="ai-chart-note">${aiIcon("warning")}${fmt.esc(c.note)}</p>` : ""}
  </figure>`;
}

/** Grafiğin metinsel karşılığı. Renk tek anlam taşıyıcısı olmamalı. */
function aiValueTable(rows) {
  if (!rows.length) return "";
  return `<dl class="ai-values">${rows
    .map(
      (r) =>
        `<div class="ai-value-row"><dt><span class="ai-swatch" style="background:${
          aiToneColor(r.tone)
        }"></span>${fmt.esc(r.label)}</dt><dd>${fmt.esc(r.value)}</dd></div>`
    )
    .join("")}</dl>`;
}

/* ================================================================== */
/* Bileşen kayıt defteri                                               */
/* ================================================================== */

const AI_COMPONENTS = {
  /* ---------------- özet ve kartlar ---------------- */

  decision_summary(c) {
    const badges = (c.badges || [])
      .map(
        (b) =>
          `<span class="ai-badge ai-badge-${fmt.esc(b.tone || "info")}">${fmt.esc(
            b.label
          )}</span>`
      )
      .join("");
    return `<section class="ai-decision" data-ai-type="decision_summary" aria-label="${fmt.esc(
      c.aria_label || "Karar özeti"
    )}">
      <p class="ai-decision-text">${fmt.esc(c.title || "")}</p>
      ${badges ? `<div class="ai-badges">${badges}</div>` : ""}
    </section>`;
  },

  kpi_card(c) {
    const sentiment = ["positive", "negative", "neutral"].includes(c.sentiment)
      ? c.sentiment : "neutral";
    const level = AI_LEVEL_TEXT[c.level] ? c.level : "";
    const arrow = c.trend === "up" ? "▲" : c.trend === "down" ? "▼" : "■";

    const previous = c.baseline_label
      ? `<div class="ai-kpi-prev"><span>Mevcut</span><b>${fmt.esc(
          c.baseline_label
        )}</b></div>`
      : "";
    const delta = c.delta_label
      ? `<div class="ai-kpi-delta ai-sent-${sentiment}">
           <span aria-hidden="true">${arrow}</span>${fmt.esc(c.delta_label)}
         </div>`
      : "";

    return `<article class="ai-kpi ${level ? "ai-kpi-" + level : ""}"
      data-ai-type="kpi_card"
      aria-label="${fmt.esc(c.aria_label || c.title || "Gösterge")}">
      <header class="ai-kpi-head">
        ${aiIcon(c.icon || "metric", "ai-kpi-icon")}
        <h5 class="ai-kpi-title">${fmt.esc(c.title || "")}</h5>
        ${level ? `<span class="ai-chip ai-chip-${level}">${AI_LEVEL_TEXT[level]}</span>` : ""}
      </header>
      <div class="ai-kpi-value">${fmt.esc(c.value || "—")}</div>
      <div class="ai-kpi-foot">${previous}${delta}</div>
      ${c.caption ? `<p class="ai-kpi-caption">${fmt.esc(c.caption)}</p>` : ""}
      ${aiScopeBadge(c)}
    </article>`;
  },

  metric_card(c) {
    return AI_COMPONENTS.kpi_card(c);
  },

  comparison_metric(c) {
    return AI_COMPONENTS.kpi_card(c);
  },

  risk_summary_card(c) {
    const level = AI_LEVEL_TEXT[c.level] ? c.level : "info";
    return `<article class="ai-risk-card ai-risk-${level}"
      data-ai-type="risk_summary_card" aria-label="${fmt.esc(c.aria_label || c.title || "Risk")}">
      <header class="ai-risk-head">
        ${aiIcon(c.icon || "warning", "ai-risk-icon")}
        <h5 class="ai-risk-title">${fmt.esc(c.title || "")}</h5>
        <span class="ai-chip ai-chip-${level}">${AI_LEVEL_TEXT[level]}</span>
      </header>
      ${c.subtitle ? `<p class="ai-risk-sub">${fmt.esc(c.subtitle)}</p>` : ""}
      <div class="ai-risk-value">${fmt.esc(c.value || "—")}</div>
      ${c.caption ? `<p class="ai-risk-caption">${fmt.esc(c.caption)}</p>` : ""}
    </article>`;
  },

  risk_card(c) {
    const level = AI_LEVEL_TEXT[c.level] ? c.level : "info";
    return `<article class="ai-risk-card ai-risk-${level}">
      <header class="ai-risk-head">
        ${aiIcon("warning", "ai-risk-icon")}
        <h5 class="ai-risk-title">${fmt.esc(c.title || "")}</h5>
        ${c.subtitle ? `<span class="ai-risk-sub">${fmt.esc(c.subtitle)}</span>` : ""}
      </header>
      <ul class="ai-list">${(c.items || [])
        .map((item) => `<li>${fmt.esc(item)}</li>`).join("")}</ul>
      ${c.note ? `<p class="ai-risk-caption">${fmt.esc(c.note)}</p>` : ""}
    </article>`;
  },

  information_box(c) {
    const level = AI_LEVEL_TEXT[c.level] ? c.level : "info";
    const items = (c.items || []).length
      ? `<ul class="ai-list ai-list-flag">${c.items
          .map((i) => `<li>${fmt.esc(i)}</li>`).join("")}</ul>`
      : "";
    return `<aside class="ai-info ai-info-${level}" data-ai-type="information_box"
      aria-label="${fmt.esc(c.aria_label || c.title || "Bilgi")}">
      <header class="ai-info-head">
        ${aiIcon(c.icon || "warning")}
        ${c.title ? `<h5 class="ai-info-title">${fmt.esc(c.title)}</h5>` : ""}
      </header>
      ${items}
      ${c.body ? `<div class="ai-info-body">${aiSafeText(c.body)}</div>` : ""}
      ${c.note ? `<p class="ai-info-note">${fmt.esc(c.note)}</p>` : ""}
    </aside>`;
  },

  decision_list(c) {
    return `<ol class="ai-decisions" data-ai-type="decision_list" aria-label="${fmt.esc(
      c.aria_label || "Karar önerileri"
    )}">${(c.items || [])
      .map(
        (item, i) =>
          `<li><span class="ai-decision-no">${i + 1}</span><span>${fmt.esc(
            item
          )}</span></li>`
      )
      .join("")}</ol>`;
  },

  recommendation_list(c) {
    return `<ul class="ai-list">${(c.items || [])
      .map((item) => `<li>${fmt.esc(item)}</li>`).join("")}</ul>`;
  },

  data_source_panel(c) {
    return `<div class="ai-sources">
      <div class="ai-panel-title">${fmt.esc(c.title || "Kullanılan veriler")}</div>
      <ul class="ai-list">${(c.items || [])
        .map((item) => `<li>${fmt.esc(item)}</li>`).join("")}</ul>
    </div>`;
  },

  assumptions_panel(c) {
    return `<div class="ai-assumptions">
      <div class="ai-panel-title">${fmt.esc(c.title || "Varsayımlar")}</div>
      <ul class="ai-list">${(c.items || [])
        .map((item) => `<li>${fmt.esc(item)}</li>`).join("")}</ul>
    </div>`;
  },

  scope_badge(c) {
    return aiScopeBadge(c);
  },

  legend_panel(c) {
    const items = (c.legend || [])
      .map(
        (entry) =>
          `<span class="ai-legend-item"><span class="ai-swatch" style="background:${
            aiToneColor(entry.role)
          }"></span>${fmt.esc(entry.label)}</span>`
      )
      .join("");
    if (!items) return "";
    return `<div class="ai-legend" data-ai-type="legend_panel" role="note"
      aria-label="Renk açıklaması">${items}</div>`;
  },

  expandable_details(c) {
    // <details>/<summary> klavyeyle açılıp kapanır; ayrıca bir tuş
    // dinleyicisi yazmak yerine tarayıcının kendi davranışı kullanılıyor.
    const inner =
      (c.components || []).map((child) => aiRenderComponent(child)).join("") +
      (c.body ? `<div class="ai-info-body">${aiSafeText(c.body)}</div>` : "") +
      (c.markdown ? `<pre class="ai-markdown">${fmt.esc(c.markdown)}</pre>` : "");
    return `<details class="ai-accordion" data-ai-type="expandable_details"${
      c.open ? " open" : ""}>
      <summary>${aiIcon(c.icon || "detail")}<span>${fmt.esc(
        c.title || "Ayrıntılar"
      )}</span><span class="ai-acc-caret" aria-hidden="true">›</span></summary>
      <div class="ai-acc-body">${inner}</div>
    </details>`;
  },

  /* ---------------- grafikler ---------------- */

  dumbbell_chart(c) {
    const baseline = aiSeriesValue(c, "baseline", 0);
    const scenario = aiSeriesValue(c, "scenario", 0);
    if (!Number.isFinite(baseline) || !Number.isFinite(scenario)) {
      throw new Error("dumbbell için iki uç değer gerekli");
    }
    const min = Math.min(baseline, scenario);
    const max = Math.max(baseline, scenario);
    const pad = (max - min) * 0.35 || Math.abs(max) * 0.15 || 1;
    const lo = Math.min(min - pad, min * 0.9);
    const hi = max + pad;
    const x = (v) => 60 + ((v - lo) / (hi - lo || 1)) * 480;

    const delta = scenario - baseline;
    const svg = `<svg viewBox="0 0 600 150" class="ai-svg" role="img"
      aria-label="${fmt.esc(c.aria_label || c.title || "")}">
      <line x1="60" y1="120" x2="540" y2="120" class="ai-axis"/>
      <line class="ai-dumbbell-link ai-anim-line" x1="${x(baseline)}" y1="70"
            x2="${x(scenario)}" y2="70"/>
      <circle class="ai-dot ai-anim-pop" cx="${x(baseline)}" cy="70" r="13"
              fill="${AI_TONES.baseline}"><title>Mevcut: ${fmt.esc(
                aiNum(baseline)
              )}</title></circle>
      <circle class="ai-dot ai-anim-pop" cx="${x(scenario)}" cy="70" r="15"
              fill="${AI_TONES.scenario}"><title>Senaryo: ${fmt.esc(
                aiNum(scenario)
              )}</title></circle>
      <text class="ai-label" x="${x(baseline)}" y="44" text-anchor="middle">${fmt.esc(
        aiNum(baseline)
      )}</text>
      <text class="ai-label ai-label-strong" x="${x(scenario)}" y="44"
            text-anchor="middle">${fmt.esc(aiNum(scenario))}</text>
      <text class="ai-delta-tag" x="${(x(baseline) + x(scenario)) / 2}" y="102"
            text-anchor="middle">${fmt.esc(aiSigned(delta))}</text>
    </svg>`;

    return aiChartShell(c, svg, aiValueTable([
      // Etiketler LEGEND'DEN FARKLI: bu bir veri tablosu, ikinci bir
      // renk açıklaması değil.
      { label: "Mevcut", value: aiNum(baseline) + " " + (c.unit || ""), tone: "baseline" },
      { label: "Senaryo", value: aiNum(scenario) + " " + (c.unit || ""), tone: "scenario" },
      { label: "Değişim", value: aiSigned(delta) + " " + (c.unit || ""), tone: "info" },
    ]));
  },

  slope_chart(c) {
    const baseline = aiSeriesValue(c, "baseline", 0);
    const scenario = aiSeriesValue(c, "scenario", 0);
    if (!Number.isFinite(baseline) || !Number.isFinite(scenario)) {
      throw new Error("slope için iki uç değer gerekli");
    }
    const max = Math.max(baseline, scenario) * 1.15 || 1;
    const y = (v) => 130 - (v / max) * 100;
    const svg = `<svg viewBox="0 0 600 160" class="ai-svg" role="img"
      aria-label="${fmt.esc(c.aria_label || c.title || "")}">
      <line class="ai-slope ai-anim-line" x1="140" y1="${y(baseline)}" x2="460"
            y2="${y(scenario)}"/>
      <circle cx="140" cy="${y(baseline)}" r="8" fill="${AI_TONES.baseline}"/>
      <circle cx="460" cy="${y(scenario)}" r="8" fill="${AI_TONES.scenario}"/>
      <text class="ai-label" x="140" y="${y(baseline) - 16}" text-anchor="middle">${
        fmt.esc(aiNum(baseline))}</text>
      <text class="ai-label ai-label-strong" x="460" y="${y(scenario) - 16}"
            text-anchor="middle">${fmt.esc(aiNum(scenario))}</text>
      <text class="ai-axis-label" x="140" y="152" text-anchor="middle">Mevcut</text>
      <text class="ai-axis-label" x="460" y="152" text-anchor="middle">Senaryo</text>
    </svg>`;
    return aiChartShell(c, svg);
  },

  bullet_chart(c) {
    const capacity = aiSeriesValue(c, "capacity", 0);
    const baseline = aiSeriesValue(c, "baseline", 0);
    const scenario = aiSeriesValue(c, "scenario", 0);
    if (![capacity, baseline, scenario].every(Number.isFinite)) {
      throw new Error("bullet için kapasite, mevcut ve senaryo gerekli");
    }
    const max = Math.max(capacity, baseline, scenario) * 1.2 || 1;
    const w = (v) => (v / max) * 520;

    const markers = (c.markers || [])
      .map(
        (m) =>
          `<line class="ai-marker" x1="${w(m.value)}" y1="12" x2="${w(m.value)}"
                 y2="78"><title>${fmt.esc(m.label)}: ${fmt.esc(
                   aiNum(m.value)
                 )}</title></line>`
      )
      .join("");

    const svg = `<svg viewBox="0 0 560 110" class="ai-svg" role="img"
      aria-label="${fmt.esc(c.aria_label || c.title || "")}">
      <rect class="ai-bullet-track ai-anim-grow-x" x="0" y="22" rx="8" height="46"
            width="${w(capacity)}"><title>Kullanılabilir kapasite: ${fmt.esc(
              aiNum(capacity))}</title></rect>
      <rect class="ai-bullet-measure ai-anim-grow-x" x="0" y="32" rx="6" height="12"
            width="${w(baseline)}" fill="${AI_TONES.baseline}">
            <title>Mevcut ihtiyaç: ${fmt.esc(aiNum(baseline))}</title></rect>
      <rect class="ai-bullet-measure ai-anim-grow-x" x="0" y="50" rx="6" height="12"
            width="${w(scenario)}" fill="${AI_TONES.scenario}">
            <title>Senaryo ihtiyacı: ${fmt.esc(aiNum(scenario))}</title></rect>
      ${markers}
      <text class="ai-label" x="${w(baseline) + 8}" y="42">${fmt.esc(aiNum(baseline))}</text>
      <text class="ai-label ai-label-strong" x="${w(scenario) + 8}" y="60">${
        fmt.esc(aiNum(scenario))}</text>
      <text class="ai-axis-label" x="0" y="98">0</text>
      <text class="ai-axis-label" x="530" y="98" text-anchor="end">${fmt.esc(
        aiNum(max, 0))}</text>
    </svg>`;

    return aiChartShell(c, svg, aiValueTable([
      { label: "Kullanılabilir kapasite", value: aiNum(capacity) + " " + (c.unit || ""), tone: "capacity" },
      { label: "Mevcut ihtiyaç", value: aiNum(baseline) + " " + (c.unit || ""), tone: "baseline" },
      { label: "Senaryo ihtiyacı", value: aiNum(scenario) + " " + (c.unit || ""), tone: "scenario" },
    ]));
  },

  radial_gauge(c) {
    const scenario = Number(
      c.data && c.data.scenario !== undefined ? c.data.scenario : c.percent
    );
    const baseline = Number(c.data ? c.data.baseline : NaN);
    if (!Number.isFinite(scenario)) throw new Error("gauge için yüzde gerekli");

    const pct = Math.max(0, Math.min(100, scenario));
    const R = 46;
    const C = 2 * Math.PI * R;
    const tone = aiToneColor(c.tone || "info");
    const delta = Number.isFinite(baseline) ? scenario - baseline : NaN;

    const svg = `<svg viewBox="0 0 120 120" class="ai-gauge-svg" role="img"
      aria-label="${fmt.esc(c.aria_label || c.title || "")}">
      <circle class="ai-gauge-bg" cx="60" cy="60" r="${R}"/>
      ${Number.isFinite(baseline) ? `<circle class="ai-gauge-baseline" cx="60" cy="60"
        r="${R}" stroke-dasharray="${(baseline / 100) * C} ${C}"
        transform="rotate(-90 60 60)"><title>Mevcut: %${fmt.esc(
          aiNum(baseline))}</title></circle>` : ""}
      <circle class="ai-gauge-value ai-anim-dash" cx="60" cy="60" r="${R}"
        stroke="${tone}" stroke-dasharray="${(pct / 100) * C} ${C}"
        transform="rotate(-90 60 60)"><title>Senaryo: %${fmt.esc(
          aiNum(scenario))}</title></circle>
      <text class="ai-gauge-main" x="60" y="62" text-anchor="middle">%${fmt.esc(
        aiNum(scenario))}</text>
      <text class="ai-gauge-sub" x="60" y="80" text-anchor="middle">senaryo</text>
    </svg>`;

    return `<div class="ai-gauge-cell" data-ai-type="radial_gauge">
      ${svg}
      <div class="ai-gauge-caption">
        <b>${fmt.esc(c.title || "")}</b>
        ${Number.isFinite(baseline)
          ? `<span>Mevcut: %${fmt.esc(aiNum(baseline))}</span>` : ""}
        ${Number.isFinite(delta)
          ? `<span class="ai-sent-${delta < 0 ? "negative" : "positive"}">${
              delta < 0 ? "▼" : "▲"} ${fmt.esc(aiNum(Math.abs(delta), 2))} puan</span>`
          : ""}
      </div>
    </div>`;
  },

  semi_circle_gauge(c) {
    const value = Number(
      c.data && c.data.scenario !== undefined ? c.data.scenario : c.percent
    );
    if (!Number.isFinite(value)) throw new Error("gauge için yüzde gerekli");
    const pct = Math.max(0, Math.min(100, value));
    const L = Math.PI * 50;
    return `<div class="ai-gauge-cell">
      <svg viewBox="0 0 120 70" class="ai-gauge-svg" role="img"
        aria-label="${fmt.esc(c.aria_label || c.title || "")}">
        <path class="ai-gauge-bg" d="M10 60 A50 50 0 0 1 110 60" fill="none"/>
        <path class="ai-gauge-value ai-anim-dash" d="M10 60 A50 50 0 0 1 110 60"
          fill="none" stroke="${aiToneColor(c.tone || "info")}"
          stroke-dasharray="${(pct / 100) * L} ${L}"/>
        <text class="ai-gauge-main" x="60" y="56" text-anchor="middle">%${fmt.esc(
          aiNum(value))}</text>
      </svg>
      <div class="ai-gauge-caption"><b>${fmt.esc(c.title || "")}</b></div>
    </div>`;
  },

  progress_ring(c) {
    const value = Number(
      c.data && c.data.scenario !== undefined ? c.data.scenario : c.percent
    );
    const pct = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
    return `<div class="ai-gauge-cell">
      <div class="ai-ring" role="img" aria-label="${fmt.esc(
        c.aria_label || c.title || "")}">
        <div class="ai-ring-track"><div class="ai-ring-fill" style="width:${pct}%"></div></div>
        <b>%${fmt.esc(aiNum(pct))}</b>
      </div>
      <div class="ai-gauge-caption"><b>${fmt.esc(c.title || "")}</b></div>
    </div>`;
  },

  gauge(c) {
    return AI_COMPONENTS.progress_ring(c);
  },

  gauge_group(c) {
    const children = (c.components || []).map((child) => aiRenderComponent(child)).join("");
    if (!children) throw new Error("gauge grubu boş");
    return aiChartShell(c, `<div class="ai-gauge-grid">${children}</div>`);
  },

  waterfall_chart(c) {
    const series = (c.series || [])[0];
    if (!series || !series.values || series.values.length < 2) {
      throw new Error("şelale için en az iki kalem gerekli");
    }
    const values = series.values.map(Number);
    const kinds = series.kinds || [];
    const categories = c.categories || [];

    // Kümülatif taban: "total" türü sıfırdan başlar.
    let running = 0;
    const bars = values.map((value, i) => {
      const kind = kinds[i] || (i === values.length - 1 ? "total" : "increase");
      const start = kind === "total" ? 0 : running;
      const end = kind === "total" ? value : running + value;
      if (kind !== "total") running = end;
      return { value, kind, start, end, label: categories[i] || "" };
    });

    const all = bars.flatMap((b) => [b.start, b.end]).concat(0);
    const max = Math.max(...all);
    const min = Math.min(...all);
    const span = max - min || 1;
    const y = (v) => 20 + (1 - (v - min) / span) * 110;
    const bw = 78;
    const step = 150;

    const rects = bars
      .map((b, i) => {
        const x = 40 + i * step;
        const top = Math.min(y(b.start), y(b.end));
        const height = Math.max(3, Math.abs(y(b.end) - y(b.start)));
        const tone =
          b.kind === "total" ? "info" : b.value >= 0 ? "positive" : "critical";
        return `<g class="ai-wf-bar">
          <rect class="ai-anim-grow" x="${x}" y="${top}" width="${bw}" height="${height}"
                rx="6" fill="${aiToneColor(tone)}"><title>${fmt.esc(b.label)}: ${
                  fmt.esc(aiSigned(b.value, 0))}</title></rect>
          <text class="ai-label" x="${x + bw / 2}" y="${top - 8}"
                text-anchor="middle">${fmt.esc(aiSigned(b.value, 0))}</text>
          <text class="ai-axis-label" x="${x + bw / 2}" y="152"
                text-anchor="middle">${fmt.esc(b.label)}</text>
        </g>`;
      })
      .join("");

    const connectors = bars
      .slice(0, -1)
      .map((b, i) =>
        bars[i + 1].kind === "total"
          ? ""
          : `<line class="ai-wf-link" x1="${40 + i * step + bw}" y1="${y(b.end)}"
               x2="${40 + (i + 1) * step}" y2="${y(b.end)}"/>`
      )
      .join("");

    const svg = `<svg viewBox="0 0 ${40 + bars.length * step} 165" class="ai-svg"
      role="img" aria-label="${fmt.esc(c.aria_label || c.title || "")}">
      <line class="ai-axis" x1="20" y1="${y(0)}" x2="${20 + bars.length * step}"
            y2="${y(0)}"/>
      ${connectors}${rects}
    </svg>`;

    return aiChartShell(c, svg, aiValueTable(
      bars.map((b) => ({
        label: b.label,
        value: aiSigned(b.value, 0) + " " + (c.unit || ""),
        tone: b.kind === "total" ? "info" : b.value >= 0 ? "positive" : "critical",
      }))
    ));
  },

  line_chart(c) {
    return aiLineChart(c, { area: false, forecast: false });
  },

  stacked_area_chart(c) {
    return aiLineChart(c, { area: true, forecast: false });
  },

  forecast_line_chart(c) {
    return aiLineChart(c, { area: false, forecast: true });
  },

  bar_chart(c) {
    return aiGroupedBars(c);
  },

  grouped_bar_chart(c) {
    return aiGroupedBars(c);
  },

  horizontal_comparison_bar(c) {
    const categories = c.categories && c.categories.length
      ? c.categories : [c.title || ""];
    const series = (c.series || []).filter((s) => s.values && s.values.length);
    if (!series.length) throw new Error("karşılaştırma çubuğu için seri gerekli");
    const max =
      Math.max(...series.flatMap((s) => s.values.map(Number)).filter(Number.isFinite)) || 1;

    const rows = categories
      .map((category, i) => {
        const bars = series
          .map((s) => {
            const value = Number(s.values[i]);
            if (!Number.isFinite(value)) return "";
            return `<div class="ai-hbar-row">
              <span class="ai-hbar-name">${fmt.esc(s.label)}</span>
              <span class="ai-hbar-track">
                <span class="ai-hbar-fill ai-anim-grow-x" style="width:${
                  (value / max) * 100}%;background:${aiToneColor(s.role)}"
                  title="${fmt.esc(s.label)}: ${fmt.esc(aiNum(value))}"></span>
              </span>
              <b class="ai-hbar-value">${fmt.esc(aiNum(value))}</b>
            </div>`;
          })
          .join("");
        return `<div class="ai-hbar-group">
          <div class="ai-hbar-cat">${fmt.esc(category)}</div>${bars}
        </div>`;
      })
      .join("");

    return aiChartShell(c, `<div class="ai-hbars">${rows}</div>`);
  },

  heatmap(c) {
    const cells = c.cells || [];
    if (!cells.length) throw new Error("ısı haritası için hücre gerekli");
    const values = cells.map((x) => Number(x.value)).filter(Number.isFinite);
    const max = Math.max(...values) || 1;
    const min = Math.min(...values);
    const body = cells
      .map((cell) => {
        const value = Number(cell.value);
        const ratio = (value - min) / (max - min || 1);
        return `<div class="ai-heat-cell" style="--ai-heat:${ratio.toFixed(3)}"
          title="${fmt.esc(cell.label)}: ${fmt.esc(aiNum(value))}">
          <span>${fmt.esc(cell.label)}</span><b>${fmt.esc(aiNum(value))}</b>
        </div>`;
      })
      .join("");
    return aiChartShell(c, `<div class="ai-heatmap">${body}</div>`);
  },

  risk_matrix(c) {
    const cells = c.cells || [];
    if (!cells.length) throw new Error("risk matrisi için hücre gerekli");
    const dots = cells
      .map((cell) => {
        const p = Math.max(0, Math.min(100, Number(cell.probability)));
        const impact = Math.max(0, Math.min(100, Number(cell.impact)));
        const tone = impact > 66 && p > 66 ? "critical" : impact > 33 ? "warning" : "info";
        return `<circle cx="${40 + (p / 100) * 200}" cy="${180 - (impact / 100) * 150}"
          r="9" fill="${aiToneColor(tone)}" class="ai-anim-pop">
          <title>${fmt.esc(cell.label)} — olasılık ${fmt.esc(aiNum(p))},
          etki ${fmt.esc(aiNum(impact))}</title></circle>`;
      })
      .join("");
    const svg = `<svg viewBox="0 0 280 210" class="ai-svg" role="img"
      aria-label="${fmt.esc(c.aria_label || "Risk matrisi")}">
      <rect class="ai-matrix-bg" x="40" y="30" width="200" height="150" rx="8"/>
      <line class="ai-axis" x1="40" y1="180" x2="240" y2="180"/>
      <line class="ai-axis" x1="40" y1="30" x2="40" y2="180"/>
      ${dots}
      <text class="ai-axis-label" x="140" y="202" text-anchor="middle">Olasılık</text>
      <text class="ai-axis-label" x="14" y="105" text-anchor="middle"
            transform="rotate(-90 14 105)">Etki</text>
    </svg>`;
    return aiChartShell(c, svg, aiValueTable(
      cells.map((cell) => ({
        label: cell.label,
        value: `olasılık ${aiNum(cell.probability)} · etki ${aiNum(cell.impact)}`,
        tone: "warning",
      }))
    ));
  },

  treemap(c) {
    const cells = (c.cells || []).filter((x) => Number.isFinite(Number(x.value)));
    if (!cells.length) throw new Error("treemap için hücre gerekli");
    const total = cells.reduce((sum, x) => sum + Math.abs(Number(x.value)), 0) || 1;
    const body = cells
      .map((cell, i) => {
        const share = (Math.abs(Number(cell.value)) / total) * 100;
        const tone = ["baseline", "info", "capacity", "scenario"][i % 4];
        return `<div class="ai-tree-cell" style="flex-basis:${share.toFixed(2)}%;
          background:${aiToneColor(tone)}"
          title="${fmt.esc(cell.label)}: ${fmt.esc(aiNum(cell.value))}">
          <span>${fmt.esc(cell.label)}</span>
          <b>${fmt.esc(aiNum(cell.value))}</b>
        </div>`;
      })
      .join("");
    return aiChartShell(c, `<div class="ai-treemap">${body}</div>`);
  },

  radar_chart(c) {
    const categories = c.categories || [];
    const series = (c.series || [])[0];
    if (!series || categories.length < 3) throw new Error("radar için en az 3 eksen gerekli");
    const values = series.values.map(Number);
    const max = Math.max(...values.filter(Number.isFinite)) || 1;
    const cx = 130, cy = 125, R = 90;
    const point = (i, ratio) => {
      const angle = (Math.PI * 2 * i) / categories.length - Math.PI / 2;
      return [cx + Math.cos(angle) * R * ratio, cy + Math.sin(angle) * R * ratio];
    };
    const grid = [0.25, 0.5, 0.75, 1]
      .map(
        (r) =>
          `<polygon class="ai-radar-grid" points="${categories
            .map((_, i) => point(i, r).map((n) => n.toFixed(1)).join(","))
            .join(" ")}"/>`
      )
      .join("");
    const shape = categories
      .map((_, i) => point(i, (values[i] || 0) / max).map((n) => n.toFixed(1)).join(","))
      .join(" ");
    const labels = categories
      .map((label, i) => {
        const [x, y] = point(i, 1.16);
        return `<text class="ai-axis-label" x="${x.toFixed(1)}" y="${y.toFixed(1)}"
          text-anchor="middle">${fmt.esc(label)}</text>`;
      })
      .join("");
    const svg = `<svg viewBox="0 0 260 250" class="ai-svg" role="img"
      aria-label="${fmt.esc(c.aria_label || c.title || "")}">
      ${grid}
      <polygon class="ai-radar-shape ai-anim-pop" points="${shape}"
        fill="${aiToneColor(series.role)}"/>
      ${labels}
    </svg>`;
    return aiChartShell(c, svg);
  },

  sparkline(c) {
    const series = (c.series || [])[0];
    const values = ((series && series.values) || []).map(Number).filter(Number.isFinite);
    if (values.length < 2) throw new Error("sparkline için en az iki nokta gerekli");
    const max = Math.max(...values), min = Math.min(...values);
    const points = values
      .map((v, i) => `${(i / (values.length - 1)) * 100},${
        24 - ((v - min) / (max - min || 1)) * 20}`)
      .join(" ");
    return `<svg viewBox="0 0 100 26" class="ai-sparkline" role="img"
      aria-label="${fmt.esc(c.aria_label || "Eğilim")}" preserveAspectRatio="none">
      <polyline points="${points}" fill="none" stroke="${aiToneColor(
        (series && series.role) || "baseline")}" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
  },
};

/* ------------------------------------------------------------------ */
/* Paylaşılan çizim yardımcıları                                       */
/* ------------------------------------------------------------------ */

/** Belirli role sahip serinin i. değerini döndürür. */
function aiSeriesValue(component, role, i) {
  const series = (component.series || []).find((s) => s.role === role);
  if (series && series.values && series.values[i] !== undefined) {
    return Number(series.values[i]);
  }
  const data = component.data || {};
  return Number(data[role]);
}

function aiLineChart(c, { area, forecast }) {
  const categories = c.categories || [];
  const series = (c.series || []).filter((s) => (s.values || []).length);
  if (!series.length || categories.length < 2) {
    throw new Error("çizgi grafiği için en az iki nokta gerekli");
  }
  const all = series.flatMap((s) => s.values.map(Number)).filter(Number.isFinite);
  const max = Math.max(...all) * 1.1 || 1;
  const W = 560, H = 190;
  const x = (i) => 40 + (i / Math.max(categories.length - 1, 1)) * (W - 70);
  const y = (v) => H - 40 - (v / max) * (H - 70);

  const paths = series
    .map((s) => {
      const points = s.values
        .map((v, i) => (Number.isFinite(Number(v)) ? `${x(i)},${y(Number(v))}` : null))
        .filter(Boolean);
      if (!points.length) return "";
      const color = aiToneColor(s.role);
      const band =
        forecast && (s.lower || []).length
          ? `<polygon class="ai-band" fill="${color}" points="${s.upper
              .map((v, i) => `${x(i)},${y(Number(v))}`)
              .join(" ")} ${s.lower
              .slice()
              .reverse()
              .map((v, i) => `${x(s.lower.length - 1 - i)},${y(Number(v))}`)
              .join(" ")}"/>`
          : "";
      const fill = area
        ? `<polygon class="ai-area" fill="${color}" points="${points.join(" ")} ${x(
            points.length - 1
          )},${y(0)} ${x(0)},${y(0)}"/>`
        : "";
      const dots = s.values
        .map((v, i) =>
          Number.isFinite(Number(v))
            ? `<circle cx="${x(i)}" cy="${y(Number(v))}" r="4" fill="${color}">
                 <title>${fmt.esc(s.label)} — ${fmt.esc(
                   categories[i] || "")}: ${fmt.esc(aiNum(v))}</title></circle>`
            : ""
        )
        .join("");
      return `${band}${fill}<polyline class="ai-line ai-anim-line" fill="none"
        stroke="${color}" ${s.dashed ? 'stroke-dasharray="7 5"' : ""}
        points="${points.join(" ")}"/>${dots}`;
    })
    .join("");

  const axis = categories
    .map(
      (label, i) =>
        `<text class="ai-axis-label" x="${x(i)}" y="${H - 16}" text-anchor="middle">${
          fmt.esc(label)}</text>`
    )
    .join("");

  const svg = `<svg viewBox="0 0 ${W} ${H}" class="ai-svg" role="img"
    aria-label="${fmt.esc(c.aria_label || c.title || "")}">
    <line class="ai-axis" x1="40" y1="${y(0)}" x2="${W - 20}" y2="${y(0)}"/>
    ${paths}${axis}
  </svg>`;
  return aiChartShell(c, svg);
}

function aiGroupedBars(c) {
  const categories = c.categories && c.categories.length ? c.categories : [""];
  const series = (c.series || []).filter((s) => (s.values || []).length);
  if (!series.length) throw new Error("çubuk grafiği için seri gerekli");
  const all = series.flatMap((s) => s.values.map(Number)).filter(Number.isFinite);
  const max = Math.max(...all.map(Math.abs)) || 1;

  const groups = categories
    .map((category, i) => {
      const bars = series
        .map((s) => {
          const value = Number(s.values[i]);
          if (!Number.isFinite(value)) return "";
          return `<div class="ai-bar-wrap" title="${fmt.esc(s.label)}: ${fmt.esc(
            aiNum(value))}">
            <span class="ai-bar-value">${fmt.esc(aiNum(value))}</span>
            <span class="ai-bar ai-anim-grow" style="height:${Math.max(
              3, (Math.abs(value) / max) * 100)}%;background:${aiToneColor(s.role)}"></span>
            <span class="ai-bar-name">${fmt.esc(s.label)}</span>
          </div>`;
        })
        .join("");
      return `<div class="ai-bar-group"><div class="ai-bars">${bars}</div>
        <div class="ai-bar-label">${fmt.esc(category)}</div></div>`;
    })
    .join("");

  return aiChartShell(c, `<div class="ai-bar-chart">${groups}</div>`);
}

function aiScopeBadge(c) {
  if (!c.scope_name) return "";
  const labels = {
    program: "Program",
    department: "Bölüm",
    faculty: "Fakülte",
    university: "Üniversite",
  };
  const label = labels[c.scope_type] || "Kapsam";
  return `<span class="ai-scope-badge">${fmt.esc(label)}: ${fmt.esc(
    c.scope_name)}</span>`;
}

/**
 * Metni güvenli biçimde çizer.
 * ÖNCE kaçırır, SONRA sınırlı biçimlendirme uygular — tersi yapılsaydı
 * gelen bir <script> sayfaya girerdi. Desteklenen tek biçimler: başlık,
 * madde listesi ve paragraf.
 */
function aiSafeText(raw) {
  const escaped = fmt.esc(String(raw || ""));

  const renderLines = (lines) => {
    let html = "";
    let list = [];
    const flush = () => {
      if (!list.length) return;
      html += "<ul>" + list.map((l) => `<li>${l}</li>`).join("") + "</ul>";
      list = [];
    };
    lines.forEach((line) => {
      const text = line.trim();
      if (!text) return;
      const heading = text.match(/^(#{1,6})\s+(.*)$/);
      if (heading) {
        flush();
        html += `<div class="ai-sub-head">${heading[2]}</div>`;
        return;
      }
      const item = text.match(/^[-*•]\s+(.*)$/);
      if (item) {
        list.push(item[1]);
        return;
      }
      flush();
      html += `<p>${text}</p>`;
    });
    flush();
    return html;
  };

  return escaped
    .split(/\n{2,}/)
    .map((block) => renderLines(block.split("\n")))
    .join("");
}

/* ------------------------------------------------------------------ */
/* Bileşen çizimi — hata yalıtımı ve fallback                          */
/* ------------------------------------------------------------------ */

/**
 * Bir bileşeni çizer.
 *
 * * Tanımlı olmayan tür SESSİZCE ATLANIR.
 * * Çizim sırasında hata olursa `fallback` zinciri denenir.
 * * Zincir de tükenirse yalnızca O KART hata kutusuna dönüşür; panelin
 *   geri kalanı çalışmaya devam eder.
 */
function aiRenderComponent(component, sourceIndex, depth = 0) {
  if (!component || typeof component !== "object") return "";
  if (sourceIndex === undefined) sourceIndex = AI_CURRENT_SOURCE;
  const renderer = AI_COMPONENTS[component.type];
  if (!renderer) {
    console.warn("Bilinmeyen bileşen türü atlandı:", component.type);
    return "";
  }

  const prepared = sourceIndex ? aiVerifiedComponent(component, sourceIndex) : component;
  try {
    return renderer(prepared);
  } catch (error) {
    const next = component.fallback || AI_FALLBACK_CHAIN[component.type];
    if (next && depth < 4) {
      console.warn(
        `"${component.type}" çizilemedi (${error.message}); "${next}" deneniyor.`
      );
      return aiRenderComponent(
        Object.assign({}, component, { type: next, fallback: null }),
        sourceIndex,
        depth + 1
      );
    }
    console.warn("Bileşen çizilemedi:", component.type, error.message);
    return `<div class="ai-chart ai-chart-failed" data-ai-type="failed" role="note">
      <h5 class="ai-chart-title">${fmt.esc(component.title || "Grafik")}</h5>
      <p class="ai-chart-sub">Bu grafik çizilemedi. Diğer bölümler etkilenmedi.</p>
    </div>`;
  }
}

/* ------------------------------------------------------------------ */
/* Pencere                                                             */
/* ------------------------------------------------------------------ */

const AI_SECTION_CLASS = {
  decision_summary: "ai-section-decision",
  metric_grid: "ai-section-metrics",
  chart_grid: "ai-section-charts",
  risk_summary: "ai-section-risks",
  recommendations: "ai-section-decisions",
  management_comment: "ai-section-comment",
  accordion: "ai-section-accordion",
  details: "ai-section-accordion",
};

/**
 * `ui_spec`ten tam pencere HTML'i üretir.
 *
 * `structured` verilirse her sayı kaynağa göre doğrulanır.
 */
function aiRenderView(spec, structured) {
  if (!spec || typeof spec !== "object" || spec.version !== "2.0") {
    return `<div class="state error">Sonuç penceresi tanımı okunamadı.</div>`;
  }

  const sourceIndex = structured ? aiSourceIndex(structured) : null;
  AI_CURRENT_SOURCE = sourceIndex;
  const viewId = aiSafeId(spec.view_id);

  const sections = (spec.sections || [])
    .map((section) => {
      const cls = AI_SECTION_CLASS[section.type];
      if (!cls) return "";
      const inner = (section.components || [])
        .map((component) => {
          const html = aiRenderComponent(component, sourceIndex);
          if (!html) return "";
          const span = Math.min(12, Math.max(1, Number(component.span) || 12));
          return `<div class="ai-cell" data-ai-declared="${fmt.esc(component.type)}"
            style="--ai-span:${span}">${html}</div>`;
        })
        .join("");
      if (!inner) return "";
      return `<section class="ai-section ${cls}">
        ${section.title
          ? `<header class="ai-section-head">
               <h4 class="ai-section-title">${fmt.esc(section.title)}</h4>
               ${section.subtitle
                 ? `<p class="ai-section-sub">${fmt.esc(section.subtitle)}</p>` : ""}
             </header>`
          : ""}
        <div class="ai-grid">${inner}</div>
      </section>`;
    })
    .join("");

  const scopeText = Object.values(spec.scope || {}).filter(Boolean).slice(-1)[0];
  const calculated = spec.calculated_at
    ? new Date(spec.calculated_at).toLocaleString("tr-TR")
    : "—";

  return `<style>${aiScopedStyle(viewId, spec.theme || {})}</style>
  <div class="ai-generated-view" data-view-id="${viewId}" role="region"
       aria-label="${fmt.esc(spec.title || "Analiz penceresi")}">
    <header class="ai-view-head">
      <div>
        <h3 class="ai-view-title">${fmt.esc(spec.title || "Analiz")}</h3>
        ${spec.subtitle ? `<div class="ai-view-sub">${fmt.esc(spec.subtitle)}</div>` : ""}
      </div>
      <button class="ai-close" type="button" data-ai-close
              aria-label="Analiz penceresini kapat">Kapat</button>
    </header>

    ${sections}

    <footer class="ai-view-foot">
      <div><span>Akademik yıl</span><b>${fmt.esc(spec.academic_year || "—")}</b></div>
      <div><span>Kapsam</span><b>${fmt.esc(scopeText || "Üniversite geneli")}</b></div>
      <div><span>Hesaplama zamanı</span><b>${fmt.esc(calculated)}</b></div>
      <div><span>Ek maliyetler</span><b>Hesaba katılmadı</b></div>
    </footer>
  </div>`;
}
