"""Geliştirme ortamı için başlangıç (test) verilerini ekleyen script.

Çalıştırma:  python seed_data.py
Script birden fazla kez çalıştırılsa bile aynı kayıtları tekrar eklemez.
"""

from typing import Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, init_db
from app.models import AcademicProgram, AdministrativeUnit, Department, Faculty

ModelType = TypeVar("ModelType", bound=Base)


def get_or_create(
    db: Session,
    model: Type[ModelType],
    code: str,
    **fields: object,
) -> tuple[ModelType, bool]:
    """Verilen code'a sahip kayıt varsa onu döndürür, yoksa oluşturur."""
    # Script'in tekrar tekrar çalıştırılabilir (idempotent) olmasını sağlayan fonksiyon budur.
    # Benzersizlik kontrolünü code alanı üzerinden yapıyoruz.
    existing: Optional[ModelType] = (
        db.execute(select(model).where(model.code == code)).scalars().first()
    )
    if existing is not None:
        return existing, False

    obj = model(code=code, **fields)
    db.add(obj)
    # flush, kaydı veritabanına yazıp id'yi hemen üretir.
    # Böylece alt kayıtlar (bölüm, program) bu id'yi kullanabilir.
    db.flush()
    return obj, True


def seed() -> None:
    """Fakülte, bölüm, program ve idari birim örnek verilerini ekler."""
    # Tabloların var olduğundan emin olmak için önce init_db çağrılıyor.
    init_db()

    db: Session = SessionLocal()
    created_count: int = 0
    skipped_count: int = 0

    try:
        # 1) Fakülte
        faculty, created = get_or_create(
            db,
            Faculty,
            code="FEA",
            name="Faculty of Engineering and Architecture",
            description="Mühendislik ve mimarlık alanındaki bölümleri barındıran fakülte.",
            is_active=True,
        )
        created_count += int(created)
        skipped_count += int(not created)

        # 2) Bölümler - yukarıda üretilen fakültenin id'sine bağlanır.
        software_dept, created = get_or_create(
            db,
            Department,
            code="SWE",
            faculty_id=faculty.id,
            name="Software Engineering",
            description="Yazılım mühendisliği bölümü.",
            is_active=True,
        )
        created_count += int(created)
        skipped_count += int(not created)

        computer_dept, created = get_or_create(
            db,
            Department,
            code="CENG",
            faculty_id=faculty.id,
            name="Computer Engineering",
            description="Bilgisayar mühendisliği bölümü.",
            is_active=True,
        )
        created_count += int(created)
        skipped_count += int(not created)

        # 3) Akademik programlar - ilgili bölümlere bağlanır.
        _, created = get_or_create(
            db,
            AcademicProgram,
            code="SWE-BSC",
            department_id=software_dept.id,
            name="Software Engineering Bachelor's Program",
            degree_level="Bachelor",
            duration_years=4,
            quota=80,
            description="Yazılım mühendisliği lisans programı.",
            is_active=True,
        )
        created_count += int(created)
        skipped_count += int(not created)

        _, created = get_or_create(
            db,
            AcademicProgram,
            code="CENG-BSC",
            department_id=computer_dept.id,
            name="Computer Engineering Bachelor's Program",
            degree_level="Bachelor",
            duration_years=4,
            quota=100,
            description="Bilgisayar mühendisliği lisans programı.",
            is_active=True,
        )
        created_count += int(created)
        skipped_count += int(not created)

        # 4) İdari birim
        _, created = get_or_create(
            db,
            AdministrativeUnit,
            code="ERASMUS",
            name="Erasmus Office",
            description="Uluslararası değişim programlarını yürüten ofis.",
            is_active=True,
        )
        created_count += int(created)
        skipped_count += int(not created)

        # Tüm eklemeler sorunsuz tamamlandıysa tek seferde kaydediyoruz.
        db.commit()
        print(f"Seed tamamlandi. Eklenen: {created_count}, zaten mevcut: {skipped_count}")

    except Exception as error:
        # Hata olursa yarım kalmış veri kalmasın diye tüm işlemler geri alınır.
        db.rollback()
        print(f"Seed sirasinda hata olustu: {error}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
