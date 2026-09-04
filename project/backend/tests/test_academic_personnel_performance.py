"""Akademik personel ekranı için odaklı puan ve kapsam kontrolleri."""

from decimal import Decimal

from app.models import AcademicProgram, AcademicStaff, Department, Faculty
from app.models.program_allocation import ProgramAcademicStaffAllocation
from app.services import academic_staff_service
from app.services.scope import resolve


def _staff(**overrides) -> AcademicStaff:
    data = {
        "id": 901,
        "staff_number": "FOCUSED-901",
        "first_name": "Odak",
        "last_name": "Test",
        "title": "DOÇENT",
        "department_id": 1,
        "academic_year": "2098-2099",
        "publication_count": 16,
        "citation_count": 0,
        "teaching_load_hours": 0,
        "advising_count": 0,
        "project_count": 0,
        "patent_count": 0,
        "community_engagement_score": 0,
    }
    data.update(overrides)
    return AcademicStaff(**data)


def test_configured_score_and_missing_components_are_explicit():
    expected = academic_staff_service.academic_performance_score(_staff())
    assert expected["total_score"] == 80
    assert expected["classification"] == "beklenen performans"
    assert expected["weights"]["publication_count"] == 5
    assert expected["component_breakdown"]["citation_count"] == {
        "metric_key": "citation_count",
        "label": "Atıf sayısı",
        "value": None,
        "available": False,
        "weight": 2.0,
        "contribution": 0.0,
        "source_type": None,
        "source_label": None,
    }

    uploaded = academic_staff_service.academic_performance_score(
        _staff(),
        uploaded_metrics={
            "citation_count": {"value": Decimal("35"), "filename": "atif.xlsx"}
        },
    )
    assert uploaded["total_score"] == 150
    assert uploaded["classification"] == "yüksek performans"
    assert uploaded["component_breakdown"]["citation_count"]["source_type"] == "uploaded"


def test_faculty_department_and_program_allocation_scope(db_session, unique_suffix):
    year = "2098-2099"
    faculty_one = Faculty(name=f"Odak Fakülte {unique_suffix}", code=f"OF-{unique_suffix}")
    faculty_two = Faculty(name=f"Diğer Fakülte {unique_suffix}", code=f"DF-{unique_suffix}")
    db_session.add_all([faculty_one, faculty_two])
    db_session.flush()
    department_one = Department(
        faculty_id=faculty_one.id, name=f"Odak Bölüm {unique_suffix}", code=f"OB-{unique_suffix}"
    )
    department_two = Department(
        faculty_id=faculty_two.id, name=f"Diğer Bölüm {unique_suffix}", code=f"DB-{unique_suffix}"
    )
    db_session.add_all([department_one, department_two])
    db_session.flush()
    program = AcademicProgram(
        department_id=department_one.id,
        name=f"Odak Program {unique_suffix}",
        code=f"OP-{unique_suffix}",
        degree_level="Bachelor",
    )
    first = _staff(
        id=None, staff_number=f"S1-{unique_suffix}", department_id=department_one.id,
        publication_count=30,
    )
    second = _staff(
        id=None, staff_number=f"S2-{unique_suffix}", department_id=department_two.id,
        publication_count=10,
    )
    db_session.add_all([program, first, second])
    db_session.flush()

    faculty_rows = academic_staff_service.rank_staff(
        db_session, academic_year=year, scope=resolve(db_session, faculty_id=faculty_one.id)
    )
    department_rows = academic_staff_service.rank_staff(
        db_session, academic_year=year,
        scope=resolve(db_session, department_id=department_one.id),
    )
    program_scope = resolve(db_session, academic_program_id=program.id)
    assert [row["staff_id"] for row in faculty_rows] == [first.id]
    assert [row["staff_id"] for row in department_rows] == [first.id]
    assert academic_staff_service.rank_staff(
        db_session, academic_year=year, scope=program_scope
    ) == []

    db_session.add(ProgramAcademicStaffAllocation(
        academic_year=year,
        program_id=program.id,
        academic_staff_id=first.id,
        allocation_percent=Decimal("50"),
        weekly_course_hours=6,
        role="öğretim üyesi",
        is_primary=True,
    ))
    db_session.flush()
    allocated = academic_staff_service.rank_staff(
        db_session, academic_year=year, scope=program_scope
    )
    assert [row["staff_id"] for row in allocated] == [first.id]
    db_session.rollback()
