"""Akademik başarı kayıtları.

Program × akademik yıl kırılımında ders geçme, kalma, bırakma ve mezuniyet
oranlarını tutar.

Neden en alt kırılım program: fakülte ve bölüm oranları burada saklanmaz,
program satırlarından öğrenci sayısına göre ağırlıklı ortalamayla hesaplanır.
Fakülte oranı ayrıca saklansaydı, bir program verisi güncellendiğinde fakülte
satırı eskimiş kalır ve iki ekran farklı sayı gösterirdi.
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
    from app.models.academic_program import AcademicProgram


class AcademicSuccessRecord(Base):
    """Bir programın bir akademik yıldaki başarı göstergeleri."""

    __tablename__ = "academic_success_records"
    __table_args__ = (
        UniqueConstraint(
            "academic_program_id", "academic_year", name="uq_academic_success_program_year"
        ),
    )

    # Oran sınırı (0-100) neden veritabanı CHECK kısıtı DEĞİL:
    # Projede para ve oran alanları MoneyType ile saklanır ve MoneyType
    # Decimal'i TEXT olarak yazar (float yuvarlamasını önlemek için). SQLite
    # bir CHECK kısıtında metni sayıyla karşılaştırırken tip önceliği uygular
    # ve '77.57' <= 100 ifadesi FALSE döner — yani geçerli veri reddedilir.
    # Bu yüzden sınır kontrolü Pydantic şemasında (ge=0, le=100) ve
    # doğrulama servisinde yapılır; ikisi de testle kapsanmıştır.
    RATE_MIN: Decimal = Decimal("0")
    RATE_MAX: Decimal = Decimal("100")

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    academic_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=False, index=True
    )
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    # Ölçümün dayandığı öğrenci sayısı. Ağırlıklı ortalamanın ağırlığı budur;
    # bu alan olmadan fakülte ortalaması yanlış hesaplanırdı (küçük bir program
    # büyük bir programla aynı ağırlığa sahip olurdu).
    measured_student_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Ders geçme oranı. Kalma oranı ayrı saklanmaz; 100 - geçme olarak türetilir
    # ki ikisinin toplamı her zaman 100 etsin.
    course_pass_rate: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    # 0-100 arası ortalama başarı puanı.
    average_success_score: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    dropout_rate: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    graduation_rate: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)

    graduate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    academic_program: Mapped["AcademicProgram"] = relationship("AcademicProgram")

    @property
    def course_fail_rate(self) -> Decimal:
        """Ders kalma oranı. Geçme oranından türetilir; ikisi toplamı 100'dür."""
        return Decimal("100") - self.course_pass_rate
