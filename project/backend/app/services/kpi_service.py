"""Modül 8 — Kurumsal performans (KPI) izleme servisi.

Entegrasyon notu: Durum sınıflandırma mantığı Halil'in `kpi/backend/db.py`
dosyasındaki `evaluate()` fonksiyonuyla aynıdır:

    başarı >= on_track_threshold   -> hedefte   (varsayılan %90)
    başarı <  at_risk_threshold    -> riskli    (varsayılan %70)
    aksi halde                     -> gecikmeli

Eşikler KPI başına saklanıyor; proje tanımı eşiklerin yönetim tarafından
yapılandırılabilir olmasını istiyor.

Değişen iki şey var:
1) Fakülte kırılımı sırasız listeden fakülte foreign key'ine taşındı.
2) Değerler Decimal; eşik sınırındaki bir KPI'nın float yuvarlaması yüzünden
   yanlış banda düşmesi engellendi.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:  # yalnızca tip ipucu; döngüsel import olmasın
    from app.services.scope import Scope

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.decimal_types import quantize_money
from app.models import Faculty, KpiFacultyValue, StrategicKpi
from app.schemas.kpi import (
    KpiMeasurement,
    StrategicKpiCreate,
    StrategicKpiUpdate,
)

STATUS_ON_TRACK = "hedefte"
STATUS_DELAYED = "gecikmeli"
STATUS_AT_RISK = "riskli"

# Ölçümü olmayan gösterge için ayrı durum.
# ÖNEMLİ: Veri eksikliği "riskli" ile aynı şey değildir. Değeri 0 kabul edip
# riskli saymak, ölçüm yapılmamış bir alanı başarısız göstermek demektir ve
# kurum ortalamasını haksız yere düşürür.
STATUS_NO_DATA = "veri eksik"

# Sistem verisinden hesaplanan (türetilmiş) göstergeler.
# Bu göstergelerin değeri KPI tablosunda saklanmaz; her istekte ilgili
# servisten okunur. Elle girilen bir değer formülle veri arasındaki bağı
# koparırdı.
DERIVED_KPI_RESOLVERS = {
    "Üniversite-sanayi iş birliği endeksi": (
        "engagement", "industry_collaboration", "Sanayi iş birliği kayıtları"
    ),
    "Bölgesel katkı endeksi": (
        "engagement", "regional_contribution", "Bölgesel katkı kayıtları"
    ),
}


def _resolve_derived_value(db: Session, kpi: StrategicKpi) -> Optional[Decimal]:
    """Türetilmiş göstergenin güncel değerini ilgili servisten okur.

    Kayıt bulunamazsa None döner; çağıran taraf bunu "veri eksik" olarak
    işler. Sıfır döndürmek, ölçülmemiş bir alanı "sıfır performans" gibi
    göstermek olurdu.
    """
    resolver = DERIVED_KPI_RESOLVERS.get(kpi.name)
    if resolver is None:
        return None

    _, function_name, _ = resolver
    try:
        from app.services import engagement_service

        result = getattr(engagement_service, function_name)(db, kpi.academic_year)
        return Decimal(str(result["index_value"]))
    except Exception:
        # Kayıt yoksa servis 404 fırlatır; bu bir hata değil, veri yokluğudur.
        return None


def _base_query():
    """Fakülte kırılımını tek sorguda getirir (N+1 önlenir)."""
    return select(StrategicKpi).options(
        selectinload(StrategicKpi.faculty_values).selectinload(KpiFacultyValue.faculty)
    )


def _direction_label(change_percent, higher_is_better: bool) -> str:
    """Değişimi kurumun lehine mi aleyhine mi olduğuyla birlikte anlatır.

    Sadece "+%2,5" yazmak yeterli değildir: öğrenci başına maliyetin %2,5
    artması kötüdür, yayın sayısının %2,5 artması iyidir. Yön bilgisi
    olmadan arayüz her artışı yeşil gösterirdi.
    """
    if change_percent is None:
        return "geçen dönem verisi yok"
    if change_percent == 0:
        return "geçen döneme göre değişmedi"
    increased = change_percent > 0
    improved = increased == higher_is_better
    movement = "arttı" if increased else "azaldı"
    judgement = "iyileşme" if improved else "kötüleşme"
    return f"geçen döneme göre {movement} ({judgement})"


def evaluate(kpi: StrategicKpi, db: Optional[Session] = None) -> dict:
    """KPI'yı hesaplanmış başarı oranı ve durumuyla birlikte döndürür.

    db verilirse türetilmiş göstergelerin değeri ilgili servisten okunur.
    """
    current_value = kpi.current_value
    has_data = True

    if kpi.value_source == "derived":
        resolved = _resolve_derived_value(db, kpi) if db is not None else None
        if resolved is None:
            # Ölçüm bulunamadı. 0 yazmak yerine "veri eksik" olarak işaretliyoruz.
            has_data = False
            current_value = None
        else:
            current_value = resolved

    if not has_data or current_value is None:
        achievement = None
        state = STATUS_NO_DATA
    else:
        achievement = (
            quantize_money(current_value / kpi.target_value * Decimal("100"))
            if kpi.target_value
            else None
        )
        if achievement is None:
            state = STATUS_NO_DATA
        elif achievement >= kpi.on_track_threshold:
            state = STATUS_ON_TRACK
        elif achievement < kpi.at_risk_threshold:
            state = STATUS_AT_RISK
        else:
            state = STATUS_DELAYED

    # Geçmiş veri yoksa değişim hesaplanmaz; %0 yazmak "değişim olmadı"
    # anlamına gelir ve veri eksikliğini gizlerdi.
    change = None
    if (
        has_data
        and current_value is not None
        and kpi.previous_value is not None
        and kpi.previous_value != 0
    ):
        change = quantize_money(
            (current_value - kpi.previous_value) / kpi.previous_value * Decimal("100")
        )

    gap = None
    if has_data and current_value is not None and kpi.university_average is not None:
        gap = quantize_money(current_value - kpi.university_average)

    return {
        "id": kpi.id,
        "name": kpi.name,
        "dimension": kpi.dimension,
        "unit": kpi.unit,
        "academic_year": kpi.academic_year,
        "current_value": current_value,
        "has_data": has_data,
        "target_value": kpi.target_value,
        "previous_value": kpi.previous_value,
        "university_average": kpi.university_average,
        "achievement_percent": achievement,
        "status": state,
        "on_track_threshold": kpi.on_track_threshold,
        "at_risk_threshold": kpi.at_risk_threshold,
        "change_vs_previous_percent": change,
        "gap_vs_university_average": gap,
        "corrective_action": kpi.corrective_action,
        # Göstergenin künyesi: ne ölçtüğü, nasıl hesaplandığı, nereden geldiği.
        "description": kpi.description,
        "formula": kpi.formula,
        "data_source": (
            DERIVED_KPI_RESOLVERS[kpi.name][2]
            if kpi.name in DERIVED_KPI_RESOLVERS
            else kpi.data_source
        ),
        "higher_is_better": kpi.higher_is_better,
        "value_source": kpi.value_source,
        # Değişimin sade dille yorumu. Yalnızca artı/eksi işareti göstermek
        # yetmiyor: öğrenci başına maliyetin artması "kötüleşti" demektir ama
        # yayın sayısının artması "iyileşti" demektir.
        "direction_label": (
            "ölçüm bulunamadı"
            if not has_data
            else _direction_label(change, kpi.higher_is_better)
        ),
        "faculty_values": [
            {
                "faculty_id": fv.faculty_id,
                "faculty_name": fv.faculty.name if fv.faculty else None,
                "value": fv.value,
            }
            for fv in sorted(kpi.faculty_values, key=lambda x: x.faculty_id)
        ],
        "is_active": kpi.is_active,
    }


# ----------------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------------


def list_kpis(
    db: Session,
    academic_year: Optional[str] = None,
    dimension: Optional[str] = None,
    kpi_status: Optional[str] = None,
    include_inactive: bool = False,
    scope: Optional["Scope"] = None,
) -> List[dict]:
    """Filtrelenebilir KPI listesi.

    KAPSAM
    ------
    KPI'lar KURUM seviyesinde tanımlanır ve en fazla FAKÜLTE kırılımı
    taşır (`kpi_faculty_values`). Bu yüzden:

      * üniversite kapsamı → kurumsal değer + tüm fakülte kırılımı
      * fakülte kapsamı    → yalnızca o fakültenin kırılımı; başka
                             fakültelerin değerleri listeden çıkarılır
      * bölüm / program    → KPI bu seviyede ÖLÇÜLMÜYOR; fakültenin
                             değerini programın değeriymiş gibi
                             göstermemek için boş liste döner

    Boş liste döndürmek "veri yok" demektir ve çağıran uç bunu açık bir
    404 mesajına çevirir; üst birimin sayısını aşağı taşımak sızıntıdır.
    """
    if scope is not None and scope.level in ("department", "program"):
        return []

    query = _base_query()
    if not include_inactive:
        query = query.where(StrategicKpi.is_active.is_(True))
    if academic_year:
        query = query.where(StrategicKpi.academic_year == academic_year)
    if dimension:
        query = query.where(StrategicKpi.dimension == dimension)

    rows = [
        evaluate(k, db)
        for k in db.execute(
            query.order_by(StrategicKpi.dimension, StrategicKpi.name)
        ).scalars().unique()
    ]

    if scope is not None and scope.faculty_ids is not None:
        # Fakülte kırılımı kapsam dışı fakülteleri taşımasın.
        for r in rows:
            r["faculty_values"] = [
                fv for fv in r["faculty_values"]
                if fv["faculty_id"] in scope.faculty_ids
            ]

    if kpi_status:
        valid = (STATUS_ON_TRACK, STATUS_DELAYED, STATUS_AT_RISK, STATUS_NO_DATA)
        if kpi_status not in valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"status alanı {', '.join(valid)} değerlerinden biri olmalı.",
            )
        rows = [r for r in rows if r["status"] == kpi_status]
    return rows


def get_kpi(db: Session, kpi_id: int) -> StrategicKpi:
    """Tek KPI; bulunamazsa 404."""
    kpi = db.execute(_base_query().where(StrategicKpi.id == kpi_id)).scalars().first()
    if kpi is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{kpi_id} numaralı KPI bulunamadı.",
        )
    return kpi


def list_dimensions(db: Session) -> List[str]:
    """Tanımlı stratejik boyutlar."""
    return sorted(
        {
            row
            for row in db.execute(
                select(StrategicKpi.dimension).where(StrategicKpi.is_active.is_(True))
            ).scalars()
        }
    )


def create_kpi(db: Session, payload: StrategicKpiCreate) -> StrategicKpi:
    """Yeni KPI tanımlar; aynı yıl aynı isim varsa 409."""
    existing = db.execute(
        select(StrategicKpi).where(
            StrategicKpi.name == payload.name,
            StrategicKpi.academic_year == payload.academic_year,
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{payload.name}' KPI'sı {payload.academic_year} yılı için "
                "zaten tanımlı."
            ),
        )

    data = payload.model_dump(exclude={"faculty_values"})
    kpi = StrategicKpi(**data)
    db.add(kpi)
    db.flush()

    for item in payload.faculty_values:
        if db.get(Faculty, item.faculty_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{item.faculty_id} numaralı fakülte bulunamadı.",
            )
        db.add(
            KpiFacultyValue(
                kpi_id=kpi.id,
                faculty_id=item.faculty_id,
                value=quantize_money(item.value),
            )
        )

    db.commit()
    db.refresh(kpi)
    return kpi


def update_kpi(db: Session, kpi_id: int, payload: StrategicKpiUpdate) -> StrategicKpi:
    """KPI tanımını veya eşiklerini günceller."""
    kpi = get_kpi(db, kpi_id)
    data = payload.model_dump(exclude_unset=True)

    # Eşik tutarlılığı güncel değerlerle birlikte kontrol edilmeli; kısmi
    # güncellemede yalnızca bir eşik gönderilebilir.
    new_on = data.get("on_track_threshold", kpi.on_track_threshold)
    new_risk = data.get("at_risk_threshold", kpi.at_risk_threshold)
    if new_on <= new_risk:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"on_track_threshold ({new_on}) at_risk_threshold ({new_risk}) "
                "değerinden büyük olmalı."
            ),
        )

    for field, value in data.items():
        setattr(kpi, field, value)
    db.commit()
    db.refresh(kpi)
    return kpi


def record_measurement(db: Session, kpi_id: int, payload: KpiMeasurement) -> StrategicKpi:
    """Yeni ölçüm değeri kaydeder; durum otomatik yeniden hesaplanır."""
    kpi = get_kpi(db, kpi_id)
    kpi.current_value = quantize_money(payload.value)
    db.commit()
    db.refresh(kpi)
    return kpi


def set_faculty_value(
    db: Session, kpi_id: int, faculty_id: int, value: Decimal
) -> StrategicKpi:
    """Bir fakültenin KPI değerini ekler veya günceller."""
    kpi = get_kpi(db, kpi_id)
    if db.get(Faculty, faculty_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{faculty_id} numaralı fakülte bulunamadı.",
        )

    row = db.execute(
        select(KpiFacultyValue).where(
            KpiFacultyValue.kpi_id == kpi_id,
            KpiFacultyValue.faculty_id == faculty_id,
        )
    ).scalars().first()

    if row is None:
        db.add(
            KpiFacultyValue(
                kpi_id=kpi_id, faculty_id=faculty_id, value=quantize_money(value)
            )
        )
    else:
        row.value = quantize_money(value)

    db.commit()
    db.refresh(kpi)
    return kpi


def deactivate_kpi(db: Session, kpi_id: int) -> StrategicKpi:
    """KPI izlemeden çıkarılır; ölçüm geçmişi korunur."""
    kpi = get_kpi(db, kpi_id)
    kpi.is_active = False
    db.commit()
    db.refresh(kpi)
    return kpi


# ----------------------------------------------------------------------------
# Özet raporlar
# ----------------------------------------------------------------------------


def scorecard(db: Session, academic_year: Optional[str] = None,
              scope: Optional["Scope"] = None) -> dict:
    """Tüm KPI'ların karne özeti ve boyut bazlı dağılımı."""
    rows = list_kpis(db, academic_year=academic_year, scope=scope)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year or 'tüm yıllar'}' için tanımlı KPI yok. "
                "Önce KPI tanımlayın."
            ),
        )

    # Ölçümü olmayan göstergeler ortalamaya KATILMAZ.
    # 0 kabul edip ortalamaya katmak, veri toplanmamış bir alanı sıfır
    # performans saymak ve kurumu haksız yere başarısız göstermek olurdu.
    measured = [r for r in rows if r["status"] != STATUS_NO_DATA]
    no_data = [r for r in rows if r["status"] == STATUS_NO_DATA]

    dimensions: Dict[str, dict] = {}
    for row in rows:
        bucket = dimensions.setdefault(
            row["dimension"],
            {
                "count": 0, "measured": 0, "achievement": Decimal("0"),
                "on": 0, "delayed": 0, "risk": 0, "no_data": 0,
            },
        )
        bucket["count"] += 1
        if row["status"] == STATUS_NO_DATA:
            bucket["no_data"] += 1
            continue
        bucket["measured"] += 1
        bucket["achievement"] += row["achievement_percent"]
        if row["status"] == STATUS_ON_TRACK:
            bucket["on"] += 1
        elif row["status"] == STATUS_DELAYED:
            bucket["delayed"] += 1
        else:
            bucket["risk"] += 1

    by_dimension = [
        {
            "dimension": name,
            "kpi_count": data["count"],
            # Ölçülen gösterge yoksa ortalama hesaplanmaz; 0 yazmak yanıltırdı.
            "average_achievement_percent": (
                quantize_money(data["achievement"] / data["measured"])
                if data["measured"]
                else None
            ),
            "on_track_count": data["on"],
            "delayed_count": data["delayed"],
            "at_risk_count": data["risk"],
            "no_data_count": data["no_data"],
        }
        for name, data in dimensions.items()
    ]
    # Ölçümü olmayan boyutlar sıralamanın başına düşmesin diye sona atılıyor.
    by_dimension.sort(
        key=lambda row: (
            row["average_achievement_percent"] is None,
            row["average_achievement_percent"] or Decimal("0"),
        )
    )

    total = len(rows)
    overall = (
        quantize_money(
            sum((r["achievement_percent"] for r in measured), Decimal("0")) / len(measured)
        )
        if measured
        else None
    )
    at_risk = sum(1 for r in rows if r["status"] == STATUS_AT_RISK)
    on_track = sum(1 for r in rows if r["status"] == STATUS_ON_TRACK)

    # Kurum geneli durumu, tek tek KPI'larla aynı eşik mantığına göre belirlenir.
    if overall is None:
        overall_status = STATUS_NO_DATA
    elif overall >= Decimal("90"):
        overall_status = STATUS_ON_TRACK
    elif overall < Decimal("70"):
        overall_status = STATUS_AT_RISK
    else:
        overall_status = STATUS_DELAYED

    return {
        "academic_year": academic_year or "tüm yıllar",
        "total_kpis": total,
        "measured_kpi_count": len(measured),
        "no_data_count": len(no_data),
        "on_track_count": on_track,
        "delayed_count": len(measured) - on_track - at_risk,
        "at_risk_count": at_risk,
        "overall_achievement_percent": overall,
        "overall_status": overall_status,
        "average_basis_note": (
            f"Genel başarı, ölçümü bulunan {len(measured)} gösterge üzerinden hesaplandı. "
            f"{len(no_data)} gösterge için veri bulunmadığı için ortalamaya dahil edilmedi."
            if no_data
            else f"Genel başarı {len(measured)} göstergenin tamamı üzerinden hesaplandı."
        ),
        "by_dimension": by_dimension,
    }


def faculty_comparison(db: Session, academic_year: Optional[str] = None,
                       scope: Optional["Scope"] = None) -> List[dict]:
    """Fakültelerin ölçülmüş KPI'lardaki ortalama performansı.

    Yalnızca o fakülte için değer girilmiş KPI'lar dikkate alınır; ölçülmemiş
    KPI'yı sıfır saymak fakülteyi haksız yere düşük gösterirdi.
    """
    rows = list_kpis(db, academic_year=academic_year, scope=scope)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{academic_year or 'tüm yıllar'}' için tanımlı KPI yok.",
        )

    faculties: Dict[int, dict] = {}
    for row in rows:
        if row["status"] == STATUS_NO_DATA:
            continue
        target = row["target_value"]
        average = row["university_average"]
        for fv in row["faculty_values"]:
            bucket = faculties.setdefault(
                fv["faculty_id"],
                {
                    "name": fv["faculty_name"] or "Bilinmiyor",
                    "count": 0,
                    "achievement": Decimal("0"),
                    "above_average": 0,
                },
            )
            bucket["count"] += 1
            if target:
                bucket["achievement"] += fv["value"] / target * Decimal("100")
            if average is not None and fv["value"] > average:
                bucket["above_average"] += 1

    result = [
        {
            "faculty_id": fid,
            "faculty_name": data["name"],
            "measured_kpi_count": data["count"],
            "average_achievement_percent": quantize_money(
                data["achievement"] / data["count"]
            ),
            "kpis_above_university_average": data["above_average"],
        }
        for fid, data in faculties.items()
    ]
    result.sort(key=lambda row: row["average_achievement_percent"], reverse=True)
    return result


def attention_list(db: Session, academic_year: Optional[str] = None,
                   scope: Optional["Scope"] = None) -> List[dict]:
    """Riskli ve gecikmeli KPI'lar, en düşük başarıdan başlayarak."""
    # Veri eksikliği bir performans sorunu değil, bir veri toplama sorunudur.
    # Müdahale listesi yalnızca ÖLÇÜLEN ve hedefin altında kalan göstergeleri
    # içerir; eksik veriler ayrı bir listede raporlanır.
    rows = [
        r
        for r in list_kpis(db, academic_year=academic_year, scope=scope)
        if r["status"] in (STATUS_DELAYED, STATUS_AT_RISK)
    ]
    rows.sort(key=lambda row: row["achievement_percent"])
    return rows


def missing_data_list(db: Session, academic_year: Optional[str] = None,
                      scope: Optional["Scope"] = None) -> List[dict]:
    """Ölçümü bulunmayan göstergeler.

    Bunlar riskli değildir; ölçüm eksiğidir ve ayrı raporlanır.
    """
    return [
        r
        for r in list_kpis(db, academic_year=academic_year, scope=scope)
        if r["status"] == STATUS_NO_DATA
    ]
