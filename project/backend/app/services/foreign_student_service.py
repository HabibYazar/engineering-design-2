"""YABANCI ÖĞRENCİ GÖSTERGESİ — sayı her zaman, oran yalnızca hak edilince.

SAYI VE ORAN AYRI ŞEYLERDİR
---------------------------
Yabancı öğrenci SAYISI kurumun yetkili kaynağından gelir ve her kapsamda
gösterilebilir. ORAN ise bir BÖLME işlemidir ve paydanın üç şartı
sağlaması gerekir:

    1. AYNI KAPSAM      — fakülte payını üniversite paydasına bölmek
                          fakülteyi olduğundan küçük gösterir.
    2. AYNI AKADEMİK YIL — 2025-2026 payını başka yılın paydasına
                          bölmek iki farklı zamanı karşılaştırmaktır.
    3. UYUMLU NÜFUS TANIMI — pay "hâlihazırda kayıtlı yabancı öğrenci"
                          sayısıdır. Payda da "hâlihazırda kayıtlı
                          öğrenci" olmalıdır.

ÜNİVERSİTE DÜZEYİNDE ORAN HESAPLANIR
------------------------------------
Payda: YÖK'ün bildirdiği kayıtlı öğrenci sayısı (aynı yıl, aynı kapsam,
aynı nüfus tanımı). 2025-2026 için 233 / 3.626 → yaklaşık %6,43. Oran
KODA GÖMÜLMEZ; her istekte iki kaynaktan yeniden hesaplanır.

ALT KAPSAMLARDA ORAN HESAPLANMAZ
--------------------------------
Elimizdeki tek alt kapsam paydası, ÖSYM yerleştirmelerinden türetilen
"son ≤4 kohort toplamı"dır. O sayı:
    · farklı bir nüfus tanımıdır (yerleştirme temelli; lisansüstü,
      yatay geçiş ve DGS ile geleni kapsamaz),
    · TEK bir yıla değil dört yıla aittir.
Yabancı öğrenci sayısını bu paydaya bölüp "yabancı öğrenci oranı"
demek, iki farklı şeyin bölümünü üçüncü bir şeymiş gibi sunmak olurdu.
Bu yüzden alt kapsamlarda SAYI gösterilir, oran `available: False` ile
gerekçesi yazılarak bildirilir.

DÖNEM
-----
Veri kümesi 2025-2026'ya aittir. Başka bir dönem seçildiğinde bu
satırlar KULLANILMAZ; `available: False` döner. Bir yılın sayısını
başka yılın etiketiyle göstermek, panonun en tehlikeli hatasıdır.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AcademicProgram, Department, Faculty
from app.models.student_demographic import (
    DIMENSION_FOREIGN,
    RESOLUTION_PROGRAM,
    StudentDemographicCount,
)

if TYPE_CHECKING:
    from app.services.scope import Scope

#: Oranın paydası için kabul edilen tek kaynak. Aynı yıl + aynı kapsam +
#: aynı nüfus tanımı şartını sağlayan başka bir ölçümümüz yok.
PAYDA_KAYNAGI = "yok_kayitli"

ALT_KAPSAM_NOTU = (
    "Bu kapsamda yabancı öğrenci ORANI hesaplanmaz: elimizdeki tek payda "
    "ÖSYM yerleştirmelerinden türetilen son ≤4 kohort toplamıdır; farklı "
    "bir nüfus tanımına ve tek yıla değil dört yıla aittir. Sayı gerçek, "
    "oran ölçülemez."
)


def _kapsam_susu(sorgu, scope: Optional["Scope"]):
    """Satırları seçili kapsama daraltır — kardeş sızıntısı olmadan.

    Satırlar üç düzeyde bağlı olabilir (program / bölüm / fakülte).
    Fakülte kapsamı, o fakülteye yazılmış HER satırı içerir; bölüm
    kapsamı yalnızca o bölüme veya altındaki programlara bağlı
    satırları; program kapsamı yalnızca o programı.
    """
    if scope is None or scope.is_university:
        return sorgu
    if getattr(scope, "academic_program_id", None):
        return sorgu.where(
            StudentDemographicCount.academic_program_id
            == scope.academic_program_id)
    if getattr(scope, "department_id", None):
        return sorgu.where(
            StudentDemographicCount.department_id == scope.department_id)
    if scope.faculty_id:
        return sorgu.where(StudentDemographicCount.faculty_id == scope.faculty_id)
    return sorgu


def available_periods(db: Session) -> List[str]:
    """Yabancı öğrenci verisi bulunan akademik yıllar."""
    return sorted(
        y for (y,) in db.execute(
            select(StudentDemographicCount.academic_year).distinct()
            .where(StudentDemographicCount.dimension == DIMENSION_FOREIGN)
        ) if y
    )


def foreign_students(db: Session, scope: Optional["Scope"] = None,
                     donem: Optional[str] = None) -> dict:
    """Seçili kapsam ve dönemde yabancı öğrenci sayısı (+ hak edilirse oran)."""
    yillar = available_periods(db)
    if not yillar:
        return {"available": False, "requested_period": donem,
                "available_periods": [],
                "note": "Yabancı öğrenci veri kümesi yüklenmemiş."}

    # DÖNEM: verilmezse veri kümesinin kendi yılı; verilirse ondan
    # SAPILMAZ. Başka yılın sayısı bu dönemin etiketiyle gösterilmez.
    hedef = donem or yillar[-1]
    if hedef not in yillar:
        return {
            "available": False,
            "requested_period": hedef,
            "available_periods": yillar,
            "student_count": None,
            "ratio_percent": None,
            "note": (f"{hedef} döneminde yabancı öğrenci verisi yok. "
                     f"Veri kümesi yalnızca {', '.join(yillar)} yılına aittir; "
                     "başka bir yılın sayısı bu dönem için kullanılmaz."),
        }

    temel = select(StudentDemographicCount).where(
        StudentDemographicCount.dimension == DIMENSION_FOREIGN,
        StudentDemographicCount.academic_year == hedef,
    )
    satirlar = db.execute(_kapsam_susu(temel, scope)).scalars().all()
    if not satirlar:
        return {
            "available": False,
            "requested_period": hedef,
            "available_periods": yillar,
            "student_count": None,
            "ratio_percent": None,
            "note": "Bu kapsamda yabancı öğrenci kaydı yok.",
        }

    toplam = sum(r.student_count for r in satirlar)

    # ---------------- ORAN: yalnızca uyumlu payda varsa ----------------
    oran = None
    payda = None
    payda_notu = ALT_KAPSAM_NOTU
    payda_kaynagi = None
    if scope is None or scope.is_university:
        from app.services import university_headcount_service as kayitli

        ozet = kayitli.enrolled_headcount(db, scope, donem=hedef)
        if ozet.get("available") and ozet.get("student_count"):
            payda = int(ozet["student_count"])
            payda_kaynagi = PAYDA_KAYNAGI
            oran = round(toplam / payda * 100, 2)
            payda_notu = (
                f"Oran = {toplam} / {payda}. Payda, YÖK'ün {hedef} yılı için "
                "bildirdiği kayıtlı öğrenci sayısıdır: aynı kapsam, aynı yıl, "
                "aynı nüfus tanımı.")
        else:
            payda_notu = (
                f"{hedef} yılı için YÖK kayıtlı öğrenci sayısı yok; "
                "uyumlu payda bulunmadığından oran hesaplanmadı.")

    # ---------------- kırılım ----------------
    kirilim = []
    for r in sorted(satirlar, key=lambda x: -x.student_count):
        kirilim.append({
            "source_faculty_label": r.source_faculty_label,
            "source_program_label": r.source_program_label,
            "education_language": r.education_language,
            "student_count": r.student_count,
            "faculty_id": r.faculty_id,
            "department_id": r.department_id,
            "academic_program_id": r.academic_program_id,
            "resolution": r.resolution,
            "resolution_note": r.resolution_note,
        })

    return {
        "available": True,
        "academic_year": hedef,
        "requested_period": donem,
        "available_periods": yillar,
        "student_count": toplam,
        "row_count": len(satirlar),
        "program_resolved_count": sum(
            1 for r in satirlar if r.resolution == RESOLUTION_PROGRAM),
        "ratio_available": oran is not None,
        "ratio_percent": oran,
        "denominator": payda,
        "denominator_source": payda_kaynagi,
        "ratio_note": payda_notu,
        "rows": kirilim,
        "source_file": satirlar[0].source_file,
        "source_dataset": satirlar[0].source_dataset,
    }


def faculty_breakdown(db: Session, donem: Optional[str] = None) -> dict:
    """Fakülte başına yabancı öğrenci sayısı (üniversite panosu için)."""
    yillar = available_periods(db)
    hedef = donem or (yillar[-1] if yillar else None)
    if not hedef or hedef not in yillar:
        return {"available": False, "requested_period": donem,
                "available_periods": yillar, "rows": []}

    satirlar = db.execute(
        select(StudentDemographicCount.source_faculty_label,
               StudentDemographicCount.faculty_id,
               func.sum(StudentDemographicCount.student_count))
        .where(StudentDemographicCount.dimension == DIMENSION_FOREIGN,
               StudentDemographicCount.academic_year == hedef)
        .group_by(StudentDemographicCount.source_faculty_label,
                  StudentDemographicCount.faculty_id)
        .order_by(func.sum(StudentDemographicCount.student_count).desc())
    ).all()

    return {
        "available": bool(satirlar),
        "academic_year": hedef,
        "total": sum(int(n) for _, _, n in satirlar),
        "rows": [{"label": ad, "faculty_id": fid, "student_count": int(n)}
                 for ad, fid, n in satirlar],
    }
