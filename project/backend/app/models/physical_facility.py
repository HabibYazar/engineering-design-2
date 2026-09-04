"""Fiziksel mekân/tesis (Modül 5) veritabanı modeli.

Entegrasyon notu: Eda'nın orijinal kodunda hem `Facility` hem `Classroom` sınıfı
vardı ve `Classroom` alanları `Facility`'nin alt kümesiydi. İki tablo tutmak aynı
derslik için iki farklı doluluk değeri saklanmasına yol açacağı için tek tabloda
birleştirildi; derslikler `facility_type == "classroom"` ile filtreleniyor.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.faculty import Faculty

# Desteklenen tesis türleri. Serbest metin yerine sabit liste kullanılıyor ki
# tür bazlı kullanım oranı raporu her zaman aynı grupları üretsin.
FACILITY_TYPES = ("classroom", "laboratory", "office", "library", "other")


class PhysicalFacility(Base):
    """Derslik, laboratuvar, ofis ve benzeri fiziksel mekânları temsil eder."""

    __tablename__ = "physical_facilities"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Mekân kodu ("A101", "Lab-1"). Kampüs genelinde tekil olduğu için unique.
    code: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    facility_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Ortak kullanım alanları (kütüphane, konferans salonu) hiçbir bölüme ait
    # olmayabilir; bu yüzden nullable bırakıldı.
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id"), nullable=True, index=True
    )

    # FİZİKSEL oturma kapasitesi (kaynakta "SINIF KAPASİTESİ").
    #
    # NULL OLABİLİR. Gerçek envanterde bazı mekânların (ör. film stüdyosu)
    # kapasitesi ölçülmemiştir. 0 yazmak "kapasitesi yok" demek olurdu;
    # ölçülmemiş kapasite doluluk hesabına GİRMEZ.
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    #: DERS PLANLAMASINDA kullanılabilir öğrenci kapasitesi (kaynakta
    #: "ÖĞRENCİ KAPASİTESİ"). Fiziksel kapasiteden küçüktür: laboratuvar
    #: tezgâhı, stüdyo ekipmanı, engelli erişimi gibi kısıtlar yüzünden
    #: her koltuk derste kullanılamaz. Kapasite planlaması bu sayıyı
    #: kullanır, `capacity` ise binanın gerçek büyüklüğünü gösterir.
    student_capacity: Mapped[Optional[int]] = mapped_column(Integer,
                                                            nullable=True)

    # Fiilen kullanılan yer sayısı. ÖLÇÜM GEREKTİRİR; envanter dosyası
    # bunu içermez, bu yüzden NULL olabilir ve NULL "sıfır kişi" DEĞİL
    # "ölçülmedi" demektir.
    occupied: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Metrekare bilgisi kişi başına düşen alan raporunda kullanılır; her mekân
    # için ölçüm girilmemiş olabileceğinden nullable.
    area_square_meters: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- DERSLİK ENVANTERİ (data/ekdata/part3) ---
    #
    # Derslikler BÖLÜME değil FAKÜLTEYE tahsis edilir: kaynak dosyadaki
    # sahiplik sütunu MMF / İTBF / GSTF / HF / MYO gibi birim kısaltmaları
    # taşır. `department_id` bu yüzden boş kalır; tahsis `faculty_id`
    # üzerinden kurulur ve kapsam süzmesi bunu kullanır.
    faculty_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("faculties.id"), nullable=True, index=True
    )

    #: Bina katı (0, 1, 2 …). Kaynakta "KAT : 0" blok başlığından gelir.
    floor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                                 index=True)

    #: Kaynaktaki HAM sahiplik etiketi ("MMF-Lab", "Hazırlık Okulu", "ANK").
    #: Akademik bir fakülteye çözülemeyen sahipler (Hazırlık Okulu gibi)
    #: kaydın DIŞLANMASINA yol açmaz; etiket burada korunur.
    owner_label: Mapped[Optional[str]] = mapped_column(String(60),
                                                       nullable=True, index=True)

    #: Mekânın kaynaktaki açıklaması ("Duruşma Salonu", "BİLG 4").
    room_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    source_dataset: Mapped[Optional[str]] = mapped_column(String(80),
                                                          nullable=True)
    source_file: Mapped[Optional[str]] = mapped_column(String(255),
                                                       nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    department: Mapped[Optional["Department"]] = relationship("Department")
    faculty: Mapped[Optional["Faculty"]] = relationship("Faculty")

    @property
    def occupancy_percent(self) -> Optional[float]:
        """Doluluk yüzdesi. Ölçülmemişse `None` — 0 DEĞİL.

        Daha önce ölçülmemiş doluluk 0.0 dönüyordu; bu, envanterden gelen
        (kullanım verisi olmayan) bir dersliği "tamamen boş" göstererek
        kapasite kararlarını yanıltırdı.
        """
        if not self.capacity or self.occupied is None:
            return None
        return round((self.occupied / self.capacity) * 100, 2)
