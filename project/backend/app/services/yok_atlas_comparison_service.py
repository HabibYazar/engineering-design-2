"""Scope-safe comparisons backed by the secondary Ankara YÖK Atlas data."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Dict, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcademicProgram,
    ComparableUniversityProgram,
    Faculty,
    YokAtlasBenchmarkMetric,
    YksPlacementRecord,
)
from app.models.university_headcount import HOME_UNIVERSITY
from app.services.program_equivalence import (
    ENGINEERING_ARCHITECTURE,
    MATCH_EQUIVALENT,
    MATCH_EXACT,
    MATCH_SIMILAR,
    canonical_faculty_key,
    canonical_program_family,
    canonical_program_key,
    discipline_family,
    display_program_name,
    program_match_type,
)
from app.services.scope import FACULTY_LEVEL, PROGRAM_LEVEL, UNIVERSITY, Scope
from app.services.student_count import _donem_yili


SOURCE_DATASET = "YÖK Atlas dataset 2025"
SOURCE_FILE = "yokatlas_ankara_2022_plus.csv"
SUPPORTED_YEARS = (2022, 2023, 2024)

#: EKİP DERLEMESİ KULVARI — 2021 ve 2025.
#: ---------------------------------------------------------------------
#: `import_team_2021_2025.py` bu etiketle yazar. Kanonik kulvardan AYRI
#: tutulur çünkü grain'i farklıdır: kanonik kulvar bir bölümün tüm YÖK
#: program kodlarının ve burs varyantlarının toplamını taşır, bu kulvar
#: ise tek bir varyantı taşır.
#:
#: Bu ayrım ölçülmüştür: 2025 kayıtlarının 26'sı "Burslu" varyantıdır ve
#: burslu kontenjanlar her zaman dolduğu (çoğu kez ek yerleştirmeyle
#: taştığı) için 47 kaydın 37'si %100 üzerinde doluluk gösterir; kulvarın
#: 2025 doluluk ortalaması %112'dir. 2021 tarafı görece temizdir
#: (ortalama %97, 24 kayıttan yalnızca 2'si %100 üzeri).
#:
#: Bu sabiti bir sorguya EKLEYEN, o sorgunun çıktısının artık karışık
#: grain taşıdığını kabul etmiş olur. Varsayılan hiçbir yerde eklenmez;
#: yalnızca `program_year_comparison_service` bilinçli olarak ekler ve
#: sonucu arayüzde dipnotla işaretler.
TEAM_SOURCE_DATASET = "Ekip derlemesi 2021-2025 (varyant düzeyi)"
TEAM_YEARS = (2021, 2025)
ADDITIVE_METRICS = {
    "quota",
    "placed",
    "preference_total",
    "preference_first",
    "preference_top3",
    "preference_top9",
}


def _cohort_year_label(target_year: int) -> str:
    """Keep the single-year label natural while retaining inclusive ranges."""
    return "2022" if target_year == 2022 else f"2022-{target_year}"


def _source_window(years: tuple[int, ...]) -> str:
    return str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}"


def _cohort_methodology(source_target_year: int, latest_available: bool) -> str:
    if latest_available:
        return (
            "2022-2024 YÖK Atlas yerleşen kohortları toplamı; "
            "2025 verisi kaynakta bulunmadığı için son mevcut pencere "
            "kullanılmıştır. Resmî kayıtlı öğrenci sayısı değildir."
        )
    return (
        f"{_cohort_year_label(source_target_year)} YKS yerleşen kohortları "
        "toplamı; resmî kayıtlı öğrenci sayısı değildir."
    )


def _aggregate(values: Iterable[Decimal], metric: str) -> Optional[Decimal]:
    values = [Decimal(v) for v in values]
    if not values:
        return None
    if metric == "base_score":
        positive = [v for v in values if v > 0]
        return min(positive) if positive else None
    if metric == "success_rank":
        positive = [v for v in values if v > 0]
        return max(positive) if positive else None
    return sum(values, Decimal("0"))


def _number(value: Optional[Decimal]):
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else round(float(value), 5)


def _annual_from_atlas(metrics: Iterable[YokAtlasBenchmarkMetric]) -> dict:
    grouped: Dict[int, Dict[str, list[Decimal]]] = defaultdict(
        lambda: defaultdict(list)
    )
    references: Dict[int, set[str]] = defaultdict(set)
    for metric in metrics:
        if metric.metric == "occupancy_percent":
            continue  # recomputed from the aggregate quota and placed counts
        grouped[metric.source_year][metric.metric].append(metric.value)
        references[metric.source_year].add(metric.source_program_code)

    annual = {}
    for year, metric_values in grouped.items():
        values = {
            metric: _aggregate(items, metric)
            for metric, items in metric_values.items()
        }
        quota, placed = values.get("quota"), values.get("placed")
        values["occupancy_percent"] = (
            placed / quota * Decimal("100")
            if quota is not None and quota > 0 and placed is not None
            else None
        )
        annual[year] = {
            **{metric: _number(value) for metric, value in values.items()},
            "source_row_references": sorted(references[year]),
            "source": SOURCE_DATASET,
            "metric_sources": {
                metric: SOURCE_DATASET
                for metric, value in values.items()
                if value is not None
            },
        }
    return annual


def _merge_existing_comparable(
    db: Session,
    groups: dict,
    canonical_keys: set[str],
    years: tuple[int, ...],
) -> None:
    """Overlay existing project comparator values, filling only their gaps."""
    if not canonical_keys:
        return
    records = db.execute(
        select(ComparableUniversityProgram).where(
            ComparableUniversityProgram.academic_year.in_(
                [f"{year}-{year + 1}" for year in years]
            )
        )
    ).scalars().all()
    for record in records:
        key = canonical_program_key(record.program_name)
        if key not in canonical_keys:
            continue
        year = _donem_yili(record.academic_year)
        if year not in years:
            continue
        matching = [
            group
            for identity, group in groups.items()
            if identity[0] == record.university_name and identity[-1] == key
        ]
        for group in matching:
            annual = group["annual"].setdefault(
                year,
                {
                    "source_row_references": [],
                    "source": "Mevcut proje karşılaştırma verisi",
                },
            )
            # Existing project values win even when they are zero.
            annual["quota"] = record.quota
            annual["placed"] = record.enrolled_student_count
            annual["occupancy_percent"] = (
                float(record.occupancy_rate)
                if record.occupancy_rate is not None
                else (
                    round(record.enrolled_student_count / record.quota * 100, 5)
                    if record.quota else None
                )
            )
            if record.minimum_admission_score is not None:
                annual["base_score"] = float(record.minimum_admission_score)
            annual["source"] = "Mevcut proje karşılaştırma verisi"
            annual.setdefault("metric_sources", {}).update(
                {
                    "quota": "Mevcut proje karşılaştırma verisi",
                    "placed": "Mevcut proje karşılaştırma verisi",
                    "occupancy_percent": "Mevcut proje karşılaştırma verisi",
                    **(
                        {"base_score": "Mevcut proje karşılaştırma verisi"}
                        if record.minimum_admission_score is not None
                        else {}
                    ),
                }
            )


def _internal_home_annual(
    db: Session, program_ids: Optional[Iterable[int]], years: tuple[int, ...]
) -> dict:
    if program_ids is None:
        return {}
    program_ids = tuple(program_ids)
    if not program_ids:
        return {}
    records = db.execute(
        select(YksPlacementRecord).where(
            YksPlacementRecord.academic_program_id.in_(program_ids),
            YksPlacementRecord.placement_year.in_(years),
        )
    ).scalars().all()
    grouped: Dict[int, Dict[str, list[Decimal]]] = defaultdict(
        lambda: defaultdict(list)
    )
    refs: Dict[int, set[str]] = defaultdict(set)
    for record in records:
        values = {
            "quota": record.quota,
            "placed": record.placed_students,
            "base_score": record.base_score,
            "success_rank": record.success_rank,
        }
        for metric, raw in values.items():
            if raw is None or (metric in {"base_score", "success_rank"} and raw <= 0):
                continue
            grouped[record.placement_year][metric].append(Decimal(raw))
        refs[record.placement_year].add(
            record.source_row_key or str(record.id)
        )

    annual = {}
    for year, metric_values in grouped.items():
        values = {
            metric: _aggregate(items, metric)
            for metric, items in metric_values.items()
        }
        quota, placed = values.get("quota"), values.get("placed")
        values["occupancy_percent"] = (
            placed / quota * Decimal("100")
            if quota is not None and quota > 0 and placed is not None
            else None
        )
        annual[year] = {
            **{metric: _number(value) for metric, value in values.items()},
            "source": "Mevcut ABÜ ÖSYM/YKS verisi",
            "source_row_references": sorted(refs[year]),
            "metric_sources": {
                metric: "Mevcut ABÜ ÖSYM/YKS verisi"
                for metric, value in values.items()
                if value is not None
            },
        }
    return annual


def _fill_home_missing(home: dict, atlas_home_groups: list[dict], years: tuple[int, ...]) -> None:
    """Use Atlas only for a missing ABÜ annual metric; never overwrite."""
    for year in years:
        atlas_annual = [
            group["annual"][year]
            for group in atlas_home_groups
            if year in group["annual"]
        ]
        if not atlas_annual:
            continue
        target = home.setdefault(
            year,
            {"source": SOURCE_DATASET, "source_row_references": []},
        )
        filled_any = False
        for metric in (
            "quota",
            "placed",
            "base_score",
            "success_rank",
            "preference_total",
            "preference_first",
            "preference_top3",
            "preference_top9",
        ):
            if target.get(metric) is not None:
                continue
            values = [a[metric] for a in atlas_annual if a.get(metric) is not None]
            value = _aggregate([Decimal(str(v)) for v in values], metric)
            if value is not None:
                target[metric] = _number(value)
                target.setdefault("metric_sources", {})[metric] = SOURCE_DATASET
                filled_any = True
        if target.get("occupancy_percent") is None:
            quota, placed = target.get("quota"), target.get("placed")
            if quota and placed is not None:
                target["occupancy_percent"] = round(placed / quota * 100, 5)
                target.setdefault("metric_sources", {})["occupancy_percent"] = (
                    target.get("metric_sources", {}).get("placed", target["source"])
                )
        atlas_refs = {
            ref
            for annual in atlas_annual
            for ref in annual.get("source_row_references", [])
        }
        target["cross_check_source_row_references"] = sorted(atlas_refs)
        if filled_any:
            target["source_row_references"] = sorted(
                set(target.get("source_row_references", [])) | atlas_refs
            )


def _finalize_group(
    group: dict,
    years: tuple[int, ...],
    source_target_year: int,
    latest_available: bool,
) -> dict:
    annual = group["annual"]
    placed_values = [
        annual[year].get("placed")
        for year in years
        if year in annual and annual[year].get("placed") is not None
    ]
    current = annual.get(source_target_year, {})
    cohort_size = sum(placed_values) if placed_values else None
    row_refs = sorted(
        {
            ref
            for year in years
            for ref in annual.get(year, {}).get("source_row_references", [])
        }
    )
    metric_sources = {
        metric: current.get("metric_sources", {}).get(metric, current.get("source"))
        for metric in (
            "quota",
            "placed",
            "occupancy_percent",
            "base_score",
            "success_rank",
            "preference_total",
            "preference_first",
        )
        if current.get(metric) is not None
    }
    cohort_sources = sorted(
        {
            annual[year].get("metric_sources", {}).get(
                "placed", annual[year].get("source")
            )
            for year in years
            if year in annual and annual[year].get("placed") is not None
        }
    )
    metric_sources["cohort_size"] = cohort_sources
    return {
        "university_name": group["university_name"],
        "faculty_name": group.get("faculty_name"),
        "program_name": group.get("program_name"),
        "canonical_program_key": group.get("canonical_program_key"),
        "label": group["label"],
        "is_home_institution": group.get("is_home_institution", False),
        # Kurum türü YETKİLİ kaynaktan taşınır; bilinmiyorsa None kalır
        # (uydurulmaz) ve tür süzgeçlerine giremez.
        "university_type": group.get("university_type"),
        # Bu satırın karşılaştırmaya HANGİ GEREKÇEYLE girdiği satırın
        # kendisinde taşınır; arayüz rozet için provenance'ı kazmak
        # zorunda kalmaz ve gerekçe veriden ayrı düşemez.
        "match_type": group.get("match_type"),
        "match_reason": group.get("match_reason"),
        "cohort_size": cohort_size,
        "quota": current.get("quota"),
        "placed_students": current.get("placed"),
        "occupancy_percent": current.get("occupancy_percent"),
        "base_score": current.get("base_score"),
        "success_rank": current.get("success_rank"),
        "preference_total": current.get("preference_total"),
        "preference_first": current.get("preference_first"),
        "metric_sources": metric_sources,
        "yearly": [
            {"source_year": year, "academic_year": f"{year}-{year + 1}", **annual[year]}
            for year in years
            if year in annual
        ],
        "provenance": {
            "source": (
                "Mevcut proje verisi; eksik alanlarda YÖK Atlas"
                if group.get("is_home_institution")
                else SOURCE_DATASET
            ),
            "source_file": SOURCE_FILE,
            "source_years": list(years),
            "metric": [
                "cohort_size",
                "quota",
                "placed",
                "occupancy_percent",
                "base_score",
                "success_rank",
            ],
            "derived": True,
            "methodology": (
                f"{_cohort_methodology(source_target_year, latest_available)} "
                "Cari kaynak yılı kontenjan, "
                "yerleşen ve doluluk değerleri ayrı gösterilir."
            ),
            "canonical_program_key": group.get("canonical_program_key"),
            "original_source_faculty_label": group.get("faculty_name"),
            "included_programs": group.get("included_programs", []),
            "excluded_programs": group.get("excluded_programs", []),
            "latest_available": latest_available,
            "source_window": _source_window(years),
            "contains_2025_data": False,
            "source_row_references": row_refs,
            "cross_check_source_row_references": sorted(
                {
                    ref
                    for year in years
                    for ref in annual.get(year, {}).get(
                        "cross_check_source_row_references", []
                    )
                }
            ),
        },
    }


#: Kurum türü süzgeci — ORTAK PROGRAM METODOLOJİSİNDEN BAĞIMSIZ.
#: İki boyut ayrı ayrı uygulanır ve birbirini etkilemez:
#:     uygun akran  →  KURUM TÜRÜ süzgeci  →  ORTAK/EŞDEĞER PROGRAM süzgeci
#: "Devlet + MMF" yalnızca devlet kurumlarını alır ama yine SADECE ortak
#: mühendislik programlarını kıyaslar; fakültenin tamamı geri gelmez.
INSTITUTION_TYPE_ALL = "all"
INSTITUTION_TYPE_STATE = "state"
INSTITUTION_TYPE_FOUNDATION = "foundation"
INSTITUTION_TYPE_SIMILAR = "similar"
_TYPE_VALUE = {INSTITUTION_TYPE_STATE: "DEVLET",
               INSTITUTION_TYPE_FOUNDATION: "VAKIF"}

# ---------------------------------------------------------------------------
# 2. BOYUT — PROGRAM EŞLEŞTİRME KİPİ ("Aynı / Benzer / Ortak Bölümler")
# ---------------------------------------------------------------------------
# Kurum türü boyutundan TAMAMEN BAĞIMSIZDIR. Biri HANGİ KURUMLAR, diğeri
# HANGİ PROGRAMLAR sorusuna cevap verir. İkisi çarpım olarak uygulanır ve
# hiçbiri diğerinin varsayılanını değiştirmez.
#
#   same_program     Yalnızca aynı kanonik program (exact + equivalent).
#   similar_programs Aynı program + AYNI DAR DİSİPLİN AİLESİ (+ similar).
#                    "mühendislik" içermek ölçüt DEĞİLDİR.
#   shared_programs  Kendi fakültemizde de bulunan programların fakülte
#                    düzeyinde toplamı (mevcut ortak-bölüm metodolojisi).
MATCH_MODE_ALL = "all_programs"
MATCH_MODE_SAME = "same_program"
MATCH_MODE_SIMILAR = "similar_programs"
MATCH_MODE_SHARED = "shared_programs"
MATCH_MODES = (MATCH_MODE_ALL, MATCH_MODE_SAME, MATCH_MODE_SIMILAR, MATCH_MODE_SHARED)
MATCH_MODE_LABELS = {
    MATCH_MODE_ALL: "Hepsi",
    MATCH_MODE_SAME: "Aynı Bölümler",
    MATCH_MODE_SIMILAR: "Benzer Bölümler",
    MATCH_MODE_SHARED: "Ortak Bölümler",
}


def default_match_mode(scope: Optional[Scope]) -> str:
    """Bağlama göre varsayılan eşleştirme kipi.

    Program/bölüm kapsamı → "Aynı Bölüm" (elmayla elma).
    Fakülte kapsamı       → "Ortak Bölümler" (tek bir "aynı bölüm" yoktur).

    Varsayılan kurum türü süzgecinden BAĞIMSIZ hesaplanır; kurum türü her
    zaman "Tümü" kalır.
    """
    return (MATCH_MODE_SHARED
            if scope is not None and scope.level == FACULTY_LEVEL
            else MATCH_MODE_SAME)


def _university_types(db: Session) -> Dict[str, Optional[str]]:
    """Kurum adı → DEVLET/VAKIF. YETKİLİ alan `university_profiles`tir.

    `benchmark_institutions.institution_type` KULLANILMAZ: o alan rekabet
    rolünü ('similar'/'competitor') taşır, hukuki kurum türünü değil.
    Bugün ikisi tesadüfen örtüşüyor; bir gün örtüşmediğinde sessizce
    yanlış cevap üretirdi.
    """
    from app.models.university_profile import UniversityProfile

    return {
        p.university_name: p.university_type
        for p in db.execute(select(UniversityProfile)).scalars()
    }


def _similar_universities(db: Session) -> set[str]:
    """ABÜ ile öğrenci sayısı ölçeği benzer kurumlar (0.35x - 3.0x).

    Hem DEVLET hem VAKIF kurumları girebilir (hukuki statüye değil, öğrenci
    ölçeğine bakar). Kendi kurumumuz her zaman dâhildir.
    """
    from app.services.university_competitor_service import (
        SIMILAR_LOWER,
        SIMILAR_UPPER,
        _satirlar,
    )
    satirlar = _satirlar(db)
    biz = next((r for r in satirlar if r["is_home_institution"]), None)
    if biz is None or not biz.get("student_count"):
        return {r["university_name"] for r in satirlar}
    alt = biz["student_count"] * SIMILAR_LOWER
    ust = biz["student_count"] * SIMILAR_UPPER
    secilen = {
        r["university_name"]
        for r in satirlar
        if r.get("student_count") is not None and alt <= r["student_count"] <= ust
    }
    secilen.add(HOME_UNIVERSITY)
    return secilen


def _dislanan_akran_programlari(
    db: Session,
    years: tuple[int, ...],
    fakulte_anahtari: Optional[str],
    izinli_anahtarlar: set[str],
    tur_haritasi: Dict[str, Optional[str]],
    tur_kipi: str,
    benzer_kurumlar: Optional[set[str]] = None,
) -> list[dict]:
    """Akranın KIYASLANABİLİR fakültesinde olup dışarıda kalan programlar.

    Dürüst payda budur: "akranın diğer 11 ilgisiz programı" ifadesi ancak
    aynı fakülte evreninde anlamlıdır. Tüm Ankara evreni üzerinden sayım
    yapmak sayıyı şişirir ve kullanıcıyı yanıltır.

    Kabul edilen satırların süzgeci SQL'de uygulandığı için dışlananlar
    Python döngüsünde görünmez; bu yüzden ayrı ve HAFİF bir sorguyla
    (yalnızca kimlik sütunları, ORM nesnesi değil) hesaplanır.
    """
    if not fakulte_anahtari:
        return []
    satirlar = db.execute(
        select(
            YokAtlasBenchmarkMetric.university_name,
            YokAtlasBenchmarkMetric.faculty_name,
            YokAtlasBenchmarkMetric.program_name,
            YokAtlasBenchmarkMetric.canonical_program_key,
        )
        .where(
            YokAtlasBenchmarkMetric.source_dataset == SOURCE_DATASET,
            YokAtlasBenchmarkMetric.source_year.in_(years),
            YokAtlasBenchmarkMetric.canonical_faculty_key == fakulte_anahtari,
            YokAtlasBenchmarkMetric.university_name != HOME_UNIVERSITY,
        )
        .distinct()
    ).all()
    istenen_tur = _TYPE_VALUE.get(tur_kipi)
    sonuc: list[dict] = []
    for uni, fak, prog, anahtar in satirlar:
        if anahtar in izinli_anahtarlar:
            continue
        # Kurum türü / ölçek süzgeci dışarıda bıraktıysa gerekçe ORADADIR; aynı
        # kurumu iki farklı gerekçeyle iki kez raporlamayız.
        if tur_kipi == INSTITUTION_TYPE_SIMILAR and benzer_kurumlar is not None:
            if uni not in benzer_kurumlar:
                continue
        elif istenen_tur and tur_haritasi.get(uni) != istenen_tur:
            continue
        sonuc.append({
            "university_name": uni,
            "original_source_faculty_label": fak,
            "program_name": prog,
            "canonical_program_key": anahtar,
            "program_family": canonical_program_family(anahtar),
            "discipline_family": discipline_family(anahtar),
            "match_type": None,
            "reason": "program_not_academically_similar",
            "source_row_references": [],
        })
    sonuc.sort(key=lambda x: (x["university_name"], x["program_name"] or ""))
    return sonuc


def _eslesme_aciklamasi(kip: str, groups: dict, dislananlar: list,
                        fakulte_toplami: bool) -> str:
    """İnsan tarafından okunabilir tek cümlelik gerekçe.

    Sayılar burada TÜRETİLMEZ; yalnızca zaten hesaplanmış kümelerin
    büyüklüğü aktarılır. Böylece metin ile veri asla ayrışamaz.
    """
    if fakulte_toplami:
        return ("Karşılaştırma yalnızca kendi fakültemizde de bulunan ortak "
                "programlar üzerinden yapıldı; gösterilen değer akran kurumun "
                "tüm fakülte nüfusu değildir.")
    # Sayılar ayrı ayrı adlandırılır: "kaç farklı program" ile "kaç satır"
    # aynı şey değildir ve ikisini karıştırmak metni yanlış yapardı.
    programlar = {
        item["canonical_program_key"]
        for group in groups.values()
        for item in group["included_programs"]
    }
    kurumlar = {group["university_name"] for group in groups.values()}
    dislanan_akran = sum(1 for item in dislananlar
                         if item["university_name"] != HOME_UNIVERSITY)
    if kip == MATCH_MODE_SIMILAR:
        return (f"Bu karşılaştırmada {len(kurumlar)} akran üniversiteden "
                f"{len(programlar)} akademik olarak benzer program kullanıldı. "
                f"Akran üniversitelerin aynı fakültedeki diğer {dislanan_akran} "
                "ilgisiz programı karşılaştırmaya dâhil edilmedi.")
    return (f"Bu karşılaştırmada {len(kurumlar)} akran üniversitede yalnızca "
            f"aynı bölümün karşılığı kullanıldı. Akran üniversitelerin aynı "
            f"fakültedeki diğer {dislanan_akran} programı karşılaştırmaya "
            "dâhil edilmedi.")


def comparison(
    db: Session,
    scope: Optional[Scope] = None,
    academic_year: Optional[str] = None,
    institution_type: Optional[str] = None,
    matching_mode: Optional[str] = None,
) -> dict:
    scope = scope or Scope()
    tur_kipi = (institution_type or INSTITUTION_TYPE_ALL).strip().lower()
    if tur_kipi not in (INSTITUTION_TYPE_ALL, INSTITUTION_TYPE_STATE,
                        INSTITUTION_TYPE_FOUNDATION, INSTITUTION_TYPE_SIMILAR):
        tur_kipi = INSTITUTION_TYPE_ALL
    # İkinci boyut ayrı çözülür: kurum türü kipini OKUMAZ, ona yazmaz.
    eslesme_kipi = (matching_mode or "").strip().lower()
    if eslesme_kipi not in MATCH_MODES:
        eslesme_kipi = default_match_mode(scope)
    tur_haritasi = _university_types(db)
    target_year = _donem_yili(academic_year) if academic_year else 2024
    base = {
        "level": scope.level,
        "requested_period": academic_year,
        "source": SOURCE_DATASET,
        "source_file": SOURCE_FILE,
        "metric_label": "YÖK Atlas Kohort Büyüklüğü",
        "registered_headcount": False,
        "latest_available": False,
        "source_window": None,
        "contains_2025_data": False,
        "available": False,
        "peers": [],
        # İki boyut erken dönüşlerde de taşınır ki arayüz seçicileri
        # hiçbir durumda "bilinmiyor" hâline düşmesin.
        "institution_type_filter": tur_kipi,
        "matching_mode": eslesme_kipi,
        "matching_mode_label": MATCH_MODE_LABELS[eslesme_kipi],
    }
    if scope.level == UNIVERSITY:
        return {
            **base,
            "note": (
                "Üniversite kapsamında mevcut resmî YÖK kayıtlı öğrenci "
                "karşılaştırması kullanılır; Atlas kohortu onun yerine geçmez."
            ),
        }
    latest_available = academic_year == "2025-2026"
    if target_year not in SUPPORTED_YEARS and not latest_available:
        return {
            **base,
            "note": (
                f"{academic_year or target_year} için YÖK Atlas kaynak yılı yok; "
                "2024-2025 değeri ileri taşınmadı."
            ),
        }

    source_target_year = 2024 if latest_available else target_year
    years = tuple(year for year in SUPPORTED_YEARS if year <= source_target_year)
    program_keys: set[str] = set()
    faculty_key: Optional[str] = None
    selected_label = scope.label
    selected_faculty_name: Optional[str] = None

    if scope.level == FACULTY_LEVEL and scope.faculty_id:
        faculty = db.get(Faculty, scope.faculty_id)
        selected_faculty_name = faculty.name if faculty else scope.label
        selected_label = selected_faculty_name
        faculty_key = canonical_faculty_key(selected_faculty_name)
    else:
        programs = db.execute(
            select(AcademicProgram).where(
                AcademicProgram.id.in_(scope.program_ids or ())
            )
        ).scalars().all()
        program_keys = {
            key
            for key in (canonical_program_key(program.name) for program in programs)
            if key
        }
        if not program_keys:
            return {**base, "note": "Seçili kapsam için kanonik program bulunamadı."}
        selected_label = display_program_name(programs[0].name) if len(programs) == 1 else scope.label

    required_program_family = (
        ENGINEERING_ARCHITECTURE
        if faculty_key == "ENGINEERING_FACULTY"
        else None
    )

    # Faculty-level (e.g. "Mühendislik Fakülteleri") comparisons must stay
    # scoped to the programs the home institution ACTUALLY OFFERS in that
    # faculty ("ortak bölümler"). Otherwise a peer whose engineering faculty
    # simply has more distinct programs (e.g. ODTÜ) inflates its total with
    # programs the home institution doesn't have at all, which is not an
    # apples-to-apples comparison. This must be computed before we filter
    # the peer Atlas rows below.
    home_included_programs: list[dict] = []
    home_excluded_programs: list[dict] = []
    home_program_ids: list[int] = []
    home_canonical_keys: set[str] = set()
    if faculty_key:
        home_programs = db.execute(
            select(AcademicProgram).where(
                AcademicProgram.id.in_(scope.program_ids or ())
            )
        ).scalars().all()
        for program in home_programs:
            key = canonical_program_key(program.name)
            family = canonical_program_family(key)
            detail = {
                "program_name": display_program_name(program.name),
                "canonical_program_key": key,
                "program_family": family,
            }
            if required_program_family and family != required_program_family:
                exclusion = {
                    "university_name": HOME_UNIVERSITY,
                    "original_source_faculty_label": selected_faculty_name,
                    **detail,
                    "reason": "program_family_incompatible_with_engineering_faculty",
                    "source_row_references": [],
                }
                home_excluded_programs.append(exclusion)
            else:
                home_program_ids.append(program.id)
                home_included_programs.append(detail)
                if key:
                    home_canonical_keys.add(key)

    # ------------------------------------------------------------------
    # 2. BOYUT HAZIRLIĞI: KENDİ PROGRAM ANAHTARLARIMIZ VE İZİNLİ KÜME
    # ------------------------------------------------------------------
    # Fakülte kapsamında kendi anahtarlarımız yukarıda `home_canonical_keys`
    # olarak hesaplandı; program kapsamında `program_keys` zaten odur. Tek
    # bir kaynağa indirgenir ki iki kod yolu ayrışmasın.
    kendi_anahtarlar: set[str] = set(home_canonical_keys) if faculty_key else set(program_keys)
    # Eşleştirme program ADI üzerinden yapılır (exact/equivalent ayrımı yazımı
    # gerektirir), bu yüzden kendi program adlarımız her iki kapsamda da
    # tek bir yerden üretilir.
    kendi_program_adlari: list[str] = [
        p.name
        for p in db.execute(
            select(AcademicProgram).where(
                AcademicProgram.id.in_(
                    home_program_ids if faculty_key else (scope.program_ids or ())
                )
            )
        ).scalars()
    ]

    # Dışlama muhasebesinin PAYDASI: akranın kıyaslanabilir fakültesi.
    # Program kapsamında bile bir fakülte bağlamı vardır (programın kendi
    # fakültesi); "akranın diğer programları" ancak o evrende anlamlıdır.
    kiyas_fakulte_anahtari = faculty_key
    if not kiyas_fakulte_anahtari and scope.faculty_ids:
        _fak = db.get(Faculty, next(iter(scope.faculty_ids)))
        kiyas_fakulte_anahtari = canonical_faculty_key(_fak.name) if _fak else None

    # "Ortak Bölümler" fakülte bağlamına ait bir kavramdır. Program
    # kapsamında ortak bölüm diye bir şey yoktur; sessizce yanlış bir şey
    # göstermek yerine açıkça "Aynı Bölüm"e düşer ve bunu üst veride bildirir.
    kip_geri_dusme = None
    if eslesme_kipi == MATCH_MODE_SHARED and not faculty_key:
        kip_geri_dusme = {
            "requested": MATCH_MODE_SHARED,
            "applied": MATCH_MODE_SAME,
            "reason": "shared_programs_requires_faculty_scope",
        }
        eslesme_kipi = MATCH_MODE_SAME

    # "Benzer Bölümler" için izinli anahtar kümesi, KAPALI kayıttan üretilir:
    # kendi anahtarlarımız + onlarla AYNI dar disiplin ailesindeki anahtarlar.
    # Kayıtta olmayan hiçbir program bu kümeye giremez (fail-closed).
    izinli_anahtarlar: set[str] = set(kendi_anahtarlar)
    kendi_aileler: set[str] = {
        aile for aile in (discipline_family(k) for k in kendi_anahtarlar) if aile
    }
    if eslesme_kipi == MATCH_MODE_SIMILAR:
        from app.services.program_equivalence import _DISCIPLINE_FAMILY_BY_KEY

        izinli_anahtarlar |= {
            anahtar
            for anahtar, aile in _DISCIPLINE_FAMILY_BY_KEY.items()
            if aile in kendi_aileler
        }

    # SUNUM GRANÜLERLİĞİ: yalnızca "Ortak Bölümler" kipi fakülte düzeyinde
    # toplar. Aynı/Benzer kipleri program düzeyinde satır üretir; aksi hâlde
    # "hangi program?" sorusu toplamın içinde kaybolurdu.
    fakulte_toplami = (eslesme_kipi == MATCH_MODE_SHARED)

    atlas_query = select(YokAtlasBenchmarkMetric).where(
        YokAtlasBenchmarkMetric.source_dataset == SOURCE_DATASET,
        YokAtlasBenchmarkMetric.source_year.in_(years),
    )
    if eslesme_kipi == MATCH_MODE_ALL:
        fakulte_toplami = False
        if faculty_key:
            atlas_query = atlas_query.where(
                YokAtlasBenchmarkMetric.canonical_faculty_key == faculty_key
            )
    elif eslesme_kipi == MATCH_MODE_SHARED:
        # Mevcut ortak-bölüm metodolojisi AYNEN korunur.
        atlas_query = atlas_query.where(
            YokAtlasBenchmarkMetric.canonical_faculty_key == faculty_key
        )
    else:
        # Aynı/Benzer kipinde fakülte etiketi ölçüt DEĞİLDİR: akranın
        # programı hangi fakültenin altında duruyorsa dursun, akademik
        # olarak eşleşiyorsa girer, eşleşmiyorsa giremez.
        atlas_query = atlas_query.where(
            YokAtlasBenchmarkMetric.canonical_program_key.in_(izinli_anahtarlar or {"__YOK__"})
        )
    atlas_metrics = db.execute(atlas_query).scalars().all()

    # ------------------------------------------------------------------
    # 1. BOYUT: KURUM TÜRÜ / ÖLÇEK SÜZGECİ (ortak program mantığından BAĞIMSIZ)
    # ------------------------------------------------------------------
    # Bu süzgeç yalnızca HANGİ KURUMLARIN yarışacağını belirler. Hangi
    # PROGRAMLARIN kıyaslanacağına aşağıdaki ortak-program mantığı karar
    # verir ve o mantık burada değişmez. Kendi kurumumuz her zaman kalır.
    tur_disi_kurumlar: list[dict] = []
    benzer_kurumlar = _similar_universities(db) if tur_kipi == INSTITUTION_TYPE_SIMILAR else None
    if tur_kipi == INSTITUTION_TYPE_SIMILAR:
        uygun = []
        for metric in atlas_metrics:
            if metric.university_name == HOME_UNIVERSITY:
                uygun.append(metric)
                continue
            if metric.university_name in benzer_kurumlar:
                uygun.append(metric)
            elif not any(x["university_name"] == metric.university_name
                         for x in tur_disi_kurumlar):
                tur_disi_kurumlar.append({
                    "university_name": metric.university_name,
                    "university_type": tur_haritasi.get(metric.university_name),
                    "reason": "institution_scale_not_similar",
                })
        atlas_metrics = uygun
    elif tur_kipi != INSTITUTION_TYPE_ALL:
        istenen = _TYPE_VALUE[tur_kipi]
        uygun = []
        for metric in atlas_metrics:
            if metric.university_name == HOME_UNIVERSITY:
                uygun.append(metric)
                continue
            kurum_turu = tur_haritasi.get(metric.university_name)
            if kurum_turu == istenen:
                uygun.append(metric)
            elif not any(x["university_name"] == metric.university_name
                         for x in tur_disi_kurumlar):
                tur_disi_kurumlar.append({
                    "university_name": metric.university_name,
                    "university_type": kurum_turu,
                    "reason": ("institution_type_mismatch" if kurum_turu
                               else "institution_type_unknown"),
                })
        atlas_metrics = uygun

    excluded_index: dict[tuple, dict] = {}
    # Her kabul edilen akran satırının HANGİ GEREKÇEYLE girdiği taşınır:
    # kanonik anahtar → exact / equivalent / similar. Arayüz ve asistan
    # bunu gösterir; "neden bu program burada?" sorusu cevapsız kalmaz.
    eslesme_turu_by_key: dict[str, str] = {}

    if eslesme_kipi in (MATCH_MODE_SAME, MATCH_MODE_SIMILAR):
        # -------------------------------------------------------------
        # AYNI / BENZER BÖLÜM SÜZGECİ
        # -------------------------------------------------------------
        # Ölçüt yalnızca kanonik anahtar ve dar disiplin ailesidir.
        # Fakülte adı, "mühendislik" kelimesi, metin benzerliği ve geniş
        # YÖK kategorisi KULLANILMAZ. Eşleşmeyen her satır gerekçesiyle
        # birlikte dışlananlar listesine yazılır.
        kendi_adlar = kendi_program_adlari or [selected_label]
        uygun_metrikler = []
        for metric in atlas_metrics:
            if metric.university_name == HOME_UNIVERSITY:
                uygun_metrikler.append(metric)
                continue
            tur = None
            for kendi_ad in kendi_adlar:
                aday = program_match_type(kendi_ad, metric.program_name)
                if aday == MATCH_EXACT:
                    tur = MATCH_EXACT
                    break
                if aday and (tur is None or tur == MATCH_SIMILAR):
                    tur = aday
            if tur == MATCH_SIMILAR and eslesme_kipi == MATCH_MODE_SAME:
                tur = None  # "Aynı Bölüm" kipinde benzerlik yetmez.
            if tur:
                eslesme_turu_by_key[metric.canonical_program_key or ""] = (
                    eslesme_turu_by_key.get(metric.canonical_program_key or "") or tur
                )
                uygun_metrikler.append(metric)
                continue
            anahtar = (metric.university_name, metric.faculty_name,
                       metric.canonical_program_key, metric.program_name)
            dislanan = excluded_index.setdefault(anahtar, {
                "university_name": metric.university_name,
                "original_source_faculty_label": metric.faculty_name,
                "program_name": metric.program_name,
                "canonical_program_key": metric.canonical_program_key,
                "program_family": canonical_program_family(metric.canonical_program_key),
                "discipline_family": discipline_family(metric.canonical_program_key),
                "match_type": None,
                "reason": ("program_not_academically_similar"
                           if eslesme_kipi == MATCH_MODE_SIMILAR
                           else "program_not_same_as_home_program"),
                "source_row_references": set(),
            })
            dislanan["source_row_references"].add(metric.source_program_code)
        atlas_metrics = uygun_metrikler
    elif faculty_key:
        compatible_metrics = []
        for metric in atlas_metrics:
            family = canonical_program_family(metric.canonical_program_key)
            family_ok = (
                not required_program_family or family == required_program_family
            )
            # A peer university's own program never needs to appear in the
            # home institution's key set (it *is* the home institution) —
            # only OTHER universities are restricted to shared programs.
            common_ok = (
                metric.university_name == HOME_UNIVERSITY
                or metric.canonical_program_key in home_canonical_keys
            )
            if family_ok and common_ok:
                compatible_metrics.append(metric)
                continue
            reason = (
                "program_family_incompatible_with_engineering_faculty"
                if not family_ok
                else "program_not_offered_at_home_university"
            )
            exclusion_key = (
                metric.university_name,
                metric.faculty_name,
                metric.canonical_program_key,
                metric.program_name,
            )
            exclusion = excluded_index.setdefault(
                exclusion_key,
                {
                    "university_name": metric.university_name,
                    "original_source_faculty_label": metric.faculty_name,
                    "program_name": metric.program_name,
                    "canonical_program_key": metric.canonical_program_key,
                    "program_family": family,
                    "reason": reason,
                    "source_row_references": set(),
                },
            )
            exclusion["source_row_references"].add(metric.source_program_code)
        atlas_metrics = compatible_metrics

    excluded_programs = list(home_excluded_programs)
    if eslesme_kipi in (MATCH_MODE_SAME, MATCH_MODE_SIMILAR):
        excluded_programs.extend(
            _dislanan_akran_programlari(
                db, years, kiyas_fakulte_anahtari, izinli_anahtarlar,
                tur_haritasi, tur_kipi, benzer_kurumlar,
            )
        )
    for exclusion in excluded_index.values():
        excluded_programs.append(
            {
                **exclusion,
                "source_row_references": sorted(exclusion["source_row_references"]),
            }
        )
    excluded_programs.sort(
        key=lambda item: (
            item["university_name"], item["original_source_faculty_label"],
            item["program_name"],
        )
    )

    grouped_metrics: dict[tuple, list[YokAtlasBenchmarkMetric]] = defaultdict(list)
    for metric in atlas_metrics:
        identity = (
            (metric.university_name, metric.faculty_name)
            if fakulte_toplami
            else (
                metric.university_name,
                metric.faculty_name,
                metric.canonical_program_key,
            )
        )
        grouped_metrics[identity].append(metric)

    groups: dict[tuple, dict] = {}
    for identity, metrics in grouped_metrics.items():
        first = metrics[0]
        included_programs = sorted(
            {
                (
                    metric.program_name,
                    metric.canonical_program_key,
                    canonical_program_family(metric.canonical_program_key),
                )
                for metric in metrics
            }
        )
        groups[identity] = {
            "university_name": first.university_name,
            "faculty_name": first.faculty_name,
            "program_name": (
                None if fakulte_toplami else display_program_name(first.program_name)
            ),
            "canonical_program_key": (
                None if fakulte_toplami else first.canonical_program_key
            ),
            "label": (
                f"{first.university_name} — {first.faculty_name}"
                if fakulte_toplami
                else (
                    f"{first.university_name} — "
                    f"{display_program_name(first.program_name)} · {first.faculty_name}"
                )
            ),
            "annual": _annual_from_atlas(metrics),
            "is_home_institution": first.university_name == HOME_UNIVERSITY,
            "university_type": tur_haritasi.get(first.university_name),
            "match_type": (
                MATCH_EXACT if first.university_name == HOME_UNIVERSITY
                else (None if fakulte_toplami
                      else eslesme_turu_by_key.get(first.canonical_program_key or ""))
            ),
            "match_reason": (
                None if fakulte_toplami or first.university_name == HOME_UNIVERSITY
                else {
                    MATCH_EXACT: "Aynı program adı",
                    MATCH_EQUIVALENT: "Aynı kanonik program (yazım varyantı)",
                    MATCH_SIMILAR: (
                        "Aynı disiplin ailesi: "
                        f"{discipline_family(first.canonical_program_key)}"
                    ),
                }.get(eslesme_turu_by_key.get(first.canonical_program_key or ""))
            ),
            "included_programs": [
                {
                    "program_name": name,
                    "canonical_program_key": key,
                    "program_family": family,
                    # Bu programın karşılaştırmaya HANGİ GEREKÇEYLE girdiği.
                    "discipline_family": discipline_family(key),
                    "match_type": (
                        MATCH_EXACT if first.university_name == HOME_UNIVERSITY
                        else eslesme_turu_by_key.get(key or "")
                    ),
                }
                for name, key, family in included_programs
            ],
            "excluded_programs": [
                exclusion
                for exclusion in excluded_programs
                if exclusion["university_name"] == first.university_name
                and exclusion["original_source_faculty_label"] == first.faculty_name
            ],
        }

    if not fakulte_toplami:
        _merge_existing_comparable(db, groups, program_keys, years)

    atlas_home_groups = [
        group for group in groups.values() if group["is_home_institution"]
    ]
    for identity in [key for key, group in groups.items() if group["is_home_institution"]]:
        del groups[identity]

    if not faculty_key:
        # Program/department level scopes never computed the home program
        # breakdown above (it's only needed for faculty-level "ortak
        # bölümler" filtering), so derive it here as before.
        home_programs = db.execute(
            select(AcademicProgram).where(
                AcademicProgram.id.in_(scope.program_ids or ())
            )
        ).scalars().all()
        for program in home_programs:
            key = canonical_program_key(program.name)
            family = canonical_program_family(key)
            home_program_ids.append(program.id)
            home_included_programs.append(
                {
                    "program_name": display_program_name(program.name),
                    "canonical_program_key": key,
                    "program_family": family,
                }
            )

    home_annual = _internal_home_annual(db, home_program_ids, years)
    _fill_home_missing(home_annual, atlas_home_groups, years)
    home_group = {
        "university_name": HOME_UNIVERSITY,
        "faculty_name": selected_faculty_name,
        "program_name": None if fakulte_toplami else selected_label,
        "canonical_program_key": (
            None if fakulte_toplami else (next(iter(program_keys)) if len(program_keys) == 1 else None)
        ),
        "label": f"{HOME_UNIVERSITY} — {selected_label}",
        "annual": home_annual,
        "is_home_institution": True,
        "included_programs": home_included_programs,
        "excluded_programs": home_excluded_programs,
    }

    rows = [
        _finalize_group(home_group, years, source_target_year, latest_available)
    ]
    rows.extend(
        _finalize_group(group, years, source_target_year, latest_available)
        for group in groups.values()
    )
    rows = [row for row in rows if row["cohort_size"] is not None]
    rows.sort(key=lambda row: (-row["cohort_size"], row["label"]))
    available = len(rows) > 1

    if faculty_key == "ENGINEERING_FACULTY":
        title = (
            "Mühendislik Fakülteleri — Tahmini Öğrenci Büyüklüğü"
            if latest_available
            else "Mühendislik Fakülteleri — YÖK Atlas Kohort Büyüklüğü"
        )
    elif faculty_key:
        title = (
            f"{selected_label} — Tahmini Öğrenci Büyüklüğü"
            if latest_available
            else f"{selected_label} — YÖK Atlas Kohort Büyüklüğü"
        )
    else:
        title = (
            f"{selected_label} Programları — Tahmini Öğrenci Büyüklüğü"
            if latest_available
            else f"{selected_label} Programları — YÖK Atlas Karşılaştırması"
        )

    return {
        **base,
        "metric_label": (
            "Tahmini Öğrenci Büyüklüğü"
            if latest_available
            else base["metric_label"]
        ),
        "latest_available": latest_available,
        "source_window": _source_window(years),
        "contains_2025_data": False,
        "current_metric_source_year": source_target_year,
        "current_metric_period": f"{source_target_year}-{source_target_year + 1}",
        "available": available,
        "comparison_type": ("faculty" if fakulte_toplami else
                            ("similar_programs" if eslesme_kipi == MATCH_MODE_SIMILAR
                             else "equivalent_program")),
        # KURUM TÜRÜ BOYUTU — ortak program metodolojisinden bağımsızdır.
        "institution_type_filter": tur_kipi,
        "institution_type_label": {
            INSTITUTION_TYPE_ALL: "Tümü",
            INSTITUTION_TYPE_STATE: "Devlet",
            INSTITUTION_TYPE_FOUNDATION: "Vakıf",
            INSTITUTION_TYPE_SIMILAR: "Benzer Ölçek",
        }[tur_kipi],
        "excluded_by_institution_type": tur_disi_kurumlar,
        # PROGRAM EŞLEŞTİRME BOYUTU — kurum türünden bağımsız.
        "matching_mode": eslesme_kipi,
        "matching_mode_label": MATCH_MODE_LABELS[eslesme_kipi],
        "matching_mode_fallback": kip_geri_dusme,
        "home_programs": [
            {**item, "match_type": MATCH_EXACT,
             "discipline_family": discipline_family(item.get("canonical_program_key"))}
            for item in home_included_programs
        ],
        "home_discipline_families": sorted(kendi_aileler),
        "peer_programs_used": sorted(
            {
                (item["program_name"], item["canonical_program_key"],
                 item.get("match_type"))
                for group in groups.values()
                for item in group["included_programs"]
            },
            key=lambda t: (t[0] or "",),
        ) if not fakulte_toplami else [],
        "match_type_breakdown": {
            tur: sum(1 for v in eslesme_turu_by_key.values() if v == tur)
            for tur in (MATCH_EXACT, MATCH_EQUIVALENT, MATCH_SIMILAR)
        },
        "excluded_peer_programs": [
            item for item in excluded_programs
            if item["university_name"] != HOME_UNIVERSITY
        ],
        "excluded_peer_program_count": sum(
            1 for item in excluded_programs
            if item["university_name"] != HOME_UNIVERSITY
        ),
        "matching_explanation": _eslesme_aciklamasi(
            eslesme_kipi, groups, excluded_programs, fakulte_toplami
        ),
        # KOHORTUN NEYİ TEMSİL ETTİĞİ — makine tarafından okunabilir.
        # Fakülte kapsamında gösterilen sayı, akran kurumun TÜM fakülte
        # nüfusu DEĞİLDİR: yalnızca kendi fakültemizde de bulunan
        # ("ortak") programların kohortudur. Bu ayrımın adı burada
        # açıkça taşınır ki arayüz ve asistan yanlış genelleme yapmasın.
        "cohort_basis": {
            MATCH_MODE_ALL: "all_programs_in_scope",
            MATCH_MODE_SHARED: "shared_programs_with_home_faculty",
            MATCH_MODE_SAME: "same_canonical_program",
            MATCH_MODE_SIMILAR: "same_discipline_family_programs",
        }[eslesme_kipi],
        "shared_program_names": [
            item["program_name"] for item in home_included_programs
        ] if fakulte_toplami else [],
        "title": title,
        "subtitle": (
            (
                "Son mevcut YÖK Atlas verisi · 2022-2024"
                if latest_available
                else _cohort_methodology(source_target_year, False)
            )
            + (
                (" · yalnızca ortak programlar (akranın tüm fakülte nüfusu değildir)"
                 if fakulte_toplami
                 else f" · {MATCH_MODE_LABELS[eslesme_kipi].lower()}")
            )
        ),
        "years_used": list(years),
        "subject": {
            "label": selected_label,
            "faculty_key": faculty_key,
            "canonical_program_keys": sorted(program_keys),
        },
        "peers": rows,
        "peer_count": len(rows),
        "methodology": (
            f"{_cohort_methodology(source_target_year, latest_available)} "
            "aynı üniversite/fakülte/kanonik programdaki benzersiz kaynak "
            "kodları toplanır. Mevcut proje metriği varsa o korunur."
            + (
                (" Fakülte kapsamında karşılaştırma YALNIZCA kendi "
                 "fakültemizde de bulunan ortak programlar üzerinden yapılır; "
                 "gösterilen kohort akran kurumun tüm fakülte nüfusu değildir."
                 if fakulte_toplami
                 else " Program eşleştirmesi kanonik program anahtarı ve "
                      "kapalı disiplin ailesi kaydıyla yapılır; fakülte adı, "
                      "'mühendislik' kelimesi veya metin benzerliği ölçüt "
                      "değildir.")
            )
        ),
        "aggregation_debug": {
            "required_program_family": required_program_family,
            "matching_mode": eslesme_kipi,
            "allowed_canonical_keys": sorted(izinli_anahtarlar) if not fakulte_toplami else [],
            "home_canonical_keys": sorted(kendi_anahtarlar),
            "excluded_program_count": len(excluded_programs),
            "excluded_programs": excluded_programs,
        },
        "note": (
            "Karşılaştırma ikincil YÖK Atlas kaynağıyla dolduruldu."
            if available
            else "Bu kapsamda en az iki karşılaştırılabilir Atlas birimi yok."
        ),
    }
