"""ÜCRET KAYNAK ÖNCELİĞİ VE TOPLAMA KURALI — tek yerde, açıkça.

NEDEN BU MODÜL VAR
------------------
Ekranda aynı sayının iki farklı yerde farklı çıkması, neredeyse her
zaman o sayının iki farklı yerde AYRI AYRI hesaplanmasından gelir.
Ücret tarafında tam olarak bu vardı: Ankara Bilim Üniversitesi'nin
"%50 burslu medyanı" üç ayrı kod yolunda birbirinden bağımsız
hesaplanıyordu (ana ücret paneli, dar kapsamlı rakip kıyası, üniversite
kapsamlı rakip kıyası). Üçü bugünkü veride aynı sonucu veriyordu, ama
bunu GARANTİ eden hiçbir şey yoktu; biri kapsamı, diğeri yılı, üçüncüsü
dil kopyalarını farklı ele aldığı anda sayılar sessizce ayrışır.

Bu modül iki kuralı tek kaynağa bağlar:

    1. KAYNAK ÖNCELİĞİ  — ABÜ'nün ücreti hangi tablodan okunur
    2. TOPLAMA KURALI   — birden çok satır tek sayıya nasıl indirgenir

KAYNAK ÖNCELİĞİ
---------------
    ProgramTuitionFee      ABÜ için TEK YETKİLİ kaynak (part3'teki
                           "Ankara_Bilim_Universitesi_Egitim_Ucretleri"
                           dosyası)
    CompetitorTuitionFee   YALNIZCA diğer kurumlar için

Rakip çalışma kitabı bugün ABÜ satırı içermiyor (kaynak dosyanın 12
numaralı notu bunu açıkça söylüyor). Ama bu bir GARANTİ değil, bir
rastlantı: yarın ABÜ satırı içeren bir sürüm aktarılırsa, kıyas
grafiğinde ya ikinci bir ABÜ çubuğu belirir ya da yetkili değeri ezen
bir değer görünürdü. `is_home_university()` bu ihtimali yapısal olarak
kapatır: rakip tablosundan gelen ABÜ satırları akran havuzundan ÇIKARILIR
ve çıkarıldıkları AYRICA bildirilir — sessizce yutulmazlar.

TOPLAMA KURALI (her iki taraf için AYNI)
----------------------------------------
    1) SÜZME    akademik yıl birebir, ücret türü birebir, kapsam içi
    2) SADELEŞTİRME  aynı programın yalnızca öğretim dili farklı olan ve
                     ÜCRETİ BİREBİR AYNI olan satırları TEK satıra iner
    3) MEDYAN   kalan sayısal değerlerin medyanı

(2) numaralı adım şart, çünkü ABÜ programlarının bir kısmı hem Türkçe
hem İngilizce satırla ve AYNI ücretle yayımlanıyor. Bu satırlar aynı
fiyatın iki kaydıdır, iki ayrı fiyat değil; ikisini de medyana sokmak o
programa çift ağırlık verir ve medyanı kaydırır. Ücretler FARKLIYSA
satırlar korunur — o zaman gerçekten iki ayrı fiyat vardır.

Aralık metni olarak yayımlanmış ücretler (ör. "386.000 TL - 410.000 TL")
sayısal olmadıkları için medyana girmez; uydurma bir orta nokta
üretilmez, kaç satırın bu yüzden dışarıda kaldığı sayılır.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Final, List, Optional, Tuple

#: Toplama yönteminin makine tarafından okunabilir adı — yanıtın içinde
#: taşınır ki grafiğin hangi kuralla üretildiği sonradan tartışılabilsin.
AGGREGATION_MEDIAN: Final = "median_of_language_collapsed_rows"

#: Satırın hangi kaynaktan geldiği. Yanıtta taşınır.
SOURCE_HOME: Final = "abu_program_tuition"        # yetkili ABÜ kaynağı
SOURCE_COMPETITOR: Final = "competitor_tuition"   # akran kurumlar

_TR: Final = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def _sade(ad: Optional[str]) -> str:
    if not ad:
        return ""
    d = unicodedata.normalize("NFKD", str(ad).translate(_TR))
    d = "".join(c for c in d if not unicodedata.combining(c)).upper()
    return re.sub(r"[^A-Z0-9]+", " ", d).strip()


#: Kendi kurumumuzu tanıyan yazım çeşitleri. Rakip tablosunda bu adlarla
#: bir satır belirirse akran değildir — yetkili kaynağın kopyasıdır.
_EV_ADLARI: Final = frozenset({
    _sade("Ankara Bilim Üniversitesi"),
    _sade("Ankara Bilim Universitesi"),
    _sade("ABÜ"),
    _sade("ABU"),
})


def is_home_university(ad: Optional[str]) -> bool:
    """Bu kurum adı bizim kurumumuzu mu gösteriyor?

    Ad benzerliğine göre TAHMİN YAPMAZ: yalnızca yukarıdaki kapalı
    listede yazılı yazım çeşitlerini tanır. Böylece "Ankara Medipol"
    ya da "Ankara Üniversitesi" gibi adlar yanlışlıkla eşleşmez.
    """
    s = _sade(ad)
    if not s:
        return False
    return s in _EV_ADLARI


def collapse_language_duplicates(
    satirlar: List[dict],
) -> Tuple[List[dict], List[dict]]:
    """Aynı program + aynı ücret, yalnızca dili farklı satırları birleştirir.

    Girdi satırları en az şu alanları taşımalı:
        `identity`  programın kimliği (program id ya da normalize ad)
        `annual_fee`  sayısal ücret ya da None
        `education_language`  dil ya da None

    Döner: (kalan, birleştirilen)
      kalan            medyana girecek satırlar; birleşenlerde
                       `languages` alanı bütün dilleri taşır
      birleştirilen    hangi satırların hangi satıra katıldığı —
                       gizlenmez, raporlanabilir

    Ücretleri FARKLI olan dil çeşitleri BİRLEŞTİRİLMEZ; onlar gerçekten
    iki ayrı fiyattır.
    """
    kalan: List[dict] = []
    birlesen: List[dict] = []
    kova: Dict[tuple, dict] = {}

    for s in satirlar:
        anahtar = (s.get("identity"), s.get("annual_fee"))
        # Sayısal olmayan (aralık metni) satırlar birleştirilmez: hangi
        # fiyatı anlattıkları bilinmiyor, kimliği paylaştıkları
        # varsayılamaz.
        if s.get("annual_fee") is None:
            kalan.append({**s, "languages": [s.get("education_language")]
                          if s.get("education_language") else []})
            continue
        varsa = kova.get(anahtar)
        if varsa is None:
            yeni = {**s, "languages": ([s["education_language"]]
                                       if s.get("education_language") else [])}
            kova[anahtar] = yeni
            kalan.append(yeni)
        else:
            dil = s.get("education_language")
            if dil and dil not in varsa["languages"]:
                varsa["languages"].append(dil)
            birlesen.append(s)

    for s in kalan:
        s["languages"] = sorted(d for d in s.get("languages", []) if d)
    return kalan, birlesen


def median(degerler: List[float]) -> Optional[float]:
    if not degerler:
        return None
    s = sorted(degerler)
    n = len(s)
    return round(float(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2), 2)


def aggregate(satirlar: List[dict]) -> dict:
    """Bir kurumun satırlarını TEK sayıya indirger — kural yukarıda.

    Çıktı, sayının nasıl üretildiğini açıklayacak kadar iz taşır:
    hangi satırlar kullanıldı, hangileri dil kopyası olduğu için
    birleşti, kaç satır sayısal olmadığı için dışarıda kaldı.
    """
    kalan, birlesen = collapse_language_duplicates(satirlar)
    sayisal = [r["annual_fee"] for r in kalan if r["annual_fee"] is not None]
    return {
        "median_fee": median(sayisal),
        "min_fee": min(sayisal) if sayisal else None,
        "max_fee": max(sayisal) if sayisal else None,
        "measured_count": len(sayisal),
        "text_only_count": len(kalan) - len(sayisal),
        "aggregation": AGGREGATION_MEDIAN,
        "source_rows": kalan,
        "collapsed_duplicate_rows": birlesen,
    }
