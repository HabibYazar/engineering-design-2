"""ARAÇ SONUÇLARINDAN DETERMİNİSTİK ÖZET — MODEL ÇAĞRILMADAN.

NEDEN VAR
---------
Ölçülen olay: veri araçları başarıyla çalışıyor (32 + 35 satır dönüyor),
ama modelin YORUM turu zaman aşımına uğruyor. Eski davranışta kullanıcı
şunu görüyordu:

    "Model bu isteğe zamanında yanıt veremedi."
    **base_score** (toplam 32 satır)
    - university_name=…, program_name=…, value=…
    - … (ilk beş satır)

Yani veritabanından okunmuş 67 satırlık gerçek veri, kullanıcıya beş
satırlık ham döküm olarak yansıyordu. Bir yöneticinin bu listeden
çıkarabileceği bir karar yok.

Bu modül aynı veriden ÖLÇÜLEBİLİR bir özet üretir: kaç kayıt, kaç
kurum, en düşük/en yüksek/ortalama/medyan, ve iki karşılaştırılabilir
küme varsa aralarındaki fark. Model çağrılmaz, ağ isteği yapılmaz;
hesap tamamen elde olan satırlardan çıkar.

NE HESAPLANMAZ
--------------
Anlamı bilinmeyen alanda aritmetik YAPILMAZ. Bir sütunun sayısal
görünmesi, ortalamasının anlamlı olduğu anlamına gelmez: `academic_year`
"2025" olarak saklanıyorsa ortalaması saçmadır, kimlik alanlarının
(`id`, `code`) toplamı da öyle. Bu yüzden aritmetik yalnızca ÖLÇÜM
olduğu açıkça belli alanlara uygulanır (bkz. `_OLCUM_ALANI`), gerisi
sayılır ama hesaplanmaz.

Yüzdelerin ortalaması da alınmaz: doluluk gibi oranlar kayıt başına
farklı büyüklükteki tabanlara dayanır; ortalamaları yanlış sonuç verir.
Bu tür alanlarda yalnızca aralık (en düşük–en yüksek) verilir.
"""

from __future__ import annotations

import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

#: Aritmetiğe açık ölçüm alanları. Ad kalıbı, birim taşıyan gerçek
#: ölçümleri kimlik/yıl/kod alanlarından ayırır.
_OLCUM_ALANI = re.compile(
    r"(?:^|_)(value|score|count|total|capacity|quota|placed|staff|students?|"
    r"hours?|amount|sum|avg|average|min|max|rank|puan|sayi|toplam)(?:_|$)",
    re.I)

#: Ortalaması alınmayacak alanlar: oran/yüzde. Yalnız aralık verilir.
_ORAN_ALANI = re.compile(r"(percent|pct|ratio|oran|yuzde|rate)", re.I)

#: Kimlik/etiket alanları — gruplama için kullanılır, hesaplanmaz.
_KIMLIK_ALANI = re.compile(
    r"(name|title|label|program|university|faculty|department|kurum|"
    r"bolum|unvan|code|kod|type|tur|category|metric|year|donem|academic)",
    re.I)


def _sayi(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip().replace("%", "").replace(".", "").replace(",", ".")
        try:
            return float(t)
        except ValueError:
            return None
    return None


def _sabit_alanlar(satirlar: List[dict]) -> Dict[str, Any]:
    """Bütün satırlarda AYNI olan alanlar — üst bilgiye taşınabilir.

    `academic_year=2025-2026` ve `metric=base_score` her satırda
    tekrarlanıyorsa bu, hem modele giden yükü hem de kullanıcıya
    gösterilen gürültüyü boşuna büyütür. Bir kez söylemek yeter.
    """
    if not satirlar:
        return {}
    ortak = {}
    ilk = satirlar[0]
    for k, v in ilk.items():
        if not isinstance(v, (str, int, float, bool)) or v is None:
            continue
        if all(s.get(k) == v for s in satirlar):
            ortak[k] = v
    return ortak


def _olcum_sutunlari(satirlar: List[dict], sabitler: Dict[str, Any]) -> List[str]:
    aday = []
    for k in satirlar[0]:
        if k in sabitler or _KIMLIK_ALANI.search(k):
            continue
        if not _OLCUM_ALANI.search(k):
            continue
        if sum(1 for s in satirlar if _sayi(s.get(k)) is not None) >= max(2, len(satirlar) // 3):
            aday.append(k)
    return aday


def _gruplama_sutunu(satirlar: List[dict], sabitler: Dict[str, Any]) -> Optional[str]:
    """Satırları anlamlı biçimde ayıran kimlik sütunu.

    "Kaç farklı üniversite?" sorusunun cevabı buradan çıkar. Her satırda
    farklı olan (kimlik) ya da hep aynı olan (sabit) sütunlar işe
    yaramaz; ortadaki ayrım gücü en yüksek sütun seçilir.
    """
    en_iyi, en_iyi_puan = None, 0.0
    for k in satirlar[0]:
        if k in sabitler or not _KIMLIK_ALANI.search(k):
            continue
        farkli = len({str(s.get(k)) for s in satirlar if s.get(k) is not None})
        if farkli < 2 or farkli == len(satirlar):
            continue
        puan = farkli / len(satirlar)
        if puan > en_iyi_puan:
            en_iyi, en_iyi_puan = k, puan
    return en_iyi


def _istatistik(degerler: List[float], oran: bool) -> str:
    if not degerler:
        return ""
    en_az, en_cok = min(degerler), max(degerler)
    bicim = lambda x: f"{x:,.1f}".replace(",", ".").rstrip("0").rstrip(".")
    if oran or len(degerler) < 3:
        return f"aralık {bicim(en_az)} – {bicim(en_cok)}"
    return (f"en düşük {bicim(en_az)} · en yüksek {bicim(en_cok)} · "
            f"ortalama {bicim(statistics.mean(degerler))} · "
            f"medyan {bicim(statistics.median(degerler))}")


def veri_kumesi_ozeti(ad: str, satirlar: List[dict]) -> str:
    """Tek bir araç sonucunun okunabilir özeti."""
    if not satirlar:
        return f"**{ad}** — kayıt yok."
    sabitler = _sabit_alanlar(satirlar)
    kapsam = ", ".join(f"{k}={v}" for k, v in list(sabitler.items())[:4]
                       if not str(k).startswith("_"))
    grup = _gruplama_sutunu(satirlar, sabitler)
    olcumler = _olcum_sutunlari(satirlar, sabitler)

    satir = [f"**{ad}** — {len(satirlar)} kayıt"
             + (f" · {kapsam}" if kapsam else "")]
    if grup:
        n = len({str(s.get(grup)) for s in satirlar if s.get(grup) is not None})
        satir.append(f"- {n} farklı {grup}")
        if n < len(satirlar):
            satir.append(f"- kayıt sayısı {grup} sayısından fazla: "
                         f"program varyantları (burslu/ücretli/dil) ayrı satır olabilir")
    for k in olcumler[:3]:
        d = [x for x in (_sayi(s.get(k)) for s in satirlar) if x is not None]
        ist = _istatistik(d, bool(_ORAN_ALANI.search(k)))
        if ist:
            satir.append(f"- {k}: {ist}")
    return "\n".join(satir)


def karsilastirma(kumeler: List[Tuple[str, List[dict]]]) -> str:
    """İki veri kümesi aynı ölçümü taşıyorsa aralarındaki farkı verir."""
    if len(kumeler) != 2:
        return ""
    (a_ad, a), (b_ad, b) = kumeler
    if not a or not b:
        return ""
    ortak = (set(_olcum_sutunlari(a, _sabit_alanlar(a)))
             & set(_olcum_sutunlari(b, _sabit_alanlar(b))))
    if not ortak:
        return ""
    k = sorted(ortak)[0]
    if _ORAN_ALANI.search(k):
        return ""
    da = [x for x in (_sayi(s.get(k)) for s in a) if x is not None]
    db = [x for x in (_sayi(s.get(k)) for s in b) if x is not None]
    if len(da) < 3 or len(db) < 3:
        return ""
    oa, ob = statistics.mean(da), statistics.mean(db)
    fark = oa - ob
    yon = "yüksek" if fark > 0 else "düşük"
    bicim = lambda x: f"{abs(x):,.1f}".replace(",", ".").rstrip("0").rstrip(".")
    return (f"**Karşılaştırma ({k})** — {a_ad} ortalaması, {b_ad} "
            f"ortalamasından {bicim(fark)} puan daha {yon} "
            f"({bicim(oa)} / {bicim(ob)}).")
