"""Müfredat kataloğu ve akademisyen ders kayıtları endpoint'leri.

Aktarılan 1205 müfredat satırı ve 1836 akademisyen ders kaydı buradan
görünür hâle gelir. Kapsam kuralları diğer analiz uçlarıyla AYNIDIR
(`scope_params` + `resolve`); müfredat da hiyerarşiye tabidir.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import curriculum_service as service
from app.services.scope import resolve, scope_params

router = APIRouter(prefix="/api/curriculum", tags=["Müfredat"])


@router.get("/overview", summary="Müfredat özeti")
def get_overview(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> dict:
    """Ders sayısı, bölüm sayısı ve kaynak belge dağılımı."""
    return service.course_overview(db, resolve(db, **kapsam))


@router.get("/courses", summary="Müfredat dersleri")
def list_courses(
    search: Optional[str] = Query(
        default=None, description="Ders kodu veya adı içinde arar"
    ),
    source_type: Optional[str] = Query(
        default=None, description="Kaynak belge türüne göre süz"
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[dict]:
    """Kapsamdaki müfredat derslerini listeler.

    Aktarılan satırlar kurumun operasyonel verisidir; kalite/doğrulama
    ayrımı yapılmaz.
    """
    return service.list_courses(
        db, resolve(db, **kapsam), search, source_type, skip, limit
    )


@router.get("/by-class-year", summary="Dersler sınıfa göre gruplanmış")
def by_class_year(
    search: Optional[str] = Query(default=None),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[dict]:
    """1./2./3./4. sınıf blokları; sınıfı çıkarılamayan dersler sonda.

    Gruplama ders kodundan gelir ve HER program için aynı biçimde
    çalışır — bölüme özel kural yoktur.
    """
    return service.courses_by_class_year(db, resolve(db, **kapsam), search)


@router.get("/current-teaching", summary="Cari dönem öğretim özeti")
def current_teaching(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> dict:
    """Bu yıl fiilen ders veren kadro, ders ve saat sayısı."""
    return service.current_teaching_summary(db, resolve(db, **kapsam))


@router.get("/by-department", summary="Bölüm bazında ders sayısı ve kadro yükü")
def by_department(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[dict]:
    """Ders sayısı tek başına değil, kadroyla birlikte döner."""
    return service.courses_by_department(db, resolve(db, **kapsam))


@router.get("/sources", summary="Ders kaynaklarının dağılımı")
def sources(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[dict]:
    """Derslerin hangi kaynak belgeden geldiği — köken şeffaflığı."""
    return service.source_type_breakdown(db, resolve(db, **kapsam))


@router.get(
    "/staff/{academic_staff_id}/courses",
    summary="Bir akademisyenin verdiği dersler",
)
def staff_courses(
    academic_staff_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Akademik yıla göre gruplanmış gerçek ders listesi.

    Kaynak YÖK Akademik'in kişi bazlı ders geçmişidir. Ders ataması
    UYDURULMAZ: kaynakta olmayan bir ders burada görünmez.
    """
    sonuc = service.staff_courses(db, academic_staff_id)
    if not sonuc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{academic_staff_id} numaralı akademik personel bulunamadı.",
        )
    return sonuc


@router.get("/staff-course-counts", summary="Kapsamdaki personelin ders sayıları")
def staff_course_counts(
    academic_year: Optional[str] = Query(
        default=None,
        description="Boş bırakılırsa CARİ DÖNEM sayılır; 'all' tüm geçmiş.",
    ),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> Dict[int, int]:
    """Personel listesinde "bu dönem ders veriyor mu?" rozetini besler.

    Varsayılan CARİ DÖNEMDİR: yönetim için "bu yıl ders veriyor mu"
    sorusu, "hiç ders vermiş mi" sorusundan daha yararlıdır.
    """
    # Cari dönem varsayılanı serviste; burada yalnızca aktarılır.
    return service.staff_course_counts(db, resolve(db, **kapsam), academic_year)
