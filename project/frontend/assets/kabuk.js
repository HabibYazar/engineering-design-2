/* ABÜ KDS — YÖNETİM KABUĞU (hocanın UI tasarımına birebir)
   ==========================================================================
   Sol menü ağacı + üstte Fakülte/Bölüm/Dönem seçicileri + "Raporu İndir"
   + sol altta "Seçili Birim Bilgileri". Altı ekran `ekranlar.js` içinde.

   KAPSAM (scope) TEK KAYNAKTAN
   ----------------------------
   Seçilen fakülte/bölüm `data-adapter.js` içindeki ağaçtan GERÇEK
   veritabanı kimliğine çevrilir (`agac.kapsam`). Hiçbir istek ad/kod
   tahminiyle süzülmez; bu, alt birimde kardeş verisi görünmesini
   yapısal olarak engeller.

   VERİSİ OLMAYAN PANEL
   --------------------
   Hocanın tasarımındaki panel KALDIRILMAZ; içine "Veri kaynağı
   bekleniyor" rozeti konur (bkz. `bekleniyorGovde`). Böylece yerleşim
   birebir korunur ve hiçbir sayı uydurulmaz.
   ========================================================================== */

/* ---------------- menü tanımı (mockup sırasıyla) ---------------- */
const MENU = [
  /* SIDEBAR YALNIZCA GERÇEK SAYFALARI GÖSTERİR.
     ==========================================================================
     Burada altı grubun altında toplam on üç alt öğe vardı. Ölçüldü:
     bunların çoğu ayrı bir ekran DEĞİLDİ.

       * "Genel Bakış" öğeleri (akademik, ogrenci, altyapi, finans)
         grubun KENDİ kimliğini taşıyordu; başlığa tıklamakla birebir
         aynı şeyi yapıyorlardı.
       * "Ders Yükü", "Yayın Performansı", "Akademisyen İhtiyacı",
         "Derslik Envanteri", "İhtiyaç Projeksiyonları", "Talep ve
         Yerleştirme", "Burs Analizi", "Eğitim Ücretleri" ise
         `ekranlar.js` sonunda takma ad olarak tanımlıydı:

             EKRANLAR["akademik-yuk"] = EKRANLAR.akademik;

         Yani ayrı sayfa açmıyor, aynı ekranı yeniden çiziyorlardı.

     Menüde ayrı satır görünüp aynı yere gitmek kullanıcıya yanlış bir
     yapı vaat ediyordu. Bu yüzden takma adlar menüden kaldırıldı;
     grupların KENDİLERİ gerçek ekran olduğu için düz gezinme öğesine
     dönüştüler. Hiçbir ekran, kart ya da veri silinmedi — yalnızca
     yanıltıcı gezinme satırları kaldırıldı ve ekran kodları
     (`EKRANLAR[...]`) olduğu gibi duruyor.

     "Akademik Personel" alt öğe olarak kaldı çünkü `ekranlar.js`
     içinde KENDİ tanımı var ve gerçekten ayrı bir sayfadır. */
  { id: "ozet", ad: "Geçiş Paneli", ik: "⌂" },
  { id: "fakulteler", ad: "Fakülteler", ik: "🏛", agac: true },
  { id: "karsilastirma", ad: "Karşılaştırmalar", ik: "⇄" },
  {
    id: "akademik", ad: "Akademik Analizler", ik: "🎓",
    alt: [
      { id: "akademik-personel", ad: "Akademik Personel" },
    ],
  },
  { id: "ogrenci", ad: "Öğrenci Analizleri", ik: "👥" },
  { id: "altyapi", ad: "Altyapı Analizleri", ik: "🏗" },
  { id: "finans", ad: "Finansal Analizler", ik: "₺" },
  { id: "kokpit", ad: "Yapay Zeka Kokpiti", ik: "✦", yeni: true },
  { id: "mufredat", ad: "Müfredat", ik: "▤" },
  //{ id: "klasik", ad: "Klasik Görünüm (harita)", ik: "◍", dis: "klasik.html" },//
];

/* ---------------- durum ---------------- */
const K = {
  ekran: "ozet",
  birimId: "abu",          // ağaçtaki düğüm kimliği
  donem: null,             // seçili akademik yıl
  donemler: [],            // seçilebilir yıllar (gerçek verisi olanlar)
  donemOzet: null,         // /api/reference/data-periods yanıtı
  veriKaynagi: null,       // /api/reference/data-source yanıtı
  acikMenu: new Set(["akademik"]),   // tek açılır grup kaldı
  acikFakulte: null,
};

/* Seçili düğümün kapsam parametreleri — HER istek bunu taşır. */
/* İSTEK PARAMETRELERİ — KAPSAM **VE** DÖNEM
   ==========================================================================
   HATA: Bu yardımcı yalnızca kapsamı (faculty_id/department_id/…)
   döndürüyordu. Dönem seçici `K.donem`i güncelliyor, `ciz()` panoyu
   yeniden çiziyordu; ama İSTEKLER dönemi hiç taşımadığı için backend her
   seferinde aynı (en güncel) veriyi döndürüyordu. Seçici görsel olarak
   değişiyor, sayılar değişmiyordu.

   Tek kanonik durum `K.donem`dir ve her istek onu AÇIKÇA taşır.
   Dönemi umursamayan uçlar (fiziksel mekânlar, kanonik müfredat) fazladan
   parametreyi görmezden gelir — bu bilinçlidir ve ilgili panellerde
   "dönemden bağımsız" olarak belirtilir. */
const kapsam = (ek = {}) => ({
  ...(agac.kapsam(K.birimId) || {}),
  ...(K.donem ? { academic_year: K.donem } : {}),
  ...ek,
});

/** Yalnızca dönem taşıyan parametre kümesi (kapsamsız uçlar için). */
const donemParam = (ek = {}) => ({ ...(K.donem ? { academic_year: K.donem } : {}), ...ek });
const seviye = () => agac.kapsamSeviyesi(K.birimId);
const dugum = () => (agac.bul(K.birimId) || {}).dugum || agac.kok;

/* ==========================================================================
   ORTAK BİLEŞENLER
   ========================================================================== */

const esc = s => fmt.esc(String(s ?? ""));

/* KURUMSAL ETİKET ÇÖZÜCÜSÜ
   ==========================================================================
   Bir birimin ekranda görünen adı TEK yerden çözülür.

   SORUN: `ref.faculties()/departments()/programs()` uçları çıktıyı
   `_translate()` üzerinden geçirip kurumsal Türkçe adı yazıyordu; ama
   ANALİTİK uçları (ör. `child-breakdown`) ham veritabanı adını dönüyordu.
   Sonuç: aynı fakülte üstteki seçicide "Mühendislik ve Mimarlık
   Fakültesi", hemen altındaki dağılım grafiğinde "Software Engineering"
   olarak görünüyordu — kaynak veri kümesinin etiketi panonun etiketi
   hâline gelmişti.

   Kural: kullanıcıya gösterilen her birim adı buradan geçer. Çözüm
   KOD üzerinden yapılır (kod bir kimliktir); karşılığı yoksa hiyerarşinin
   kendi adı kullanılır. Kod ekranda görünmez, ipucunda kalır. */
let _adSozlugu = null;
async function adSozluguYukle() {
  if (_adSozlugu) return _adSozlugu;
  try { _adSozlugu = (await ref.displayNames()) || {}; }
  catch { _adSozlugu = {}; }
  return _adSozlugu;
}
function birimAdi(kod, yedek) {
  const t = _adSozlugu || {};
  for (const tur of ["faculties", "departments", "programs"]) {
    const bulunan = t[tur] && kod && t[tur][kod];
    if (bulunan) return bulunan;
  }
  return yedek || kod || "—";
}
const sayi = n => (n === null || n === undefined || !Number.isFinite(Number(n))
  ? "—" : fmt.int(n));
const yuzde = (n, d = 1) => (n === null || n === undefined || !Number.isFinite(Number(n))
  ? "—" : fmt.pct(n, d));
const ondalik = (n, d = 1) => (n === null || n === undefined || !Number.isFinite(Number(n))
  ? "—" : fmt.dec(n, d));
const paraTL = n => (n === null || n === undefined || !Number.isFinite(Number(n))
  ? "—" : new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(n) + " ₺");

/** KPI kartı. `deger` yoksa kart yine çizilir ama "veri bekleniyor" der. */
function kpi(etiket, deger, alt, opt = {}) {
  const yok = deger === null || deger === undefined || deger === "—";
  /* `donemselEksik`: gösterge kalıcı olarak eksik DEĞİL, yalnızca
     SEÇİLEN DÖNEMDE ölçülmemiş. Hero şeridi kalıcı boşlukları eler ama
     bunları TUTAR — kullanıcı seçtiği yılda neyin olmadığını görmeli. */
  return `<div class="kpi" data-renk="${opt.renk || "mavi"}"${
    opt.donemselEksik ? ' data-donem-eksik="1"' : ""}>
    <div style="min-width:0">
      <div class="et">${esc(etiket)}</div>
      ${yok
        ? `<span class="bekleniyor" title="${esc(opt.kaynak || "Kaynak veri seti henüz yüklenmedi")}">◷ veri bekleniyor</span>`
        : `<div class="dg">${deger}</div>`}
      ${alt && !yok ? `<div class="alt-not">${alt}</div>` : ""}
      ${opt.trend !== undefined && opt.trend !== null && Number.isFinite(Number(opt.trend))
        ? `<div class="trend ${Number(opt.trend) >= 0 ? "yukari" : "asagi"}">${
            Number(opt.trend) >= 0 ? "↑" : "↓"} ${yuzde(Math.abs(opt.trend), 1)} ${
            esc(opt.trendNot || "geçen yıla göre")}</div>`
        : ""}
    </div>
    <div class="ikon">${opt.ikon || "◈"}</div>
  </div>`;
}

/** Panel kabuğu. `id` verilirse gövdesi sonradan doldurulur.
 *
 *  BÜYÜT DÜĞMESİ
 *  -------------
 *  Başlığın sağına küçük bir ⛶ düğmesi konur, ama BAŞTAN GİZLİDİR.
 *  Görünür olup olmayacağına gövde çizildikten SONRA, içinde gerçekten
 *  grafik olup olmadığına bakılarak karar verilir (`buyutDugmesiniTazele`).
 *  Böylece KPI kartlarına, metin panellerine ve "veri bekleniyor"
 *  kartlarına düğme çıkmaz — kullanıcı boş bir kutuyu büyütemez.
 *
 *  `opt.buyutulmez: true` verilirse panel hiç düğme almaz. */
function panel(baslik, not, govde, opt = {}) {
  const dugme = opt.buyutulmez
    ? ""
    : ` <button class="buyut-dugme" type="button" data-buyut ${opt.herZamanBuyutilebilir ? 'data-her-zaman="1"' : "hidden"}
          title="Büyüt" aria-label="Grafiği büyüt">⛶</button>`;
  /* `basId` / `notId`: başlık ve alt başlık SONRADAN değişebilsin diye.
     Kapsam değiştiğinde bazı panellerin başlığı da değişmek zorunda
     (ör. rakip ücret kıyası bölüm seçilince "…Yazılım Mühendisliği
     Ücret Karşılaştırması" olur). Başlığı `doldur()` içinden
     değiştirmek, paneli baştan çizmekten ucuz ve güvenlidir. */
  return `<div class="panel" ${opt.stil ? `style="${opt.stil}"` : ""}${opt.buyutDetay ? ' data-buyut-detay="1"' : ""}>
    <h3><span${opt.basId ? ` id="${opt.basId}"` : ""}>${esc(baslik)}</span>${
      opt.rozet ? ` <span class="bekleniyor">◷ veri bekleniyor</span>` : ""}${
      /* `basEk`: başlık satırına sığan küçük denetim (ör. karşılaştırma
         evreni seçici). Kendi satırını/kartını açmadığı için kompakt
         yerleşim korunur; ⛶ düğmesinin solunda durur. */
      opt.basEk || ""}${dugme}</h3>
    ${not ? `<div class="not"${opt.notId ? ` id="${opt.notId}"` : ""}>${esc(not)}</div>` : ""}
    <div class="govde-ic"${opt.id ? ` id="${opt.id}"` : ""}>${govde || ""}</div>
  </div>`;
}

/** Bir panelin büyüt düğmesini, gövdesinde grafik varsa açar. */
function buyutDugmesiniTazele(govdeIc) {
  const p = govdeIc && govdeIc.closest(".panel");
  if (!p) return;
  const d = p.querySelector(":scope > h3 > .buyut-dugme");
  if (!d) return;
  if (govdeIc.id === "aiPanel" || p.classList.contains("ai-panel") || d.dataset.herZaman === "1") {
    d.hidden = false;
    return;
  }
  d.hidden = !(typeof grafikIceriyorMu === "function" && grafikIceriyorMu(govdeIc));
}


/** Ekran çizildikten sonra bütün panelleri bir kez tarar (senkron
 *  çizilen, `doldur()` kullanmayan paneller için). */
function buyutDugmeleriniTazele(kok) {
  (kok || document).querySelectorAll(".panel > .govde-ic")
    .forEach(buyutDugmesiniTazele);
}

/** Verisi olmayan panelin gövdesi — hangi kaynağın eksik olduğunu söyler. */
function bekleniyorGovde(neden) {
  return `<div class="bekleniyor-govde">
    <div class="bs">◷</div>
    <div><b>Veri kaynağı bekleniyor</b><br>${esc(neden)}</div>
  </div>`;
}

const iskeletHtml = (n = 4) =>
  `<div class="isk">${Array.from({ length: n }, () => "<i></i>").join("")}</div>`;

/** Yorum kartı — sayıdan çıkarılan CÜMLE. Model değil, kural üretir. */
function yorumKarti(ikon, baslik, metin, rozet) {
  return `<div class="yorum">
    <div class="bas"><span class="ik">${ikon}</span>${esc(baslik)}</div>
    <p>${esc(metin)}</p>
    <span class="rozet ${rozet.tur}">${esc(rozet.ad)}</span>
  </div>`;
}

/** Hedef–gerçekleşme çubuğu. */
function hedefCubugu(ad, gercek, hedef) {
  const oran = hedef ? Math.min(100, (gercek / hedef) * 100) : 0;
  return `<div class="hedef-sat">
    <div class="bas"><span>${esc(ad)}</span>
      <span><b>${yuzde(gercek, 0)}</b> <span style="color:var(--sonuk)">/ ${yuzde(hedef, 0)}</span></span></div>
    <div class="ray"><div class="dol" style="width:${oran.toFixed(1)}%"></div></div>
  </div>`;
}

/** Ölçek çubuğu (skor bileşenleri). */
function olcek(ad, deger, maks = 100) {
  return `<div class="olcek">
    <div class="bas"><span>${esc(ad)}</span><b>${ondalik(deger, 0)}/${maks}</b></div>
    <div class="ray"><div class="dol" style="width:${Math.min(100, (deger / maks) * 100).toFixed(1)}%"></div></div>
  </div>`;
}

/* Veriyi kabına yükler; hata ve boş durumu aynı görsel dilde gösterir. */
let nesil = 0;
/* AÇIKLAMALAR PANELDE DEĞİL, (i) DÜĞMESİNİN ARDINDA
   ------------------------------------------------------------------
   Kaynak/yöntem açıklamaları panelin üçte birini yiyordu: Geçiş
   Paneli'ndeki "Kaynak: ÖSYM türevi…" notu 395 karakter ve grafiğin
   kendisinden uzundu. Uyarı DEĞERLİ — silinmemeli — ama her bakışta
   okunması gereken bir şey de değil.

   Bu yüzden uzun not gizlenir, panelin sağ altına küçük bir (i) konur;
   tıklanınca açıklama popup'ta açılır (Esc ile kapanır).

   EŞİK NEDEN VAR: kısa notlar (eksen etiketi "öğrenci sayısı" gibi)
   yerinde kalmalı — onları düğmenin arkasına saklamak okumayı
   zorlaştırırdı. Yalnızca panele sığmayan uzunluktakiler taşınır. */
const NOT_ESIGI = 90;

/* AÇIKLAMA BALONU — tam ekran modal yerine
   ------------------------------------------------------------------
   (i) düğmesi önce `grafikModalAc` çağırıyordu: ekranın tamamı
   kararıyor, 92vw'lik bir kutu açılıyor ve içinde tek cümle duruyordu.
   Bir dipnot için fazla ağır bir jest.

   Bunun yerine düğmenin yanında küçük bir balon açılır. Sayfa
   kararmaz, arka plan okunmaya devam eder; dışarı tıklamak, Esc ya da
   aynı düğmeye tekrar basmak kapatır. Kaydırınca da kapanır — çünkü
   `position: fixed` balon, kaydırılan panelle birlikte gitmez. */
let _notPop = null;
let _notPopSahip = null;

function _notPopKapat() {
  if (_notPop) _notPop.remove();
  _notPop = null;
  _notPopSahip = null;
}

function _notPopAc(dugme, parcalar) {
  _notPopKapat();
  const p = document.createElement("div");
  p.className = "not-pop";
  p.setAttribute("role", "dialog");
  p.innerHTML = parcalar.map(t => `<p>${esc(t)}</p>`).join("");
  document.body.appendChild(p);

  const b = dugme.getBoundingClientRect();
  const k = p.getBoundingClientRect();
  /* Varsayılan: düğmenin ÜSTÜNE ve sağ kenarları hizalı. Üstte yer
     yoksa altına geçer; yanlara taşarsa görüntü alanına çekilir. */
  let x = b.right - k.width;
  let y = b.top - k.height - 9;
  if (y < 8) y = b.bottom + 9;
  if (x < 8) x = 8;
  if (x + k.width > window.innerWidth - 8) x = window.innerWidth - k.width - 8;
  p.style.left = Math.round(x) + "px";
  p.style.top = Math.round(y) + "px";

  _notPop = p;
  _notPopSahip = dugme;
}

document.addEventListener("click", e => {
  if (!_notPop) return;
  if (e.target.closest(".not-pop") || e.target.closest(".not-dugme")) return;
  _notPopKapat();
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") _notPopKapat();
});
window.addEventListener("scroll", _notPopKapat, true);
window.addEventListener("resize", _notPopKapat);

function notlariTasi(govdeIc) {
  const panel = govdeIc && govdeIc.closest(".panel");
  if (!panel) return;

  /* Panel yeniden doldurulmuş olabilir: önceki düğme kalmasın. */
  const eski = panel.querySelector(":scope > .not-dugme");
  if (eski) eski.remove();

  const uzunlar = Array.from(govdeIc.querySelectorAll(".not, .eksen-not"))
    .filter(n => n.textContent.trim().length >= NOT_ESIGI);
  if (!uzunlar.length) return;

  const parcalar = uzunlar.map(n => n.textContent.replace(/\s+/g, " ").trim());
  uzunlar.forEach(n => { n.hidden = true; });

  const d = document.createElement("button");
  d.type = "button";
  d.className = "not-dugme";
  d.textContent = "i";
  d.title = "Kaynak ve yöntem açıklaması";
  d.setAttribute("aria-label", "Kaynak ve yöntem açıklamasını göster");
  d.addEventListener("click", e => {
    e.preventDefault();
    e.stopPropagation();
    if (_notPopSahip === d) { _notPopKapat(); return; }   // aynı düğme = kapat
    _notPopAc(d, parcalar);
  });
  panel.appendChild(d);
}

/* GRAFİK İPUCU — tarayıcının kendi kutusu yerine kendi kutumuz
   ------------------------------------------------------------------
   SVG'deki `<title>` etiketi işletim sisteminin kutusunu açar: yarım
   saniye gecikmeyle gelir, temayla hiç ilgisi yoktur, uzun metni tek
   satıra sıkıştırır ve grafiğin dışına taşar.

   Çözüm: çizimden sonra `<title>` içeriği `data-ipucu`ya taşınır ve
   etiket KALDIRILIR (kaldırılmazsa yerleşik kutu yine açılır). Erişim
   kaybolmasın diye aynı metin `aria-label` olarak da yazılır.

   Kutu tek tanedir ve `position: fixed` ile imlecin yanında durur;
   ekranın sağına/üstüne taşacaksa karşı tarafa geçer. */
function ipucuHazirla(kap) {
  if (!kap || !kap.querySelectorAll) return;
  kap.querySelectorAll("svg title").forEach(t => {
    const sahip = t.parentElement;
    if (sahip && !sahip.dataset.ipucu) {
      const metin = t.textContent.replace(/\s+/g, " ").trim();
      sahip.dataset.ipucu = metin;
      sahip.setAttribute("aria-label", metin);
    }
    t.remove();
  });
}

let _ipucuKutu = null;
let _ipucuSahip = null;

/* Kolon verisinden yapısal ipucu üretir: başlık, sıra, her metrik için
   renk lekesi + ad + değer. İmlecin üstündeki metrik satırı vurgulanır. */
function _ipucuKolonHtml(sahip) {
  let v;
  try { v = JSON.parse(sahip.dataset.ipucuKolon); } catch (e) { return null; }
  if (!v || !v.satir) return null;
  const etkin = Number(sahip.dataset.ipucuSeri);
  const g = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  return `<div class="ip-bas">${g(v.ad)}${
      v.biz ? `<span class="ip-biz">bizim kurumumuz</span>` : ""}</div>
    ${v.sira ? `<div class="ip-alt">${g(v.sira)}</div>` : ""}
    <table>${v.satir.map((s, i) => `
      <tr class="${i === etkin ? "etkin" : ""}">
        <td class="ip-ad"><i class="ip-renk" style="background:${
          g(s.renk)}"></i>${g(s.ad)}</td>
        <td class="ip-deger">${g(s.deger)}</td>
      </tr>`).join("")}</table>`;
}

function _ipucuGoster(metin, mx, my, sahip) {
  if (!_ipucuKutu) {
    _ipucuKutu = document.createElement("div");
    _ipucuKutu.className = "grafik-ipucu";
    document.body.appendChild(_ipucuKutu);
  }
  const html = (sahip && sahip.dataset.ipucuKolon)
    ? _ipucuKolonHtml(sahip) : null;
  if (html) {
    _ipucuKutu.innerHTML = html;
    _ipucuKutu.classList.add("genis");
  } else {
    _ipucuKutu.textContent = metin;
    _ipucuKutu.classList.remove("genis");
  }
  _ipucuKutu.style.display = "block";
  const k = _ipucuKutu.getBoundingClientRect();
  let x = mx + 14;
  let y = my - k.height - 12;
  if (x + k.width > window.innerWidth - 8) x = mx - k.width - 14;
  if (x < 8) x = 8;
  if (y < 8) y = my + 20;                     // üstte yer yoksa altına
  _ipucuKutu.style.left = Math.round(x) + "px";
  _ipucuKutu.style.top = Math.round(y) + "px";
}

function _ipucuGizle() {
  if (_ipucuKutu) _ipucuKutu.style.display = "none";
  _ipucuSahip = null;
}

/* Tek dinleyici; her fare hareketinde `closest` çalışır ama kutu
   yalnızca SAHİP DEĞİŞTİĞİNDE yeniden yazılır. */
function _ipucuOlay(e) {
  const h = e.target && e.target.closest
    ? e.target.closest("[data-ipucu], [data-ipucu-kolon]") : null;
  if (!h) { if (_ipucuSahip) _ipucuGizle(); return; }
  _ipucuSahip = h;
  _ipucuGoster(h.dataset.ipucu || "", e.clientX, e.clientY, h);
}

/* İKİ OLAY BİRDEN DİNLENİR.
   `mousemove` kutuyu imleçle birlikte taşır. Ama imleç kıpırdamadan
   altında bir öge belirirse (grafik yeniden çizilince olur) hareket
   olmadığı için hiç tetiklenmez; `mouseover` o durumu yakalar. */
document.addEventListener("mousemove", _ipucuOlay);
document.addEventListener("mouseover", _ipucuOlay);
document.addEventListener("mouseout", e => {
  const h = e.target && e.target.closest
    ? e.target.closest("[data-ipucu], [data-ipucu-kolon]") : null;
  if (h && h === _ipucuSahip) _ipucuGizle();
});
document.addEventListener("mouseleave", _ipucuGizle);
window.addEventListener("scroll", _ipucuGizle, true);

async function doldur(kapId, getir, ciz, opt = {}) {
  const benim = nesil;
  const kap = document.getElementById(kapId);
  if (!kap) return;
  kap.innerHTML = iskeletHtml(opt.iskelet || 4);
  try {
    const veri = await getir();
    if (benim !== nesil) return;
    const hedef = document.getElementById(kapId);
    if (!hedef) return;
    hedef.innerHTML = ciz(veri) ?? "";
    buyutDugmesiniTazele(hedef);   // grafik geldiyse ⛶ düğmesi açılır
    /* DERSLİK KULLANIM HARİTASI MUAF.
       ------------------------------------------------------------------
       Bu iki yardımcı panelin DOM'unu değiştirir: `notlariTasi` panelin
       `.not` / `.eksen-not` metinlerini gizleyip (i) balonuna taşır,
       `ipucuHazirla` ise `<title>` düğümlerini silip kendi kutusuna
       çevirir. Haritanın kat özeti ("Kat 0 · 19 sınıf/lab/amfi…") ve oda
       ipuçları tam olarak bu iki mekanizmayı kullanıyor; muaf tutulmazsa
       harita paneli kendi bilgisini kaybeder ve `.panel:has(> .not-dugme)`
       kuralı yüzünden yüksekliği de değişir.

       Harita, çalışan hâliyle dokunulmaz kabul edildiği için burada
       açıkça dışarıda bırakılır. */
    if (kapId !== "alHarita") {
      notlariTasi(hedef);          // uzun açıklama (i) düğmesine taşınır
      ipucuHazirla(hedef);         // <title> -> kendi ipucu kutumuz
    }
    if (typeof _acikModal !== "undefined" && _acikModal && _acikModal.panelId === kapId) {
      const modalIc = _acikModal.kap ? _acikModal.kap.querySelector(".gmodal-ic") : null;
      if (modalIc && !modalIc.classList.contains("canli-panel")) {
        const kopya = hedef.cloneNode(true);
        if (_acikModal.panelEl && _acikModal.panelEl.dataset.buyutDetay === "1") {
          kopya.querySelectorAll("details.detay").forEach(d => { d.open = true; });
        } else {
          kopya.querySelectorAll("details.detay").forEach(d => d.remove());
        }
        modalIc.innerHTML = kopya.innerHTML;
      }
    }
  } catch (err) {
    if (benim !== nesil) return;
    const hedef = document.getElementById(kapId);
    if (!hedef) return;
    // 404 = "bu veri yok", arıza değil. Hocanın panelini boş hata
    // kutusuyla değil, kaynak beklendiğini söyleyen rozetle gösteririz.
    hedef.innerHTML = bekleniyorGovde(
      err && err.status === 404
        ? (err.userMessage || err.detail || "Bu kapsam için kayıt bulunmuyor.")
        : "Veri alınamadı: " + esc((err && (err.userMessage || err.message)) || err));
  }
}

/* ==========================================================================
   KABUK ÇİZİMİ
   ========================================================================== */

function menuCiz() {
  const fakulteler = (agac.kok && agac.kok.cocuklar) || [];
  return MENU.map(m => {
    if (m.dis) {
      return `<a class="mad" href="${m.dis}" style="text-decoration:none">
        <span class="ik">${m.ik}</span>${esc(m.ad)}</a>`;
    }
    if (m.agac) {
      const acik = K.acikMenu.has(m.id);
      return `<div class="mad ${acik ? "" : ""}" data-menu="${m.id}">
          <span class="ik">${m.ik}</span>${esc(m.ad)}<span class="ok">${acik ? "▾" : "▸"}</span>
        </div>
        <div class="alt-liste ${acik ? "acik" : ""}">
          ${fakulteler.map(f => {
            const fAcik = K.acikFakulte === f.id;
            const bolumler = agac.gercekCocuklar(f);
            /* ETİKET = KURUMSAL AD.
               Eskiden `f.kisa` yazılıyordu; o alan birimin İÇ KODUdur
               (MUHMIM, FEA, FEAS…). Kod bir kimliktir, kullanıcıya
               gösterilecek isim değildir — ekranda "FEA" gören bir
               rektör hangi fakülteye baktığını bilemez. Ad tam yazılır,
               sığmazsa CSS kısaltır; kod ipucunda kalır. */
            return `<div class="alt ${K.birimId === f.id ? "etkin" : ""}"
                      data-birim="${esc(f.id)}" data-fak="${esc(f.id)}"
                      title="${esc(f.ad)}${f.kod ? " (" + esc(f.kod) + ")" : ""}">
                <span class="ad">${esc(f.ad)}</span>${bolumler.length ? `<span class="ok2">${fAcik ? "▾" : "▸"}</span>` : ""}
              </div>
              ${fAcik ? bolumler.map(b => `<div class="alt" style="padding-left:60px"
                  data-birim="${esc(b.id)}" title="${esc(b.ad)}"
                  ><span class="ad">${esc(b.ad)}</span></div>`).join("") : ""}`;
          }).join("")}
        </div>`;
    }
    if (m.alt) {
      const acik = K.acikMenu.has(m.id);
      const etkin = m.alt.some(a => a.id === K.ekran);
      /* İKİ AYRI TIKLAMA HEDEFİ.
         Satırın kendisi GEZİNME (`data-ekran`), yalnızca chevron
         AÇ/KAPA (`data-menu`). Eskiden bütün satır aç/kapa yapıyordu ve
         grubun kendi ekranına ulaşmanın hiçbir yolu yoktu. */
      return `<div class="mad ${K.ekran === m.id ? "etkin" : (etkin && !acik ? "etkin" : "")}"
             data-ekran="${m.id}">
          <span class="ik">${m.ik}</span>${esc(m.ad)}<span class="ok" data-menu="${m.id}"
             role="button" tabindex="0"
             title="${acik ? "Alt başlıkları gizle" : "Alt başlıkları göster"}"
             aria-expanded="${acik ? "true" : "false"}">${acik ? "▾" : "▸"}</span>
        </div>
        <div class="alt-liste ${acik ? "acik" : ""}">
          ${m.alt.map(a => `<div class="alt ${K.ekran === a.id ? "etkin" : ""}"
             data-ekran="${a.id}">${esc(a.ad)}</div>`).join("")}
        </div>`;
    }
    return `<div class="mad ${K.ekran === m.id ? "etkin" : ""}" data-ekran="${m.id}">
      <span class="ik">${m.ik}</span>${esc(m.ad)}
      ${m.yeni ? `<span class="yeni">YENİ</span>` : ""}</div>`;
  }).join("");
}

/* SEÇİLİ BİRİM BİLGİLERİ
   ==========================================================================
   ÖĞRENCİ SAYISI BURADA HESAPLANMAZ.

   Önceki sürümde bu kutu sayıyı gezinme ağacından okuyordu. Ağaç ise
   program metriklerini `/api/student-analytics/by-program` ucundan alıp
   `program_code` STRING'i üzerinden eşleştiriyor ve `active_student_count`
   alanını topluyordu. KPI kartı ise `/api/decision-analytics/staffing`
   ucunun `student_count` değerini gösteriyor; o değer ÖSYM yerleştirme
   kayıtlarından türetilir.

   Bunlar İKİ FARKLI MODÜLÜN İKİ FARKLI ALANIDIR. Veritabanında örnek
   (demo) öğrenci kaydı bulunduğu anda `active_student_count` o kayıtları
   sayar ve ÖSYM türevinden ayrışır — ekranda aynı fakülte için iki farklı
   "öğrenci sayısı" belirir (gözlenen: KPI 2.213 · kenar panel 1.689).

   Kural: "bu birimde kaç öğrenci var?" sorusunun TEK cevabı
   `/api/decision-analytics/staffing` + geçerli kapsamdır. Kutu artık o
   yanıtı bekler ve KAYNAĞINI da yazar (YÖK kayıtlı / ÖSYM türevi).
   Eşleştirme ad veya kod ile değil, gerçek birim kimlikleriyle yapılır.
   ========================================================================== */
function birimKutusu() {
  const zincir = (agac.bul(K.birimId) || {}).zincir || [];
  const fak = zincir.find(n => n.tur === "fakulte");
  const bol = zincir.find(n => n.tur === "bolum");
  return `<div class="birim-kutu">
    <h4>SEÇİLİ BİRİM BİLGİLERİ</h4>
    ${bol ? `<div class="sat"><span>Bölüm</span><b>${esc(bol.ad)}</b></div>` : ""}
    ${fak ? `<div class="sat"><span>Fakülte</span><b title="${esc(fak.ad)}">${esc(fak.ad)}</b></div>` : ""}
    <div class="sat"><span>Kapsam</span><b>${
      { university: "Üniversite", faculty: "Fakülte", department: "Bölüm", program: "Program" }[seviye()]
    }</b></div>
    <div class="sat"><span>Öğrenci sayısı</span><b id="birimOgrenci">…</b></div>
    <div class="sat"><span>Akademisyen</span><b id="birimAkademik">…</b></div>
    <div class="sat"><span>Program</span><b id="birimProgram">…</b></div>
    <button data-eylem="birim-degistir">Birim Değiştir</button>
  </div>`;
}

/** Kutuyu KPI ile AYNI uçtan doldurur. */
async function birimKutusuDoldur() {
  const benim = nesil;
  const yaz = (id, deger, baslik) => {
    if (benim !== nesil) return;
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = deger;
    if (baslik) el.title = baslik;
  };
  try {
    const k = await api.get("/api/decision-analytics/staffing", kapsam());
    yaz("birimOgrenci", sayi(k.student_count),
        k.student_count_source === "yok_kayitli"
          ? "YÖK kayıtlı öğrenci sayısı (üniversite düzeyinde yetkili kaynak)"
          : "ÖSYM yerleştirmelerinden türetilen öğrenci sayısı");
    yaz("birimAkademik", sayi(k.academic_staff_count), "Aktif akademik kadro");
  } catch {
    yaz("birimOgrenci", "—", "Değer alınamadı");
    yaz("birimAkademik", "—", "Değer alınamadı");
  }
  /* Program sayısı bir GEZİNME bilgisidir (ağaçtaki düğüm sayısı),
     bir ölçüm değil; ağaçtan okunması doğrudur. */
  const d = dugum();
  yaz("birimProgram", sayi((d.metrik || {}).programSayisi));
}

/** Seçili dönemde HANGİ veri kümelerinin kaydı var — seçiciye ipucu. */
function donemIpucu() {
  const o = K.donemOzet;
  if (!o || !K.donem) return "Gerçek verisi olan dönemler listelenir.";
  const etiket = o.dataset_labels || {};
  const kapsam = (o.coverage_by_period || {})[K.donem] || [];
  const eksik = Object.keys(o.dataset_years || {}).filter(k => !kapsam.includes(k));
  return `${K.donem} döneminde kaydı olan veri kümeleri: `
    + (kapsam.map(k => etiket[k] || k).join(", ") || "yok")
    + (eksik.length ? `\nBu dönemde kaydı OLMAYAN: `
        + eksik.map(k => etiket[k] || k).join(", ") : "");
}

function ustSerit() {
  const fakulteler = (agac.kok && agac.kok.cocuklar) || [];
  const zincir = (agac.bul(K.birimId) || {}).zincir || [];
  const seciliFak = zincir.find(n => n.tur === "fakulte");
  const seciliBol = zincir.find(n => n.tur === "bolum");
  const seciliProgram = zincir.find(n => n.tur === "program");
  const bolumler = seciliFak ? agac.gercekCocuklar(seciliFak) : [];
  /* Program kapsamı servislerde zaten vardır; üst çubukta erişilemez
     olması program düzeyindeki "veri yok" ile bölüm toplamını ayırmayı
     imkânsızlaştırıyordu. Ham çocuklar bilinçli kullanılır: tek programlı
     bölümde de gerçek program kimliği seçilebilir. */
  const programlar = seciliBol ? (seciliBol.cocuklar || []) : [];
  const baslik = EKRANLAR[K.ekran] ? EKRANLAR[K.ekran].baslik : "";
  const altBaslik = EKRANLAR[K.ekran] ? EKRANLAR[K.ekran].altBaslik : "";

  return `<div class="ust">
    <h1>${esc(baslik)}${altBaslik ? `<small>${esc(altBaslik)}</small>` : ""}</h1>
    <div class="secici"><label>Fakülte</label>
      <select id="secFakulte">
        <option value="abu">Tüm Üniversite</option>
        ${fakulteler.map(f => `<option value="${esc(f.id)}" ${
          seciliFak && seciliFak.id === f.id ? "selected" : ""}>${esc(f.ad)}</option>`).join("")}
      </select></div>
    <div class="secici"><label>Bölüm</label>
      <select id="secBolum" ${bolumler.length ? "" : "disabled"}>
        <option value="">${bolumler.length ? "Tüm Bölümler" : "—"}</option>
        ${bolumler.map(b => `<option value="${esc(b.id)}" ${
          seciliBol && seciliBol.id === b.id ? "selected" : ""}>${esc(b.ad)}</option>`).join("")}
      </select></div>
    <div class="secici"><label>Program</label>
      <select id="secProgram" ${programlar.length ? "" : "disabled"}>
        <option value="">${programlar.length ? "Tüm Programlar" : "—"}</option>
        ${programlar.map(p => `<option value="${esc(p.id)}" ${
          seciliProgram && seciliProgram.id === p.id ? "selected" : ""}>${esc(p.ad)}</option>`).join("")}
      </select></div>
    <div class="sag">
      <div class="secici"><label>Dönem</label>
        ${K.donemler.length
          ? `<select id="secDonem" title="${esc(donemIpucu())}">
              ${K.donemler.slice().reverse().map(y =>
                `<option ${y === K.donem ? "selected" : ""}>${esc(y)}</option>`).join("")}
             </select>`
          /* SEÇİLEBİLİR DÖNEM YOKSA BOŞ KUTU GÖSTERİLMEZ.
             Canlıda çekirdek veri kümelerinin hepsi boş olduğu için liste
             boş dönüyor ve seçici bomboş bir kutu olarak çiziliyordu —
             kullanıcı "arayüz bozuk" diye okuyor, asıl sorun (veri yok)
             görünmüyordu. Artık durum AÇIKÇA yazılır. */
          : `<select id="secDonem" disabled
                title="Çekirdek veri kümelerinin hiçbirinde akademik yıl kaydı yok.">
               <option>dönem verisi yok</option>
             </select>`}
      </div>
      <button class="dugme" data-eylem="rapor">⤓ Raporu İndir</button>
    </div>
  </div>`;
}

/** Pano gerçek veri üzerinde çalışmıyorsa kapatılamaz uyarı şeridi. */
function veriKaynagiSeridi() {
  const v = K.veriKaynagi;
  if (!v || !v.message) return "";
  const tur = v.mode === "demo" || v.mode === "empty" ? "kritik" : "dikkat";
  return `<div class="kaynak-uyari ${tur}">
    <span class="ik">${tur === "kritik" ? "⛔" : "⚠"}</span>
    <span class="mtn">${esc(v.message)}</span>
    <span class="etiket">${esc({ demo: "ÖRNEK VERİ", empty: "VERİ YOK",
      partial: "EKSİK AKTARIM" }[v.mode] || v.mode)}</span>
  </div>`;
}

function ciz() {
  nesil++;
  const uygulama = document.getElementById("kds");

  /* SOL MENÜNÜN KAYDIRMA KONUMU KORUNUR
     ------------------------------------------------------------------
     HATA: `ciz()` tüm `#kds` ağacını `innerHTML` ile yeniden kuruyor.
     Kaydırılabilir kap olan `.yan-liste` yok edilip YENİDEN yaratıldığı
     için `scrollTop` sıfırlanıyordu. Kullanıcı menüyü aşağı kaydırıp bir
     hedefe tıkladığında ekran doğru açılıyor ama menü en başa fırlıyordu
     (ölçüldü: 377 → 0).

     Konum, DOM değiştirilmeden ÖNCE okunur ve yeni kap kurulduktan hemen
     SONRA, aynı iş parçacığında geri yazılır. Aynı görev içinde
     yapıldığı için tarayıcı arada boyama yapmaz; titreme olmaz ve
     zamanlayıcıya gerek kalmaz.

     `scrollIntoView` KULLANILMAZ: etkin maddeyi görünüre çekmek,
     kullanıcının bıraktığı konumu bozar. */
  const menuKaydirma = (() => {
    const l = uygulama.querySelector(".yan-liste");
    return l ? l.scrollTop : 0;
  })();

  uygulama.innerHTML = `
    <aside class="yan">
      <div class="yan-marka">
        <div class="arma">◈</div>
        <div><b>ABÜN</b><span>ÜST DÜZEY BİLGİ SİSTEMİ</span></div>
      </div>
      <div class="yan-baslik">Ana Menü</div>
      <div class="yan-liste" id="menuListe">${menuCiz()}</div>
      ${birimKutusu()}
    </aside>
    <div class="icerik-sar">
      ${ustSerit()}
      ${veriKaynagiSeridi()}
      <div class="govde" id="govde"></div>
    </div>`;

  /* Yeni kap kurulur kurulmaz konum geri yazılır — ekran içeriği
     çizilmeden önce, tek görev içinde. Menü yüksekliği kısalmışsa
     (ör. bir grup kapalıyken çizildiyse) tarayıcı değeri kendiliğinden
     sınırlar; uydurma bir konuma zorlamayız. */
  const yeniListe = uygulama.querySelector(".yan-liste");
  if (yeniListe && menuKaydirma) yeniListe.scrollTop = menuKaydirma;

  /* Yeniden çizim, açık bir büyütme kaplamasını geçersiz kılar. */
  if (typeof grafikModalKapat === "function") grafikModalKapat();
  if (typeof academicDetailClose === "function") academicDetailClose();

  /* FAKÜLTE TEMASI — kapsamdaki fakülteden belirlenir.
     ------------------------------------------------------------------
     `themes.js` bu arayüzden önce de vardı ama YALNIZCA eski kabuktan
     (`app.js` → klasik.html) çağrılıyordu; yeni arayüzde tema hiç
     uygulanmıyordu. Çağrı gövde çizilmeden hemen önce yapılır:
     değişkenler `documentElement` üzerine yazılır, grafikler
     `var(--vurgu)` ile okuduğu için doğru renge oturur.

     Yapıya dokunulmaz — yalnızca renk değişkenleri ve `body[data-yazi]`
     değişir. Açık tema seçiliyse `temaUygula` paleti zaten uygulamaz. */
  /* KARŞILAŞTIRMA EKRANI TARAFSIZ KALIR.
     ------------------------------------------------------------------
     Bu ekran kurumu BAŞKA kurumlarla yan yana koyar (ODTÜ, Gazi,
     Bilkent, Ostim…). Fakülte kimliğini burada sürdürmek iki şeyi
     bozar: rakip kurumların çubukları bizim fakültemizin paletinden
     çizilir ve ekran "Mühendislik'in dünyası" gibi okunur. Oysa kıyas
     dışarıya bakar; dışarıya bakarken kurumsal görünüm doğru olandır.
     Kapsam seçimi DEĞİŞMEZ — yalnızca renk kurumsala döner. */
  const NOTR_EKRANLAR = new Set(["karsilastirma"]);
  if (typeof temaUygula === "function" && typeof aktifFakulte === "function") {
    temaUygula(NOTR_EKRANLAR.has(K.ekran)
      ? "abu"
      : aktifFakulte((agac.bul(K.birimId) || {}).zincir || []));
  }

  const ekran = EKRANLAR[K.ekran] || EKRANLAR.ozet;
  const govdeKap = document.getElementById("govde");
  govdeKap.innerHTML = ekran.ciz();

  if (K.ekran !== "kokpit" && typeof mountScreenAI === "function") {
    mountScreenAI(govdeKap, K.ekran, ekran.baslik || K.ekran);
  }

  if (ekran.yukle) ekran.yukle();

  if (K.ekran !== "kokpit" && typeof refreshScreenAI === "function") {
    setTimeout(() => refreshScreenAI(K.ekran), 50);
  }

  /* Senkron çizilen paneller için düğme taraması; `doldur()` ile gelen
     paneller kendi tazelemesini dolduktan sonra yapar. */
  buyutDugmeleriniTazele(govdeKap);
  birimKutusuDoldur();
  document.title = `ABÜ KDS — ${ekran.baslik}`;
}

/* ---------------- olaylar (tek dinleyici, delegasyon) ---------------- */
function olaylariBagla() {
  document.addEventListener("click", e => {
    const academicDetail = e.target.closest("[data-academic-detail]");
    if (academicDetail && typeof academicDetailOpen === "function") {
      e.preventDefault();
      academicDetailOpen(Number(academicDetail.dataset.academicDetail));
      return;
    }
    /* GRAFİĞİ BÜYÜT — panoyu HİÇ yeniden çizmez.
       `ciz()` çağrılmadığı için açık ekran, kapsam/dönem seçimi ve sol
       menünün kaydırma konumu yapısal olarak korunur; kaplama kapanınca
       kullanıcı bıraktığı yere döner. */
    const buyut = e.target.closest("[data-buyut]");
    if (buyut) {
      e.preventDefault();
      paneliBuyut(buyut.closest(".panel"));
      return;
    }
    /* ------------------------------------------------------------------
       MENÜ GRUBU BAŞLIĞI — YALNIZCA AÇ/KAPA
       ------------------------------------------------------------------
       HATA: Bu dal eskiden `ciz()` çağırıyordu. `ciz()` uygulamanın TAM
       yeniden çizim yoludur: `#kds` bütünüyle yeniden kurulur, açık ekran
       baştan çizilir ve bütün API istekleri yeniden atılır.

       Kullanıcının gördüğü sonuç: "Öğrenci Analizleri" başlığına
       tıklayınca pano iskelete dönüp yeniden yükleniyor (sıfırlanmış
       gibi), üstelik grup da kapanıyordu — çünkü gruplar açık başlıyor.
       Alt maddeler gizlendiği için kullanıcı başlığa BİR KEZ DAHA
       tıklayıp grubu geri açmak, sonra hedefe tıklamak zorunda kalıyordu.
       "İki tıklama gerekiyor" şikâyetinin kaynağı buydu.

       Grup başlığı bir GEZİNME hedefi değildir; tek işi alt listeyi
       açıp kapamaktır. Bu yüzden artık yalnızca kenar çubuğunun DOM'unu
       yerinde günceller: pano dokunulmadan kalır, açık ekran ve verisi
       korunur, kapsam/dönem seçimi değişmez.
       ------------------------------------------------------------------ */
    /* CHEVRON ÖNCE DENENİR ve olayı burada bitirir.
       Chevron artık satırın İÇİNDE; önce `data-ekran` aransaydı
       chevron'a tıklamak da ekran değiştirirdi ve aç/kapa hiç
       çalışmazdı. Sıra bu yüzden önemli. */
    const menu = e.target.closest("[data-menu]");
    if (menu) {
      e.stopPropagation();
      const id = menu.dataset.menu;
      const acik = !K.acikMenu.has(id);
      acik ? K.acikMenu.add(id) : K.acikMenu.delete(id);
      /* Chevron başlığın içinde: grup kapsayıcısı olarak satırı ver. */
      menuGrubunuGuncelle(menu.closest(".mad") || menu, acik);
      return;
    }
    const ekranD = e.target.closest("[data-ekran]");
    if (ekranD) { K.ekran = ekranD.dataset.ekran; ciz(); return; }

    const birimD = e.target.closest("[data-birim]");
    if (birimD) {
      const id = birimD.dataset.birim;
      if (birimD.dataset.fak) K.acikFakulte = K.acikFakulte === id ? null : id;
      K.birimId = id; ciz(); return;
    }
    const eylem = e.target.closest("[data-eylem]");
    if (eylem) {
      if (eylem.dataset.eylem === "rapor") raporIndir();
      if (eylem.dataset.eylem === "birim-degistir") {
        K.birimId = "abu"; K.acikFakulte = null; ciz();
      }
      return;
    }
    const cip = e.target.closest(".cip[data-soru]");
    if (cip) {
      if (typeof asistanOneriSec === "function") asistanOneriSec(cip.dataset.soru);
      return;
    }
    const hazir = e.target.closest("[data-hazir]");
    if (hazir && typeof hazirSenaryoUygula === "function") {
      hazirSenaryoUygula(hazir.dataset.hazir); return;
    }
  });

  document.addEventListener("change", e => {
    if (e.target.id === "secFakulte") {
      K.birimId = e.target.value;
      K.acikFakulte = e.target.value === "abu" ? null : e.target.value;
      ciz(); return;
    }
    if (e.target.id === "secBolum") {
      const zincir = (agac.bul(K.birimId) || {}).zincir || [];
      const fak = zincir.find(n => n.tur === "fakulte");
      K.birimId = e.target.value || (fak ? fak.id : "abu");
      ciz(); return;
    }
    if (e.target.id === "secProgram") {
      const zincir = (agac.bul(K.birimId) || {}).zincir || [];
      const bol = zincir.find(n => n.tur === "bolum");
      K.birimId = e.target.value || (bol ? bol.id : "abu");
      ciz(); return;
    }
    if (e.target.id === "secDonem") { K.donem = e.target.value; ciz(); return; }
    /* KARŞILAŞTIRMA EVRENİ değişti.
       `ciz()` ÇAĞRILMAZ: tüm pano yeniden kurulursa sol menü kaydırması,
       açık detaylar ve diğer panellerin verisi gereksiz yere yenilenir.
       Yalnızca evrene bağlı paneller yeniden doldurulur; eski süzgecin
       verisi ekranda kalmasın diye ilgili kaplar önce iskelete döner. */
    if (e.target.matches && e.target.matches("[data-evren]")) {
      K_EVREN = e.target.value;
      document.querySelectorAll("[data-evren]").forEach(s => { s.value = K_EVREN; });
      if (typeof evrenPanelleriniYenile === "function") evrenPanelleriniYenile();
      return;
    }
    /* İKİNCİ BOYUT: program eşleştirme adaleti. Kurum türü değişkenine
       DOKUNMAZ — iki seçici birbirini sıfırlayamaz. Aynı tazeleme yolunu
       kullanır ki iki boyut tek istekte birlikte uygulansın. */
    if (e.target.matches && e.target.matches("[data-eslesme]")) {
      K_ESLESME = e.target.value;
      document.querySelectorAll("[data-eslesme]").forEach(s => { s.value = K_ESLESME; });
      if (typeof evrenPanelleriniYenile === "function") evrenPanelleriniYenile();
      return;
    }
    if (e.target.classList && e.target.classList.contains("kaydirici-giris")
        && typeof kokpitGuncelle === "function") {
      kokpitGuncelle(); return;
    }
  });

  document.addEventListener("input", e => {
    if (e.target.classList && e.target.classList.contains("kaydirici-giris")) {
      const et = e.target.parentElement.querySelector(".bas b");
      if (et) et.textContent = (e.target.value > 0 ? "+" : "") + e.target.value + "%";
      if (typeof kokpitGuncelle === "function") kokpitGuncelle();
    }
  });
}

/** Menü grubunu YERİNDE açar/kapar — panoya dokunmadan.

    `menuCiz()` tam çizimde aynı sonucu üretir; buradaki değişiklik
    yalnızca o çizimi BEKLEMEDEN aynı görsel durumu kurar. Tek doğruluk
    kaynağı yine `K.acikMenu`; bir sonraki `ciz()` çağrısı aynı hâli
    yeniden üretir, dolayısıyla iki yol ayrışamaz. */
function menuGrubunuGuncelle(baslik, acik) {
  const liste = baslik.nextElementSibling;
  if (liste && liste.classList.contains("alt-liste")) {
    liste.classList.toggle("acik", acik);
  }
  const ok = baslik.querySelector(".ok");
  if (ok) ok.textContent = acik ? "▾" : "▸";

  /* Başlığın "etkin" vurgusu, grup KAPALIYKEN ve içindeki ekran
     açıkken gösterilir (menuCiz ile aynı kural). */
  const grup = MENU.find(m => m.id === (baslik.dataset.menu
      || baslik.dataset.ekran
      || (baslik.querySelector("[data-menu]") || {}).dataset?.menu));
  if (grup && grup.alt) {
    const icerideAcikEkran = grup.alt.some(a => a.id === K.ekran);
    baslik.classList.toggle("etkin", icerideAcikEkran && !acik);
  }
}

/* Raporu İndir — ekrandaki gerçek sayıları CSV olarak verir. */
function raporIndir() {
  const satirlar = [["Ekran", EKRANLAR[K.ekran].baslik],
                    ["Birim", dugum().ad], ["Dönem", K.donem || "—"], [], []];
  document.querySelectorAll("#govde .panel").forEach(p => {
    const bas = p.querySelector("h3");
    satirlar.push([bas ? bas.textContent.trim() : ""]);
    p.querySelectorAll("table tr").forEach(tr => {
      satirlar.push([...tr.children].map(td => td.textContent.trim()));
    });
    p.querySelectorAll(".kpi").forEach(k => {
      satirlar.push([k.querySelector(".et").textContent.trim(),
                     (k.querySelector(".dg") || {}).textContent || "veri yok"]);
    });
    satirlar.push([]);
  });
  const csv = satirlar.map(r => r.map(h => `"${String(h).replace(/"/g, '""')}"`).join(";")).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  a.download = `ABU-KDS-${K.ekran}-${K.donem || "guncel"}.csv`;
  a.click();
}

/* ---------------- açılış ---------------- */
async function baslat() {
  const uygulama = document.getElementById("kds");
  uygulama.innerHTML = `<div style="padding:40px">${iskeletHtml(6)}</div>`;
  try {
    await agac.yukle();
    /* DÖNEM: TEK ÇÖZÜCÜ
       ------------------
       Eskiden `ref.academicYears()` kullanılıyordu; o uç örnek veri
       modülünün `program_enrollment_snapshots` tablosunu okur ve ileri
       tarihli planlama yıllarını da döndürür. Sonuç: arayüz açılışta
       2026-2027'yi seçiyor, gerçek verisi 2025-2026'da biten bütün
       paneller boş görünüyordu.

       `/api/reference/data-periods` yalnızca panonun ÇEKİRDEK veri
       kümelerinde (ÖSYM yerleştirme + YÖK kayıtlı öğrenci + ders yükü)
       kaydı olan yılları verir ve varsayılan olarak hepsinde verisi olan
       EN GÜNCEL yılı işaretler. */
    /* VERİ KAYNAĞI DURUMU
       -------------------
       Pano örnek (demo) veritabanı üzerinde çalışıyorsa bunu SÖYLEMEK
       zorundadır. Canlıda tam tersi oldu: bütün gerçek veri tabloları
       boşken ekran uydurma sayıları kurumsal gerçekmiş gibi gösterdi.
       Bir karar destek sisteminde bu, boş ekrandan daha tehlikelidir. */
    K.veriKaynagi = await api.get("/api/reference/data-source").catch(() => null);
    await adSozluguYukle();   // etiket çözücüsü ekranlardan ÖNCE hazır olmalı
    try {
      K.donemOzet = await api.get("/api/reference/data-periods");
      K.donemler = K.donemOzet.selectable_periods || [];
      K.donem = K.donemOzet.default_period
        || (K.donemler.length ? K.donemler[K.donemler.length - 1] : null);
    } catch {
      K.donemOzet = null; K.donemler = []; K.donem = null;
    }
  } catch (err) {
    uygulama.innerHTML = `<div style="padding:40px;color:var(--kotu)">
      Veri yüklenemedi: ${esc((err && err.message) || err)}</div>`;
    return;
  }
  olaylariBagla();
  ciz();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", baslat);
} else {
  baslat();
}
