"""`team_changes/newdata` veri setini canonical veritabanına ALAN DÜZEYİNDE birleştirir.

TESLİM PAKETİNDE ÇALIŞTIRILMASI GEREKMEZ.
-----------------------------------------
Teslim edilen `university_management.db` bu birleştirme UYGULANMIŞ
hâldedir (2020-2026 YKS, akademik kadro, öğrenci, finans, stratejik).
Betik geliştirme deposundaki `team_changes/newdata` klasör düzenini
bekler; teslim paketindeki `data_sources/` arşivi domainlere göre
yeniden düzenlendiği için bu betik orada doğrudan çalışmaz. Kaynak
dosyalar denetim ve tekrar üretilebilirlik amacıyla `data_sources/`
altında saklanır; betik ise geçmişin kaydı olarak burada durur.

NE YAPAR
--------
Bu bir "dosyaları içe aktar" betiği DEĞİLDİR. Klasörü özyinelemeli
tarar, her Excel sayfasının GERÇEK İÇERİĞİNE bakar, kolonları canonical
tablolara eşler ve mevcut kayıtlarla alan alan birleştirir.

BİRLEŞTİRME KURALI (tek cümle)
------------------------------
Arkadaş kaynağının DOLU değeri kazanır; BOŞ değeri mevcut dolu değeri
asla silmez; arkadaşta olup bizde olmayan kayıt/alan eklenir.

"Boş" ne demek: None, NaN, boş metin, yalnız boşluk. `0`, `0.0` ve
`False` GERÇEK DEĞERDİR ve boş sayılmaz — bir programın kontenjanının
sıfır olması ölçülmemiş olması demek değildir.

EŞLEŞTİRME NEDEN GÜVENLİ
------------------------
Program düzeyinde eşleştirme YÖK program koduyla yapılır
(`source_program_code`). Ölçüldü: mevcut tabloda kod + akademik yıl +
metrik üçlüsü 36.563 satırın tamamında benzersiz. Yani "Bilgisayar
Mühendisliği (Burslu)" ile "(İngilizce, Burslu)" varyantlarını
karıştırma riski yoktur; ad benzerliğine hiç bakılmaz.

Kurum düzeyinde eşleştirme için ad normalize edilir (Türkçe harfler,
noktalama, fazla boşluk) ama BULANIK EŞLEŞTİRME YAPILMAZ: normalize
edilmiş adlar birebir tutmuyorsa kayıt eşleştirilmez, incelemeye
bırakılır.

KAYNAK DOSYALARIN KENDİ UYARILARINA UYULUR
------------------------------------------
Arkadaşın `Metadata` sayfaları veri tuzaklarını açıkça yazmış ve bu
betik onlara uyar:

  * 2021/2022 dosyalarında puan/sıra alanlarındaki sıfırlar kaynakta
    zaten boşa çevrilmiş; kontenjan/cinsiyet/tercih alanlarında sıfır
    gerçek değerdir.
  * 2026 `placed_students` alanı YÖK Atlas `gkY` (genel kontenjan
    yerleşmesi) alanıdır; projedeki ABÜ dosyasındaki "yerleşen" okul
    birincisi/şehit/depremzede kontenjanlarını da içerir. İKİSİ AYNI
    TANIM DEĞİLDİR, bu yüzden ABÜ yerleşen sayıları bu betikle
    EZİLMEZ (bkz. `_ABU_YERLESEN_KORU`).
  * Akademik kadro sayıları üç farklı tanımda ölçülmüştür (YÖK
    istatistik kişi bazında, YÖK Atlas program bağlantısı bazında,
    projenin kendi personel kaydı). Farklı tanımlı sayılar birbirinin
    üstüne YAZILMAZ; ayrı kulvarda tutulur.

KULLANIM
--------
    python merge_newdata.py              # kuru çalıştırma, yazmaz
    python merge_newdata.py --apply      # yedek alır ve uygular

Betik idempotenttir: ikinci çalıştırma yeni kayıt üretmez.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

# PROJENİN KENDİ EŞDEĞERLİK KURALLARI KULLANILIR.
# Kendi normalizasyonumu yazsaydım aynı program iki farklı anahtar
# alabilir ve mevcut kayıtlarla eşleşmeyip DUPLICATE üretirdi.
from app.services.program_equivalence import (  # noqa: E402
    canonical_faculty_key,
    canonical_program_key,
)
DB = KOK / "university_management.db"
def _newdata_bul() -> Path:
    """`team_changes/newdata` klasörünü yukarı doğru arar.

    Betik hem `newversion/integration/backend` (canonical) hem
    `integration/backend` (çalışan kopya) altından çalıştırılıyor ve
    ikisinin proje köküne uzaklığı FARKLI. Sabit `parents[2]` yazmak
    çalışan kopyada klasörü bulamıyordu.
    """
    for ata in [KOK, *KOK.parents]:
        aday = ata / "team_changes" / "newdata"
        if aday.is_dir():
            return aday
    return KOK / "team_changes" / "newdata"


NEWDATA = _newdata_bul()
CIKTI = NEWDATA / "_merge_output"

#: Program düzeyi veriler mevcut YÖK Atlas kulvarına yazılır. Ayrı kulvar
#: açmak "birleştirme" değil KOPYA üretmek olurdu: aynı program/yıl iki
#: kez sayılır, grafiklerde çift çizgi çıkardı.
KULVAR_PROGRAM = "YÖK Atlas dataset 2025"

#: Kurum düzeyi metrikler (kadro, öğrenci) program düzeyi kulvara
#: KARIŞTIRILMAZ; `program_name` boş satırlar program karşılaştırma
#: sorgularını bozardı.
KULVAR_KURUM = "Ekip newdata 2026 (kurum düzeyi)"

#: YALNIZCA BOŞLUK DOLDURAN KAYNAKLAR.
#:
#: Bu dosyalardan gelen değer, canonical tarafta AYNI ALAN BOŞSA yazılır;
#: dolu bir değeri EZMEZ. Kullanıcının bu kaynak için verdiği kural
#: birebir buydu: "sadece eksik 2025 verilerini koy".
#:
#: Genel kural (arkadaşın dolu değeri kazanır) diğer dosyalarda aynen
#: sürer; burada dosya bazında daraltılıyor.
YALNIZ_EKSIGI_DOLDUR: Tuple[str, ...] = (
    "ankara_yks_2025_kontenjan_doluluk.xlsx",
)

#: 2025 `placed` KAYNAK TANIMI.
#: Kaynak dosyanın kendi Metadata sayfası şunu yazıyor: 2025 yerleşen
#: sayısı ÖSYM Ek Yerleştirme Kılavuzu'ndaki boş kontenjandan
#: türetilmiştir (kontenjan − ek yerleştirme boş kontenjanı), yani EK
#: YERLEŞTİRME ÖNCESİDİR. Projedeki 2021-2024 değerleri ek yerleştirme
#: DAHİL nihai yerleşeni kullanır; ölçülen fark yıllara göre ~4-4,5 puan.
#:
#: Değer canonical olarak kullanılır (kullanıcı kararı) ama bu tanım
#: `methodology` alanında kayıt altına alınır: asistan "2024'ten 2025'e
#: doluluk neden düştü?" sorusunda yalnız sayıya bakıp nedensellik
#: kurmasın diye.
_TANIM_2025 = (
    "2025 yerleşen değeri ek yerleştirme ÖNCESİ tanımına dayanır "
    "(kontenjan − ÖSYM ek yerleştirme boş kontenjanı). 2021-2024 "
    "değerleri ek yerleştirme DAHİL nihai yerleşendir; ölçülen fark "
    "yıllara göre yaklaşık 4-4,5 puandır. Kontenjan alanı her yıl için "
    "aynı tanımdadır."
)

#: ABÜ yerleşen sayısı bu betikle güncellenmez — tanım farkı vardır
#: (bkz. modül başlığı). Kontenjan, puan, sıra normal şekilde birleşir.
_ABU_YERLESEN_KORU = True

ABU = "ANKARA BİLİM ÜNİVERSİTESİ"

_TR = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


# ---------------------------------------------------------------------------
# Değer temizliği
# ---------------------------------------------------------------------------
def bos_mu(v: Any) -> bool:
    """`0`, `0.0`, `False` BOŞ DEĞİLDİR — gerçek ölçüm olabilirler."""
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        return not v.strip()
    return False


def sayi(v: Any) -> Optional[float]:
    """Metin/sayı karışık hücreyi sayıya çevirir; çeviremezse `None`.

    Türkçe binlik ve ondalık ayracı, yüzde işareti ve para birimi
    işaretleri temizlenir. Çevrilemeyen değer SIFIR SAYILMAZ.
    """
    if bos_mu(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace("₺", "").replace("TL", "")
    s = s.replace(" ", "").strip()
    if not s:
        return None
    # "1.234,56" → "1234.56" ;  "1,234.56" → "1234.56"
    if "," in s and "." in s:
        s = (s.replace(".", "").replace(",", ".")
             if s.rfind(",") > s.rfind(".") else s.replace(",", ""))
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def metin(v: Any) -> Optional[str]:
    if bos_mu(v):
        return None
    return re.sub(r"\s+", " ", str(v)).strip()


def kod(v: Any) -> Optional[str]:
    """Program kodu METİN olarak korunur — baştaki sıfırlar anlamlıdır."""
    if bos_mu(v):
        return None
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


def normalize_ad(v: Any) -> Optional[str]:
    """Kurum/birim adı için deterministik normalizasyon.

    Yapılan: Unicode birleştirme, Türkçe harf katlama, noktalama
    temizliği, fazla boşluk atma, büyük harfe çevirme. YAPILMAYAN:
    bulanık benzerlik. Normalize hâller birebir tutmuyorsa kayıtlar
    eşleştirilmez — "Yazılım" ile "Bilgisayar" mühendisliğinin
    birleşmesi bu yüzden imkânsızdır.
    """
    s = metin(v)
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_TR).upper()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip() or None


#: Kurum adının sonundaki parantezli İL EKİ.
#: Arkadaşın kaynağı adları "BAŞKENT ÜNİVERSİTESİ (ANKARA)" biçiminde
#: yazıyor; projenin canonical adı ise ilsizdir. Bu iki yazım aynı
#: kurumdur ve ayrı tutulurlarsa grafikte AYNI ÜNİVERSİTE İKİ ÇİZGİ
#: olur — biri 2021-2024 dolu 2025-2026 boş, diğeri tam tersi.
#: Ölçüldü: 14 kurum bu yüzden ikiye bölünmüştü.
#:
#: Kural DAR: yalnızca SONDAKİ parantez, yalnızca içi il adıysa atılır.
#: "Bilgisayar Mühendisliği (Burslu)" gibi anlam taşıyan parantezlere
#: dokunulmaz — zaten bu yalnızca kurum adlarına uygulanır.
_IL_EKI = re.compile(r"\s*\((ANKARA)\)\s*$", re.IGNORECASE)


def kurum_adi_sadelestir(v: Any) -> Optional[str]:
    """Kurum adını il ekinden arındırılmış hâliyle döndürür."""
    s = metin(v)
    return _IL_EKI.sub("", s).strip() if s else None


def akademik_yil(v: Any) -> Optional[str]:
    """`2026`, `2026-2027`, `2026/27` → `2026-2027`."""
    s = metin(v)
    if not s:
        return None
    m = re.match(r"^(\d{4})\s*[-/]\s*(\d{2,4})$", s)
    if m:
        return f"{m.group(1)}-{int(m.group(1)) + 1}"
    m = re.match(r"^(\d{4})(\.0)?$", s)
    if m:
        return f"{m.group(1)}-{int(m.group(1)) + 1}"
    return s


# ---------------------------------------------------------------------------
# Birleştirme sayacı
# ---------------------------------------------------------------------------
class Sayac:
    def __init__(self) -> None:
        self.inserted = Counter()
        self.updated = Counter()
        self.unchanged = Counter()
        self.null_korundu = Counter()
        #: Kaynak dolu ama canonical de dolu olduğu için EZİLMEYEN alanlar
        #: (yalnızca `YALNIZ_EKSIGI_DOLDUR` kaynakları için anlamlı).
        self.dolu_korundu = Counter()
        self.ambiguous: List[Dict[str, Any]] = []
        self.yeni_alan: List[Dict[str, Any]] = []
        self.envanter: List[Dict[str, Any]] = []

    def ozet(self) -> List[Dict[str, Any]]:
        tablolar = (set(self.inserted) | set(self.updated)
                    | set(self.unchanged) | set(self.null_korundu))
        return [{"tablo": t, "inserted": self.inserted[t],
                 "updated": self.updated[t], "unchanged": self.unchanged[t],
                 "friend_null_kept_existing": self.null_korundu[t],
                 "existing_kept_not_overwritten": self.dolu_korundu[t]}
                for t in sorted(tablolar)]


def alan_birlestir(sayac: Sayac, tablo: str, mevcut: Any, friend: Any) -> Tuple[Any, bool]:
    """Tek alanın birleşmiş değerini ve değişip değişmediğini döndürür."""
    if bos_mu(friend):
        if not bos_mu(mevcut):
            sayac.null_korundu[tablo] += 1
        return mevcut, False
    if bos_mu(mevcut):
        return friend, True
    # Sayısal karşılaştırma: 50 ile 50.0 aynı değerdir, güncelleme sayılmaz.
    a, b = sayi(mevcut), sayi(friend)
    if a is not None and b is not None:
        return (friend, False) if abs(a - b) < 1e-9 else (friend, True)
    return (friend, False) if str(mevcut) == str(friend) else (friend, True)


# ---------------------------------------------------------------------------
# 1) PROGRAM DÜZEYİ METRİKLER  →  yok_atlas_benchmark_metrics
# ---------------------------------------------------------------------------
#: Arkadaş kolonu → canonical metrik adı.
#: Soldakiler kaynak dosyalarda geçen adlar, sağdakiler tablonun zaten
#: kullandığı metrik adları. Yeni metrikler (ücret, kadro, cinsiyet)
#: aynı tabloya yazılır: mevcut yapı `metric/value` uzun formatta
#: olduğu için YENİ KOLON ya da YENİ TABLO GEREKMEZ.
METRIK_ESLEME = {
    # mevcut metrikler
    "quota": "quota", "kontenjan": "quota",
    "placed_students": "placed", "yerlesme": "placed",
    "occupancy_rate": "occupancy_percent",
    "base_score": "base_score", "puan": "base_score",
    "success_rank": "success_rank", "sira": "success_rank",
    "tercihbirinci": "preference_first",
    "tercihilkuc": "preference_top3",
    "tercihilkdokuz": "preference_top9",
    "tercihtoplam": "preference_total",
    # --- DOSYA ADIYLA İLGİSİ OLMAYAN, YENİ KAZANILAN METRİKLER ---
    # Bunlar "yks" ya da "ucret" adlı dosyaların içinden çıktı; ada
    # bakılsaydı hiçbiri keşfedilmezdi.
    "kontenjan_2025": "quota",
    "yerlesen_kayitli_2025": "placed",
    "doluluk_yuzde_2025": "occupancy_percent",
    "ek_yerlestirme_bos_kontenjan": "additional_placement_vacancy",
    "taban_puan_2025": "base_score",
    "basari_sirasi_2025": "success_rank",
    "annual_fee_try": "annual_fee_try",
    "prof": "staff_prof", "profesor": "staff_prof",
    "docent": "staff_docent",
    "dr_ogr_uyesi": "staff_dr_ogr_uyesi", "dou": "staff_dr_ogr_uyesi",
    "ars_gor": "staff_ars_gor", "arastirma_gorevlisi": "staff_ars_gor",
    "ogretim_gorevlisi": "staff_ogretim_gorevlisi",
    "toplam_ogretim_elemani": "staff_total",
    "erkek": "placed_male", "kiz": "placed_female",
    "liseli": "placed_high_school", "mezun": "placed_graduate",
    "unimezunu": "placed_university_graduate",
    "universiteli": "placed_university_student",
    "maxpuan": "highest_score",
    "birinci": "first_choice_placed",
    "birincipuan": "first_choice_base_score",
    "birincimaxpuan": "first_choice_highest_score",
    "birinciyerlesme": "first_choice_placements",
    "min_rank_requirement": "min_rank_requirement",
    "ogrenci_ogretim_elemani_orani": "student_per_staff",
}

#: ÖLÇÜM alanları: kaynakta sıfır "ölçülmedi" demektir (bkz. 2021/2022
#: Metadata: "Puan/sıra gibi ÖLÇÜM alanlarında bu sıfırlar BOŞA
#: çevrilmiştir"). SAYIM alanlarında sıfır gerçek değerdir ve korunur.
OLCUM_METRIKLERI = frozenset({
    "base_score", "success_rank", "highest_score",
    "first_choice_base_score", "first_choice_highest_score",
    "min_rank_requirement",
})

#: Yüzdeye çevrilecek metrikler (kaynak 0-1 aralığında veriyor).
ORAN_METRIKLERI = {"occupancy_percent"}

#: Metrik → birim. Tabloda `unit` NOT NULL; mevcut kayıtların kullandığı
#: Türkçe birimler korunur ki aynı metrik iki farklı birimle görünmesin.
BIRIM = {
    "quota": "kişi", "placed": "kişi", "occupancy_percent": "%",
    "base_score": "puan", "success_rank": "sıra", "highest_score": "puan",
    "preference_first": "tercih", "preference_top3": "tercih",
    "preference_top9": "tercih", "preference_total": "tercih",
    "annual_fee_try": "TL",
    "staff_prof": "kişi", "staff_docent": "kişi",
    "staff_dr_ogr_uyesi": "kişi", "staff_ars_gor": "kişi",
    "staff_ogretim_gorevlisi": "kişi", "staff_total": "kişi",
    "staff_prof_ratio": "%", "students_per_staff": "oran",
    "student_per_staff": "oran",
    "placed_male": "kişi", "placed_female": "kişi",
    "placed_high_school": "kişi", "placed_graduate": "kişi",
    "placed_university_graduate": "kişi", "placed_university_student": "kişi",
    "first_choice_placed": "kişi", "first_choice_placements": "kişi",
    "first_choice_base_score": "puan", "first_choice_highest_score": "puan",
    "min_rank_requirement": "sıra",
    "additional_placement_vacancy": "kişi",
    "students_associate": "kişi", "students_bachelor": "kişi",
    "students_master": "kişi", "students_doctorate": "kişi",
    "students_total": "kişi",
}


def _program_satirlari(df: pd.DataFrame, yil_sabit: Optional[str],
                       kaynak: str) -> Iterable[Dict[str, Any]]:
    """Bir sayfayı (üniversite, program kodu, yıl, metrik, değer) dizisine açar."""
    kolonlar = {c.lower().strip(): c for c in df.columns}

    def al(*adaylar):
        for a in adaylar:
            if a in kolonlar:
                return kolonlar[a]
        return None

    k_kod = al("program_code", "kaynak_id", "program_kodu")
    k_uni = al("university_name", "universite")
    k_prog = al("program_name", "program_adi")
    k_fak = al("faculty", "fakulte")
    k_yil = al("academic_year")
    k_dil = al("language", "ogrenim_dili")
    k_burs = al("scholarship_type", "burs_turu")
    k_tur = al("university_type", "universite_turu")
    if not k_kod:
        return

    for _, r in df.iterrows():
        pkod = kod(r[k_kod])
        if not pkod:
            continue
        yil = akademik_yil(r[k_yil]) if k_yil else yil_sabit
        if not yil:
            continue
        ortak = {
            "program_code": pkod,
            "academic_year": yil,
            "university_name": metin(r[k_uni]) if k_uni else ABU,
            "program_name": metin(r[k_prog]) if k_prog else None,
            "faculty_name": metin(r[k_fak]) if k_fak else None,
            "language": metin(r[k_dil]) if k_dil else None,
            "scholarship": metin(r[k_burs]) if k_burs else None,
            "university_type": metin(r[k_tur]) if k_tur else None,
            "source_file": kaynak,
        }
        for ham_kolon, gercek in kolonlar.items():
            metrik = METRIK_ESLEME.get(ham_kolon)
            if not metrik:
                continue
            deger = sayi(r[gercek])
            # ARKADAŞIN BOŞ DEĞERİ DE ÜRETİLİR (`value=None`).
            # Atlanırsa davranış yine doğru olurdu — boş değer mevcut
            # veriyi zaten silmez — ama "kaç değer korundu" ÖLÇÜLEMEZDİ.
            # Sessizce doğru olmak yetmez; sayılabilir olmalı.
            if metrik in OLCUM_METRIKLERI and deger == 0:
                deger = None      # ölçüm alanında sıfır = ölçülmedi
            if deger is not None and metrik in ORAN_METRIKLERI and 0 <= deger <= 1:
                deger *= 100.0
            yield {**ortak, "metric": metrik, "value": deger}


def _canonical_kurum_adlari(cur: sqlite3.Cursor) -> Dict[str, str]:
    """sade ad → veritabanındaki YERLEŞİK yazım.

    Yeni kayıt eklerken kurumun adı kaynaktan değil BURADAN alınır.
    Böylece "(ANKARA)" ekli yazım veritabanına hiç girmez ve aynı
    kurum tek çizgi olarak kalır.
    """
    esleme: Dict[str, str] = {}
    for (ad,) in cur.execute(
            "SELECT DISTINCT university_name FROM yok_atlas_benchmark_metrics "
            "WHERE university_name IS NOT NULL"):
        sade = kurum_adi_sadelestir(ad)
        if not sade:
            continue
        anahtar = normalize_ad(sade)
        # İl eki OLMAYAN yazım tercih edilir: canonical olan odur.
        if anahtar and (anahtar not in esleme or len(ad) < len(esleme[anahtar])):
            esleme[anahtar] = sade
    return esleme


def hizala_kurum_adlari(con: sqlite3.Connection, sayac: Sayac) -> int:
    """Veritabanındaki il ekli kurum adlarını canonical yazıma çeker.

    Bu bir veri düzeltmesidir, birleştirme değil: değer alanlarına
    dokunmaz, yalnızca `university_name` yazımını tekilleştirir.
    Ölçüldü: hizalama sonrası (program kodu, yıl, metrik) üçlüsünde
    ÇAKIŞMA OLUŞMUYOR, yani kayıt kaybı ya da duplicate riski yok.
    """
    cur = con.cursor()
    duzeltilen = 0
    for (ad,) in list(cur.execute(
            "SELECT DISTINCT university_name FROM yok_atlas_benchmark_metrics "
            "WHERE university_name LIKE '%(%'")):
        sade = kurum_adi_sadelestir(ad)
        if not sade or sade == ad:
            continue
        cur.execute(
            "UPDATE yok_atlas_benchmark_metrics SET university_name = ? "
            "WHERE university_name = ?", (sade, ad))
        duzeltilen += cur.rowcount
    if duzeltilen:
        sayac.updated["yok_atlas_benchmark_metrics(kurum adı)"] += duzeltilen
    return duzeltilen


def birlestir_program_metrikleri(con: sqlite3.Connection, sayac: Sayac,
                                 satirlar: List[Dict[str, Any]]) -> None:
    """Alan düzeyi birleştirme: metrik = alan.

    Bu tablo uzun formatta (`metric`/`value`) olduğu için "alan düzeyi
    birleştirme" doğrudan satır düzeyinde karşılık bulur: arkadaşın
    doldurduğu her metrik ilgili satırı günceller, dokunmadığı
    metrikler yerinde kalır. Satırın tamamı asla değiştirilmez.
    """
    T = "yok_atlas_benchmark_metrics"
    cur = con.cursor()
    mevcut = {
        (r[0], r[1], r[2]): (r[3], r[4])
        for r in cur.execute(
            "SELECT source_program_code, academic_year, metric, value, id "
            f"FROM {T} WHERE source_dataset = ?", (KULVAR_PROGRAM,))
    }
    canonical_kurum = _canonical_kurum_adlari(cur)

    for s in satirlar:
        anahtar = (s["program_code"], s["academic_year"], s["metric"])

        # ARKADAŞ DEĞERİ BOŞ: mevcut dolu değer korunur, sayılır.
        if s["value"] is None:
            if anahtar in mevcut and not bos_mu(mevcut[anahtar][0]):
                sayac.null_korundu[T] += 1
            continue

        # ABÜ yerleşen tanımı farklı — üzerine yazma (bkz. modül başlığı).
        if (_ABU_YERLESEN_KORU and s["metric"] == "placed"
                and normalize_ad(s["university_name"]) == normalize_ad(ABU)
                and anahtar in mevcut):
            sayac.unchanged[T] += 1
            continue

        if anahtar in mevcut:
            eski, satir_id = mevcut[anahtar]

            # YALNIZCA BOŞLUK DOLDURAN KAYNAK: dolu değer korunur.
            if (any(ad in (s["source_file"] or "") for ad in YALNIZ_EKSIGI_DOLDUR)
                    and not bos_mu(eski)):
                sayac.dolu_korundu[T] += 1
                sayac.unchanged[T] += 1
                continue

            yeni, degisti = alan_birlestir(sayac, T, eski, s["value"])
            if degisti:
                cur.execute(
                    f"UPDATE {T} SET value = ?, source_file = ?, "
                    "source_description = ? WHERE id = ?",
                    (yeni, s["source_file"],
                     f"newdata birleştirme {dt.date.today()}", satir_id))
                sayac.updated[T] += 1
            else:
                sayac.unchanged[T] += 1
            continue

        # `canonical_program_key` NOT NULL. Toplu ("... ve ... programları")
        # satırlarda proje fonksiyonu bilerek None döndürür: bunlar tek bir
        # programa ait olmadığı için program karşılaştırmasına giremezler.
        # Kayıp olmasın diye incelemeye bırakılır.
        pkey = canonical_program_key(s["program_name"])
        if not pkey:
            sayac.ambiguous.append({
                "sebep": "toplu/çözülemeyen program adı",
                "source_file": s["source_file"],
                "program_code": s["program_code"],
                "program_name": s["program_name"],
                "university": s["university_name"],
                "academic_year": s["academic_year"],
                "metric": s["metric"], "value": s["value"]})
            continue

        cur.execute(
            f"INSERT INTO {T} (university_name, faculty_name, program_name, "
            "canonical_program_key, canonical_faculty_key, "
            "city, university_type, program_language, scholarship_type, "
            "source_description, source_year, academic_year, metric, value, "
            "unit, source_dataset, source_file, source_program_code, "
            "source_row_identity, methodology, derived, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
            (canonical_kurum.get(normalize_ad(kurum_adi_sadelestir(
                 s["university_name"])), kurum_adi_sadelestir(
                 s["university_name"]) or s["university_name"]),
             s["faculty_name"] or "(belirtilmemiş)",
             s["program_name"], pkey, canonical_faculty_key(s["faculty_name"]),
             "ANKARA", s["university_type"], s["language"], s["scholarship"],
             f"newdata birleştirme {dt.date.today()}",
             int(s["academic_year"][:4]), s["academic_year"], s["metric"],
             s["value"], BIRIM.get(s["metric"], "birim"), KULVAR_PROGRAM,
             s["source_file"], s["program_code"],
             f"{s['source_file']}|{s['program_code']}|{s['academic_year']}",
             (_TANIM_2025
              if (s["metric"] in ("placed", "occupancy_percent")
                  and any(ad in (s["source_file"] or "")
                          for ad in YALNIZ_EKSIGI_DOLDUR))
              else "newdata kaynağından birebir aktarıldı"),
             dt.datetime.now()))
        mevcut[anahtar] = (s["value"], cur.lastrowid)
        sayac.inserted[T] += 1


# ---------------------------------------------------------------------------
# 2) KURUM DÜZEYİ METRİKLER  →  yok_atlas_benchmark_metrics (ayrı kulvar)
# ---------------------------------------------------------------------------
KURUM_METRIK_ESLEME = {
    "profesor": "staff_prof", "docent": "staff_docent",
    "dr_ogr_uyesi": "staff_dr_ogr_uyesi",
    "ogretim_gorevlisi": "staff_ogretim_gorevlisi",
    "arastirma_gorevlisi": "staff_ars_gor",
    "toplam_ogretim_elemani": "staff_total",
    "profesor_orani_yuzde": "staff_prof_ratio",
    "ogrenci_basina_ogretim_elemani": "students_per_staff",
    "onlisans": "students_associate", "lisans": "students_bachelor",
    "yuksek_lisans": "students_master", "doktora": "students_doctorate",
    "toplam": "students_total",
}


def birlestir_kurum_metrikleri(con: sqlite3.Connection, sayac: Sayac,
                               df: pd.DataFrame, kaynak: str) -> None:
    """Üniversite × yıl × metrik. Program kulvarına KARIŞMAZ.

    Kadro sayıları program düzeyi kulvara yazılsaydı `program_name`
    boş satırlar oluşur ve program karşılaştırma sorguları bozulurdu.
    Ayrı kulvar bunu yapısal olarak imkânsız kılar.
    """
    T = "yok_atlas_benchmark_metrics"
    cur = con.cursor()
    mevcut = {
        (r[0], r[1], r[2]): (r[3], r[4])
        for r in cur.execute(
            "SELECT source_university_code, academic_year, metric, value, id "
            f"FROM {T} WHERE source_dataset = ?", (KULVAR_KURUM,))
    }
    kolonlar = {c.lower().strip(): c for c in df.columns}
    k_uni = kolonlar.get("university_name")
    k_yil = kolonlar.get("academic_year")
    if not (k_uni and k_yil):
        return

    for _, r in df.iterrows():
        uni = metin(r[k_uni])
        yil = akademik_yil(r[k_yil])
        if not (uni and yil):
            continue
        anah_uni = normalize_ad(uni)
        for ham, gercek in kolonlar.items():
            metrik = KURUM_METRIK_ESLEME.get(ham)
            if not metrik:
                continue
            deger = sayi(r[gercek])
            if deger is None:
                continue
            anahtar = (anah_uni, yil, metrik)
            if anahtar in mevcut:
                eski, sid = mevcut[anahtar]
                yeni, degisti = alan_birlestir(sayac, T, eski, deger)
                if degisti:
                    cur.execute(f"UPDATE {T} SET value=?, source_file=? WHERE id=?",
                                (yeni, kaynak, sid))
                    sayac.updated[T] += 1
                else:
                    sayac.unchanged[T] += 1
                continue
            # Kurum düzeyi satırda program yoktur; NOT NULL kısıtı için
            # kurumun kendisi anahtar olur. Ayrı kulvarda durduğu için
            # program sorgularına karışmaz.
            cur.execute(
                f"INSERT INTO {T} (university_name, city, academic_year, "
                "canonical_program_key, faculty_name, program_name, metric, "
                "value, unit, source_dataset, source_file, "
                "source_university_code, source_program_code, "
                "source_row_identity, source_description, methodology, "
                "source_year, derived, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                (uni, "ANKARA", yil, f"KURUM::{anah_uni}",
                 "(kurum geneli)", "(kurum geneli)", metrik, deger,
                 BIRIM.get(metrik, "birim"), KULVAR_KURUM, kaynak, anah_uni,
                 f"KURUM::{anah_uni}", f"{kaynak}|{anah_uni}|{yil}|{metrik}",
                 f"newdata kurum düzeyi {dt.date.today()}",
                 "Kurum düzeyi; program karşılaştırmasına girmez",
                 int(yil[:4]), dt.datetime.now()))
            mevcut[anahtar] = (deger, cur.lastrowid)
            sayac.inserted[T] += 1


# ---------------------------------------------------------------------------
# 3) ÖĞRENCİ SAYILARI  →  university_student_headcounts
# ---------------------------------------------------------------------------
_SEVIYE = {"onlisans": "ONLISANS", "lisans": "LISANS",
           "yukseklisans": "YUKSEKLISANS", "doktora": "DOKTORA"}


def birlestir_ogrenci_sayilari(con: sqlite3.Connection, sayac: Sayac,
                               df: pd.DataFrame, kaynak: str) -> None:
    """Cinsiyet × öğretim türü × seviye kırılımı.

    `Yeni_Yillar_Detay` sayfası dosya adının söylemediği bir ayrıntı
    taşıyor: cinsiyet (E/K) ve öğretim türü (birinci/ikinci/uzaktan).
    Mevcut tablo bu kırılımı zaten destekliyor; yeni kolon gerekmedi.
    """
    T = "university_student_headcounts"
    cur = con.cursor()
    mevcut = {
        (r[0], r[1], r[2], r[3], r[4]): (r[5], r[6])
        for r in cur.execute(
            "SELECT university_name, academic_year, education_mode, "
            f"degree_level, gender, student_count, id FROM {T}")
    }
    kolonlar = {c.lower().strip(): c for c in df.columns}
    k_uni, k_yil = kolonlar.get("university_name"), kolonlar.get("academic_year")
    if not (k_uni and k_yil):
        return

    for _, r in df.iterrows():
        uni, yil = metin(r[k_uni]), akademik_yil(r[k_yil])
        if not (uni and yil):
            continue
        mod = metin(r[kolonlar["education_mode"]]) if "education_mode" in kolonlar else None
        mod = (mod or "BİRİNCİ").split()[0].upper()
        tur = metin(r[kolonlar["university_type"]]) if "university_type" in kolonlar else None
        sehir = metin(r[kolonlar["city"]]) if "city" in kolonlar else "ANKARA"

        for onek, seviye in _SEVIYE.items():
            for ek, cinsiyet in (("_e", "E"), ("_k", "K")):
                # `kolonlar` sözlüğünün anahtarları KÜÇÜK HARF. Aramayı
                # "onlisans_E" ile yapmak sessizce hiçbir şey bulmuyordu:
                # 77 satırlık cinsiyet kırılımı tamamen kayboluyordu ve
                # betik hata da vermiyordu.
                sut = kolonlar.get(onek + ek)
                if not sut:
                    continue
                deger = sayi(r[sut])
                if deger is None:
                    continue
                anahtar = (uni, yil, mod, seviye, cinsiyet)
                if anahtar in mevcut:
                    eski, sid = mevcut[anahtar]
                    yeni, degisti = alan_birlestir(sayac, T, eski, int(deger))
                    if degisti:
                        cur.execute(
                            f"UPDATE {T} SET student_count=?, source_file=?, "
                            "updated_at=? WHERE id=?",
                            (int(yeni), kaynak, dt.datetime.now(), sid))
                        sayac.updated[T] += 1
                    else:
                        sayac.unchanged[T] += 1
                    continue
                cur.execute(
                    f"INSERT INTO {T} (university_name, university_type, city, "
                    "academic_year, education_mode, degree_level, gender, "
                    "student_count, source_dataset, source_file, created_at, "
                    "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (uni, tur, sehir, yil, mod, seviye, cinsiyet, int(deger),
                     "newdata_2026", kaynak, dt.datetime.now(), dt.datetime.now()))
                mevcut[anahtar] = (int(deger), cur.lastrowid)
                sayac.inserted[T] += 1


# ---------------------------------------------------------------------------
# 4) STRATEJİK HEDEFLER  →  strategic_kpis
# ---------------------------------------------------------------------------
def birlestir_kpi(con: sqlite3.Connection, sayac: Sayac,
                  df: pd.DataFrame, kaynak: str) -> None:
    """Kurumun kendi stratejik plan göstergeleri (KİDR 2024).

    Yalnızca GÖSTERGESİ olan satırlar alınır: göstergesiz hedefler
    ölçülebilir bir KPI değildir ve tabloyu boş kayıtla doldurmaları
    panelin okunurluğunu bozardı.
    """
    T = "strategic_kpis"
    cur = con.cursor()
    # ÖLÇÜLDÜ: `Stratejik_Amac_Hedef` sayfasında `gosterge` kolonu 37
    # satırın 37'sinde de BOŞ. Yani bu sayfa ölçülebilir gösterge değil,
    # stratejik plan hiyerarşisi (amaç → hedef) taşıyor. Göstergesiz
    # satırları KPI tablosuna yazmak paneli boş kayıtla doldururdu.
    # Ölçülmüş değerler `Rapordan_Olgular` sayfasındadır ve kurum
    # metrikleri olarak ayrıca aktarılır.
    mevcut = {normalize_ad(r[0]): (r[1], r[2], r[3])
              for r in cur.execute(f"SELECT name, current_value, target_value, id FROM {T}")}

    for _, r in df.iterrows():
        ad = metin(r.get("gosterge"))
        if not ad:
            continue
        anah = normalize_ad(ad)
        mev, hed = r.get("mevcut_deger"), r.get("hedef_deger")
        yil = akademik_yil(r.get("hedef_yili"))
        birim = metin(r.get("birim"))
        aciklama = metin(r.get("hedef"))
        kaynak_belge = metin(r.get("kaynak_belge")) or kaynak

        if anah in mevcut:
            e_mev, e_hed, sid = mevcut[anah]
            y_mev, d1 = alan_birlestir(sayac, T, e_mev, mev)
            y_hed, d2 = alan_birlestir(sayac, T, e_hed, hed)
            if d1 or d2:
                cur.execute(
                    f"UPDATE {T} SET current_value=?, target_value=?, "
                    "data_source=?, updated_at=? WHERE id=?",
                    (None if bos_mu(y_mev) else str(y_mev),
                     None if bos_mu(y_hed) else str(y_hed),
                     kaynak_belge, dt.datetime.now(), sid))
                sayac.updated[T] += 1
            else:
                sayac.unchanged[T] += 1
            continue

        cur.execute(
            f"INSERT INTO {T} (name, dimension, unit, academic_year, "
            "current_value, target_value, description, data_source, "
            "higher_is_better, value_source, is_active, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,1,'manual',1,?,?)",
            (ad, metin(r.get("amac")), birim, yil,
             None if bos_mu(mev) else str(mev),
             None if bos_mu(hed) else str(hed),
             aciklama, kaynak_belge, dt.datetime.now(), dt.datetime.now()))
        mevcut[anah] = (mev, hed, cur.lastrowid)
        sayac.inserted[T] += 1


# ---------------------------------------------------------------------------
# 5) ABÜ PROGRAM ÜCRETLERİ  →  program_tuition_fees
# ---------------------------------------------------------------------------
def birlestir_abu_ucret(con: sqlite3.Connection, sayac: Sayac,
                        df: pd.DataFrame, kaynak: str) -> None:
    """KULLANIM DIŞI — çağrılmıyor. Neden bırakıldığı aşağıda.

    GRANÜLERLİK FARKI YÜZÜNDEN YAZILMIYOR
    -------------------------------------
    `program_tuition_fees` PROGRAM düzeyinde ("Bilgisayar Mühendisliği"),
    arkadaşın ücret sayfası ise BURS VARYANTI düzeyinde ("Bilgisayar
    Mühendisliği (%50 İndirimli)", "(Burslu)", "(İngilizce, Burslu)").
    Ölçüldü: eşleştirme hiçbir satırda tutmuyor ve 60 satırın tamamı
    INSERT olarak gidiyordu — yani aynı programın ücreti tabloda iki
    farklı granülerlikte iki kez görünecekti. Bu tam olarak yasaklanan
    duplicate durumudur.

    Veri KAYBOLMUYOR: aynı ücretler `yok_atlas_benchmark_metrics`
    tablosuna `annual_fee_try` metriği olarak, program KODUYLA
    eşleşerek ve varyant granülerliği KORUNARAK yazılıyor.

    Fonksiyon silinmedi çünkü ileride program-varyant eşlemesi
    kurulursa doğru başlangıç noktası budur.

    Ücret "tam (ücretli) fiyat"tır — kaynak Metadata'sı açıkça
    söylüyor: burslu öğrenci 0, %50 indirimli yarısını öder. Bu yüzden
    burs varyantına göre bölünmez; olduğu gibi saklanır ve yorumu
    servis katmanına bırakılır.
    """
    T = "program_tuition_fees"
    cur = con.cursor()
    abu = normalize_ad(ABU)
    kolonlar = {c.lower().strip(): c for c in df.columns}
    if "university_name" not in kolonlar:
        return

    mevcut = {
        (r[0], normalize_ad(r[1])): (r[2], r[3])
        for r in cur.execute(
            "SELECT academic_year, source_program_name, annual_fee, id "
            f"FROM {T}")
    }
    for _, r in df.iterrows():
        if normalize_ad(r[kolonlar["university_name"]]) != abu:
            continue
        yil = akademik_yil(r[kolonlar.get("academic_year")]) if "academic_year" in kolonlar else None
        ad = metin(r[kolonlar.get("program_name")]) if "program_name" in kolonlar else None
        ucret = sayi(r[kolonlar.get("annual_fee_try")]) if "annual_fee_try" in kolonlar else None
        if not (yil and ad) or ucret is None:
            continue
        anahtar = (yil, normalize_ad(ad))
        if anahtar in mevcut:
            eski, sid = mevcut[anahtar]
            yeni, degisti = alan_birlestir(sayac, T, eski, ucret)
            if degisti:
                cur.execute(f"UPDATE {T} SET annual_fee=?, source_file=?, "
                            "updated_at=? WHERE id=?",
                            (yeni, kaynak, dt.datetime.now(), sid))
                sayac.updated[T] += 1
            else:
                sayac.unchanged[T] += 1
            continue
        cur.execute(
            f"INSERT INTO {T} (academic_year, source_faculty_name, "
            "source_program_name, education_language, fee_type, annual_fee, "
            "currency, source_dataset, source_file, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (yil,
             metin(r[kolonlar["faculty"]]) if "faculty" in kolonlar else None,
             ad,
             metin(r[kolonlar["language"]]) if "language" in kolonlar else None,
             metin(r[kolonlar["scholarship_type"]]) if "scholarship_type" in kolonlar else None,
             ucret, "TRY", "newdata_2026", kaynak,
             dt.datetime.now(), dt.datetime.now()))
        mevcut[anahtar] = (ucret, cur.lastrowid)
        sayac.inserted[T] += 1


# ---------------------------------------------------------------------------
# 6) KURUMUN KENDİ RAPORLADIĞI ÖLÇÜMLER  →  kurum kulvarı
# ---------------------------------------------------------------------------
#: `Rapordan_Olgular` sayfası dosya adının ("stratejik hedefler")
#: söylemediği bir şey taşıyor: kurumun KİDR raporunda beyan ettiği
#: gerçek sayılar. Bunlar YÖK portalındaki sayılarla ÇELİŞEBİLİR ve
#: bu çelişki yönetim için bilgidir; atılmaz.
OLGU_ESLEME = {
    "lisans ogrenci sayisi": "students_bachelor_reported",
    "yuksek lisans ogrenci sayisi": "students_master_reported",
    "onlisans ogrenci sayisi": "students_associate_reported",
    "toplam ogrenci sayisi raporun beyani": "students_total_reported",
    "fakulte sayisi": "faculty_count_reported",
    "meslek yuksekokulu sayisi": "vocational_school_count_reported",
    "bolum sayisi": "department_count_reported",
    "program sayisi": "program_count_reported",
    "akademik personel sayisi": "academic_staff_count_reported",
    "idari personel sayisi": "administrative_staff_count_reported",
    # --- İNCELEMEDEN SONRA EKLENENLER ---
    # İlk turda eşlenemeyip incelemeye düşen 7 olgu tek tek bakıldı;
    # hiçbirinde iki makul canonical karşılık yoktu, hepsi tek anlamlı.
    "lisansustu egitim enstitusu": "graduate_school_count_reported",
    "ogrenci toplulugu sayisi": "student_club_count_reported",
    "kurulus yili": "founding_year_reported",
    # DİKKAT: "açılıştaki" olanlar KURULUŞ ANINDAKİ sayıdır, bugünkü
    # değil. `faculty_count_reported` (2024'te 4) ile aynı metrik adına
    # yazılsalardı kurumun bugünkü fakülte sayısı 3 görünürdü.
    "acilistaki fakulte sayisi": "faculty_count_at_founding",
    "acilistaki bolum sayisi": "department_count_at_founding",
    "stratejik amac sayisi": "strategic_goal_count",
    "stratejik hedef sayisi": "strategic_objective_count",
}


def birlestir_kurum_olgulari(con: sqlite3.Connection, sayac: Sayac,
                             df: pd.DataFrame, kaynak: str) -> None:
    T = "yok_atlas_benchmark_metrics"
    cur = con.cursor()
    anah_uni = normalize_ad(ABU)
    mevcut = {
        (r[0], r[1]): (r[2], r[3])
        for r in cur.execute(
            "SELECT academic_year, metric, value, id "
            f"FROM {T} WHERE source_dataset = ? AND source_university_code = ?",
            (KULVAR_KURUM, anah_uni))
    }

    # ZAMANSIZ OLGULARIN DÖNEMİ.
    # "Kuruluş yılı", "Stratejik amaç sayısı" gibi olguların
    # `akademik_yil` hücresi "—" geliyor: bunlar bir öğretim yılına ait
    # değil. Yıl uydurulmaz; hepsi AYNI BELGEDEN geldiği için o
    # sayfadaki diğer olguların dönemi kullanılır ve `methodology`
    # alanında bunun bir atama olduğu yazılır.
    donemler = [akademik_yil(x) for x in df.get("akademik_yil", [])]
    varsayilan_yil = next(
        (d for d in donemler if d and re.match(r"^\d{4}-\d{4}$", d)), None)
    for _, r in df.iterrows():
        ad = normalize_ad(r.get("olgu"))
        deger = sayi(r.get("deger"))
        yil = akademik_yil(r.get("akademik_yil"))
        zamansiz = not (yil and re.match(r"^\d{4}-\d{4}$", yil))
        if zamansiz:
            yil = varsayilan_yil
        if not ad or deger is None or not yil:
            continue
        metrik = OLGU_ESLEME.get((ad or "").lower())
        if not metrik:
            sayac.ambiguous.append({
                "sebep": "kurum olgusu eşlenemedi",
                "source_file": kaynak, "program_code": "", "program_name": "",
                "university": ABU, "academic_year": yil,
                "metric": metin(r.get("olgu")), "value": deger})
            continue
        anahtar = (yil, metrik)
        if anahtar in mevcut:
            eski, sid = mevcut[anahtar]
            yeni, degisti = alan_birlestir(sayac, T, eski, deger)
            if degisti:
                cur.execute(f"UPDATE {T} SET value=?, source_file=? WHERE id=?",
                            (yeni, kaynak, sid))
                sayac.updated[T] += 1
            else:
                sayac.unchanged[T] += 1
            continue
        cur.execute(
            f"INSERT INTO {T} (university_name, city, academic_year, "
            "canonical_program_key, faculty_name, program_name, metric, value, "
            "unit, source_dataset, source_file, source_university_code, "
            "source_program_code, source_row_identity, source_description, "
            "methodology, source_year, derived, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
            (ABU, "ANKARA", yil, f"KURUM::{anah_uni}", "(kurum geneli)",
             "(kurum geneli)", metrik, deger,
             metin(r.get("birim")) or "adet", KULVAR_KURUM, kaynak, anah_uni,
             f"KURUM::{anah_uni}", f"{kaynak}|{anah_uni}|{yil}|{metrik}",
             metin(r.get("kaynak_belge")) or "KİDR 2024",
             ("Kurumun kendi raporundaki beyan" if not zamansiz else
              "Kurumun kendi raporundaki beyan; olgu döneme bağlı değil, "
              "raporun dönemine yazıldı"), int(yil[:4]),
             dt.datetime.now()))
        mevcut[anahtar] = (deger, cur.lastrowid)
        sayac.inserted[T] += 1


# ---------------------------------------------------------------------------
# 7) KAYNAK ÇELİŞKİLERİ  →  data_source_conflicts
# ---------------------------------------------------------------------------
def birlestir_celiskiler(con: sqlite3.Connection, sayac: Sayac,
                         df: pd.DataFrame, kaynak: str) -> None:
    """Arkadaşın tespit ettiği kaynak çelişkileri kayda geçer.

    Bunlar hata değil, iki resmî kaynağın farklı sayı vermesidir
    (örneğin KİDR raporu önlisans öğrencilerini hiç saymıyor). Karar
    destek açısından değerlidir: bir sayı sorulduğunda hangi kaynağın
    ne dediği görülebilmelidir.
    """
    T = "data_source_conflicts"
    cur = con.cursor()
    mevcut = {(r[0], r[1]) for r in cur.execute(
        f"SELECT record_label, field_name FROM {T}")}
    for _, r in df.iterrows():
        metrik = metin(r.get("metrik"))
        yil = metin(r.get("akademik_yil"))
        if not metrik:
            continue
        etiket = f"{metrik} · {yil}"
        # Benzersizlik kısıtı (table_name, record_id, field_name,
        # incoming_source) üzerinde. Alan adını sabit bırakmak dört
        # çelişkinin ilkinden sonrasını çakıştırıyordu.
        alan = f"newdata::{normalize_ad(metrik)}::{yil}"
        if (etiket, alan) in mevcut:
            sayac.unchanged[T] += 1
            continue
        cur.execute(
            f"INSERT INTO {T} (table_name, record_id, field_name, "
            "record_label, existing_value, existing_source, incoming_value, "
            "incoming_source, resolution, note, detected_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("yok_atlas_benchmark_metrics", 0, alan, etiket,
             metin(r.get("deger_1")), metin(r.get("kaynak_1")),
             metin(r.get("deger_2")), metin(r.get("kaynak_2")),
             "review_required",
             f"{metin(r.get('aciklama')) or ''} (fark: {metin(r.get('fark'))})",
             dt.datetime.now()))
        mevcut.add((etiket, alan))
        sayac.inserted[T] += 1


# ---------------------------------------------------------------------------
# Keşif + sürücü
# ---------------------------------------------------------------------------
def envanter_cikar(sayac: Sayac) -> List[Tuple[Path, str, pd.DataFrame]]:
    """Klasörü özyinelemeli tarar; DOSYA ADINA DEĞİL İÇERİĞE bakar.

    Her Excel dosyasının BÜTÜN sayfaları okunur. Sınıflandırma
    kolonlardan yapılır: bir sayfada `program_code` varsa program
    düzeyi, `education_mode` varsa öğrenci kırılımı, `gosterge` varsa
    stratejik hedef sayfasıdır — dosyanın adı ne olursa olsun.
    """
    sayfalar = []
    for f in sorted(NEWDATA.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in (".xlsx", ".xls", ".csv"):
            continue
        # KENDİ ÇIKTIMIZI GİRDİ SANMA. `_merge_output/` altındaki
        # raporlar ikinci çalıştırmada veri dosyası gibi taranıyordu;
        # betiği idempotent olmaktan çıkarırdı.
        if CIKTI in f.parents:
            continue
        rel = str(f.relative_to(NEWDATA))
        if f.suffix.lower() == ".csv":
            df = pd.read_csv(f)
            sayfalar.append((f, "(csv)", df))
            sayac.envanter.append({"dosya": rel, "sheet": "(csv)",
                                   "satir": len(df), "kolon": len(df.columns),
                                   "kolonlar": "; ".join(map(str, df.columns))})
            continue
        xl = pd.ExcelFile(f)
        for sh in xl.sheet_names:
            df = xl.parse(sh)
            sayfalar.append((f, sh, df))
            sayac.envanter.append({"dosya": rel, "sheet": sh,
                                   "satir": len(df), "kolon": len(df.columns),
                                   "kolonlar": "; ".join(map(str, df.columns))})
    return sayfalar


#: Dosya adıyla ilgisi olmayıp içerikten keşfedilen değerli alanlar.
#: Rapor için; hangi kolonun nereye gittiğini gösterir.
def _yeni_alan_kaydet(sayac: Sayac, dosya: str, sheet: str,
                      kolonlar: Iterable[str]) -> None:
    ANLAM = {
        "annual_fee_try": ("Programın yıllık tam öğrenim ücreti (TL)",
                           "yok_atlas_benchmark_metrics.metric='annual_fee_try'"),
        "prof": ("Programa bağlı profesör sayısı",
                 "yok_atlas_benchmark_metrics.metric='staff_prof'"),
        "docent": ("Programa bağlı doçent sayısı",
                   "yok_atlas_benchmark_metrics.metric='staff_docent'"),
        "dr_ogr_uyesi": ("Programa bağlı Dr. Öğr. Üyesi sayısı",
                         "yok_atlas_benchmark_metrics.metric='staff_dr_ogr_uyesi'"),
        "ars_gor": ("Programa bağlı araştırma görevlisi sayısı",
                    "yok_atlas_benchmark_metrics.metric='staff_ars_gor'"),
        "erkek": ("Yerleşen erkek öğrenci sayısı",
                  "yok_atlas_benchmark_metrics.metric='placed_male'"),
        "kiz": ("Yerleşen kız öğrenci sayısı",
                "yok_atlas_benchmark_metrics.metric='placed_female'"),
        "liseli": ("Yerleşenlerin lise öğrencisi olanları",
                   "yok_atlas_benchmark_metrics.metric='placed_high_school'"),
        "mezun": ("Yerleşenlerin mezun olanları",
                  "yok_atlas_benchmark_metrics.metric='placed_graduate'"),
        "tercihtoplam": ("Programı tercih eden toplam aday",
                         "yok_atlas_benchmark_metrics.metric='preference_total'"),
        "tercihbirinci": ("Programı 1. sırada yazan aday",
                          "yok_atlas_benchmark_metrics.metric='preference_first'"),
        "education_mode": ("Öğretim türü (birinci/ikinci/uzaktan)",
                           "university_student_headcounts.education_mode"),
        "onlisans_e": ("Önlisans erkek öğrenci",
                       "university_student_headcounts (gender='E')"),
        "gosterge": ("Stratejik plan performans göstergesi",
                     "strategic_kpis.name"),
        "min_rank_requirement": ("Programın taban sıralama koşulu",
                                 "yok_atlas_benchmark_metrics.metric='min_rank_requirement'"),
        "maxpuan": ("Yerleşenlerin en yüksek puanı",
                    "yok_atlas_benchmark_metrics.metric='highest_score'"),
    }
    for c in kolonlar:
        anahtar = str(c).lower().strip()
        if anahtar in ANLAM:
            anlam, hedef = ANLAM[anahtar]
            sayac.yeni_alan.append({
                "source_file": dosya, "sheet": sheet, "source_column": c,
                "semantic_meaning": anlam, "canonical_destination": hedef,
                "action": "merged"})


def calistir(uygula: bool) -> int:
    if not NEWDATA.is_dir():
        print(f"newdata klasörü bulunamadı: {NEWDATA}")
        return 2
    CIKTI.mkdir(parents=True, exist_ok=True)
    sayac = Sayac()
    sayfalar = envanter_cikar(sayac)
    print(f"Taranan: {len({p for p, _, _ in sayfalar})} dosya, "
          f"{len(sayfalar)} sayfa\n")

    yedek = None
    if uygula:
        damga = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        yedek = DB.parent / f"university_management_before_newdata_{damga}.db"
        shutil.copy2(DB, yedek)
        print(f"Yedek: {yedek.name}\n")

    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        # ÖNCE AD HİZALAMA: yeni satırlar canonical adla eşleşsin diye
        # birleştirmeden ÖNCE çalışır.
        n = hizala_kurum_adlari(con, sayac)
        if n:
            print(f"  kurum adı hizalandı: {n} satır")

        for f, sh, df in sayfalar:
            rel = str(f.relative_to(NEWDATA))
            kol = {str(c).lower().strip() for c in df.columns}
            if df.empty:
                continue
            _yeni_alan_kaydet(sayac, rel, sh, df.columns)

            # --- SINIFLANDIRMA İÇERİKTEN, ADDAN DEĞİL ---
            if {"program_code", "kaynak_id", "program_kodu"} & kol:
                yil_sabit = None
                m = re.search(r"(20\d{2})", sh) or re.search(r"(20\d{2})", f.stem)
                if m and "academic_year" not in kol:
                    yil_sabit = f"{m.group(1)}-{int(m.group(1)) + 1}"
                satirlar = list(_program_satirlari(df, yil_sabit, rel))
                if satirlar:
                    print(f"  program  {rel} :: {sh}  → {len(satirlar)} metrik")
                    birlestir_program_metrikleri(con, sayac, satirlar)
                # Ücret `annual_fee_try` metriği olarak yukarıda zaten
                # birleşti; `program_tuition_fees` granülerlik farkı
                # yüzünden atlanıyor (bkz. `birlestir_abu_ucret`).
                continue

            if {"onlisans_e", "lisans_e"} & kol:
                print(f"  öğrenci  {rel} :: {sh}  → {len(df)} satır")
                birlestir_ogrenci_sayilari(con, sayac, df, rel)
                continue

            if "olgu" in kol and "deger" in kol:
                print(f"  olgu     {rel} :: {sh}  → {len(df)} satır")
                birlestir_kurum_olgulari(con, sayac, df, rel)
                continue

            if {"kaynak_1", "kaynak_2"} <= kol:
                print(f"  çelişki  {rel} :: {sh}  → {len(df)} satır")
                birlestir_celiskiler(con, sayac, df, rel)
                continue

            if "gosterge" in kol:
                print(f"  KPI      {rel} :: {sh}  → {len(df)} satır")
                birlestir_kpi(con, sayac, df, rel)
                continue

            if "university_name" in kol and "academic_year" in kol and (
                    set(KURUM_METRIK_ESLEME) & kol):
                print(f"  kurum    {rel} :: {sh}  → {len(df)} satır")
                birlestir_kurum_metrikleri(con, sayac, df, rel)
                continue

        if uygula:
            con.commit()
            print("\nUYGULANDI (commit).")
        else:
            con.rollback()
            print("\nKURU ÇALIŞTIRMA — hiçbir değişiklik yazılmadı.")
    except Exception:
        con.rollback()
        print("\nHATA — geri alındı, veritabanı değişmedi.")
        raise
    finally:
        con.close()

    _raporla(sayac)
    print("\n" + "=" * 70)
    for s in sayac.ozet():
        print(f"  {s['tablo']:<34} +{s['inserted']:<6} ~{s['updated']:<6} "
              f"={s['unchanged']:<7} null-korundu:{s['friend_null_kept_existing']}")
    if yedek:
        print(f"\nYedek: {yedek}")
    return 0


def _raporla(sayac: Sayac) -> None:
    def yaz(ad: str, satirlar: List[Dict[str, Any]]) -> None:
        if not satirlar:
            return
        yol = CIKTI / ad
        with open(yol, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(satirlar[0]))
            w.writeheader()
            w.writerows(satirlar)
        print(f"  yazıldı: {yol.name} ({len(satirlar)} satır)")

    print()
    yaz("inventory.csv", sayac.envanter)
    yaz("merge_summary.csv", sayac.ozet())
    # Aynı kolon birden çok sayfada geçebilir; tekilleştirilir.
    gorulen, tekil = set(), []
    for a in sayac.yeni_alan:
        k = (a["source_file"], a["sheet"], a["source_column"])
        if k not in gorulen:
            gorulen.add(k)
            tekil.append(a)
    yaz("new_fields_discovered.csv", tekil)
    yaz("ambiguous_records.csv", sayac.ambiguous)

    # KALAN KAYITLARIN İNSAN İÇİN ÖZETİ.
    # `ambiguous_records.csv` her metrik satırını ayrı yazar (151 satır);
    # karar vermek için gereken şey ise KAÇ FARKLI VARLIK olduğudur.
    # Bu dosya onu gösterir: aynı varlığın 85 metriği tek satırda.
    ozet: Dict[str, Dict[str, Any]] = {}
    for a in sayac.ambiguous:
        deger = a.get("program_name") or a.get("metric") or "?"
        k = (a.get("sebep", ""), deger)
        kayit = ozet.setdefault(str(k), {
            "source_file": a.get("source_file", ""),
            "sheet": "(program sayfaları)",
            "source_value": deger,
            "entity_type": ("program" if "program" in a.get("sebep", "")
                            else "kurum olgusu"),
            "candidate_1": "", "candidate_2": "",
            "reason": "", "recommendation": "", "_adet": 0,
        })
        kayit["_adet"] += 1

    for k, v in ozet.items():
        if v["entity_type"] == "program":
            v["candidate_1"] = "(tek bir programa karşılık gelmiyor)"
            v["candidate_2"] = "(fakülte/alan toplamı olabilir)"
            v["reason"] = (
                "Ad açıkça çoğul ve toplu: '… Programları'. Kaynakta tek "
                "bir YÖK programını değil bir grubun toplamını gösteriyor. "
                "Program düzeyi karşılaştırmaya girerse tek programlarla "
                "toplamlar aynı grafikte kıyaslanır ve sayılar şişer.")
            v["recommendation"] = (
                "DIŞARIDA BIRAK. Bu bir eşleştirme sorunu değil, farklı "
                "granülerlik. Kurum/fakülte düzeyi bir toplam metriği "
                "istenirse ayrı kulvarda ele alınmalı.")
        v["affected_rows"] = v.pop("_adet")
    yaz("remaining_ambiguous_review.csv", list(ozet.values()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true",
                   help="Değişiklikleri gerçekten yaz (yedek alarak).")
    sys.exit(calistir(p.parse_args().apply))
