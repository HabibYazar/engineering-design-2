"""Araç çıktısını modele gönderirken sıkıştırma.

NEDEN GEREKTİ
-------------
Bulut sağlayıcı dakikalık bir token bütçesi uyguluyor ve bu bütçe TÜM
turların toplamıdır. Ölçüm:

    tur 1 isteği (yönerge + 7 araç şeması + soru)   ~4.100 token
    `get_program_quota_trend` çıktısı              ~2.980 token
    tur 2 isteği (tur 1 + araç sonucu)              ~7.100 token
    ------------------------------------------------------------
    dakikadaki toplam                              ~11.200 token

Yani araç çağıran her soru, iki tura varmadan bütçeyi bitiriyordu.

Şişkinlik VERİDE DEĞİL BİÇİMDE. `get_program_quota_trend` 19 üniversite
× 5 yıl döndürüyor; JSON her hücre için anahtar adını tekrar yazıyor:

    {"year":2022,"quota":1215.0,"placed":1215.0,"occupancy_percent":100.0}

Aynı bilgi tablo biçiminde beşte bir yer tutuyor:

    year;quota;placed;occupancy_percent
    2022;1215;1215;100

Ölçülen kazanç: quota_trend %58, akran karşılaştırması %69.

SAYILARA DOKUNULMAZ
-------------------
Bu modül YUVARLAMA, KISALTMA ya da ÖRNEKLEME yapmaz. Yaptığı üç şey:

  1. `null` alanları atar (bilgi taşımıyorlar),
  2. `1215.0` gibi tam sayı float'ları `1215` yazar,
  3. aynı anahtarlara sahip sözlük listelerini tabloya çevirir.

Üçü de tersine çevrilebilir biçim değişiklikleridir. Bir satırı atmak ya
da bir sayıyı yuvarlamak bu modülün işi DEĞİLDİR: modelin eksik veriyle
"yaklaşık" cevap üretmesi, cevap verememesinden daha tehlikelidir.

NEREYE UYGULANIR
----------------
YALNIZCA modele giden kopyaya. `structured_result`, `ui_spec` ve grafik
üretimi HAM çıktıyı kullanmaya devam eder; ekrandaki sayılar bu
modülden etkilenmez.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

#: Modele bilgi taşımayan, yalnızca yer kaplayan alanlar.
#: `methodology` ve `available_programs` backend'in kendi kayıtları için
#: değerlidir ama modelin cevabına katkı vermez; kaynak/uyarı bilgisi
#: `notes` alanında zaten geliyor.
ATILAN_ALANLAR = frozenset({
    "available_programs",
    "methodology",
})

#: Tablo biçimine geçmenin kazançlı olduğu en az kayıt sayısı. Altında
#: JSON daha okunaklı ve kazanç zaten önemsiz.
TABLO_ESIGI = 3


def _hucre(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, bool):
        return "1" if x else "0"
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def _tablola(liste: List[Dict]) -> str:
    """Aynı anahtarlara sahip sözlük listesini `başlık\\nsatır` metnine çevirir."""
    anahtarlar: List[str] = []
    for kayit in liste:
        for k in kayit:
            if k not in anahtarlar:
                anahtarlar.append(k)
    satirlar = [";".join(anahtarlar)]
    for kayit in liste:
        satirlar.append(";".join(_hucre(kayit.get(k)) for k in anahtarlar))
    return "\n".join(satirlar)


def _duz_mu(kayit: Dict) -> bool:
    """Sözlüğün tüm değerleri tabloya sığacak kadar basit mi?"""
    return all(not isinstance(v, (dict, list)) for v in kayit.values())


def _sikistir(o: Any) -> Any:
    if isinstance(o, dict):
        return {
            k: _sikistir(v)
            for k, v in o.items()
            if k not in ATILAN_ALANLAR and v is not None and v != [] and v != {}
        }
    if isinstance(o, list):
        ic = [_sikistir(x) for x in o]
        if (len(ic) >= TABLO_ESIGI
                and all(isinstance(x, dict) for x in ic)
                and all(_duz_mu(x) for x in ic)):
            return _tablola(ic)
        return ic
    if isinstance(o, float) and o.is_integer():
        return int(o)
    return o


def sikistir(icerik: str) -> str:
    """Araç çıktısının modele gidecek sıkıştırılmış hâlini döndürür.

    JSON değilse ya da sıkıştırma bir şekilde büyütürse GİRDİ AYNEN
    döner: bu fonksiyonun hiçbir koşulda veri bozmaması gerekir.
    """
    if not icerik:
        return icerik
    try:
        veri = json.loads(icerik)
    except (ValueError, TypeError):
        return icerik

    try:
        yeni = json.dumps(_sikistir(veri), ensure_ascii=False,
                          separators=(",", ":"))
    except (TypeError, ValueError):
        return icerik

    return yeni if len(yeni) < len(icerik) else icerik
