"""Üniversite-sanayi iş birliği ve bölgesel katkı kayıtları.

Bu iki gösterge daha önce KPI tablosunda elle girilmiş tek bir sayıydı ve
hangi veriden geldiği belli değildi. Artık ölçülebilir alt bileşenler kayıt
olarak saklanıyor ve KPI değeri bunlardan formülle hesaplanıyor.

Sayılar oran olarak değil ADET/TUTAR olarak saklanır; oranı saklamak, payda
değiştiğinde kaydı geçersiz kılardı ve doğrulanamaz hale getirirdi.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.decimal_types import MoneyType
from app.database import Base

if TYPE_CHECKING:
    from app.models.faculty import Faculty


class IndustryCollaborationRecord(Base):
    """Bir fakültenin bir akademik yıldaki sanayi iş birliği göstergeleri."""

    __tablename__ = "industry_collaboration_records"
    __table_args__ = (
        UniqueConstraint("faculty_id", "academic_year", name="uq_industry_faculty_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculties.id"), nullable=False, index=True
    )
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    active_partnerships: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    joint_projects: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Sanayi destekli araştırma bütçesi, milyon USD.
    funded_research_musd: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    intern_students: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    signed_protocols: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    faculty: Mapped["Faculty"] = relationship("Faculty")


class RegionalContributionRecord(Base):
    """Üniversite genelinin bir akademik yıldaki bölgesel katkı göstergeleri.

    Fakülte kırılımı yok: bölgesel katkının çoğu bileşeni (belediye iş birliği,
    halka açık etkinlik) kurum düzeyinde yürütülür ve fakülteye pay etmek
    uydurma bir dağıtım olurdu.
    """

    __tablename__ = "regional_contribution_records"
    __table_args__ = (
        UniqueConstraint("academic_year", name="uq_regional_contribution_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    academic_year: Mapped[str] = mapped_column(
        String(9), nullable=False, index=True
    )

    graduates_employed_in_region: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    local_public_projects: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    municipality_partnerships: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    community_service_hours: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    regional_sme_collaborations: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    public_events_hosted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
