/* ABÜ KDS — fakülte temaları.
   Bir fakülteye girildiğinde arayüz o fakültenin kimliğine bürünür:
   arka plan dokusu, renk paleti, tipografi ve düğüm şekli değişir.
   Tema, gezinme zincirindeki fakülteden otomatik belirlenir.            */

const TEMALAR = {
  /* ---------- varsayılan: kurumsal kokpit ---------- */
  abu: {
    ad: "Kurumsal", sekil: "daire", desen: null, yaziTipi: null,
    ipucu: "Kurumsal görünüm",
  },

  /* ---------- MMF: siber / devre kartı ---------- */
  mmf: {
    ad: "Siber", sekil: "altigen", desen: "devre", yaziTipi: "mono",
    ipucu: "Siber tema — mühendislik",
    degiskenler: {
      "--bg": "#03080e", "--bg-2": "#061118", "--yuzey": "#07161f", "--yuzey-2": "#0a1e2a",
      "--cizgi": "#0e3040", "--kenar": "rgba(0,229,255,.16)",
      "--metin": "#d6f7ff", "--metin-2": "#7fc6d9", "--sonuk": "#4a8497",
      "--vurgu": "#00e5ff", "--vurgu-2": "#00ffa3",
      "--iyi": "#00ffa3", "--uyari": "#ffc400", "--kotu": "#ff2d6f",
      "--mor": "#9d7bff", "--pembe": "#ff5ca8",
      "--vurgu-uzeri": "#04222b",
      "--golge": "0 0 0 1px rgba(0,229,255,.08), 0 8px 28px rgba(0,229,255,.10)",
    },
  },

  /* ---------- Hukuk: kağıt ve mürekkep ---------- */
  hukuk: {
    ad: "Kağıt", sekil: "daire", desen: "kagit", yaziTipi: "serif",
    ipucu: "Kağıt tema — hukuk",
    degiskenler: {
      "--bg": "#efe7d6", "--bg-2": "#e6dcc6", "--yuzey": "#faf5e9", "--yuzey-2": "#f3ecdb",
      "--cizgi": "#d8cbb0", "--kenar": "rgba(60,42,24,.18)",
      "--metin": "#241a10", "--metin-2": "#5c4a34", "--sonuk": "#8a7458",
      "--vurgu": "#1d3f6e", "--vurgu-2": "#7a1f2b",
      "--iyi": "#2f6b3a", "--uyari": "#a8701a", "--kotu": "#8b2130",
      "--track": "#e2d7bf",
      "--mor": "#5b4a8a", "--pembe": "#a2536b",
      "--vurgu-uzeri": "#ffffff",
      "--golge": "0 1px 2px rgba(60,42,24,.10), 0 8px 22px rgba(60,42,24,.10)",
    },
  },

  /* ---------- İnsan ve Toplum: kütüphane ---------- */
  insan: {
    ad: "Kütüphane", sekil: "daire", desen: "kagit", yaziTipi: "serif",
    ipucu: "Kütüphane teması — insan ve toplum bilimleri",
    degiskenler: {
      "--bg": "#120c14", "--bg-2": "#17101a", "--yuzey": "#1c1420", "--yuzey-2": "#241a29",
      "--cizgi": "#3a2b42", "--kenar": "rgba(198,160,246,.16)",
      "--metin": "#f0e6f5", "--metin-2": "#c0a8cc", "--sonuk": "#8a7396",
      "--vurgu": "#c6a0f6", "--vurgu-2": "#f0b27a",
      "--iyi": "#6fcf97", "--uyari": "#f0b27a", "--kotu": "#eb6f92",
      "--mor": "#c6a0f6", "--pembe": "#eb6f92",
      "--vurgu-uzeri": "#1d1026",
      "--golge": "0 0 0 1px rgba(198,160,246,.08), 0 8px 28px rgba(60,20,80,.28)",
    },
  },

  /* ---------- Havacılık ve Uzay: gece göğü / uçuş paneli ---------- */
  havacilik: {
    ad: "Gökyüzü", sekil: "ucgen", desen: "izgara", yaziTipi: "mono",
    ipucu: "Gökyüzü teması — havacılık ve uzay bilimleri",
    degiskenler: {
      "--bg": "#060b16", "--bg-2": "#0a1020", "--yuzey": "#0d1628", "--yuzey-2": "#121e33",
      "--cizgi": "#1c2f4d", "--kenar": "rgba(122,178,255,.16)",
      "--metin": "#e6efff", "--metin-2": "#9fbde0", "--sonuk": "#6a86a8",
      "--vurgu": "#7ab2ff", "--vurgu-2": "#ffcf6b",
      "--iyi": "#5fd0a0", "--uyari": "#ffcf6b", "--kotu": "#ff6b8a",
      "--mor": "#9d8bff", "--pembe": "#ff8ab4",
      "--vurgu-uzeri": "#04121f",
      "--golge": "0 0 0 1px rgba(122,178,255,.08), 0 8px 28px rgba(10,25,60,.34)",
    },
  },

  /* ---------- Meslek Yüksekokulu: atölye ---------- */
  myo: {
    ad: "Atölye", sekil: "kare", desen: "izgara", yaziTipi: null,
    ipucu: "Atölye teması — meslek yüksekokulu",
    degiskenler: {
      "--bg": "#0d0f10", "--bg-2": "#131618", "--yuzey": "#181c1e", "--yuzey-2": "#202629",
      "--cizgi": "#303840", "--kenar": "rgba(255,176,32,.16)",
      "--metin": "#eef1f3", "--metin-2": "#b3bcc4", "--sonuk": "#7d8791",
      "--vurgu": "#ffb020", "--vurgu-2": "#4fc3f7",
      "--iyi": "#66bb6a", "--uyari": "#ffb020", "--kotu": "#ef5350",
      "--mor": "#9575cd", "--pembe": "#f06292",
      "--vurgu-uzeri": "#1a1205",
      "--golge": "0 0 0 1px rgba(255,176,32,.08), 0 8px 28px rgba(0,0,0,.40)",
    },
  },

  /* ---------- İTBF: piyasa terminali ---------- */
  itbf: {
    ad: "Piyasa", sekil: "kare", desen: "izgara", yaziTipi: "mono",
    ipucu: "Piyasa teması — iktisadi bilimler",
    degiskenler: {
      "--bg": "#04120c", "--bg-2": "#071a12", "--yuzey": "#0a2118", "--yuzey-2": "#0d2a1e",
      "--cizgi": "#14402c", "--kenar": "rgba(212,175,55,.18)",
      "--metin": "#eaf6ee", "--metin-2": "#93c4a8", "--sonuk": "#5c8a72",
      "--vurgu": "#d4af37", "--vurgu-2": "#2ec27e",
      "--iyi": "#3ddc84", "--uyari": "#e8b64c", "--kotu": "#ff5252",
      "--mor": "#a68fd6", "--pembe": "#d9789b",
      "--vurgu-uzeri": "#241c05",
      "--golge": "0 1px 2px rgba(0,0,0,.4), 0 10px 26px rgba(212,175,55,.08)",
    },
  },

  /* ---------- GSTF: atölye / eskiz ---------- */
  gstf: {
    ad: "Atölye", sekil: "elmas", desen: "eskiz", yaziTipi: null,
    ipucu: "Atölye teması — sanat ve tasarım",
    degiskenler: {
      "--bg": "#160d18", "--bg-2": "#1f1122", "--yuzey": "#26152a", "--yuzey-2": "#2f1a34",
      "--cizgi": "#432347", "--kenar": "rgba(255,138,190,.18)",
      "--metin": "#fdeaf5", "--metin-2": "#d8a8c4", "--sonuk": "#a1748f",
      "--vurgu": "#ff8abe", "--vurgu-2": "#ffc46b",
      "--iyi": "#7be0a6", "--uyari": "#ffc46b", "--kotu": "#ff6b8a",
      "--mor": "#b57bff", "--pembe": "#f2679f",
      "--vurgu-uzeri": "#3a0d22",
      "--golge": "0 1px 2px rgba(0,0,0,.35), 0 12px 30px rgba(255,138,190,.12)",
    },
  },

  /* ---------- Lisansüstü: akademi / kütüphane ---------- */
  lisansustu: {
    ad: "Akademi", sekil: "daire", desen: "kubbe", yaziTipi: "serif",
    ipucu: "Akademi teması — lisansüstü",
    degiskenler: {
      "--bg": "#0b0a18", "--bg-2": "#12102a", "--yuzey": "#181534", "--yuzey-2": "#1f1b42",
      "--cizgi": "#2e2a5c", "--kenar": "rgba(197,168,96,.18)",
      "--metin": "#efeaf8", "--metin-2": "#b3a9d4", "--sonuk": "#7d739e",
      "--vurgu": "#c5a860", "--vurgu-2": "#9b8bef",
      "--iyi": "#6fd6a0", "--uyari": "#e0b354", "--kotu": "#e8697f",
      "--mor": "#8f7bd8", "--pembe": "#e07fa8",
      "--vurgu-uzeri": "#1f1705",
      "--golge": "0 1px 2px rgba(0,0,0,.4), 0 12px 30px rgba(155,139,239,.12)",
    },
  },
};

/* --- SVG desenleri (harita arka planı) --- */
const DESENLER = {
  devre: `
    <pattern id="dsn" width="46" height="46" patternUnits="userSpaceOnUse">
      <path d="M0 23h14M32 23h14M23 0v14M23 32v14" stroke="#00e5ff" stroke-width=".7" opacity=".18" fill="none"/>
      <circle cx="23" cy="23" r="3.2" fill="none" stroke="#00e5ff" stroke-width=".7" opacity=".26"/>
      <circle cx="0" cy="0" r="1.4" fill="#00e5ff" opacity=".2"/>
      <circle cx="46" cy="46" r="1.4" fill="#00e5ff" opacity=".2"/>
    </pattern>`,
  kagit: `
    <pattern id="dsn" width="100%" height="26" patternUnits="userSpaceOnUse">
      <line x1="0" y1="25" x2="100%" y2="25" stroke="#7a5f3c" stroke-width=".6" opacity=".22"/>
    </pattern>`,
  izgara: `
    <pattern id="dsn" width="34" height="34" patternUnits="userSpaceOnUse">
      <path d="M34 0H0v34" fill="none" stroke="#d4af37" stroke-width=".5" opacity=".13"/>
    </pattern>`,
  eskiz: `
    <pattern id="dsn" width="30" height="30" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
      <line x1="0" y1="0" x2="0" y2="30" stroke="#ff8abe" stroke-width=".8" opacity=".13"/>
    </pattern>`,
  kubbe: `
    <pattern id="dsn" width="56" height="56" patternUnits="userSpaceOnUse">
      <path d="M0 56 A28 28 0 0 1 56 56" fill="none" stroke="#c5a860" stroke-width=".6" opacity=".16"/>
    </pattern>`,
};

/* --- aktif temayı uygula --- */
function temaUygula(fakulteId) {
  const t = TEMALAR[fakulteId] || TEMALAR.abu;
  const kok = document.documentElement;

  /* önceki tema değişkenlerini temizle */
  Object.values(TEMALAR).forEach(x =>
    Object.keys(x.degiskenler || {}).forEach(k => kok.style.removeProperty(k)));

  /* açık tema (gündüz modu) seçiliyken fakülte paletini uygulama —
     kullanıcının tercihi önceliklidir */
  if (kok.dataset.tema !== "acik" && t.degiskenler) {
    Object.entries(t.degiskenler).forEach(([k, v]) => kok.style.setProperty(k, v));
  }

  document.body.dataset.fak = fakulteId || "abu";
  document.body.dataset.yazi = t.yaziTipi || "sans";
  return t;
}

/* Gezinme zincirinden aktif fakülteyi bul.
   Prototipte düğüm kimliği ("mmf") doğrudan tema anahtarıydı. Üretimde
   ağaç backend'den kuruluyor ve kimlik "f-FEA" gibi kod taşıyor; hangi
   temanın kullanılacağı `data-adapter.js` tarafından düğüme yazılan
   `temaAnahtar` alanından okunur. Alan yoksa kimliğe düşülür. */
function aktifFakulte(zincir) {
  const f = (zincir || []).find(n => n.tur === "fakulte");
  if (!f) return "abu";
  return f.temaAnahtar || (TEMALAR[f.id] ? f.id : "abu");
}
