/* ==========================================================================
   DERSLİK KULLANIM HARİTASI — Altyapı / Fiziksel Kaynaklar
   --------------------------------------------------------------------------
   Kat planı görselinin üzerine, gerçek ders programından türetilmiş
   kullanım yoğunluğunu bindirir.

   KAPSAM: yalnızca `alHarita` paneli. Global grafik yardımcılarına
   (`yatayCubuk`, `gruplandirilmisCubuk` …) dokunmaz, yeni modal sistemi
   kurmaz — panel mevcut `panel()`/`doldur()`/⛶ altyapısını kullanır.

   VERİ: `/api/physical-resources/classroom-usage-map` (salt okunur).
   Sunucu tam veri kümesini bir kez yayınlar; gün/saat/kat süzgeçleri
   burada uygulanır. Böylece her açılır liste değişimi ağ isteği
   atmadan anında sonuçlanır.

   UYDURMA YOK: kaynakta programı olmayan oda "veri yok" olarak
   gösterilir, sıfır doluluk sayılmaz; kapasitesi yazmayan oda "—".
   ========================================================================== */

/** Panelin kendi durumu. Ekran state'ine (K) karışmaz. */
const DH = {
  veri: null,
  gun: "Pazartesi",
  slot: "all",     // "all" | slot index (sayı)
  kat: 0,          // TEK kat gösterilir; "Tümü" seçeneği YOKTUR
  secili: null,    // tıklanan oda (kalıcı bilgi paneli)

  /* --- DERSLİK EŞLEŞTİRME MODU ---------------------------------------
     `alanlar` KALICI veridir: backend'deki `room_schedule_mapping.json`
     dosyasından gelir ve 💾 Kaydet ile oraya geri yazılır. Tarayıcı
     belleğinde tutulan geçici bir durum DEĞİLDİR — ama kaydedilene
     kadar da diske yazılmaz, bu yüzden `kirli` bayrağı kullanıcıya
     kaydedilmemiş değişiklik olduğunu söyler. */
  mod: false,          // eşleştirme modu açık mı
  alanlar: [],         // [{area_id, floor, shape, room_code, label}]
  atanabilir: [],      // Excel'den gelen gerçek derslik listesi
  kaydedilme: null,    // son kayıt zamanı (sunucudan)
  kirli: false,        // kaydedilmemiş değişiklik var mı
  seciliAlan: null,    // düzenlenen area_id
  ciziliyor: null,     // {kat, x0, y0, x1, y1} — sürükleme sırasında
  mesaj: null,         // {tur:"hata"|"ok", metin}
  plan: null,          // floor_plans.json — gerçek oda poligonları
};

/** Yeni alan kimliği — çakışmayacak biçimde. */
function dhYeniAlanId() {
  let n = DH.alanlar.length + 1;
  const mevcut = new Set(DH.alanlar.map(a => a.area_id));
  while (mevcut.has("a" + n)) n++;
  return "a" + n;
}

/** Yoğunluk kovaları — oran (0..1) → renk + etiket.
 *  Eşikler SABİT SLOT SAYISINA göre değil, ORANA göredir; kaynaktaki
 *  gerçek slot sayısı değişirse skala kendiliğinden uyar. */
const DH_KOVA = [
  { esik: 0.001, ad: "Boş", renk: "#2f9e64" },
  { esik: 0.25, ad: "Düşük", renk: "#7fc45f" },
  { esik: 0.50, ad: "Orta", renk: "#e0b341" },
  { esik: 0.75, ad: "Yüksek", renk: "#e08341" },
  { esik: 1.01, ad: "Çok yüksek", renk: "#d9534f" },
];
const DH_VERI_YOK = "#4a5568";

function dhKova(oran) {
  if (oran === null || oran === undefined) return { ad: "Veri yok", renk: DH_VERI_YOK };
  for (const k of DH_KOVA) if (oran < k.esik) return k;
  return DH_KOVA[DH_KOVA.length - 1];
}

/** Bir odanın seçili gün/saat için durumu.
 *  Programı yoksa `null` döner — SIFIR DEĞİL. "Boş" ile "bilinmiyor"
 *  aynı şey değildir; ikisini karıştırmak doluluk oranını bozar. */
function dhDurum(oda) {
  if (!oda.has_schedule || !oda.schedule) return { veriVar: false };
  const gunluk = oda.schedule[DH.gun] || [];
  if (DH.slot === "all") {
    const toplam = gunluk.length;
    const dolu = gunluk.filter(Boolean).length;
    return { veriVar: true, kip: "gun", dolu, toplam,
             oran: toplam ? dolu / toplam : null };
  }
  const ders = gunluk[DH.slot] || null;
  return { veriVar: true, kip: "slot", ders, dolu: ders ? 1 : 0, toplam: 1,
           oran: ders ? 1 : 0 };
}

function dhRenk(oda) {
  const d = dhDurum(oda);
  if (!d.veriVar) return DH_VERI_YOK;
  if (d.kip === "slot") return d.ders ? "#d9534f" : "#2f9e64";
  return dhKova(d.oran).renk;
}

const dhSayi = v => (v === null || v === undefined ? "—" : v);

/** İpucu metni — yalnızca kaynakta olan alanlar yazılır. */
function dhIpucu(oda) {
  const d = dhDurum(oda);
  const satir = [
    `${oda.room_code}${oda.name ? " · " + oda.name : ""}`,
    `Kat ${oda.floor}`,
    `Kapasite: ${dhSayi(oda.class_capacity)} (öğrenci: ${dhSayi(oda.student_capacity)})`,
  ];
  if (oda.owner_unit) satir.push(`Birim: ${oda.owner_unit}`);
  if (!d.veriVar) {
    satir.push("Durum: programda yok (veri yok)");
  } else if (d.kip === "slot") {
    satir.push(`Durum: ${d.ders ? "Dolu" : "Boş"}`);
    if (d.ders) satir.push(`Ders: ${d.ders}`);
    const etiket = (oda.slot_labels || [])[DH.slot];
    if (etiket) satir.push(`Saat: ${etiket}`);
  } else {
    satir.push(`${DH.gun}: ${d.dolu}/${d.toplam} slot dolu`
      + ` (%${fmt.dec(d.oran * 100, 0)})`);
    satir.push(`Yoğunluk: ${dhKova(d.oran).ad}`);
  }
  return satir.join("\n");
}

/* -------------------------------------------------------------------------
   ÖZET KPI — seçili süzgece göre yeniden hesaplanır.
   Sayfadaki mevcut kapasite KPI'larını TEKRAR ETMEZ: buradakiler
   zaman boyutuna bağlı kullanım ölçüleridir, envanter sayısı değil.
   ------------------------------------------------------------------------- */
function dhOzet(odalar) {
  const olculen = odalar.filter(o => dhDurum(o).veriVar);
  const saatli = DH.slot !== "all";
  const dolu = olculen.filter(o => dhDurum(o).dolu > 0).length;
  const bos = olculen.length - dolu;

  let ortalama = null;
  if (!saatli && olculen.length) {
    /* Oranların ortalaması DEĞİL: toplam dolu slot / toplam slot.
       Oran ortalaması küçük odaları büyükler kadar ağırlıklandırır. */
    const t = olculen.reduce((a, o) => {
      const d = dhDurum(o); return { d: a.d + d.dolu, t: a.t + d.toplam };
    }, { d: 0, t: 0 });
    ortalama = t.t ? t.d / t.t : null;
  }

  // En yoğun kat — yalnızca ölçülen odalar üzerinden.
  const katlar = {};
  olculen.forEach(o => {
    const d = dhDurum(o);
    const k = katlar[o.floor] || (katlar[o.floor] = { d: 0, t: 0 });
    k.d += d.dolu; k.t += d.toplam;
  });
  const enYogun = Object.entries(katlar)
    .map(([k, v]) => ({ kat: k, oran: v.t ? v.d / v.t : 0 }))
    .sort((a, b) => b.oran - a.oran)[0];

  return kpi(saatli ? "O Saatte Dolu" : "Kullanılan Derslik",
             `${dolu}`, `${olculen.length} ölçülen derslik içinde`,
             { ikon: "▦", renk: "turuncu" })
    + kpi(saatli ? "O Saatte Boş" : "Hiç Kullanılmayan",
          `${saatli ? bos : olculen.filter(o => dhDurum(o).dolu === 0).length}`,
          saatli ? "boş derslik" : `${DH.gun} günü boyunca`,
          { ikon: "○", renk: "yesil" })
    + (saatli ? "" : kpi("Ortalama Kullanım",
        ortalama === null ? "—" : fmt.pct(ortalama * 100, 1),
        "dolu slot / toplam slot", { ikon: "%", renk: "mavi" }))
    + (enYogun ? kpi("En Yoğun Kat", `Kat ${enYogun.kat}`,
        fmt.pct(enYogun.oran * 100, 1) + " kullanım",
        { ikon: "▲", renk: "mor" }) : "");
}

/* -------------------------------------------------------------------------
   SÜZGEÇLER — saat seçenekleri Excel'den gelir, sabit yazılmaz.
   ------------------------------------------------------------------------- */
function dhSuzgecler(v) {
  const sec = (id, etiket, secenekler, deger) => `
    <span class="evren-sec dh-sec">
      <label for="${id}">${esc(etiket)}</label>
      <select id="${id}">${secenekler.map(o =>
        `<option value="${esc(o.d)}"${String(o.d) === String(deger) ? " selected" : ""}>${
          esc(o.a)}</option>`).join("")}</select>
    </span>`;
  return `<div class="dh-suzgec">
    ${sec("dhGun", "Gün", v.days.map(g => ({ d: g, a: g })), DH.gun)}
    ${/* TEK KAT: "Tümü" seçeneği YOKTUR. Üç farklı kat geometrisini
          aynı anda göstermek sayfayı uzatıyor ve hiçbirini okunur
          bırakmıyordu. */""}
    ${sec("dhKat", "Kat", (DH.plan && DH.plan.floors
        ? Object.keys(DH.plan.floors).map(Number).sort((x, y) => x - y)
        : v.floors.map(f => f.floor)).map(f => ({ d: f, a: `Kat ${f}` })), DH.kat)}
    ${sec("dhSaat", "Saat", [{ d: "all", a: "Tümü (günlük yoğunluk)" }].concat(
        v.time_slots.map(s => ({ d: s.index, a: s.label }))), DH.slot)}
  </div>`;
}

function dhLejant() {
  const kutu = (renk, ad) =>
    `<span class="dh-lj"><i style="background:${renk}"></i>${esc(ad)}</span>`;
  return `<div class="dh-lejant">${
    (DH.slot === "all"
      ? DH_KOVA.map(k => kutu(k.renk, k.ad))
      : [kutu("#2f9e64", "Boş"), kutu("#d9534f", "Dolu")]).join("")
  }${kutu(DH_VERI_YOK, "Veri yok")}</div>`;
}

/* -------------------------------------------------------------------------
   KAT GÖRÜNÜMÜ — plan görseli + üzerine konumu KANITLANMIŞ oda işaretleri.
   Konumu olmayan odalar plan üzerinde uydurulmaz; alttaki ızgarada
   tam işlevsel olarak yer alır.
   ------------------------------------------------------------------------- */
/* Base plan + kullanıcı poligonları: derslik-harita-plan.js */

/** Kat görünümü = base mimari plan + sağda günlük ders programı.
 *  Harita ANA GÖRSEL kalır; panel dar bir yan sütundur. Dar ekranda
 *  (CSS) haritanın altına iner. */
function dhKatGorunumu(v, kat) {
  return `<div class="dh-yerlesim">
    <div class="dh-yerlesim-harita">${dhpPlanGovdesi(kat)}</div>
    <aside class="dh-yerlesim-yan">${dhProgramPaneli(v)}</aside>
  </div>`;
}

/** YARDIMCI liste — ana görselleştirme DEĞİLDİR.
 *  Yalnızca plandaki hiçbir alana eşleştirilmemiş derslikleri sayar ve
 *  kompakt biçimde listeler; asıl kullanım bilgisi SVG planın üzerindedir. */
function dhEslesmeyenler(odalar) {
  const atanmis = new Set(DH.alanlar.filter(a => a.room_code).map(a => a.room_code));
  const disarida = odalar.filter(o => !atanmis.has(o.room_code));
  if (!disarida.length) return "";
  return `<details class="dh-kalan"><summary>Plana yerleştirilmemiş
      ${disarida.length} derslik</summary>
    <div class="dh-kalan-ic">${disarida.map(o => {
      const d = dhDurum(o);
      const alt = !d.veriVar ? "veri yok"
        : d.kip === "slot" ? (d.ders ? "dolu" : "boş")
        : `${d.dolu}/${d.toplam}`;
      return `<span class="dh-kalan-oge" title="${esc(dhIpucu(o))}"
        style="border-left-color:${dhRenk(o)}">${esc(o.room_code)}
        <i>${esc(alt)}</i></span>`;
    }).join("")}</div></details>`;
}

/* =========================================================================
   GÜNLÜK DERS PROGRAMI PANELİ — haritanın sağında
   -------------------------------------------------------------------------
   Haritada bir dersliğe tıklanınca o dersliğin SEÇİLİ GÜNDEKİ tam programı
   burada listelenir.

   KAYNAK: yeni bir uç nokta YOKTUR. `classroom-usage-map` zaten her odanın
   `schedule` alanını (gün → 12 slotluk dizi) tek seferde yayınlıyordu;
   panel o veriyi okur. Tıklama başına ağ isteği atılmaz, Excel yeniden
   ayrıştırılmaz.

   SAAT SÜZGECİNDEN BAĞIMSIZDIR: `DH.slot` haritadaki yoğunluk boyamasını
   yönetir; buradaki liste her zaman GÜNÜN TAMAMIDIR. Kullanıcı 10:00'u
   seçtiğinde sağda yalnızca o dersi görmek istemiyor — dersliğin bütün
   gününü görmek istiyor.
   ========================================================================= */

/** Unvan kalıpları — metnin içinde öğretim elemanını GÜVENLE tanımak için. */
const DH_UNVAN = /(Prof\.|Doç\.|Dr\.|Öğr\.\s*Gör\.|Assoc\.|Asst\.|Lect\.|Arş\.\s*Gör\.)/i;

/** Ders kodu: isteğe bağlı birim öneki + harf kümesi + üç hane.
 *  "MYO - BIL 122", "HUK114", "CENG 102", "ceng214" hepsi yakalanır. */
const DH_KOD = /^(?:MYO\s*-?\s*)?([A-ZÇĞİÖŞÜa-zçğıöşü]{2,6})\s*-?\s*(\d{3})\b/;

/** Anlamlı ders olmayan hücreler. Kaynak Excel'de formül hatası ve
 *  serbest not da bulunuyor; bunları ders gibi göstermek yanlış olur. */
const DH_COP = /^(#REF!|#N\/A|#DEĞER!|0)$/i;

/** Slot metnini GÜVENLİ biçimde parçalar.
 *
 *  ÖLÇÜM: kaynakta 474 benzersiz hücre metni var ve yalnızca 84'ü
 *  "CENG 102 (Teorik) - Sec 1 (Ad Soyad)" düzenine uyuyor. Kalanı çok
 *  çeşitli: "HUK114", "IE 242 Cost Analysis in Engineering Dr. Orhan
 *  GERDAN", "MYO - BIL 122 JAVA İLE PROGRAMLAMA II Ş1", "SİMURG
 *  MASTERCLASS"…
 *
 *  Bu yüzden burada AGRESİF ayrıştırma yapılmaz. Yalnızca yanılma payı
 *  düşük olan üç şey ayrılır: ders kodu, (Teorik)/(Lab) etiketi ve
 *  UNVANLA başlayan öğretim elemanı. Geri kalan metin OLDUĞU GİBİ
 *  gösterilir. "Ders adı" diye ayrı bir alan İDDİA EDİLMEZ: çoğu
 *  hücrede ders adıyla eğitmen adı arasında ayraç yok ve nereden
 *  kesileceğini bilmek mümkün değil. Yanlış yerden kesmek, uydurmanın
 *  başka bir biçimi olurdu. */
function dhDersCoz(metin) {
  const ham = String(metin || "").trim().replace(/^"|"$/g, "").trim();
  if (!ham || DH_COP.test(ham)) return null;

  const sonuc = { ham, kod: null, tur: null, kisi: null, sube: null, kalan: "" };
  let kalan = ham;

  const k = DH_KOD.exec(kalan);
  if (k) {
    sonuc.kod = `${k[1].toUpperCase()} ${k[2]}`;
    kalan = kalan.slice(k[0].length);
  }

  const t = /\((Teorik|Lab|Uygulama|teorik|lab|uygulama)\)/.exec(kalan);
  if (t) { sonuc.tur = t[1][0].toUpperCase() + t[1].slice(1).toLowerCase();
           kalan = kalan.replace(t[0], " "); }

  /* Öğretim elemanı YALNIZCA unvanla tanınır. Unvansız bir parantez
     "(MMF)" gibi bir bölüm kısaltması da olabilir; onu kişi adı diye
     göstermek yanlış bilgi olurdu. */
  const par = /\(([^)]*)\)/g;
  let m;
  while ((m = par.exec(kalan)) !== null) {
    if (DH_UNVAN.test(m[1])) {
      sonuc.kisi = m[1].trim();
      kalan = kalan.replace(m[0], " ");
      break;
    }
  }
  if (!sonuc.kisi) {
    /* Ayraçsız biçim: "… Dr. Orhan GERDAN". Unvandan SONRASI kişidir. */
    const u = DH_UNVAN.exec(kalan);
    if (u && u.index > 0) {
      sonuc.kisi = kalan.slice(u.index).trim();
      kalan = kalan.slice(0, u.index);
    }
  }
  if (!sonuc.kisi) {
    /* "- Sec 2 (Hasan Karaaslan)" — kaynaktaki en yaygın düzenli biçim.
       "Sec N" açıkça şube işaretidir; hemen ardından gelen parantez
       unvansız da olsa öğretim elemanıdır. Bu kalıp yeterince dar
       olduğu için "(MMF)" gibi bölüm kısaltmalarıyla karışmaz. */
    const sec = /-?\s*Sec\s*(\d+)\s*\(([^)]+)\)/i.exec(kalan);
    if (sec) {
      sonuc.sube = sec[1];
      sonuc.kisi = sec[2].trim();
      kalan = kalan.replace(sec[0], " ");
    }
  }

  sonuc.kalan = kalan.replace(/\s*[-–]\s*$/, "").replace(/\s{2,}/g, " ")
                     .replace(/^[\s\-–·]+|[\s\-–·]+$/g, "").trim();
  return sonuc;
}

/** Günün BÜTÜN slotlarını sırayla bloklara böler — dolu VE boş.
 *
 *  NEDEN BOŞ SLOTLAR DA VAR
 *  ------------------------
 *  Önceki sürüm yalnızca dolu slotları listeliyordu. Bu, "bu derslik
 *  bugün ne zaman kullanılıyor" sorusuna cevap veriyordu ama asıl
 *  yönetsel soruya — "ne zaman BOŞ, buraya ders koyabilir miyim" —
 *  vermiyordu. Kullanıcı iki dersin arasındaki üç saatlik boşluğu
 *  görmek için satır aralarını kendisi hesaplamak zorundaydı.
 *
 *  Boşluk bilgisi UYDURULMUYOR: kaynaktaki 12 slotluk dizide `null`
 *  olan hücre, o saatte ders atanmadığı anlamına gelir. Gün başındaki,
 *  aradaki ve gün sonundaki boşluklar aynı diziden okunur.
 *
 *  ARDIŞIK BİRLEŞTİRME iki yönde de çalışır: dört saat süren bir ders
 *  tek blok olur; arka arkaya beş boş slot da tek "boş" bloğu olur.
 *  Aksi hâlde panel on iki satırlık bir tabloya dönerdi.
 *
 *  Dönen her blokta `bos` alanı vardır; çağıran taraf dolu/boş ayrımını
 *  ona bakarak yapar. */
function dhGunBloklari(oda, gun) {
  const slots = (oda.schedule && oda.schedule[gun]) || [];
  const etiketler = oda.slot_labels || [];
  const bloklar = [];
  for (let i = 0; i < slots.length; i++) {
    const ders = dhDersCoz(slots[i]);          // null → o saat boş
    const son = bloklar[bloklar.length - 1];
    /* Bir öncekiyle BİRLEŞTİRİLEBİLİR Mİ: bitişik olmalı ve ikisi de
       ya aynı ders ya da ikisi de boş olmalı. */
    const surüyor = son && son.bitisIdx === i - 1
      && (ders ? (son.ders && son.ders.ham === ders.ham) : !son.ders);
    if (surüyor) son.bitisIdx = i;
    else bloklar.push({ baslangicIdx: i, bitisIdx: i, ders: ders || null });
  }
  return bloklar.map(b => {
    const bas = String(etiketler[b.baslangicIdx] || "").split("-")[0].trim();
    const bit = String(etiketler[b.bitisIdx] || "").split("-")[1];
    return { ...b, bos: !b.ders,
             slotSayisi: b.bitisIdx - b.baslangicIdx + 1,
             saat: bas && bit ? `${bas} – ${bit.trim()}` : (bas || "—") };
  });
}

/** Seçili dersliğin, seçili gündeki programı. */
function dhProgramPaneli(v) {
  const bos = (bas, alt) => `<div class="dh-prog">
      <div class="dh-prog-bas"><b>${esc(bas)}</b></div>
      <p class="dh-prog-bos">${esc(alt)}</p></div>`;

  if (!DH.secili) {
    return bos("Derslik Seçin",
      "Harita üzerinden bir dersliğe tıklayarak günlük ders programını "
      + "görüntüleyebilirsiniz.");
  }
  const o = v.rooms.find(r => r.room_key === DH.secili);
  if (!o) {
    /* Kat değişti ve oda bu katta yok: seçim sessizce düşer. */
    return bos("Derslik Seçin",
      "Seçili derslik bu katta bulunmuyor. Haritadan bir derslik seçin.");
  }

  const baslik = `${o.room_code} · ${DH.gun} Ders Programı`;
  const ust = `<div class="dh-prog-bas">
      <b>${esc(o.room_code)}</b>
      <button type="button" class="dh-kapat" data-dh-kapat
              aria-label="Paneli kapat">×</button>
      <div class="dh-prog-alt">${esc(DH.gun)} Ders Programı</div>
      <div class="dh-prog-meta">${o.name ? esc(o.name) + " · " : ""}Kat ${
        o.floor}${o.class_capacity ? " · " + o.class_capacity + " kişilik" : ""}${
        o.owner_unit ? " · " + esc(o.owner_unit) : ""}</div>
    </div>`;

  if (!o.has_schedule || !o.schedule) {
    return `<div class="dh-prog">${ust}
      <p class="dh-prog-bos">Bu derslik kaynak ders programında yer almıyor.</p>
      </div>`;
  }
  const bloklar = dhGunBloklari(o, DH.gun);
  if (!bloklar.length) {
    /* Kaynakta bu gün için hiç slot tanımlı değil — "hepsi boş" demek
       DEĞİLDİR, o yüzden yeşil satır üretilmez. */
    return `<div class="dh-prog">${ust}
      <p class="dh-prog-bos">Bu gün için slot tanımı bulunmuyor.</p>
      </div>`;
  }
  const dersSayisi = bloklar.filter(b => !b.bos).length;
  const bosSayisi = bloklar.length - dersSayisi;
  /* Gün tamamen boşsa bunu açıkça söyle: kullanıcı on iki yeşil satırı
     tarayıp "hiç ders yokmuş" sonucunu kendi çıkarmak zorunda kalmasın. */
  const gunBosNotu = dersSayisi === 0
    ? `<p class="dh-prog-bos">Bu gün için planlanmış ders bulunmuyor.</p>`
    : "";

  const satirlar = bloklar.map(b => {
    /* BOŞ SLOT — yeşil. "Boş" tek başına kararsız bir kelime ("veri yok"
       ile karışır); burada kastedilen kaynakta ders ATANMAMIŞ olmasıdır,
       bu yüzden "Müsait" yazılır. */
    if (b.bos) {
      return `<li class="dh-ders bos">
        <span class="dh-ders-saat">${esc(b.saat)}</span>
        <span class="dh-ders-govde">
          <b>Müsait</b>
          <div class="dh-ders-ad">Bu saatte ders planlanmamış${
            b.slotSayisi > 1 ? ` · ${b.slotSayisi} saat` : ""}</div>
        </span>
      </li>`;
    }
    const d = b.ders;
    /* DOLU SLOT — kırmızı. Yalnızca gerçekten var olan alanlar yazılır. */
    const bas = d.kod
      ? `<b>${esc(d.kod)}</b>${d.tur ? ` <i>${esc(d.tur)}</i>` : ""}${
          d.sube ? ` <i>Şube ${esc(d.sube)}</i>` : ""}`
      : `<b>${esc(d.kalan || d.ham)}</b>`;
    const ad = d.kod && d.kalan ? `<div class="dh-ders-ad">${esc(d.kalan)}</div>` : "";
    const kisi = d.kisi ? `<div class="dh-ders-kisi">${esc(d.kisi)}</div>` : "";
    return `<li class="dh-ders dolu">
      <span class="dh-ders-saat">${esc(b.saat)}</span>
      <span class="dh-ders-govde">${bas}${ad}${kisi}</span>
    </li>`;
  }).join("");

  return `<div class="dh-prog">${ust}${gunBosNotu}
    <ul class="dh-ders-liste" aria-label="${esc(baslik)}">${satirlar}</ul>
    <div class="dh-prog-not">${dersSayisi} ders · ${bosSayisi} müsait aralık
      · saat süzgecinden bağımsız, günün tamamı</div>
  </div>`;
}

/** Tıklanan odanın kalıcı bilgi kutusu. */
function dhDetay(v) {
  if (!DH.secili) return "";
  const o = v.rooms.find(r => r.room_key === DH.secili);
  if (!o) return "";
  const d = dhDurum(o);
  const sat = (a, b) => `<div><span>${esc(a)}</span><b>${b}</b></div>`;
  return `<div class="dh-detay">
    <div class="dh-detay-bas">
      <b>${esc(o.room_code)}</b>${o.name ? ` · ${esc(o.name)}` : ""}
      <button type="button" class="dh-kapat" data-dh-kapat>×</button>
    </div>
    ${sat("Kat", o.floor)}
    ${sat("Sınıf kapasitesi", dhSayi(o.class_capacity))}
    ${sat("Öğrenci kapasitesi", dhSayi(o.student_capacity))}
    ${sat("Birim", esc(o.owner_unit || "—"))}
    ${!d.veriVar
      ? sat("Durum", '<span class="dh-yok">Programda yok</span>')
      : d.kip === "slot"
        ? sat("Durum", d.ders
            ? `Dolu · ${esc(d.ders)}`
            : "Boş")
        : sat(`${DH.gun} kullanımı`,
            `${d.dolu}/${d.toplam} slot · %${fmt.dec(d.oran * 100, 0)} · ${
              dhKova(d.oran).ad}`)}
    ${o.plan_position ? `<div class="not">Plan konumu: ${esc(o.plan_position.source)}</div>` : ""}
  </div>`;
}

/* =========================================================================
   EŞLEŞTİRME MODU — araç çubuğu, atama düzenleyici, kaydetme
   ========================================================================= */

function dhAracCubugu() {
  const kirli = DH.kirli;
  return `<div class="dh-arac">
    <button type="button" class="dh-btn${DH.mod ? " acik" : ""}" data-dh-mod>
      ${DH.mod ? "✎ Eşleştirme Modu: AÇIK" : "✎ Derslik Eşleştirme"}
    </button>
    ${DH.mod ? `
      <button type="button" class="dh-btn kaydet${kirli ? " kirli" : ""}"
              data-dh-kaydet ${kirli ? "" : "disabled"}>💾 Kaydet</button>
      ${kirli ? `<span class="dh-kirli">● Kaydedilmemiş değişiklikler var</span>`
              : `<span class="dh-temiz">Tüm değişiklikler kayıtlı${
                  DH.kaydedilme ? " · " + esc(String(DH.kaydedilme).slice(0, 16).replace("T", " ")) : ""}</span>`}
      <span class="dh-say">${DH.alanlar.length} alan ·
        ${DH.alanlar.filter(a => a.room_code).length} eşleşmiş</span>` : ""}
    ${DH.mesaj ? `<span class="dh-mesaj ${DH.mesaj.tur}">${esc(DH.mesaj.metin)}</span>` : ""}
  </div>`;
}

/** Seçili alanın atama düzenleyicisi. */
function dhAlanDuzenleyici() {
  if (!DH.mod || !DH.seciliAlan) return "";
  /* Seçili alan, semantik haritadan OTOMATİK çıkarılmış bir odadır.
     Kullanıcı poligon çizmez; yalnızca derslik kodu atar. Henüz atama
     yapılmadıysa `DH.alanlar` içinde kaydı yoktur — düzenleyici yine de
     açılır, kayıt ilk atamada oluşturulur. */
  const oda = (typeof dhpSeciliOda === "function") ? dhpSeciliOda() : null;
  const a = DH.alanlar.find(x => x.area_id === DH.seciliAlan)
         || (oda ? { area_id: oda.area_id, floor: Number(DH.kat),
                     polygon: oda.polygon, room_code: null,
                     label: oda.architectural_label } : null);
  if (!a) return "";
  const planBilgi = oda
    ? `${oda.architectural_label}${oda.area_m2 ? ` · ${oda.area_m2} m²` : ""}`
    : `${a.polygon ? a.polygon.length : 0} nokta`;
  /* Açılır listede YALNIZCA Excel'de gerçekten bulunan derslikler.
     Başka alana atanmış olanlar işaretlenir ki kullanıcı çakışmayı
     kaydetmeden önce görsün. */
  const baskaAlanda = new Map(
    DH.alanlar.filter(x => x.room_code && x.area_id !== a.area_id)
              .map(x => [x.room_code, x.svg_area_id || x.area_id]));
  const secenek = DH.atanabilir.map(r => {
    const cakisma = baskaAlanda.get(r.room_code);
    return `<option value="${esc(r.room_code)}"${
      r.room_code === a.room_code ? " selected" : ""}>${esc(r.room_code)}${
      r.name ? " — " + esc(r.name) : ""} (Kat ${r.floor}${
      r.class_capacity ? ", " + r.class_capacity + " kişi" : ""})${
      cakisma ? "  ⚠ " + cakisma + " alanında" : ""}</option>`;
  }).join("");
  return `<div class="dh-duzen">
    <div class="dh-duzen-bas"><b>${esc(planBilgi)}</b>
      <span>Kat ${a.floor}</span>
      <button type="button" class="dh-kapat" data-dh-alan-kapat>×</button></div>
    <label class="dh-satir"><span>Derslik kodu</span>
      <select data-dh-oda>
        <option value="">— eşleştirilmemiş —</option>${secenek}
      </select></label>
    <div class="dh-duzen-alt">
      <button type="button" class="dh-btn kucuk" data-dh-alan-sil>Eşleştirmeyi kaldır</button>
      ${/* "Alanı sil" YALNIZCA elle eklenmiş istisnai alanlar için
           anlamlıdır: otomatik çıkarılmış oda silinse bile bir sonraki
           yüklemede semantik haritadan yine gelir. */""}
      ${String(a.area_id).startsWith("manuel") ? `<button type="button"
        class="dh-btn kucuk tehlike" data-dh-alan-kaldir>Alanı sil</button>` : ""}
    </div>
  </div>`;
}

/** Değişiklik kaydedildi mi bilgisini tek yerden yönetir. */
function dhKirlet() { DH.kirli = true; DH.mesaj = null; }

async function dhKaydet() {
  /* Çakışma sunucuda da denetlenir; burada erken uyarı vererek
     kullanıcıyı gereksiz bir 409'a göndermeyiz. */
  const sayac = {};
  DH.alanlar.forEach(a => {
    if (a.room_code) sayac[a.room_code] = (sayac[a.room_code] || 0) + 1;
  });
  const cakisan = Object.keys(sayac).filter(k => sayac[k] > 1);
  if (cakisan.length) {
    DH.mesaj = { tur: "hata",
      metin: `Aynı derslik birden fazla alanda: ${cakisan.join(", ")}. `
             + "Önce eskisini kaldırın." };
    derslikHaritasiTazele();
    return;
  }
  try {
    const y = await api.put("/api/physical-resources/classroom-map-areas",
                            { areas: DH.alanlar });
    DH.kirli = false;
    DH.kaydedilme = y.updated_at;
    DH.mesaj = { tur: "ok", metin: `Kaydedildi (${y.area_count} alan).` };
  } catch (e) {
    /* `ApiError.detail` FastAPI'nin `detail` gövdesidir (api.js onu
       zaten açar). Sunucunun söylediği gerekçe aynen gösterilir;
       "bir şeyler ters gitti" gibi bilgi taşımayan bir metne
       indirgenmez. */
    const d = (e && e.detail) || {};
    DH.mesaj = { tur: "hata",
      metin: (typeof d === "string" ? d : d.message)
             || "Kaydedilemedi. Sunucu isteği reddetti." };
  }
  derslikHaritasiTazele();
}

/* -------------------------------------------------------------------------
   ANA GÖVDE
   ------------------------------------------------------------------------- */
function derslikHaritasiGovde(v, esleme, plan) {
  if (!v || !v.available) {
    return bekleniyorGovde((v && v.note)
      || "Derslik kullanım veri kümesi üretilmemiş.");
  }
  DH.veri = v;
  /* Eşleştirme dosyası YALNIZCA ilk yüklemede alınır. Sonraki
     tazelemeler (`derslikHaritasiTazele`) bu argümanı taşımaz; aksi
     hâlde kullanıcının kaydetmediği düzenlemeleri sunucudaki eski
     hâlle ezerdik. */
  if (plan && plan.available) DH.plan = plan;
  if (esleme) {
    DH.alanlar = Array.isArray(esleme.areas) ? esleme.areas : [];
    DH.atanabilir = esleme.assignable_rooms || [];
    DH.kaydedilme = esleme.updated_at;
    DH.kirli = false;
    if (esleme.error) DH.mesaj = { tur: "hata", metin: esleme.error };
  }
  /* TEK kat render edilir. KPI'lar da yalnızca o katın odalarından
     hesaplanır; başka katın verisi seçili kata karışmaz. */
  if (DH.plan && DH.plan.floors && !DH.plan.floors[String(DH.kat)]) {
    DH.kat = Number(Object.keys(DH.plan.floors)[0]);
  }
  const aktifKat = Number(DH.kat);
  const gorunen = v.rooms.filter(o => o.floor === aktifKat);

  const kapsam = v.coverage || {};
  return `<div class="kpi-serit dh-kpi">${dhOzet(gorunen)}</div>
    ${dhSuzgecler(v)}
    ${dhAracCubugu()}
    ${dhpAracCubugu()}
    ${dhLejant()}
    ${dhAlanDuzenleyici()}
    ${/* `dhDetay()` BURADAN KALDIRILDI. Onu açan `[data-oda]` seçicisi
         zaten hiçbir yerde üretilmiyordu — ulaşılamaz bir kutuydu.
         Yerini, aynı `DH.secili` durumunu kullanan ve haritanın sağında
         duran ders programı paneli aldı. */""}
    <div class="dh-katlar">${dhKatGorunumu(v, aktifKat)}</div>
    ${dhEslesmeyenler(gorunen)}
    <div class="eksen-not">Kaynak: ${esc(v.meta.source_workbook)} ·
      ${esc((v.meta.source_plans || []).join(", "))} · ${esc(v.meta.semester)}.
      ${kapsam.rooms_total} derslikten ${kapsam.rooms_with_schedule} tanesinin
      ders programı var; ${kapsam.rooms_without_schedule} tanesi kaynakta
      programsız olduğu için "veri yok" gösterilir ve kullanım oranına
      KATILMAZ.</div>`;
}

/** Süzgeç/tıklama olayları — panel gövdesini yeniden çizer.
 *  `doldur()` yeniden çağrılmaz: veri zaten elde, ağ isteği gereksiz. */
function derslikHaritasiTazele() {
  const kap = document.getElementById("alHarita");
  if (kap && DH.veri) kap.innerHTML = derslikHaritasiGovde(DH.veri);
}

document.addEventListener("change", e => {
  if (e.target.matches && e.target.matches("[data-dh-oda]")) {
    /* Derslik ataması. Çakışma burada ENGELLENMEZ ama görünür kılınır:
       kullanıcı önce eskisini kaldırmak isteyebilir. Kaydetme anında
       hem istemci hem sunucu ayrıca denetler. */
    /* Kaydı ilk atamada oluştururuz; GEOMETRİ SEMANTİK HARİTADAN kopyalanır,
       kullanıcı çizmez. Poligonu kayda gömmek, harita yeniden üretildiğinde
       eşleştirmenin görsel karşılığını kaybetmemesini sağlar. */
    let a = DH.alanlar.find(x => x.area_id === DH.seciliAlan);
    if (!a && DH.seciliAlan && typeof dhpEslemeAlaniHazirla === "function") {
      a = dhpEslemeAlaniHazirla(DH.seciliAlan);
    }
    if (a) {
      const yeni = e.target.value || null;
      const baska = yeni && DH.alanlar.find(
        x => x.room_code === yeni && x.area_id !== a.area_id);
      a.room_code = yeni;
      /* SIRA ÖNEMLİ: `dhKirlet()` mesajı temizler, bu yüzden uyarı
         ONDAN SONRA yazılır. Aksi hâlde çakışma uyarısı hiç
         görünmezdi. */
      dhKirlet();
      if (baska) {
        DH.mesaj = { tur: "hata",
          metin: `"${yeni}" zaten ${baska.area_id} alanına atanmış. `
                 + "Kaydetmeden önce birini kaldırın." };
      }
      derslikHaritasiTazele();
    }
    return;
  }
  if (!e.target.id) return;
  if (e.target.id === "dhGun") { DH.gun = e.target.value; derslikHaritasiTazele(); }
  else if (e.target.id === "dhKat") {
    DH.kat = Number(e.target.value); DH.seciliAlan = null; derslikHaritasiTazele();
  }
  else if (e.target.id === "dhSaat") {
    DH.slot = e.target.value === "all" ? "all" : Number(e.target.value);
    derslikHaritasiTazele();
  }
});

document.addEventListener("click", e => {
  const harita = document.getElementById("alHarita");
  if (!harita) return;

  if (e.target.closest("[data-dh-mod]")) {
    if (DH.mod && DH.kirli
        && !confirm("Kaydedilmemiş eşleştirme değişiklikleri var. "
                    + "Eşleştirme modundan çıkılsın mı? (değişiklikler ekranda kalır)")) {
      return;
    }
    DH.mod = !DH.mod;
    DH.seciliAlan = null;
    DH.mesaj = null;
    derslikHaritasiTazele(); return;
  }
  if (e.target.closest("[data-dh-kaydet]")) { dhKaydet(); return; }
  if (e.target.closest("[data-dh-alan-kapat]")) {
    DH.seciliAlan = null; derslikHaritasiTazele(); return;
  }
  if (e.target.closest("[data-dh-alan-sil]")) {          // yalnızca atamayı kaldır
    const a = DH.alanlar.find(x => x.svg_area_id === DH.seciliAlan
                                   || x.area_id === DH.seciliAlan);
    if (a) { a.room_code = null; dhKirlet(); derslikHaritasiTazele(); }
    return;
  }
  if (e.target.closest("[data-dh-alan-kaldir]")) {        // alanın kendisini sil
    DH.alanlar = DH.alanlar.filter(x => x.svg_area_id !== DH.seciliAlan
                                        && x.area_id !== DH.seciliAlan);
    DH.seciliAlan = null; dhKirlet(); derslikHaritasiTazele(); return;
  }
  /* `data-svg-alan` işleyicisi KALDIRILDI: onu üreten CAD-pafta
     görünümü artık yok. Ölü bir seçicinin durması, ilerideki bir
     okuyucuya hâlâ iki ayrı seçim yolu varmış izlenimi verirdi.
     Oda seçimi tek yerden yapılır: derslik-harita-plan.js içindeki
     `[data-oda-alan]`. */
  const alan = e.target.closest("[data-alan]");
  if (alan && harita.contains(alan)) {
    if (!DH.mod) return;                 // mod kapalıyken alan seçilmez
    DH.seciliAlan = DH.seciliAlan === alan.dataset.alan ? null : alan.dataset.alan;
    DH.mesaj = null; derslikHaritasiTazele(); return;
  }
  if (e.target.closest("[data-dh-kapat]")) {
    DH.secili = null; derslikHaritasiTazele(); return;
  }
  /* DERSLİK SEÇİMİ — ders programı paneli için.
     -------------------------------------------------------------------
     Eşleştirme modu KAPALIYKEN çalışır. Mod açıkken aynı tıklama
     `derslik-harita-plan.js` içinde derslik kodu atamak için
     kullanılıyor; iki işlevi tek tıklamaya yüklemek, kullanıcının hangi
     sonucu beklediğini belirsiz kılardı.

     Yalnızca GERÇEK bir dersliğe (kodu atanmış oda) tıklandığında panel
     açılır. Koridor, duvar ve kod atanmamış alan paneli açmaz — açsaydı
     panel "bu alanın programı yok" demek zorunda kalırdı ki bu bilgi
     değil, gürültüdür. */
  const alanG = e.target.closest("[data-oda-alan]");
  if (alanG && harita.contains(alanG) && !DH.mod) {
    const oda = (typeof dhpOda === "function")
      ? dhpOda(alanG.dataset.odaAlan) : null;
    if (!oda) return;                       // eşleştirilmemiş alan: sessiz
    DH.secili = DH.secili === oda.room_key ? null : oda.room_key;
    derslikHaritasiTazele();
  }
});

/* Panelden/sayfadan ayrılırken kaydedilmemiş değişiklik uyarısı.
   Global gezinme yeniden yazılmaz; yalnızca tarayıcının kendi kancası. */
window.addEventListener("beforeunload", e => {
  if (DH.kirli) { e.preventDefault(); e.returnValue = ""; }
});
