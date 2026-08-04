"""Bölüm (Department) veritabanı modeli."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.academic_program import AcademicProgram
    from app.models.faculty import Faculty


class Department(Base):
    """Bir fakülteye bağlı akademik bölümleri temsil eden model."""

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Foreign key: Her bölüm mutlaka bir fakülteye bağlıdır.
    # Bu kısıt sayesinde veritabanı seviyesinde de bağlantı garanti altına alınır.
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculties.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Many-to-one: Bölümden bağlı olduğu fakülteye erişim.
    faculty: Mapped["Faculty"] = relationship("Faculty", back_populates="departments")

    # One-to-many: Bir bölümün birden fazla akademik programı olabilir.
    programs: Mapped[List["AcademicProgram"]] = relationship(
        "AcademicProgram",
        back_populates="department",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<Department(id={self.id}, code='{self.code}')>"
