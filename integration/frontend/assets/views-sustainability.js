// Program Sürdürülebilirliği ekranı.
//
// TASARIM İLKESİ — aşamalı gösterim:
//   1. Özet          → seçilen programın tek bakışta durumu
//   2. Seçim         → fakülte › bölüm › program
//   3. Sonuç         → ana kriterler, üç grupta
//   4. Ayrıntılar    → eksik kriterler, destekleyici ölçümler
//   5. Yöntem        → ağırlık tablosu ve veri kaynakları (kapalı)
//
// Sayfa ilk açıldığında 14 programın tamamı ve 11 satırlık ağırlık tablosu
// GÖSTERİLMEZ. Kullanıcı seçim yapıp "Sonuçları Göster" düğmesine basar.
// Böylece hem ekran sadeleşir hem de sayfa açılışında ağır hesaplama tetiklenmez.

// Veri tamlığı bu eşiğin altındaysa kesin kategori verilmez.
// Sekiz kriterin verisi yokken "yeniden yapılandırılmalı" demek, ölçülmemiş
// bir programı haksız yere başarısız ilan etmek olurdu.
const SUSTAINABILITY_PRELIMINARY_THRESHOLD = 60;

// Kategori adlarının yönetici diline çevrilmiş hâli ve ne anlama geldiği.
const SUSTAINABILITY_CATEGORY_INFO = {
  "Yeniden yapılandırılması gereken program": {
    label: "Yeniden yapılandırma gerekli",
    kind: "critical",
    meaning:
      "Programın talep, performans veya kaynak göstergelerinde önemli iyileştirme " +
      "ihtiyacı bulunmaktadır.",
  },
  "Güçlendirilmesi gereken program": {
    label: "Güçlendirme gerekli",
    kind: "warning",
    meaning:
      "Program ayakta ancak bazı göstergelerde hedefin gerisinde; hedefli " +
      "destekle iyileştirilebilir.",
  },
  "Sürdürülebilir program": {
    label: "Sürdürülebilir",
    kind: "good",
    meaning: "Program talep, performans ve kaynak açısından sağlıklı görünüyor.",
  },
  "Öncelikli yatırım yapılacak program": {
    label: "Öncelikli yatırım adayı",
    kind: "good",
    meaning: "Program güçlü performans gösteriyor; büyüme yatırımı için uygun.",
  },
};

function sustainabilityCategoryInfo(category) {
  return (
    SUSTAINABILITY_CATEGORY_INFO[category] || {
      label: category || "Değerlendirilmedi",
      kind: "nodata",
      meaning: "Bu kategori için açıklama tanımlanmamış.",
    }
  );
}

VIEWS["sustainability"] = {
  title: "Program Sürdürülebilirliği",
  subtitle:
    "Programların öğrenci talebi, doluluk, mezuniyet, mali durum ve " +
    "kurumsal katkı açısından değerlendirilmesi",
  html: () => `
    <div class="card">
      <h3>Değerlendirilecek programı seçin</h3>
      <div class="note">
        Fakülte seçtikten sonra bölüm, bölüm seçtikten sonra program
        seçebilirsiniz. Tek bir programı veya bir bölümün/fakültenin tamamını
        değerlendirebilirsiniz.
      </div>
      <div id="susFilter"></div>
    </div>

    <div id="susResult">
      ${ui.empty(
        "Yukarıdan bir kapsam seçip “Sonuçları Göster” düğmesine basın."
      )}
    </div>

    <div id="susMethod"></div>`,

  async init() {
    // Sayfa açılışında yalnızca dönem listesi ve fakülteler çekilir.
    // Program skorları ağır hesaplamadır; kullanıcı istemeden çalıştırılmaz.
    const years = await api
      .get("/api/academic-success/academic-years")
      .catch(() => [CURRENT_YEAR]);

    SUS_FILTER = new OrgFilter("susFilter", {
      withYear: true,
      years,
      defaultYear: years.includes(CURRENT_YEAR) ? CURRENT_YEAR : years[years.length - 1],
      level: "program",
      onApply: (scope) => runSustainability(scope),
    });
    await SUS_FILTER.render();

    // Hesaplama yöntemi bölümü sayfanın en altında ve KAPALI durur.
    renderSustainabilityMethod();
  },
};

let SUS_FILTER = null;
let SUS_WEIGHTS = null;

/** Ağırlık yapılandırmasını bir kez okur; her seçimde tekrar çekmez. */
async function sustainabilityWeights() {
  if (!SUS_WEIGHTS) SUS_WEIGHTS = await api.get("/api/program-sustainability/weights");
  return SUS_WEIGHTS;
}

/** Teknik kriter anahtarını kullanıcıya gösterilecek Türkçe ada çevirir. */
function criterionLabel(key, weights) {
  return (weights.criterion_labels && weights.criterion_labels[key]) || key;
}

function criterionDescription(key, weights) {
  return (weights.criterion_descriptions && weights.criterion_descriptions[key]) || "";
}

function criterionSource(key, weights) {
  return (weights.criterion_sources && weights.criterion_sources[key]) || "—";
}

async function runSustainability(scope) {
  const box = document.getElementById("susResult");
  // Filtre değişince eski sonuç hemen temizlenir; kullanıcı bayat veriye bakmasın.
  box.innerHTML = ux.skeleton(4);

  try {
    const weights = await sustainabilityWeights();
    const programs = await ref.programs();

    // Tek program seçildiyse yalnızca o programı hesaplat (çok daha hızlı).
    let rows;
    if (scope.programId) {
      const program = programs.find((p) => p.id === scope.programId);
      const single = await api.get(
        `/api/program-sustainability/scores/${encodeURIComponent(program.code)}`,
        { academic_year: scope.year }
      );
      rows = [single];
    } else {
      const all = await api.get("/api/program-sustainability/scores", {
        academic_year: scope.year,
      });
      // Kapsam daraltması program kodları üzerinden yapılır.
      const allowed = new Set(
        programs
          .filter((p) => {
            if (scope.departmentId) return p.department_id === scope.departmentId;
            if (scope.facultyId) {
              const department = (SUS_DEPARTMENTS || []).find(
                (d) => d.id === p.department_id
              );
              return department && department.faculty_id === scope.facultyId;
            }
            return true;
          })
          .map((p) => p.code)
      );
      rows = all.filter((r) => allowed.has(r.program_code));
    }

    if (!rows.length) {
      box.innerHTML = ui.empty(
        "Seçilen kapsamda değerlendirilebilecek program bulunamadı. " +
          "Farklı bir fakülte veya bölüm seçmeyi deneyin."
      );
      return;
    }

    box.innerHTML =
      rows.length === 1
        ? renderSustainabilityProgram(rows[0], weights, programs)
        : renderSustainabilityList(rows, weights, programs);

    bindSustainabilityInteractions(box, rows, weights, programs);
  } catch (err) {
    box.innerHTML = ui.error(err);
  }
}

// Bölüm listesi fakülte filtresi için gerekli; bir kez alınıp saklanır.
let SUS_DEPARTMENTS = null;
ref.departments().then((rows) => (SUS_DEPARTMENTS = rows)).catch(() => {});

/* ------------------------------------------------------------------ */
/* Tek program görünümü                                                */
/* ------------------------------------------------------------------ */

function renderSustainabilityProgram(row, weights, programs) {
  const program = programs.find((p) => p.code === row.program_code);
  const completeness = Number(row.data_completeness_percent);
  const isPreliminary = completeness < SUSTAINABILITY_PRELIMINARY_THRESHOLD;
  const info = sustainabilityCategoryInfo(row.category);

  // Veri tamlığı düşükse kesin kategori verilmez.
  const categoryBadge = isPreliminary
    ? ux.statusBadge(
        "nodata",
        "Ön değerlendirme — veri eksik",
        `Değerlendirme kriterlerinin yalnızca %${fmt.dec(completeness, 0)}'i için veri ` +
          "bulunduğundan kesin kategori verilmemiştir."
      )
    : ux.statusBadge(info.kind, info.label, info.meaning);

  const reliability =
    completeness >= 80 ? ["good", "Yüksek"]
    : completeness >= 60 ? ["warning", "Orta"]
    : ["critical", "Düşük"];

  const scoreNote = isPreliminary
    ? `<span class="status-badge status-warning" title="Değerlendirme kriterlerinin yalnızca %${fmt.dec(
        completeness, 0
      )}'i için veri bulunmaktadır."><span class="status-icon">⚠</span>Sonuç sınırlı veriye dayanmaktadır</span>`
    : "";

  return `
    <div class="card">
      <h3>${fmt.esc(programTitle(program, row))}</h3>
      <div class="note">${fmt.esc(programSubtitle(program, row))}</div>

      <div class="grid cols-3-2" style="margin-top:14px">
        <div>
          ${ux.scoreBlock(row.sustainability_score, 100, "Genel değerlendirme", scoreNote)}
        </div>
        <div class="kv">
          ${kv("Durum", categoryBadge)}
          ${kv("Veri güvenilirliği", ux.statusBadge(reliability[0], reliability[1]))}
          ${kv("Kullanılabilir veri", fmt.pct(completeness, 0))}
          ${kv("Değerlendirme dönemi", fmt.esc(row.academic_year))}
        </div>
      </div>

      <div class="state ${isPreliminary ? "warn" : "empty"}">
        <b>${isPreliminary ? "Bu bir ön değerlendirmedir" : info.label}</b>
        <div class="msg">${fmt.esc(
          isPreliminary
            ? `Programın ${row.missing_criteria.length} kriteri için henüz ölçüm bulunmuyor. ` +
              "Eksik veriler tamamlandığında sonuç değişebilir; bu puan kesin bir " +
              "başarısızlık göstergesi değildir."
            : info.meaning
        )}</div>
      </div>
    </div>

    ${renderCriteriaGroups(row, weights)}

    ${renderMissingCriteria(row, weights)}

    ${ux.details(
      "Kullanılan veriler",
      renderSupportingMetrics(row),
      { hint: "Puanın dayandığı ham ölçümler" }
    )}`;
}

function programTitle(program, row) {
  // Program kodu başlık DEĞİLDİR; ikincil bilgi olarak altta gösterilir.
  if (!program) return row.program_name;
  const name = program.name || row.program_name;
  return name.replace(/\s*(Bachelor's|Master's|PhD)\s*Program\s*$/i, "").trim();
}

function programSubtitle(program, row) {
  const level = program
    ? { Bachelor: "Lisans Programı", Master: "Yüksek Lisans Programı", PhD: "Doktora Programı" }[
        program.degree_level
      ] || "Program"
    : "Program";
  return `${level} · Kod: ${row.program_code}`;
}

/* ------------------------------------------------------------------ */
/* Kriterler — üç grupta                                               */
/* ------------------------------------------------------------------ */

function renderCriteriaGroups(row, weights) {
  const byKey = Object.fromEntries((row.criteria || []).map((c) => [c.name, c]));
  const groups = weights.criterion_groups || {};

  const groupHtml = Object.entries(groups)
    .map(([groupName, keys]) => {
      const rows = keys
        .map((key) => {
          const criterion = byKey[key];
          const label = criterionLabel(key, weights);
          const description = criterionDescription(key, weights);
          const available = criterion && criterion.available;
          const score = available ? Number(criterion.score) : null;

          // Verisi olmayan kriterde 0 YAZILMAZ. Sıfır "ölçtük, kötü çıktı"
          // demektir; burada ölçüm hiç yapılmamıştır.
          const valueCell = available
            ? `<div class="criterion-value">${fmt.dec(score, 0)}<span class="muted"> / 100</span></div>`
            : `<div class="criterion-value is-missing">Veri bulunamadı</div>`;

          const color =
            score === null ? "rgba(127,127,127,0.3)"
            : score >= 75 ? "#0ca30c"
            : score >= 50 ? "var(--accent, #e08c00)"
            : "var(--critical, #c0392b)";

          return `<div class="criterion${available ? "" : " is-missing"}">
            <div class="criterion-name">${fmt.esc(label)}<small>${fmt.esc(description)}</small></div>
            <div class="criterion-track">
              <div class="criterion-fill" style="width:${score === null ? 0 : score}%;background:${color}"></div>
            </div>
            ${valueCell}
          </div>`;
        })
        .join("");

      return `<div class="card">
        <h3>${fmt.esc(groupName)}</h3>
        ${rows}
      </div>`;
    })
    .join("");

  return `<div class="grid cols-2">${groupHtml}</div>`;
}

/* ------------------------------------------------------------------ */
/* Eksik kriterler — tek satır özet + açılır detay                     */
/* ------------------------------------------------------------------ */

function renderMissingCriteria(row, weights) {
  const missing = row.missing_criteria || [];
  if (!missing.length) {
    return `<div class="card"><h3>Veri durumu</h3>
      ${ui.empty("Tüm değerlendirme kriterleri için ölçüm bulunuyor.")}</div>`;
  }

  const list = missing
    .map((key) => {
      const weight = (weights.weights || {})[key];
      return `<li>
        <b>${fmt.esc(criterionLabel(key, weights))}</b>
        <span class="muted"> · ağırlık %${fmt.dec(weight ?? 0, 0)}</span>
        <div class="note">${fmt.esc(criterionDescription(key, weights))}</div>
        <div class="note muted">Beklenen kaynak: ${fmt.esc(criterionSource(key, weights))}</div>
      </li>`;
    })
    .join("");

  return `<div class="card">
    <h3>Veri durumu</h3>
    <div class="note">
      ${ux.statusBadge("warning", `${missing.length} kriter için veri eksik`)}
      Eksik kriterler puana dahil edilmez; sıfır olarak sayılmaz.
    </div>
    ${ux.details("Detayları göster", `<ul class="plain">${list}</ul>`, {
      hint: "Hangi kriterlerin verisi bekleniyor",
    })}
  </div>`;
}

function renderSupportingMetrics(row) {
  const metrics = row.supporting_metrics || {};
  const labels = {
    quota: ["Kontenjan", (v) => fmt.int(v)],
    enrolled_student_count: ["Yerleşen öğrenci", (v) => fmt.int(v)],
    occupancy_rate: ["Kontenjan doluluğu", (v) => fmt.pct(v)],
    graduation_rate: ["Mezuniyet oranı", (v) => fmt.pct(v)],
    attrition_rate: ["Öğrenci kaybı oranı", (v) => fmt.pct(v)],
    total_students: ["Toplam öğrenci", (v) => fmt.int(v)],
    minimum_admission_score: ["Taban puan", (v) => fmt.dec(v, 1)],
    national_score_gap: ["Türkiye ortalamasından fark", (v) => fmt.dec(v, 1) + " puan"],
  };
  const rows = Object.entries(metrics)
    .filter(([key]) => labels[key])
    .map(([key, value]) => kv(labels[key][0], labels[key][1](value)));
  return rows.length
    ? `<div class="kv">${rows.join("")}</div>`
    : ui.empty("Destekleyici ölçüm bulunamadı.");
}

/* ------------------------------------------------------------------ */
/* Çoklu program görünümü (bölüm / fakülte / üniversite kapsamı)       */
/* ------------------------------------------------------------------ */

function renderSustainabilityList(rows, weights, programs) {
  const sorted = [...rows].sort(
    (a, b) => Number(a.sustainability_score) - Number(b.sustainability_score)
  );

  const preliminary = sorted.filter(
    (r) => Number(r.data_completeness_percent) < SUSTAINABILITY_PRELIMINARY_THRESHOLD
  ).length;

  const summary = `
    <div class="summary-strip">
      <div class="summary-item">
        <div class="label">Değerlendirilen program</div>
        <div class="value">${sorted.length}</div>
        <div class="sub">${fmt.esc(sorted[0].academic_year)} dönemi</div>
      </div>
      <div class="summary-item is-critical">
        <div class="label">En düşük puan</div>
        <div class="value">${fmt.dec(sorted[0].sustainability_score, 0)}<span class="muted"> / 100</span></div>
        <div class="sub">${fmt.esc(programTitle(programs.find((p) => p.code === sorted[0].program_code), sorted[0]))}</div>
      </div>
      <div class="summary-item is-good">
        <div class="label">En yüksek puan</div>
        <div class="value">${fmt.dec(sorted[sorted.length - 1].sustainability_score, 0)}<span class="muted"> / 100</span></div>
        <div class="sub">${fmt.esc(programTitle(programs.find((p) => p.code === sorted[sorted.length - 1].program_code), sorted[sorted.length - 1]))}</div>
      </div>
      <div class="summary-item ${preliminary ? "is-warning" : "is-good"}">
        <div class="label">Veri yeterliliği</div>
        <div class="value">${sorted.length - preliminary} / ${sorted.length}</div>
        <div class="sub">${preliminary ? `${preliminary} program ön değerlendirme` : "tümü değerlendirilebilir"}</div>
      </div>
    </div>`;

  const body = sorted
    .map((r, index) => {
      const program = programs.find((p) => p.code === r.program_code);
      const completeness = Number(r.data_completeness_percent);
      const isPreliminary = completeness < SUSTAINABILITY_PRELIMINARY_THRESHOLD;
      const info = sustainabilityCategoryInfo(r.category);
      const score = Number(r.sustainability_score);
      const kind = isPreliminary ? "nodata" : info.kind;

      return `<tr class="expandable" data-index="${index}">
        <td><b>${fmt.esc(programTitle(program, r))}</b>
            <br><span class="muted">${fmt.esc(programSubtitle(program, r))}</span></td>
        <td><b>${fmt.dec(score, 0)}</b><span class="muted"> / 100</span></td>
        <td>${
          isPreliminary
            ? ux.statusBadge("nodata", "Ön değerlendirme",
                `Kriterlerin yalnızca %${fmt.dec(completeness, 0)}'i ölçülmüş.`)
            : ux.statusBadge(info.kind, info.label, info.meaning)
        }</td>
        <td>${fmt.pct(completeness, 0)}</td>
        <td class="muted">${r.missing_criteria.length ? r.missing_criteria.length + " kriter eksik" : "tam"}</td>
      </tr>`;
    })
    .join("");

  return (
    summary +
    `<div class="card">
      <h3>Program karnesi</h3>
      <div class="note">
        En düşük puandan başlayarak sıralanmıştır. Bir satıra tıklayarak
        kriter kırılımını açabilirsiniz.
      </div>
      <div class="table-wrap"><table>
        <thead><tr>
          <th>Program</th><th>Puan</th><th>Durum</th>
          <th>Veri tamlığı</th><th>Eksik kriter</th>
        </tr></thead>
        <tbody>${body}</tbody>
      </table></div>
    </div>
    <div id="susDetail"></div>`
  );
}

function bindSustainabilityInteractions(box, rows, weights, programs) {
  const sorted = [...rows].sort(
    (a, b) => Number(a.sustainability_score) - Number(b.sustainability_score)
  );
  box.querySelectorAll("tr.expandable").forEach((tr) => {
    tr.addEventListener("click", () => {
      const row = sorted[Number(tr.dataset.index)];
      const target = document.getElementById("susDetail");
      target.innerHTML = renderSustainabilityProgram(row, weights, programs);
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

/* ------------------------------------------------------------------ */
/* Hesaplama yöntemi — sayfanın altında, KAPALI                        */
/* ------------------------------------------------------------------ */

async function renderSustainabilityMethod() {
  const box = document.getElementById("susMethod");
  try {
    const weights = await sustainabilityWeights();
    const rows = Object.entries(weights.weights || {})
      .sort((a, b) => b[1] - a[1])
      .map(([key, weight]) => [
        `<b>${fmt.esc(criterionLabel(key, weights))}</b>`,
        `%${fmt.dec(weight, 0)}`,
        fmt.esc(criterionDescription(key, weights)),
        `<span class="muted">${fmt.esc(criterionSource(key, weights))}</span>`,
      ]);

    box.innerHTML = ux.details(
      "Hesaplama yöntemi ve değerlendirme ağırlıkları",
      `<p class="note">
         Her kriter 0–100 arasında puanlanır ve ağırlığıyla çarpılarak genel
         puana katkı verir. <b>Ölçümü bulunmayan kriterler hesaba katılmaz</b>;
         sıfır puan olarak sayılmaz. Bu yüzden veri tamlığı düşük olan
         programların puanı sınırlı sayıda kriterden gelir ve kesin sonuç
         olarak yorumlanmamalıdır.
       </p>` +
        table(["Kriter", "Ağırlık", "Ne ölçer", "Veri kaynağı"], rows) +
        `<p class="note muted">Ağırlıklar toplamı: %${fmt.dec(weights.total_weight, 0)}</p>`,
      { hint: `${rows.length} kriter` }
    );
  } catch (err) {
    box.innerHTML = "";
  }
}
