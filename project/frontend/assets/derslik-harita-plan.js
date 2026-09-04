/* ==========================================================================
   SEMANTİK KAT HARİTASI — temiz plan + otomatik derslik alanları
   --------------------------------------------------------------------------
   Ekranda mimari PAFTA GÖSTERİLMEZ. Lejant, kot çizgileri, ölçülendirme,
   pafta çerçevesi ve on binlerce CAD ilkeli arayüze hiç gelmez; backend
   `build_semantic_map.py` bunları eleyip yalnızca anlamlı geometriyi
   yayınlar:

       outline    → bina sınırı
       corridors  → koridor / ortak alan (etkileşimsiz)
       rooms      → SINIF / LAB / AMFİ / STÜDYO (ETKİLEŞİMLİ)
       landmarks  → merdiven, asansör, WC (yön bulma)

   ODA POLİGONLARI OTOMATİK ÜRETİLİR. Kullanıcı poligon çizmez; yalnızca
   hazır bir odaya tıklayıp Excel derslik kodunu atar. Elle çizim
   "Gelişmiş" altında istisnai bir yedek olarak durur.
   ========================================================================== */

const DHP = {
  gelismis: false,   // manuel alan ekleme (istisnai yedek) açık mı
  arac: null,        // null | "ciz"
  taslak: [],
  imlec: null,
};

/** Mekân türü → temel renk (derslik kodu ATANMAMIŞ odalar için nötr). */
const DHP_TUR_RENK = {
  CLASSROOM: "#46536b",
  LAB: "#55506b",
  AMPHI: "#4a4f70",
  STUDIO: "#445a63",
};
const DHP_TUR_AD = {
  CLASSROOM: "Sınıf", LAB: "Laboratuvar", AMPHI: "Amfi", STUDIO: "Stüdyo",
};

function dhpKat(kat) {
  const f = DH.plan && DH.plan.floors && DH.plan.floors[String(kat)];
  return f || null;
}

/** Bu odaya atanmış eşleştirme kaydı (varsa). */
function dhpEsleme(odaId) {
  return DH.alanlar.find(a => a.area_id === odaId) || null;
}

function dhpOda(odaId) {
  const e = dhpEsleme(odaId);
  if (!e || !e.room_code || !DH.veri) return null;
  return DH.veri.rooms.find(o => o.room_code === e.room_code) || null;
}

/** Oda rengi.
 *  Derslik kodu ATANMAMIŞSA nötr gri — "boş" iddia edilmez, çünkü o
 *  odanın programı hakkında hiçbir şey bilinmiyor. */
function dhpRenk(r) {
  const oda = dhpOda(r.area_id);
  return oda ? dhRenk(oda) : (DHP_TUR_RENK[r.room_type] || "#4a5568");
}

function dhpIpucu(r) {
  const bas = [`${r.architectural_label}  ·  ${DHP_TUR_AD[r.room_type] || r.room_type}`];
  if (r.area_m2) bas.push(`Plan alanı: ${r.area_m2} m²`);
  const oda = dhpOda(r.area_id);
  if (!oda) {
    bas.push("Derslik kodu atanmamış — tıklayıp atayın");
    return bas.join("\n");
  }
  const ipuc = DH.mod ? "" : "\n\nDers programı için tıklayın";
  return bas.join("\n") + "\n\n" + dhIpucu(oda) + ipuc;
}

function dhpEtiket(r) {
  const e = dhpEsleme(r.area_id);
  if (e && e.room_code) return e.room_code;
  const m = /^(\d{1,2})\s*-/.exec(r.architectural_label);
  if (m) return m[1];
  /* Numarasız oda: mimari adın TAMAMI yazılır. Önceki sürüm ilk
     kelimeyi alıyordu; "ENDÜSTRİ LAB." haritada "ENDÜSTRİ", "FİZİK LAB."
     ise "FİZİK" görünüyor ve mekân türü kaybolmuş oluyordu. Ad, alan
     bilgisinden (" · 131.6 m²") ayrılır — alan zaten ipucunda var. */
  return r.architectural_label.split(" · ")[0];
}

const _pts = p => p.map(q => `${q[0]},${q[1]}`).join(" ");
const _orta = p => {
  const xs = p.map(q => q[0]), ys = p.map(q => q[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2,
          (Math.min(...ys) + Math.max(...ys)) / 2];
};

/* -------------------------------------------------------------------------
   HARİTA
   ------------------------------------------------------------------------- */
function dhpPlanGovdesi(kat) {
  const f = dhpKat(kat);
  if (!f) {
    return bekleniyorGovde("Kat için semantik harita üretilmemiş "
      + "(build_semantic_map.py çalıştırılmalı).");
  }

  const bina = f.outline && f.outline.length
    ? `<polygon class="dhp-bina" points="${_pts(f.outline)}"/>` : "";
  const koridor = (f.corridors || []).map(c =>
    `<polygon class="dhp-koridor" points="${_pts(c.polygon)}"/>`).join("");

  const odalar = (f.rooms || []).map(r => {
    const e = dhpEsleme(r.area_id);
    const secili = DH.seciliAlan === r.area_id;
    /* Ders programı için seçilmiş derslik. `secili`den AYRI bir durumdur:
       o, eşleştirme modunda düzenlenen alanı gösterir. İkisi de yalnızca
       KENAR ÇİZGİSİNİ değiştirir; doluluk rengi (yeşil→kırmızı) aynen
       kalır, çünkü o renk verinin kendisidir. */
    const programSecili = !!(DH.secili && e && e.room_code
                             && dhpOda(r.area_id)
                             && dhpOda(r.area_id).room_key === DH.secili);
    const [cx, cy] = _orta(r.polygon);
    return `<g class="dhp-oda${e && e.room_code ? " atanmis" : ""}${
        secili ? " secili" : ""}${programSecili ? " program-secili" : ""
        }" data-oda-alan="${esc(r.area_id)}">
      <polygon points="${_pts(r.polygon)}" fill="${dhpRenk(r)}"/>
      <text x="${cx.toFixed(1)}" y="${(cy + 2.5).toFixed(1)}"
            text-anchor="middle">${esc(dhpEtiket(r))}</text>
      <title>${esc(dhpIpucu(r))}</title>
    </g>`;
  }).join("");

  const isaret = (f.landmarks || []).map(l =>
    `<g class="dhp-isaret"><circle cx="${l.x}" cy="${l.y}" r="3"/>
      <title>${esc(l.label)}</title></g>`).join("");

  const taslak = (DHP.arac === "ciz" && DHP.taslak.length)
    ? `<polyline class="dhp-taslak" points="${
        _pts(DHP.taslak.concat(DHP.imlec ? [DHP.imlec] : []))}"/>`
    : "";

  const atanmis = (f.rooms || []).filter(r => {
    const e = dhpEsleme(r.area_id); return e && e.room_code;
  }).length;

  return `<div class="dhp-sarmal${DH.mod ? " mod" : ""}${
      DHP.arac ? " ciziyor" : ""}">
    <svg viewBox="${f.viewBox}" class="dhp-svg" data-kat="${kat}"
         preserveAspectRatio="xMidYMid meet"
         role="img" aria-label="Kat ${kat} derslik haritası">
      ${bina}
      <g class="dhp-koridorlar">${koridor}</g>
      <g class="dhp-odalar">${odalar}</g>
      <g class="dhp-isaretler">${isaret}</g>
      ${taslak}
    </svg>
  </div>
  <div class="not dhp-not">Kat ${kat} · <b>${(f.rooms || []).length}</b>
    sınıf/lab/amfi otomatik çıkarıldı, <b>${atanmis}</b> tanesine derslik
    kodu atandı. ${DH.mod
      ? "Bir odaya tıklayıp Excel derslik kodunu seçin."
      : "Kodu atanmamış odalar nötr gri gösterilir."}</div>`;
}

/* -------------------------------------------------------------------------
   ARAÇ ÇUBUĞU — ana akış yalnızca "tıkla ve ata"
   ------------------------------------------------------------------------- */
function dhpAracCubugu() {
  if (!DH.mod) return "";
  return `<div class="dhp-arac">
    <span class="dhp-ipuc">Haritadaki bir sınıfa tıklayın → derslik kodunu
      seçin → 💾 Kaydet</span>
    <button type="button" class="dh-btn kucuk${DHP.gelismis ? " acik" : ""}"
      data-dhp-gelismis title="Otomatik çıkarılamayan istisnai alanlar için">
      ⚙ Gelişmiş</button>
    ${DHP.gelismis ? `
      <button type="button" class="dh-btn kucuk${DHP.arac === "ciz" ? " acik" : ""}"
        data-dhp-arac="ciz">✏ Manuel alan ekle</button>
      ${DHP.arac === "ciz" ? `<span class="dhp-ipuc">${DHP.taslak.length}
        nokta · ilk noktaya tıkla → kapat · ESC → iptal</span>` : ""}` : ""}
  </div>`;
}

/* -------------------------------------------------------------------------
   ETKİLEŞİM
   ------------------------------------------------------------------------- */
function dhpKonum(svg, olay) {
  const n = svg.createSVGPoint();
  n.x = olay.clientX; n.y = olay.clientY;
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const u = n.matrixTransform(ctm.inverse());
  return [+u.x.toFixed(2), +u.y.toFixed(2)];
}

function dhpTaslagiKapat() {
  if (DHP.taslak.length < 3) {
    DH.mesaj = { tur: "hata", metin: "Alan en az 3 nokta gerektirir." };
    derslikHaritasiTazele(); return;
  }
  let n = 1;
  const mevcut = new Set(DH.alanlar.map(a => a.area_id));
  while (mevcut.has(`manuel${n}`)) n++;
  const alan = { area_id: `manuel${n}`, floor: Number(DH.kat),
                 polygon: DHP.taslak.slice(), room_code: null, label: null };
  DH.alanlar.push(alan);
  DHP.taslak = []; DHP.imlec = null; DHP.arac = null;
  DH.seciliAlan = alan.area_id;
  dhKirlet(); derslikHaritasiTazele();
}

document.addEventListener("click", e => {
  const harita = document.getElementById("alHarita");
  if (!harita) return;

  if (e.target.closest("[data-dhp-gelismis]")) {
    DHP.gelismis = !DHP.gelismis;
    if (!DHP.gelismis) { DHP.arac = null; DHP.taslak = []; }
    derslikHaritasiTazele(); return;
  }
  const aracBtn = e.target.closest("[data-dhp-arac]");
  if (aracBtn) {
    DHP.arac = DHP.arac === aracBtn.dataset.dhpArac ? null : aracBtn.dataset.dhpArac;
    DHP.taslak = []; DHP.imlec = null;
    derslikHaritasiTazele(); return;
  }

  const svg = e.target.closest(".dhp-svg");
  if (!svg || !DH.mod) return;

  if (DHP.arac === "ciz") {
    const p = dhpKonum(svg, e);
    if (!p) return;
    if (DHP.taslak.length >= 3) {
      const ilk = DHP.taslak[0];
      if (Math.hypot(ilk[0] - p[0], ilk[1] - p[1]) < 8) { dhpTaslagiKapat(); return; }
    }
    DHP.taslak.push(p); derslikHaritasiTazele(); return;
  }

  /* ANA AKIŞ: hazır odaya tıkla → düzenleyici açılır. */
  const g = e.target.closest("[data-oda-alan]");
  if (g) {
    const id = g.dataset.odaAlan;
    DH.seciliAlan = DH.seciliAlan === id ? null : id;
    DH.mesaj = null;
    derslikHaritasiTazele();
  }
});

document.addEventListener("mousemove", e => {
  if (!DH.mod || DHP.arac !== "ciz" || !DHP.taslak.length) return;
  const svg = document.querySelector("#alHarita .dhp-svg");
  if (!svg) return;
  const p = dhpKonum(svg, e);
  if (p) { DHP.imlec = p; derslikHaritasiTazele(); }
});

document.addEventListener("keydown", e => {
  if (e.key === "Escape" && DH.mod && (DHP.taslak.length || DHP.arac)) {
    DHP.taslak = []; DHP.imlec = null; DHP.arac = null;
    derslikHaritasiTazele();
    e.preventDefault();
  }
});

/** Seçili odanın plan bilgisi (düzenleyici başlığı için). */
function dhpSeciliOda() {
  const f = dhpKat(DH.kat);
  if (!f) return null;
  return (f.rooms || []).find(r => r.area_id === DH.seciliAlan) || null;
}

/** Eşleştirme kaydı yoksa oluşturur — geometri semantik haritadan gelir,
 *  kullanıcı çizmez. */
function dhpEslemeAlaniHazirla(odaId) {
  let a = DH.alanlar.find(x => x.area_id === odaId);
  if (a) return a;
  const r = dhpSeciliOda();
  if (!r) return null;
  a = { area_id: r.area_id, floor: Number(DH.kat),
        polygon: r.polygon, room_code: null,
        label: r.architectural_label };
  DH.alanlar.push(a);
  return a;
}
