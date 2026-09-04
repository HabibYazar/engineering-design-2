"""Semantik veri kataloğu ve sorgu planlayıcı.

NEDEN VAR
---------
Merkezî veritabanında 60 kaynak var. Modelden bu adları ezberleyip doğru
olanı seçmesini beklemek çalışmıyordu; ölçülen davranışlar:

  · yanlış tabloyu seçmek
  · aşırı dar bir kaynağa yapışıp tek üniversitenin verisini getirmek
  · yıl aralığı istenen soruda tek tabloda kalmak (eski yıllar başka
    tabloda olduğu hâlde)
  · kullanıcı isim/değer isterken veri kümesi özeti döndürmek

Ortak sebep şuydu: kaynak seçimi ANAHTAR KELİME eşleşmesine dayanıyordu.
"taban puanı" ile `base_score` arasında, "öğretim elemanı" ile
`academic_staff` arasında hiçbir köprü yoktu. Soru Türkçe, şema İngilizce.

Bu modül üç şey yapar ve üçü de GENELDİR — hiçbir soruya, programa ya da
üniversiteye özel dal içermez:

1. KATALOG: her kaynağın profilini veritabanının kendisinden çıkarır
   (aile, yıl kapsamı, seviye, ölçüm sütunları, kökeni). Elle yazılmış
   tablo listesi yoktur; yeni bir tablo eklendiğinde profili kendiliğinden
   oluşur.

2. PLAN: sorudan niyet, metrik ailesi, kapsam ve zaman aralığı çıkarır.
   Kavram sözlüğü kelimeleri DEĞİL kavramları eşler; "puan", "taban
   puanı" ve "admission score" aynı metrik ailesine düşer.

3. ADAY SEÇİMİ: plana göre kaynakları PUANLAR. Zaman aralığı tek kaynağa
   sığmıyorsa birden çok kaynak önerir — retrieval ilk tabloyu bulunca
   durmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.services.assistant import abu_kds_store as store
from app.services.assistant import entity_katalogu

import logging

logger = logging.getLogger(__name__)

#: Türkçe büyük/küçük harf ve aksan farklarını silen katlama.
_KATLA = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def sadelestir(metin: str) -> str:
    return (metin or "").translate(_KATLA).lower()


# ---------------------------------------------------------------------------
# 1) KAVRAM SÖZLÜĞÜ
# ---------------------------------------------------------------------------
# Buradaki her giriş bir KAVRAM ailesidir, bir kelime değil. Amaç
# kullanıcının hangi kelimeyi seçtiğinden bağımsız olarak aynı veriye
# ulaşmak. Liste kısa tutulur: uzun eşanlam listeleri her soruyu her
# aileye eşleştirip ayrımı yok eder.
#
# `sutun` alanı, o kavramın veritabanı sütun adlarında nasıl göründüğünü
# söyler — Türkçe soruyu İngilizce şemaya bağlayan köprü budur.

@dataclass(frozen=True)
class Kavram:
    anahtar: str
    aile: str
    terimler: Tuple[str, ...]          # soruda aranan (sadeleştirilmiş)
    sutun: Tuple[str, ...]             # şemada aranan
    birim: str = ""                    # "kişi", "puan", "%", "USD"
    #: Kullanıcıya gösterilebilir Türkçe ad. Netleştirme sorusunda
    #: kullanılır; `terimler` sadeleştirilmiş (aksansız) olduğu için
    #: doğrudan ekrana yazılamaz.
    etiket: str = ""


KAVRAMLAR: Tuple[Kavram, ...] = (
    Kavram("student_count", "students",
           ("ogrenci", "ogrenci sayisi", "kayitli ogrenci", "student"),
           ("student", "ogrenci", "lisans", "onlisans", "toplam"), "kişi", etiket="öğrenci sayısı"),
    Kavram("foreign_student", "students",
           ("yabanci ogrenci", "uluslararasi ogrenci", "uyruk"),
           ("foreign", "yabanci", "uyruk"), "kişi", etiket="yabancı öğrenci sayısı"),
    Kavram("graduate", "students",
           ("mezun", "mezuniyet", "graduate"),
           ("mezun", "graduate"), "kişi", etiket="mezun sayısı"),

    Kavram("academic_staff", "academic_staff",
           ("akademisyen", "ogretim eleman", "ogretim uye", "akademik kadro",
            "academic staff", "faculty member", "kadro", "profesor",
            "docent", "arastirma gorevli"),
           ("staff", "ogretim", "akademik", "kadro", "profesor", "docent"),
           "kişi", etiket="akademisyen sayısı"),
    Kavram("student_per_staff", "academic_staff",
           ("ogrenci basina", "ogretim uyesi basina", "student per staff"),
           ("per_staff", "basina"), "oran", etiket="öğretim üyesi başına öğrenci"),

    Kavram("base_score", "yks_admissions",
           ("taban puan", "tabanpuan", "yerlesme puan", "giris puan",
            "admission score", "base score", "puan"),
           ("base_score", "taban_puan", "puan", "score"), "puan", etiket="taban puanı"),
    Kavram("success_rank", "yks_admissions",
           ("basari sira", "siralamasi", "success rank"),
           ("rank", "sira"), "sıra", etiket="başarı sırası"),
    Kavram("quota", "yks_admissions",
           ("kontenjan", "quota", "kapasite kontenjan"),
           ("quota", "kontenjan"), "kişi", etiket="kontenjan"),
    Kavram("placed", "yks_admissions",
           ("yerlesen", "yerlesme", "kayit yaptiran", "placed"),
           ("placed", "yerlesen", "yerlesme"), "kişi", etiket="yerleşen sayısı"),
    Kavram("occupancy", "yks_admissions",
           ("doluluk", "doluluk oran", "occupancy"),
           ("occupancy", "doluluk"), "%", etiket="doluluk oranı"),
    Kavram("preference", "yks_admissions",
           ("tercih", "preference"), ("tercih",), "adet", etiket="tercih sayısı"),

    Kavram("tuition", "tuition_finance",
           ("ucret", "fiyat", "tuition", "harc", "burs"),
           ("fee", "ucret", "burs", "tuition"), "USD", etiket="ücret"),
    Kavram("revenue", "tuition_finance",
           ("gelir", "revenue", "ciro"), ("revenue", "gelir"), "USD", etiket="gelir"),

    # TÜRKÇE ÜNSÜZ YUMUŞAMASI YÜZÜNDEN KÖKLER KISA TUTULUR.
    # "derslik" yazarsak "dersliğimiz" EŞLEŞMEZ: ek alınca k→ğ döner ve
    # sadeleştirme onu "dersligimiz" yapar. Ölçüldü: "Kaç dersliğimiz
    # var?" sorusu bu yüzden altyapı ailesini hiç bulamıyor, "ders"
    # kelimesi üzerinden müfredata düşüyordu.
    Kavram("classroom", "infrastructure",
           ("dersli", "sinif", "amfi", "laboratuv", "mekan", "altyapi",
            "classroom"),
           ("room", "classroom", "derslik", "floor", "space"), "adet", etiket="derslik sayısı"),
    Kavram("room_capacity", "infrastructure",
           ("kapasite", "oturma kapasite", "kisilik", "capacity"),
           ("capacity", "kapasite"), "kişi", etiket="derslik kapasitesi"),
    Kavram("room_schedule", "infrastructure",
           ("ders program", "haftalik program", "kullanim oran",
            "doluluk oran"),
           ("schedule", "booking", "utilization", "time_slot"), "", etiket="derslik kullanım oranı"),

    # "ders" TEK BAŞINA ALINMAZ: "derslik", "ders programı" ve "ders
    # yükü" hep onu içerir. Ayırt edici terimler kullanılır.
    Kavram("course", "curriculum",
           ("mufredat", "course", "kredi", "akts", "ders sayisi",
            "ders listesi", "ders katalog"),
           ("course", "ders", "credit"), "adet", etiket="ders sayısı"),

    Kavram("strategic_goal", "strategic",
           ("stratejik", "hedef", "kpi", "gosterge", "amac"),
           ("goal", "hedef", "kpi", "target"), "", etiket="stratejik hedef"),

    Kavram("program_match", "department_matching",
           ("ayni bolum", "benzer bolum", "muadil", "esdeger",
            "karsilastirilabilir"),
           ("matching", "similar", "same"), "", etiket="benzer program eşleşmesi"),

    Kavram("university_profile", "university_benchmark",
           ("universite kunye", "rektor", "adres", "iletisim", "profil"),
           ("website", "rektor", "adres", "telefon"), "", etiket="üniversite künyesi"),
)

#: Aile adları — kaynak profillerinde ve trace'te kullanılır.
AILELER: Tuple[str, ...] = tuple(dict.fromkeys(k.aile for k in KAVRAMLAR))

#: `_tables.category` değeri → bu modüldeki aile adı. Veritabanının kendi
#: sınıflandırması korunur, yalnızca adlandırma hizalanır.
_KATEGORI_AILE = {
    "students": "students",
    "academic_staff": "academic_staff",
    "yks": "yks_admissions",
    "finance": "tuition_finance",
    "infrastructure": "infrastructure",
    "curriculum": "curriculum",
    "strategic": "strategic",
    "department_matching": "department_matching",
    "merge_reports": "merge_reports",
    "docs": "docs",
}


# ---------------------------------------------------------------------------
# 2) KAYNAK PROFİLİ — veritabanından otomatik
# ---------------------------------------------------------------------------
_YIL_SUTUN = re.compile(r"^(academic_year|year|yil)$", re.I)
_YIL_DEGER = re.compile(r"(20\d\d)")


def _yil_araligi(kaynak: str, sutunlar: Sequence[str]) -> Optional[Tuple[int, int]]:
    """Kaynağın gerçekten kapsadığı yıllar — şemadan değil, VERİDEN.

    Tablo adındaki "2020_2026" gibi ipuçlarına güvenilmez; ad yanlış ya
    da eksik olabilir. Yıl sütunu iki biçimde geliyor: `2021` (tam sayı)
    ve `2020-2021` (metin). İkisi de aynı ölçeğe indirilir, yoksa iki
    kaynağın yıl kapsamı karşılaştırılamazdı.
    """
    yil_sut = next((s for s in sutunlar if _YIL_SUTUN.match(s)), None)
    if not yil_sut:
        return None
    try:
        return store.yil_araligi(kaynak, yil_sut)
    except Exception:  # noqa: BLE001
        return None


@dataclass
class KaynakProfili:
    kaynak: str
    aile: str
    sutunlar: List[str]
    yil_araligi: Optional[Tuple[int, int]]
    yil_sutunu: Optional[str]
    universite_seviyesi: bool
    program_seviyesi: bool
    kavramlar: Set[str]                 # bu kaynakta bulunan metrik anahtarları
    satir_sayisi: Optional[int]
    koken: Optional[str]

    def yil_kapsar(self, yil: int) -> bool:
        if not self.yil_araligi:
            return False
        return self.yil_araligi[0] <= yil <= self.yil_araligi[1]


_UNI = re.compile(r"(universit|university|kurum|institution)", re.I)
_PROG = re.compile(r"(program|bolum|department|fakulte|faculty)", re.I)


@lru_cache(maxsize=1)
def profiller() -> Dict[str, KaynakProfili]:
    """Bütün kaynakların profili. Süreçte bir kez hesaplanır."""
    cikti: Dict[str, KaynakProfili] = {}
    for kaynak, sutunlar in store.kaynaklar().items():
        kategori = store.kategori(kaynak) or ""
        aile = _KATEGORI_AILE.get(kategori, kategori or "diger")
        sade_sut = [sadelestir(s) for s in sutunlar]

        bulunan: Set[str] = set()
        for kav in KAVRAMLAR:
            if kav.aile != aile:
                continue
            if any(any(ip in s for ip in kav.sutun) for s in sade_sut):
                bulunan.add(kav.anahtar)

        yil_sut = next((s for s in sutunlar if _YIL_SUTUN.match(s)), None)
        cikti[kaynak] = KaynakProfili(
            kaynak=kaynak, aile=aile, sutunlar=list(sutunlar),
            yil_araligi=_yil_araligi(kaynak, sutunlar), yil_sutunu=yil_sut,
            universite_seviyesi=any(_UNI.search(s) for s in sutunlar),
            program_seviyesi=any(_PROG.search(s) for s in sutunlar),
            kavramlar=bulunan,
            satir_sayisi=store.satir_sayisi(kaynak),
            koken=store.kaynak_notu(kaynak))
    return cikti


# ---------------------------------------------------------------------------
# 3) SORGU PLANI
# ---------------------------------------------------------------------------
_NIYET = (
    # Sıra önemli: en ayırt edici kalıp önce denenir.
    # "Hangi bölümler geriledi?" bir SIRALAMA sorusudur: birden çok
    # varlığı bir ölçüye göre kıyaslar. Önceki kalıp yalnızca "en" ya
    # da "daha" içeren biçimleri yakalıyordu; yön bildiren fiiller
    # (yükseldi/geriledi/arttı) kaçıyor ve soru "tekil değer" sayılıyordu.
    ("ranking", re.compile(
        r"(en (dusuk|yuksek|az|cok|buyuk|kucuk)|sirala|siralama|ilk \d+|"
        r"top \d+|hangi.*(en|daha)|"
        r"hangi.*(yukseldi|geriledi|artti|azaldi|dustu|one cikti|"
        r"iyilesti|kotulesti))", re.I)),
    ("trend", re.compile(
        r"(trend|egilim|yillar (icinde|gore)|degisim|seyir|son \d+ yil|"
        r"gelisim|artis|azalis)", re.I)),
    ("comparison", re.compile(
        r"(karsilastir|kiyasla|fark|versus|\bvs\b|ile .*arasinda|"
        r"gore nasil)", re.I)),
    ("aggregation", re.compile(
        r"(toplam|ortalama|kac tane|kac adet|sayisi kac|ne kadar)", re.I)),
    ("list", re.compile(r"(listele|hangileri|neler|liste)", re.I)),
)

#: "son 5 yıl" kadar "son beş yıl" da yazılır. Yazıyla sayılar
#: olmadan bu sorular yıl aralığı ÜRETMİYORDU — soru beş yıllık, plan
#: yılsız kalıyordu.
_SAYI_KELIME = {
    "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6,
    "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10,
}
_YIL_ARALIK = re.compile(
    r"son\s+(\d+|" + "|".join(_SAYI_KELIME) + r")\s*yil", re.I)
_ACIK_YIL = re.compile(r"\b(20\d\d)\b")

#: Kapsam sinyalleri — hangi seviyede cevap bekleniyor.
_KAPSAM_PROGRAM = re.compile(
    r"(program|bolum|muhendislik|fakulte|lisans)", re.I)
_KAPSAM_UNIVERSITE = re.compile(
    r"(universite|kurum|rakip|benchmark|ankara|sehir)", re.I)


@dataclass
class SorguPlani:
    soru: str
    niyet: str = "single_value"
    aileler: List[str] = field(default_factory=list)
    kavramlar: List[str] = field(default_factory=list)
    yillar: List[int] = field(default_factory=list)
    program_seviyesi: bool = False
    universite_seviyesi: bool = False
    artan: bool = True

    # --- VARLIK ÇÖZÜMLEMESİ (entity_katalogu) ---------------------------
    #: Sorunun işaret ettiği TEKİL varlık (canonical ad). Belirsizse
    #: `None` kalır — yanlış varlık seçmektense seçmemek doğrudur.
    varlik: Optional[str] = None
    varlik_turu: Optional[str] = None
    #: Sorunun geçtiği daha geniş kapsam: "Mühendislik fakültesindeki
    #: bölümler" → kapsam faculty, sorulan department.
    kapsam_varligi: Optional[str] = None
    kapsam_turu: Optional[str] = None
    #: Tekil varlık değil, aile: "mühendislikler", "vakıf üniversiteleri".
    varlik_grubu: Optional[str] = None
    #: İki aday çok yakınsa işaretlenir; kaynak seçimi buna göre daha
    #: geniş davranır ve cevap kapsamı açıkça söylenir.
    varlik_belirsiz: bool = False

    @property
    def metrik_bilinmiyor(self) -> bool:
        """Soru bir ölçü İSTİYOR ama hangisi olduğunu söylemiyor mu.

        "Son iki yılda hangi mühendislikler yükseldi?" — yükselen NE?
        Taban puan mı, doluluk mu, kontenjan mı? Bunu tahmin etmek
        sessizce yanlış bir cevap üretir. Karşılaştırma/sıralama/eğilim
        niyeti varken metrik yoksa açıkça BİLİNMİYOR denir.
        """
        return (not self.kavramlar
                and self.niyet in ("ranking", "trend", "comparison"))

    def ozet(self) -> str:
        """Trace satırı — tek satırda okunabilir."""
        y = (f"{min(self.yillar)}-{max(self.yillar)}" if self.yillar else "-")
        m = ",".join(self.kavramlar) or ("UNKNOWN" if self.metrik_bilinmiyor
                                         else "-")
        e = (self.varlik or ("?" if self.varlik_belirsiz else "-"))
        return (f"intent={self.niyet} metric={m}"
                f" entity={e} group={self.varlik_grubu or '-'}"
                f" scope={self.kapsam_varligi or '-'}"
                f" level={'program' if self.program_seviyesi else ''}"
                f"{'+uni' if self.universite_seviyesi else ''}")


def plan_cikar(soru: str, *, bugun_yil: int = 2026) -> SorguPlani:
    """Sorudan yapılandırılmış plan üretir. Hiçbir soruya özel dal yok."""
    sade = sadelestir(soru)
    plan = SorguPlani(soru=soru)

    for ad, kalip in _NIYET:
        if kalip.search(sade):
            plan.niyet = ad
            break

    # "en düşük" artan, "en yüksek" azalan sıralama ister.
    if re.search(r"en (yuksek|cok|buyuk|fazla)", sade):
        plan.artan = False

    # KAVRAM EŞLEME — kelime değil kavram. Bir soruda birden çok metrik
    # geçebilir ("öğrenci ve akademisyen"); hepsi toplanır.
    # KAVRAM EŞLEŞMESİ DE EK-TOLERANSLI.
    # ------------------------------------------------------------------
    # ÖLÇÜLEN ARIZA: "doluluğu" sorusunda `occupancy` kavramı hiç
    # yakalanmıyordu — terim "doluluk", metinde "dolulugu" geçiyor ve
    # düz alt-dize araması bunu görmüyor. Metrik boş kalınca soru
    # metriksiz sayılıyor, kaynak seçimi kör kalıyordu.
    #
    # Artık iki yol denenir: (1) düz alt-dize (çok kelimeli terimler
    # için gerekli: "taban puan"), (2) tek kelimelik terimlerde
    # ek-toleranslı token karşılaştırması.
    _soru_tokenlari = entity_katalogu.tokenlar(soru)

    # "AKADEMİK YIL" BİR ZAMAN İFADESİDİR, KADRO METRİĞİ DEĞİL.
    # Ölçüldü: "2025-2026 akademik yılında öğrenci sayısı" sorusu
    # `academic_staff` metriğini de yakalıyordu; alt-dize eşleşmesi tek
    # başına karar veremez. Terimden hemen sonra "yıl" geliyorsa o
    # kelime zamanı niteler.
    _ZAMAN_NITELEYEN = re.compile(r"\b(akademik|egitim|ogretim)\s+yil", re.I)
    _zaman_baglami = bool(_ZAMAN_NITELEYEN.search(sade))

    # Zaman bağlamında "akademik"/"öğretim" kelimeleri YILI niteler;
    # kadro metriğine köprü kurmamalılar. Engel TERİM üzerinde değil
    # SORU TOKEN'I üzerinde olmalı: kavramın terimi "akademisyen"dir,
    # soruda geçen kelime "akademik"tir ve ek toleransı ikisini
    # eşleştirir. Ölçüldü: engel terim tarafına konunca hiç çalışmadı.
    _ZAMAN_TOKENI = {"akademik", "ogretim", "egitim"}

    def _kavram_gecti(terim: str) -> bool:
        if terim in sade:
            return True
        if " " in terim:
            return False        # çok kelimeli terim alt-dize ister
        for t in _soru_tokenlari:
            if _zaman_baglami and t in _ZAMAN_TOKENI:
                continue
            if entity_katalogu.ayni_kavram(t, terim, kisa_kavram=True):
                return True
        return False

    for kav in KAVRAMLAR:
        if any(_kavram_gecti(t) for t in kav.terimler):
            if kav.anahtar not in plan.kavramlar:
                plan.kavramlar.append(kav.anahtar)
            if kav.aile not in plan.aileler:
                plan.aileler.append(kav.aile)

    # ZAMAN — "son 5 yıl" ve açık yıllar birlikte çalışır.
    acik = sorted({int(y) for y in _ACIK_YIL.findall(soru)})
    m = _YIL_ARALIK.search(sade)
    if m:
        ham = m.group(1)
        n = int(ham) if ham.isdigit() else _SAYI_KELIME.get(ham, 5)
        n = max(1, min(n, 15))
        son = max(acik) if acik else bugun_yil - 1
        plan.yillar = list(range(son - n + 1, son + 1))
    elif acik:
        plan.yillar = (list(range(min(acik), max(acik) + 1))
                       if len(acik) > 1 else acik)
    elif plan.niyet == "trend":
        # Eğilim en az iki dönem ister; aralık verilmemişse son beş yıl.
        plan.yillar = list(range(bugun_yil - 5, bugun_yil))

    plan.program_seviyesi = bool(_KAPSAM_PROGRAM.search(sade))
    plan.universite_seviyesi = bool(_KAPSAM_UNIVERSITE.search(sade))

    # VARLIK ÇÖZÜMLEMESİ — ek-toleranslı, ama karıştırmayan.
    # ------------------------------------------------------------------
    # Katalog süreçte bir kez kurulur ve ters indeksle taranır; bu blok
    # milisaniyeler mertebesindedir. Çözümleme BAŞARISIZ olursa plan
    # eskisi gibi çalışmaya devam eder — varlık alanları boş kalır,
    # kaynak seçimi metrik ve yıl üzerinden yürür.
    try:
        parcalar = entity_katalogu.tokenlar(soru)
        cozum = entity_katalogu.coz(
            soru, beklenen_tur=entity_katalogu.tur_ipucu(parcalar))
        plan.varlik_grubu = cozum.grup
        plan.varlik_belirsiz = cozum.belirsiz
        if cozum.varlik is not None:
            plan.varlik = cozum.varlik.ad
            plan.varlik_turu = cozum.varlik.tur
        plan.varlik_turu = plan.varlik_turu or entity_katalogu.tur_ipucu(
            parcalar)
        kapsam = entity_katalogu.kapsam_ipucu(parcalar)
        # Kapsam ancak SORULAN türden farklıysa anlamlıdır: "fakültedeki
        # bölümler" ikisini birden taşır, "fakülteler" yalnızca birini.
        if kapsam and kapsam != plan.varlik_turu:
            plan.kapsam_turu = kapsam
            if cozum.varlik is not None and cozum.varlik.tur == kapsam:
                plan.kapsam_varligi = cozum.varlik.ad
                plan.varlik = None      # sorulan o değil, kapsam o
        # Seviye bayrakları varlık türünden de beslenir.
        if plan.varlik_turu in ("program", "department"):
            plan.program_seviyesi = True
        if plan.varlik_turu == "university" or plan.kapsam_turu == "university":
            plan.universite_seviyesi = True
    except Exception:  # noqa: BLE001
        logger.debug("varlık çözümlemesi atlandı", exc_info=True)
    return plan


# ---------------------------------------------------------------------------
# 4) ADAY KAYNAK SEÇİMİ
# ---------------------------------------------------------------------------
def _puan(p: KaynakProfili, plan: SorguPlani) -> float:
    """Kaynağın plana uygunluğu. Yüksek olan önce denenir."""
    puan = 0.0
    if plan.aileler:
        if p.aile in plan.aileler:
            puan += 10.0
            # Aile içinde aranan metriği GERÇEKTEN taşıyan kaynak öne.
            ortak = p.kavramlar & set(plan.kavramlar)
            puan += 6.0 * len(ortak)
            # DAR KAPSAMLI ÖZEL TABLO GENEL SORUYA CEVAP VERMEZ.
            # Kaynak, planda İSTENMEYEN bir kavrama özelleşmişse geriye
            # alınır. Ölçüldü: "toplam öğrenci sayımız" sorusunda
            # `foreign_students` (yalnızca yabancı uyruklular) listenin
            # başına geliyordu — sayı doğru okunur, cevap yanlış olurdu.
            fazla = p.kavramlar - set(plan.kavramlar)
            puan -= 2.0 * len(fazla)
        else:
            return 0.0                      # yanlış aile hiç denenmez

    # Seviye uyumu: program sorusuna üniversite toplamı dönmemeli.
    if plan.program_seviyesi and p.program_seviyesi:
        puan += 3.0
    if plan.universite_seviyesi and p.universite_seviyesi:
        puan += 3.0
    if plan.program_seviyesi and not p.program_seviyesi:
        puan -= 4.0

    # Zaman kapsaması: istenen yılların kaçını gerçekten içeriyor.
    if plan.yillar:
        kapsanan = sum(1 for y in plan.yillar if p.yil_kapsar(y))
        puan += 4.0 * (kapsanan / len(plan.yillar))
        if kapsanan == 0:
            puan -= 6.0

    # Sıralama/karşılaştırma çok satır ister; tek satırlık özet tablolar
    # bu niyetlerde işe yaramaz.
    if plan.niyet in ("ranking", "comparison", "trend", "list"):
        # `None` = satır sayısı BİLİNMİYOR (türetilmiş görünümler için
        # katalogda kayıt yok), sıfır değil. `or 0` yazmak bu kaynakları
        # "tek satırlık özet tablo" sayıp cezalandırıyordu: ölçüldü, beş
        # yıllık taban puan görünümü tam da beş yıllık soruda üç yıllık
        # tablonun arkasına düşüyordu.
        if p.satir_sayisi is not None and p.satir_sayisi < 5:
            puan -= 3.0

    # Zaman aralığını TEK BAŞINA karşılayan kaynak öne alınır: birden
    # çok tabloyu birleştirmek her zaman mümkün ama daha kırılgandır.
    if plan.yillar and p.yil_araligi:
        if all(p.yil_kapsar(y) for y in plan.yillar):
            puan += 2.0
    return puan


def aday_kaynaklar(plan: SorguPlani, *, en_fazla: int = 4
                   ) -> List[Tuple[str, float]]:
    # METRİK BİLİNMİYORSA KAYNAK SEÇİLMEZ.
    # ------------------------------------------------------------------
    # "Son iki yılda hangi mühendislikler yükseldi?" — yükselen NE?
    # Taban puan mı, doluluk mu, kontenjan mı? Rastgele bir kaynak
    # seçmek, modele rastgele bir metrik vermek demektir; cevap
    # grounded görünür ama yanlış ölçüyü anlatır. Kaynak listesi boş
    # döner, model de neyin sorulduğunu netleştirir.
    if plan.metrik_bilinmiyor:
        return []
    """Plana en uygun kaynaklar, puanıyla birlikte.

    ÇOK KAYNAKLI: istenen yıl aralığı tek kaynağa sığmıyorsa, kalan
    yılları kapsayan kaynaklar da listeye eklenir. Retrieval ilk tabloyu
    bulunca durmaz — 2021-2025 sorusunda 2023-2025 tablosuyla yetinmek
    sessizce yanlış bir "son beş yıl" cevabı üretirdi.
    """
    sirali = sorted(
        ((ad, _puan(p, plan)) for ad, p in profiller().items()),
        key=lambda x: (-x[1], x[0]))
    secilen = [(ad, s) for ad, s in sirali if s > 0][:en_fazla]
    if not plan.yillar or not secilen:
        return secilen

    prof = profiller()
    kapsanan = {y for ad, _ in secilen for y in plan.yillar
                if prof[ad].yil_kapsar(y)}
    eksik = [y for y in plan.yillar if y not in kapsanan]
    if not eksik:
        return secilen

    secili_ad = {ad for ad, _ in secilen}
    for ad, s in sirali:
        if s <= 0 or ad in secili_ad:
            continue
        p = prof[ad]
        if any(p.yil_kapsar(y) for y in eksik):
            secilen.append((ad, s))
            secili_ad.add(ad)
            eksik = [y for y in eksik if not p.yil_kapsar(y)]
            if not eksik:
                break
    return secilen


# ---------------------------------------------------------------------------
# 5) SONUÇ KALİTE DENETİMİ
# ---------------------------------------------------------------------------
#: Netleştirme sorusunda kaç seçenek sunulacağı. Dört, bir cümlede
#: okunabilir olanın üst sınırı; daha fazlası soruyu listeye çevirir.
_EN_FAZLA_SECENEK = 4


def onerilen_metrikler(plan: SorguPlani) -> List[str]:
    """Belirsiz bir soruda kullanıcıya sorulacak ölçü seçenekleri.

    Seçenekler KODA YAZILMAZ; `KAVRAMLAR` kataloğundan, sorunun
    seviyesine göre süzülür. Yeni bir metrik kavramı eklendiğinde
    netleştirme sorusu da kendiliğinden onu içerir.
    """
    # Sorunun seviyesi hangi ailelerin anlamlı olduğunu belirler:
    # program/bölüm sorusunda yerleştirme ölçüleri öne çıkar, kurum
    # sorusunda öğrenci/kadro sayıları.
    if plan.program_seviyesi:
        sira = ("yks_admissions", "students", "academic_staff",
                "tuition_finance")
    elif plan.universite_seviyesi:
        sira = ("students", "academic_staff", "yks_admissions",
                "tuition_finance")
    else:
        sira = ("students", "yks_admissions", "academic_staff",
                "infrastructure")

    # ÇEŞİTLİLİK: aileler arasında SIRAYLA dolaşılır.
    # Tek aileyi baştan sona taramak "taban puanı, başarı sırası,
    # kontenjan, yerleşen sayısı" gibi birbirine yakın dört seçenek
    # üretiyordu; kullanıcıya asıl lazım olan farklı BOYUTLARI görmek.
    # Aile içinde de birimi farklı olan kavram öne alınır (puan / % /
    # kişi), çünkü ayrım yaratan şey birimdir.
    havuz: Dict[str, List[Kavram]] = {}
    for kav in KAVRAMLAR:
        if kav.etiket:
            havuz.setdefault(kav.aile, []).append(kav)

    secenekler: List[str] = []
    kullanilan_birim: Set[str] = set()
    for tur in range(3):                 # en fazla üç tur yeterli
        for aile in sira:
            for kav in havuz.get(aile, []):
                if kav.etiket in secenekler:
                    continue
                # İlk turda her aileden bir kavram; sonraki turlarda
                # yalnızca YENİ bir birim getiriyorsa eklenir.
                if tur > 0 and kav.birim in kullanilan_birim:
                    continue
                secenekler.append(kav.etiket)
                kullanilan_birim.add(kav.birim)
                break
            if len(secenekler) >= _EN_FAZLA_SECENEK:
                return secenekler
    return secenekler


def dogrula(plan: SorguPlani, satirlar: Sequence[Dict[str, Any]]
            ) -> List[str]:
    """Modele göndermeden önce sonucu plana karşı denetler.

    Uyarılar sonucu ENGELLEMEZ; modele not olarak taşınır. Amaç sessiz
    yanlışı görünür kılmak: "üniversiteler" sorulup tek kurum dönmesi ya
    da beş yıl istenip iki yıl gelmesi, cevabın kendisi doğru görünse
    bile yanlış bir tabloya bakıldığının işaretidir.
    """
    uyari: List[str] = []
    if not satirlar:
        return ["Sonuç boş. Boş sonuç SIFIR DEĞİLDİR; başka kaynak denenmeli."]

    anahtarlar = set(satirlar[0].keys())
    sade_anahtar = {sadelestir(a) for a in anahtarlar}

    # 1) Çok varlık beklenirken tek varlık geldi mi?
    if plan.niyet in ("ranking", "comparison") or plan.universite_seviyesi:
        uni_alan = next((a for a in anahtarlar
                         if _UNI.search(a)), None)
        if uni_alan:
            farkli = {str(r.get(uni_alan)) for r in satirlar}
            if len(farkli) == 1 and len(satirlar) > 1:
                uyari.append(
                    f"Sonuçta tek kurum var ({next(iter(farkli))}). Soru "
                    "birden çok kurumu kapsıyorsa süzgeç fazla dar.")

    # 2) İstenen yılların kaçı geldi?
    if plan.yillar:
        yil_alan = next((a for a in anahtarlar if _YIL_SUTUN.match(a)), None)
        if yil_alan:
            gelen: Set[int] = set()
            for r in satirlar:
                gelen.update(int(x) for x in
                             _YIL_DEGER.findall(str(r.get(yil_alan) or "")))
            eksik = sorted(set(plan.yillar) - gelen)
            # SATIR SINIRI İLE KAYNAK EKSİKLİĞİNİ KARIŞTIRMA.
            # Sıralama sorularında ilk N satır tek yıla yığılabilir;
            # bu, kaynağın o yılları kapsamadığı anlamına GELMEZ.
            # Ölçüldü: "en düşük 5 taban puan" sorgusunda beşi de 2021
            # olunca "2022-2025 yok" uyarısı çıkıyordu — yanlış ve
            # modeli gereksiz bir arayışa itiyordu.
            siralama_kirpmasi = (plan.niyet in ("ranking", "list")
                                 and len(satirlar) <= 25)
            if eksik and len(eksik) < len(plan.yillar):
                if siralama_kirpmasi:
                    uyari.append(
                        "Bu liste sıralamanın ilk satırlarıdır; tek yıla "
                        "yığılmış olabilir. Yıl kapsamını cevapta belirtin.")
                else:
                    uyari.append(
                        f"İstenen yıllardan {', '.join(map(str, eksik))} bu "
                        "sonuçta yok; kapsamı belirtin ya da ek kaynak "
                        "ekleyin.")

    # 3) Sorulan metrik gerçekten sonuçta var mı?
    for anahtar in plan.kavramlar:
        kav = next((k for k in KAVRAMLAR if k.anahtar == anahtar), None)
        if not kav:
            continue
        if not any(any(ip in a for ip in kav.sutun) for a in sade_anahtar):
            uyari.append(
                f"'{anahtar}' metriği sonuç sütunlarında görünmüyor.")

    # 4) Program sorusuna üniversite toplamı dönmüş mü?
    if plan.program_seviyesi:
        if not any(_PROG.search(a) for a in anahtarlar):
            uyari.append(
                "Soru program/bölüm düzeyinde ama sonuçta program sütunu "
                "yok; kurum toplamı program cevabı yerine geçmez.")
    return uyari
