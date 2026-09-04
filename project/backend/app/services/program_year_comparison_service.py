"""PROGRAM × YIL KARŞILAŞTIRMASI — kontenjan ve doluluk.

Yıl ekseni veritabanındaki gerçek yıllardan türer (`mevcut_yillar`);
sabit bir aralık yazılı DEĞİLDİR.

NEDEN AYRI BİR SERVİS
--------------------
Mevcut iki uç bu soruyu cevaplamıyordu:

    `university-competitors`  yıl kırılımı olarak yalnızca `yearly_totals`
                              (öğrenci mevcudu) veriyor; kontenjan/yerleşen
                              tek bir toplam olarak dönüyor.
    `yok-atlas-comparison`    üniversite kapsamında `available=False` dönüp
                              resmî YÖK sayımına yönlendiriyor.

Bu yüzden ÜÇÜNCÜ bir soru için minimum bir uç eklendi: "seçilen bölümde
kurumların kontenjanı ve doluluğu yıllara göre nasıl seyretti?" Mevcut
servislerin hiçbiri küçültülmedi veya değiştirilmedi.

KAYNAK
------
`yok_atlas_benchmark_metrics` tablosu — canonical YÖK Atlas aktarımı
(`yokatlas_ankara_2022_plus.csv`). Ekipten gelen "corrected" dosyalar
KULLANILMAZ.

TOPLAMA KURALI
--------------
Aynı üniversite/program/yıl için burslu, %50 indirimli, ücretli ve dil
varyantları AYRI SATIRLARDIR ve toplanabilir:

    kontenjan = Σ quota
    yerleşen  = Σ placed
    doluluk   = yerleşen / kontenjan × 100

Doluluk YÜZDELERİN ORTALAMASI DEĞİLDİR. Ortalama alınsaydı 5 kişilik
burslu kontenjanın %100'ü, 100 kişilik ücretli kontenjanın %40'ıyla eşit
ağırlık taşırdı.

ÜNİVERSİTE TOPLAMINA DÜŞMEK YASAK
---------------------------------
Kapsam bir programdır. Bir kurumda o program yoksa kurum listeye
girmez; başka programların kontenjanı toplanarak "veri üretilmez".
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.yok_atlas_metric import YokAtlasBenchmarkMetric

#: Sabitler MEVCUT servisten alınır, burada yeniden yazılmaz: aktarım
#: etiketi değişirse iki yer birden değişmek zorunda kalmasın.
from app.services.yok_atlas_comparison_service import (  # noqa: E402
    HOME_UNIVERSITY,
    SOURCE_DATASET,
    SOURCE_FILE,
    TEAM_SOURCE_DATASET,
    TEAM_YEARS,
)

#: Kaynakta gerçekten bulunan yıllar. Sabit yazılır ama yanıt yalnızca
#: VERİSİ OLAN yılları döner; boş yıl uydurulmaz.
#:
#: 2021 ve 2025 ekip derlemesinden gelir ve VARYANT DÜZEYİNDEDİR (bkz.
#: `TEAM_SOURCE_DATASET`). Bu grafikte diğer yıllarla aynı çizgide
#: gösterilmeleri bilinçli bir üründür; karışık grain'i kullanıcıya
#: söyleme yükü `mixed_grain_years` alanına ve arayüzdeki dipnota
#: bırakılmıştır.
#: EN ERKEN / EN GEÇ MAKUL YIL.
#: Yıl listesi artık sabit değil, veritabanından okunuyor (aşağıya bkz).
#: Bu iki sınır bozuk bir kaydın (yazım hatası, 1900, 9999) ekseni
#: bozmasını engeller — açık uçlu bir aralık kabul edilmez.
_EN_ERKEN_YIL = 2000
_EN_GEC_YIL = 2100

#: Geriye dönük uyumluluk için korunan varsayılan. Sorgu artık bunu
#: KULLANMAZ; yalnızca veritabanına hiç erişilemediğinde devreye girer.
YEARS = (2021, 2022, 2023, 2024, 2025)


def mevcut_yillar(db: Session) -> Tuple[int, ...]:
    """Grafiğin yıl ekseni — VERİTABANINDAKİ GERÇEK YILLAR.

    NEDEN SABİT DEĞİL
    -----------------
    Burada `YEARS = (2021 … 2025)` diye sabit bir liste vardı ve sorgu
    `source_year.in_(YEARS)` ile süzüyordu. Yeni veri kümesiyle
    veritabanına 2026 girdi (ölçüldü: 15.253 satır, `source_year=2026`)
    ama grafik onu HİÇ SORMADIĞI için ekranda 2025'te kesiliyordu.
    Veri oradaydı, soru yanlıştı.

    Sabit listeyi bir yıl ileri almak aynı hatayı bir yıl sonraya
    ertelemek olurdu. Eksen artık kaynağın kendisinden türüyor: yeni
    bir yıl aktarıldığı anda kod değişmeden görünür.

    Uydurma yıl ÜRETİLMEZ: yalnızca gerçekten kaydı olan yıllar döner.
    """
    satir = db.execute(
        select(YokAtlasBenchmarkMetric.source_year)
        .where(
            YokAtlasBenchmarkMetric.source_dataset.in_(KULVARLAR),
            YokAtlasBenchmarkMetric.source_year.is_not(None),
            YokAtlasBenchmarkMetric.source_year >= _EN_ERKEN_YIL,
            YokAtlasBenchmarkMetric.source_year <= _EN_GEC_YIL,
        )
        .distinct()
    ).scalars().all()
    return tuple(sorted(int(y) for y in satir)) or YEARS
#: DOLULUK İÇİN EN AZ YERLEŞEN KAPSAMASI.
#:
#: Doluluk = SUM(placed) / SUM(quota). Payda o yılın TÜM programlarını
#: sayarken pay yalnızca yerleşen kaydı OLAN programları sayarsa oran
#: gerçeğin çok altında çıkar.
#:
#: Ölçüldü — yerleşen kaydı olan program oranı:
#:     2021 %100 · 2022 %100 · 2023 %97 · 2024 %98 · 2025 %3 · 2026 %100
#:
#: 2025 için kaynakta yerleşen sütunu hiç yok (`Gecmis_2023_2025`
#: sayfasında `placed_students` kolonu bulunmuyor). Bu yüzden ekranda
#: Başkent %2,5 · OSTİM %1,1 gibi rakamlar çıkıyordu: veri eksikliği,
#: doluluk çöküşü gibi görünüyordu. Yöneticiyi yanıltan bu sayı
#: hesaplanmaz; nokta BOŞ bırakılır ve kontenjan çizgisi etkilenmez.
_MIN_YERLESEN_KAPSAMASI = 0.60

#: "Tüm bölümler" kapsamı — ABÜ'nün sahip olduğu bölümlerin TOPLAMI.
TUM_BOLUMLER = "__all__"

#: Bu servisin okuduğu kulvarlar. Kardeş servisler yalnızca kanonik
#: kulvarı okur; genişletme burada YEREL kalır.
KULVARLAR = (SOURCE_DATASET, TEAM_SOURCE_DATASET)

_TYPE_LABEL = {
    "all": "Ankara'daki tüm üniversiteler",
    "state": "Devlet üniversiteleri",
    "foundation": "Vakıf üniversiteleri",
    "similar": "Benzer ölçekli üniversiteler (devlet + vakıf)",
}


def _sayi(v: Optional[Decimal]) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _kurum_suzgeci(db: Session, institution_type: str) -> Optional[set[str]]:
    """Mevcut kurum süzgeci mantığını AYNEN kullanır; yenisi yazılmaz.

    `None` dönmesi "süzme" demektir (Tümü).
    """
    if institution_type in (None, "", "all"):
        return None
    if institution_type == "similar":
        from app.services.yok_atlas_comparison_service import _similar_universities
        return _similar_universities(db)
    from app.services.yok_atlas_comparison_service import _university_types
    turler = _university_types(db)
    hedef = "DEVLET" if institution_type == "state" else "VAKIF"
    secilen = {ad for ad, t in turler.items() if t == hedef}
    secilen.add(HOME_UNIVERSITY)          # referans kurum her zaman kalır
    return secilen


def program_secenekleri(db: Session) -> List[Dict[str, Any]]:
    """Seçilebilir bölümler — YALNIZCA kendi kurumumuzda bulunanlar.

    Kıyas bizim bir bölümümüzü akranlarla karşılaştırmak içindir; bizde
    olmayan bir bölümü listelemek kullanıcıyı boş bir grafiğe götürürdü.
    """
    bizim = db.execute(
        select(
            YokAtlasBenchmarkMetric.canonical_program_key,
            YokAtlasBenchmarkMetric.program_name,
        )
        .where(
            YokAtlasBenchmarkMetric.source_dataset.in_(KULVARLAR),
            YokAtlasBenchmarkMetric.university_name == HOME_UNIVERSITY,
            YokAtlasBenchmarkMetric.metric == "quota",
        )
        .distinct()
    ).all()

    etiket: Dict[str, str] = {}
    for anahtar, ad in bizim:
        etiket.setdefault(anahtar, ad)

    if not etiket:
        return []

    # Kaç kurumda var — kullanıcı kıyasın ne kadar geniş olacağını görsün.
    sayim = db.execute(
        select(
            YokAtlasBenchmarkMetric.canonical_program_key,
            YokAtlasBenchmarkMetric.university_name,
        )
        .where(
            YokAtlasBenchmarkMetric.source_dataset.in_(KULVARLAR),
            YokAtlasBenchmarkMetric.canonical_program_key.in_(list(etiket)),
            YokAtlasBenchmarkMetric.metric == "quota",
        )
        .distinct()
    ).all()
    kurum: Dict[str, set] = {}
    for anahtar, ad in sayim:
        kurum.setdefault(anahtar, set()).add(ad)

    return sorted(
        (
            {
                "key": k,
                "label": etiket[k],
                "university_count": len(kurum.get(k, ())),
            }
            for k in etiket
        ),
        key=lambda x: (-x["university_count"], x["label"]),
    )


def _evrendeki_kurumlar(db: Session, suzgec: Optional[set]) -> Dict[str, Optional[str]]:
    """Seçili kurum evrenindeki TÜM üniversiteler (bölümden bağımsız).

    Bir bölüm seçildiğinde "kimlerde yok" sorusunu cevaplayabilmek için
    önce "kimler var" kümesini bilmek gerekir.
    """
    satir = db.execute(
        select(
            YokAtlasBenchmarkMetric.university_name,
            YokAtlasBenchmarkMetric.university_type,
        )
        .where(YokAtlasBenchmarkMetric.source_dataset.in_(KULVARLAR))
        .distinct()
    ).all()
    return {ad: tur for ad, tur in satir
            if suzgec is None or ad in suzgec}


def _kurumun_programlari(db: Session, universite: str) -> Dict[str, str]:
    """Bir kurumun kanonik program anahtarı → görünen ad eşlemesi."""
    satir = db.execute(
        select(
            YokAtlasBenchmarkMetric.canonical_program_key,
            YokAtlasBenchmarkMetric.program_name,
        )
        .where(
            YokAtlasBenchmarkMetric.source_dataset.in_(KULVARLAR),
            YokAtlasBenchmarkMetric.university_name == universite,
            YokAtlasBenchmarkMetric.metric == "quota",
        )
        .distinct()
    ).all()
    cikti: Dict[str, str] = {}
    for anahtar, ad in satir:
        cikti.setdefault(anahtar, ad)
    return cikti


def _etiket(anahtar: str, secenekler: List[Dict[str, Any]]) -> str:
    if anahtar == TUM_BOLUMLER:
        return "Tüm bölümler (ABÜ portföyü)"
    return next((p["label"] for p in secenekler if p["key"] == anahtar), anahtar)


def comparison(
    db: Session,
    program_key: Optional[str] = None,
    institution_type: str = "all",
) -> Dict[str, Any]:
    secenekler = program_secenekleri(db)
    if not secenekler:
        return {
            "available": False,
            "programs": [],
            "universities": [],
            "years": [],
            "note": "YÖK Atlas program kayıtları yüklenmemiş.",
        }

    gecerli = {p["key"] for p in secenekler}
    tumu = program_key in (None, "", TUM_BOLUMLER)
    if not tumu and program_key not in gecerli:
        tumu = True
    if tumu:
        program_key = TUM_BOLUMLER

    suzgec = _kurum_suzgeci(db, institution_type)

    """KAPSAM SEÇİMİ.

    `__all__`  ABÜ'nün SAHİP OLDUĞU bölümlerin tamamı. Kurumların
               genel toplamı DEĞİLDİR: yalnızca bizde de bulunan
               bölümler toplanır, böylece "bizim portföyümüzde bu
               kurumlar ne büyüklükte?" sorusu adil kalır. Rakibin
               bizde olmayan bir bölümü toplama girmez.
    tek anahtar  yalnızca o bölüm.
    """
    kapsam_anahtarlari = sorted(gecerli) if tumu else [program_key]

    satirlar = db.execute(
        select(
            YokAtlasBenchmarkMetric.university_name,
            YokAtlasBenchmarkMetric.university_type,
            YokAtlasBenchmarkMetric.source_year,
            YokAtlasBenchmarkMetric.metric,
            YokAtlasBenchmarkMetric.value,
            YokAtlasBenchmarkMetric.program_name,
        ).where(
            YokAtlasBenchmarkMetric.source_dataset.in_(KULVARLAR),
            YokAtlasBenchmarkMetric.canonical_program_key.in_(kapsam_anahtarlari),
            YokAtlasBenchmarkMetric.metric.in_(("quota", "placed", "success_rank")),
            YokAtlasBenchmarkMetric.source_year.in_(mevcut_yillar(db)),
        )
    ).all()

    # kurum -> yıl -> {quota, placed, siralar, adlar}
    kova: Dict[str, Dict[int, Dict[str, Any]]] = {}
    tur: Dict[str, Optional[str]] = {}
    for ad, utur, yil, metrik, deger, pad in satirlar:
        if suzgec is not None and ad not in suzgec:
            continue
        tur.setdefault(ad, utur)
        hucre = kova.setdefault(ad, {}).setdefault(
            yil, {"quota": None, "placed": None, "siralar": [], "adlar": set(),
                  "quota_adet": 0, "placed_adet": 0}
        )
        v = _sayi(deger)
        if metrik == "success_rank":
            # SIRALAMA TOPLANMAZ.
            # --------------------------------------------------------------
            # Kontenjan ve yerleşen sayıdır; varyantlar toplanır. Başarı
            # sırası ise bir KONUMDUR: iki varyantın sırasını toplamak
            # ("15.000 + 40.000 = 55.000") anlamsız bir sayı üretir.
            # Ham değerler biriktirilir, aşağıda en iyisi (en küçüğü)
            # seçilir — bir bölümün "kaçıncı sıradan öğrenci aldığı"
            # sorusunun standart cevabı budur.
            if v is not None:
                hucre["siralar"].append(v)
        elif v is not None:
            hucre[metrik] = (hucre[metrik] or 0) + v
            # Kapsama sayacı: kaç programda bu ölçüm gerçekten var.
            hucre[f"{metrik}_adet"] += 1
        hucre["adlar"].add(pad)

    if not kova:
        return {
            "available": False,
            "programs": [{"key": TUM_BOLUMLER,
                          "label": "Tüm bölümler (ABÜ portföyü)",
                          "university_count": 0}] + secenekler,
            "program_key": program_key,
            "program_label": _etiket(program_key, secenekler),
            "universities": [],
            "years": [],
            "institution_type": institution_type,
            "institution_type_label": _TYPE_LABEL.get(institution_type, institution_type),
            "note": "Bu bölüm seçili kurum evreninde bulunmuyor.",
        }

    gorulen_yil = sorted({y for k in kova.values() for y in k})

    kurumlar = []
    for ad, yillar in kova.items():
        seri = []
        for y in gorulen_yil:
            h = yillar.get(y)
            if not h:
                # O yıl kayıt YOK — sıfır değil, ölçülmemiş.
                seri.append({"year": y, "quota": None, "placed": None,
                             "occupancy_percent": None, "program_names": []})
                continue
            q, p = h["quota"], h["placed"]
            # KISMİ VERİYLE ORAN HESAPLANMAZ (bkz. _MIN_YERLESEN_KAPSAMASI).
            kapsama = (h["placed_adet"] / h["quota_adet"]
                       if h["quota_adet"] else 0.0)
            yeterli = kapsama >= _MIN_YERLESEN_KAPSAMASI
            occ = (p / q * 100) if (q and p is not None and yeterli) else None
            sira = min(h["siralar"]) if h["siralar"] else None
            seri.append({
                "year": y,
                "quota": q,
                # Yerleşen de kısmi ise gösterilmez: 234 programın
                # 3'ünün toplamı "o yıl yerleşen sayısı" değildir.
                "placed": p if yeterli else None,
                "placed_coverage": round(kapsama, 3),
                "occupancy_percent": round(occ, 2) if occ is not None else None,
                # Kurumun o yıl bu bölümde aldığı EN İYİ (en küçük) başarı
                # sırası. Yokluğu `None`'dır; sıfır değildir.
                "success_rank": int(sira) if sira is not None else None,
                "program_names": sorted(h["adlar"]),
            })
        kurumlar.append({
            "university_name": ad,
            "university_type": tur.get(ad),
            "is_home_institution": ad == HOME_UNIVERSITY,
            "series": seri,
        })

    # En son yılın kontenjanına göre büyükten küçüğe; kendi kurumumuz
    # sıraya karışır ama arayüz onu ayrıca vurgular.
    def _anahtar(k):
        son = next((s for s in reversed(k["series"]) if s["quota"] is not None), None)
        return -(son["quota"] if son else 0)

    kurumlar.sort(key=_anahtar)
    for k in kurumlar:
        k["has_program"] = True
        k["equivalent"] = None

    # ------------------------------------------------------------------
    # BÖLÜMÜ OLMAYAN KURUMLAR — SESSİZCE KAYBOLMASINLAR
    # ------------------------------------------------------------------
    # Önceki sürüm bu kurumları listeden tamamen düşürüyordu. Uydurma
    # yoktu ama kullanıcı da "neden 19 kurumdan 13'ü kaldı?" sorusunun
    # cevabını göremiyordu. Artık listeye GİRERLER, yalnızca SERİLERİ
    # BOŞTUR: çizgi çizilmez, sayı üretilmez, sıfır varsayılmaz.
    #
    # Muadil ararken YENİ BİR BENZERLİK ALGORİTMASI YAZILMAZ. "Benzer
    # Bölümler" kipinin kullandığı kapalı `discipline_family` listesi
    # aynen kullanılır: listede olmayan anahtar `None` döner ve muadil
    # sayılmaz (fail-closed).
    if not tumu:
        from app.services.program_equivalence import discipline_family

        hedef_aile = discipline_family(program_key)
        evren = _evrendeki_kurumlar(db, suzgec)
        olan = {k["university_name"] for k in kurumlar}
        for ad in sorted(set(evren) - olan):
            muadil = None
            if hedef_aile:
                for anahtar, etiket in _kurumun_programlari(db, ad).items():
                    if anahtar != program_key and discipline_family(anahtar) == hedef_aile:
                        muadil = {"program_key": anahtar, "label": etiket,
                                  "family": hedef_aile}
                        break
            kurumlar.append({
                "university_name": ad,
                "university_type": evren.get(ad),
                "is_home_institution": ad == HOME_UNIVERSITY,
                "series": [],
                "has_program": False,
                "equivalent": muadil,
            })

    baslangic = [{
        "key": TUM_BOLUMLER,
        "label": "Tüm bölümler (ABÜ portföyü)",
        "university_count": len(kurumlar),
    }] + secenekler
    return {
        "available": True,
        "programs": baslangic,
        "program_key": program_key,
        "program_label": _etiket(program_key, secenekler),
        "program_scope": "all" if tumu else "single",
        "with_program_count": sum(1 for k in kurumlar if k.get("has_program")),
        "without_program_count": sum(1 for k in kurumlar if not k.get("has_program")),
        "years": gorulen_yil,
        # KARIŞIK GRAIN UYARISI — grafiğin kendisi bunu gösteremez.
        # Ekranda görünen yılların hangileri ekip derlemesinden geldiğini
        # arayüzün dipnotta söyleyebilmesi için buradan bildirilir. Boş
        # liste "tüm yıllar kanonik kulvardan" demektir.
        # SIRALAMA KIYASI YALNIZCA TEK BÖLÜMDE GEÇERLİ.
        # ------------------------------------------------------------------
        # Başarı sırası puan türüne (SAY/EA/SÖZ/DİL/TYT) göre ayrı bir
        # sıralamadır. "Tüm bölümler" kapsamında farklı puan türlerinin
        # sıraları aynı eksende toplanır ve karşılaştırılamaz bir sayı
        # üretirdi. Arayüz bu bayrağa bakıp sıralama grafiğini kapatır.
        "rank_comparable": not tumu,
        "mixed_grain_years": [y for y in gorulen_yil if y in TEAM_YEARS],
        "mixed_grain_note": (
            "Bazı yıllar ekip derlemesinden gelir ve varyant düzeyindedir: "
            "bir bölümün tüm program kodlarının ve burs varyantlarının "
            "toplamı değil, tek bir varyantıdır. 2025 kayıtlarının çoğu "
            "burslu kontenjandır; burslu kontenjanlar hemen her zaman "
            "dolduğu için bu yılın doluluğu yukarı yanlıdır."
        ),
        "universities": kurumlar,
        "institution_type": institution_type,
        "institution_type_label": _TYPE_LABEL.get(institution_type, institution_type),
        "source": "YÖK Atlas",
        "source_file": SOURCE_FILE,
        "methodology": (
            "Burs türü ve dil varyantları toplanır: kontenjan = Σ quota, "
            "yerleşen = Σ placed, doluluk = yerleşen / kontenjan × 100. "
            "Yüzdelerin ortalaması alınmaz. Program kapsamı dışına çıkılmaz; "
            "kurumda bu bölüm yoksa kurum listeye girmez. 2022-2024 kanonik "
            "YÖK Atlas aktarımından, bir kısmı ekip derlemesinden gelir."
        ),
    }
