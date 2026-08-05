// Sistem ekranları: Üniversite Yapısı (M1), Veri Aktarımı (M13),
// Kullanıcı ve Yetki (M14).

/* ==================================================================
   Üniversite Yapısı — Modül 1 (Habib)
   ================================================================== */

VIEWS["structure"] = {
  title: "Üniversite Yapısı",
  subtitle: "Fakülte, bölüm, program ve idari birim yönetimi · Modül 1",
  html: () => `
    <div id="structTiles"></div>

    <div class="card">
      <h3>Yeni kayıt ekle</h3>
      <div class="note">
        Kod alanı kurum genelinde tekildir; aynı kodla ikinci kayıt
        oluşturulmaya çalışılırsa sunucu 409 döndürür.
      </div>
      <div class="filters">
        <label class="f">Kayıt türü <select id="structType">
          <option value="faculties">Fakülte</option>
          <option value="departments">Bölüm</option>
          <option value="programs">Akademik program</option>
          <option value="administrative-units">İdari birim</option>
        </select></label>
      </div>
      <div class="form-grid" id="structForm"></div>
      <div class="form-actions">
        <button class="primary" id="structSave">Kaydet</button>
      </div>
    </div>

    <div class="grid cols-2">
      <div class="card">
        <h3>Fakülteler ve bölümleri</h3>
        <div id="structTree"></div>
      </div>
      <div class="card">
        <h3>Akademik programlar</h3>
        <div id="structPrograms"></div>
      </div>
    </div>

    <div class="card">
      <h3>İdari birimler</h3>
      <div id="structUnits"></div>
    </div>`,

  async init() {
    document.getElementById("structType").addEventListener("change", renderStructureForm);
    renderStructureForm();
    document.getElementById("structSave").addEventListener("click", saveStructureRecord);
    refreshStructure();
  },
};

async function renderStructureForm() {
  const type = document.getElementById("structType").value;
  const box = document.getElementById("structForm");

  // Kullanıcı kimlik numarası yazmak zorunda kalmasın diye üst kayıtlar
  // açılır listede isimleriyle sunuluyor.
  let parentField = "";
  if (type === "departments") {
    const faculties = await ref.faculties();
    parentField = `<label class="f">Bağlı fakülte <select data-key="faculty_id">
      ${optionsHtml(faculties)}</select></label>`;
  } else if (type === "programs") {
    const departments = await ref.departments();
    parentField = `<label class="f">Bağlı bölüm <select data-key="department_id">
      ${optionsHtml(departments)}</select></label>`;
  }

  const extra =
    type === "programs"
      ? `<label class="f">Derece <select data-key="degree_level">
           <option>Bachelor</option><option>Master</option><option>PhD</option></select></label>
         <label class="f">Süre (yıl) <input type="number" data-key="duration_years" value="4" min="1" max="8"></label>
         <label class="f">Kontenjan <input type="number" data-key="quota" value="60" min="1" max="2000"></label>`
      : "";

  box.innerHTML = `
    <label class="f">Kod <input data-key="code" placeholder="Örn: EEE" maxlength="50"></label>
    <label class="f">Ad <input data-key="name" placeholder="Örn: Elektrik-Elektronik Mühendisliği"></label>
    ${parentField}
    ${extra}
    <label class="f wide">Açıklama <input data-key="description" placeholder="İsteğe bağlı"></label>`;
}

async function saveStructureRecord() {
  const type = document.getElementById("structType").value;
  const payload = {};
  document.querySelectorAll("#structForm [data-key]").forEach((i) => {
    const v = i.value.trim();
    if (v === "") return;
    payload[i.dataset.key] = i.type === "number" || i.dataset.key.endsWith("_id") ? Number(v) : v;
  });

  const btn = document.getElementById("structSave");
  btn.disabled = true;
  try {
    await api.post(`/api/${type}`, payload);
    ui.toast("Kayıt oluşturuldu.", "success");
    ref.clear();
    renderStructureForm();
    refreshStructure();
  } catch (err) {
    // Sunucunun sebebini olduğu gibi gösteriyoruz; "bir hata oluştu" demiyoruz.
    ui.toast(err.userMessage, "error");
  } finally {
    btn.disabled = false;
  }
}

function refreshStructure() {
  ref.clear();

  load(
    "structTiles",
    async () => {
      const [f, d, p, u] = await Promise.all([
        api.get("/api/faculties", { limit: 200 }),
        api.get("/api/departments", { limit: 200 }),
        api.get("/api/programs", { limit: 200 }),
        api.get("/api/administrative-units", { limit: 200 }),
      ]);
      return { f, d, p, u };
    },
    ({ f, d, p, u }, el) => {
      el.className = "tiles";
      el.innerHTML = tileHtml([
        ["Fakülte", fmt.int(f.length)],
        ["Bölüm", fmt.int(d.length)],
        ["Akademik program", fmt.int(p.length)],
        ["İdari birim", fmt.int(u.length)],
        ["Toplam kontenjan", fmt.int(p.reduce((a, x) => a + (x.quota || 0), 0))],
        ["Lisansüstü program", fmt.int(p.filter((x) => x.degree_level !== "Bachelor").length)],
      ]);
    }
  );

  load(
    "structTree",
    async () => {
      const [faculties, departments] = await Promise.all([
        api.get("/api/faculties", { limit: 200 }),
        api.get("/api/departments", { limit: 200 }),
      ]);
      return { faculties, departments };
    },
    ({ faculties, departments }, el) => {
      el.innerHTML = faculties
        .map((f) => {
          const kids = departments.filter((d) => d.faculty_id === f.id);
          return `<div class="tree-group">
            <div class="tree-head"><b>${fmt.esc(f.name)}</b>
              <code>${fmt.esc(f.code)}</code>
              <span class="push muted">${kids.length} bölüm</span></div>
            ${
              kids.length
                ? `<ul class="plain">${kids
                    .map(
                      (d) =>
                        `<li>${fmt.esc(d.name)} <code>${fmt.esc(d.code)}</code>
                          ${d.is_active ? "" : chip("neutral", "pasif")}</li>`
                    )
                    .join("")}</ul>`
                : `<div class="note">Bu fakülteye bağlı bölüm yok.</div>`
            }
          </div>`;
        })
        .join("");
    }
  );

  load(
    "structPrograms",
    async () => {
      const [programs, departments] = await Promise.all([
        api.get("/api/programs", { limit: 200 }),
        api.get("/api/departments", { limit: 200 }),
      ]);
      return { programs, departments };
    },
    ({ programs, departments }, el) => {
      const byId = new Map(departments.map((d) => [d.id, d]));
      el.innerHTML = table(
        ["Kod", "Program", "Bölüm", "Derece", "Süre", "Kontenjan"],
        programs.map((p) => [
          `<code>${fmt.esc(p.code)}</code>`,
          fmt.esc(p.name),
          fmt.esc(byId.get(p.department_id)?.name || "—"),
          fmt.esc(p.degree_level),
          fmt.int(p.duration_years) + " yıl",
          fmt.int(p.quota),
        ])
      );
    }
  );

  load(
    "structUnits",
    () => api.get("/api/administrative-units", { limit: 200 }),
    (rows, el) => {
      el.innerHTML = table(
        ["Kod", "Birim", "Açıklama", "Durum"],
        rows.map((r) => [
          `<code>${fmt.esc(r.code)}</code>`,
          fmt.esc(r.name),
          fmt.esc(r.description || "—"),
          chip(r.is_active ? "good" : "neutral", r.is_active ? "aktif" : "pasif"),
        ])
      );
    }
  );
}

/* ==================================================================
   Veri Aktarımı — Modül 13 (Habib)
   ================================================================== */

VIEWS["data-import"] = {
  title: "Veri Aktarımı",
  subtitle: "CSV / Excel / JSON toplu veri yükleme",
  html: () => `
    <div class="grid cols-3-2">
      <div class="card">
        <h3>Dosya yükle</h3>
        <div class="note">
          <b>Önizleme</b> modunda hiçbir kayıt veritabanına yazılmaz; dosya
          yalnızca doğrulanır. Sonuç uygunsa "Gerçekten aktar" ile yazabilirsiniz.
        </div>

        <label class="f">Kaynak türü <select id="impResource"></select></label>
        <label class="f">Dosya <input type="file" id="impFile" accept=".csv,.xlsx,.json"></label>

        <div class="form-actions">
          <button class="ghost" id="impTemplate">Şablon indir</button>
          <button class="primary" id="impPreview">Önizle (yazmadan)</button>
          <button class="ghost" id="impCommit" disabled>Gerçekten aktar</button>
        </div>
      </div>

      <div class="card">
        <h3>Beklenen alanlar</h3>
        <div class="note">Seçilen kaynak türünün zorunlu ve isteğe bağlı sütunları.</div>
        <div id="impFields"></div>
      </div>
    </div>

    <div class="card">
      <h3>Sonuç raporu</h3>
      <div id="impResult">${ui.empty("Henüz dosya yüklenmedi.")}</div>
    </div>

    <div class="card">
      <h3>Aktarım geçmişi</h3>
      <div id="impHistory"></div>
    </div>`,

  async init() {
    const info = await api.get("/api/data-integration/resources");
    const sel = document.getElementById("impResource");
    sel.innerHTML = info.resource_types
      .map((r) => {
        const value = typeof r === "string" ? r : r.resource_type;
        const label = typeof r === "string" ? r : r.label || r.resource_type;
        return `<option value="${fmt.esc(value)}">${fmt.esc(label)}</option>`;
      })
      .join("");
    sel.addEventListener("change", showImportFields);
    showImportFields();

    document.getElementById("impTemplate").addEventListener("click", () => {
      // Şablon indirmesi tarayıcının kendi indirme akışını kullanır.
      window.location.href = `/api/data-integration/templates/${sel.value}`;
    });
    document.getElementById("impPreview").addEventListener("click", () => runImport(true));
    document.getElementById("impCommit").addEventListener("click", () => runImport(false));

    refreshImportHistory();
  },
};

async function showImportFields() {
  const resource = document.getElementById("impResource").value;
  await load(
    "impFields",
    async () => {
      // Beklenen sütunlar için ayrı bir endpoint yok; sunucunun ürettiği CSV
      // şablonunun başlık satırı tek doğruluk kaynağı. Alan listesini elle
      // yazmak, şablon değiştiğinde arayüzün yanlış bilgi vermesine yol açardı.
      const response = await fetch(`/api/data-integration/templates/${resource}`);
      if (!response.ok) throw new ApiError(response.status, "Şablon alınamadı.", resource);
      const text = await response.text();
      const lines = text.trim().split(/\r?\n/);
      return { headers: (lines[0] || "").split(","), sample: lines[1] || "" };
    },
    ({ headers, sample }, el) => {
      // Şablonda örnek satır varsa değerleri de gösteriyoruz; yoksa boş bir
      // sütun basmak yerine tabloyu tek sütuna indiriyoruz.
      const sampleValues = sample ? sample.split(",") : null;
      el.innerHTML =
        `<div class="note">${headers.length} sütun bekleniyor:</div>` +
        (sampleValues
          ? table(
              ["Sütun", "Örnek değer"],
              headers.map((h, i) => [
                `<code>${fmt.esc(h)}</code>`,
                `<span class="muted">${fmt.esc(sampleValues[i] || "")}</span>`,
              ])
            )
          : table(["Sütun"], headers.map((h) => [`<code>${fmt.esc(h)}</code>`]))) +
        `<div class="note">
           Sütun adları ve sıraları sunucunun ürettiği şablondan okunur; arayüzde
           ayrıca yazılmaz. Fazladan sütunlar yok sayılır, eksik zorunlu sütun
           satır hatası üretir.
         </div>`;
    }
  );
}

async function runImport(previewOnly) {
  const resource = document.getElementById("impResource").value;
  const fileInput = document.getElementById("impFile");
  if (!fileInput.files.length) {
    ui.toast("Önce bir dosya seçin.", "error");
    return;
  }

  const form = new FormData();
  form.append("file", fileInput.files[0]);
  form.append("preview", previewOnly ? "true" : "false");

  const box = document.getElementById("impResult");
  box.innerHTML = ui.loading(previewOnly ? "Dosya doğrulanıyor…" : "Kayıtlar aktarılıyor…");

  try {
    const r = await api.upload(`/api/data-integration/import/${resource}?preview=${previewOnly}`, form);
    const errors = r.errors || r.row_errors || [];
    const okCount = r.created_count ?? r.success_count ?? 0;

    box.innerHTML = `
      <div class="tiles">
        ${tileHtml([
          ["Mod", previewOnly ? "Önizleme" : "Aktarım"],
          ["Okunan satır", fmt.int(r.total_rows ?? r.row_count)],
          ["Geçerli", fmt.int(okCount)],
          ["Güncellenen", fmt.int(r.updated_count ?? 0)],
          ["Hatalı satır", fmt.int(errors.length)],
        ])}
      </div>
      ${
        errors.length
          ? `<h4>Satır bazlı hatalar</h4>` +
            table(
              ["Satır", "Alan", "Hata"],
              errors.map((e) => [
                fmt.int(e.row_number ?? e.row),
                `<code>${fmt.esc(e.field || "—")}</code>`,
                fmt.esc(e.message || e.error),
              ])
            )
          : `<div class="state empty">Hiçbir satırda hata bulunmadı.</div>`
      }
      <div class="note">${
        previewOnly
          ? "Bu bir önizlemedir; veritabanına <b>hiçbir kayıt yazılmadı</b>."
          : "Kayıtlar veritabanına yazıldı."
      }</div>`;

    // Hatasız önizlemeden sonra gerçek aktarım açılır.
    document.getElementById("impCommit").disabled = !previewOnly || errors.length > 0;
    if (!previewOnly) {
      ui.toast(`${okCount} kayıt aktarıldı.`, "success");
      refreshImportHistory();
    }
  } catch (err) {
    box.innerHTML = ui.error(err);
    document.getElementById("impCommit").disabled = true;
  }
}

function refreshImportHistory() {
  load(
    "impHistory",
    () => api.get("/api/data-integration/jobs", { limit: 20 }),
    (rows, el) => {
      const list = Array.isArray(rows) ? rows : rows.jobs || [];
      if (!list.length) return void (el.innerHTML = ui.empty("Henüz aktarım yapılmadı."));
      el.innerHTML = table(
        ["Tarih", "Kaynak", "Dosya", "Mod", "Toplam", "Başarılı", "Hatalı", "Durum"],
        list.map((j) => [
          fmt.esc((j.created_at || "").slice(0, 19).replace("T", " ")),
          fmt.esc(j.resource_type),
          fmt.esc(j.file_name || "—"),
          j.is_preview ? chip("info", "önizleme") : chip("good", "aktarım"),
          fmt.int(j.total_rows),
          fmt.int(j.success_count ?? j.created_count),
          fmt.int(j.error_count),
          chip(j.status === "completed" || j.status === "success" ? "good" : "warning", j.status),
        ])
      );
    }
  );
}

/* ==================================================================
   Kullanıcı ve Yetki — Modül 14 (Eda)
   ================================================================== */

VIEWS["users"] = {
  title: "Kullanıcı ve Yetki Yönetimi",
  subtitle: "Rol tabanlı erişim denetimi",
  html: () => `
    <div class="state empty">
      <b>Güvenlik notu:</b> Parolalar veritabanında düz metin olarak saklanmaz.
      PBKDF2-HMAC-SHA256 ile saltlanıp özetlenir ve hiçbir API cevabında yer almaz.
    </div>

    <div class="card">
      <h3>Tanımlı roller</h3>
      <div id="usrRoles"></div>
    </div>

    <div class="card">
      <h3>Yeni kullanıcı</h3>
      <div id="usrFormBox"></div>
    </div>

    <div class="card">
      <h3>Kullanıcılar</h3>
      <div id="usrList"></div>
    </div>`,

  async init() {
    load(
      "usrRoles",
      () => api.get("/api/auth/roles"),
      (rows, el) => {
        el.innerHTML = table(
          ["Rol", "Yetkiler", "Kapsam"],
          rows.map((r) => [
            `<b>${fmt.esc(r.role)}</b>`,
            r.permissions.map((p) => `<code>${fmt.esc(p)}</code>`).join(" "),
            fmt.esc(r.description),
          ])
        );
      }
    );

    // Kullanıcı yönetimi yalnızca yetkisi olana gösterilir.
    const box = document.getElementById("usrFormBox");
    if (!auth.can("manage_users")) {
      box.innerHTML = ui.empty(
        "Kullanıcı oluşturma yetkiniz yok (manage_users). Bu bölüm yalnızca Admin rolüne açıktır."
      );
    } else {
      const [faculties, departments, roles] = await Promise.all([
        ref.faculties(),
        ref.departments(),
        api.get("/api/auth/roles"),
      ]);
      box.innerHTML = `
        <div class="form-grid">
          <label class="f">Kullanıcı adı <input id="usrName" placeholder="ornek.kullanici"></label>
          <label class="f">Ad Soyad <input id="usrFull" placeholder="Ad Soyad"></label>
          <label class="f">Parola <input id="usrPass" type="password" placeholder="en az 4 karakter"></label>
          <label class="f">Rol <select id="usrRole">
            ${roles.map((r) => `<option>${fmt.esc(r.role)}</option>`).join("")}</select></label>
          <label class="f">Fakülte kapsamı <select id="usrFaculty">
            <option value="">Yok</option>${optionsHtml(faculties)}</select></label>
          <label class="f">Bölüm kapsamı <select id="usrDept">
            <option value="">Yok</option>${optionsHtml(departments)}</select></label>
        </div>
        <div class="form-actions"><button class="primary" id="usrSave">Kullanıcı oluştur</button></div>`;

      document.getElementById("usrSave").addEventListener("click", async () => {
        const payload = {
          username: document.getElementById("usrName").value.trim(),
          full_name: document.getElementById("usrFull").value.trim(),
          password: document.getElementById("usrPass").value,
          role: document.getElementById("usrRole").value,
          faculty_id: Number(document.getElementById("usrFaculty").value) || null,
          department_id: Number(document.getElementById("usrDept").value) || null,
        };
        try {
          await api.post("/api/auth/users", payload);
          ui.toast("Kullanıcı oluşturuldu.", "success");
          refreshUsers();
        } catch (err) {
          ui.toast(err.userMessage, "error");
        }
      });
    }

    refreshUsers();
  },
};

function refreshUsers() {
  load(
    "usrList",
    () => api.get("/api/auth/users", { include_inactive: true }),
    (rows, el) => {
      const canManage = auth.can("manage_users");
      el.innerHTML = table(
        ["Kullanıcı", "Ad Soyad", "Rol", "Kapsam", "Yetkiler", "Son giriş", "Durum", ""],
        rows.map((u) => [
          `<code>${fmt.esc(u.username)}</code>`,
          fmt.esc(u.full_name),
          fmt.esc(u.role),
          fmt.esc(u.department_name || u.faculty_name || "tüm kurum"),
          u.permissions.map((p) => `<code>${fmt.esc(p)}</code>`).join(" "),
          u.last_login_at ? fmt.esc(u.last_login_at.slice(0, 16).replace("T", " ")) : fmt.empty,
          chip(u.is_active ? "good" : "neutral", u.is_active ? "aktif" : "pasif"),
          canManage && u.is_active
            ? `<button class="ghost small" data-deactivate="${u.id}">Devre dışı bırak</button>`
            : "",
        ])
      );
      el.querySelectorAll("[data-deactivate]").forEach((btn) =>
        btn.addEventListener("click", async () => {
          try {
            await api.del(`/api/auth/users/${btn.dataset.deactivate}`);
            ui.toast("Kullanıcı devre dışı bırakıldı ve açık oturumu kapatıldı.", "success");
            refreshUsers();
          } catch (err) {
            ui.toast(err.userMessage, "error");
          }
        })
      );
    }
  );
}
