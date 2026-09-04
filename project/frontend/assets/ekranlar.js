/* ABÜ KDS — EKRANLAR (hocanın UI tasarımındaki 6 sayfa)
   ==========================================================================
     ozet      → ÖZET TABLO        (Yönetici Özeti / rektör ana sayfası)
     ogrenci   → ÖĞRENCİLER-I
     akademik  → AKADEMİSYENLER
     altyapi   → ALTYAPI KULLANIMI
     finans    → GELİR/GİDER ANALİZİ
     kokpit    → YAPAY ZEKA WHAT-IF KOKPİTİ

   İLKE: hocanın yerleşimi BİREBİR korunur. Verisi olan panel gerçek
   sayıyla dolar; verisi olmayan panel KALDIRILMAZ, "veri kaynağı
   bekleniyor" rozetiyle durur. Hiçbir sayı uydurulmaz, sıfırla
   doldurulmaz.
   ========================================================================== */

/** Öğrenci sayısının kaynağını okunur etikete çevirir.
    Üniversite kapsamında YÖK kayıtlı sayısı, alt kapsamlarda ÖSYM
    yerleştirmelerinden türetilen sayı gösterilir; ikisi farklı
    ölçümlerdir ve kart altında hangisi olduğu YAZILIR. */
const ogrenciKaynagi = k => ({
  yok_kayitli: "YÖK kayıtlı",
  yks_turevi: "ÖSYM türevi",
  /* Öğrenci satırlarından sayım. Eskiden bu durum da "ÖSYM türevi"
     olarak etiketleniyordu; yerleştirme kaydı olmayan bir kurulumda
     dağılım paneli "ÖSYM'den türetildi" derken trend paneli "yerleştirme
     kaydı yok" diyordu. Etiket artık gerçeği söyler. */
  ogrenci_kaydi: "öğrenci kaydı sayımı",
  karisik: "karma kaynak",
}[k] || "kaynak belirtilmemiş");

/* ---------------- ortak küçük grafikler ---------------- */

/** Yatay çubuk listesi. `vurgu` olan satır renklenir. */
function cubukListe(satirlar, opt = {}) {
  const gecerli = satirlar.filter(s => Number.isFinite(Number(s.deger)));
  if (!gecerli.length) return bekleniyorGovde(opt.bos || "Ölçülen değer yok.");
  const maks = opt.maks || Math.max(...gecerli.map(s => Math.abs(Number(s.deger))), 1);
  return `<div style="display:grid;gap:7px">${gecerli.map(s => `
    <div style="display:grid;grid-template-columns:1fr 92px;gap:9px;align-items:center">
      <div style="min-width:0">
        <div style="font-size:.73rem;margin-bottom:3px;overflow:hidden;
                    text-overflow:ellipsis;white-space:nowrap">${esc(s.ad)}</div>
        <div style="height:7px;background:var(--cizgi);border-radius:4px;overflow:hidden">
          <div style="height:100%;border-radius:4px;width:${
            (Math.abs(Number(s.deger)) / maks * 100).toFixed(1)}%;
            background:${s.vurgu ? "var(--vurgu)" : (s.renk || "var(--vurgu-2)")}"></div>
        </div>
      </div>
      <div style="text-align:right;font-size:.76rem;font-weight:${s.vurgu ? 660 : 400}">${
        s.etiket ?? sayi(s.deger)}</div>
    </div>`).join("")}</div>`;
}

/** Çok serili çizgi grafiği (SVG). seriler: [{ad,renk,veri:[]}] */
function cizgi(etiketler, seriler, opt = {}) {
  const gecerli = seriler.filter(s => (s.veri || []).some(v => Number.isFinite(Number(v))));
  if (!etiketler.length || !gecerli.length) {
    return bekleniyorGovde(opt.bos || "Grafik için yeterli veri yok.");
  }
  const G = 640, Y = opt.yukseklik
    ? Math.max(135, Math.round(opt.yukseklik * .74)) : 150;
  const S = 48, Sa = 14, U = 14, A = 26;
  const hepsi = gecerli.flatMap(s => s.veri).map(Number).filter(Number.isFinite);
  const ust = opt.maks ?? ((Math.max(...hepsi) * 1.12) || 1);
  const alt = opt.min ?? Math.min(0, Math.min(...hepsi));
  const x = i => S + i * (G - S - Sa) / Math.max(etiketler.length - 1, 1);
  const y = v => U + (ust - Number(v)) / (ust - alt || 1) * (Y - U - A);
  let s = "";
  for (let i = 0; i <= 4; i++) {
    const v = alt + (ust - alt) * i / 4;
    s += `<line x1="${S}" y1="${y(v)}" x2="${G - Sa}" y2="${y(v)}" stroke="var(--cizgi)"/>
          <text x="${S - 6}" y="${y(v) + 3}" text-anchor="end" fill="var(--sonuk)"
                font-size="9">${opt.yb ? opt.yb(v) : Math.round(v)}</text>`;
  }
  etiketler.forEach((e, i) => {
    s += `<text x="${x(i)}" y="${Y - 7}" text-anchor="middle" fill="var(--sonuk)"
             font-size="9">${esc(e)}</text>`;
  });
  gecerli.forEach(sr => {
    const nk = sr.veri.map((v, i) => Number.isFinite(Number(v)) ? `${x(i)},${y(v)}` : null)
      .filter(Boolean).join(" ");
    s += `<polyline points="${nk}" fill="none" stroke="${sr.renk}" stroke-width="2.2"
            stroke-linejoin="round" stroke-linecap="round"/>`;
    sr.veri.forEach((v, i) => {
      if (!Number.isFinite(Number(v))) return;
      /* Görünen nokta küçük kalır (3,4 px); fare hedefi ayrı ve 10 px.
         İpucu tek değeri değil O YILIN bütün serilerini gösterir. */
      s += `<circle cx="${x(i)}" cy="${y(v)}" r="3.4" fill="${sr.renk}"
              stroke="var(--yuzey)" stroke-width="1.6" pointer-events="none"/>
            <circle cx="${x(i)}" cy="${y(v)}" r="10" fill="transparent"
              data-ipucu-seri="${gecerli.indexOf(sr)}"
              data-ipucu-kolon="${typeof _ipucuKolon === 'function'
                ? _ipucuKolon(etiketler, gecerli, i, opt, opt.yb) : ''}"
              ><title>${esc(sr.ad)} · ${esc(etiketler[i])}: ${
                opt.yb ? opt.yb(v) : v}</title></circle>`;
    });
  });
  const gost = gecerli.map(sr =>
    `<span style="display:inline-flex;align-items:center;gap:5px;margin-right:12px;font-size:.7rem">
      <i style="width:10px;height:3px;border-radius:2px;background:${sr.renk};display:inline-block"></i>
      ${esc(sr.ad)}</span>`).join("");
  return `<div style="margin-bottom:6px">${gost}</div>
    <svg viewBox="0 0 ${G} ${Y}" style="width:100%;height:auto">${s}</svg>`;
}

/** Halka (donut). dilimler: [{ad,deger,renk}] */
function halkaGrafik(dilimler, merkezUst, merkezAlt) {
  const gecerli = dilimler.filter(d => Number(d.deger) > 0);
  if (!gecerli.length) return bekleniyorGovde("Dağılım verisi yok.");
  const toplam = gecerli.reduce((t, d) => t + Number(d.deger), 0);
  const R = 54, C = 2 * Math.PI * R;
  let acc = 0;
  const halkalar = gecerli.map(d => {
    const pay = Number(d.deger) / toplam;
    const dash = `${(pay * C).toFixed(2)} ${(C - pay * C).toFixed(2)}`;
    const ofs = -acc * C;
    acc += pay;
    return `<circle cx="70" cy="70" r="${R}" fill="none" stroke="${d.renk}"
      stroke-width="19" stroke-dasharray="${dash}" stroke-dashoffset="${ofs.toFixed(2)}"
      transform="rotate(-90 70 70)"><title>${esc(d.ad)}: ${sayi(d.deger)}</title></circle>`;
  }).join("");
  return `<div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
    <svg viewBox="0 0 140 140" style="width:140px;height:140px;flex:0 0 140px">
      ${halkalar}
      <text x="70" y="66" text-anchor="middle" fill="var(--sonuk)" font-size="9">${esc(merkezUst || "Toplam")}</text>
      <text x="70" y="84" text-anchor="middle" fill="var(--metin)" font-size="16" font-weight="600">${
        esc(merkezAlt ?? sayi(toplam))}</text>
    </svg>
    <div style="flex:1 1 190px;min-width:0;display:grid;grid-template-columns:minmax(0,1fr);gap:5px">
      ${gecerli.map(d => `<div style="display:flex;align-items:center;gap:7px;font-size:.73rem;min-width:0">
        <i style="width:9px;height:9px;border-radius:2px;background:${d.renk};flex:0 0 9px;display:inline-block"></i>
        <span style="flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
              title="${esc(d.ad)}">${esc(d.ad)}</span>
        <b style="flex:0 0 auto;white-space:nowrap">${sayi(d.deger)}</b>
        <span style="color:var(--sonuk);flex:0 0 46px;text-align:right;white-space:nowrap">${
          yuzde(Number(d.deger) / toplam * 100, 1)}</span></div>`).join("")}
    </div></div>`;
}

/** Yarım daire gösterge (bütçe/skor). */
function gostergeYay(deger, etiket, renk = "var(--iyi)") {
  if (!Number.isFinite(Number(deger))) return bekleniyorGovde("Ölçüm yok.");
  const oran = Math.max(0, Math.min(100, Number(deger))) / 100;
  const R = 62, C = Math.PI * R;
  return `<div style="text-align:center">
    <svg viewBox="0 0 160 92" style="width:100%;max-width:210px">
      <path d="M 18 80 A ${R} ${R} 0 0 1 142 80" fill="none" stroke="var(--cizgi)" stroke-width="14" stroke-linecap="round"/>
      <path d="M 18 80 A ${R} ${R} 0 0 1 142 80" fill="none" stroke="${renk}" stroke-width="14"
        stroke-linecap="round" stroke-dasharray="${(oran * C).toFixed(1)} ${C.toFixed(1)}"/>
      <text x="80" y="70" text-anchor="middle" fill="var(--metin)" font-size="22" font-weight="700">${
        yuzde(deger, 1)}</text>
    </svg>
    <div style="font-size:.72rem;color:var(--sonuk)">${esc(etiket)}</div></div>`;
}

/* Dağılım (konumlandırma) grafiği — ui-kit'teki `dagilimGrafik` kullanılır. */

/** EKSİK VERİ ŞERİDİ
    Kaynağı olmayan göstergeler GİZLENMEZ ama hero alanını da işgal etmez.
    Küçük, ikincil bir şeritte listelenir: yönetici neyin ölçülmediğini
    görür, ekranın üstü ise yalnızca gerçek sayılarla dolar. */
function eksikVeriSeridi(satirlar) {
  return `<div class="eksik-serit">
    <span class="bas">◷ Henüz kaynağı olmayan göstergeler</span>
    ${satirlar.map(([ad, neden]) =>
      `<span class="oge" title="${esc(neden)}">${esc(ad)}</span>`).join("")}
  </div>`;
}

/* ==========================================================================
   EKRAN KAYDI
   ========================================================================== */
const EKRANLAR = {};

/* ==========================================================================
   ADAPTİF PANEL ALTYAPISI — "kıyaslanacak kardeş kalmadığında ne gösterilir?"
   --------------------------------------------------------------------------
   SORUN
   -----
   Alt birim karşılaştıran paneller, kapsam daraldıkça anlamsızlaşıyor:
   bölüm kapsamında `child-breakdown` TEK satır döner (o bölümün tek
   programı) ve panel, üstteki KPI'da zaten yazan sayıyı tek bir çubuk
   hâlinde TEKRAR eder. Kadro panelinde ise o tek satırın kadro alanları
   `null` olduğu için panel "veri kaynağı bekleniyor" kutusuna düşer.
   İkisi de ekranda yer kaplar, hiçbir yeni şey söylemez.

   ÇÖZÜM: BAĞLAMI YUKARI TAŞI
   --------------------------
   Alt birim kıyaslanamıyorsa birim ÜST GRUBUNUN İÇİNDE kıyaslanır:
   bölüm ↔ fakültedeki kardeş bölümler. Veri aynı uçtan, yalnızca ÜST
   kapsamla çekilir; yeni uç, yeni tablo, yeni hesap yoktur.

   TEKRAR YASAĞI — BU MODÜLÜN ASIL KURALI
   --------------------------------------
   Buradan çıkan hiçbir metin HAM DEĞER yazmaz. Ne öğrenci sayısı, ne
   akademisyen sayısı, ne oranın kendisi. Yalnızca o ham değerin
   BAĞLAMI üretilir:
       · kardeşler arasındaki SIRA
       · medyana göre YÜZDE FARK
       · bunlardan türeyen BİRLEŞİK risk/denge yargısı
   Sıra ve medyan farkı sayfanın hiçbir yerinde yoktur; ham değerler ise
   zaten KPI şeridindedir ve burada bir daha yazılmaz.

   ANLAMLI DEĞİLSE GÖSTERME
   ------------------------
   Bir ölçüt ancak kendisi ÖLÇÜLMÜŞSE ve en az 2 kardeşte ölçülmüşse
   kullanılır (tek kardeşle "sıra" veya "medyan" uydurmak olur). Hiçbir
   ölçüt kalmıyorsa panel tamamen GİZLENİR — kocaman bir "veri yok"
   kartı bırakılmaz, ama eksik veriyi örtmek için de analiz uydurulmaz.
   ========================================================================== */

/** Seçili birimin ÜST kapsamı: kardeşlerini getirecek istek parametreleri.
 *  Üniversite kapsamında üst yoktur → `null`. */
function ebeveynKapsami() {
  const bulunan = agac.bul(K.birimId);
  if (!bulunan) return null;
  const zincir = (bulunan.zincir || []).filter(
    n => n.dbId !== undefined && n.dbId !== null);
  const kendi = zincir[zincir.length - 1];
  if (!kendi) return null;                       // üniversite kapsamı
  const ust = {};
  zincir.slice(0, -1).forEach(n => {
    if (n.tur === "fakulte") ust.faculty_id = n.dbId;
    if (n.tur === "bolum") ust.department_id = n.dbId;
  });
  return {
    p: { ...ust, ...(K.donem ? { academic_year: K.donem } : {}) },
    kendiId: kendi.dbId,
    kendiTur: kendi.tur,
    ustAd: zincir.length > 1
      ? birimAdi(zincir[zincir.length - 2].kod, zincir[zincir.length - 2].ad)
      : "üniversite",
    ustKapsamVar: zincir.length > 1,
  };
}

const _medyan = d => {
  const s = d.slice().sort((a, b) => a - b);
  if (!s.length) return null;
  const o = Math.floor(s.length / 2);
  return s.length % 2 ? s[o] : (s[o - 1] + s[o]) / 2;
};

/** Bir ölçüt için göreli konum. Ölçülemiyorsa `null` — uydurma yok.
 *  @param yuksekIyi true ise büyük değer İYİdir (kadro derinliği),
 *                   false ise büyük değer YÜKtür (öğrenci/akademisyen). */
function _konumOlc(olcut, kendiSatir, kardesler) {
  const oku = olcut.oku;
  const kendi = oku(kendiSatir);
  if (!_sayiVar(kendi)) return null;
  const tumu = kardesler.map(oku).filter(_sayiVar).map(Number);
  if (tumu.length < 2) return null;              // sıra/medyan için yetersiz
  const med = _medyan(tumu);
  /* Sıra her zaman "1 = en yüksek değer" olarak hesaplanır; yorumu
     `yuksekIyi` belirler. Böylece sıralama mantığı tek yerde kalır. */
  const sirali = tumu.slice().sort((a, b) => b - a);
  const sira = sirali.indexOf(Number(kendi)) + 1;
  const fark = med ? (Number(kendi) - med) / Math.abs(med) * 100 : null;
  /* Medyanın ±%10 bandı "farksız" sayılır: ölçüm gürültüsünü yönetsel
     sinyal gibi sunmamak için. */
  const yon = fark === null || Math.abs(fark) < 10 ? "esit"
    : (fark > 0) === !!olcut.yuksekIyi ? "iyi" : "riskli";
  return { ad: olcut.ad, sira, toplam: tumu.length, fark, yon,
           birim: olcut.birim || "" };
}

/** Göreli konum panelinin gövdesi. Ham değer YAZMAZ. */
function konumGovdesi(olcutler, kendiSatir, kardesler, opt = {}) {
  const olculer = olcutler
    .map(o => _konumOlc(o, kendiSatir, kardesler))
    .filter(Boolean);
  if (!olculer.length) return null;              // anlamlı analiz yok → gizle

  const rz = y => y === "riskli" ? '<span class="knm-rz rk">dikkat</span>'
    : y === "iyi" ? '<span class="knm-rz iy">güçlü</span>'
    : '<span class="knm-rz es">ortalama</span>';
  const farkYazi = f => f === null ? "medyanla aynı"
    : Math.abs(f) < 10 ? "medyan seviyesinde"
    : `medyanın <b>%${fmt.dec(Math.abs(f), 0)}</b> ${f > 0 ? "üstünde" : "altında"}`;

  const satirlar = olculer.map(m => `
    <div class="knm-sat">
      <span class="knm-ad">${esc(m.ad)}</span>
      <span class="knm-sira">${m.toplam} birim içinde <b>${m.sira}.</b></span>
      <span class="knm-fark">${farkYazi(m.fark)}</span>
      ${rz(m.yon)}
    </div>`).join("");

  /* BİRLEŞİK YARGI — tek tek metriklerde görünmeyen sonuç.
     İki ya da daha fazla riskli sinyal bir arada ise bu, tek bir metriğin
     kötü olmasından farklı bir yönetsel durumdur ve ayrıca söylenir. */
  const riskli = olculer.filter(m => m.yon === "riskli");
  const guclu = olculer.filter(m => m.yon === "iyi");
  /* En fazla üç ölçüt adlandırılır; gerisi "ve N ölçüt daha" olur. Uzun
     "a ve b ve c ve d" zinciri cümleyi okunmaz hâle getiriyordu. */
  const listele = d => {
    const adlar = d.map(x => esc(x.ad.toLocaleLowerCase("tr")));
    const bas = adlar.slice(0, 3);
    const metin = bas.length > 1
      ? bas.slice(0, -1).join(", ") + " ve " + bas[bas.length - 1] : bas[0];
    return adlar.length > 3 ? `${metin} (ve ${adlar.length - 3} ölçüt daha)` : metin;
  };
  const yargi = riskli.length >= 2
    ? { s: "rk", m: `<b>Dengesiz:</b> ${listele(riskli)} birlikte kardeş `
        + "birimlerin gerisinde — tek bir metrik sorunu değil, yapısal bir açık." }
    : riskli.length === 1
    ? { s: "iz", m: `<b>İzlenmeli:</b> ${listele(riskli)} kardeş birimlerden ayrışıyor.` }
    : guclu.length
    ? { s: "iy", m: `<b>Dengeli:</b> ${listele(guclu)} kardeş birimlerin önünde, `
        + "riskli ayrışma yok." }
    : { s: "es", m: "<b>Dengeli:</b> tüm ölçütlerde kardeş birimlerin medyanı seviyesinde." };

  return `<div class="knm">${satirlar}</div>
    <div class="knm-yargi ${yargi.s}">${yargi.m}</div>
    <div class="eksen-not">${esc(opt.not || "")} Karşılaştırma tabanı:
      <b>${esc(opt.ustAd || "üst birim")}</b> içindeki kardeş birimler.
      Bu panel ham değerleri değil, onların bu taban içindeki konumunu
      gösterir; ham değerler sayfanın üst şeridindedir.</div>`;
}

/** Paneli tamamen gizler/geri gösterir (kart iskeleti de kalkar). */
function paneliGoster(kapId, gorunsun) {
  const kap = document.getElementById(kapId);
  const panelEl = kap && kap.closest(".panel");
  if (panelEl) panelEl.style.display = gorunsun ? "" : "none";
}

/* --------------------------------------------------------------------------
   1) ÖZET TABLO — Yönetici Özeti (rektör ana sayfası)
   -------------------------------------------------------------------------- */
EKRANLAR.ozet = {
  baslik: "Hoş Geldiniz, Sayın Rektör",
  altBaslik: "Yönetici Özeti — kurumun bütüncül durumu",
  ciz() {
    return `<div id="ozKpi" class="kpi-serit">${iskeletHtml(2)}</div>
      <div class="izgara-3">
        ${panel("Öğrenci Sayılarının Yıllara Göre Değişimi",
          seviye() === "university"
            ? "YÖK kayıtlı öğrenci sayısı; öğrenim düzeyine göre."
            : "Bu birimin ÖSYM kontenjan ve yerleşen sayıları.",
          iskeletHtml(6), { id: "ozTrend" })}
        ${panel(seviye() === "university" ? "Fakülte / Yüksekokul Öğrenci Dağılımı"
                                          : "Alt Birim Öğrenci Dağılımı",
          "Alt birimlerin öğrenci sayıları; kaynak grafiğin altında yazar.",
          /* Başlık `yukle()` içinde güncellenir: kıyaslanacak alt birim
             kalmadığında panel "üst grup içindeki konum"a dönüşür. */
          iskeletHtml(6), { id: "ozDagilim", basId: "ozDagilimBas" })}
      </div>
      <div class="izgara-3">
        ${panel("Araştırma Performansı", "Proje, yayın, atıf ve patent sayıları.",
          iskeletHtml(4), { id: "ozArastirma" })}
        ${panel("Aktif Uyarılar ve Bildirimler",
          "Gerçek verilerden türetilen operasyonel uyarılar.", iskeletHtml(5), { id: "ozUyari" })}
      </div>
      ${/* BÜYÜK PANELLER KAYNAK YOKSA ÇİZİLMEZ.
            "Bütçe Gerçekleşme" ve "Performans Göstergeleri" panelleri
            ekranın en değerli üçte birini yalnızca "veri bekleniyor"
            demek için kaplıyordu. Backend yetenekleri DURUYOR; sadece
            bu aşamada panel yerine tek satırlık kayıt gösteriliyor.
            Veri geldiğinde paneller geri açılır. */""}
      ${eksikVeriSeridi([
        ["İdari personel", "Personel kayıtlarında idari kadro yok"],
        ["Bütçe gerçekleşme", "Mali dönem ve bütçe kalemleri aktarılmadı"],
        ["Performans göstergeleri", "Stratejik KPI hedef değerleri tanımlanmadı"],
      ])}
      <div class="dip-not">ⓘ Yetkili kayıtlar her zaman önceliklidir; ikincil veya sentetik
        bir değer kullanılırsa kaynağı ilgili kartta açıkça gösterilir.</div>`;
  },
  yukle() {
    const p = kapsam();
    /* HERO ŞERİDİ — YALNIZCA ÖLÇÜLEN GÖSTERGELER
       ------------------------------------------------------------------
       Şeritte daha önce "Toplam İdari Personel" ve "Yıl Sonu Bütçe
       Gerçekleşme Oranı" kartları vardı; ikisinin de kaynağı yok ve
       ekranın en değerli alanını yalnızca "veri bekleniyor" demek için
       işgal ediyorlardı. Kaldırılmadılar, KÜÇÜLTÜLDÜLER: sayfanın
       altındaki "Eksik Veri" şeridine indiler. Böylece ilk satır
       yalnızca gerçek sayı gösterir, eksik olan da gizlenmez. */
    doldur("ozKpi", () => api.get("/api/decision-analytics/executive-overview", p), o => {
      const k = o.staffing || {}, g = o.student_body || {}, m = o.curriculum_load || {};
      /* Kadro seçilen dönemde ölçülmemişse kart SIFIR göstermez ve
         gizlenmez: rozetle durur, ipucunda hangi dönemin eksik olduğu
         yazar. Başka bir yılın kadrosu bu dönemin etiketiyle asla
         gösterilmez. */
      const kadroEksik = k.available === false;
      const kadroNot = k.note || "Bu dönemde kadro kaydı yok";
      const kartlar = [
        kpi("Toplam Öğrenci", sayi(g.student_count),
            ogrenciKaynagi(g.student_count_source),
            { ikon: "👥", renk: "mavi", trend: g.intake_change_percent,
              trendNot: "son kohortta" }),
        kpi("Akademik Personel", sayi(k.academic_staff_count), "aktif kadro",
            { ikon: "🎓", renk: "yesil",
              donemselEksik: kadroEksik, kaynak: kadroNot }),
        kpi("Öğrenci / Akademisyen", ondalik(k.students_per_academic_staff, 1),
            "sınıf yoğunluğu", { ikon: "÷", renk: "mor",
              donemselEksik: kadroEksik, kaynak: kadroNot }),
        kpi("Müfredat Ders Sayısı", sayi(m.curriculum_course_count),
            "tekilleştirilmiş", { ikon: "▤", renk: "pembe",
            kaynak: "Bu kapsamda kanonik müfredat kaydı yok" }),
        kpi("Program Sayısı", sayi((o.breakdown || {}).program_count
              ?? (dugum().metrik || {}).programSayisi),
            "aktif program", { ikon: "◱", renk: "turuncu" }),
      ];
      /* Kalıcı olarak kaynağı olmayan kart hero şeridine ALINMAZ;
         yalnızca SEÇİLEN DÖNEMDE ölçülmemiş olan (`data-donem-eksik`)
         kalır — dönem seçiminin sonucu görünür olmalıdır. */
      return kartlar.filter(h => !/bekleniyor/.test(h) || /data-donem-eksik/.test(h))
        .join("")
        || bekleniyorGovde("Bu kapsamda ölçülen gösterge yok.");
    }, { iskelet: 2 });

    /* ÖĞRENCİ TRENDİ — KAPSAMA GÖRE FARKLI KAYNAK
       ------------------------------------------------------------------
       YÖK kayıtlı öğrenci sayısı YALNIZCA üniversite düzeyinde vardır;
       fakülte/bölüm kırılımı yoktur. Fakülte seçiliyken bu seriyi
       göstermek, ekranda üniversite genelinin sayısını fakültenin
       sayısıymış gibi bırakırdı — sessiz ve tehlikeli bir hata.
       Alt kapsamlarda bu yüzden ÖSYM yerleştirme serisine geçilir; o
       seri gerçekten kapsamla süzülür. Hangi kaynağın kullanıldığı
       panelde açıkça yazar. */
    if (seviye() === "university") {
      doldur("ozTrend", () => api.get("/api/decision-analytics/enrolled-headcount", donemParam()), o => {
        if (!o.available) return bekleniyorGovde(o.note || "Kayıtlı öğrenci verisi yok.");
        const y = o.years || [];
        const duz = ad => y.map(r => (r.by_degree_level || {})[ad] ?? null);
        return cizgi(y.map(r => r.academic_year), [
          { ad: "Toplam", renk: "var(--vurgu)", veri: y.map(r => r.student_count) },
          { ad: "Lisans", renk: "var(--vurgu-2)", veri: duz("Lisans") },
          { ad: "Önlisans", renk: "var(--mor)", veri: duz("Önlisans") },
          { ad: "Yüksek Lisans", renk: "var(--uyari)", veri: duz("Yüksek Lisans") },
        ], { yb: v => fmt.int(Math.round(v)) })
        + `<div class="not" style="margin-top:8px">Kaynak: YÖK kayıtlı öğrenci sayısı.
           Dönem büyümesi: <b style="color:var(--iyi)">${yuzde(o.period_growth_percent, 1)}</b>
           (${esc(o.first_academic_year)} → ${esc(o.latest_academic_year)})</div>`;
      }, { iskelet: 6 });
    } else {
      doldur("ozTrend", () => api.get("/api/decision-analytics/yks-trend", p), o => {
        const y = o.years || [];
        if (!y.length) return bekleniyorGovde("Bu kapsamda yerleştirme kaydı yok.");
        return cizgi(y.map(r => String(r.placement_year)), [
          { ad: "Kontenjan", renk: "var(--mor)", veri: y.map(r => r.quota) },
          { ad: "Yerleşen", renk: "var(--vurgu)", veri: y.map(r => r.placed_students) },
        ], { yb: v => fmt.int(Math.round(v)) })
        + `<div class="not" style="margin-top:8px">Kaynak: ÖSYM yerleştirme kayıtları
           (bu birime ait). YÖK kayıtlı öğrenci sayısının fakülte/bölüm kırılımı
           yayımlanmadığı için bu kapsamda yerleştirme serisi gösterilir.</div>`;
      }, { iskelet: 6 });
    }

    /* ADAPTİF: kıyaslanacak en az 2 alt birim yoksa dağılım grafiği yerine
       birimin ÜST GRUP içindeki konumu gösterilir (bkz. adaptif altyapı). */
    const ustKapsam = ebeveynKapsami();
    doldur("ozDagilim", () => Promise.all([
      api.get("/api/decision-analytics/child-breakdown", p),
      ustKapsam && ustKapsam.ustKapsamVar
        ? api.get("/api/decision-analytics/child-breakdown", ustKapsam.p)
                .catch(() => null)
        : Promise.resolve(null),
    ]), ([o, ustVeri]) => {
      const bas = document.getElementById("ozDagilimBas");
      const kiyaslanabilir = (o.rows || []).filter(r => _sayiVar(r.student_count));
      if (kiyaslanabilir.length < 2) {
        /* TEK BAR YASAK: üstteki KPI'da zaten yazan sayıyı tekrar etmek
           yerine o sayının ÜST GRUP içindeki anlamı gösterilir. */
        const kardesler = (ustVeri && ustVeri.rows) || [];
        const kendi = kardesler.find(r => r.unit_id === (ustKapsam || {}).kendiId);
        const govde = kendi && konumGovdesi([
          { ad: "Öğrenci yükü", oku: r => r.students_per_academic_staff,
            yuksekIyi: false },
          { ad: "Ders yükü", oku: r => r.average_teaching_load_hours,
            yuksekIyi: false },
          { ad: "Kontenjan doluluğu", oku: r => r.occupancy_percent,
            yuksekIyi: true },
          { ad: "Kadro derinliği", oku: r => r.academics_per_100_students,
            yuksekIyi: true },
        ], kendi, kardesler, { ustAd: (ustKapsam || {}).ustAd });
        if (!govde) { paneliGoster("ozDagilim", false); return ""; }
        paneliGoster("ozDagilim", true);
        if (bas) bas.textContent = `${(ustKapsam || {}).ustAd || "Üst Birim"} İçindeki Konum`;
        return govde;
      }
      paneliGoster("ozDagilim", true);
      if (bas) {
        bas.textContent = seviye() === "university"
          ? "Fakülte / Yüksekokul Öğrenci Dağılımı" : "Alt Birim Öğrenci Dağılımı";
      }
      const renkler = ["var(--vurgu)", "var(--vurgu-2)", "var(--mor)", "var(--uyari)",
                       "var(--pembe)", "#46b3e6", "#8fa3bf"];
      /* Etiket kurumsal addan çözülür; analitik ucunun ham adı doğrudan
         ekrana yazılmaz (bkz. kabuk.js `birimAdi`). */
      const dilim = (o.rows || []).filter(r => r.student_count)
        .map((r, i) => ({ ad: birimAdi(r.code, r.name), deger: r.student_count,
                          renk: renkler[i % renkler.length] }));
      /* Merkezdeki sayı "kurumun öğrenci sayısı" DEĞİLDİR: dilimlerin
         toplamıdır ve ÖSYM türevidir. Üniversite kapsamında KPI kartı
         YÖK kayıtlı sayıyı (3.626) gösterirken burada 3.348 yazması,
         etiketlenmezse iki farklı sayı gibi okunur. Etiket bunu açıkça
         söyler; iki ölçüm de korunur, karıştırılmaz. */
      /* KAYNAK SABİT YAZILMAZ.
         Panel eskiden koşulsuz "ÖSYM yerleştirmelerinden türetilen"
         diyordu. Yerleştirme kaydı bulunmayan bir kurulumda bu, hemen
         yanındaki "Bu kapsamda yerleştirme kaydı yok" panelini
         yalanlıyordu. Etiket artık servisin bildirdiği GERÇEK kaynaktan
         gelir. */
      /* KAYNAK VE KIYASLANABİLİRLİK
         ------------------------------------------------------------------
         Bu panel ALT BİRİM satırları gösterir. Üniversite kapsamında bile
         satırların kaynağı ÖSYM yerleştirmeleridir; YÖK kayıtlı öğrenci
         sayısının fakülte kırılımı YOKTUR.

         Canlıda panel "Kaynak: YÖK kayıtlı" yazıyordu (kapsamın yetkili
         ölçümünü kopyalıyordu) ama listelediği değerler ÖSYM türeviydi.
         Üstelik toplam (7.348) üniversite sayısıyla (3.626) tutmuyordu.

         Artık: kaynak SATIRLARDAN gelir ve toplam, kurumun yetkili
         sayısıyla KIYASLANMAZ — iki ölçüm farklı tanımlıdır. */
      const kaynak = ogrenciKaynagi(o.student_count_source);
      const aciklama = {
        "ÖSYM türevi": "her birimin ÖSYM yerleştirme kayıtlarının son ≤4 "
          + "kohort toplamı",
        "öğrenci kaydı sayımı": "öğrenci kayıt satırlarının sayımı "
          + "(bu kapsamda ÖSYM yerleştirme kaydı yok)",
        "karma kaynak": "birimlerin bir kısmı ÖSYM, bir kısmı öğrenci "
          + "kaydı sayımından geliyor",
      }[kaynak] || "kaynak bildirilmedi";
      /* Halka yerine SÜTUN: yönetici birimleri yan yana kıyaslayabilsin.
         Halka yalnızca pay okutur, sütun sıralama da verir. */
      return yatayCubuk(dilim.map(d => ({ ad: d.ad, deger: d.deger, renk: d.renk })),
                        { eksenY: "öğrenci sayısı" })
        + `<div class="not" style="margin-top:8px">
             Kaynak: <b>${esc(kaynak)}</b> — ${esc(aciklama)}.
             ${seviye() === "university" ? `Bu toplam kurumun
               <b>YÖK kayıtlı öğrenci sayısıyla KIYASLANAMAZ</b>: YÖK sayısı
               lisansüstü, yatay geçiş ve DGS ile geleni de kapsar ve
               yalnızca üniversite düzeyinde yayımlanır; bu satırlar ise
               yerleştirmeden türetilmiş alt birim değerleridir.` : ""}
           </div>`;
    }, { iskelet: 6 });

    const arastirmaAnahtarlari = ["citation_count", "project_count", "patent_count"];
    const metrikKapsami = dataSourceScope();
    doldur("ozArastirma", () => Promise.all([
      api.get("/api/decision-analytics/executive-overview", p),
      ...arastirmaAnahtarlari.map(key => dataSourceAvailability(key, metrikKapsami)),
    ]), ([o, ...metrikler]) => {
      const y = o.publication_productivity || [];
      const toplam = y.length
        ? y.reduce((t, r) => t + (r.total_publications || 0), 0)
        : null;
      const metrik = key => metrikler.find(row => row.definition && row.definition.key === key);
      const ikincilKpi = (key, etiket, ikon, renk) => {
        const row = metrik(key);
        const deger = row && row.resolved_value;
        const varMi = deger !== null && deger !== undefined && Number.isFinite(Number(deger));
        const kaynak = varMi ? dataSourceCaption(row) : `${etiket} verisi aktarılmadı`;
        return kpi(etiket, varMi ? sayi(deger) : null, varMi ? esc(kaynak) : null,
          { ikon, renk, kaynak });
      };
      return `<div class="kpi-serit" style="margin:0">
        ${kpi("Yayın Sayısı", sayi(toplam) , "YÖK Akademik", { ikon: "📄", renk: "yesil" })}
        ${ikincilKpi("citation_count", "Atıf Sayısı", "❝", "mavi")}
        ${ikincilKpi("project_count", "Proje Sayısı", "🧪", "mor")}
        ${ikincilKpi("patent_count", "Patent Sayısı", "◉", "turuncu")}
      </div>`;
    }, { iskelet: 4 });

    doldur("ozUyari", () => api.get("/api/decision-analytics/warnings", p), rows => {
      if (!rows.length) return bekleniyorGovde("Bu kapsamda türetilmiş uyarı yok.");
      const ikon = { kritik: "🔴", yuksek: "🔴", orta: "🟡" };
      return rows.map(u => `<div class="uyari-sat">
        <span class="ik">${ikon[u.severity] || "🔵"}</span>
        <div style="flex:1;min-width:0"><b>${esc(u.title)}</b>
          <span>${esc(u.explanation)}</span></div>
        <span class="zaman">${esc(u.severity)}</span></div>`).join("");
    }, { iskelet: 5 });
  },
};

/* --------------------------------------------------------------------------
   2) ÖĞRENCİLER-I
   -------------------------------------------------------------------------- */
EKRANLAR.ogrenci = {
  baslik: "Öğrenciler",
  altBaslik: "Kontenjan, burs kırılımı, talep ve rekabet",
  ciz() {
    const uni = seviye() === "university";
    return `<div id="ogKpi" class="kpi-serit">${iskeletHtml(2)}</div>
      <div class="izgara-3">
        ${panel("Burs Türlerine Göre Kontenjan Doluluk Oranları (%)",
          "ÖSYM yerleştirme kayıtlarından; yıllara göre.", iskeletHtml(6), { id: "ogBursTrend" })}
        ${panel(uni
            ? "Ankara'daki Üniversitelerle Öğrenci Sayısı Karşılaştırması"
            : "Dış Kurum Öğrenci Sayısı Karşılaştırması",
          uni
            ? "YÖK kayıtlı öğrenci sayısı — kurumumuz vurgulanmıştır."
            : "Seçili alt kapsam için yalnızca eşdeğer dış birim verisi kullanılabilir.",
          iskeletHtml(6), { id: "ogKiyas", basId: "ogKiyasBas",
                            notId: "ogKiyasNot",
                            basEk: karsilastirmaSecicileri("ogEvren", "ogEslesme") })}
        ${panel("Alt Birim Karşılaştırması",
          "Öğrenci, kontenjan, yerleşen ve doluluk bir arada.",
          iskeletHtml(6), { id: "ogAltBirim", basId: "ogAltBirimBas" })}
      </div>
      <div class="izgara-3">
        ${panel("Akademik Performans", "Mezuniyet derecesi ve süresi.",
          iskeletHtml(5), { id: "ogAkademikBasari" })}
        ${panel("İstihdam Performansı", "Mezun istihdam oranı ve işe başlama süresi.",
          iskeletHtml(5), { id: "ogIstihdam" })}
        ${panel("Yabancı Öğrenci",
          "Kurumun yetkili yabancı öğrenci sayıları; oran yalnızca uyumlu payda varsa.",
          iskeletHtml(5), { id: "ogYabanci" })}
      </div>
      <div class="izgara-1">
        ${panel("Yapay Zeka Analiz Sonuçları",
          "Aşağıdaki yorumlar ekrandaki gerçek sayılardan kural motoruyla üretilmiştir.",
          iskeletHtml(4), { id: "ogYorum" })}
      </div>`;
  },
  yukle() {
    const p = kapsam();
    const uni = seviye() === "university";
    doldur("ogKpi", () => Promise.all([
      api.get("/api/decision-analytics/student-body", p),
      api.get("/api/decision-analytics/scholarship-breakdown", p),
      api.get("/api/decision-analytics/foreign-students", p),
    ]), ([g, b, y]) => {
      const bul = ad => (b.types || []).find(t => t.scholarship_type === ad);
      const tam = bul("Burslu"), yari = bul("%50 İndirimli"), ucr = bul("Ücretli");
      return kpi("Kontenjan", sayi(g.latest_quota), `${esc(g.latest_placement_year || "")} yerleştirmesi`,
                 { ikon: "◱", renk: "mor" })
        + kpi("Toplam Öğrenci", sayi(g.student_count),
              ogrenciKaynagi(g.student_count_source), { ikon: "👥", renk: "mavi" })
        + kpi("Tam Burslu", sayi(tam && tam.placed_students),
              tam ? `%${ondalik(tam.occupancy_percent, 1)} doluluk` : "", { ikon: "🎓", renk: "yesil" })
        + kpi("%50 Burslu", sayi(yari && yari.placed_students),
              yari ? `%${ondalik(yari.occupancy_percent, 1)} doluluk` : "", { ikon: "◑", renk: "mavi" })
        + kpi("Ücretli", sayi(ucr && ucr.placed_students),
              ucr ? `%${ondalik(ucr.occupancy_percent, 1)} doluluk` : "", { ikon: "₺", renk: "turuncu" })
        + kpi("Başarı Burslu", null, null,
              { ikon: "★", renk: "pembe", kaynak: "Kurum başarı bursu kırılımı yayımlamıyor" })
        + kpi("Yabancı Öğrenci", sayi(y && y.available ? y.student_count : null),
              /* Oran YALNIZCA uyumlu payda varsa yazılır (üniversite
                 düzeyinde YÖK kayıtlı sayı). Alt kapsamlarda sayı
                 gösterilir, oran iddia edilmez. */
              y && y.ratio_available ? `%${ondalik(y.ratio_percent, 2)} · ${esc(y.academic_year)}`
                : (y && y.available ? `${esc(y.academic_year)} · oran ölçülemez` : ""),
              { ikon: "🌐", renk: "kirmizi", donemselEksik: !!(y && !y.available),
                kaynak: (y && y.note) || "Bu dönemde yabancı öğrenci verisi yok" });
    }, { iskelet: 2 });

    doldur("ogAkademikBasari",
      () => api.get("/api/academic-success/overview", p), o => {
        if (!o || !o.measured_student_count) {
          return bekleniyorGovde("Bu kapsam ve dönemde akademik başarı ölçümü yok.");
        }
        return `<div class="kpi-serit" style="margin:0">
          ${kpi("Ders Geçme", yuzde(o.course_pass_rate, 1), "oran", { ikon: "✓", renk: "yesil" })}
          ${kpi("Başarı Puanı", ondalik(o.average_success_score, 1), "100 üzerinden", { ikon: "◆", renk: "mavi" })}
          ${kpi("Öğrenci Kaybı", yuzde(o.dropout_rate, 1), "oran", { ikon: "↘", renk: "kirmizi" })}
          ${kpi("Mezuniyet", yuzde(o.graduation_rate, 1), `${sayi(o.graduate_count)} mezun`, { ikon: "🎓", renk: "mor" })}
        </div>
        <div class="not" style="margin-top:8px">${esc(dataSourceCaption(o))} ·
          ${sayi(o.measured_student_count)} ölçülen öğrenci.</div>`;
      }, { iskelet: 5 });

    doldur("ogIstihdam",
      () => api.get("/api/decision-analytics/student-employment", p), o => {
        if (!o.available) return bekleniyorGovde(o.note || "İstihdam analitiği yok.");
        return `<div class="kpi-serit" style="margin:0">
          ${kpi("Mezun İstihdamı", yuzde(o.graduate_employment_rate, 1),
                `${sayi(o.graduate_count)} mezun tabanı`, { ikon: "▣", renk: "yesil" })}
          ${kpi("6 Ay İçinde", yuzde(o.employment_within_6_months_rate, 1),
                "toplulaştırılmış tahmin", { ikon: "6", renk: "mavi" })}
          ${kpi("12 Ay İçinde", yuzde(o.employment_within_12_months_rate, 1),
                "toplulaştırılmış tahmin", { ikon: "12", renk: "mor" })}
          ${kpi("Alan Uyumlu", yuzde(o.sector_alignment_rate, 1),
                "sektör uyumu", { ikon: "◎", renk: "turuncu" })}
          ${o.regional_employment_rate == null ? "" :
            kpi("Bölgede İstihdam", yuzde(o.regional_employment_rate, 1),
                `${sayi(o.regional_employment_count)} / ${sayi(o.graduate_count)} · türetilmiş`,
                { ikon: "⌖", renk: "kirmizi" })}
        </div>
        <div class="not" style="margin-top:8px">${esc(dataSourceCaption(o))} · ${esc(o.note)}</div>`;
      }, { iskelet: 5 });

    /* YABANCI ÖĞRENCİ
       ------------------------------------------------------------------
       Sayı her kapsamda gerçektir. ORAN yalnızca aynı kapsam + aynı yıl
       + uyumlu nüfus tanımına sahip bir payda varsa gösterilir; bu da
       şu an yalnızca üniversite düzeyinde (YÖK kayıtlı öğrenci sayısı)
       mümkündür. Alt kapsamda 4 yıllık ÖSYM türevi toplama bölmek iki
       farklı ölçümün bölümünü "oran" diye sunmak olurdu. */
    doldur("ogYabanci", () => api.get("/api/decision-analytics/foreign-students", p),
      o => {
        if (!o.available) return bekleniyorGovde(o.note || "Kayıt yok.");
        const ust = `<div class="kpi-serit" style="margin-bottom:10px">
            ${kpi("Yabancı Öğrenci", sayi(o.student_count),
                  esc(o.academic_year), { ikon: "🌐", renk: "kirmizi" })}
            ${kpi("Yabancı Öğrenci Oranı",
                  o.ratio_available ? yuzde(o.ratio_percent, 2) : null,
                  o.ratio_available
                    ? `${sayi(o.student_count)} / ${sayi(o.denominator)} · YÖK kayıtlı`
                    : null,
                  { ikon: "%", renk: "mor",
                    kaynak: o.ratio_note || "Uyumlu payda yok" })}
          </div>`;
        /* Program adları uzun → YATAY sütun. Tablo detaya indi. */
        const dilRenk = { "İngilizce": "var(--vurgu)", "Türkçe": "var(--vurgu-2)" };
        const grafik = yatayCubuk((o.rows || []).map(r => ({
          ad: r.source_program_label, deger: r.student_count,
          renk: dilRenk[r.education_language] || "var(--mor)",
        })), { eksenY: "yabancı öğrenci · renk = eğitim dili" });
        const tablo = `<table>
            <thead><tr><th>Program</th><th>Dil</th><th>Yabancı öğrenci</th></tr></thead>
            <tbody>${(o.rows || []).map(r => `<tr>
              <td style="text-align:left">${esc(r.source_program_label)}</td>
              <td>${esc(r.education_language || "—")}</td>
              <td>${sayi(r.student_count)}</td></tr>`).join("")}</tbody></table>`;
        return ust + grafik + detay("Program tablosunu göster", tablo)
          + `<div class="eksen-not">${esc(o.ratio_note || "")}</div>`;
      }, { iskelet: 5 });

    doldur("ogBursTrend", () => api.get("/api/decision-analytics/scholarship-breakdown", p), o => {
      if (!o.available) return bekleniyorGovde("Yerleştirme kaydı yok.");
      const renk = { "Burslu": "var(--vurgu-2)", "%50 İndirimli": "var(--vurgu)" };
      const yillar = o.years.map(String);
      /* "ÜCRETLİ" SERİSİ BU PANELDE GÖSTERİLMEZ.
         ------------------------------------------------------------------
         Yalnızca SUNUM kararıdır: API yanıtı (`scholarship-breakdown`)
         ve veritabanı olduğu gibi kalır, ücretli öğrenciler başka
         yerlerde (ör. üstteki KPI şeridi) görünmeye devam eder. Süzme
         tek noktada, iki grafiğin de beslendiği `turler` dizisinde
         yapılır; böylece yığın sütun, doluluk sütunu ve lejant
         kendiliğinden aynı kümeyi kullanır ve ⛶ büyütülmüş görünüm de
         (panel gövdesini kopyaladığı için) aynı kümeyi gösterir. */
      const ucretliMi = ad => {
        /* Gerçek veri (`ankara_bilim_yks_4year.csv` → `scholarship_type`)
           tam olarak "Ücretli" yazıyor. Yine de katı eşitlik yerine
           normalize edilmiş karşılaştırma yapılır: Türkçe büyük harf
           dönüşümü ("ı/İ" tuzağı) ve olası "TAM ÜCRETLİ" varyantı
           sessizce süzgeçten kaçmasın. `import_part3.ucret_turu()` de
           aynı yaklaşımı kullanır. */
        const s = String(ad || "")
          .replace(/i/g, "İ").replace(/ı/g, "I").toUpperCase()
          .replace(/[ÜU]/g, "U").replace(/[İI]/g, "I").replace(/Ç/g, "C");
        return s.includes("UCRETLI");
      };
      const turler = (o.types || []).filter(t => !ucretliMi(t.scholarship_type));
      if (!turler.length) return bekleniyorGovde("Burslu/indirimli yerleştirme kaydı yok.");
      /* YIĞIN SÜTUN: yıl başına yerleşen öğrencinin burs kademesine göre
         dağılımı. Doluluk yüzdesi ayrı grafikte; ikisini tek eksende
         göstermek "yüzde" ile "kişi"yi karıştırırdı. */
      const yigin = turler.map(t => ({
        ad: t.scholarship_type, renk: renk[t.scholarship_type] || "var(--mor)",
        veri: o.years.map(y => {
          const s = t.series.find(x => x.placement_year === y);
          return s ? s.placed_students : null;
        }),
      }));
      const doluluk = turler.map(t => ({
        ad: t.scholarship_type, renk: renk[t.scholarship_type] || "var(--mor)",
        veri: o.years.map(y => {
          const s = t.series.find(x => x.placement_year === y);
          return s ? s.occupancy_percent : null;
        }),
      }));
      /* HALKA + TREND YAN YANA.
         Pasta bu panelin TAMAMI olamaz: dört yıl var ve halkanın zaman
         ekseni yoktur — Hukuk'ta "Burslu" üç yıldır sabit 11 kişi, bunu
         yalnızca zaman ekseninde görebilirsin. Ama halkanın DOĞRU olduğu
         bir soru da var: "bu yıl kontenjanın ne kadarı tam burslu?"
         O yüzden ikisi birden: solda son yılın bileşimi, sağda yılların
         seyri. Farklı iki soruyu cevaplıyorlar. */
      const sonYil = o.years[o.years.length - 1];
      const sonDilim = turler.map(t => {
        const s = t.series.find(x => x.placement_year === sonYil);
        return {
          ad: t.scholarship_type,
          deger: s ? s.placed_students : null,
          renk: renk[t.scholarship_type] || "var(--mor)",
        };
      });

      return `<div class="burs-ikili">
          <div class="halka-yan">
            <div class="not">${esc(String(sonYil))} bileşimi</div>
            ${dagilimHalkasi(sonDilim, {
              merkezEtiket: sonYil + " yerleşen",
              bos: "Bu yıl yerleştirme kaydı yok.",
            })}
          </div>
          <div class="trend-yan">
            <div class="not">Yıllara göre yerleşen</div>
            ${yiginCubuk(yillar, yigin, { eksenY: "yerleşen öğrenci" })}
          </div>
        </div>`
        + `<div class="not" style="margin:10px 0 6px">Kontenjan doluluğu (%)</div>`
        + gruplandirilmisCubuk(yillar, doluluk,
            { eksenY: "%", yb: v => Math.round(v) + "%", yukseklik: 210 });
    }, { iskelet: 6 });

    /* ÜNİVERSİTE KAPSAMI — KARŞILAŞTIRMALAR SAYFASIYLA AYNI KAYNAK.
       ------------------------------------------------------------------
       HATA: Burası `/enrolled-headcount/peers` çağırıyordu. O uç
       `filter_mode` PARAMETRESİ ALMAZ (bkz. router: yalnızca kapsam ve
       dönem); Ankara'daki tüm kurumları koşulsuz döndürür. Dolayısıyla
       başlıktaki "Karşılaştırma" seçicisi değişse bile istek aynı
       kalıyor, dönen liste aynı kalıyor ve filtre çalışmıyor gibi
       görünüyordu — seçici gerçekten hiçbir şeyi filtrelemiyordu.

       ÇÖZÜM: yeni bir filtre mantığı yazmak yerine Karşılaştırmalar
       sayfasının ZATEN ÇALIŞAN kaynağı kullanılır:
       `/university-competitors` + `filter_mode: K_EVREN`. Devlet/Vakıf
       ayrımı ve "Benzer Ölçek" bandı orada `_suz()` içinde tanımlıdır;
       burada kopyalanmaz. `_suz()` kendi kurumumuzu DAİMA kümede
       tutar, bu yüzden ABÜ hangi kip seçilirse seçilsin grafikte
       kalır. Ekran durumu da aynı: `K_EVREN`. */
    doldur("ogKiyas", () => uni
      ? api.get("/api/decision-analytics/university-competitors",
                donemParam({ filter_mode: K_EVREN, matching_mode: eslesmeKipi() }))
      : api.get("/api/decision-analytics/yok-atlas-comparison",
                { ...p,
                  institution_type: K_EVREN,
                  matching_mode: eslesmeKipi() }), o => {
      if (uni) {
        const bas = document.getElementById("ogKiyasBas");
        const not = document.getElementById("ogKiyasNot");
        if (!o || !o.available) return bekleniyorGovde(
          (o && o.note)
          || "Bu dönemde karşılaştırılabilir resmî kurum verisi bulunmuyor.");

        const isMatchedUni = eslesmeKipi() !== "all_programs";

        /* Sıralama SÜZÜLMÜŞ küme üzerinden yeniden yapılır; etiket
           gizleme değil, gerçek yeniden hesaplama. Ölçülmemiş kurum
           sıralamaya giremez (0 gibi davranmaz). */
        const rows = (o.universities || [])
          .filter(r => _sayiVar(r.student_count))
          .slice()
          .sort((a, b) => b.student_count - a.student_count);
        if (!rows.length) return bekleniyorGovde(
          "Bu süzgeçte kayıtlı öğrenci sayısı ölçülmüş kurum yok.");
        /* Kurumumuz ilk 10'a giremese bile grafikte KALIR: bu kart bir
           "en büyük 10" listesi değil, kendi konumumuzu okuma aracıdır.
           `_suz()` zaten kümede tutuyor; burada da görünürlüğü korunur. */
        const biz = rows.find(r => r.is_home_institution);
        let gosterilen = rows.slice(0, 10);
        if (biz && !gosterilen.includes(biz)) {
          gosterilen = rows.slice(0, 9).concat([biz]);
        }
        if (bas) bas.textContent = "Ankara'daki Üniversitelerle Öğrenci Sayısı Karşılaştırması";
        if (not) {
          const t = o.type_breakdown || {};
          not.textContent = `Karşılaştırma: ${o.filter_label || evrenAdi(K_EVREN)} · ${o.matching_mode_label || eslesmeAdi(eslesmeKipi())}`
            + ` · akranlar: ${t.DEVLET || 0} devlet, ${t.VAKIF || 0} vakıf`
            + ` (+ kurumumuz)`
            + (o.academic_year ? ` · ${o.academic_year}` : "");
        }
        /* Tür eki düz metindir: `yatayCubuk` etiketi kaçırdığı için
           rozet HTML'i buraya konulamaz. Tür bilinmiyorsa hiçbir şey
           yazılmaz — uydurulmaz. */
        const turEki = t => t === "DEVLET" ? " (Devlet)"
          : t === "VAKIF" ? " (Vakıf)" : "";
        const eksenMetni = isMatchedUni
          ? "eşleşen program kohortu · ★ kurumumuz"
          : "kayıtlı öğrenci · ★ kurumumuz";
        return yatayCubuk(gosterilen.map(r => ({
          ad: r.university_name + turEki(r.university_type)
              + (r.is_home_institution ? "  ★" : ""),
          deger: r.student_count,
          renk: r.is_home_institution ? "var(--vurgu)" : "var(--vurgu-2)",
        })), { eksenY: eksenMetni });
      }

      const bas = document.getElementById("ogKiyasBas");
      const not = document.getElementById("ogKiyasNot");
      if (bas) bas.textContent = o.title || "YÖK Atlas Kohort Karşılaştırması";
      if (not) {
        /* Kullanıcı HER İKİ boyutta da nerede olduğunu HER ZAMAN
           görebilmeli. Etiketler sunucunun döndürdüğü değerlerden
           okunur; istemci kendi tahminini yazmaz. */
        not.textContent = `Karşılaştırma: ${
          o.institution_type_label || evrenAdi(K_EVREN)} · ${
          o.matching_mode_label || eslesmeAdi(eslesmeKipi())} · ${
          o.subtitle || o.note || ""}`
          + (o.matching_mode_fallback
             ? ` · "${eslesmeAdi(o.matching_mode_fallback.requested)}" bu `
               + `kapsamda geçerli değil, "${
                 o.matching_mode_label}" uygulandı.`
             : "");
      }
      if (!o.available) return bekleniyorGovde(o.note ||
        "Bu kapsamda karşılaştırılabilir YÖK Atlas verisi bulunmuyor.");

      const tumSatirlar = o.peers || [];
      const bizimSatir = tumSatirlar.find(r => r.is_home_institution);
      /* 2025-2026 Atlas geri dönüşü 2024 kaynak yılını kullanır.
         Cari metrik başlıklarında istenen dönemi kaynak yılı gibi
         göstermemek için API'nin açık kaynak dönemini kullan. */
      const atlasCariDonem = o.current_metric_period || K.donem;
      let rows = tumSatirlar.slice(0, 12);
      /* Okunabilirlik sınırı kurumumuzun çubuğunu gizleyemez. ABÜ ilk
         12'de değilse son dış satır yerine ABÜ eklenir. */
      if (bizimSatir && !rows.includes(bizimSatir)) {
        rows = tumSatirlar.slice(0, 11).concat([bizimSatir]);
      }
      const etiketler = rows.map(r => r.label + (r.is_home_institution ? "  ★" : ""));
      /* EŞLEŞTİRME ŞEFFAFLIĞI: hangi programların hangi gerekçeyle
         karşılaştırmaya girdiği ve akranın hangi programlarının DIŞARIDA
         bırakıldığı, kullanıcı sormadan görünür olmalı. Metin sunucudan
         gelir; istemci sayı türetmez. */
      const eslesmeNotu = o.matching_explanation
        ? `<div class="not es-aciklama" data-es-aciklama style="margin:10px 0 2px">${
            esc(o.matching_explanation)}</div>`
        : "";
      const dislananlar = o.excluded_peer_programs || [];
      const eslesmeDetay = detay(
        `Eşleştirme gerekçesi ve dışlanan ${dislananlar.length} program`,
        `<div class="not">Kip: <b>${esc(o.matching_mode_label || "")}</b> · `
        + `Temel: <code>${esc(o.cohort_basis || "")}</code> · `
        + `Kendi disiplin ailemiz: <code>${
            esc((o.home_discipline_families || []).join(", ") || "—")}</code></div>`
        + `<table><thead><tr><th>Kurum</th><th>Program</th>
             <th>Disiplin ailesi</th><th>Derece</th></tr></thead><tbody>${
          (rows.filter(r => !r.is_home_institution).map(r =>
            `<tr><td style="text-align:left">${esc(r.university_name)}</td>
             <td style="text-align:left">${esc(r.program_name || r.faculty_name || "")}</td>
             <td style="text-align:left">${esc(
               ((r.provenance || {}).included_programs || [])
                 .map(x => x.discipline_family).filter(Boolean)[0] || "—")}</td>
             <td>${esc(r.match_reason || r.match_type || "—")}</td></tr>`).join(""))
          }</tbody></table>`
        + (dislananlar.length
           ? `<div class="not" style="margin-top:10px">Aynı fakülte
                evreninde olup akademik olarak eşleşmediği için DIŞARIDA
                bırakılanlar:</div>`
             + `<table><thead><tr><th>Kurum</th><th>Program</th>
                  <th>Gerekçe</th></tr></thead><tbody>${
               dislananlar.slice(0, 60).map(x =>
                 `<tr><td style="text-align:left">${esc(x.university_name)}</td>
                  <td style="text-align:left">${esc(x.program_name || "")}</td>
                  <td style="text-align:left"><code>${esc(x.reason)}</code></td></tr>`
               ).join("")}</tbody></table>`
             + (dislananlar.length > 60
                ? `<div class="not">İlk 60 satır gösterildi (toplam ${
                    dislananlar.length}).</div>` : "")
           : ""));
      const kohort = yatayCubuk(rows.map(r => ({
        ad: r.label + (r.is_home_institution ? "  ★" : ""),
        deger: r.cohort_size,
        renk: r.is_home_institution ? "var(--vurgu)" : "var(--vurgu-2)",
      })), { eksenY: "YKS yerleşen kohortları toplamı · kayıtlı öğrenci değildir" })
        + eslesmeNotu;
      const alim = `<div class="not" style="margin:12px 0 6px">${
        esc(atlasCariDonem)} kontenjan ve yerleşen</div>`
        + gruplandirilmisCubuk(etiketler, [
          { ad: "Kontenjan", veri: rows.map(r => r.quota) },
          { ad: "Yerleşen", veri: rows.map(r => r.placed_students) },
        ], { eksenY: "kişi", yukseklik: 230 });
      const doluluk = `<div class="not" style="margin:12px 0 6px">${
        esc(atlasCariDonem)} kontenjan doluluğu</div>`
        + yatayCubuk(rows.map(r => ({
          ad: r.label, deger: r.occupancy_percent,
          renk: r.is_home_institution ? "var(--vurgu)" : "var(--mor)",
        })), { yb: v => ondalik(v, 1) + "%", eksenY: "% · ayrı eksen" });
      const tablo = `<table><thead><tr><th>Kurum / program</th>
          <th>Kohort</th><th>Kontenjan</th><th>Yerleşen</th><th>Doluluk</th>
          <th>Taban puan</th><th>Başarı sırası</th><th>Kaynak kodları</th></tr></thead><tbody>${
        rows.map(r => `<tr class="${r.is_home_institution ? "bizim" : ""}">
          <td style="text-align:left">${esc(r.label)}</td>
          <td>${sayi(r.cohort_size)}</td><td>${sayi(r.quota)}</td>
          <td>${sayi(r.placed_students)}</td><td>${yuzde(r.occupancy_percent, 1)}</td>
          <td>${ondalik(r.base_score, 2)}</td><td>${sayi(r.success_rank)}</td>
          <td style="text-align:left">${esc(((r.provenance || {}).source_row_references || []).join(", "))}</td>
        </tr>`).join("")}</tbody></table>`;
      return kohort + alim + doluluk + eslesmeDetay
        + detay("Kaynak satırları ve metrikleri göster",
        tablo + `<div class="eksen-not">${esc(o.methodology)} Kaynak: ${esc(o.source)} · ${
          esc(o.source_file)}</div>`);
    }, { iskelet: 6 });

    /* ALT BİRİM ÇOKLU METRİK: yönetici tek bakışta hangi birimin
       kontenjanını doldurduğunu, hangisinin doluluğunun düştüğünü görür. */
    /* ADAPTİF (aynı desen): tek alt birim kaldığında bu panel kontenjan ve
       öğrenci sayısını tek çubuk hâlinde tekrar ederdi — ikisi de üstteki
       KPI şeridinde zaten var. Onun yerine talep/kapasite konumu. */
    const ogUst = ebeveynKapsami();
    doldur("ogAltBirim", () => Promise.all([
      api.get("/api/decision-analytics/child-breakdown", p),
      ogUst && ogUst.ustKapsamVar
        ? api.get("/api/decision-analytics/child-breakdown", ogUst.p).catch(() => null)
        : Promise.resolve(null),
    ]), ([o, ustVeri]) => {
      const bas = document.getElementById("ogAltBirimBas");
      const r = (o.rows || []).slice(0, 9);
      if (r.length < 2) {
        const kardesler = (ustVeri && ustVeri.rows) || [];
        const kendi = kardesler.find(x => x.unit_id === (ogUst || {}).kendiId);
        const govde = kendi && konumGovdesi([
          { ad: "Kontenjan doluluğu", oku: x => x.occupancy_percent, yuksekIyi: true },
          { ad: "Öğrenci yükü", oku: x => x.students_per_academic_staff,
            yuksekIyi: false },
          { ad: "Kadro derinliği", oku: x => x.academics_per_100_students,
            yuksekIyi: true },
        ], kendi, kardesler, { ustAd: (ogUst || {}).ustAd });
        if (!govde) { paneliGoster("ogAltBirim", false); return ""; }
        paneliGoster("ogAltBirim", true);
        if (bas) bas.textContent = "Talep ve Kapasite Konumu";
        return govde;
      }
      paneliGoster("ogAltBirim", true);
      if (bas) bas.textContent = "Alt Birim Karşılaştırması";
      const ad = r.map(x => birimAdi(x.code, x.name));
      const ogrenciEtiketi = o.student_count_source === "yks_turevi"
        ? "Öğrenci (ÖSYM türevi)" : "Öğrenci";
      const kaynakNotu = o.student_count_source === "yks_turevi"
        ? `<div class="not" style="margin-top:8px">Kaynak: ÖSYM yerleştirme
           kohortlarından türetilen alt birim değerleri.${uni ? ` Kurumun
           YÖK kayıtlı öğrenci toplamıyla karşılaştırılmaz.` : ""}</div>`
        : "";
      return gruplandirilmisCubuk(ad, [
        { ad: ogrenciEtiketi, veri: r.map(x => x.student_count) },
        { ad: "Kontenjan", veri: r.map(x => x.quota) },
        { ad: "Yerleşen", veri: r.map(x => x.placed_students) },
      ], { eksenY: "kişi", yukseklik: 240 })
      + `<div class="not" style="margin:10px 0 6px">Kontenjan doluluğu (%)</div>`
      + yatayCubuk(r.map(x => ({ ad: birimAdi(x.code, x.name),
          deger: x.occupancy_percent,
          renk: (x.occupancy_percent || 0) >= 80 ? "var(--iyi)"
              : (x.occupancy_percent || 0) >= 50 ? "var(--uyari)" : "var(--kotu)" })),
        { yb: v => ondalik(v, 1) + "%", eksenY: "renk: ≥%80 iyi · ≥%50 dikkat · altı risk" })
      + kaynakNotu;
    }, { iskelet: 6 });

    doldur("ogYorum", () => Promise.all([
      api.get("/api/decision-analytics/student-body", p),
      api.get("/api/decision-analytics/scholarship-breakdown", p),
      uni
        ? api.get("/api/decision-analytics/university-competitors",
                  donemParam({ filter_mode: K_EVREN }))
        : api.get("/api/decision-analytics/peer-comparison", p),
    ]), ([g, b, r]) => {
      const kartlar = [];
      const d = g.demand_pressure || {};
      if (d.available) {
        kartlar.push(yorumKarti("📉", "Doluluk Oranı",
          `${d.placement_year} yerleştirmesinde doluluk %${ondalik(d.occupancy_percent, 1)}. ${d.explanation}`,
          d.status === "talep_yetersiz" ? { tur: "risk", ad: "Risk" }
            : d.status === "gevsek" ? { tur: "dikkat", ad: "Dikkat" }
            : { tur: "olumlu", ad: "Olumlu" }));
      }
      if (g.intake_change_percent !== null && g.intake_change_percent !== undefined) {
        kartlar.push(yorumKarti("👥", "Öğrenci Alımı",
          `Son kohort bir önceki yıla göre %${ondalik(Math.abs(g.intake_change_percent), 1)} ${
            g.intake_change_percent >= 0 ? "arttı" : "azaldı"}.`,
          g.intake_change_percent >= 0 ? { tur: "olumlu", ad: "Olumlu" } : { tur: "dikkat", ad: "Dikkat" }));
      }
      const en = (b.types || []).slice().sort((a, c) =>
        (c.occupancy_percent || 0) - (a.occupancy_percent || 0))[0];
      if (en) {
        kartlar.push(yorumKarti("🎓", "Burs Politikası",
          `En yüksek doluluk "${en.scholarship_type}" kontenjanında (%${ondalik(en.occupancy_percent, 1)}). ` +
          `Burs kademesi talebi doğrudan etkiliyor.`, { tur: "bilgi", ad: "Bilgi" }));
      }
      const h = uni ? r.home : null;
      if (h && h.ankara_rank) {
        kartlar.push(yorumKarti("⇄", "Rekabetçilik",
          `Ankara'da kayıtlı öğrenci sayısında ${h.ankara_rank}. sıradayız (${h.ankara_university_count} kurum). ` +
          `4 yıllık büyüme %${ondalik(h.growth_percent_period, 1)}.`,
          { tur: "olumlu", ad: "Olumlu" }));
      } else if (!uni && r.available && r.ranks && r.ranks.student_count) {
        const secili = (r.peers || []).find(x => x.is_selected);
        kartlar.push(yorumKarti("⇄", "İç Akran Konumu",
          `${esc((secili && secili.name) || dugum().ad)}, ${esc(r.basis_label || "akran kümesi")} `
          + `içinde öğrenci sayısına göre ${r.ranks.student_count}. sırada.`,
          { tur: "bilgi", ad: "Kapsamlı" }));
      }
      return `<div class="yorum-serit">${kartlar.join("")}</div>
        <div class="dip-not">ⓘ Bu yorumlar sabit kurallarla üretilir; dil modeli kullanılmaz.</div>`;
    }, { iskelet: 4 });
  },
};

/* ==========================================================================
   KARŞILAŞTIRMA EVRENİ SEÇİCİSİ — Tümü / Devlet / Vakıf / Benzer Ölçek
   ==========================================================================
   HATA: Bu paneller `filter_mode: "similar"` değerini SABİT gönderiyordu.
   Backend'de "benzer" tanımı AYNI TÜR + ölçek bandı olduğu için, ABÜ bir
   vakıf kurumu olduğundan karşılaştırma kümesi sessizce "yalnızca vakıf
   üniversiteleri" oluyordu: ekranda "Benzer üniversiteler" yazarken
   ODTÜ, Hacettepe, Gazi, Ankara Üniversitesi kümede HİÇ görünmüyordu.

   Artık evren KULLANICININ SEÇİMİ. Varsayılan "Tümü" — karşılaştırma
   evrenini daraltmak bir analiz tercihidir, sessiz bir varsayılan değil.
   Seçim değişince yalnızca ilgili panelin verisi yeniden çekilir; sayfa
   yeniden yüklenmez ve kapsam/dönem seçimi korunur.
   ========================================================================== */

const KARSILASTIRMA_EVRENI = [
  { deger: "all",        ad: "Tümü" },
  { deger: "state",      ad: "Devlet" },
  { deger: "foundation", ad: "Vakıf" },
  { deger: "similar",    ad: "Benzer Ölçek" },
];

/** Seçili evren. Varsayılan "all" — "similar" DEĞİL. */
let K_EVREN = "all";

const evrenAdi = d =>
  (KARSILASTIRMA_EVRENI.find(x => x.deger === d) || {}).ad || "Tümü";

/** Panel başlığına sığan kompakt seçici. Yeni satır/kart açmaz. */
function evrenSecici(id) {
  return `<span class="evren-sec">
    <label for="${id}">Karşılaştırma</label>
    <select id="${id}" data-evren>${KARSILASTIRMA_EVRENI.map(o =>
      `<option value="${o.deger}"${o.deger === K_EVREN ? " selected" : ""}>${
        esc(o.ad)}</option>`).join("")}</select>
  </span>`;
}

/* ==========================================================================
   İKİNCİ BOYUT — PROGRAM EŞLEŞTİRME ADALETİ
   --------------------------------------------------------------------------
   Kurum türü seçicisinden TAMAMEN BAĞIMSIZDIR. Biri "hangi üniversiteler",
   diğeri "hangi bölümler" sorusuna cevap verir. Birini değiştirmek diğerinin
   değerini DEĞİŞTİRMEZ; ikisi çarpım olarak uygulanır.

   "Benzer Bölümler" bir metin benzerliği değildir: sunucudaki KAPALI
   disiplin ailesi kaydına dayanır. Adında "mühendislik" geçmesi bir
   programı benzer yapmaz.
   ========================================================================== */

const PROGRAM_ESLESTIRME = [
  { deger: "all_programs",     ad: "Hepsi" },
  { deger: "same_program",     ad: "Aynı Bölümler" },
  { deger: "similar_programs", ad: "Benzer Bölümler" },
];

/** Kullanıcı seçimi. `null` = "henüz dokunulmadı, bağlam varsayılanı geçerli". */
let K_ESLESME = null;

/** Bağlama göre varsayılan eşleştirme kipi. */
function eslesmeVarsayilani() {
  return seviye() === "university" ? "all_programs" : "same_program";
}

/** Yürürlükteki kip: kullanıcı seçtiyse o, seçmediyse bağlam varsayılanı. */
const eslesmeKipi = () => K_ESLESME || eslesmeVarsayilani();

const eslesmeAdi = d =>
  (PROGRAM_ESLESTIRME.find(x => x.deger === d) || {}).ad || "Hepsi";

/** İKİ SEÇİCİ, TEK ETİKET, TEK SATIR (Kurum ve Bölüm filtreleri). */
/* ==========================================================================
   KARŞILAŞTIRMA EKRANI — PANEL BAŞINA YEREL SÜZGEÇ DURUMU
   --------------------------------------------------------------------------
   Eskiden bu ekrandaki tek bir seçici `K_EVREN`/`K_ESLESME` genel
   değişkenlerini yazıyor, `evrenPanelleriniYenile()` de sayfadaki BÜTÜN
   karşılaştırma panellerini birden tazeliyordu. Bir kartta "Vakıf"
   seçmek yandaki kartın da evrenini değiştiriyordu.

   Artık üstteki iki kartın her biri KENDİ durumunu taşır. Bir kartın
   durumu değişince yalnızca o kart yeniden doldurulur; komşu kartın
   nesnesine dokunulmaz (`{...}` ile kopyalanmaz, ayrı nesnelerdir).

   `K_EVREN` / `K_ESLESME` KALDIRILMADI: Öğrenciler ekranı ve alttaki
   karşılaştırma üçlüsü hâlâ onları kullanıyor. Yalnızca üstteki iki
   kart onlardan ayrıldı. */
const KR_YEREL = {
  coklu:  { evren: "all", eslesme: null },
  yillik: { evren: "all", program: null, mod: "occupancy" },
  /* Yerleşme sıralaması kartı. Kontenjan kartıyla aynı uçtan beslenir
     ama KENDİ süzgeç durumunu tutar — iki kart bağımsız gezilebilsin. */
  siralama: { evren: "all", program: null },
  sira:   { evren: "all", eslesme: null },
};

/** Panel adı → o paneli TEK BAŞINA yeniden dolduran işlev.
 *  Ekranın `yukle()` akışı çalışırken doldurulur. */
const KR_TAZELE = {};

/* Yerel süzgeç değişimi. `data-evren`/`data-eslesme` işleyicisinden
   AYRIDIR: burada ne genel değişkenler yazılır ne de sayfadaki diğer
   seçiciler eşitlenir. Yalnızca kendi panelinin durumu güncellenir ve
   yalnızca o panel yeniden doldurulur. */
document.addEventListener("change", e => {
  const s = e.target.closest && e.target.closest("[data-kr-panel]");
  if (!s) return;
  const panel = s.dataset.krPanel, alan = s.dataset.krAlan;
  if (!KR_YEREL[panel]) return;
  KR_YEREL[panel][alan] = s.value;
  /* Bölüm değişince kurum evreni AYNEN kalır ve tersi — iki boyut
     birbirini sıfırlamaz. */
  if (typeof KR_TAZELE[panel] === "function") KR_TAZELE[panel]();
});

/* Doluluk / Kontenjan ölçütü — yalnızca yıllık kartı ilgilendirir. */
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-kr-mod]");
  if (!b) return;
  KR_YEREL.yillik.mod = b.dataset.krMod === "quota" ? "quota" : "occupancy";
  if (typeof KR_TAZELE.yillik === "function") KR_TAZELE.yillik();
});

/** Yerel seçici — `data-evren`/`data-eslesme` KULLANMAZ.
 *  O nitelikler kabuk.js'teki genel işleyiciyi tetikler ve sayfadaki
 *  tüm seçicileri eşitler; burada tam olarak istemediğimiz şey odur. */
function krYerelSecici(panel, alan, id, etiket, secenekler, deger) {
  return `<span class="evren-sec">
    <label for="${id}">${esc(etiket)}</label>
    <select id="${id}" data-kr-panel="${panel}" data-kr-alan="${alan}"
            aria-label="${esc(etiket)}">${secenekler.map(o =>
      `<option value="${esc(o.deger)}"${
        String(o.deger) === String(deger) ? " selected" : ""}>${esc(o.ad)}</option>`
    ).join("")}</select></span>`;
}

function karsilastirmaSecicileri(evrenId, eslesmeId) {
  const kip = eslesmeKipi();
  return `<span class="evren-sec ikili-sec">
    <label for="${evrenId}">Kurum:</label>
    <select id="${evrenId}" data-evren
            aria-label="Kurum türü">${
      KARSILASTIRMA_EVRENI.map(o =>
        `<option value="${o.deger}"${o.deger === K_EVREN ? " selected" : ""}>${
          esc(o.ad)}</option>`).join("")}</select>
    <label for="${eslesmeId}">Bölüm:</label>
    <select id="${eslesmeId}" data-eslesme
            aria-label="Bölüm eşleşmesi">${
      PROGRAM_ESLESTIRME.map(o =>
        `<option value="${o.deger}"${o.deger === kip ? " selected" : ""}>${
          esc(o.ad)}</option>`).join("")}</select>
  </span>`;
}

/** Eşleşme derecesi rozeti — "bu program neden burada?" sorusunu satırın
 *  kendisinde cevaplar. Sunucudan gelen `match_type` dışında bir şey
 *  uydurmaz; bilinmiyorsa hiçbir şey göstermez. */
const eslesmeRozet = t =>
  t === "similar" ? ' <span class="es-rz benzer">benzer</span>'
  : t === "equivalent" ? ' <span class="es-rz esdeger">eşdeğer</span>'
  : t === "exact" ? ' <span class="es-rz ayni">aynı</span>' : "";

/** Kurum türü rozeti — akran adının yanında, sade. */
const turRozet = t => t === "DEVLET" ? ' <span class="tur-rz dv">Devlet</span>'
  : t === "VAKIF" ? ' <span class="tur-rz vk">Vakıf</span>' : "";


/** Evren seçimi değişince YALNIZCA etkilenen panelleri yeniden yükler.
 *  Tüm panoyu yeniden çizmez: kapsam, dönem, menü kaydırması ve diğer
 *  panellerin verisi olduğu gibi kalır. Bayat veri ekranda kalmasın diye
 *  ilgili kaplar önce iskelete döndürülür. */
function evrenPanelleriniYenile() {
  const ekran = EKRANLAR[K.ekran];
  if (!ekran || typeof ekran.yukle !== "function") return;
  /* İKİ SEÇİCİ BİRBİRİNİ SIFIRLAMAZ: burada yalnızca veri tazelenir,
     seçicilerin değerleri (K_EVREN / K_ESLESME) hiç yazılmaz. */
  ["krSiralama", "krBuyukluk", "krYogunluk", "krSira", "ogKiyas", "ogYorum"]
    .forEach(id => {
      const kap = document.getElementById(id);
      if (kap) kap.innerHTML = iskeletHtml(5);
    });
  if (typeof _acikModal !== "undefined" && _acikModal && _acikModal.panelId) {
    const modalIc = _acikModal.kap ? _acikModal.kap.querySelector(".gmodal-ic") : null;
    if (modalIc && !modalIc.classList.contains("canli-panel")) {
      modalIc.innerHTML = iskeletHtml(6);
    }
  }
  /* Seçicinin kendi değeri korunur (yeniden çizilmiyor), etiketler
     `doldur()` içinde güncellenir. */
  ekran.yukle();
}

/* --------------------------------------------------------------------------
   Akademik personel + yönetim-politikası performans bileşenleri
   -------------------------------------------------------------------------- */
const AKADEMIK_PERFORMANS_ALANLARI = [
  "publication_count", "citation_count", "teaching_load_hours",
  "advising_count", "project_count", "patent_count",
  "community_engagement_score",
];
const AKADEMIK_ALAN_ETIKETLERI = {
  publication_count: "Yayın", citation_count: "Atıf",
  teaching_load_hours: "Ders yükü", advising_count: "Danışmanlık",
  project_count: "Proje", patent_count: "Patent",
  community_engagement_score: "Toplumsal katkı",
};
const _academicRows = new Map();
let _academicDetailModal = null;
let _academicDetailKeyHandler = null;

function academicClassLabel(value) {
  return ({
    "yüksek performans": "Yüksek Performans",
    "beklenen performans": "Beklenen Performans",
    "desteklenmesi gereken": "Destek Gerekli",
  })[value] || value || "Ölçülmedi";
}

function academicClassColor(value) {
  return value === "yüksek performans" ? "var(--iyi)"
    : value === "beklenen performans" ? "var(--vurgu)" : "var(--uyari)";
}

function academicMetricUnit(key) {
  return key === "teaching_load_hours" ? "saat"
    : key === "community_engagement_score" ? "puan" : "adet";
}

function academicMetricText(component) {
  if (!component || !component.available) return "ölçülmedi";
  return `${sayi(component.value)} ${academicMetricUnit(component.metric_key)}`;
}

function academicRemember(rows) {
  (rows || []).forEach(row => _academicRows.set(Number(row.staff_id), row));
  return rows || [];
}

function academicEmptyBody() {
  return bekleniyorGovde(seviye() === "program"
    ? "Bu program için doğrudan akademik personel tahsisi bulunmuyor. Bölüm kadrosu program kadrosu gibi devralınmadı."
    : "Seçili kapsam ve dönemde akademik personel kaydı yok.");
}

function academicDetailClose() {
  if (!_academicDetailModal) return;
  document.removeEventListener("keydown", _academicDetailKeyHandler, true);
  _academicDetailModal.remove();
  _academicDetailModal = null;
  _academicDetailKeyHandler = null;
}

function academicDetailOpen(staffId) {
  const row = _academicRows.get(Number(staffId));
  if (!row) return;
  academicDetailClose();
  const components = row.component_breakdown || {};
  const breakdown = AKADEMIK_PERFORMANS_ALANLARI.map(key => {
    const item = components[key] || { metric_key: key, available: false,
      weight: (row.weights || {})[key] || 0, contribution: 0 };
    const formula = item.available
      ? `${sayi(item.value)} × ${sayi(item.weight)} = ${sayi(item.contribution)}`
      : `ölçülmedi · puan katkısı ${sayi(item.contribution || 0)}`;
    return `<div class="academic-breakdown-row ${item.available ? "" : "is-missing"}">
      <div><b>${esc(AKADEMIK_ALAN_ETIKETLERI[key])}</b>
        <small>${esc(item.source_label || "Kaynak veri bulunmuyor")}</small></div>
      <div class="academic-formula">${esc(formula)}</div>
    </div>`;
  }).join("");

  const overlay = document.createElement("div");
  overlay.className = "gmodal academic-detail-modal";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Akademik personel detayi");
  overlay.innerHTML = `<div class="gmodal-kutu academic-detail-box">
    <div class="gmodal-bas">
      <div class="gmodal-baslik"><h3>${esc(row.full_name)}</h3>
        <div class="not">${esc(row.title)} · ${esc(row.department_name)}</div></div>
      <button type="button" class="gmodal-kapat" data-academic-close
        aria-label="Kapat">✕</button>
    </div>
    <div class="gmodal-ic">
      <div class="academic-detail-identity">
        <div><span>Fakülte</span><b>${esc(row.faculty_name)}</b></div>
        <div><span>Bölüm</span><b>${esc(row.department_name)}</b></div>
        <div><span>Dönem</span><b>${esc(row.academic_year)}</b></div>
      </div>
      <div class="academic-score-hero" style="--academic-color:${academicClassColor(row.classification)}">
        <div><span>Akademik Performans Puanı</span><strong>${sayi(row.total_score)}</strong></div>
        <b>${esc(academicClassLabel(row.classification))}</b>
      </div>
      <div class="academic-policy-note">${esc(row.policy_label)} Bu puan resmî bir YÖK puanı değildir.</div>
      <h4 class="academic-detail-heading">Bileşen Kırılımı</h4>
      <div class="academic-breakdown">${breakdown}</div>
    </div>
  </div>`;
  overlay.addEventListener("click", event => {
    if (event.target === overlay || event.target.closest("[data-academic-close]")) {
      academicDetailClose();
    }
  });
  _academicDetailKeyHandler = event => {
    if (event.key === "Escape") academicDetailClose();
  };
  document.addEventListener("keydown", _academicDetailKeyHandler, true);
  document.body.appendChild(overlay);
  _academicDetailModal = overlay;
  overlay.querySelector("[data-academic-close]").focus();
}

function academicCards(rows) {
  if (!rows.length) return academicEmptyBody();
  const cards = rows.map(row => {
    const c = row.component_breakdown || {};
    return `<article class="academic-card">
      <div class="academic-card-head">
        <div class="academic-avatar">◈</div>
        <div><h4>${esc(row.full_name)}</h4><span>${esc(row.title)}</span></div>
        <b class="academic-rank">#${sayi(row.rank)}</b>
      </div>
      <div class="academic-unit">${esc(row.faculty_name)}<br><b>${esc(row.department_name)}</b></div>
      <div class="academic-metrics">
        <div><span>Yayın</span><b>${esc(academicMetricText(c.publication_count))}</b></div>
        <div><span>Atıf</span><b>${esc(academicMetricText(c.citation_count))}</b></div>
        <div><span>Proje</span><b>${esc(academicMetricText(c.project_count))}</b></div>
        <div><span>Ders yükü</span><b>${esc(academicMetricText(c.teaching_load_hours))}</b></div>
      </div>
      <div class="academic-card-foot">
        <span class="academic-band" style="--academic-color:${academicClassColor(row.classification)}">
          ${esc(academicClassLabel(row.classification))}</span>
        <strong>${sayi(row.total_score)} puan</strong>
        <button type="button" data-academic-detail="${row.staff_id}">Detayı Göster</button>
      </div>
    </article>`;
  }).join("");
  return `<div class="academic-card-grid">${cards}</div>`;
}

function academicTable(rows) {
  if (!rows.length) return "";
  return `<div class="academic-table-wrap"><table>
    <thead><tr><th>Ad Soyad</th><th>Unvan</th><th>Fakülte</th><th>Bölüm</th>
      <th>Yayın</th><th>Atıf</th><th>Proje</th><th>Patent</th>
      <th>Ders yükü</th><th>Puan</th><th>Sınıf</th></tr></thead>
    <tbody>${rows.map(row => {
      const c = row.component_breakdown || {};
      const metric = key => esc(academicMetricText(c[key]));
      return `<tr><td><button type="button" class="academic-name-button"
          data-academic-detail="${row.staff_id}">${esc(row.full_name)}</button></td>
        <td>${esc(row.title)}</td><td>${esc(row.faculty_name)}</td>
        <td>${esc(row.department_name)}</td><td>${metric("publication_count")}</td>
        <td>${metric("citation_count")}</td><td>${metric("project_count")}</td>
        <td>${metric("patent_count")}</td><td>${metric("teaching_load_hours")}</td>
        <td><b>${sayi(row.total_score)}</b></td>
        <td>${esc(academicClassLabel(row.classification))}</td></tr>`;
    }).join("")}</tbody></table></div>`;
}

function academicScoreChart(rows) {
  if (!rows.length) return academicEmptyBody();
  const limit = seviye() === "university" ? 40 : rows.length;
  const shown = rows.slice(0, limit);
  return yatayCubuk(shown.map(row => ({
    ad: row.full_name, deger: row.total_score,
    renk: academicClassColor(row.classification),
    ipucu: `${sayi(row.total_score)} puan · ${academicClassLabel(row.classification)}`,
  })), { eksenY: "Akademik Performans Puanı · azalan sıra" })
    + (rows.length > shown.length
      ? `<div class="eksen-not">Üniversite görünümünde ilk ${shown.length} akademisyen gösteriliyor; tam liste Detayı Göster tablosundadır.</div>` : "");
}

function academicMetricChart(rows, key, axis) {
  const measured = rows.filter(row => row.component_breakdown?.[key]?.available)
    .sort((a, b) => Number(b.component_breakdown[key].value)
      - Number(a.component_breakdown[key].value));
  if (!measured.length) return bekleniyorGovde(`${AKADEMIK_ALAN_ETIKETLERI[key]} verisi ölçülmedi.`);
  return yatayCubuk(measured.slice(0, 24).map(row => ({
    ad: row.full_name, deger: row.component_breakdown[key].value,
  })), { eksenY: axis });
}

function academicKpis(rows) {
  if (!rows.length) return academicEmptyBody();
  const average = rows.reduce((sum, row) => sum + Number(row.total_score || 0), 0) / rows.length;
  const high = rows.filter(row => row.classification === "yüksek performans").length;
  const expected = rows.filter(row => row.classification === "beklenen performans").length;
  const support = rows.filter(row => row.classification === "desteklenmesi gereken").length;
  return kpi("Akademik Personel", sayi(rows.length), "seçili kapsam", { ikon: "🎓", renk: "mavi" })
    + kpi("Ortalama Puan", ondalik(average, 1), "yönetim politikası", { ikon: "◈", renk: "mor" })
    + kpi("Yüksek Performans", sayi(high), "150 ve üzeri", { ikon: "↑", renk: "yesil" })
    + kpi("Beklenen Performans", sayi(expected), "80–149", { ikon: "●", renk: "mavi" })
    + kpi("Destek Gerekli", sayi(support), "80 altı", { ikon: "!", renk: "turuncu" });
}

function academicPolicy(rows) {
  if (!rows.length) return academicEmptyBody();
  const policy = rows[0];
  return `<div class="academic-policy">
    <div class="academic-policy-title"><b>Akademik Performans Puanı</b>
      <span>${esc(policy.policy_version)}</span></div>
    <p>${esc(policy.policy_label)} Resmî YÖK puanı değildir.</p>
    <div class="academic-weight-grid">${AKADEMIK_PERFORMANS_ALANLARI.map(key => `
      <div><span>${esc(AKADEMIK_ALAN_ETIKETLERI[key])}</span>
        <b>× ${sayi((policy.weights || {})[key])}</b></div>`).join("")}</div>
    <div class="academic-thresholds">
      <span style="--academic-color:var(--iyi)">≥ ${sayi(policy.thresholds.high_performance)} · Yüksek</span>
      <span style="--academic-color:var(--vurgu)">≥ ${sayi(policy.thresholds.expected_performance)} · Beklenen</span>
      <span style="--academic-color:var(--uyari)">&lt; ${sayi(policy.thresholds.expected_performance)} · Destek gerekli</span>
    </div>
  </div>`;
}

EKRANLAR["akademik-personel"] = {
  baslik: "Akademik Personel",
  altBaslik: "Seçili kapsamdaki gerçek ABÜ akademisyenleri",
  ciz() {
    return `<div id="prsKpi" class="kpi-serit">${iskeletHtml(2)}</div>
      <div class="izgara-21">
        ${panel("Akademik Kadro", "Karttan akademisyen detayına ulaşın.",
          iskeletHtml(7), { id: "prsCards" })}
        ${panel("Performans Sıralaması", "Yönetim politikası puanına göre azalan sıra.",
          iskeletHtml(7), { id: "prsChart" })}
      </div>
      ${panel("Akademik Personel Tablosu", "Tam sayısal liste isteğe bağlı açılır.",
        iskeletHtml(5), { id: "prsTable", herZamanBuyutilebilir: true, buyutDetay: true })}`;
  },
  yukle() {
    const request = api.get("/api/academic-staff/ranking", kapsam());
    doldur("prsKpi", () => request, rows => academicKpis(academicRemember(rows)), { iskelet: 2 });
    doldur("prsCards", () => request, rows => academicCards(academicRemember(rows)), { iskelet: 7 });
    doldur("prsChart", () => request, rows => academicScoreChart(academicRemember(rows)), { iskelet: 7 });
    doldur("prsTable", () => request, rows => {
      academicRemember(rows);
      return rows.length ? detay("Detayı Göster", academicTable(rows)) : academicEmptyBody();
    }, { iskelet: 5 });
  },
};

EKRANLAR["akademik-performans"] = {
  baslik: "Akademik Performans",
  altBaslik: "Yönetim politikası puanı ve bileşenleri",
  ciz() {
    return `<div id="prfKpi" class="kpi-serit">${iskeletHtml(2)}</div>
      ${panel("Akademik Performans Puanı", "Yönetim politikası ağırlıklarıyla hesaplanır.",
        iskeletHtml(7), { id: "prfChart" })}
      <div class="izgara-2">
        ${panel("Yayın Karşılaştırması", "Yalnızca ölçülen yayın sayıları.",
          iskeletHtml(6), { id: "prfPublication" })}
        ${panel("Ders Yükü Karşılaştırması", "Yalnızca ders kaydı bulunan akademisyenler.",
          iskeletHtml(6), { id: "prfTeaching" })}
      </div>
      <div class="izgara-21">
        ${panel("Akademisyenler", "Kişiye tıklayarak puan kırılımını görün.",
          iskeletHtml(7), { id: "prfCards", buyutulmez: true })}
        ${panel("Puanlama Politikası", "Yapılandırmadaki güncel ağırlık ve eşikler.",
          iskeletHtml(5), { id: "prfPolicy", buyutulmez: true })}
      </div>`;
  },
  yukle() {
    const request = api.get("/api/academic-staff/ranking", kapsam());
    const remember = rows => academicRemember(rows);
    doldur("prfKpi", () => request, rows => academicKpis(remember(rows)), { iskelet: 2 });
    doldur("prfChart", () => request, rows => academicScoreChart(remember(rows)), { iskelet: 7 });
    doldur("prfPublication", () => request,
      rows => academicMetricChart(remember(rows), "publication_count", "Yayın sayısı"), { iskelet: 6 });
    doldur("prfTeaching", () => request,
      rows => academicMetricChart(remember(rows), "teaching_load_hours", "Haftalık ders saati"), { iskelet: 6 });
    doldur("prfCards", () => request, rows => academicCards(remember(rows)), { iskelet: 7 });
    doldur("prfPolicy", () => request, rows => academicPolicy(remember(rows)), { iskelet: 5 });
  },
};

/* --------------------------------------------------------------------------
   3) AKADEMİSYENLER
   -------------------------------------------------------------------------- */

/* ==========================================================================
   AKADEMİK ÜNVAN HİYERARŞİSİ — YALNIZCA "Akademik Ünvan Dağılımı" PANELİNE AİT
   --------------------------------------------------------------------------
   KAPSAM UYARISI: Bu harita GLOBAL bir sıralama kuralı DEĞİLDİR. Yalnızca
   `akUnvan` paneli tarafından kullanılır. Grafik yardımcılarının
   (`yatayCubuk`, `yiginCubuk`, `karsilastirmaCubugu` …) sıralama davranışı
   değiştirilmemiştir; başka hiçbir grafik veya liste bundan etkilenmez.

   SIRA: aşağıdan yukarıya kıdem. Dizideki konum ekrandaki konumdur —
   ilk eleman en üstte, son eleman en altta çizilir:

       0  ARAŞTIRMA GÖREVLİSİ      (en üstte)
       1  ÖĞRETİM GÖREVLİSİ
       2  DOKTOR ÖĞRETİM ÜYESİ
       3  DOÇENT
       4  PROFESÖR                 (en altta)

   Kadro sayısı sıralamayı ETKİLEMEZ. Profesör 10 kişi de olsa 1000 kişi
   de olsa en alttadır.
   ========================================================================== */

/** Türkçe'ye duyarlı büyük harfe çevirme.
 *
 *  `toUpperCase()` Türkçe'de HATALIDIR: "i" → "I" üretir, oysa doğru
 *  karşılık "İ"dir. Bu yüzden problemli harfler önce elle eşlenir.
 *  Bu yardımcı BİLEREK yereldir (global bir yardımcıya terfi ettirilmedi):
 *  görev kapsamı tek bir bileşendir ve projede hâlihazırda bir frontend
 *  normalize katmanı yoktur — yenisini global olarak dayatmak, bu görevin
 *  izin verdiğinden daha geniş bir değişiklik olurdu. */
function _unvanNormalize(metin) {
  return String(metin == null ? "" : metin)
    .replace(/i/g, "İ").replace(/ı/g, "I")
    .toUpperCase()
    .replace(/[\s.\-_]+/g, " ")      // "Dr. Öğr.  Üyesi" → "DR ÖĞR ÜYESİ"
    .trim();
}

/** Kanonik ünvan → hiyerarşi sırası. Yazım varyantları AÇIKÇA listelenir;
 *  tahmin ya da bulanık eşleşme yoktur. */
const AKADEMIK_UNVAN_HIYERARSISI = [
  { sira: 0, varyantlar: ["ARAŞTIRMA GÖREVLİSİ", "ARS GÖR", "ARŞ GÖR",
                          "ARAŞTIRMA GOREVLISI", "RESEARCH ASSISTANT"] },
  { sira: 1, varyantlar: ["ÖĞRETİM GÖREVLİSİ", "ÖĞR GÖR", "OGRETIM GOREVLISI",
                          "LECTURER", "INSTRUCTOR"] },
  { sira: 2, varyantlar: ["DOKTOR ÖĞRETİM ÜYESİ", "DR ÖĞR ÜYESİ",
                          "DOKTOR OGRETIM UYESI", "DR ÖĞR ÜYESI",
                          "ASSISTANT PROFESSOR"] },
  { sira: 3, varyantlar: ["DOÇENT", "DOÇ DR", "DOCENT", "DOÇ",
                          "ASSOCIATE PROFESSOR"] },
  { sira: 4, varyantlar: ["PROFESÖR", "PROF DR", "PROFESOR", "PROF",
                          "PROFESSOR"] },
];

/** Varyant → sıra sözlüğü. Modül yüklenirken bir kez kurulur. */
const _UNVAN_SIRA = (() => {
  const m = new Map();
  AKADEMIK_UNVAN_HIYERARSISI.forEach(({ sira, varyantlar }) =>
    varyantlar.forEach(v => m.set(_unvanNormalize(v), sira)));
  return m;
})();

/** Ünvanın hiyerarşi sırası. Haritada YOKSA `Infinity` döner.
 *
 *  Bilinmeyen bir ünvan ASLA bir kademeye zorlanmaz — yanlış kategoriye
 *  sokmak, sıralamayı hiç uygulamamaktan daha zararlıdır. Tanınmayanlar
 *  listenin sonuna, kendi aralarında API'nin verdiği sırayı koruyarak
 *  dizilir; böylece yeni bir ünvan eklendiğinde sessizce yanlış yerde
 *  görünmez, gözle fark edilir bir şekilde en altta belirir. */
function unvanSirasi(unvan) {
  const s = _UNVAN_SIRA.get(_unvanNormalize(unvan));
  return s === undefined ? Infinity : s;
}

/** `/titles` satırlarını akademik hiyerarşiye göre sıralar.
 *
 *  Girdiyi DEĞİŞTİRMEZ (yeni dizi döndürür) ve satırların içeriğine —
 *  `staff_count`, `share_percent` — dokunmaz. Yalnızca sıra değişir.
 *  Eşit sırada olanlar (yalnızca tanınmayanlar) API'nin özgün sırasını
 *  korur: `sort` kararlılığına güvenmek yerine özgün indeks açıkça
 *  ikinci ölçüt olarak kullanılır. */
function unvanaGoreSirala(satirlar) {
  return (satirlar || [])
    .map((r, i) => ({ r, i, s: unvanSirasi(r.title) }))
    .sort((a, b) => {
      /* `Infinity - Infinity` NaN üretir ve NaN döndüren bir karşılaştırma
         sıralamayı tanımsız hâle getirir. Bu yüzden eşitlik AÇIKÇA
         sınanır; aritmetiğe güvenilmez. */
      if (a.s !== b.s) return a.s < b.s ? -1 : 1;
      return a.i - b.i;
    })
    .map(x => x.r);
}

/* ==========================================================================
   BİRİM × METRİK ÇUBUĞU — YALNIZCA "Kadro ve Yük" PANELİNE AİT
   --------------------------------------------------------------------------
   NEDEN GLOBAL YARDIMCI KULLANILMIYOR
   -----------------------------------
   İstenen görünümde X ekseni METRİKLER, renkler ise BİRİMLERDİR. Global
   `karsilastirmaCubugu` ölçeklemeyi SERİ başına yapar (`maksimumlar[si]`);
   orada seri = metrik olduğu için bu doğrudur. Diziler basitçe devrik
   verilseydi seri = birim olurdu ve ölçekleme "birim başına" hâle gelirdi:
   akademisyen SAYISI ile ortalama ders SAATİ aynı maksimuma bölünür,
   çubuk yükseklikleri anlamsızlaşırdı. `gruplandirilmisCubuk` ise TEK bir
   ortak maksimum kullanır; farklı birimlerdeki metrikler için o da uygun
   değildir.

   Global fonksiyonların davranışını değiştirmek başka panelleri bozacağı
   için, bu panele ÖZEL ve yerel bir çizici yazıldı. `karsilastirmaCubugu`
   ve `gruplandirilmisCubuk` olduğu gibi durur.

   KORUNAN DAVRANIŞ
   ----------------
   "Her metrik KENDİ en yüksek değerine göre ölçeklenir; çubuk yüksekliği
   sıralamayı, üstündeki etiket GERÇEK değeri gösterir." Ölçekleme artık
   seri yerine KATEGORİ (metrik) başına yapılır — anlamı birebir aynıdır,
   çünkü bir metrik artık bir seri değil bir kategoridir.
   ========================================================================== */

/**
 * @param metrikler [{ ad, oku(satir), bicim? }]  → X eksenindeki gruplar
 * @param birimler  [{ ad, satir }]               → renk/legend (fakülte|bölüm)
 */
function birimMetrikCubugu(metrikler, birimler, opt = {}) {
  const seriler = (birimler || []).map((b, i) => ({
    ad: b.ad, renk: GRAFIK_RENK[i % GRAFIK_RENK.length], satir: b.satir,
  }));
  if (!metrikler.length || !seriler.length) {
    return bekleniyorGovde("Karşılaştırma için ölçülen metrik yok.");
  }

  const G = 760, Y = opt.yukseklik
    ? Math.max(170, Math.round(opt.yukseklik * .74)) : 205;
  const SOL = 72, SAG = 14, UST = 18;
  const ALT = 52 + Math.min(34, Math.max(...metrikler.map(m => m.ad.length)) * 1.1);
  const alan = G - SOL - SAG;
  const grupW = alan / metrikler.length;
  const cubukW = Math.max(4, (grupW * 0.74) / seriler.length);
  const taban = Y - ALT;

  /* Değerler API'den geldiği gibi okunur; hiçbir yeniden hesaplama yok. */
  const deger = (m, sr) => m.oku(sr.satir);
  /* Ölçekleme METRİK başına: her grup kendi en yüksek değerine göre. */
  const maksimumlar = metrikler.map(m =>
    Math.max(...seriler.map(sr => deger(m, sr)).filter(_sayiVar).map(Number), 1));

  let s = "";
  metrikler.forEach((m, gi) => {
    const x0 = SOL + gi * grupW + (grupW - cubukW * seriler.length) / 2;
    seriler.forEach((sr, si) => {
      const v = deger(m, sr);
      const x = x0 + si * cubukW;
      const bicim = m.bicim || (n => formatChartValue(n, opt));
      if (!_sayiVar(v)) {
        /* Ölçülmemiş değer SIFIR gibi çizilmez; boşluğu açıkça söyler. */
        s += `<text x="${x + cubukW / 2}" y="${taban - 4}" text-anchor="middle"
                 fill="var(--sonuk)" font-size="8">—<title>${esc(sr.ad)} · ${
                 esc(m.ad)}: ölçülmedi</title></text>`;
        return;
      }
      const h = Math.max(2, (Number(v) / maksimumlar[gi]) * (taban - UST));
      s += `<rect x="${x}" y="${taban - h}" width="${Math.max(1, cubukW - 2)}"
              height="${h}" rx="2" fill="${sr.renk}"><title>${esc(sr.ad)} · ${
              esc(m.ad)}: ${bicim(v)}</title></rect>`;
      /* Çubuk dar olduğunda etiket okunamayacak biçimde üst üste binerdi;
         o durumda gerçek değer yalnızca ipucunda kalır. */
      if (cubukW >= 15) {
        s += `<text x="${x + (cubukW - 2) / 2}" y="${taban - h - 3}"
                 text-anchor="middle" fill="var(--metin-2)"
                 font-size="7.5">${bicim(v)}</text>`;
      }
    });
    const cx = SOL + gi * grupW + grupW / 2;
    s += `<text x="${cx}" y="${taban + 14}" text-anchor="end" fill="var(--metin-2)"
             font-size="9" transform="rotate(-30 ${cx} ${taban + 14})"
             >${esc(m.ad.length > 20 ? m.ad.slice(0, 19) + "…" : m.ad)}</text>`;
  });
  s += `<line x1="${SOL}" y1="${taban}" x2="${G - SAG}" y2="${taban}" stroke="var(--kenar)"/>`;

  return gosterge(seriler)
    + `<svg viewBox="0 0 ${G} ${Y}" style="width:100%;height:auto"
            role="img" aria-label="Birimlerin metrik karşılaştırması">${s}</svg>`
    + `<div class="eksen-not">Her metrik KENDİ en yüksek değerine göre
        ölçeklendi (birimleri farklı). Çubuk yüksekliği sıralamayı,
        üstündeki etiket gerçek değeri gösterir.</div>`;
}

EKRANLAR.akademik = {
  baslik: "Akademisyenler",
  altBaslik: "Kadro, ders yükü ve akademik üretkenlik",
  ciz() {
    return `<div id="akKpi" class="kpi-serit">${iskeletHtml(2)}</div>
      <div class="izgara-3">
        ${panel("Ders Yükü Durumu", "Yıllara göre verilen toplam ders saati.",
          iskeletHtml(6), { id: "akYuk" })}
        ${panel("Akademik Ünvan Dağılımı", "Aktif kadronun kıdem yapısı.",
          iskeletHtml(6), { id: "akUnvan" })}
        ${panel("Bölüm Bazında Kadro ve Yük",
          "Akademisyen, öğrenci/akademisyen ve müfredat dersi bir arada.",
          /* Başlık kapsama göre `yukle()` içinde güncellenir: üniversite
             kapsamında seriler fakülte, fakülte kapsamında bölümdür. */
          iskeletHtml(6), { id: "akBolum", basId: "akBolumBas" })}
      </div>
      <div class="izgara-3">
        ${panel("Yayın Performansı", "YÖK Akademik profillerinden.", iskeletHtml(4), { id: "akYayin" })}
        ${panel("Akademik Üretim Göstergeleri", "Atıf, proje ve patent — yetkili veri yoksa dosya kaynağı.",
          iskeletHtml(4), { id: "akKaynak" })}
        ${panel("Ders Anket Sonuçları", "Öğrenci değerlendirme ortalamaları.",
          iskeletHtml(5), { id: "akAnket" })}
      </div>
      <div class="izgara-21">
        ${panel("Akademisyen İhtiyaç Analizi",
          "Mevcut kadro ile ders yükünün karşılanma durumu.", iskeletHtml(5), { id: "akIhtiyac" })}
        ${panel("Maaş Senaryoları", "Maaş artışının bütçeye etkisi.",
          iskeletHtml(5), { id: "akMaas" })}
      </div>`;
  },
  yukle() {
    const p = kapsam();
    dataSourceGroupLoad("akKaynak",
      ["citation_count", "project_count", "patent_count"]);
    doldur("akKpi", () => Promise.all([
      api.get("/api/decision-analytics/staffing", p),
      api.get("/api/decision-analytics/titles", p),
    ]), ([k, t]) => {
      const bul = ad => (t.find(x => x.title === ad) || {}).staff_count;
      const gencKadro = t.length
        ? (bul("ÖĞRETİM GÖREVLİSİ") || 0) + (bul("ARAŞTIRMA GÖREVLİSİ") || 0)
        : null;
      return kpi("Akademik Personel Sayısı", sayi(k.academic_staff_count), "aktif kadro",
                 { ikon: "🎓", renk: "mavi" })
        + kpi("Profesör", sayi(bul("PROFESÖR")), yuzdePay(bul("PROFESÖR"), k.academic_staff_count),
              { ikon: "◆", renk: "yesil" })
        + kpi("Doçent", sayi(bul("DOÇENT")), yuzdePay(bul("DOÇENT"), k.academic_staff_count),
              { ikon: "◈", renk: "yesil" })
        + kpi("Dr. Öğr. Üyesi", sayi(bul("DOKTOR ÖĞRETİM ÜYESİ")),
              yuzdePay(bul("DOKTOR ÖĞRETİM ÜYESİ"), k.academic_staff_count), { ikon: "◇", renk: "mor" })
        + kpi("Öğr. Gör. & Arş. Gör.",
              sayi(gencKadro),
              "", { ikon: "○", renk: "mavi" })
        + kpi("Fiilen Ders Veren", sayi(k.active_teaching_staff_count),
              `${sayi(k.academic_staff_count)} kadronun içinde`, { ikon: "▤", renk: "turuncu" })
        
    }, { iskelet: 2 });

    /* KURULUŞ ÖNCESİ DÖNEMLER GÖSTERİLMEZ.
       ------------------------------------------------------------------
       Uç, ders kayıtlarının bulunduğu bütün dönemleri döndürüyor ve
       bunların içinde 2016-2017 … 2019-2020 da var. Ankara Bilim
       Üniversitesi 2020'de kurulduğu için o dönemler kurumun kendi
       geçmişi DEĞİLDİR; grafikte "yükselen eğri"nin bir bölümünü
       kurumun var olmadığı yıllar oluşturuyordu.

       Süzme YALNIZCA BU KARTIN çizim adımında yapılır:
         * veritabanına dokunulmaz, kayıt silinmez,
         * uç yanıtı değişmez (başka tüketiciler etkilenmez),
         * başka grafiklerin yıl aralığı olduğu gibi kalır.

       Ölçüt SEMANTİKTİR: dönem etiketinin BAŞLANGIÇ YILI okunur ve
       `KURULUS_YILI` ile karşılaştırılır. Dizinin ilk dört elemanını
       kesmek de aynı görüntüyü verirdi ama veri bir dönem kaydığında
       sessizce yanlış olurdu. Ayrıştırılamayan bir etiket ELENMEZ:
       bilinmeyen bir biçim yüzünden gerçek veri kaybolmamalı.

       İki seri de aynı `rows` dizisinden çizildiği için başlangıç
       dönemleri kendiliğinden aynı olur. `paneliBuyut()` panelin O ANKİ
       gövdesini kopyaladığından ⛶ ile açılan büyük görünüm de aynı
       süzülmüş veriyi gösterir; modal için ayrı bir yol yoktur. */
    const KURULUS_YILI = 2020;
    const kurulustanSonra = satirlar => satirlar.filter(r => {
      const m = /^(\d{4})/.exec(String(r.academic_year || ""));
      return m ? Number(m[1]) >= KURULUS_YILI : true;
    });

    doldur("akYuk", () => api.get("/api/decision-analytics/teaching-load/trend", p), ham => {
      const rows = kurulustanSonra(ham);
      if (!rows.length) return bekleniyorGovde("Ders kaydı yok.");
      return cizgi(rows.map(r => r.academic_year), [
        { ad: "Verilen ders saati", renk: "var(--vurgu)", veri: rows.map(r => r.total_weekly_hours) },
        { ad: "Ders veren akademisyen", renk: "var(--vurgu-2)", veri: rows.map(r => r.teaching_staff_count) },
      ], { yb: v => fmt.int(Math.round(v)) })
      + `<div class="not" style="margin-top:6px">"Vermesi gereken ders saati" (norm kadro)
         <span class="bekleniyor">◷ veri bekleniyor</span></div>`;
    }, { iskelet: 6 });

    /* UNVAN: tek yığın sütun kadronun kıdem yapısını bütün olarak,
       yatay sütun da unvanları AKADEMİK HİYERARŞİ sırasında gösterir.

       SIRALAMA NEDEN SAYIYA GÖRE DEĞİL
       --------------------------------
       API (`/titles`) satırları kadro sayısına göre azalan döndürür ve bu
       DOĞRUDUR: başka tüketiciler (KPI şeridi, asistan) o sırayı bekler ve
       API'nin gerçek verisine dokunulmaz. Ama bu panelde okunan şey bir
       "en çok hangisi" listesi değil, kadronun KIDEM YAPISIDIR. Sayıya
       göre sıralamak, ünvanları her dönem farklı yerlere atar; okuyucu
       piramidi göremez, iki dönemi gözle karşılaştıramaz.

       Bu yüzden sıralama YALNIZCA BURADA, çizimden önce, tek noktada
       uygulanır. Global `yatayCubuk`/`yiginCubuk` yardımcılarının
       davranışı DEĞİŞTİRİLMEZ; onlar kendilerine verilen diziyi olduğu
       gibi çizer. Böylece diğer hiçbir grafik etkilenmez.

       TEK KAYNAK, İKİ GÖRÜNÜM
       -----------------------
       `paneliBuyut()` panelin O ANKİ gövdesini kopyalar; yeniden veri
       çekmez, yeniden hesaplamaz. Dolayısıyla burada hazırlanan tek
       sıralı dizi hem küçük panele hem de ⛶ ile açılan büyük görünüme
       aynen gider. Modal için AYRI bir sıralama yoktur ve olamaz. */
    doldur("akUnvan", () => api.get("/api/decision-analytics/titles", p), rows => {
      if (!rows.length) return bekleniyorGovde("Bu dönemde kadro kaydı yok.");
      const renkler = ["var(--vurgu)", "var(--vurgu-2)", "var(--mor)",
                       "var(--uyari)", "var(--pembe)", "#46b3e6"];
      /* RENK KİMLİĞİ ÜNVANA BAĞLANIR, SIRAYA DEĞİL.
         Renk, API'nin ORİJİNAL sırasındaki konumdan üretilir; sıralama
         sonradan uygulanır. Sonuç: her ünvan bugünkü rengini birebir
         korur, buna rağmen legend / yığın sütun / yatay çubuk aynı
         ünvan-renk eşleşmesini kullanır (üçü de bu tek diziden beslenir). */
      /* TEK SIRALI DİZİ — ekranda yukarıdan aşağıya okunacak sıra.
         Aşağıdaki iki gösterim de YALNIZCA bundan türetilir. */
      const veri = unvanaGoreSirala(
        rows.map((r, i) => ({ ...r, renk: renkler[i % renkler.length] })));

      /* YIĞIN SÜTUN ÇİZİM YÖNÜ
         ----------------------
         `yiginCubuk` serileri taban çizgisinden YUKARI doğru yığar
         (`birikim` 0'dan başlar): dizinin İLK elemanı sütunun EN ALTINDA
         çizilir. Dolayısıyla ekranda yukarıdan aşağıya "Araştırma
         Görevlisi → Profesör" okunması için seri dizisi ters verilmelidir.

         Bu bir İKİNCİ SIRALAMA DEĞİLDİR — aynı `veri` dizisinin ters
         okunuşudur. İki gösterim tek kaynaktan beslendiği için biri
         değişip diğeri değişmeden kalamaz. `slice()` özgün diziyi korur;
         `reverse()` yerinde çalışır ve altındaki `yatayCubuk`u bozardı. */
      /* HALKA — tek sütunlu yığın grafiğin yerine.
         Eskiden "Aktif kadro" adında TEK kategorili bir yığın sütun
         çiziliyordu. Tek sütunlu yığın grafik zaten halkanın çubuğa
         katlanmış hâlidir ve dar panelde okunmuyordu; üstelik altındaki
         yatay çubuklarla AYNI soruyu cevaplıyordu.

         Artık iki gösterim farklı iş yapar:
           halka  → pay ("kadronun bileşimi nasıl?")
           çubuk  → kesin sayı ve sıra ("kaç kişi?")

         Ters çevirme de gerekmez: halka diziyi verildiği sırada saat
         yönünde çizer ve gösterge aynı diziden üretilir. Böylece
         gösterge ile aşağıdaki çubuklar AYNI yönde okunur — eskiden
         yığın sütuna dizi ters verildiği için gösterge, çubuklarla zıt
         sıradaydı (üstte Profesör, altta Araştırma Görevlisi). */
      return dagilimHalkasi(veri.map(r => ({
          ad: r.title, deger: r.staff_count, renk: r.renk })),
        { merkezEtiket: "aktif kadro" })
      + yatayCubuk(veri.map(r => ({
          ad: r.title, deger: r.staff_count, renk: r.renk })),
        { eksenY: "unvana göre kadro · akademik hiyerarşi sırasıyla" });
    }, { iskelet: 6 });

    /* BİRİM BAZINDA ÇOKLU METRİK — X ekseni METRİKLER, renkler BİRİMLER.
       Kapsam üniversiteyse seriler fakülteler, fakülte seçiliyse o
       fakültenin bölümleridir; ikisini de `child-breakdown` verir. */
    /* ADAPTİF: alt birim kalmadığında panel boş "veri bekleniyor" kutusuna
       düşmez; birimin fakülte içindeki KADRO RİSKİ konumuna dönüşür. */
    const akUst = ebeveynKapsami();
    doldur("akBolum", () => Promise.all([
      api.get("/api/decision-analytics/child-breakdown", p),
      akUst && akUst.ustKapsamVar
        ? api.get("/api/decision-analytics/child-breakdown", akUst.p).catch(() => null)
        : Promise.resolve(null),
    ]), ([o, ustVeri]) => {
      const bas = document.getElementById("akBolumBas");
      /* "Anlamlı satır" = kadro/yük alanlarından en az biri ÖLÇÜLMÜŞ satır.
         Bölüm kapsamında dönen tek program satırının bu alanları `null`dur;
         sayınca 1 görünüp grafiği boş çizdiriyordu. */
      const anlamli = (o.rows || []).filter(x =>
        _sayiVar(x.academic_staff_count) || _sayiVar(x.students_per_academic_staff)
        || _sayiVar(x.curriculum_course_count) || _sayiVar(x.average_teaching_load_hours));
      if (anlamli.length < 2) {
        const kardesler = (ustVeri && ustVeri.rows) || [];
        const kendi = kardesler.find(x => x.unit_id === (akUst || {}).kendiId);
        const govde = kendi && konumGovdesi([
          { ad: "Öğrenci/akademisyen yükü", oku: r => r.students_per_academic_staff,
            yuksekIyi: false },
          { ad: "Ortalama ders saati", oku: r => r.average_teaching_load_hours,
            yuksekIyi: false },
          { ad: "Akademisyen başına ders", oku: r => r.courses_per_active_academic,
            yuksekIyi: false },
          { ad: "Kadro derinliği", oku: r => r.academics_per_100_students,
            yuksekIyi: true },
          /* Ders veren kadro oranı: iki ham sayıdan TÜRETİLİR, ikisi de
             ekranda ayrı ayrı duruyor ama bu oran hiçbir yerde yok. */
          { ad: "Ders veren kadro oranı", yuksekIyi: true,
            oku: r => (_sayiVar(r.active_teaching_staff_count)
                       && _sayiVar(r.academic_staff_count) && r.academic_staff_count)
              ? r.active_teaching_staff_count / r.academic_staff_count * 100 : null },
        ], kendi, kardesler, { ustAd: (akUst || {}).ustAd });
        if (!govde) { paneliGoster("akBolum", false); return ""; }
        paneliGoster("akBolum", true);
        if (bas) bas.textContent = "Kadro Riski ve Fakülte Konumu";
        return govde;
      }
      paneliGoster("akBolum", true);
      const r = anlamli.slice(0, 9);
      if (bas) {
        bas.textContent = seviye() === "university"
          ? "Fakülte Bazında Kadro ve Yük"
          : "Bölüm Bazında Kadro ve Yük";
      }
      /* Metrik tanımları TEK yerde: ad, okuyucu ve biçim bir arada durur ki
         bir metrik eklendiğinde üçü birden ayrışmasın. Hesaplar API'den
         geldiği gibi kullanılır; burada hiçbir değer yeniden üretilmez. */
      return birimMetrikCubugu([
        { ad: "Akademisyen",          oku: x => x.academic_staff_count },
        { ad: "Öğrenci / Akademisyen", oku: x => x.students_per_academic_staff,
          bicim: v => ondalik(v, 1) },
        { ad: "Müfredat dersi",       oku: x => x.curriculum_course_count },
        { ad: "Ortalama ders saati",  oku: x => x.average_teaching_load_hours,
          bicim: v => ondalik(v, 1) },
      ], r.map(x => ({ ad: birimAdi(x.code, x.name), satir: x })),
        { yukseklik: 270 });
    }, { iskelet: 6 });

    doldur("akYayin", () => Promise.all([
      api.get("/api/decision-analytics/publications", p),
      api.get("/api/decision-analytics/publication-quality", p),
    ]), ([rows, kalite]) => {
      if (!rows.length) return bekleniyorGovde(
        "Bu kapsam ve dönemde yayın/kadro anlık görüntüsü yok.");
      const toplam = rows.reduce((t, r) => t + (r.total_publications || 0), 0);
      const kisi = rows.reduce((t, r) => t + (r.academic_staff_count || 0), 0);
      return `<div class="kpi-serit" style="margin:0">
        ${kpi("Toplam Yayın", sayi(toplam), "YÖK Akademik", { ikon: "📄", renk: "yesil" })}
        ${kpi("Akademisyen Başına", ondalik(kisi ? toplam / kisi : null, 2), "yayın",
              { ikon: "÷", renk: "mavi" })}
        ${kpi("Q1 Yayın Oranı", kalite.available ? yuzde(kalite.q1_publication_rate, 1) : null,
              kalite.available ? esc(dataSourceCaption(kalite.q1_source)) : null,
              { ikon: "①", renk: "turuncu", kaynak: kalite.note })}
        ${kpi("H-indeks", kalite.available ? sayi(kalite.estimated_h_index) : null,
              kalite.available ? esc(dataSourceCaption(kalite.h_index_source)) : null,
              { ikon: "H", renk: "mor", kaynak: kalite.note })}
      </div>${kalite.available ? `<div class="not" style="margin-top:8px">${esc(kalite.note)}</div>` : ""}`;
    }, { iskelet: 4 });

    doldur("akAnket", () => api.get("/api/decision-analytics/course-surveys", p), o => {
      if (!o.available) return bekleniyorGovde(o.note || "Ders anketi analitiği yok.");
      return `<div class="kpi-serit" style="margin:0">
        ${kpi("Ortalama Puan", `${ondalik(o.average_course_evaluation_score, 2)} / 5`,
              `${sayi(o.evaluation_count)} toplu katılım`, { ikon: "★", renk: "mor" })}
        ${kpi("Ders Memnuniyeti", yuzde(o.course_satisfaction_rate, 1),
              "toplulaştırılmış", { ikon: "✓", renk: "yesil" })}
        ${kpi("Öğretim Elemanı", yuzde(o.instructor_satisfaction_rate, 1),
              "memnuniyet", { ikon: "🎓", renk: "mavi" })}
        ${kpi("Yanıt Oranı", yuzde(o.course_survey_response_rate, 1),
              `${sayi(o.eligible_student_count)} uygun öğrenci`, { ikon: "%", renk: "turuncu" })}
      </div><div class="not" style="margin-top:8px">${esc(dataSourceCaption(o))} · ${esc(o.note)}</div>`;
    }, { iskelet: 5 });

    doldur("akMaas", () => api.get("/api/decision-analytics/salary-scenarios", p), o => {
      if (!o.available) return bekleniyorGovde(o.note || "Maaş senaryosu hesaplanamadı.");
      return gruplandirilmisCubuk(["Baz", "+%10", "+%20"], [{
          ad: "Yıllık akademik personel gideri",
          veri: [o.payroll_scenario_base_musd, o.payroll_scenario_plus_10_musd,
                 o.payroll_scenario_plus_20_musd], birim: "milyon USD",
        }], { eksenY: "milyon USD", yb: v => fmt.usdMillion(v, 1), yukseklik: 210 })
        + `<div class="not" style="margin-top:8px">Aylık baz tahmin <b>${fmt.usdMillion(o.estimated_monthly_academic_payroll_musd, 3)}</b> ·
          akademisyen başına yıllık planlama maliyeti <b>${fmt.usd(o.estimated_average_annual_academic_cost_usd, 0)}</b>.<br>
          ${esc(dataSourceCaption(o))} · ${esc(o.note)}</div>`;
    }, { iskelet: 5 });

    doldur("akIhtiyac", () => Promise.all([
      api.get("/api/decision-analytics/staffing", p),
      api.get("/api/decision-analytics/teaching-load", p),
    ]), ([k, y]) => {
      if (!k.available) return bekleniyorGovde(
        k.note || "Bu kapsam ve dönemde kadro ölçümü yok.");
      /* Sayısal tablo DETAYA indi; üstte grafik var. */
      return gruplandirilmisCubuk(["Kadro"], [
          { ad: "Toplam kadro", veri: [k.academic_staff_count] },
          { ad: "Fiilen ders veren", veri: [k.active_teaching_staff_count] },
          { ad: "Ders yükü kaydı yok", veri: [k.staff_without_teaching_load] },
        ], { eksenY: "akademisyen", yukseklik: 200 })
      + detay("Sayısal tabloyu göster", `<table><tbody>
        <tr><td>Mevcut akademik kadro</td><td><b>${sayi(k.academic_staff_count)}</b></td></tr>
        <tr><td>Fiilen ders veren</td><td><b>${sayi(k.active_teaching_staff_count)}</b></td></tr>
        <tr><td>Ders yükü kaydı olmayan</td><td class="${
          k.staff_without_teaching_load ? "kotu" : ""}"><b>${sayi(k.staff_without_teaching_load)}</b></td></tr>
        <tr><td>Öğrenci / akademisyen</td><td><b>${ondalik(k.students_per_academic_staff, 1)}</b></td></tr>
        <tr><td>100 öğrenciye akademisyen</td><td><b>${ondalik(k.academics_per_100_students, 2)}</b></td></tr>
        <tr><td>Ortalama haftalık ders saati</td><td><b>${ondalik(y.average_hours, 1)}</b></td></tr>
        <tr><td>Ortanca haftalık ders saati</td><td><b>${sayi(y.median_hours)}</b></td></tr>
        </tbody></table>`)
        + `<div class="eksen-not" style="margin-top:8px">Norm kadro (vermesi gereken saat) tanımlandığında
        ideal kadro ve açık otomatik hesaplanacaktır.
        <span class="bekleniyor">◷ norm verisi bekleniyor</span></div>`;
    }, { iskelet: 5 });
  },
};

const yuzdePay = (a, b) => (a && b) ? yuzde(a / b * 100, 1) : "";

/* --------------------------------------------------------------------------
   4) ALTYAPI KULLANIMI
   -------------------------------------------------------------------------- */
EKRANLAR.altyapi = {
  baslik: "Altyapı Kullanımı",
  altBaslik: "Derslik, laboratuvar ve kapasite analizi",
  ciz() {
    const kapsamNotu = seviye() === "program"
      ? "Kaynakta program bazlı mekân tahsisi yoktur; bölüm kapasitesi programa devredilmez."
      : "Fakülteye veya bölüme kimlikle tahsis edilmiş mekânlar.";
    return `<div id="alKpi" class="kpi-serit">${iskeletHtml(2)}</div>
      <div class="izgara-1">
        ${panel("Derslik Kullanım Haritası",
          "Kat planları üzerinde gerçek ders programından türetilmiş kullanım yoğunluğu.",
          iskeletHtml(8), { id: "alHarita" })}
      </div>
      <div class="izgara-3">
        ${panel("Mekân Türüne Göre Kapasite", "Derslik ve laboratuvar dağılımı.",
          iskeletHtml(5), { id: "alTur" })}
        ${panel("Altyapı Kullanım Oranları", "Derslik ve laboratuvar — yetkili ölçüm yoksa dosya kaynağı.",
          iskeletHtml(4), { id: "alKaynak" })}
        ${panel("Mekânların Kapasite Dağılımı",
          "Derslik ve laboratuvarların kişi kapasitesine göre dağılımı.",
          iskeletHtml(4), { id: "alKisi" })}
      </div>
      <div class="izgara-21">
        ${panel("Öğrenci Sayısına Göre İhtiyaç Projeksiyonları",
          "Kayıt artış senaryolarında derslik kapasitesi yeterli mi?", iskeletHtml(6), { id: "alProjeksiyon" })}
        ${panel("Birim Bazında Kapasite", kapsamNotu,
          iskeletHtml(6), { id: "alBirim" })}
      </div>
      <div class="izgara-2">
        ${panel("Derslik Envanteri", "Kurumun gerçek mekân listesi.", iskeletHtml(8), { id: "alListe" })}
        ${panel("Ofis / Kütüphane / Ortak Alan", "Diğer mekân türleri.",
          iskeletHtml(6), { id: "alTamamlayici" })}
      </div>
      <div class="dip-not">ⓘ Fiziksel mekân envanteri akademik yıl boyutu
        taşımadığı için dönem seçiminden bağımsızdır; öğrenci ve kadro
        paydaları ise seçili döneme aittir.</div>`;
  },
  yukle() {
    const p = kapsam();
    /* DERSLİK KULLANIM HARİTASI — kapsam/dönem taşımaz: kaynak, bir
       dönemin ders programı dosyasıdır ve fakülte/bölüm süzgeciyle
       bölünmez. Gün/saat/kat süzgeçleri panelin kendi içindedir. */
    /* İki uç birlikte çekilir: kullanım verisi (salt okunur) ve
       KALICI eşleştirme dosyası. Eşleştirme okunamazsa harita yine
       çalışır — sadece kullanıcı alanları görünmez. */
    doldur("alHarita", () => Promise.all([
      api.get("/api/physical-resources/classroom-usage-map"),
      api.get("/api/physical-resources/classroom-map-areas").catch(() => null),
      api.get("/api/physical-resources/classroom-vector-plans").catch(() => null),
    ]), ([o, esleme, plan]) => derslikHaritasiGovde(o, esleme, plan),
        { iskelet: 8 });
    dataSourceGroupLoad("alKaynak",
      ["classroom_utilization_rate", "laboratory_utilization_rate"]);
    doldur("alTamamlayici",
      () => api.get("/api/decision-analytics/supplementary-facilities", p), o => {
        if (!o.available) return bekleniyorGovde(o.note || "Tamamlayıcı mekân analitiği yok.");
        return `<div class="kpi-serit" style="margin:0">
          ${kpi("Ofis", sayi(o.office_count), `${sayi(o.office_area_m2)} m²`, { ikon: "▤", renk: "mavi" })}
          ${kpi("Kütüphane", sayi(o.library_count), `${sayi(o.library_area_m2)} m²`, { ikon: "▥", renk: "yesil" })}
          ${kpi("Ortak Alan", sayi(o.common_area_count), `${sayi(o.common_area_m2)} m²`, { ikon: "◇", renk: "mor" })}
          ${kpi("Çalışma Kapasitesi", sayi(o.study_area_capacity), "kişi", { ikon: "◱", renk: "turuncu" })}
        </div><div class="not" style="margin-top:8px">Toplam tamamlayıcı alan <b>${sayi(o.supplementary_area_m2)} m²</b> ·
          ${esc(dataSourceCaption(o))} · ${esc(o.note)}</div>`;
      }, { iskelet: 6 });
    doldur("alKpi", () => Promise.all([
      api.get("/api/physical-resources/capacity/overview", p).catch(() => null),
      api.get("/api/decision-analytics/staffing", p),
      dataSourceAvailability("facility_occupancy_rate"),
    ]), ([o, k, doluluk]) => {
      if (!o) return bekleniyorGovde("Bu kapsamda mekân kaydı yok.");
      return kpi("Toplam Öğrenci", sayi(k.student_count),
                 ogrenciKaynagi(k.student_count_source), { ikon: "👥", renk: "mavi" })
        + kpi("Akademik Personel", sayi(k.academic_staff_count), "aktif", { ikon: "🎓", renk: "yesil" })
        + kpi("Toplam Mekân", sayi(o.total_facilities), "derslik + laboratuvar",
              { ikon: "🏗", renk: "mor" })
        + kpi("Sınıf Kapasitesi", sayi(o.total_capacity), "fiziksel koltuk",
              { ikon: "◱", renk: "turuncu" })
        + kpi("Öğrenci Kapasitesi", sayi(o.total_student_capacity), "planlamada kullanılabilir",
              { ikon: "◪", renk: "yesil" })
        + kpi("Doluluk Oranı",
              doluluk.resolved_value == null ? null : yuzde(doluluk.resolved_value, 1),
              doluluk.resolved_value == null ? null : esc(dataSourceCaption(doluluk)),
              { ikon: "◐", renk: "kirmizi", kaynak: "Kullanım ölçümü aktarılmadı" });
    }, { iskelet: 2 });

    doldur("alTur", () => api.get("/api/physical-resources/capacity/by-type", p), rows => {
      if (!rows.length) return bekleniyorGovde("Mekân kaydı yok.");
      /* EKSEN YÖNÜ: METRİK = KATEGORİ, MEKÂN TÜRÜ = SERİ.
         ------------------------------------------------------------
         Eskiden tersiydi (mekân türü kategori, metrik seri). O düzende
         okunan soru "Dersliğin üç metriği nedir?" oluyordu; oysa bu
         panelin sorusu "Her metrikte derslik ile laboratuvar nasıl
         kıyaslanıyor?".

         `olcekKategoriBazli` ZORUNLUDUR: seriler artık farklı birimlerde
         metrikler değil, KARŞILAŞTIRILAN İKİ VARLIK. Seri bazlı ölçekle
         Derslik'in 3.171 koltuğu ile Laboratuvar'ın 607'si ikisi de tam
         yükseklik çizilir ve grafik iki kapasiteyi eşit gösterirdi.

         Veri dönüştürülmez, yalnızca YENİDEN DİZİLİR: `rows` içindeki
         alanlar olduğu gibi okunur, hiçbir toplama/oran hesabı yoktur. */
      const tur = r => r.facility_type === "laboratory" ? "Laboratuvar" : "Derslik";
      /* Derslik önce: gösterge ve çubuk sırası kaynak sırasına değil,
         okunabilir bir düzene bağlansın. */
      const sirali = rows.slice().sort((a, b) =>
        (a.facility_type === "laboratory" ? 1 : 0)
        - (b.facility_type === "laboratory" ? 1 : 0));
      return karsilastirmaCubugu(
        ["Mekân sayısı", "Koltuk kapasitesi", "Öğrenci kapasitesi"],
        sirali.map(r => ({
          ad: tur(r),
          veri: [r.facility_count, r.total_capacity, r.total_student_capacity],
        })),
        { yukseklik: 220, olcekKategoriBazli: true });
    }, { iskelet: 5 });

    /* MEKÂNLARIN KAPASİTE DAĞILIMI
       ------------------------------------------------------------------
       Bu kart eskiden "Öğrenci Başına Kapasite" idi ve toplam koltuk /
       öğrenci kapasitesi / öğrenci sayısını yan yana koyuyordu — yani
       sayfadaki diğer kartların zaten cevapladığı "toplam kapasitemiz
       kaç?" sorusunu tekrarlıyordu.

       Yeni soru: "fiziksel mekânlarımız hangi büyüklüklerde
       yoğunlaşıyor?" Bunun cevabı toplamdan çıkarılamaz; ODA BAZLI
       veri gerekir. `/facilities` ucu zaten her mekânı tek tek
       döndürüyor (kod, tür, kapasite), bu yüzden backend'e dokunulmadı
       ve histogram burada sayılıyor.

       KAPASİTESİ BİLİNMEYEN MEKÂN SIFIR SAYILMAZ. `capacity` alanı boş
       olan oda hiçbir kutuya girmez; sayısı grafiğin altında ayrıca
       belirtilir. Aksi hâlde ölçülmemiş bir oda "0 kişilik" gibi
       okunurdu.

       Yalnızca derslik ve laboratuvar alınır; `facility_type` API'nin
       kendi kanonik değeridir, burada yeni bir sınıflandırma
       tanımlanmaz. */
    /* `limit`: ucun varsayılanı 100'dür. Bugün 80 mekân var ama kapsam
       büyüdüğünde liste sessizce kesilip histogram eksik sayardı. */
    doldur("alKisi",
      () => api.get("/api/physical-resources/facilities", { ...p, limit: 500 }),
      mekanlar => {
      const KUTULAR = [
        { ad: "0–30",   sinir: v => v <= 30 },
        { ad: "31–50",  sinir: v => v > 30 && v <= 50 },
        { ad: "51–75",  sinir: v => v > 50 && v <= 75 },
        { ad: "76–100", sinir: v => v > 75 && v <= 100 },
        { ad: "100+",   sinir: v => v > 100 },
      ];
      const TURLER = [
        { anahtar: "classroom",  ad: "Derslik" },
        { anahtar: "laboratory", ad: "Laboratuvar" },
      ];

      const ilgili = (mekanlar || []).filter(m =>
        TURLER.some(t => t.anahtar === m.facility_type));
      if (!ilgili.length) return bekleniyorGovde("Derslik ya da laboratuvar kaydı yok.");

      const olculen = ilgili.filter(m => _sayiVar(m.capacity));
      const eksik = ilgili.length - olculen.length;
      if (!olculen.length) {
        return bekleniyorGovde("Mekân kapasiteleri henüz ölçülmedi.");
      }

      const seriler = TURLER.map(t => ({
        ad: t.ad,
        veri: KUTULAR.map(k => olculen.filter(m =>
          m.facility_type === t.anahtar && k.sinir(Number(m.capacity))).length),
      }));

      return karsilastirmaCubugu(KUTULAR.map(k => k.ad), seriler, {
        yukseklik: 200,
        olcekOrtak: true,   /* hepsi "adet" — tek eksen */
        yEkseni: true,
        birim: "mekân",
        eksenNot: `Çubuklar mekân SAYISINI gösterir, kapasite toplamını değil. `
          + `Grafikte ${olculen.length} mekân var`
          + (eksik ? `; ${eksik} mekânın kapasitesi ölçülmediği için hiçbir `
                     + `aralığa girmedi (sıfır sayılmadı).` : "."),
      });
    }, { iskelet: 4 });

    doldur("alProjeksiyon", () => Promise.all([
      api.get("/api/physical-resources/capacity/overview", p).catch(() => null),
      api.get("/api/decision-analytics/staffing", p),
    ]), ([o, k]) => {
      if (!o || !k.student_count) return bekleniyorGovde("Projeksiyon için kapasite ve öğrenci sayısı gerekir.");
      /* KAPASİTE İHTİYACI: derslik koltuk kapasitesi bir anda TÜM
         öğrencileri değil, aynı anda derste olan öğrenciyi barındırır.
         Eşzamanlılık oranı bir VARSAYIMDIR ve ekranda açıkça yazılır;
         gizli bir katsayı kullanılmaz. */
      const esZaman = 0.35;
      const senaryolar = [0, 10, 20, 30, 50];
      const satir = senaryolar.map(a => {
        const ogr = Math.round(k.student_count * (1 + a / 100));
        const gerek = Math.round(ogr * esZaman);
        const fark = o.total_capacity - gerek;
        return `<tr${a === 0 ? ' class="bizim"' : ""}>
          <td>${a === 0 ? "Mevcut" : "%" + a + " artış"} (${sayi(ogr)})</td>
          <td>${sayi(gerek)}</td><td>${sayi(o.total_capacity)}</td>
          <td class="${fark < 0 ? "kotu" : "iyi"}">${fark >= 0 ? "+" : ""}${sayi(fark)}</td></tr>`;
      }).join("");
      return `<table>
        <thead><tr><th>Öğrenci senaryosu</th><th>Gereken koltuk</th>
          <th>Mevcut</th><th>Fark</th></tr></thead>
        <tbody>${satir}</tbody></table>
        <div class="not" style="margin-top:8px">
          Eşzamanlılık varsayımı: öğrencilerin <b>%${esZaman * 100}</b>'i aynı anda derste.
          Bu bir planlama varsayımıdır, ölçüm değildir.</div>`;
    }, { iskelet: 6 });

    /* BİRİM KAPASİTESİ: mekân sayısı ile koltuk kapasitesi farklı
       büyüklükte olduğu için ölçekli karşılaştırma; tablo detaya indi. */
    doldur("alBirim", () => api.get("/api/physical-resources/capacity/by-department", p),
      rows => {
        if (!rows.length) return bekleniyorGovde("Bu kapsamda tahsisli mekân yok.");
        const r = rows.slice(0, 10);
        return karsilastirmaCubugu(r.map(x => x.department_name), [
            { ad: "Mekân sayısı", veri: r.map(x => x.facility_count) },
            { ad: "Koltuk kapasitesi", veri: r.map(x => x.total_capacity) },
            { ad: "Öğrenci kapasitesi", veri: r.map(x => x.total_student_capacity) },
          ], { yukseklik: 260 })
        + detay("Kapasite tablosunu göster", `<table>
            <thead><tr><th>Birim</th><th>Mekân</th><th>Koltuk</th><th>Öğr. kap.</th></tr></thead>
            <tbody>${rows.map(x => `<tr><td style="text-align:left">${esc(x.department_name)}</td>
              <td>${sayi(x.facility_count)}</td><td>${sayi(x.total_capacity)}</td>
              <td>${sayi(x.total_student_capacity)}</td></tr>`).join("")}</tbody></table>`);
      }, { iskelet: 6 });

    doldur("alListe", () => api.get("/api/physical-resources/facilities",
      kapsam({ limit: 200 })), rows => {
      const liste = Array.isArray(rows) ? rows : (rows.items || []);
      if (!liste.length) return bekleniyorGovde("Bu kapsamda mekân yok.");
      /* ENVANTER: önce KAT bazında dağılım grafiği (yönetici "hangi
         katta ne kadar kapasite var" sorusuna bakar), ham liste detayda. */
      const kat = {};
      liste.forEach(r => {
        const k = r.floor === null || r.floor === undefined ? "Belirtilmemiş"
                : `${r.floor}. kat`;
        kat[k] = kat[k] || { derslik: 0, lab: 0, koltuk: 0 };
        kat[k][r.facility_type === "laboratory" ? "lab" : "derslik"] += 1;
        kat[k].koltuk += Number(r.capacity) || 0;
      });
      const katlar = Object.keys(kat).sort();
      const grafik = karsilastirmaCubugu(katlar, [
        { ad: "Derslik", veri: katlar.map(k => kat[k].derslik) },
        { ad: "Laboratuvar", veri: katlar.map(k => kat[k].lab) },
        { ad: "Koltuk", veri: katlar.map(k => kat[k].koltuk) },
      ], { yukseklik: 230 });
      return grafik + detay(`Mekân listesini göster (${liste.length})`,
        `<div style="max-height:330px;overflow:auto"><table>
        <thead><tr><th>Kod</th><th>Tür</th><th>Kat</th><th>Sahip</th><th>Koltuk</th></tr></thead>
        <tbody>${liste.slice().sort((a, b) => (a.floor - b.floor) ||
          String(a.code).localeCompare(String(b.code))).map(r => `<tr>
          <td>${esc(r.code)}</td>
          <td>${r.facility_type === "laboratory" ? "Lab" : "Derslik"}</td>
          <td>${sayi(r.floor)}</td>
          <td>${esc(r.faculty_name || r.owner_label || "—")}</td>
          <td>${sayi(r.capacity)}</td></tr>`).join("")}</tbody></table></div>`);
    }, { iskelet: 8 });
  },
};

/* --------------------------------------------------------------------------
   5) GELİR / GİDER ANALİZİ
   -------------------------------------------------------------------------- */
EKRANLAR.finans = {
  baslik: "Finansal Analizler",
  altBaslik: "Gelir, gider ve eğitim ücreti konumu",
  ciz() {
    return `<div id="fnKaynakKpi" class="kpi-serit">${iskeletHtml(3)}</div>
      <div class="izgara-2">
        ${panel("Gelir – Gider ve Personel Gideri", "Seçili kapsam ve akademik yıl.",
          iskeletHtml(4), { id: "fnKaynakChart" })}
        ${panel("Giderlerin Dağılımı", "Gider kalemleri.",
          iskeletHtml(6), { id: "fnDagilim" })}
      </div>
      <div class="izgara-21">
        ${panel("Eğitim Ücretleri (gerçek veri)",
          "Kapsamdaki programların yıllık ücreti — kurumun yayımladığı tarife.",
          iskeletHtml(6), { id: "fnUcret" })}
        ${panel("Ücret Seyri", "%50 burslu kontenjan üzerinden medyan.",
          iskeletHtml(5), { id: "fnTrend" })}
      </div>
      <div class="izgara-1">
        ${panel("Rakip Üniversitelerle Ücret Karşılaştırması",
          "Kıyas kapsamı takip eder: bölüm/program seçiliyse eşdeğer programlar.",
          iskeletHtml(6), { id: "fnRakip", basId: "fnRakipBas", notId: "fnRakipNot" })}
      </div>`;
  },
  yukle() {
    const p = kapsam();
    const finansMetrikleri = ["total_income", "total_expense", "personnel_cost"];
    dataSourceGroupLoad("fnKaynakKpi", finansMetrikleri, { view: "cards" });
    dataSourceGroupLoad("fnKaynakChart", finansMetrikleri, { view: "chart" });
    doldur("fnDagilim", () => api.get(`/api/finance/${encodeURIComponent(K.donem)}/summary`, p), f => {
      const rows = f.expenditure_breakdown || [];
      if (!rows.length) return bekleniyorGovde(
        "Bu kapsamda kaynak/provenansı korunmuş gider kalemi yok.");
      return yatayCubuk(rows.map(r => ({
        ad: r.category, deger: Number(r.amount),
        renk: r.is_synthetic ? "var(--uyari)" : "var(--vurgu)",
        ipucu: `${fmt.usdMillion(r.amount, 2)} · ${dataSourceProvenance(r)}`,
      })), { yb: v => fmt.usdMillion(v, 1), eksenY: "milyon USD" }) +
        `<div class="not" style="margin-top:8px">Kaynak: ${esc(dataSourceCaption(f))}. ` +
        `Yüklenmiş analitik kalemler denetlenmiş muhasebe kaydı değildir.</div>`;
    }, { iskelet: 6 });
    doldur("fnUcret", () => api.get("/api/tuition/program-fees", p), o => {
      if (!o.available) return bekleniyorGovde(o.note || "Ücret verisi yok.");
      const yari = (o.by_fee_type || []).find(t => t.fee_type === "HALF");
      const tam = (o.by_fee_type || []).find(t => t.fee_type === "FULL");
      const ust = `<div class="kpi-serit" style="margin-bottom:10px">
          ${kpi("Akademik Yıl", esc(o.academic_year), "ücret dönemi",
                { ikon: "◷", renk: "mavi" })}
          ${kpi("%50 Burslu Medyan", yari && yari.median_fee ? paraTL(yari.median_fee) : null,
                "yıllık", { ikon: "◑", renk: "yesil" })}
          ${kpi("Tam Ücret Medyan", tam && tam.median_fee ? paraTL(tam.median_fee) : null,
                "yıllık", { ikon: "₺", renk: "turuncu" })}
        </div>`;
      /* Program ücretleri: uzun adlar → YATAY sütun, ücret türüne göre
         renk. Ham tablo "Detayı göster" altına indi. */
      const turRenk = { HALF: "var(--vurgu)", FULL: "var(--uyari)" };
      const grafik = yatayCubuk(o.rows.slice(0, 14).map(r => ({
          ad: r.program_name + (r.education_language ? " · " + r.education_language : ""),
          deger: r.annual_fee, renk: turRenk[r.fee_type] || "var(--mor)",
        })), { yb: v => fmt.int(Math.round(v / 1000)) + "B ₺",
               eksenY: "yıllık ücret (bin ₺) · mavi %50 burslu · turuncu tam ücret" });
      const tablo = `<div style="max-height:300px;overflow:auto"><table>
          <thead><tr><th>Program</th><th>Dil</th><th>Tür</th><th>Yıllık ücret</th></tr></thead>
          <tbody>${o.rows.map(r => `<tr>
            <td style="text-align:left">${esc(r.program_name)}</td>
            <td>${esc(r.education_language || "—")}</td>
            <td>${esc(r.fee_type_label)}</td><td>${paraTL(r.annual_fee)}</td>
            </tr>`).join("")}</tbody></table></div>`;
      return ust + grafik
        + detay("Ücret tablosunu göster (" + o.rows.length + " program)", tablo);
    }, { iskelet: 6 });

    doldur("fnTrend", () => api.get("/api/tuition/trend", p), o => {
      if (!o.available || (o.years || []).length < 2) {
        return bekleniyorGovde("Trend için en az iki yıllık ücret verisi gerekir.");
      }
      /* Yıllara göre SÜTUN: seviye kıyası çizgiden daha okunur. */
      return gruplandirilmisCubuk(o.years.map(y => y.academic_year), [
        { ad: "Medyan ücret", veri: o.years.map(y => y.median_fee), birim: "₺" },
      ], { eksenY: "₺", yb: v => fmt.int(Math.round(v / 1000)) + "B", yukseklik: 230 })
      + detay("Yıllık değişim tablosu", `<table>
         <thead><tr><th>Yıl</th><th>Medyan</th><th>Değişim</th><th>Kaynak</th></tr></thead>
         <tbody>${o.years.map(y => `<tr><td>${esc(y.academic_year)}</td>
           <td>${paraTL(y.median_fee)}</td>
           <td class="${y.change_percent > 0 ? "iyi" : ""}">${yuzde(y.change_percent, 1)}</td>
           <td>${esc(y.is_synthetic ? "SYNTHETIC_GENERATED tarihsel tahmin" : "Yetkili tarife")}</td></tr>`).join("")}
         </tbody></table>`)
      + `<div class="not" style="margin-top:8px">${esc(o.provenance || "")}. 2025-2026 noktası kurumun yetkili tarifesidir; geçmiş noktalar analitik backcast tahminidir.</div>`;
    }, { iskelet: 5 });

    /* RAKİP ÜCRET KIYASI — KAPSAMI TAKİP EDER.
       -------------------------------------------------------------
       Eskiden bu çağrı HİÇ parametre göndermiyordu: ne kapsam ne dönem.
       Sonuç olarak Yazılım Mühendisliği seçiliyken bile ekranda kurum
       geneli medyanları görünüyordu ve üstelik gösterilen yıl,
       seçili dönem değil rakip tablosundaki EN GÜNCEL yıldı.

       Artık kapsam ve dönem birlikte gider (`kapsam()` ikisini de
       taşır). Başlık ve alt başlık sunucunun döndürdüğü kapsam
       bilgisinden yazılır; bölüm kapsamında "kurum medyanları"
       ifadesi KULLANILMAZ. */
    doldur("fnRakip", () => api.get("/api/tuition/competitors", p), o => {
      const bas = document.getElementById("fnRakipBas");
      const alt = document.getElementById("fnRakipNot");
      if (bas && o.title) bas.textContent = o.title;
      if (alt) {
        alt.textContent = o.subtitle
          || "Kıyas kapsamı takip eder: bölüm/program seçiliyse eşdeğer programlar.";
      }
      if (!o.available) {
        return bekleniyorGovde(o.unavailable_reason
          || "Karşılaştırılabilir program verisi yok.");
      }
      /* ÜCRET ÖZEL DURUMU
         ----------------
         Devlet üniversiteleri öğrenciden eğitim ücreti almaz. Bu panelde
         "Devlet" ya da "Tümü" seçilse bile devlet kurumlarını 0 ₺'lık
         rakip gibi göstermek yanlış olurdu: ölçülmemiş bir değeri sıfır
         saymak, tam da kaçındığımız hata. Bunun yerine evrenin neden
         vakıf ağırlıklı olduğu tek cümleyle söylenir. */
      const ucretNotu = (K_EVREN === "state" || K_EVREN === "all")
        ? `<div class="not" style="margin-bottom:6px">Karşılaştırma: ${
            esc(evrenAdi(K_EVREN))} · karşılaştırılabilir ücret verisi `
          + `yalnızca VAKIF kurumları için vardır; devlet üniversiteleri `
          + `öğrenciden eğitim ücreti almadığı için bu kıyasa girmez.</div>`
        : "";
      /* Sunucunun verdiği `median_fee` OLDUĞU GİBİ çizilir; burada
         yeniden hesap ya da dönüştürme YAPILMAZ. Etiket yer kazanmak
         için bine yuvarlanır, tam değer ipucunda taşınır — böylece
         ★ çubuğu ile üstteki "%50 Burslu Medyan" kartı birebir
         karşılaştırılabilir. */
      const cubuklar = o.universities.filter(u => u.median_fee).map(u => ({
        ad: u.university_name + (u.is_home_institution ? "  ★" : "")
            + (u.language_match === "farkli" ? "  ⚠" : ""),
        deger: u.median_fee,
        ipucu: paraTL(u.median_fee)
               + (u.is_home_institution ? " · yetkili ABÜ ücret kaynağı" : ""),
        renk: u.is_home_institution ? "var(--vurgu)" : "var(--vurgu-2)",
      }));
      const kurumumuzVar = o.universities.some(
        u => u.is_home_institution
          && u.median_fee !== null && u.median_fee !== undefined);
      const grafik = yatayCubuk(cubuklar, {
        yb: v => fmt.int(Math.round(v / 1000)) + "B ₺",
        eksenY: `${o.coverage_note} · ${o.fee_type_label} · ${o.academic_year}`
          + (kurumumuzVar ? " · ★ kurumumuz" : " · kurumumuz için dönem verisi yok"),
      });
      /* Program kapsamında HANGİ programların eşleştiği görünür olmalı:
         kıyasın dürüstlüğü buna bağlı. */
      if (o.mode !== "program") return ucretNotu + grafik;
      const satirlar = o.universities.flatMap(u =>
        (u.matched_programs || []).map(m => `<tr>
          <td style="text-align:left">${esc(u.university_name)}</td>
          <td style="text-align:left">${esc(m.program_name)}</td>
          <td>${esc(m.education_language || "—")}</td>
          <td>${m.annual_fee ? paraTL(m.annual_fee) : esc(m.fee_text || "—")}</td>
        </tr>`)).join("");
      return ucretNotu + grafik + detay(
        `Eşleşen programları göster (${esc((o.program_labels || []).join(", "))})`,
        `<table><thead><tr><th>Kurum</th><th>Program</th>
           <th>Dil</th><th>Yıllık ücret</th></tr></thead>
         <tbody>${satirlar}</tbody></table>`);
    }, { iskelet: 6 });
  },
};

/* --------------------------------------------------------------------------
   6) YAPAY ZEKA WHAT-IF KOKPİTİ
   -------------------------------------------------------------------------- */
const KOKPIT_TEMEL = { ogrenci: null, kadro: null, kapasite: null, ucret: null };

EKRANLAR.kokpit = {
  baslik: "Yapay Zeka What-If Kokpiti",
  altBaslik: "Senaryo analizleri ile stratejik kararlarınızı destekleyin",
  ciz() {
    return `<div id="koKpi" class="kpi-serit">${iskeletHtml(2)}</div>
      <div class="izgara-12">
        ${panel("Senaryo Parametreleri", "Parametreleri değiştirin, etkiler anında hesaplansın.",
          `${kaydirici("ogrenci", "Öğrenci Sayısı Değişimi", -20, 40, 10)}
           ${kaydirici("burs", "Tam Burslu Kontenjan Değişimi", -20, 50, 0)}
           ${kaydirici("ucret", "Eğitim Ücreti Değişimi", -20, 60, 0)}
           ${kaydirici("kadro", "Akademik Kadro Değişimi", -10, 50, 0)}
           <div class="dip-not">ⓘ Hesaplar kurumun gerçek öğrenci, kadro,
             kapasite ve ücret verisi üzerinde yapılır. Mekân kapasitesi
             dönem bağımsız envanterden gelir.</div>`)}
        ${panel("Senaryo Etki Özeti", "Baz senaryoya göre tahmini değişim.",
          iskeletHtml(5), { id: "koEtki" })}
      </div>
      <div class="izgara-3">
        ${panel("Genel Senaryo Skoru", "Alt bileşenlerin ağırlıksız ortalaması.",
          iskeletHtml(5), { id: "koSkor" })}
        ${panel("Kapasite ve Kadro İhtiyacı", "Senaryonun fiziksel ve insan kaynağı sonucu.",
          iskeletHtml(5), { id: "koIhtiyac" })}
        ${panel("Hazır Senaryolar", "Tek tıkla parametre kümesi.",
          `<div class="hazir" data-hazir="buyume"><span class="ik">📈</span>
             <div><b>Hızlı Büyüme</b><span>Öğrenci +%25, kadro +%15</span></div><span class="ok">›</span></div>
           <div class="hazir" data-hazir="kalite"><span class="ik">🎓</span>
             <div><b>Akademik Kalite Atağı</b><span>Kadro +%30, burs +%15</span></div><span class="ok">›</span></div>
           <div class="hazir" data-hazir="gelir"><span class="ik">₺</span>
             <div><b>Gelir Odaklı</b><span>Ücret +%30, burs −%10</span></div><span class="ok">›</span></div>
           <div class="hazir" data-hazir="denge"><span class="ik">⚖</span>
             <div><b>Dengeli Büyüme</b><span>Öğrenci +%10, kadro +%10</span></div><span class="ok">›</span></div>
           <div class="hazir" data-hazir="sifirla"><span class="ik">↺</span>
             <div><b>Sıfırla</b><span>Mevcut duruma dön</span></div><span class="ok">›</span></div>`)}
      </div>
      ${asistanPaneli()}
      <div class="izgara-2">
        ${panel("Öğrenci Profili ve Gelir Etkisi",
          "Burs kademesine göre öğrenci ve ücret geliri.", iskeletHtml(5), { id: "koProfil" })}
        ${panel("Senaryo Yorumu", "Sonuçların okunuşu.", iskeletHtml(4), { id: "koYorum" })}
      </div>
      <div class="dip-not">ⓘ Bu kokpit deterministik bir hesap motorudur; dil modeli
        kullanmaz. Varsayımlar her panelde açıkça belirtilir; dönemli girdiler
        seçili akademik yıldan gelir.</div>`;
  },
  yukle() {
    const p = kapsam();
    const benim = nesil;
    Object.assign(KOKPIT_TEMEL, {
      ogrenci: null, kadro: null, kapasite: null, ucret: null, burs: null,
    });
    Promise.all([
      api.get("/api/decision-analytics/staffing", p),
      api.get("/api/physical-resources/capacity/overview", p).catch(() => null),
      api.get("/api/tuition/program-fees", p).catch(() => null),
      api.get("/api/decision-analytics/scholarship-breakdown", p).catch(() => null),
    ]).then(([k, kap, uc, burs]) => {
      if (benim !== nesil) return;
      KOKPIT_TEMEL.ogrenci = k.student_count;
      KOKPIT_TEMEL.kadro = k.academic_staff_count;
      KOKPIT_TEMEL.kapasite = kap ? kap.total_capacity : null;
      const yari = uc && (uc.by_fee_type || []).find(t => t.fee_type === "HALF");
      KOKPIT_TEMEL.ucret = yari ? yari.median_fee : null;
      KOKPIT_TEMEL.burs = burs;
      kokpitGuncelle();
    }).catch(() => {
      if (benim !== nesil) return;
      const hedef = document.getElementById("koEtki");
      if (hedef) hedef.innerHTML = bekleniyorGovde(
        "Senaryo için temel veriler okunamadı.");
    });
    asistanKur();
  },
};

function kaydirici(id, ad, min, maks, varsayilan) {
  return `<div class="kaydirici">
    <div class="bas"><span>${esc(ad)}</span><b>${varsayilan > 0 ? "+" : ""}${varsayilan}%</b></div>
    <input class="kaydirici-giris" type="range" id="kd_${id}"
           min="${min}" max="${maks}" step="5" value="${varsayilan}">
    <div class="uc"><span>${min}%</span><span>+${maks}%</span></div>
  </div>`;
}

const kdDeger = id => {
  const el = document.getElementById("kd_" + id);
  return el ? Number(el.value) : 0;
};

function hazirSenaryoUygula(ad) {
  const kur = (o, b, u, k) => {
    const at = (id, v) => {
      const el = document.getElementById("kd_" + id);
      if (!el) return;
      el.value = v;
      const et = el.parentElement.querySelector(".bas b");
      if (et) et.textContent = (v > 0 ? "+" : "") + v + "%";
    };
    at("ogrenci", o); at("burs", b); at("ucret", u); at("kadro", k);
  };
  ({ buyume: () => kur(25, 0, 0, 15),
     kalite: () => kur(0, 15, 0, 30),
     gelir: () => kur(0, -10, 30, 0),
     denge: () => kur(10, 0, 0, 10),
     sifirla: () => kur(0, 0, 0, 0) }[ad] || (() => {}))();
  kokpitGuncelle();
}

/** Kokpitin tek hesap noktası — tüm paneller buradan beslenir. */
function kokpitGuncelle() {
  const T = KOKPIT_TEMEL;
  if (T.ogrenci === null || T.ogrenci === undefined) return;
  const dO = kdDeger("ogrenci") / 100, dB = kdDeger("burs") / 100,
        dU = kdDeger("ucret") / 100, dK = kdDeger("kadro") / 100;

  const ogrenci = Math.round(T.ogrenci * (1 + dO));
  const kadro = T.kadro ? Math.round(T.kadro * (1 + dK)) : null;
  const oranSimdi = T.kadro ? T.ogrenci / T.kadro : null;
  const oranSenaryo = kadro ? ogrenci / kadro : null;
  const esZaman = 0.35;
  const gerekenKoltuk = Math.round(ogrenci * esZaman);
  const koltukFark = T.kapasite !== null ? T.kapasite - gerekenKoltuk : null;
  const ucret = T.ucret !== null ? T.ucret * (1 + dU) : null;
  const gelirSimdi = T.ucret !== null ? T.ucret * T.ogrenci : null;
  const gelirSenaryo = ucret !== null ? ucret * ogrenci : null;

  /* Kokpit panelleri `doldur()` kullanmaz, doğrudan bu yardımcıyla
     doldurulur. Uzun açıklamanın (i) düğmesine taşınması burada da
     çalışsın diye `notlariTasi` buradan da çağrılır — aksi hâlde
     "Gelir tahmini = medyan %50 burslu ücret × öğrenci sayısı…" gibi
     152 karakterlik notlar panelde açıkta kalıyordu. */
  const yaz = (id, html) => {
    const e = document.getElementById(id);
    if (!e) return;
    e.innerHTML = html;
    if (typeof notlariTasi === "function") notlariTasi(e);
    if (typeof ipucuHazirla === "function") ipucuHazirla(e);
  };

  yaz("koKpi",
    kpi("Toplam Öğrenci", sayi(ogrenci), `baz: ${sayi(T.ogrenci)}`,
        { ikon: "👥", renk: "mavi", trend: dO * 100, trendNot: "baz senaryoya göre" })
    + kpi("Akademik Kadro", sayi(kadro), `baz: ${sayi(T.kadro)}`,
          { ikon: "🎓", renk: "yesil", trend: dK * 100, trendNot: "baz senaryoya göre" })
    + kpi("Öğrenci / Akademisyen", ondalik(oranSenaryo, 1),
          `baz: ${ondalik(oranSimdi, 1)}`, { ikon: "÷", renk: "mor" })
    + kpi("Gereken Koltuk", sayi(gerekenKoltuk),
          T.kapasite !== null ? `mevcut: ${sayi(T.kapasite)}` : "", { ikon: "◱", renk: "turuncu" })
    + kpi("Kapasite Farkı", koltukFark === null ? null
            : (koltukFark >= 0 ? "+" : "") + sayi(koltukFark),
          koltukFark === null ? null : (koltukFark >= 0 ? "yeterli" : "AÇIK VAR"),
          { ikon: "⚠", renk: koltukFark !== null && koltukFark < 0 ? "kirmizi" : "yesil",
            kaynak: "Derslik kapasitesi okunamadı" })
    + kpi("Ücret Geliri (tahmini)", gelirSenaryo === null ? null : paraTL(gelirSenaryo),
          gelirSimdi === null ? null : `baz: ${paraTL(gelirSimdi)}`,
          { ikon: "₺", renk: "yesil", kaynak: "Ücret verisi yok" }));

  yaz("koEtki", `<div class="kpi-serit" style="margin:0">
      ${kpi("Öğrenci Değişimi", (ogrenci - T.ogrenci >= 0 ? "+" : "") + sayi(ogrenci - T.ogrenci),
            "kişi", { ikon: "👥", renk: "mavi" })}
      ${kpi("Kadro Değişimi", kadro === null ? null
              : (kadro - T.kadro >= 0 ? "+" : "") + sayi(kadro - T.kadro), "kişi",
            { ikon: "🎓", renk: "yesil" })}
      ${kpi("Gelir Değişimi", gelirSenaryo === null ? null
              : (gelirSenaryo - gelirSimdi >= 0 ? "+" : "") + paraTL(gelirSenaryo - gelirSimdi),
            "yıllık", { ikon: "₺", renk: "turuncu", kaynak: "Ücret verisi yok" })}
      ${kpi("Öğrenci/Akademisyen", oranSenaryo === null ? null
              : ondalik(oranSenaryo - oranSimdi, 2), "puan değişim",
            { ikon: "÷", renk: "mor" })}
    </div>
    <div class="not" style="margin-top:10px">
      Gelir tahmini = medyan %50 burslu ücret × öğrenci sayısı. Burs
      dağılımı ve tahsilat oranı hesaba katılmamıştır; bu bir üst sınır
      tahminidir.</div>`);

  /* SKOR: yalnızca ÖLÇÜLEBİLEN bileşenlerden. Eksik bileşen skoru
     düşürmez, ortalamaya hiç girmez. */
  const bilesen = [];
  if (oranSenaryo !== null) {
    // 20 öğrenci/akademisyen referans kabul edilir; altı iyi.
    bilesen.push({ ad: "Akademik kapasite", p: Math.max(0, Math.min(100, 100 - (oranSenaryo - 20) * 4)) });
  }
  if (koltukFark !== null && T.kapasite) {
    bilesen.push({ ad: "Fiziksel altyapı uygunluğu",
                   p: Math.max(0, Math.min(100, 50 + (koltukFark / T.kapasite) * 100)) });
  }
  if (gelirSenaryo !== null && gelirSimdi) {
    bilesen.push({ ad: "Gelir etkisi",
                   p: Math.max(0, Math.min(100, 50 + ((gelirSenaryo / gelirSimdi) - 1) * 100)) });
  }
  bilesen.push({ ad: "Büyüme hızı", p: Math.max(0, Math.min(100, 50 + dO * 150)) });
  const skor = bilesen.reduce((t, b) => t + b.p, 0) / bilesen.length;
  yaz("koSkor", `<div class="skor">
      <div class="sy">${Math.round(skor)}<small>/100</small></div>
      <div class="et">${skor >= 75 ? "Çok iyi senaryo" : skor >= 55 ? "Dengeli senaryo"
        : skor >= 40 ? "Riskli senaryo" : "Sürdürülemez senaryo"}</div>
    </div>
    ${bilesen.map(b => olcek(b.ad, b.p)).join("")}
    <div class="not">Yalnızca ölçülebilen ${bilesen.length} bileşen hesaba girdi.</div>`);

  yaz("koIhtiyac", `<table><tbody>
      <tr><td>Öğrenci sayısı</td><td><b>${sayi(ogrenci)}</b></td></tr>
      <tr><td>Gereken koltuk (eşzamanlı %${esZaman * 100})</td><td><b>${sayi(gerekenKoltuk)}</b></td></tr>
      <tr><td>Mevcut koltuk kapasitesi</td><td><b>${sayi(T.kapasite)}</b></td></tr>
      <tr><td>Kapasite farkı</td><td class="${koltukFark !== null && koltukFark < 0 ? "kotu" : "iyi"}">
        <b>${koltukFark === null ? "—" : (koltukFark >= 0 ? "+" : "") + sayi(koltukFark)}</b></td></tr>
      <tr><td>Akademik kadro</td><td><b>${sayi(kadro)}</b></td></tr>
      <tr><td>20 öğr./akad. için gereken kadro</td><td><b>${sayi(Math.ceil(ogrenci / 20))}</b></td></tr>
      <tr><td>Kadro açığı</td><td class="${kadro !== null && Math.ceil(ogrenci / 20) > kadro ? "kotu" : "iyi"}">
        <b>${kadro === null ? "—" : sayi(Math.max(0, Math.ceil(ogrenci / 20) - kadro))}</b></td></tr>
    </tbody></table>`);

  const burs = KOKPIT_TEMEL.burs;
  yaz("koProfil", burs && burs.available
    ? `<table><thead><tr><th>Burs türü</th><th>Mevcut</th><th>Senaryo</th><th>Değişim</th></tr></thead>
       <tbody>${burs.types.map(t => {
         const mev = t.placed_students || 0;
         const carpan = t.scholarship_type === "Burslu" ? (1 + dO + dB) : (1 + dO);
         const sen = Math.round(mev * carpan);
         return `<tr><td>${esc(t.scholarship_type)}</td><td>${sayi(mev)}</td>
           <td>${sayi(sen)}</td>
           <td class="${sen - mev >= 0 ? "iyi" : "kotu"}">${sen - mev >= 0 ? "+" : ""}${sayi(sen - mev)}</td></tr>`;
       }).join("")}</tbody></table>
       <div class="not" style="margin-top:8px">Tam burslu kontenjan değişimi yalnızca
         "Burslu" kademesine uygulanır.</div>`
    : bekleniyorGovde("Burs kırılımı verisi yok."));

  const cumleler = [];
  cumleler.push(`Öğrenci sayısı ${sayi(T.ogrenci)} → ${sayi(ogrenci)} olur.`);
  if (koltukFark !== null) {
    cumleler.push(koltukFark < 0
      ? `Derslik kapasitesi ${sayi(Math.abs(koltukFark))} koltuk AÇIK verir; ek derslik gerekir.`
      : `Mevcut derslik kapasitesi ${sayi(koltukFark)} koltuk yedekle yeterlidir.`);
  }
  if (oranSenaryo !== null) {
    cumleler.push(oranSenaryo > 25
      ? `Öğrenci/akademisyen oranı ${ondalik(oranSenaryo, 1)}'e çıkar; kadro takviyesi gerekir.`
      : `Öğrenci/akademisyen oranı ${ondalik(oranSenaryo, 1)} ile makul bantta kalır.`);
  }
  if (gelirSenaryo !== null) {
    cumleler.push(`Ücret geliri tahmini ${paraTL(gelirSimdi)} → ${paraTL(gelirSenaryo)}.`);
  }
  yaz("koYorum", `<div class="yorum-serit">
      ${yorumKarti("◑", "Senaryo Okuması", cumleler.join(" "),
        skor >= 70 ? { tur: "olumlu", ad: "Olumlu" }
          : skor >= 50 ? { tur: "dikkat", ad: "Dikkat" } : { tur: "risk", ad: "Risk" })}
    </div>`);
  buyutDugmeleriniTazele(document.getElementById("govde"));
}

/* --------------------------------------------------------------------------
   Yan ekranlar — menüdeki alt maddeler ana ekranlara yönlendirir
   -------------------------------------------------------------------------- */
EKRANLAR["ogrenci-talep"] = EKRANLAR.ogrenci;
EKRANLAR["ogrenci-burs"] = EKRANLAR.ogrenci;
EKRANLAR["akademik-yuk"] = EKRANLAR.akademik;
EKRANLAR["akademik-yayin"] = EKRANLAR.akademik;
EKRANLAR["akademik-ihtiyac"] = EKRANLAR.akademik;
EKRANLAR["altyapi-derslik"] = EKRANLAR.altyapi;
EKRANLAR["altyapi-ihtiyac"] = EKRANLAR.altyapi;
EKRANLAR["finans-ucret"] = EKRANLAR.finans;

/* Karşılaştırmalar — rakip analizi (mevcut servis) */
EKRANLAR.karsilastirma = {
  baslik: "Karşılaştırmalar",
  altBaslik: "Kapsama göre akran karşılaştırması — çoklu metrik",
  ciz() {
    /* KAPSAM AKRANI BELİRLER (hiyerarşi kuralı korunmuştur):
         üniversite → Ankara'daki diğer üniversiteler
         fakülte    → ABÜ'nün diğer fakülteleri
         bölüm      → aynı fakültenin diğer bölümleri
         program    → aynı bölümün diğer programları                     */
    const akran = { university: "Ankara'daki üniversiteler",
                    faculty: "ABÜ'deki akademik fakülteler",
                    department: "Aynı fakültedeki kardeş bölümler",
                    program: "Aynı bölümdeki kardeş programlar" }[seviye()];
    /* ÜST SIRA: iki KOMPAKT kart yan yana. Çoklu Metrik tek başına
       tam genişlik kaplıyordu; artık yanına yıllık trend giriyor ve
       hoca tek ekranda iki ayrı analiz görüyor. */
    const cokluSecici =
      krYerelSecici("coklu", "evren", "krCokluEvren", "Kurum:",
        KARSILASTIRMA_EVRENI, KR_YEREL.coklu.evren)
      + krYerelSecici("coklu", "eslesme", "krCokluEslesme", "Bölüm:",
        PROGRAM_ESLESTIRME, KR_YEREL.coklu.eslesme || eslesmeVarsayilani());
    /* Alttaki üçlü eskiden bu ekranın tek seçicisine bağlıydı; o seçici
       artık Çoklu Metrik'e ait. Üçlünün kontrolü kendi başlığına taşındı
       ki üstteki iki karttan bağımsız kalsın. */
    const altSecici = karsilastirmaSecicileri("krEvren", "krEslesme");
    return `<div id="krKpi" class="kpi-serit">${iskeletHtml(2)}</div>
      <div class="izgara-2 kr-ust">
        ${/* Çoklu Metrik kartı kaldırıldı; yerine yerleşme sıralaması
              geldi. Kontenjan kartıyla AYNI veri ve AYNI grafik motoru
              kullanılır — tek fark ölçülen metrik. Böylece iki kart yan
              yana aynı kurumları, aynı yılları ve aynı renk sırasını
              gösterir; göz bir karttan diğerine geçerken yeniden
              yönelmek zorunda kalmaz. */""}
        ${panel("Yıllara Göre Yerleşme Sıralaması",
          "Seçilen bölümde akran kurumların başarı sırası. Yukarısı daha iyi.",
          iskeletHtml(5), { id: "krSiralama", basEk: `<span class="ys-basek"></span>` })}
        ${panel("Yıllara Göre Kontenjan ve Doluluk",
          /* Yıl aralığı SABİT YAZILMAZ: eksen veritabanındaki gerçek
             yıllardan türüyor (bkz. `mevcut_yillar`). Metne 2021–2025
             yazmak yeni yıl geldiğinde sessizce yanlış olurdu. */
          "Seçilen bölümde akran kurumların yıllara göre seyri.",
          iskeletHtml(5), { id: "krYillik", basEk: `<span class="yt-basek"></span>` })}
      </div>
      <div class="izgara-2">
        ${panel("Büyüklük ve Kadro", "Öğrenci ve akademisyen sayısı yan yana.",
          iskeletHtml(6), { id: "krBuyukluk", basEk: altSecici })}
        ${panel("Yoğunluk ve Portföy",
          "Öğrenci/akademisyen ile program sayısı.", iskeletHtml(6), { id: "krYogunluk" })}
      </div>
      ${panel("Sıralama", "Tek metrikte akranlar arasındaki yer.",
        iskeletHtml(6), { id: "krSira", basEk:
          krYerelSecici("sira", "evren", "krSiraEvren", "Kurum:",
            KARSILASTIRMA_EVRENI, KR_YEREL.sira.evren)
          + krYerelSecici("sira", "eslesme", "krSiraEslesme", "Bölüm:",
            PROGRAM_ESLESTIRME, KR_YEREL.sira.eslesme || eslesmeVarsayilani()) })}`;
  },
  yukle() {
    const p = kapsam();
    const uni = seviye() === "university";
    /* Süzgeç kaynağı ARTIK PARAMETRE. Alttaki üçlü genel değişkenleri
       kullanmaya devam eder; Çoklu Metrik kendi yerel durumunu geçirir.
       Böylece iki grup aynı isteği kurar ama farklı süzgeçle çalışır. */
    const isteDurum = d => uni
      ? api.get("/api/decision-analytics/university-competitors",
                donemParam({ filter_mode: d.evren,
                             matching_mode: d.eslesme || eslesmeVarsayilani() }))
      : api.get("/api/decision-analytics/yok-atlas-comparison",
                { ...p, institution_type: d.evren,
                  matching_mode: d.eslesme || eslesmeVarsayilani() });
    /* Alttaki paneller: genel durum (mevcut davranış korunur). */
    const iste = () => isteDurum({ evren: K_EVREN, eslesme: eslesmeKipi() });
    /* Çoklu Metrik: yalnızca kendi durumu. */
    const isteCoklu = () => isteDurum(KR_YEREL.coklu);

    /* Kapsam ne olursa olsun satırları AYNI biçime indirger; böylece
       grafik kodu tek, kapsam kuralı yine hiyerarşiden gelir. */
    const normalize = o => uni
      ? (o.universities || []).map(r => ({
          ad: r.university_name, biz: r.is_home_institution,
          tur: r.university_type,
          ogrenci: r.student_count, kadro: r.academic_staff_count,
          oran: r.students_per_academic, program: r.department_count,
          birim: r.academic_unit_count, ucret: r.median_tuition_fee,
          buyume: r.growth_percent_period,
          kontenjan: r.quota, yerlesen: r.placed, doluluk: r.occupancy_percent,
          raw_program: r.raw_program_count, matched_program: r.matched_program_count,
        }))
      : (o.available ? (o.peers || []) : []).map(r => ({
          ad: r.label || r.university_name || birimAdi(r.code, r.name),
          biz: !!r.is_home_institution || !!r.is_selected,
          tur: r.university_type,
          ogrenci: r.cohort_size ?? r.student_count,
          kadro: r.academic_staff_count,
          oran: r.students_per_academic_staff,
          program: r.program_count,
          ders: r.curriculum_course_count,
          kontenjan: r.quota,
          yerlesen: r.placed_students,
          doluluk: r.occupancy_percent,
        }));

    const akranlariSec = (list, limit = 10) => {
      if (!list || !list.length) return [];
      if (list.length <= limit) return list;
      const bizIdx = list.findIndex(x => x.biz);
      if (bizIdx < 0 || bizIdx < limit) {
        return list.slice(0, limit);
      }
      return [...list.slice(0, limit - 1), list[bizIdx]];
    };

    doldur("krKpi", iste, o => {
      if (uni) {
        const h = o.home;
        if (!h) return bekleniyorGovde("Kurumumuz kümede bulunamadı.");
        const isMatched = eslesmeKipi() !== "all_programs";
        if (isMatched) {
          return kpi("Eşleşen Program Kohortu", sayi(h.student_count), "eşleşen programlar",
                     { ikon: "👥", renk: "mavi" })
            + kpi("Eşleşen Program Sayısı", sayi(h.department_count), "portföy kapsamı",
                  { ikon: "⇄", renk: "mor" })
            + kpi("Toplam Kontenjan", sayi(h.quota), "eşleşen programlar",
                  { ikon: "🎓", renk: "yesil" })
            + kpi("Toplam Yerleşen", sayi(h.placed), "eşleşen programlar",
                  { ikon: "◱", renk: "turuncu" });
        }
        return kpi("Kayıtlı Öğrenci", sayi(h.student_count), esc(o.academic_year),
                   { ikon: "👥", renk: "mavi" })
          + kpi("Ankara Sıralaması", `${h.ankara_rank}. / ${sayi(h.ankara_university_count)}`,
                "öğrenci sayısına göre", { ikon: "⇄", renk: "mor" })
          + kpi("4 Yıllık Büyüme", yuzde(h.growth_percent_period, 1), "dönem",
                { ikon: "📈", renk: "yesil" })
          + kpi("Öğrenci / Akademisyen", ondalik(h.students_per_academic, 1), "",
                { ikon: "÷", renk: "turuncu", kaynak: o.profile_note });
      }
      const r = normalize(o);
      if (!r.length) return bekleniyorGovde(o.note || "Karşılaştırılacak akran yok.");
      const top = a => r.reduce((t, x) => t + (Number(x[a]) || 0), 0);
      return kpi("Karşılaştırılan Birim", sayi(r.length), "akran", { ikon: "⇄", renk: "mor" })
        + kpi("Toplam Kohort", sayi(top("ogrenci")), "kapsamda", { ikon: "👥", renk: "mavi" })
        + kpi("Toplam Kontenjan", sayi(top("kontenjan")), "kapsamda", { ikon: "🎓", renk: "yesil" })
        + kpi("Toplam Yerleşen", sayi(top("yerlesen")), "kapsamda", { ikon: "◱", renk: "turuncu" });
    }, { iskelet: 2 });

    /* ---- ANA GÖRÜNÜM: ÇOKLU METRİK ---- */
    /* ---- YILLARA GÖRE KONTENJAN VE DOLULUK (kendi durumu) ----
       Kaynak: canonical YÖK Atlas aktarımı (`yok_atlas_benchmark_metrics`).
       Kapsam bir PROGRAMDIR; kurumda o bölüm yoksa kurum listeye girmez,
       üniversite toplamına düşülmez. */
    const isteYillik = () => api.get(
      "/api/decision-analytics/program-year-comparison",
      { institution_type: KR_YEREL.yillik.evren,
        ...(KR_YEREL.yillik.program ? { program_key: KR_YEREL.yillik.program } : {}) });

    const cizYillik = o => {
      if (!o.programs || !o.programs.length) {
        /* Neden boş olduğunu SÖYLE. "Veri bekleniyor" tek başına
           kullanıcıya hiçbir şey anlatmıyor; kaynak tablo yüklenmemişse
           bunu açıkça yazmak sorunu bir bakışta çözülebilir kılar. */
        return bekleniyorGovde(o.note
          || "YÖK Atlas program kayıtları bu veritabanında bulunamadı "
             + "(yok_atlas_benchmark_metrics). Sunucu yeniden başlatıldıysa "
             + "ve tablo doluysa panel kendiliğinden gelir.");
      }
      KR_YEREL.yillik.program = o.program_key;
      const mod = KR_YEREL.yillik.mod;
      /* Süzgeçler kartın İÇİNDE: başlık şeridi iki kart yan yanayken
         dar kalıyor ve seçiciler sığmıyordu. */
      const kontrol = `<div class="yt-kontrol">
        ${krYerelSecici("yillik", "evren", "krYillikEvren", "Kurum:",
            KARSILASTIRMA_EVRENI, KR_YEREL.yillik.evren)}
        ${krYerelSecici("yillik", "program", "krYillikProgram", "Bölüm:",
            o.programs.map(x => ({ deger: x.key, ad: x.label })), o.program_key)}
        <span class="yt-mod" role="group" aria-label="Ölçüt">
          <button type="button" class="mp-mini${mod === "occupancy" ? " acik" : ""}"
            data-kr-mod="occupancy" aria-pressed="${mod === "occupancy"}">Doluluk %</button>
          <button type="button" class="mp-mini${mod === "quota" ? " acik" : ""}"
            data-kr-mod="quota" aria-pressed="${mod === "quota"}">Kontenjan</button>
        </span></div>`;

      if (!o.available || !(o.universities || []).length) {
        return kontrol + bekleniyorGovde(o.note
          || "Bu bölüm seçili kurum evreninde bulunmuyor.");
      }

      const bicimle = s => mod === "quota"
        ? (_sayiVar(s.quota) ? sayi(s.quota) : "—")
        : (_sayiVar(s.occupancy_percent) ? yuzde(s.occupancy_percent, 1) : "—");
      const tablo = `<table>
        <thead><tr><th>Üniversite</th>${
          o.years.map(y => `<th>${y}</th>`).join("")}</tr></thead>
        <tbody>${o.universities.map(u => `<tr class="${
          u.is_home_institution ? "bizim" : ""}">
          <td style="text-align:left">${esc(u.university_name)}${
            turRozet(u.university_type)}</td>${
          o.years.map(y => {
            const s = u.series.find(z => z.year === y);
            return `<td>${s ? bicimle(s) : "—"}</td>`;
          }).join("")}</tr>`).join("")}</tbody></table>`;

      return kontrol
        + `<div class="not">${esc(o.program_label)} · ${
            esc(o.institution_type_label)} · ${
            mod === "quota" ? "kontenjan" : "doluluk"}. ${
            o.program_scope === "single"
              ? `<b>${o.with_program_count}</b> kurumda var, <b>${
                  o.without_program_count}</b> kurumda yok (kesik çerçeveli
                 düğmeler; tıklayınca sebebini yazar).`
              : `${o.universities.length} kurum.`
          } Burs ve dil varyantları toplanır;
            doluluk = Σ yerleşen / Σ kontenjan.</div>`
        + yilTrendGrafigi(o.years, o.universities,
            { mod, yukseklik: 210,
              /* `enFazla` VERİLMEZ: sınır kaldırıldı. Eskiden 5 geçiliyordu
                 ve grafik motorundaki varsayılanı geçersiz kılıyordu. */
              programAdi: o.program_label, evrenId: "krYillikEvren",
              /* Hangi yılların farklı grain'den geldiğini BACKEND söyler;
                 arayüz yıl numarası tahmin etmez. Alan yoksa dipnot da
                 çıkmaz — eski yanıtlarla uyumlu kalır. */
              karisikYillar: o.mixed_grain_years || [] })
        + detay("Sayısal tabloyu göster", tablo);
    };
    /* Tazeleyici DIŞARIDAN çağrılabilir olmalı: yerel süzgeç değişince
       YALNIZCA bu panel yeniden doldurulacak. */
    KR_TAZELE.yillik = () => doldur("krYillik", isteYillik, cizYillik, { iskelet: 5 });
    KR_TAZELE.yillik();

    /* ------------------------------------------------------------------
       YILLARA GÖRE YERLEŞME SIRALAMASI
       ------------------------------------------------------------------
       Aynı uç, aynı grafik motoru, farklı metrik. Kod kontenjan kartıyla
       ortaklaştırılmadı çünkü tek gerçek fark iki satır; ortak bir
       "kart üretici" soyutlaması bu ikisini de okunmaz hale getirirdi. */
    /* `api.get` — bu kapsamdaki `iste` SIFIR ARGÜMANLI yerel bir yardımcı
       (durum uçları için). Ona URL vermek argümanları sessizce yutuyor ve
       kart "veri yok" sanıyordu. Kardeş kart `isteYillik` de `api.get`
       kullanır. */
    const isteSiralama = () => api.get(
      "/api/decision-analytics/program-year-comparison",
      { institution_type: KR_YEREL.siralama.evren,
        ...(KR_YEREL.siralama.program
              ? { program_key: KR_YEREL.siralama.program } : {}) });

    const cizSiralama = o => {
      if (!o.programs || !o.programs.length) {
        return bekleniyorGovde(o.note
          || "YÖK Atlas başarı sırası kayıtları bulunamadı.");
      }
      KR_YEREL.siralama.program = o.program_key;
      const kontrol = `<div class="yt-kontrol">
        ${krYerelSecici("siralama", "evren", "krSiralamaEvren", "Kurum:",
            KARSILASTIRMA_EVRENI, KR_YEREL.siralama.evren)}
        ${krYerelSecici("siralama", "program", "krSiralamaProgram", "Bölüm:",
            o.programs.map(x => ({ deger: x.key, ad: x.label })), o.program_key)}
        </div>`;

      /* SIRALAMA PUAN TÜRÜNE BAĞLIDIR.
         "Tüm bölümler" kapsamında SAY, EA, SÖZ, DİL ve TYT sıralamaları
         aynı eksende toplanırdı; bu sayı hiçbir şey ifade etmez. Sunucu
         `rank_comparable=false` diyorsa grafik çizilmez, sebebi yazılır. */
      if (o.rank_comparable === false) {
        /* İLK AÇILIŞTA BOŞ EKRAN GÖSTERME.
           Uç, bölüm verilmezse "Tüm bölümler"e düşer; sıralama orada
           tanımsızdır. Kullanıcıyı "önce bir bölüm seç" diye boş bir
           karta bakmaya zorlamak yerine, en çok kurumda bulunan bölümü
           kendimiz seçip bir kez yeniden yükleriz. Bayrak, kullanıcı
           bilinçli olarak "Tüm bölümler"e dönerse döngüye girmeyi
           engeller. */
        const ilk = (o.programs || []).find(p => p.key && p.key !== "__all__");
        if (ilk && !KR_YEREL.siralama.otoSecildi) {
          KR_YEREL.siralama.otoSecildi = true;
          KR_YEREL.siralama.program = ilk.key;
          setTimeout(() => KR_TAZELE.siralama && KR_TAZELE.siralama(), 0);
          return kontrol + bekleniyorGovde("Bölüm seçiliyor…");
        }
        return kontrol + bekleniyorGovde(
          "Başarı sırası puan türüne (SAY, EA, SÖZ, DİL, TYT) göre ayrı bir "
          + "sıralamadır; farklı türler aynı eksende karşılaştırılamaz. "
          + "Sıralamayı görmek için yukarıdan tek bir bölüm seçin.");
      }
      if (!o.available || !(o.universities || []).length) {
        return kontrol + bekleniyorGovde(o.note
          || "Bu bölüm seçili kurum evreninde bulunmuyor.");
      }
      const varMi = (o.universities || []).some(
        u => (u.series || []).some(s => _sayiVar(s.success_rank)));
      if (!varMi) {
        return kontrol + bekleniyorGovde(
          "Bu bölüm için başarı sırası kaydı yok. Kontenjan ve yerleşen "
          + "verisi bulunsa da sıralama ayrı bir alandır ve her programda "
          + "doldurulmamıştır.");
      }

      const tablo = `<table>
        <thead><tr><th>Üniversite</th>${
          o.years.map(y => `<th>${y}</th>`).join("")}</tr></thead>
        <tbody>${o.universities.map(u => `<tr class="${
          u.is_home_institution ? "bizim" : ""}">
          <td style="text-align:left">${esc(u.university_name)}${
            turRozet(u.university_type)}</td>${
          o.years.map(y => {
            const s = (u.series || []).find(z => z.year === y);
            return `<td>${s && _sayiVar(s.success_rank)
              ? sayi(s.success_rank) : "—"}</td>`;
          }).join("")}</tr>`).join("")}</tbody></table>`;

      return kontrol
        + `<div class="not">${esc(o.program_label)} · ${
            esc(o.institution_type_label)} · başarı sırası. Küçük sıra daha
            iyidir; eksen bu yüzden terstir ve yukarısı daha iyiyi gösterir.
            Bir kurumda birden çok varyant varsa EN İYİ sıra alınır,
            sıralamalar toplanmaz.</div>`
        + yilTrendGrafigi(o.years, o.universities,
            { mod: "success_rank", yukseklik: 210,
              programAdi: o.program_label, evrenId: "krSiralamaEvren",
              karisikYillar: o.mixed_grain_years || [] })
        + detay("Sayısal tabloyu göster", tablo);
    };
    KR_TAZELE.siralama = () =>
      doldur("krSiralama", isteSiralama, cizSiralama, { iskelet: 5 });
    KR_TAZELE.siralama();

    const cizCoklu = o => {
      const r = akranlariSec(normalize(o), 10);
      if (!r.length) return bekleniyorGovde(o.note || "Karşılaştırılacak akran yok.");
      const tb = o.type_breakdown;
      /* Kart kendi süzgecini okur; ekranın genel durumuna bakmaz. */
      const kipi = KR_YEREL.coklu.eslesme || eslesmeVarsayilani();
      const isMatchedUni = uni && kipi !== "all_programs";
      const evrenNot = uni
        ? `<div class="not">Karşılaştırma: ${esc(o.filter_label || evrenAdi(KR_YEREL.coklu.evren))} · ${esc(o.matching_mode_label || eslesmeAdi(kipi))}`
          + (tb ? ` · ${tb.DEVLET} devlet, ${tb.VAKIF} vakıf` : "")
          + ((o.excluded_unknown_type || []).length
              ? ` · ${o.excluded_unknown_type.length} kurum türü bilinmediği için dışarıda`
              : "")
          + `</div>`
        : `<div class="not">Karşılaştırma: ${esc(o.institution_type_label || evrenAdi(KR_YEREL.coklu.evren))} · ${esc(o.matching_mode_label || eslesmeAdi(kipi))}${
            o.subtitle ? ` · ${esc(o.subtitle)}` : ""
          }</div>`;

      let seriler = [];
      if (uni) {
        if (isMatchedUni) {
          seriler = [
            { ad: "Eşleşen Kohort", veri: r.map(x => x.ogrenci) },
            { ad: "Toplam Kontenjan", veri: r.map(x => x.kontenjan) },
            { ad: "Toplam Yerleşen", veri: r.map(x => x.yerlesen) },
            { ad: "Doluluk %", veri: r.map(x => x.doluluk), bicim: v => ondalik(v, 1) + "%" },
            { ad: "Eşleşen Program Sayısı", veri: r.map(x => x.program) },
          ];
        } else {
          seriler = [
            { ad: "Kayıtlı Öğrenci", veri: r.map(x => x.ogrenci) },
            { ad: "Akademik Personel", veri: r.map(x => x.kadro) },
            { ad: "Öğrenci / Akademisyen", veri: r.map(x => x.oran), bicim: v => ondalik(v, 1) },
            { ad: "Bölüm Sayısı", veri: r.map(x => x.program) },
            { ad: "Eğitim Ücreti", veri: r.map(x => x.ucret),
              bicim: v => fmt.int(Math.round(v / 1000)) + "B ₺", birim: "₺",
              /* İpucunda kısaltma değil, ödenecek gerçek tutar yazsın. */
              tamBicim: v => paraTL(v) },
          ];
        }
      } else {
        seriler = [
          { ad: "Kohort", veri: r.map(x => x.ogrenci) },
          { ad: "Kontenjan", veri: r.map(x => x.kontenjan) },
          { ad: "Yerleşen", veri: r.map(x => x.yerlesen) },
          { ad: "Doluluk %", veri: r.map(x => x.doluluk), bicim: v => ondalik(v, 1) + "%" },
        ];
      }

      const tabloCols = uni
        ? (isMatchedUni
            ? `<th>Birim</th><th>Eşleşen Kohort</th><th>Kontenjan</th><th>Yerleşen</th><th>Doluluk</th><th>Eşleşen / Ham</th>`
            : `<th>Birim</th><th>Kayıtlı Öğrenci</th><th>Akademisyen</th><th>Öğr./Akad.</th><th>Bölüm</th><th>Ücret</th>`)
        : `<th>Birim</th><th>Kohort</th><th>Kontenjan</th><th>Yerleşen</th><th>Doluluk</th><th>Ders</th>`;

      const tabloRows = r.map(x => {
        if (uni && isMatchedUni) {
          return `<tr class="${x.biz ? "bizim" : ""}">
            <td style="text-align:left">${esc(x.ad)}${turRozet(x.tur)}</td>
            <td>${sayi(x.ogrenci)}</td><td>${sayi(x.kontenjan)}</td>
            <td>${sayi(x.yerlesen)}</td><td>${yuzde(x.doluluk, 1)}</td>
            <td>${sayi(x.program)} / ${sayi(x.raw_program)}</td></tr>`;
        } else if (uni) {
          return `<tr class="${x.biz ? "bizim" : ""}">
            <td style="text-align:left">${esc(x.ad)}${turRozet(x.tur)}</td>
            <td>${sayi(x.ogrenci)}</td><td>${sayi(x.kadro)}</td>
            <td>${ondalik(x.oran, 1)}</td><td>${sayi(x.program)}</td>
            <td>${paraTL(x.ucret)}</td></tr>`;
        } else {
          return `<tr class="${x.biz ? "bizim" : ""}">
            <td style="text-align:left">${esc(x.ad)}${turRozet(x.tur)}</td>
            <td>${sayi(x.ogrenci)}</td><td>${sayi(x.kontenjan)}</td>
            <td>${sayi(x.yerlesen)}</td><td>${yuzde(x.doluluk, 1)}</td>
            <td>${sayi(x.ders)}</td></tr>`;
        }
      }).join("");

      /* EKİP ÖNCESİ CANONICAL GÖSTERİM GERİ ALINDI.
         Kısa süre çizgi (`cizgiKarsilastirma`) ve ardından metrik profili
         (`metrikProfili`) denendi; ikisi de bu kart için istenmedi. Kart
         kendi çalışan hâline döndü: her metrik KENDİ maksimumuna göre
         ölçeklenen karşılaştırma çubuğu. `metrikProfili` silinmedi —
         yandaki yıllık kartın altyapısı ondan geliyor.

         Yükseklik 300'den 220'ye indi: kart artık tam genişlik değil,
         yanında yıllık trend kartı var. */
      return evrenNot
        + karsilastirmaCubugu(r.map(x => x.ad), seriler, { yukseklik: 220 })
        + (o.profile_note
          ? `<div class="not" style="margin-top:8px">${esc(o.profile_note)}</div>` : "")
        + detay("Sayısal tabloyu göster", `<table>
            <thead><tr>${tabloCols}</tr></thead>
            <tbody>${tabloRows}</tbody></table>`);
    };
    /* Çoklu Metrik kartı ekrandan kaldırıldı; yerini "Yıllara Göre
       Yerleşme Sıralaması" aldı. `cizCoklu` ve `isteCoklu` SİLİNMEDİ:
       kart geri istenirse tek satırla geri gelsin, ayrıca `metrikProfili`
       gibi bu ekrana özgü çizim mantığı tek kopya kalsın. Yalnızca
       yükleme kaydı kaldırıldı — DOM'da `krCoklu` artık yok, doldurmaya
       çalışmak boşuna istek üretirdi. */

    /* ---- ORTAK EKSENLİ İKİLİLER ---- */
    doldur("krBuyukluk", iste, o => {
      const r = akranlariSec(normalize(o), 8);
      if (!r.length) return bekleniyorGovde("Karşılaştırılacak akran yok.");
      const isMatchedUni = uni && eslesmeKipi() !== "all_programs";
      if (isMatchedUni || (!r.some(x => _sayiVar(x.kadro)) && r.some(x => _sayiVar(x.kontenjan)))) {
        return gruplandirilmisCubuk(r.map(x => x.ad), [
          { ad: "Eşleşen Kohort", veri: r.map(x => x.ogrenci) },
          { ad: "Toplam Kontenjan", veri: r.map(x => x.kontenjan) },
        ], { eksenY: "kişi", yukseklik: 250 });
      }
      return gruplandirilmisCubuk(r.map(x => x.ad), [
        { ad: "Kayıtlı Öğrenci", veri: r.map(x => x.ogrenci) },
        { ad: "Akademik Personel", veri: r.map(x => x.kadro) },
      ], { eksenY: "kişi", yukseklik: 250 })
        + (o.profile_note
          ? `<div class="not" style="margin-top:8px">${esc(o.profile_note)}</div>` : "");
    }, { iskelet: 6 });

    doldur("krYogunluk", iste, o => {
      const r = akranlariSec(normalize(o), 8);
      if (!r.length) return bekleniyorGovde("Karşılaştırılacak akran yok.");
      const isMatchedUni = uni && eslesmeKipi() !== "all_programs";
      if (isMatchedUni) {
        return karsilastirmaCubugu(r.map(x => x.ad), [
          { ad: "Eşleşen Program Sayısı", veri: r.map(x => x.program) },
          { ad: "Toplam Kontenjan", veri: r.map(x => x.kontenjan) },
          { ad: "Doluluk %", veri: r.map(x => x.doluluk), bicim: v => ondalik(v, 0) + "%" },
        ], { yukseklik: 250 });
      }
      return karsilastirmaCubugu(r.map(x => x.ad), [
        { ad: "Öğrenci / Akademisyen", veri: r.map(x => x.oran),
          bicim: v => ondalik(v, 1) },
        { ad: uni ? "Bölüm Sayısı" : "Program Sayısı", veri: r.map(x => x.program) },
        ...(uni ? [{ ad: "4 Yıllık Büyüme %", veri: r.map(x => x.buyume),
                     bicim: v => ondalik(v, 0) + "%" }]
                : [{ ad: "Doluluk %", veri: r.map(x => x.doluluk),
                     bicim: v => ondalik(v, 0) + "%" }]),
      ], { yukseklik: 250 });
    }, { iskelet: 6 });

    const isteSira = () => isteDurum(KR_YEREL.sira);
    const cizSira = o => {
      const r = normalize(o).filter(x => Number.isFinite(Number(x.ogrenci)))
        .sort((a, b) => b.ogrenci - a.ogrenci);
      if (!r.length) return bekleniyorGovde("Sıralanabilir akran verisi yok.");
      /* Kart kendi süzgecini okur — komşu kartların durumuna bakmaz. */
      const siraKip = KR_YEREL.sira.eslesme || eslesmeVarsayilani();
      const isMatchedUni = uni && siraKip !== "all_programs";
      const eksenMetni = isMatchedUni
        ? "Eşleşen program kohort büyüklüğüne göre sıralama · ★ kurumumuz"
        : "Kayıtlı öğrenci sayısına göre sıralama · ★ kurumumuz";
      return yatayCubuk(r.map(x => ({
        ad: x.ad + (x.biz ? "  ★" : ""), deger: x.ogrenci,
        renk: x.biz ? "var(--vurgu)" : "var(--vurgu-2)",
      })), { eksenY: eksenMetni })
        + `<div class="not">${esc(o.filter_label || o.institution_type_label
            || evrenAdi(KR_YEREL.sira.evren))} · ${esc(o.matching_mode_label
            || eslesmeAdi(siraKip))} · ${r.length} kurum</div>`;
    };
    KR_TAZELE.sira = () => doldur("krSira", isteSira, cizSira, { iskelet: 6 });
    KR_TAZELE.sira();
  },
};

/* Müfredat */
EKRANLAR.mufredat = {
  baslik: "Müfredat",
  altBaslik: "Sınıf/yıl bazında ders programı",
  ciz() {
    return panel("Müfredat — Sınıf/Yıl Dağılımı",
      "Ders kodundaki ilk basamaktan türetilir. Kaynak dönem boyutu taşımadığı için yıl seçiminden bağımsızdır.",
      iskeletHtml(8), { id: "mfListe" });
  },
  yukle() {
    doldur("mfListe", () => api.get("/api/curriculum/by-class-year", kapsam()), gruplar => {
      if (!gruplar.length) return bekleniyorGovde("Bu kapsamda müfredat kaydı yok.");
      return gruplar.map(g => `<div style="margin-bottom:14px">
        <div style="font-size:.82rem;font-weight:620;margin-bottom:6px">
          ${esc(g.label)} <span style="color:var(--sonuk);font-weight:400">
          (${sayi(g.course_count)} ders)</span></div>
        <table><thead><tr><th>Kod</th><th>Ders</th><th>Bölüm</th></tr></thead>
        <tbody>${g.courses.map(c => `<tr><td>${esc(c.course_code || "—")}</td>
          <td style="text-align:left">${esc(c.course_name || "—")}</td>
          <td style="text-align:left">${esc(c.department_name || "—")}</td></tr>`).join("")}
        </tbody></table></div>`).join("");
    }, { iskelet: 8 });
  },
};

/* Fakülteler menüsü ana ekranı özet gösterir */
EKRANLAR.fakulteler = EKRANLAR.ozet;

/* ==========================================================================
   YÖNETİCİ YAPAY ZEKA ASİSTANI — TEK aktif uygulama
   ==========================================================================
   Bu bölüm, daha önce iki ayrı yerde (kabuk.js içindeki geçici tıklama
   dinleyicisi ve ekranlar.js sonuna eklenen AI kokpit düzeltme bloğu)
   duran denemelerin YERİNE geçer. İkisi de kaldırıldı.

   ÖNCEKİ "GÖNDER" DÜĞMESİNİN ÇALIŞMAMA SEBEBİ
   -------------------------------------------
   İki dinleyici aynı düğmeye bağlanmıştı ve ikisi de `#soruGiris`
   kimliğini arıyordu. `soruPaneli()` aynı sayfada İKİ KEZ çiziliyordu
   (Öğrenci ve Finans ekranlarında), yani DOM'da aynı `id` iki kez vardı.
   `document.getElementById("soruGiris")` her zaman BİRİNCİSİNİ döndürür;
   kullanıcı ikincisine yazdığında okunan değer boş kalıyor ve
   `if (!soru) return;` isteği sessizce iptal ediyordu. Ağda hiçbir
   POST görünmemesinin sebebi buydu.

   Çözüm yapısal: asistan artık TEK yerde (Yapay Zeka Kokpiti) yaşıyor,
   girişin kimliği tekil ve gönderme işi tek fonksiyonda.

   GRAFİK GÜVENLİĞİ
   ----------------
   Grafiklerin sayıları backend'den KAPALI bir şemayla gelir. Buradan
   `eval` çağrılmaz, model metninden sayı ayıklanmaz, modelden gelen
   HTML/JS çalıştırılmaz. Gelen her alan `esc()` ile kaçırılır.
   ========================================================================== */

const ASISTAN = {
  konusmaId: null,
  mesajlar: [],      // {rol, metin, grafikler, kaynaklar, kapsam, yil}
  mesgul: false,
  durum: null,       // {ready, message, model}
};

const ASISTAN_ONERILER = [
  "Toplam öğrenci sayımız kaç?",
  "Bu birimde kaç akademisyen var?",
  "Fakültelere göre öğrenci sayılarını grafikle göster.",
  "Akademisyenleri performans puanına göre grafikle.",
  "Rakip üniversitelerle ücret karşılaştırmasını grafikle göster.",
  "Öğrenci sayısı %10 artarsa mevcut durumla grafik üzerinde karşılaştır.",
];

/** Kokpit ekranındaki asistan paneli — `panel()` ile, ⛶ düğmesi dâhil. */
function asistanPaneli() {
  return `<div class="izgara-1">
    ${panel("Yönetici Yapay Zeka Asistanı",
      "Kurum verisine dayalı yanıtlar; sayılar backend'den gelir.",
      `<div class="ai-alan">
         <div class="ai-ust">
           <span class="ai-durum" id="aiDurum">◷ Yapay zekâ durumu okunuyor…</span>
           <button class="dugme" type="button" data-ai="yeni">↺ Yeni Konuşma</button>
         </div>
         <div class="ai-akis" id="aiAkis"></div>
         <div class="cipler" id="aiOneriler">${ASISTAN_ONERILER.map(o =>
           `<span class="cip" data-soru="${esc(o)}">${esc(o)}</span>`).join("")}</div>
         <div class="ai-giris">
           <textarea id="aiGiris" rows="2" placeholder="Sorunuzu yazın… (Enter: gönder, Shift+Enter: yeni satır)"></textarea>
           <button class="dugme birincil" type="button" data-ai="gonder">Gönder</button>
         </div>
       </div>`,
      { id: "aiPanel", basId: "aiPanelBas", herZamanBuyutilebilir: true })}
  </div>`;
}

function _aktifGirisBul() {
  if (document.activeElement && document.activeElement.matches?.(".ai-giris textarea, #aiGiris")) {
    return document.activeElement;
  }
  const modalGiris = document.querySelector(".gmodal .ai-giris textarea, .gmodal #aiGiris");
  if (modalGiris) return modalGiris;
  return document.querySelector("#aiPanel .ai-giris textarea, #aiGiris");
}

/** Öneri çipine tıklanınca girişi doldurur (kabuk.js buradan çağırır). */
function asistanOneriSec(soru) {
  const g = _aktifGirisBul();
  if (!g) return;
  g.value = soru;
  g.focus();
}

/* ---------------- çizim ---------------- */

function aiKaynakEtiketi(tur) {
  return ({
    authoritative: "Kurumun resmî kaydı",
    derived: "Türetilmiş / kohort tahmini",
    scenario: "What-If senaryosu",
    upload: "Kullanıcı tarafından yüklenen veri",
  })[tur] || "Kaynak belirtilmemiş";
}

/** Backend'den gelen KAPALI şemayı mevcut grafik sözlüğüyle çizer. */
function aiGrafikCiz(g) {
  const kategoriler = g.categories || [];
  const seriler = (g.series || []).map(s => ({
    ad: s.name, veri: s.data, birim: s.unit || g.display_unit,
  }));
  const eksen = [g.subtitle, aiKaynakEtiketi(g.source_type), g.source_label]
    .filter(Boolean).join(" · ");

  const chartOpt = {
    measure_type: g.measure_type,
    display_precision: g.display_precision,
    display_unit: g.display_unit,
    birim: g.display_unit || (seriler[0] && seriler[0].birim),
    eksenY: g.y_label || eksen,
  };

  let govde;
  if (g.chart_type === "bubble" || g.chart_type === "scatter") {
    govde = typeof baloncukGrafik === "function"
      ? baloncukGrafik(g.points || [], {
          eksenX: g.x_label,
          eksenY: g.y_label,
          eksenSize: g.size_label,
          referansCizgileri: g.reference_lines || [],
          yukseklik: 280,
          ...chartOpt,
        })
      : bekleniyorGovde("Grafik çizilemiyor.");
  } else if (g.chart_type === "stacked" || g.chart_type === "stacked_bar") {
    govde = typeof yiginCubuk === "function"
      ? yiginCubuk(kategoriler, seriler, {
          eksenY: g.y_label || (seriler[0] && seriler[0].birim) || "Öğrenci",
          yukseklik: 260,
          ...chartOpt,
        })
      : gruplandirilmisCubuk(kategoriler, seriler, { eksenY: g.y_label || "", yukseklik: 250, ...chartOpt });
  } else if (g.chart_type === "pie" || g.chart_type === "donut") {
    /* PASTA VE HALKA GERÇEKTEN ÇİZİLİR.
       ÖLÇÜLEN ARIZA: `donut` bu satırda `hbar` ile aynı dalda duruyordu
       ve YATAY ÇUBUK çiziliyordu. Kullanıcı "donut yap" dediğinde
       backend türü doğru gönderiyor, arayüz onu çubuğa çeviriyordu.
       İkisi aynı geometriyi paylaşır; tek fark ortadaki boşluktur
       (pasta = 0 iç yarıçap). */
    const sPay = seriler[0] || { veri: [] };
    govde = typeof dagilimHalkasi === "function"
      ? dagilimHalkasi(kategoriler.map((k, i) => ({
          ad: k, deger: sPay.veri[i],
        })), {
          icYaricap: g.chart_type === "pie" ? 0 : 62,
          yb: v => (typeof formatChartValue === "function"
            ? formatChartValue(v, chartOpt) : fmt.int(v)),
          ...chartOpt,
        })
      : bekleniyorGovde("Grafik çizilemiyor.");
  } else if (g.chart_type === "hbar") {
    const s0 = seriler[0] || { veri: [] };
    govde = yatayCubuk(kategoriler.map((k, i) => {
      const val = s0.veri[i];
      const valFmt = typeof formatChartValue === "function" ? formatChartValue(val, chartOpt) : fmt.int(val);
      const unitStr = s0.birim ? " " + s0.birim : "";
      return {
        ad: k,
        deger: val,
        ipucu: `${k}: ${valFmt}${unitStr}`,
      };
    }), {
      yb: v => (typeof formatChartValue === "function" ? formatChartValue(v, chartOpt) : fmt.int(v)),
      eksenY: eksen,
      ...chartOpt,
    });
  } else if (g.chart_type === "line") {
    /* ÇİZGİ GERÇEKTEN ÇİZGİ.
       ÖLÇÜLEN ARIZA: bu dal `gruplandirilmisCubuk` çağırıyordu — yani
       backend "line" gönderdiğinde ekranda ÇUBUK görünüyordu. Projede
       hazır bir çizgi grafiği zaten var (`cizgiKarsilastirma`); eksik
       olan tek şey ona bağlanmaktı. `mutlak: true`, tek birimli bir
       seride yüzde ekseni yerine gerçek değerleri gösterir. */
    govde = typeof cizgiKarsilastirma === "function"
      ? cizgiKarsilastirma(kategoriler, seriler,
          { eksenY: g.y_label || "", yukseklik: 240, mutlak: true,
            ...chartOpt })
      : gruplandirilmisCubuk(kategoriler, seriler,
          { eksenY: g.y_label || "", yukseklik: 240, ...chartOpt });
  } else {
    /* bar / grouped / bilinmeyen → dikey sütun. */
    govde = gruplandirilmisCubuk(kategoriler, seriler,
      { eksenY: g.y_label || "", yukseklik: 250, ...chartOpt });
  }



  const notlar = (g.notes || []).filter(Boolean);
  return `<div class="ai-grafik">
    <div class="ai-grafik-bas">
      <b>${esc(g.title)}</b>
      <button class="buyut-dugme" type="button" data-ai-buyut
              title="Büyüt" aria-label="Grafiği büyüt">⛶</button>
    </div>
    ${g.subtitle ? `<div class="not">${esc(g.subtitle)}</div>` : ""}
    ${govde}
    ${g.is_scenario ? `<div class="kaynak-uyari">⚠ ${esc(notlar[notlar.length - 1] || "")}</div>` : ""}
    ${notlar.length && !g.is_scenario
      ? `<div class="dip-not">ⓘ ${notlar.map(esc).join(" · ")}</div>` : ""}
  </div>`;
}

function aiMesajCiz(m) {
  if (m.rol === "user") {
    return `<div class="ai-mesaj kullanici"><div class="ai-balon">${esc(m.metin)}</div></div>`;
  }
  const ust = [m.yil, m.kapsam].filter(Boolean).join(" · ");
  return `<div class="ai-mesaj asistan">
    <div class="ai-balon">
      ${ust ? `<div class="ai-kapsam">${esc(ust)}</div>` : ""}
      <div class="ai-metin">${esc(m.metin)}</div>
      ${(m.grafikler || []).map(aiGrafikCiz).join("")}
      ${(m.kaynaklar || []).length
        ? `<div class="dip-not">ⓘ Kaynak: ${m.kaynaklar.map(esc).join(", ")}</div>` : ""}
    </div>
  </div>`;
}

function asistanAkisCiz() {
  const akislar = document.querySelectorAll(".ai-akis, #aiAkis");
  if (!akislar.length) return;
  const icerik = ASISTAN.mesajlar.length
    ? ASISTAN.mesajlar.map(aiMesajCiz).join("")
      + (ASISTAN.mesgul ? `<div class="ai-mesaj asistan"><div class="ai-balon">
           <span class="ai-yukleniyor">Yanıt oluşturuluyor…</span></div></div>` : "")
    : `<div class="ai-bos">Kurum verisine dayalı bir soru sorun.
         Yanıtlar seçili kapsam ve döneme göre üretilir.</div>`;
  akislar.forEach(akis => {
    akis.innerHTML = icerik;
    akis.scrollTop = akis.scrollHeight;
  });
  if (typeof buyutDugmeleriniTazele === "function") {
    buyutDugmeleriniTazele(document.getElementById("aiPanel"));
  }
}

/* ---------------- gönderme — TEK fonksiyon ---------------- */

async function asistanGonder() {
  if (ASISTAN.mesgul) return;
  const giris = _aktifGirisBul();
  if (!giris) return;
  const soru = giris.value.trim();
  if (!soru) return;

  ASISTAN.mesgul = true;
  document.querySelectorAll(".ai-giris textarea, #aiGiris").forEach(g => {
    g.value = "";
    g.disabled = true;
  });
  ASISTAN.mesajlar.push({ rol: "user", metin: soru });
  asistanAkisCiz();

  /* KAPSAM VE DÖNEM YAPISAL OLARAK GİDER — soru metnine gömülmez.
     `agac.kapsam()` seçili düğümün gerçek veritabanı kimliklerini verir;
     üniversite kapsamında hiçbir kimlik gönderilmez. Her istek o anki
     seçimi taşır, bu yüzden kapsam değişince BİR SONRAKİ yanıt değişir. */
  const k = agac.kapsam(K.birimId) || {};
  /* ÖNCEKİ GRAFİKLER İSTEKLE BİRLİKTE GİDER.
     "bunu line yap" gibi bir takip mesajında dönüştürülecek veri, son
     asistan cevabının grafikleridir. Sunucu bunu kendi belleğinde de
     tutuyor ama o bellek süreç ömrüyle sınırlı; arayüz zaten elinde
     tuttuğu payload'ı gönderirse takip mesajı her koşulda çalışır.
     DOM'dan yeniden ayrıştırma YAPILMAZ — yapısal state kullanılır. */
  const sonAsistan = [...ASISTAN.mesajlar].reverse()
    .find(m => m.rol === "assistant" && (m.grafikler || []).length);
  /* ÖNCEKİ CEVAPTA GRAFİK OLMAYABİLİR AMA TABLO OLABİLİR.
     "line yap" dendiğinde dönüştürülecek veri, son asistan cevabının
     grafiği YOKSA metnindeki tablodur. Son asistan mesajı ayrıca
     gönderilir; sunucu önce yapısal veriyi, olmazsa tabloyu okur. */
  const sonCevap = [...ASISTAN.mesajlar].reverse()
    .find(m => m.rol === "assistant" && (m.metin || "").trim());
  const govde = {
    message: soru,
    conversation_id: ASISTAN.konusmaId,
    stream: false,
    academic_year: K.donem || null,
  };
  if (sonAsistan) govde.previous_charts = sonAsistan.grafikler;
  if (sonCevap) govde.previous_answer = (sonCevap.metin || "").slice(0, 20000);
  const kapsamAlani = {};
  if (k.faculty_id) kapsamAlani.faculty_id = k.faculty_id;
  if (k.department_id) kapsamAlani.department_id = k.department_id;
  if (k.academic_program_id) kapsamAlani.academic_program_id = k.academic_program_id;
  if (Object.keys(kapsamAlani).length) govde.scope = kapsamAlani;

  try {
    const yanit = await api.post("/api/assistant/chat", govde);
    ASISTAN.konusmaId = yanit.conversation_id || ASISTAN.konusmaId;
    ASISTAN.mesajlar.push({
      rol: "assistant",
      metin: yanit.answer || "Yanıt alınamadı.",
      grafikler: yanit.charts || [],
      kaynaklar: yanit.data_sources || [],
      yil: yanit.academic_year,
      kapsam: Object.values(yanit.scope || {}).join(" / "),
    });
  } catch (err) {
    ASISTAN.mesajlar.push({
      rol: "assistant",
      metin: (err && (err.userMessage || err.detail || err.message))
        || "Yerel yapay zeka servisine ulaşılamıyor.",
    });
  } finally {
    ASISTAN.mesgul = false;
    document.querySelectorAll(".ai-giris textarea, #aiGiris").forEach(g => {
      g.disabled = false;
    });
    asistanAkisCiz();
    const sonGiris = _aktifGirisBul();
    if (sonGiris) sonGiris.focus();
  }
}

function asistanYeniKonusma() {
  ASISTAN.konusmaId = null;
  ASISTAN.mesajlar = [];
  document.querySelectorAll(".ai-giris textarea, #aiGiris").forEach(g => {
    g.value = "";
  });
  asistanAkisCiz();
}

/* ---------------- kurulum ---------------- */

async function asistanKur() {
  asistanAkisCiz();
  const rozetler = document.querySelectorAll(".ai-durum, #aiDurum");
  if (!rozetler.length) return;
  try {
    const d = await api.get("/api/assistant/status");
    ASISTAN.durum = d;
    const metin = d.ready
      ? `● Gemini bağlı · ${d.model || "model"}`
      : `○ ${d.message || "Yerel yapay zeka servisine ulaşılamıyor."}`;
    const cls = "ai-durum " + (d.ready ? "acik" : "kapali");
    rozetler.forEach(r => {
      r.textContent = metin;
      r.className = cls;
    });
  } catch {
    rozetler.forEach(r => {
      r.textContent = "○ Yerel yapay zeka servisine ulaşılamıyor.";
      r.className = "ai-durum kapali";
    });
  }
}

/* Tek delegasyonlu dinleyici — modül yüklenirken BİR KEZ bağlanır.
   `ciz()` panoyu yeniden kursa bile bu dinleyici document üzerinde
   durduğu için tekrar bağlanmaz; çift POST olmaz. */
document.addEventListener("click", e => {
  const d = e.target.closest("[data-ai]");
  if (d) {
    if (d.dataset.ai === "gonder") asistanGonder();
    if (d.dataset.ai === "yeni") asistanYeniKonusma();
    return;
  }
  const b = e.target.closest("[data-ai-buyut]");
  if (b && typeof grafikModalAc === "function") {
    const kutu = b.closest(".ai-grafik");
    const kopya = kutu.cloneNode(true);
    kopya.querySelectorAll("[data-ai-buyut]").forEach(x => x.remove());
    grafikModalAc((kutu.querySelector("b") || {}).textContent || "Grafik",
                  kopya.innerHTML, "");
  }
});

document.addEventListener("keydown", e => {
  if (e.target && (e.target.id === "aiGiris" || e.target.matches?.(".ai-giris textarea")) && e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    asistanGonder();
  }
});
