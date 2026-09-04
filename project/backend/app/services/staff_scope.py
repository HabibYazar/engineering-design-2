"""AKADEMİK KADRO SÜZGECİ — "kaç akademisyen var?" sorusunun TEK kuralı.

ÇİFT SAYMA HATASI
-----------------
`academic_staff` tablosu bir kişi için HER AKADEMİK YIL ayrı satır tutar;
tablo bir anlık görüntü (snapshot) defteridir, kişi kütüğü değildir.
Yıl süzgeci uygulanmadığında aynı kişi her yıl için bir kez sayılır.

Canlı kurulumda gözlenen sonuç (kanıt):

    academic_staff satır sayısı            360
    (ad, soyad, bölüm) tekil kişi sayısı   180
    yıl dağılımı        2024-2025 → 180 · 2025-2026 → 180

    Mühendislik fakültesi "Akademik Personel"      216   (gerçek: 108)
    Aynı fakültenin "Yayın Sayısı"                2.062   (gerçek: 1.031)
    Üniversite yayın toplamı                      3.142   (gerçek: 1.571)

Kurumun gerçek YÖK verisinde şu an TEK yıl bulunduğu için hata
görünmüyordu; ikinci yıl aktarıldığı anda bütün kadro ve yayın
göstergeleri sessizce ikiye katlanacaktı. Bir fakültenin üniversite
toplamını aşması da bu mekanizmayla mümkün hâle geliyordu.

KURAL
-----
Kadro göstergeleri EN GÜNCEL yıl anlık görüntüsü üzerinden okunur.
Yılı boş olan satırlar (yıl bilgisi taşımayan eski kayıtlar) yalnızca
hiç yıllı satır yoksa kullanılır; aksi hâlde güncel görüntüye karışıp
tekrar üretirlerdi.

Bu kural TEK YERDE durur ve kadroya bakan bütün servisler buradan
geçer — analitik, kapasite, müfredat, karşılaştırma. Kuralın kopyalanması
hâlinde biri güncellenip diğeri unutulur ve ekranın iki köşesinde iki
farklı akademisyen sayısı belirir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.models import AcademicStaff

if TYPE_CHECKING:
    from app.services.scope import Scope


def latest_staff_period(db: Session) -> Optional[str]:
    """`academic_staff` içindeki en güncel akademik yıl (yoksa None)."""
    return db.execute(
        select(func.max(AcademicStaff.academic_year))
        .where(AcademicStaff.academic_year.isnot(None))
    ).scalar()


def staff_periods(db: Session) -> list:
    """Kadro anlık görüntüsü bulunan akademik yıllar."""
    return sorted(
        y for (y,) in db.execute(
            select(AcademicStaff.academic_year).distinct()
            .where(AcademicStaff.academic_year.isnot(None))
        ) if y
    )


def resolve_staff_period(db: Session, donem: Optional[str] = None) -> Optional[str]:
    """Kullanılacak kadro dönemi.

    · `donem` verilmemişse → en güncel anlık görüntü (varsayılan davranış).
    · `donem` VERİLMİŞSE → aynen o dönem kullanılır. Kaydı yoksa BAŞKA
      bir yıla DÜŞÜLMEZ; çağıran taraf "bu dönemde ölçülmedi" der.
      Sessizce en güncel yıla düşmek, kullanıcının seçtiği yılın etiketi
      altında başka bir yılın sayısını göstermek olurdu.
    """
    if donem:
        return donem
    return latest_staff_period(db)


def staff_period_available(db: Session, donem: Optional[str] = None) -> bool:
    """Seçili dönemde kadro anlık görüntüsü var mı?"""
    hedef = resolve_staff_period(db, donem)
    if hedef is None:
        return False
    return hedef in staff_periods(db)


def apply_staff_filters(sorgu, db: Session, scope: Optional["Scope"] = None,
                        donem: Optional[str] = None):
    """Bir `academic_staff` sorgusuna aktiflik + kapsam + DÖNEM süzgeci ekler.

    Dönem verilmezse en güncel anlık görüntü kullanılır (bkz.
    `resolve_staff_period`). Verilirse ondan sapılmaz.
    """
    sorgu = sorgu.where(AcademicStaff.is_active.is_(True))
    # Kaynak personeli BÖLÜME bağlar; program FK'sı yoktur. Program
    # ekranında bölüm kadrosunu program kadrosu gibi göstermek yasaktır.
    if scope is not None and scope.level == "program":
        return sorgu.where(false())
    if scope is not None and scope.department_ids is not None:
        sorgu = sorgu.where(AcademicStaff.department_id.in_(scope.department_ids))
    hedef = resolve_staff_period(db, donem)
    if hedef is not None:
        sorgu = sorgu.where(AcademicStaff.academic_year == hedef)
    return sorgu


def active_staff_query(db: Session, scope: Optional["Scope"] = None,
                       donem: Optional[str] = None):
    """Kapsamdaki aktif kadro — kişi başına TEK satır."""
    return apply_staff_filters(select(AcademicStaff), db, scope, donem)


def active_staff_count(db: Session, scope: Optional["Scope"] = None,
                       donem: Optional[str] = None) -> int:
    """Kapsamdaki aktif akademisyen SAYISI."""
    return db.execute(
        apply_staff_filters(
            select(func.count(func.distinct(AcademicStaff.id)))
            .select_from(AcademicStaff), db, scope, donem)
    ).scalar_one()
