"""ÜNİVERSİTE DÜZEYİNDE KAYITLI ÖĞRENCİ SAYISI ve BÜYÜME TRENDİ.

YETKİLİ KAYNAK — VE SINIRI
--------------------------
YÖK'ün bildirdiği kayıtlı öğrenci sayısı, **üniversite düzeyinde**
kurumun fiilî öğrenci gövdesinin yetkili ölçüsüdür. ÖSYM'den türetilen
`student_count` (son ≤4 kohort) yerleştirme temellidir ve lisansüstü,
yatay geçiş, DGS ile gelenleri kapsamaz.

Ama bu veri kümesinin **fakülte/bölüm/program kırılımı YOKTUR.**
Dolayısıyla:

  · ÜNİVERSİTE kapsamında  → YÖK sayısı yetkilidir, trend buradan okunur
  · ALT kapsamlarda        → `available: False`. Üniversite toplamını bir
                             fakülteye yazmak ya da programlara paylaştırmak
                             uydurma olurdu; onun yerine bu verinin o
                             seviyede ÖLÇÜLMEDİĞİ açıkça söylenir.

Bu yüzden fonksiyon üniversite toplamını alt kapsamlara SIZDIRMAZ ve
`student_count` zincirini (program → bölüm → fakülte) hiç değiştirmez.

ÇİFT SAYMA
----------
Tabloda yalnızca ayrıntı satırları ve yalnızca E/K hücreleri vardır
(bkz. `models/university_headcount.py`). Toplam almak bu yüzden basit
bir `SUM`'dır; "toplamı toplama" riski yapısal olarak yoktur.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import UniversityStudentHeadcount as Sayim
from app.models.university_headcount import (
    DEGREE_LEVEL_LABELS,
    EDUCATION_MODE_LABELS,
    HOME_UNIVERSITY,
)

if TYPE_CHECKING:
    from app.services.scope import Scope

#: Alt kapsamlarda dönen açıklama. Kullanıcıya "veri yok" değil,
#: "bu veri bu seviyede ölçülmüyor" demek gerekir — ikisi farklı
#: kararlara yol açar.
UNIT_GRANULARITY_NOTE = (
    "YÖK kayıtlı öğrenci sayıları yalnızca ÜNİVERSİTE düzeyinde "
    "yayımlanır; fakülte/bölüm/program kırılımı kaynakta yoktur."
)


def _yuzde(simdi: Optional[int], onceki: Optional[int]) -> Optional[float]:
    """Önceki yıl yoksa/sıfırsa değişim TANIMSIZDIR; 0 döndürülmez."""
    if simdi is None or onceki in (None, 0):
        return None
    return round((simdi - onceki) / onceki * 100, 2)


def available_years(db: Session,
                    university_name: str = HOME_UNIVERSITY) -> List[str]:
    return [
        y for (y,) in db.execute(
            select(Sayim.academic_year)
            .where(Sayim.university_name == university_name)
            .group_by(Sayim.academic_year)
            .order_by(Sayim.academic_year)
        )
    ]


def _kirilim(db: Session, university_name: str, sutun) -> Dict[str, Dict[str, int]]:
    """{yıl: {kırılım: toplam}} — tek sorguda."""
    out: Dict[str, Dict[str, int]] = {}
    for yil, anahtar, toplam in db.execute(
        select(Sayim.academic_year, sutun, func.sum(Sayim.student_count))
        .where(Sayim.university_name == university_name)
        .group_by(Sayim.academic_year, sutun)
    ):
        out.setdefault(yil, {})[anahtar] = int(toplam or 0)
    return out


def enrolled_headcount(
    db: Session, scope: Optional["Scope"] = None,
    university_name: str = HOME_UNIVERSITY,
    donem: Optional[str] = None,
) -> dict:
    """Kayıtlı öğrenci sayısı ve yıllık büyüme.

    Kapsam üniversite değilse hesaplanmaz (bkz. modül açıklaması).

    DÖNEM
    -----
    `donem` verilirse "güncel" alanlar (student_count, by_degree_level…)
    O YILI anlatır; çok yıllı seri de seçilen yılda biter. Geçmiş bir
    dönem seçiliyken gelecekteki gözlemleri göstermek dönem sızıntısıdır.
    Seçilen yılın kaydı yoksa BAŞKA yıla düşülmez:
    `available: False` döner ve arayüz "bu dönemde ölçülmedi" der.
    """
    if scope is not None and not scope.is_university:
        return {
            "available": False,
            "measured_at_level": "university",
            "requested_level": scope.level,
            "note": UNIT_GRANULARITY_NOTE,
        }

    yillar = available_years(db, university_name)
    if not yillar:
        return {"available": False, "measured_at_level": "university",
                "note": "Kayıtlı öğrenci sayısı verisi yüklenmemiş."}

    toplamlar = {
        yil: int(toplam or 0)
        for yil, toplam in db.execute(
            select(Sayim.academic_year, func.sum(Sayim.student_count))
            .where(Sayim.university_name == university_name)
            .group_by(Sayim.academic_year)
        )
    }
    duzeyler = _kirilim(db, university_name, Sayim.degree_level)
    turler = _kirilim(db, university_name, Sayim.education_mode)
    cinsiyetler = _kirilim(db, university_name, Sayim.gender)

    seri: List[dict] = []
    for i, yil in enumerate(yillar):
        onceki = yillar[i - 1] if i else None
        toplam = toplamlar.get(yil)
        onceki_toplam = toplamlar.get(onceki) if onceki else None
        d = duzeyler.get(yil, {})
        c = cinsiyetler.get(yil, {})
        seri.append({
            "academic_year": yil,
            "student_count": toplam,
            "change_percent": _yuzde(toplam, onceki_toplam),
            "change_absolute": (toplam - onceki_toplam
                                if toplam is not None and onceki_toplam is not None
                                else None),
            # Sıfır GERÇEK bir değerdir burada: "bu düzeyde öğrencimiz yok".
            "by_degree_level": {
                DEGREE_LEVEL_LABELS.get(k, k): v for k, v in sorted(d.items())},
            "by_education_mode": {
                EDUCATION_MODE_LABELS.get(k, k): v
                for k, v in sorted(turler.get(yil, {}).items())},
            "female_count": c.get("K"),
            "male_count": c.get("E"),
            "female_percent": (round(c["K"] / toplam * 100, 2)
                               if toplam and c.get("K") is not None else None),
        })

    if donem:
        # SEÇİLEN DÖNEM AYNEN KULLANILIR — kaydı yoksa başka yıla DÜŞÜLMEZ.
        son = next((y for y in seri if y["academic_year"] == donem), None)
        if son is None:
            return {
                "available": False,
                "measured_at_level": "university",
                "requested_period": donem,
                "available_periods": [y["academic_year"] for y in seri],
                "note": (f"{donem} döneminde YÖK kayıtlı öğrenci sayısı "
                         "yayımlanmamış. Başka bir yılın sayısı bu dönemin "
                         "etiketiyle gösterilmez."),
            }
    else:
        son = seri[-1]
    gorunen_seri = seri[:seri.index(son) + 1]
    ilk = gorunen_seri[0]
    # Dönem boyu büyüme: ilk yıldan son yıla. Yıllık bileşik oran
    # HESAPLANMAZ — dört gözlemden bileşik oran türetmek, verinin
    # taşıdığından fazla kesinlik iddia etmek olurdu.
    return {
        "available": True,
        "measured_at_level": "university",
        "university_name": university_name,
        "source": "YÖK istatistik — kayıtlı öğrenci sayıları",
        "years": gorunen_seri,
        "year_count": len(gorunen_seri),
        "latest_academic_year": son["academic_year"],
        "requested_period": donem,
        "student_count": son["student_count"],
        "previous_student_count": (
            gorunen_seri[-2]["student_count"]
            if len(gorunen_seri) > 1 else None),
        "latest_change_percent": son["change_percent"],
        "latest_change_absolute": son["change_absolute"],
        "first_academic_year": ilk["academic_year"],
        "first_student_count": ilk["student_count"],
        "period_growth_percent": _yuzde(son["student_count"],
                                        ilk["student_count"]),
        "period_growth_absolute": (
            son["student_count"] - ilk["student_count"]
            if son["student_count"] is not None
            and ilk["student_count"] is not None else None),
        "by_degree_level": son["by_degree_level"],
        "by_education_mode": son["by_education_mode"],
        "female_percent": son["female_percent"],
        "note": ("Kurumun fiilen kayıtlı öğrenci sayısıdır; ÖSYM "
                 "yerleştirmelerinden türetilen program öğrenci sayılarından "
                 "farklı bir ölçümdür ve onun yerine geçmez."),
    }


def peer_headcounts(db: Session, academic_year: Optional[str] = None
                    ) -> List[dict]:
    """Aynı yıl, aynı ildeki DİĞER üniversitelerin kayıtlı öğrenci sayısı.

    Üniversite seviyesindeki dış karşılaştırmayı gerçek sayıyla besler;
    alt seviyelerde ÇAĞRILMAZ (bkz. `peer_comparison_service`).
    """
    yil = academic_year or (available_years(db) or [None])[-1]
    if not yil:
        return []
    satirlar = db.execute(
        select(Sayim.university_name, Sayim.university_type,
               func.sum(Sayim.student_count))
        .where(Sayim.academic_year == yil)
        .group_by(Sayim.university_name, Sayim.university_type)
    ).all()
    out = [
        {"university_name": ad, "university_type": tur,
         "academic_year": yil, "student_count": int(toplam or 0),
         "is_home_institution": ad == HOME_UNIVERSITY}
        for ad, tur, toplam in satirlar
    ]
    out.sort(key=lambda r: -r["student_count"])
    for i, r in enumerate(out, start=1):
        r["rank"] = i
    return out
