"""Üniversite-sanayi iş birliği ve bölgesel katkı endpoint'leri."""

from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import engagement_service as service

router = APIRouter(prefix="/api/engagement", tags=["Sanayi İş Birliği ve Bölgesel Katkı"])


class IndexComponent(BaseModel):
    """Endeksi oluşturan tek bileşen.

    Endeksin hangi bileşenden ne kadar geldiği görünsün diye ham değer,
    referans değer, ağırlık ve katkı ayrı ayrı döndürülür.
    """

    key: str = Field(examples=["joint_projects"])
    label: str = Field(examples=["Ortak proje sayısı"])
    unit: str = Field(examples=["adet"])
    value: Decimal = Field(description="Ölçülen ham değer", examples=[Decimal("29.00")])
    reference_value: Decimal = Field(
        description="Stratejik plan hedefi (normalizasyon tabanı)", examples=[Decimal("40.00")]
    )
    weight: Decimal = Field(description="Endeksteki ağırlığı", examples=[Decimal("0.25")])
    achievement_percent: Optional[Decimal] = Field(
        default=None, description="Değer / referans × 100", examples=[Decimal("72.50")]
    )
    contribution_to_index: Decimal = Field(
        description="Bu bileşenin endekse katkısı", examples=[Decimal("18.13")]
    )


class FacultyCollaborationRow(BaseModel):
    """Fakülte bazlı sanayi iş birliği ham verisi."""

    faculty_id: int
    faculty_name: str
    active_partnerships: int = Field(examples=[19])
    joint_projects: int = Field(examples=[18])
    funded_research_musd: Decimal = Field(
        description="Sanayi destekli araştırma bütçesi (milyon USD)", examples=[Decimal("1.62")]
    )
    intern_students: int = Field(examples=[134])
    signed_protocols: int = Field(examples=[11])


class IndexResponse(BaseModel):
    """Endeks sonucu ve bileşen kırılımı."""

    academic_year: str
    index_value: Decimal = Field(
        description="Ağırlıklı endeks. 100 = hedefe tam ulaşıldı, üstü hedefin aşıldığını gösterir.",
        examples=[Decimal("64.82")],
    )
    target_value: Decimal = Field(examples=[Decimal("75.00")])
    achievement_vs_target_percent: Optional[Decimal] = Field(
        default=None, examples=[Decimal("86.43")]
    )
    components: List[IndexComponent]
    weight_total: Decimal
    weight_warning: Optional[str] = Field(
        default=None,
        description="Ağırlık toplamı 1.00 değilse uyarı; endeks güvenilir değildir.",
    )


class IndustryCollaborationResponse(IndexResponse):
    """Sanayi iş birliği endeksi + fakülte kırılımı."""

    by_faculty: List[FacultyCollaborationRow]


class RegionalContributionResponse(IndexResponse):
    """Bölgesel katkı endeksi + istihdam oranı."""

    region: str = Field(examples=["İç Anadolu"])
    total_graduates: int = Field(
        description="Sistemdeki toplam mezun sayısı (oranın paydası)", examples=[748]
    )
    regional_employment_share_percent: Optional[Decimal] = Field(
        default=None,
        description=(
            "Bölgede istihdam edilen mezunların O YILIN toplam mezununa oranı. "
            "Oran %100'ü aşarsa veri tutarsız demektir ve null döner."
        ),
        examples=[Decimal("60.43")],
    )
    regional_employment_note: str = Field(
        default="", description="Oranın sade dille açıklaması veya hesaplanamama sebebi"
    )


class EngagementTrendPoint(BaseModel):
    """İki endeksin bir yıldaki değeri."""

    academic_year: str
    industry_collaboration_index: Optional[Decimal] = None
    regional_contribution_index: Optional[Decimal] = None


@router.get(
    "/industry-collaboration",
    response_model=IndustryCollaborationResponse,
    summary="Üniversite-sanayi iş birliği endeksi",
)
def get_industry_collaboration(
    academic_year: str = Query(examples=["2025-2026"]),
    db: Session = Depends(get_db),
) -> IndustryCollaborationResponse:
    """Beş ölçülebilir bileşenden ağırlıklı endeks üretir.

    Bileşenler: aktif iş birliği sayısı, ortak proje sayısı, sanayi destekli
    araştırma bütçesi, staj yapan öğrenci sayısı ve imzalanan protokol sayısı.
    Her bileşenin ham değeri ve endekse katkısı ayrı ayrı döndürülür.
    """
    return IndustryCollaborationResponse(
        **service.industry_collaboration(db, academic_year)
    )


@router.get(
    "/regional-contribution",
    response_model=RegionalContributionResponse,
    summary="Bölgesel katkı endeksi",
)
def get_regional_contribution(
    academic_year: str = Query(examples=["2025-2026"]),
    db: Session = Depends(get_db),
) -> RegionalContributionResponse:
    """Altı ölçülebilir bileşenden ağırlıklı endeks üretir.

    Bileşenler: bölgede istihdam edilen mezun sayısı, yerel kamu projesi,
    belediye iş birliği, toplum hizmeti saati, bölgesel KOBİ iş birliği ve
    halka açık etkinlik sayısı.
    """
    return RegionalContributionResponse(
        **service.regional_contribution(db, academic_year)
    )


@router.get(
    "/trend",
    response_model=List[EngagementTrendPoint],
    summary="İki endeksin yıllara göre gelişimi",
)
def get_trend(db: Session = Depends(get_db)) -> List[EngagementTrendPoint]:
    """Sanayi iş birliği ve bölgesel katkı endekslerinin zaman serisi."""
    return [EngagementTrendPoint(**row) for row in service.engagement_trend(db)]
