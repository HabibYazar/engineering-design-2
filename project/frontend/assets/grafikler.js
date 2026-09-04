/* ABÜ KDS — SÜTUN GRAFİĞİ SÖZLÜĞÜ
   ==========================================================================
   NEDEN AYRI DOSYA
   ----------------
   `ekranlar.js` ekranların NE gösterdiğini, bu dosya NASIL gösterdiğini
   tanımlar. Grafik yardımcıları tek yerde durunca eksen, gösterge
   (legend), değer etiketi ve "veri yok" davranışı bütün panellerde aynı
   olur; her panelde ayrı ayrı SVG yazmak, on ekran sonra on farklı
   görsel dil demektir.

   TASARIM KURALLARI (hepsi burada zorunlu tutulur)
   -----------------------------------------------
     · her grafikte gösterge (legend) ve eksen etiketi bulunur
     · her sütunun gerçek değeri ya üstünde yazar ya da tooltip'te durur
     · sıfır/eksik değer UYDURULMAZ: `null` çubuk çizilmez, kategori
       "ölçülmedi" olarak işaretlenir
     · veri hiç yoksa grafik değil "veri yok" kartı döner

   ÖLÇEK DÜRÜSTLÜĞÜ — `karsilastirmaCubugu`
   ----------------------------------------
   Yönetim "birkaç metriği aynı anda" görmek istiyor; ama öğrenci sayısı
   (1.219) ile akademisyen sayısı (32) aynı eksende çizilirse küçük olan
   görünmez olur. Çözüm: HER SERİ KENDİ MAKSİMUMUNA göre ölçeklenir,
   çubuğun üstünde GERÇEK değer yazar ve grafiğin altına ölçek notu
   düşülür. Böylece kıyas "hangi birim bu metrikte önde" sorusunu
   cevaplar; mutlak büyüklükler ise etiketlerden okunur.

   Aynı birimdeki metrikler (kontenjan/yerleşen, derslik/kapasite) için
   `gruplandirilmisCubuk` kullanılır: orada ortak eksen DOĞRUDUR.
   ========================================================================== */

/* Seri renkleri — birbirinden kolay ayrılan, temayla uyumlu palet. */
/* Seri paleti TAMAMEN temadan turetilir. Altinci ve yedinci renk eskiden
   sabit hex idi (#46b3e6, #8fa3bf); fakulte temasi degisince o iki seri
   kurumsal mavi/gri kalip paletin geri kalanindan kopuyordu. Artik ikisi
   de iki tema renginin karisimi: her temada uyumlu, yine de saf
   renklerden ayirt edilebilir. */
const GRAFIK_RENK = [
  "var(--vurgu)", "var(--vurgu-2)", "var(--mor)", "var(--uyari)",
  "var(--pembe)",
  "color-mix(in srgb, var(--vurgu) 50%, var(--pembe))",
  "color-mix(in srgb, var(--vurgu-2) 50%, var(--uyari))",
  "var(--iyi)",
];

const _sayiVar = v => v !== null && v !== undefined && Number.isFinite(Number(v));

/**
 * Ölçüye ve anlamsal tipe duyarlı merkezi sayı biçimlendirici.
 * Küçük rasyonel oranları (0.0692, 0.0254 vb.) sıfıra yuvarlamaz;
 * metrik üst verisi (measure_type, display_precision, display_unit) ile çalışır.
 */
function formatChartValue(v, opt = {}) {
  if (!_sayiVar(v)) return "—";
  const n = Number(v);
  if (opt.display_precision !== undefined && opt.display_precision !== null) {
    return n.toLocaleString("tr-TR", {
      minimumFractionDigits: opt.display_precision,
      maximumFractionDigits: opt.display_precision,
    });
  }
  if (opt.measure_type === "percentage" || (opt.birim && String(opt.birim).includes("%"))) {
    return n.toLocaleString("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
  }
  if (Math.abs(n) > 0 && Math.abs(n) < 0.1) {
    return n.toLocaleString("tr-TR", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  }
  if (Math.abs(n) > 0 && Math.abs(n) < 10 && !Number.isInteger(n)) {
    return n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (!Number.isInteger(n)) {
    return n.toLocaleString("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }
  return n.toLocaleString("tr-TR");
}

/** Gösterge şeridi (legend). */
function gosterge(seriler) {
  return `<div class="gsterge">${seriler.map((s, i) => `
    <span><i style="background:${s.renk || GRAFIK_RENK[i % GRAFIK_RENK.length]}"></i>${
      esc(s.ad)}${s.birim ? ` <small>(${esc(s.birim)})</small>` : ""}</span>`).join("")}</div>`;
}

/** "Detayı Göster" ile açılan ikincil içerik (tablolar buraya iner). */
function detay(baslik, icerik) {
  if (!icerik) return "";
  return `<details class="detay">
    <summary>${esc(baslik || "Detayı göster")}</summary>
    <div class="detay-ic">${icerik}</div>
  </details>`;
}

/* ==========================================================================
   1) GRUPLANDIRILMIŞ SÜTUN — ortak eksen (aynı birimdeki metrikler)
   ========================================================================== */
/**
 * @param kategoriler ["Bilgisayar Müh.", …]
 * @param seriler     [{ad, veri:[…], renk?, birim?}]
 * @param opt         {eksenY, yb, yukseklik, deger, measure_type, display_precision}
 */
function gruplandirilmisCubuk(kategoriler, seriler, opt = {}) {
  const gecerli = (seriler || []).filter(s => (s.veri || []).some(_sayiVar));
  if (!kategoriler.length || !gecerli.length) {
    return bekleniyorGovde(opt.bos || "Grafik için ölçülen değer yok.");
  }
  const G = 720, Y = opt.yukseklik
    ? Math.max(160, Math.round(opt.yukseklik * .74)) : 190;
  const SOL = 78, SAG = 14, UST = 14;
  const ALT = 46 + Math.min(30, Math.max(...kategoriler.map(k => k.length)) * 1.1);
  const tumu = gecerli.flatMap(s => s.veri).filter(_sayiVar).map(Number);
  const yb = opt.yb || (tumu.every(Number.isInteger)
    ? (v => fmt.int(Math.round(v)))
    : (v => formatChartValue(v, opt)));
  const maks = Math.max(...tumu, 1) * 1.12;
  const alan = G - SOL - SAG;
  const grupW = alan / kategoriler.length;
  const cubukW = Math.max(4, (grupW * 0.72) / gecerli.length);
  const y = v => UST + (1 - Number(v) / maks) * (Y - UST - ALT);

  let s = "";
  for (let i = 0; i <= 4; i++) {                       // ızgara + Y ekseni
    const v = maks * i / 4;
    s += `<line x1="${SOL}" y1="${y(v)}" x2="${G - SAG}" y2="${y(v)}" stroke="var(--cizgi)"/>
      <text x="${SOL - 6}" y="${y(v) + 3}" text-anchor="end" fill="var(--sonuk)"
            font-size="9">${yb(v)}</text>`;
  }
  kategoriler.forEach((kat, gi) => {
    const x0 = SOL + gi * grupW + (grupW - cubukW * gecerli.length) / 2;
    gecerli.forEach((sr, si) => {
      const v = sr.veri[gi];
      const renk = sr.renk || GRAFIK_RENK[si % GRAFIK_RENK.length];
      const x = x0 + si * cubukW;
      const kolon = _ipucuKolon(kategoriler, gecerli, gi, opt, yb);
      if (!_sayiVar(v)) {                              // ÖLÇÜLMEDİ — çubuk yok
        s += `<text x="${x + cubukW / 2}" y="${y(0) - 3}" text-anchor="middle"
                 fill="var(--sonuk)" font-size="8"
                 data-ipucu-seri="${si}" data-ipucu-kolon="${kolon}">·<title>${
                 esc(sr.ad)} · ${esc(kat)}: ölçülmedi</title></text>`;
        return;
      }
      const yy = y(v), h = Math.max(1, y(0) - yy);
      s += `<rect x="${x}" y="${yy}" width="${cubukW - 2}" height="${h}" rx="2"
              fill="${renk}" data-ipucu-seri="${si}"
              data-ipucu-kolon="${kolon}"><title>${esc(sr.ad)} · ${esc(kat)}: ${yb(v)}${
              sr.birim ? " " + esc(sr.birim) : ""}</title></rect>`;
      if (opt.deger !== false && kategoriler.length * gecerli.length <= 24) {
        /* Aynı üst üste binme sorunu gruplandırılmış çubukta da var. */
        s += _degerEtiketi(x + (cubukW - 2) / 2, yy - 4, yb(v), cubukW);
      }
    });
    // X ekseni etiketi — uzun adlar eğik yazılır
    const cx = SOL + gi * grupW + grupW / 2;
    s += `<text x="${cx}" y="${Y - ALT + 14}" text-anchor="end" fill="var(--sonuk)"
             font-size="9" transform="rotate(-32 ${cx} ${Y - ALT + 14})"
             >${esc(kat.length > 18 ? kat.slice(0, 17) + "…" : kat)}</text>`;
  });
  s += `<line x1="${SOL}" y1="${y(0)}" x2="${G - SAG}" y2="${y(0)}" stroke="var(--kenar)"/>`;

  return gosterge(gecerli)
    + `<svg viewBox="0 0 ${G} ${Y}" style="width:100%;height:auto"
            role="img" aria-label="${esc(opt.eksenY || "Karşılaştırma")}">${s}</svg>`
    + (opt.eksenY ? `<div class="eksen-not">Y ekseni: ${esc(opt.eksenY)}</div>` : "");
}

/* ==========================================================================
   2) KARŞILAŞTIRMA SÜTUNU — farklı birimlerdeki metrikler bir arada
   ========================================================================== */
/**
 * Her seri KENDİ maksimumuna göre ölçeklenir; çubuk yüksekliği "bu
 * metrikte ne kadar öndesin"i, üstündeki etiket GERÇEK değeri gösterir.
 * Ölçek notu grafiğin altında AÇIKÇA yazar — ortak eksen iddiası yok.
 */
/** Çubuk üstü değer etiketi — dar çubukta DİKEY yazar.
 *  Çoklu metrikte bir grupta 5 seri var; 10 kurum × 5 = 50 çubuk yan yana
 *  düşünce yatay yazılan "86.878" ile komşusundaki "69.179" üst üste
 *  biniyor ve ikisi de okunamaz hâle geliyordu ("86.87869.179").
 *  Çubuk genişliği eşiğin altındaysa etiket 90° döndürülür: metin artık
 *  komşusuna değil, kendi çubuğunun üstüne doğru uzar. */
const _DIK_ESIK = 14;
function _degerEtiketi(cx, cy, metin, cubukW) {
  const dik = cubukW < _DIK_ESIK;
  return `<text x="${cx.toFixed(1)}" y="${cy.toFixed(1)}"
    text-anchor="${dik ? "start" : "middle"}" fill="var(--metin-2)"
    font-size="${dik ? 7 : 7.5}"${
      dik ? ` transform="rotate(-90 ${cx.toFixed(1)} ${cy.toFixed(1)})"` : ""
    }>${metin}</text>`;
}

function karsilastirmaCubugu(kategoriler, seriler, opt = {}) {
  const gecerli = (seriler || []).filter(s => (s.veri || []).some(_sayiVar));
  if (!kategoriler.length || !gecerli.length) {
    return bekleniyorGovde(opt.bos || "Karşılaştırma için ölçülen metrik yok.");
  }
  const G = 760, Y = opt.yukseklik
    ? Math.max(170, Math.round(opt.yukseklik * .74)) : 205;
  const SOL = 72, SAG = 14, UST = 18;
  const ALT = 52 + Math.min(34, Math.max(...kategoriler.map(k => k.length)) * 1.1);
  const alan = G - SOL - SAG;
  const grupW = alan / kategoriler.length;
  const cubukW = Math.max(4, (grupW * 0.74) / gecerli.length);
  const taban = Y - ALT;

  /* ÖLÇEK YÖNÜ — hangi eksende normalize edilecek?
     ------------------------------------------------------------------
     Varsayılan SERİ BAZLIDIR: her seri kendi en yüksek değerine göre
     ölçeklenir. Bu, serilerin FARKLI BİRİMLERDE metrikler olduğu
     kullanım için doğrudur (kişi sayısı ile TL aynı eksene sığmaz).

     `olcekKategoriBazli` verildiğinde normalize KATEGORİ içinde yapılır:
     aynı kategorideki seriler birbirine göre ölçeklenir. Bu, seriler
     KARŞILAŞTIRILAN VARLIKLAR (Derslik / Laboratuvar gibi) ve
     kategoriler metrik olduğunda ZORUNLUDUR.

     Neden zorunlu: seri bazlı ölçekle Derslik'in 3.171'i ile
     Laboratuvar'ın 607'si İKİSİ DE tam yükseklik çizilir; grafiğe bakan
     kişi iki kapasitenin eşit olduğunu okur. Ölçüldü ve bu yüzden
     eklendi. Değerler her iki durumda da aynıdır — değişen yalnızca
     çubuk yüksekliğinin neye göre hesaplandığıdır. */
  const kategoriMaks = kategoriler.map((_, gi) =>
    Math.max(...gecerli.map(s => s.veri[gi]).filter(_sayiVar).map(Number), 1));
  const maksimumlar = gecerli.map(s =>
    Math.max(...s.veri.filter(_sayiVar).map(Number), 1));
  /* ÜÇÜNCÜ MOD: ORTAK ÖLÇEK.
     Bütün çubuklar AYNI BİRİMDEYSE (histogramda hepsi "adet") tek bir
     eksen gerekir. Seri ya da kategori bazlı normalize burada yanlış
     okuma üretir: 18 derslik ile 15 laboratuvar farklı ölçeklere
     bölünüp ikisi de tam yükseklik çizilir, aradaki fark kaybolur.
     Ortak ölçekte Y ekseni de anlamlıdır (bkz. `yEkseni`). */
  const ortakMaks = Math.max(
    ...gecerli.flatMap(s => s.veri.filter(_sayiVar).map(Number)), 1);
  const olcek = (v, si, gi) =>
    Number(v) / (opt.olcekOrtak ? ortakMaks
      : opt.olcekKategoriBazli ? kategoriMaks[gi] : maksimumlar[si]);

  /* Y ekseni yalnızca ortak ölçekte çizilir; farklı birimler tek
     eksende gösterilemez. Adım "güzel sayı"dır: 1, 2, 5, 10, 20, 50…
     Sayım grafiği olduğu için değerler tam sayıdır. */
  const yAdim = (m) => {
    const ham = m / 4;
    const us = Math.pow(10, Math.floor(Math.log10(Math.max(ham, 1))));
    return [1, 2, 5, 10].map(k => k * us).find(a => a >= ham) || us * 10;
  };

  let s = "";
  if (opt.olcekOrtak && opt.yEkseni) {
    const adim = yAdim(ortakMaks);
    for (let v = 0; v <= ortakMaks; v += adim) {
      const y = taban - (v / ortakMaks) * (taban - UST);
      s += `<line x1="${SOL}" y1="${y.toFixed(1)}" x2="${G - SAG}" y2="${
        y.toFixed(1)}" stroke="var(--kenar)" stroke-opacity=".35"/>
        <text x="${SOL - 8}" y="${(y + 3).toFixed(1)}" text-anchor="end"
          fill="var(--sonuk)" font-size="9">${v}</text>`;
    }
  }
  kategoriler.forEach((kat, gi) => {
    const x0 = SOL + gi * grupW + (grupW - cubukW * gecerli.length) / 2;
    gecerli.forEach((sr, si) => {
      const v = sr.veri[gi];
      const renk = sr.renk || GRAFIK_RENK[si % GRAFIK_RENK.length];
      const x = x0 + si * cubukW;
      const bicim = sr.bicim || (n => formatChartValue(n, { ...opt, birim: sr.birim }));
      /* Ölçülmemiş değerde bile ipucu verilir: kullanıcı boşluğun
         üzerine geldiğinde o kategorinin diğer metriklerini görsün. */
      const kolon = _ipucuKolon(kategoriler, gecerli, gi, opt);
      if (!_sayiVar(v)) {
        s += `<text x="${x + cubukW / 2}" y="${taban - 4}" text-anchor="middle"
                 fill="var(--sonuk)" font-size="8"
                 data-ipucu-seri="${si}" data-ipucu-kolon="${kolon}">—<title>${
                 esc(sr.ad)} · ${esc(kat)}: ölçülmedi</title></text>`;
        return;
      }
      const oran = olcek(v, si, gi);
      const h = Math.max(2, oran * (taban - UST));
      s += `<rect x="${x}" y="${taban - h}" width="${cubukW - 2}" height="${h}" rx="2"
              fill="${renk}" data-ipucu-seri="${si}"
              data-ipucu-kolon="${kolon}"><title>${esc(sr.ad)} · ${esc(kat)}: ${bicim(v)}${
              sr.birim ? " " + esc(sr.birim) : ""}</title></rect>
            ${_degerEtiketi(x + (cubukW - 2) / 2, taban - h - 4, bicim(v), cubukW)}`;
    });
    const cx = SOL + gi * grupW + grupW / 2;
    s += `<text x="${cx}" y="${taban + 14}" text-anchor="end" fill="var(--metin-2)"
             font-size="9" transform="rotate(-30 ${cx} ${taban + 14})"
             >${esc(kat.length > 20 ? kat.slice(0, 19) + "…" : kat)}</text>`;
  });
  s += `<line x1="${SOL}" y1="${taban}" x2="${G - SAG}" y2="${taban}" stroke="var(--kenar)"/>`;

  return gosterge(gecerli)
    + `<svg viewBox="0 0 ${G} ${Y}" style="width:100%;height:auto"
            role="img" aria-label="Çoklu metrik karşılaştırması">${s}</svg>`
    /* Ortak ölçekte çubuk yüksekliği ZATEN değerin kendisidir; oradaki
       "yükseklik sıralamayı, etiket değeri gösterir" uyarısı yalnızca
       farklı ölçekli modlar için anlamlıdır ve ortak ölçekte kafa
       karıştırır. Bu yüzden kuyruk cümlesi yalnız o modlarda eklenir. */
    + `<div class="eksen-not">${opt.olcekOrtak
        ? (opt.eksenNot || "Bütün çubuklar aynı ölçekte; yükseklikler "
            + "doğrudan karşılaştırılabilir.")
        : (opt.olcekKategoriBazli
        ? "Her metrik KENDİ İÇİNDE ölçeklendi: çubuklar aynı metrikteki serileri "
          + "birbiriyle karşılaştırır (birimler metrikler arasında farklı)."
        : `Her metrik KENDİ en yüksek değerine göre
        ölçeklendi (birimleri farklı).`) + ` Çubuk yüksekliği sıralamayı,
        üstündeki etiket gerçek değeri gösterir.`}</div>`;
}

/* ==========================================================================
   3) YIĞIN SÜTUN — bir bütünün parçaları (burs türü, unvan…)
   ========================================================================== */
/* ==========================================================================
   DAĞILIM HALKASI — bir bütünün parçaları, TEK an
   --------------------------------------------------------------------------
   Ne zaman halka, ne zaman sütun?
     • Halka: tek bir ana ait bütünün parçaları (aktif kadronun unvan
       bileşimi gibi). Kaybolacak bir zaman ekseni yoktur.
     • Sütun: birden çok kategori ya da birden çok yıl. Halkanın zaman
       ekseni olmadığı için orada bilgi KAYBEDER.

   Unvan dağılımı eskiden TEK kategorili yığın sütunla çiziliyordu:
   "Aktif kadro" diye tek bir sütun. Tek sütunlu yığın grafik zaten
   halkanın çubuğa katlanmış hâlidir; dar panelde okunmuyordu.

   Küçük dilimler (Doçent 9, Profesör 10) halkada incedir — bu yüzden
   panelde yatay çubuklar KALIR: pay halkadan, kesin sayı çubuktan
   okunur. İkisi farklı soruyu cevaplar.
   ========================================================================== */
/* Halka açılış maskesi için benzersiz kimlik.
   Aynı sayfada birden çok halka olabilir; maske kimlikleri çakışırsa
   ikinci halka birincinin maskesini kullanır ve yanlış açılır. */
let _halkaMaskeNo = 0;

function dagilimHalkasi(parcalar, opt = {}) {
  const gecerli = (parcalar || [])
    .filter(p => _sayiVar(p.deger) && Number(p.deger) > 0);
  if (!gecerli.length) {
    return bekleniyorGovde(opt.bos || "Dağılım için ölçülen değer yok.");
  }
  const toplam = gecerli.reduce((t, p) => t + Number(p.deger), 0);
  /* İÇ YARIÇAP SEÇENEKLİ: 0 = pasta (dolu daire), >0 = halka (donut).
     Pasta ile halka aynı veriyi gösterir; farkları yalnızca ortadaki
     boşluktur. İki ayrı çizim fonksiyonu yazmak, aynı geometriyi iki
     yerde bakımı zor biçimde tekrarlamak olurdu. `ic = 0` olduğunda
     iç yay dejenere olur ve SVG onu düz çizgi sayar — sonuç tam bir
     pasta dilimidir. */
  const G = 250, cx = G / 2, cy = G / 2, R = 96;
  const ic = Number.isFinite(opt.icYaricap) ? Math.max(0, opt.icYaricap) : 62;
  const yb = opt.yb || (v => fmt.int(Math.round(v)));

  const nokta = (aci, yaricap) => {
    const a = (aci - 90) * Math.PI / 180;
    return [cx + yaricap * Math.cos(a), cy + yaricap * Math.sin(a)];
  };

  let s = "";
  let acik = 0;

  /* Tek parça %100 ise yay dejenere olur (başlangıç = bitiş); halka iki
     çemberle çizilir. */
  if (gecerli.length === 1) {
    const p = gecerli[0];
    s += `<circle cx="${cx}" cy="${cy}" r="${(R + ic) / 2}" fill="none"
      stroke="${p.renk || GRAFIK_RENK[0]}" stroke-width="${R - ic}"
      ><title>${esc(p.ad)}: ${esc(yb(p.deger))} (%100)</title></circle>`;
  } else {
    gecerli.forEach((p, i) => {
      const pay = Number(p.deger) / toplam;
      const kapali = acik + pay * 360;
      const buyuk = pay > 0.5 ? 1 : 0;
      const [x1, y1] = nokta(acik, R);
      const [x2, y2] = nokta(kapali, R);
      const [x3, y3] = nokta(kapali, ic);
      const [x4, y4] = nokta(acik, ic);
      const renk = p.renk || GRAFIK_RENK[i % GRAFIK_RENK.length];
      s += `<path d="M ${x1} ${y1} A ${R} ${R} 0 ${buyuk} 1 ${x2} ${y2}
        L ${x3} ${y3} A ${ic} ${ic} 0 ${buyuk} 0 ${x4} ${y4} Z"
        fill="${renk}" stroke="var(--yuzey)" stroke-width="1.5"
        ><title>${esc(p.ad)}: ${esc(yb(p.deger))} (%${
        (pay * 100).toFixed(1).replace(".", ",")})</title></path>`;

      /* Etiket yalnızca dilim yeterince genişse yazılır; ince dilimde
         üst üste biner ve okunmaz. Kesin sayı zaten çubuklarda. */
      if (pay >= 0.09) {
        const [ex, ey] = nokta(acik + pay * 180, (R + ic) / 2);
        s += `<text x="${ex}" y="${ey + 3.5}" text-anchor="middle"
          fill="#fff" font-size="10" font-weight="600"
          >${Math.round(pay * 100)}%</text>`;
      }
      acik = kapali;
    });
  }

  /* Merkez: toplam. Halkanın ortası boşsa göz oraya "eksik" diye bakar.
     Merkez yazısı MASKE DIŞINDA tutulur: halka dönerek dolarken toplam
     sayı yerinde durur, süpürme onu kesip yeniden ortaya çıkarmaz. */
  const merkez = `<text x="${cx}" y="${cy - 2}" text-anchor="middle" fill="var(--metin)"
    font-size="26" font-weight="700">${esc(yb(toplam))}</text>
    <text x="${cx}" y="${cy + 17}" text-anchor="middle" fill="var(--sonuk)"
    font-size="10">${esc(opt.merkezEtiket || "toplam")}</text>`;

  /* AÇILIŞ MASKESİ — GEOMETRİYİ DEĞİŞTİRMEZ.
     ------------------------------------------------------------------
     Dilimler `<path>` ile DOLDURULARAK çiziliyor, `stroke` ile değil;
     bu yüzden dilimlerin kendisine `stroke-dasharray` uygulanamaz.
     Bunun yerine halka bandını kaplayan tek bir maske çemberi çizilir
     ve o çember `stroke-dashoffset` ile saat yönünde açılır. Dilimler
     maskenin altından sırayla görünür.

     Dilimlerin `d` yolları, açıları, renkleri ve `<title>` ipuçları
     OLDUĞU GİBİ kalır — animasyon yalnızca neyin GÖRÜNDÜĞÜNÜ belirler,
     neyin ÇİZİLDİĞİNİ değil. Maske CSS'te kapatılırsa (azaltılmış
     hareket) halka ilk kareden itibaren tam görünür.

     Maske çemberi: yarıçap (R+ic)/2, kalınlık (R-ic)+8. Fazladan 8
     birim, dilimlerin `stroke-width` kenarlığını da kapsaması içindir;
     aksi hâlde açılma sırasında dilim kenarında ince bir çizgi kalır. */
  const maskeNo = ++_halkaMaskeNo;
  const mr = (R + ic) / 2;
  const cevre = 2 * Math.PI * mr;
  const maske = `<defs><mask id="abu-halka-${maskeNo}" maskUnits="userSpaceOnUse">
      <circle class="abu-halka-sweep" cx="${cx}" cy="${cy}" r="${mr.toFixed(2)}"
        fill="none" stroke="#fff" stroke-width="${(R - ic + 8).toFixed(1)}"
        stroke-dasharray="${cevre.toFixed(2)}"
        style="--abu-halka-cevre:${cevre.toFixed(2)}"
        transform="rotate(-90 ${cx} ${cy})"/>
    </mask></defs>`;

  return gosterge(gecerli.map(p => ({ ad: p.ad, renk: p.renk })))
    + `<div class="halka-kap"><svg viewBox="0 0 ${G} ${G}"
        role="img" aria-label="${esc(opt.merkezEtiket || "dağılım")}">${
        maske}<g mask="url(#abu-halka-${maskeNo})">${s}</g>${merkez}</svg></div>`;
}

/* ==========================================================================
   KARŞILAŞTIRMA ÇİZGİSİ — çok metrik, çok kurum
   --------------------------------------------------------------------------
   NEDEN ÇİZGİ, NEDEN BURADA MAKUL:
   Çizgi normalde SIRALI bir eksen ister (çoğunlukla zaman). Buradaki eksen
   kurumlar, yani kategorik — ama liste ilk metriğe göre BÜYÜKTEN KÜÇÜĞE
   sıralı geldiği için eksenin bir yönü var. O yüzden çizginin inişi
   anlamlıdır: "büyüklük sırasında nerede duruyoruz" sorusunu okutur.

   BİTİŞİK ÇUBUĞA GÖRE ASIL KAZANÇ:
   Metriklerin birimleri farklı (kişi, yüzde) ve her seri KENDİ en yüksek
   değerine göre ölçekleniyor. Çubukta bu bir tuzaktı: göz yan yana duran
   iki çubuğu kıyaslar, oysa ölçekleri ayrıdır. Çizgide göz tek bir seriyi
   TAKİP eder, komşusuyla kıyaslamaz — aynı ölçekleme çizgide yanıltmaz.

   Y ekseni bu yüzden mutlak değer değil, "kendi en yükseğinin yüzdesi"
   olarak etiketlenir; gerçek sayı noktanın ipucunda durur.
   ========================================================================== */
/* Bir kategorinin (kurumun) BÜTÜN metriklerini ipucu için paketler.
   Öznitelikte HTML taşımak kaçış sorunları çıkarır; onun yerine JSON
   yazılır ve okurken tarayıcı zaten çözer. `<` ve `"` ayrıca kaçırılır
   ki öznitelik bozulmasın. */
function _ipucuKolon(kategoriler, seriler, i, opt, ortakBicim) {
  const veri = {
    ad: kategoriler[i],
    /* SIRA YALNIZCA SIRALI EKSENDE ANLAMLI.
       Kurum karşılaştırmasında liste büyüklüğe göre dizili, "3 / 10"
       bilgi taşır. Ama yıl ekseninde ("2023-2024") aynı satır
       "büyüklük sırası: 2 / 4" diye çıkıyordu — yıllar büyüklüğe göre
       sıralanmaz. Etiketi yalnızca çağıran verirse yazılır. */
    sira: opt.siraEtiketi
      ? opt.siraEtiketi + ": " + (i + 1) + " / " + kategoriler.length
      : null,
    biz: Number.isInteger(opt.vurguIndeks) && opt.vurguIndeks === i,
    satir: seriler.map((sr, si) => {
      const v = sr.veri[i];
      /* Sıra: serinin kendi biçimi > çağıranın ortak biçimi > genel.
         Böylece ipucundaki sayı, grafiğin üzerinde yazan sayıyla AYNI
         biçimde çıkar (yüzde, bin ayracı, ondalık basamak). */
      const bicim = sr.bicim || ortakBicim
        || (x => formatChartValue(x, { ...opt, birim: sr.birim }));
      return {
        ad: sr.ad,
        deger: _sayiVar(v)
          ? bicim(v) + (sr.birim ? " " + sr.birim : "")
          : "—",
        renk: sr.renk || GRAFIK_RENK[si % GRAFIK_RENK.length],
      };
    }),
  };
  return JSON.stringify(veri)
    .replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

/* ==========================================================================
   YIL TRENDİ — X ekseni YILLAR, her çizgi bir KURUM
   --------------------------------------------------------------------------
   Burada çizgi grafik DOĞRU araçtır: 2022 → 2023 → 2024 gerçek bir zaman
   eksenidir, kurum sıralaması gibi keyfî değildir.

   Y ekseni seçilen moda göre DOLULUK (%) ya da KONTENJAN (kişi) gösterir.
   Kontenjan modunda normalize edilmez — ham sayı okunur.

   Ölçülmemiş yıl SIFIR DEĞİLDİR: nokta çizilmez, çizgi kopar. Sıfır
   yazılsaydı "o yıl kimse yerleşmedi" gibi okunurdu.
   ========================================================================== */
/* SIRA RENGİ — konumu renge çeviren tek kaynak.
   ---------------------------------------------------------------------
   Palet döngüsü (`GRAFIK_RENK[i % n]`) rengi kimlik olarak kullanıyordu:
   renk yalnızca "bu, diğerinden başka bir kurum" diyordu. Burada renk
   BİLGİ taşır — listedeki konum. En üstteki koyu yeşil, en alttaki koyu
   kırmızı; aradakiler sürekli bir geçiş.

   HSL kullanılır çünkü tek eksende (ton) yürümek gerekiyor: 145° yeşil,
   0° kırmızı. Doygunluk ve açıklık dar bir bantta tutulur, yoksa orta
   sıradaki sarı-yeşiller koyu temada okunmaz hale gelir. */
function siraRengi(i, n) {
  const t = n > 1 ? i / (n - 1) : 0;         // 0 = en üst, 1 = en alt
  const ton = 145 - 145 * t;                 // yeşil → sarı → turuncu → kırmızı
  /* Ortadaki tonlar (sarı ~60°) doğal olarak daha parlak görünür;
     açıklığı orada bir miktar düşürmek sıçramayı engeller. */
  const orta = 1 - Math.abs(t - 0.5) * 2;    // uçlarda 0, ortada 1
  const doygunluk = 62 - 8 * orta;
  const acikli = 44 - 6 * orta;
  return `hsl(${ton.toFixed(0)} ${doygunluk.toFixed(0)}% ${acikli.toFixed(0)}%)`;
}

/* Eksen etiketinin metin karşılığı — dipnotta da aynı biçim kullanılsın. */
function _bicimEksen(v, mod) {
  return mod === "occupancy" ? "%" + Math.round(v) : fmt.int(v);
}

function yilTrendGrafigi(yillar, kurumlar, opt = {}) {
  /* Üç kip: kontenjan (adet), doluluk (%), sıralama (konum). */
  const mod = ["quota", "success_rank"].includes(opt.mod) ? opt.mod : "occupancy";
  const sira = mod === "success_rank";
  const hepsi = kurumlar || [];
  /* İKİ AYRI KÜME.
     `K`        seçilen bölümde ÖLÇÜLEN kurumlar → çizgi + düğme.
     `yokListe` bu bölümü hiç açmamış kurumlar → YALNIZCA düğme.

     Bunları listeden tamamen düşürmek "13 kurum" yazıp neden 19 değil
     olduğunu söylememek olurdu. Sıfır yazmak ise çok daha kötü: kurum
     "kontenjanı boş kalmış" gibi okunurdu. Bu yüzden görünürler ama
     SAYILARI YOKTUR; tıklanınca neden olmadığını söylerler. */
  const deger = s => s[mod === "quota" ? "quota"
    : sira ? "success_rank" : "occupancy_percent"];
  const K = hepsi.filter(k => (k.series || []).some(s => _sayiVar(deger(s))));
  const yokListe = hepsi.filter(k => k.has_program === false
    || !(k.series || []).length);
  if (!yillar.length || !K.length) {
    return bekleniyorGovde(opt.bos || "Bu bölüm için yıllık kayıt yok.");
  }
  /* SEÇİM SINIRI KALDIRILDI.
     Eskiden 5'ti; gerekçe okunabilirlikti. Ancak kullanıcı tüm evreni
     birden görmek isteyebiliyor ve sınır bunu imkânsız kılıyordu. Artık
     varsayılan sınır kurum sayısıdır (yani sınırsız); `opt.enFazla`
     verilirse ona uyulur. Okunabilirlik kaygısı, başlangıçta yalnızca
     birkaç çizginin AÇIK gelmesiyle karşılanır — kullanıcı istediğini
     ekler. */
  const enFazla = opt.enFazla || K.length;

  const tumu = K.flatMap(k => (k.series || []).map(deger)).filter(_sayiVar).map(Number);
  /* Doluluk ekseni 0'dan başlar ve normalde 100'de biter: %98 ile %100
     arasındaki farkı ekranın tamamına yayıp "iki kat" gibi göstermek
     yanıltıcı olurdu. Ancak ek yerleştirme yüzünden doluluk 100'ü
     AŞABİLİR (ör. %101,8); o zaman eksen gerçek tepeye kadar uzar,
     yoksa çizgi tavana yapışıp fazlalık görünmez olurdu. */
  const tepe = tumu.length ? Math.max(...tumu) : 0;
  /* SIRALAMA EKSENİ TERSTİR ve SIFIRDAN BAŞLAMAZ.
     ------------------------------------------------------------------
     Başarı sırasında KÜÇÜK olan iyidir. Eksen normal çizilseydi en
     başarılı kurum en dipte görünürdü — grafiğin söylediği ile gerçeğin
     tam tersi. Bu yüzden `y()` sıralama kipinde ters çevrilir ve yukarı
     "daha iyi" demek olur.

     Sıfırdan başlamak da yanlış olurdu: sıralamalar 15.000-400.000
     aralığında gezinir, 0 tabanı tüm çizgileri üst şeride yapıştırıp
     aralarındaki farkı görünmez yapardı. Taban, en iyi sıranın biraz
     altına alınır. */
  const dip = tumu.length ? Math.min(...tumu) : 0;
  const pay = sira ? Math.max(1, (tepe - dip) * 0.12) : 0;

  /* SIFIR TABANI KURAL, SIKIŞIKLIK İSTİSNA.
     ------------------------------------------------------------------
     Doluluk ve kontenjan ekseni normalde 0'dan başlar; başlamazsa iki
     yakın değer arasındaki fark ekranın tamamına yayılır ve "iki katı"
     gibi okunur. Bu yüzden sıfır tabanı varsayılan kalır.

     Ama tüm çizgiler dar bir banda sıkışırsa (ör. doluluk %79-%125
     arası, eksen 0-125) grafiğin %63'ü boş kalır ve kurumlar birbirine
     yapışır — o zaman grafik hiçbir şey anlatmaz. İSTİSNA yalnızca bu
     durumda uygulanır: veri yayılımı eksenin dörtte birinden darsa
     taban veriye yaklaştırılır.

     Ölçüt YAYILIM DEĞİL, VERİNİN ALTINDA KALAN BOŞLUKTUR. İlk deneme
     "yayılım eksenin dörtte birinden darsa" idi ve ekrandaki asıl vakayı
     kaçırdı: doluluk %79-125 aralığında yayılım 46, eksen 125, oran 0,37
     — eşiğin üstünde, ama grafiğin alt %63'ü boş ve çizgiler üst şeride
     yapışmış durumda. Doğru soru "değerler birbirine mi yakın" değil,
     "eksenin ne kadarı boşa gidiyor".

     Yayılım geniş olduğunda (0'dan başlayan veri) taban zaten veriye
     yakındır ve hiçbir şey değişmez; yani "her zaman değil, hepsi
     sıkışıksa" davranışı korunur.

     Daraltma yapıldığında `eksenDaraldi` işaretlenir ve grafiğin altında
     söylenir: kesilmiş eksen, söylenmezse farkları abartır. */
  const _BOS_ALT_ESIK = 0.35;      // eksenin alt üçte biri boşsa daralt
  const yayilim = tepe - dip;
  const tamUst = mod === "quota" ? Math.max(1, tepe)
    : Math.max(100, Math.ceil(tepe / 5) * 5);
  const eksenDaraldi = !sira && tumu.length > 1 && tamUst > 0
    && yayilim > 0 && dip / tamUst > _BOS_ALT_ESIK;

  const enUst = sira ? tepe + pay
    : eksenDaraldi ? Math.ceil((tepe + yayilim * 0.15) / 5) * 5
      : tamUst;
  const enAlt = sira ? Math.max(0, dip - pay)
    : eksenDaraldi ? Math.max(0, Math.floor((dip - yayilim * 0.15) / 5) * 5)
      : 0;

  const G = 560, Y = Math.max(190, opt.yukseklik || 210);
  const SOL = 40, SAG = 14, UST = 12, ALT = 26;
  const gw = G - SOL - SAG, gh = Y - UST - ALT;
  const x = i => SOL + (yillar.length === 1 ? gw / 2 : (gw * i) / (yillar.length - 1));
  const oran = v => (Number(v) - enAlt) / (enUst - enAlt || 1);
  /* Sıralamada eksen ters: küçük sıra YUKARIDA. */
  const y = v => sira ? UST + gh * oran(v) : UST + gh - gh * oran(v);

  let s = "";
  const kademe = [0, .25, .5, .75, 1].map(f =>
    Math.round(enAlt + (enUst - enAlt) * f));
  [...new Set(kademe)].forEach(v => {
    s += `<line x1="${SOL}" y1="${y(v).toFixed(1)}" x2="${G - SAG}" y2="${y(v).toFixed(1)}"
            stroke="var(--cizgi)" stroke-width=".6" ${
            v === enAlt && !sira ? "" : 'stroke-dasharray="3 4"'}
            opacity=".7"/>
          <text x="${SOL - 6}" y="${(y(v) + 3.2).toFixed(1)}" text-anchor="end"
            fill="var(--sonuk)" font-size="8.5">${
            mod === "occupancy" ? v : fmt.int(v)}</text>`;
  });
  yillar.forEach((yl, i) => {
    s += `<text x="${x(i).toFixed(1)}" y="${UST + gh + 15}" text-anchor="${
            i === 0 ? "start" : i === yillar.length - 1 ? "end" : "middle"}"
            fill="var(--metin-2)" font-size="9.5">${esc(String(yl))}</text>`;
  });

  /* Renk artık kimlik değil KONUM bildirir; kendi kurumumuz da bu
     kuralın dışında değil. Referans kurumu ayırt etmeyi renk yerine
     kalın çizgi, büyük nokta ve künyedeki `.biz` vurgusu üstlenir —
     böylece "ABÜ hangi renk" sorusu "ABÜ kaçıncı sırada" sorusunun
     cevabını gizlemez. */
  const renkAl = (k, i) => siraRengi(i, K.length);
  const bizIdx = K.findIndex(k => k.is_home_institution);
  const acik = new Set();
  if (bizIdx >= 0) acik.add(bizIdx);
  for (let i = 0; i < K.length && acik.size < Math.min(enFazla, 3); i++) acik.add(i);

  const cizgiler = K.map((k, ki) => {
    const renk = renkAl(k, ki);
    let d = "", kop = true, noktalar = "";
    yillar.forEach((yl, i) => {
      const sr = (k.series || []).find(z => z.year === yl);
      const v = sr ? deger(sr) : null;
      if (!_sayiVar(v)) { kop = true; return; }
      const px = x(i), py = y(v);
      d += `${kop ? "M" : "L"}${px.toFixed(1)},${py.toFixed(1)} `;
      kop = false;
      /* İPUCU: hem kontenjan hem yerleşen hem doluluk — mod ne olursa
         olsun üçü birlikte okunur. Eksik alan "veri yok" yazar. */
      const yok = "veri yok";
      const ipucu = `${k.university_name}\n${opt.programAdi || ""}\n${yl}\n`
        + `Kontenjan: ${_sayiVar(sr.quota) ? fmt.int(sr.quota) : yok}\n`
        + `Yerleşen: ${_sayiVar(sr.placed) ? fmt.int(sr.placed) : yok}\n`
        + `Doluluk: ${_sayiVar(sr.occupancy_percent)
            ? "%" + fmt.dec(sr.occupancy_percent, 1) : yok}\n`
        + `Başarı sırası: ${_sayiVar(sr.success_rank)
            ? fmt.int(sr.success_rank) : yok}`;
      noktalar += `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}"
          r="${k.is_home_institution ? 3.8 : 3}" fill="${renk}"
          stroke="var(--yuzey)" stroke-width="1.2" pointer-events="none"/>
        <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="10" fill="transparent"
          data-ipucu="${esc(ipucu)}"><title>${esc(ipucu)}</title></circle>`;
    });
    return `<g class="mp-seri${k.is_home_institution ? " biz" : ""}" data-i="${ki}"
      data-acik="${acik.has(ki) ? 1 : 0}">
      <path d="${d.trim()}" fill="none" stroke="${renk}"
        stroke-width="${k.is_home_institution ? 2.6 : 1.6}"
        stroke-linejoin="round" stroke-linecap="round"/>${noktalar}</g>`;
  }).join("");

  const kisalt = a => String(a).replace(/\s*ÜNİVERSİTESİ\s*$/i, "")
                              .replace(/\s*ÜNİVERSİTES$/i, "");
  const dugmeler = K.map((k, ki) => `<button type="button" class="mp-btn${
      k.is_home_institution ? " biz" : ""}" data-mp-kurum="${ki}"
      aria-pressed="${acik.has(ki) ? "true" : "false"}"
      title="${esc(k.university_name)}"
      style="--mp-renk:${renkAl(k, ki)}"><i></i>${esc(kisalt(k.university_name))}</button>`).join("");
  /* AYRI SATIR. Aynı kaydırılabilir kutuya konsaydı 14 veri düğmesinin
     arkasında kalır ve kullanıcı hiç göremezdi. */
  const yokDugmeleri = yokListe.map(k => {
        /* Uyarı metni SUNUCUDAN gelen kanıta dayanır: muadil varsa adı
           yazılır, yoksa "muadili de yok" denir. Tahmin yapılmaz. */
        const m = k.equivalent;
        const mesaj = m
          ? `${k.university_name}: bu bölüm yok. Muadil bölüm: ${m.label}.`
          : `${k.university_name}: bu bölüm ve muadili yok, çizgi oluşturulmadı.`;
        return `<button type="button" class="mp-btn yok" data-mp-yok="${esc(mesaj)}"
          aria-disabled="true" title="${esc(mesaj)}"><i></i>${
          esc(kisalt(k.university_name))}${m ? " ≈" : ""}</button>`;
      }).join("");

  return `<div class="mprofil ytrend" data-mp-renkli data-mp-max="${enFazla}"${
      opt.evrenId ? ` data-mp-evren="${opt.evrenId}"` : ""}>
    <svg viewBox="0 0 ${G} ${Y}" class="mp-svg yt-svg" preserveAspectRatio="xMidYMid meet"
         role="img" aria-label="Yıllara göre ${
           mod === "quota" ? "kontenjan"
             : sira ? "başarı sırası (yukarısı daha iyi)" : "doluluk"}">${s}${cizgiler}</svg>
    <div class="mp-alt">
      <div class="mp-btnler">${dugmeler}</div>
      <div class="mp-arac">
        <button type="button" class="mp-mini" data-mp-hepsi>Tümünü Aç</button>
        <button type="button" class="mp-mini" data-mp-kapat>Tümünü Kapat</button>
        <button type="button" class="mp-mini" data-mp-benzer>Benzerleri Göster</button>
        <span class="mp-uyari" role="status"></span>
      </div>
    </div>
    ${yokDugmeleri ? `<div class="mp-yoklar" role="group"
      aria-label="Bu bölümü açmamış kurumlar"><span class="mp-yok-bas">Bu
      bölüm yok:</span>${yokDugmeleri}</div>` : ""}
    ${eksenDaraldi ? `<p class="yt-dipnot eksen">Çizgiler dar bir banda
      toplandığı için dikey eksen sıfırdan değil ${
        _bicimEksen(enAlt, mod)}'den başlatıldı; aradaki farklar bu sayede
      görünür. Kesilmiş eksen farkları olduğundan büyük gösterir —
      değerleri noktaların ipucundan okuyun.</p>` : ""}
    ${/* KARIŞIK GRAIN DİPNOTU — kalıcı, tıklamayla kaybolmaz.
          `.mp-uyari` geçici mesajlar içindir (maksimum-5, bölüm yok) ve
          bir sonraki tıklamada silinir. Bu not ise grafikteki her okuma
          için geçerli olduğundan ayrı ve kalıcı bir satırdır. */
      (opt.karisikYillar || []).length ? `<p class="yt-dipnot">${
        esc(opt.karisikYillar.join(" ve "))} ekip derlemesinden gelir ve
        varyant düzeyindedir: bir bölümün tüm program kodlarının ve burs
        varyantlarının toplamı değil, tek bir varyantıdır. 2025'in
        doluluğu yukarı yanlıdır — kayıtların çoğu burslu kontenjandır ve
        burslu kontenjanlar hemen her zaman dolar.</p>` : ""}
  </div>`;
}

/* ==========================================================================
   METRİK PROFİLİ — X ekseni METRİKLER, her çizgi bir KURUM
   --------------------------------------------------------------------------
   Önceki kurgu terstiydi: X ekseninde kurumlar, çizgilerde metrikler vardı.
   İki ayrı hata üretiyordu:

     1. Kurumlar bir ZAMAN SERİSİ DEĞİLDİR. Soldan sağa inen bir çizgi
        "azalıyor" diye okunuyordu; oysa eksen yalnızca bir sıralama.
     2. Öğrenci sayısı (binler), kadro (yüzler), oran (onlar), bölüm
        (onlar) ve ücret (yüz binler ₺) AYNI Y ekseninde çiziliyordu.
        Ücret serisi diğer dördünü ezip düz çizgiye indiriyordu.

   Yeni kurgu her kurumu kendi PROFİLİ olarak okutur: "bu kurum hangi
   metrikte evrenin neresinde?" Metrikler birbirine göre değil, KENDİ
   İÇİNDE karşılaştırılabilir olsun diye her metrik ayrı ayrı 0–100'e
   normalize edilir.

   100 "EN İYİ" DEMEK DEĞİLDİR — evrendeki en yüksek ham değer demektir.
   Öğrenci/akademisyen oranında ve ücrette yüksek olmak olumlu değildir;
   bu yüzden eksen "başarı"/"performans" diye adlandırılmaz.

   ÖLÇÜLMEMİŞ DEĞER SIFIR SAYILMAZ: devlet üniversitelerinde ücret
   `null` gelir. O nokta çizilmez, çizgi orada kopar; sıfır kabul
   edilseydi kurum "en ucuz" gibi görünürdü.
   ========================================================================== */

/** Bir metriği evren içinde 0–100'e taşır.
 *  `max === min` ise (tek kurum ya da tüm değerler eşit) fark yoktur;
 *  0 ya da 100 demek yanıltıcı olurdu, orta seviye 50 döner. */
function _endeksle(deger, min, maks) {
  if (!_sayiVar(deger)) return null;
  if (!_sayiVar(min) || !_sayiVar(maks)) return null;
  if (maks === min) return 50;
  return ((Number(deger) - min) / (maks - min)) * 100;
}

/** @param kurumlar  [{ad, biz, tur}]
 *  @param metrikler [{ad, birim, bicim, degerler:[kurum sırasıyla ham değer]}]
 *  @param opt       {yukseklik, enFazla, bos} */
function metrikProfili(kurumlar, metrikler, opt = {}) {
  const M = (metrikler || []).filter(m => (m.degerler || []).some(_sayiVar));
  const K = kurumlar || [];
  if (!K.length || M.length < 2) {
    return bekleniyorGovde(opt.bos || "Profil için yeterli metrik yok.");
  }
  const enFazla = opt.enFazla || 5;

  /* --- METRİK BAZINDA NORMALİZASYON ------------------------------------ */
  const olcek = M.map(m => {
    const v = (m.degerler || []).filter(_sayiVar).map(Number);
    return { min: Math.min(...v), maks: Math.max(...v), olculen: v.length };
  });

  const G = 780, Y = Math.max(300, Math.round((opt.yukseklik || 340)));
  const SOL = 46, SAG = 18, UST = 20, ALT = 62;
  const gw = G - SOL - SAG, gh = Y - UST - ALT;
  const x = i => SOL + (M.length === 1 ? gw / 2 : (gw * i) / (M.length - 1));
  const y = e => UST + gh - (gh * e) / 100;

  /* --- IZGARA + Y EKSENİ ------------------------------------------------ */
  let s = "";
  [0, 25, 50, 75, 100].forEach(e => {
    s += `<line x1="${SOL}" y1="${y(e).toFixed(1)}" x2="${G - SAG}" y2="${y(e).toFixed(1)}"
            stroke="var(--cizgi)" stroke-width="${e === 0 ? 1 : .6}"
            ${e === 0 ? "" : 'stroke-dasharray="3 4"'} opacity=".75"/>
          <text x="${SOL - 8}" y="${(y(e) + 3.5).toFixed(1)}" text-anchor="end"
            fill="var(--sonuk)" font-size="9">${e}</text>`;
  });

  /* --- X EKSENİ: METRİK ADLARI, YATAY VE İKİ SATIRA KADAR --------------- */
  M.forEach((m, i) => {
    const kelime = String(m.ad).split(" ");
    const satir = kelime.length > 2
      ? [kelime.slice(0, Math.ceil(kelime.length / 2)).join(" "),
         kelime.slice(Math.ceil(kelime.length / 2)).join(" ")]
      : [m.ad];
    /* İlk ve son etiket ORTALANMAZ: eksenin uçlarında ortalanan metin
       çizim alanının dışına taşıp kırpılıyordu ("Eğitim Ücr…"). Uçlar
       içeri doğru hizalanır, aradakiler ortalanır. */
    const hiza = i === 0 ? "start" : i === M.length - 1 ? "end" : "middle";
    s += `<line x1="${x(i).toFixed(1)}" y1="${UST}" x2="${x(i).toFixed(1)}" y2="${UST + gh}"
            stroke="var(--cizgi)" stroke-width=".6" opacity=".5"/>`;
    satir.forEach((t, j) => {
      s += `<text x="${x(i).toFixed(1)}" y="${UST + gh + 16 + j * 11}" text-anchor="${hiza}"
              fill="var(--metin-2)" font-size="9.5">${esc(t)}</text>`;
    });
    const o = olcek[i];
    if (o.olculen < K.length) {
      s += `<text x="${x(i).toFixed(1)}" y="${UST + gh + 16 + satir.length * 11}"
              text-anchor="${hiza}" fill="var(--sonuk)" font-size="8">${
              o.olculen}/${K.length} ölçüldü</text>`;
    }
  });

  /* --- KURUM ÇİZGİLERİ --------------------------------------------------- */
  const renkAl = (k, i) => k.biz ? "var(--vurgu)"
    : GRAFIK_RENK[(i + 1) % GRAFIK_RENK.length];

  /* Varsayılan açık küme: kendi kurumumuz HER ZAMAN, sonra listenin
     başındaki akranlar. Liste büyüklüğe göre sıralı geldiği için ilk
     sıradakiler en anlamlı kıyas adaylarıdır. */
  const bizIdx = K.findIndex(k => k.biz);
  const acik = new Set();
  if (bizIdx >= 0) acik.add(bizIdx);
  for (let i = 0; i < K.length && acik.size < Math.min(enFazla, 3); i++) acik.add(i);

  const cizgiler = K.map((k, ki) => {
    const renk = renkAl(k, ki);
    const nokta = M.map((m, mi) => {
      const ham = (m.degerler || [])[ki];
      const e = _endeksle(ham, olcek[mi].min, olcek[mi].maks);
      return e === null ? null : { x: x(mi), y: y(e), e, ham, m };
    });
    /* Ölçülmeyen noktada çizgi KOPAR — düz bir çizgiyle atlanmaz. */
    let d = "", ac = true;
    nokta.forEach(n => {
      if (!n) { ac = true; return; }
      d += `${ac ? "M" : "L"}${n.x.toFixed(1)},${n.y.toFixed(1)} `;
      ac = false;
    });
    const kalin = k.biz ? 2.8 : 1.7;
    const r = k.biz ? 4.2 : 3.2;
    const noktaHtml = nokta.filter(Boolean).map(n => {
      /* İPUCUNDA HAM DEĞER TAM HÂLİYLE YAZILIR.
         Eksen üzerindeki kısaltma ("493B ₺") yer kazanmak içindir;
         ipucunda okunması gereken sayının kendisidir. `tamBicim`
         varsa o kullanılır, yoksa eksen biçimi. Birim yalnızca hiçbir
         biçimleyici yokken eklenir — aksi hâlde "493B ₺ ₺" çıkardı. */
      const deger = n.m.tamBicim ? n.m.tamBicim(n.ham)
        : n.m.bicim ? n.m.bicim(n.ham)
        : formatChartValue(n.ham, {}) + (n.m.birim ? " " + n.m.birim : "");
      const ipucu = `${k.ad}\n${n.m.ad}\n${deger}\nKarşılaştırma Endeksi: ${
        Math.round(n.e)} / 100`;
      return `<circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="${r}"
        fill="${renk}" stroke="var(--yuzey)" stroke-width="1.4"
        pointer-events="none"/>
        <circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="11" fill="transparent"
          data-ipucu="${esc(ipucu)}"><title>${esc(ipucu)}</title></circle>`;
    }).join("");
    return `<g class="mp-seri${k.biz ? " biz" : ""}" data-i="${ki}"
      data-acik="${acik.has(ki) ? 1 : 0}">
      <path d="${d.trim()}" fill="none" stroke="${renk}" stroke-width="${kalin}"
        stroke-linejoin="round" stroke-linecap="round"/>
      ${noktaHtml}</g>`;
  }).join("");

  /* --- KURUM DÜĞMELERİ (gösterge yerine seçim alanı) -------------------- */
  const dugmeler = K.map((k, ki) => `<button type="button" class="mp-btn${
      k.biz ? " biz" : ""}" data-mp-kurum="${ki}"
      aria-pressed="${acik.has(ki) ? "true" : "false"}"
      style="--mp-renk:${renkAl(k, ki)}"><i></i>${esc(k.ad)}</button>`).join("");

  return `<div class="mprofil" data-mp-max="${enFazla}">
    <div class="not mp-eksen">Karşılaştırma Endeksi — her metrik bu evrende
      ayrı ayrı 0–100'e ölçeklenmiştir. <b>100 “en iyi”, 0 “kötü” demek
      değildir</b>: 100 evrendeki en yüksek, 0 en düşük ham değerdir.
      Öğrenci/akademisyen oranında ve ücrette yüksek olmak olumlu değildir.
      Gerçek değerler noktaların ipucunda ve aşağıdaki tabloda.</div>
    <svg viewBox="0 0 ${G} ${Y}" class="mp-svg" preserveAspectRatio="xMidYMid meet"
         role="img" aria-label="Kurumların metrik profili">${s}${cizgiler}</svg>
    <div class="mp-alt">
      <div class="mp-btnler">${dugmeler}</div>
      <div class="mp-arac">
        <button type="button" class="mp-mini" data-mp-kapat>Tümünü Kapat</button>
        <button type="button" class="mp-mini" data-mp-benzer>Benzerleri Göster</button>
        <span class="mp-uyari" role="status"></span>
      </div>
    </div>
  </div>`;
}

/* Seçim işleyicisi DELEGE edilir ve YALNIZCA tıklanan kutunun kendi
   `.mprofil` kabında çalışır. Bu yüzden ⛶ Büyüt panelin gövdesini
   kopyaladığında modaldeki düğmeler de sorunsuz çalışır: dışarıda
   tutulan bir durum nesnesi yoktur, açık/kapalı bilgisi DOM'un
   kendisindedir (`data-acik`, `aria-pressed`). */
/* RENK, AÇIK ÇİZGİLERE GÖRE CANLI DAĞITILIR.
   ---------------------------------------------------------------------
   Renk çizim anında sabitlenirse, 19 kurumun 4'ü açıkken açık olanlar
   gradyanın rastgele yerlerinden renk alır: ikinci sıradaki kurum
   kırmızı görünür, çünkü kırmızı ona değil listenin 19'uncusuna aitti.
   Renk konumu anlatacaksa, konum DEĞİŞTİĞİNDE rengin de değişmesi
   gerekir.

   Bu yüzden gradyan yalnızca O AN AÇIK olan çizgiler arasında paylaşılır
   ve her açma/kapamada yeniden hesaplanır. Sıra DOM sırasıdır; o da
   sunucunun sıralamasıdır (son yılın kontenjanına göre büyükten küçüğe).

   Kaynak `data-mp-renkli` ile işaretli kaplarda çalışır — endeks profili
   gibi rengi kimlik olarak kullanan grafikler etkilenmez. */
function mpRenkleriDagit(kap) {
  if (!kap || !kap.hasAttribute("data-mp-renkli")) return;
  const acik = [...kap.querySelectorAll('.mp-seri[data-acik="1"]')];

  /* SIRALAMA EKRANDAKİ KONUMA GÖREDİR, VERİ SIRASINA GÖRE DEĞİL.
     ------------------------------------------------------------------
     Önceki sürüm DOM sırasını kullanıyordu; o da sunucunun sıralamasıydı
     (son yılın KONTENJANI, büyükten küçüğe). Ama grafikte çizilen şey
     doluluk yüzdesi ya da başarı sırası. Kontenjanı en büyük kurumun
     doluluğu en yüksek olmak zorunda değil — bu yüzden yeşil, ekranda
     ortalarda duran bir çizgiye düşüyordu ve renk rastgele görünüyordu.

     Doğrusu: çizginin gerçekten NEREDE durduğuna bakmak. Bunu veriden
     yeniden hesaplamak yerine çizilmiş noktaların `cy` değerlerinden
     okuyoruz — SVG koordinatında küçük `cy` yukarı demektir. Bu yöntem
     eksen ters çevrilmiş olsa bile (sıralama grafiği) doğru çalışır,
     çünkü ters çevirme zaten `cy`'ye yansımıştır.

     Çizgiler kesişebildiği için tek bir yıl yerine noktaların ORTALAMA
     yüksekliği alınır: "genel olarak yukarıda duran" çizgi yeşil olur. */
  const yukseklik = g => {
    const cy = [...g.querySelectorAll("circle")]
      .filter(c => c.getAttribute("fill") !== "transparent")
      .map(c => parseFloat(c.getAttribute("cy")))
      .filter(v => !Number.isNaN(v));
    return cy.length ? cy.reduce((a, b) => a + b, 0) / cy.length : Infinity;
  };
  acik.sort((a, b) => yukseklik(a) - yukseklik(b));   // küçük cy = yukarıda

  acik.forEach((g, j) => {
    const renk = siraRengi(j, acik.length);
    const yol = g.querySelector("path");
    if (yol) yol.setAttribute("stroke", renk);
    g.querySelectorAll("circle[fill]:not([fill='transparent'])")
      .forEach(c => c.setAttribute("fill", renk));
    const b = kap.querySelector(`[data-mp-kurum="${g.dataset.i}"]`);
    if (b) b.style.setProperty("--mp-renk", renk);
  });
  /* Kapalı çizgilerin künye noktası nötrleşir: kapalıyken renk taşımak
     "bu kurum şu sırada" der ama çizgi ekranda yok — yanıltıcı olur. */
  kap.querySelectorAll('.mp-seri[data-acik="0"]').forEach(g => {
    const b = kap.querySelector(`[data-mp-kurum="${g.dataset.i}"]`);
    if (b) b.style.setProperty("--mp-renk", "var(--sonuk)");
  });
}

/* İlk çizimde de çalışmalı. `doldur()` gövdeyi innerHTML ile yazdığı
   için tek güvenilir kanca DOM değişimini izlemektir. */
if (!window._mpRenkGozcu) {
  window._mpRenkGozcu = new MutationObserver(kayitlar => {
    const kaplar = new Set();
    kayitlar.forEach(k => {
      const h = k.target instanceof Element ? k.target : null;
      if (!h) return;
      h.querySelectorAll
        && h.querySelectorAll("[data-mp-renkli]").forEach(x => kaplar.add(x));
      const kendi = h.closest && h.closest("[data-mp-renkli]");
      if (kendi) kaplar.add(kendi);
    });
    kaplar.forEach(mpRenkleriDagit);
  });
  window._mpRenkGozcu.observe(document.body, { childList: true, subtree: true });
}

if (!window._mpBagli) {
  window._mpBagli = true;
  document.addEventListener("click", e => {
    const kap = e.target.closest && e.target.closest(".mprofil");
    if (!kap) return;
    const uyari = kap.querySelector(".mp-uyari");
    const yaz = t => { if (uyari) uyari.textContent = t || ""; };
    const seriler = kap.querySelectorAll(".mp-seri");
    const dugme = i => kap.querySelector(`[data-mp-kurum="${i}"]`);
    const ac = (i, v) => {
      const g = kap.querySelector(`.mp-seri[data-i="${i}"]`);
      if (g) g.dataset.acik = v ? 1 : 0;
      const b = dugme(i);
      if (b) b.setAttribute("aria-pressed", v ? "true" : "false");
      /* Açık küme değişti → gradyan yeniden dağıtılır. Tek tek çağırmak
         yerine `ac`'nin içine konuldu: hangi düğmeden gelirse gelsin
         (tekil tıklama, Tümünü Aç, Tümünü Kapat) renk güncel kalsın. */
      mpRenkleriDagit(kap);
    };
    const acikSayi = () =>
      kap.querySelectorAll('.mp-seri[data-acik="1"]').length;

    /* VERİ OLMAYAN KURUM — çizgi açılmaz, sebebi aynı uyarı alanına
       aynı biçimde yazılır (maksimum-5 uyarısıyla tek dil). */
    const yokBtn = e.target.closest("[data-mp-yok]");
    if (yokBtn) { yaz(yokBtn.dataset.mpYok); return; }

    const btn = e.target.closest("[data-mp-kurum]");
    if (btn) {
      const i = btn.dataset.mpKurum;
      const suan = btn.getAttribute("aria-pressed") === "true";
      if (!suan && acikSayi() >= Number(kap.dataset.mpMax || 5)) {
        yaz(`Okunabilirlik için en fazla ${
          kap.dataset.mpMax || 5} üniversite karşılaştırılabilir.`);
        return;
      }
      ac(i, !suan); yaz(""); return;
    }
    if (e.target.closest("[data-mp-hepsi]")) {
      /* Tüm çizgileri açar. Sınır kaldırıldığı için bu artık mümkün;
         eskiden 5'te tıkanırdı. */
      seriler.forEach(g => ac(g.dataset.i, true)); yaz(""); return;
    }
    if (e.target.closest("[data-mp-kapat]")) {
      /* Kendi kurumumuz açık kalır: referanssız kıyas okunmaz. */
      seriler.forEach(g => ac(g.dataset.i, g.classList.contains("biz")));
      yaz(""); return;
    }
    if (e.target.closest("[data-mp-benzer]")) {
      /* YENİ BENZERLİK ALGORİTMASI YAZILMAZ. Kurum süzgecini mevcut
         "Benzer Ölçek" kipine alır; evreni backend yeniden kurar ve
         panel kendi akış'ıyla tazelenir. Hangi seçici olduğunu kabın
         kendisi söyler — böylece her kart KENDİ süzgecini değiştirir,
         komşu kartınkine dokunmaz. */
      const sec = document.getElementById(kap.dataset.mpEvren || "krEvren");
      if (sec && sec.value !== "similar") {
        sec.value = "similar";
        sec.dispatchEvent(new Event("change", { bubbles: true }));
        return;
      }
      /* Zaten "Benzer Ölçek" evrenindeyiz: listenin başındaki akranlar
         backend'in benzer bulduklarıdır, sınır kadarını aç. */
      const enFazla = Number(kap.dataset.mpMax || 5);
      let n = 0;
      seriler.forEach(g => {
        const biz = g.classList.contains("biz");
        const al = biz || n < enFazla - 1;
        ac(g.dataset.i, al);
        if (al && !biz) n++;
      });
      yaz("Benzer ölçekli kurumlar seçildi.");
    }
  });
}

function cizgiKarsilastirma(kategoriler, seriler, opt = {}) {
  const gecerli = (seriler || []).filter(s => (s.veri || []).some(_sayiVar));
  if (!kategoriler.length || !gecerli.length) {
    return bekleniyorGovde(opt.bos || "Karşılaştırma için ölçülen metrik yok.");
  }

  const G = 760, Y = opt.yukseklik
    ? Math.max(215, Math.round(opt.yukseklik * .88)) : 255;
  const SOL = 44, SAG = 16, UST = 16;
  const ALT = 54 + Math.min(34, Math.max(...kategoriler.map(k => k.length)) * 1.1);
  const alan = G - SOL - SAG;
  const taban = Y - ALT;
  const n = kategoriler.length;
  const x = i => (n === 1 ? SOL + alan / 2 : SOL + i * alan / (n - 1));
  /* İKİ ÖLÇEK MODU.
     GÖRELİ (varsayılan): her seri kendi en yüksek değerinin yüzdesi
     olarak çizilir. Birimleri farklı metrikleri tek eksende
     kıyaslamanın tek dürüst yolu budur ve mevcut çağıranlar bunu
     kullanır.
     MUTLAK (`opt.mutlak`): tek birimli tek/az serili bir grafikte
     yüzde ekseni yanıltıcıdır — kullanıcı gerçek sayıyı görmek ister.
     Asistanın "line yap" dönüşümü bu modu kullanır. */
  const _mutlak = !!opt.mutlak;
  const _ortakMaks = Math.max(...gecerli.map(s =>
    Math.max(...s.veri.filter(_sayiVar).map(Number), 1)), 1);
  const maks = gecerli.map(s => (_mutlak ? _ortakMaks
    : Math.max(...s.veri.filter(_sayiVar).map(Number), 1)));
  const y = (v, si) => taban - (Number(v) / maks[si]) * (taban - UST);

  let s = "";

  /* Izgara: göreli yüzde. Mutlak sayı yazmak yanlış olurdu — her serinin
     ölçeği ayrı. */
  for (let i = 0; i <= 4; i++) {
    const oran = i / 4;
    const yy = taban - oran * (taban - UST);
    s += `<line x1="${SOL}" y1="${yy}" x2="${G - SAG}" y2="${yy}"
      stroke="var(--cizgi)"/>
      <text x="${SOL - 6}" y="${yy + 3}" text-anchor="end" fill="var(--sonuk)"
        font-size="9">${_mutlak
          ? formatChartValue(oran * _ortakMaks, opt)
          : Math.round(oran * 100) + "%"}</text>`;
  }

  /* Kendi kurumumuz dikey şeritle işaretlenir — on kurum arasında
     "biz neredeyiz" sorusu göz taramasıyla cevaplanmamalı. */
  const vi = Number.isInteger(opt.vurguIndeks) ? opt.vurguIndeks : -1;
  if (vi >= 0 && vi < n) {
    s += `<line x1="${x(vi)}" y1="${UST - 4}" x2="${x(vi)}" y2="${taban}"
      stroke="var(--vurgu)" stroke-width="1.2" stroke-dasharray="3 3"
      opacity=".55"/>`;
  }

  gecerli.forEach((sr, si) => {
    const renk = sr.renk || GRAFIK_RENK[si % GRAFIK_RENK.length];
    const bicim = sr.bicim
      || (v => formatChartValue(v, { ...opt, birim: sr.birim }));
    let d = "";
    let noktalar = "";
    kategoriler.forEach((kat, i) => {
      const v = sr.veri[i];
      if (!_sayiVar(v)) return;               // ölçülmemiş nokta ATLANIR
      const px = x(i), py = y(v, si);
      d += (d ? " L " : "M ") + px.toFixed(1) + " " + py.toFixed(1);
      /* GÖRÜNEN NOKTA ile FARE HEDEFİ ayrıdır.
         Görünen nokta 3,2 piksel; o boyutta bir daireyi fareyle
         yakalamak zor. Üstüne görünmez ve 10 piksellik ikinci bir daire
         konur — ipucunu O taşır. Böylece nokta küçük kalır ama üzerine
         gelmek kolaylaşır. */
      /* İpucu TEK DEĞER DEĞİL, O KURUMUN TÜM SÜTUNU.
         Eskiden her nokta yalnızca kendi sayısını söylüyordu
         ("Bölüm Sayısı · X Üniversitesi: 128"). Oysa kullanıcı bir
         noktaya geldiğinde asıl merak ettiği o kurumun bütünü. Kolonun
         verisi `_ipucuKolon` ile hazırlanıp noktaya iliştirilir;
         `data-ipucu-seri` hangi satırın vurgulanacağını söyler. */
      noktalar += `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}"
        r="${i === vi ? 4.6 : 3.2}" fill="${renk}"
        stroke="var(--yuzey)" stroke-width="1.4" pointer-events="none"/>
        <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="10"
        fill="transparent" data-ipucu-seri="${si}"
        data-ipucu-kolon="${_ipucuKolon(kategoriler, gecerli, i, opt)}"
        ></circle>`;
    });
    if (d) {
      s += `<path d="${d}" fill="none" stroke="${renk}" stroke-width="2"
        stroke-linejoin="round" stroke-linecap="round"/>${noktalar}`;
    }
  });

  /* Kategori etiketleri — uzun kurum adları eğik yazılır. */
  kategoriler.forEach((kat, i) => {
    const px = x(i);
    s += `<text x="${px}" y="${taban + 14}" text-anchor="end"
      fill="${i === vi ? "var(--vurgu)" : "var(--metin-2)"}"
      font-size="9" font-weight="${i === vi ? "700" : "400"}"
      transform="rotate(-32 ${px} ${taban + 14})"
      >${esc(kat.length > 22 ? kat.slice(0, 21) + "…" : kat)}</text>`;
  });
  s += `<line x1="${SOL}" y1="${taban}" x2="${G - SAG}" y2="${taban}"
    stroke="var(--kenar)"/>`;

  return gosterge(gecerli)
    + `<svg viewBox="0 0 ${G} ${Y}" style="width:100%;height:auto"
        role="img" aria-label="Kurumlar arası çoklu metrik karşılaştırması"
        >${s}</svg>`
    + (_mutlak
      ? `<div class="eksen-not">Değerler gerçek ölçekte çizilmiştir; kesin
          sayı noktanın üzerine gelince görünür.</div>`
      : `<div class="eksen-not">Y ekseni GÖRELİDİR: her çizgi kendi en yüksek
        değerinin yüzdesi olarak çizilir (metriklerin birimleri farklı).
        Gerçek sayı noktanın üzerine gelince görünür. Kurumlar ilk metriğe
        göre büyükten küçüğe sıralıdır.</div>`);
}

function yiginCubuk(kategoriler, seriler, opt = {}) {
  const gecerli = (seriler || []).filter(s => (s.veri || []).some(_sayiVar));
  if (!kategoriler.length || !gecerli.length) {
    return bekleniyorGovde(opt.bos || "Grafik için ölçülen değer yok.");
  }
  const G = 720, Y = opt.yukseklik
    ? Math.max(155, Math.round(opt.yukseklik * .74)) : 185;
  const SOL = 54, SAG = 12, UST = 14, ALT = 42;
  const tumu = gecerli.flatMap(s => s.veri).filter(_sayiVar).map(Number);
  const yb = opt.yb || (tumu.every(Number.isInteger)
    ? (v => fmt.int(Math.round(v)))
    : (v => formatChartValue(v, opt)));
  const toplamlar = kategoriler.map((_, i) =>
    gecerli.reduce((t, s) => t + (_sayiVar(s.veri[i]) ? Number(s.veri[i]) : 0), 0));
  const maks = Math.max(...toplamlar, 1) * 1.1;
  const alan = G - SOL - SAG;
  const grupW = alan / kategoriler.length;
  const cubukW = Math.min(64, grupW * 0.6);
  const y = v => UST + (1 - v / maks) * (Y - UST - ALT);

  let s = "";
  for (let i = 0; i <= 4; i++) {
    const v = maks * i / 4;
    s += `<line x1="${SOL}" y1="${y(v)}" x2="${G - SAG}" y2="${y(v)}" stroke="var(--cizgi)"/>
      <text x="${SOL - 6}" y="${y(v) + 3}" text-anchor="end" fill="var(--sonuk)"
            font-size="9">${yb(v)}</text>`;
  }
  kategoriler.forEach((kat, gi) => {
    const x = SOL + gi * grupW + (grupW - cubukW) / 2;
    let birikim = 0;
    gecerli.forEach((sr, si) => {
      const v = _sayiVar(sr.veri[gi]) ? Number(sr.veri[gi]) : null;
      if (v === null) return;
      const y1 = y(birikim + v), y2 = y(birikim);
      const renk = sr.renk || GRAFIK_RENK[si % GRAFIK_RENK.length];
      s += `<rect x="${x}" y="${y1}" width="${cubukW}" height="${Math.max(1, y2 - y1)}"
              fill="${renk}" data-ipucu-seri="${si}"
              data-ipucu-kolon="${
                _ipucuKolon(kategoriler, gecerli, gi, opt, yb)
              }"><title>${esc(sr.ad)} · ${esc(kat)}: ${yb(v)}</title></rect>`;
      if (y2 - y1 > 13) {
        s += `<text x="${x + cubukW / 2}" y="${(y1 + y2) / 2 + 3}" text-anchor="middle"
                 fill="#fff" font-size="8.5">${yb(v)}</text>`;
      }
      birikim += v;
    });
    s += `<text x="${x + cubukW / 2}" y="${y(0) - 0 - (y(0) - y(toplamlar[gi])) - 5}"
             text-anchor="middle" fill="var(--metin-2)" font-size="9"
             >${yb(toplamlar[gi])}</text>
          <text x="${x + cubukW / 2}" y="${Y - ALT + 16}" text-anchor="middle"
             fill="var(--sonuk)" font-size="9">${esc(kat)}</text>`;
  });
  return gosterge(gecerli)
    + `<svg viewBox="0 0 ${G} ${Y}" style="width:100%;height:auto"
            role="img" aria-label="${esc(opt.eksenY || "Yığın dağılım")}">${s}</svg>`
    + (opt.eksenY ? `<div class="eksen-not">Y ekseni: ${esc(opt.eksenY)}
        · sütun üstündeki sayı toplamdır</div>` : "");
}

/* ==========================================================================
   4) YATAY SÜTUN — uzun adlı kategoriler (program listeleri)
   ========================================================================== */
function yatayCubuk(satirlar, opt = {}) {
  const gecerli = (satirlar || []).filter(r => _sayiVar(r.deger));
  if (!gecerli.length) {
    return bekleniyorGovde(opt.bos || "Ölçülen değer yok.");
  }
  const yb = opt.yb || (v => formatChartValue(v, opt));
  const maks = Math.max(...gecerli.map(r => Math.abs(Number(r.deger))), 1);
  const renkli = (r, i) => r.renk || GRAFIK_RENK[i % GRAFIK_RENK.length];
  /* Çubuk etiketi yer kazanmak için yuvarlanır ("464B ₺"). Bu yüzden
     TAM DEĞER ipucunda taşınır: aynı sayının başka bir panelde tam
     yazımıyla karşılaştırılabilmesi buna bağlı. `ipucu` verilmezse
     etiketin kendisi kullanılır. */
  return `<div class="ycubuk">${gecerli.map((r, i) => `
    <div class="sat" title="${esc(r.ad)}: ${
      r.ipucu ? esc(r.ipucu) : yb(r.deger) + (opt.birim ? " " + esc(opt.birim) : "")}">
      <span class="ad">${esc(r.ad)}</span>
      <span class="ray"><i style="width:${(Math.abs(Number(r.deger)) / maks * 100).toFixed(1)}%;
        background:${renkli(r, i)}"></i></span>
      <b>${yb(r.deger)}</b>
    </div>`).join("")}</div>`
    + (opt.eksenY ? `<div class="eksen-not">${esc(opt.eksenY)}</div>` : "");
}

/* ==========================================================================
   5) BALONCUK / DAĞILIM GRAFİĞİ (Bubble / Scatter) — çok boyutlu analiz
   ========================================================================== */
function baloncukGrafik(noktalar, opt = {}) {
  const gecerli = (noktalar || []).filter(n => _sayiVar(n.x) && _sayiVar(n.y));
  if (!gecerli.length) {
    return bekleniyorGovde(opt.bos || "Dağılım grafiği için ölçülen değer yok.");
  }
  const G = 760, Y = opt.yukseklik
    ? Math.max(180, Math.round(opt.yukseklik * .74)) : 215;
  const SOL = 72, SAG = 36, UST = 24, ALT = 46;
  const xs = gecerli.map(n => Number(n.x)), ys = gecerli.map(n => Number(n.y));
  const sizes = gecerli.map(n => Number(n.size || 100));

  const pad = (a, b) => (a === b ? Math.abs(a || 1) * 0.2 : (b - a) * 0.14);
  let x0 = Math.min(0, Math.min(...xs)), x1 = Math.max(105, Math.max(...xs));
  let y0 = Math.min(0, Math.min(...ys)), y1 = Math.max(10, Math.max(...ys));
  const px = pad(x0, x1), py = pad(y0, y1);
  x1 += px; y1 += py;

  const X = v => SOL + (Number(v) - x0) / (x1 - x0 || 1) * (G - SOL - SAG);
  const Yc = v => UST + (y1 - Number(v)) / (y1 - y0 || 1) * (Y - UST - ALT);

  const minSz = Math.min(...sizes), maxSz = Math.max(...sizes, 1);
  const R = s => 7 + (Number(s) - minSz) / (maxSz - minSz || 1) * 16;

  let s = "";
  // Y ızgarası
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (y1 - y0) * i / 4;
    s += `<line x1="${SOL}" y1="${Yc(v)}" x2="${G - SAG}" y2="${Yc(v)}" stroke="var(--cizgi)"/>
      <text x="${SOL - 7}" y="${Yc(v) + 3}" text-anchor="end" fill="var(--sonuk)"
            font-size="9">${v.toFixed(1).replace(".0", "")}</text>`;
  }
  // X ızgarası
  for (let i = 0; i <= 4; i++) {
    const v = x0 + (x1 - x0) * i / 4;
    s += `<line x1="${X(v)}" y1="${UST}" x2="${X(v)}" y2="${Y - ALT}" stroke="var(--cizgi)"/>
      <text x="${X(v)}" y="${Y - ALT + 14}" text-anchor="middle" fill="var(--sonuk)"
            font-size="9">${Math.round(v)}%</text>`;
  }

  // Referans çizgileri (ör. X=100 kapasite sınırı)
  (opt.referansCizgileri || []).forEach(ref => {
    if (ref.axis === "x" && _sayiVar(ref.value)) {
      const rx = X(ref.value);
      s += `<line x1="${rx}" y1="${UST}" x2="${rx}" y2="${Y - ALT}" stroke="var(--kotu, #f2545b)"
              stroke-width="1.8" stroke-dasharray="4 4"/>
            <text x="${rx}" y="${UST - 7}" text-anchor="middle" fill="var(--kotu, #f2545b)"
                  font-size="8.5" font-weight="600">${esc(ref.label || "Kapasite Sınırı (%100)")}</text>`;
    }
  });

  // Noktalar / Baloncuklar
  gecerli.forEach((n, i) => {
    const cx = X(n.x), cy = Yc(n.y), r = R(n.size);
    const isExcess = n.is_excess || Number(n.x) > 100;
    const fillRenk = isExcess ? "rgba(242, 84, 91, .65)" : "rgba(76, 141, 255, .55)";
    const strokeRenk = isExcess ? "var(--kotu, #f2545b)" : "var(--vurgu, #4c8dff)";

    s += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fillRenk}"
            stroke="${strokeRenk}" stroke-width="${isExcess ? 2.5 : 1.8}">
            <title>${esc(n.tooltip || `${n.label}: X=${n.x}, Y=${n.y}`)}</title>
          </circle>`;
    s += `<text x="${cx}" y="${cy - r - 4}" text-anchor="middle"
            fill="var(--metin)" font-size="8.5" font-weight="580"
            >${esc(n.label.length > 24 ? n.label.slice(0, 23) + "…" : n.label)}</text>`;
  });

  s += `<line x1="${SOL}" y1="${Y - ALT}" x2="${G - SAG}" y2="${Y - ALT}" stroke="var(--kenar)"/>`;
  s += `<line x1="${SOL}" y1="${UST}" x2="${SOL}" y2="${Y - ALT}" stroke="var(--kenar)"/>`;

  const eksenNotu = [
    opt.eksenX ? `X: ${opt.eksenX}` : "",
    opt.eksenY ? `Y: ${opt.eksenY}` : "",
    opt.eksenSize ? `Baloncuk boyutu: ${opt.eksenSize}` : "",
  ].filter(Boolean).join(" · ");

  return `<svg viewBox="0 0 ${G} ${Y}" style="width:100%;height:auto"
              role="img" aria-label="Analitik Baloncuk Dağılım Grafiği">${s}</svg>`
    + (eksenNotu ? `<div class="eksen-not">${esc(eksenNotu)}</div>` : "");
}

/* ==========================================================================
   6) GRAFİK BÜYÜTME — tek, paylaşılan kaplama (modal)
   ==========================================================================

   YAKLAŞIM: VERİYİ DEĞİL, ÇİZİLMİŞ DOM'U BÜYÜTÜRÜZ
   ------------------------------------------------
   Grafiklerin hepsi `viewBox` taşıyan ve `width:100%` ile çizilen SVG'ler.
   Bu yüzden büyütmek için yeniden hesap YAPMAYA GEREK YOK: kartın o an
   ekranda duran gövdesi olduğu gibi büyük bir kaba kopyalanır, SVG kabın
   yeni genişliğine kendiliğinden uyum sağlar.

   Bunun üç doğrudan sonucu var:
     · Modal için YENİ İSTEK ATILMAZ — kapsam/dönem zaten çizilmiş
       hâlin içindedir, ayrışma imkânsızdır.
     · İş mantığı KOPYALANMAZ — başlık, gösterge, eksen notu, değer
       etiketleri ve tooltip'ler aynı düğümlerdir.
     · Pano yeniden çizilmez; açık ekran, kapsam seçimi ve sol menü
       kaydırma konumu dokunulmadan kalır.

   Büyük görünüm GRAFİĞE odaklanır: kartın içindeki "Detayı göster"
   tablosu kopyaya alınmaz (kullanıcı onu normal kartta açabilir).
   ========================================================================== */

/** Aynı anda tek kaplama; ikinci çağrı öncekini kapatır. */
let _acikModal = null;

function grafikModalKapat() {
  if (!_acikModal) return;
  const { kap, oncekiOdak, govdeOverflow, geriYukle } = _acikModal;
  document.removeEventListener("keydown", _acikModal.tus, true);
  if (typeof geriYukle === "function") geriYukle();
  kap.remove();
  // Panonun kaydırması geri açılır (kaydırma KONUMU hiç bozulmadı).
  const govde = document.getElementById("govde");
  if (govde) govde.style.overflowY = govdeOverflow;
  _acikModal = null;
  if (oncekiOdak && oncekiOdak.focus) oncekiOdak.focus();
}

/**
 * @param baslik  Kartın başlığı (aynen taşınır)
 * @param icerik  Kartın gövdesinin HTML'i (zaten çizilmiş hâli)
 * @param not     Panelin açıklama satırı (varsa)
 */
function grafikModalAc(baslik, icerik, not, opt = {}) {
  grafikModalKapat();                       // tek kaplama kuralı

  const kap = document.createElement("div");
  kap.className = "gmodal";
  kap.setAttribute("role", "dialog");
  kap.setAttribute("aria-modal", "true");
  kap.setAttribute("aria-label", baslik || "Grafik");
  kap.innerHTML = `
    <div class="gmodal-kutu" role="document">
      <div class="gmodal-bas">
        <div class="gmodal-baslik">
          <h3>${esc(baslik || "Grafik")}</h3>
          ${not ? `<div class="not">${esc(not)}</div>` : ""}
        </div>
        ${opt.basEkHtml ? `<div class="gmodal-ek-denetim">${opt.basEkHtml}</div>` : ""}
        <button class="gmodal-kapat" type="button" aria-label="Kapat"
                title="Kapat (Esc)">✕</button>
      </div>
      <div class="gmodal-ic">${typeof icerik === "string" ? icerik : ""}</div>
    </div>`;

  /* Modal içeriği yeni DOM'dur: `<title>` etiketleri orada da kendi
     ipucumuza çevrilmeli, yoksa büyütülmüş grafikte yerleşik kutu açılır. */
  if (typeof ipucuHazirla === "function") ipucuHazirla(kap);

  const modalGovde = kap.querySelector(".gmodal-ic");
  if (icerik && typeof icerik === "object" && icerik.nodeType === 1 && modalGovde) {
    modalGovde.classList.add("canli-panel");
    modalGovde.appendChild(icerik);
  }

  /* Panonun arka planda kaymasını engelle. Kaydırılabilir kap `body`
     değil `.govde`; `body` zaten `overflow:hidden`. Konum DEĞİŞTİRİLMEZ,
     yalnızca kaydırma geçici olarak kapatılır. */
  const govde = document.getElementById("govde");
  const govdeOverflow = govde ? govde.style.overflowY : "";
  if (govde) govde.style.overflowY = "hidden";

  const tus = e => {
    if (e.key === "Escape") { e.stopPropagation(); grafikModalKapat(); }
  };
  document.addEventListener("keydown", tus, true);

  kap.addEventListener("click", e => {
    // Dışarı tıklama VE kapat düğmesi
    if (e.target === kap || e.target.closest(".gmodal-kapat")) {
      grafikModalKapat();
    }
  });

  document.body.appendChild(kap);
  _acikModal = {
    kap, tus, govdeOverflow, oncekiOdak: document.activeElement,
    geriYukle: opt.geriYukle, panelId: opt.panelId, panelEl: opt.panelEl,
  };
  const kapatBtn = kap.querySelector(".gmodal-kapat");
  if (kapatBtn) kapatBtn.focus();
  return kap;
}

/**
 * Bir panel kartını büyütür.
 * Kartın O ANKİ gövdesini kopyalar; yeniden veri çekmez, yeniden
 * hesaplamaz. "Detayı göster" bloğu büyük görünüme alınmaz.
 */
function paneliBuyut(panelEl) {
  if (!panelEl) return;
  const baslikSpan = panelEl.querySelector("h3 > span") || panelEl.querySelector("h3");
  const baslik = baslikSpan ? baslikSpan.textContent.replace(/⛶|Büyüt/g, "").trim() : "Grafik";
  const not = (panelEl.querySelector(":scope > .not") || {}).textContent || "";
  const govdeIc = panelEl.querySelector(".govde-ic");
  if (!govdeIc) return;

  const isKarsilastirma = (typeof K !== "undefined" && K.ekran === "karsilastirma")
    || (panelEl.id && ["krCoklu", "krBuyukluk", "krYogunluk", "krSira", "ogKiyas"].includes(panelEl.id))
    || (govdeIc.id && ["krCoklu", "krBuyukluk", "krYogunluk", "krSira", "ogKiyas"].includes(govdeIc.id))
    || !!panelEl.querySelector(".evren-sec");

  let basEkHtml = "";

  /* PANELİN KENDİ SEÇİCİLERİ ÖNCELİKLİDİR.
     ------------------------------------------------------------------
     Aşağıdaki blok modal başlığına `data-evren` / `data-eslesme` taşıyan
     YENİ bir seçici üretiyordu. O nitelikler GENEL süzgeci yazar; oysa
     Karşılaştırmalar ekranındaki kartlar artık kendi yerel durumlarını
     (`data-kr-panel`) kullanıyor. Sonuç: modal içinde filtre değiştirince
     arkadaki genel paneller yenileniyor ama BÜYÜTÜLEN kart yenilenmiyordu;
     kullanıcı küçültüp yeniden büyütmek zorunda kalıyordu.

     Çözüm kopyalamak: panelin başlığındaki gerçek seçiciler olduğu gibi
     modale taşınır, böylece hangi mekanizmaya bağlıysa (yerel ya da
     genel) modalde de AYNI mekanizma çalışır. `id`ler çakışmasın diye
     sonlarına `_m` eklenir; işleyiciler zaten olayın hedefinden okuyor,
     kimlikle çalışmıyor. */
  const basKap = panelEl.querySelector(":scope > .bas, :scope > h3");
  const kendiSeciciler = basKap
    ? Array.from(basKap.querySelectorAll(".evren-sec")) : [];

  /* DENETİMİ GÖVDESİNDE OLAN KART, BAŞLIĞA SAHTE SEÇİCİ İSTEMEZ.
     ------------------------------------------------------------------
     Yıllık kartların (kontenjan, sıralama) Kurum/Bölüm seçicileri
     başlıkta değil GÖVDEDE (`.yt-kontrol`); gövde zaten modale
     kopyalanıyor. Başlıkta `.evren-sec` bulunamadığı için aşağıdaki
     `isKarsilastirma` dalı devreye giriyor ve `data-evren` taşıyan
     GENEL seçiciler üretiyordu. O seçiciler bu kartı değil ekranın
     geri kalanını süzüyor: kullanıcı modalde "Kurum" değiştiriyor,
     baktığı grafik aynı kalıyor, arkadaki paneller değişiyor.

     Gövdesinde kendi denetimi olan kartta başlık eki üretilmez. */
  const govdedeDenetimVar = !!govdeIc.querySelector(".yt-kontrol");
  if (govdedeDenetimVar) {
    basEkHtml = "";
  } else if (kendiSeciciler.length) {
    basEkHtml = kendiSeciciler.map(el => {
      const k = el.cloneNode(true);
      k.querySelectorAll("[id]").forEach(x => {
        const eski = x.id;
        x.id = eski + "_m";
        const lab = k.querySelector(`label[for="${eski}"]`);
        if (lab) lab.setAttribute("for", x.id);
      });
      return k.outerHTML;
    }).join("");
  } else if (isKarsilastirma) {
    const kip = typeof eslesmeKipi === "function" ? eslesmeKipi() : "all_programs";
    const curEvren = typeof K_EVREN !== "undefined" ? K_EVREN : "all";
    const evrenler = typeof KARSILASTIRMA_EVRENI !== "undefined" ? KARSILASTIRMA_EVRENI : [
      { deger: "all", ad: "Tümü" },
      { deger: "state", ad: "Devlet" },
      { deger: "foundation", ad: "Vakıf" },
      { deger: "similar", ad: "Benzer Ölçek" },
    ];
    const eslesmeler = typeof PROGRAM_ESLESTIRME !== "undefined" ? PROGRAM_ESLESTIRME : [
      { deger: "all_programs", ad: "Hepsi" },
      { deger: "same_program", ad: "Aynı Bölümler" },
      { deger: "similar_programs", ad: "Benzer Bölümler" },
    ];
    basEkHtml = `<span class="evren-sec ikili-sec">
      <label for="modal_evren">Kurum:</label>
      <select id="modal_evren" data-evren aria-label="Kurum türü">${
        evrenler.map(o =>
          `<option value="${o.deger}"${o.deger === curEvren ? " selected" : ""}>${
            esc(o.ad)}</option>`).join("")}</select>
      <label for="modal_eslesme">Bölüm:</label>
      <select id="modal_eslesme" data-eslesme aria-label="Bölüm eşleşmesi">${
        eslesmeler.map(o =>
          `<option value="${o.deger}"${o.deger === kip ? " selected" : ""}>${
            esc(o.ad)}</option>`).join("")}</select>
    </span>`;
  }

  /* Etkileşimli gövdeler kopyalanmaz: aynı paylaşılan modal içine geçici
     olarak taşınır ve kapanırken tam yerine döner. Sohbet durumu ve DOM
     kimliği bu nedenle tekil kalır. */
  if (panelEl.dataset.buyutTasi === "1") {
    const ebeveyn = govdeIc.parentNode;
    const yer = document.createComment("buyut-geri-donus");
    ebeveyn.insertBefore(yer, govdeIc);
    const geriYukle = () => {
      if (yer.parentNode) yer.parentNode.insertBefore(govdeIc, yer);
      if (yer.parentNode) yer.remove();
    };
    grafikModalAc(baslik, govdeIc, not.trim(), { geriYukle, basEkHtml, panelId: govdeIc.id, panelEl });
    return;
  }

  const kopya = govdeIc.cloneNode(true);
  if (panelEl.dataset.buyutDetay === "1") {
    kopya.querySelectorAll("details.detay").forEach(d => { d.open = true; });
  } else {
    kopya.querySelectorAll("details.detay").forEach(d => d.remove());
  }
  const modalKap = grafikModalAc(baslik, kopya.innerHTML, not.trim(), {
    basEkHtml, panelId: govdeIc.id, panelEl
  });
  if (govdeIc.id === "aiPanel" || panelEl.classList.contains("ai-panel") || kopya.querySelector(".ai-alan")) {
    if (typeof asistanAkisCiz === "function") asistanAkisCiz();
    if (typeof asistanKur === "function") asistanKur();
    if (modalKap) {
      const modalInput = modalKap.querySelector("textarea");
      if (modalInput) modalInput.focus();
    }
  }
}


/** Kartın gövdesinde büyütüldüğünde anlamlı olacak içerik var mı?
 *
 *  "Detayı göster" İÇİNDEKİLER SAYILMAZ: büyük görünüm grafiğe odaklanır
 *  ve detay bloğunu kopyalamaz. Yalnızca detayın içinde grafik olan bir
 *  kart için düğme göstermek, kullanıcıyı boş bir kaplamaya açardı.
 *  Küçük bağımsız KPI kutuları panel değildir ve düğme almaz. Boş/bekleyen
 *  paneller de elenir; grafik, görünür tablo veya anlamlı analitik kart
 *  grubu taşıyan büyük paneller aynı mevcut modalı kullanır. */
function grafikIceriyorMu(el) {
  if (!el) return false;
  if (el.querySelector(".bekleniyor-govde, .durum.hata, .durum.bos")) return false;
  const aday = [...el.querySelectorAll(
    "svg, .ycubuk, table, .academic-card-grid, .academic-table-wrap, " +
    ".yorum-serit, .data-source-grid, .kpi-serit, .skor, .olcek"
  )];
  return aday.some(d => !d.closest("details"));
}
