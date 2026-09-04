"""EK ARAÇLAR — asistanın erişemediği veri kümelerini açar.

NEDEN AYRI DOSYA
----------------
`tools.py` 80 KB ve beş yıllık bir birikim taşıyor; bugün doğru çalışan
yedi aracın hepsi orada. Bu dosyayı büyütmek yerine yenileri ayrı bir
modüle koymak iki şey sağlar: mevcut araçların davranışı hiçbir biçimde
değişmez ve bu katman gerekirse tek satırlık bir import'la geri alınır.

NEDEN GEREKLİ
-------------
Tanı ölçümü şunu gösterdi: veritabanında 35 dolu tablo ve ~44.000 satır
var; asistanın araçları bunların yalnızca dört modeline (`AcademicProgram`,
`Department`, `PhysicalFacility`, `FinancialPeriod`) ve beş servise
dokunuyordu. Ekranlarda gösterdiğimiz veriyi asistan göremiyordu:

    yok_atlas_benchmark_metrics    36.563 satır   rakip kıyas, kontenjan,
                                                  doluluk, puan, sıralama
    academic_staff_courses          1.836 satır   ders yükü
    curriculum_courses (+canonical) 2.208 satır   müfredat
    university_student_headcounts   1.264 satır   yıllara göre öğrenci
    competitor_tuition_fees           708 satır   rakip ücretler
    strategic_kpis / kpi_faculty_*     52 satır   KPI karnesi
    evaluation_* (5 tablo)            128 satır   sıralama hazırlığı

"Bilgisayar Mühendisliği rakiplere göre nerede?" sorusuna cevap
verememesinin sebebi buydu: cevabın bulunduğu 36.563 satırlık tabloya
hiçbir yol yoktu.

TASARIM KURALLARI
-----------------
1. YENİ SORGU/ALGORİTMA YAZILMAZ. Her araç mevcut bir servisi sarmalar.
   Ekranların kullandığı hesap ile asistanın gördüğü hesap aynı kalmalı;
   ikisi ayrışırsa aynı soruya iki farklı sayı çıkar.
2. VERİ YOKSA "veri yok" DENİR, sıfır yazılmaz.
3. Her araç `data_source` alanında kaynağını Türkçe olarak bildirir.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.services.assistant.tool_registry import (
    ToolDefinition,
    ToolExecutionError,
    registry,
)
from app.services.assistant.tool_schemas import ScopeInput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ORTAK YARDIMCILAR
# ---------------------------------------------------------------------------

def _scope_from(db: Session, payload) -> Optional[Any]:
    """Araç girdisindeki kapsamı `Scope` nesnesine çevirir.

    Kapsam çözülemezse `None` döner ve servis kurum geneli çalışır —
    hata fırlatmak yerine daha geniş kapsama düşmek, kullanıcıyı boş
    cevapla baş başa bırakmaktan iyidir. Cevapta kapsam yazılır.
    """
    ad = getattr(payload, "program", None) or getattr(payload, "department", None) \
        or getattr(payload, "faculty", None)
    if not ad:
        return None
    try:
        from app.services.assistant import entity_resolver
        _yil, fak, bol, prog = entity_resolver.resolve_scope(
            db,
            academic_year=getattr(payload, "academic_year", None),
            faculty=getattr(payload, "faculty", None),
            department=getattr(payload, "department", None),
            program=getattr(payload, "program", None),
        )
        from app.services import scope as scope_service
        varlik = prog or bol or fak
        if varlik is None:
            return None
        return scope_service.resolve_scope(
            db,
            faculty_id=getattr(fak, "entity_id", None) if fak else None,
            department_id=getattr(bol, "entity_id", None) if bol else None,
            program_id=getattr(prog, "entity_id", None) if prog else None,
        )
    except Exception:  # noqa: BLE001
        # Kapsam çözülemedi: kurum geneli ile devam. Sessiz kalmaz, loglanır.
        logger.info("Kapsam cozulemedi, kurum geneli kullaniliyor: %s", ad)
        return None


def _bos_ise_hata(veri: Any, mesaj: str) -> None:
    """Boş sonuç için AÇIK hata — model 'veri yok' diyebilsin."""
    if not veri:
        raise ToolExecutionError(mesaj, kind="metric_unavailable")


# ---------------------------------------------------------------------------
# 1. KURUM YAPISI  (fakülte / bölüm / program sayıları ve adları)
# ---------------------------------------------------------------------------
# Tanı ölçümünde "Kaç fakültemiz var?" sorusu ÜÇ farklı yazımda da
# cevapsız kalıyordu: katalogda fakülte/bölüm sayısı diye bir metrik
# hiç tanımlı değildi. En temel kurumsal soru cevapsızdı.

class OrganizationInput(BaseModel):
    include_names: bool = Field(
        default=True,
        description="Birim adları da listelensin mi. Yalnızca sayı isteniyorsa false.",
    )


class OrganizationOutput(BaseModel):
    """Birim sayıları TÜRE GÖRE ayrılır.

    `faculties` tablosu yalnızca fakülteleri değil, meslek yüksekokulunu
    ve rektörlüğü de tutar (`unit_type`). Ham satır sayısı "fakülte
    sayısı" olarak verilirse rektörlük fakülte sayılır — canlı testte
    tam olarak bu oldu, asistan "7 fakültemiz" deyip listeye Rektörlük'ü
    koydu. Sayılar artık türe göre ayrı döner ve karıştırılamaz.
    """

    faculty_count: int = Field(description="YALNIZCA unit_type=FACULTY")
    vocational_school_count: int = 0
    administrative_unit_count: int = 0
    academic_unit_count: int = Field(
        default=0, description="Fakülte + yüksekokul (idari birimler HARİÇ)")
    department_count: int
    program_count: int
    faculties: List[str] = Field(default_factory=list)
    vocational_schools: List[str] = Field(default_factory=list)
    administrative_units: List[str] = Field(default_factory=list)
    departments: List[str] = Field(default_factory=list)
    programs: List[str] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_organization(db: Session, payload: OrganizationInput) -> OrganizationOutput:
    from app.models import AcademicProgram, Department
    from app.models.faculty import Faculty
    from app.services import unit_types

    birimler = db.query(Faculty).all()
    bolumler = db.query(Department).all()
    programlar = db.query(AcademicProgram).all()

    ad = lambda x: getattr(x, "name", None) or getattr(x, "code", "") or "?"

    # Tür bilgisi KAYITTAN okunur; ad tahminine düşülmez. Kayıtta yoksa
    # `classify_unit` mevcut sınıflandırıcıyı kullanır — yeni bir kural
    # yazılmaz.
    def _tur(u) -> str:
        return (getattr(u, "unit_type", None)
                or unit_types.classify_unit(ad(u), getattr(u, "code", "") or ""))

    fakulteler = [u for u in birimler if _tur(u) == "FACULTY"]
    myo = [u for u in birimler if _tur(u) == "VOCATIONAL_SCHOOL"]
    idari = [u for u in birimler if not unit_types.is_academic(_tur(u))]

    return OrganizationOutput(
        faculty_count=len(fakulteler),
        vocational_school_count=len(myo),
        administrative_unit_count=len(idari),
        academic_unit_count=len(fakulteler) + len(myo),
        department_count=len(bolumler),
        program_count=len(programlar),
        faculties=[ad(f) for f in fakulteler] if payload.include_names else [],
        vocational_schools=[ad(f) for f in myo] if payload.include_names else [],
        administrative_units=[ad(f) for f in idari] if payload.include_names else [],
        departments=[ad(b) for b in bolumler] if payload.include_names else [],
        programs=[ad(p) for p in programlar] if payload.include_names else [],
        note=(f"{len(fakulteler)} fakülte, {len(myo)} meslek yüksekokulu, "
              f"{len(idari)} idari birim. Rektörlük FAKÜLTE DEĞİLDİR ve "
              f"fakülte sayısına dâhil edilmez."),
    )


registry.register(ToolDefinition(
    name="get_organization_structure",
    description=(
        "Üniversitenin akademik yapısı: kaç FAKÜLTE, kaç meslek yüksekokulu, "
        "kaç idari birim, kaç bölüm, kaç program olduğunu ve adlarını "
        "döndürür. 'Kaç fakültemiz var', 'bölümlerimiz neler', 'hangi "
        "programlar var' gibi sorularda kullanılır. ÖNEMLİ: `faculty_count` "
        "yalnızca fakülteleri sayar; Rektörlük ve Meslek Yüksekokulu ayrı "
        "alanlardadır, fakülte sayısına eklenmemelidir."
    ),
    input_model=OrganizationInput,
    output_model=OrganizationOutput,
    handler=_handle_organization,
    timeout_seconds=15.0,
    required_permission=None,
    data_source="Kurumsal hiyerarşi kayıtları",
))


# ---------------------------------------------------------------------------
# 2. RAKİP ÜNİVERSİTE KIYASI  (36.563 satırlık YÖK Atlas)
# ---------------------------------------------------------------------------
# En büyük boşluk buydu. Ekranlardaki bütün kıyas kartları bu veriyi
# kullanıyor, asistanın hiçbir yolu yoktu.

class PeerComparisonInput(BaseModel):
    institution_filter: str = Field(
        default="all",
        description="all | state | foundation | similar — kurum evreni.",
    )
    matching_mode: str = Field(
        default="all_programs",
        description="all_programs | same_program | similar_programs",
    )


class PeerComparisonOutput(BaseModel):
    institution_filter_label: Optional[str] = None
    matching_mode_label: Optional[str] = None
    university_count: int = 0
    home: Optional[Dict[str, Any]] = None
    universities: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_peer_comparison(
    db: Session, payload: PeerComparisonInput
) -> PeerComparisonOutput:
    from app.services import university_competitor_service as svc

    sonuc = svc.competitor_analysis(
        db, payload.institution_filter, None, payload.matching_mode
    )
    kurumlar = sonuc.get("universities") or []
    _bos_ise_hata(kurumlar, "Seçilen kurum evreninde karşılaştırılabilir üniversite yok.")

    # Bağlam penceresini korumak için her kurumdan yalnızca karar için
    # gerekli alanlar taşınır; ham satırın tamamı 30+ alan içeriyor.
    sade = [
        {
            "university": r.get("university_name"),
            "type": r.get("university_type"),
            "is_home": r.get("is_home_institution"),
            "students": r.get("student_count"),
            "academic_staff": r.get("academic_staff_count"),
            "students_per_academic": r.get("students_per_academic"),
            "departments": r.get("department_count"),
            "median_tuition": r.get("median_tuition_fee"),
            "quota": r.get("quota"),
            "placed": r.get("placed"),
            "occupancy_percent": r.get("occupancy_percent"),
        }
        for r in kurumlar
    ]
    return PeerComparisonOutput(
        institution_filter_label=sonuc.get("filter_label"),
        matching_mode_label=sonuc.get("matching_mode_label"),
        university_count=len(sade),
        home=next((r for r in sade if r.get("is_home")), None),
        universities=sade,
        note=sonuc.get("note"),
    )


registry.register(ToolDefinition(
    name="compare_with_peer_universities",
    description=(
        "Ankara'daki diğer üniversitelerle karşılaştırma: öğrenci sayısı, "
        "akademik personel, öğrenci/akademisyen oranı, bölüm sayısı, eğitim "
        "ücreti, kontenjan ve doluluk. 'Rakiplere göre neredeyiz', 'ODTÜ ile "
        "kıyasla', 'Ankara'da kaçıncı sıradayız' gibi sorularda kullanılır. "
        "Kurum evreni daraltılabilir (devlet/vakıf/benzer ölçek)."
    ),
    input_model=PeerComparisonInput,
    output_model=PeerComparisonOutput,
    handler=_handle_peer_comparison,
    timeout_seconds=30.0,
    required_permission=None,
    data_source="YÖK Atlas rakip üniversite kayıtları",
))


# ---------------------------------------------------------------------------
# 3. BÖLÜM × YIL KONTENJAN VE DOLULUK  (2022–2024 seyri)
# ---------------------------------------------------------------------------

class ProgramTrendInput(BaseModel):
    program_key: Optional[str] = Field(
        default=None,
        description=(
            "Kanonik bölüm anahtarı (ör. COMPUTER_ENG, PSYCHOLOGY, LAW). "
            "Boş bırakılırsa ABÜ'nün tüm bölümlerinin toplamı alınır."
        ),
    )
    institution_filter: str = Field(default="all", description="all|state|foundation|similar")


class ProgramTrendOutput(BaseModel):
    program_label: Optional[str] = None
    years: List[int] = Field(default_factory=list)
    with_program_count: int = 0
    without_program_count: int = 0
    universities: List[Dict[str, Any]] = Field(default_factory=list)
    available_programs: List[str] = Field(default_factory=list)
    methodology: Optional[str] = None


def _handle_program_trend(db: Session, payload: ProgramTrendInput) -> ProgramTrendOutput:
    from app.services import program_year_comparison_service as svc

    sonuc = svc.comparison(db, payload.program_key, payload.institution_filter)
    if not sonuc.get("available"):
        raise ToolExecutionError(
            sonuc.get("note") or "Bu bölüm için yıllık kayıt yok.",
            kind="metric_unavailable",
        )
    sade = [
        {
            "university": u["university_name"],
            "is_home": u["is_home_institution"],
            "has_program": u.get("has_program", True),
            "equivalent_program": (u.get("equivalent") or {}).get("label"),
            "series": [
                {"year": s["year"], "quota": s["quota"], "placed": s["placed"],
                 "occupancy_percent": s["occupancy_percent"]}
                for s in u.get("series") or []
            ],
        }
        for u in sonuc.get("universities") or []
    ]
    return ProgramTrendOutput(
        program_label=sonuc.get("program_label"),
        years=sonuc.get("years") or [],
        with_program_count=sonuc.get("with_program_count") or 0,
        without_program_count=sonuc.get("without_program_count") or 0,
        universities=sade,
        available_programs=[p["label"] for p in (sonuc.get("programs") or [])],
        methodology=sonuc.get("methodology"),
    )


registry.register(ToolDefinition(
    name="get_program_quota_trend",
    description=(
        "Seçilen bölümde 2022-2024 yıllarına göre kontenjan, yerleşen ve "
        "doluluk oranının akran üniversitelerle karşılaştırması. 'Bilgisayar "
        "Mühendisliğinde doluluğumuz nasıl gidiyor', 'kontenjanımız rakiplere "
        "göre nerede', 'bu bölüm başka hangi üniversitelerde var' gibi "
        "sorularda kullanılır. Bölüm belirtilmezse tüm bölümlerin toplamı."
    ),
    input_model=ProgramTrendInput,
    output_model=ProgramTrendOutput,
    handler=_handle_program_trend,
    timeout_seconds=30.0,
    required_permission=None,
    data_source="YÖK Atlas kontenjan ve yerleştirme kayıtları · 2022-2024",
))


# ---------------------------------------------------------------------------
# 4. MÜFREDAT
# ---------------------------------------------------------------------------

class CurriculumInput(ScopeInput):
    by_class_year: bool = Field(
        default=False, description="Sınıf/yıl kırılımı istensin mi."
    )


class CurriculumOutput(BaseModel):
    scope_label: str
    total_courses: Optional[int] = None
    canonical_courses: Optional[int] = None
    raw_row_count: Optional[int] = None
    department_count: Optional[int] = None
    by_class_year: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_curriculum(db: Session, payload: CurriculumInput) -> CurriculumOutput:
    from app.services import curriculum_service as svc

    kapsam = _scope_from(db, payload)
    ozet = svc.course_overview(db, kapsam) or {}
    kirilim: List[Dict[str, Any]] = []
    if payload.by_class_year:
        try:
            kirilim = [
                {"label": g.get("label"), "course_count": len(g.get("courses") or [])}
                for g in (svc.courses_by_class_year(db, kapsam) or [])
            ]
        except Exception:  # noqa: BLE001
            logger.info("Sinif yili kirilimi alinamadi")

    # Servisin gerçek anahtarı `total_course_count`. Ham satır sayısı
    # (`raw_row_count`) DEĞİL: aynı ders birden çok kaynaktan geldiğinde
    # iki kez sayılır, "kaç dersimiz var" sorusunun cevabı o değildir.
    toplam = ozet.get("total_course_count")
    if toplam is None and not kirilim:
        raise ToolExecutionError(
            "Bu kapsamda müfredat kaydı bulunmuyor.", kind="metric_unavailable"
        )
    return CurriculumOutput(
        scope_label=(payload.program or payload.department or payload.faculty
                     or "Üniversite geneli"),
        total_courses=toplam,
        canonical_courses=ozet.get("classified_course_count"),
        raw_row_count=ozet.get("raw_row_count"),
        department_count=ozet.get("department_count"),
        by_class_year=kirilim,
        note=("`total_courses` tekilleştirilmiş ders sayısıdır; "
              "`raw_row_count` ham kayıt sayısıdır (aynı ders birden çok "
              "kaynaktan gelebilir)."),
    )


registry.register(ToolDefinition(
    name="get_curriculum_summary",
    description=(
        "Müfredat özeti: ders sayısı, sınıf/yıl dağılımı. 'Kaç dersimiz var', "
        "'müfredatta ne kadar ders', 'birinci sınıfta kaç ders' gibi "
        "sorularda kullanılır. Fakülte/bölüm/program kapsamı verilebilir."
    ),
    input_model=CurriculumInput,
    output_model=CurriculumOutput,
    handler=_handle_curriculum,
    timeout_seconds=20.0,
    required_permission=None,
    data_source="Müfredat ve ders kayıtları",
))


# ---------------------------------------------------------------------------
# 5. AKADEMİSYEN DERS YÜKÜ
# ---------------------------------------------------------------------------

class TeachingLoadInput(ScopeInput):
    top_n: int = Field(default=10, ge=1, le=50,
                       description="Kaç akademisyen listelensin.")


class TeachingLoadOutput(BaseModel):
    scope_label: str
    staff_count: Optional[int] = None
    total_course_records: Optional[int] = None
    average_courses_per_staff: Optional[float] = None
    top_staff: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_teaching_load(db: Session, payload: TeachingLoadInput) -> TeachingLoadOutput:
    from app.models.staff_course import AcademicStaffCourse
    from app.models.academic_staff import AcademicStaff
    from sqlalchemy import func

    # `full_name` bir sütun değil, Python tarafında hesaplanan bir
    # property; SQL'e verilemez. Ad ve soyad ayrı sütunlardan alınır.
    q = (
        db.query(
            AcademicStaff.first_name.label("ad"),
            AcademicStaff.last_name.label("soyad"),
            AcademicStaff.title.label("unvan"),
            func.count(AcademicStaffCourse.id).label("ders"),
            func.sum(AcademicStaffCourse.weekly_hours).label("saat"),
        )
        .join(AcademicStaffCourse,
              AcademicStaffCourse.academic_staff_id == AcademicStaff.id)
        .group_by(AcademicStaff.id)
        .order_by(func.count(AcademicStaffCourse.id).desc())
    )
    satir = q.limit(payload.top_n).all()
    _bos_ise_hata(satir, "Ders yükü kaydı bulunmuyor.")

    toplam = db.query(func.count(AcademicStaffCourse.id)).scalar() or 0
    kisi = db.query(func.count(func.distinct(
        AcademicStaffCourse.academic_staff_id))).scalar() or 0
    return TeachingLoadOutput(
        scope_label=(payload.department or payload.faculty or "Üniversite geneli"),
        staff_count=kisi,
        total_course_records=toplam,
        average_courses_per_staff=round(toplam / kisi, 2) if kisi else None,
        top_staff=[{"name": f"{r.ad} {r.soyad}".strip(), "title": r.unvan,
                    "course_count": r.ders, "weekly_hours": r.saat}
                   for r in satir],
        note=("`course_count` ders KAYDI sayısıdır. `weekly_hours` "
              "kaynakta varsa haftalık saattir; boşsa o kayıt için "
              "saat bilgisi yoktur — sıfır sayılmaz."),
    )


registry.register(ToolDefinition(
    name="get_teaching_load",
    description=(
        "Akademisyenlerin ders yükü: kişi başına ders sayısı ve en çok ders "
        "veren akademisyenler. 'Kimin ders yükü fazla', 'ders yükü dengeli mi', "
        "'ortalama kaç ders' gibi sorularda kullanılır."
    ),
    input_model=TeachingLoadInput,
    output_model=TeachingLoadOutput,
    handler=_handle_teaching_load,
    timeout_seconds=20.0,
    required_permission="view_academic_staff",
    data_source="Akademisyen ders atama kayıtları",
))


# ---------------------------------------------------------------------------
# 6. YILLARA GÖRE ÖĞRENCİ SAYISI (resmî YÖK)
# ---------------------------------------------------------------------------

class HeadcountTrendInput(BaseModel):
    include_peers: bool = Field(
        default=False, description="Akran üniversitelerin sayıları da gelsin mi."
    )


class HeadcountTrendOutput(BaseModel):
    years: List[str] = Field(default_factory=list)
    home_by_year: Dict[str, Optional[int]] = Field(default_factory=dict)
    growth_percent_period: Optional[float] = None
    peers: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_headcount_trend(
    db: Session, payload: HeadcountTrendInput
) -> HeadcountTrendOutput:
    from app.services import university_headcount_service as svc

    yillar = svc.available_years(db) or []
    _bos_ise_hata(yillar, "Resmî öğrenci sayısı kaydı bulunmuyor.")

    bizim: Dict[str, Optional[int]] = {}
    buyume = None
    for y in yillar:
        try:
            veri = svc.enrolled_headcount(db, academic_year=y)
            bizim[y] = (veri or {}).get("student_count")
            if buyume is None:
                buyume = (veri or {}).get("growth_percent_period")
        except Exception:  # noqa: BLE001
            bizim[y] = None

    akranlar: List[Dict[str, Any]] = []
    if payload.include_peers:
        try:
            p = svc.peer_headcounts(db) or {}
            akranlar = [
                {"university": r.get("university_name"),
                 "students": r.get("student_count"),
                 "type": r.get("university_type")}
                for r in (p.get("universities") or p.get("peers") or [])
            ]
        except Exception:  # noqa: BLE001
            logger.info("Akran ogrenci sayilari alinamadi")

    return HeadcountTrendOutput(
        years=list(yillar), home_by_year=bizim,
        growth_percent_period=buyume, peers=akranlar,
        note="YÖK resmî kayıtlı öğrenci sayıları.",
    )


registry.register(ToolDefinition(
    name="get_student_headcount_trend",
    description=(
        "Yıllara göre resmî kayıtlı öğrenci sayısı ve dönemsel büyüme. "
        "'Öğrenci sayımız artıyor mu', 'son yıllarda trend nasıl', 'kaç yıldır "
        "büyüyoruz' gibi sorularda kullanılır. İstenirse akran üniversitelerin "
        "sayıları da gelir."
    ),
    input_model=HeadcountTrendInput,
    output_model=HeadcountTrendOutput,
    handler=_handle_headcount_trend,
    timeout_seconds=25.0,
    required_permission="view_students",
    data_source="YÖK resmî kayıtlı öğrenci sayıları",
))


# ---------------------------------------------------------------------------
# 7. EĞİTİM ÜCRETİ VE RAKİP ÜCRETLERİ
# ---------------------------------------------------------------------------

class TuitionInput(ScopeInput):
    include_competitors: bool = Field(
        default=True, description="Rakip üniversitelerin ücretleri de gelsin mi."
    )


class TuitionOutput(BaseModel):
    scope_label: str
    our_fee: Optional[float] = None
    currency: Optional[str] = None
    competitor_median: Optional[float] = None
    competitors: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_tuition(db: Session, payload: TuitionInput) -> TuitionOutput:
    from app.services import tuition_service as svc

    kapsam = _scope_from(db, payload)
    bizim = None
    try:
        yillar = svc.available_years(db) or []
        yil = yillar[-1] if yillar else None
        if yil:
            # `fee_type` zorunlu: aynı program için burslu/indirimli/ücretli
            # ayrı satırlardır. Kıyasın anlamlı olması için tam ücret alınır.
            bizim = svc.home_scoped_fee(db, kapsam, yil, "Ücretli")
    except Exception:  # noqa: BLE001
        logger.info("Kendi ucretimiz alinamadi", exc_info=True)

    rakipler: List[Dict[str, Any]] = []
    medyan = None
    if payload.include_competitors:
        try:
            from app.models.tuition_fee import CompetitorTuitionFee
            satir = db.query(CompetitorTuitionFee).limit(200).all()
            rakipler = [
                {"university": getattr(r, "university_name", None),
                 "program": getattr(r, "program_name", None),
                 "year": getattr(r, "academic_year", None),
                 "fee": float(getattr(r, "fee_amount", None)
                              or getattr(r, "amount", None)
                              or getattr(r, "annual_fee", None) or 0) or None}
                for r in satir
            ]
            ucretler = sorted(x["fee"] for x in rakipler if x["fee"])
            if ucretler:
                n = len(ucretler)
                medyan = (ucretler[n // 2] if n % 2
                          else (ucretler[n // 2 - 1] + ucretler[n // 2]) / 2)
        except Exception:  # noqa: BLE001
            logger.info("Rakip ucretleri alinamadi")

    deger = (bizim or {}).get("fee") if isinstance(bizim, dict) else bizim
    if deger is None and not rakipler:
        raise ToolExecutionError(
            "Bu kapsamda ücret kaydı bulunmuyor.", kind="metric_unavailable"
        )
    return TuitionOutput(
        scope_label=(payload.program or payload.department or payload.faculty
                     or "Üniversite geneli"),
        our_fee=float(deger) if deger is not None else None,
        currency="TRY",
        competitor_median=medyan,
        competitors=rakipler[:40],
        note="Rakip ücretleri yıllık öğrenim ücretidir.",
    )


registry.register(ToolDefinition(
    name="get_tuition_comparison",
    description=(
        "Kendi eğitim ücretimiz ve rakip üniversitelerin ücretleri. 'Ücretimiz "
        "pahalı mı', 'rakiplere göre fiyatımız', 'medyan ücret ne kadar' gibi "
        "sorularda kullanılır."
    ),
    input_model=TuitionInput,
    output_model=TuitionOutput,
    handler=_handle_tuition,
    timeout_seconds=25.0,
    required_permission="view_finance",
    data_source="Öğrenim ücreti ve rakip ücret kayıtları",
))


# ---------------------------------------------------------------------------
# 8. STRATEJİK KPI KARNESİ
# ---------------------------------------------------------------------------

class KpiInput(BaseModel):
    only_off_target: bool = Field(
        default=False, description="Yalnızca hedefin altındakiler listelensin mi."
    )


class KpiOutput(BaseModel):
    kpi_count: int = 0
    kpis: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_kpi(db: Session, payload: KpiInput) -> KpiOutput:
    from app.services import kpi_service as svc

    try:
        liste = svc.list_kpis(db)
    except TypeError:
        liste = svc.list_kpis(db=db)
    kayitlar = liste.get("items") if isinstance(liste, dict) else liste
    _bos_ise_hata(kayitlar, "Tanımlı stratejik KPI bulunmuyor.")

    cikti = []
    for k in kayitlar or []:
        d = k if isinstance(k, dict) else getattr(k, "__dict__", {})
        satir = {
            "name": d.get("name") or d.get("kpi_name"),
            "current_value": d.get("current_value") or d.get("value"),
            "target_value": d.get("target_value") or d.get("target"),
            "unit": d.get("unit"),
            "status": d.get("status") or d.get("direction_label"),
        }
        if payload.only_off_target:
            c, t = satir["current_value"], satir["target_value"]
            try:
                if c is not None and t is not None and float(c) >= float(t):
                    continue
            except (TypeError, ValueError):
                pass
        cikti.append(satir)
    return KpiOutput(kpi_count=len(cikti), kpis=cikti,
                     note="Stratejik plan göstergeleri.")


registry.register(ToolDefinition(
    name="get_strategic_kpis",
    description=(
        "Stratejik plan göstergeleri (KPI): mevcut değer, hedef ve durum. "
        "'Hedeflerimize ulaşıyor muyuz', 'hangi göstergeler geride', 'KPI "
        "karnesi' gibi sorularda kullanılır."
    ),
    input_model=KpiInput,
    output_model=KpiOutput,
    handler=_handle_kpi,
    timeout_seconds=20.0,
    required_permission=None,
    data_source="Stratejik KPI kayıtları",
))


# ---------------------------------------------------------------------------
# 9. ERKEN UYARILAR
# ---------------------------------------------------------------------------

class AlertInput(BaseModel):
    severity: Optional[str] = Field(
        default=None, description="critical | warning — boşsa hepsi."
    )


class AlertOutput(BaseModel):
    alert_count: int = 0
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_alerts(db: Session, payload: AlertInput) -> AlertOutput:
    from app.services import student_alert_service as svc

    try:
        sonuc = svc.build_alerts(db)
    except Exception as exc:  # noqa: BLE001
        raise ToolExecutionError(
            f"Erken uyarılar hesaplanamadı: {exc}", kind="error"
        ) from exc
    ham = getattr(sonuc, "alerts", None)
    if ham is None and isinstance(sonuc, dict):
        ham = sonuc.get("alerts")
    uyarilar = []
    for a in ham or []:
        if isinstance(a, dict):
            uyarilar.append(a)
        elif hasattr(a, "model_dump"):
            uyarilar.append(a.model_dump(mode="json"))
        else:
            uyarilar.append(dict(getattr(a, "__dict__", {})))

    if payload.severity:
        uyarilar = [a for a in uyarilar
                    if str(a.get("severity", "")).lower() == payload.severity.lower()]
    _bos_ise_hata(uyarilar, "Şu an tetiklenmiş erken uyarı bulunmuyor.")
    return AlertOutput(alert_count=len(uyarilar), alerts=uyarilar[:30],
                       note="Kural motoru tarafından üretilen uyarılar.")


registry.register(ToolDefinition(
    name="get_early_warnings",
    description=(
        "Erken uyarı sistemi tarafından tetiklenmiş riskler ve uyarılar. "
        "'Nelere dikkat etmeliyim', 'risk var mı', 'hangi programlar sorunlu' "
        "gibi sorularda kullanılır."
    ),
    input_model=AlertInput,
    output_model=AlertOutput,
    handler=_handle_alerts,
    timeout_seconds=25.0,
    required_permission=None,
    data_source="Erken uyarı kural motoru",
))


# ---------------------------------------------------------------------------
# 10. DERSLİK KULLANIMI (haftalık program)
# ---------------------------------------------------------------------------

class ClassroomUsageInput(BaseModel):
    day: Optional[str] = Field(
        default=None, description="Pazartesi…Cuma. Boşsa hafta geneli."
    )


class ClassroomUsageOutput(BaseModel):
    room_count: int = 0
    rooms_with_schedule: int = 0
    rooms_without_schedule: int = 0
    average_utilization_percent: Optional[float] = None
    busiest_floor: Optional[str] = None
    note: Optional[str] = None


def _handle_classroom_usage(
    db: Session, payload: ClassroomUsageInput
) -> ClassroomUsageOutput:
    from app.services import classroom_usage_service as svc

    veri = svc.classroom_usage_map() or {}
    if not veri.get("available"):
        raise ToolExecutionError(
            veri.get("note") or "Derslik kullanım veri kümesi üretilmemiş.",
            kind="metric_unavailable",
        )
    kapsam = veri.get("coverage") or {}
    odalar = veri.get("rooms") or []

    gun = payload.day
    dolu = toplam = 0
    kat: Dict[Any, List[int]] = {}
    for o in odalar:
        prog = o.get("schedule") or {}
        gunler = [gun] if gun else list(prog.keys())
        for g in gunler:
            slotlar = prog.get(g) or []
            dolu += sum(1 for s in slotlar if s)
            toplam += len(slotlar)
            k = kat.setdefault(o.get("floor"), [0, 0])
            k[0] += sum(1 for s in slotlar if s)
            k[1] += len(slotlar)

    enYogun = None
    if kat:
        enYogun = max(kat.items(), key=lambda kv: (kv[1][0] / kv[1][1]) if kv[1][1] else 0)
    return ClassroomUsageOutput(
        room_count=kapsam.get("rooms_total") or len(odalar),
        rooms_with_schedule=kapsam.get("rooms_with_schedule") or 0,
        rooms_without_schedule=kapsam.get("rooms_without_schedule") or 0,
        average_utilization_percent=round(dolu / toplam * 100, 1) if toplam else None,
        busiest_floor=f"Kat {enYogun[0]}" if enYogun else None,
        note=("Programı olmayan derslik doluluk hesabına KATILMAZ; "
              "sıfır sayılmaz."),
    )


registry.register(ToolDefinition(
    name="get_classroom_usage",
    description=(
        "Dersliklerin haftalık ders programına göre kullanım yoğunluğu. "
        "'Derslikler ne kadar dolu', 'hangi kat yoğun', 'boş derslik var mı' "
        "gibi sorularda kullanılır."
    ),
    input_model=ClassroomUsageInput,
    output_model=ClassroomUsageOutput,
    handler=_handle_classroom_usage,
    timeout_seconds=20.0,
    required_permission="view_physical_resources",
    data_source="Derslik ders programı (Excel) türevi",
))


# ---------------------------------------------------------------------------
# 12. MEKÂN ENVANTERİ  (kaç derslik / laboratuvar, ne kapasitede)
# ---------------------------------------------------------------------------
# Canlı testte "Kaç dersliğimiz var?" cevapsız kalıyordu. Mevcut
# `get_capacity_summary` aracı KULLANIM ve TAHSİS hesaplıyor; "kaç tane
# var" gibi düz bir envanter sorusuna uygun değil. Katalogdaki
# `classroom_count` metriği ise yalnızca belirli bir soru kalıbıyla
# eşleşiyordu ("Toplam derslik sayımız kaç?" tutuyor, "Kaç dersliğimiz
# var?" tutmuyordu). Sayının kendisi veritabanında duruyordu.

class FacilityInventoryInput(ScopeInput):
    facility_type: Optional[str] = Field(
        default=None,
        description="classroom | laboratory — boş bırakılırsa tüm türler.",
    )


class FacilityInventoryOutput(BaseModel):
    scope_label: str
    total_facilities: int = 0
    by_type: List[Dict[str, Any]] = Field(default_factory=list)
    total_seat_capacity: Optional[int] = None
    average_capacity: Optional[float] = None
    note: Optional[str] = None


def _handle_facility_inventory(
    db: Session, payload: FacilityInventoryInput
) -> FacilityInventoryOutput:
    from sqlalchemy import func

    from app.models import PhysicalFacility

    q = db.query(
        PhysicalFacility.facility_type.label("tur"),
        func.count(PhysicalFacility.id).label("adet"),
        func.sum(PhysicalFacility.capacity).label("kapasite"),
    )
    if payload.facility_type:
        q = q.where(PhysicalFacility.facility_type == payload.facility_type)
    satir = q.group_by(PhysicalFacility.facility_type).all()
    _bos_ise_hata(satir, "Mekân envanteri kaydı bulunmuyor.")

    kirilim = [
        {"facility_type": r.tur, "count": r.adet,
         "seat_capacity": int(r.kapasite) if r.kapasite is not None else None}
        for r in satir
    ]
    toplam = sum(x["count"] for x in kirilim)
    koltuk = sum(x["seat_capacity"] or 0 for x in kirilim) or None
    return FacilityInventoryOutput(
        scope_label=(payload.program or payload.department or payload.faculty
                     or "Üniversite geneli"),
        total_facilities=toplam,
        by_type=kirilim,
        total_seat_capacity=koltuk,
        average_capacity=round(koltuk / toplam, 1) if (koltuk and toplam) else None,
        note=("Kapasite EŞ ZAMANLI koltuk sayısıdır; haftalık koltuk-saat "
              "değildir. Kullanım oranı için `get_classroom_usage` kullanılır."),
    )


registry.register(ToolDefinition(
    name="get_facility_inventory",
    description=(
        "Mekân envanteri: kaç derslik, kaç laboratuvar var ve toplam koltuk "
        "kapasiteleri ne. 'Kaç dersliğimiz var', 'kaç laboratuvarımız var', "
        "'toplam kapasitemiz ne kadar', 'ortalama derslik büyüklüğü' gibi "
        "SAYIM sorularında kullanılır. Kullanım/doluluk için bu araç değil "
        "`get_classroom_usage` kullanılır."
    ),
    input_model=FacilityInventoryInput,
    output_model=FacilityInventoryOutput,
    handler=_handle_facility_inventory,
    timeout_seconds=15.0,
    required_permission="view_physical_resources",
    data_source="Fiziksel mekân envanteri",
))


# ---------------------------------------------------------------------------
# 11. SIRALAMA / DEĞERLENDİRME HAZIRLIĞI
# ---------------------------------------------------------------------------

class RankingInput(BaseModel):
    framework: Optional[str] = Field(
        default=None, description="Değerlendirme çerçevesi adı. Boşsa hepsi."
    )


class RankingOutput(BaseModel):
    framework_count: int = 0
    frameworks: List[Dict[str, Any]] = Field(default_factory=list)
    dimensions: List[Dict[str, Any]] = Field(default_factory=list)
    note: Optional[str] = None


def _handle_ranking(db: Session, payload: RankingInput) -> RankingOutput:
    from app.models.evaluation_framework import EvaluationFramework
    from app.models.evaluation_dimension import EvaluationDimension

    cerceveler = db.query(EvaluationFramework).all()
    _bos_ise_hata(cerceveler, "Tanımlı değerlendirme çerçevesi bulunmuyor.")
    boyutlar = db.query(EvaluationDimension).all()

    ad = lambda x: getattr(x, "name", None) or getattr(x, "code", "?")
    return RankingOutput(
        framework_count=len(cerceveler),
        frameworks=[{"name": ad(c), "description": getattr(c, "description", None)}
                    for c in cerceveler],
        dimensions=[{"name": ad(b), "weight": getattr(b, "weight", None),
                     "framework_id": getattr(b, "framework_id", None)}
                    for b in boyutlar],
        note="Sıralama hazırlık çerçeveleri ve boyut ağırlıkları.",
    )


registry.register(ToolDefinition(
    name="get_ranking_frameworks",
    description=(
        "Üniversite sıralama/değerlendirme çerçeveleri ve boyutları "
        "(ağırlıklar, göstergeler). 'Sıralamaya hazır mıyız', 'hangi "
        "kriterlerde zayıfız', 'değerlendirme boyutları' gibi sorularda "
        "kullanılır."
    ),
    input_model=RankingInput,
    output_model=RankingOutput,
    handler=_handle_ranking,
    timeout_seconds=20.0,
    required_permission=None,
    data_source="Sıralama değerlendirme çerçeveleri",
))
