"""Grafik türü değiştirme — "bunları line yap", "pie chart olsun".

ÖLÇÜLEN ARIZA
-------------
Kullanıcı bir grafik aldıktan sonra "bunları line graph yapabilir
misin?" dediğinde sistem çoğu zaman grafiği üretemiyor, bazen de
"tek bir noktayı temsil ettiği için çizgi grafik oluşturulamaz" gibi
YANLIŞ bir gerekçe döndürüyordu — oysa ekrandaki grafikte beş yıllık
veri duruyordu.

KÖK NEDEN
---------
İki ayrı eksik aynı yere çıkıyordu:

1. Takip mesajı BAĞIMSIZ bir soru gibi işleniyordu. "bunları line yap"
   cümlesinde ne metrik var, ne varlık, ne yıl. Retrieval haklı olarak
   hiçbir şey bulamıyor, elde tek bir şey kalmıyor ve "tek nokta"
   gerekçesi oradan çıkıyordu. Oysa istenen veri BİR ÖNCEKİ CEVAPTA
   hazır duruyordu.

2. Grafik türü yalnızca ÜRETİM anında seçilebiliyordu. Üretilmiş bir
   grafiğin türünü değiştirmenin yolu yoktu; tek yol veriyi baştan
   çekmekti.

ÇÖZÜM
-----
Tür değişimi bir SORU değil, bir DÖNÜŞTÜRME işlemidir. Bu modül:

    · takip mesajındaki tür niyetini deterministik olarak okur,
    · konuşmanın son grafiklerini hatırlar,
    · aynı veriyi istenen türe çevirir.

Yeni sorgu yok, yeni model çağrısı yok, yeni DB taraması yok. Veri
zaten elde; değişen tek şey onu nasıl çizdiğimiz.

DÖNÜŞTÜRME İLKESİ
-----------------
Kullanıcı bir tür istediyse ve veri o türe MANTIKLI biçimde
çevrilebiliyorsa çevrilir. "Pasta grafik yalnızca şu durumda olur"
türünden kısıtlar konmaz — kullanıcının ne göreceğine kullanıcı karar
verir.

Tek gerçek engel anlamsızlığa dönüşen durumlardır ve bunlar sayılıdır:
pay grafiği negatif değerle ya da tek bir dilimle çizilemez. Böyle bir
durumda cevap bozulmaz: en yakın anlamlı tür çizilir ve NEDEN
değiştirildiği tek cümleyle söylenir.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.assistant import chart_builder

logger = logging.getLogger(__name__)

#: Konuşma başına saklanan son ÇİZİLEBİLİR ÇIKTI: grafikler, turun
#: yapılandırılmış sonucu ve görünür metin. Süreç içi, sınırlı ve
#: yalnızca dönüştürme için: kalıcı bir depo değil.
_MAKS_KONUSMA = 200
_SON_CIKTI: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

#: Kullanıcının söyleyebileceği tür adları → CANONICAL tür.
#: `pie` ve `donut` AYRI tutulur: ikisi aynı veriyi gösterir ama biri
#: dolu daire, diğeri halkadır. Eskiden "pasta" da `donut`a çevriliyor,
#: arayüzde ise `donut` dalı yatay çubuk çiziyordu — kullanıcı ne pasta
#: ne halka görüyordu. Alias katmanı kullanıcı dilini karşılar, canonical
#: ad iki katman arasında tek sözleşmedir.
_TUR_ESLEME: Tuple[Tuple[str, str], ...] = (
    (r"\b(line|cizgi|çizgi|lineer|trend grafi)\w*", "line"),
    (r"\b(horizontal[_ ]?bar|yatay (?:cubuk|çubuk|bar|sutun|sütun))\w*",
     "hbar"),
    (r"\b(hbar)\b", "hbar"),
    (r"\b(donut|halka)\w*", "donut"),
    (r"\b(pie|pasta)\w*", "pie"),
    (r"\b(bar|sutun|sütun|cubuk|çubuk|column)\w*", "bar"),
    (r"\b(scatter|dagilim grafi|dağılım grafi|nokta grafi)\w*", "scatter"),
    (r"\b(stacked|yigin|yığın)\w*", "stacked"),
    (r"\b(grouped|grupl)\w*", "grouped"),
)
#: Pay gösteren türler — uygunluk kuralları ikisinde de aynıdır.
_PAY_TURLERI = ("pie", "donut")
_TUR_KALIPLARI = tuple((re.compile(k, re.I), t) for k, t in _TUR_ESLEME)

#: Takip mesajını "yeni soru" değil "aynı şeyi başka türde göster"
#: yapan işaretler. Biri bile yeterli; hiçbiri yoksa mesaj normal
#: soru akışına gider ve mevcut davranış değişmez.
_GERI_ATIF = re.compile(
    r"\b(bunu|bunlari|bunları|bunlar|onu|onlari|onları|sunu|şunu|"
    r"ayni|aynı|bu veriyi|bu sonucu|bu grafi|o grafi|grafigi|grafiği|"
    r"this|these|it|same)\b", re.I)
#: "bar yerine line", "line olarak göster", "line'a çevir" gibi
#: DOĞRUDAN tür komutları — geri atıf sözcüğü olmasa da takip sayılır.
_TUR_KOMUTU = re.compile(
    r"\b(yerine|olarak|olsun|yap\w*|cevir\w*|çevir\w*|donustur\w*|"
    r"dönüştür\w*|goster\w*|göster\w*|ciz\w*|çiz\w*|olustur\w*|"
    r"oluştur\w*|ver|m[iı]s[iı]n|as a|instead|make it|show)\b", re.I)

#: Mesajda BAŞKA bir konu var mı — varsa bu bir tür değişimi değil,
#: yeni bir sorudur ve normal akışa gitmelidir.
_YENI_KONU = re.compile(
    r"\b(kac|kaç|hangi|nedir|neden|nasil|nasıl|karsilastir|karşılaştır|"
    r"sirala|sırala|listele|yil|yıl|20\d\d|ortalama|toplam|trend[iı]|"
    r"analiz|yorumla|acikla|açıkla)\b", re.I)

#: Pay grafiğinin anlamlı olması için gereken en az dilim.
_EN_AZ_DILIM = 2


@dataclass
class Istek:
    """Takip mesajından okunan tür değişimi isteği."""

    tur: Optional[str] = None
    #: Mesaj YALNIZCA tür değişimi mi istiyor (yeni soru değil).
    sadece_tur: bool = False

    def __bool__(self) -> bool:
        return bool(self.tur)


def tur_oku(mesaj: str) -> Optional[str]:
    """Mesajdaki grafik türü — mevcut sözleşmenin adıyla.

    Sıra ÖNEMLİ: "bar yerine line" cümlesinde iki tür de geçiyor.
    Kalıplar en ayırt ediciden başlar ve İLK eşleşme kazanır; ama
    "yerine" kalıbı varsa ondan SONRA gelen tür istenen türdür —
    "X yerine Y" ifadesinde hedef Y'dir.
    """
    if not mesaj:
        return None
    yerine = re.search(r"\byerine\b|\binstead of\b", mesaj, re.I)
    aranan = mesaj[yerine.end():] if yerine else mesaj
    bulunan = _ilk_tur(aranan)
    if bulunan is None and yerine:
        # "line yerine bar" biçiminde hedef sonda; bulunamadıysa
        # cümlenin tamamına bakılır.
        bulunan = _ilk_tur(mesaj)
    return bulunan


def _ilk_tur(metin: str) -> Optional[str]:
    en_erken: Optional[Tuple[int, str]] = None
    for kalip, tur in _TUR_KALIPLARI:
        eslesme = kalip.search(metin)
        if eslesme and (en_erken is None or eslesme.start() < en_erken[0]):
            en_erken = (eslesme.start(), tur)
    return en_erken[1] if en_erken else None


def istek_oku(mesaj: str) -> Istek:
    """Takip mesajı bir tür değişimi mi.

    KARAR DAR TUTULUR. "2025 doluluk oranını bar chart göster" bir tür
    değişimi DEĞİL, yeni bir sorudur: içinde yıl ve metrik var, elde
    olan veriye atıf yok. Böyle bir mesajı dönüştürme yoluna sokmak
    kullanıcının sorduğu şeyi görmezden gelmek olurdu.

    Tür değişimi sayılması için:
      · bir tür adı geçmeli,
      · geri atıf ya da doğrudan tür komutu bulunmalı,
      · yeni bir konu (yıl, metrik, soru sözcüğü) GEÇMEMELİ.
    """
    tur = tur_oku(mesaj)
    if not tur:
        return Istek()
    atif = bool(_GERI_ATIF.search(mesaj) or _TUR_KOMUTU.search(mesaj))
    yeni_konu = bool(_YENI_KONU.search(mesaj))
    return Istek(tur=tur, sadece_tur=atif and not yeni_konu)


# ---------------------------------------------------------------------------
# Konuşma hafızası
# ---------------------------------------------------------------------------
def hatirla(konusma_id: Optional[str],
            grafikler: Optional[List[Dict[str, Any]]] = None,
            *, metin: Optional[str] = None,
            yapisal: Any = None) -> None:
    """Turun ÇİZİLEBİLİR ÇIKTISINI konuşmaya bağlar.

    Yalnızca grafik saklamak yetmiyordu: kullanıcı grafiksiz ama
    tablolu bir cevap alıp "line yap" dediğinde elde hiçbir şey
    kalmıyordu. Artık üç şey birden tutulur — grafikler, turun
    yapılandırılmış sonucu ve görünür metin. Üçü de AYNI turun
    çıktısıdır; hangisinin işe yarayacağına dönüştürme anında karar
    verilir.

    BOŞ DEĞER ÜSTÜNE YAZMAZ. Grafiksiz bir tur, bir önceki turun
    grafiğini silmemeli; aynı şekilde metinsiz bir tur eski metni
    silmemeli.
    """
    if not konusma_id:
        return
    if len(_SON_CIKTI) > _MAKS_KONUSMA:
        _SON_CIKTI.clear()
    kayit = _SON_CIKTI.setdefault(konusma_id, {})
    if grafikler:
        kayit["grafikler"] = [dict(g) for g in grafikler]
    if yapisal:
        kayit["yapisal"] = yapisal
    if (metin or "").strip():
        kayit["metin"] = metin


def son_grafikler(konusma_id: Optional[str]) -> List[Dict[str, Any]]:
    kayit = _SON_CIKTI.get(konusma_id or "", {})
    return [dict(g) for g in (kayit.get("grafikler") or [])]


def son_cikti(konusma_id: Optional[str]) -> Dict[str, Any]:
    """Turun bütün çizilebilir izleri — grafik, yapısal sonuç, metin."""
    return dict(_SON_CIKTI.get(konusma_id or "", {}))


def unut(konusma_id: Optional[str]) -> None:
    _SON_CIKTI.pop(konusma_id or "", None)


# ---------------------------------------------------------------------------
# Dönüştürme
# ---------------------------------------------------------------------------
def _noktalar(grafik: Dict[str, Any]) -> int:
    """Grafikteki GERÇEK veri noktası sayısı.

    "Tek nokta var" gerekçesinin yanlış çıkmasının sebebi buydu:
    kategori sayısına bakılıyor, serilerdeki değerler sayılmıyordu.
    Tek kategorili ama beş serili bir grafik beş noktadır.
    """
    sayi = 0
    for seri in grafik.get("series") or []:
        sayi += sum(1 for v in (seri.get("data") or []) if v is not None)
    return sayi


def _pay_uygun(grafik: Dict[str, Any]) -> Tuple[bool, str]:
    """Pay grafiği (pie/donut) bu veriyle çizilebilir mi.

    KULLANICININ İSTEĞİ REDDEDİLMEZ. "Bu veri gerçek bir parça-bütün
    ilişkisi değil" gerekçesiyle grafiği çizmemek, kullanıcının ne
    göreceğine onun yerine karar vermektir. Şart üçe indirildi ve
    üçü de matematikseldir:

        · en az iki değer  (tek dilim bir dağılım göstermez)
        · değerler sayısal
        · negatif değer yok (negatif bir payı temsil edemez)

    Bunlar sağlanıyorsa çizilir; oran yorumu için gerekiyorsa NOT
    düşülür, grafik yine de üretilir.
    """
    degerler = [v for seri in (grafik.get("series") or [])
                for v in (seri.get("data") or []) if v is not None]
    if not degerler:
        return False, "Grafikte sayısal değer yok; sütun grafiği kullanıldı."
    if any(float(v) < 0 for v in degerler):
        return False, ("Veride negatif değerler olduğu için pay grafiği "
                       "çizilemez; sütun grafiği kullanıldı.")
    if len(degerler) < _EN_AZ_DILIM:
        return False, ("Pay grafiği için en az iki değer gerekir; "
                       "sütun grafiği kullanıldı.")
    return True, ""


#: Pay grafiği çizildiğinde, veri gerçek bir parça-bütün ilişkisi
#: değilse eklenen not. Grafiği ENGELLEMEZ, yalnızca nasıl okunacağını
#: söyler.
NOT_PARCA_BUTUN = ("Bu grafik değerlerin görsel karşılaştırmasını "
                   "gösterir; oran toplamı olarak yorumlanmamalıdır.")


def _parca_butun_mu(grafik: Dict[str, Any]) -> bool:
    """Değerler toplanabilir mi — yani bir bütünün parçaları mı.

    Oran, yüzde ve sıra birimleri toplanamaz; bunların payı anlamlı
    bir "bütün" vermez. Grafik yine çizilir, sadece not eklenir.
    """
    return bool(grafik.get("additive", True))


def _paya_indirge(grafik: Dict[str, Any]) -> Dict[str, Any]:
    """Çok serili bir grafiği tek serili paya çevirir.

    Pay grafiği tek bir bütünün parçalarını gösterir; iki seriyi aynı
    halkaya koymak iki farklı bütünü karıştırmak olurdu. Çok seri
    varsa İLK seri kullanılır ve bu, alt başlıkta yazılır.
    """
    seriler = grafik.get("series") or []
    if len(seriler) <= 1:
        return grafik
    yeni = dict(grafik)
    yeni["series"] = [seriler[0]]
    ad = seriler[0].get("name") or ""
    onceki = grafik.get("subtitle") or ""
    ek = f"Pay grafiği tek seri gösterir: {ad}." if ad else ""
    yeni["subtitle"] = (f"{onceki} {ek}".strip() or None)
    return yeni


def donustur(grafik: Dict[str, Any], tur: str
             ) -> Tuple[Optional[Dict[str, Any]], str]:
    """Bir grafiği istenen türe çevirir. (grafik, not) döner.

    Veri KOPYALANIR, yeniden hesaplanmaz: kategoriler ve seriler
    olduğu gibi taşınır. Böylece dönüştürülmüş grafik ile metin cevabı
    ayrışamaz — ikisi hâlâ aynı sayıları anlatır.
    """
    if not isinstance(grafik, dict) or not grafik.get("series"):
        return None, ""
    if tur not in chart_builder.CHART_TYPES:
        return None, ""
    if grafik.get("chart_type") == tur:
        return dict(grafik), ""

    kaynak, not_metni = grafik, ""
    hedef = tur
    if tur in _PAY_TURLERI:
        uygun, sebep = _pay_uygun(grafik)
        if not uygun:
            hedef, not_metni = "bar", sebep
        else:
            kaynak = _paya_indirge(grafik)
            if not _parca_butun_mu(grafik):
                not_metni = NOT_PARCA_BUTUN

    yeni = dict(kaynak)
    yeni["chart_type"] = hedef
    # Yığılmış türler oran verisinde anlamsızdır: yüzdeleri üst üste
    # koymak %190 gibi bir toplam gösterir.
    if hedef in ("stacked", "stacked_bar") and not kaynak.get("additive", True):
        yeni["chart_type"] = "bar"
        not_metni = not_metni or ("Oran verisi yığılamaz; sütun grafiği "
                                  "kullanıldı.")
    return yeni, not_metni


def donustur_hepsi(grafikler: List[Dict[str, Any]], tur: str
                   ) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Çok metrikli listeyi topluca çevirir.

    HER GRAFİK AYRI DEĞERLENDİRİLİR. Biri paya uygun değilse yalnızca
    o sütuna düşer; diğerleri istenen türde çizilir. Tek bir uygunsuz
    grafik yüzünden bütün listeyi reddetmek, kullanıcının istediği
    dönüşümü sebepsiz iptal etmek olurdu.
    """
    cikti: List[Dict[str, Any]] = []
    notlar: List[str] = []
    for grafik in grafikler or []:
        yeni, notu = donustur(grafik, tur)
        if yeni is None:
            continue
        cikti.append(yeni)
        if notu and notu not in notlar:
            notlar.append(notu)
    return cikti, notlar


def satirlardan_grafik(kategoriler: List[str], degerler: List[Any],
                       tur: str, baslik: str, **ek) -> Optional[Dict[str, Any]]:
    """Kategori-değer çiftlerinden doğrudan grafik — kapalı şemayla."""
    return chart_builder._chart(
        tur if tur in chart_builder.CHART_TYPES else "bar",
        baslik, kategoriler, [{"name": ek.pop("seri_adi", baslik),
                               "data": degerler}], **ek)


# ---------------------------------------------------------------------------
# Metin ile grafik çelişmesin
# ---------------------------------------------------------------------------
#: Grafiğin ÜRETİLEMEDİĞİNİ söyleyen cümleler. Dönüştürme başarılı
#: olduğunda bu cümleler OLGUSAL OLARAK YANLIŞTIR: grafik ekranda
#: duruyor. Yanlış "tek nokta var" gerekçesi tam olarak buradan
#: geliyordu — model, takip mesajında veriyi göremediği için grafiğin
#: imkânsız olduğunu yazıyordu.
_OLUMSUZ = re.compile(
    r"(olu[sş]turulamaz|olu[sş]turulamad[iı]|[cç]izilemez|[cç]izilemedi|"
    r"[uü]retilemez|[uü]retilemedi|m[uü]mk[uü]n de[gğ]il|"
    r"tek (?:bir )?nokta|yeterli veri (?:yok|bulunam)|"
    r"grafi[kğ]e d[oö]n[uü][sş]t[uü]r[uü]lemez)", re.I)

_CUMLE = re.compile(r"[^.!?\n]+[.!?\n]?")

#: Dönüştürme başarılıysa kullanıcıya söylenen tek cümle.
_ONAY = {"line": "çizgi", "bar": "sütun", "hbar": "yatay sütun",
         "pie": "pasta", "donut": "halka",
         "scatter": "dağılım", "stacked": "yığılmış",
         "stacked_bar": "yığılmış sütun", "grouped": "gruplanmış"}


def celiski_temizle(metin: str, tur: str) -> str:
    """Grafik çizildiyse "çizilemez" cümlesi metinde kalmamalı.

    KAPSAM DAR: yalnızca grafiğin üretilemediğini İDDİA EDEN cümleler
    düşer. Analiz, sayılar, yorum ve cevabın geri kalanı aynen kalır —
    "model metnini tamamen silme" ilkesi burada da geçerli. Silinen
    şey bir görüş değil, artık doğru olmayan bir olgu iddiasıdır.
    """
    onay = f"Aynı veri {_ONAY.get(tur, tur)} grafiğine dönüştürüldü."
    if not (metin or "").strip():
        return onay
    tutulan = [c for c in _CUMLE.findall(metin) if not _OLUMSUZ.search(c)]
    govde = "".join(tutulan).strip()
    if not govde:
        return onay
    return govde if onay in govde else f"{onay}\n\n{govde}"


# ---------------------------------------------------------------------------
# GÖRÜNÜR METİNDE GRAFİK KODU OLMAZ
# ---------------------------------------------------------------------------
"""ÖLÇÜLEN ARIZA: kullanıcı ekranda ham `render_chart` bloğu görüyordu.

Model bazen grafiği bir araç çağrısıyla değil, cevabın içine gömülü
bir kod bloğu yazarak istiyor. O blok araç katmanına hiç ulaşmıyor,
doğrudan metin olarak kullanıcıya gidiyor. Sonuç: ekranda grafik
yerine JSON.

Yönerge katmanı ("chart kodu yazma") ilk savunmadır ama tek başına
yeterli değildir — modelin her turda uyacağının garantisi yok. Bu
yüzden çıkışta deterministik bir temizlik var.

KAPSAM DAR: yalnızca GRAFİK YÜKÜ olduğu belli bloklar düşer.
Kullanıcının sorduğu bir SQL ya da Python örneği silinmez; blok
`render_chart` etiketli değilse ve içinde grafik alanları
(`chart_type`, `x_field`, `series`…) yoksa dokunulmaz.
"""

#: ```render_chart ... ``` — etiketli blok. Kapanış çiti EKSİK olabilir;
#: model bazen bloğu kapatmadan bitiriyor, bu yüzden kapanış isteğe
#: bağlı ve metin sonuna kadar alınır.
_FENCE_ETIKETLI = re.compile(
    r"```[ \t]*(?:render[_ ]?chart|chart|grafik)[^\n]*\n.*?(?:```|\Z)",
    re.I | re.S)
#: ```json ... ``` — yalnızca İÇİ grafik yüküyse silinir.
_FENCE_JSON = re.compile(r"```[ \t]*(?:json)?[^\n]*\n(.*?)(?:```|\Z)",
                         re.I | re.S)
#: Çitsiz kalmış çıplak JSON gövdesi; yalnızca grafik alanı taşıyorsa.
_CIPLAK_JSON = re.compile(r"\{[^{}]*\}", re.S)
#: Bir bloğu GRAFİK YÜKÜ yapan alanlar. İkisi birden gerekmez ama
#: rastgele bir JSON'un bunları taşıması beklenmez.
_GRAFIK_ALANI = re.compile(
    r'"?(chart_type|source_tool|x_field|y_field|series_field|'
    r'render_chart|categories|datasets)"?\s*:', re.I)
#: Yalnız `data`/`x`/`y` taşıyan yükler de grafik sayılır ama bu alanlar
#: tek başına çok genel; en az ikisi birden aranır.
_ZAYIF_ALAN = re.compile(r'"?(data|labels|x|y|type|title)"?\s*:', re.I)


def _grafik_yuku_mu(govde: str) -> bool:
    if _GRAFIK_ALANI.search(govde or ""):
        return True
    return len(set(m.group(1).lower()
                   for m in _ZAYIF_ALAN.finditer(govde or ""))) >= 3


def _bos_satirlari_topla(metin: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", metin).strip()


@dataclass
class TemizlikSonucu:
    metin: str
    kaldirilan: int = 0


def kod_bloklarini_ayikla(metin: str) -> TemizlikSonucu:
    """Görünür metinden grafik kodu bloklarını çıkarır.

    CEVAP SİLİNMEZ. Kişi adı sanitizer'ıyla aynı ilke: sorunlu PARÇA
    temizlenir, cevabın kendisi değil. Blok çıktıktan sonra geriye
    doğal dil kalıyorsa o aynen kullanıcıya gider; hiçbir şey kalmazsa
    boş dize döner ve çağıran taraf kendi metnini koyar.
    """
    if not (metin or "").strip():
        return TemizlikSonucu(metin=metin or "")
    kaldirilan = 0

    yeni, sayi = _FENCE_ETIKETLI.subn("", metin)
    kaldirilan += sayi

    def _json_cit(eslesme):
        nonlocal kaldirilan
        if _grafik_yuku_mu(eslesme.group(1)):
            kaldirilan += 1
            return ""
        return eslesme.group(0)

    yeni = _FENCE_JSON.sub(_json_cit, yeni)

    def _ciplak(eslesme):
        nonlocal kaldirilan
        if _grafik_yuku_mu(eslesme.group(0)):
            kaldirilan += 1
            return ""
        return eslesme.group(0)

    yeni = _CIPLAK_JSON.sub(_ciplak, yeni)

    # ÖKSÜZ ÇİT YALNIZCA EŞLEŞMEYENDİR.
    # Silinen bloğun kapanış çiti geride kalmış olabilir. Ama bütün
    # tek satırlık çitleri silmek, kullanıcının sorduğu bir SQL/Python
    # bloğunun kapanışını da götürürdü. Bu yüzden yalnızca çit sayısı
    # TEK kaldıysa (yani eşleşmemiş bir çit var) sondaki tek çit
    # düşürülür ve bu, ancak bir blok gerçekten silindiyse yapılır.
    if kaldirilan:
        citler = re.findall(r"^[ \t]*```", yeni, flags=re.M)
        if len(citler) % 2 == 1:
            yeni = re.sub(r"\n?[ \t]*```[ \t]*(?=\n|$)", "", yeni, count=1)
    return TemizlikSonucu(metin=_bos_satirlari_topla(yeni),
                          kaldirilan=kaldirilan)
