"""Toplu kapsam — "tüm / hepsi / genel / üniversitelere göre".

ÖLÇÜLEN ARIZA
-------------
"Ankara'daki üniversitelerde bilgisayar mühendisliğinin trendi" sorusu
`ANKARA ÜNİVERSİTESİ` varlığına kilitleniyordu. Cevap tek kuruma daralıyor,
kullanıcı ise şehirdeki bütün kurumları soruyordu.

KÖK NEDEN
---------
Varlık çözümleyici Türkçe eklere BİLEREK toleranslı: "üniversite",
"üniversitesi", "üniversiteler" aynı kavrama düşsün diye. Kavram
eşleştirmesi için bu doğru. Ama KAPSAM için tam tersi geçerli:

    "üniversitesi"  → tekil, bir kurumu işaret eder
    "üniversiteler" → çoğul, kümeyi işaret eder

Tekil/çoğul ayrımı kaybolunca "Ankara'daki üniversiteler" ifadesindeki
iki sözcük, bitişik oldukları için `ANKARA ÜNİVERSİTESİ` adıyla
eşleşiyordu. Yani hata çözümleyicinin puanlamasında değil, ondan ÖNCE
sorulması gereken sorunun hiç sorulmamasındaydı:

    Kullanıcı TEK bir varlık mı istiyor, yoksa bir KÜME mi?

BU MODÜLÜN İŞİ
--------------
O soruyu tek başına cevaplar. Varlık çözümleyiciye, ters indekse,
kaynak seçimine ve puanlamaya DOKUNMAZ; yalnızca çözümün sonucunu
kapsam kararına göre yerli yerine koyar:

    · Çoğul tür = çözülen varlığın türü  → varlık DÜŞÜRÜLÜR
      ("Ankara'daki üniversiteler" → tek üniversiteye kilitlenme)

    · Çoğul tür ≠ çözülen varlığın türü → varlık KAPSAM olur
      ("Gazi Üniversitesi'nin tüm bölümleri" → Gazi kapsam, bölümler
      sorulan)

    · Tür belirsiz ("genel durum")       → varlığa DOKUNULMAZ
      ("Ankara Üniversitesi'nin genel durumu" tek kurum sorusudur)

Üçüncü dal bilinçli olarak muhafazakâr: kapsamın hangi türe ait olduğu
anlaşılmıyorsa doğru olan, çalışan davranışı bozmamaktır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

#: Türkçe büyük/küçük ve aksan katlaması (`veri_ailesi.sadelestir` ile
#: aynı tablo; bu modül tek başına da kullanılabilsin diye kopyalanmadı,
#: içeri alındı).
_KATLA = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def sadelestir(metin: str) -> str:
    return (metin or "").translate(_KATLA).lower()


#: Varlık TÜRÜ kökleri → plan/katalog türü. Bunlar tür sözcükleridir,
#: kurum ADI değil: yeni bir üniversite ya da bölüm eklendiğinde bu
#: liste değişmez.
_TUR_KOK = (
    (r"universite|kurum", "university"),
    (r"fakulte", "faculty"),
    (r"yuksekokul|meslek yuksekokul", "faculty"),
    (r"bolum|anabilim", "department"),
    (r"program|muhendislik|lisans", "program"),
)

#: ÇOĞUL tür sözcüğü: kök + Türkçe çoğul eki (-ler/-lar) + isteğe bağlı
#: hâl eki. "üniversiteler", "üniversitelerin", "bölümlere",
#: "mühendislikleri" hepsi buraya düşer.
_COGUL = tuple(
    (re.compile(r"\b(?:" + kok + r")\w*?(?:ler|lar)\w*", re.I), tur)
    for kok, tur in _TUR_KOK)

#: Evrensel niceleyiciler. Tür söylemezler ama kapsamın tekil OLMADIĞINI
#: söylerler.
_EVRENSEL = re.compile(
    r"\b(tum|tumu|tumunde|hepsi|hepsinin|butun|genel|geneli|genelinde|"
    r"genelde|overall|toplamda|her bir|tamami|tamaminda)\b", re.I)

#: "üniversitelere göre", "bölümlere göre" — kırılım istenmiş demektir.
#: Kırılım her zaman çok varlıklıdır.
_GORE = re.compile(r"\b\w*?(?:ler|lar)\w*\s+gore\b", re.I)

#: "Ankara'daki", "ankaradaki", "Ankara'da" — coğrafi SÜZGEÇ.
#: Tek başına toplu kapsam saymaz; çoğul bir tür sözcüğüyle birlikte
#: anlam kazanır. Coğrafi sözcüğün tek başına bir üniversite seçtirmesi
#: tam da düzeltilen arızaydı.
_COGRAFI = re.compile(r"\b\w+['’]?d[ae]ki\b|\b\w+['’]?d[ae]\b", re.I)


@dataclass(frozen=True)
class Kapsam:
    """Sorunun kapsam kararı."""

    #: Kullanıcı bir KÜME mi istiyor.
    toplu: bool = False
    #: Kümenin türü — biliniyorsa. "genel durum" der ama tür söylemezse
    #: `None` kalır ve varlığa dokunulmaz.
    tur: Optional[str] = None
    #: Hangi sinyalin devreye girdiği — yalnızca iz için.
    isaret: str = ""
    #: Coğrafi bir süzgeç var mı ("Ankara'daki").
    cografi: bool = False

    def ozet(self) -> str:
        return (f"collective={'yes' if self.toplu else 'no'}"
                f" scope_type={self.tur or '-'}"
                f" signal={self.isaret or '-'}"
                f"{' geo' if self.cografi else ''}")


def coz(soru: str) -> Kapsam:
    """Sorunun tek varlık mı, küme mi istediğini söyler.

    Karar SIRALIDIR ve en açık sinyal önce gelir:

      1. Çoğul tür sözcüğü — hem toplu olduğunu hem TÜRÜNÜ söyler.
         En güçlü sinyal budur.
      2. "…lere göre" kırılımı — tür sözcüğünden de türetilmeye
         çalışılır; bulunamazsa tür bilinmez ama kapsam yine topludur.
      3. Evrensel niceleyici — "genel durum" gibi. Tür söylemez.

    Hiçbiri yoksa kapsam tekildir ve mevcut davranış aynen sürer.
    """
    sade = sadelestir(soru)
    cografi = bool(_COGRAFI.search(sade))

    for kalip, tur in _COGUL:
        eslesme = kalip.search(sade)
        if eslesme:
            return Kapsam(toplu=True, tur=tur, isaret=eslesme.group(0),
                          cografi=cografi)

    if _GORE.search(sade):
        return Kapsam(toplu=True, tur=None, isaret="gore", cografi=cografi)

    evrensel = _EVRENSEL.search(sade)
    if evrensel:
        return Kapsam(toplu=True, tur=None, isaret=evrensel.group(1),
                      cografi=cografi)

    return Kapsam(cografi=cografi)


def _tam_ad_gecti(ad: Optional[str], soru: str) -> bool:
    """Varlığın TAM adı soruda geçiyor mu.

    NEDEN GEREKLİ: "Ankara genelinde durum nedir?" sorusunda çözümleyici
    `ANKARA ÜNİVERSİTESİ`ni buluyordu — soruda yalnızca "Ankara" var,
    "üniversite" hiç geçmiyor. Coğrafi bir sözcüğün tek başına bir
    kurum seçtirmesi tam olarak düzeltilmek istenen davranış.

    Kapsam TOPLU olduğunda tekil varlık ancak adının BÜTÜN anlamlı
    parçaları soruda geçiyorsa korunur. Ek toleransı mevcut
    `entity_katalogu.ayni_kavram` ile sağlanır; yeni bir eşleştirme
    mantığı yazılmaz.
    """
    if not ad:
        return False
    try:
        from app.services.assistant import entity_katalogu as ek
        soru_parcalari = ek.tokenlar(soru)
        ad_parcalari = [p for p in ek.tokenlar(ad) if len(p) > 2]
    except Exception:  # noqa: BLE001
        return True          # denetim kurulamadıysa mevcut davranış sürer
    if not ad_parcalari:
        return True
    return all(any(ek.ayni_kavram(t, parca) for t in soru_parcalari)
               for parca in ad_parcalari)


#: Kurumsal hiyerarşi — geniş olan küçük sayı. Varlığın kapsam mı yoksa
#: süzgeç mi olduğu bu sıraya göre belirlenir.
_GENISLIK = {"university": 0, "faculty": 1, "department": 2, "program": 2}


def _daha_genis(varlik_turu: Optional[str], kapsam_turu: str) -> bool:
    a = _GENISLIK.get(varlik_turu or "", 9)
    b = _GENISLIK.get(kapsam_turu, 9)
    return a < b


def uygula(plan, kapsam: Kapsam) -> None:
    """Kapsam kararını plana işler. Plan YERİNDE değiştirilir.

    Varlık çözümleyicinin sonucu SİLİNMEZ, YERİNE KONUR: tür eşleşmesi
    varsa kilitlenme kaldırılır, tür farklıysa varlık kapsam olarak
    korunur. Bilgi kaybı olmaz.
    """
    if not kapsam.toplu:
        return

    # TOPLU KAPSAMDA TEKİL VARLIK, ANCAK TAM ADIYLA ANILMIŞSA YAŞAR.
    # "Ankara genelinde" → "Ankara" bir yer adıdır, kurum adı değil.
    # "Gazi Üniversitesi'nin tüm bölümleri" → tam ad geçiyor, korunur.
    if plan.varlik and not _tam_ad_gecti(plan.varlik, plan.soru):
        plan.varlik = None
        plan.varlik_belirsiz = False

    if kapsam.tur:
        if plan.varlik_turu == kapsam.tur or plan.varlik_turu is None:
            # TEKİL KİLİTLENME KALDIRILIR.
            # "Ankara'daki üniversiteler" sorusunda çözümleyici
            # ANKARA ÜNİVERSİTESİ'ni bitişik iki sözcükten buluyordu;
            # oysa ikinci sözcük ÇOĞUL ve kümeyi işaret ediyor.
            plan.varlik = None
            plan.varlik_belirsiz = False
        elif plan.varlik and _daha_genis(plan.varlik_turu, kapsam.tur):
            # VARLIK DAHA GENİŞ: soruyu çevreleyen kapsamdır.
            # "Gazi Üniversitesi'nin tüm bölümleri" → sorulan bölümler,
            # Gazi ise onları çevreleyen kurum.
            if not plan.kapsam_varligi:
                plan.kapsam_varligi = plan.varlik
                plan.kapsam_turu = plan.varlik_turu
            plan.varlik = None
        # VARLIK DAHA DAR İSE OLDUĞU YERDE KALIR.
        # "Ankara'daki bilgisayar mühendisliğini üniversitelere göre
        # karşılaştır" — kırılım üniversite, ama bilgisayar
        # mühendisliği sorunun SÜZGECİ. Onu kapsama taşımak süzgeci
        # kaybettirir ve cevap bütün programlara yayılırdı. Tekil
        # kilitlenme riski de yoktur: seçilen bir program, kırılım
        # ekseni ise üniversite.
        plan.varlik_turu = kapsam.tur
        if kapsam.tur == "university":
            plan.universite_seviyesi = True
        elif kapsam.tur in ("program", "department"):
            plan.program_seviyesi = True

    # NİYET: tek değer sorusu, küme sorulduğunda karşılaştırmaya döner.
    # Sıralama/eğilim niyetleri zaten çok varlıklıdır; onlara
    # dokunulmaz.
    if plan.niyet in ("single_value", "aggregation") and kapsam.tur:
        plan.niyet = "comparison"
