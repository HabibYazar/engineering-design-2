/* ABÜ KDS — ANALİZ MERCEKLERİ (hub içerikleri).
   ==========================================================================
   Bu dosya, prototipin `lenses.js` dosyasının ÜRETİM KARŞILIĞIDIR.

   GÖRSEL: tamamen yeni tasarımın dili — `kutu`, `kart`, `izgara.k2/k3/k32`,
   `cubuklar`, `cizgiGrafik`, `halka`, `etiket-c`, `tablo-sar`. Hiçbir eski
   ekran bileşeni (tile / donut-row / hbar / view-head) kullanılmaz.

   VERİ: tamamen mevcut backend — prototipin `BOLUMLER`, `KAMPUS`, `KPILER`
   sabitleri yerine gerçek uç noktalar. Uydurma sayı yok; değer gelmezse
   "veri yok" görünür.

   KAPSAM: her mercek seçili birime göre süzülür. `agac.kapsam(id)` seçili
   düğümün faculty/department/program kodlarını verir; uç noktalar bu
   parametreleri zaten kabul ediyor.
   ========================================================================== */

/* ==========================================================================
   KAPSAM — HER İSTEĞE GEÇİRİLİR
   --------------------------------------------------------------------------
   `agac.kapsam(id)` seçili düğümün GERÇEK veritabanı kimliklerini verir
   (`faculty_id / department_id / academic_program_id`). Daha önce burada
   kod gönderiliyordu ve backend bu parametreleri tanımadığı için sessizce
   atıyordu — bir programa inildiğinde kardeş programlar görünmeye devam
   ediyordu.

   KURAL: bu dosyadaki HER `api.get` çağrısı kapsamı taşır. Kapsam
   taşımayan tek istisna, kapsamdan bağımsız REFERANS listeleridir
   (akademik yıl listesi, sıralama çerçeveleri, kıyas kurumları) ve
   bunlar ayrıca yorumla işaretlenmiştir.
   ========================================================================== */
function kapsamParam(dugumId, ekstra = {}) {
  return { ...agac.kapsam(dugumId), ...ekstra };
}

/* Değeri olmayan göstergeyi HİÇ ÇİZME.
   "0 atıf" ile "atıf verisi yok" aynı görünürse yanlış karar alınır.
   Kaynakta karşılığı olmayan alanlar (GPA, uluslararası oran, mezuniyet)
   gerçek veride 0 gelir; bu kartlar basılmaz. */
const varsaKutu = (baslik, deger, alt, tur) =>
  (deger === null || deger === undefined || deger === "—" || deger === "0"
    || deger === 0)
    ? "" : kutu(baslik, deger, alt, tur);

/* Sayısal bir alanın GERÇEKTEN ölçülüp ölçülmediği. Gerçek veride
   öğrenci kaydı olmadığı için GPA/uluslararası/mezuniyet 0 gelir. */
const olculdu = v => v !== null && v !== undefined && Number(v) > 0;

/* Yetkili olmayan analitik değeri kaynağıyla birlikte göster. Etiket
   yalnızca API'nin provenance alanından gelir; sentetik değer resmî
   kurum/YÖK/OSYM kaydı gibi sunulmaz. */
const yonetilenKaynakNotu = veri => {
  if (!veri || !veri.source_type) return "";
  const etiket = veri.provenance || veri.source_label || veri.source_type;
  const sentetik = veri.is_synthetic
    && !String(etiket).toUpperCase().startsWith("SYNTHETIC_GENERATED")
    ? "SYNTHETIC_GENERATED · " : "";
  const dosya = veri.filename ? ` · ${veri.filename}` : "";
  return `<div class="not">Kaynak: ${fmt.esc(sentetik + etiket + dosya)}</div>`;
};

/* Seçili kapsamın seviyesi: "university" | "faculty" | "department" | "program" */
const kapsamSeviye = dugumId => agac.kapsamSeviyesi(dugumId);

/* ==========================================================================
   YÖNETİM GÖSTERGESİ YARDIMCILARI
   --------------------------------------------------------------------------
   Üç ekran (pano, öğrenci analitiği, karşılaştırma) aynı sayıları aynı
   biçimde göstermek zorunda. Biçimlendirme tek yerde durur; iki ekranda
   farklı yuvarlanan bir oran, "veriler tutmuyor" izlenimi yaratır.
   ========================================================================== */

/* Yönlü değişim: artı/eksi işareti ve iyi/kötü rengi birlikte.
   `iyiYon = +1` büyümenin iyi olduğu göstergeler (yerleşen, doluluk),
   `-1` küçülmenin iyi olduğu göstergeler (başarı sırası) içindir. */
const degisimKutusu = (baslik, deger, birim = "%", iyiYon = 1, alt = "") => {
  if (deger === null || deger === undefined || !Number.isFinite(Number(deger))) return "";
  const v = Number(deger);
  const isaret = v > 0 ? "+" : v < 0 ? "−" : "";
  const metin = isaret + fmt.dec(Math.abs(v), birim === "%" ? 1 : 0)
    + (birim === "%" ? "%" : birim ? " " + birim : "");
  const tur = v === 0 ? "" : (v * iyiYon > 0 ? "iyi" : "kotu");
  return kutu(baslik, metin, alt, tur);
};

/* Ölçülmüş sayısal gösterge kartı. `null`/tanımsız kart BASILMAZ;
   0 ise yalnızca `sifirGecerli` işaretlendiğinde basılır — "0 aşırı
   yüklü akademisyen" gerçek bir cevaptır, "0 GPA" değildir. */
const olcumKutusu = (baslik, deger, alt = "", tur = "", sifirGecerli = false) => {
  if (deger === null || deger === undefined) return "";
  const v = Number(deger);
  if (!Number.isFinite(v)) return "";
  if (v === 0 && !sifirGecerli) return "";
  return kutu(baslik, typeof deger === "number" && !Number.isInteger(v)
    ? fmt.dec(v, 2) : fmtSayi(v), alt, tur);
};

/* Talep baskısı durumunun görsel karşılığı. */
const baskiTuru = durum => durum === "talep_fazlasi" ? "iyi"
  : durum === "dengeli" ? "iyi"
  : durum === "gevsek" ? "uyari" : "kotu";
const baskiAdi = durum => ({
  talep_fazlasi: "Kontenjan doldu", dengeli: "Dengeli",
  gevsek: "Boşluk var", talep_yetersiz: "Talep yetersiz",
}[durum] || "—");

/* Uyarı önem derecesi → çip türü. */
const uyariTuru = s => s === "kritik" ? "kotu" : s === "yuksek" ? "uyari" : "bilgi";

/* Bir alt seviye birim karşılaştırma tablosu — kapsam neyse onun ALTI.
   Satır tıklanabilir değildir: kırılım satırları fakülte/bölüm/program
   olabilir ve hepsinin gezinme kimliği aynı biçimde kurulamaz. */
function kirilimTablosu(kirilim) {
  if (!kirilim || !kirilim.rows || !kirilim.rows.length) {
    return bosDurum("Bu kapsamda alt birim kırılımı yok.");
  }
  return tablo(
    ["Birim", "Öğrenci", "Kontenjan", "Yerleşen", "Doluluk",
     "Akademisyen", "Öğr./Akad.", "Ders", "Durum"],
    kirilim.rows.map(r => {
      const tur = dolulukTur(r.occupancy_percent);
      return [
        fmt.esc(r.name),
        fmtSayi(r.student_count), fmtSayi(r.quota), fmtSayi(r.placed_students),
        { icerik: fmtYuzde(r.occupancy_percent, 1),
          sinif: tur === "kotu" ? "kotu" : tur === "iyi" ? "iyi" : "" },
        fmtSayi(r.academic_staff_count),
        fmtOndalik(r.students_per_academic_staff, 1),
        fmtSayi(r.curriculum_course_count),
        { icerik: etiketC(tur, tur === "iyi" ? "Sağlıklı"
            : tur === "uyari" ? "İzlemede" : tur === "kotu" ? "Riskli" : "Veri yok"),
          stil: "text-align:left" },
      ];
    })
  );
}

/* Akademik yıl seçimi — mercek filtrelerinde tekrar tekrar kullanılıyor. */
let YIL_LISTESI = null;
async function yillar() {
  if (!YIL_LISTESI) {
    YIL_LISTESI = await ref.academicYears().catch(() => []);
  }
  return YIL_LISTESI;
}
const varsayilanYil = () => (YIL_LISTESI && YIL_LISTESI.length ? YIL_LISTESI[0] : "2025-2026");

/* NOT: Ağaç düğümünün `metrik` alanından çizilen eski "Alt birim
   karşılaştırması" KALDIRILDI. Karşılaştırma artık tek yerden gelir:
   backend'in gerçek hiyerarşi kimlikleriyle kurduğu kırılım
   (`/api/decision-analytics/child-breakdown` → `kirilimTablosu`).
   İki ayrı karşılaştırma yolu tutmak, ikisinin er ya da geç farklı
   sayı göstermesi demekti. */

/* ==========================================================================
   MERCEK KAYDI
   --------------------------------------------------------------------------
   Her sekme: { id, ad, ikon, filtreler(dugum), ciz(dugum, F) }
   `ciz` iskelet HTML döndürür; veri `veri()` ile asenkron doldurulur.
   ========================================================================== */
const MERCEK_CIZ = {};

/* ---------------- Genel Bakış › Yönetim Panosu ----------------
   YÖNETİCİ PANOSU. Her kart "bu ekrandan hangi kararı alırım?"
   sorusuna cevap verir:

     kadro yeterli mi        → öğrenci/akademisyen, 100 öğrenciye akademisyen
     yük dengeli mi          → ortalama/ortanca yük, aşırı yüklü kişi, yoğunlaşma
     öğretim kaç kişiye bağlı→ fiilen ders veren akademisyen, yoğunlaşma payı
     talep ne yönde          → 4 yıllık kontenjan/yerleşen, doluluk, yön
     nerede zayıfım          → BİR ALT seviyedeki birimlerin karşılaştırması
     neye bakmalıyım         → gerçek veriden türetilen uyarılar

   Kırılım seviyeye göre backend'de belirlenir: üniversitede fakülteler,
   fakültede bölümler, bölümde programlar. Program yaprağında kırılım
   yoktur; birimin kendi operasyonel sağlığı gösterilir.

   ÖLÇÜLMEYEN GÖSTERGE KARTI BASILMAZ (bkz. `olcumKutusu`). */
MERCEK_CIZ["genel/pano"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id);

    setTimeout(() => {
      /* TEK İSTEK: bütün göstergeler aynı kapsamdan gelsin diye. İki
         ayrı istek arasında kapsam değişirse ekranda karışık veri olur. */
      veri("ypPano",
        () => api.get("/api/decision-analytics/executive-overview", p),
        (o, kap) => {
          const k = o.staffing, y = o.teaching_load, m = o.curriculum_load;
          const g = o.student_body, yog = o.course_concentration;

          /* Aşırı yüklü akademisyen = en üst bant (21+ saat). Eşik
             iddiası yapılmaz; bandın kendisi etiketiyle gösterilir. */
          const ustBant = (y.bands || []).find(b => b.max_hours === null);
          const asiriYuklu = ustBant ? ustBant.staff_count : null;

          const kartlar = kutular(
            olcumKutusu("Öğrenci", k.student_count, "kapsamda") +
            olcumKutusu("Akademisyen", k.academic_staff_count, "aktif kadro") +
            olcumKutusu("Fiilen ders veren", k.active_teaching_staff_count,
              k.academic_staff_count
                ? `${fmtSayi(k.academic_staff_count)} kadronun içinde` : "") +
            olcumKutusu("Öğrenci / akademisyen", k.students_per_academic_staff,
              "kadro geneli",
              Number(k.students_per_academic_staff) >= 40 ? "kotu"
                : Number(k.students_per_academic_staff) >= 25 ? "uyari" : "iyi") +
            olcumKutusu("Öğrenci / ders veren", k.students_per_active_teaching_staff,
              "fiilen öğretim yapan") +
            olcumKutusu("100 öğrenciye akademisyen", k.academics_per_100_students) +
            olcumKutusu("Ortalama ders yükü", y.average_hours, "haftalık saat") +
            olcumKutusu("Ortanca ders yükü", y.median_hours, "haftalık saat") +
            olcumKutusu("Aşırı yüklü", asiriYuklu,
              ustBant ? ustBant.label : "", "uyari", true) +
            (y.top20_percent_share !== null && y.top20_percent_share !== undefined
              ? kutu("Yük yoğunlaşması", fmtYuzde(y.top20_percent_share, 0),
                  `en yüklü ${fmtSayi(y.top20_percent_staff_count)} kişide`,
                  y.top20_percent_share >= 50 ? "uyari" : "") : "") +
            olcumKutusu("Müfredat dersi", m.curriculum_course_count, "tekilleştirilmiş") +
            olcumKutusu("Ders / ders veren akademisyen",
              m.courses_per_academic_staff && k.active_teaching_staff_count
                ? Math.round(m.curriculum_course_count
                    / k.active_teaching_staff_count * 100) / 100 : null) +
            olcumKutusu("Kontenjan", g.latest_quota,
              g.latest_placement_year ? `${g.latest_placement_year} yerleştirmesi` : "") +
            olcumKutusu("Yerleşen", g.latest_placed_students,
              g.latest_placement_year ? `${g.latest_placement_year} yerleştirmesi` : "") +
            (g.latest_occupancy_percent !== null
              && g.latest_occupancy_percent !== undefined
              ? kutu("Doluluk", fmtYuzde(g.latest_occupancy_percent, 1),
                  baskiAdi(g.demand_pressure && g.demand_pressure.status),
                  dolulukTur(g.latest_occupancy_percent)) : "") +
            degisimKutusu("Yerleşen değişimi", g.intake_change_percent, "%", 1,
              "bir önceki kohorta göre") +
            (g.demand_momentum && g.demand_momentum.available
              ? kutu("Talep yönü", fmt.esc(g.demand_momentum.direction),
                  `${g.demand_momentum.measured_signal_count} sinyal`,
                  g.demand_momentum.direction === "artıyor" ? "iyi"
                    : g.demand_momentum.direction === "azalıyor" ? "kotu" : "") : "") +
            olcumKutusu("Akademisyen başına yayın",
              k.average_publications_per_academic)
          );

          /* --- kırılım / yaprak sağlığı --- */
          const kir = o.breakdown || {};
          const kirBaslik = kir.child_kind === "faculty" ? "Fakülte karşılaştırması"
            : kir.child_kind === "department" ? "Bölüm karşılaştırması"
            : kir.child_kind === "program" ? "Program karşılaştırması"
            : "Birim sağlığı";
          const kirGovde = kir.is_leaf
            ? (o.unit ? tablo(["Gösterge", "Değer"], [
                ["Öğrenci", fmtSayi(o.unit.student_count)],
                ["Kontenjan", fmtSayi(o.unit.quota)],
                ["Yerleşen", fmtSayi(o.unit.placed_students)],
                ["Doluluk", fmtYuzde(o.unit.occupancy_percent, 1)],
                ["Akademisyen", fmtSayi(o.unit.academic_staff_count)],
                ["Fiilen ders veren", fmtSayi(o.unit.active_teaching_staff_count)],
                ["Öğrenci / akademisyen", fmtOndalik(o.unit.students_per_academic_staff, 1)],
                ["Müfredat dersi", fmtSayi(o.unit.curriculum_course_count)],
                ["Cari dönem ders kaydı", fmtSayi(o.unit.current_course_records)],
              ]) : bosDurum("Birim için ölçüm yok."))
            : kirilimTablosu(kir);

          /* --- unvan karması --- */
          const unvan = (o.title_distribution || []).length
            ? cubuklar(o.title_distribution.slice(0, 8).map(t =>
                [t.title, t.staff_count,
                 `${fmtSayi(t.staff_count)} · ${fmtYuzde(t.share_percent, 0)}`]))
            : bosDurum("Unvan verisi yok.");

          /* --- ders yükü bantları --- */
          const bantlar = (y.bands || []).some(b => b.staff_count)
            ? cubuklar(y.bands.map(b => [b.label, b.staff_count, fmtSayi(b.staff_count)]))
            : bosDurum("Ders yükü verisi yok.");

          /* --- 4 yıllık talep --- */
          const yillar = (g.cohorts || []);
          const talepGrafik = yillar.length > 1
            ? cizgiGrafik(yillar.map(c => c.placement_year), [
                { ad: "Kontenjan", veri: yillar.map(c => c.quota), renk: "var(--vurgu-2)" },
                { ad: "Yerleşen", veri: yillar.map(c => c.placed_students),
                  renk: "var(--vurgu)", alan: true },
              ], { yb: v => fmt.int(Math.round(v)) })
            : bosDurum("Trend için en az iki yıllık yerleştirme verisi gerekir.");

          /* --- uyarılar --- */
          const uyarilar = (o.warnings || []).length
            ? tablo(["Önem", "Bulgu", "Ölçülen", "Dayanak"],
                o.warnings.map(u => [
                  { icerik: etiketC(uyariTuru(u.severity), u.severity),
                    stil: "text-align:left" },
                  fmt.esc(u.title),
                  fmtOndalik(u.measured_value, 1),
                  fmt.esc(u.explanation),
                ]))
            : bosDurum("Bu kapsamda türetilmiş operasyonel uyarı yok.");

          /* --- yayın üretkenliği (yalnızca ölçüldüyse) --- */
          const yayin = (o.publication_productivity || [])
            .filter(r => r.publications_per_academic);
          const yayinGovde = yayin.length
            ? cubuklar(yayin.slice(0, 8).map(r =>
                [r.department_name, r.publications_per_academic,
                 fmtOndalik(r.publications_per_academic, 1)]))
            : "";

          return kartlar +
            kart(kirBaslik,
              kir.is_leaf
                ? "Bu birimin altında ayrı bir kırılım yok; kendi göstergeleri."
                : "Öğrenci, kontenjan, kadro ve müfredat aynı satırda — " +
                  "hangi birim hangi göstergede zayıf.",
              kirGovde, { stil: "margin-top:14px" }) +
            `<div class="izgara k2" style="margin-top:14px">` +
              kart("Talep trendi",
                "Son yerleştirme yıllarında kontenjan ve yerleşen öğrenci.",
                talepGrafik) +
              kart("Ders yükü dağılımı",
                "Haftalık saat bantlarına göre akademisyen sayısı.", bantlar) +
            `</div>` +
            `<div class="izgara k2" style="margin-top:14px">` +
              kart("Kadro unvan karması",
                "Kadro yapısının kıdem dağılımı.", unvan) +
              kart("Operasyonel uyarılar",
                "Yalnızca ölçülmüş göstergelerden türetilir.", uyarilar) +
            `</div>` +
            (yayinGovde
              ? kart("Akademisyen başına yayın",
                  "Bölüm bazında üretkenlik.", yayinGovde,
                  { stil: "margin-top:14px" })
              : "");
        }, { iskelet: 4 });
    }, 0);

    return `<div id="ypPano">${iskelet(5)}</div>`;
  },
};

/* ---------------- Genel Bakış › Risk ve Erken Uyarı ---------------- */
MERCEK_CIZ["genel/uyari"] = {
  filtreler: () => [{
    id: "severity", tip: "cip", varsayilan: "hepsi", secenekler: [
      { ad: "Hepsi", deger: "hepsi" }, { ad: "Kritik", deger: "kritik" },
      { ad: "Yüksek", deger: "yuksek" }, { ad: "Orta", deger: "orta" },
    ],
  }],
  ciz(dugum, F = {}) {
    setTimeout(() => {
      veri("euOzet",
        () => api.get("/api/early-warning/summary", kapsamParam(dugum.id)),
        s => {
          const sev = s.by_severity || {};
          return kutular(
            kutu("Açık uyarı", fmtSayi(s.total_alerts), "tüm kapsamlar") +
            kutu("Kritik", fmtSayi(sev.kritik || 0), "acil müdahale",
              (sev.kritik || 0) > 0 ? "kotu" : "iyi") +
            kutu("Yüksek", fmtSayi(sev.yuksek || 0), "izlemede",
              (sev.yuksek || 0) > 0 ? "uyari" : "") +
            kutu("Orta", fmtSayi(sev.orta || 0), "planlı takip")
          );
        }, { iskelet: 2 });

      veri("euListe",
        () => api.get("/api/early-warning/alerts", kapsamParam(dugum.id,
          F.severity && F.severity !== "hepsi" ? { severity: F.severity } : {})),
        rows => tablo(
          ["Kapsam", "Kural", "Önem", "Ölçülen", "Eşik", "Durum"],
          rows.slice(0, 60).map(r => [
            fmt.esc(r.scope_code || "—"),
            fmt.esc(r.rule_name || r.message || "—"),
            { icerik: etiketC(
                r.severity === "kritik" ? "kotu" : r.severity === "yuksek" ? "uyari" : "bilgi",
                r.severity || "orta"), stil: "text-align:left" },
            fmtOndalik(r.measured_value, 2),
            fmtOndalik(r.threshold_value, 2),
            { icerik: etiketC(r.is_resolved ? "iyi" : "notr",
                r.is_resolved ? "Kapandı" : "Açık"), stil: "text-align:left" },
          ])
        ), { bos: "Bu önem derecesinde açık uyarı yok." });
    }, 0);

    return `<div id="euOzet">${iskelet(2)}</div>` +
      kart("Açık uyarılar", "Kural motorunun ürettiği uyarılar; eşik ve ölçülen değer birlikte.",
        `<div id="euListe">${iskelet(6)}</div>`);
  },
};

/* ---------------- Öğrenciler › Öğrenci Analitiği ----------------
   Elimizdeki gerçek öğrenci verisi ÖSYM yerleştirmesidir; bireysel
   öğrenci kaydı YOKTUR. Bu yüzden bu ekran GPA, mezuniyet, terk,
   uluslararası ve burslu oranı GÖSTERMEZ — o sayılar ölçülmediği için
   hep 0 gelirdi ve "ölçtük, sıfır çıktı" yanılgısı yaratırdı.

   Bunun yerine yönetimin gerçekten karar aldığı büyüklükler gösterilir:
   öğrenci gövdesi, kohort dağılımı, kontenjan/yerleşen/doluluk, bunların
   yıllık değişimi, talep baskısı ve kadroyla ilişkisi. Karşılaştırma
   kapsamın BİR ALTINDAKİ birimlerle yapılır. */
MERCEK_CIZ["ogrenci/analitik"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      veri("ogGovde",
        () => api.get("/api/decision-analytics/student-body", p),
        g => {
          const b = g.demand_pressure || {};
          return kutular(
            olcumKutusu("Öğrenci sayısı", g.student_count,
              g.cohort_count ? `${fmtSayi(g.cohort_count)} kohort toplamı` : "") +
            olcumKutusu("Kontenjan", g.latest_quota,
              g.latest_placement_year ? `${g.latest_placement_year} yerleştirmesi` : "") +
            olcumKutusu("Yerleşen", g.latest_placed_students,
              g.latest_placement_year ? `${g.latest_placement_year} yerleştirmesi` : "") +
            (g.latest_occupancy_percent !== null
              && g.latest_occupancy_percent !== undefined
              ? kutu("Doluluk", fmtYuzde(g.latest_occupancy_percent, 1),
                  baskiAdi(b.status), dolulukTur(g.latest_occupancy_percent)) : "") +
            olcumKutusu("Boş kalan kontenjan", b.unfilled_quota, "bu yerleştirmede",
              "uyari") +
            degisimKutusu("Yerleşen değişimi", g.intake_change_percent, "%", 1,
              "önceki kohorta göre") +
            degisimKutusu("Kontenjan değişimi", g.quota_change_percent, "%", 1,
              "önceki yıla göre") +
            degisimKutusu("Doluluk değişimi", g.occupancy_change_points, "puan", 1,
              "önceki yıla göre") +
            degisimKutusu("Taban puan değişimi", g.base_score_change, "puan", 1) +
            degisimKutusu("Başarı sırası", g.success_rank_improvement, "sıra", 1,
              "küçülme iyileşmedir") +
            olcumKutusu("Öğrenci / akademisyen", g.students_per_academic_staff,
              "kadro geneli",
              Number(g.students_per_academic_staff) >= 40 ? "kotu"
                : Number(g.students_per_academic_staff) >= 25 ? "uyari" : "iyi") +
            olcumKutusu("Öğrenci / ders veren", g.students_per_active_teaching_staff,
              "fiilen öğretim yapan") +
            olcumKutusu("100 öğrenciye akademisyen", g.academics_per_100_students) +
            olcumKutusu("Pencere kontenjanı", g.window_quota_total,
              g.cohort_years && g.cohort_years.length
                ? `${g.cohort_years[0]}–${g.cohort_years[g.cohort_years.length - 1]}` : "")
          );
        }, { iskelet: 2 });

      /* 4 yıllık alım trendi: kontenjan ve yerleşen aynı eksende;
         doluluk ayrı seride, yüzde ölçeği farklı olduğu için ayrı kart. */
      veri("ogTrend",
        () => api.get("/api/decision-analytics/student-body", p),
        g => {
          const c = g.cohorts || [];
          if (c.length < 2) {
            return bosDurum("Trend için en az iki yıllık yerleştirme verisi gerekir.");
          }
          return cizgiGrafik(c.map(x => x.placement_year), [
            { ad: "Kontenjan", veri: c.map(x => x.quota), renk: "var(--vurgu-2)" },
            { ad: "Yerleşen", veri: c.map(x => x.placed_students),
              renk: "var(--vurgu)", alan: true },
          ], { yb: v => fmt.int(Math.round(v)) }) +
          altBaslik("Doluluk (%)") +
          cizgiGrafik(c.map(x => x.placement_year), [
            { ad: "Doluluk", veri: c.map(x => x.occupancy_percent),
              renk: "var(--iyi)" },
          ], { yb: v => Math.round(v) + "%", yukseklik: 150 });
        });

      /* Kohort dağılımı: öğrenci gövdesinin hangi yıllardan geldiği.
         Küçülen bir kohort, dört yıl boyunca gövdeyi aşağı çeker. */
      veri("ogKohort",
        () => api.get("/api/decision-analytics/student-body", p),
        g => {
          const c = g.cohorts || [];
          if (!c.length) return bosDurum("Kohort verisi yok.");
          return cubuklar(c.map(x => [
            String(x.placement_year), x.placed_students,
            `${fmtSayi(x.placed_students)} · ${fmtYuzde(x.cohort_share_percent, 0)}`,
            x.placement_year === g.latest_placement_year,
          ])) + altBaslik("Talep baskısı") + (
            g.demand_pressure && g.demand_pressure.available
              ? kutular(
                  kutu("Durum", etiketC(baskiTuru(g.demand_pressure.status),
                    baskiAdi(g.demand_pressure.status)),
                    g.demand_pressure.explanation) +
                  kutu("Doluluk", fmtYuzde(g.demand_pressure.occupancy_percent, 1),
                    `${g.demand_pressure.placement_year} yerleştirmesi`,
                    dolulukTur(g.demand_pressure.occupancy_percent)) +
                  (g.demand_momentum && g.demand_momentum.available
                    ? kutu("Talep yönü", fmt.esc(g.demand_momentum.direction),
                        `${g.demand_momentum.improving_signals} iyileşen / ` +
                        `${g.demand_momentum.declining_signals} gerileyen sinyal`,
                        g.demand_momentum.direction === "artıyor" ? "iyi"
                          : g.demand_momentum.direction === "azalıyor" ? "kotu" : "")
                    : "")
                )
              : bosDurum("Talep baskısı için doluluk verisi yok.")
          );
        });

      /* KAPSAMA UYGUN KARŞILAŞTIRMA: bir alt seviyedeki birimler.
         Üniversitede fakülteler, fakültede bölümler, bölümde programlar. */
      veri("ogKirilim",
        () => api.get("/api/decision-analytics/child-breakdown", p),
        k => {
          if (k.is_leaf) {
            return bosDurum("Bu birimin altında karşılaştırılacak alt birim yok.");
          }
          return kirilimTablosu(k) + altBaslik("Doluluğa göre") + cubuklar(
            [...k.rows].filter(r => r.occupancy_percent !== null)
              .sort((a, b) => a.occupancy_percent - b.occupancy_percent)
              .map(r => [r.name, r.occupancy_percent,
                fmtYuzde(r.occupancy_percent, 0), false,
                r.occupancy_percent < 60 ? "var(--kotu)"
                  : r.occupancy_percent < 80 ? "var(--uyari)" : null]),
            { maks: 100, bos: "Doluluk ölçülen alt birim yok." });
        });
    }, 0);

    /* YÖK KAYITLI ÖĞRENCİ SAYISI — yalnızca ÜNİVERSİTE kapsamında.
       Kaynakta fakülte/bölüm kırılımı yoktur; alt kapsamlarda uç
       `available:false` döner ve kart hiç çizilmez. Üniversite
       toplamını bir fakülteye yazmak uydurma olurdu. */
    if (kapsamSeviye(dugum.id) === "university") {
      setTimeout(() => {
        veri("ogKayitli",
          () => api.get("/api/decision-analytics/enrolled-headcount", p),
          o => {
            if (!o.available) return bosDurum(o.note);
            const y = o.years || [];
            return kutular(
              kutu("Kayıtlı öğrenci", fmtSayi(o.student_count),
                `${o.latest_academic_year} · YÖK`) +
              degisimKutusu("Yıllık değişim", o.latest_change_percent, "%", 1,
                o.previous_student_count
                  ? `önceki yıl ${fmtSayi(o.previous_student_count)}` : "") +
              degisimKutusu("Dönem büyümesi", o.period_growth_percent, "%", 1,
                `${o.first_academic_year} → ${o.latest_academic_year}`) +
              olcumKutusu("Kadın öğrenci payı", o.female_percent, "yüzde")
            ) + (y.length > 1
              ? cizgiGrafik(y.map(x => x.academic_year), [
                  { ad: "Kayıtlı öğrenci", veri: y.map(x => x.student_count),
                    renk: "var(--vurgu)", alan: true },
                ], { yb: v => fmt.int(Math.round(v)) })
              : "") + altBaslik("Öğrenim düzeyine göre") + cubuklar(
                Object.entries(o.by_degree_level || {})
                  .filter(([, v]) => v > 0)
                  .map(([ad, v]) => [ad, v, fmtSayi(v)]),
                { bos: "Düzey kırılımı yok." });
          }, { iskelet: 3 });
      }, 0);
    }

    const kayitliKart = kapsamSeviye(dugum.id) === "university"
      ? kart("Kayıtlı öğrenci sayısı ve büyüme",
          "YÖK'ün bildirdiği fiilen kayıtlı öğrenci sayısı. " +
          "ÖSYM yerleştirmelerinden türetilen program sayılarından " +
          "ayrı bir ölçümdür.",
          `<div id="ogKayitli">${iskelet(3)}</div>`,
          { stil: "margin-top:14px" })
      : "";

    return `<div id="ogGovde">${iskelet(2)}</div>` + kayitliKart +
      izgara("k32",
        kart("Alım trendi", "Son yerleştirme yıllarında kontenjan, yerleşen ve doluluk.",
          `<div id="ogTrend">${iskelet(6)}</div>`),
        kart("Kohort dağılımı ve talep baskısı",
          "Öğrenci gövdesinin hangi yıllardan geldiği.",
          `<div id="ogKohort">${iskelet(4)}</div>`)) +
      kart("Alt birim karşılaştırması",
        "Öğrenci, kontenjan, doluluk ve kadro aynı satırda.",
        `<div id="ogKirilim">${iskelet(6)}</div>`, { stil: "margin-top:14px" });
  },
};

/* ---------------- Öğrenciler › Akademik Başarı ---------------- */
MERCEK_CIZ["ogrenci/basari"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id, { academic_year: varsayilanYil() });
    setTimeout(() => {
      veri("abKutular",
        () => api.get("/api/academic-success/overview", p),
        o => kutular(
          kutu("Geçme oranı", fmtYuzde(o.course_pass_rate, 1), "ders bazında") +
          kutu("Başarısızlık", fmtYuzde(o.course_fail_rate, 1), "ders bazında") +
          kutu("Ortalama başarı", fmtOndalik(o.average_success_score, 1), "100 üzerinden") +
          kutu("Öğrenci kaybı", fmtYuzde(o.dropout_rate, 1), "oran") +
          kutu("Mezuniyet", fmtYuzde(o.graduation_rate, 1), "oran") +
          kutu("Ölçülen öğrenci", fmtSayi(o.measured_student_count), "kapsamda") +
          kutu("Mezun", fmtSayi(o.graduate_count), "bu dönem")
        ) + yonetilenKaynakNotu(o), { iskelet: 2 });

      veri("abProgram",
        () => api.get("/api/academic-success/by-program", p),
        rows => tablo(
          ["Program", "Öğrenci", "Geçme", "Başarı puanı", "Kayıp", "Mezuniyet"],
          [...rows].sort((a, b) => Number(a.course_pass_rate) - Number(b.course_pass_rate)).map(r => {
            const tur = Number(r.course_pass_rate) >= 80 ? "iyi" : Number(r.course_pass_rate) >= 60 ? "uyari" : "kotu";
            return [
              fmt.esc(r.program_code || r.program_name), fmtSayi(r.measured_student_count),
              { icerik: fmtYuzde(r.course_pass_rate, 1), sinif: tur === "kotu" ? "kotu" : tur === "iyi" ? "iyi" : "" },
              fmtOndalik(r.average_success_score, 1), fmtYuzde(r.dropout_rate, 1),
              fmtYuzde(r.graduation_rate, 1),
            ];
          })
        ) + yonetilenKaynakNotu(rows[0]));

      veri("abTrend",
        () => api.get("/api/academic-success/trend", agac.kapsam(dugum.id)),
        rows => {
          const seri = [...rows].sort((a, b) =>
            String(a.academic_year).localeCompare(String(b.academic_year)));
          return cizgiGrafik(
            seri.map(r => r.academic_year),
            [{ ad: "Geçme oranı", renk: "#2ec4a6", alan: true,
               veri: seri.map(r => Number(r.course_pass_rate)) }],
            { min: 0, maks: 100, yb: v => "%" + Math.round(v) }) +
            yonetilenKaynakNotu(seri[seri.length - 1]);
        });
    }, 0);

    return `<div id="abKutular">${iskelet(2)}</div>` +
      izgara("k2",
        kart("Geçme oranı seyri", "Akademik yıllara göre geçme oranı.",
          `<div id="abTrend">${iskelet(5)}</div>`),
        kart("Program bazında başarı", "En düşük geçme oranından başlayarak.",
          `<div id="abProgram">${iskelet(6)}</div>`));
  },
};

/* ---------------- Akademik Personel ---------------- */
MERCEK_CIZ["personel/kadro"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      /* CARİ DÖNEM ODAKLI ÖZET.
         Atıf / idari görev / sanayi iş birliği alanları kaynakta YOK
         (hepsi 0); "0 atıf" kartı basmak "ölçtük, sıfır çıktı" demek
         olurdu. Bu kartlar kaldırıldı — `varsaKutu` yalnızca değeri
         olan göstergeyi çizer. */
      veri("apKutular",
        () => Promise.all([
          api.get("/api/curriculum/current-teaching", p),
          api.get("/api/decision-analytics/staffing", p),
        ]),
        ([c, st]) => kutular(
          kutu("Akademik personel", fmtSayi(st.academic_staff_count), "kadro") +
          (c.available
            ? kutu("Bu dönem ders veren", fmtSayi(c.teaching_staff_count),
                c.current_academic_year,
                c.teaching_staff_count / Math.max(1, c.academic_staff_count) < 0.4
                  ? "uyari" : "iyi") +
              kutu("Bu dönem ders", fmtSayi(c.distinct_course_count), "farklı ders") +
              varsaKutu("Haftalık saat", fmtSayi(c.total_weekly_hours), "toplam") +
              varsaKutu("Ders veren başına",
                fmtOndalik(c.average_hours_per_teaching_staff, 1), "saat / hafta")
            : "") +
          varsaKutu("Öğrenci / akademisyen",
            fmtOndalik(st.students_per_academic_staff, 1), "kadro geneli") +
          varsaKutu("Akademisyen başına yayın",
            fmtOndalik(st.average_publications_per_academic, 1), "yayın")
        ), { iskelet: 2 });

      veri("apUnvan",
        () => api.get("/api/academic-staff/overview", p),
        o => cubuklar((o.title_distribution || [])
          .map(t => [t.title, t.count, fmtSayi(t.count)])));

      /* AKADEMİSYEN DRILL-DOWN
         Satıra tıklanınca ALTINDA bir akordiyon açılır ve o kişinin
         GERÇEK ders geçmişi akademik yıla göre gruplanmış gelir.
         Ders ataması uydurulmaz: kaynakta olmayan ders görünmez.
         Kapsam korunur — liste zaten `p` ile süzülüyor, akordiyon da
         yalnızca listede olan kişiyi açabiliyor. */
      veri("apSira",
        () => Promise.all([
          api.get("/api/academic-staff/ranking", { ...p, limit: 50 }),
          // Varsayılan CARİ DÖNEM: "bu yıl ders veriyor mu?" sorusu
          // yönetim için "hiç ders vermiş mi?"den daha yararlıdır.
          api.get("/api/curriculum/staff-course-counts", p).catch(() => ({})),
        ]),
        ([rows, dersSayilari], hedef) => {
          // ALAN ADLARI ucun GERÇEK cevabından: rank, staff_id, full_name,
          // title, department_name, total_score, performance_band,
          // score_breakdown. Daha önce burada var olmayan alanlar
          // (weighted_score / publication_count / teaching_load_hours)
          // okunuyordu ve hücreler boş çiziliyordu.
          const html = tablo(
            ["#", "Ad", "Unvan", "Bölüm", "Puan", "Durum", "Bu dönem"],
            rows.map(r => ({
              hucreler: [
                fmtSayi(r.rank),
                { icerik: `<button class="baglanti-btn" data-personel="${r.staff_id}"
                     aria-expanded="false">${fmt.esc(r.full_name || "—")}</button>` },
                fmt.esc(r.title || "—"),
                fmt.esc(r.department_name || "—"),
                { icerik: fmtOndalik(r.total_score, 1), sinif: "iyi" },
                { icerik: etiketC("bilgi", r.performance_band || "—"),
                  stil: "text-align:left" },
                { icerik: (dersSayilari || {})[r.staff_id]
                    ? etiketC("iyi", fmtSayi(dersSayilari[r.staff_id]) + " ders")
                    // Bu dönem ders vermeyen kişi "0" değil, "—".
                    : etiketC("notr", "bu dönem yok"), stil: "text-align:left" },
              ],
            }))
          );
          // Dinleyici DELEGASYONLA bağlanır (bkz. personelAkordiyonuBagla):
          // `veri()` bu tabloyu her yeniden çizişinde innerHTML'i
          // değiştiriyor ve tek tek bağlanan dinleyiciler kaybolurdu.
          personelAkordiyonuBagla(hedef);
          return html;
        }, { iskelet: 8 });

      veri("apTrend",
        () => api.get("/api/academic-staff/trend", agac.kapsam(dugum.id)),
        rows => {
          const seri = [...rows].sort((a, b) =>
            String(a.academic_year).localeCompare(String(b.academic_year)));
          return cizgiGrafik(seri.map(r => r.academic_year), [
            { ad: "Yayın", renk: "#9b7ff0", alan: true, veri: seri.map(r => Number(r.total_publication)) },
            { ad: "Personel", renk: "#4c8dff", veri: seri.map(r => Number(r.total_staff)) },
          ], { min: 0 });
        });
    }, 0);

    return `<div id="apKutular">${iskelet(2)}</div>` +
      izgara("k32",
        kart("Akademik üretim seyri", "Yıllara göre yayın sayısı ve kadro büyüklüğü.",
          `<div id="apTrend">${iskelet(5)}</div>`),
        kart("Unvan dağılımı", "Kadronun unvanlara göre kırılımı.",
          `<div id="apUnvan">${iskelet(5)}</div>`)) +
      kart("Performans sıralaması", "Ağırlıklı puana göre ilk 15 öğretim üyesi.",
        `<div id="apSira">${iskelet(6)}</div>`, { stil: "margin-top:14px" });
  },
};

/* ---------------- Finans ---------------- */
/* EĞİTİM ÜCRETLERİ — kapsam duyarlı bölüm.
   Program/bölüm/fakülte/üniversite kapsamında yalnızca O kapsamın
   programlarının ücretleri gösterilir; uç nokta kapsamı ID ile süzer. */
function ucretBolumu(dugum) {
  const p = kapsamParam(dugum.id);
  setTimeout(() => {
    veri("ucKutular",
      () => api.get("/api/tuition/program-fees", p),
      o => {
        if (!o.available) return bosDurum(o.note || "Ücret verisi yok.");
        const tam = (o.by_fee_type || []).find(t => t.fee_type === "FULL");
        const yari = (o.by_fee_type || []).find(t => t.fee_type === "HALF");
        return kutular(
          kutu("Akademik yıl", fmt.esc(o.academic_year), "ücret dönemi") +
          olcumKutusu("Ücretlendirilen program", o.row_count, "kayıt") +
          (yari && yari.median_fee
            ? kutu("%50 burslu medyan", fmtPara(yari.median_fee), "TL/yıl") : "") +
          (tam && tam.median_fee
            ? kutu("Tam ücret medyanı", fmtPara(tam.median_fee), "TL/yıl") : "") +
          (yari && yari.min_fee
            ? kutu("En düşük (%50)", fmtPara(yari.min_fee), "TL/yıl") : "") +
          (yari && yari.max_fee
            ? kutu("En yüksek (%50)", fmtPara(yari.max_fee), "TL/yıl") : "")
        );
      }, { iskelet: 2 });

    veri("ucTablo",
      () => api.get("/api/tuition/program-fees", p),
      o => {
        if (!o.available) return bosDurum(o.note || "Ücret verisi yok.");
        return tablo(
          ["Program", "Bölüm", "Dil", "Ücret türü", "Yıllık ücret"],
          o.rows.map(r => [
            fmt.esc(r.program_name),
            fmt.esc(r.department_name || r.faculty_name || "—"),
            fmt.esc(r.education_language || "—"),
            { icerik: etiketC(r.fee_type === "FULL" ? "notr" : "bilgi",
                r.fee_type_label), stil: "text-align:left" },
            fmtPara(r.annual_fee),
          ]));
      });

    veri("ucTrend",
      () => api.get("/api/tuition/trend", p),
      o => {
        if (!o.available || (o.years || []).length < 2) {
          return bosDurum("Trend için en az iki yıllık ücret verisi gerekir.");
        }
        return cizgiGrafik(o.years.map(y => y.academic_year), [
          { ad: "Medyan ücret", veri: o.years.map(y => y.median_fee),
            renk: "var(--vurgu)", alan: true },
        ], { yb: v => fmtPara(v) }) +
          tablo(["Yıl", "Program", "Medyan", "En düşük", "En yüksek", "Değişim"],
            o.years.map(y => [
              fmt.esc(y.academic_year), fmtSayi(y.program_count),
              fmtPara(y.median_fee), fmtPara(y.min_fee), fmtPara(y.max_fee),
              { icerik: fmtYuzde(y.change_percent, 1),
                sinif: y.change_percent > 0 ? "iyi" : "" },
            ]));
      });
  }, 0);

  return kart("Eğitim ücretleri",
    "Kapsamdaki programların yıllık ücreti. Kaynak: kurumun yayımladığı " +
    "eğitim ücreti tarifesi.",
    `<div id="ucKutular">${iskelet(2)}</div>` +
    `<div id="ucTablo" style="margin-top:12px">${iskelet(6)}</div>`,
    { stil: "margin-top:14px" }) +
    kart("Ücret seyri", "%50 burslu kontenjan üzerinden yıllara göre medyan.",
      `<div id="ucTrend">${iskelet(5)}</div>`, { stil: "margin-top:14px" });
}

MERCEK_CIZ["finans/mali"] = {
  filtreler: () => [{
    id: "yil", tip: "secim", varsayilan: varsayilanYil(),
    secenekler: (YIL_LISTESI || [varsayilanYil()]).map(y => ({ ad: y, deger: y })),
  }],
  ciz(dugum, F = {}) {
    const yil = F.yil || varsayilanYil();
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      veri("fnKutular",
        () => api.get(`/api/finance/${encodeURIComponent(yil)}/summary`, p),
        f => {
          const denge = Number(f.balance) * 1e6;
          return kutular(
            kutu("Toplam gelir", fmtPara(Number(f.total_revenue) * 1e6), yil) +
            kutu("Toplam gider", fmtPara(Number(f.total_expenditure) * 1e6), yil) +
            kutu("Denge", (denge >= 0 ? "+" : "−") + fmtPara(Math.abs(denge)),
              f.balance_status || "", denge >= 0 ? "iyi" : "kotu") +
            kutu("Öğrenci başına gelir", fmtPara(f.revenue_per_student_usd), "yıllık") +
            kutu("Öğrenci başına maliyet", fmtPara(f.cost_per_student_usd), "yıllık") +
            kutu("Öğrenci", fmtSayi(f.total_students), "mali dönem kaydı") +
            kutu("Mezun", fmtSayi(f.total_graduates), "mali dönem kaydı")
          ) + yonetilenKaynakNotu(f);
        }, { iskelet: 2 });

      veri("fnDagilim",
        () => api.get(`/api/finance/${encodeURIComponent(yil)}/summary`, p),
        f => {
          const rows = f.expenditure_breakdown || [];
          if (!rows.length) return bosDurum(
            "Bu kapsamda kaynak/provenansı korunmuş gider kalemi yok.");
          return cubuklar(rows.map(r => [
            r.category, Number(r.amount), `$${fmtOndalik(r.amount, 2)}M · ${fmtYuzde(r.share_percent, 1)}`,
            false, r.is_synthetic ? "var(--uyari)" : null,
          ])) + yonetilenKaynakNotu(f) +
            tablo(["Gider kalemi", "Tutar", "Pay", "Kaynak"], rows.map(r => [
              fmt.esc(r.category), `$${fmtOndalik(r.amount, 2)}M`,
              fmtYuzde(r.share_percent, 1),
              fmt.esc((r.is_synthetic ? "SYNTHETIC_GENERATED · " : "") +
                (r.source_label || "Yetkili mali kayıt")),
            ]));
        }, { iskelet: 5 });

      veri("fnBirim",
        () => api.get(`/api/finance/${encodeURIComponent(yil)}/departments`, p),
        rows => tablo(
          ["Birim", "Gelir", "Gider", "Net", "Durum"],
          rows.map(r => {
            const net = Number(r.net_balance ?? (Number(r.revenue) - Number(r.expenditure)));
            return [
              fmt.esc(r.department_name || r.name || "—"),
              fmtPara(Number(r.revenue) * (Math.abs(Number(r.revenue)) < 1000 ? 1e6 : 1)),
              fmtPara(Number(r.expenditure) * (Math.abs(Number(r.expenditure)) < 1000 ? 1e6 : 1)),
              { icerik: (net >= 0 ? "+" : "−") +
                  fmtPara(Math.abs(net) * (Math.abs(net) < 1000 ? 1e6 : 1)),
                sinif: net >= 0 ? "iyi" : "kotu" },
              { icerik: etiketC(net >= 0 ? "iyi" : "kotu", net >= 0 ? "Fazla" : "Açık"),
                stil: "text-align:left" },
            ];
          })
        ));

      veri("fnTrend",
        // Mali trend KURUM geneli tek seridir; birim kırılımı yoktur.
        // Kapsam parametresi göndermek yanlış bir daralma izlenimi verirdi.
        () => api.get("/api/finance/trend"),
        rows => {
          const seri = [...rows].sort((a, b) =>
            String(a.academic_year).localeCompare(String(b.academic_year)));
          return cizgiGrafik(seri.map(r => r.academic_year), [
            { ad: "Gelir", renk: "#2ec4a6", alan: true, veri: seri.map(r => Number(r.total_revenue)) },
            { ad: "Gider", renk: "#f2545b", alan: true, veri: seri.map(r => Number(r.total_expenditure)) },
          ], { min: 0, yb: v => "$" + v.toFixed(0) + "M" });
        });
    }, 0);

    return `<div id="fnKutular">${iskelet(2)}</div>` +
      izgara("k32",
        kart("Gelir ve gider seyri", "Mali dönemlere göre toplam gelir ve gider (milyon USD).",
          `<div id="fnTrend">${iskelet(5)}</div>`),
        kart("Birim bazında denge", "Gelir–gider farkı birim kırılımında.",
          `<div id="fnBirim">${iskelet(6)}</div>`)) +
      kart("Giderlerin dağılımı",
        "Analitik gider kalemleri; yüklenmiş değerler denetlenmiş muhasebe kaydı değildir.",
        `<div id="fnDagilim">${iskelet(6)}</div>`, { stil: "margin-top:14px" }) +
      // Eğitim ücretleri KAPSAM DUYARLIDIR: program/bölüm/fakülte
      // seçildiğinde yalnızca o kapsamın ücretleri görünür.
      ucretBolumu(dugum);
  },
};

/* ---------------- Programlar › Sürdürülebilirlik ---------------- */
MERCEK_CIZ["program/surdurulebilirlik"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      veri("psKutular",
        () => api.get("/api/program-sustainability/scores", p),
        rows => {
          const puanlar = rows.map(r => Number(r.sustainability_score)).filter(Number.isFinite);
          const ort = puanlar.length ? puanlar.reduce((a, b) => a + b, 0) / puanlar.length : null;
          const riskli = rows.filter(r => Number(r.sustainability_score) < 50).length;
          return kutular(
            kutu("Değerlendirilen program", fmtSayi(rows.length), "toplam") +
            kutu("Ortalama puan", fmtOndalik(ort, 1), "100 üzerinden") +
            kutu("Riskli program", fmtSayi(riskli), "puan < 50", riskli ? "kotu" : "iyi") +
            kutu("Veri tamlığı", fmtYuzde(
              rows.length ? rows.reduce((t, r) => t + Number(r.data_completeness_percent || 0), 0)
                / rows.length : null, 0), "ortalama")
          );
        }, { iskelet: 2 });

      veri("psCubuk",
        () => api.get("/api/program-sustainability/scores", p),
        rows => cubuklar(
          [...rows].sort((a, b) => Number(a.sustainability_score) - Number(b.sustainability_score))
            .map(r => [r.program_code, Number(r.sustainability_score) || 0,
              fmtOndalik(r.sustainability_score, 1), false,
              Number(r.sustainability_score) < 50 ? "var(--kotu)"
                : Number(r.sustainability_score) < 70 ? "var(--uyari)" : null]),
          { maks: 100 }));

      veri("psTablo",
        () => api.get("/api/program-sustainability/scores", p),
        rows => tablo(
          ["Program", "Puan", "Kategori", "Veri tamlığı"],
          [...rows].sort((a, b) => Number(a.sustainability_score) - Number(b.sustainability_score))
            .map(r => {
              const s = Number(r.sustainability_score);
              const tur = s >= 70 ? "iyi" : s >= 50 ? "uyari" : "kotu";
              return [
                fmt.esc(r.program_code),
                { icerik: fmtOndalik(s, 1), sinif: tur === "kotu" ? "kotu" : tur === "iyi" ? "iyi" : "" },
                { icerik: etiketC(tur, r.category || "—"), stil: "text-align:left" },
                fmtYuzde(r.data_completeness_percent, 0),
              ];
            })
        ));
    }, 0);

    return `<div id="psKutular">${iskelet(2)}</div>` +
      izgara("k32",
        kart("Sürdürülebilirlik puanları", "En düşük puandan başlayarak; %50 altı yeniden yapılandırma sinyali.",
          `<div id="psCubuk">${iskelet(8)}</div>`),
        kart("Kategori dağılımı", "Puan ve veri tamlığıyla birlikte sınıflandırma.",
          `<div id="psTablo">${iskelet(6)}</div>`));
  },
};

/* ---------------- Kıyaslama ---------------- */
/* KARŞILAŞTIRMA — kiminle kıyaslandığımızı HİYERARŞİ belirler.

     ÜNİVERSİTE → dış kurumlarla RAKİP ANALİZİ panosu
     FAKÜLTE    → üniversitedeki DİĞER akademik fakülteler
     BÖLÜM      → AYNI fakültedeki diğer bölümler
     PROGRAM    → AYNI bölümdeki diğer programlar

   Alt seviyelerin davranışı DEĞİŞMEDİ: küme backend'de gerçek kimlik
   ilişkisiyle kurulur (`/api/decision-analytics/peer-comparison`),
   arayüz ad eşleştirmesi yapmaz ve kümeyi genişletemez. Dış kurumlar
   alt seviyelerde GÖSTERİLMEZ.

   ÜNİVERSİTE dalı bir rakip analizi panosuna dönüştürüldü
   (`/api/decision-analytics/university-competitors`). Gösterge
   KAPSAMA KURALINA tabidir: karşılaştırmadaki bütün kurumlarda
   ölçülmeyen bir gösterge hiç çizilmez — eksik değer 0 sayılmaz. */
MERCEK_CIZ["kiyas/degerlendirme"] = {
  filtreler(dugum) {
    /* Süzgeç YALNIZCA üniversite kapsamında görünür; alt seviyelerde
       karşılaştırma kümesini hiyerarşi belirler, kullanıcı değil. */
    if (kapsamSeviye(dugum.id) !== "university") return [];
    return [{
      id: "rakip", tip: "cip", varsayilan: "similar", secenekler: [
        { ad: "Benzer ölçekli", deger: "similar" },
        { ad: "Vakıf", deger: "foundation" },
        { ad: "Devlet", deger: "state" },
        { ad: "Tüm Ankara", deger: "all" },
      ],
    }];
  },
  ciz(dugum, F = {}) {
    const p = kapsamParam(dugum.id);
    const seviye = kapsamSeviye(dugum.id);

    /* ================= ÜNİVERSİTE: RAKİP ANALİZİ =================
       BÖLÜM BÖLÜM ÇİZİLİR. Her bölümün kendi kabı ve kendi `veri()`
       çağrısı vardır; biri çizilirken hata alırsa YALNIZCA o kutu
       etkilenir, pano ayakta kalır. Daha önce panonun tamamı tek bir
       geri çağrıydı: `dagilimGrafik` tanımsız olduğunda bütün ekran
       "Veri alınamadı" oluyordu.

       İstek TEK: bütün bölümler aynı sözü (promise) paylaşır, böylece
       bağımsız çizim çoklu HTTP isteğine mal olmaz. */
    if (seviye === "university") {
      const kip = F.rakip || "similar";
      setTimeout(() => {
        const istek = api.get(
          "/api/decision-analytics/university-competitors",
          { filter_mode: kip });
        const bolum = (kapId, ciz, opt = {}) =>
          veri(kapId, () => istek, ciz, { iskelet: 3, ...opt });

        /* Kapsam notu: her grafik hangi kümeye baktığını söyler. */
        const kapsamNotu = m =>
          m ? `<div class="not">${fmt.esc(m.coverage_note)}</div>` : "";

        /* --- A) ÜST YÖNETİM KONUM KARTLARI --- */
        bolum("ruKartlar", o => {
          if (!o.available) return bosDurum(o.note);
          const b = o.home, M = o.metrics;
          if (!b) return bosDurum("Kurumumuz bu karşılaştırma kümesinde yok.");
          const konum = k => (b.position && b.position[k]) || null;
          const sira = k => {
            const kk = konum(k);
            return kk ? `${kk.rank}. / ${fmtSayi(kk.cohort_size)}` : "";
          };
          return kutular(
            olcumKutusu("Kayıtlı öğrenci", b.student_count,
              `${o.academic_year} · ${sira("student_count")}`) +
            (b.ankara_rank
              ? kutu("Ankara sıralaması",
                  `${b.ankara_rank}. / ${fmtSayi(b.ankara_university_count)}`,
                  "kayıtlı öğrenciye göre") : "") +
            degisimKutusu("4 yıllık büyüme", b.growth_percent_period, "%", 1,
              `${o.first_academic_year} → ${o.academic_year} · ${
                sira("growth_percent_period")}`) +
            degisimKutusu("Son yıl büyümesi", b.growth_percent_yoy, "%", 1,
              sira("growth_percent_yoy")) +
            olcumKutusu("Akademik personel", b.academic_staff_count,
              sira("academic_staff_count")) +
            (M.students_per_academic && M.students_per_academic.available
              ? kutu("Öğrenci / akademisyen",
                  fmtOndalik(b.students_per_academic, 1),
                  sira("students_per_academic")) : "") +
            (M.academics_per_100_students
              && M.academics_per_100_students.available
              ? kutu("100 öğrenciye akademisyen",
                  fmtOndalik(b.academics_per_100_students, 2),
                  sira("academics_per_100_students")) : "") +
            olcumKutusu("Akademik birim", b.academic_unit_count,
              sira("academic_unit_count")) +
            olcumKutusu("Bölüm", b.department_count, sira("department_count"))
          );
        }, { iskelet: 2 });

        /* --- Kohorttaki konum: medyan ve en iyi çeyrek --- */
        bolum("ruKonum", o => {
          if (!o.available || !o.home || !o.home.position) {
            return bosDurum("Konum karşılaştırması için veri yok.");
          }
          const satir = Object.entries(o.home.position);
          if (!satir.length) return bosDurum("Konum karşılaştırması için veri yok.");
          return tablo(
            ["Gösterge", "Kurumumuz", "Kohort medyanı", "Fark",
             "En iyi çeyrek", "Sıra", "Kapsam"],
            satir.map(([k, v]) => {
              const m = o.metrics[k];
              const iyiFark = m.higher_is_better
                ? v.difference_from_median > 0 : v.difference_from_median < 0;
              return [
                fmt.esc(m.label),
                fmtOndalik(m.home_value, 2),
                fmtOndalik(v.median, 2),
                { icerik: fmtOndalik(v.difference_from_median, 2),
                  sinif: v.difference_from_median === 0 ? ""
                    : iyiFark ? "iyi" : "kotu" },
                fmtOndalik(v.top_quartile, 2),
                `${v.rank}. / ${fmtSayi(v.cohort_size)}`,
                fmt.esc(v.coverage_note),
              ];
            })
          );
        }, { iskelet: 4 });

        /* --- B) KARŞILAŞTIRMA TABLOSU (sütunlar kapsama göre) --- */
        bolum("ruTablo", o => {
          if (!o.available) return bosDurum(o.note);
          const M = o.metrics, U = o.universities;
          const acik = k => M[k] && M[k].available;
          const sutun = [["#", null], ["Üniversite", null], ["Tür", null]];
          const alan = [];
          const ekle = (k, baslik, bicim) => {
            if (!acik(k)) return;
            sutun.push([baslik, k]);
            alan.push([k, bicim]);
          };
          ekle("student_count", "Öğrenci", v => fmtSayi(v));
          ekle("growth_percent_period", "4 yıl %", v => fmtYuzde(v, 1));
          ekle("growth_percent_yoy", "Son yıl %", v => fmtYuzde(v, 1));
          ekle("academic_staff_count", "Akademisyen", v => fmtSayi(v));
          ekle("students_per_academic", "Öğr./Akad.", v => fmtOndalik(v, 1));
          ekle("academics_per_100_students", "Akad./100 öğr.",
            v => fmtOndalik(v, 2));
          ekle("academic_unit_count", "Birim", v => fmtSayi(v));
          ekle("department_count", "Bölüm", v => fmtSayi(v));
          return tablo(
            sutun.map(c => c[0]),
            U.map((r, i) => ({
              hucreler: [
                fmtSayi(i + 1),
                { icerik: r.is_home_institution
                    ? `<b>${fmt.esc(r.university_name)}</b> ${
                        etiketC("bilgi", "kurumumuz")}`
                    : fmt.esc(r.university_name),
                  stil: "text-align:left" },
                { icerik: etiketC("notr", r.university_type || "—"),
                  stil: "text-align:left" },
                // Ölçülmeyen hücre "—" görünür; 0 YAZILMAZ.
                ...alan.map(([k, bicim]) => ({
                  icerik: (r[k] === null || r[k] === undefined)
                    ? "—" : bicim(r[k]),
                  sinif: r.is_home_institution ? "iyi" : "",
                })),
              ],
            }))
          );
        }, { iskelet: 6 });

        /* --- C) SIRALAMA GRAFİKLERİ — her biri KENDİ kohortunda --- */
        const siralama = (kapId, k, bicim) => bolum(kapId, o => {
          if (!o.available) return bosDurum(o.note);
          const m = o.metrics[k];
          if (!m) return bosDurum("Gösterge tanımlı değil.");
          if (!m.available) {
            // Grafik çizilmez ama SEBEBİ yazılır; ekran sessizce boşalmaz.
            return bosDurum(m.note || m.coverage_note);
          }
          return kapsamNotu(m) + cubuklar(m.cohort.map(r => [
            r.university_name, Math.abs(Number(r.value)), bicim(r.value),
            r.is_home_institution,
            r.is_home_institution ? "var(--vurgu)" : null,
          ])) + (m.median !== null
            ? `<div class="not">Kohort medyanı: ${
                fmt.esc(String(bicim(m.median)))}${
                m.home_vs_median !== null
                  ? ` · kurumumuz ${m.home_vs_median > 0 ? "+" : ""}${
                      fmt.esc(String(bicim(m.home_vs_median)))}` : ""}</div>`
            : "");
        }, { iskelet: 5 });

        siralama("ruOgrenci", "student_count", v => fmtSayi(v));
        siralama("ruBuyume", "growth_percent_period", v => fmtYuzde(v, 1));
        siralama("ruOran", "students_per_academic", v => fmtOndalik(v, 1));
        siralama("ruAkad100", "academics_per_100_students", v => fmtOndalik(v, 2));
        siralama("ruBirim", "academic_unit_count", v => fmtSayi(v));
        siralama("ruBolum", "department_count", v => fmtSayi(v));
        siralama("ruBolumOgr", "students_per_department", v => fmtSayi(v));
        // FİYAT KONUMU (part3 eğitim ücretleri). Kohortu eksik olsa bile
        // diğer göstergeleri etkilemez; kendi kapsamını bildirir.
        siralama("ruUcret", "median_tuition_fee", v => fmtPara(v));

        /* --- D) STRATEJİK KONUMLANDIRMA --- */
        bolum("ruKonumlandirma", o => {
          if (!o.available) return bosDurum(o.note);
          const mx = o.metrics.student_count, my = o.metrics.growth_percent_period;
          if (!mx || !my || !mx.available || !my.available) {
            return bosDurum("Konumlandırma için ölçek ve büyüme verisi gerekir.");
          }
          // Yalnızca İKİ eksende de ölçülü kurumlar noktalanır.
          const nokta = o.universities
            .filter(r => r.student_count !== null
              && r.growth_percent_period !== null)
            .map(r => ({
              x: r.student_count, y: r.growth_percent_period,
              ad: r.university_name,
              kisa: r.is_home_institution ? "ABÜ" : "",
              vurgulu: r.is_home_institution,
            }));
          return `<div class="not">${fmtSayi(nokta.length)} / ${
            fmtSayi(o.university_count)} kurumda veri</div>` +
            dagilimGrafik(nokta, {
              xb: v => fmt.int(Math.round(v)),
              yb: v => Math.round(v) + "%",
              eksen: "Sağ üst çeyrek: hem büyük hem hızlı büyüyen kurumlar.",
            });
        }, { iskelet: 5 });

        /* --- E) ÖĞRENCİ GÖVDESİ BİLEŞİMİ --- */
        bolum("ruBilesim", o => {
          if (!o.available || !o.home) return bosDurum("Bileşim verisi yok.");
          const d = o.home.by_degree_level || {};
          const satir = Object.entries(d).filter(([, v]) => v > 0);
          if (!satir.length) return bosDurum("Öğrenim düzeyi kırılımı yok.");
          const toplam = satir.reduce((t, [, v]) => t + v, 0);
          const bizim = altBaslik("Kurumumuz") + cubuklar(satir.map(([ad, v]) => [
            ad, v, `${fmtSayi(v)} · ${fmtYuzde(v / toplam * 100, 1)}`]));

          /* Rakiplerin lisans payı: aynı kırılım onlarda da varsa. */
          const rakip = o.universities
            .filter(r => r.by_degree_level && r.student_count)
            .map(r => {
              const lis = r.by_degree_level["Lisans"];
              return lis === undefined ? null : {
                ad: r.university_name, kendi: r.is_home_institution,
                pay: lis / r.student_count * 100,
              };
            }).filter(Boolean);
          const karsilastirma = rakip.length >= 3
            ? altBaslik("Lisans payı — kohort karşılaştırması") +
              `<div class="not">${fmtSayi(rakip.length)} / ${
                fmtSayi(o.university_count)} kurumda veri</div>` +
              cubuklar([...rakip].sort((a, b) => b.pay - a.pay).map(r =>
                [r.ad, r.pay, fmtYuzde(r.pay, 1), r.kendi,
                 r.kendi ? "var(--vurgu)" : null]), { maks: 100 })
            : "";
          return bizim + karsilastirma;
        }, { iskelet: 4 });

        /* --- Karşılaştırmaya girmeyen göstergeler --- */
        bolum("ruKapali", o => {
          const kapali = (o.unavailable_metrics || []);
          if (!kapali.length) return bosDurum("Bütün göstergeler karşılaştırıldı.");
          return tablo(["Gösterge", "Kapsam", "Neden"],
            kapali.map(m => [
              fmt.esc(m.label),
              `${fmtSayi(m.measured_count)} / ${fmtSayi(m.total_count)}`,
              fmt.esc(m.reason || "—"),
            ]));
        }, { iskelet: 2 });

        /* --- "Benzer ölçekli" kuralının açıklaması --- */
        bolum("ruKural", o => {
          const k = o.similar_rule;
          if (!k) return bosDurum("Kural bilgisi yok.");
          return `<div class="not">${fmt.esc(k.explanation)}</div>` +
            (k.reference_student_count
              ? `<div class="not">Referans: ${
                  fmtSayi(k.reference_student_count)} öğrenci · bant ${
                  fmtSayi(Math.round(k.reference_student_count * k.lower_multiplier))}–${
                  fmtSayi(Math.round(k.reference_student_count * k.upper_multiplier))}</div>`
              : "");
        }, { iskelet: 1 });
      }, 0);

      const K = (baslik, not, kap, satir = 4, opt = {}) =>
        kart(baslik, not, `<div id="${kap}">${iskelet(satir)}</div>`, opt);

      return `<div id="ruKartlar">${iskelet(2)}</div>` +
        K("Kohorttaki konum",
          "Kurumumuzun her göstergedeki sırası, kohort medyanı ve en iyi " +
          "çeyreğin eşiği. Her satır kendi kapsamını bildirir.",
          "ruKonum", 4, { stil: "margin-top:14px" }) +
        K("Rakip karşılaştırma tablosu",
          "Sütunlar ölçülebilen göstergelere göre oluşur; ölçülmeyen hücre " +
          "boş bırakılır, sıfır yazılmaz.",
          "ruTablo", 6, { stil: "margin-top:14px" }) +
        `<div class="izgara k2" style="margin-top:14px">` +
          K("Kayıtlı öğrenci sıralaması", "Kurumumuz vurgulanmıştır.", "ruOgrenci", 5) +
          K("4 yıllık büyüme sıralaması", "Kurumumuz vurgulanmıştır.", "ruBuyume", 5) +
        `</div>` +
        `<div class="izgara k2" style="margin-top:14px">` +
          K("Öğrenci / akademisyen sıralaması",
            "Küçük değer daha iyidir.", "ruOran", 5) +
          K("100 öğrenciye akademisyen sıralaması",
            "Büyük değer daha iyidir.", "ruAkad100", 5) +
        `</div>` +
        `<div class="izgara k2" style="margin-top:14px">` +
          K("Akademik birim sayısı", "Kurumsal yapı genişliği.", "ruBirim", 5) +
          K("Bölüm sayısı", "Kurumsal yapı derinliği.", "ruBolum", 5) +
        `</div>` +
        `<div class="izgara k2" style="margin-top:14px">` +
          K("Bölüm başına öğrenci",
            "Bölüm ölçeği. Küçük değer daha az kalabalık bölüm demektir.",
            "ruBolumOgr", 5) +
          K("Eğitim ücreti konumu",
            "%50 burslu lisans ücretinin kurum medyanı. Yüksek/düşük " +
            "olmak tek başına iyi ya da kötü değildir; konumu gösterir.",
            "ruUcret", 5) +
        `</div>` +
        K("Stratejik konumlandırma",
          "Yatay: kayıtlı öğrenci (ölçek). Dikey: 4 yıllık büyüme. " +
          "Kesikli çizgiler kohort ortalamalarıdır.",
          "ruKonumlandirma", 5, { stil: "margin-top:14px" }) +
        K("Öğrenci gövdesi bileşimi",
          "Öğrenim düzeyine göre dağılım (önlisans / lisans / yüksek lisans / doktora).",
          "ruBilesim", 4, { stil: "margin-top:14px" }) +
        `<div class="izgara k2" style="margin-top:14px">` +
          K("Karşılaştırmaya girmeyen göstergeler",
            "Kapsamı yetersiz ya da kurumlar arasında aynı şeyi ölçmeyen " +
            "göstergeler sıralanmaz.", "ruKapali", 2) +
          K("“Benzer ölçekli” nasıl seçiliyor?",
            "Rakip kümesi elle tutulmaz; kuraldan üretilir.", "ruKural", 2) +
        `</div>`;
    }

    /* ============ ALT SEVİYELER: DEĞİŞMEDİ ============ */
    setTimeout(() => {
      veri("kyKume",
        () => api.get("/api/decision-analytics/peer-comparison", p),
        o => {
          if (!o.available) {
            return bosDurum(o.note);
          }
          const kendi = (o.peers || []).find(r => r.is_selected);
          const sira = o.ranks || {};
          const siraKutusu = (baslik, deger, alt) =>
            (deger === null || deger === undefined) ? ""
              : kutu(baslik, `${deger}. / ${fmtSayi(o.peer_count)}`, alt);

          return kutular(
            kutu("Karşılaştırma tabanı", fmt.esc(o.basis_label),
              o.parent && o.parent.name
                ? `${fmt.esc(o.parent.name)} içinde` : "") +
            kutu("Kardeş birim", fmtSayi(o.sibling_count), "karşılaştırmada") +
            siraKutusu("Öğrenci sıralaması", sira.student_count, "büyükten küçüğe") +
            siraKutusu("Doluluk sıralaması", sira.occupancy_percent, "yüksekten düşüğe") +
            siraKutusu("Kadro sıralaması", sira.academic_staff_count, "büyükten küçüğe") +
            siraKutusu("Öğrenci/akademisyen", sira.students_per_academic_staff,
              "düşük olan üstte")
          ) + tablo(
            ["Birim", "Öğrenci", "Kontenjan", "Yerleşen", "Doluluk",
             "Akademisyen", "Ders veren", "Öğr./Akad.", "Ders"],
            o.peers.map(r => {
              const tur = dolulukTur(r.occupancy_percent);
              const ad = r.is_selected
                ? `<b>${fmt.esc(r.name)}</b> ${etiketC("bilgi", "seçili")}`
                : fmt.esc(r.name);
              return {
                hucreler: [
                  { icerik: ad, stil: "text-align:left" },
                  fmtSayi(r.student_count), fmtSayi(r.quota),
                  fmtSayi(r.placed_students),
                  { icerik: fmtYuzde(r.occupancy_percent, 1),
                    sinif: tur === "kotu" ? "kotu" : tur === "iyi" ? "iyi" : "" },
                  fmtSayi(r.academic_staff_count),
                  fmtSayi(r.active_teaching_staff_count),
                  fmtOndalik(r.students_per_academic_staff, 1),
                  fmtSayi(r.curriculum_course_count),
                ],
              };
            })
          ) + (kendi ? "" : bosDurum(
            "Seçili birim karşılaştırma kümesinde bulunamadı."));
        }, { iskelet: 3 });

      veri("kyGrafik",
        () => api.get("/api/decision-analytics/peer-comparison", p),
        o => {
          if (!o.available) return bosDurum(o.note);
          const cizim = (anahtar, baslik, bicim) => {
            const satir = o.peers.filter(r => r[anahtar] !== null
              && r[anahtar] !== undefined);
            if (!satir.length) return "";
            return altBaslik(baslik) + cubuklar(
              [...satir].sort((a, b) => b[anahtar] - a[anahtar])
                .map(r => [r.name, r[anahtar], bicim(r[anahtar]), r.is_selected,
                  r.is_selected ? "var(--vurgu)" : null]));
          };
          return cizim("student_count", "Öğrenci sayısı", v => fmtSayi(v)) +
            cizim("occupancy_percent", "Doluluk", v => fmtYuzde(v, 0)) +
            cizim("students_per_academic_staff", "Öğrenci / akademisyen",
              v => fmtOndalik(v, 1));
        });
    }, 0);

    const baslik = seviye === "faculty" ? "Fakülte karşılaştırması"
      : seviye === "department" ? "Bölüm karşılaştırması"
      : "Program karşılaştırması";
    const not = seviye === "faculty"
      ? "Yalnızca üniversitedeki diğer akademik fakülteler."
      : seviye === "department"
      ? "Yalnızca aynı fakültedeki bölümler."
      : "Yalnızca aynı bölümdeki programlar.";

    return kart(baslik, not, `<div id="kyKume">${iskelet(5)}</div>`) +
      kart("Göstergeye göre kıyas", "Seçili birim vurgulanmıştır.",
        `<div id="kyGrafik">${iskelet(6)}</div>`, { stil: "margin-top:14px" });
  },
};

/* ---------------- Fiziksel Kaynaklar ---------------- */
MERCEK_CIZ["fiziksel/kapasite"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      veri("fzKutular",
        () => Promise.all([
          api.get("/api/physical-resources/capacity/overview", p),
          api.get("/api/data-sources/availability", {
            metric_key: "facility_occupancy_rate", academic_year: varsayilanYil(),
            scope_type: "university",
          }),
          api.get("/api/data-sources/availability", {
            metric_key: "facility_area_m2", academic_year: varsayilanYil(),
            scope_type: "university",
          }),
        ]),
        ([o, doluluk, alan]) => {
          const dolulukDegeri = olculdu(o.overall_occupancy_percent)
            ? o.overall_occupancy_percent : doluluk.resolved_value;
          const alanDegeri = o.total_area_square_meters ?? alan.resolved_value;
          return kutular(
          olcumKutusu("Mekân", o.total_facilities, "derslik ve laboratuvar") +
          olcumKutusu("Sınıf kapasitesi", o.total_capacity, "fiziksel koltuk") +
          olcumKutusu("Öğrenci kapasitesi", o.total_student_capacity,
            "ders planlamasında kullanılabilir") +
          olcumKutusu("Kullanılan", o.total_occupied, "eş zamanlı kişi") +
          (olculdu(dolulukDegeri)
            ? kutu("Doluluk", fmtYuzde(dolulukDegeri, 1), "genel",
                Number(dolulukDegeri) > 90 ? "kotu"
                  : Number(dolulukDegeri) > 75 ? "uyari" : "iyi")
            : "") +
          (olculdu(alanDegeri)
            ? kutu("Toplam alan", fmtOndalik(alanDegeri, 0) + " m²", "analitik alan")
            : "") +
          olcumKutusu("Aşırı dolu", o.overcrowded_count, "mekân", "kotu", true) +
          olcumKutusu("Az kullanılan", o.underutilized_count, "mekân",
            "uyari", true)
          ) + yonetilenKaynakNotu(
            olculdu(o.overall_occupancy_percent) ? {
              source_type: "authoritative", source_label: "Fiziksel kaynak envanteri",
            } : doluluk
          ) + (alan.source_type === doluluk.source_type ? "" : yonetilenKaynakNotu(alan));
        }, { iskelet: 2 });

      // DERSLİK ENVANTERİ — kapsamdaki gerçek mekânlar.
      veri("fzListe",
        () => api.get("/api/physical-resources/facilities",
          kapsamParam(dugum.id, { limit: 200 })),
        rows => {
          const satir = Array.isArray(rows) ? rows : (rows.items || []);
          if (!satir.length) return bosDurum("Bu kapsamda mekân kaydı yok.");
          return tablo(
            ["Kod", "Mekân", "Tür", "Kat", "Sahip", "Sınıf kap.", "Öğrenci kap."],
            [...satir].sort((a, b) => (a.floor - b.floor)
              || String(a.code).localeCompare(String(b.code)))
              .map(r => [
                fmt.esc(r.code),
                fmt.esc(r.room_label || r.name || "—"),
                { icerik: etiketC("notr",
                    r.facility_type === "laboratory" ? "Lab" : "Derslik"),
                  stil: "text-align:left" },
                fmtSayi(r.floor),
                fmt.esc(r.faculty_name || r.owner_label || "—"),
                fmtSayi(r.capacity),
                fmtSayi(r.student_capacity),
              ]));
        });

      veri("fzTur",
        () => api.get("/api/physical-resources/capacity/by-type", p),
        rows => {
          // Kullanım ölçülmüşse doluluk, ölçülmemişse KAPASİTE çizilir;
          // ölçülmemiş oranı 0 kabul edip çubuk çizmek yanlış olurdu.
          const olculmus = rows.some(r =>
            r.average_utilization_percent !== null
            && r.average_utilization_percent !== undefined);
          if (olculmus) {
            return cubuklar(rows.map(r => [
              r.facility_type, Number(r.average_utilization_percent) || 0,
              fmtYuzde(r.average_utilization_percent, 1), false,
              Number(r.average_utilization_percent) > 90 ? "var(--kotu)"
                : Number(r.average_utilization_percent) > 75 ? "var(--uyari)" : null,
            ]), { maks: 120 });
          }
          return `<div class="not">Kullanım ölçümü yok; toplam kapasite gösteriliyor.</div>` +
            cubuklar(rows.map(r => [
              r.facility_type === "laboratory" ? "Laboratuvar" : "Derslik",
              Number(r.total_capacity) || 0,
              `${fmtSayi(r.total_capacity)} koltuk · ${fmtSayi(r.facility_count)} mekân`,
            ]));
        });

      veri("fzBolum",
        () => api.get("/api/physical-resources/capacity/by-department", p),
        rows => tablo(
          ["Birim", "Mekân", "Kapasite", "Kullanılan", "Doluluk"],
          rows.map(r => {
            const d = Number(r.average_utilization_percent ?? r.occupancy_percent);
            const sinif = !Number.isFinite(d) ? "" : d > 90 ? "kotu" : d < 50 ? "uyari" : "iyi";
            return [
              fmt.esc(r.department_name || r.name || "—"),
              fmtSayi(r.facility_count), fmtSayi(r.total_capacity), fmtSayi(r.total_occupied),
              { icerik: fmtYuzde(d, 1), sinif },
            ];
          })
        ));

      veri("fzHalka",
        () => Promise.all([
          api.get("/api/physical-resources/capacity/overview", p),
          api.get("/api/data-sources/availability", {
            metric_key: "facility_occupancy_rate", academic_year: varsayilanYil(),
            scope_type: "university",
          }),
        ]),
        ([o, doluluk]) => {
          const olculen = (o.by_type || []).filter(t =>
            t.average_utilization_percent !== null && t.average_utilization_percent !== undefined);
          if (olculen.length) return halkalar(olculen.slice(0, 3).map(t =>
            halka(t.average_utilization_percent, t.facility_type,
              Number(t.average_utilization_percent) > 90 ? "var(--kotu)"
                : Number(t.average_utilization_percent) > 75 ? "var(--uyari)" : "var(--iyi)")).join(""));
          if (doluluk.resolved_value === null) return bosDurum("Doluluk ölçümü yok.");
          return halkalar(halka(doluluk.resolved_value, "Genel doluluk", "var(--uyari)")) +
            yonetilenKaynakNotu(doluluk);
        });
    }, 0);

    return `<div id="fzKutular">${iskelet(2)}</div>` +
      izgara("k32",
        kart("Mekân türüne göre kullanım", "Ortalama doluluk oranı; %90 üzeri aşırı kullanım.",
          `<div id="fzTur">${iskelet(5)}</div>`),
        kart("Tür kırılımı", "İlk üç mekân türünün doluluğu.",
          `<div id="fzHalka">${iskelet(2)}</div>`)) +
      kart("Birim bazında kapasite", "Mekân sayısı, kapasite ve kullanım.",
        `<div id="fzBolum">${iskelet(6)}</div>`, { stil: "margin-top:14px" }) +
      kart("Derslik envanteri",
        "Kaynak: kurumun derslik listesi. Sınıf kapasitesi fiziksel " +
        "koltuk sayısı, öğrenci kapasitesi ders planlamasında " +
        "kullanılabilen sayıdır.",
        `<div id="fzListe">${iskelet(8)}</div>`, { stil: "margin-top:14px" });
  },
};

/* ---------------- Performans › Göstergeler ---------------- */
MERCEK_CIZ["kpi/gosterge"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      veri("kpKutular",
        () => api.get("/api/kpi/scorecard", p),
        s => kutular(
          kutu("Gösterge", fmtSayi(s.total_kpis), `${fmtSayi(s.measured_kpi_count)} ölçüldü`) +
          kutu("Genel başarı", fmtYuzde(s.overall_achievement_percent, 1),
            s.overall_status || "", Number(s.overall_achievement_percent) >= 90 ? "iyi"
              : Number(s.overall_achievement_percent) >= 70 ? "uyari" : "kotu") +
          kutu("Hedefte", fmtSayi(s.on_track_count), "gösterge", "iyi") +
          kutu("Gecikmeli", fmtSayi(s.delayed_count), "gösterge", "uyari") +
          kutu("Riskli", fmtSayi(s.at_risk_count), "gösterge", s.at_risk_count ? "kotu" : "") +
          kutu("Veri yok", fmtSayi(s.no_data_count), "gösterge")
        ), { iskelet: 2 });

      veri("kpBoyut",
        () => api.get("/api/kpi/scorecard", p),
        s => cubuklar((s.by_dimension || []).map(d => [
          d.dimension, Number(d.achievement_percent) || 0,
          fmtYuzde(d.achievement_percent, 1), false,
          Number(d.achievement_percent) < 70 ? "var(--kotu)"
            : Number(d.achievement_percent) < 90 ? "var(--uyari)" : null,
        ]), { maks: 120 }));

      veri("kpListe",
        () => api.get("/api/kpi", p),
        rows => tablo(
          ["Gösterge", "Boyut", "Ölçülen", "Hedef", "Başarı", "Durum"],
          rows.map(r => {
            const b = Number(r.achievement_percent);
            const tur = b >= 90 ? "iyi" : b >= 70 ? "uyari" : "kotu";
            return [
              fmt.esc(r.name || r.kpi_name || "—"), fmt.esc(r.dimension || "—"),
              fmtOndalik(r.measured_value, 2), fmtOndalik(r.target_value, 2),
              { icerik: fmtYuzde(b, 1), sinif: tur === "kotu" ? "kotu" : tur === "iyi" ? "iyi" : "" },
              { icerik: etiketC(tur, r.status || "—"), stil: "text-align:left" },
            ];
          })
        ));

      veri("kpDikkat",
        () => api.get("/api/kpi/attention", p),
        rows => cubuklar(rows.slice(0, 8).map(r => [
          r.name || r.kpi_name, Number(r.achievement_percent) || 0,
          fmtYuzde(r.achievement_percent, 0), false, "var(--kotu)"]), { maks: 100 }),
        { bos: "Dikkat gerektiren gösterge yok." });
    }, 0);

    return `<div id="kpKutular">${iskelet(2)}</div>` +
      izgara("k32",
        kart("Boyut bazında başarı", "Stratejik boyutlara göre hedefe ulaşma oranı.",
          `<div id="kpBoyut">${iskelet(5)}</div>`),
        kart("Dikkat gerektirenler", "Hedefin en altında kalan göstergeler.",
          `<div id="kpDikkat">${iskelet(4)}</div>`)) +
      kart("Gösterge listesi", "Ölçülen değer, hedef ve başarı oranı.",
        `<div id="kpListe">${iskelet(6)}</div>`, { stil: "margin-top:14px" });
  },
};

/* ---------------- Performans › Sanayi ve Bölgesel Katkı ---------------- */
MERCEK_CIZ["kpi/katki"] = {
  filtreler: () => [],
  ciz(dugum) {
    const yil = varsayilanYil();
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      veri("skKutular",
        () => api.get("/api/engagement/industry-collaboration",
          kapsamParam(dugum.id, { academic_year: yil })),
        d => {
          const bileşen = key => (d.components || []).find(c => c.key === key) || {};
          return kutular(
            kutu("İş birliği endeksi", fmtOndalik(d.index_value, 2), "100 = bileşen hedefleri") +
            kutu("Ortak proje", fmtSayi(bileşen("joint_projects").value), yil) +
            kutu("Aktif ortaklık", fmtSayi(bileşen("active_partnerships").value), "kurum") +
            kutu("Staj yapan", fmtSayi(bileşen("intern_students").value), "öğrenci") +
            kutu("Araştırma bütçesi", "$" + fmtOndalik(bileşen("funded_research_musd").value, 2) + "M", "analitik")
          ) + yonetilenKaynakNotu(d);
        }, { iskelet: 2 });

      veri("skBolge",
        () => api.get("/api/engagement/regional-contribution",
          kapsamParam(dugum.id, { academic_year: yil })),
        o => {
          return tablo(
            ["Katkı alanı", "Değer", "Birim"],
            (o.components || []).map(c => [
              fmt.esc(c.label), fmtOndalik(c.value, c.unit === "%" ? 1 : 0),
              fmt.esc(c.unit),
            ])
          ) + yonetilenKaynakNotu(o);
        });

      veri("skTrend",
        // Katkı trendi KURUM geneli tek seridir; birim kırılımı yoktur.
        () => api.get("/api/engagement/trend"),
        rows => {
          const seri = [...rows].sort((a, b) =>
            String(a.academic_year).localeCompare(String(b.academic_year)));
          return cizgiGrafik(seri.map(r => r.academic_year), [
            { ad: "Sanayi iş birliği", renk: "#2ec27e", alan: true,
              veri: seri.map(r => Number(r.industry_collaboration_index)) },
            { ad: "Bölgesel katkı", renk: "#4c8dff", alan: false,
              veri: seri.map(r => Number(r.regional_contribution_index)) },
          ], { min: 0, yb: v => fmtOndalik(v, 0) });
        });
    }, 0);

    return `<div id="skKutular">${iskelet(2)}</div>` +
      izgara("k2",
        kart("Sanayi iş birliği seyri", "Yıllara göre proje sayısı.",
          `<div id="skTrend">${iskelet(5)}</div>`),
        kart("Bölgesel katkı", "Kayıtlı katkı göstergeleri.",
          `<div id="skBolge">${iskelet(5)}</div>`));
  },
};

/* ---------------- Genel Bakış › Akıllı Asistan ----------------
   GÖRSEL yeni tasarımın kart dili; MOTOR mevcut asistan akışı.
   Sohbet balonu/tam ekranla AYNI `THREAD`i kullanır — üç kap da
   `data-thread` taşır ve `renderThread()` hepsini birlikte çizer. */
MERCEK_CIZ["genel/asistan"] = {
  filtreler: () => [],
  ciz(dugum) {
    setTimeout(() => {
      refreshAssistantStatus();
      renderThread();
      bindComposer();
      veri("asMimari",
        () => api.get("/api/assistant/architecture"),
        m => cubuklar((m.components || []).map(c => [
          c.file.split("/").pop(), c.status === "hazır" ? 100 : 40,
          c.status, c.status !== "hazır"])) +
          altBaslik("Sonraki adımlar") +
          tablo(["Adım"], (m.next_steps || []).map(a => [fmt.esc(a)])),
        { iskelet: 4 });
    }, 0);

    return kutular(
      kutu("Model", "Gemini", "bulut API; yalnızca kurum verisiyle cevap verir") +
      kutu("Sayı kaynağı", "structured_result", "LLM metninden sayı ayrıştırılmaz") +
      kutu("Kapsam", fmt.esc(dugum.kisa), "sorular bu birime göre yanıtlanır")
    ) +
    izgara("k32",
      kart("Sohbet", "Yerel model kurum verisini gerçek kayıtlardan okur.",
        `<div id="asistanDurum"></div>
         <div id="assistantThread" class="assistant-thread" data-thread></div>
         <div id="assistantViewPanel" class="ai-panel" hidden></div>
         <form id="assistantForm" class="yaz" autocomplete="off">
           <input id="assistantInput" maxlength="4000"
             placeholder="Sorunuzu yazın… (Enter gönderir)">
           <button class="ana-btn" id="assistantSend" type="submit">➤</button>
         </form>
         <div class="not" style="display:flex;justify-content:space-between;margin-top:8px">
           <span id="assistantCounter">0 / 4000</span>
           <button class="fcip" id="assistantReset" type="button">Yeni konuşma</button>
         </div>`),
      kart("Asistan mimarisi", "Hangi katman hazır, sırada ne var.",
        `<div id="asMimari">${iskelet(4)}</div>`));
  },
};

/* ==========================================================================
   MÜFREDAT VE DERSLER  (Programlar ve Müfredat › Müfredat)
   --------------------------------------------------------------------------
   Aktarılan 1205 gerçek müfredat satırını görünür kılar. Sürdürülebilirlik
   puanının arkasında kalmaz: bu hub'ın ilk sekmesidir.

   VERİ KALİTESİ GİZLENMEZ
   43 satırda ders adı PDF ayrıştırma artığıdır. Bu satırlar silinmez ve
   temizmiş gibi de gösterilmez: ayrı sayılır, tabloda "doğrulanmamış"
   etiketiyle işaretlenir ve filtreyle tek başına incelenebilir.
   ========================================================================== */
MERCEK_CIZ["program/mufredat"] = {
  filtreler: () => [
    { id: "ara", tip: "arama", yer: "Ders kodu veya adı ara…" },
  ],
  ciz(dugum, F = {}) {
    const p = kapsamParam(dugum.id);
    const suzgec = { ...p };
    if (F.ara) suzgec.search = F.ara;

    setTimeout(() => {
      veri("mfKutular",
        () => api.get("/api/curriculum/overview", p),
        o => kutular(
          kutu("Ders", fmtSayi(o.total_course_count), "müfredatta") +
          kutu("Sınıfa atanan", fmtSayi(o.classified_course_count),
            "ders kodundan") +
          kutu("Bölüm", fmtSayi(o.department_count), "ders kaydı olan") +
          kutu("Kaynak belge", fmtSayi((o.source_types || []).length), "farklı")
        ), { iskelet: 2 });

      // SINIF AKORDİYONU — her program için aynı biçimde çalışır.
      veri("mfSinif",
        () => api.get("/api/curriculum/by-class-year", suzgec),
        (gruplar, hedef) => {
          if (!gruplar.length) return bosDurum("Bu aramayla eşleşen ders yok.");
          const html = gruplar.map((g, i) => `
            <div class="sinif-blok">
              <button class="sinif-bas" data-sinif="${i}"
                      aria-expanded="${i === 0}">
                <span class="ok">▸</span>
                <span class="ad">${fmt.esc(g.label)}</span>
                <span class="adet">${fmtSayi(g.course_count)} ders</span>
              </button>
              <div class="sinif-ic" data-sinif-ic="${i}"
                   ${i === 0 ? "" : "hidden"}>
                ${tablo(["Kod", "Ders", "Program / Bölüm", "Kaynak"],
                  g.courses.map(c => [
                    c.course_code ? `<code>${fmt.esc(c.course_code)}</code>` : "—",
                    fmt.esc(c.course_name),
                    fmt.esc(c.academic_program_name || c.department_name || "—"),
                    fmt.esc(c.source_type || "—"),
                  ]))}
              </div>
            </div>`).join("");
          hedef.innerHTML = html;
          sinifAkordiyonuBagla(hedef);
          return html;
        }, { iskelet: 8 });

      veri("mfBolum",
        () => api.get("/api/curriculum/by-department", p),
        rows => tablo(
          ["Bölüm", "Ders", "Akademisyen", "Ders/Akademisyen"],
          rows.map(r => [
            fmt.esc(r.department_name),
            fmtSayi(r.course_count),
            fmtSayi(r.academic_staff_count),
            r.courses_per_staff === null ? "—" : fmtOndalik(r.courses_per_staff, 1),
          ])
        ));

      veri("mfKapasite",
        () => api.get("/api/decision-analytics/curriculum-load", p),
        o => {
          if (!o.available) return bosDurum("Müfredat veya kadro verisi yok.");
          const k = o.curriculum_coverage || {};
          return cubuklar([
            ["Müfredat dersi", o.curriculum_course_count, fmtSayi(o.curriculum_course_count)],
            ["Akademik personel", o.academic_staff_count, fmtSayi(o.academic_staff_count)],
          ]) + altBaslik("Akademisyen başına ders") +
            `<div class="buyuk-sayi">${fmtOndalik(o.courses_per_academic_staff, 1)}</div>` +
            (k.coverage_percent === null || k.coverage_percent === undefined ? "" :
              `<p class="kucuk-not">Katalogdaki derslerin ` +
              `<b>%${fmtOndalik(k.coverage_percent, 1)}</b>'i için ders kaydı ` +
              `eşleşiyor (${fmtSayi(k.matched_curriculum_course_count)} / ` +
              `${fmtSayi(k.curriculum_course_count)}).</p>`);
        });
    }, 0);

    return `<div id="mfKutular">${iskelet(2)}</div>` +
      kart("Sınıflara göre dersler",
        "Sınıf, ders kodundaki üç haneli sayının ilk basamağından gelir. " +
        "Bir sınıfa tıklayarak ders listesini açın.",
        `<div id="mfSinif">${iskelet(8)}</div>`, { stil: "margin-top:14px" }) +
      `<div class="izgara k2" style="margin-top:14px">` +
      kart("Müfredat büyüklüğü ve öğretim kapasitesi",
        "Ders sayısı tek başına yeterli değildir: aynı sayı farklı kadro " +
        "büyüklüklerinde farklı anlama gelir.",
        `<div id="mfKapasite">${iskelet(5)}</div>`) +
      kart("Bölüm bazında ders yükü", "Ders sayısı ve kadro birlikte.",
        `<div id="mfBolum">${iskelet(6)}</div>`) +
      `</div>`;
  },
};

/* Sınıf bloklarını açıp kapatır. Dinleyici KAPSAYICIYA bağlanır:
   `veri()` içeriği yeniden çizdiğinde tek tek düğme dinleyicileri
   kaybolurdu. */
function sinifAkordiyonuBagla(kap) {
  if (kap.dataset.sinifBagli === "1") return;
  kap.dataset.sinifBagli = "1";
  kap.addEventListener("click", e => {
    const btn = e.target.closest("[data-sinif]");
    if (!btn || !kap.contains(btn)) return;
    const ic = kap.querySelector(`[data-sinif-ic="${btn.dataset.sinif}"]`);
    if (!ic) return;
    const acik = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!acik));
    ic.hidden = acik;
  });
}

/* ==========================================================================
   DERS YÜKÜ VE YETERLİLİK  (Akademik Personel › Ders Yükü)
   --------------------------------------------------------------------------
   Karar destek göstergeleri; hepsi GERÇEKTEN dolu tablolardan gelir.
   Veri olmayan gösterge için kart basılmaz (bkz. `varsaKutu`).
   ========================================================================== */

MERCEK_CIZ["personel/yuk"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      veri("dyKutular",
        () => api.get("/api/decision-analytics/staffing", p),
        o => kutular(
          varsaKutu("Akademik personel", fmtSayi(o.academic_staff_count), "kişi") +
          varsaKutu("Öğrenci", fmtSayi(o.student_count), "toplam") +
          varsaKutu("Öğrenci / akademisyen",
            fmtOndalik(o.students_per_academic_staff, 1), "tüm kadro",
            o.students_per_academic_staff > 40 ? "kotu"
              : o.students_per_academic_staff > 25 ? "uyari" : "iyi") +
          // Ders veren kadro üzerinden oran, gerçek sınıf yükünü gösterir.
          varsaKutu("Öğrenci / ders veren",
            fmtOndalik(o.students_per_active_teaching_staff, 1),
            `${fmtSayi(o.active_teaching_staff_count)} kişi ders veriyor`,
            o.students_per_active_teaching_staff > 60 ? "kotu"
              : o.students_per_active_teaching_staff > 35 ? "uyari" : "iyi") +
          varsaKutu("100 öğrenciye akademisyen",
            fmtOndalik(o.academics_per_100_students, 2), "kişi") +
          varsaKutu("Ortalama ders yükü",
            fmtOndalik(o.average_teaching_load_hours, 1), "saat / hafta") +
          varsaKutu("Akademisyen başına yayın",
            fmtOndalik(o.average_publications_per_academic, 1), "yayın")
        ), { iskelet: 2 });

      veri("dyDagilim",
        () => api.get("/api/decision-analytics/teaching-load", p),
        o => {
          if (!o.available) return bosDurum(o.note || "Ders yükü verisi yok.");
          return cubuklar(o.bands.map(b =>
            [b.label, b.staff_count, fmtSayi(b.staff_count)])) +
            altBaslik("Özet") + cubuklar([
              ["En düşük", o.min_hours, `${o.min_hours} saat`],
              ["Ortanca", o.median_hours, `${o.median_hours} saat`],
              ["En yüksek", o.max_hours, `${o.max_hours} saat`],
            ]) +
            (o.top20_percent_share === null ? "" :
              altBaslik("Yük yoğunlaşması") +
              `<p class="kucuk-not">Toplam ders yükünün ` +
              `<b>%${fmtOndalik(o.top20_percent_share, 1)}</b>'ini en yüklü ` +
              `${fmtSayi(o.top20_percent_staff_count)} akademisyen taşıyor.</p>`) +
            `<p class="kucuk-not">${fmtSayi(o.measured_staff_count)} akademisyenin ` +
            `ders yükü ölçüldü; ${fmtSayi(o.staff_without_load)} kişide bu ` +
            `dönem için ders kaydı yok.</p>`;
        });

      veri("dyTrend",
        () => api.get("/api/decision-analytics/teaching-load/trend", p),
        rows => rows.length ? cizgiGrafik(rows.map(r => r.academic_year), [
          { ad: "Toplam saat", renk: "#f2a33c", alan: true,
            veri: rows.map(r => Number(r.total_weekly_hours || 0)) },
          { ad: "Ders veren akademisyen", renk: "#4c8dff",
            veri: rows.map(r => Number(r.teaching_staff_count)) },
        ], { min: 0 }) : bosDurum("Ders geçmişi verisi yok."));

      veri("dyProgram",
        () => api.get("/api/decision-analytics/staffing/by-program", p),
        rows => tablo(
          ["Program", "Bölüm", "Öğrenci", "Akademisyen", "Öğrenci/Akademisyen"],
          rows.map(r => [
            fmt.esc(r.program_name),
            fmt.esc(r.department_name || "—"),
            r.student_count === null ? "—" : fmtSayi(r.student_count),
            fmtSayi(r.academic_staff_count),
            { icerik: r.students_per_academic_staff === null ? "—"
                : fmtOndalik(r.students_per_academic_staff, 1),
              sinif: r.students_per_academic_staff > 40 ? "kotu"
                : r.students_per_academic_staff > 25 ? "uyari" : "iyi" },
          ])
        ));

      veri("dyMufredat",
        () => api.get("/api/decision-analytics/curriculum-load", p),
        o => {
          if (!o.available) return bosDurum("Müfredat veya kadro verisi yok.");
          const k = o.curriculum_coverage || {};
          return cubuklar([
            ["Müfredat dersi", o.curriculum_course_count, fmtSayi(o.curriculum_course_count)],
            ["Akademik personel", o.academic_staff_count, fmtSayi(o.academic_staff_count)],
          ]) + altBaslik("Akademisyen başına ders") +
            `<div class="buyuk-sayi">${fmtOndalik(o.courses_per_academic_staff, 1)}</div>` +
            (k.coverage_percent === null || k.coverage_percent === undefined ? "" :
              altBaslik("Ders kayıtlarıyla eşleşen müfredat") +
              cubuklar([["Eşleşen", k.matched_curriculum_course_count,
                         `${fmtSayi(k.matched_curriculum_course_count)} / ` +
                         `${fmtSayi(k.curriculum_course_count)} (%${
                           fmtOndalik(k.coverage_percent, 1)})`]],
                       { maks: k.curriculum_course_count })) +
            (o.staff_teaching_multiple_courses
              ? `<p class="kucuk-not">${fmtSayi(o.staff_teaching_multiple_courses)} ` +
                `akademisyen birden çok farklı ders veriyor; ders kaydı olan ` +
                `kişi başına ortalama ${fmtOndalik(o.average_distinct_courses_per_teaching_staff, 1)} ` +
                `farklı ders.</p>` : "");
        });

      veri("dyYogunlasma",
        () => api.get("/api/decision-analytics/course-concentration", p),
        o => {
          if (!o.available) return bosDurum(o.note || "Ders kaydı yok.");
          return cubuklar([
            ["En yüklü %20'nin payı", o.top20_percent_share,
             `%${fmtOndalik(o.top20_percent_share, 1)}`, true],
          ], { maks: 100 }) +
            altBaslik("Dayanıklılık") +
            cubuklar([
              ["Ders veren akademisyen", o.teaching_staff_count, fmtSayi(o.teaching_staff_count)],
              ["Toplam ders kaydı", o.total_course_records, fmtSayi(o.total_course_records)],
              ["Bir kişinin en fazla dersi", o.max_courses_by_one_staff,
               fmtSayi(o.max_courses_by_one_staff)],
              ["Ortanca ders sayısı", o.median_courses_per_staff,
               fmtSayi(o.median_courses_per_staff)],
            ]) +
            `<p class="kucuk-not">Pay yükseldikçe öğretim az sayıda kişiye ` +
            `bağımlı hâle gelir; ayrılma veya izin durumunda müfredat riske girer.</p>`;
        });

      veri("dyUcDeger",
        () => api.get("/api/decision-analytics/teaching-load", p),
        o => {
          if (!o.available) return bosDurum(o.note || "Ders yükü verisi yok.");
          return altBaslik("En yüksek ders yükü") +
            tablo(["Ad", "Unvan", "Saat"],
              (o.highest_load_staff || []).map(k => [
                fmt.esc(k.full_name), fmt.esc(k.title || "—"),
                fmtSayi(k.teaching_load_hours)])) +
            altBaslik("Ders veren en düşük yüklü") +
            tablo(["Ad", "Unvan", "Saat"],
              (o.lowest_load_active_staff || []).map(k => [
                fmt.esc(k.full_name), fmt.esc(k.title || "—"),
                fmtSayi(k.teaching_load_hours)]));
        });
    }, 0);

    return `<div id="dyKutular">${iskelet(2)}</div>` +
      izgara("k32",
        kart("Ders yükü dağılımı",
          "Ortalama tek başına yanıltıcıdır: aynı ortalama, dengeli bir " +
          "dağılımı da birkaç kişide yığılmayı da tarif edebilir.",
          `<div id="dyDagilim">${iskelet(6)}</div>`),
        kart("Müfredat yükü", "Ders sayısı ve kadro büyüklüğü.",
          `<div id="dyMufredat">${iskelet(4)}</div>`)) +
      `<div class="izgara k2" style="margin-top:14px">` +
      kart("Yıllara göre ders yükü",
        "Toplam haftalık saat ve o yıl ders veren akademisyen sayısı.",
        `<div id="dyTrend">${iskelet(5)}</div>`) +
      kart("Öğretim yoğunlaşması",
        "Öğretim kaç kişiye bağımlı? Kadro planlaması için kırılganlık sinyali.",
        `<div id="dyYogunlasma">${iskelet(5)}</div>`) +
      `</div>` +
      `<div class="izgara k2" style="margin-top:14px">` +
      kart("Uç değerler", "En yüksek ve en düşük ders yükü taşıyan akademisyenler.",
        `<div id="dyUcDeger">${iskelet(6)}</div>`) +
      kart("Program bazında kadro yeterliliği",
        "Kadro bölüme bağlıdır; satırlar programın bağlı olduğu bölümün " +
        "kadrosunu gösterir.",
        `<div id="dyProgram">${iskelet(6)}</div>`) +
      `</div>`;
  },
};


/* ==========================================================================
   AKADEMİSYEN DERS AKORDİYONU
   --------------------------------------------------------------------------
   Personel tablosunda bir ada tıklanınca, o satırın HEMEN ALTINA yeni bir
   satır eklenir ve kişinin ders geçmişi orada açılır. Ayrı bir sayfaya
   gitmek yerine satır içi açmak, kullanıcıyı listedeki yerinden koparmaz.

   Veri `/api/curriculum/staff/{id}/courses` ucundan gelir; kaynağı YÖK
   Akademik'in kişi bazlı ders geçmişidir. Saat bilgisi olmayan ders
   0 saat sayılmaz, "—" görünür.
   ========================================================================== */
function personelAkordiyonuBagla(kap) {
  // Dinleyici KAPSAYICIYA bir kez bağlanır. Tablo yeniden çizildiğinde
  // içerik değişir ama kapsayıcı aynı kalır; tek tek düğmelere bağlanan
  // dinleyiciler her çizimde kaybolurdu.
  if (kap.dataset.akordiyonBagli === "1") return;
  kap.dataset.akordiyonBagli = "1";

  kap.addEventListener("click", async e => {
    const btn = e.target.closest("[data-personel]");
    if (!btn || !kap.contains(btn)) return;
    {
      const satir = btn.closest("tr");
      const acik = satir.nextElementSibling;

      // Aynı kişiye ikinci tıklama akordiyonu kapatır.
      if (acik && acik.classList.contains("akordiyon-satir")) {
        acik.remove();
        btn.setAttribute("aria-expanded", "false");
        return;
      }
      // Başka bir kişi açıksa önce o kapanır: aynı anda tek panel.
      kap.querySelectorAll(".akordiyon-satir").forEach(t => t.remove());
      kap.querySelectorAll("[data-personel]").forEach(b =>
        b.setAttribute("aria-expanded", "false"));

      const sutun = satir.children.length;
      const yeni = document.createElement("tr");
      yeni.className = "akordiyon-satir";
      yeni.innerHTML = `<td colspan="${sutun}">${iskelet(3)}</td>`;
      satir.after(yeni);
      btn.setAttribute("aria-expanded", "true");

      try {
        const d = await api.get(
          `/api/curriculum/staff/${encodeURIComponent(btn.dataset.personel)}/courses`);
        yeni.querySelector("td").innerHTML = personelDersleriHtml(d);
        gecmisAkordiyonuBagla(yeni);
      } catch (err) {
        yeni.querySelector("td").innerHTML = hataDurum(err);
      }
    }
  });
}

function personelDersleriHtml(d) {
  if (!d.years || !d.years.length) {
    return bosDurum(`${d.full_name} için kaynakta ders kaydı yok.`);
  }

  const yilBlogu = y => `
    <div class="akordiyon-yil">
      <div class="akordiyon-yil-bas">
        <span class="yil">${fmt.esc(y.academic_year)}</span>
        <span class="kucuk-not">${fmtSayi(y.course_count)} ders${
          y.total_weekly_hours === null ? ""
            : ` · ${fmtSayi(y.total_weekly_hours)} saat/hafta`}</span>
      </div>
      ${tablo(["Kod", "Ders", "Dil", "Saat", "Program / Bölüm"],
        y.courses.map(c => [
          c.course_code ? `<code>${fmt.esc(c.course_code)}</code>` : "—",
          fmt.esc(c.course_name),
          fmt.esc(c.language || "—"),
          c.weekly_hours === null ? "—" : fmtSayi(c.weekly_hours),
          fmt.esc(c.academic_program_name || c.department_name || "—"),
        ]))}
    </div>`;

  /* CARİ DÖNEM ÖNCE. Yönetim ekranı 30 yıllık geçmişi değil, bu yılın
     yükünü gösterir; geçmiş ikincil bir bölümde durur. */
  const cari = d.current
    ? `<div class="akordiyon-ozet">
         <b>Cari dönem · ${fmt.esc(d.current_academic_year || "")}</b> —
         ${fmtSayi(d.current_course_count)} ders,
         ${fmtSayi(d.current_distinct_course_count)} farklı ders${
           d.current_weekly_hours === null ? ""
             : `, ${fmtSayi(d.current_weekly_hours)} saat/hafta`}
       </div>${yilBlogu(d.current)}`
    : `<div class="akordiyon-ozet">
         <b>Cari dönem · ${fmt.esc(d.current_academic_year || "")}</b> —
         bu dönem için ders kaydı yok.
       </div>`;

  const gecmis = (d.history_years || []).length
    ? `<div class="gecmis-blok">
         <button class="sinif-bas" data-gecmis="1" aria-expanded="false">
           <span class="ok">▸</span>
           <span class="ad">Geçmiş Yıllar</span>
           <span class="adet">${fmtSayi(d.history_year_count)} yıl ·
             ${fmtSayi(d.total_course_count - d.current_course_count)} ders</span>
         </button>
         <div class="sinif-ic" data-gecmis-ic="1" hidden>
           ${d.history_years.map(yilBlogu).join("")}
           ${(d.repeated_courses || []).length
             ? altBaslik("Yıllar boyunca tekrarlanan dersler") +
               tablo(["Ders", "Yıl sayısı", "Yıllar"],
                 d.repeated_courses.slice(0, 8).map(r => [
                   fmt.esc(r.course_name),
                   fmtSayi(r.year_count),
                   fmt.esc(r.years.join(", ")),
                 ]))
             : ""}
         </div>
       </div>`
    : "";

  return `<div class="akordiyon-ic">
    <div class="akordiyon-ozet">
      <b>${fmt.esc(d.full_name)}</b> · ${fmt.esc(d.title || "—")}
    </div>${cari}${gecmis}</div>`;
}

/* "Geçmiş Yıllar" bölümünü açar/kapatır. */
function gecmisAkordiyonuBagla(kap) {
  kap.addEventListener("click", e => {
    const btn = e.target.closest("[data-gecmis]");
    if (!btn || !kap.contains(btn)) return;
    const ic = kap.querySelector("[data-gecmis-ic]");
    if (!ic) return;
    const acik = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!acik));
    ic.hidden = acik;
  });
}

/* ==========================================================================
   YKS TALEP TRENDİ  (Öğrenciler › Talep ve Yerleştirme)
   --------------------------------------------------------------------------
   4 yıllık ÖSYM verisi: kontenjan, yerleşen, doluluk, taban puan, başarı
   sırası ve bunların yıllık değişimi. Tek yıllık veriden yön okunamayacağı
   için momentum en az iki yıl ister.
   ========================================================================== */
MERCEK_CIZ["ogrenci/talep"] = {
  filtreler: () => [],
  ciz(dugum) {
    const p = kapsamParam(dugum.id);
    setTimeout(() => {
      veri("ytKutular",
        () => api.get("/api/decision-analytics/yks-trend", p),
        o => {
          if (!o.available) return bosDurum("Bu kapsamda YKS verisi yok.");
          const son = o.years[o.years.length - 1];
          const m = o.momentum || {};
          return kutular(
            kutu("Kontenjan", fmtSayi(son.quota), son.academic_year) +
            kutu("Yerleşen", fmtSayi(son.placed_students), son.academic_year) +
            varsaKutu("Doluluk", fmtYuzde(son.occupancy_percent, 1), son.academic_year,
              son.occupancy_percent >= 90 ? "iyi"
                : son.occupancy_percent >= 70 ? "uyari" : "kotu") +
            varsaKutu("Taban puan", fmtOndalik(son.best_base_score, 2), "en yüksek") +
            varsaKutu("Başarı sırası", fmtSayi(son.best_success_rank), "en iyi") +
            (m.available
              ? kutu("Talep yönü", m.direction,
                  `${m.improving_signals}/${m.measured_signal_count} sinyal iyileşiyor`,
                  m.direction === "artıyor" ? "iyi"
                    : m.direction === "azalıyor" ? "kotu" : "")
              : "")
          );
        }, { iskelet: 2 });

      veri("ytKontenjan",
        () => api.get("/api/decision-analytics/yks-trend", p),
        o => o.available ? cizgiGrafik(o.years.map(y => y.academic_year), [
          { ad: "Kontenjan", renk: "#4c8dff", veri: o.years.map(y => Number(y.quota || 0)) },
          { ad: "Yerleşen", renk: "#2ec4a6", alan: true,
            veri: o.years.map(y => Number(y.placed_students || 0)) },
        ], { min: 0 }) : bosDurum("YKS verisi yok."));

      veri("ytDoluluk",
        () => api.get("/api/decision-analytics/yks-trend", p),
        o => o.available ? cizgiGrafik(o.years.map(y => y.academic_year), [
          { ad: "Doluluk %", renk: "#f2a33c", alan: true,
            veri: o.years.map(y => Number(y.occupancy_percent || 0)) },
        ], { min: 0 }) : bosDurum("YKS verisi yok."));

      veri("ytPuan",
        () => api.get("/api/decision-analytics/yks-trend", p),
        o => {
          if (!o.available) return bosDurum("YKS verisi yok.");
          // Taban puan ve başarı sırası FARKLI ölçeklerdedir; aynı eksene
          // koymak grafiği okunamaz yapar. İki ayrı seri, iki ayrı grafik.
          const puanli = o.years.filter(y => y.best_base_score !== null);
          if (!puanli.length) return bosDurum("Taban puan verisi yok.");
          return cizgiGrafik(puanli.map(y => y.academic_year), [
            { ad: "Taban puan", renk: "#9b7ff0", alan: true,
              veri: puanli.map(y => Number(y.best_base_score)) },
          ]) + altBaslik("Başarı sırası (küçük = iyi)") +
            cizgiGrafik(puanli.map(y => y.academic_year), [
              { ad: "Sıra", renk: "#e0679b",
                veri: puanli.map(y => Number(y.best_success_rank || 0)) },
            ]);
        });

      veri("ytDegisim",
        () => api.get("/api/decision-analytics/yks-trend", p),
        o => o.available ? tablo(
          ["Yıl", "Kontenjan", "Δ Kontenjan", "Yerleşen", "Δ Yerleşen",
           "Doluluk", "Δ Doluluk"],
          o.years.map(y => [
            fmt.esc(y.academic_year),
            fmtSayi(y.quota),
            // İlk yılda önceki yıl yok; "—" gösterilir, 0 değil.
            { icerik: y.quota_change_percent === null ? "—"
                : fmtYuzde(y.quota_change_percent, 1),
              sinif: y.quota_change_percent > 0 ? "iyi"
                : y.quota_change_percent < 0 ? "kotu" : "" },
            fmtSayi(y.placed_students),
            { icerik: y.placed_change_percent === null ? "—"
                : fmtYuzde(y.placed_change_percent, 1),
              sinif: y.placed_change_percent > 0 ? "iyi"
                : y.placed_change_percent < 0 ? "kotu" : "" },
            fmtYuzde(y.occupancy_percent, 1),
            { icerik: y.occupancy_change_points === null ? "—"
                : fmtOndalik(y.occupancy_change_points, 1) + " puan",
              sinif: y.occupancy_change_points > 0 ? "iyi"
                : y.occupancy_change_points < 0 ? "kotu" : "" },
          ])
        ) : bosDurum("YKS verisi yok."));
    }, 0);

    return `<div id="ytKutular">${iskelet(2)}</div>` +
      izgara("k32",
        kart("Kontenjan ve yerleşen", "4 yıllık ÖSYM yerleştirme verisi.",
          `<div id="ytKontenjan">${iskelet(5)}</div>`),
        kart("Doluluk seyri", "Yerleşen / kontenjan oranı.",
          `<div id="ytDoluluk">${iskelet(5)}</div>`)) +
      `<div class="izgara k2" style="margin-top:14px">` +
      kart("Taban puan ve başarı sırası",
        "İki gösterge farklı ölçeklerde olduğu için ayrı çizilir.",
        `<div id="ytPuan">${iskelet(5)}</div>`) +
      kart("Yıllık değişim", "Bir önceki yıla göre kontenjan, yerleşen ve doluluk.",
        `<div id="ytDegisim">${iskelet(5)}</div>`) +
      `</div>`;
  },
};
