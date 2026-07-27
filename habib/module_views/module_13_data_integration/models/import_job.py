"""İçe aktarma işlemlerinin geçmişini tutan (ImportJob) veritabanı modeli."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportJob(Base):
    """Yapılan her içe aktarma (veya ön izleme) denemesinin kaydını tutar."""

    # Bu tabloyu tutmamızın sebebi: hangi dosyanın ne zaman, kim tarafından ve
    # hangi sonuçla yüklendiği sonradan sorgulanabilsin. Hatalı bir aktarım olduğunda
    # geriye dönük inceleme yapmak için gerekli.
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Hangi kaynağa aktarım yapıldı (faculties, departments, programs, administrative-units).
    resource_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # preview=True ise veritabanına yazılmadı, sadece deneme yapıldı demektir.
    preview: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Sayısal özet alanları: raporun aynısı burada da saklanır ki
    # geçmiş listelenirken dosyayı tekrar okumaya gerek kalmasın.
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conflict_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # status: preview | completed | partial | skipped | failed
    # "partial" bazı satırların aktarılıp bazılarının atlandığını,
    # "skipped" hiçbir satırın aktarılmadığını ama sistemsel bir hata olmadığını ifade eder.
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)

    # Kısa hata özeti; detaylı satır listesi cevapta döndürülür, burada sadece not tutulur.
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Nesnenin okunabilir metin gösterimini döndürür."""
        return f"<ImportJob(id={self.id}, resource='{self.resource_type}', status='{self.status}')>"
