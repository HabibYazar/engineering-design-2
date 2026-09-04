"""Regression tests for the secondary Ankara YÖK Atlas integration."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    AcademicProgram,
    ComparableUniversityProgram,
    DataSourceConflict,
    Department,
    Faculty,
    YokAtlasBenchmarkMetric,
    YksPlacementRecord,
)
from app.services.scope import DEPARTMENT_LEVEL, FACULTY_LEVEL, Scope
from app.services import yok_atlas_comparison_service as comparison_service
from app.services.program_equivalence import (
    ENGINEERING_ARCHITECTURE,
    SOCIAL_SCIENCES,
    canonical_program_family,
    canonical_program_key,
)
from import_yok_atlas_ankara import (
    DEFAULT_SOURCE_DIR,
    EXPECTED_PROGRAM_UNIVERSITIES,
    EXPECTED_SOURCE_ROWS,
    SOURCE_DATASET,
    import_yok_atlas,
    validate_source,
)


@pytest.fixture(scope="module")
def atlas_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = Session(engine)

    faculty = Faculty(
        name="Mühendislik ve Mimarlık Fakültesi",
        code="ATLAS-FAC",
        unit_type="FACULTY",
    )
    db.add(faculty)
    db.flush()
    department = Department(
        faculty_id=faculty.id,
        name="Yazılım Mühendisliği",
        code="ATLAS-DEPT",
    )
    db.add(department)
    db.flush()
    program = AcademicProgram(
        department_id=department.id,
        name="Software Engineering Bachelor's Program",
        code="ATLAS-SWE",
        degree_level="Bachelor",
        student_count=777,
        student_count_source_method="authoritative-test",
        student_count_year_span="2022-2024",
    )
    db.add(program)
    db.flush()

    for year, quota, placed in (
        (2022, 111, 101),
        (2023, 122, 102),
        (2024, 133, 103),
    ):
        db.add(
            YksPlacementRecord(
                academic_program_id=program.id,
                placement_year=year,
                academic_year=f"{year}-{year + 1}",
                placement_program_name="Software Engineering (Authoritative)",
                score_type="SAY",
                scholarship_type=f"Authoritative-{year}",
                quota=quota,
                placed_students=placed,
                occupancy_rate=None,
                base_score=400 + (year - 2022),
                success_rank=10000 + (year - 2022),
                source_dataset="Existing authoritative project YKS",
                source_file="authoritative-test.csv",
                source_row_key=f"authoritative-{year}",
            )
        )
    db.commit()

    before = {
        "program": (
            program.student_count,
            program.student_count_source_method,
            program.student_count_year_span,
        ),
        "yks": list(
            db.execute(
                select(
                    YksPlacementRecord.placement_year,
                    YksPlacementRecord.quota,
                    YksPlacementRecord.placed_students,
                    YksPlacementRecord.base_score,
                    YksPlacementRecord.success_rank,
                ).order_by(YksPlacementRecord.placement_year)
            ).all()
        ),
    }
    report = import_yok_atlas(db, DEFAULT_SOURCE_DIR, purge=True)

    department_scope = Scope(
        level=DEPARTMENT_LEVEL,
        faculty_id=faculty.id,
        department_id=department.id,
        faculty_ids=frozenset({faculty.id}),
        department_ids=frozenset({department.id}),
        program_ids=frozenset({program.id}),
        label="Yazılım Mühendisliği",
        program_codes=frozenset({program.code}),
    )
    faculty_scope = Scope(
        level=FACULTY_LEVEL,
        faculty_id=faculty.id,
        faculty_ids=frozenset({faculty.id}),
        department_ids=frozenset({department.id}),
        program_ids=frozenset({program.id}),
        label=faculty.name,
        program_codes=frozenset({program.code}),
    )
    yield db, report, before, program, department_scope, faculty_scope
    db.close()
    engine.dispose()


def test_source_contract_and_hashes_are_immutable() -> None:
    audit = validate_source(Path(DEFAULT_SOURCE_DIR))
    assert len(audit["rows"]) == EXPECTED_SOURCE_ROWS == 1768
    assert len(audit["program_universities"]) == EXPECTED_PROGRAM_UNIVERSITIES == 21
    assert audit["years"] == [2022, 2023, 2024]
    assert audit["duplicate_ids"] == []


def test_import_all_real_data_wires_atlas_as_last_stage() -> None:
    source = (Path(__file__).resolve().parents[1] / "import_all_real_data.py").read_text(
        encoding="utf-8"
    )
    assert "6/6  Ankara YÖK Atlas" in source
    assert "import_yok_atlas_ankara.py" in source
    assert source.rindex("import_foreign_students.py") < source.rindex(
        "import_yok_atlas_ankara.py"
    )


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Yazılım Mühendisliği", "SOFTWARE_ENG"),
        ("Software Engineering", "SOFTWARE_ENG"),
        ("Software Engineering Bachelor's Program", "SOFTWARE_ENG"),
        ("Bilgisayar Mühendisliği BÖLÜMÜ", "COMPUTER_ENG"),
        ("Computer Engineering PR.", "COMPUTER_ENG"),
        ("Psikoloji PROGRAMI", "PSYCHOLOGY"),
        ("Psychology", "PSYCHOLOGY"),
    ],
)
def test_program_matching_is_exact_deterministic_and_suffix_safe(label, expected) -> None:
    assert canonical_program_key(label) == expected


@pytest.mark.parametrize(
    ("label", "expected_family"),
    [
        ("Computer Engineering", ENGINEERING_ARCHITECTURE),
        ("Elektrik-Elektronik Mühendisliği", ENGINEERING_ARCHITECTURE),
        ("Endüstri Mühendisliği", ENGINEERING_ARCHITECTURE),
        ("Makine Mühendisliği", ENGINEERING_ARCHITECTURE),
        ("Psychology", SOCIAL_SCIENCES),
        ("Business Administration", SOCIAL_SCIENCES),
        ("İngilizce Öğretmenliği", SOCIAL_SCIENCES),
        ("Siyaset Bilimi ve Uluslararası İlişkiler", SOCIAL_SCIENCES),
        ("Tanımsız Yeni Program", "OTHER"),
    ],
)
def test_program_family_is_controlled_and_fails_closed(label, expected_family) -> None:
    assert canonical_program_family(canonical_program_key(label)) == expected_family


def test_import_is_normalized_idempotent_and_ankara_only(atlas_db) -> None:
    db, report, *_ = atlas_db
    assert report["source_rows"] == 1768
    assert report["ankara_universities"] == 21
    assert report["years"] == [2022, 2023, 2024]
    assert report["non_ankara_rows"] == 0
    assert report["older_metrics_imported"] == 0
    assert report["source_files_unchanged"] is True
    assert report["inserted"] > 30000
    assert report["skipped_duplicate_rows"] == 0

    stored = db.scalar(select(func.count()).select_from(YokAtlasBenchmarkMetric))
    assert stored == report["inserted"]
    assert set(
        db.execute(select(YokAtlasBenchmarkMetric.source_year).distinct()).scalars()
    ) == {2022, 2023, 2024}
    assert set(
        db.execute(select(YokAtlasBenchmarkMetric.city).distinct()).scalars()
    ) == {"ANKARA"}

    second = import_yok_atlas(db, DEFAULT_SOURCE_DIR)
    assert second["inserted"] == 0
    assert second["unchanged"] == stored
    assert db.scalar(select(func.count()).select_from(YokAtlasBenchmarkMetric)) == stored


def test_authoritative_program_and_yks_values_are_never_overwritten(atlas_db) -> None:
    db, report, before, program, *_ = atlas_db
    db.refresh(program)
    after_program = (
        program.student_count,
        program.student_count_source_method,
        program.student_count_year_span,
    )
    after_yks = list(
        db.execute(
            select(
                YksPlacementRecord.placement_year,
                YksPlacementRecord.quota,
                YksPlacementRecord.placed_students,
                YksPlacementRecord.base_score,
                YksPlacementRecord.success_rank,
            ).order_by(YksPlacementRecord.placement_year)
        ).all()
    )
    assert after_program == before["program"]
    assert after_yks == before["yks"]
    assert report["conflicts"] > 0
    assert db.scalar(
        select(func.count()).select_from(DataSourceConflict).where(
            DataSourceConflict.incoming_source == SOURCE_DATASET,
            DataSourceConflict.resolution == "kept_existing",
        )
    ) > 0


@pytest.mark.parametrize(
    ("period", "years", "expected_home_cohort"),
    [
        ("2022-2023", [2022], 101),
        ("2023-2024", [2022, 2023], 203),
        ("2024-2025", [2022, 2023, 2024], 306),
    ],
)
def test_cohort_window_uses_only_2022_through_selected_year(
    atlas_db, period, years, expected_home_cohort
) -> None:
    db, _, _, _, department_scope, _ = atlas_db
    result = comparison_service.comparison(db, department_scope, period)
    assert result["available"] is True
    assert result["years_used"] == years
    home = next(row for row in result["peers"] if row["is_home_institution"])
    assert home["cohort_size"] == expected_home_cohort
    assert result["registered_headcount"] is False
    assert "kayıtlı öğrenci sayısı değildir" in result["subtitle"]


def test_2025_uses_latest_atlas_window_without_inventing_2025(atlas_db) -> None:
    db, _, _, _, department_scope, _ = atlas_db
    result = comparison_service.comparison(db, department_scope, "2025-2026")
    assert result["available"] is True
    assert result["latest_available"] is True
    assert result["requested_period"] == "2025-2026"
    assert result["source_window"] == "2022-2024"
    assert result["contains_2025_data"] is False
    assert result["years_used"] == [2022, 2023, 2024]
    assert result["current_metric_source_year"] == 2024
    assert result["current_metric_period"] == "2024-2025"
    # BEKLENTİ DEĞİŞİKLİĞİ (gizlenmiş bir regresyon DEĞİL):
    #   ESKİ: "Son mevcut YÖK Atlas verisi · 2022-2024"
    #   YENİ: "Son mevcut YÖK Atlas verisi · 2022-2024 · aynı bölüm"
    # Alt başlık artık kullanılan PROGRAM EŞLEŞTİRME KİPİNİ de söylüyor.
    # Bunu söylememek, aynı grafiğin farklı kiplerde farklı sayı
    # göstermesine rağmen aynı görünmesi demekti; kaynak penceresi
    # ("2022-2024") ve yıl mantığı değişmedi ve yukarıda hâlâ test ediliyor.
    assert result["subtitle"].startswith(
        "Son mevcut YÖK Atlas verisi · 2022-2024")
    assert result["subtitle"].endswith("· aynı bölüm")
    assert result["matching_mode"] == "same_program"
    assert "2025 verisi kaynakta bulunmadığı" in result["methodology"]

    home = next(row for row in result["peers"] if row["is_home_institution"])
    assert home["cohort_size"] == 101 + 102 + 103
    assert home["quota"] == 133
    assert home["placed_students"] == 103
    assert {item["source_year"] for item in home["yearly"]} == {2022, 2023, 2024}
    assert all(item["source_year"] != 2025 for row in result["peers"] for item in row["yearly"])
    assert home["metric_sources"]["placed"] == "Mevcut ABÜ ÖSYM/YKS verisi"


def test_existing_comparable_metric_x_beats_atlas_y(atlas_db) -> None:
    db, _, _, _, department_scope, _ = atlas_db
    authoritative = ComparableUniversityProgram(
        university_name="TED ÜNİVERSİTESİ",
        program_name="Software Engineering",
        city="ANKARA",
        academic_year="2024-2025",
        quota=999,
        enrolled_student_count=888,
        occupancy_rate="88.8",
        minimum_admission_score="444.4",
        is_competitor=True,
    )
    db.add(authoritative)
    db.flush()
    result = comparison_service.comparison(db, department_scope, "2024-2025")
    ted = next(
        row
        for row in result["peers"]
        if row["university_name"] == "TED ÜNİVERSİTESİ"
    )
    assert ted["quota"] == 999
    assert ted["placed_students"] == 888
    assert ted["base_score"] == 444.4
    db.delete(authoritative)
    db.commit()


def test_matching_examples_and_faculty_use_deterministic_keys(atlas_db) -> None:
    db, _, _, _, department_scope, faculty_scope = atlas_db
    software = comparison_service.comparison(db, department_scope, "2024-2025")
    assert software["subject"]["canonical_program_keys"] == ["SOFTWARE_ENG"]
    assert all(
        row["canonical_program_key"] in {None, "SOFTWARE_ENG"}
        for row in software["peers"]
    )
    assert any(
        row["provenance"]["source_row_references"]
        for row in software["peers"]
        if not row["is_home_institution"]
    )

    faculty = comparison_service.comparison(db, faculty_scope, "2024-2025")
    assert faculty["available"] is True
    assert faculty["subject"]["faculty_key"] == "ENGINEERING_FACULTY"
    assert faculty["title"].startswith("Mühendislik Fakülteleri")
    assert all(
        comparison_service.canonical_faculty_key(row["faculty_name"])
        == "ENGINEERING_FACULTY"
        for row in faculty["peers"]
        if not row["is_home_institution"]
    )


def test_engineering_faculty_excludes_incompatible_source_programs(atlas_db) -> None:
    db, _, _, _, _, faculty_scope = atlas_db
    result = comparison_service.comparison(db, faculty_scope, "2024-2025")
    odtu = next(
        row
        for row in result["peers"]
        if row["university_name"] == "ORTA DOĞU TEKNİK ÜNİVERSİTESİ"
    )

    raw_odtu_total = db.scalar(
        select(func.sum(YokAtlasBenchmarkMetric.value)).where(
            YokAtlasBenchmarkMetric.university_name
            == "ORTA DOĞU TEKNİK ÜNİVERSİTESİ",
            YokAtlasBenchmarkMetric.canonical_faculty_key == "ENGINEERING_FACULTY",
            YokAtlasBenchmarkMetric.metric == "placed",
            YokAtlasBenchmarkMetric.source_year.in_([2022, 2023, 2024]),
        )
    )
    assert int(raw_odtu_total) == 5003

    # The test fixture's home faculty only offers Software Engineering, so
    # a faculty-level ("ortak bölümler") comparison must reduce ODTÜ's
    # engineering total down to ODTÜ's own Software Engineering cohort
    # only — not the sum of every ODTÜ engineering program.
    assert odtu["cohort_size"] == 143
    assert [item["placed"] for item in odtu["yearly"]] == [53, 59, 31]

    excluded_reasons = {
        item["program_name"]: item["reason"]
        for item in odtu["provenance"]["excluded_programs"]
    }
    # Programs incompatible with the engineering/architecture family are
    # still excluded for that reason...
    assert excluded_reasons["Psikoloji"] == (
        "program_family_incompatible_with_engineering_faculty"
    )
    assert excluded_reasons["İşletme"] == (
        "program_family_incompatible_with_engineering_faculty"
    )
    # ...while compatible engineering programs the home institution simply
    # doesn't offer are excluded as "not offered at home university",
    # rather than being folded into the comparison total.
    assert excluded_reasons["Bilgisayar Mühendisliği"] == (
        "program_not_offered_at_home_university"
    )
    assert excluded_reasons["Makine Mühendisliği"] == (
        "program_not_offered_at_home_university"
    )
    assert odtu["provenance"]["original_source_faculty_label"] == "Mühendislik Fakültesi"

    included_names = {
        item["program_name"] for item in odtu["provenance"]["included_programs"]
    }
    assert included_names == {"Yazılım Mühendisliği"}
    assert all(
        item["program_family"] == ENGINEERING_ARCHITECTURE
        for item in odtu["provenance"]["included_programs"]
    )


def test_engineering_filter_keeps_known_faculties_sensible(atlas_db) -> None:
    db, _, _, _, _, faculty_scope = atlas_db
    result = comparison_service.comparison(db, faculty_scope, "2024-2025")
    cohorts = {row["university_name"]: row["cohort_size"] for row in result["peers"]}
    # Only peers that also offer Software Engineering (the home faculty's
    # only program in this fixture) remain in the comparison; peers whose
    # engineering faculty doesn't include it (e.g. İhsan Doğramacı Bilkent
    # Üniversitesi, Gazi Üniversitesi, Hacettepe Üniversitesi in this
    # dataset) are correctly dropped rather than shown with an inflated,
    # non-comparable total.
    assert cohorts["ANKARA BİLİM ÜNİVERSİTESİ"] == 306
    assert cohorts["ATILIM ÜNİVERSİTESİ"] == 161
    assert "İHSAN DOĞRAMACI BİLKENT ÜNİVERSİTESİ" not in cohorts
    assert "GAZİ ÜNİVERSİTESİ" not in cohorts
    assert "HACETTEPE ÜNİVERSİTESİ" not in cohorts


@pytest.mark.parametrize(
    ("program_name", "expected_key"),
    [
        ("Computer Engineering", "COMPUTER_ENG"),
        ("Psychology", "PSYCHOLOGY"),
    ],
)
def test_named_lower_scopes_are_available_in_2025_latest_window(
    atlas_db, program_name, expected_key
) -> None:
    db, _, _, _, _, faculty_scope = atlas_db
    department = Department(
        faculty_id=faculty_scope.faculty_id,
        name=f"{program_name} Test Department",
        code=f"LATEST-{expected_key}-DEPT",
    )
    db.add(department)
    db.flush()
    program = AcademicProgram(
        department_id=department.id,
        name=program_name,
        code=f"LATEST-{expected_key}",
        degree_level="Bachelor",
        student_count=0,
        student_count_source_method="test-only",
    )
    db.add(program)
    db.flush()
    scope = Scope(
        level=DEPARTMENT_LEVEL,
        faculty_id=faculty_scope.faculty_id,
        department_id=department.id,
        faculty_ids=frozenset({faculty_scope.faculty_id}),
        department_ids=frozenset({department.id}),
        program_ids=frozenset({program.id}),
        label=program_name,
        program_codes=frozenset({program.code}),
    )

    result = comparison_service.comparison(db, scope, "2025-2026")
    assert result["available"] is True
    assert result["subject"]["canonical_program_keys"] == [expected_key]
    assert result["years_used"] == [2022, 2023, 2024]
    assert result["latest_available"] is True
    assert result["source_window"] == "2022-2024"
    assert result["contains_2025_data"] is False
    assert all(
        annual["source_year"] != 2025
        for row in result["peers"]
        for annual in row["yearly"]
    )

    db.delete(program)
    db.delete(department)
    db.commit()


def test_engineering_faculty_is_available_in_2025_latest_window(atlas_db) -> None:
    db, _, _, _, _, faculty_scope = atlas_db
    result = comparison_service.comparison(db, faculty_scope, "2025-2026")
    assert result["available"] is True
    assert result["title"] == "Mühendislik Fakülteleri — Tahmini Öğrenci Büyüklüğü"
    assert result["requested_period"] == "2025-2026"
    assert result["latest_available"] is True
    assert result["source_window"] == "2022-2024"
    assert result["contains_2025_data"] is False
    odtu = next(
        row
        for row in result["peers"]
        if row["university_name"] == "ORTA DOĞU TEKNİK ÜNİVERSİTESİ"
    )
    assert odtu["cohort_size"] == 143


@pytest.mark.parametrize(
    ("canonical_key", "minimum_universities"),
    [
        ("SOFTWARE_ENG", 8),
        ("COMPUTER_ENG", 10),
        ("PSYCHOLOGY", 10),
    ],
)
def test_named_program_examples_have_2022_2024_peers_and_source_codes(
    atlas_db, canonical_key, minimum_universities
) -> None:
    db, *_ = atlas_db
    rows = db.execute(
        select(
            YokAtlasBenchmarkMetric.university_name,
            YokAtlasBenchmarkMetric.source_year,
            YokAtlasBenchmarkMetric.source_program_code,
        ).where(
            YokAtlasBenchmarkMetric.canonical_program_key == canonical_key,
            YokAtlasBenchmarkMetric.metric == "placed",
        )
    ).all()
    assert len({row.university_name for row in rows}) >= minimum_universities
    assert {row.source_year for row in rows} == {2022, 2023, 2024}
    assert all(row.source_program_code for row in rows)
