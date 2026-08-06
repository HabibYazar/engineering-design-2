// Dinamik sonuç penceresi çizici.
//
// TASARIM İLKESİ
// --------------
// Bu dosya YALNIZCA backend'in ürettiği `ui_spec` nesnesini çizer. Modelin
// serbest metninden sayı ayıklamaz, hiçbir hesap yapmaz ve modelin gönderdiği
// hiçbir kodu çalıştırmaz.
//
// GÜVENLİK
// --------
// 1. Bileşen kayıt defteri KAPALIDIR. Tanımlı olmayan bir `type` çizilmez.
// 2. Bütün metinler `fmt.esc()` ile kaçırılır; ham HTML basılmaz.
// 3. Tema yalnızca beş belirteçten oluşur ve KAPSAMLI (scoped) CSS
//    değişkenlerine çevrilir: `.ai-generated-view[data-view-id="…"]`.
//    body, html, *, #sidebar gibi seçicilere stil yazılamaz.

/** İzin verilen tema belirteçleri. Listede olmayan değer yok sayılır. */
const AI_THEME_TOKENS = {
  accent: {
    indigo: "#4f46e5",
    teal: "#0d9488",
    amber: "#d97706",
    slate: "#475569",
    rose: "#e11d48",
  },
  density: { compact: "8px", comfortable: "14px" },
  card_radius: { sharp: "2px", soft: "10px", round: "18px" },
  chart_emphasis: { low: "0.55", normal: "0.8", high: "1" },
  risk_emphasis: { low: "0.5", normal: "0.85", high: "1" },
};

// Grafik serisi rolleri → renk. Legend bu adlarla eşleşir.
const AI_SERIES_COLORS = {
  baseline: "var(--ai-baseline)",
  scenario: "var(--ai-scenario)",
  capacity: "var(--ai-capacity)",
};

/**
 * Pencere kimliğini CSS'e girmeden önce beyaz listeden geçirir.
 *
 * Kaçırma (escaping) burada YETMEZ: `<style>` içeriği ham metin olarak
 * ayrıştırılır, dolayısıyla `"] * { … }` gibi bir kimlik seçiciyi kırıp
 * genel CSS üretebilirdi. Harf, rakam, tire ve alt çizgi dışındaki her
 * karakter atılır; geriye kalan hiçbir dizgi CSS seçicisini bozamaz.
 */
function aiSafeId(viewId) {
  const cleaned = String(viewId || "").replace(/[^A-Za-z0-9_-]/g, "");
  return cleaned || "aiv-unknown";
}

/**
 * Tema belirteçlerinden KAPSAMLI CSS üretir.
 *
 * Seçici her zaman `[data-view-id]` ile sınırlıdır; üretilen stil
 * uygulamanın geri kalanına sızamaz.
 */
function aiScopedStyle(viewId, theme = {}) {
  const pick = (group, value, fallback) =>
    AI_THEME_TOKENS[group][value] !== undefined
      ? AI_THEME_TOKENS[group][value]
      : AI_THEME_TOKENS[group][fallback];

  const accent = pick("accent", theme.accent, "indigo");
  const gap = pick("density", theme.density, "comfortable");
  const radius = pick("card_radius", theme.card_radius, "soft");
  const chartOpacity = pick("chart_emphasis", theme.chart_emphasis, "normal");
  const riskOpacity = pick("risk_emphasis", theme.risk_emphasis, "normal");

  return (
    `.ai-generated-view[data-view-id="${aiSafeId(viewId)}"]{` +
    `--ai-accent:${accent};` +
    `--ai-gap:${gap};` +
    `--ai-card-radius:${radius};` +
    `--ai-chart-opacity:${chartOpacity};` +
    `--ai-risk-opacity:${riskOpacity};` +
    `--ai-baseline:#2563eb;` +
    `--ai-scenario:#ea580c;` +
    `--ai-capacity:#94a3b8;` +
    `}`
  );
}

/* ------------------------------------------------------------------ */
/* Bileşen kayıt defteri                                               */
/* ------------------------------------------------------------------ */

const AI_COMPONENTS = {
  metric_card(c) {
    return `<div class="ai-card">
      ${aiScopeBadge(c)}
      <div class="ai-card-title">${fmt.esc(c.title || "")}</div>
      <div class="ai-card-value">${fmt.esc(c.value || "—")}</div>
      ${c.note ? `<div class="ai-card-note">${fmt.esc(c.note)}</div>` : ""}
    </div>`;
  },

  comparison_metric(c) {
    const trendClass = c.trend ? ` ai-trend-${fmt.esc(c.trend)}` : "";
    return `<div class="ai-card">
      ${aiScopeBadge(c)}
      <div class="ai-card-title">${fmt.esc(c.title || "")}</div>
      <div class="ai-card-compare">
        <span class="ai-before">${fmt.esc(c.baseline_label || "—")}</span>
        <span class="ai-arrow">→</span>
        <span class="ai-after">${fmt.esc(c.scenario_label || "—")}</span>
      </div>
      ${c.delta_label ? `<div class="ai-card-delta${trendClass}">${fmt.esc(c.delta_label)}</div>` : ""}
      ${c.note ? `<div class="ai-card-note">${fmt.esc(c.note)}</div>` : ""}
    </div>`;
  },

  bar_chart(c) {
    return aiBarChart(c);
  },

  line_chart(c) {
    // Bu aşamada çizgi grafiği de çubuk olarak çizilir; ayrı bir çizim
    // motoru eklemek yerine aynı güvenli SVG üreticisi kullanılır.
    return aiBarChart(c);
  },

  gauge(c) {
    const percent = Math.max(0, Math.min(100, Number(c.percent) || 0));
    return `<div class="ai-card ai-gauge">
      <div class="ai-card-title">${fmt.esc(c.title || "")}</div>
      <div class="ai-gauge-track"><div class="ai-gauge-fill" style="width:${percent}%"></div></div>
      <div class="ai-card-value">${fmt.esc(String(c.percent ?? "—"))}%</div>
    </div>`;
  },

  risk_card(c) {
    const level = ["info", "warning", "critical"].includes(c.level) ? c.level : "info";
    return `<div class="ai-risk ai-risk-${level}">
      <div class="ai-risk-head">
        <span class="ai-risk-title">${fmt.esc(c.title || "")}</span>
        ${c.subtitle ? `<span class="ai-risk-sub">${fmt.esc(c.subtitle)}</span>` : ""}
      </div>
      <ul class="ai-list">${(c.items || [])
        .map((item) => `<li>${fmt.esc(item)}</li>`)
        .join("")}</ul>
      ${c.note ? `<div class="ai-card-note">${fmt.esc(c.note)}</div>` : ""}
    </div>`;
  },

  information_box(c) {
    const level = ["info", "warning", "critical"].includes(c.level) ? c.level : "info";
    return `<div class="ai-info ai-info-${level}">
      ${c.title ? `<div class="ai-card-title">${fmt.esc(c.title)}</div>` : ""}
      <div class="ai-info-body">${aiSafeText(c.body || "")}</div>
    </div>`;
  },

  recommendation_list(c) {
    return `<ul class="ai-list">${(c.items || [])
      .map((item) => `<li>${fmt.esc(item)}</li>`)
      .join("")}</ul>`;
  },

  data_source_panel(c) {
    return `<div class="ai-sources">
      <div class="ai-card-title">${fmt.esc(c.title || "Kullanılan veriler")}</div>
      <ul class="ai-list">${(c.items || [])
        .map((item) => `<li>${fmt.esc(item)}</li>`)
        .join("")}</ul>
    </div>`;
  },

  scope_badge(c) {
    return aiScopeBadge(c);
  },

  assumptions_panel(c) {
    return `<div class="ai-assumptions">
      <div class="ai-card-title">${fmt.esc(c.title || "Varsayımlar")}</div>
      <ul class="ai-list">${(c.items || [])
        .map((item) => `<li>${fmt.esc(item)}</li>`)
        .join("")}</ul>
    </div>`;
  },

  expandable_details(c) {
    const inner =
      (c.components || []).map(aiRenderComponent).join("") +
      (c.markdown ? `<div class="ai-markdown">${aiSafeText(c.markdown)}</div>` : "");
    return `<details class="ai-details"${c.open ? " open" : ""}>
      <summary>${fmt.esc(c.title || "Ayrıntılar")}</summary>
      <div class="ai-details-body">${inner}</div>
    </details>`;
  },
};

/** Bir bileşeni çizer. Tanımlı olmayan tür SESSİZCE ATLANIR. */
function aiRenderComponent(component) {
  if (!component || typeof component !== "object") return "";
  const renderer = AI_COMPONENTS[component.type];
  if (!renderer) {
    // Bilinmeyen tür çizilmez. Uygulama çökmez, yalnızca o bileşen atlanır.
    console.warn("Bilinmeyen bileşen türü atlandı:", component.type);
    return "";
  }
  return renderer(component);
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
  return `<span class="ai-scope-badge ai-scope-${fmt.esc(
    c.scope_type || "university"
  )}">${fmt.esc(label)}: ${fmt.esc(c.scope_name)}</span>`;
}

/**
 * Metni güvenli biçimde çizer.
 * ÖNCE kaçırır, SONRA sınırlı biçimlendirme uygular — tersi yapılsaydı
 * gelen bir <script> sayfaya girerdi.
 */
function aiSafeText(raw) {
  const escaped = fmt.esc(String(raw || ""));

  // Desteklenen tek biçimler: başlık (#), madde listesi ve paragraf.
  // Başka hiçbir Markdown yapısı HTML'e çevrilmez.
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
/* Grafik — güvenli SVG                                                */
/* ------------------------------------------------------------------ */

function aiBarChart(c) {
  const categories = c.categories || [];
  const series = (c.series || []).filter((s) => Array.isArray(s.values));
  if (!categories.length || !series.length) {
    return `<div class="ai-chart"><div class="ai-card-title">${fmt.esc(
      c.title || ""
    )}</div><div class="ai-empty">Grafik için veri yok.</div></div>`;
  }

  const all = series.flatMap((s) => s.values).filter((v) => Number.isFinite(v));
  const max = Math.max(...all, 1);

  const groups = categories
    .map((category, index) => {
      const bars = series
        .map((s) => {
          const value = Number(s.values[index]);
          if (!Number.isFinite(value)) return "";
          const height = Math.max(2, (value / max) * 100);
          const color = AI_SERIES_COLORS[s.role] || "var(--ai-baseline)";
          return `<div class="ai-bar-wrap" title="${fmt.esc(s.label)}: ${fmt.esc(
            aiFormatNumber(value)
          )}">
            <div class="ai-bar-value">${fmt.esc(aiFormatNumber(value))}</div>
            <div class="ai-bar" style="height:${height}%;background:${color}"></div>
          </div>`;
        })
        .join("");
      return `<div class="ai-bar-group">
        <div class="ai-bars">${bars}</div>
        <div class="ai-bar-label">${fmt.esc(category)}</div>
      </div>`;
    })
    .join("");

  // Legend YALNIZCA burada, bir kez çizilir.
  const legend = (c.legend || [])
    .map(
      (entry) =>
        `<span class="ai-legend-item"><span class="ai-swatch" style="background:${
          AI_SERIES_COLORS[entry.role] || "var(--ai-baseline)"
        }"></span>${fmt.esc(entry.label)}</span>`
    )
    .join("");

  return `<div class="ai-chart">
    <div class="ai-card-title">${fmt.esc(c.title || "")}</div>
    ${c.subtitle ? `<div class="ai-card-note">${fmt.esc(c.subtitle)}</div>` : ""}
    <div class="ai-bar-chart">${groups}</div>
    ${legend ? `<div class="ai-legend">${legend}</div>` : ""}
    ${c.unit ? `<div class="ai-card-note">Birim: ${fmt.esc(c.unit)}</div>` : ""}
  </div>`;
}

function aiFormatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  if (Number.isInteger(number)) return number.toLocaleString("tr-TR");
  return number.toLocaleString("tr-TR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/* ------------------------------------------------------------------ */
/* Pencere                                                             */
/* ------------------------------------------------------------------ */

const AI_SECTION_TITLES = {
  metric_grid: "ai-section-metrics",
  chart_grid: "ai-section-charts",
  risk_summary: "ai-section-risks",
  management_comment: "ai-section-comment",
  details: "ai-section-details",
};

/** `ui_spec`ten tam pencere HTML'i üretir. */
function aiRenderView(spec) {
  if (!spec || typeof spec !== "object" || spec.version !== "1.0") {
    return `<div class="state error">Sonuç penceresi tanımı okunamadı.</div>`;
  }

  // Kimlik hem `data-view-id` özniteliğine hem CSS seçicisine girer; ikisi
  // AYNI temizlenmiş değeri kullanmalı, yoksa stil hiç eşleşmez.
  const viewId = aiSafeId(spec.view_id);
  const sections = (spec.sections || [])
    .map((section) => {
      const cls = AI_SECTION_TITLES[section.type];
      if (!cls) return "";
      const inner = (section.components || []).map(aiRenderComponent).join("");
      if (!inner) return "";
      return `<section class="ai-section ${cls}">
        ${section.title ? `<h4 class="ai-section-title">${fmt.esc(section.title)}</h4>` : ""}
        <div class="ai-section-body">${inner}</div>
      </section>`;
    })
    .join("");

  const scopeText = Object.values(spec.scope || {}).filter(Boolean).slice(-1)[0];
  const calculated = spec.calculated_at
    ? new Date(spec.calculated_at).toLocaleString("tr-TR")
    : "—";

  return `<style>${aiScopedStyle(viewId, spec.theme || {})}</style>
  <div class="ai-generated-view" data-view-id="${viewId}">
    <header class="ai-view-head">
      <div>
        <h3 class="ai-view-title">${fmt.esc(spec.title || "Analiz")}</h3>
        ${spec.subtitle ? `<div class="ai-view-sub">${fmt.esc(spec.subtitle)}</div>` : ""}
      </div>
      <button class="ai-close" type="button" data-ai-close>Kapat</button>
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
