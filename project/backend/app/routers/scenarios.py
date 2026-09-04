"""What-if senaryo analizi endpoint'leri.

Bu router hesap yapmaz. İsteği alır, aktif baseline'ı bulur, hesaplama motorunu
ve risk/öneri servislerini çağırır, sonucu kaydeder ve cevabı döndürür.

NOT: Yol tanımlarının sırası önemlidir. "/baselines" gibi sabit yollar,
"/{scenario_id}" gibi parametreli yollardan ÖNCE tanımlanmalıdır; aksi halde
FastAPI "baselines" kelimesini scenario_id sanıp 422 döndürür.
"""

from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Scenario,
    ScenarioBaseline,
    ScenarioInput,
    ScenarioResult,
    Student,
)
from app.schemas.student_analytics import StudentDataSyncResponse
from app.schemas.scenarios import (
    MetricComparisonResponse,
    ScenarioComparisonReport,
    FinancialBreakdown,
    RiskItem,
    RiskLevel,
    ScenarioBaselineCreate,
    ScenarioBaselineResponse,
    ScenarioBaselineUpdate,
    ScenarioCreate,
    ScenarioInputCreate,
    ScenarioInputResponse,
    ScenarioResponse,
    ScenarioResultResponse,
    ScenarioStatus,
    ScenarioType,
    ScenarioUpdate,
    SimulationMetrics,
    SimulationResponse,
)
from app.services.crud_helpers import apply_updates, get_object_or_404
from app.services.scenario_baseline_builder import (
    available_periods,
    build_from_financial_period,
)
from app.services.scenario_engine import (
    build_comparison,
    ScenarioComputation,
    ScenarioValidationError,
    calculate,
)
from app.services.scenario_recommendations import build_recommendation
from app.services.scenario_risk import evaluate

router = APIRouter(prefix="/api/scenarios", tags=["Scenario Analysis"])

BASELINE_LABEL: str = "Baseline"
SCENARIO_LABEL: str = "Senaryo"


# ===========================================================================
# Yardımcı fonksiyonlar
# ===========================================================================


def _get_active_baseline(db: Session) -> ScenarioBaseline:
    """Sistemdeki aktif baseline'ı getirir, yoksa 409 döndürür."""
    # 409 Conflict seçildi: istek biçimsel olarak doğru ama sistemin mevcut
    # durumu (aktif baseline yok) işlemi yapmaya elverişli değil.
    statement = select(ScenarioBaseline).where(ScenarioBaseline.is_active.is_(True))
    baseline: Optional[ScenarioBaseline] = db.execute(statement).scalars().first()

    if baseline is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Sistemde aktif bir baseline bulunmuyor. Simülasyon yapabilmek için "
                "önce POST /api/scenarios/baselines ile bir baseline oluşturun."
            ),
        )
    return baseline


def _deactivate_other_baselines(db: Session, keep_id: Optional[int] = None) -> None:
    """Aktif baseline'ları pasifleştirir; sistemde tek aktif kayıt kalmasını sağlar."""
    # Kural: "yalnızca bir aktif baseline". Yeni bir kayıt aktif yapıldığında
    # eskisini otomatik pasifleştirerek kullanıcıyı manuel işlemden kurtarıyoruz.
    statement = select(ScenarioBaseline).where(ScenarioBaseline.is_active.is_(True))
    for existing in db.execute(statement).scalars().all():
        if keep_id is None or existing.id != keep_id:
            existing.is_active = False


def _count_live_active_students(db: Session) -> int:
    """Modül 2'deki aktif öğrenci sayısını döndürür."""
    # "Aktif öğrenci" = kaydı silinmemiş (is_active) ve hâlâ öğrenim gören
    # (active veya newly-enrolled) öğrenciler. Mezun ve ayrılanlar dahil edilmez.
    statement = (
        select(func.count(Student.id))
        .where(Student.is_active.is_(True))
        .where(Student.current_status.in_(["active", "newly-enrolled"]))
    )
    return int(db.execute(statement).scalar() or 0)


def _run_simulation(
    baseline: ScenarioBaseline,
    payload: ScenarioInputCreate,
    student_count_override: Optional[int] = None,
) -> Tuple[ScenarioComputation, List[RiskItem], RiskLevel, str]:
    """Hesaplama, risk tespiti ve öneri üretimini sırayla çalıştırır."""
    try:
        computation: ScenarioComputation = calculate(
            baseline, payload, student_count_override=student_count_override
        )
    except ScenarioValidationError as error:
        # Baseline'a bağlı doğrulama hatası: şema katmanı yakalayamadığı için burada 422'ye çeviriyoruz.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["body", error.field], "msg": error.message, "type": "value_error"}],
        ) from error

    risks, risk_level = evaluate(computation)
    recommendation: str = build_recommendation(computation, risks, risk_level)
    return computation, risks, risk_level, recommendation


def _build_comparison_report(computation: ScenarioComputation) -> ScenarioComparisonReport:
    """Hesaplama sonucunu API'nin karşılaştırma bloğuna dönüştürür.

    Fark ve yüzde hesabı servis katmanında yapılır; burada yalnızca şemaya
    çevriliyor. Arayüz kendi farkını hesaplamaz.
    """
    report = build_comparison(computation)
    to_schema = lambda m: MetricComparisonResponse(
        key=m.key, label=m.label, unit=m.unit,
        baseline_value=m.baseline_value, projected_value=m.projected_value,
        absolute_change=m.absolute_change, percent_change=m.percent_change,
        direction=m.direction, is_favorable=m.is_favorable,
        group=m.group, description=m.description,
    )
    return ScenarioComparisonReport(
        currency="USD",
        financial=[to_schema(m) for m in report.financial],
        academic=[to_schema(m) for m in report.academic],
        capacity=[to_schema(m) for m in report.capacity],
        most_significant=[to_schema(m) for m in report.most_significant(5)],
    )


def _build_metrics(computation: ScenarioComputation) -> SimulationMetrics:
    """Hesaplama sonucunu API cevabındaki metrik bloğuna dönüştürür."""
    return SimulationMetrics(
        baseline_student_count=computation.baseline_student_count,
        projected_student_count=computation.projected_student_count,
        baseline_revenue=computation.baseline_revenue,
        projected_revenue=computation.projected_revenue,
        baseline_expenditure=computation.baseline_expenditure,
        projected_expenditure=computation.projected_expenditure,
        baseline_staff_count=computation.baseline_staff_count,
        projected_staff_count=computation.projected_staff_count,
        baseline_student_staff_ratio=computation.baseline_student_staff_ratio,
        projected_student_staff_ratio=computation.projected_student_staff_ratio,
        baseline_cost_per_student=computation.baseline_cost_per_student,
        projected_cost_per_student=computation.projected_cost_per_student,
        baseline_classroom_capacity=computation.baseline_classroom_capacity,
        projected_classroom_capacity=computation.projected_classroom_capacity,
        baseline_laboratory_capacity=computation.baseline_laboratory_capacity,
        projected_laboratory_capacity=computation.projected_laboratory_capacity,
        classroom_capacity_status=computation.classroom_capacity_status,
        laboratory_capacity_status=computation.laboratory_capacity_status,
    )


def _resolve_student_source(
    db: Session, use_live_student_data: bool
) -> Tuple[Optional[int], str, Optional[int]]:
    """Öğrenci sayısının kaynağını belirler.

    Dönüş: (hesaplamada kullanılacak override, kaynak etiketi, canlı aktif öğrenci sayısı).
    """
    # Varsayılan davranış korunuyor: parametre gönderilmezse baseline kullanılır,
    # yani Modül 9'un mevcut sonuçları hiç değişmez.
    if not use_live_student_data:
        return None, "baseline", None

    live_count: int = _count_live_active_students(db)
    return live_count, "live-student-module", live_count


def _build_breakdown(computation: ScenarioComputation) -> FinancialBreakdown:
    """Gelir/gider kalemlerinin dökümünü hazırlar."""
    return FinancialBreakdown(
        projected_tuition_revenue=computation.projected_tuition_revenue,
        projected_research_revenue=computation.projected_research_revenue,
        projected_other_revenue=computation.projected_other_revenue,
        projected_personnel_expense=computation.projected_personnel_expense,
        projected_education_expense=computation.projected_education_expense,
        projected_rd_expense=computation.projected_rd_expense,
        projected_building_energy_expense=computation.projected_building_energy_expense,
        projected_technology_expense=computation.projected_technology_expense,
        effective_scholarship_rate_percent=computation.effective_scholarship_rate_percent,
        scholarship_deduction=computation.scholarship_deduction,
        baseline_balance=computation.baseline_balance,
        projected_balance=computation.projected_balance,
    )


# ===========================================================================
# BASELINE ENDPOINT'LERİ  (parametreli yollardan önce tanımlanmalı)
# ===========================================================================


@router.post(
    "/baselines",
    response_model=ScenarioBaselineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni baseline oluştur",
)
def create_baseline(
    payload: ScenarioBaselineCreate,
    db: Session = Depends(get_db),
) -> ScenarioBaseline:
    """Yeni bir baseline kaydı oluşturur; aktif işaretlenirse diğerlerini pasifleştirir."""
    if payload.is_active:
        _deactivate_other_baselines(db)

    baseline = ScenarioBaseline(**payload.model_dump())
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return baseline


@router.post(
    "/baselines/sync-student-data",
    response_model=StudentDataSyncResponse,
    summary="Aktif baseline'ın öğrenci sayısını Modül 2 verisiyle güncelle",
)
def sync_student_data(db: Session = Depends(get_db)) -> StudentDataSyncResponse:
    """Aktif baseline'daki student_count alanını canlı aktif öğrenci sayısıyla günceller."""
    # Yalnızca öğrenci sayısı senkronize edilir. Derslik/laboratuvar kapasitesi
    # program snapshot verilerinden türetilmeye ÇALIŞILMAZ; çünkü snapshot'lar
    # kontenjan bilgisidir, fiziksel kapasite değildir. Bu iki kavramı karıştırmak
    # yanlış kapasite riskleri üretirdi.
    baseline: ScenarioBaseline = _get_active_baseline(db)

    previous_count: int = baseline.student_count
    new_count: int = _count_live_active_students(db)

    baseline.student_count = new_count
    db.commit()
    db.refresh(baseline)

    difference: int = new_count - previous_count
    return StudentDataSyncResponse(
        baseline_id=baseline.id,
        baseline_name=baseline.name,
        previous_student_count=previous_count,
        new_student_count=new_count,
        difference=difference,
        message=(
            f"Aktif baseline'ın öğrenci sayısı {previous_count} değerinden {new_count} "
            f"değerine güncellendi (fark: {difference:+d})."
        ),
    )


@router.get(
    "/baselines",
    response_model=List[ScenarioBaselineResponse],
    summary="Baseline'ları listele",
)
def list_baselines(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[ScenarioBaseline]:
    """Kayıtlı baseline'ları listeler."""
    statement = select(ScenarioBaseline)
    if is_active is not None:
        statement = statement.where(ScenarioBaseline.is_active.is_(is_active))

    statement = statement.order_by(ScenarioBaseline.id.desc()).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get(
    "/baselines/active",
    response_model=ScenarioBaselineResponse,
    summary="Aktif baseline'ı getir",
)
def get_active_baseline(db: Session = Depends(get_db)) -> ScenarioBaseline:
    """Simülasyonlarda kullanılan aktif baseline'ı döndürür."""
    return _get_active_baseline(db)


@router.get(
    "/baselines/{baseline_id}",
    response_model=ScenarioBaselineResponse,
    summary="Baseline detayı",
)
def get_baseline(baseline_id: int, db: Session = Depends(get_db)) -> ScenarioBaseline:
    """Tek bir baseline kaydını id ile getirir."""
    return get_object_or_404(db, ScenarioBaseline, baseline_id, BASELINE_LABEL)


@router.put(
    "/baselines/{baseline_id}",
    response_model=ScenarioBaselineResponse,
    summary="Baseline güncelle",
)
def update_baseline(
    baseline_id: int,
    payload: ScenarioBaselineUpdate,
    db: Session = Depends(get_db),
) -> ScenarioBaseline:
    """Var olan bir baseline'ı kısmi olarak günceller."""
    baseline = get_object_or_404(db, ScenarioBaseline, baseline_id, BASELINE_LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    # Bu kayıt aktif yapılıyorsa diğer aktif kayıtlar pasifleştirilir.
    if update_data.get("is_active") is True:
        _deactivate_other_baselines(db, keep_id=baseline_id)

    apply_updates(baseline, update_data)
    db.commit()
    db.refresh(baseline)
    return baseline


@router.delete(
    "/baselines/{baseline_id}",
    response_model=ScenarioBaselineResponse,
    summary="Baseline'ı pasifleştir",
)
def deactivate_baseline(baseline_id: int, db: Session = Depends(get_db)) -> ScenarioBaseline:
    """Baseline'ı silmez, is_active=False yaparak pasifleştirir."""
    # Geçmiş simülasyon sonuçları bu baseline'a dayandığı için fiziksel silme yapılmıyor.
    baseline = get_object_or_404(db, ScenarioBaseline, baseline_id, BASELINE_LABEL)
    baseline.is_active = False
    db.commit()
    db.refresh(baseline)
    return baseline


# ===========================================================================
# ÖN İZLEME (kayıt oluşturmayan tek seferlik simülasyon)
# ===========================================================================


@router.post(
    "/preview",
    response_model=SimulationResponse,
    summary="Kayıt oluşturmadan hızlı simülasyon",
)
def preview_simulation(
    payload: ScenarioInputCreate,
    financial_period: Optional[str] = Query(
        default=None,
        description=(
            "Senaryo tabanının alınacağı mali dönem (örn. 2024-2025). Verilirse o dönemin "
            "GERÇEK gelir/gider verisinden taban üretilir. Boş bırakılırsa kayıtlı aktif "
            "baseline kullanılır. Seçilebilecek dönemler: GET /api/scenarios/financial-periods"
        ),
        examples=["2025-2026"],
    ),
    use_live_student_data: bool = Query(
        default=False,
        description=(
            "true ise başlangıç öğrenci sayısı canlı öğrenci verisinden alınır. "
            "Varsayılan false: seçilen tabanın öğrenci sayısı kullanılır."
        ),
    ),
    db: Session = Depends(get_db),
) -> SimulationResponse:
    """Hesaplama yapar ama veritabanına hiçbir kayıt yazmaz.

    Mali dönem seçilirse taban o dönemin gerçek verisinden üretilir; böylece
    senaryo ekranındaki rakamlar mali analiz ekranıyla birebir aynı olur.
    """
    # Yönetici farklı değerleri hızlıca deneyip veritabanını kalabalıklaştırmasın diye eklendi.
    if financial_period:
        baseline: ScenarioBaseline = build_from_financial_period(db, financial_period)
    else:
        baseline = _get_active_baseline(db)
    override, source, live_count = _resolve_student_source(db, use_live_student_data)
    computation, risks, risk_level, recommendation = _run_simulation(
        baseline, payload, student_count_override=override
    )

    return SimulationResponse(
        scenario_id=None,
        scenario_name=None,
        scenario_type=None,
        # Mali dönemden türetilen taban veritabanına yazılmadığı için id'si yoktur.
        baseline_id=baseline.id or 0,
        baseline_name=baseline.name,
        preview=True,
        inputs=payload,
        result=_build_metrics(computation),
        breakdown=_build_breakdown(computation),
        comparison=_build_comparison_report(computation),
        risks=risks,
        risk_level=risk_level,
        recommendation=recommendation,
        result_id=None,
        calculated_at=datetime.now(),
        student_data_source=source,
        live_active_student_count=live_count,
    )


# ===========================================================================
# SENARYO KATALOĞU VE MALİ DÖNEM SEÇİMİ
# ===========================================================================


@router.get(
    "/catalog",
    summary="Desteklenen senaryo türleri ve parametreleri",
)
def get_scenario_catalog() -> List[dict]:
    """Arayüzün senaryo formunu oluşturmak için kullandığı katalog.

    Alan adları ve sınırlar arayüzde elle yazılırsa, backend şeması
    değiştiğinde sessizce uyumsuz hale gelir. Nitekim önceki sürümde tam
    olarak bu olmuş, arayüz "staff_count_change" gönderirken backend
    "academic_staff_change" beklemiş ve hiçbir parametre uygulanmamıştı.
    Katalog sunucudan geldiği için bu uyumsuzluk artık mümkün değil.
    """
    return [
        {
            "key": "academic-staffing",
            "label": "Akademik personel maaşlarına zam",
            "question": "Akademik personel maaşlarına %2 zam yapılırsa ne olur?",
            "description": (
                "Personel sayısı sabit kalır, ortalama maaş değişir. Toplam personel "
                "gideri, bütçe dengesi ve öğrenci başına maliyet yeniden hesaplanır."
            ),
            "fields": [
                {"name": "academic_salary_change_percent", "label": "Akademik maaş değişimi",
                 "unit": "%", "default": 2, "min": -100, "max": 1000, "step": 0.5},
            ],
        },
        {
            "key": "academic-staffing-headcount",
            "label": "Akademik personel sayısı değişikliği",
            "question": "10 yeni öğretim üyesi alınırsa bütçe nasıl etkilenir?",
            "description": (
                "Kadro sayısı değişir, ortalama maaş sabit kalır. Öğrenci/öğretim üyesi "
                "oranı ve personel gideri yeniden hesaplanır."
            ),
            "fields": [
                {"name": "academic_staff_change", "label": "Akademik personel değişimi",
                 "unit": "kişi", "default": 10, "min": -5000, "max": 5000, "step": 1},
                {"name": "administrative_staff_change", "label": "İdari personel değişimi",
                 "unit": "kişi", "default": 0, "min": -5000, "max": 5000, "step": 1},
            ],
        },
        {
            "key": "student-enrollment",
            "label": "Öğrenci sayısı değişikliği",
            "question": "Öğrenci sayısı %10 artarsa gelir ve kapasite nasıl etkilenir?",
            "description": (
                "Öğrenci sayısı doğrudan değişir. Öğrenim ücreti geliri, eğitim gideri, "
                "öğrenci başına maliyet ve kapasite talebi yeniden hesaplanır."
            ),
            "fields": [
                {"name": "student_change_percent", "label": "Öğrenci sayısı değişimi",
                 "unit": "%", "default": 10, "min": -100, "max": 1000, "step": 1},
            ],
        },
        {
            "key": "quota-change",
            "label": "Kontenjan değişikliği",
            "question": "Kontenjanlar %15 artırılırsa ne olur?",
            "description": (
                "Kontenjan artışının tamamı öğrenciye dönüşmez; mevcut doluluk esnekliği "
                "(0,85) kadarı yerleşir. Boş kontenjan gelir üretmez."
            ),
            "fields": [
                {"name": "quota_change_percent", "label": "Kontenjan değişimi",
                 "unit": "%", "default": 15, "min": -100, "max": 1000, "step": 1},
            ],
        },
        {
            "key": "tuition-scholarship",
            "label": "Öğrenim ücreti değişikliği",
            "question": "Öğrenim ücreti %10 artarsa gelir ne kadar artar?",
            "description": (
                "Brüt öğrenim ücreti geliri değişir; burs indirimi yeni brüt tutar "
                "üzerinden hesaplanır."
            ),
            "fields": [
                {"name": "tuition_change_percent", "label": "Öğrenim ücreti değişimi",
                 "unit": "%", "default": 10, "min": -100, "max": 1000, "step": 1},
            ],
        },
        {
            "key": "scholarship-policy",
            "label": "Burs oranı değişikliği",
            "question": "Burs oranı 5 puan artırılırsa gelire etkisi ne olur?",
            "description": (
                "Mevcut burs oranına YÜZDE PUANI eklenir (%38 + 5 puan = %43). "
                "Sonuç %0-%100 aralığı dışına çıkarsa istek reddedilir."
            ),
            "fields": [
                {"name": "scholarship_change_percent", "label": "Burs oranı değişimi",
                 "unit": "puan", "default": 5, "min": -100, "max": 100, "step": 0.5},
            ],
        },
        {
            "key": "investment",
            "label": "Derslik / laboratuvar kapasitesi değişikliği",
            "question": "300 kişilik ek derslik kapasitesi yeterli olur mu?",
            "description": (
                "Kapasite yeterliliği eş zamanlı kullanım katsayısıyla değerlendirilir: "
                "öğrencilerin %35'i aynı anda derslikte, %18'i laboratuvarda kabul edilir."
            ),
            "fields": [
                {"name": "classroom_capacity_change", "label": "Derslik kapasitesi değişimi",
                 "unit": "kişi", "default": 300, "min": -100000, "max": 100000, "step": 10},
                {"name": "laboratory_capacity_change", "label": "Laboratuvar kapasitesi değişimi",
                 "unit": "kişi", "default": 50, "min": -100000, "max": 100000, "step": 10},
            ],
        },
        {
            "key": "revenue-item",
            "label": "Gelir kaleminde değişiklik",
            "question": "Sanayi iş birliği geliri %20 artarsa bütçe dengesi ne olur?",
            "description": "Seçilen tek bir gelir kaleminde yüzdesel değişiklik uygulanır.",
            "fields": [
                {"name": "target_revenue_category", "label": "Gelir kalemi",
                 "unit": "", "type": "revenue_category", "default": ""},
                {"name": "revenue_item_change_percent", "label": "Değişim",
                 "unit": "%", "default": 20, "min": -100, "max": 1000, "step": 1},
            ],
        },
        {
            "key": "expense-item",
            "label": "Gider kaleminde değişiklik",
            "question": "Enerji giderini %15 düşürürsek ne kazanırız?",
            "description": "Seçilen tek bir gider kaleminde yüzdesel değişiklik uygulanır.",
            "fields": [
                {"name": "target_expense_category", "label": "Gider kalemi",
                 "unit": "", "type": "expense_category", "default": ""},
                {"name": "expense_item_change_percent", "label": "Değişim",
                 "unit": "%", "default": -15, "min": -100, "max": 1000, "step": 1},
            ],
        },
        {
            "key": "economic-risk",
            "label": "Ekonomik risk (enflasyon ve kur)",
            "question": "Enflasyon %30, kur %20 artarsa giderler nereye gider?",
            "description": (
                "Enflasyon eğitim, Ar-Ge, bina-enerji ve teknoloji giderlerini; kur ise "
                "ağırlıklı olarak ithal teknoloji giderini etkiler."
            ),
            "fields": [
                {"name": "inflation_percent", "label": "Enflasyon",
                 "unit": "%", "default": 30, "min": -100, "max": 1000, "step": 1},
                {"name": "exchange_rate_change_percent", "label": "Kur değişimi",
                 "unit": "%", "default": 20, "min": -100, "max": 1000, "step": 1},
            ],
        },
        {
            "key": "research-strategy",
            "label": "Araştırma fonu değişikliği",
            "question": "Araştırma fonları %25 artarsa Ar-Ge gideri ne olur?",
            "description": "Araştırma geliri ve buna bağlı Ar-Ge gideri birlikte değişir.",
            "fields": [
                {"name": "research_funding_change_percent", "label": "Araştırma fonu değişimi",
                 "unit": "%", "default": 25, "min": -100, "max": 1000, "step": 1},
            ],
        },
    ]


@router.get(
    "/financial-periods",
    summary="Senaryo tabanı olarak seçilebilecek mali dönemler",
)
def get_scenario_financial_periods(db: Session = Depends(get_db)) -> dict:
    """Gerçekleşen verisi olan mali dönemleri listeler.

    Kalemi olmayan veya öğrenci sayısı sıfır olan planlama yılları listelenmez;
    seçilseler sıfır tabanlı anlamsız bir senaryo üretirlerdi.
    """
    periods = available_periods(db)
    return {
        "periods": periods,
        "default": periods[-1] if periods else None,
        "note": (
            "Bir dönem seçildiğinde senaryo tabanı o dönemin gerçekleşen gelir/gider "
            "verisinden üretilir; böylece senaryo sonuçları mali analiz ekranıyla birebir uyumludur."
        ),
    }


@router.get(
    "/financial-categories",
    summary="Senaryoda hedeflenebilecek gelir ve gider kalemleri",
)
def get_scenario_financial_categories(
    academic_year: Optional[str] = Query(default=None, examples=["2025-2026"]),
    db: Session = Depends(get_db),
) -> dict:
    """Kalem bazlı senaryolarda seçilebilecek kalem adlarını döndürür."""
    from app.models import FinancialEntry, FinancialPeriod

    query = select(FinancialEntry.kind, FinancialEntry.category).distinct()
    if academic_year:
        query = query.join(
            FinancialPeriod, FinancialPeriod.id == FinancialEntry.financial_period_id
        ).where(FinancialPeriod.academic_year == academic_year)

    revenue, expenditure = [], []
    for kind, category in db.execute(query):
        (revenue if kind == "revenue" else expenditure).append(category)
    return {
        "revenue_categories": sorted(set(revenue)),
        "expenditure_categories": sorted(set(expenditure)),
    }


# ===========================================================================
# SENARYO CRUD
# ===========================================================================


@router.post("", response_model=ScenarioResponse, status_code=status.HTTP_201_CREATED)
def create_scenario(payload: ScenarioCreate, db: Session = Depends(get_db)) -> Scenario:
    """Yeni bir senaryo kaydı oluşturur."""
    scenario = Scenario(
        name=payload.name,
        description=payload.description,
        scenario_type=payload.scenario_type.value,
        status=payload.status.value,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.get("", response_model=List[ScenarioResponse])
def list_scenarios(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    scenario_type: Optional[ScenarioType] = Query(default=None),
    scenario_status: Optional[ScenarioStatus] = Query(
        default=None, alias="status", description="draft | simulated | archived"
    ),
    db: Session = Depends(get_db),
) -> List[Scenario]:
    """Senaryoları listeler; tür ve duruma göre filtrelenebilir."""
    statement = select(Scenario)
    if scenario_type is not None:
        statement = statement.where(Scenario.scenario_type == scenario_type.value)
    if scenario_status is not None:
        statement = statement.where(Scenario.status == scenario_status.value)

    statement = statement.order_by(Scenario.id.desc()).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


@router.get("/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(scenario_id: int, db: Session = Depends(get_db)) -> Scenario:
    """Tek bir senaryoyu id ile getirir."""
    return get_object_or_404(db, Scenario, scenario_id, SCENARIO_LABEL)


@router.put("/{scenario_id}", response_model=ScenarioResponse)
def update_scenario(
    scenario_id: int,
    payload: ScenarioUpdate,
    db: Session = Depends(get_db),
) -> Scenario:
    """Var olan bir senaryoyu kısmi olarak günceller."""
    scenario = get_object_or_404(db, Scenario, scenario_id, SCENARIO_LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    # Enum alanları veritabanına metin olarak yazılır.
    if "scenario_type" in update_data and update_data["scenario_type"] is not None:
        update_data["scenario_type"] = update_data["scenario_type"].value
    if "status" in update_data and update_data["status"] is not None:
        update_data["status"] = update_data["status"].value

    apply_updates(scenario, update_data)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.delete("/{scenario_id}", response_model=ScenarioResponse)
def archive_scenario(scenario_id: int, db: Session = Depends(get_db)) -> Scenario:
    """Senaryoyu silmez, status='archived' yaparak arşivler."""
    # Diğer modüllerdeki soft delete yaklaşımıyla tutarlı olmak için
    # senaryo kaydı ve geçmiş sonuçları korunuyor.
    scenario = get_object_or_404(db, Scenario, scenario_id, SCENARIO_LABEL)
    scenario.status = ScenarioStatus.ARCHIVED.value
    db.commit()
    db.refresh(scenario)
    return scenario


# ===========================================================================
# SİMÜLASYON VE SONUÇLAR
# ===========================================================================


@router.post(
    "/{scenario_id}/simulate",
    response_model=SimulationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Senaryoyu çalıştır ve sonucu kaydet",
)
def simulate_scenario(
    scenario_id: int,
    payload: ScenarioInputCreate,
    use_live_student_data: bool = Query(
        default=False,
        description=(
            "true ise başlangıç öğrenci sayısı Modül 2'deki aktif öğrenci sayısından alınır. "
            "Varsayılan false: baseline.student_count kullanılır."
        ),
    ),
    db: Session = Depends(get_db),
) -> SimulationResponse:
    """Senaryoyu aktif baseline ile hesaplar; girdi ve sonucu veritabanına yazar."""
    scenario = get_object_or_404(db, Scenario, scenario_id, SCENARIO_LABEL)
    baseline: ScenarioBaseline = _get_active_baseline(db)

    override, source, live_count = _resolve_student_source(db, use_live_student_data)
    computation, risks, risk_level, recommendation = _run_simulation(
        baseline, payload, student_count_override=override
    )

    # Girdi kaydı: hangi varsayımlarla hesaplandığı sonradan görülebilsin diye saklanıyor.
    scenario_input = ScenarioInput(scenario_id=scenario.id, **payload.model_dump())
    db.add(scenario_input)

    scenario_result = ScenarioResult(
        scenario_id=scenario.id,
        baseline_student_count=computation.baseline_student_count,
        projected_student_count=computation.projected_student_count,
        baseline_revenue=computation.baseline_revenue,
        projected_revenue=computation.projected_revenue,
        baseline_expenditure=computation.baseline_expenditure,
        projected_expenditure=computation.projected_expenditure,
        baseline_staff_count=computation.baseline_staff_count,
        projected_staff_count=computation.projected_staff_count,
        baseline_student_staff_ratio=computation.baseline_student_staff_ratio,
        projected_student_staff_ratio=computation.projected_student_staff_ratio,
        baseline_cost_per_student=computation.baseline_cost_per_student,
        projected_cost_per_student=computation.projected_cost_per_student,
        baseline_classroom_capacity=computation.baseline_classroom_capacity,
        projected_classroom_capacity=computation.projected_classroom_capacity,
        baseline_laboratory_capacity=computation.baseline_laboratory_capacity,
        projected_laboratory_capacity=computation.projected_laboratory_capacity,
        classroom_capacity_status=computation.classroom_capacity_status.value,
        laboratory_capacity_status=computation.laboratory_capacity_status.value,
        risk_level=risk_level.value,
        recommendation=recommendation,
    )
    db.add(scenario_result)

    # Senaryo en az bir kez çalıştırıldığı için durumu güncelleniyor.
    if scenario.status == ScenarioStatus.DRAFT.value:
        scenario.status = ScenarioStatus.SIMULATED.value

    # Girdi ve sonuç birlikte anlamlı olduğu için tek commit ile yazılıyor;
    # biri yazılıp diğeri yazılamazsa ikisi de geri alınır.
    db.commit()
    db.refresh(scenario_result)

    return SimulationResponse(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        scenario_type=scenario.scenario_type,
        baseline_id=baseline.id,
        baseline_name=baseline.name,
        preview=False,
        inputs=payload,
        result=_build_metrics(computation),
        breakdown=_build_breakdown(computation),
        comparison=_build_comparison_report(computation),
        risks=risks,
        risk_level=risk_level,
        recommendation=recommendation,
        result_id=scenario_result.id,
        calculated_at=scenario_result.calculated_at,
        student_data_source=source,
        live_active_student_count=live_count,
    )


@router.get(
    "/{scenario_id}/results",
    response_model=List[ScenarioResultResponse],
    summary="Senaryonun geçmiş sonuçları",
)
def list_scenario_results(
    scenario_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[ScenarioResult]:
    """Bir senaryonun tüm simülasyon sonuçlarını en yeniden eskiye listeler."""
    # Senaryonun varlığını önce kontrol ediyoruz ki olmayan id için boş liste yerine 404 dönsün.
    get_object_or_404(db, Scenario, scenario_id, SCENARIO_LABEL)

    statement = (
        select(ScenarioResult)
        .where(ScenarioResult.scenario_id == scenario_id)
        .order_by(ScenarioResult.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


@router.get(
    "/{scenario_id}/results/latest",
    response_model=ScenarioResultResponse,
    summary="Senaryonun en son sonucu",
)
def get_latest_scenario_result(
    scenario_id: int,
    db: Session = Depends(get_db),
) -> ScenarioResult:
    """Senaryonun en son hesaplanan sonucunu döndürür."""
    get_object_or_404(db, Scenario, scenario_id, SCENARIO_LABEL)

    statement = (
        select(ScenarioResult)
        .where(ScenarioResult.scenario_id == scenario_id)
        .order_by(ScenarioResult.id.desc())
        .limit(1)
    )
    result: Optional[ScenarioResult] = db.execute(statement).scalars().first()

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bu senaryo için henüz bir simülasyon sonucu yok (scenario_id={scenario_id}).",
        )
    return result


@router.get(
    "/{scenario_id}/inputs",
    response_model=List[ScenarioInputResponse],
    summary="Senaryonun geçmiş girdileri",
)
def list_scenario_inputs(
    scenario_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[ScenarioInput]:
    """Bir senaryoda kullanılmış girdi parametrelerini listeler."""
    get_object_or_404(db, Scenario, scenario_id, SCENARIO_LABEL)

    statement = (
        select(ScenarioInput)
        .where(ScenarioInput.scenario_id == scenario_id)
        .order_by(ScenarioInput.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())
