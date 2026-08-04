"""Modül 4 — Akademik personel CRUD ve performans hesaplama servisi.

Entegrasyon notu: Puanlama formülü Eda'nın `scores_calculator.py` dosyasındaki
ağırlıklı toplam mantığını birebir korur. Değişen tek şey verinin kaynağı:
modül seviyesindeki `staffs` listesi yerine veritabanı sorgusu kullanılıyor.

Ayrıca orijinal kodda `config/weights.json` yolu var olmayan bir klasörü işaret
ettiği için `/ranking` endpoint'i çalışmıyordu (FileNotFoundError). Ağırlık dosyası
app/config altına taşındı ve yol bir kez okunup önbelleğe alınıyor.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AcademicStaff, Department, Faculty
from app.schemas.academic_staff import AcademicStaffCreate, AcademicStaffUpdate

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "academic_staff_weights.json"


@lru_cache(maxsize=1)
def load_weights() -> Dict[str, object]:
    """Ağırlık ve eşik yapılandırmasını okur.

    lru_cache kullanılıyor çünkü dosya her istekte değil, süreç ömründe bir kez
    okunmalı; sıralama endpoint'i her personel için bu değerlere ihtiyaç duyuyor.
    """
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _base_query():
    """Bölüm ve fakülteyi tek sorguda getiren temel select.

    selectinload olmadan her personel için ayrı sorgu atılırdı (N+1); sıralama
    endpoint'i tüm personeli dolaştığı için bu fark hissedilir.
    """
    return select(AcademicStaff).options(
        selectinload(AcademicStaff.department).selectinload(Department.faculty)
    )


def _department_name(staff: AcademicStaff) -> str:
    return staff.department.name if staff.department else "Bilinmiyor"


def _faculty_name(staff: AcademicStaff) -> str:
    if staff.department and staff.department.faculty:
        return staff.department.faculty.name
    return "Bilinmiyor"


def to_response_dict(staff: AcademicStaff) -> dict:
    """SQLAlchemy nesnesini API cevabına uygun sözlüğe çevirir."""
    return {
        "id": staff.id,
        "staff_number": staff.staff_number,
        "first_name": staff.first_name,
        "last_name": staff.last_name,
        "full_name": staff.full_name,
        "title": staff.title,
        "department_id": staff.department_id,
        "department_name": _department_name(staff),
        "faculty_name": _faculty_name(staff),
        "academic_year": staff.academic_year,
        "publication_count": staff.publication_count,
        "citation_count": staff.citation_count,
        "teaching_load_hours": staff.teaching_load_hours,
        "advising_count": staff.advising_count,
        "project_count": staff.project_count,
        "patent_count": staff.patent_count,
        "community_engagement_score": staff.community_engagement_score,
        "has_administrative_duty": staff.has_administrative_duty,
        "has_industry_collaboration": staff.has_industry_collaboration,
        "is_active": staff.is_active,
    }


# ----------------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------------


def list_staff(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    department_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    academic_year: Optional[str] = None,
    include_inactive: bool = False,
) -> List[AcademicStaff]:
    """Filtrelenebilir personel listesi."""
    query = _base_query()
    if not include_inactive:
        query = query.where(AcademicStaff.is_active.is_(True))
    if department_id is not None:
        query = query.where(AcademicStaff.department_id == department_id)
    if faculty_id is not None:
        # Fakülte filtresi bölüm üzerinden yapılıyor; personelde ayrı fakülte
        # kolonu tutulmadığı için tek doğruluk kaynağı bölüm tablosu.
        query = query.join(Department).where(Department.faculty_id == faculty_id)
    if academic_year:
        query = query.where(AcademicStaff.academic_year == academic_year)
    query = query.order_by(AcademicStaff.staff_number).offset(skip).limit(limit)
    return list(db.execute(query).scalars().unique())


def get_staff(db: Session, staff_id: int) -> AcademicStaff:
    """Tek personel; bulunamazsa 404."""
    staff = db.execute(_base_query().where(AcademicStaff.id == staff_id)).scalars().first()
    if staff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{staff_id} numaralı akademik personel bulunamadı.",
        )
    return staff


def create_staff(db: Session, payload: AcademicStaffCreate) -> AcademicStaff:
    """Yeni personel kaydı; sicil no tekrarında 409, bölüm yoksa 404."""
    existing = db.execute(
        select(AcademicStaff).where(AcademicStaff.staff_number == payload.staff_number)
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.staff_number}' sicil numarası zaten kayıtlı.",
        )

    department = db.get(Department, payload.department_id)
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{payload.department_id} numaralı bölüm bulunamadı.",
        )

    staff = AcademicStaff(**payload.model_dump())
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff


def update_staff(db: Session, staff_id: int, payload: AcademicStaffUpdate) -> AcademicStaff:
    """Kısmi güncelleme."""
    staff = get_staff(db, staff_id)
    data = payload.model_dump(exclude_unset=True)

    if "department_id" in data and db.get(Department, data["department_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{data['department_id']} numaralı bölüm bulunamadı.",
        )

    for field, value in data.items():
        setattr(staff, field, value)
    db.commit()
    db.refresh(staff)
    return staff


def deactivate_staff(db: Session, staff_id: int) -> AcademicStaff:
    """Kayıt silinmez, pasifleştirilir; geçmiş raporlar bozulmasın diye."""
    staff = get_staff(db, staff_id)
    staff.is_active = False
    db.commit()
    db.refresh(staff)
    return staff


# ----------------------------------------------------------------------------
# Performans hesaplama
# ----------------------------------------------------------------------------


def calculate_score_breakdown(staff: AcademicStaff) -> Dict[str, float]:
    """Her bileşenin puana katkısını ayrı ayrı döndürür."""
    weights = load_weights()["weights"]
    return {
        field: round(getattr(staff, field) * weight, 2)
        for field, weight in weights.items()
    }


def _performance_band(total_score: float) -> str:
    """Puanı yapılandırmadaki eşiklere göre sınıflandırır."""
    thresholds = load_weights()["score_thresholds"]
    if total_score >= thresholds["high_performance"]:
        return "yüksek performans"
    if total_score >= thresholds["expected_performance"]:
        return "beklenen performans"
    return "desteklenmesi gereken"


def rank_staff(
    db: Session,
    academic_year: Optional[str] = None,
    department_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
) -> List[dict]:
    """Ağırlıklı toplam puana göre azalan sıralama."""
    staff_list = list_staff(
        db,
        skip=0,
        limit=10_000,
        department_id=department_id,
        faculty_id=faculty_id,
        academic_year=academic_year,
    )

    rows = []
    for staff in staff_list:
        breakdown = calculate_score_breakdown(staff)
        total = round(sum(breakdown.values()), 2)
        rows.append(
            {
                "staff_id": staff.id,
                "staff_number": staff.staff_number,
                "full_name": staff.full_name,
                "title": staff.title,
                "department_name": _department_name(staff),
                "faculty_name": _faculty_name(staff),
                "academic_year": staff.academic_year,
                "total_score": total,
                "performance_band": _performance_band(total),
                "score_breakdown": breakdown,
            }
        )

    rows.sort(key=lambda row: row["total_score"], reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


# Karşılaştırma anahtarı -> personelden değeri çıkaran fonksiyon.
COMPARISON_FIELDS = {
    "department": _department_name,
    "faculty": _faculty_name,
    "title": lambda staff: staff.title,
}


def compare_staff(
    db: Session, group_by: str, academic_year: Optional[str] = None
) -> List[dict]:
    """Bölüm, fakülte veya unvan bazlı ortalama üretim karşılaştırması."""
    if group_by not in COMPARISON_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{group_by}' geçerli bir gruplama değil. "
                f"Kullanılabilir değerler: {', '.join(COMPARISON_FIELDS)}."
            ),
        )

    key_func = COMPARISON_FIELDS[group_by]
    staff_list = list_staff(db, skip=0, limit=10_000, academic_year=academic_year)

    groups: Dict[str, dict] = {}
    for staff in staff_list:
        key = key_func(staff)
        bucket = groups.setdefault(
            key,
            {"count": 0, "publication": 0, "citation": 0, "score": 0.0},
        )
        bucket["count"] += 1
        bucket["publication"] += staff.publication_count
        bucket["citation"] += staff.citation_count
        bucket["score"] += sum(calculate_score_breakdown(staff).values())

    result = [
        {
            "group_key": key,
            "staff_count": data["count"],
            "average_publication": round(data["publication"] / data["count"], 2),
            "average_citation": round(data["citation"] / data["count"], 2),
            "average_score": round(data["score"] / data["count"], 2),
            "total_publication": data["publication"],
            "total_citation": data["citation"],
        }
        for key, data in groups.items()
    ]
    result.sort(key=lambda row: row["average_score"], reverse=True)
    return result


def staff_trend(db: Session) -> List[dict]:
    """Akademik yıla göre toplam yayın/atıf trendi."""
    staff_list = list_staff(db, skip=0, limit=10_000)

    years: Dict[str, dict] = {}
    for staff in staff_list:
        bucket = years.setdefault(
            staff.academic_year, {"publication": 0, "citation": 0, "count": 0}
        )
        bucket["publication"] += staff.publication_count
        bucket["citation"] += staff.citation_count
        bucket["count"] += 1

    return [
        {
            "academic_year": year,
            "staff_count": data["count"],
            "total_publication": data["publication"],
            "total_citation": data["citation"],
            "average_publication_per_staff": round(
                data["publication"] / data["count"], 2
            ),
        }
        for year, data in sorted(years.items())
    ]


def staff_overview(db: Session, academic_year: Optional[str] = None) -> dict:
    """Modül 4 özet göstergeleri.

    Veri yoksa sıfır değil, boş özet döner; böylece arayüzde "0 personel"
    ile "veri girilmemiş" durumu karışmaz.
    """
    staff_list = list_staff(db, skip=0, limit=10_000, academic_year=academic_year)
    if not staff_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year or 'tüm yıllar'}' için akademik personel verisi yok."
            ),
        )

    titles: Dict[str, int] = {}
    total_score = 0.0
    for staff in staff_list:
        titles[staff.title] = titles.get(staff.title, 0) + 1
        total_score += sum(calculate_score_breakdown(staff).values())

    count = len(staff_list)
    return {
        "academic_year": academic_year or "tüm yıllar",
        "total_staff": count,
        "total_publication": sum(s.publication_count for s in staff_list),
        "total_citation": sum(s.citation_count for s in staff_list),
        "average_teaching_load_hours": round(
            sum(s.teaching_load_hours for s in staff_list) / count, 2
        ),
        "staff_with_administrative_duty": sum(
            1 for s in staff_list if s.has_administrative_duty
        ),
        "staff_with_industry_collaboration": sum(
            1 for s in staff_list if s.has_industry_collaboration
        ),
        "average_score": round(total_score / count, 2),
        "title_distribution": [
            {"title": title, "count": number}
            for title, number in sorted(titles.items(), key=lambda x: -x[1])
        ],
    }
