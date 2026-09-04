/* ABÜ KDS — yeniden kullanılabilir dosya tabanlı ikincil veri kaynağı sistemi. */

const dataSourceState = {
  definitions: null,
  activeModal: null,
  source: null,
  inspection: null,
  mapping: {},
  validation: null,
  triggerMetric: null,
};

function dataSourceScope() {
  const raw = typeof kapsam === "function" ? kapsam() : {};
  return {
    scope_type: typeof seviye === "function" ? seviye() : "university",
    academic_year: (typeof K !== "undefined" && K.donem) || raw.academic_year,
    faculty_id: raw.faculty_id,
    department_id: raw.department_id,
    program_id: raw.academic_program_id,
  };
}

function dataSourceCanManage(scope = dataSourceScope()) {
  const user = typeof auth !== "undefined" ? auth.user : null;
  if (!user) return true;
  const permissions = Array.isArray(user.permissions) ? user.permissions : [];
  if (permissions.includes("edit_all")) return true;
  if (permissions.includes("edit_faculty")) {
    return !!scope.faculty_id && Number(scope.faculty_id) === Number(user.faculty_id);
  }
  if (permissions.includes("edit_department")) {
    return !!scope.department_id && Number(scope.department_id) === Number(user.department_id);
  }
  return false;
}

async function dataSourceDefinitions() {
  if (!dataSourceState.definitions) {
    dataSourceState.definitions = api.get("/api/data-sources/definitions")
      .then(rows => Object.fromEntries(rows.map(row => [row.key, row])));
  }
  return dataSourceState.definitions;
}

function dataSourceUploadButton(metricKey = "") {
  if (!dataSourceCanManage()) return "";
  return `<button type="button" class="data-source-add" data-source-upload="${fmt.esc(metricKey)}">+ Veri Kaynağı Ekle</button>`;
}

function uploadedSourceBadge(row) {
  if (row.source_type === "uploaded") {
    return `<span class="data-source-badge is-uploaded" data-source-id="${row.uploaded_source_id}">
      ${fmt.esc(dataSourceProvenance(row))}</span>
      <small class="data-source-filename">${fmt.esc(row.filename || "")}</small>`;
  }
  return `<span class="data-source-badge is-authoritative">✓ ${fmt.esc(row.source_label || "Yetkili veri")}</span>`;
}

function dataSourceProvenance(row) {
  if (!row) return "";
  const label = row.provenance || row.source_label || "Kullanıcı veri kaynağı";
  return row.is_synthetic && !String(label).includes("SYNTHETIC_GENERATED")
    ? `SYNTHETIC_GENERATED · ${label}` : String(label);
}

function dataSourceCaption(row) {
  const label = dataSourceProvenance(row);
  return [label, row && row.filename].filter(Boolean).join(" · ");
}

function dataSourceFormat(row) {
  const value = row && row.resolved_value;
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  const unit = row.unit || (row.definition && row.definition.unit) || "";
  if (unit === "%") return fmt.pct(value, 1);
  if (unit === "adet") return fmt.int(value);
  if (unit === "milyon USD") return fmt.usdMillion(value, 2);
  return `${fmt.dec(value, 2)}${unit ? " " + fmt.esc(unit) : ""}`;
}

function dataSourceCard(row) {
  const definition = row.definition || {};
  if (row.status === "unavailable") {
    return `<article class="data-source-card is-empty" data-source-metric="${fmt.esc(definition.key)}">
      <div class="data-source-card-label">${fmt.esc(definition.label)}</div>
      <div class="data-source-empty-copy">Veri bulunamadı</div>
      ${row.can_upload ? dataSourceUploadButton(definition.key) : ""}
    </article>`;
  }
  return `<article class="data-source-card" data-source-metric="${fmt.esc(definition.key)}">
    <div class="data-source-card-label">${fmt.esc(definition.label)}</div>
    <div class="data-source-card-value">${dataSourceFormat(row)}</div>
    <div class="data-source-card-meta">${uploadedSourceBadge(row)}</div>
    ${row.source_type === "uploaded" ? `<button type="button" class="data-source-link" data-source-detail="${row.uploaded_source_id}">Kaynak detayı</button>` : ""}
  </article>`;
}

function dataSourceChart(rows) {
  const values = (rows || []).filter(row => row.resolved_value !== null
    && row.resolved_value !== undefined && Number.isFinite(Number(row.resolved_value)));
  if (!values.length) return bekleniyorGovde("Bu kapsam ve dönemde çizilecek ölçüm yok.");
  const colors = ["var(--vurgu)", "var(--vurgu-2)", "var(--mor)"];
  return yatayCubuk(values.map((row, index) => ({
    ad: row.definition.label,
    deger: Number(row.resolved_value),
    renk: colors[index % colors.length],
    ipucu: `${dataSourceFormat(row)} · ${row.source_label}${row.filename ? `: ${row.filename}` : ""}`,
  })), {
    yb: value => {
      const unit = values[0].unit || values[0].definition.unit;
      if (unit === "%") return fmt.pct(value, 1);
      if (unit === "adet") return fmt.int(value);
      if (unit === "milyon USD") return fmt.usdMillion(value, 1);
      return fmt.dec(value, 1);
    },
    eksenY: `${values[0].unit || values[0].definition.unit || "değer"} · kaynak kartlarda belirtilir`,
  });
}

function dataSourceGroupRender(rows, view = "full") {
  const manager = dataSourceCanManage()
    ? `<div class="data-source-toolbar"><button type="button" data-source-manager>Veri Kaynakları</button></div>` : "";
  const cards = `<div class="data-source-grid">${rows.map(dataSourceCard).join("")}</div>`;
  const chart = `<div class="data-source-chart" data-source-chart>${dataSourceChart(rows)}</div>`;
  if (view === "cards") return cards + manager;
  if (view === "chart") return chart;
  return cards + chart + manager;
}

async function dataSourceAvailability(metricKey, fixedScope = null) {
  return api.get("/api/data-sources/availability", {
    metric_key: metricKey, ...(fixedScope || dataSourceScope()),
  });
}

function dataSourceGroupLoad(containerId, metricKeys, options = {}) {
  const target = document.getElementById(containerId);
  if (!target) return;
  target.dataset.sourceMetrics = metricKeys.join(",");
  target.dataset.sourceView = options.view || "full";
  doldur(
    containerId,
    () => Promise.all(metricKeys.map(key => dataSourceAvailability(key))),
    rows => dataSourceGroupRender(rows, options.view || "full"),
    { iskelet: Math.max(3, metricKeys.length) },
  );
}

function dataSourceModalClose() {
  if (!dataSourceState.activeModal) return;
  document.removeEventListener("keydown", dataSourceState.activeModal.keyHandler, true);
  dataSourceState.activeModal.element.remove();
  dataSourceState.activeModal = null;
}

function dataSourceModalShell(title, subtitle = "") {
  dataSourceModalClose();
  const overlay = document.createElement("div");
  overlay.className = "data-source-modal";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", title);
  overlay.innerHTML = `<div class="data-source-modal-box" role="document">
    <header class="data-source-modal-head">
      <div><h3>${fmt.esc(title)}</h3><p>${fmt.esc(subtitle)}</p></div>
      <button type="button" data-source-close aria-label="Kapat">✕</button>
    </header>
    <div class="data-source-modal-body" data-source-modal-body></div>
  </div>`;
  const keyHandler = event => {
    if (event.key === "Escape") dataSourceModalClose();
  };
  document.addEventListener("keydown", keyHandler, true);
  overlay.addEventListener("click", event => {
    if (event.target === overlay || event.target.closest("[data-source-close]")) dataSourceModalClose();
  });
  document.body.appendChild(overlay);
  dataSourceState.activeModal = { element: overlay, keyHandler };
  return overlay;
}

function dataSourceBody() {
  return dataSourceState.activeModal && dataSourceState.activeModal.element.querySelector("[data-source-modal-body]");
}

function wizardSteps(active) {
  const labels = ["Dosya", "İncele", "Eşle", "Doğrula", "İçe Aktar"];
  return `<div class="data-source-steps">${labels.map((label, index) =>
    `<span class="${index + 1 === active ? "active" : index + 1 < active ? "done" : ""}">${index + 1}. ${label}</span>`
  ).join("")}</div>`;
}

function sourceError(message) {
  return `<div class="data-source-error" data-source-error>${fmt.esc(message)}</div>`;
}

function filePreview(inspection) {
  if (!inspection.columns.length) return `<div class="data-source-empty">Tablo seçildikten sonra önizleme gösterilir.</div>`;
  return `<div class="data-source-preview"><table>
    <thead><tr><th>#</th>${inspection.columns.map(column => `<th>${fmt.esc(column)}</th>`).join("")}</tr></thead>
    <tbody>${inspection.preview_rows.map((row, index) => `<tr><td>${index + 2}</td>${inspection.columns.map(column =>
      `<td title="${fmt.esc(row[column] ?? "")}">${fmt.esc(row[column] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
}

function renderInspect() {
  const body = dataSourceBody();
  const info = dataSourceState.inspection;
  const source = dataSourceState.source;
  if (!body || !info) return;
  const selector = info.sheets.length
    ? `<label>Excel sayfası<select data-source-sheet>${info.sheets.map(name =>
        `<option value="${fmt.esc(name)}"${name === info.selected_sheet ? " selected" : ""}>${fmt.esc(name)}</option>`).join("")}</select></label>`
    : info.tables.length
    ? `<label>SQLite tablosu<select data-source-table><option value="">Tablo seçin</option>${info.tables.map(name =>
        `<option value="${fmt.esc(name)}"${name === info.selected_table ? " selected" : ""}>${fmt.esc(name)}</option>`).join("")}</select></label>` : "";
  body.innerHTML = `${wizardSteps(2)}
    <div class="data-source-facts">
      <div><span>Dosya</span><b>${fmt.esc(source.original_filename)}</b></div>
      <div><span>Tür</span><b>${fmt.esc(source.file_type.toUpperCase())}</b></div>
      <div><span>Satır</span><b>${fmt.int(info.row_count)}</b></div>
      <div><span>Sütun</span><b>${fmt.int(info.columns.length)}</b></div>
    </div>
    <div class="data-source-selectors">${selector}</div>
    <h4>İlk ${Math.min(20, info.preview_rows.length)} satır</h4>
    ${filePreview(info)}
    <div class="data-source-error" data-source-error hidden></div>
    <div class="data-source-buttons"><button type="button" data-source-close>İptal</button>
      <button type="button" class="primary" data-source-to-map${info.requires_table_selection ? " disabled" : ""}>Sütun Eşlemeye Geç</button></div>`;
  const reload = async selection => {
    const error = body.querySelector("[data-source-error]");
    try {
      dataSourceState.inspection = await api.post(`/api/data-sources/${source.id}/inspect`, selection);
      dataSourceState.mapping = { ...dataSourceState.inspection.auto_mapping };
      renderInspect();
    } catch (requestError) {
      error.textContent = requestError.userMessage || requestError.message;
      error.hidden = false;
    }
  };
  body.querySelector("[data-source-sheet]")?.addEventListener("change", event => reload({ selected_sheet: event.target.value }));
  body.querySelector("[data-source-table]")?.addEventListener("change", event => reload({ selected_table: event.target.value || null }));
  body.querySelector("[data-source-to-map]")?.addEventListener("click", renderMapping);
}

function columnMapper(inspection, mapping) {
  const options = [{ key: "ignore", label: "Kullanma", kind: "ignore" }, ...inspection.semantic_fields];
  return `<div class="data-source-mapper">${inspection.columns.map(column => {
    const selected = mapping[column] || "ignore";
    return `<label><span><b>${fmt.esc(column)}</b><small>${fmt.esc((inspection.preview_rows[0] || {})[column] || "boş")}</small></span>
      <select data-map-column="${fmt.esc(column)}">${options.map(option =>
        `<option value="${fmt.esc(option.key)}"${option.key === selected ? " selected" : ""}>${fmt.esc(option.label)}${option.kind === "metric" && option.unit ? ` (${fmt.esc(option.unit)})` : ""}</option>`
      ).join("")}</select></label>`;
  }).join("")}</div>`;
}

function renderMapping() {
  const body = dataSourceBody();
  const info = dataSourceState.inspection;
  if (!body || !info) return;
  body.innerHTML = `${wizardSteps(3)}
    <p class="data-source-note">Otomatik eşlemeler yalnızca açık ve tekil başlık eşleşmelerinde yapıldı. Her sütunu kontrol edin; belirsiz alanlar kendiliğinden tahmin edilmez.</p>
    ${columnMapper(info, dataSourceState.mapping)}
    <div class="data-source-error" data-source-error hidden></div>
    <div class="data-source-buttons"><button type="button" data-source-back-inspect>Geri</button>
      <button type="button" class="primary" data-source-validate>Doğrula</button></div>`;
  body.querySelectorAll("[data-map-column]").forEach(select => select.addEventListener("change", event => {
    dataSourceState.mapping[event.target.dataset.mapColumn] = event.target.value;
  }));
  body.querySelector("[data-source-back-inspect]").addEventListener("click", renderInspect);
  body.querySelector("[data-source-validate]").addEventListener("click", async event => {
    const button = event.currentTarget;
    const error = body.querySelector("[data-source-error]");
    button.disabled = true;
    error.hidden = true;
    try {
      const response = await api.post(`/api/data-sources/${dataSourceState.source.id}/validate`, {
        mapping: dataSourceState.mapping,
        selected_sheet: info.selected_sheet,
        selected_table: info.selected_table,
      });
      dataSourceState.validation = response.summary;
      renderValidation();
    } catch (requestError) {
      error.textContent = requestError.userMessage || requestError.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
}

function validationSummary(summary) {
  const facts = [
    ["Okunan satır", summary.rows_read], ["Geçerli satır", summary.rows_valid],
    ["Eşleşmeyen", summary.rows_unmatched], ["Yetkili veri çakışması", summary.conflict_count],
    ["Doldurulabilecek eksik değer", summary.new_missing_values],
  ];
  const unmatched = (summary.unmatched_examples || []).map(item =>
    `<li><b>Satır ${item.row}</b>: ${fmt.esc(item.reason)}</li>`).join("");
  const conflicts = (summary.conflict_examples || []).map(item =>
    `<li><b>Satır ${item.row} · ${fmt.esc(item.metric)}</b>: yüklenen ${fmt.esc(item.uploaded_value)}, korunan ${fmt.esc(item.authoritative_value)} (${fmt.esc(item.authoritative_source)})</li>`).join("");
  return `<div class="data-source-summary">${facts.map(([label, value]) =>
      `<div><span>${label}</span><b>${fmt.int(value)}</b></div>`).join("")}</div>
    ${unmatched ? `<details><summary>Eşleşmeyen satır örnekleri</summary><ul>${unmatched}</ul></details>` : ""}
    ${conflicts ? `<details><summary>Çakışma örnekleri</summary><ul>${conflicts}</ul></details>` : ""}`;
}

function renderValidation() {
  const body = dataSourceBody();
  const summary = dataSourceState.validation;
  if (!body || !summary) return;
  body.innerHTML = `${wizardSteps(4)}${validationSummary(summary)}
    <p class="data-source-note">Varsayılan davranış <b>yalnızca eksikleri doldur</b>. Yetkili kaynaklarla çakışan değerler içe aktarılmayacak.</p>
    <div class="data-source-error" data-source-error hidden></div>
    <div class="data-source-buttons"><button type="button" data-source-back-map>Geri</button>
      <button type="button" class="primary" data-source-import${summary.new_missing_values ? "" : " disabled"}>İçe Aktar</button></div>`;
  body.querySelector("[data-source-back-map]").addEventListener("click", renderMapping);
  body.querySelector("[data-source-import]")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    const error = body.querySelector("[data-source-error]");
    button.disabled = true;
    try {
      const response = await api.post(`/api/data-sources/${dataSourceState.source.id}/import`, {
        mapping: dataSourceState.mapping,
        selected_sheet: summary.selected_sheet,
        selected_table: summary.selected_table,
        confirm: true,
      });
      dataSourceState.source = response.source;
      body.innerHTML = `${wizardSteps(5)}<div class="data-source-success">
        <b>İçe aktarma tamamlandı</b><p>${fmt.int(response.summary.importable_row_count)} satır, ${fmt.int(response.summary.new_missing_values)} eksik değeri doldurdu.</p>
        ${validationSummary(response.summary)}</div>
        <div class="data-source-buttons"><button type="button" data-source-open-manager>Veri Kaynakları</button>
          <button type="button" class="primary" data-source-finish>Tamam</button></div>`;
      document.dispatchEvent(new CustomEvent("data-source-changed"));
      body.querySelector("[data-source-finish]").addEventListener("click", dataSourceModalClose);
      body.querySelector("[data-source-open-manager]").addEventListener("click", uploadedSourceManager);
    } catch (requestError) {
      error.textContent = requestError.userMessage || requestError.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
}

function dataSourceUploadModal(metricKey = "") {
  dataSourceState.source = null;
  dataSourceState.inspection = null;
  dataSourceState.mapping = {};
  dataSourceState.validation = null;
  dataSourceState.triggerMetric = metricKey;
  const scope = dataSourceScope();
  const overlay = dataSourceModalShell("Veri Kaynağı Ekle", "Dosyanız yetkili proje tablolarından ayrı tutulur.");
  const body = dataSourceBody();
  body.innerHTML = `${wizardSteps(1)}
    <form class="data-source-upload-form" data-source-upload-form>
      <div class="data-source-context"><span>Kapsam</span><b>${fmt.esc(typeof dugum === "function" ? dugum().ad : scope.scope_type)}</b>
        <span>Akademik yıl</span><b>${fmt.esc(scope.academic_year)}</b></div>
      <label class="data-source-drop">XLSX, XLS, CSV, JSON veya SQLite .db
        <input type="file" name="file" required accept=".xlsx,.xls,.csv,.json,.db">
        <small>En fazla 20 MB. Dosya veri olarak okunur; kod veya SQL çalıştırılmaz.</small></label>
      <label>Kaynak notu <small>(isteğe bağlı)</small><textarea name="notes" rows="2" maxlength="4000"></textarea></label>
      <div class="data-source-error" data-source-error hidden></div>
      <div class="data-source-buttons"><button type="button" data-source-manager>Mevcut Kaynaklar</button>
        <button type="submit" class="primary">Yükle ve İncele</button></div>
    </form>`;
  const form = body.querySelector("[data-source-upload-form]");
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const file = form.elements.file.files[0];
    const error = form.querySelector("[data-source-error]");
    const button = form.querySelector("button[type='submit']");
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
      error.textContent = "Dosya 20 MB yükleme sınırını aşıyor.";
      error.hidden = false;
      return;
    }
    const payload = new FormData();
    payload.append("file", file);
    Object.entries(scope).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") payload.append(key, value);
    });
    const notes = String(form.elements.notes.value || "").trim();
    if (notes) payload.append("notes", notes);
    button.disabled = true;
    try {
      dataSourceState.source = await api.upload("/api/data-sources/upload", payload);
      dataSourceState.inspection = await api.post(`/api/data-sources/${dataSourceState.source.id}/inspect`, {});
      dataSourceState.mapping = { ...dataSourceState.inspection.auto_mapping };
      renderInspect();
    } catch (requestError) {
      error.textContent = requestError.userMessage || requestError.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
  overlay.querySelector("input[type='file']")?.focus();
  return overlay;
}

function sourceScopeLabel(source) {
  const ids = [source.faculty_id && `F:${source.faculty_id}`, source.department_id && `B:${source.department_id}`, source.program_id && `P:${source.program_id}`].filter(Boolean);
  return `${source.scope_type}${ids.length ? ` (${ids.join("/")})` : ""} · ${source.academic_year || "yıl dosyada"}`;
}

async function uploadedSourceManager(focusId = null) {
  dataSourceModalShell("Veri Kaynakları", "Yüklenen ikincil kaynakları inceleyin veya kaldırın.");
  const body = dataSourceBody();
  body.innerHTML = ui.loading("Veri kaynakları yükleniyor…");
  try {
    const sources = await api.get("/api/data-sources");
    const add = dataSourceCanManage()
      ? `<div class="data-source-toolbar">${dataSourceUploadButton("")}</div>` : "";
    body.innerHTML = add + (sources.length ? `<div class="data-source-list">${sources.map(source => `
      <article${Number(source.id) === Number(focusId) ? ' class="focused"' : ""}>
        <div><b>${fmt.esc(source.original_filename)}</b><small>${fmt.esc(sourceScopeLabel(source))}</small></div>
        <div class="data-source-counts"><span>${fmt.int(source.row_count)} satır</span><span>${fmt.int(source.imported_row_count)} eşleşti</span>
          <span>${fmt.int(source.unmatched_row_count)} eşleşmedi</span><span>${fmt.int(source.conflict_count)} çakışma</span></div>
        <small>Yüklendi: ${fmt.esc(source.uploaded_at || "—")}</small>
        <div class="data-source-list-actions"><button type="button" data-source-detail="${source.id}">Detay</button>
          <button type="button" class="danger" data-source-delete="${source.id}">Sil</button></div>
      </article>`).join("")}</div>` : `<div class="data-source-empty">Henüz yüklenmiş veri kaynağı yok.</div>`);
  } catch (error) {
    body.innerHTML = sourceError(error.userMessage || error.message);
  }
}

async function dataSourceDetail(sourceId) {
  dataSourceModalShell("Veri Kaynağı Detayı", "Dosya, eşleme ve içe aktarma özeti.");
  const body = dataSourceBody();
  body.innerHTML = ui.loading();
  try {
    const source = await api.get(`/api/data-sources/${sourceId}`);
    const summary = source.validation;
    body.innerHTML = `<div class="data-source-facts">
      <div><span>Dosya</span><b>${fmt.esc(source.original_filename)}</b></div>
      <div><span>Tür</span><b>${fmt.esc(source.file_type.toUpperCase())}</b></div>
      <div><span>Durum</span><b>${fmt.esc(source.status)}</b></div>
      <div><span>Seçim</span><b>${fmt.esc(source.selected_sheet || source.selected_table || "—")}</b></div>
      <div><span>Satır</span><b>${fmt.int(source.row_count)}</b></div>
      <div><span>Checksum</span><b title="${fmt.esc(source.checksum_sha256)}">${fmt.esc(source.checksum_sha256.slice(0, 14))}…</b></div>
    </div>${summary ? validationSummary(summary) : ""}
    <div class="data-source-buttons"><button type="button" data-source-manager>Listeye Dön</button>
      <button type="button" class="danger" data-source-delete="${source.id}">Kaynağı Sil</button></div>`;
  } catch (error) {
    body.innerHTML = sourceError(error.userMessage || error.message);
  }
}

function dataSourceDelete(sourceId) {
  const overlay = dataSourceModalShell("Veri Kaynağını Sil", "Bu işlem yalnızca seçili kullanıcı kaynağını etkiler.");
  const body = dataSourceBody();
  body.innerHTML = `<div class="data-source-confirm"><p>Bu veri kaynağını silerseniz yalnızca bu dosyadan içe aktarılan veriler kaldırılacaktır. Yetkili proje verileri etkilenmeyecektir.</p>
    <div class="data-source-error" data-source-error hidden></div>
    <div class="data-source-buttons"><button type="button" data-source-close>Vazgeç</button>
      <button type="button" class="danger" data-source-confirm-delete="${sourceId}">Evet, Kaynağı Sil</button></div></div>`;
  overlay.querySelector("[data-source-confirm-delete]").addEventListener("click", async event => {
    const button = event.currentTarget;
    const error = body.querySelector("[data-source-error]");
    button.disabled = true;
    try {
      await api.del(`/api/data-sources/${sourceId}`);
      dataSourceModalClose();
      ui.toast("Veri kaynağı ve yalnızca ona bağlı ikincil kayıtlar kaldırıldı.");
      document.dispatchEvent(new CustomEvent("data-source-changed"));
    } catch (requestError) {
      error.textContent = requestError.userMessage || requestError.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
}

document.addEventListener("click", event => {
  const upload = event.target.closest("[data-source-upload]");
  if (upload) { event.preventDefault(); dataSourceUploadModal(upload.dataset.sourceUpload); return; }
  const manager = event.target.closest("[data-source-manager]");
  if (manager) { event.preventDefault(); uploadedSourceManager(); return; }
  const detail = event.target.closest("[data-source-detail]");
  if (detail) { event.preventDefault(); dataSourceDetail(detail.dataset.sourceDetail); return; }
  const remove = event.target.closest("[data-source-delete]");
  if (remove) { event.preventDefault(); dataSourceDelete(remove.dataset.sourceDelete); }
});

document.addEventListener("data-source-changed", () => {
  document.querySelectorAll("[data-source-metrics]").forEach(element => {
    const keys = (element.dataset.sourceMetrics || "").split(",").filter(Boolean);
    dataSourceGroupLoad(element.id, keys, { view: element.dataset.sourceView || "full" });
  });
});
