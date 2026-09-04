"""Kaynaklar arası ÇAKIŞMA kaydı.

NEDEN VAR
---------
Birden çok gerçek kaynak aynı varlığın aynı alanını farklı değerlerle
doldurabilir. Örneğin bir programın kontenjanı hem ÖSYM dosyasından hem
ileride yüklenecek bir öğrenci bilgi sistemi dosyasından gelebilir.

Kural: **ikinci kaynak birincinin değerini sessizce EZMEZ.** Bunun yerine
mevcut değer korunur ve çakışma bu tabloya yazılır. Böylece:

  * hangi alanın hangi kaynaktan geldiği izlenebilir,
  * "sayı neden değişti?" sorusunun cevabı veritabanında durur,
  * veri sahibi hangi kaynağın doğru olduğuna sonra karar verebilir.

Sessizce ezmek, kullanıcıya doğru görünen ama kaynağı belirsiz bir sayı
göstermek demektir; bu sistemin bütün tasarımına aykırıdır.

Bu tablo bir HATA KAYDI değil, bir VERİ YÖNETİŞİMİ kaydıdır: dolu olması
sistemin bozuk olduğu anlamına gelmez, birden çok kaynağın örtüştüğü
anlamına gelir.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DataSourceConflict(Base):
    """Aynı alan için iki farklı kaynağın farklı değer vermesi."""

    __tablename__ = "data_source_conflicts"

    __table_args__ = (
        # Aynı çakışma her aktarımda yeniden eklenmesin: aktarım
        # idempotent kalmalı.
        UniqueConstraint(
            "table_name",
            "record_id",
            "field_name",
            "incoming_source",
            name="uq_data_conflict",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # --- çakışmanın yeri ---
    table_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: İnsan tarafından okunabilir kimlik ("YAZILIM MÜHENDİSLİĞİ PR. · 2025").
    record_label: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # --- taraflar ---
    existing_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    existing_source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    incoming_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    incoming_source: Mapped[str] = mapped_column(String(200), nullable=False)

    #: Ne yapıldı: "kept_existing" (varsayılan) | "applied_incoming"
    #: Şu an yalnızca "kept_existing" üretiliyor; alan, ileride bir
    #: kaynak öncelik kuralı tanımlanırsa kararın kaydı olsun diye var.
    resolution: Mapped[str] = mapped_column(
        String(40), default="kept_existing", server_default="'kept_existing'",
        nullable=False,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DataSourceConflict({self.table_name}.{self.field_name} "
            f"#{self.record_id})>"
        )
