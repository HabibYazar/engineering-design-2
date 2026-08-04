"""THE / QS / YÖK değerlendirme ve izleme endpoint'leri (Modül 10).

UYARI: Bu modül gerçek THE/QS/YÖK sıralaması ÜRETMEZ. Skorlar kurumun kendi
verisine dayanan iç performans izleme, veri hazırlık ve uyum göstergeleridir.

Router hesap yapmaz; tüm hesaplamalar app/services altındaki ranking_* servislerindedir.

NOT: Sabit yollar ("/frameworks", "/assessments/calculate" vb.) parametreli
yollardan ÖNCE tanımlanmıştır; aksi halde FastAPI sabit kelimeyi id sanardı.
"""

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    BenchmarkInstitution,
    BenchmarkMetricValue,
    DimensionAssessment,
    EvaluationDimension,
    EvaluationFramework,
    EvaluationIndicator,
    FrameworkAssessment,
    InstitutionalMetricValue,
)
from app.schemas.ranking_evaluations import (
    AssessmentCalculateRequest,
    AssessmentCalculateResponse,
    AssessmentDetailResponse,
    AssessmentResponse,
    BenchmarkComparisonResponse,
    BenchmarkInstitutionCreate,
    BenchmarkInstitutionResponse,
    BenchmarkInstitutionUpdate,
    BenchmarkScope,
    BenchmarkValueCreate,
    BenchmarkValueResponse,
    DashboardSummaryResponse,
    DataStatus,
    DimensionAssessmentResponse,
    DimensionCreate,
    DimensionDetailResponse,
    DimensionResponse,
    DimensionUpdate,
    EvaluationRiskLevel,
    EvaluationTrendPoint,
    EvaluationTrendResponse,
    FrameworkCode,
    FrameworkCreate,
    FrameworkDetailResponse,
    FrameworkResponse,
    FrameworkSummaryRow,
    FrameworkUpdate,
    ImpactPreviewRequest,
    ImpactPreviewResponse,
    IndicatorCreate,
    IndicatorDetailResponse,
    IndicatorResponse,
    IndicatorUpdate,
    MetricOrigin,
    MetricPeriod,
    MetricValueCreate,
    MetricValueDetailResponse,
    MetricValueResponse,
    MetricValueUpdate,
    MissingDataSummary,
    RecommendationItem,
    StudentMetricSyncRequest,
    StudentMetricSyncResponse,
)
from app.services.crud_helpers import apply_updates, get_object_or_404
from app.services.ranking_benchmark_service import build_comparison
from app.services.ranking_calculation_service import (
    MetricSnapshot,
    evaluate_framework,
    normalize_score,
    persist_assessment,
    resolve_effective_value,
    validate_dimension_weights,
    validate_indicator_weights,
)
from app.services.ranking_impact_service import build_impact_preview
from app.services.ranking_readiness_service import ZERO, quantize
from app.services.ranking_recommendation_service import build_recommendations
from app.services.ranking_student_sync_service import sync_student_metrics

router = APIRouter(prefix="/api/ranking-evaluations", tags=["Ranking Evaluations"])

FRAMEWORK_LABEL: str = "Değerlendirme çerçevesi"
DIMENSION_LABEL: str = "Değerlendirme boyutu"
INDICATOR_LABEL: str = "Gösterge"
METRIC_LABEL: str = "Gösterge verisi"
ASSESSMENT_LABEL: str = "Değerlendirme"
INSTITUTION_LABEL: str = "Karşılaştırma kurumu"

# Trend yönü belirlenirken bu puandan küçük değişimler "sabit" sayılır.
TREND_STABILITY_POINTS: Decimal = Decimal("2.00")


# ===========================================================================
# Yardımcı fonksiyonlar
# ===========================================================================


def _get_framework_or_404(db: Session, framework_id: int) -> EvaluationFramework:
    """Çerçeveyi id ile getirir, yoksa 404 döndürür."""
    return get_object_or_404(db, EvaluationFramework, framework_id, FRAMEWORK_LABEL)


def _resolve_framework_by_code(db: Session, code: str) -> EvaluationFramework:
    """Çerçeveyi koduna göre bulur; birden fazla metodoloji yılı varsa en yenisini alır."""
    # Aynı code için birden fazla metodoloji yılı olabildiğinden aktif ve en yeni
    # metodolojiyi seçiyoruz. Aktif kayıt yoksa yine de en yeni yıla düşüyoruz.
    statement = (
        select(EvaluationFramework)
        .where(EvaluationFramework.code == code)
        .order_by(
            EvaluationFramework.is_active.desc(),
            EvaluationFramework.methodology_year.desc(),
        )
    )
    framework: Optional[EvaluationFramework] = db.execute(statement).scalars().first()
    if framework is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{code}' kodlu değerlendirme çerçevesi bulunamadı.",
        )
    return framework


def _ensure_framework_unique(
    db: Session, code: str, methodology_year: int, exclude_id: Optional[int] = None
) -> None:
    """Aynı code + metodoloji yılı kombinasyonu varsa 409 fırlatır."""
    statement = (
        select(EvaluationFramework)
        .where(EvaluationFramework.code == code)
        .where(EvaluationFramework.methodology_year == methodology_year)
    )
    if exclude_id is not None:
        statement = statement.where(EvaluationFramework.id != exclude_id)

    if db.execute(statement).scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{code}' çerçevesinin {methodology_year} metodoloji yılı zaten tanımlı."
            ),
        )


def _ensure_dimension_unique(
    db: Session, framework_id: int, code: str, exclude_id: Optional[int] = None
) -> None:
    """Aynı çerçeve içinde aynı boyut kodu varsa 409 fırlatır."""
    statement = (
        select(EvaluationDimension)
        .where(EvaluationDimension.framework_id == framework_id)
        .where(EvaluationDimension.code == code)
    )
    if exclude_id is not None:
        statement = statement.where(EvaluationDimension.id != exclude_id)

    if db.execute(statement).scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Bu çerçevede '{code}' kodlu boyut zaten tanımlı.",
        )


def _ensure_indicator_unique(
    db: Session, code: str, exclude_id: Optional[int] = None
) -> None:
    """Aynı gösterge kodu varsa 409 fırlatır (kod sistem genelinde benzersizdir)."""
    statement = select(EvaluationIndicator).where(EvaluationIndicator.code == code)
    if exclude_id is not None:
        statement = statement.where(EvaluationIndicator.id != exclude_id)

    if db.execute(statement).scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{code}' kodlu gösterge zaten tanımlı. Gösterge kodları sistem "
                "genelinde benzersizdir (içe aktarımda anahtar olarak kullanılır)."
            ),
        )


def _ensure_metric_unique(
    db: Session,
    indicator_id: int,
    academic_year: str,
    period: str,
    exclude_id: Optional[int] = None,
) -> None:
    """Aynı gösterge + yıl + dönem kaydı varsa 409 fırlatır."""
    statement = (
        select(InstitutionalMetricValue)
        .where(InstitutionalMetricValue.indicator_id == indicator_id)
        .where(InstitutionalMetricValue.academic_year == academic_year)
        .where(InstitutionalMetricValue.period == period)
    )
    if exclude_id is not None:
        statement = statement.where(InstitutionalMetricValue.id != exclude_id)

    if db.execute(statement).scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Bu gösterge için {academic_year} akademik yılı '{period}' dönemine ait "
                "kayıt zaten mevcut."
            ),
        )


def _build_detail_with_recommendations(
    db: Session,
    framework: EvaluationFramework,
    academic_year: str,
    period: str,
) -> AssessmentDetailResponse:
    """Değerlendirmeyi hesaplar ve önerileri ekler."""
    detail: AssessmentDetailResponse = evaluate_framework(
        db, framework, academic_year, period
    )
    detail.recommendations = build_recommendations(detail)
    return detail


# ===========================================================================
# FRAMEWORK YÖNETİMİ
# ===========================================================================


@router.get(
    "/frameworks",
    response_model=List[FrameworkDetailResponse],
    summary="Değerlendirme çerçevelerini listele",
)
def list_frameworks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    framework_code: Optional[FrameworkCode] = Query(default=None),
    methodology_year: Optional[int] = Query(default=None, ge=2000, le=2100),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[FrameworkDetailResponse]:
    """THE, QS ve YÖK çerçevelerini boyut/gösterge sayılarıyla birlikte listeler."""
    statement = select(EvaluationFramework)
    if framework_code is not None:
        statement = statement.where(EvaluationFramework.code == framework_code.value)
    if methodology_year is not None:
        statement = statement.where(
            EvaluationFramework.methodology_year == methodology_year
        )
    if is_active is not None:
        statement = statement.where(EvaluationFramework.is_active.is_(is_active))

    frameworks = list(
        db.execute(
            statement.order_by(EvaluationFramework.code, EvaluationFramework.methodology_year)
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )

    # Boyut ve gösterge sayıları tek toplu sorguyla alınır (N+1 yok).
    counts = {
        framework_id: (dimension_count, indicator_count)
        for framework_id, dimension_count, indicator_count in db.execute(
            select(
                EvaluationDimension.framework_id,
                func.count(func.distinct(EvaluationDimension.id)),
                func.count(EvaluationIndicator.id),
            )
            .outerjoin(
                EvaluationIndicator,
                EvaluationIndicator.dimension_id == EvaluationDimension.id,
            )
            .group_by(EvaluationDimension.framework_id)
        ).all()
    }

    results: List[FrameworkDetailResponse] = []
    for framework in frameworks:
        dimension_count, indicator_count = counts.get(framework.id, (0, 0))
        total_weight, balanced = validate_dimension_weights(db, framework.id)
        results.append(
            FrameworkDetailResponse(
                **{
                    field: getattr(framework, field)
                    for field in (
                        "id",
                        "code",
                        "name",
                        "methodology_year",
                        "description",
                        "is_active",
                        "created_at",
                        "updated_at",
                    )
                },
                dimension_count=dimension_count,
                indicator_count=indicator_count,
                total_dimension_weight=total_weight,
                weight_is_balanced=balanced,
            )
        )
    return results


@router.post(
    "/frameworks",
    response_model=FrameworkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni değerlendirme çerçevesi oluştur",
)
def create_framework(
    payload: FrameworkCreate, db: Session = Depends(get_db)
) -> EvaluationFramework:
    """Yeni bir THE/QS/YÖK metodoloji kaydı oluşturur."""
    _ensure_framework_unique(db, payload.code.value, payload.methodology_year)

    data = payload.model_dump()
    data["code"] = payload.code.value

    framework = EvaluationFramework(**data)
    db.add(framework)
    db.commit()
    db.refresh(framework)
    return framework


@router.get(
    "/frameworks/{framework_id}",
    response_model=FrameworkDetailResponse,
    summary="Çerçeve detayı",
)
def get_framework(
    framework_id: int, db: Session = Depends(get_db)
) -> FrameworkDetailResponse:
    """Tek bir çerçeveyi ağırlık dengesi bilgisiyle birlikte getirir."""
    framework = _get_framework_or_404(db, framework_id)

    dimension_count: int = int(
        db.execute(
            select(func.count(EvaluationDimension.id)).where(
                EvaluationDimension.framework_id == framework_id
            )
        ).scalar()
        or 0
    )
    indicator_count: int = int(
        db.execute(
            select(func.count(EvaluationIndicator.id))
            .join(
                EvaluationDimension,
                EvaluationIndicator.dimension_id == EvaluationDimension.id,
            )
            .where(EvaluationDimension.framework_id == framework_id)
        ).scalar()
        or 0
    )
    total_weight, balanced = validate_dimension_weights(db, framework_id)

    return FrameworkDetailResponse(
        id=framework.id,
        code=framework.code,
        name=framework.name,
        methodology_year=framework.methodology_year,
        description=framework.description,
        is_active=framework.is_active,
        created_at=framework.created_at,
        updated_at=framework.updated_at,
        dimension_count=dimension_count,
        indicator_count=indicator_count,
        total_dimension_weight=total_weight,
        weight_is_balanced=balanced,
    )


@router.put(
    "/frameworks/{framework_id}",
    response_model=FrameworkResponse,
    summary="Çerçeve güncelle",
)
def update_framework(
    framework_id: int,
    payload: FrameworkUpdate,
    db: Session = Depends(get_db),
) -> EvaluationFramework:
    """Var olan bir çerçeveyi kısmi olarak günceller."""
    framework = _get_framework_or_404(db, framework_id)
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("code") is not None:
        update_data["code"] = update_data["code"].value

    new_code: str = update_data.get("code", framework.code)
    new_year: int = update_data.get("methodology_year", framework.methodology_year)
    if new_code != framework.code or new_year != framework.methodology_year:
        _ensure_framework_unique(db, new_code, new_year, exclude_id=framework_id)

    apply_updates(framework, update_data)
    db.commit()
    db.refresh(framework)
    return framework


@router.delete(
    "/frameworks/{framework_id}",
    response_model=FrameworkResponse,
    summary="Çerçeveyi pasifleştir",
)
def deactivate_framework(
    framework_id: int, db: Session = Depends(get_db)
) -> EvaluationFramework:
    """Çerçeveyi silmez, is_active=False yaparak pasifleştirir."""
    # Geçmiş değerlendirmeler bu çerçeveye bağlı olduğu için fiziksel silme yapılmıyor;
    # projedeki diğer modüllerle tutarlı soft delete yaklaşımı uygulanıyor.
    framework = _get_framework_or_404(db, framework_id)
    framework.is_active = False
    db.commit()
    db.refresh(framework)
    return framework


# ===========================================================================
# DIMENSION YÖNETİMİ
# ===========================================================================


@router.get(
    "/dimensions",
    response_model=List[DimensionDetailResponse],
    summary="Boyutları listele",
)
def list_dimensions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    framework_id: Optional[int] = Query(default=None, gt=0),
    framework_code: Optional[FrameworkCode] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[DimensionDetailResponse]:
    """Değerlendirme boyutlarını gösterge sayısı ve ağırlık dengesiyle listeler."""
    statement = select(EvaluationDimension, EvaluationFramework.code).join(
        EvaluationFramework, EvaluationDimension.framework_id == EvaluationFramework.id
    )
    if framework_id is not None:
        statement = statement.where(EvaluationDimension.framework_id == framework_id)
    if framework_code is not None:
        statement = statement.where(EvaluationFramework.code == framework_code.value)
    if is_active is not None:
        statement = statement.where(EvaluationDimension.is_active.is_(is_active))

    rows = db.execute(
        statement.order_by(
            EvaluationDimension.framework_id, EvaluationDimension.display_order
        )
        .offset(skip)
        .limit(limit)
    ).all()

    indicator_counts = {
        dimension_id: count
        for dimension_id, count in db.execute(
            select(EvaluationIndicator.dimension_id, func.count(EvaluationIndicator.id))
            .group_by(EvaluationIndicator.dimension_id)
        ).all()
    }

    results: List[DimensionDetailResponse] = []
    for dimension, code in rows:
        total_weight, balanced = validate_indicator_weights(db, dimension.id)
        results.append(
            DimensionDetailResponse(
                id=dimension.id,
                framework_id=dimension.framework_id,
                code=dimension.code,
                name=dimension.name,
                description=dimension.description,
                weight=dimension.weight,
                display_order=dimension.display_order,
                is_active=dimension.is_active,
                created_at=dimension.created_at,
                updated_at=dimension.updated_at,
                framework_code=code,
                indicator_count=indicator_counts.get(dimension.id, 0),
                total_indicator_weight=total_weight,
                weight_is_balanced=balanced,
            )
        )
    return results


@router.post(
    "/dimensions",
    response_model=DimensionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni boyut oluştur",
)
def create_dimension(
    payload: DimensionCreate, db: Session = Depends(get_db)
) -> EvaluationDimension:
    """Bir çerçeveye yeni değerlendirme boyutu ekler."""
    _get_framework_or_404(db, payload.framework_id)
    _ensure_dimension_unique(db, payload.framework_id, payload.code)

    dimension = EvaluationDimension(**payload.model_dump())
    db.add(dimension)
    db.commit()
    db.refresh(dimension)
    return dimension


@router.get(
    "/dimensions/{dimension_id}",
    response_model=DimensionDetailResponse,
    summary="Boyut detayı",
)
def get_dimension(
    dimension_id: int, db: Session = Depends(get_db)
) -> DimensionDetailResponse:
    """Tek bir boyutu gösterge sayısı ve ağırlık dengesiyle getirir."""
    dimension = get_object_or_404(db, EvaluationDimension, dimension_id, DIMENSION_LABEL)
    framework = db.get(EvaluationFramework, dimension.framework_id)

    indicator_count: int = int(
        db.execute(
            select(func.count(EvaluationIndicator.id)).where(
                EvaluationIndicator.dimension_id == dimension_id
            )
        ).scalar()
        or 0
    )
    total_weight, balanced = validate_indicator_weights(db, dimension_id)

    return DimensionDetailResponse(
        id=dimension.id,
        framework_id=dimension.framework_id,
        code=dimension.code,
        name=dimension.name,
        description=dimension.description,
        weight=dimension.weight,
        display_order=dimension.display_order,
        is_active=dimension.is_active,
        created_at=dimension.created_at,
        updated_at=dimension.updated_at,
        framework_code=framework.code if framework else "",
        indicator_count=indicator_count,
        total_indicator_weight=total_weight,
        weight_is_balanced=balanced,
    )


@router.put(
    "/dimensions/{dimension_id}",
    response_model=DimensionResponse,
    summary="Boyut güncelle",
)
def update_dimension(
    dimension_id: int,
    payload: DimensionUpdate,
    db: Session = Depends(get_db),
) -> EvaluationDimension:
    """Var olan bir boyutu kısmi olarak günceller."""
    dimension = get_object_or_404(db, EvaluationDimension, dimension_id, DIMENSION_LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("framework_id") is not None:
        _get_framework_or_404(db, update_data["framework_id"])

    new_framework: int = update_data.get("framework_id", dimension.framework_id)
    new_code: str = update_data.get("code", dimension.code)
    if new_framework != dimension.framework_id or new_code != dimension.code:
        _ensure_dimension_unique(db, new_framework, new_code, exclude_id=dimension_id)

    apply_updates(dimension, update_data)
    db.commit()
    db.refresh(dimension)
    return dimension


@router.delete(
    "/dimensions/{dimension_id}",
    response_model=DimensionResponse,
    summary="Boyutu pasifleştir",
)
def deactivate_dimension(
    dimension_id: int, db: Session = Depends(get_db)
) -> EvaluationDimension:
    """Boyutu silmez, is_active=False yaparak pasifleştirir."""
    dimension = get_object_or_404(db, EvaluationDimension, dimension_id, DIMENSION_LABEL)
    dimension.is_active = False
    db.commit()
    db.refresh(dimension)
    return dimension


# ===========================================================================
# INDICATOR YÖNETİMİ
# ===========================================================================


@router.get(
    "/indicators",
    response_model=List[IndicatorDetailResponse],
    summary="Göstergeleri listele",
)
def list_indicators(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    dimension_id: Optional[int] = Query(default=None, gt=0),
    framework_id: Optional[int] = Query(default=None, gt=0),
    framework_code: Optional[FrameworkCode] = Query(default=None),
    required_for_readiness: Optional[bool] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[IndicatorDetailResponse]:
    """Göstergeleri boyut ve çerçeve bilgisiyle birlikte listeler."""
    statement = (
        select(EvaluationIndicator, EvaluationDimension, EvaluationFramework)
        .join(EvaluationDimension, EvaluationIndicator.dimension_id == EvaluationDimension.id)
        .join(EvaluationFramework, EvaluationDimension.framework_id == EvaluationFramework.id)
    )
    if dimension_id is not None:
        statement = statement.where(EvaluationIndicator.dimension_id == dimension_id)
    if framework_id is not None:
        statement = statement.where(EvaluationDimension.framework_id == framework_id)
    if framework_code is not None:
        statement = statement.where(EvaluationFramework.code == framework_code.value)
    if required_for_readiness is not None:
        statement = statement.where(
            EvaluationIndicator.required_for_readiness.is_(required_for_readiness)
        )
    if is_active is not None:
        statement = statement.where(EvaluationIndicator.is_active.is_(is_active))

    rows = db.execute(
        statement.order_by(EvaluationIndicator.id).offset(skip).limit(limit)
    ).all()

    metric_counts = {
        indicator_id: count
        for indicator_id, count in db.execute(
            select(
                InstitutionalMetricValue.indicator_id,
                func.count(InstitutionalMetricValue.id),
            ).group_by(InstitutionalMetricValue.indicator_id)
        ).all()
    }

    return [
        IndicatorDetailResponse(
            **{
                field: getattr(indicator, field)
                for field in (
                    "id",
                    "dimension_id",
                    "code",
                    "name",
                    "description",
                    "unit",
                    "calculation_type",
                    "weight",
                    "direction",
                    "minimum_value",
                    "target_value",
                    "maximum_value",
                    "data_source",
                    "required_for_readiness",
                    "auto_source_key",
                    "impact_numerator_variable",
                    "impact_denominator_variable",
                    "is_active",
                    "created_at",
                    "updated_at",
                )
            },
            dimension_code=dimension.code,
            dimension_name=dimension.name,
            framework_code=framework.code,
            framework_id=framework.id,
            metric_value_count=metric_counts.get(indicator.id, 0),
        )
        for indicator, dimension, framework in rows
    ]


@router.post(
    "/indicators",
    response_model=IndicatorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni gösterge oluştur",
)
def create_indicator(
    payload: IndicatorCreate, db: Session = Depends(get_db)
) -> EvaluationIndicator:
    """Bir boyuta yeni gösterge ekler."""
    get_object_or_404(db, EvaluationDimension, payload.dimension_id, DIMENSION_LABEL)
    _ensure_indicator_unique(db, payload.code)

    data = payload.model_dump()
    data["calculation_type"] = payload.calculation_type.value
    data["direction"] = payload.direction.value

    indicator = EvaluationIndicator(**data)
    db.add(indicator)
    db.commit()
    db.refresh(indicator)
    return indicator


@router.get(
    "/indicators/{indicator_id}",
    response_model=IndicatorDetailResponse,
    summary="Gösterge detayı",
)
def get_indicator(
    indicator_id: int, db: Session = Depends(get_db)
) -> IndicatorDetailResponse:
    """Tek bir göstergeyi boyut ve çerçeve bilgisiyle getirir."""
    indicator = get_object_or_404(db, EvaluationIndicator, indicator_id, INDICATOR_LABEL)
    dimension = db.get(EvaluationDimension, indicator.dimension_id)
    framework = db.get(EvaluationFramework, dimension.framework_id) if dimension else None

    metric_count: int = int(
        db.execute(
            select(func.count(InstitutionalMetricValue.id)).where(
                InstitutionalMetricValue.indicator_id == indicator_id
            )
        ).scalar()
        or 0
    )

    return IndicatorDetailResponse(
        **{
            field: getattr(indicator, field)
            for field in (
                "id",
                "dimension_id",
                "code",
                "name",
                "description",
                "unit",
                "calculation_type",
                "weight",
                "direction",
                "minimum_value",
                "target_value",
                "maximum_value",
                "data_source",
                "required_for_readiness",
                "auto_source_key",
                "impact_numerator_variable",
                "impact_denominator_variable",
                "is_active",
                "created_at",
                "updated_at",
            )
        },
        dimension_code=dimension.code if dimension else "",
        dimension_name=dimension.name if dimension else "",
        framework_code=framework.code if framework else "",
        framework_id=framework.id if framework else 0,
        metric_value_count=metric_count,
    )


@router.put(
    "/indicators/{indicator_id}",
    response_model=IndicatorResponse,
    summary="Gösterge güncelle",
)
def update_indicator(
    indicator_id: int,
    payload: IndicatorUpdate,
    db: Session = Depends(get_db),
) -> EvaluationIndicator:
    """Var olan bir göstergeyi kısmi olarak günceller."""
    indicator = get_object_or_404(db, EvaluationIndicator, indicator_id, INDICATOR_LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("dimension_id") is not None:
        get_object_or_404(
            db, EvaluationDimension, update_data["dimension_id"], DIMENSION_LABEL
        )
    if update_data.get("code") is not None and update_data["code"] != indicator.code:
        _ensure_indicator_unique(db, update_data["code"], exclude_id=indicator_id)

    if update_data.get("calculation_type") is not None:
        update_data["calculation_type"] = update_data["calculation_type"].value
    if update_data.get("direction") is not None:
        update_data["direction"] = update_data["direction"].value

    # Sınır tutarlılığı güncellenen değerlerle birlikte yeniden kontrol edilir.
    minimum = update_data.get("minimum_value", indicator.minimum_value)
    target = update_data.get("target_value", indicator.target_value)
    maximum = update_data.get("maximum_value", indicator.maximum_value)

    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["body", "minimum_value"],
                    "msg": (
                        f"minimum_value ({minimum}) maximum_value ({maximum}) "
                        "değerinden büyük olamaz."
                    ),
                    "type": "value_error",
                }
            ],
        )
    if target is not None and minimum is not None and target < minimum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["body", "target_value"],
                    "msg": (
                        f"target_value ({target}) minimum_value ({minimum}) "
                        "değerinden küçük olamaz."
                    ),
                    "type": "value_error",
                }
            ],
        )
    if target is not None and maximum is not None and target > maximum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["body", "target_value"],
                    "msg": (
                        f"target_value ({target}) maximum_value ({maximum}) "
                        "değerinden büyük olamaz."
                    ),
                    "type": "value_error",
                }
            ],
        )

    apply_updates(indicator, update_data)
    db.commit()
    db.refresh(indicator)
    return indicator


@router.delete(
    "/indicators/{indicator_id}",
    response_model=IndicatorResponse,
    summary="Göstergeyi pasifleştir",
)
def deactivate_indicator(
    indicator_id: int, db: Session = Depends(get_db)
) -> EvaluationIndicator:
    """Göstergeyi silmez, is_active=False yaparak pasifleştirir."""
    indicator = get_object_or_404(db, EvaluationIndicator, indicator_id, INDICATOR_LABEL)
    indicator.is_active = False
    db.commit()
    db.refresh(indicator)
    return indicator


# ===========================================================================
# METRIC YÖNETİMİ  (sabit yol /metrics/sync-student-data önce tanımlandı)
# ===========================================================================


@router.post(
    "/metrics/sync-student-data",
    response_model=StudentMetricSyncResponse,
    summary="Modül 1/2 verisinden otomatik gösterge senkronizasyonu",
)
def sync_student_data(
    payload: StudentMetricSyncRequest, db: Session = Depends(get_db)
) -> StudentMetricSyncResponse:
    """Öğrenci verilerinden hesaplanan göstergeleri kaydeder.

    Elle girilmiş veya içe aktarılmış kayıtlar korunur (overwrite_manual=false).
    """
    result = sync_student_metrics(
        db,
        academic_year=payload.academic_year,
        period=payload.period.value,
        overwrite_manual=payload.overwrite_manual,
    )
    # Tüm senkronizasyon tek transaction içinde tamamlanır.
    db.commit()
    return result


@router.get(
    "/metrics",
    response_model=List[MetricValueDetailResponse],
    summary="Gösterge verilerini listele",
)
def list_metrics(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    indicator_id: Optional[int] = Query(default=None, gt=0),
    framework_id: Optional[int] = Query(default=None, gt=0),
    framework_code: Optional[FrameworkCode] = Query(default=None),
    dimension_id: Optional[int] = Query(default=None, gt=0),
    academic_year: Optional[str] = Query(default=None),
    period: Optional[MetricPeriod] = Query(default=None),
    data_status: Optional[DataStatus] = Query(default=None),
    origin: Optional[MetricOrigin] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[MetricValueDetailResponse]:
    """Kurumun gösterge verilerini hesaplanmış değer ve skorla birlikte listeler."""
    statement = (
        select(
            InstitutionalMetricValue,
            EvaluationIndicator,
            EvaluationDimension,
            EvaluationFramework,
        )
        .join(
            EvaluationIndicator,
            InstitutionalMetricValue.indicator_id == EvaluationIndicator.id,
        )
        .join(EvaluationDimension, EvaluationIndicator.dimension_id == EvaluationDimension.id)
        .join(EvaluationFramework, EvaluationDimension.framework_id == EvaluationFramework.id)
    )

    if indicator_id is not None:
        statement = statement.where(InstitutionalMetricValue.indicator_id == indicator_id)
    if framework_id is not None:
        statement = statement.where(EvaluationDimension.framework_id == framework_id)
    if framework_code is not None:
        statement = statement.where(EvaluationFramework.code == framework_code.value)
    if dimension_id is not None:
        statement = statement.where(EvaluationIndicator.dimension_id == dimension_id)
    if academic_year:
        statement = statement.where(InstitutionalMetricValue.academic_year == academic_year)
    if period is not None:
        statement = statement.where(InstitutionalMetricValue.period == period.value)
    if data_status is not None:
        statement = statement.where(
            InstitutionalMetricValue.data_status == data_status.value
        )
    if origin is not None:
        statement = statement.where(InstitutionalMetricValue.origin == origin.value)

    rows = db.execute(
        statement.order_by(
            InstitutionalMetricValue.academic_year.desc(), InstitutionalMetricValue.id
        )
        .offset(skip)
        .limit(limit)
    ).all()

    results: List[MetricValueDetailResponse] = []
    for metric, indicator, dimension, framework in rows:
        snapshot = MetricSnapshot.from_model(metric)
        effective_value, value_notes = resolve_effective_value(indicator, snapshot)
        score, score_notes = normalize_score(indicator, effective_value)

        results.append(
            MetricValueDetailResponse(
                id=metric.id,
                indicator_id=metric.indicator_id,
                academic_year=metric.academic_year,
                period=MetricPeriod(metric.period),
                value=metric.value,
                numerator=metric.numerator,
                denominator=metric.denominator,
                data_status=DataStatus(metric.data_status),
                origin=MetricOrigin(metric.origin),
                source_reference=metric.source_reference,
                notes=metric.notes,
                measured_at=metric.measured_at,
                created_at=metric.created_at,
                updated_at=metric.updated_at,
                indicator_code=indicator.code,
                indicator_name=indicator.name,
                indicator_unit=indicator.unit,
                dimension_code=dimension.code,
                framework_code=framework.code,
                effective_value=effective_value,
                performance_score=score,
                calculation_notes=value_notes + score_notes,
            )
        )
    return results


@router.post(
    "/metrics",
    response_model=MetricValueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni gösterge verisi ekle",
)
def create_metric(
    payload: MetricValueCreate, db: Session = Depends(get_db)
) -> InstitutionalMetricValue:
    """Bir gösterge için yıl/dönem verisi oluşturur."""
    get_object_or_404(db, EvaluationIndicator, payload.indicator_id, INDICATOR_LABEL)
    _ensure_metric_unique(
        db, payload.indicator_id, payload.academic_year, payload.period.value
    )

    data = payload.model_dump()
    data["period"] = payload.period.value
    data["data_status"] = payload.data_status.value
    data["origin"] = payload.origin.value

    metric = InstitutionalMetricValue(**data)
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


@router.get(
    "/metrics/{metric_id}",
    response_model=MetricValueDetailResponse,
    summary="Gösterge verisi detayı",
)
def get_metric(
    metric_id: int, db: Session = Depends(get_db)
) -> MetricValueDetailResponse:
    """Tek bir gösterge verisini hesaplanmış değer ve skorla getirir."""
    metric = get_object_or_404(db, InstitutionalMetricValue, metric_id, METRIC_LABEL)
    indicator = db.get(EvaluationIndicator, metric.indicator_id)
    dimension = db.get(EvaluationDimension, indicator.dimension_id) if indicator else None
    framework = db.get(EvaluationFramework, dimension.framework_id) if dimension else None

    snapshot = MetricSnapshot.from_model(metric)
    effective_value, value_notes = resolve_effective_value(indicator, snapshot)
    score, score_notes = normalize_score(indicator, effective_value)

    return MetricValueDetailResponse(
        id=metric.id,
        indicator_id=metric.indicator_id,
        academic_year=metric.academic_year,
        period=MetricPeriod(metric.period),
        value=metric.value,
        numerator=metric.numerator,
        denominator=metric.denominator,
        data_status=DataStatus(metric.data_status),
        origin=MetricOrigin(metric.origin),
        source_reference=metric.source_reference,
        notes=metric.notes,
        measured_at=metric.measured_at,
        created_at=metric.created_at,
        updated_at=metric.updated_at,
        indicator_code=indicator.code if indicator else "",
        indicator_name=indicator.name if indicator else "",
        indicator_unit=indicator.unit if indicator else None,
        dimension_code=dimension.code if dimension else "",
        framework_code=framework.code if framework else "",
        effective_value=effective_value,
        performance_score=score,
        calculation_notes=value_notes + score_notes,
    )


@router.put(
    "/metrics/{metric_id}",
    response_model=MetricValueResponse,
    summary="Gösterge verisi güncelle",
)
def update_metric(
    metric_id: int,
    payload: MetricValueUpdate,
    db: Session = Depends(get_db),
) -> InstitutionalMetricValue:
    """Var olan bir gösterge verisini kısmi olarak günceller."""
    metric = get_object_or_404(db, InstitutionalMetricValue, metric_id, METRIC_LABEL)
    update_data = payload.model_dump(exclude_unset=True)

    if update_data.get("indicator_id") is not None:
        get_object_or_404(
            db, EvaluationIndicator, update_data["indicator_id"], INDICATOR_LABEL
        )
    for enum_field in ("period", "data_status", "origin"):
        if update_data.get(enum_field) is not None:
            update_data[enum_field] = update_data[enum_field].value

    new_indicator: int = update_data.get("indicator_id", metric.indicator_id)
    new_year: str = update_data.get("academic_year", metric.academic_year)
    new_period: str = update_data.get("period", metric.period)
    if (
        new_indicator != metric.indicator_id
        or new_year != metric.academic_year
        or new_period != metric.period
    ):
        _ensure_metric_unique(db, new_indicator, new_year, new_period, exclude_id=metric_id)

    apply_updates(metric, update_data)
    db.commit()
    db.refresh(metric)
    return metric


@router.delete(
    "/metrics/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Gösterge verisini sil",
)
def delete_metric(metric_id: int, db: Session = Depends(get_db)) -> None:
    """Bir gösterge verisini siler."""
    # Gösterge verisinde is_active alanı yok; yanlış girilen bir yıl/dönem
    # kaydının tamamen kaldırılabilmesi için fiziksel silme uygulanıyor.
    metric = get_object_or_404(db, InstitutionalMetricValue, metric_id, METRIC_LABEL)
    db.delete(metric)
    db.commit()


# ===========================================================================
# DEĞERLENDİRME
# ===========================================================================


@router.post(
    "/assessments/calculate",
    response_model=AssessmentCalculateResponse,
    summary="Değerlendirme hesapla",
)
def calculate_assessment(
    payload: AssessmentCalculateRequest, db: Session = Depends(get_db)
) -> AssessmentCalculateResponse:
    """Bir veya tüm çerçeveler için değerlendirme hesaplar.

    UYARI: Sonuç gerçek THE/QS/YÖK sıralaması değildir; iç izleme skorudur.
    """
    statement = select(EvaluationFramework).where(EvaluationFramework.is_active.is_(True))
    if payload.framework_id is not None:
        statement = select(EvaluationFramework).where(
            EvaluationFramework.id == payload.framework_id
        )
    elif payload.framework_code is not None:
        statement = statement.where(EvaluationFramework.code == payload.framework_code.value)

    frameworks: List[EvaluationFramework] = list(
        db.execute(statement.order_by(EvaluationFramework.id)).scalars().all()
    )
    if not frameworks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hesaplanacak aktif değerlendirme çerçevesi bulunamadı.",
        )

    details: List[AssessmentDetailResponse] = []
    for framework in frameworks:
        detail = _build_detail_with_recommendations(
            db, framework, payload.academic_year, payload.period.value
        )
        if payload.persist:
            assessment = persist_assessment(db, framework, detail)
            # id'yi cevaba koyabilmek için flush ediyoruz; commit döngü sonunda.
            db.flush()
            detail.assessment_id = assessment.id
            detail.persisted = True
        details.append(detail)

    # Tüm çerçeveler tek transaction içinde yazılır; biri hata verirse hiçbiri yazılmaz.
    if payload.persist:
        db.commit()

    return AssessmentCalculateResponse(
        academic_year=payload.academic_year,
        period=payload.period,
        persisted=payload.persist,
        calculated_framework_count=len(details),
        assessments=details,
    )


@router.get(
    "/assessments",
    response_model=List[AssessmentResponse],
    summary="Kaydedilmiş değerlendirmeleri listele",
)
def list_assessments(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    framework_id: Optional[int] = Query(default=None, gt=0),
    framework_code: Optional[FrameworkCode] = Query(default=None),
    academic_year: Optional[str] = Query(default=None),
    period: Optional[MetricPeriod] = Query(default=None),
    risk_level: Optional[EvaluationRiskLevel] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[FrameworkAssessment]:
    """Geçmiş değerlendirme kayıtlarını en yeniden eskiye listeler."""
    statement = select(FrameworkAssessment).join(
        EvaluationFramework, FrameworkAssessment.framework_id == EvaluationFramework.id
    )
    if framework_id is not None:
        statement = statement.where(FrameworkAssessment.framework_id == framework_id)
    if framework_code is not None:
        statement = statement.where(EvaluationFramework.code == framework_code.value)
    if academic_year:
        statement = statement.where(FrameworkAssessment.academic_year == academic_year)
    if period is not None:
        statement = statement.where(FrameworkAssessment.period == period.value)
    if risk_level is not None:
        statement = statement.where(FrameworkAssessment.risk_level == risk_level.value)

    return list(
        db.execute(
            statement.order_by(
                FrameworkAssessment.academic_year.desc(), FrameworkAssessment.id.desc()
            )
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )


@router.get(
    "/assessments/latest/{framework_code}",
    response_model=AssessmentDetailResponse,
    summary="Çerçevenin en güncel değerlendirmesi",
)
def get_latest_assessment(
    framework_code: FrameworkCode,
    period: MetricPeriod = Query(default=MetricPeriod.ANNUAL),
    db: Session = Depends(get_db),
) -> AssessmentDetailResponse:
    """Bir çerçevenin en son kaydedilmiş değerlendirmesini detaylı döndürür."""
    framework = _resolve_framework_by_code(db, framework_code.value)

    statement = (
        select(FrameworkAssessment)
        .where(FrameworkAssessment.framework_id == framework.id)
        .where(FrameworkAssessment.period == period.value)
        .order_by(FrameworkAssessment.academic_year.desc(), FrameworkAssessment.id.desc())
        .limit(1)
    )
    assessment: Optional[FrameworkAssessment] = db.execute(statement).scalars().first()

    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{framework_code.value}' çerçevesi için henüz hesaplanmış değerlendirme yok. "
                "Önce POST /api/ranking-evaluations/assessments/calculate çağırın."
            ),
        )

    # Detaylı rapor kayıtlı özetten değil, güncel veriden yeniden üretilir;
    # böylece boyut ve gösterge kırılımları her zaman tutarlı olur.
    detail = _build_detail_with_recommendations(
        db, framework, assessment.academic_year, assessment.period
    )
    detail.assessment_id = assessment.id
    detail.persisted = True
    return detail


@router.get(
    "/assessments/{assessment_id}",
    response_model=AssessmentDetailResponse,
    summary="Değerlendirme detayı",
)
def get_assessment(
    assessment_id: int, db: Session = Depends(get_db)
) -> AssessmentDetailResponse:
    """Kaydedilmiş bir değerlendirmenin tam raporunu döndürür."""
    assessment = get_object_or_404(db, FrameworkAssessment, assessment_id, ASSESSMENT_LABEL)
    framework = db.get(EvaluationFramework, assessment.framework_id)

    detail = _build_detail_with_recommendations(
        db, framework, assessment.academic_year, assessment.period
    )
    detail.assessment_id = assessment.id
    detail.persisted = True
    return detail


@router.get(
    "/assessments/{assessment_id}/dimensions",
    response_model=List[DimensionAssessmentResponse],
    summary="Değerlendirmenin boyut kırılımı",
)
def get_assessment_dimensions(
    assessment_id: int, db: Session = Depends(get_db)
) -> List[DimensionAssessmentResponse]:
    """Bir değerlendirmenin boyut bazındaki sonuçlarını döndürür."""
    assessment = get_object_or_404(db, FrameworkAssessment, assessment_id, ASSESSMENT_LABEL)
    framework = db.get(EvaluationFramework, assessment.framework_id)

    detail = evaluate_framework(
        db, framework, assessment.academic_year, assessment.period
    )

    # Kaydedilmiş boyut satırlarının id'leri cevaba eklenir.
    stored = {
        row.dimension_id: row.id
        for row in db.execute(
            select(DimensionAssessment).where(
                DimensionAssessment.framework_assessment_id == assessment_id
            )
        )
        .scalars()
        .all()
    }
    for dimension_result in detail.dimensions:
        dimension_result.id = stored.get(dimension_result.dimension_id)

    return detail.dimensions


@router.get(
    "/assessments/{assessment_id}/missing-data",
    response_model=MissingDataSummary,
    summary="Değerlendirmenin eksik veri analizi",
)
def get_assessment_missing_data(
    assessment_id: int, db: Session = Depends(get_db)
) -> MissingDataSummary:
    """Eksik, kısmi ve geçersiz verileri readiness kaybıyla birlikte döndürür."""
    assessment = get_object_or_404(db, FrameworkAssessment, assessment_id, ASSESSMENT_LABEL)
    framework = db.get(EvaluationFramework, assessment.framework_id)

    detail = evaluate_framework(
        db, framework, assessment.academic_year, assessment.period
    )
    return detail.missing_data


# ===========================================================================
# ÖNERİLER
# ===========================================================================


@router.get(
    "/recommendations/{assessment_id}",
    response_model=List[RecommendationItem],
    summary="Değerlendirmeye dayalı stratejik öneriler",
)
def get_recommendations(
    assessment_id: int,
    limit: int = Query(default=15, ge=1, le=100),
    db: Session = Depends(get_db),
) -> List[RecommendationItem]:
    """Değerlendirme sonucundan üretilen Türkçe önerileri döndürür."""
    assessment = get_object_or_404(db, FrameworkAssessment, assessment_id, ASSESSMENT_LABEL)
    framework = db.get(EvaluationFramework, assessment.framework_id)

    detail = evaluate_framework(
        db, framework, assessment.academic_year, assessment.period
    )
    return build_recommendations(detail, limit=limit)


# ===========================================================================
# KARŞILAŞTIRMA
# ===========================================================================


@router.get(
    "/benchmarks/institutions",
    response_model=List[BenchmarkInstitutionResponse],
    summary="Karşılaştırma kurumlarını listele",
)
def list_benchmark_institutions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    institution_type: Optional[str] = Query(default=None),
    is_competitor: Optional[bool] = Query(default=None),
    country: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[BenchmarkInstitution]:
    """Karşılaştırma için tanımlı kurumları listeler."""
    statement = select(BenchmarkInstitution)
    if institution_type:
        statement = statement.where(
            BenchmarkInstitution.institution_type == institution_type
        )
    if is_competitor is not None:
        statement = statement.where(BenchmarkInstitution.is_competitor.is_(is_competitor))
    if country:
        statement = statement.where(BenchmarkInstitution.country == country)
    if is_active is not None:
        statement = statement.where(BenchmarkInstitution.is_active.is_(is_active))

    return list(
        db.execute(statement.order_by(BenchmarkInstitution.name).offset(skip).limit(limit))
        .scalars()
        .all()
    )


@router.post(
    "/benchmarks/institutions",
    response_model=BenchmarkInstitutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni karşılaştırma kurumu ekle",
)
def create_benchmark_institution(
    payload: BenchmarkInstitutionCreate, db: Session = Depends(get_db)
) -> BenchmarkInstitution:
    """Karşılaştırma için yeni kurum tanımlar."""
    existing = db.execute(
        select(BenchmarkInstitution).where(BenchmarkInstitution.name == payload.name)
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.name}' adlı karşılaştırma kurumu zaten tanımlı.",
        )

    institution = BenchmarkInstitution(**payload.model_dump())
    db.add(institution)
    db.commit()
    db.refresh(institution)
    return institution


@router.get(
    "/benchmarks/institutions/{institution_id}",
    response_model=BenchmarkInstitutionResponse,
    summary="Karşılaştırma kurumu detayı",
)
def get_benchmark_institution(
    institution_id: int, db: Session = Depends(get_db)
) -> BenchmarkInstitution:
    """Tek bir karşılaştırma kurumunu getirir."""
    return get_object_or_404(db, BenchmarkInstitution, institution_id, INSTITUTION_LABEL)


@router.put(
    "/benchmarks/institutions/{institution_id}",
    response_model=BenchmarkInstitutionResponse,
    summary="Karşılaştırma kurumu güncelle",
)
def update_benchmark_institution(
    institution_id: int,
    payload: BenchmarkInstitutionUpdate,
    db: Session = Depends(get_db),
) -> BenchmarkInstitution:
    """Karşılaştırma kurumunu kısmi olarak günceller."""
    institution = get_object_or_404(
        db, BenchmarkInstitution, institution_id, INSTITUTION_LABEL
    )
    apply_updates(institution, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(institution)
    return institution


@router.delete(
    "/benchmarks/institutions/{institution_id}",
    response_model=BenchmarkInstitutionResponse,
    summary="Karşılaştırma kurumunu pasifleştir",
)
def deactivate_benchmark_institution(
    institution_id: int, db: Session = Depends(get_db)
) -> BenchmarkInstitution:
    """Kurumu silmez, is_active=False yaparak pasifleştirir."""
    institution = get_object_or_404(
        db, BenchmarkInstitution, institution_id, INSTITUTION_LABEL
    )
    institution.is_active = False
    db.commit()
    db.refresh(institution)
    return institution


@router.post(
    "/benchmarks/values",
    response_model=BenchmarkValueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Karşılaştırma kurumu gösterge değeri ekle",
)
def create_benchmark_value(
    payload: BenchmarkValueCreate, db: Session = Depends(get_db)
) -> BenchmarkMetricValue:
    """Bir karşılaştırma kurumu için gösterge değeri kaydeder."""
    get_object_or_404(
        db, BenchmarkInstitution, payload.benchmark_institution_id, INSTITUTION_LABEL
    )
    get_object_or_404(db, EvaluationIndicator, payload.indicator_id, INDICATOR_LABEL)

    existing = db.execute(
        select(BenchmarkMetricValue)
        .where(
            BenchmarkMetricValue.benchmark_institution_id == payload.benchmark_institution_id
        )
        .where(BenchmarkMetricValue.indicator_id == payload.indicator_id)
        .where(BenchmarkMetricValue.academic_year == payload.academic_year)
        .where(BenchmarkMetricValue.period == payload.period.value)
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Bu kurum ve gösterge için aynı akademik yıl ve döneme ait kayıt "
                "zaten mevcut."
            ),
        )

    data = payload.model_dump()
    data["period"] = payload.period.value

    value = BenchmarkMetricValue(**data)
    db.add(value)
    db.commit()
    db.refresh(value)
    return value


@router.get(
    "/benchmarks/comparison",
    response_model=BenchmarkComparisonResponse,
    summary="Karşılaştırma raporu",
)
def get_benchmark_comparison(
    academic_year: str = Query(..., description="YYYY-YYYY"),
    period: MetricPeriod = Query(default=MetricPeriod.ANNUAL),
    framework_code: Optional[FrameworkCode] = Query(default=None),
    indicator_id: Optional[int] = Query(default=None, gt=0),
    scope: BenchmarkScope = Query(default=BenchmarkScope.ALL),
    db: Session = Depends(get_db),
) -> BenchmarkComparisonResponse:
    """Kurumu geçmiş yıllar, ulusal ortalama, benzer ve rakip kurumlarla karşılaştırır."""
    return build_comparison(
        db,
        academic_year=academic_year,
        period=period.value,
        framework_code=framework_code.value if framework_code else None,
        indicator_id=indicator_id,
        scope=scope.value,
    )


# ===========================================================================
# TREND
# ===========================================================================


@router.get(
    "/trends/{framework_code}",
    response_model=EvaluationTrendResponse,
    summary="Çerçevenin yıllara göre gelişimi",
)
def get_framework_trend(
    framework_code: FrameworkCode,
    period: MetricPeriod = Query(default=MetricPeriod.ANNUAL),
    db: Session = Depends(get_db),
) -> EvaluationTrendResponse:
    """Kaydedilmiş değerlendirmelerden yıllara göre trend serisi üretir."""
    framework = _resolve_framework_by_code(db, framework_code.value)

    assessments: List[FrameworkAssessment] = list(
        db.execute(
            select(FrameworkAssessment)
            .where(FrameworkAssessment.framework_id == framework.id)
            .where(FrameworkAssessment.period == period.value)
            .order_by(FrameworkAssessment.academic_year)
        )
        .scalars()
        .all()
    )

    points: List[EvaluationTrendPoint] = []
    previous_performance: Optional[Decimal] = None
    previous_readiness: Optional[Decimal] = None

    for assessment in assessments:
        points.append(
            EvaluationTrendPoint(
                academic_year=assessment.academic_year,
                period=MetricPeriod(assessment.period),
                readiness_score=assessment.readiness_score,
                performance_score=assessment.performance_score,
                compliance_score=assessment.compliance_score,
                risk_level=EvaluationRiskLevel(assessment.risk_level),
                performance_change=(
                    None
                    if previous_performance is None
                    else quantize(assessment.performance_score - previous_performance)
                ),
                readiness_change=(
                    None
                    if previous_readiness is None
                    else quantize(assessment.readiness_score - previous_readiness)
                ),
            )
        )
        previous_performance = assessment.performance_score
        previous_readiness = assessment.readiness_score

    # --- Genel yön ---
    direction: str = "stable"
    message: str = "Trend hesaplamak için en az iki değerlendirme gerekiyor."
    if len(points) >= 2:
        change: Decimal = points[-1].performance_score - points[0].performance_score
        if change > TREND_STABILITY_POINTS:
            direction = "increasing"
            message = (
                f"Performans skoru {points[0].academic_year} döneminden bu yana "
                f"{quantize(change)} puan yükseldi."
            )
        elif change < -TREND_STABILITY_POINTS:
            direction = "decreasing"
            message = (
                f"Performans skoru {points[0].academic_year} döneminden bu yana "
                f"{quantize(abs(change))} puan geriledi."
            )
        else:
            message = "Performans skoru son dönemlerde belirgin bir değişim göstermiyor."
    elif len(points) == 1:
        message = "Yalnızca tek dönem verisi var; trend hesaplanamadı."
    elif not points:
        message = (
            f"'{framework_code.value}' çerçevesi için kaydedilmiş değerlendirme yok. "
            "Önce assessments/calculate çağrılmalıdır."
        )

    return EvaluationTrendResponse(
        framework_code=framework.code,
        framework_name=framework.name,
        point_count=len(points),
        points=points,
        overall_direction=direction,
        message=message,
    )


# ===========================================================================
# SENARYO ETKİSİ
# ===========================================================================


@router.post(
    "/impact-preview",
    response_model=ImpactPreviewResponse,
    summary="Senaryo değişkenlerinin skorlara etkisi (kayıt oluşturmaz)",
)
def impact_preview(
    payload: ImpactPreviewRequest, db: Session = Depends(get_db)
) -> ImpactPreviewResponse:
    """Yayın, atıf, personel gibi değişkenlerin skorlara etkisini hesaplar.

    Veritabanına hiçbir kayıt yazmaz ve mevcut gösterge değerlerini değiştirmez.
    UYARI: Gerçek sıralama tahmini yapmaz.
    """
    return build_impact_preview(db, payload)


# ===========================================================================
# DASHBOARD
# ===========================================================================


@router.get(
    "/dashboard-summary",
    response_model=DashboardSummaryResponse,
    summary="Modül 10 genel bakış paneli",
)
def get_dashboard_summary(
    academic_year: Optional[str] = Query(default=None, description="YYYY-YYYY"),
    period: MetricPeriod = Query(default=MetricPeriod.ANNUAL),
    db: Session = Depends(get_db),
) -> DashboardSummaryResponse:
    """Tüm çerçevelerin özet durumunu, eksik verileri ve öncelikli önerileri döndürür."""
    frameworks: List[EvaluationFramework] = list(
        db.execute(
            select(EvaluationFramework)
            .where(EvaluationFramework.is_active.is_(True))
            .order_by(EvaluationFramework.code)
        )
        .scalars()
        .all()
    )

    # Yıl verilmezse en güncel değerlendirme yılı kullanılır.
    resolved_year: Optional[str] = academic_year
    if resolved_year is None:
        resolved_year = db.execute(
            select(func.max(FrameworkAssessment.academic_year))
        ).scalar()
    if resolved_year is None:
        resolved_year = db.execute(
            select(func.max(InstitutionalMetricValue.academic_year))
        ).scalar()

    # --- Sayaçlar (tek sorgu grubu) ---
    dimension_count: int = int(
        db.execute(select(func.count(EvaluationDimension.id))).scalar() or 0
    )
    indicator_count: int = int(
        db.execute(select(func.count(EvaluationIndicator.id))).scalar() or 0
    )
    metric_count: int = int(
        db.execute(select(func.count(InstitutionalMetricValue.id))).scalar() or 0
    )
    institution_count: int = int(
        db.execute(select(func.count(BenchmarkInstitution.id))).scalar() or 0
    )

    rows: List[FrameworkSummaryRow] = []
    readiness_values: List[Decimal] = []
    performance_values: List[Decimal] = []
    compliance_values: List[Decimal] = []
    all_missing = []
    all_recommendations: List[RecommendationItem] = []

    risk_order = {
        EvaluationRiskLevel.LOW: 0,
        EvaluationRiskLevel.MEDIUM: 1,
        EvaluationRiskLevel.HIGH: 2,
        EvaluationRiskLevel.CRITICAL: 3,
    }
    highest_risk: EvaluationRiskLevel = EvaluationRiskLevel.LOW

    for framework in frameworks:
        framework_indicator_count: int = int(
            db.execute(
                select(func.count(EvaluationIndicator.id))
                .join(
                    EvaluationDimension,
                    EvaluationIndicator.dimension_id == EvaluationDimension.id,
                )
                .where(EvaluationDimension.framework_id == framework.id)
            ).scalar()
            or 0
        )

        row = FrameworkSummaryRow(
            framework_id=framework.id,
            framework_code=framework.code,
            framework_name=framework.name,
            methodology_year=framework.methodology_year,
            academic_year=resolved_year,
            total_indicator_count=framework_indicator_count,
        )

        if resolved_year:
            detail = _build_detail_with_recommendations(
                db, framework, resolved_year, period.value
            )
            row.readiness_score = detail.readiness_score
            row.performance_score = detail.performance_score
            row.compliance_score = detail.compliance_score
            row.risk_level = detail.risk_level
            row.missing_indicator_count = detail.missing_indicator_count

            # Kaydedilmiş bir değerlendirme var mı?
            row.has_assessment = (
                db.execute(
                    select(func.count(FrameworkAssessment.id))
                    .where(FrameworkAssessment.framework_id == framework.id)
                    .where(FrameworkAssessment.academic_year == resolved_year)
                    .where(FrameworkAssessment.period == period.value)
                ).scalar()
                or 0
            ) > 0

            readiness_values.append(detail.readiness_score)
            performance_values.append(detail.performance_score)
            compliance_values.append(detail.compliance_score)
            all_missing.extend(detail.missing_data.items)
            all_recommendations.extend(detail.recommendations)

            if risk_order[detail.risk_level] > risk_order[highest_risk]:
                highest_risk = detail.risk_level

        rows.append(row)

    def _average(values: List[Decimal]) -> Decimal:
        """Listenin ortalamasını güvenli biçimde hesaplar."""
        if not values:
            return ZERO
        return quantize(sum(values, ZERO) / Decimal(len(values)))

    # En yüksek readiness kaybına yol açan eksik veriler öne çıkarılır.
    all_missing.sort(key=lambda item: item.estimated_readiness_loss, reverse=True)

    urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_recommendations.sort(
        key=lambda item: (
            urgency_order[item.urgency.value],
            -item.expected_score_gain,
        )
    )

    return DashboardSummaryResponse(
        academic_year=resolved_year,
        period=period,
        framework_count=len(frameworks),
        dimension_count=dimension_count,
        indicator_count=indicator_count,
        metric_value_count=metric_count,
        benchmark_institution_count=institution_count,
        average_readiness_score=_average(readiness_values),
        average_performance_score=_average(performance_values),
        average_compliance_score=_average(compliance_values),
        highest_risk_level=highest_risk,
        frameworks=rows,
        top_missing_data=all_missing[:10],
        top_recommendations=all_recommendations[:10],
    )
