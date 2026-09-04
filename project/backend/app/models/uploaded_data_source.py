"""Kullanıcı dosyaları ve onlardan üretilen ikincil metrik kayıtları."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.decimal_types import MoneyType
from app.database import Base


class UploadedDataSource(Base):
    """Yüklenmiş dosyanın değişmez kimliği ve içe aktarma özeti."""

    __tablename__ = "uploaded_data_sources"
    __table_args__ = (
        Index(
            "uq_uploaded_source_active_checksum",
            "checksum_sha256",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    selected_sheet: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    selected_table: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="uploaded", nullable=False, index=True)
    source_label: Mapped[str] = mapped_column(
        String(120), default="Kullanıcı veri kaynağı", nullable=False
    )
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    mapping_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scope_type: Mapped[str] = mapped_column(String(20), default="university", nullable=False)
    faculty_id: Mapped[Optional[int]] = mapped_column(ForeignKey("faculties.id"), nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)
    program_id: Mapped[Optional[int]] = mapped_column(ForeignKey("academic_programs.id"), nullable=True)
    academic_year: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)

    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmatched_row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    imported_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UploadedMetricRecord(Base):
    """Yetkili tablolardan ayrı, dosya satırına kadar izlenebilir metrik."""

    __tablename__ = "uploaded_metric_records"
    __table_args__ = (
        Index(
            "ix_uploaded_metric_resolution",
            "metric_key", "academic_year", "scope_type", "faculty_id",
            "department_id", "program_id", "is_active",
        ),
        Index(
            "uq_uploaded_metric_source_row",
            "uploaded_source_id", "metric_key", "original_row_number",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    uploaded_source_id: Mapped[int] = mapped_column(
        ForeignKey("uploaded_data_sources.id"), nullable=False, index=True
    )
    metric_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), default="metric", nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    faculty_id: Mapped[Optional[int]] = mapped_column(ForeignKey("faculties.id"), nullable=True)
    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"), nullable=True)
    program_id: Mapped[Optional[int]] = mapped_column(ForeignKey("academic_programs.id"), nullable=True)
    academic_staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_staff.id"), nullable=True, index=True
    )
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    numeric_value: Mapped[Optional[Decimal]] = mapped_column(MoneyType, nullable=True)
    text_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    original_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_values_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

