"""Senaryo (Scenario) veritabanı modeli."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_input import ScenarioInput
    from app.models.scenario_result import ScenarioResult


class Scenario(Base):
    """Yöneticinin oluşturduğu "ya olursa" senaryosunun başlık kaydı.

    Senaryonun kendisi sadece bir kapsayıcıdır; girilen değerler ScenarioInput,
    hesaplanan sonuçlar ise ScenarioResult tablolarında tutulur. Bu ayrım sayesinde
    aynı senaryo farklı parametrelerle tekrar tekrar çalıştırılıp sonuçlar karşılaştırılabilir.
    """

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # scenario_type: student-enrollment, tuition-scholarship, academic-staffing,
    # investment, research-strategy, economic-risk, combined
    # Değer doğrulaması Pydantic Enum ile yapıldığı için burada serbest metin tutuyoruz.
    scenario_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # status: draft (henüz çalıştırılmadı) | simulated (en az bir kez hesaplandı) | archived
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Bir senaryonun birden fazla girdi ve sonuç kaydı olabilir (her simülasyon bir tane üretir).
    # cascade: Senaryo silinirse ona ait girdi ve sonuçlar da temizlenir.
    inputs: Mapped[List["ScenarioInput"]] = relationship(
        "ScenarioInput", back_populates="scenario", cascade="all, delete-orphan"
    )
    results: Mapped[List["ScenarioResult"]] = relationship(
        "ScenarioResult", back_populates="scenario", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<Scenario(id={self.id}, name='{self.name}', type='{self.scenario_type}')>"
