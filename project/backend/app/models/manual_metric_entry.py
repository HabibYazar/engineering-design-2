"""Kapsam ve dönem bağlı, kaynağı açıkça işaretlenen manuel göstergeler.

Bu tablo içe aktarılan yetkili veri tablolarından bilinçli olarak ayrıdır.
Manuel bir kayıt, kaynak tablosundaki satırı değiştirmez; çözümleme servisi
yetkili veri varsa onu seçer ve manuel yazmayı reddeder.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.decimal_types import MoneyType
from app.database import Base


class ManualMetricEntry(Base):
    """Tek metrik × tam kapsam × akademik yıl için kullanıcı girişi."""

    __tablename__ = "manual_metric_entries"
    __table_args__ = (
        Index(
            "ix_manual_metric_lookup",
            "metric_key",
            "academic_year",
            "scope_type",
            "faculty_id",
            "department_id",
            "program_id",
            "is_active",
        ),
        Index(
            "uq_manual_metric_active_identity", "identity_key", unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    metric_label: Mapped[str] = mapped_column(String(160), nullable=False)
    screen_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)

    # Kapsamın türü ve bütün soy kimlikleri birlikte saklanır. Örneğin program
    # kaydı program_id yanında kendi bölüm/fakülte kimliğini de taşır; böylece
    # tutarsız bir kombinasyon veritabanında sessizce anlam değiştiremez.
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    faculty_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("faculties.id"), nullable=True, index=True
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )
    program_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_programs.id"), nullable=True, index=True
    )
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)

    # İlk hedeflerin tümü sayısal olsa da altyapı sonraki metin göstergelerini
    # destekler. Servis, kayıt defterindeki veri tipine göre yalnızca birini
    # doldurur; NULL hiçbir zaman sıfıra çevrilmez.
    numeric_value: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    text_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ManualMetricEntryAudit(Base):
    """Manuel göstergenin basit, ekleme-only değişiklik izi."""

    __tablename__ = "manual_metric_entry_audits"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("manual_metric_entries.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    old_value_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
