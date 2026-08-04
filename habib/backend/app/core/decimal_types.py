"""Para ve oran değerlerinin kayıpsız saklanması için özel SQLAlchemy tipi.

SQLite'ta Numeric sütunlar arka planda float olarak tutulur. Float ikili tabanda
çalıştığı için 0.1 + 0.2 = 0.30000000000000004 gibi sapmalar oluşur ve bu sapma
bütçe hesaplarında milyonlarca liralık tablolarda gözle görülür hataya dönüşebilir.

Bu yüzden Decimal değerleri veritabanına METİN olarak yazıp okurken tekrar Decimal'e
çeviriyoruz. Böylece yazdığımız değerin aynısını geri okuduğumuz garanti altına alınır.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

# Tüm para ve oran alanlarında iki ondalık basamak kullanıyoruz.
TWO_PLACES: Decimal = Decimal("0.01")

# Öğrenci, personel ve kapasite gibi sayılabilir değerler tam sayıya yuvarlanır.
ZERO_PLACES: Decimal = Decimal("1")


def quantize_money(value: Any) -> Decimal:
    """Bir değeri iki ondalık basamaklı Decimal'e yuvarlar."""
    # str() üzerinden Decimal'e çevirmemizin sebebi: float doğrudan Decimal'e
    # verilirse ikili gösterimden gelen sapma da taşınır (Decimal(0.1) -> 0.1000000000000000055...).
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def quantize_count(value: Any) -> Decimal:
    """Öğrenci/personel gibi sayılabilir değerleri en yakın tam sayıya yuvarlar."""
    # Yarım öğrenci olamayacağı için başlıklar tam sayıya çekilir.
    return Decimal(str(value)).quantize(ZERO_PLACES, rounding=ROUND_HALF_UP)


class MoneyType(TypeDecorator):
    """Decimal değerleri veritabanında metin olarak saklayan sütun tipi."""

    # impl: Veritabanında hangi gerçek tipin kullanılacağını söyler.
    impl = String(32)

    # cache_ok: SQLAlchemy'nin sorgu derleme önbelleğini kullanabilmesi için gerekli.
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Optional[str]:
        """Python -> veritabanı yönünde Decimal'i metne çevirir."""
        if value is None:
            return None
        return str(quantize_money(value))

    def process_result_value(self, value: Any, dialect: Any) -> Optional[Decimal]:
        """Veritabanı -> Python yönünde metni Decimal'e çevirir."""
        if value is None:
            return None
        return Decimal(value)
