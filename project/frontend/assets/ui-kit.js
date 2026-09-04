/* ABÜ KDS — YENİ TASARIMIN BİLEŞEN SÖZLÜĞÜ.
   ==========================================================================
   KAYNAK: halilhan/frontend-upgraded/assets/lenses.js — görsel yardımcılar.

   Bu dosya yeni tasarımın çizim ilkelerini taşır. Ekranlar ARTIK eski
   `views-*.js` bileşenleriyle (tile / donut / hbar / table) çizilmiyor;
   hepsi buradaki `kutu`, `cubuklar`, `cizgiGrafik`, `halka`, `tablo`,
   `kart` sözlüğüyle yeniden yazıldı.

   Sınıf adları prototiple BİREBİR aynıdır (`.kutu`, `.cubuk-satir`,
   `.halka-kutu`, `.kart`, `.izgara.k2`…) — böylece `shell.css` içindeki
   stiller, hover'lar ve animasyonlar hiç değiştirilmeden geçerli olur.

   ESKİ CSS BU EKRANLARDA KULLANILMAZ. `integration.css` yalnızca dinamik
   AI panelinin (`.ai-*`) ve bildirim/iskelet gibi GÖRÜNÜMSÜZ davranış
   parçalarının stillerini sağlar.
   ========================================================================== */

/* ---------------- metrik kutusu ---------------- */
const kutu = (etiket, deger, fark = "", sinif = "") =>
  `<div class="kutu ${sinif}"><div class="etiket">${fmt.esc(etiket)}</div>
   <div class="deger">${deger}</div>${fark ? `<div class="fark">${fark}</div>` : ""}</div>`;

const kutular = html => `<div class="kutular">${html}</div>`;

/* ---------------- yatay çubuk listesi ---------------- */
const cubuklar = (satirlar, opt = {}) => {
  const sayisal = satirlar.map(s => Number(s[1]) || 0);
  const maks = opt.maks || Math.max(...sayisal, 1);
  if (!satirlar.length) return bosDurum(opt.bos || "Gösterilecek kayıt yok.");
  return `<div class="cubuk">` + satirlar.map(([ad, deger, etiket, vurgulu, renk]) => `
    <div class="cubuk-satir ${vurgulu ? "vurgulu" : ""}"
         title="${fmt.esc(ad)}: ${fmt.esc(String(etiket ?? deger))}">
      <span class="ad">${fmt.esc(ad)}</span>
      <div class="ray"><div class="dolgu" style="width:${
        Math.min((Number(deger) || 0) / maks * 100, 100).toFixed(1)}%${
        renk ? `;background:${renk}` : ""}"></div></div>
      <span class="deger">${fmt.esc(String(etiket ?? fmtSayi(deger)))}</span>
    </div>`).join("") + `</div>`;
};

/* ---------------- çizgi grafiği ---------------- */
function cizgiGrafik(etiketler, seriler, opt = {}) {
  const gecerli = seriler.filter(s => (s.veri || []).some(v => Number.isFinite(Number(v))));
  if (!etiketler.length || !gecerli.length) {
    return bosDurum(opt.bos || "Grafik için yeterli veri yok.");
  }
  const G = 620, Y = opt.yukseklik
    ? Math.max(135, Math.round(opt.yukseklik * .72)) : 145;
  const S = 46, Sa = 16, U = 14, A = 30;
  const hepsi = gecerli.flatMap(s => s.veri).map(Number).filter(Number.isFinite);
  const alt = opt.min ?? Math.min(...hepsi) * .88;
  const ust = opt.maks ?? ((Math.max(...hepsi) * 1.08) || 1);
  const x = i => S + i * (G - S - Sa) / Math.max(etiketler.length - 1, 1);
  const y = v => U + (ust - v) / (ust - alt || 1) * (Y - U - A);

  let s = "";
  for (let i = 0; i <= 4; i++) {
    const v = alt + (ust - alt) * i / 4;
    s += `<line class="kilavuz" x1="${S}" y1="${y(v)}" x2="${G - Sa}" y2="${y(v)}"/>
          <text x="${S - 7}" y="${y(v) + 3}" text-anchor="end">${
            opt.yb ? opt.yb(v) : Math.round(v)}</text>`;
  }
  etiketler.forEach((e, i) => {
    s += `<text x="${x(i)}" y="${Y - 8}" text-anchor="middle">${fmt.esc(String(e))}</text>`;
  });
  gecerli.forEach(sr => {
    const nokta = sr.veri.map((v, i) => `${x(i)},${y(Number(v))}`).join(" ");
    if (sr.alan) {
      s += `<polygon points="${x(0)},${y(alt)} ${nokta} ${x(sr.veri.length - 1)},${y(alt)}"
              fill="${sr.renk}" opacity=".10"/>`;
    }
    s += `<polyline points="${nokta}" fill="none" stroke="${sr.renk}" stroke-width="2.4"
            stroke-linecap="round" stroke-linejoin="round"/>`;
    sr.veri.forEach((v, i) => {
      s += `<circle cx="${x(i)}" cy="${y(Number(v))}" r="4" fill="${sr.renk}"
              stroke="var(--yuzey)" stroke-width="2">
              <title>${fmt.esc(sr.ad)} · ${fmt.esc(String(etiketler[i]))}: ${
                fmt.esc(String(opt.yb ? opt.yb(v) : v))}</title></circle>`;
    });
  });
  return `<svg class="grafik" viewBox="0 0 ${G} ${Y}">${s}</svg>`;
}

/* ---------------- dağılım (scatter) grafiği ----------------
   Stratejik konumlandırma için: iki gösterge aynı anda okunur
   (ör. X = ölçek, Y = büyüme). Çubuk grafik bunu yapamaz — iki ayrı
   sıralama, "büyük ama yavaş" ile "küçük ama hızlı" ayrımını
   göstermez.

   `noktalar`: [{x, y, ad, vurgulu}]  — vurgulu nokta büyük ve dolgulu
   çizilir; kendi kurumumuzu işaretlemek için kullanılır.
   Değeri olmayan nokta ÇİZİLMEZ (0 varsayılmaz).                     */
function dagilimGrafik(noktalar, opt = {}) {
  const gecerli = (noktalar || []).filter(n =>
    Number.isFinite(Number(n.x)) && Number.isFinite(Number(n.y)));
  if (gecerli.length < 2) {
    return bosDurum(opt.bos || "Dağılım için yeterli veri yok.");
  }
  const G = 620, Y = opt.yukseklik
    ? Math.max(175, Math.round(opt.yukseklik * .74)) : 195;
  const S = 54, Sa = 18, U = 16, A = 34;
  const xs = gecerli.map(n => Number(n.x)), ys = gecerli.map(n => Number(n.y));
  const pad = (a, b) => (a === b ? Math.abs(a || 1) * 0.5 : (b - a) * 0.12);
  let x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  const px = pad(x0, x1), py = pad(y0, y1);
  x0 -= px; x1 += px; y0 -= py; y1 += py;
  const X = v => S + (Number(v) - x0) / (x1 - x0 || 1) * (G - S - Sa);
  const Yc = v => U + (y1 - Number(v)) / (y1 - y0 || 1) * (Y - U - A);

  let s = "";
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (y1 - y0) * i / 4;
    s += `<line class="kilavuz" x1="${S}" y1="${Yc(v)}" x2="${G - Sa}" y2="${Yc(v)}"/>
          <text x="${S - 7}" y="${Yc(v) + 3}" text-anchor="end">${
            opt.yb ? opt.yb(v) : Math.round(v)}</text>`;
  }
  for (let i = 0; i <= 3; i++) {
    const v = x0 + (x1 - x0) * i / 3;
    s += `<text x="${X(v)}" y="${Y - 8}" text-anchor="middle">${
      opt.xb ? opt.xb(v) : Math.round(v)}</text>`;
  }
  // Ortalama çizgileri: dört çeyrek okunabilir olsun diye.
  if (opt.ortalama !== false) {
    const ox = xs.reduce((a, b) => a + b, 0) / xs.length;
    const oy = ys.reduce((a, b) => a + b, 0) / ys.length;
    s += `<line class="kilavuz" x1="${X(ox)}" y1="${U}" x2="${X(ox)}" y2="${Y - A}"
            stroke-dasharray="4 4"/>
          <line class="kilavuz" x1="${S}" y1="${Yc(oy)}" x2="${G - Sa}" y2="${Yc(oy)}"
            stroke-dasharray="4 4"/>`;
  }
  gecerli.forEach(n => {
    const r = n.vurgulu ? 8 : 5;
    const renk = n.vurgulu ? "var(--vurgu)" : "var(--vurgu-2)";
    s += `<circle cx="${X(n.x)}" cy="${Yc(n.y)}" r="${r}" fill="${renk}"
            fill-opacity="${n.vurgulu ? 1 : 0.55}" stroke="var(--yuzey)"
            stroke-width="${n.vurgulu ? 3 : 1.5}">
            <title>${fmt.esc(n.ad || "")} · ${
              opt.xb ? opt.xb(n.x) : n.x} · ${opt.yb ? opt.yb(n.y) : n.y}</title>
          </circle>`;
    if (n.vurgulu) {
      s += `<text x="${X(n.x)}" y="${Yc(n.y) - 13}" text-anchor="middle"
              class="vurgu-etiket">${fmt.esc(n.kisa || n.ad || "")}</text>`;
    }
  });
  return `<svg class="grafik" viewBox="0 0 ${G} ${Y}">${s}</svg>` +
    (opt.eksen ? `<div class="not">${fmt.esc(opt.eksen)}</div>` : "");
}

/* ---------------- halka (ring) ---------------- */
function halka(deger, etiket, renk) {
  const v = Number(deger);
  if (!Number.isFinite(v)) {
    return `<div class="halka-kutu"><div class="etiket">${fmt.esc(etiket)}</div>
      <div class="not">veri yok</div></div>`;
  }
  const R = 34, C = 2 * Math.PI * R;
  return `<div class="halka-kutu">
    <svg width="92" height="92" viewBox="0 0 84 84">
      <circle cx="42" cy="42" r="${R}" fill="none" stroke="var(--cizgi)" stroke-width="8"/>
      <circle cx="42" cy="42" r="${R}" fill="none" stroke="${renk}" stroke-width="8"
        stroke-linecap="round"
        stroke-dasharray="${(Math.min(v, 100) / 100 * C).toFixed(1)} ${C.toFixed(1)}"
        transform="rotate(-90 42 42)"/>
      <text class="deger" x="42" y="47" text-anchor="middle">%${Math.round(v)}</text>
    </svg>
    <div class="etiket">${fmt.esc(etiket)}</div></div>`;
}
const halkalar = html => `<div class="halkalar">${html}</div>`;

/* ---------------- etiket çipi ---------------- */
const etiketC = (tur, metin) => `<span class="etiket-c ${tur}">${fmt.esc(metin)}</span>`;
const dolulukTur = d =>
  d === null || d === undefined ? "notr" : d >= 80 ? "iyi" : d >= 55 ? "uyari" : "kotu";

/* ---------------- kart ve ızgara ---------------- */
const kart = (baslik, not, govde, opt = {}) =>
  `<div class="kart"${opt.stil ? ` style="${opt.stil}"` : ""}${
    opt.id ? ` id="${opt.id}"` : ""}>
    ${baslik ? `<h3>${fmt.esc(baslik)}</h3>` : ""}
    ${not ? `<div class="not">${fmt.esc(not)}</div>` : ""}
    ${govde}</div>`;

const izgara = (sinif, ...kartlar) =>
  `<div class="izgara ${sinif}">${kartlar.join("")}</div>`;

const altBaslik = metin => `<h4>${fmt.esc(metin)}</h4>`;

/* ---------------- tablo ---------------- */
function tablo(basliklar, satirlar, opt = {}) {
  if (!satirlar.length) return bosDurum(opt.bos || "Gösterilecek kayıt yok.");
  return `<div class="tablo-sar"><table>
    <thead><tr>${basliklar.map(b => `<th>${fmt.esc(b)}</th>`).join("")}</tr></thead>
    <tbody>${satirlar.map(r => {
      const hucreler = Array.isArray(r) ? r : r.hucreler;
      const git = Array.isArray(r) ? null : r.git;
      return `<tr${git ? ` class="tiklanir" data-git="${fmt.esc(git)}"` : ""}>${
        hucreler.map(h => typeof h === "string" || typeof h === "number"
          ? `<td>${h}</td>`
          : `<td${h.sinif ? ` class="${h.sinif}"` : ""}${
              h.stil ? ` style="${h.stil}"` : ""}>${h.icerik}</td>`).join("")}</tr>`;
    }).join("")}</tbody>
  </table></div>`;
}

/* ---------------- durum bileşenleri — YENİ görsel dilde ----------------
   Eski `ui.loading/error/empty` kutuları eski kabuğun görünümüne aitti.
   Davranış aynı (yükleniyor / hata / boş), görünüm yeni tasarımın. */
const yukleniyorDurum = (metin = "Veriler yükleniyor…") =>
  `<div class="durum yukleniyor"><span class="donen"></span>${fmt.esc(metin)}</div>`;

const bosDurum = (metin = "Kayıt bulunamadı.") =>
  `<div class="durum bos">${fmt.esc(metin)}</div>`;

const hataDurum = err => {
  const mesaj = (err && (err.userMessage || err.message)) || String(err);
  return `<div class="durum hata"><b>Veri alınamadı.</b><span>${fmt.esc(mesaj)}</span></div>`;
};

const iskelet = (satir = 3) =>
  `<div class="iskelet">${Array.from({ length: satir },
    () => `<div class="iskelet-satir"></div>`).join("")}</div>`;

/* ==========================================================================
   VERİ YÜKLEYİCİ
   --------------------------------------------------------------------------
   Bir kabı iskeletle doldurur, veriyi çeker, gelince çizer.
   Hata ve boş durum aynı görsel dilde gösterilir; ekran sessizce boş
   kalmaz. Yarış durumu koruması: kap yeniden çizildiyse geç gelen cevap
   yazılmaz (`veriNesli`).
   ========================================================================== */
let veriNesli = 0;
function nesilTazele() { veriNesli++; return veriNesli; }

async function veri(kapId, getir, ciz, opt = {}) {
  const nesil = veriNesli;
  const kap = document.getElementById(kapId);
  if (!kap) return;
  kap.innerHTML = opt.iskelet === false
    ? yukleniyorDurum(opt.yukleniyor) : iskelet(opt.iskelet || 3);
  try {
    const sonuc = await getir();
    if (nesil !== veriNesli) return;               // ekran değişti
    const hedef = document.getElementById(kapId);
    if (!hedef) return;
    const bos = Array.isArray(sonuc)
      ? !sonuc.length
      : sonuc === null || sonuc === undefined;
    if (bos && opt.bos !== false) { hedef.innerHTML = bosDurum(opt.bos); return; }
    hedef.innerHTML = ciz(sonuc, hedef) ?? hedef.innerHTML;
  } catch (err) {
    if (nesil !== veriNesli) return;
    const hedef = document.getElementById(kapId);
    if (!hedef) return;
    // Backend "bu yıl/bu modül için veri yok" durumunu 404 + açıklayıcı
    // mesajla bildiriyor. Bu bir ARIZA değil, VERİ YOKLUĞUDUR; kırmızı hata
    // kutusu yerine sade boş durum gösterilir. Gerçek hatalar (500, ağ
    // kesintisi, 4xx doğrulama) eskisi gibi hata kutusuna düşer.
    if (err && err.status === 404) {
      hedef.innerHTML = bosDurum(err.userMessage || err.detail || undefined);
      return;
    }
    hedef.innerHTML = hataDurum(err);
  }
}

/* Sayı biçimleri: prototipin yazımı, `fmt` üzerinden (bkz. data-adapter.js).
   `fmtPara` burada tanımlı — prototipte de öyleydi. */
const fmtPara = n => {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) return "—";
  const v = Number(n);
  const mutlak = Math.abs(v);
  if (mutlak >= 1e6) return "$" + (v / 1e6).toFixed(1).replace(".", ",") + "M";
  if (mutlak >= 1e3) return "$" + Math.round(v / 1e3) + "K";
  return "$" + Math.round(v).toLocaleString("tr-TR");
};
