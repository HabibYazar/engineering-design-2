"""Modül 5 — Fiziksel kaynak ve kapasite endpoint'leri.

Entegrasyon notu: Eda'nın orijinal kodunda `/capacity` yolu hem
`classroom_routes.py` hem `capacity_routes.py` içinde tanımlıydı ve iki router
aynı uygulamaya eklendiği için ikincisi sessizce gölgede kalıyordu. Burada tek
router kullanılarak bu belirsizlik ortadan kaldırıldı.
"""

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.physical_resources import (
    AllocationByDepartmentItem,
    CapacityForecastResponse,
    CapacityOverview,
    FacilityFlagItem,
    PhysicalFacilityCreate,
    PhysicalFacilityResponse,
    PhysicalFacilityUpdate,
    SpacePerPersonResponse,
    UtilizationByTypeItem,
)
from app.services import physical_resources_service as service
from app.services.scope import resolve, scope_params

router = APIRouter(
    prefix="/api/physical-resources", tags=["Modül 5 — Fiziksel Kaynaklar"]
)


# Sabit yollar parametreli yoldan önce tanımlandı.


@router.get(
    "/capacity/overview",
    response_model=CapacityOverview,
    summary="Kapasite özet göstergeleri",
)
def capacity_overview(
    kapsam: dict = Depends(scope_params), db: Session = Depends(get_db)
) -> CapacityOverview:
    """Toplam kapasite, doluluk ve tür bazlı dağılımı özetler."""
    return CapacityOverview(**service.capacity_overview(db, resolve(db, **kapsam)))


@router.get(
    "/capacity/by-type",
    response_model=List[UtilizationByTypeItem],
    summary="Tesis türüne göre kullanım oranı",
)
def by_type(
    kapsam: dict = Depends(scope_params), db: Session = Depends(get_db)
) -> List[UtilizationByTypeItem]:
    """Derslik, laboratuvar, ofis gibi türlerin kullanım oranını verir."""
    return [UtilizationByTypeItem(**row) for row in service.utilization_by_type(db, resolve(db, **kapsam))]


@router.get(
    "/capacity/by-department",
    response_model=List[AllocationByDepartmentItem],
    summary="Bölüm bazlı alan dağılımı",
)
def by_department(
    kapsam: dict = Depends(scope_params), db: Session = Depends(get_db)
) -> List[AllocationByDepartmentItem]:
    """Hangi bölüme ne kadar kapasite ayrıldığını gösterir."""
    return [
        AllocationByDepartmentItem(**row) for row in service.allocation_by_department(db, resolve(db, **kapsam))
    ]


@router.get(
    "/capacity/per-person",
    response_model=SpacePerPersonResponse,
    summary="Kişi başına düşen kapasite",
)
def per_person(
    kapsam: dict = Depends(scope_params), db: Session = Depends(get_db)
) -> SpacePerPersonResponse:
    """Öğrenci ve personel sayıları veritabanından sayılarak hesaplanır."""
    return SpacePerPersonResponse(**service.space_per_person(db, resolve(db, **kapsam)))


@router.get(
    "/capacity/underutilized",
    response_model=List[FacilityFlagItem],
    summary="Az kullanılan mekânlar (%50 altı)",
)
def underutilized(
    kapsam: dict = Depends(scope_params), db: Session = Depends(get_db)
) -> List[FacilityFlagItem]:
    """Doluluk oranı eşiğin altında kalan mekânları listeler."""
    return [FacilityFlagItem(**row) for row in service.underutilized_facilities(db, resolve(db, **kapsam))]


@router.get(
    "/capacity/overcrowded",
    response_model=List[FacilityFlagItem],
    summary="Aşırı dolu mekânlar (%90 üstü)",
)
def overcrowded(
    kapsam: dict = Depends(scope_params), db: Session = Depends(get_db)
) -> List[FacilityFlagItem]:
    """Doluluk oranı kritik eşiği aşan mekânları listeler."""
    return [FacilityFlagItem(**row) for row in service.overcrowded_facilities(db, resolve(db, **kapsam))]


@router.get(
    "/capacity/forecast",
    response_model=CapacityForecastResponse,
    summary="Büyüme senaryosunda kapasite projeksiyonu",
)
def forecast(
    growth_percent: float = Query(
        default=10.0,
        ge=-50.0,
        le=200.0,
        description="Beklenen öğrenci artış yüzdesi. Negatif değer küçülmeyi ifade eder.",
    ),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> CapacityForecastResponse:
    """Verilen büyüme oranında kapasitenin yetip yetmeyeceğini hesaplar."""
    return CapacityForecastResponse(
        **service.forecast_capacity_need(db, growth_percent, resolve(db, **kapsam))
    )


@router.get(
    "/facilities",
    response_model=List[PhysicalFacilityResponse],
    summary="Mekân listesi",
)
def list_facilities(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    facility_type: Optional[str] = Query(default=None, examples=["classroom"]),
    include_inactive: bool = Query(default=False),
    kapsam: dict = Depends(scope_params),
    db: Session = Depends(get_db),
) -> List[PhysicalFacilityResponse]:
    """Filtrelenebilir ve sayfalanabilir mekân listesi."""
    return [
        PhysicalFacilityResponse(**service.to_response_dict(facility))
        for facility in service.list_facilities(
            db, skip, limit, facility_type, None, include_inactive,
            resolve(db, **kapsam)
        )
    ]


@router.post(
    "/facilities",
    response_model=PhysicalFacilityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni mekân ekle",
)
def create_facility(
    payload: PhysicalFacilityCreate, db: Session = Depends(get_db)
) -> PhysicalFacilityResponse:
    """Mekân kodu tekrar ederse 409, bölüm bulunamazsa 404 döner."""
    facility = service.create_facility(db, payload)
    return PhysicalFacilityResponse(
        **service.to_response_dict(service.get_facility(db, facility.id))
    )


@router.get(
    "/facilities/{facility_id}",
    response_model=PhysicalFacilityResponse,
    summary="Tek mekân bilgisi",
)
def get_facility(facility_id: int, db: Session = Depends(get_db)) -> PhysicalFacilityResponse:
    """Mekân bulunamazsa 404 döner."""
    return PhysicalFacilityResponse(
        **service.to_response_dict(service.get_facility(db, facility_id))
    )


@router.patch(
    "/facilities/{facility_id}",
    response_model=PhysicalFacilityResponse,
    summary="Mekân bilgilerini güncelle",
)
def update_facility(
    facility_id: int, payload: PhysicalFacilityUpdate, db: Session = Depends(get_db)
) -> PhysicalFacilityResponse:
    """Doluluk kapasiteyi aşarsa 422 döner."""
    service.update_facility(db, facility_id, payload)
    return PhysicalFacilityResponse(
        **service.to_response_dict(service.get_facility(db, facility_id))
    )


@router.delete(
    "/facilities/{facility_id}",
    response_model=PhysicalFacilityResponse,
    summary="Mekânı pasifleştir",
)
def deactivate_facility(
    facility_id: int, db: Session = Depends(get_db)
) -> PhysicalFacilityResponse:
    """Kayıt silinmez; kapasite geçmişi korunsun diye pasifleştirilir."""
    service.deactivate_facility(db, facility_id)
    return PhysicalFacilityResponse(
        **service.to_response_dict(service.get_facility(db, facility_id))
    )


@router.get(
    "/classroom-usage-map",
    summary="Derslik kullanım haritası (kat planı + ders programı)",
)
def classroom_usage_map() -> dict:
    """Kat planları ve derslik programından türetilmiş kullanım haritası.

    SALT OKUNUR ve VERİTABANINDAN BAĞIMSIZDIR: kaynak, ham PDF/XLSX'ten
    `build_infrastructure_map.py` ile üretilen türetilmiş dosyalardır.
    `physical_facilities` tablosuna yazmaz, ondan okumaz — o tablo
    kurumun yetkili mekân envanteri, bu ise bir dönemin ders programıdır.
    İkisini birleştirmek iki farklı gerçeği tek sayıya indirger.

    Gün/saat/kat süzgeçleri istemcide uygulanır; bu uç tam veri kümesini
    tek bir doğru olarak yayınlar.
    """
    from app.services import classroom_usage_service

    return classroom_usage_service.classroom_usage_map()


@router.get(
    "/classroom-vector-plans",
    summary="SEMANTİK kat haritası (temiz plan — mimari pafta DEĞİL)",
)
def classroom_vector_plans() -> dict:
    """Her kat için ANLAMLI geometri: bina sınırı, koridor, oda, işaret.

    MİMARİ PAFTA YAYINLANMAZ. Lejant, kot çizgileri, ölçülendirme, pafta
    çerçevesi ve diğer CAD ayrıntıları `build_semantic_map.py` içinde
    elenir; arayüze yalnızca dört anlamlı katman gider:

        outline    bina sınırı
        corridors  koridor / ortak alan (etkileşimsiz)
        rooms      SINIF / LAB / AMFİ / STÜDYO (etkileşimli)
        landmarks  merdiven, asansör, WC (yön bulma)

    Odalar ETİKET GÜDÜMLÜ çıkarılır: paftanın lejantı oda numarasını
    türe bağlar (`13- SINIF-c`), oda içindeki `13-86.7 m²` etiketi ise
    o odanın konumunu verir. Etiket ➜ tohum noktası ➜ duvarla çevrili
    bölge ➜ oda poligonu. Etiketi olmayan bir boşluk oda SAYILMAZ; bu
    yüzden koridor, şaft veya cephe boşluğu derslik gibi görünemez.

    Yayınlanan harita İKİ katmanın birleşimidir: `build_semantic_map.py`
    çıktısı + elle bakılan `semantic_map_overrides.json`. İkisi ayrı
    dosyada durduğu için extractor yeniden çalıştırıldığında elle
    düzeltmeler kaybolmaz. Her oda `origin` alanıyla damgalıdır.
    """
    from app.services import semantic_map_service

    return semantic_map_service.kat_haritalari()


@router.get(
    "/classroom-map-areas",
    summary="Kroki alanı ↔ derslik eşleştirmeleri (kalıcı)",
)
def classroom_map_areas() -> dict:
    """Kullanıcının elle tanımladığı kroki alanları ve atanabilir dersliler.

    Yukarıdaki salt-okunur kullanım haritası ucundan AYRIDIR ve onu
    değiştirmez; arayüz ikisini birleştirir.
    """
    from app.services import classroom_mapping_service

    return classroom_mapping_service.esleme_durumu()


@router.put(
    "/classroom-map-areas",
    summary="Kroki alanı eşleştirmelerini kalıcı olarak kaydet",
)
def save_classroom_map_areas(payload: dict = Body(...)) -> dict:
    """Eşleştirmeleri doğrular ve dosyaya ATOMİK yazar.

    Doğrulama başarısızsa HİÇBİR ŞEY yazılmaz: kısmi kayıt, kullanıcının
    ekranda gördüğüyle diskteki gerçeğin ayrışması demektir.

    400 → şema/şekil/bilinmeyen derslik · 409 → aynı derslik iki alanda.
    """
    from app.services import classroom_mapping_service as ms

    try:
        return ms.esleme_yaz(payload)
    except ms.EslesmeHatasi as hata:
        kod = (status.HTTP_409_CONFLICT
               if "duplicate_room_code" in hata.ayrinti
               else status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status_code=kod,
                            detail={"message": hata.mesaj, **hata.ayrinti})
