/* ABÜ KDS — 8 hub ve içlerindeki alt modüller.
   ==========================================================================
   ÜST DÜZEY HUB SAYISI 8'DE SABİTTİR.

   Yeni tasarımın 8 merceğinin karşılığı olmayan modüller yeni bir menü
   maddesi AÇMAZ; ilgili hub'ın içinde sekme olur. Böylece hem tek gezinme
   dili korunur hem de hiçbir ekran kaybolmaz.

   Her sekme, `lenses.js` içindeki bir MERCEĞE işaret eder. Mercekler
   yeni tasarımın bileşen sözlüğüyle (kutu / kart / cubuk / halka /
   cizgiGrafik / tablo) YENİDEN YAZILDI; eski ekran DOM'u kullanılmaz.
   Veri gerçek backend uçlarından gelir.

   İSTİSNA: `sistem` ekranları ve asistan tam sayfası hâlâ eski `VIEWS`
   kaydını kullanır (bkz. `view:` alanı). Bunlar form ve tablo ağırlıklı
   YÖNETİM ekranlarıdır; görsel taşımaları sıradaki adımdır.

   `sadeceUniversite: true` olan hub yalnızca ABÜ seviyesinde görünür —
   yeni tasarımın kuralı budur (Fiziksel Kaynaklar ve KPI kurum genelidir).
   ========================================================================== */

const HUBLAR = [
  {
    id: "genel", ad: "Genel Bakış", ikon: "◧", renk: "#4c8dff",
    ozet: "Kurumun bütününe tek bakış, riskler ve senaryolar",
    sekmeler: [
      { id: "pano", ad: "Yönetim Panosu", ikon: "◧" },
      { id: "uyari", ad: "Risk ve Erken Uyarı", ikon: "◭" },
      { id: "senaryo", ad: "Senaryo Analizi", ikon: "◑", view: "scenarios" },
      // Asistan hem sağ alttaki balonda hem burada tam sayfa olarak yaşar.
      // Balon hızlı soru içindir; tam sayfa mimari açıklamasını, model
      // durumunu ve analiz penceresini bir arada gösterir. İkisi AYNI
      // sohbeti paylaşır.
      { id: "asistan", ad: "Akıllı Asistan", ikon: "◍" },
    ],
  },
  {
    id: "ogrenci", ad: "Öğrenciler", ikon: "◍", renk: "#2ec4a6",
    ozet: "Öğrenci sayısı, doluluk, başarı ve mezuniyet",
    sekmeler: [
      { id: "analitik", ad: "Öğrenci Analitiği", ikon: "◔" },
      { id: "talep", ad: "Talep ve Yerleştirme", ikon: "◑" },
      { id: "basari", ad: "Akademik Başarı", ikon: "◈" },
    ],
  },
  {
    id: "personel", ad: "Akademik Personel", ikon: "◇", renk: "#9b7ff0",
    ozet: "Kadro, ders yükü, akademik üretim ve performans",
    sekmeler: [
      { id: "kadro", ad: "Akademik Personel", ikon: "◇" },
      { id: "yuk", ad: "Ders Yükü ve Yeterlilik", ikon: "◫" },
    ],
  },
  {
    id: "finans", ad: "Finans", ikon: "▦", renk: "#f2a33c",
    ozet: "Gelir, gider, bütçe dengesi ve birim kırılımı",
    sekmeler: [
      { id: "mali", ad: "Finansal Analiz", ikon: "▦" },
    ],
  },
  {
    id: "program", ad: "Programlar ve Müfredat", ikon: "▤", renk: "#e0679b",
    ozet: "Müfredat kataloğu, program envanteri ve sürdürülebilirlik",
    sekmeler: [
      // Müfredat ÖNCE gelir: 1205 gerçek ders kaydı bu hub'ın asıl
      // içeriğidir ve sürdürülebilirlik puanının arkasında kalmamalıdır.
      { id: "mufredat", ad: "Müfredat ve Dersler", ikon: "▤" },
      { id: "surdurulebilirlik", ad: "Program Sürdürülebilirliği", ikon: "◎" },
    ],
  },
  {
    id: "kiyas", ad: "Kıyaslama", ikon: "◆", renk: "#46b3e6",
    ozet: "Sıralama çerçeveleri ve kurum karşılaştırmaları",
    sekmeler: [
      { id: "degerlendirme", ad: "Değerlendirme ve Kıyaslama", ikon: "◆" },
    ],
  },
  {
    id: "fiziksel", ad: "Fiziksel Kaynaklar", ikon: "▥", renk: "#8fa3bf",
    ozet: "Derslik, laboratuvar ve mekân kapasitesi",
    sadeceUniversite: true,
    sekmeler: [
      { id: "kapasite", ad: "Fiziksel Kaynaklar", ikon: "▥" },
    ],
  },
  {
    id: "kpi", ad: "Performans", ikon: "◉", renk: "#2ec27e",
    ozet: "Kurumsal göstergeler ve dış paydaş katkısı",
    sadeceUniversite: true,
    sekmeler: [
      { id: "gosterge", ad: "Performans Göstergeleri", ikon: "◉" },
      { id: "katki", ad: "Sanayi ve Bölgesel Katkı", ikon: "◐" },
    ],
  },
];

/* ==========================================================================
   SİSTEM / YÖNETİM EKRANLARI
   --------------------------------------------------------------------------
   Bunlar analiz merceği DEĞİLDİR: bir bölümün altına sıkıştırmak yanlış
   olurdu (kullanıcı yönetimi bir bölümün özelliği değildir). Üst şeritteki
   sistem menüsünde dururlar — üst düzey hub sayısını artırmadan.
   ========================================================================== */
const SISTEM_EKRANLARI = [
  { rota: "yapi", ad: "Üniversite Yapısı", ikon: "▥", view: "structure",
    grup: "Yönetim" },
  { rota: "veri", ad: "Veri Aktarımı", ikon: "▽", view: "data-import",
    grup: "Veri yönetimi" },
  { rota: "kullanici", ad: "Kullanıcı ve Yetki", ikon: "◌", view: "users",
    grup: "Yönetim" },
];

/** Bir düğümde gösterilecek hub listesi. */
function hublariSuz(dugum) {
  return HUBLAR.filter(h => !h.sadeceUniversite || (dugum && dugum.tur === "universite"));
}

/** Bir sekmenin mercek anahtarı: "hub/sekme". */
const mercekAnahtari = (hubId, sekmeId) => `${hubId}/${sekmeId}`;

/** Hangi hub'ın hangi sekmesi bir ekranı barındırıyor? (test ve doğrulama) */
function ekraninYeri(viewAdi) {
  for (const hub of HUBLAR) {
    const sekme = hub.sekmeler.find(s => s.view === viewAdi);
    if (sekme) return { tur: "hub", hub: hub.id, sekme: sekme.id };
  }
  const sistem = SISTEM_EKRANLARI.find(s => s.view === viewAdi);
  if (sistem) return { tur: "sistem", rota: sistem.rota };
  return null;
}

/** Yeni tasarım diliyle YENİDEN YAZILMIŞ mercekler (test ve doğrulama). */
function tasinmisMercekler() {
  const out = [];
  HUBLAR.forEach(h => h.sekmeler.forEach(s => {
    if (MERCEK_CIZ[mercekAnahtari(h.id, s.id)]) out.push(mercekAnahtari(h.id, s.id));
  }));
  return out;
}
