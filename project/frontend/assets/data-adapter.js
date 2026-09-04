/* ABÜ KDS — gezinme ağacı veri katmanı.
   ==========================================================================
   BU DOSYA, YENİ TASARIMIN `data.js` DOSYASININ YERİNE GEÇER.

   Yeni tasarımda 21 bölüm, kampüs envanteri, KPI değerleri ve kıyas
   üniversiteleri `data.js` içinde SABİT yazılıydı — prototip olduğu için.
   Üretimde tek bir uydurma sayı kalmamalı; bu dosya aynı ağacı GERÇEK
   backend uçlarından kurar:

       /api/faculties               fakülteler
       /api/departments             bölümler
       /api/programs                programlar
       /api/student-analytics/by-faculty   öğrenci sayısı + doluluk
       /api/student-analytics/by-program   program kırılımı

   Türkçe görünen adlar `ref` (api.js) üzerinden gelir; çeviri tablosu
   burada TEKRARLANMAZ.

   NE SAKLANMAZ
   ------------
   Hiçbir metrik burada hesaplanmaz veya uydurulmaz. Bir değer backend'den
   gelmiyorsa `null` kalır ve arayüz "veri yok" gösterir. Yeni tasarımın
   "sayılar toplanır, yazılmaz" ilkesi korunur: fakülte toplamı, o
   fakültenin programlarının backend'den gelen sayılarının toplamıdır.
   ========================================================================== */

const agac = (() => {
  let kok = null;          // { id, ad, kisa, tur, cocuklar, metrik }
  let dizin = new Map();   // id -> { dugum, zincir }
  let yukleniyor = null;   // paylaşılan söz (promise)
  let hata = null;
  let idariBirimler = [];  // akademik AĞACIN DIŞINDA kalan birimler

  /* Fakülte renkleri: yeni tasarımın palet sırası. Renk BİRİM KİMLİĞİDİR,
     veri değil; koddan gelir, backend'den değil. */
  const PALET = ["#4c8dff", "#2ec4a6", "#9b7ff0", "#f2a33c", "#e0679b", "#46b3e6", "#8fa3bf"];

  const kisalt = (ad, kod) => kod || (ad || "").split(/\s+/).map(w => w[0]).join("").slice(0, 4).toUpperCase();

  /** Bir düğümün metriklerini çocuklarından TOPLAR. */
  function topla(dugum) {
    const cocuklar = dugum.cocuklar || [];
    if (!cocuklar.length) return dugum.metrik;

    cocuklar.forEach(topla);
    const say = alan => cocuklar.reduce((t, c) => {
      const v = c.metrik[alan];
      return v === null || v === undefined ? t : t + Number(v);
    }, 0);

    const kontenjan = say("kontenjan");
    const yerlesen = say("yerlesen");
    dugum.metrik = {
      ogrenciToplam: say("ogrenciToplam"),
      kontenjan,
      yerlesen,
      // Doluluk TÜREVDİR: alt birimlerin toplamından hesaplanır, ayrıca
      // saklanmaz. İki yerde tutulan aynı oran er ya da geç ayrışır.
      doluluk: kontenjan ? (yerlesen / kontenjan) * 100 : null,
      programSayisi: cocuklar.reduce(
        (t, c) => t + (c.tur === "program" ? 1 : c.metrik.programSayisi || 0), 0),
    };
    return dugum.metrik;
  }

  function dizinKur(dugum, zincir) {
    const yol = [...zincir, dugum];
    dizin.set(dugum.id, { dugum, zincir: yol });
    (dugum.cocuklar || []).forEach(c => dizinKur(c, yol));
  }

  /** Ağacı gerçek API'den kurar. Aynı anda birden çok çağrı gelirse tek istek. */
  function yukle() {
    if (yukleniyor) return yukleniyor;
    yukleniyor = (async () => {
      const [fakulteler, bolumler, programlar, programMetrik] = await Promise.all([
        ref.faculties(),
        ref.departments(),
        ref.programs(),
        // Doluluk ve öğrenci sayısı program seviyesinde geliyor; üst
        // seviyeler bundan toplanacak.
        api.get("/api/student-analytics/by-program").catch(() => []),
      ]);

      /* EŞLEŞTİRME KİMLİKLE YAPILIR, KODLA DEĞİL.
         `program_code` bir GÖRÜNTÜ alanıdır: 17 bölümde program kodu
         bölüm koduyla aynıdır ve kaynak dosyalarda yazım varyantları
         bulunur. Kod üzerinden eşleştirmek yanlış programın metriğini
         bir başkasına yazabilir. `program_id` gerçek varlık kimliğidir. */
      const metrikIndeks = new Map();
      (programMetrik || []).forEach(r => metrikIndeks.set(r.program_id, r));

      const programDugum = p => {
        const m = metrikIndeks.get(p.id) || {};
        return {
          // KİMLİK = tablo + GERÇEK DB id. Eskiden koddan üretiliyordu;
          // 17 bölümde program kodu bölüm koduyla AYNI olduğu için iki
          // farklı varlık aynı görünüyordu.
          id: "p-" + p.id, kod: p.code, ad: p.name, kisa: p.code,
          tur: "program", cocuklar: [],
          // GERÇEK VERİTABANI KİMLİĞİ. Kapsam süzgeci bunun üzerinden
          // çalışır; kod/ad eşleştirmesi yapılmaz.
          dbId: p.id,
          bolumId: p.department_id, fakulteId: p.faculty_id,
          // Alan adları backend şemasının kendisidir; yeniden adlandırma
          // yapılmaz, yalnızca eşlenir. Değer yoksa null kalır — 0 yazmak
          // "veri yok" ile "sıfır öğrenci"yi karıştırırdı.
          metrik: {
            /* ÖĞRENCİ SAYISI: `/api/programs` üzerindeki `student_count`.
               Bu alan, backend'in `student_count` servisinin yazdığı
               ÖSYM türevi sayının ta kendisidir — yani panonun KPI
               kartlarıyla AYNI kuraldır.

               Eskiden `student-analytics` modülünün `active_student_count`
               alanı okunuyordu. O alan, veritabanında öğrenci satırı
               varsa onları sayar; örnek veri yüklü bir kurulumda ÖSYM
               türevinden ayrışır ve aynı fakülte için ekranda iki farklı
               sayı belirir. Tek kural: `student_count`.

               `null` bilinçlidir — 0 yazmak "veri yok" ile "öğrencisi
               yok"u karıştırırdı. */
            ogrenciToplam: p.student_count ?? null,
            ogrenciKaynakYontem: p.student_count_source_method ?? null,
            kontenjan: m.quota ?? p.quota ?? null,
            yerlesen: m.enrolled_student_count ?? null,
            doluluk: m.occupancy_rate === undefined || m.occupancy_rate === null
              ? null : Number(m.occupancy_rate),
            programSayisi: 1,
          },
        };
      };

      const bolumDugum = (b, renk) => ({
        id: "b-" + b.id, kod: b.code, ad: b.name, kisa: kisalt(b.name, b.code),
        tur: "bolum", renk,
        dbId: b.id,
        fakulteId: b.faculty_id,
        cocuklar: programlar.filter(p => p.department_id === b.id).map(programDugum),
        metrik: {},
      });

      /* İDARİ BİRİMLER AKADEMİK AĞACA GİRMEZ.
         ------------------------------------------------------------------
         `faculties` tablosu üniversitenin bütün üst düzey birimlerini
         tutuyor: fakülte, meslek yüksekokulu, enstitü VE Rektörlük.
         Rektörlük'ü fakülte gibi çizmek üç şeyi bozuyordu: fakülte sayısı
         yanlış çıkıyor, akademik karşılaştırmaya idari birim giriyor ve
         öğrencisi olmadığı için doluluk grafiği çarpılıyordu.

         Tür bilgisi backend'den `unit_type` ile geliyor; burada ad
         tahmini YAPILMAZ. İdari birimler ayrı bir listede tutulur ve
         sistem/yönetim ekranlarında gösterilir. */
      const akademikBirimler = fakulteler.filter(f => f.is_academic !== false);
      idariBirimler = fakulteler
        .filter(f => f.is_academic === false)
        .map(f => ({
          id: "i-" + f.id, kod: f.code, ad: f.name, dbId: f.id,
          tur: "idari", birimTuru: f.unit_type,
          birimTuruAdi: f.unit_type_label || "İdari Birim",
        }));

      const fakulteDugumler = akademikBirimler.map((f, i) => {
        const renk = PALET[i % PALET.length];
        return {
          id: "f-" + f.id, kod: f.code, ad: f.name, kisa: kisalt(f.name, f.code),
          tur: "fakulte", renk, temaAnahtar: temaAnahtariBul(f.code, f.name),
          dbId: f.id,
          birimTuru: f.unit_type || "FACULTY",
          birimTuruAdi: f.unit_type_label || "Fakülte",
          cocuklar: bolumler.filter(b => b.faculty_id === f.id).map(b => bolumDugum(b, renk)),
          metrik: {},
        };
      });

      kok = {
        id: "abu", ad: "Ankara Bilim Üniversitesi", kisa: "ABÜ",
        tur: "universite", renk: "#4c8dff", cocuklar: fakulteDugumler, metrik: {},
      };
      topla(kok);

      /* ==================================================================
         ÜNİVERSİTE DÜZEYİNDE ÖĞRENCİ SAYISI: YÖK KAYITLI SAYISI
         ------------------------------------------------------------------
         `topla()` kökün öğrenci sayısını çocuklarından toplar; bu toplam
         ÖSYM yerleştirmelerinden türetilmiştir (son ≤4 kohort) ve 3348
         eder. Oysa kurumun FİİLEN KAYITLI öğrenci sayısı YÖK'e göre
         3626'dır: aradaki fark lisansüstü öğrenciler, yatay geçiş ve DGS
         ile gelenlerdir.

         Üniversite başlığında ve merkez düğümde kurumun GERÇEK büyüklüğü
         görünmelidir. Bu yüzden YALNIZCA KÖK düğümün sayısı YÖK
         rakamıyla değiştirilir.

         ALT SEVİYELER DEĞİŞMEZ. YÖK sayısının fakülte/bölüm/program
         kırılımı YOKTUR; üniversite toplamını alt birimlere paylaştırmak
         uydurma olurdu. Alt düğümler ÖSYM türevi sayılarını korur.

         Uç çağrısı başarısız olursa ağaç yine kurulur: kök ÖSYM
         toplamıyla kalır ve `ogrenciKaynak` bunu söyler. Bir gösterge
         gelmedi diye gezinme ağacı çökmez. */
      try {
        const kayitli = await api.get(
          "/api/decision-analytics/enrolled-headcount");
        if (kayitli && kayitli.available
            && Number.isFinite(Number(kayitli.student_count))) {
          kok.metrik.ogrenciYks = kok.metrik.ogrenciToplam;   // izlenebilirlik
          kok.metrik.ogrenciToplam = Number(kayitli.student_count);
          kok.metrik.ogrenciKaynak = "yok_kayitli";
          kok.metrik.ogrenciDonem = kayitli.latest_academic_year || null;
        } else {
          kok.metrik.ogrenciKaynak = "yks_kohort";
        }
      } catch {
        kok.metrik.ogrenciKaynak = "yks_kohort";
      }

      dizin = new Map();
      dizinKur(kok, []);
      return kok;
    })().catch(err => {
      hata = err;
      // Ağaç kurulamazsa uygulama boş ekranla kalmasın: yalnızca kök düğüm
      // ve açık bir hata mesajı gösterilir.
      kok = {
        id: "abu", ad: "Ankara Bilim Üniversitesi", kisa: "ABÜ",
        tur: "universite", renk: "#4c8dff", cocuklar: [],
        metrik: { ogrenciToplam: null, doluluk: null, programSayisi: 0 },
      };
      dizin = new Map([["abu", { dugum: kok, zincir: [kok] }]]);
      throw err;
    });
    return yukleniyor;
  }

  /* Fakülte kodundan tema anahtarı. Yeni tasarımın 6 teması kodla değil
     ANLAMLA eşleşir; kod farklıysa ada bakılır. Eşleşme yoksa kurumsal. */
  function temaAnahtariBul(kod, ad) {
    const metin = `${kod || ""} ${ad || ""}`.toLocaleLowerCase("tr");
    /* Havacılık kuralı mühendislik kuralından ÖNCE gelir: bu fakültenin
       altında "Uçak Mühendisliği" bölümü var, sonra gelirse fakülte
       yanlışlıkla mühendislik temasına düşer. */
    if (/havacılık|uzay|aviation|aerospace/.test(metin)) return "havacilik";
    if (/meslek yüksekokulu|myo|vocational/.test(metin)) return "myo";
    if (/insan ve toplum|sosyal bilim|social|humanities/.test(metin)) return "insan";
    if (/mühendis|engineer|mimar|architect|fea|mmf/.test(metin)) return "mmf";
    if (/hukuk|law/.test(metin)) return "hukuk";
    if (/iktisad|işletme|idari|business|econom|itbf|fear/.test(metin)) return "itbf";
    if (/sanat|tasarım|design|art|gstf/.test(metin)) return "gstf";
    if (/lisansüstü|enstitü|graduate|institute/.test(metin)) return "lisansustu";
    return "abu";
  }

  return {
    yukle,
    get hata() { return hata; },
    get hazir() { return !!kok; },
    get kok() { return kok; },
    bul(id) { return dizin.get(id) || (kok && id === "abu" ? { dugum: kok, zincir: [kok] } : null); },
    /* ======================================================================
       GEZİNİLEBİLİR ALT BİRİMLER — ad değil YAPI kararı
       ----------------------------------------------------------------------
       Kural: bir bölüm, TEK bir programa sahipse o program ayrı bir
       gezinme düğümü DEĞİLDİR. Bölüm zaten o programın kendisidir;
       ayrı düğüm göstermek kullanıcıyı aynı veriye iki kez götürür.

       Bu bir AD karşılaştırması değil, gerçek satır SAYISI kararıdır:
       `academic_programs` içinde o `department_id` ile kaç satır var?
         · 1 satır  → bölüm YAPRAKTIR, program düğümü çizilmez
         · >1 satır → programlar gerçek alt kırılımdır, hepsi çizilir

       Gerçek veride 22 bölümün 1, 4 bölümün 2–5 programı var; yani
       Bilgisayar Teknolojileri altında 4 program gezinilebilir kalır,
       Bilgisayar Mühendisliği ise yaprak olur.

       Ek güvenlik: hiçbir çocuk, ebeveyniyle AYNI KİMLİĞE sahip olamaz.
       Kimlik artık gerçek DB id'sidir, dolayısıyla bu kontrol ad
       benzerliğine değil varlık kimliğine bakar.
       ====================================================================== */
    gercekCocuklar(dugum) {
      const cocuklar = (dugum && dugum.cocuklar) || [];
      const suzulmus = cocuklar.filter(c => c.id !== dugum.id);
      if (dugum.tur === "bolum" && suzulmus.length === 1) return [];
      return suzulmus;
    },

    /** Bir düğümün altındaki bütün yaprakları döndürür. */
    yapraklar(dugum) {
      const out = [];
      (function gez(d) {
        if (!d.cocuklar || !d.cocuklar.length) out.push(d);
        else d.cocuklar.forEach(gez);
      })(dugum);
      return out;
    },
    /** Akademik ağacın DIŞINDA kalan idari birimler (Rektörlük vb.). */
    get idari() { return idariBirimler; },

    /* ======================================================================
       KAPSAM SÖZLÜĞÜ — API filtre parametreleri
       ----------------------------------------------------------------------
       ÖNEMLİ HATA DÜZELTMESİ
       Burası eskiden `{faculty, department, program}` biçiminde KOD
       gönderiyordu. Uçlar ise `faculty_id / department_id /
       academic_program_id` bekliyor ve FastAPI tanımadığı sorgu
       parametresini SESSİZCE ATIYOR. Sonuç: hiçbir kapsam filtresi
       uygulanmıyor, YAZMUH sayfasında kardeş programlar görünüyordu.

       Artık gerçek veritabanı kimlikleri gönderiliyor. Kimliği olmayan
       bir düğüm için parametre EKLENMEZ; yanlış bir id uydurmaktansa
       kapsamsız (üniversite) davranmak daha dürüsttür ve testte görünür.

       Not: en dar seviye tek başına yeterlidir (program verilirse backend
       bölüm/fakülteyi kendisi türetir), ama üçü de gönderilir; backend
       `resolve()` tutarsız kombinasyonu 400 ile reddederek arayüz
       hatalarını sessiz veri hatasına dönüşmeden yakalar.
       ====================================================================== */
    kapsam(id) {
      const bulunan = this.bul(id);
      if (!bulunan) return {};
      const k = {};
      bulunan.zincir.forEach(n => {
        if (n.dbId === undefined || n.dbId === null) return;
        if (n.tur === "fakulte") k.faculty_id = n.dbId;
        if (n.tur === "bolum") k.department_id = n.dbId;
        if (n.tur === "program") k.academic_program_id = n.dbId;
      });
      return k;
    },

    /** Seçili düğümün kapsam seviyesi — ekranların karar vermesi için. */
    kapsamSeviyesi(id) {
      const bulunan = this.bul(id);
      if (!bulunan) return "university";
      const t = bulunan.dugum.tur;
      return t === "program" ? "program"
        : t === "bolum" ? "department"
        : t === "fakulte" ? "faculty" : "university";
    },
  };
})();

/* NOT: `aktifFakulte()` themes.js içinde tanımlıdır; burada TEKRAR
   TANIMLANMAZ — iki kez tanımlanan bir global sessizce birbirini ezer.
   Bu dosya yalnızca düğümlere `temaAnahtar` alanını koyar; hangi temanın
   uygulanacağına themes.js karar verir. */

/* Sayı biçimleri — yeni tasarımın yazımı, `fmt` (api.js) üzerinden.
   Ayrı bir biçimlendirme tablosu tutulmuyor; ikisi ayrışırsa aynı sayı
   iki ekranda farklı görünür. */
const fmtSayi = n => (n === null || n === undefined ? "—" : fmt.int(n));
const fmtYuzde = (n, d = 1) => (n === null || n === undefined ? "—" : fmt.pct(n, d));
const fmtOndalik = (n, d = 1) => (n === null || n === undefined ? "—" : fmt.dec(n, d));
