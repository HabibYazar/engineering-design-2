"""Önceki cevaptaki VERİDEN grafik — grafik olmasa bile.

ÖLÇÜLEN ARIZA
-------------
Kullanıcı beş satırlık bir taban puan tablosu içeren cevap aldı, sonra
"line yap" dedi. Sistem "Önceki grafiğin verisi bu konuşmada
bulunamadı" dedi.

Cevap yanlıştı çünkü ARANAN ŞEY YANLIŞTI: dönüştürme yalnızca önceki
GRAFİĞİ arıyordu. Oysa kullanıcının gördüğü ekranda grafik yoktu,
TABLO vardı — ve o tablo pekâlâ çizilebilir. "Grafik yok" demek,
elindeki veriyi görmezden gelip kullanıcıyı geri çevirmek oldu.

KAYNAK ÖNCELİĞİ
---------------
Bu modül zincirin son iki halkasını sağlar. Tam sıra:

    1. previous_charts          — kullanıcının GÖRDÜĞÜ grafik
    2. structured evidence      — araç/analiz çıktısı (satır listesi)
    3. tablo payload            — aynı yapı, başka adla
    4. görünür metindeki tablo  — SON ÇARE

Metin ayrıştırma en sonda çünkü en kırılgan olanıdır: yapılandırılmış
veri elde varken metni yeniden okumak, aynı sayıyı iki kez yorumlama
riskini davet eder.

METİN AYRIŞTIRMADA GÜVENLİK
---------------------------
Her sayı grafik değildir. Bir paragraftaki rastgele rakamları toplayıp
grafik çizmek, olmayan bir veri kümesi uydurmak olurdu. Bu yüzden üç
şart birden aranır:

    · en az iki VERİ satırı,
    · en az bir sayısal sütun,
    · en az bir etiket (kategori) sütunu.

Üçü sağlanmıyorsa hiçbir şey üretilmez ve zincir "veri yok" der.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.assistant import chart_builder

logger = logging.getLogger(__name__)

#: Grafik üretmek için gereken en az veri satırı.
EN_AZ_SATIR = 2
#: Okunabilirlik tavanı — bunun üstü grafikte etiket çorbasına döner.
_EN_FAZLA_KATEGORI = 40
_EN_FAZLA_SERI = 6

#: Markdown tablo satırı: `| a | b |`.
_TABLO_SATIRI = re.compile(r"^\s*\|(.+)\|\s*$")
#: Ayraç satırı: `|---|---:|`.
_AYRAC = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

#: Yıl/dönem başlığı — bu sütun DEĞER değil EKSEN adayıdır.
_YIL_BASLIK = re.compile(r"^(yil|yıl|year|donem|dönem|period|akademik)", re.I)
_YIL_DEGER = re.compile(r"^(19|20)\d{2}(\s*[-/]\s*(19|20)\d{2})?$")

#: Kimlik/kod sütunları etiket olarak da değer olarak da işe yaramaz.
_ATLA_BASLIK = re.compile(r"(^id$|_id$|kod$|code$|^no$|sıra no|url|link)", re.I)


# ---------------------------------------------------------------------------
# 1) SAYI OKUMA — TÜRKÇE BİÇİM
# ---------------------------------------------------------------------------
def sayi_oku(deger: Any) -> Optional[float]:
    """Türkçe yazılmış sayıyı float'a çevirir.

    "302,45" ondalık virgüllüdür; "1.234,56" binlik noktası taşır;
    "1234" düz. Bu üçünü ayırmadan okumak, 1.234'ü 1,234 sanmak gibi
    sessiz bir hata üretirdi. Kural: SON ayraç ondalıktır.
    """
    if deger is None or isinstance(deger, bool):
        return None
    if isinstance(deger, (int, float)):
        return float(deger)
    metin = str(deger).strip()
    if not metin:
        return None
    metin = re.sub(r"[^\d,.\-+]", "", metin)
    if not re.search(r"\d", metin):
        return None
    if "," in metin and "." in metin:
        # Hangisi sonda ise ondalık odur; diğeri binlik ayracıdır.
        if metin.rfind(",") > metin.rfind("."):
            metin = metin.replace(".", "").replace(",", ".")
        else:
            metin = metin.replace(",", "")
    elif "," in metin:
        metin = metin.replace(",", ".")
    elif metin.count(".") > 1:
        metin = metin.replace(".", "")          # 1.234.567
    try:
        return float(metin)
    except ValueError:
        return None


def _yil_mi(baslik: str, degerler: Sequence[str]) -> bool:
    if _YIL_BASLIK.search(baslik or ""):
        return True
    gecerli = [d for d in degerler if str(d).strip()]
    return bool(gecerli) and all(_YIL_DEGER.match(str(d).strip())
                                 for d in gecerli)


# ---------------------------------------------------------------------------
# 2) MARKDOWN TABLO
# ---------------------------------------------------------------------------
@dataclass
class Tablo:
    basliklar: List[str] = field(default_factory=list)
    satirlar: List[List[str]] = field(default_factory=list)

    @property
    def gecerli(self) -> bool:
        return len(self.satirlar) >= EN_AZ_SATIR and len(self.basliklar) >= 2


def _hucreler(satir: str) -> List[str]:
    icerik = _TABLO_SATIRI.match(satir).group(1)
    return [h.strip() for h in icerik.split("|")]


def markdown_tablolar(metin: str) -> List[Tablo]:
    """Metindeki markdown tabloları. Ayraç satırı ZORUNLU DEĞİL.

    Model bazen ayraç satırını atlıyor; onu şart koşmak, gerçek bir
    tabloyu görmezden gelmek olurdu. Bunun yerine sütun sayısı
    tutarlılığı aranır: aynı genişlikte ardışık satırlar bir tablodur.
    """
    tablolar: List[Tablo] = []
    aktif: Optional[Tablo] = None
    for ham in (metin or "").splitlines():
        if not _TABLO_SATIRI.match(ham):
            if aktif and aktif.gecerli:
                tablolar.append(aktif)
            aktif = None
            continue
        if _AYRAC.match(ham):
            continue                       # biçim satırı, veri değil
        hucre = _hucreler(ham)
        if aktif is None:
            aktif = Tablo(basliklar=hucre)
            continue
        if len(hucre) != len(aktif.basliklar):
            if aktif.gecerli:
                tablolar.append(aktif)
            aktif = Tablo(basliklar=hucre)
            continue
        aktif.satirlar.append(hucre)
    if aktif and aktif.gecerli:
        tablolar.append(aktif)
    return tablolar


# ---------------------------------------------------------------------------
# 3) SÖZLÜK LİSTESİ (structured evidence)
# ---------------------------------------------------------------------------
def _sozlukten_tablo(satirlar: Sequence[Dict[str, Any]]) -> Optional[Tablo]:
    """`[{"program": "...", "puan": 302.45}, ...]` → Tablo."""
    temiz = [s for s in satirlar if isinstance(s, dict) and s]
    if len(temiz) < EN_AZ_SATIR:
        return None
    basliklar: List[str] = []
    for satir in temiz:
        for anahtar in satir:
            if anahtar not in basliklar:
                basliklar.append(str(anahtar))
    if len(basliklar) < 2:
        return None
    return Tablo(basliklar=basliklar,
                 satirlar=[[("" if s.get(b) is None else str(s.get(b)))
                            for b in basliklar] for s in temiz])


def _yapidan_satirlar(veri: Any, derinlik: int = 0
                      ) -> List[Dict[str, Any]]:
    """İç içe bir yapıdaki İLK anlamlı kayıt listesini bulur.

    Araç çıktıları farklı adlar kullanıyor (`rows`, `records`, `data`,
    `items`). Ad ezberlemek yerine YAPI aranır: sözlüklerden oluşan,
    en az iki elemanlı bir liste.
    """
    if derinlik > 4:
        return []
    if isinstance(veri, list):
        if (len(veri) >= EN_AZ_SATIR
                and all(isinstance(x, dict) for x in veri)):
            return veri
        for oge in veri:
            bulunan = _yapidan_satirlar(oge, derinlik + 1)
            if bulunan:
                return bulunan
        return []
    if isinstance(veri, dict):
        # Önce alışıldık adlar, sonra bütün değerler.
        for anahtar in ("rows", "records", "data", "items", "series",
                        "values", "table"):
            if anahtar in veri:
                bulunan = _yapidan_satirlar(veri[anahtar], derinlik + 1)
                if bulunan:
                    return bulunan
        for deger in veri.values():
            bulunan = _yapidan_satirlar(deger, derinlik + 1)
            if bulunan:
                return bulunan
    return []


# ---------------------------------------------------------------------------
# 4) TABLO → GRAFİK
# ---------------------------------------------------------------------------
def _sutun(tablo: Tablo, i: int) -> List[str]:
    return [s[i] if i < len(s) else "" for s in tablo.satirlar]


def _sutun_turleri(tablo: Tablo) -> Tuple[List[int], List[int], List[int]]:
    """(etiket sütunları, yıl sütunları, değer sütunları)."""
    etiket: List[int] = []
    yil: List[int] = []
    deger: List[int] = []
    for i, baslik in enumerate(tablo.basliklar):
        if _ATLA_BASLIK.search(baslik):
            continue
        degerler = _sutun(tablo, i)
        sayisal = [sayi_oku(d) for d in degerler]
        oran = sum(1 for s in sayisal if s is not None) / max(len(sayisal), 1)
        if oran < 0.6:
            etiket.append(i)
        elif _yil_mi(baslik, degerler):
            yil.append(i)
        else:
            deger.append(i)
    return etiket, yil, deger


def _etiketler(tablo: Tablo, sutunlar: Sequence[int]) -> List[str]:
    """Birden çok etiket sütunu tek okunabilir ada birleşir."""
    adlar: List[str] = []
    for satir in tablo.satirlar:
        parca = [satir[i].strip() for i in sutunlar
                 if i < len(satir) and satir[i].strip()]
        adlar.append(" — ".join(parca) if parca else "—")
    return adlar


def tablodan_grafik(tablo: Tablo, tur: str, *, baslik: str = ""
                    ) -> List[Dict[str, Any]]:
    """Tablodan grafik(ler). Sayı UYDURULMAZ, hücreden okunur.

    EKSEN SEÇİMİ VERİNİN ŞEKLİNDEN ÇIKAR: tabloda yıl sütunu varsa ve
    yıllar etiketlerden ÇOKSA eksen yıldır (aynı varlığın zaman
    serisi); değilse eksen etikettir (farklı varlıkların kıyası).
    Örnekteki tabloda beş farklı program ve iki yıl var — doğru eksen
    programdır.
    """
    if not tablo.gecerli:
        return []
    etiket_s, yil_s, deger_s = _sutun_turleri(tablo)
    if not deger_s:
        # Yıl dışında sayısal sütun yoksa yıl DEĞER olarak kullanılamaz:
        # yılların grafiği bir veri değil, bir takvimdir.
        return []
    if not etiket_s and not yil_s:
        return []

    etiketler = (_etiketler(tablo, etiket_s) if etiket_s
                 else _sutun(tablo, yil_s[0]))
    farkli_etiket = len(set(etiketler))
    yil_degerleri = _sutun(tablo, yil_s[0]) if yil_s else []
    farkli_yil = len(set(y for y in yil_degerleri if y.strip()))

    if yil_s and farkli_yil > farkli_etiket:
        kategoriler = [str(y).strip() for y in yil_degerleri]
    else:
        kategoriler = etiketler

    if len(kategoriler) > _EN_FAZLA_KATEGORI:
        logger.info("Tablo grafiğe çevrilmedi: %d kategori okunmaz",
                    len(kategoriler))
        return []

    grafikler: List[Dict[str, Any]] = []
    for i in deger_s[:_EN_FAZLA_SERI]:
        degerler = [sayi_oku(d) for d in _sutun(tablo, i)]
        if sum(1 for d in degerler if d is not None) < EN_AZ_SATIR:
            continue
        ad = tablo.basliklar[i].strip() or "Değer"
        grafik = chart_builder._chart(
            tur if tur in chart_builder.CHART_TYPES else "bar",
            (baslik or ad), kategoriler,
            [{"name": ad, "data": degerler}],
            x_label=(tablo.basliklar[etiket_s[0]] if etiket_s else None),
            y_label=ad)
        if grafik:
            grafikler.append(grafik)
    return grafikler


# ---------------------------------------------------------------------------
# 5) TEK GİRİŞ — KAYNAK ZİNCİRİ
# ---------------------------------------------------------------------------
@dataclass
class Sonuc:
    grafikler: List[Dict[str, Any]] = field(default_factory=list)
    #: Hangi kaynaktan geldi — geliştirme izi için.
    kaynak: str = "yok"
    satir: int = 0


def grafiklenebilir(tur: str, *, yapisal: Any = None,
                    metin: str = "") -> Sonuc:
    """Yapılandırılmış veriden, olmazsa metindeki tablodan grafik.

    Hiçbir koşulda istisna yükseltmez: bu bir yardımcı yoldur, cevabı
    düşürmemelidir. Bulunamazsa boş `Sonuc` döner ve çağıran taraf
    dürüst bir mesaj verir — yeni bir konu araştırmaz.
    """
    try:
        if yapisal is not None:
            satirlar = _yapidan_satirlar(yapisal)
            tablo = _sozlukten_tablo(satirlar) if satirlar else None
            if tablo is not None:
                grafikler = tablodan_grafik(tablo, tur)
                if grafikler:
                    return Sonuc(grafikler, "structured", len(tablo.satirlar))

        for tablo in markdown_tablolar(metin):
            grafikler = tablodan_grafik(tablo, tur)
            if grafikler:
                return Sonuc(grafikler, "markdown_table", len(tablo.satirlar))
    except Exception:  # noqa: BLE001
        logger.debug("tablodan grafik üretilemedi", exc_info=True)
    return Sonuc()
