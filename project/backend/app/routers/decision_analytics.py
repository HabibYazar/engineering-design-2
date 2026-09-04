"""Karar destek göstergeleri endpoint'leri.

Bütün göstergeler `decision_analytics_service` içinde hesaplanır ve
yalnızca GERÇEKTEN dolu olan tablolardan türetilir. Veri olmayan
gösterge `None` / `available: false` döner; sıfır dolu kart üretilmez.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import decision_analytics_service as service
from app.services.scope import resolve, scope_params

#: DÖNEM PARAMETRESİ — panonun seçtiği akademik yıl.
#: Verilmezse servisler "en güncel" davranışını korur (geriye dönük
#: uyumluluk). Verilirse O DÖNEM kullanılır ve başka yıla düşülmez.
DONEM_SORGU = Query(
    default=None,
    description='Akademik yıl, ör. "2024-2025". Verilmezse en güncel dönem.',
)

router = APIRouter(prefix="/api/decision-analytics", tags=["Karar Destek"])


@router.get("/overview", summary="Kapsamın bütün karar göstergeleri")
def overview(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    """Tek istekte bütün göstergeler.

    Arayüzün 7 ayrı istek atmasını önler ve hepsinin AYNI kapsamdan
    geldiğini garanti eder — iki isteğin arasında kapsam değişirse
    ekranda karışık veri oluşurdu.
    """
    return service.overview(db, resolve(db, **kapsam), academic_year)


@router.get("/staffing", summary="Öğrenci/personel oranları ve kadro göstergeleri")
def staffing(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    return service.staffing_overview(db, resolve(db, **kapsam), academic_year)


@router.get("/staffing/by-program", summary="Program bazında kadro yeterliliği")
def staffing_by_program(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> List[dict]:
    """Kadro BÖLÜME bağlıdır; satırlar bunu `staff_scope` ile bildirir."""
    return service.staffing_by_program(
        db, resolve(db, **kapsam), academic_year)


@router.get("/titles", summary="Akademik unvan dağılımı")
def titles(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> List[dict]:
    return service.title_distribution(db, resolve(db, **kapsam), academic_year)


@router.get("/teaching-load", summary="Ders yükü dağılımı")
def teaching_load(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    """Ortalama tek başına yanıltıcı olduğu için dağılım da döner."""
    return service.teaching_load_distribution(db, resolve(db, **kapsam), academic_year)


@router.get("/teaching-load/trend", summary="Yıllara göre ders yükü")
def teaching_load_trend(
    kapsam: dict = Depends(scope_params),
    academic_year: Optional[str] = DONEM_SORGU,
    db: Session = Depends(get_db),
) -> List[dict]:
    return service.teaching_load_trend(
        db, resolve(db, **kapsam), academic_year)


@router.get("/publications", summary="Bölüm bazında yayın üretkenliği")
def publications(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> List[dict]:
    return service.publication_productivity(db, resolve(db, **kapsam), academic_year)


@router.get("/course-surveys", summary="Toplulaştırılmış ders anketi analitiği")
def course_surveys(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    """Öğrenci yanıtı/PII döndürmez; program toplamlarını kapsam için birleştirir."""
    return service.course_survey_overview(
        db, resolve(db, **kapsam), academic_year)


@router.get("/student-employment", summary="Toplulaştırılmış mezun istihdam analitiği")
def student_employment(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    return service.student_employment_overview(
        db, resolve(db, **kapsam), academic_year)


@router.get("/publication-quality", summary="Q1 ve H-indeks analitik görünümü")
def publication_quality(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    return service.publication_quality_overview(
        db, resolve(db, **kapsam), academic_year)


@router.get("/salary-scenarios", summary="Toplu akademik personel gideri senaryoları")
def salary_scenarios(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    return service.salary_scenarios(db, resolve(db, **kapsam), academic_year)


@router.get("/supplementary-facilities", summary="Ofis, kütüphane ve ortak alan analitiği")
def supplementary_facilities(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    return service.supplementary_facility_overview(
        db, resolve(db, **kapsam), academic_year)


@router.get("/yks-trend", summary="4 yıllık kontenjan/yerleşen/puan trendi")
def yks_trend(
    kapsam: dict = Depends(scope_params),
    academic_year: Optional[str] = DONEM_SORGU,
    db: Session = Depends(get_db),
) -> dict:
    return service.yks_trend(db, resolve(db, **kapsam), academic_year)


@router.get("/course-concentration", summary="Öğretimin kaç kişiye bağımlı olduğu")
def course_concentration(
    kapsam: dict = Depends(scope_params),
    academic_year: Optional[str] = DONEM_SORGU,
    db: Session = Depends(get_db),
) -> dict:
    return service.course_concentration(
        db, resolve(db, **kapsam), academic_year)


@router.get("/curriculum-load", summary="Müfredat ders sayısı ve kadro")
def curriculum_load(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    return service.curriculum_load(db, resolve(db, **kapsam), academic_year)


@router.get("/executive-overview", summary="Yönetim panosu — tek istek")
def executive_overview(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    """Rektörlük / dekanlık / bölüm yönetimi için kapsam duyarlı pano.

    Alt birim kırılımı seviyeye göre kendiliğinden değişir; arayüz
    hangi seviyede olduğunu bilmek zorunda değildir.
    """
    return service.executive_overview(db, resolve(db, **kapsam), academic_year)


@router.get("/student-body", summary="Öğrenci gövdesi, kohortlar ve talep")
def student_body(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    return service.student_body_overview(db, resolve(db, **kapsam), academic_year)


@router.get("/warnings", summary="Gerçek veriden türetilen operasyonel uyarılar")
def warnings(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> List[dict]:
    return service.operational_warnings(
        db, resolve(db, **kapsam), academic_year)


@router.get("/peer-comparison", summary="Hiyerarşiye uygun karşılaştırma kümesi")
def peer_comparison(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    """Kiminle karşılaştırıldığımızı KAPSAM belirler.

    Üniversite → dış kurumlar, fakülte → kardeş fakülteler,
    bölüm → kardeş bölümler, program → kardeş programlar.
    """
    from app.services import peer_comparison_service

    return peer_comparison_service.peer_comparison(
        db, resolve(db, **kapsam), academic_year)


@router.get(
    "/yok-atlas-comparison",
    summary="Alt kapsamlar için Ankara YÖK Atlas karşılaştırması",
)
def yok_atlas_comparison(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
    institution_type: Optional[str] = Query(
        default=None,
        description="all | state | foundation (boş bırakılırsa 'all'). "
                    "Kurum türü süzgeci ORTAK PROGRAM metodolojisinden "
                    "bağımsızdır; ikisi birlikte uygulanır.",
    ),
    matching_mode: Optional[str] = Query(
        default=None,
        description="same_program | similar_programs | shared_programs. "
                    "Boş bırakılırsa bağlama göre seçilir: fakülte kapsamında "
                    "'shared_programs', program/bölüm kapsamında "
                    "'same_program'. Kurum türü süzgecinden BAĞIMSIZDIR: "
                    "birini değiştirmek diğerini değiştirmez.",
    ),
) -> dict:
    """Eksik alt-kapsam kıyasını ikincil veriyle doldurur.

    Üniversite kapsamında mevcut resmî kayıtlı öğrenci servisi
    kullanılmaya devam eder. Bu uç yalnızca fakülte/bölüm/program
    karşılaştırmaları içindir.
    """
    from app.services import yok_atlas_comparison_service

    return yok_atlas_comparison_service.comparison(
        db, resolve(db, **kapsam), academic_year,
        institution_type=institution_type,
        matching_mode=matching_mode)


@router.get("/child-breakdown", summary="Bir alt seviyedeki birimlerin ölçümü")
def child_breakdown(
    kapsam: dict = Depends(scope_params),
    academic_year: Optional[str] = DONEM_SORGU,
    db: Session = Depends(get_db),
) -> dict:
    from app.services import peer_comparison_service

    return peer_comparison_service.child_breakdown(
        db, resolve(db, **kapsam), academic_year)


@router.get("/enrolled-headcount",
            summary="YÖK kayıtlı öğrenci sayısı ve büyüme (üniversite düzeyi)")
def enrolled_headcount(
    kapsam: dict = Depends(scope_params),
    academic_year: Optional[str] = DONEM_SORGU,
    db: Session = Depends(get_db),
) -> dict:
    """Kurumun fiilen kayıtlı öğrenci sayısı ve yıllık değişimi.

    Kaynakta fakülte/bölüm kırılımı YOKTUR; alt kapsamlarda
    `available: false` döner. Üniversite toplamını alt birime yazmak
    uydurma olurdu.
    """
    from app.services import university_headcount_service

    return university_headcount_service.enrolled_headcount(
        db, resolve(db, **kapsam), donem=academic_year)


@router.get("/enrolled-headcount/peers",
            summary="Aynı ildeki üniversitelerin kayıtlı öğrenci sayısı")
def enrolled_headcount_peers(
    kapsam: dict = Depends(scope_params),
    academic_year: Optional[str] = Query(
        default=None, description="Boş bırakılırsa en güncel yıl."),
    db: Session = Depends(get_db),
) -> List[dict]:
    """DIŞ kurum karşılaştırması — yalnızca üniversite kapsamında.

    Kaynakta fakülte/bölüm/program kayıtlı öğrenci toplamı yoktur. Dar
    kapsam gönderildiğinde üniversite toplamlarını sessizce döndürmek yerine
    boş küme döner; arayüz karşılaştırılamayan kapsam açıklamasını gösterir.
    """
    from app.services import university_headcount_service

    scope = resolve(db, **kapsam)
    if not scope.is_university:
        return []
    return university_headcount_service.peer_headcounts(db, academic_year)


@router.get("/program-year-comparison",
            summary="Seçilen bölümde yıllara göre kontenjan ve doluluk")
def program_year_comparison(
    program_key: Optional[str] = Query(
        default=None,
        description="Kanonik program anahtarı (ör. COMPUTER_ENG). Boşsa "
                    "en çok kurumda bulunan bölüm seçilir.",
    ),
    institution_type: Optional[str] = Query(
        default="all",
        description="all | state | foundation | similar — mevcut kurum "
                    "süzgeci mantığının aynısı",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """PROGRAM kapsamında 2022–2024 kontenjan/yerleşen/doluluk.

    Mevcut uçlar bu kırılımı vermiyordu: `university-competitors` yıl
    kırılımı olarak yalnızca öğrenci mevcudu, `yok-atlas-comparison` ise
    üniversite kapsamında veri döndürmüyor. Bu uç yalnızca eksik olanı
    ekler; ikisi de değiştirilmedi.

    ÜNİVERSİTE TOPLAMINA DÜŞÜLMEZ: kurumda seçilen bölüm yoksa kurum
    listeye girmez, başka bölümlerin kontenjanı toplanmaz.
    """
    from app.services import program_year_comparison_service

    return program_year_comparison_service.comparison(
        db, program_key, institution_type or "all"
    )


@router.get("/university-competitors",
            summary="Üniversite seviyesi rakip analizi")
def university_competitors(
    filter_mode: Optional[str] = Query(
        default=None,
        description="similar | all | foundation | state "
                    "(boş bırakılırsa 'all')",
    ),
    matching_mode: Optional[str] = Query(
        default=None,
        description="all_programs | same_program | similar_programs "
                    "(boş bırakılırsa 'all_programs')",
    ),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    """ÜNİVERSİTE kapsamına özgü rakip panosu."""
    from app.services import university_competitor_service

    return university_competitor_service.competitor_analysis(
        db, filter_mode, academic_year, matching_mode
    )


@router.get("/scholarship-breakdown",
            summary="Burs türüne göre kontenjan, doluluk ve puan")
def scholarship_breakdown(
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
    academic_year: Optional[str] = DONEM_SORGU,
) -> dict:
    """Tam burslu / %50 indirimli / ücretli kırılımı — ÖSYM verisinden."""
    return service.scholarship_breakdown(db, resolve(db, **kapsam), academic_year)


@router.get("/foreign-students",
            summary="Yabancı öğrenci sayısı (ve uyumlu payda varsa oranı)")
def foreign_students(
    kapsam: dict = Depends(scope_params),
    academic_year: Optional[str] = DONEM_SORGU,
    db: Session = Depends(get_db),
) -> dict:
    """Kapsam + dönem bazlı yabancı öğrenci sayısı.

    ORAN yalnızca aynı kapsam/yıl/nüfus tanımına sahip bir payda varsa
    hesaplanır (üniversite düzeyinde YÖK kayıtlı öğrenci sayısı). Alt
    kapsamlarda sayı gösterilir, oran "ölçülemez" olarak bildirilir.
    """
    from app.services import foreign_student_service

    return foreign_student_service.foreign_students(
        db, resolve(db, **kapsam), academic_year)


@router.get("/foreign-students/by-faculty",
            summary="Fakülte başına yabancı öğrenci sayısı")
def foreign_students_by_faculty(
    academic_year: Optional[str] = DONEM_SORGU,
    db: Session = Depends(get_db),
) -> dict:
    from app.services import foreign_student_service

    return foreign_student_service.faculty_breakdown(db, academic_year)
