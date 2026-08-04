"""Modül 8 — Kurumsal performans (KPI) izleme şemaları."""

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KpiFacultyValueItem(BaseModel):
    """Bir KPI'nın tek fakülteye ait değeri."""

    faculty_id: int = Field(ge=1, examples=[1])
    faculty_name: Optional[str] = Field(default=None, examples=["Mühendislik Fakültesi"])
    value: Decimal = Field(examples=[Decimal("4.20")])


class KpiFacultyValueInput(BaseModel):
    """Fakülte kırılımı girişi."""

    faculty_id: int = Field(ge=1, examples=[1])
    value: Decimal = Field(examples=[Decimal("4.20")])


class StrategicKpiCreate(BaseModel):
    """Yeni KPI tanımlar."""

    name: str = Field(min_length=3, max_length=255, examples=["Ders değerlendirme puanı (/5)"])
    dimension: str = Field(min_length=2, max_length=120, examples=["Eğitim ve Öğretim Kalitesi"])
    unit: Optional[str] = Field(default=None, max_length=40, examples=["puan"])
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$", examples=["2025-2026"])

    current_value: Decimal = Field(ge=0, examples=[Decimal("4.10")])
    # Hedef sıfır olamaz: başarı oranının paydası.
    target_value: Decimal = Field(gt=0, examples=[Decimal("4.30")])
    previous_value: Optional[Decimal] = Field(default=None, ge=0, examples=[Decimal("4.00")])
    university_average: Optional[Decimal] = Field(default=None, ge=0, examples=[Decimal("3.90")])

    on_track_threshold: Decimal = Field(default=Decimal("90"), gt=0, le=200, examples=[Decimal("90")])
    at_risk_threshold: Decimal = Field(default=Decimal("70"), gt=0, le=200, examples=[Decimal("70")])

    corrective_action: Optional[str] = Field(
        default=None, examples=["Mevcut öğretim destek programları sürdürülecek."]
    )
    faculty_values: List[KpiFacultyValueInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_thresholds(self) -> "StrategicKpiCreate":
        """Hedefte eşiği risk eşiğinden büyük olmalı.

        Ters girilirse hiçbir KPI "gecikmeli" bandına düşemez ve ara durum
        sessizce kaybolur; bu yüzden veri girişinde engelleniyor.
        """
        if self.on_track_threshold <= self.at_risk_threshold:
            raise ValueError(
                "on_track_threshold, at_risk_threshold değerinden büyük olmalı."
            )
        return self


class StrategicKpiUpdate(BaseModel):
    """KPI tanımını veya eşiklerini günceller."""

    dimension: Optional[str] = Field(default=None, min_length=2, max_length=120)
    unit: Optional[str] = Field(default=None, max_length=40)
    target_value: Optional[Decimal] = Field(default=None, gt=0)
    previous_value: Optional[Decimal] = Field(default=None, ge=0)
    university_average: Optional[Decimal] = Field(default=None, ge=0)
    on_track_threshold: Optional[Decimal] = Field(default=None, gt=0, le=200)
    at_risk_threshold: Optional[Decimal] = Field(default=None, gt=0, le=200)
    corrective_action: Optional[str] = None


class KpiMeasurement(BaseModel):
    """Yeni ölçüm değeri kaydeder."""

    value: Decimal = Field(ge=0, examples=[Decimal("4.25")])


class StrategicKpiResponse(BaseModel):
    """KPI ve hesaplanmış durum bilgisi."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(examples=["Ders değerlendirme puanı (/5)"])
    dimension: str = Field(examples=["Eğitim ve Öğretim Kalitesi"])
    unit: Optional[str] = Field(default=None, examples=["puan"])
    academic_year: str = Field(examples=["2025-2026"])

    current_value: Decimal = Field(examples=[Decimal("4.10")])
    target_value: Decimal = Field(examples=[Decimal("4.30")])
    previous_value: Optional[Decimal] = Field(default=None, examples=[Decimal("4.00")])
    university_average: Optional[Decimal] = Field(default=None, examples=[Decimal("3.90")])

    achievement_percent: Decimal = Field(
        description="Mevcut değerin hedefe oranı.", examples=[Decimal("95.35")]
    )
    status: str = Field(
        description="hedefte / gecikmeli / riskli", examples=["hedefte"]
    )
    on_track_threshold: Decimal = Field(examples=[Decimal("90")])
    at_risk_threshold: Decimal = Field(examples=[Decimal("70")])

    change_vs_previous_percent: Optional[Decimal] = Field(
        default=None,
        description="Geçen yıla göre değişim. Geçmiş veri yoksa hesaplanmaz.",
        examples=[Decimal("2.50")],
    )
    gap_vs_university_average: Optional[Decimal] = Field(
        default=None,
        description="Üniversite ortalamasından fark.",
        examples=[Decimal("0.20")],
    )
    corrective_action: Optional[str] = None
    faculty_values: List[KpiFacultyValueItem] = Field(default_factory=list)
    is_active: bool


class KpiDimensionSummary(BaseModel):
    """Stratejik boyut bazında özet."""

    dimension: str = Field(examples=["Eğitim ve Öğretim Kalitesi"])
    kpi_count: int = Field(examples=[3])
    average_achievement_percent: Decimal = Field(examples=[Decimal("92.40")])
    on_track_count: int = Field(examples=[2])
    delayed_count: int = Field(examples=[1])
    at_risk_count: int = Field(examples=[0])


class KpiScorecard(BaseModel):
    """Modül 8 karne özeti."""

    academic_year: str = Field(examples=["2025-2026"])
    total_kpis: int = Field(examples=[14])
    on_track_count: int = Field(examples=[6])
    delayed_count: int = Field(examples=[5])
    at_risk_count: int = Field(examples=[3])
    overall_achievement_percent: Decimal = Field(examples=[Decimal("88.70")])
    overall_status: str = Field(examples=["gecikmeli"])
    by_dimension: List[KpiDimensionSummary]


class KpiFacultyComparisonItem(BaseModel):
    """Fakülte bazlı KPI performansı."""

    faculty_id: int = Field(examples=[1])
    faculty_name: str = Field(examples=["Mühendislik Fakültesi"])
    measured_kpi_count: int = Field(examples=[8])
    average_achievement_percent: Decimal = Field(examples=[Decimal("94.10")])
    kpis_above_university_average: int = Field(examples=[5])
