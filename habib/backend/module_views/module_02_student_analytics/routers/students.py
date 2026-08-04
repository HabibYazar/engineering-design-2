"""Öğrenci ve akademik kayıt CRUD endpoint'leri.

Router yalnızca isteği alır, doğrulama yardımcılarını ve servis katmanını çağırır.
Analitik hesaplamalar bu dosyada değil, student_analytics_service içindedir.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AcademicProgram, Student, StudentAcademicRecord
from app.schemas.students import (
    Semester,
    StudentAcademicRecordCreate,
    StudentAcademicRecordResponse,
    StudentAcademicRecordUpdate,
    StudentCreate,
    StudentResponse,
    StudentStatus,
    StudentUpdate,
)
from app.services.crud_helpers import apply_updates, get_object_or_404
from app.services.student_analytics_service import build_student_filter_statement

router = APIRouter(prefix="/api/students", tags=["Students"])

STUDENT_LABEL: str = "Öğrenci"
RECORD_LABEL: str = "Akademik kayıt"


# ===========================================================================
# Yardımcı doğrulamalar
# ===========================================================================


def _ensure_program_exists(db: Session, program_id: int) -> AcademicProgram:
    """Öğrencinin bağlanacağı akademik programın var olduğunu doğrular."""
    # Geçersiz program id'sinde ham veritabanı hatası yerine anlaşılır 404 döndürüyoruz.
    program: Optional[AcademicProgram] = db.get(AcademicProgram, program_id)
    if program is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"İlişkili akademik program bulunamadı (academic_program_id={program_id}).",
        )
    return program


def _ensure_student_number_unique(
    db: Session, student_number: str, exclude_id: Optional[int] = None
) -> None:
    """Aynı öğrenci numarasına sahip başka kayıt varsa 409 fırlatır."""
    statement = select(Student).where(Student.student_number == student_number)
    if exclude_id is not None:
        statement = statement.where(Student.id != exclude_id)

    if db.execute(statement).scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{student_number}' numaralı öğrenci zaten kayıtlı.",
        )


def _ensure_record_unique(
    db: Session,
    student_id: int,
    academic_year: str,
    semester: str,
    exclude_id: Optional[int] = None,
) -> None:
    """Aynı öğrenci + yıl + dönem kaydı varsa 409 fırlatır."""
    # Veritabanında da UniqueConstraint var; burada önceden kontrol ederek
    # kullanıcıya ham bütünlük hatası yerine anlaşılır bir mesaj veriyoruz.
    statement = (
        select(StudentAcademicRecord)
        .where(StudentAcademicRecord.student_id == student_id)
        .where(StudentAcademicRecord.academic_year == academic_year)
        .where(StudentAcademicRecord.semester == semester)
    )
    if exclude_id is not None:
        statement = statement.where(StudentAcademicRecord.id != exclude_id)

    if db.execute(statement).scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bu öğrenci için {academic_year} akademik yılı {semester} dönemine ait "
                "kayıt zaten mevcut."
            ),
        )


# ===========================================================================
# Öğrenci CRUD
# ===========================================================================


@router.post("", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)) -> Student:
    """Yeni bir öğrenci kaydı oluşturur."""
    _ensure_program_exists(db, payload.academic_program_id)
    _ensure_student_number_unique(db, payload.student_number)

    data = payload.model_dump()
    # Enum alanları veritabanına metin olarak yazılır.
    data["gender"] = payload.gender.value
    data["current_status"] = payload.current_status.value

    student = Student(**data)
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("", response_model=List[StudentResponse])
def list_students(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    academic_program_id: Optional[int] = Query(default=None, gt=0),
    department_id: Optional[int] = Query(default=None, gt=0),
    faculty_id: Optional[int] = Query(default=None, gt=0),
    current_status: Optional[StudentStatus] = Query(default=None),
    is_international: Optional[bool] = Query(default=None),
    preparatory_school: Optional[bool] = Query(default=None),
    enrollment_year: Optional[int] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(
        default=None, description="Öğrenci numarası, ad veya soyadda arama yapar"
    ),
    db: Session = Depends(get_db),
) -> List[Student]:
    """Öğrencileri filtre ve sayfalama ile listeler."""
    # Filtre mantığı servis katmanında; router sadece parametreleri iletir.
    statement = build_student_filter_statement(
        faculty_id=faculty_id,
        department_id=department_id,
        academic_program_id=academic_program_id,
        current_status=current_status.value if current_status else None,
        is_international=is_international,
        preparatory_school=preparatory_school,
        enrollment_year=enrollment_year,
        is_active=is_active,
        search=search,
    )
    statement = statement.order_by(Student.id).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get("/{student_id}", response_model=StudentResponse)
def get_student(student_id: int, db: Session = Depends(get_db)) -> Student:
    """Tek bir öğrenciyi id ile getirir."""
    return get_object_or_404(db, Student, student_id, STUDENT_LABEL)


@router.put("/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: int,
    payload: StudentUpdate,
    db: Session = Depends(get_db),
) -> Student:
    """Var olan bir öğrenciyi kısmi olarak günceller."""
    student = get_object_or_404(db, Student, student_id, STUDENT_LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    if "academic_program_id" in update_data and update_data["academic_program_id"] is not None:
        _ensure_program_exists(db, update_data["academic_program_id"])

    if "student_number" in update_data and update_data["student_number"] is not None:
        _ensure_student_number_unique(
            db, update_data["student_number"], exclude_id=student_id
        )

    # Enum alanlarını metne çeviriyoruz.
    if update_data.get("gender") is not None:
        update_data["gender"] = update_data["gender"].value
    if update_data.get("current_status") is not None:
        update_data["current_status"] = update_data["current_status"].value

    # Mezuniyet yılı tutarlılığı: güncellenen değerlerle birlikte tekrar kontrol edilir.
    enrollment_year: int = update_data.get("enrollment_year", student.enrollment_year)
    graduation_year = update_data.get("actual_graduation_year", student.actual_graduation_year)
    if graduation_year is not None and graduation_year < enrollment_year:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["body", "actual_graduation_year"],
                    "msg": (
                        f"Gerçek mezuniyet yılı ({graduation_year}) kayıt yılından "
                        f"({enrollment_year}) küçük olamaz."
                    ),
                    "type": "value_error",
                }
            ],
        )

    apply_updates(student, update_data)
    db.commit()
    db.refresh(student)
    return student


@router.delete("/{student_id}", response_model=StudentResponse)
def deactivate_student(student_id: int, db: Session = Depends(get_db)) -> Student:
    """Öğrenciyi silmez, is_active=False yaparak pasifleştirir."""
    # Akademik kayıtları ve geçmiş istatistikleri korumak için fiziksel silme yapılmıyor.
    student = get_object_or_404(db, Student, student_id, STUDENT_LABEL)
    student.is_active = False
    db.commit()
    db.refresh(student)
    return student


# ===========================================================================
# Akademik kayıt CRUD
# ===========================================================================


@router.post(
    "/{student_id}/academic-records",
    response_model=StudentAcademicRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_academic_record(
    student_id: int,
    payload: StudentAcademicRecordCreate,
    db: Session = Depends(get_db),
) -> StudentAcademicRecord:
    """Öğrenci için yeni bir dönemlik akademik kayıt oluşturur."""
    get_object_or_404(db, Student, student_id, STUDENT_LABEL)
    _ensure_record_unique(db, student_id, payload.academic_year, payload.semester.value)

    data = payload.model_dump()
    data["semester"] = payload.semester.value

    record = StudentAcademicRecord(student_id=student_id, **data)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get(
    "/{student_id}/academic-records",
    response_model=List[StudentAcademicRecordResponse],
)
def list_academic_records(
    student_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    academic_year: Optional[str] = Query(default=None),
    semester: Optional[Semester] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[StudentAcademicRecord]:
    """Bir öğrencinin akademik kayıtlarını listeler."""
    get_object_or_404(db, Student, student_id, STUDENT_LABEL)

    statement = select(StudentAcademicRecord).where(
        StudentAcademicRecord.student_id == student_id
    )
    if academic_year:
        statement = statement.where(StudentAcademicRecord.academic_year == academic_year)
    if semester:
        statement = statement.where(StudentAcademicRecord.semester == semester.value)

    statement = (
        statement.order_by(
            StudentAcademicRecord.academic_year, StudentAcademicRecord.id
        )
        .offset(skip)
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


@router.get(
    "/{student_id}/academic-records/{record_id}",
    response_model=StudentAcademicRecordResponse,
)
def get_academic_record(
    student_id: int,
    record_id: int,
    db: Session = Depends(get_db),
) -> StudentAcademicRecord:
    """Tek bir akademik kaydı getirir."""
    get_object_or_404(db, Student, student_id, STUDENT_LABEL)
    record = get_object_or_404(db, StudentAcademicRecord, record_id, RECORD_LABEL)

    # Kayıt başka bir öğrenciye aitse yol tutarsızdır; 404 döndürüyoruz.
    if record.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bu akademik kayıt {student_id} numaralı öğrenciye ait değil.",
        )
    return record


@router.put(
    "/{student_id}/academic-records/{record_id}",
    response_model=StudentAcademicRecordResponse,
)
def update_academic_record(
    student_id: int,
    record_id: int,
    payload: StudentAcademicRecordUpdate,
    db: Session = Depends(get_db),
) -> StudentAcademicRecord:
    """Var olan bir akademik kaydı kısmi olarak günceller."""
    record = get_academic_record(student_id, record_id, db)
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("semester") is not None:
        update_data["semester"] = update_data["semester"].value

    # Yıl veya dönem değişiyorsa tekrar kaydı oluşmadığını kontrol ediyoruz.
    new_year: str = update_data.get("academic_year", record.academic_year)
    new_semester: str = update_data.get("semester", record.semester)
    if new_year != record.academic_year or new_semester != record.semester:
        _ensure_record_unique(db, student_id, new_year, new_semester, exclude_id=record_id)

    # Sayısal tutarlılık, güncellenmiş değerler birleştirilerek yeniden doğrulanır.
    registered = update_data.get("registered_course_count", record.registered_course_count)
    passed = update_data.get("passed_course_count", record.passed_course_count)
    failed = update_data.get("failed_course_count", record.failed_course_count)
    earned = update_data.get("earned_credits", record.earned_credits)
    attempted = update_data.get("attempted_credits", record.attempted_credits)

    if passed + failed > registered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["body", "passed_course_count"],
                    "msg": (
                        f"Geçilen ({passed}) ve kalınan ({failed}) ders sayısının toplamı, "
                        f"kayıtlı ders sayısını ({registered}) aşamaz."
                    ),
                    "type": "value_error",
                }
            ],
        )
    if earned > attempted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["body", "earned_credits"],
                    "msg": (
                        f"Kazanılan kredi ({earned}), denenen krediyi ({attempted}) aşamaz."
                    ),
                    "type": "value_error",
                }
            ],
        )

    apply_updates(record, update_data)
    db.commit()
    db.refresh(record)
    return record


@router.delete(
    "/{student_id}/academic-records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_academic_record(
    student_id: int,
    record_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Bir akademik kaydı siler."""
    # Akademik kayıtlarda is_active alanı yok; yanlış girilen bir dönem kaydının
    # tamamen kaldırılması gerektiği için burada fiziksel silme uygulanıyor.
    record = get_academic_record(student_id, record_id, db)
    db.delete(record)
    db.commit()
