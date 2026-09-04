/* ABÜ KDS — uygulama kabuğu (yeni tasarım + mevcut işlevsellik).
   ==========================================================================
   NE DEĞİŞTİ
   ----------
   Sol menü + 16 tam sayfa ekran yerine, yeni tasarımın HUB GRAFİĞİ geldi:

       ABÜ ──► fakülte ──► bölüm ──► kategori balonu ──► analiz paneli

   NE DEĞİŞMEDİ
   ------------
   `VIEWS` kaydı, oturum, gerçek `/api/auth/login`, bütün grafik ve
   biçimlendirme yardımcıları (`tiles`, `donuts`, `hbars`, `meters`,
   `lineChart`, `chip`) aynen duruyor. 12 `views-*.js` ekranı hiç
   değişmeden çalışır; artık tam sayfa yerine PANELİN İÇİNDE çizilirler.

   ÜST DÜZEY HUB SAYISI 8'DE SABİT
   -------------------------------
   Karşılığı olmayan modüller yeni bir menü maddesi açmaz; ilgili hub'ın
   içinde SEKME olur (bkz. `HUBLAR`). Yönetimsel üç ekran (yapı, veri
   aktarımı, kullanıcılar) üst şeritteki sistem menüsünde durur — analiz
   merceği değiller, birim kapsamına sıkıştırmak yanlış olurdu.

   Adres:  #/<birim>                (gezinme)
           #/<birim>/sec            (kategori seçimi)
           #/<birim>/<hub>          (analiz)
           #/<birim>/<hub>/<sekme>  (hub içindeki alt modül)
           #/sistem/<ekran>         (yönetimsel ekran)
   ========================================================================== */

const VIEWS = { login: { title: "Giriş" } };
const $ = id => document.getElementById(id);

/* ==================== tema ====================
   İKİ ÖZNİTELİK EŞZAMANLI TUTULUR:
     data-tema="acik"   → yeni tasarımın değişkenleri (varsayılan KOYU)
     data-theme="dark"  → eski ekranların JS'i (`isDark()`) bunu okur
   Biri güncellenip öteki unutulursa grafik renkleri temayla ters düşer. */
const isDark = () => document.documentElement.dataset.tema !== "acik";

function temaSenkron() {
  document.documentElement.dataset.theme = isDark() ? "dark" : "light";
}

if (localStorage.getItem("abu-tema") === "acik") {
  document.documentElement.dataset.tema = "acik";
}
temaSenkron();

function toggleTheme() {
  const acikti = document.documentElement.dataset.tema === "acik";
  if (acikti) {
    delete document.documentElement.dataset.tema;
    localStorage.removeItem("abu-tema");
  } else {
    document.documentElement.dataset.tema = "acik";
    localStorage.setItem("abu-tema", "acik");
  }
  temaSenkron();
  const b = $("temaBtn");
  if (b) b.textContent = acikti ? "🌙" : "☀️";
  // Gündüz moduna geçilince fakülte paletleri bastırılır, geceye dönünce
  // geri gelir — yeni tasarımın kuralı budur.
  const bulunan = agac.bul(durum.birim);
  if (bulunan) temaUygula(aktifFakulte(bulunan.zincir));
  // Grafikler renklerini JS'ten alıyor; tema değişince yeniden çizilmeli.
  panelYenile();
}

/* ==================== oturum ====================
   Oturum bilgisi `api.js` içindeki `auth` nesnesinden okunur. İkinci bir
   kopya tutulmaz; iki yerde saklanan oturum er ya da geç birbirinden ayrılır. */
const session = {
  get user() {
    const u = auth.user;
    if (!u) return null;
    return { name: u.full_name || u.username, role: u.role, raw: u };
  },
  signOut() {
    if (auth.token) api.post("/api/auth/logout", { token: auth.token }).catch(() => {});
    auth.clear();
    ref.clear();
  },
};

/* ==================== durum ====================
   üç mod:
     kategori=null, secim=false → gezinme (alt birim balonları)
     kategori=null, secim=true  → kategori seçimi (panel kapalı)
     kategori="finans"          → analiz (panel açık)                      */
let durum = { birim: "abu", hub: null, sekme: null, secim: false, sistem: null };
let FILTRE = {};   // seçili merceğin filtre değerleri

/* ==================== yönlendirme ==================== */
function adresOku() {
  const p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);

  if (p[0] === "login") return { login: true };
  if (p[0] === "sistem") {
    const ekran = SISTEM_EKRANLARI.find(s => s.rota === p[1]);
    return { birim: durum.birim || "abu", hub: null, sekme: null, secim: false,
             sistem: ekran ? ekran.rota : SISTEM_EKRANLARI[0].rota };
  }

  const birim = p[0] && agac.bul(p[0]) ? p[0] : "abu";
  if (p[1] === "sec") return { birim, hub: null, sekme: null, secim: true, sistem: null };

  const hub = HUBLAR.find(h => h.id === p[1]);
  if (!hub) return { birim, hub: null, sekme: null, secim: false, sistem: null };

  const sekme = hub.sekmeler.find(s => s.id === p[2]);
  return {
    birim, hub: hub.id, sistem: null, secim: false,
    sekme: sekme ? sekme.id : hub.sekmeler[0].id,
  };
}

const git = (birim, hub, sekme) => {
  location.hash = hub
    ? (sekme ? `#/${birim}/${hub}/${sekme}` : `#/${birim}/${hub}`)
    : `#/${birim}`;
};
const gitSecim = birim => { location.hash = `#/${birim}/sec`; };
const gitSistem = rota => { location.hash = `#/sistem/${rota}`; };

function currentRoute() { return location.hash.replace(/^#\/?/, "") || "login"; }

/* ==================== giriş ekranı ====================
   GÖRÜNÜM yeni tasarımdan, DAVRANIŞ mevcut sistemden: kimlik doğrulama
   sahte değil, gerçek `/api/auth/login` çağrısı yapılır ve jeton alınır. */
function girisCiz() {
  document.body.className = "giris-modu";
  document.body.innerHTML = `<div id="giris"><form class="giris-kart" id="girisForm">
    <div class="logo">ABÜ</div>
    <div><h1>Stratejik Yönetim ve<br>Karar Destek Sistemi</h1>
      <p>Ankara Bilim Üniversitesi · üst yönetim portalı</p></div>
    <label class="alan">Kullanıcı adı
      <input id="gKullanici" value="admin" autocomplete="username"></label>
    <label class="alan">Parola
      <input id="gParola" type="password" value="demo1234" autocomplete="current-password"></label>
    <div id="girisHata"></div>
    <button class="ana-btn" id="girisBtn">Giriş yap</button>
    <div class="kucuk-not">
      Demo hesapları: <b>admin</b> · <b>dekan.muh</b> · <b>baskan.ceng</b> · <b>ogretim.uyesi</b><br>
      Parola hepsinde <b>demo1234</b>. Yetkiler role göre sunucudan gelir.
    </div>
  </form></div>`;

  $("girisForm").addEventListener("submit", async e => {
    e.preventDefault();
    const btn = $("girisBtn"), kutu = $("girisHata");
    kutu.innerHTML = "";
    btn.disabled = true;
    btn.textContent = "Giriş yapılıyor…";
    try {
      const sonuc = await api.post("/api/auth/login", {
        username: $("gKullanici").value.trim(),
        password: $("gParola").value,
      });
      auth.save(sonuc);
      ref.clear();
      location.hash = "#/abu";
    } catch (err) {
      // Hata gizlenmez; kullanıcı ne yapacağını bilsin diye sebebi yazılır.
      kutu.innerHTML = ui.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Giriş yap";
    }
  });
}

/* ==================== kabuk ==================== */
function kabukCiz() {
  const k = session.user;
  const bashar = (k.name || "?").split(/[\s.]+/).filter(Boolean)
    .map(w => w[0]).join("").slice(0, 2).toUpperCase();

  document.body.className = "";
  document.body.innerHTML = `
    <header id="ust">
      <div class="marka"><div class="logo">ABÜ</div>
        <div><b>Karar Destek Sistemi</b><span>Stratejik Yönetim Platformu</span></div></div>
      <nav id="yol"></nav>
      <div class="ust-sag">
        <span class="donem" id="apiStatus" title="Backend durumu">● bağlanıyor…</span>
        <div class="sistem-sar">
          <button class="ikon-btn" id="sistemBtn" title="Sistem ve yönetim"
                  aria-haspopup="true" aria-expanded="false">⚙</button>
          <div id="sistemMenu" role="menu"></div>
        </div>
        <button class="ikon-btn" id="temaBtn" title="Gece / gündüz modu">${
          isDark() ? "🌙" : "☀️"}</button>
        <button class="ikon-btn" id="cikisBtn"
                title="Çıkış — ${fmt.esc(k.name)} (${fmt.esc(k.role)})">${bashar}</button>
      </div>
    </header>
    <div id="govde">
      <section id="harita">
        <div class="harita-baslik"><b id="haritaAd"></b><span id="haritaAlt"></span></div>
        <svg id="haritaSvg"></svg>
        <div class="harita-lejant" id="haritaLejant"></div>
        <div class="harita-ipucu" id="haritaIpucu"></div>
      </section>
      <section id="panel">
        <button class="panel-genislet" id="panelGenislet"
                title="Paneli genişlet" aria-pressed="false">
          <svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-7.5 7.5M10 20H4v-6M4 20l7.5-7.5"/></svg>
        </button>
        <button class="panel-kapat" id="panelKapat" title="Haritaya dön">✕</button>
        <div class="birim-basi" id="birimBasi"></div>
        <div id="filtreler"></div>
        <div id="icerik"></div>
      </section>
    </div>
    ${asistanKabukHtml()}`;

  HARITA.baslat($("haritaSvg"));
  $("temaBtn").addEventListener("click", toggleTheme);
  $("cikisBtn").addEventListener("click", () => {
    session.signOut();
    location.hash = "#/login";
    girisCiz();
  });
  $("panelKapat").addEventListener("click", () => gitSecim(durum.birim));
  $("panelGenislet").addEventListener("click", panelGenisligiDegistir);
  sistemMenusuKur();
  asistaniBagla();
  apiDurumunuTazele();

  // Panelin içindeki bir birim bağlantısına tıklanınca o birime gidilir.
  $("icerik").addEventListener("click", e => {
    const t = e.target.closest("[data-git]");
    if (t) git(t.dataset.git, durum.hub, durum.sekme);
  });
}

/* Panel genişletme — geniş tablolar (KPI karnesi, veri aktarımı, kullanıcı
   listesi, senaryo formu) dar panele sığmıyor. Harita yok olmaz, küçülür. */
function panelGenisligiDegistir() {
  const genis = document.body.classList.toggle("panel-genis");
  const btn = $("panelGenislet");
  btn.setAttribute("aria-pressed", String(genis));
  btn.title = genis ? "Paneli daralt" : "Paneli genişlet";
  btn.innerHTML = genis
    ? `<svg viewBox="0 0 24 24"><path d="M20 4l-6 6M14 4v6h6M4 20l6-6M10 20v-6H4"/></svg>`
    : `<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-7.5 7.5M10 20H4v-6M4 20l7.5-7.5"/></svg>`;
  // Grafikler kapsayıcı genişliğine göre çizildi; ölçü değişince yenilenmeli.
  setTimeout(panelYenile, 440);
}

/* Sistem menüsü — yönetimsel ekranlar. Üst düzey hub sayısını artırmaz. */
function sistemMenusuKur() {
  const menu = $("sistemMenu"), btn = $("sistemBtn");
  const gruplar = [...new Set(SISTEM_EKRANLARI.map(s => s.grup))];
  menu.innerHTML = gruplar.map(g =>
    `<div class="menu-baslik">${fmt.esc(g)}</div>` +
    SISTEM_EKRANLARI.filter(s => s.grup === g).map(s =>
      `<button type="button" role="menuitem" data-sistem="${s.rota}">
         <span class="menu-ikon">${s.ikon}</span>${fmt.esc(s.ad)}</button>`).join("")
  ).join("");

  const kapat = () => { menu.classList.remove("acik"); btn.setAttribute("aria-expanded", "false"); };
  btn.addEventListener("click", e => {
    e.stopPropagation();
    const ac = !menu.classList.contains("acik");
    menu.classList.toggle("acik", ac);
    btn.setAttribute("aria-expanded", String(ac));
  });
  menu.addEventListener("click", e => {
    const t = e.target.closest("[data-sistem]");
    if (!t) return;
    kapat();
    gitSistem(t.dataset.sistem);
  });
  document.addEventListener("click", kapat);
  document.addEventListener("keydown", e => { if (e.key === "Escape") kapat(); });
}

async function apiDurumunuTazele() {
  const el = $("apiStatus");
  if (!el) return;
  try {
    const health = await api.get("/health");
    el.textContent = "● API bağlı";
    el.classList.add("ok");
    el.title = `Sürüm ${health.version || "?"} · veritabanı ${health.database || "hazır"}`;
  } catch {
    el.textContent = "● API kapalı";
    el.classList.add("bad");
    el.title = "Backend çalışmıyor. python main.py ile başlatın.";
  }
}

/* ==================== uydu listesi ====================
   İKİ HATA BURADA DÜZELTİLDİ

   1. BİRİM KENDİNİ KENDİ ÇOCUĞU GİBİ GÖSTERİYORDU.
      YÖK yapısında bir bölümün çoğu zaman kendisiyle aynı adı taşıyan
      TEK bir programı var ("BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ" →
      "BİLGİSAYAR MÜHENDİSLİĞİ PR."). BILMUH'a girildiğinde merkez de
      uydu da BILMUH görünüyordu. Artık `agac.gercekCocuklar()` bu
      tekrarı eler; böyle bir birim YAPRAK sayılır.

   2. ÜST BİRİME ÇIKIŞ YOKTU.
      Bir seviye yukarı dönmek yalnızca kırıntı yolundan mümkündü.
      Artık haritada "▲ üst birim" düğümü var.
   ==================== */
function uydulariKur(dugum) {
  const cocuklar = agac.gercekCocuklar(dugum);
  const hublar = hublariSuz(dugum);
  const ust = ustBirim(dugum);

  /* Üst birim düğümü: kök dışında her yerde. Kategori görünümünde de
     durur ki kullanıcı analizi kapatmadan yukarı çıkabilsin. */
  const ustDugum = ust ? [{
    id: "__ust", tur: "ust", kisa: ust.kisa, ad: `▲ ${ust.ad}`,
    altYazi: `Üst birim · ${ust.kisa}`, ikon: "▲", renk: "var(--sonuk)",
  }] : [];

  if (durum.hub || durum.secim || !cocuklar.length) {
    const u = hublar.map(h => ({
      id: h.id, tur: "kategori", kisa: h.ad, ad: h.ad, altYazi: h.ad,
      ikon: h.ikon, renk: h.renk, aktif: h.id === durum.hub,
    }));
    if (cocuklar.length) {
      u.unshift({ id: "__birimler", tur: "geri", kisa: "Birimler",
        ad: "Alt birimler", altYazi: "Alt birimler", ikon: "⌂", renk: "var(--sonuk)" });
    }
    return [...ustDugum, ...u];
  }

  const u = cocuklar.map(c => ({
    id: c.id, tur: "birim", kisa: c.kisa, ad: c.ad,
    altYazi: c.ad.length > 26 ? c.ad.slice(0, 24) + "…" : c.ad,
    deger: c.metrik.ogrenciToplam, renk: c.renk,
    /* sağ üst köşedeki nokta = doluluk durumu göstergesi */
    rozet: dolulukRengi(c.metrik.doluluk),
    rozetMetin: c.metrik.doluluk === null || c.metrik.doluluk === undefined
      ? "doluluk verisi yok"
      : fmtYuzde(c.metrik.doluluk, 0) + (c.metrik.doluluk >= 80 ? " — iyi"
        : c.metrik.doluluk >= 55 ? " — izlemede" : " — riskli"),
  }));
  u.push({ id: "__analiz", tur: "analiz", kisa: "Analiz", ad: "Analizler",
    altYazi: "Analizler", ikon: "◎", renk: "#9b7ff0" });
  return [...ustDugum, ...u];
}

/** Bir düğümün bir üstündeki birim. Kök için null. */
function ustBirim(dugum) {
  const bulunan = agac.bul(dugum.id);
  if (!bulunan || bulunan.zincir.length < 2) return null;
  return bulunan.zincir[bulunan.zincir.length - 2];
}

const dolulukRengi = d =>
  d === null || d === undefined ? "var(--sonuk)"
    : d >= 80 ? "var(--iyi)" : d >= 55 ? "var(--uyari)" : "var(--kotu)";

/* ==================== yönlendirme ==================== */
let ilkYukleme = true;

async function route() {
  const yeni = adresOku();

  if (yeni.login || !session.user) {
    if (!session.user) { girisCiz(); return; }
    location.hash = "#/abu";
    return;
  }

  if (!$("govde")) kabukCiz();

  // Ağaç bir kez kurulur; her gezinmede yeniden çekilmez.
  if (!agac.hazir) {
    $("haritaIpucu").textContent = "Kurum yapısı yükleniyor…";
    try {
      await agac.yukle();
    } catch (err) {
      $("haritaIpucu").innerHTML = "";
      $("icerik").innerHTML = ui.error(err);
      $("panel").classList.add("acik");
      document.body.classList.add("analiz");
      return;
    }
  }

  const oncekiHub = durum.hub, oncekiSekme = durum.sekme, oncekiBirim = durum.birim;
  durum = yeni;

  const bulunan = agac.bul(durum.birim) || agac.bul("abu");
  const { dugum, zincir } = bulunan;
  durum.birim = dugum.id;

  const hublar = hublariSuz(dugum);
  const hub = hublar.find(h => h.id === durum.hub);
  if (durum.hub && !hub) { git(durum.birim, null); return; }

  const sistem = durum.sistem
    ? SISTEM_EKRANLARI.find(s => s.rota === durum.sistem) : null;

  document.body.classList.toggle("analiz", !!hub || !!sistem);

  /* fakülte teması: gezinme zincirindeki fakülteden belirlenir */
  const tema = temaUygula(aktifFakulte(zincir));
  isaretleriGuncelle(tema.sekil || "daire");

  kirintiCiz(zincir, hub, sistem);
  haritaCiz(dugum, zincir, hub, tema);

  if (sistem) {
    sistemEkraniCiz(sistem);
  } else if (hub) {
    const degisti = oncekiHub !== durum.hub || oncekiBirim !== durum.birim
      || oncekiSekme !== durum.sekme || ilkYukleme;
    hubCiz(hub, dugum, degisti);
  } else {
    $("icerik").innerHTML = "";
    $("filtreler").innerHTML = "";
    $("birimBasi").innerHTML = "";
    asistanKapat();
  }

  document.title = (sistem ? sistem.ad : hub ? `${dugum.kisa} · ${hub.ad}` : dugum.kisa)
    + " — ABÜ Karar Destek Sistemi";
  ilkYukleme = false;
  asistanBaglamGuncelle();
}

function kirintiCiz(zincir, hub, sistem) {
  const sonKirinti = !hub && !sistem && !durum.secim;
  $("yol").innerHTML = zincir.map((n, i) =>
    `${i ? '<span class="ayrac">›</span>' : ""}
     <button class="${sonKirinti && i === zincir.length - 1 ? "son" : ""}"
             data-yol="${fmt.esc(n.id)}">${fmt.esc(n.kisa)}</button>`
  ).join("") + (sistem
    ? `<span class="ayrac">›</span><button class="son">${sistem.ikon} ${fmt.esc(sistem.ad)}</button>`
    : hub
      ? `<span class="ayrac">›</span><button class="son">${hub.ikon} ${fmt.esc(hub.ad)}</button>`
      : durum.secim
        ? `<span class="ayrac">›</span><button class="son">◎ Analizler</button>`
        : "");
  $("yol").querySelectorAll("button[data-yol]").forEach(b =>
    b.addEventListener("click", () => git(b.dataset.yol, null)));
}

function haritaCiz(dugum, zincir, hub, tema) {
  HARITA.ciz(
    { kisa: dugum.kisa, ad: dugum.ad, renk: dugum.renk,
      altYazi: `${fmtSayi(dugum.metrik.ogrenciToplam)} öğrenci` },
    uydulariKur(dugum),
    (id, tur) => {
      if (tur === "birim") git(id, null);
      // "Analizler" HER ZAMAN İÇİNDE BULUNULAN kapsamı açar; alt birime
      // inmez. Yaprak birimlerde tek analiz yolu budur.
      else if (tur === "analiz") gitSecim(durum.birim);
      else if (tur === "ust") git(id === "__ust" ? ustBirim(dugum).id : id, null);
      else if (tur === "geri") git(durum.birim, null);
      else git(durum.birim, id);
    },
    tema
  );

  $("haritaAd").textContent = dugum.ad;
  $("haritaAlt").innerHTML = zincir.map(n => fmt.esc(n.kisa)).join(" › ")
    + (hub ? ` › ${fmt.esc(hub.ad)}` : durum.secim ? " › Analizler" : "")
    + (tema.degiskenler ? ` <span class="tema-rozet">${fmt.esc(tema.ad)} tema</span>` : "");

  const cocukSayi = agac.gercekCocuklar(dugum).length;
  const kategoriGosteriliyor = !!hub || durum.secim || !cocukSayi;
  $("haritaLejant").innerHTML = kategoriGosteriliyor ? "" : `
    <span class="lejant-baslik">Köşedeki nokta = doluluk</span>
    <span><i style="background:var(--iyi)"></i>%80+ iyi</span>
    <span><i style="background:var(--uyari)"></i>%55–79 izlemede</span>
    <span><i style="background:var(--kotu)"></i>%55 altı riskli</span>`;
  $("haritaIpucu").textContent = hub
    ? "Başka bir kategori balonuna tıklayarak analizi değiştirin"
    : kategoriGosteriliyor
      // Yaprak birimde "alt birim" ifadesi kullanılmaz; alt birimi yoktur.
      ? (cocukSayi
          ? "Bir kategori balonuna tıklayarak analizi açın"
          : "Bu birimin alt birimi yok · kategori balonuyla analizi açın")
      : `${cocukSayi} alt birim · düğüme tıklayarak inin, ◎ Analizler ile inceleyin`;
}

/* ==================== hub çizimi ====================
   Hub başlığı + sekme şeridi + seçili ekranın kendi çizimi.
   Ekran `VIEWS` kaydından gelir ve HİÇ DEĞİŞMEDEN çalışır. */
function hubCiz(hub, dugum, yenidenCiz) {
  const turAd = { universite: "Üniversite", fakulte: "Fakülte",
                  bolum: "Bölüm", program: "Program" }[dugum.tur] || "Birim";

  $("birimBasi").innerHTML = `
    <div class="birim-rozet"
         style="background:linear-gradient(140deg, ${hub.renk}, ${hub.renk}99)">${hub.ikon}</div>
    <div><span class="tur">${turAd} · ${fmt.esc(dugum.kisa)}</span>
      <h1>${fmt.esc(hub.ad)}</h1>
      <div class="alt">${fmt.esc(dugum.ad)} · ${fmtSayi(dugum.metrik.ogrenciToplam)} öğrenci</div></div>`;

  const sekme = hub.sekmeler.find(s => s.id === durum.sekme) || hub.sekmeler[0];
  const mercek = MERCEK_CIZ[mercekAnahtari(hub.id, sekme.id)];

  // Sekme şeridi + merceğin kendi filtreleri — ikisi de aynı çubukta,
  // prototipin `.filtreler` görünümünde.
  const sekmeSeridi = `<div class="hub-sekmeler" role="tablist">${hub.sekmeler.map(s =>
    `<button class="hub-sekme ${s.id === durum.sekme ? "aktif" : ""}"
             role="tab" aria-selected="${s.id === durum.sekme}"
             data-sekme="${fmt.esc(s.id)}"><span class="sekme-ikon">${s.ikon}</span>${
      fmt.esc(s.ad)}</button>`).join("")}</div>`;

  if (yenidenCiz) FILTRE = {};
  const tanimlar = mercek && mercek.filtreler ? mercek.filtreler(dugum) : [];
  tanimlar.forEach(t => { if (FILTRE[t.id] === undefined) FILTRE[t.id] = t.varsayilan; });

  $("filtreler").innerHTML = sekmeSeridi + (tanimlar.length ? filtreCubuguHtml(tanimlar) : "");
  $("filtreler").querySelectorAll("[data-sekme]").forEach(b =>
    b.addEventListener("click", () => git(durum.birim, hub.id, b.dataset.sekme)));
  filtreleriBagla(hub, dugum);

  if (!yenidenCiz) return;
  mercekCiz(hub, sekme, dugum);
  $("panel").scrollTop = 0;
}

/* Filtre çubuğu — prototipin `.filtreler` / `.fcip` / `select` görünümü. */
function filtreCubuguHtml(tanimlar) {
  return `<div class="filtreler"><span class="fbaslik">Filtre</span>` +
    tanimlar.map(t => t.tip === "cip"
      ? t.secenekler.map(s =>
          `<button class="fcip ${FILTRE[t.id] === s.deger ? "aktif" : ""}"
             data-f="${fmt.esc(t.id)}" data-v="${fmt.esc(s.deger)}">${fmt.esc(s.ad)}</button>`).join("")
      : t.tip === "arama"
      // Arama kutusu: müfredat 1205 satır; listeyi gözle taramak yerine
      // aramak gerekiyor. Değer FILTRE'de tutulur, mercek onu okur.
      ? `<input type="search" class="farama" data-f="${fmt.esc(t.id)}"
           placeholder="${fmt.esc(t.yer || "Ara…")}"
           value="${fmt.esc(FILTRE[t.id] || "")}">`
      : `<select data-f="${fmt.esc(t.id)}">${t.secenekler.map(s =>
          `<option value="${fmt.esc(s.deger)}"${
            String(FILTRE[t.id]) === String(s.deger) ? " selected" : ""}>${
            fmt.esc(s.ad)}</option>`).join("")}</select>`
    ).join("") + `</div>`;
}

function filtreleriBagla(hub, dugum) {
  const sekme = hub.sekmeler.find(s => s.id === durum.sekme) || hub.sekmeler[0];
  $("filtreler").querySelectorAll(".fcip").forEach(b =>
    b.addEventListener("click", () => {
      FILTRE[b.dataset.f] = b.dataset.v;
      hubCiz(hub, dugum, false);
      mercekCiz(hub, sekme, dugum);
    }));
  $("filtreler").querySelectorAll("select").forEach(sel =>
    sel.addEventListener("change", () => {
      FILTRE[sel.dataset.f] = sel.value;
      mercekCiz(hub, sekme, dugum);
    }));
  // Arama: her tuşta istek atmamak için 300 ms bekletilir.
  $("filtreler").querySelectorAll(".farama").forEach(inp => {
    let zaman;
    inp.addEventListener("input", () => {
      clearTimeout(zaman);
      zaman = setTimeout(() => {
        FILTRE[inp.dataset.f] = inp.value.trim();
        mercekCiz(hub, sekme, dugum);
      }, 300);
    });
  });
}

/**
 * Bir merceği çizer — YENİ tasarımın bileşen sözlüğüyle.
 *
 * Mercek yoksa (henüz taşınmamış sekme) eski `VIEWS` ekranı kaba çizilir;
 * bu geçici köprü `hubs.js` içinde `view:` alanıyla açıkça işaretlidir.
 */
function mercekCiz(hub, sekme, dugum) {
  const anahtar = mercekAnahtari(hub.id, sekme.id);
  const mercek = MERCEK_CIZ[anahtar];
  AKTIF_MERCEK = { hub, sekme, dugum };
  AKTIF_EKRAN = null;
  nesilTazele();                   // geç gelen eski istekler yazmasın

  if (!mercek) { ekranCiz(sekme.view); return; }
  $("icerik").innerHTML = `<div class="gecis">${mercek.ciz(dugum, FILTRE)}</div>`;
}

let AKTIF_MERCEK = null;

function sistemEkraniCiz(sistem) {
  $("birimBasi").innerHTML = `
    <div class="birim-rozet" style="background:linear-gradient(140deg,#64748b,#64748b99)">${sistem.ikon}</div>
    <div><span class="tur">Sistem · ${fmt.esc(sistem.grup)}</span>
      <h1>${fmt.esc(sistem.ad)}</h1>
      <div class="alt">Kurum geneli yönetim ekranı</div></div>`;
  $("filtreler").innerHTML = "";
  AKTIF_MERCEK = null;
  ekranCiz(sistem.view);
  $("panel").scrollTop = 0;
  // Yönetimsel ekranlar geniş tablolar taşır; panel kendiliğinden genişler.
  if (!document.body.classList.contains("panel-genis")) panelGenisligiDegistir();
}

/**
 * Mevcut bir `VIEWS` ekranını panelin içine çizer.
 *
 * ESKİ DOM'A DOKUNULMAZ: ekran kendi HTML'ini üretir, kendi `init()`ini
 * çalıştırır, kendi kimliklerini kullanır. Değişen tek şey kapsayıcıdır.
 */
function ekranCiz(viewAdi) {
  const view = VIEWS[viewAdi];
  const kap = $("icerik");
  if (!view) {
    kap.innerHTML = ui.error(new Error(`Ekran bulunamadı: ${viewAdi}`));
    return;
  }
  AKTIF_EKRAN = viewAdi;
  kap.innerHTML = `<div class="hub-govde gecis">${view.html()}</div>`;
  try {
    const sonuc = view.init && view.init();
    if (sonuc && typeof sonuc.catch === "function") {
      sonuc.catch(err =>
        ui.toast("Ekran yüklenirken hata: " + (err.userMessage || err.message), "error"));
    }
  } catch (err) {
    ui.toast("Ekran yüklenirken hata: " + (err.userMessage || err.message), "error");
  }
}

let AKTIF_EKRAN = null;

/** Tema veya panel genişliği değişince aktif içeriği yeniden çizer. */
function panelYenile() {
  if (!$("icerik")) return;
  if (AKTIF_MERCEK) {
    const { hub, sekme, dugum } = AKTIF_MERCEK;
    mercekCiz(hub, sekme, dugum);
    return;
  }
  if (AKTIF_EKRAN) ekranCiz(AKTIF_EKRAN);
}

/* ==========================================================================
   AKILLI ASİSTAN — yeni kabuk, mevcut motor
   --------------------------------------------------------------------------
   GÖRÜNÜM yeni tasarımdan: balon düğmesi (hub minyatürü ikonu), kompakt
   panel, ⤢ ile açılan tam ekran çalışma alanı, Esc/⤡/✕ davranışları,
   fakülte temasını devralma, yörünge dönüşü ve çekirdek nabzı.

   MOTOR mevcut sistemden: `/api/assistant/chat`, Gemini API, araç
   çağırma, `structured_result`, `ui_spec` ve `ai-view-renderer.js`.
   Prototipteki kural tabanlı `asistanCevap()` SİLİNDİ — sahte cevaptı.

   İki görünüm TEK SOHBETİ paylaşır: `views-assistant.js` içindeki `THREAD`.
   Balonda sorulan soru tam ekranda da görünür; tersi de geçerli.
   ========================================================================== */

/* --- Asistan işareti: uygulamanın kendi hub grafiğinin minyatürü --- */
function isaretSekli(sekil, cx, cy, r) {
  if (sekil === "altigen") {
    const p = [];
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 180 * (60 * i - 30);
      p.push(`${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`);
    }
    return `<polygon points="${p.join(" ")}"/>`;
  }
  if (sekil === "kare")
    return `<rect x="${(cx - r).toFixed(1)}" y="${(cy - r).toFixed(1)}"
      width="${(2 * r).toFixed(1)}" height="${(2 * r).toFixed(1)}" rx="${(r * .25).toFixed(1)}"/>`;
  if (sekil === "elmas") {
    const p = [[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]]
      .map(q => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(" ");
    return `<polygon points="${p}"/>`;
  }
  return `<circle cx="${cx}" cy="${cy}" r="${r}"/>`;
}

function isaretUret(sekil = "daire") {
  return `
<svg class="ai-isaret" viewBox="0 0 32 32" aria-hidden="true">
  <g class="yorunge">
    <line x1="16" y1="16" x2="16" y2="6"/>
    <line x1="16" y1="16" x2="24.7" y2="21"/>
    <line x1="16" y1="16" x2="7.3" y2="21"/>
    ${isaretSekli(sekil, 16, 6, 2.9)}
    ${isaretSekli(sekil, 24.7, 21, 2.9)}
    ${isaretSekli(sekil, 7.3, 21, 2.9)}
  </g>
  <g class="cekirdek">${isaretSekli(sekil, 16, 16, 4.6)}</g>
</svg>`;
}
const ASISTAN_ISARET = isaretUret("daire");

let sonIsaretSekli = "daire";
function isaretleriGuncelle(sekil) {
  if (sekil === sonIsaretSekli) return;
  sonIsaretSekli = sekil;
  document.querySelectorAll(".ai-isaret").forEach(eski => {
    const gecici = document.createElement("div");
    gecici.innerHTML = isaretUret(sekil);
    const yeni = gecici.firstElementChild;
    yeni.setAttribute("class", eski.getAttribute("class"));
    eski.replaceWith(yeni);
  });
}

const OK_GENISLET = `
<svg viewBox="0 0 24 24" class="ok-isaret" aria-hidden="true">
  <path d="M14 4h6v6M20 4l-7.5 7.5M10 20H4v-6M4 20l7.5-7.5"/></svg>`;
const OK_DARALT = `
<svg viewBox="0 0 24 24" class="ok-isaret" aria-hidden="true">
  <path d="M20 4l-6 6M14 4v6h6M4 20l6-6M10 20v-6H4"/></svg>`;

const ORNEK_SORULAR = [
  "Bu birimin doluluk oranı neden düşüyor?",
  "Mali durumu nasıl?",
  "Akademik personel yükü ne durumda?",
  "Öğrenci sayısı %15 artarsa ne olur?",
];

function asistanKabukHtml() {
  return `
    <button id="asistan-genislet" title="Tam ekran asistan">${OK_GENISLET}</button>
    <button id="asistan-btn" title="Akıllı asistan">${ASISTAN_ISARET}</button>
    <div id="asistan-panel">
      <div class="bas">${ASISTAN_ISARET}<b>Akıllı Asistan</b>
        <span class="ai-durum" id="asistanDurumKucuk"></span>
        <button id="asistanBuyut" title="Tam ekrana genişlet">${OK_GENISLET}</button>
        <button id="asistanKapat" title="Kapat">✕</button></div>
      <div id="akis" class="assistant-thread" data-thread></div>
      <div class="oneriler" id="oneriler"></div>
      <div class="yaz"><input id="soru" maxlength="4000"
        placeholder="Bu birim hakkında sorun…"><button id="gonder">➤</button></div>
    </div>

    <div id="asistan-tam">
      <div class="tam-kart">
        <header class="tam-bas">
          ${ASISTAN_ISARET}
          <div class="tam-baslik"><b>Akıllı Asistan</b><span id="tamBaglam"></span></div>
          <button id="asistanKucult" title="Küçült">${OK_DARALT}</button>
          <button id="asistanTamKapat" title="Kapat">✕</button>
        </header>
        <div class="tam-govde">
          <aside class="tam-yan">
            <h4>Örnek sorular</h4>
            <div class="tam-oneriler" id="tamOneriler"></div>
            <h4>Model durumu</h4>
            <div id="asistanDurum"></div>
            <h4>Aktif bağlam</h4>
            <dl class="kv" id="tamOzet"></dl>
            <div class="tam-not">Asistan kurum verisini gerçek kayıtlardan okur;
              sayıları kendi üretmez. Seçili birim soruya bağlam olarak eklenir.</div>
          </aside>
          <section class="tam-sohbet">
            <div id="tamAkis" class="assistant-thread" data-thread></div>
            <div id="tamPanel" class="ai-panel" hidden></div>
            <div class="yaz">
              <input id="tamSoru" maxlength="4000"
                placeholder="Bu birim hakkında ayrıntılı bir soru sorun…">
              <button id="tamGonder">➤</button>
            </div>
          </section>
        </div>
      </div>
    </div>`;
}

/* --- açılış/kapanış animasyonları (yeni tasarımdan aynen) --- */
function sohbetPaneli(ac) {
  $("asistan-panel").classList.toggle("acik", ac);
  document.body.classList.toggle("sohbet-acik", ac);
  if (ac) renderThread();
}

function acilisNoktasiHesapla() {
  const kart = document.querySelector(".tam-kart");
  const b = $("asistan-btn").getBoundingClientRect();
  const kaynakX = b.width ? b.left + b.width / 2 : innerWidth - 52;
  const kaynakY = b.height ? b.top + b.height / 2 : innerHeight - 52;
  kart.style.setProperty("--dx", Math.round(kaynakX - innerWidth / 2) + "px");
  kart.style.setProperty("--dy", Math.round(kaynakY - innerHeight / 2) + "px");
}

const tamAsistanAc = () => {
  asistanBaglamGuncelle();
  const tam = $("asistan-tam");
  tam.classList.remove("kapaniyor");
  acilisNoktasiHesapla();
  tam.classList.add("acik");
  sohbetPaneli(false);
  renderThread();
  setTimeout(() => $("tamSoru").focus(), 160);
};

let kapanmaZaman = null;
const tamAsistanKapat = () => {
  const tam = $("asistan-tam");
  if (!tam || !tam.classList.contains("acik")) return;
  tam.classList.add("kapaniyor");
  clearTimeout(kapanmaZaman);
  kapanmaZaman = setTimeout(() => tam.classList.remove("acik", "kapaniyor"), 340);
};

function asistanKapat() {
  const p = $("asistan-panel");
  if (p) p.classList.remove("acik");
  document.body.classList.remove("sohbet-acik");
  const t = $("asistan-tam");
  if (t) t.classList.remove("acik", "kapaniyor");
}

/* --- bağlam: hangi birimdeyiz? --- */
function asistanBaglamGuncelle() {
  const bulunan = agac.hazir ? agac.bul(durum.birim) : null;
  const dugum = bulunan ? bulunan.dugum : null;
  const etiket = dugum ? dugum.ad : "Üniversite geneli";

  const b = $("tamBaglam");
  if (b) b.textContent = etiket;

  const ozet = $("tamOzet");
  if (ozet && dugum) {
    const m = dugum.metrik || {};
    ozet.innerHTML = `
      <dt>Birim</dt><dd>${fmt.esc(dugum.ad)}</dd>
      <dt>Öğrenci</dt><dd>${fmtSayi(m.ogrenciToplam)}</dd>
      <dt>Doluluk</dt><dd>${fmtYuzde(m.doluluk, 0)}</dd>
      <dt>Program</dt><dd>${fmtSayi(m.programSayisi)}</dd>`;
  }
  const giris = $("soru"), tamGiris = $("tamSoru");
  const ipucu = dugum && dugum.tur !== "universite"
    ? `${dugum.kisa} hakkında sorun…` : "Bu birim hakkında sorun…";
  if (giris) giris.placeholder = ipucu;
  if (tamGiris) tamGiris.placeholder = ipucu;
}

/**
 * Soruyu olduğu gibi döndürür.
 *
 * ESKİ DAVRANIŞ VE NEDEN KALDIRILDI
 * ----------------------------------
 * Burada seçili birimin ADI sorunun metnine ekleniyordu:
 *     "Yazılım Mühendisliği için: doluluk nedir?"
 * Bu, kapsamı METİN üzerinden taşıyordu ve iki sorunu vardı:
 *   1. Ad eşleştirmesi yazım/büyük-küçük harf farklarında kırılıyordu.
 *   2. Kapsam, backend'de yapısal olarak zorlanamıyordu.
 *
 * Kapsam artık `/api/assistant/chat` gövdesinde `scope` alanıyla
 * KİMLİK olarak gönderiliyor (bkz. views-assistant.js) ve araçların
 * eksik kapsam parametrelerini backend dolduruyor. Fonksiyon, çağrı
 * yerlerini bozmamak için korundu.
 */
function baglamliSoru(metin) {
  return metin;
}

function asistaniBagla() {
  const oneriHtml = ORNEK_SORULAR
    .map(q => `<button type="button" data-q="${fmt.esc(q)}">${fmt.esc(q)}</button>`).join("");
  $("oneriler").innerHTML = oneriHtml;
  $("tamOneriler").innerHTML = oneriHtml;
  [$("oneriler"), $("tamOneriler")].forEach(kap =>
    kap.querySelectorAll("button").forEach(b =>
      b.addEventListener("click", () => asistanaSor(b.dataset.q))));

  $("asistan-btn").addEventListener("click", () =>
    sohbetPaneli(!$("asistan-panel").classList.contains("acik")));
  $("asistanKapat").addEventListener("click", () => sohbetPaneli(false));
  $("gonder").addEventListener("click", () => { asistanaSor($("soru").value); $("soru").value = ""; });
  $("soru").addEventListener("keydown", e => {
    if (e.key === "Enter") { asistanaSor($("soru").value); $("soru").value = ""; } });

  $("asistan-genislet").addEventListener("click", tamAsistanAc);
  $("asistanBuyut").addEventListener("click", tamAsistanAc);
  $("asistanKucult").addEventListener("click", () => { tamAsistanKapat(); sohbetPaneli(true); });
  $("asistanTamKapat").addEventListener("click", tamAsistanKapat);
  $("asistan-tam").addEventListener("click", e => {
    if (e.target.id === "asistan-tam") tamAsistanKapat(); });
  $("tamGonder").addEventListener("click", () => { asistanaSor($("tamSoru").value); $("tamSoru").value = ""; });
  $("tamSoru").addEventListener("keydown", e => {
    if (e.key === "Enter") { asistanaSor($("tamSoru").value); $("tamSoru").value = ""; } });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") tamAsistanKapat(); });

  refreshAssistantStatus();   // views-assistant.js — gerçek model durumu
  renderThread();
}

/** Sorma noktası TEK: gerçek `/api/assistant/chat` akışı kullanılır. */
function asistanaSor(metin) {
  const q = (metin || "").trim();
  if (!q) return;
  sendMessage(baglamliSoru(q));   // views-assistant.js
}
/* ==================== shared render helpers ==================== */
function tiles(id, arr) {
  $(id).innerHTML = arr.map(([label, value, delta, dir, accent]) =>
    `<div class="tile${accent ? " accent-" + accent : ""}"><div class="label">${label}</div><div class="value">${value}</div>` +
    (delta ? `<div class="delta ${dir || ""}">${delta}</div>` : "") + `</div>`).join("");
}

// Ring gauges (the donut charts from the ABU brief's reference designs).
function donuts(id, rows, opts = {}) {
  const R = 34, C = 2 * Math.PI * R;
  $(id).innerHTML = `<div class="donut-row">` + rows.map(([label, pct, color]) => `
    <div class="donut-box" title="${label}: ${pct}%">
      <svg viewBox="0 0 84 84" width="${opts.size || 92}" height="${opts.size || 92}">
        <circle cx="42" cy="42" r="${R}" fill="none" stroke="var(--track)" stroke-width="9"/>
        <circle cx="42" cy="42" r="${R}" fill="none" stroke="${color || "var(--primary)"}" stroke-width="9"
          stroke-linecap="round" stroke-dasharray="${(Math.min(pct, 100) / 100 * C).toFixed(1)} ${C.toFixed(1)}"
          transform="rotate(-90 42 42)"/>
        <text x="42" y="47" text-anchor="middle" class="donut-val">${pct}%</text>
      </svg>
      <div class="donut-label">${label}</div>${opts.unit ? `<div class="donut-unit">${opts.unit}</div>` : ""}
    </div>`).join("") + `</div>`;
}

function hbars(id, rows, opts = {}) {
  // opts.valueLabel: çubukların neyi gösterdiği (ör. "Milyon USD").
  // Bu etiket olmadan kullanıcı çubuk uzunluğunun neyi ölçtüğünü bilemiyordu.
  const max = opts.max || Math.max(...rows.map(r => Number(r[1]) || 0), 1);
  const format = opts.fmt || (v => v);
  const header = opts.valueLabel
    ? `<div class="chart-caption">${fmt.esc(opts.valueLabel)}</div>` : "";
  const legend = opts.legend
    ? `<div class="legend">` + opts.legend.map(([label, color]) =>
        `<span><span class="swatch" style="background:${color}"></span>${fmt.esc(label)}</span>`
      ).join("") + `</div>` : "";
  $(id).innerHTML = header + rows.map(([name, value, color]) => `
    <div class="hbar" title="${fmt.esc(name)}: ${format(value)}${opts.valueLabel ? " (" + fmt.esc(opts.valueLabel) + ")" : ""}">
      <span class="name">${fmt.esc(name)}</span>
      <div class="track"><div class="fill" style="width:${((Number(value) || 0) / max * 100).toFixed(1)}%${color ? `;background:${color}` : ""}"></div></div>
      <span class="val">${format(value)}</span>
    </div>`).join("") + legend;
}

function meters(id, rows) {
  $(id).innerHTML = rows.map(([name, pct, color]) => `
    <div class="meter">
      <div class="m-label"><span>${name}</span><b>${pct}%</b></div>
      <div class="track"><div class="fill" style="width:${Math.min(pct, 100)}%${color ? `;background:${color}` : ""}"></div></div>
    </div>`).join("");
}

function lineChart(id, labels, series, opts = {}) {
  // Eksen adları, birim ve legend zorunlu hale getirildi: eksende ne olduğu
  // yazmayan bir grafik "52.2" gibi anlamsız sayılar gösteriyordu.
  const W = 620, H = opts.height || 230;
  const L = opts.yAxisLabel ? 62 : 48;   // sol boşluk: y ekseni adı için yer
  const R = 16, T = 16, B = opts.xAxisLabel ? 48 : 32;

  const all = series.flatMap(s => s.values).filter(v => Number.isFinite(v));
  if (!all.length) {
    document.getElementById(id).innerHTML = ui.empty("Grafik için veri yok.");
    return;
  }
  const lo = opts.min ?? Math.min(...all) * 0.9;
  const hi = opts.max ?? Math.max(...all) * 1.05;
  const x = i => L + i * (W - L - R) / Math.max(1, labels.length - 1);
  const y = v => T + (hi - v) / (hi - lo || 1) * (H - T - B);
  const fmtY = opts.yfmt || (v => Math.round(v));

  let svg = "";
  // Yatay ızgara + y ekseni değerleri
  for (let g = 0; g <= 4; g++) {
    const v = lo + (hi - lo) * g / 4;
    svg += `<line class="grid" x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}"/>` +
           `<text x="${L - 8}" y="${y(v) + 3}" text-anchor="end">${fmtY(v)}</text>`;
  }
  // X ekseni etiketleri
  labels.forEach((lab, i) => {
    svg += `<text x="${x(i)}" y="${H - (opts.xAxisLabel ? 26 : 10)}" text-anchor="middle">${fmt.esc(lab)}</text>`;
  });
  // Eksen adları
  if (opts.yAxisLabel) {
    svg += `<text class="axis-title" transform="rotate(-90 14 ${H / 2})" x="14" y="${H / 2}" ` +
           `text-anchor="middle">${fmt.esc(opts.yAxisLabel)}</text>`;
  }
  if (opts.xAxisLabel) {
    svg += `<text class="axis-title" x="${(L + W - R) / 2}" y="${H - 6}" ` +
           `text-anchor="middle">${fmt.esc(opts.xAxisLabel)}</text>`;
  }
  // Seriler
  series.forEach(sr => {
    const pts = sr.values.map((v, i) => Number.isFinite(v) ? `${x(i)},${y(v)}` : null).filter(Boolean);
    svg += `<polyline fill="none" stroke="${sr.color}" stroke-width="2.2" points="${pts.join(" ")}"/>`;
    sr.values.forEach((v, i) => {
      if (!Number.isFinite(v)) return;
      // Tooltip: seri adı + dönem + değer + birim. Çıplak sayı bırakılmıyor.
      const tip = `${sr.label} · ${labels[i]}: ${fmtY(v)}${opts.unitSuffix || ""}`;
      svg += `<circle cx="${x(i)}" cy="${y(v)}" r="3.8" fill="${sr.color}" ` +
             `stroke="var(--surface)" stroke-width="1.5"><title>${fmt.esc(tip)}</title></circle>`;
    });
  });

  const legend = `<div class="legend">` + series.map(sr =>
    `<span><span class="swatch" style="background:${sr.color}"></span>${fmt.esc(sr.label)}</span>`
  ).join("") + (opts.periodNote ? `<span class="period-note">${fmt.esc(opts.periodNote)}</span>` : "") + `</div>`;

  document.getElementById(id).innerHTML =
    `<svg class="chart" viewBox="0 0 ${W} ${H}">${svg}</svg>` + legend;
}

function chip(status, text) {
  const map = { good: "✓", warning: "!", critical: "▲", info: "•", neutral: "•" };
  return `<span class="chip ${status}">${map[status] || ""} ${text}</span>`;
}

const fmtUSD = n => "$" + (Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(1) + "M" : Math.round(n).toLocaleString("en-US"));
const fmtK = n => "$" + Math.round(n).toLocaleString("en-US");

/* ==================== boot ==================== */
window.addEventListener("hashchange", route);
document.addEventListener("DOMContentLoaded", route);
