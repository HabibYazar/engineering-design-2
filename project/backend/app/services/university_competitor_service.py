"""ÜNİVERSİTE SEVİYESİ RAKİP ANALİZİ.

KAPSAM SINIRI
-------------
Bu servis YALNIZCA üniversite kapsamında çalışır. Fakülte, bölüm ve
program karşılaştırması `peer_comparison_service` üzerindedir ve o
davranışa DOKUNULMAZ: alt seviyelerde kardeş birim karşılaştırması
aynen sürer, dış kurum gösterilmez.

HER GÖSTERGENİN KENDİ KOHORTU VAR — bu dosyanın çekirdek fikri
--------------------------------------------------------------
Eski kural şuydu: "bir gösterge bütün kurumlarda ölçülmüyorsa hiç
gösterme". Bu kural bir kurumun tek bir eksik alanı yüzünden ekranın
tamamını boşaltabiliyordu.

Yeni kural: **her gösterge, o göstergeyi GERÇEKTEN ölçebildiğimiz
kurumlar arasında karşılaştırılır.**

    kayıtlı öğrenci   21/21 → 21 kurum arasında sıralanır
    akademik kadro    18/21 → o 18 kurum arasında sıralanır
    yayın              3/21 → sıralanmaz (kohort çok küçük ve yanlı)

Eksik değer KOHORTTAN ÇIKARILIR; asla 0'a çevrilmez. Her grafik kendi
kapsamını ekranda söyler ("18 / 21 kurumda veri"), böylece okuyucu
hangi kümeye baktığını bilir.

Bir gösterge yalnızca kohortu ANLAMLI KARŞILAŞTIRMAYA yetmiyorsa
(< `MIN_COHORT` kurum) kapatılır. Yayın sayısı bugün buna takılıyor:
toplayıcı profil ayrıntısını 21 kurumun 3'ünde indirmiş (Ankara
Bilim'de 164 kişide 1540 kayıt, Ankara Üniversitesi'nde 3659 kişide
175). Bu bir araştırma performansı farkı değil TARAMA KAPSAMI
farkıdır. Kapsam genişlerse gösterge kendiliğinden açılır.

İKİ ÖĞRENCİ SAYISI KARIŞTIRILMAZ
--------------------------------
Üniversite ölçeği için `university_student_headcounts` (YÖK, fiilen
kayıtlı) kullanılır. ÖSYM yerleştirmesinden türetilen
`academic_programs.student_count` program/bölüm/fakülte seviyesinde
kalır ve buraya karışmaz.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CompetitorTuitionFee, ProgramTuitionFee, UniversityProfile
from app.models import UniversityStudentHeadcount as Sayim
from app.models.university_headcount import (
    DEGREE_LEVEL_LABELS,
    HOME_UNIVERSITY,
)

# ---------------------------------------------------------------------------
# Süzme kipleri
# ---------------------------------------------------------------------------

FILTER_SIMILAR = "similar"
FILTER_ALL = "all"
FILTER_FOUNDATION = "foundation"
FILTER_STATE = "state"

DEFAULT_FILTER = FILTER_ALL

FILTER_LABELS: Dict[str, str] = {
    FILTER_SIMILAR: "Benzer ölçekli üniversiteler (devlet + vakıf)",
    FILTER_ALL: "Ankara'daki tüm üniversiteler",
    FILTER_FOUNDATION: "Vakıf üniversiteleri",
    FILTER_STATE: "Devlet üniversiteleri",
}

# ---------------------------------------------------------------------------
# Bölüm / Program Eşleştirme Kipleri (Hepsi / Aynı Bölümler / Benzer Bölümler)
# ---------------------------------------------------------------------------

MATCHING_ALL = "all_programs"
MATCHING_SAME = "same_program"
MATCHING_SIMILAR = "similar_programs"
DEFAULT_MATCHING = MATCHING_ALL

MATCHING_LABELS: Dict[str, str] = {
    MATCHING_ALL: "Hepsi",
    MATCHING_SAME: "Aynı Bölümler",
    MATCHING_SIMILAR: "Benzer Bölümler",
}

SIMILAR_LOWER = 0.35
SIMILAR_UPPER = 3.0

FOUNDATION = "VAKIF"
STATE = "DEVLET"


def _oran(pay, payda, basamak: int = 2) -> Optional[float]:
    if pay is None or not payda:
        return None
    return round(float(pay) / float(payda), basamak)


def _yuzde(simdi, onceki) -> Optional[float]:
    if simdi is None or onceki in (None, 0):
        return None
    return round((simdi - onceki) / onceki * 100, 2)


# ---------------------------------------------------------------------------
# Ham toplamalar
# ---------------------------------------------------------------------------


def _yillik_toplamlar(db: Session) -> Dict[str, Dict[str, int]]:
    """{üniversite: {yıl: toplam}} — tek sorgu."""
    out: Dict[str, Dict[str, int]] = {}
    for ad, yil, toplam in db.execute(
        select(Sayim.university_name, Sayim.academic_year,
               func.sum(Sayim.student_count))
        .group_by(Sayim.university_name, Sayim.academic_year)
    ):
        out.setdefault(ad, {})[yil] = int(toplam or 0)
    return out


def _duzey_dagilimi(db: Session, yil: str) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for ad, duzey, toplam in db.execute(
        select(Sayim.university_name, Sayim.degree_level,
               func.sum(Sayim.student_count))
        .where(Sayim.academic_year == yil)
        .group_by(Sayim.university_name, Sayim.degree_level)
    ):
        out.setdefault(ad, {})[duzey] = int(toplam or 0)
    return out


def available_years(db: Session) -> List[str]:
    return [y for (y,) in db.execute(
        select(Sayim.academic_year).group_by(Sayim.academic_year)
        .order_by(Sayim.academic_year))]


# ---------------------------------------------------------------------------
# Satır üretimi
# ---------------------------------------------------------------------------


def _ucret_medyanlari(db: Session, donem: Optional[str] = None) -> Dict[str, float]:
    """Kurum → %50 burslu lisans ücretinin medyanı (seçilen yıl).

    Aralık metni olarak yayımlanan ücretler sayısal olmadığı için
    hesaba girmez; uydurma bir orta nokta üretilmez.
    """
    from app.models.tuition_fee import FEE_HALF_SCHOLARSHIP, LEVEL_BACHELOR

    yil = donem or db.execute(
        select(func.max(CompetitorTuitionFee.academic_year))).scalar_one_or_none()
    if not yil:
        return {}

    # ANAHTAR KURUM KİMLİĞİDİR, ad değil. Ücret dosyası kurumları
    # kısaltarak/aksansız yazıyor ("Atilim Universitesi"), YÖK ise resmî
    # adı kullanıyor ("ATILIM ÜNİVERSİTESİ"). Aktarımda çözülen
    # `benchmark_institution_id` üzerinden bağlanınca iki taraf buluşur;
    # ham adla eşleştirmek kurumların çoğunu kaybettiriyordu.
    from app.models import BenchmarkInstitution

    kova: Dict[str, List[float]] = {}
    for kurum_adi, ucret in db.execute(
        select(BenchmarkInstitution.name, CompetitorTuitionFee.annual_fee)
        .join(BenchmarkInstitution,
              BenchmarkInstitution.id
              == CompetitorTuitionFee.benchmark_institution_id)
        .where(CompetitorTuitionFee.academic_year == yil,
               CompetitorTuitionFee.fee_type == FEE_HALF_SCHOLARSHIP,
               CompetitorTuitionFee.level == LEVEL_BACHELOR,
               CompetitorTuitionFee.annual_fee.isnot(None))
    ):
        kova.setdefault(kurum_adi, []).append(float(ucret))

    # Kendi kurumumuz AYNI ölçütle: aynı yıl, aynı ücret türü.
    kendi = [float(u) for (u,) in db.execute(
        select(ProgramTuitionFee.annual_fee).where(
            ProgramTuitionFee.academic_year == yil,
            ProgramTuitionFee.fee_type == FEE_HALF_SCHOLARSHIP,
            ProgramTuitionFee.annual_fee.isnot(None)))]
    if kendi:
        kova[HOME_UNIVERSITY] = kendi

    def _med(v: List[float]) -> float:
        v = sorted(v)
        n = len(v)
        return round(float(v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2), 2)

    return {ad: _med(v) for ad, v in kova.items() if v}


from collections import defaultdict
from app.models import YokAtlasBenchmarkMetric, AcademicProgram
from app.services.program_equivalence import canonical_program_key, program_match_type
# Kanonik kulvarın adı tek yerde tanımlıdır; burada tekrar yazılmaz.
from app.services.yok_atlas_comparison_service import SOURCE_DATASET


def _abu_active_canonical_keys(db: Session) -> set[str]:
    records = db.execute(
        select(AcademicProgram.name).where(AcademicProgram.is_active == True)
    ).scalars().all()
    return set(canonical_program_key(name) for name in records if name)


def _program_aggregated_metrics(
    db: Session, matching_mode: str, donem: Optional[str] = None
) -> Dict[str, dict]:
    abu_keys = _abu_active_canonical_keys(db)

    # KULVAR FİLTRESİ — ZORUNLU.
    # ------------------------------------------------------------------
    # Bu tabloda artık birden fazla kulvar var. Kanonik kulvar
    # ("YÖK Atlas dataset 2025") bir bölümün TÜM program kodlarının ve
    # burs varyantlarının tamamını taşır. Ekip derlemesi kulvarı ise
    # yalnızca tek bir varyantı taşır ve 2021/2025 yıllarını içerir.
    #
    # Filtre olmadan bu satırlar buraya sızar ve aşağıdaki döngü
    # `prog["years"][syear][metric]` atamasıyla üzerine yazdığı için
    # rakip profilini sessizce bozardı. Kardeş servisler
    # (program_year_comparison, yok_atlas_comparison) aynı filtreyi
    # zaten uyguluyordu; burada eksikti.
    query = select(
        YokAtlasBenchmarkMetric.university_name,
        YokAtlasBenchmarkMetric.canonical_program_key,
        YokAtlasBenchmarkMetric.program_name,
        YokAtlasBenchmarkMetric.source_year,
        YokAtlasBenchmarkMetric.metric,
        YokAtlasBenchmarkMetric.value,
    ).where(YokAtlasBenchmarkMetric.source_dataset == SOURCE_DATASET)

    rows = db.execute(query).fetchall()

    uni_programs: Dict[str, Dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"name": "", "years": {}, "cohort": 0.0})
    )
    for uname, pkey, pname, syear, metric, val in rows:
        prog = uni_programs[uname][pkey]
        prog["name"] = pname
        if syear not in prog["years"]:
            prog["years"][syear] = {}
        prog["years"][syear][metric] = float(val) if val is not None else None
        if metric == "placed" and val is not None:
            prog["cohort"] += float(val)

    target_year = 2024
    if donem:
        try:
            target_year = int(donem.split("-")[0])
        except Exception:
            target_year = 2024

    out: Dict[str, dict] = {}
    for uname, progs in uni_programs.items():
        raw_count = len(progs)
        matched_progs = {}
        for pkey, pdata in progs.items():
            if matching_mode == MATCHING_ALL:
                matched_progs[pkey] = {**pdata, "match": "all"}
            else:
                best_match = None
                for akey in abu_keys:
                    m = program_match_type(akey, pkey)
                    if m in ("exact", "equivalent"):
                        best_match = m
                        break
                    elif m == "similar" and matching_mode == MATCHING_SIMILAR:
                        best_match = m
                if best_match:
                    matched_progs[pkey] = {**pdata, "match": best_match}

        matched_count = len(matched_progs)
        total_cohort = sum(p["cohort"] for p in matched_progs.values()) if matched_progs else 0
        total_quota = sum(
            p["years"].get(target_year, {}).get("quota", 0) or 0
            for p in matched_progs.values()
        )
        total_placed = sum(
            p["years"].get(target_year, {}).get("placed", 0) or 0
            for p in matched_progs.values()
        )
        occ = round(total_placed / total_quota * 100, 2) if total_quota > 0 else None

        out[uname] = {
            "raw_program_count": raw_count,
            "matched_program_count": matched_count,
            "excluded_program_count": raw_count - matched_count,
            "cohort_size": int(total_cohort) if total_cohort else (0 if matched_count else None),
            "quota": int(total_quota) if total_quota else None,
            "placed": int(total_placed) if total_placed else None,
            "occupancy_percent": occ,
            "matched_programs": [
                {"name": p["name"], "canonical_key": k, "match_type": p["match"]}
                for k, p in matched_progs.items()
            ],
        }
    return out


def _satirlar(
    db: Session,
    donem: Optional[str] = None,
    matching_mode: str = MATCHING_ALL,
) -> List[dict]:
    """Ankara'daki her kurum için tek ölçüm satırı.

    Eksik gösterge `None` kalır; 0 YAZILMAZ.
    """
    yillar = available_years(db)
    if not yillar:
        return []
    if donem:
        if donem not in yillar:
            return []
        son = donem
    else:
        son = yillar[-1]
    gorunen_yillar = yillar[: yillar.index(son) + 1]
    ilk = gorunen_yillar[0]
    profil_donemi = yillar[-1]
    profil_olculebilir = son == profil_donemi

    toplamlar = _yillik_toplamlar(db)
    duzeyler = _duzey_dagilimi(db, son)
    ucretler = _ucret_medyanlari(db, son)
    profiller = {
        p.university_name: p
        for p in db.execute(select(UniversityProfile)).scalars()
    }

    prog_metrics = (
        _program_aggregated_metrics(db, matching_mode, donem)
        if matching_mode in (MATCHING_SAME, MATCHING_SIMILAR)
        else {}
    )

    satirlar = []
    for ad, yil_toplam in toplamlar.items():
        p = profiller.get(ad)
        ogrenci = yil_toplam.get(son)
        _i = gorunen_yillar.index(son)
        onceki_yil = gorunen_yillar[_i - 1] if _i > 0 else None
        kadro = p.academic_staff_count if p and profil_olculebilir else None
        d = duzeyler.get(ad, {})

        if matching_mode in (MATCHING_SAME, MATCHING_SIMILAR):
            pm = prog_metrics.get(ad, {})
            matched_count = pm.get("matched_program_count", 0)
            cohort_val = pm.get("cohort_size")
            quota_val = pm.get("quota")
            placed_val = pm.get("placed")
            occ_val = pm.get("occupancy_percent")
            raw_cnt = pm.get("raw_program_count", p.department_count if p else 0)

            satirlar.append({
                "university_name": ad,
                "university_type": (p.university_type if p else None),
                "is_home_institution": ad == HOME_UNIVERSITY,
                "matching_mode": matching_mode,
                "raw_program_count": raw_cnt,
                "matched_program_count": matched_count,
                "excluded_program_count": pm.get("excluded_program_count", 0),
                "matched_programs": pm.get("matched_programs", []),
                # --- 1) ÖLÇEK (Filtrelenmiş Program Toplamı) ---
                "student_count": cohort_val,
                "previous_student_count": None,
                "growth_percent_yoy": None,
                "growth_percent_period": None,
                "first_student_count": None,
                # --- 2) AKADEMİK KAPASİTE (Program düzeyinde ayrı veri yok -> None) ---
                "academic_staff_count": None,
                "students_per_academic": None,
                "academics_per_100_students": None,
                # --- 3) AKADEMİK ÜRETKENLİK ---
                "total_publications": None,
                "publications_per_academic": None,
                # --- 4) KURUMSAL YAPI ---
                "academic_unit_count": None,
                "department_count": matched_count if matched_count > 0 else None,
                "students_per_department": _oran(cohort_val, matched_count if matched_count > 0 else None),
                # --- 5) PROGRAM DÜZEYİ KONTENJAN VE DOLULUK ---
                "quota": quota_val,
                "placed": placed_val,
                "occupancy_percent": occ_val,
                # --- 6) FİYAT KONUMU ---
                "median_tuition_fee": ucretler.get(ad),
                "by_degree_level": None,
                "yearly_totals": None,
            })
        else:
            raw_cnt = p.department_count if p else (len(d) or None)
            satirlar.append({
                "university_name": ad,
                "university_type": (p.university_type if p else None),
                "is_home_institution": ad == HOME_UNIVERSITY,
                "matching_mode": matching_mode,
                "raw_program_count": raw_cnt,
                "matched_program_count": raw_cnt,
                "excluded_program_count": 0,
                "matched_programs": [],
                # --- 1) ÖLÇEK ve BÜYÜME ---
                "student_count": ogrenci,
                "previous_student_count": (
                    yil_toplam.get(onceki_yil) if onceki_yil else None
                ),
                "growth_percent_yoy": _yuzde(
                    ogrenci, yil_toplam.get(onceki_yil) if onceki_yil else None
                ),
                "growth_percent_period": _yuzde(ogrenci, yil_toplam.get(ilk)),
                "first_student_count": yil_toplam.get(ilk),
                # --- 2) AKADEMİK KAPASİTE ---
                "academic_staff_count": kadro,
                "students_per_academic": _oran(ogrenci, kadro),
                "academics_per_100_students": _oran(
                    (kadro * 100) if kadro is not None else None, ogrenci
                ),
                # --- 3) AKADEMİK ÜRETKENLİK ---
                "total_publications": (
                    p.total_publications if p and profil_olculebilir else None
                ),
                "publications_per_academic": _oran(
                    p.total_publications if p else None, kadro
                ),
                # --- 4) KURUMSAL YAPI ---
                "academic_unit_count": (
                    p.academic_unit_count if p and profil_olculebilir else None
                ),
                "department_count": (
                    p.department_count if p and profil_olculebilir else None
                ),
                "students_per_department": _oran(
                    ogrenci,
                    p.department_count if p and profil_olculebilir else None,
                ),
                # --- 5) PROGRAM DÜZEYİ ---
                "quota": None,
                "placed": None,
                "occupancy_percent": None,
                # --- 6) FİYAT KONUMU ---
                "median_tuition_fee": ucretler.get(ad),
                "by_degree_level": {
                    DEGREE_LEVEL_LABELS.get(k, k): v for k, v in sorted(d.items())
                }
                or None,
                "yearly_totals": {y: yil_toplam.get(y) for y in gorunen_yillar},
            })
    return satirlar


# ---------------------------------------------------------------------------
# Süzme
# ---------------------------------------------------------------------------


def _suz(satirlar: List[dict], mode: str) -> List[dict]:
    """Kip'e göre karşılaştırma kümesi. Kendi kurumumuz DAİMA içeridedir."""
    biz = next((r for r in satirlar if r["is_home_institution"]), None)

    if mode == FILTER_ALL:
        return list(satirlar)
    if mode == FILTER_FOUNDATION:
        secilen = [r for r in satirlar if r["university_type"] == FOUNDATION]
    elif mode == FILTER_STATE:
        secilen = [r for r in satirlar if r["university_type"] == STATE]
    else:
        # BENZER: YALNIZCA ÖLÇEK BANDI. Kurum türü koşul DEĞİLDİR —
        # aynı ölçekteki bir devlet üniversitesi de benzerdir. Ölçek
        # bilinmiyorsa kümeye alınmaz: "benzer" iddiası ölçülemeyen bir
        # kurum için kurulamaz.
        if biz is None or not biz["student_count"]:
            return list(satirlar)
        alt = biz["student_count"] * SIMILAR_LOWER
        ust = biz["student_count"] * SIMILAR_UPPER
        secilen = [
            r for r in satirlar
            if r["student_count"] is not None
            and alt <= r["student_count"] <= ust
        ]
    if biz is not None and biz not in secilen:
        secilen.append(biz)
    return secilen


# ---------------------------------------------------------------------------
# Kapsama kuralı
# ---------------------------------------------------------------------------

# İKİ AYRI "GÖSTERİLEMEZ" SEBEBİ VAR — karıştırılmamalı
# ------------------------------------------------------
#   KAPSAM        : gösterge az sayıda kurumda ölçülü (kohort küçük).
#                   Kapsam genişlerse gösterge kendiliğinden açılır.
#   KARŞILAŞTIRILABİLİRLİK : sayılar var ama AYNI ŞEYİ ölçmüyor.
#                   Kapsam genişlese bile bu düzelmez; ölçüm yönteminin
#                   kendisi kurumdan kuruma değişiyordur.
#
# Yayın sayısı ikinci gruptadır: toplayıcı profil ayrıntısını kurum
# kurum farklı derinlikte indirmiştir. Ankara Bilim'in 164
# akademisyeninde 1540 kayıt, Ankara Üniversitesi'nin 3659
# akademisyeninde 175 kayıt vardır. Bu oranları sıralamak "ABÜ 188 kat
# daha üretken" demek olurdu; ölçtüğümüz şey üretkenlik değil TARAMA
# DERİNLİĞİDİR. Kohort 3'e ulaşsa bile sıralanmaz.
#: Gösterge anahtarı → (etiket, büyük değer iyi mi, karşılaştırılabilir mi,
#:                      karşılaştırılamıyorsa gerekçe)
COMPARISON_METRICS: List[tuple] = [
    ("student_count", "Kayıtlı öğrenci", True, True, None),
    ("growth_percent_period", "4 yıllık büyüme", True, True, None),
    ("growth_percent_yoy", "Son yıl büyümesi", True, True, None),
    ("academic_staff_count", "Akademik personel", True, True, None),
    # Öğrenci/akademisyen oranında KÜÇÜK olan daha iyidir.
    ("students_per_academic", "Öğrenci / akademisyen", False, True, None),
    ("academics_per_100_students", "100 öğrenciye akademisyen", True, True, None),
    ("total_publications", "Toplam yayın", True, False,
     "Yayın kayıtları kurumlara göre farklı derinlikte taranmıştır; "
     "sayılar aynı şeyi ölçmediği için sıralanmaz."),
    ("publications_per_academic", "Akademisyen başına yayın", True, False,
     "Yayın kayıtları kurumlara göre farklı derinlikte taranmıştır; "
     "oranlar aynı şeyi ölçmediği için sıralanmaz."),
    ("academic_unit_count", "Akademik birim", True, True, None),
    ("department_count", "Bölüm", True, True, None),
    ("students_per_department", "Bölüm başına öğrenci", False, True, None),
    # Ücret: büyük değer "iyi" DEĞİLDİR — fiyat konumu bir tercih
    # meselesidir. Sıralama okunabilir olsun diye yüksekten düşüğe
    # gider; `higher_is_better` yorumu arayüzde kullanılmaz.
    ("median_tuition_fee", "Eğitim ücreti medyanı (%50 burslu)", True, True,
     None),
]


#: Bir göstergenin sıralanabilmesi için gereken en az kurum sayısı.
#: İki kurumluk bir "sıralama" karar üretmez; üç ve üzeri anlamlıdır.
MIN_COHORT = 3


def _medyan(degerler: List[float]) -> Optional[float]:
    if not degerler:
        return None
    s = sorted(degerler)
    n = len(s)
    orta = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return round(float(orta), 2)


def _ceyrek(degerler: List[float], buyuk_iyi: bool) -> Optional[float]:
    """En iyi %25'in eşiği — kurumun hedef bandını okumak için."""
    if len(degerler) < 4:
        return None
    s = sorted(degerler, reverse=buyuk_iyi)
    return round(float(s[max(0, len(s) // 4 - 1)]), 2)


def _kohortlar(satirlar: List[dict]) -> Dict[str, dict]:
    """Her gösterge için KENDİ karşılaştırma kohortu.

    Kohort = o göstergeyi ölçebildiğimiz kurumlar. Eksik kurum kohortun
    DIŞINDA kalır, 0 sayılmaz. Sıralama, medyan ve çeyrek değerleri
    yalnızca kohort içinden hesaplanır.
    """
    toplam = len(satirlar)
    out: Dict[str, dict] = {}

    for anahtar, etiket, buyuk_iyi, kiyaslanabilir, gerekce in COMPARISON_METRICS:
        olculen = [r for r in satirlar if r.get(anahtar) is not None]
        degerler = [float(r[anahtar]) for r in olculen]
        # İKİ koşul birden: yeterli kohort VE yöntemsel karşılaştırılabilirlik.
        yeterli = kiyaslanabilir and len(olculen) >= MIN_COHORT

        sirali = sorted(olculen, key=lambda r: r[anahtar],
                        reverse=buyuk_iyi) if yeterli else []
        kohort = []
        for i, r in enumerate(sirali, start=1):
            r.setdefault("ranks", {})[anahtar] = i
            kohort.append({
                "university_name": r["university_name"],
                "university_type": r["university_type"],
                "is_home_institution": r["is_home_institution"],
                "value": r[anahtar],
                "rank": i,
            })

        biz = next((r for r in olculen if r["is_home_institution"]), None)
        medyan = _medyan(degerler) if yeterli else None
        bizim = float(biz[anahtar]) if biz is not None else None

        out[anahtar] = {
            "key": anahtar,
            "label": etiket,
            "higher_is_better": buyuk_iyi,
            "comparable": kiyaslanabilir,
            "measured_count": len(olculen),
            "total_count": toplam,
            # Ekranda gösterilecek kapsam notu — grafik kendi kümesini söyler.
            "coverage_note": f"{len(olculen)} / {toplam} kurumda veri",
            "available": yeterli,
            "cohort": kohort,
            "cohort_size": len(kohort),
            "median": medyan,
            "top_quartile": _ceyrek(degerler, buyuk_iyi) if yeterli else None,
            "home_value": bizim,
            "home_rank": (biz.get("ranks", {}).get(anahtar)
                          if biz is not None and yeterli else None),
            "home_vs_median": (round(bizim - medyan, 2)
                               if bizim is not None and medyan is not None
                               else None),
            "home_measured": biz is not None,
            "note": (
                None if yeterli
                else gerekce if not kiyaslanabilir
                else (f"Karşılaştırma için yeterli kurum yok "
                      f"({len(olculen)} kurumda ölçülü, "
                      f"en az {MIN_COHORT} gerekir).")),
            "unavailable_reason": (
                None if yeterli
                else "not_comparable" if not kiyaslanabilir
                else "insufficient_cohort"),
        }

    for r in satirlar:
        r.setdefault("ranks", {})
    return out


def _ozet(biz: dict, ankara_sira: Optional[int], ankara_adet: int,
          kapsam: Dict[str, dict]) -> dict:
    """Üst yönetim kartları.

    Her gösterge için kurumun KENDİ kohortundaki konumu da verilir:
    sıra, kohort büyüklüğü, kohort medyanı, medyandan fark ve en iyi
    çeyreğin eşiği. Bunlar tavsiye değil KONUM bilgisidir.
    """
    konum = {
        anahtar: {
            "rank": bilgi["home_rank"],
            "cohort_size": bilgi["cohort_size"],
            "median": bilgi["median"],
            "difference_from_median": bilgi["home_vs_median"],
            "top_quartile": bilgi["top_quartile"],
            "coverage_note": bilgi["coverage_note"],
        }
        for anahtar, bilgi in kapsam.items()
        if bilgi["available"] and bilgi["home_rank"] is not None
    }
    return {
        "position": konum,
        "university_name": biz["university_name"],
        "university_type": biz["university_type"],
        "student_count": biz["student_count"],
        "growth_percent_period": biz["growth_percent_period"],
        "growth_percent_yoy": biz["growth_percent_yoy"],
        "students_per_academic": biz["students_per_academic"],
        "academic_staff_count": biz["academic_staff_count"],
        "academics_per_100_students": biz["academics_per_100_students"],
        "academic_unit_count": biz["academic_unit_count"],
        "department_count": biz["department_count"],
        "students_per_department": biz["students_per_department"],
        "by_degree_level": biz["by_degree_level"],
        "ankara_rank": ankara_sira,
        "ankara_university_count": ankara_adet,
        "ranks": biz.get("ranks", {}),
    }


def _filtre_secenekleri() -> List[dict]:
    return [{"value": k, "label": v,
             "is_default": k == DEFAULT_FILTER} for k, v in FILTER_LABELS.items()]


def _eslesme_secenekleri() -> List[dict]:
    return [{"value": k, "label": v,
             "is_default": k == DEFAULT_MATCHING} for k, v in MATCHING_LABELS.items()]


def competitor_analysis(
    db: Session,
    filter_mode: Optional[str] = None,
    donem: Optional[str] = None,
    matching_mode: Optional[str] = None,
) -> dict:
    """Üniversite seviyesi rakip analizi panosunun tek veri kaynağı."""
    mode = filter_mode or DEFAULT_FILTER
    if mode not in FILTER_LABELS:
        mode = DEFAULT_FILTER

    mmode = matching_mode or DEFAULT_MATCHING
    if mmode not in MATCHING_LABELS:
        mmode = DEFAULT_MATCHING

    hepsi = _satirlar(db, donem, mmode)
    if not hepsi:
        return {
            "available": False,
            "filter_mode": mode,
            "matching_mode": mmode,
            "requested_period": donem,
            "note": (f"{donem} döneminde kayıtlı öğrenci sayısı yayımlanmamış."
                     if donem else
                     "Kayıtlı öğrenci sayısı verisi yüklenmemiş."),
            "universities": [],
            "metrics": {},
            "filters": _filtre_secenekleri(),
            "matching_options": _eslesme_secenekleri(),
        }

    satirlar = _suz(hepsi, mode)
    kapsam = _kohortlar(satirlar)
    satirlar.sort(key=lambda r: (r["student_count"] is None,
                                 -(r["student_count"] or 0)))

    biz = next((r for r in satirlar if r["is_home_institution"]), None)
    yillar = available_years(db)
    hedef_donem = donem or (yillar[-1] if yillar else None)
    donem_sayisi = (
        yillar.index(hedef_donem) + 1
        if hedef_donem in yillar else len(yillar))
    profil_donemi = yillar[-1] if yillar else None
    profil_notu = (
        f"Akademik profil {profil_donemi} dönemine aittir; "
        f"{hedef_donem} seçiliyken kadro, yayın ve birim ölçümleri "
        "gösterilmez."
        if hedef_donem and profil_donemi and hedef_donem != profil_donemi
        else None)

    # Ankara sıralaması DAİMA tüm liste üzerinden verilir: süzgeç
    # değiştikçe kurumun "Ankara'da kaçıncı" cevabı değişmemeli.
    ankara = sorted((r for r in hepsi if r["student_count"] is not None),
                    key=lambda r: -r["student_count"])
    ankara_sira = next((i for i, r in enumerate(ankara, start=1)
                        if r["is_home_institution"]), None)

    return {
        "available": True,
        "academic_year": hedef_donem,
        "first_academic_year": yillar[0] if yillar else None,
        "year_count": donem_sayisi,
        "profile_academic_year": profil_donemi,
        "profile_note": profil_notu,
        "filter_mode": mode,
        "filter_label": FILTER_LABELS[mode],
        "matching_mode": mmode,
        "matching_mode_label": MATCHING_LABELS[mmode],
        "matching_options": _eslesme_secenekleri(),
        # KARŞILAŞTIRMA EVRENİNİN BİLEŞİMİ — ekranda ve asistanda
        # "hangi kurumlarla kıyaslıyorum?" sorusu sayıyla yanıtlanabilsin.
        "type_breakdown": {
            "DEVLET": sum(1 for r in satirlar
                          if r["university_type"] == STATE
                          and not r["is_home_institution"]),
            "VAKIF": sum(1 for r in satirlar
                         if r["university_type"] == FOUNDATION
                         and not r["is_home_institution"]),
            "UNKNOWN": sum(1 for r in satirlar
                           if r["university_type"] not in (STATE, FOUNDATION)
                           and not r["is_home_institution"]),
        },
        # Türü bilinmeyen kurumlar Devlet/Vakıf süzgeçlerine GİREMEZ.
        # Uydurma bir tür atamak yerine dışarıda bırakılır ve sebebi
        # açıkça bildirilir.
        "excluded_unknown_type": (
            [r["university_name"] for r in hepsi
             if r["university_type"] not in (STATE, FOUNDATION)
             and not r["is_home_institution"]]
            if mode in (FILTER_STATE, FILTER_FOUNDATION) else []
        ),
        "excluded_unknown_type_reason": (
            "Kurum türü (devlet/vakıf) kaynakta belirtilmediği için "
            "tür süzgecine alınmadı; tür uydurulmaz."
            if mode in (FILTER_STATE, FILTER_FOUNDATION) else None
        ),
        "filters": _filtre_secenekleri(),
        "universities": satirlar,
        "university_count": len(satirlar),
        "ankara_university_count": len(hepsi),
        "metrics": kapsam,
        # Sıralanabilir göstergeler (kohortu yeterli olanlar).
        "available_metrics": [k for k, v in kapsam.items() if v["available"]],
        "unavailable_metrics": [
            {"key": k, "label": v["label"],
             "measured_count": v["measured_count"],
             "total_count": v["total_count"],
             "reason": v["note"]}
            for k, v in kapsam.items() if not v["available"]
        ],
        "home": _ozet(biz, ankara_sira, len(ankara), kapsam) if biz else None,
        "similar_rule": {
            "label": FILTER_LABELS[FILTER_SIMILAR],
            "explanation": (
                "Aynı türdeki (vakıf/devlet) kurumlardan, kayıtlı öğrenci "
                f"sayısı kurumumuzun {SIMILAR_LOWER:g}–{SIMILAR_UPPER:g} katı "
                "aralığında olanlar. Liste elle tutulmaz; kurum büyüdükçe "
                "küme kendiliğinden güncellenir."
            ),
            "lower_multiplier": SIMILAR_LOWER,
            "upper_multiplier": SIMILAR_UPPER,
            "reference_student_count": (
                next((r["student_count"] for r in hepsi
                      if r["is_home_institution"]), None)),
        },
        "source": ("YÖK kayıtlı öğrenci sayıları + YÖK Akademik "
                   "toplayıcısı + YÖK Atlas"),
    }
