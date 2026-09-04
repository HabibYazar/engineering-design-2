"""Metrik belirtilmemiş analitik sorular — soru sormak yerine ÖLÇMEK.

NEDEN DEĞİŞTİ
-------------
Önceki davranış: "Son iki yılda hangi mühendislikler yükseldi?" gibi bir
soruda metrik `UNKNOWN` kalıyor, sistem hiçbir kaynak seçmiyor ve
kullanıcıya "Hangi ölçüyü karşılaştırmamı istersiniz?" diye bir
netleştirme sorusu dönüyordu.

Bunun gerekçesi savunulabilirdi — rastgele bir ölçü seçip onu analiz
etmek, kendinden emin görünen yanlış bir cevap üretir. Ama çözüm yanlış
yerden tutuluyordu: asıl sorun TEK bir ölçü seçme zorunluluğuydu, ölçüyü
bilmemek değil. Kullanıcı "yükseldi mi" diye sorduğunda genellikle tek
bir sayı değil, PROGRAMIN GİDİŞATINI soruyor; taban puanı yükselirken
doluluğun düşmesi bir çelişki değil, cevabın kendisidir.

YENİ DAVRANIŞ
-------------
    metric=UNKNOWN
      → o entity/scope/time için ANLAMLI olan metrikleri katalogdan bul
      → her biri için kaynak seç (aynı kaynağı paylaşanlar tek sorguda)
      → gerçekten verisi olanları ayrı ayrı hesapla
      → tek yapılandırılmış kanıt üret
      → modele ver

Rastgele metrik seçme riski ortadan kalkmaz çünkü seçim YAPILMAZ:
ilgili ölçülerin hepsi ayrı ayrı raporlanır ve hangisinin anlatıldığı
her satırda yazılıdır.

NE YAPILMAZ
-----------
· Bileşik skor üretilmez. "Taban puanı %60, doluluk %40 ağırlıkla
  yükseliş endeksi" gibi bir sayı, kaynağı olmayan bir yargıdır.
· Verisi olmayan metrik için sıfır ya da tahmin üretilmez; atlanır ve
  atlandığı söylenir.
· Bütün veritabanı taranmaz. Seviye, zaman ve aile uygunluğu süzgeci
  önce çalışır; SQL yalnızca hayatta kalan 3–6 metrik için yapılır.
"""

from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.assistant import abu_kds_store as store
from app.services.assistant import entity_katalogu
from app.services.assistant import veri_ailesi
from app.services.assistant.veri_ailesi import (KAVRAMLAR, Kavram,
                                                KaynakProfili, SorguPlani,
                                                profiller, sadelestir)

logger = logging.getLogger(__name__)

#: Kaç metrik analiz edilir. Üstü kullanıcı için okunamaz hale gelir,
#: altı soruyu tek boyuta indirir.
EN_FAZLA_METRIK = 6
#: Bir metrik için kaç kaynak denenir. Metrik başına derin arama
#: yapılmaz; amaç kapsamlı olmak değil, DOĞRU olmak.
_EN_FAZLA_KAYNAK = 2
#: Tek sorguda çekilen satır tavanı (`abu_kds_store` sınırı 200).
_SATIR_TAVANI = 200
#: Sıralamada gösterilen uç sayısı.
_UC_SAYISI = 5
#: "Değişmedi" sayılan bant. Yüzde biriminde puan farkı, diğerlerinde
#: göreli değişim olarak uygulanır.
_DURAGAN_ESIK = 1.0

#: Kanıtı taşıyan sanal araç adı. `used_tools` içinde görünür; adı
#: gerçeği söyler — model bu aracı çağırmadı, backend hesapladı.
ARAC_ADI = "multi_metric_analysis"
VERI_KAYNAGI = "Merkezi KDS veritabanı (çok metrikli analiz)"

#: Toplanabilir birimler. Kişi ve adet toplanır; puan, oran, yüzde,
#: sıra ve para birimi TOPLANMAZ — yüzdelerin toplamı anlamsız,
#: ortalaması yanıltıcıdır (bkz. `veri_ozeti` ile aynı ilke).
_TOPLANABILIR = ("kişi", "adet")
#: Küçük değerin İYİ olduğu birimler. Yön kelimesi yine olgusal
#: kalır ("azaldı"); yorumu modele bırakmak için yalnızca not düşülür.
_KUCUK_IYI = ("sıra",)


# ---------------------------------------------------------------------------
# 1) HANGİ METRİKLER ANLAMLI
# ---------------------------------------------------------------------------
def _aile_sirasi(plan: SorguPlani) -> Tuple[str, ...]:
    """Sorunun seviyesine göre veri ailelerinin öncelik sırası.

    Bu sıra `veri_ailesi.onerilen_metrikler` ile AYNI kaynaktan gelir;
    iki yerde iki farklı öncelik tanımlamak, aynı soruya iki farklı
    metrik kümesi üretirdi.
    """
    if plan.program_seviyesi:
        return ("yks_admissions", "students", "academic_staff",
                "tuition_finance")
    if plan.universite_seviyesi:
        return ("students", "academic_staff", "yks_admissions",
                "tuition_finance")
    return ("students", "yks_admissions", "academic_staff", "infrastructure")


def _kavram(anahtar: str) -> Optional[Kavram]:
    return next((k for k in KAVRAMLAR if k.anahtar == anahtar), None)


def _metrik_kaynaklari(anahtar: str, plan: SorguPlani
                       ) -> List[KaynakProfili]:
    """Bu metriği GERÇEKTEN taşıyan ve sorunun seviyesine uyan kaynaklar.

    Seviye süzgeci sert uygulanır: program sorusunda kurum toplamı
    veren tablo, kurum sorusunda oda düzeyi tablo işe yaramaz. Rule of
    thumb değil, ölçülen davranış: bu süzgeç olmadan program eğilimi
    sorusuna derslik kapasitesi karışıyordu.
    """
    uygun = [p for p in profiller().values() if anahtar in p.kavramlar]
    if plan.program_seviyesi:
        uygun = [p for p in uygun if p.program_seviyesi]
    elif plan.universite_seviyesi:
        uygun = [p for p in uygun if p.universite_seviyesi]
    return uygun


def _uygunluk(kav: Kavram, plan: SorguPlani) -> float:
    """Metriğin bu soru bağlamındaki anlamlılığı. 0 = dahil edilmez."""
    kaynaklar = _metrik_kaynaklari(kav.anahtar, plan)
    if not kaynaklar:
        return 0.0

    puan = 1.0
    if plan.yillar:
        # ZAMAN ŞARTTIR. Eğilim/sıralama sorusunda tek yıllık bir ölçü
        # "yükseldi mi" sorusunu cevaplayamaz; sessizce tek yılın
        # değerini eğilim gibi sunmaktansa metriği hiç almamak doğru.
        kapsam = max(sum(1 for y in plan.yillar if p.yil_kapsar(y))
                     for p in kaynaklar)
        if kapsam < 2:
            return 0.0
        puan += 4.0 * kapsam / len(plan.yillar)
    elif any(p.yil_araligi for p in kaynaklar):
        puan += 1.0

    sira = _aile_sirasi(plan)
    if kav.aile in sira:
        puan += 3.0 * (len(sira) - sira.index(kav.aile)) / len(sira)
    elif plan.aileler and kav.aile not in plan.aileler:
        # Sorunun seviyesiyle ilgisiz aile: eleme değil, geri alma.
        puan -= 1.0

    if max((p.satir_sayisi or 0) for p in kaynaklar) >= 5:
        puan += 1.0
    return puan


def uygun_metrikler(plan: SorguPlani, *, en_fazla: int = EN_FAZLA_METRIK
                    ) -> List[str]:
    """Bu soru için anlamlı metrik anahtarları — koda yazılmadan.

    Üç süzgeç sırayla uygulanır ve üçü de VERİDEN gelir:

      1. Ölçülebilirlik — `birim` alanı boş olan kavram (stratejik
         hedef, üniversite künyesi, benzer program eşleşmesi) bir
         eğilim ya da sıralama üretemez.
      2. Varlık — kavram veritabanındaki hiçbir kaynakta yoksa
         analize girmez. "DB'de olmayan metriği analiz etme" kuralı
         burada yapısal olarak sağlanır.
      3. Seviye ve zaman — `_uygunluk`.
    """
    mevcut = {a for p in profiller().values() for a in p.kavramlar}
    puanli: List[Tuple[float, str]] = []
    for kav in KAVRAMLAR:
        if not kav.birim or kav.anahtar not in mevcut:
            continue
        p = _uygunluk(kav, plan)
        if p > 0:
            puanli.append((p, kav.anahtar))
    puanli.sort(key=lambda x: (-x[0], x[1]))
    return [a for _, a in puanli[:max(1, en_fazla)]]


# ---------------------------------------------------------------------------
# 2) SÜTUN VE KAYNAK EŞLEME
# ---------------------------------------------------------------------------
def _sutun_bul(kav: Kavram, sutunlar: Sequence[str]) -> Optional[str]:
    """Kavramın bu kaynaktaki sütun karşılığı.

    Alt-dize eşleşmesi tek başına yeterli değil: `base_score` ipucu
    "score", `success_rank` sütunundaki "score" ile de eşleşebilir.
    Bu yüzden eşleşmeler DERECELENİR — tam ad, başlangıç, sonra
    içerme — ve en uzun ipucu kazanır.
    """
    en_iyi: Tuple[int, int, str] = (0, 0, "")
    for sut in sutunlar:
        sade = sadelestir(sut)
        for ipucu in kav.sutun:
            if sade == ipucu:
                derece = 3
            elif sade.startswith(ipucu) or sade.endswith(ipucu):
                derece = 2
            elif ipucu in sade:
                derece = 1
            else:
                continue
            aday = (derece, len(ipucu), sut)
            if aday > en_iyi:
                en_iyi = aday
    return en_iyi[2] or None


def _kaynak_sec(anahtar: str, plan: SorguPlani) -> List[str]:
    """Metriğin kaynakları — mevcut `aday_kaynaklar` puanlamasıyla.

    Kaynak seçimi YENİDEN YAZILMAZ: plan kopyalanır, tek metriğe
    daraltılır ve mevcut retrieval çalıştırılır. Böylece yıl kapsaması,
    seviye uyumu ve çok kaynaklı tamamlama davranışı aynen korunur.
    """
    kav = _kavram(anahtar)
    if kav is None:
        return []
    alt = SorguPlani(
        soru=plan.soru, niyet=plan.niyet, aileler=[kav.aile],
        kavramlar=[anahtar], yillar=list(plan.yillar),
        program_seviyesi=plan.program_seviyesi,
        universite_seviyesi=plan.universite_seviyesi,
        varlik=plan.varlik, varlik_turu=plan.varlik_turu,
        kapsam_varligi=plan.kapsam_varligi, kapsam_turu=plan.kapsam_turu,
        varlik_grubu=plan.varlik_grubu)
    return [ad for ad, _ in veri_ailesi.aday_kaynaklar(
        alt, en_fazla=_EN_FAZLA_KAYNAK)]


def _varlik_sutunu(prof: KaynakProfili, plan: SorguPlani) -> Optional[str]:
    """Sıralamada satırları kime ait sayacağımızı belirleyen sütun."""
    if plan.universite_seviyesi and not plan.program_seviyesi:
        oncelik = ("university_name", "universite", "kurum")
    else:
        oncelik = ("program_name", "program", "department", "bolum",
                   "faculty", "fakulte")
    for ipucu in oncelik:
        for sut in prof.sutunlar:
            if sadelestir(sut) == ipucu:
                return sut
    for ipucu in oncelik:
        for sut in prof.sutunlar:
            if ipucu in sadelestir(sut):
                return sut
    return None


#: Bir satırı KİM'e ait yapan sütunlar. Şema sözlüğüdür, iş verisi
#: değil: hiçbir program, üniversite ya da metrik adı geçmez.
_KIMLIK = re.compile(
    r"(universit|kurum|program|bolum|department|fakulte|faculty|"
    r"scholarship|burs|score_type|puan_tur|language|dil)", re.I)
#: Kod/kimlik alanları ayırt eder ama OKUNMAZ. "209510222" bir program
#: adı değildir; etikete girerse kullanıcı ne gördüğünü anlamaz.
_KOD = re.compile(r"(code|kod|_id$|^id$|no$)", re.I)
#: Etikette en fazla kaç alan birleşir. Üçü aşınca satır okunmaz olur.
_EN_FAZLA_KIMLIK = 3


def _kimlik_sutunlari(prof: KaynakProfili, plan: SorguPlani,
                      satirlar: Sequence[Dict[str, Any]]) -> List[str]:
    """Gözlem birimini oluşturan sütunlar.

    NEDEN TEK SÜTUN YETMİYOR: `kds_yks_ankara_taban_puan_5yil` içinde
    "Bilgisayar Mühendisliği" yirmi ayrı üniversitede geçiyor;
    `kds_yks_abu_4year` içinde aynı program hem "Burslu" hem "Ücretli"
    olarak. Yalnızca program adına bakınca bu satırlar tek varlık
    sanılıyor, yıllar arasındaki fark da kapsam kaymasından geliyordu.

    Sabit değer taşıyan sütun kimliğe girmez: her satırda aynı olan bir
    alan ayırt etmez, yalnızca etiketi uzatır.
    """
    ana = _varlik_sutunu(prof, plan)
    secilen: List[str] = [ana] if ana else []
    for sut in prof.sutunlar:
        if sut in secilen or not _KIMLIK.search(sut) or _KOD.search(sut):
            continue
        farkli = {str(r.get(sut)) for r in satirlar[:_SATIR_TAVANI]}
        if len(farkli) > 1:
            secilen.append(sut)
        if len(secilen) >= _EN_FAZLA_KIMLIK:
            break
    return secilen


def _varlik_adi(satir: Dict[str, Any], kimlik: Sequence[str]) -> str:
    degerler = [str(satir.get(s) or "").strip() for s in kimlik]
    degerler = [d for d in degerler if d]
    if not degerler:
        return ""
    return degerler[0] + (f" ({', '.join(degerler[1:])})"
                          if len(degerler) > 1 else "")


def _yil(deger: Any) -> Optional[int]:
    """`2021` ve `2020-2021` biçimlerini tek ölçeğe indirir.

    Metinde iki yıl varsa BÜYÜĞÜ alınır: "2020-2021" akademik yılı
    2021'de biter ve kaynakların yıl aralığı da bu ölçeğe göre
    hesaplanmıştı; iki ölçek karışırsa aynı satır iki farklı yıla
    düşer.
    """
    yillar = veri_ailesi._YIL_DEGER.findall(str(deger or ""))
    return max(int(y) for y in yillar) if yillar else None


def _sayi(deger: Any) -> Optional[float]:
    """NULL SIFIR DEĞİLDİR — ölçülmemiş değer hesaba girmez."""
    if deger is None or isinstance(deger, bool):
        return None
    if isinstance(deger, (int, float)):
        return float(deger)
    metin = str(deger).strip().replace("%", "").replace(",", ".")
    try:
        return float(metin)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 3) KANIT
# ---------------------------------------------------------------------------
@dataclass
class MetrikKaniti:
    metrik: str
    etiket: str
    birim: str
    kaynak: str
    sutun: str
    #: (yıl, değer, o yıldaki kayıt sayısı)
    noktalar: List[Tuple[int, float, int]] = field(default_factory=list)
    yontem: str = "medyan"
    delta: Optional[float] = None
    yuzde: Optional[float] = None
    yon: str = "belirsiz"
    #: (varlık adı, ilk değer, son değer, fark) — sıralama niyetinde.
    siralama: List[Tuple[str, float, float, float]] = field(
        default_factory=list)
    kucuk_iyi: bool = False
    #: Yıl değerleri AYNI varlık kümesinden mi hesaplandı. Değilse
    #: karşılaştırma yıllar arasında elmayla armut kıyaslar; kullanıcıya
    #: ve modele bu söylenir.
    dengeli: bool = False

    @property
    def yeterli(self) -> bool:
        return len(self.noktalar) >= 2


@dataclass
class Kanit:
    metrikler: List[MetrikKaniti] = field(default_factory=list)
    #: (metrik etiketi, atlanma sebebi) — sessizce yok sayılmaz.
    atlanan: List[Tuple[str, str]] = field(default_factory=list)
    kapsam: str = ""
    yillar: List[int] = field(default_factory=list)
    sorgu_sayisi: int = 0

    @property
    def var(self) -> bool:
        return any(m.yeterli for m in self.metrikler)

    def kaynaklar(self) -> List[str]:
        return list(dict.fromkeys(m.kaynak for m in self.metrikler))

    def satir_sayisi(self) -> int:
        return sum(n for m in self.metrikler for _, _, n in m.noktalar)


def _birlestir(degerler: List[float], birim: str) -> Tuple[float, str]:
    """Bir yılın çok satırını tek sayıya indirir.

    Kişi/adet TOPLANIR (toplam kontenjan, toplam yerleşen). Puan, oran,
    yüzde, sıra ve para MEDYANLA özetlenir — yüzdelerin ortalaması
    kontenjanları farklı programlarda yanıltıcıdır, medyan ise
    dağılımın kendisinden okunur ve bileşik bir sayı uydurmaz.
    """
    if birim in _TOPLANABILIR:
        return float(sum(degerler)), "toplam"
    return float(statistics.median(degerler)), "medyan"


def _yon(delta: float, ilk: float, birim: str) -> Tuple[str, Optional[float]]:
    if birim == "%":
        # Yüzdenin yüzdesi kafa karıştırır; fark PUAN olarak verilir.
        return (("arttı" if delta > _DURAGAN_ESIK else
                 "azaldı" if delta < -_DURAGAN_ESIK else "değişmedi"), None)
    yuzde = (delta / abs(ilk) * 100.0) if ilk else None
    olcut = yuzde if yuzde is not None else delta
    return (("arttı" if olcut > _DURAGAN_ESIK else
             "azaldı" if olcut < -_DURAGAN_ESIK else "değişmedi"), yuzde)


def _grup_suzgeci(plan: SorguPlani) -> List[str]:
    """Soru bir varlık grubunu işaret ediyorsa üyeleri — katalogdan."""
    if not plan.varlik_grubu:
        return []
    try:
        return entity_katalogu.grup_uyeleri(plan.varlik_grubu)
    except Exception:  # noqa: BLE001
        logger.debug("grup üyeleri okunamadı", exc_info=True)
        return []


#: Zaman aralığı söylenmemiş eğilim sorularında bakılan yıl sayısı.
#: Sabit bir takvim yılı DEĞİL: kaynağın kendi kapsamasının son N yılı.
_VARSAYILAN_PENCERE = 3


def _hedef_yillar(prof: KaynakProfili, plan: SorguPlani) -> List[int]:
    """Bu kaynakta hangi yıllara bakılacak.

    Kullanıcı "son 2 yıl" dediyse o. Demediyse — "hangi bölümler
    geriledi?" — yıl bilgisi yok ama soru yine bir DEĞİŞİM soruyor.
    Böyle bir soruya tek yılın fotoğrafını göstermek cevap değildir;
    kaynağın kendi kapsamasının son yılları alınır. Takvim yılı koda
    yazılmaz, kaynaktan okunur.
    """
    if plan.yillar:
        return sorted(plan.yillar)
    if not prof.yil_araligi:
        return []
    alt, ust = prof.yil_araligi
    return list(range(max(alt, ust - _VARSAYILAN_PENCERE + 1), ust + 1))


def _yil_kosulu(kaynak: str, yil_sut: str, alt_yil: int
                ) -> Optional[Tuple[str, str, Any]]:
    """Yıl süzgecini SQL'e taşır — 200 satır tavanı sonucu bozmasın.

    ÖLÇÜLEN ARIZA: süzgeç Python tarafında uygulanınca `LIMIT 200` en
    yeni yıla yığılıyor, önceki yıllardan hiç satır gelmiyordu; iki yıl
    istenen soruda ikinci yıl "veri yok" görünüyordu.

    Yıl iki biçimde saklanıyor (`2021` ve `2020-2021`). Biçim
    tahmin EDİLMEZ, tek satır okunup bakılır: yanlış tipte bir
    karşılaştırma SQLite'ta hata vermez, sessizce boş sonuç döner.
    """
    try:
        ornek = store.satirlar(kaynak, secilen=[yil_sut], sinir=1)
    except Exception:  # noqa: BLE001
        return None
    if not ornek:
        return None
    ham = ornek[0].get(yil_sut)
    if isinstance(ham, (int, float)) and not isinstance(ham, bool):
        return (yil_sut, ">=", int(alt_yil))
    if isinstance(ham, str) and "-" in ham:
        return (yil_sut, ">=", f"{alt_yil - 1}-{alt_yil}")
    if isinstance(ham, str) and ham.strip().isdigit():
        return (yil_sut, ">=", str(alt_yil))
    return None


def _satirlari_getir(kaynak: str, prof: KaynakProfili, plan: SorguPlani,
                     uyeler: Sequence[str], varlik_sut: Optional[str],
                     yillar: Sequence[int]) -> List[Dict[str, Any]]:
    """Kaynağı BİR KEZ okur; aynı kaynaktaki metrikler bunu paylaşır."""
    kosullar: List[Tuple[str, str, Any]] = []
    if uyeler and varlik_sut:
        kosullar.append((varlik_sut, "IN", list(uyeler)[:50]))
    elif plan.varlik and varlik_sut:
        kosullar.append((varlik_sut, "LIKE", f"%{plan.varlik}%"))
    if yillar and prof.yil_sutunu:
        yil_kos = _yil_kosulu(kaynak, prof.yil_sutunu, min(yillar))
        if yil_kos:
            kosullar.append(yil_kos)

    # SIRALAMA VARLIĞA GÖRE, YILA GÖRE DEĞİL.
    # Yıla göre sıralayıp kırpmak, en yeni yılın satırlarını alıp
    # önceki yılları düşürür ve karşılaştırma tek yıla çöker. Varlığa
    # göre sıralandığında kırpma varlık kümesini daraltır ama her
    # varlığın BÜTÜN yılları bir arada kalır.
    sirala = varlik_sut or prof.yil_sutunu
    try:
        satirlar = store.satirlar(
            kaynak, kosullar=kosullar or None, sirala=sirala,
            sinir=_SATIR_TAVANI)
    except Exception:  # noqa: BLE001
        logger.debug("%s okunamadı", kaynak, exc_info=True)
        return []
    if satirlar or not kosullar:
        return satirlar
    # SÜZGEÇ TUTMADIYSA VERİ YOK DEMEK DEĞİL. Kaynağın varlık sütunu
    # kanonik adlardan farklı yazıyor olabilir; süzgeçsiz okuyup
    # üyelikte Python tarafında eleriz.
    try:
        return store.satirlar(kaynak, sirala=sirala, sinir=_SATIR_TAVANI)
    except Exception:  # noqa: BLE001
        return []


def _uye_mi(ad: str, uyeler: Sequence[str]) -> bool:
    if not uyeler:
        return True
    sade = sadelestir(ad)
    return any(sadelestir(u) in sade or sade in sadelestir(u) for u in uyeler)


def _metrigi_hesapla(kav: Kavram, kaynak: str, prof: KaynakProfili,
                     satirlar: List[Dict[str, Any]], plan: SorguPlani,
                     uyeler: Sequence[str], yillar: Sequence[int],
                     kirpildi: bool = False
                     ) -> Tuple[Optional[MetrikKaniti], str]:
    """Tek metriğin deterministik hesabı. İkinci dönen değer: atlanma sebebi."""
    sutun = _sutun_bul(kav, prof.sutunlar)
    if not sutun:
        return None, "bu kaynakta karşılık gelen sütun yok"
    if not satirlar:
        return None, "bu kapsamda kayıt yok"
    varlik_sut = _varlik_sutunu(prof, plan)
    kimlik = _kimlik_sutunlari(prof, plan, satirlar)
    yil_sut = prof.yil_sutunu
    hedef = set(yillar)

    yil_degerleri: Dict[int, List[float]] = {}
    varlik_yil: Dict[str, Dict[int, List[float]]] = {}
    for satir in satirlar:
        deger = _sayi(satir.get(sutun))
        if deger is None:      # NULL SIFIR DEĞİLDİR
            continue
        if uyeler and varlik_sut and not _uye_mi(
                str(satir.get(varlik_sut) or ""), uyeler):
            continue
        yil = _yil(satir.get(yil_sut)) if yil_sut else None
        if yil is None or (hedef and yil not in hedef):
            continue
        yil_degerleri.setdefault(yil, []).append(deger)
        ad = _varlik_adi(satir, kimlik)
        if ad:
            varlik_yil.setdefault(ad, {}).setdefault(yil, []).append(deger)

    if len(yil_degerleri) < 2:
        # Eğilim/sıralama sorusunda tek nokta cevap değildir. Sıfır ya
        # da tahmin üretmektense metrik atlanır ve sebebi söylenir.
        return None, "yeterli tarihsel veri yok"

    kanit = MetrikKaniti(
        metrik=kav.anahtar, etiket=kav.etiket or kav.anahtar,
        birim=kav.birim, kaynak=kaynak, sutun=sutun,
        kucuk_iyi=kav.birim in _KUCUK_IYI)
    gecerli = sorted(yil_degerleri)
    ilk_yil, son_yil = gecerli[0], gecerli[-1]

    # DENGELİ KÜME: yıl değerleri AYNI varlıklardan hesaplanır.
    # ------------------------------------------------------------------
    # Ölçülen arıza: 2024'te 179, 2025'te 21 kayıt geliyordu ve iki
    # yılın medyanı farklı program kümelerinden okunuyordu. Aradaki
    # fark eğilim gibi sunuluyordu, oysa değişen şey kümenin kendisiydi.
    ortak = [ad for ad, y in varlik_yil.items()
             if all(g in y for g in gecerli)]
    if len(ortak) >= 2:
        yil_degerleri = {
            g: [d for ad in ortak for d in varlik_yil[ad][g]]
            for g in gecerli}

    for yil in gecerli:
        deger, yontem = _birlestir(yil_degerleri[yil], kav.birim)
        kanit.noktalar.append((yil, round(deger, 2), len(yil_degerleri[yil])))
        kanit.yontem = yontem

    # DENGE ÖLÇÜLÜR, VARSAYILMAZ.
    # Ortak varlık kümesine daraltmak yetmez: aynı program adı birden
    # çok üniversitede geçiyorsa yıl başına satır sayısı yine kayar.
    # Kıyas edilebilirlik, yılların KAYIT SAYISI oranından okunur;
    # ayrıca 200 satır tavanına dayanmış bir okuma eksiktir.
    sayilar = [n for _, _, n in kanit.noktalar]
    denge = min(sayilar) / max(sayilar) if max(sayilar) else 0.0
    kanit.dengeli = denge >= 0.8 and not kirpildi

    if denge >= 0.5:
        ilk, son = kanit.noktalar[0][1], kanit.noktalar[-1][1]
        kanit.delta = round(son - ilk, 2)
        kanit.yon, yuzde = _yon(kanit.delta, ilk, kav.birim)
        kanit.yuzde = round(yuzde, 1) if yuzde is not None else None
    else:
        # Yıllar arasında kapsam ikiye katlanmış ya da yarılanmışsa
        # aradaki fark eğilim değil, örneklem farkıdır. Sayı yazmak
        # yerine hesaplanmadığı söylenir — uydurmaktan iyidir.
        kanit.yon = "kapsam farkı nedeniyle hesaplanmadı"

    # VARLIK KIRILIMI: hangi varlıkta ne kadar değişti. Bileşik skor
    # değil — aynı metriğin iki uç yılı arasındaki fark.
    #
    # BİR VARLIK, BİR SATIR. Varlık uç yılların birinde birden çok kez
    # geçiyorsa (aynı program adı farklı üniversitelerde) o satırlar
    # toplanınca kırpma etkisi "düşüş" gibi görünür. Böyle bir varlık
    # kırılıma alınmaz: gözlem birimi o tabloda varlık değildir.
    uclar: List[Tuple[str, float, float, float]] = []
    for ad in (ortak or list(varlik_yil)):
        y = varlik_yil.get(ad) or {}
        if ilk_yil not in y or son_yil not in y:
            continue
        if len(y[ilk_yil]) != 1 or len(y[son_yil]) != 1:
            continue
        a, b = y[ilk_yil][0], y[son_yil][0]
        uclar.append((ad, round(a, 2), round(b, 2), round(b - a, 2)))
    uclar.sort(key=lambda x: -x[3])
    kanit.siralama = uclar
    return kanit, ""


def kanit_uret(plan: SorguPlani, *, en_fazla: int = EN_FAZLA_METRIK) -> Kanit:
    """Metrik belirtilmemiş soru için çok metrikli yapılandırılmış kanıt.

    Aynı kaynağı paylaşan metrikler TEK sorguda alınır: beş ölçü için
    beş ayrı gidiş-dönüş yapmak, aynı tabloyu beş kez okumak demekti.
    """
    kanit = Kanit(yillar=list(plan.yillar))
    if not store.kullanilabilir():
        return kanit

    metrikler = uygun_metrikler(plan, en_fazla=en_fazla)
    if not metrikler:
        return kanit

    prof = profiller()
    uyeler = _grup_suzgeci(plan)

    # Kaynak → o kaynaktan alınacak metrikler.
    plan_kaynak: Dict[str, List[str]] = {}
    for anahtar in metrikler:
        kaynaklar = _kaynak_sec(anahtar, plan)
        if not kaynaklar:
            kav = _kavram(anahtar)
            kanit.atlanan.append(
                ((kav.etiket if kav else anahtar), "uygun kaynak bulunamadı"))
            continue
        plan_kaynak.setdefault(kaynaklar[0], []).append(anahtar)

    for kaynak, anahtarlar in plan_kaynak.items():
        p = prof.get(kaynak)
        if p is None:
            continue
        varlik_sut = _varlik_sutunu(p, plan)
        yillar = _hedef_yillar(p, plan)
        satirlar = _satirlari_getir(kaynak, p, plan, uyeler, varlik_sut,
                                    yillar)
        kanit.sorgu_sayisi += 1
        for anahtar in anahtarlar:
            kav = _kavram(anahtar)
            if kav is None:
                continue
            m, sebep = _metrigi_hesapla(kav, kaynak, p, satirlar, plan,
                                        uyeler, yillar,
                                        len(satirlar) >= _SATIR_TAVANI)
            if m is None:
                kanit.atlanan.append((kav.etiket or anahtar, sebep))
            else:
                kanit.metrikler.append(m)

    kanit.metrikler.sort(key=lambda m: (-len(m.noktalar), m.etiket))
    kapsam = []
    if plan.varlik:
        kapsam.append(plan.varlik)
    elif plan.varlik_grubu and uyeler:
        kapsam.append(f"{plan.varlik_grubu} ({len(uyeler)} program)")
    if plan.yillar:
        kapsam.append(f"{min(plan.yillar)}-{max(plan.yillar)}")
    kanit.kapsam = " · ".join(kapsam)
    return kanit


# ---------------------------------------------------------------------------
# 4) METİN — hem modele hem deterministik cevaba
# ---------------------------------------------------------------------------
_BASLIK = (
    "ÇOK METRİKLİ ANALİZ — soruda ölçü belirtilmediği için bu kapsamda "
    "anlamlı olan TÜM ölçüler backend tarafından ayrı ayrı hesaplandı. "
    "Aşağıdaki sayılar kesindir: yeniden hesaplama, birleştirme ya da "
    "tek bir puana indirgeme. Ölçüler farklı yönde hareket edebilir; "
    "bu bir çelişki değil, cevabın kendisidir."
)


def _deger(m: MetrikKaniti, v: float) -> str:
    return f"{v:g}{'%' if m.birim == '%' else ''}"


def metin(kanit: Kanit, *, baslik: bool = True) -> str:
    """Kanıtı okunabilir, sıkı bir bloğa çevirir.

    Ham satır GÖNDERİLMEZ: 200 satırlık bir tablo modele verildiğinde
    hem bütçeyi yiyor hem de modelin kendi aritmetiğini yapmasına
    davetiye çıkarıyordu. Burada yalnızca hesaplanmış sayılar var.
    """
    if not kanit.var:
        return ""
    parcalar: List[str] = []
    if baslik:
        parcalar.append(_BASLIK)
    if kanit.kapsam:
        parcalar.append(f"Kapsam: {kanit.kapsam}")

    for m in kanit.metrikler:
        if not m.yeterli:
            continue
        satir = [f"[{m.etiket}] kaynak={m.kaynak} birim={m.birim or '-'} "
                 f"({m.yontem})"]
        satir.append("  " + " · ".join(
            (f"{y}: {_deger(m, v)} (n={n})" if y else
             f"{_deger(m, v)} (n={n}, yıl bilgisi yok)")
            for y, v, n in m.noktalar))
        if m.delta is None:
            satir.append(f"  değişim: {m.yon}")
        else:
            fark = (f"{m.delta:+g} puan" if m.birim == "%"
                    else f"{m.delta:+g} {m.birim}".strip())
            if m.yuzde is not None:
                fark += f" ({m.yuzde:+g}%)"
            satir.append(f"  değişim: {fark} — {m.yon}")
            if m.kucuk_iyi:
                satir.append("  not: bu ölçüde KÜÇÜK değer daha iyidir; "
                             "azalma iyileşme demektir.")
        if not m.dengeli:
            satir.append("  uyarı: yıllar aynı varlık kümesinden "
                         "hesaplanamadı; değişim kısmen kapsam farkından "
                         "olabilir.")
        if m.siralama:
            # YÖN KELİMESİ OLGUSAL. "Yükselen/gerileyen" demek, küçüğün
            # iyi olduğu ölçülerde (başarı sırası) tersini söylemek
            # olurdu. Yorum modele bırakılır; burada yalnızca işaret var.
            artan = [f"{a} ({d:+g})" for a, _, _, d in
                     m.siralama[:_UC_SAYISI] if d > 0]
            azalan = [f"{a} ({d:+g})" for a, _, _, d in
                      reversed(m.siralama[-_UC_SAYISI:]) if d < 0]
            if artan:
                satir.append("  en çok artan: " + ", ".join(artan))
            if azalan:
                satir.append("  en çok azalan: " + ", ".join(azalan))
        parcalar.append("\n".join(satir))

    if kanit.atlanan:
        parcalar.append("Veri bulunamadığı için analize girmeyen ölçüler: "
                        + "; ".join(f"{ad} ({sebep})"
                                    for ad, sebep in kanit.atlanan))
    return "\n\n".join(parcalar)


def iz(kanit: Kanit) -> str:
    """Tek satırlık geliştirme izi — UI'a gitmez."""
    return (f"resolved_metrics=[{','.join(m.metrik for m in kanit.metrikler)}]"
            f" sources=[{','.join(kanit.kaynaklar())}]"
            f" rows={kanit.satir_sayisi()} queries={kanit.sorgu_sayisi}"
            f" skipped={len(kanit.atlanan)}")
