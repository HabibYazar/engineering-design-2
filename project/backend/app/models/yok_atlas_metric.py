"""YÖK Atlas Ankara program benchmark metrics.

This table is deliberately separate from official registered-headcount and
internal YKS tables.  A row is one source program code, one source year and
one metric.  Keeping the source grain makes scholarship/language variants,
provenance and deterministic de-duplication inspectable without presenting a
placed-student cohort as an official registered headcount.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class YokAtlasBenchmarkMetric(Base):
    """A normalized, secondary YÖK Atlas metric with full provenance."""

    __tablename__ = "yok_atlas_benchmark_metrics"

    __table_args__ = (
        UniqueConstraint(
            "source_file",
            "source_program_code",
            "source_year",
            "metric",
            name="uq_yok_atlas_source_metric",
        ),
        Index(
            "ix_yok_atlas_program_period",
            "canonical_program_key",
            "academic_year",
        ),
        Index(
            "ix_yok_atlas_faculty_period",
            "faculty_name",
            "academic_year",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Source identity.  These are source labels, never hierarchy entities in
    # our own university tables.
    university_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    faculty_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    canonical_faculty_key: Mapped[Optional[str]] = mapped_column(
        String(180), nullable=True, index=True
    )
    program_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_program_key: Mapped[str] = mapped_column(
        String(180), nullable=False, index=True
    )
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    university_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    program_language: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    scholarship_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    source_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Period and normalized metric.
    source_year: Mapped[int] = mapped_column(nullable=False, index=True)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    metric: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # The source contains binary-exported score decimals with up to 14-15
    # places. Preserve those values; presentation rounds separately.
    value: Mapped[Decimal] = mapped_column(Numeric(30, 15), nullable=False)
    # Exact original cell text. Numeric storage may normalize scale, but the
    # source representation remains available byte-for-byte for audit.
    source_raw_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)

    # Provenance and methodology.
    source_dataset: Mapped[str] = mapped_column(String(120), nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_program_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_university_code: Mapped[Optional[str]] = mapped_column(
        String(180), nullable=True
    )
    source_row_identity: Mapped[str] = mapped_column(Text, nullable=False)
    derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    methodology: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<YokAtlasBenchmarkMetric({self.university_name!r} "
            f"{self.source_program_code} {self.source_year} {self.metric}="
            f"{self.value})>"
        )
