"""Modül 5 — Fiziksel kaynak ve kapasite şemaları."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PhysicalFacilityBase(BaseModel):
    """Mekân oluşturma ve güncellemede ortak alanlar."""

    code: str = Field(min_length=1, max_length=50, examples=["A101"])
    name: str = Field(min_length=2, max_length=255, examples=["A Blok 101 Dersliği"])
    facility_type: str = Field(examples=["classroom"])
    department_id: Optional[int] = Field(default=None, ge=1, examples=[1])

    # Kapasite doluluk oranında payda olduğu için sıfır kabul edilmiyor.
    capacity: int = Field(ge=1, examples=[40])
    occupied: int = Field(default=0, ge=0, examples=[35])
    area_square_meters: Optional[int] = Field(default=None, ge=1, examples=[68])

    @model_validator(mode="after")
    def check_occupied_not_above_capacity(self) -> "PhysicalFacilityBase":
        """Doluluk kapasiteyi aşamaz.

        Aşarsa doluluk oranı %100'ün üzerine çıkar ve "aşırı dolu mekân" raporu
        anlamsız hale gelir; bu yüzden veri girişinde engelleniyor.
        """
        # Envanterden gelen kayıtta ölçüm olmayabilir; None karşılaştırma
        # yapılmaz. Kural yalnızca İKİ değer de biliniyorken uygulanır.
        if self.occupied is None or self.capacity is None:
            return self
        if self.occupied > self.capacity:
            raise ValueError(
                f"Doluluk ({self.occupied}) kapasiteden ({self.capacity}) büyük olamaz."
            )
        return self


class PhysicalFacilityCreate(PhysicalFacilityBase):
    """Yeni mekân kaydı."""


class PhysicalFacilityUpdate(BaseModel):
    """Kısmi güncelleme."""

    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    facility_type: Optional[str] = None
    department_id: Optional[int] = Field(default=None, ge=1)
    capacity: Optional[int] = Field(default=None, ge=1)
    occupied: Optional[int] = Field(default=None, ge=0)
    area_square_meters: Optional[int] = Field(default=None, ge=1)


class PhysicalFacilityResponse(PhysicalFacilityBase):
    """Mekân kaydının API cevabı."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    department_name: Optional[str] = None
    faculty_name: Optional[str] = None
    faculty_id: Optional[int] = Field(default=None, examples=[4])
    # --- DERSLİK ENVANTERİ (part3) ---
    # Ölçülmemiş değerler None döner; 0 "boş derslik" demek olurdu.
    student_capacity: Optional[int] = Field(default=None, examples=[83])
    floor: Optional[int] = Field(default=None, examples=[0])
    owner_label: Optional[str] = Field(default=None, examples=["MMF-Lab"])
    room_label: Optional[str] = Field(default=None, examples=["BİLG 4"])
    capacity: Optional[int] = Field(default=None, examples=[85])
    occupied: Optional[int] = Field(default=None, examples=[62])
    occupancy_percent: Optional[float] = Field(default=None, examples=[87.5])
    occupancy_status: str = Field(
        description="Doluluk oranının eşiklere göre sınıfı.",
        examples=["yeterli"],
    )
    is_active: bool


class UtilizationByTypeItem(BaseModel):
    """Tesis türüne göre kullanım oranı."""

    facility_type: str = Field(examples=["classroom"])
    facility_count: int = Field(examples=[4])
    total_capacity: Optional[int] = Field(default=None, examples=[180])
    total_student_capacity: Optional[int] = Field(default=None, examples=[150])
    total_occupied: Optional[int] = Field(default=None, examples=[130])
    average_utilization_percent: Optional[float] = Field(default=None,
                                                         examples=[72.22])


class AllocationByDepartmentItem(BaseModel):
    """Bölüm bazlı alan dağılımı."""

    department_name: str = Field(examples=["Bilgisayar Mühendisliği"])
    faculty_name: str = Field(examples=["Mühendislik Fakültesi"])
    facility_count: int = Field(examples=[3])
    total_capacity: Optional[int] = Field(default=None, examples=[80])
    total_student_capacity: Optional[int] = Field(default=None, examples=[70])
    total_area_square_meters: Optional[int] = Field(default=None, examples=[210])


class SpacePerPersonResponse(BaseModel):
    """Kişi başına düşen kapasite.

    Öğrenci ve personel sayıları sabit değil, veritabanındaki aktif kayıtlardan
    sayılır; aksi halde rapor gerçek durumu yansıtmaz.
    """

    total_capacity: Optional[int] = Field(default=None, examples=[452])
    total_area_square_meters: Optional[int] = Field(default=None, examples=[1180])
    active_student_count: int = Field(examples=[240])
    active_staff_count: int = Field(examples=[12])
    capacity_per_student: Optional[float] = Field(default=None, examples=[1.88])
    capacity_per_staff: Optional[float] = Field(default=None, examples=[37.67])
    note: str = Field(
        examples=["Öğrenci ve personel sayıları veritabanındaki aktif kayıtlardan alındı."]
    )


class FacilityFlagItem(BaseModel):
    """Az kullanılan / aşırı dolu mekân satırı."""

    id: int = Field(examples=[4])
    code: str = Field(examples=["D110"])
    name: str = Field(examples=["D Blok 110 Dersliği"])
    facility_type: str = Field(examples=["classroom"])
    department_name: Optional[str] = Field(default=None, examples=["Mimarlık"])
    capacity: Optional[int] = Field(default=None, examples=[50])
    occupied: Optional[int] = Field(default=None, examples=[22])
    occupancy_percent: Optional[float] = Field(default=None, examples=[44.0])


class CapacityForecastResponse(BaseModel):
    """Öğrenci artışının kapasiteye etkisi."""

    expected_growth_percent: float = Field(examples=[10.0])
    current_capacity: int = Field(examples=[452])
    current_occupied: int = Field(examples=[329])
    projected_occupied: float = Field(examples=[361.9])
    projected_occupancy_percent: float = Field(examples=[80.07])
    is_sufficient: bool = Field(examples=[True])
    shortfall: float = Field(
        description="Projeksiyon kapasiteyi aşarsa eksik kalan yer sayısı.",
        examples=[0.0],
    )
    assessment: str = Field(examples=["Mevcut kapasite öngörülen artışı karşılıyor."])


class CapacityOverview(BaseModel):
    """Modül 5 özet göstergeleri."""

    total_facilities: int = Field(examples=[9])
    # ÖLÇÜLMEMİŞ GÖSTERGE None DÖNER. Derslik envanterinde kullanım
    # ölçümü yoktur; 0 göndermek bütün derslikleri boş gösterirdi.
    total_capacity: Optional[int] = Field(default=None, examples=[452])
    capacity_measured_count: Optional[int] = Field(default=None, examples=[9])
    #: Ders planlamasında kullanılabilir öğrenci kapasitesi (part3).
    total_student_capacity: Optional[int] = Field(default=None, examples=[3045])
    student_capacity_measured_count: Optional[int] = Field(default=None,
                                                           examples=[9])
    total_occupied: Optional[int] = Field(default=None, examples=[329])
    occupancy_measured_count: Optional[int] = Field(default=None, examples=[0])
    overall_occupancy_percent: Optional[float] = Field(default=None,
                                                       examples=[72.79])
    underutilized_count: Optional[int] = Field(default=None, examples=[2])
    overcrowded_count: Optional[int] = Field(default=None, examples=[3])
    by_type: List[UtilizationByTypeItem]
