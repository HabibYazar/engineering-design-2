#!/usr/bin/env python
"""YÖK KAYIT DEFTERİ + ÖĞRENCİ SAYILARI AKTARIMI  (data/ekdata/part2)

KAPSAM
------
Üç ayrı YÖK dışa aktarımı:

  1. "FakültelerEnstitülerYOMYO Hakkında Genel Bilgiler …xls"
     Ankara'daki 23 üniversitenin fakülte/enstitü/YO/MYO kayıt defteri.
     Bizden: açılış tarihi + YÖK kayıt durumu.

  2. "Bölümler Hakkında Genel Bilgiler …xls"
     Aynı üniversitelerin bölüm kayıt defteri. `Birim Grubu` sütunu
     bölümün bağlı olduğu birimi AÇIKÇA verir; eşleştirmede bu kullanılır.

  3. "Öğrenci Sayıları*.xls"  (4 farklı yıl)
     Ankara ilindeki bütün üniversitelerin FİİLEN KAYITLI öğrenci
     sayıları; öğrenim türü × düzey × cinsiyet kırılımıyla.

NEDEN AYRI BETİK
----------------
`import_ekdata.py` part-1 kümesini (ÖSYM + müfredat) aktarır ve o akış
kanıtlanmış durumda. Bu dosyalar hem farklı bir biçimde (eski BIFF
`.xls`) hem de farklı bir varlık kümesindedir. Ayrı betik, part-1
davranışının bit düzeyinde aynı kalmasını garanti eder.

DEĞİŞMEYECEK OLANLAR (kullanıcı gereksinimi)
--------------------------------------------
  · `academic_programs.student_count`  — ÖSYM'den TÜRETİLİR, dokunulmaz
  · `yks_placement_records`            — okunmaz bile
  · müfredat, personel-ders kayıtları  — bu betiğin haberi yok
  · hiyerarşi                          — yeni birim/bölüm OLUŞTURULMAZ
  · `is_active`                        — bizim soft-delete bayrağımız;
                                         YÖK'ün `Birim Durum` alanı ayrı
                                         bir sütuna (`yok_status`) yazılır

YIL BİLGİSİ DOSYADA YOKTUR
--------------------------
"Öğrenci Sayıları" dosyalarının içinde akademik yıl geçmez. Tahmin
ETMEYİZ: yıl, aşağıdaki eşlemeden ya da `--yil` seçeneğinden gelir.
Eşlemede olmayan bir dosya AKTARILMAZ ve rapora düşer.

ÇİFT SAYMA KORUMASI (üç katman)
-------------------------------
  1. `Öğrenim Türü == TOPLAM` satırları atlanır.
  2. Yalnızca E ve K hücreleri yazılır; T sütunu okunmaz (T = E+K).
  3. Doğal anahtar (üniversite, yıl, öğrenim türü, düzey, cinsiyet)
     tekildir; aynı dosyayı iki kez yüklemek satır eklemez.
Ayrıca kaynağın `T` değeri E+K ile karşılaştırılır; tutmazsa satır
YAZILMAZ ve tutarsızlık raporlanır.

İDEMPOTENT
----------
Her yazma bir doğal anahtar üzerinden upsert'tir; zenginleştirme
YALNIZCA NULL alanı doldurur. İkinci çalıştırma sıfır değişiklik yapar.

KULLANIM
--------
    python import_yok_registry.py                  # varsayılan part2 klasörü
    python import_yok_registry.py --dry-run
    python import_yok_registry.py --dir <yol> --yil "dosya.xls=2025-2026"
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    DataSourceConflict,
    Department,
    Faculty,
    UniversityProfile,
    UniversityStudentHeadcount,
)
from app.models.university_headcount import HOME_UNIVERSITY  # noqa: E402
from app.services.unit_types import (  # noqa: E402
    ACADEMIC_UNIT_TYPES,
    classify_unit,
)

VARSAYILAN_DIZIN = BACKEND_DIR.parent / "data" / "ekdata" / "part2"

KAYNAK_KUMESI = "yok_registry_part2"

# ---------------------------------------------------------------------------
# YIL EŞLEMESİ — kullanıcı tarafından onaylanmıştır
# ---------------------------------------------------------------------------
#: Dosya adı → akademik yıl. Kaynak dosyada yıl bilgisi BULUNMADIĞI için
#: bu eşleme dışarıdan gelir. Burada olmayan bir "Öğrenci Sayıları"
#: dosyası aktarılmaz; sessizce bir yıl varsaymak, dört yıllık trendi
#: sessizce yanlış hizalardı.
YIL_ESLEMESI: Dict[str, str] = {
    "Öğrenci Sayıları.xls": "2025-2026",
    "Öğrenci Sayıları (1).xls": "2024-2025",
    "Öğrenci Sayıları (2).xls": "2023-2024",
    "Öğrenci Sayıları (3).xls": "2022-2023",
    # "(4)" bilinçli olarak YOK: içeriği (3) ile bayt bayt aynıdır.
    # İçerik özeti zaten yakalar; eşlemede de bulunmaması ikinci güvencedir.
}

# ---------------------------------------------------------------------------
# AD TAKMA ADLARI (alias)
# ---------------------------------------------------------------------------
#: YÖK kayıt defterindeki resmî ad → bizdeki MEVCUT kayıt.
#:
#: Bu bir "adlar benziyor" tahmini DEĞİLDİR; her satır elle doğrulanmış
#: bir kimlik beyanıdır ve yeniden adlandırma/üst değiştirme YAPMAZ.
#: Amaç tek şey: kayıt defterindeki satırın YENİ bir bölüm sanılıp
#: raporda "eşleşmedi" diye görünmesini önlemek.
#:
#: `Bilişim Sistemleri Mühendisliği` bizde part-1 müfredat aktarımından
#: geldi (id=27, MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ). YÖK aynı bölümü
#: "BİLİŞİM SİSTEMLERİ MÜHENDİSLİĞİ BÖLÜMÜ" olarak yazıyor. Aynı bölüm.
BOLUM_TAKMA_ADLARI: Dict[Tuple[str, str], str] = {
    # (birim grubu, kayıt defterindeki ad) -> bizdeki ad
    ("MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ",
     "BİLİŞİM SİSTEMLERİ MÜHENDİSLİĞİ BÖLÜMÜ"):
        "Bilişim Sistemleri Mühendisliği",
}

_TR = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def kat(metin: Optional[str]) -> str:
    """Türkçe duyarlı katlama. Yalnızca EŞLEŞTİRME için kullanılır.

    Katlanmış ad hiçbir yere YAZILMAZ; veritabanındaki adlar olduğu gibi
    kalır. `"İ".lower()` i + birleşen nokta ürettiği için önce harf
    çevirisi yapılır.
    """
    if not metin:
        return ""
    d = unicodedata.normalize("NFKD", str(metin).translate(_TR))
    return " ".join(
        "".join(c for c in d if not unicodedata.combining(c)).upper().split()
    )


# ---------------------------------------------------------------------------
# Okuma
# ---------------------------------------------------------------------------


def _xls_oku(yol: Path) -> List[List[str]]:
    """Eski BIFF `.xls` dosyasını satır listesine çevirir."""
    import xlrd  # yerel: yalnızca bu betik gerektirir

    kitap = xlrd.open_workbook(str(yol), formatting_info=False)
    sayfa = kitap.sheet_by_index(0)
    satirlar = []
    for r in range(sayfa.nrows):
        satirlar.append([
            str(sayfa.cell_value(r, c)).strip() for c in range(sayfa.ncols)
        ])
    return satirlar


def _icerik_izi(satirlar: List[List[str]]) -> str:
    ham = "".join("".join(s) for s in satirlar)
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()


def _tarih(metin: str) -> Optional[date]:
    """"17.04.2020" → date. Ayrıştırılamıyorsa None — uydurulmaz."""
    metin = (metin or "").strip()
    for kalip in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(metin, kalip).date()
        except ValueError:
            continue
    return None


def _sayi(metin: str) -> Optional[int]:
    """Hücreyi tam sayıya çevirir. Boş hücre 0 DEĞİL, None'dır."""
    metin = (metin or "").strip()
    if not metin:
        return None
    try:
        return int(float(metin.replace(".", "").replace(",", ".")))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Öğrenci sayıları: sütun düzeni
# ---------------------------------------------------------------------------
#: Kaynakta sütunlar: 1=Üniversite 2=Tür 3=İl 4=Öğrenim Türü, sonra her
#: düzey için (E, K, T) üçlüsü, en sonda Genel Toplam (E, K, T).
#: T sütunları OKUNMAZ; yalnızca doğrulama için bakılır.
DUZEY_SUTUNLARI: Tuple[Tuple[str, int, int, int], ...] = (
    # (düzey, E, K, T)
    ("ONLISANS", 5, 6, 7),
    ("LISANS", 8, 9, 10),
    ("YUKSEKLISANS", 11, 12, 13),
    ("DOKTORA", 14, 15, 16),
)
GENEL_TOPLAM_SUTUNLARI = (17, 18, 19)

#: Öğrenim türü yazım varyantları → kapalı liste değeri.
#: Dosya (2) Türkçe harfsiz yazıyor ("BIRINCI Ö."); ham metni anahtar
#: yapmak tek kategoriyi ikiye bölerdi.
OGRENIM_TURLERI: Dict[str, str] = {
    "BIRINCI O.": "BİRİNCİ",
    "IKINCI O.": "İKİNCİ",
    "UZAKTAN O.": "UZAKTAN",
    "ACIK O.": "AÇIK",
}
TOPLAM_ETIKETI = "TOPLAM"


def ogrenim_turu(ham: str) -> Optional[str]:
    """Ham etiketi kapalı listeye indirger. `TOPLAM` → None (atlanır)."""
    k = kat(ham)
    if not k or k == TOPLAM_ETIKETI:
        return None
    return OGRENIM_TURLERI.get(k)


# ===========================================================================
# Aktarım
# ===========================================================================


class YokKayitDefteriAktarimi:
    """Üç dosya ailesini aktarır. Yazma yalnızca upsert ve NULL doldurma."""

    def __init__(self, db, dry_run: bool = False) -> None:
        self.db = db
        self.dry_run = dry_run

        self.birim_zengin: List[str] = []
        self.birim_zaten: List[str] = []
        self.birim_eslesmedi: List[str] = []
        self.bolum_zengin: List[str] = []
        self.bolum_zaten: List[str] = []
        self.bolum_eslesmedi: List[str] = []
        self.takma_ad_cozuldu: List[str] = []
        self.yapi_yazildi = 0
        self.sayim_yazildi = 0
        self.sayim_guncellendi = 0
        self.sayim_degismedi = 0
        self.yil_ozeti: Dict[str, int] = {}
        self.cakismalar: List[dict] = []
        self.notlar: List[str] = []
        self.tutarsizliklar: List[str] = []

    # -- yardımcılar --------------------------------------------------

    def _cakisma(self, tablo: str, kayit_id: int, alan: str, etiket: str,
                 mevcut, gelen, kaynak: str, not_: str) -> None:
        self.cakismalar.append({
            "table_name": tablo, "record_id": kayit_id, "field_name": alan,
            "record_label": etiket,
            "existing_value": None if mevcut is None else str(mevcut),
            "existing_source": "mevcut kayıt",
            "incoming_value": None if gelen is None else str(gelen),
            "incoming_source": kaynak, "note": not_,
        })

    def _doldur(self, nesne, alan: str, deger, tablo: str, etiket: str,
                kaynak: str) -> bool:
        """SADECE NULL alanı doldurur. Dolu alanı ASLA ezmez.

        Dolu alan farklı bir değer taşıyorsa bu bir çakışmadır: mevcut
        değer korunur ve kayıt altına alınır.
        """
        mevcut = getattr(nesne, alan)
        if deger is None:
            return False
        if mevcut is None:
            if not self.dry_run:
                setattr(nesne, alan, deger)
            return True
        if mevcut != deger:
            self._cakisma(tablo, nesne.id, alan, etiket, mevcut, deger, kaynak,
                          "Mevcut değer korundu; YÖK kayıt defteri farklı "
                          "değer bildirdi.")
        return False

    # -- 1) birimler ---------------------------------------------------

    def birimleri_zenginlestir(self, satirlar: List[List[str]],
                               dosya: str) -> None:
        """ABÜ birimlerini eşleştirir ve NULL alanları doldurur.

        DİĞER üniversitelerin birimleri okunmaz: dış kurumların iç
        yapısını modellemiyoruz (bkz. `benchmark_institution.py`).
        """
        fakulteler = list(self.db.execute(select(Faculty)).scalars())
        dizin = {kat(f.name): f for f in fakulteler}

        for satir in satirlar[1:]:
            if len(satir) < 6 or kat(satir[0]) != kat(HOME_UNIVERSITY):
                continue
            ad, tarih_ham, durum = satir[1], satir[2], satir[5]
            hedef = dizin.get(kat(ad))
            if hedef is None:
                # Sınıflandırmayı RAPOR için hesaplarız; kayıt AÇILMAZ.
                tur = classify_unit(ad)
                self.birim_eslesmedi.append(
                    f"{ad} (açılış {tarih_ham or '—'}, durum {durum}, "
                    f"tür tahmini {tur}"
                    f"{', AKADEMİK DEĞİL' if tur not in ACADEMIC_UNIT_TYPES else ''})"
                )
                continue

            degisti = False
            degisti |= self._doldur(hedef, "established_on", _tarih(tarih_ham),
                                    "faculties", hedef.name, dosya)
            degisti |= self._doldur(hedef, "yok_status", durum or None,
                                    "faculties", hedef.name, dosya)
            (self.birim_zengin if degisti else self.birim_zaten).append(hedef.name)

    # -- 2) bölümler ---------------------------------------------------

    def bolumleri_zenginlestir(self, satirlar: List[List[str]],
                               dosya: str) -> None:
        """ABÜ bölümlerini eşleştirir; ÜST BİRİM de doğrulanır.

        Ad eşleşse bile üst birim tutmuyorsa EŞLEŞME SAYILMAZ. Kayıt
        defterindeki MYO "HUKUK BÖLÜMÜ" ile bizdeki Hukuk Fakültesi
        altındaki "Hukuk" farklı varlıklardır; adına bakıp birleştirmek
        gerçek bir veri hatası olurdu.
        """
        bolumler = list(self.db.execute(select(Department)).scalars())
        fak = {f.id: f for f in self.db.execute(select(Faculty)).scalars()}
        dizin: Dict[str, List[Department]] = defaultdict(list)
        for b in bolumler:
            dizin[kat(b.name)].append(b)

        for satir in satirlar[1:]:
            if len(satir) < 7 or kat(satir[0]) != kat(HOME_UNIVERSITY):
                continue
            grup, ad, tarih_ham, durum = satir[1], satir[2], satir[3], satir[6]

            # Takma ad: kayıt defterindeki resmî ad → bizdeki mevcut kayıt.
            aranan = ad
            takma = BOLUM_TAKMA_ADLARI.get((grup, ad))
            if takma:
                aranan = takma

            adaylar = dizin.get(kat(aranan), [])
            # ÜST BİRİM DOĞRULAMASI — kimlik üzerinden.
            hedef = next(
                (b for b in adaylar
                 if b.faculty_id in fak and kat(fak[b.faculty_id].name) == kat(grup)),
                None,
            )

            if hedef is None:
                if adaylar:
                    # Ad var ama başka bir üstün altında: bu AYRI bir bölüm.
                    baska = ", ".join(
                        f"{b.name} → {fak[b.faculty_id].name}" for b in adaylar)
                    self.bolum_eslesmedi.append(
                        f"{ad} ({grup}) — aynı adlı kayıt BAŞKA üst birimde: "
                        f"{baska}; ayrı varlık sayıldı"
                    )
                    self._cakisma(
                        "departments", adaylar[0].id, "faculty_id", ad,
                        fak[adaylar[0].faculty_id].name, grup, dosya,
                        "Aynı adlı bölüm farklı üst birimde; birleştirilmedi, "
                        "yeni kayıt da açılmadı.")
                else:
                    self.bolum_eslesmedi.append(
                        f"{ad} ({grup}, açılış {tarih_ham or '—'})")
                continue

            if takma:
                self.takma_ad_cozuldu.append(
                    f"“{ad}” → id={hedef.id} “{hedef.name}” "
                    f"({fak[hedef.faculty_id].name})"
                )

            degisti = False
            degisti |= self._doldur(hedef, "established_on", _tarih(tarih_ham),
                                    "departments", hedef.name, dosya)
            degisti |= self._doldur(hedef, "yok_status", durum or None,
                                    "departments", hedef.name, dosya)
            (self.bolum_zengin if degisti else self.bolum_zaten).append(hedef.name)

    # -- 2b) kurum yapısı: HER üniversite için birim/bölüm sayısı ------

    def yapi_sayilarini_aktar(self, birim_satirlari, bolum_satirlari,
                              dosya: str) -> None:
        """Ankara'daki her kurumun birim ve bölüm SAYISI.

        Rakip analizi bütün kurumlarda aynı göstergeyi ister; kayıt
        defteri 23 kurumu da kapsadığı için bu sayılar
        karşılaştırılabilirdir.

        Yalnızca SAYI saklanır. Dış kurumların iç hiyerarşisi
        modellenmez: `faculties`/`departments` hâlâ yalnızca kendi
        kurumumuzu tutar ve kapsam çözümlemesi onlardan yürür.
        """
        birim = defaultdict(int)
        for satir in birim_satirlari[1:]:
            if len(satir) >= 2 and satir[0].strip():
                birim[satir[0].strip()] += 1
        bolum = defaultdict(int)
        for satir in bolum_satirlari[1:]:
            if len(satir) >= 3 and satir[0].strip():
                bolum[satir[0].strip()] += 1

        for ad in set(birim) | set(bolum):
            mevcut = self.db.execute(
                select(UniversityProfile).where(
                    UniversityProfile.university_name == ad)
            ).scalar_one_or_none()
            if mevcut is None:
                if self.dry_run:
                    self.yapi_yazildi += 1
                    continue
                mevcut = UniversityProfile(university_name=ad)
                self.db.add(mevcut)
            if not self.dry_run:
                mevcut.academic_unit_count = birim.get(ad)
                mevcut.department_count = bolum.get(ad)
                mevcut.structure_source = dosya
            self.yapi_yazildi += 1
        if not self.dry_run:
            self.db.flush()

    # -- 3) öğrenci sayıları -------------------------------------------

    def sayimlari_aktar(self, satirlar: List[List[str]], dosya: str,
                        akademik_yil: str) -> None:
        """Ayrıntı satırlarını E/K hücreleri olarak yazar.

        TOPLAM satırları ve T sütunları YAZILMAZ; T yalnızca E+K
        doğrulaması için okunur.
        """
        yil_toplami = 0
        yazilan_uni = set()

        for satir in satirlar:
            if len(satir) < 20:
                continue
            uni, tur, il, ogr_ham = satir[1], satir[2], satir[3], satir[4]
            if not uni or kat(uni) == TOPLAM_ETIKETI:
                continue          # dosya sonundaki genel toplam satırı

            mod = ogrenim_turu(ogr_ham)
            if mod is None:
                continue          # üniversite TOPLAM satırı veya boş satır

            # --- E+K = T doğrulaması ---
            for duzey, ce, ck, ct in DUZEY_SUTUNLARI:
                e, k, t = _sayi(satir[ce]), _sayi(satir[ck]), _sayi(satir[ct])
                if e is None or k is None:
                    continue
                if t is not None and e + k != t:
                    self.tutarsizliklar.append(
                        f"{dosya} · {uni} · {ogr_ham} · {duzey}: "
                        f"E({e})+K({k}) = {e + k} ≠ T({t}); satır yazılmadı")
                    continue
                for cinsiyet, deger in (("E", e), ("K", k)):
                    self._sayim_yaz(uni, tur, il, akademik_yil, mod, duzey,
                                    cinsiyet, deger, dosya)
                if kat(uni) == kat(HOME_UNIVERSITY):
                    yil_toplami += e + k
            yazilan_uni.add(uni)

        self.yil_ozeti[akademik_yil] = yil_toplami
        self.notlar.append(
            f"{dosya}: {akademik_yil} · {len(yazilan_uni)} üniversite · "
            f"ABÜ toplamı {yil_toplami}")

    def _sayim_yaz(self, uni: str, tur: str, il: str, yil: str, mod: str,
                   duzey: str, cinsiyet: str, deger: Optional[int],
                   dosya: str) -> None:
        if deger is None:
            return
        var = self.db.execute(
            select(UniversityStudentHeadcount).where(
                UniversityStudentHeadcount.university_name == uni,
                UniversityStudentHeadcount.academic_year == yil,
                UniversityStudentHeadcount.education_mode == mod,
                UniversityStudentHeadcount.degree_level == duzey,
                UniversityStudentHeadcount.gender == cinsiyet,
            )
        ).scalar_one_or_none()

        if var is not None:
            if var.student_count == deger:
                self.sayim_degismedi += 1
                return
            # Aynı doğal anahtar için FARKLI sayı: kaynak güncellenmiş
            # olabilir. Yeni değer yazılır ama fark kayıt altına alınır.
            self._cakisma(
                "university_student_headcounts", var.id, "student_count",
                f"{uni} · {yil} · {mod} · {duzey} · {cinsiyet}",
                var.student_count, deger, dosya,
                "Aynı anahtar için farklı sayı geldi; yeni değer yazıldı.")
            if not self.dry_run:
                var.student_count = deger
                var.source_file = dosya
            self.sayim_guncellendi += 1
            return

        if not self.dry_run:
            self.db.add(UniversityStudentHeadcount(
                university_name=uni, university_type=tur or None,
                city=il or None, academic_year=yil, education_mode=mod,
                degree_level=duzey, gender=cinsiyet, student_count=deger,
                source_dataset=KAYNAK_KUMESI, source_file=dosya,
            ))
        self.sayim_yazildi += 1

    # -- çakışmaları kalıcılaştır --------------------------------------

    def cakismalari_yaz(self) -> None:
        if self.dry_run:
            return
        for c in self.cakismalar:
            var = self.db.execute(
                select(DataSourceConflict).where(
                    DataSourceConflict.table_name == c["table_name"],
                    DataSourceConflict.record_id == c["record_id"],
                    DataSourceConflict.field_name == c["field_name"],
                    DataSourceConflict.incoming_source == c["incoming_source"],
                )
            ).scalar_one_or_none()
            if var is not None:
                var.existing_value = c["existing_value"]
                var.incoming_value = c["incoming_value"]
                continue
            self.db.add(DataSourceConflict(resolution="kept_existing", **c))


# ===========================================================================
# Giriş noktası
# ===========================================================================


def _yil_secenegi(deger: str) -> Tuple[str, str]:
    if "=" not in deger:
        raise argparse.ArgumentTypeError('Biçim: "dosya.xls=2025-2026"')
    ad, yil = deger.split("=", 1)
    return ad.strip(), yil.strip()


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=VARSAYILAN_DIZIN)
    ap.add_argument("--dry-run", action="store_true",
                    help="Hiçbir şey yazmadan ne olacağını gösterir.")
    ap.add_argument("--yil", type=_yil_secenegi, action="append", default=[],
                    metavar='"dosya.xls=2025-2026"',
                    help="Öğrenci sayısı dosyasının akademik yılı.")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if not args.dir.exists():
        print(f"BULUNAMADI: {args.dir}", file=sys.stderr)
        return 2

    yil_eslemesi = dict(YIL_ESLEMESI)
    yil_eslemesi.update(dict(args.yil))

    print("=" * 68)
    print("YÖK KAYIT DEFTERİ + ÖĞRENCİ SAYILARI AKTARIMI")
    print("=" * 68)
    print(f"Kaynak klasör : {args.dir}")
    if args.dry_run:
        print("MOD           : DRY-RUN (yazma yok)")

    init_db()
    db = SessionLocal()
    aktarim = YokKayitDefteriAktarimi(db, dry_run=args.dry_run)

    dosyalar = sorted(p for p in args.dir.rglob("*.xls") if p.is_file())
    print(f"\n[1/4] {len(dosyalar)} dosya bulundu")

    gorulen: Dict[str, str] = {}
    sayim_dosyalari: List[Tuple[Path, List[List[str]], str]] = []
    birim_dosyasi = bolum_dosyasi = None

    try:
        for yol in dosyalar:
            ad = yol.name
            satirlar = _xls_oku(yol)
            izi = _icerik_izi(satirlar)
            if izi in gorulen:
                aktarim.notlar.append(
                    f"{ad}: içeriği {gorulen[izi]} ile BİREBİR AYNI; "
                    "ikinci kez aktarılmadı.")
                print(f"      IKIZ      {ad}  — {gorulen[izi]} ile aynı")
                continue
            gorulen[izi] = ad

            basliklar = [kat(h) for h in (satirlar[0] if satirlar else [])]
            if "BIRIM ADI" in basliklar and "ACILIS TARIHI" in basliklar:
                birim_dosyasi = (yol, satirlar)
                print(f"      BIRIM     {ad}  ({len(satirlar) - 1} satır)")
            elif "BOLUM ADI" in basliklar:
                bolum_dosyasi = (yol, satirlar)
                print(f"      BOLUM     {ad}  ({len(satirlar) - 1} satır)")
            elif ad.startswith("Öğrenci Sayıları"):
                yil = yil_eslemesi.get(ad)
                if not yil:
                    aktarim.notlar.append(
                        f"{ad}: akademik yıl BİLİNMİYOR (eşlemede yok); "
                        "aktarılmadı. --yil ile bildirin.")
                    print(f"      ATLANDI   {ad}  — yıl bildirilmemiş")
                    continue
                sayim_dosyalari.append((yol, satirlar, yil))
                print(f"      SAYIM     {ad}  → {yil}")
            else:
                aktarim.notlar.append(f"{ad}: tanınmayan şema; atlandı.")
                print(f"      ATLANDI   {ad}  — tanınmayan şema")

        print("\n[2/4] Birim ve bölüm zenginleştirmesi (yalnızca NULL alanlar)")
        if birim_dosyasi:
            aktarim.birimleri_zenginlestir(birim_dosyasi[1], birim_dosyasi[0].name)
        if bolum_dosyasi:
            aktarim.bolumleri_zenginlestir(bolum_dosyasi[1], bolum_dosyasi[0].name)
        if birim_dosyasi and bolum_dosyasi:
            # Rakip analizi için HER kurumun birim/bölüm sayısı.
            aktarim.yapi_sayilarini_aktar(
                birim_dosyasi[1], bolum_dosyasi[1], bolum_dosyasi[0].name)

        print("[3/4] Öğrenci sayıları")
        for yol, satirlar, yil in sorted(sayim_dosyalari, key=lambda t: t[2]):
            aktarim.sayimlari_aktar(satirlar, yol.name, yil)

        aktarim.cakismalari_yaz()

        print("[4/4] Kaydediliyor…")
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        _rapor(aktarim)
        db.close()
    return 0


def _rapor(a: "YokKayitDefteriAktarimi") -> None:
    def blok(baslik: str, satirlar: List[str], sinir: int = 40) -> None:
        print("\n" + "-" * 68)
        print(baslik)
        print("-" * 68)
        if not satirlar:
            print("  (yok)")
            return
        for s in satirlar[:sinir]:
            print(f"  · {s}")
        if len(satirlar) > sinir:
            print(f"  … ve {len(satirlar) - sinir} satır daha")

    print("\n" + "=" * 68)
    print("ÖZET")
    print("=" * 68)
    print(f"  Birim  : {len(a.birim_zengin)} zenginleştirildi, "
          f"{len(a.birim_zaten)} zaten dolu, "
          f"{len(a.birim_eslesmedi)} eşleşmedi")
    print(f"  Bölüm  : {len(a.bolum_zengin)} zenginleştirildi, "
          f"{len(a.bolum_zaten)} zaten dolu, "
          f"{len(a.bolum_eslesmedi)} eşleşmedi")
    print(f"  Yapı   : {a.yapi_yazildi} kurum profili (birim/bölüm sayısı)")
    print(f"  Sayım  : {a.sayim_yazildi} eklendi, "
          f"{a.sayim_guncellendi} güncellendi, "
          f"{a.sayim_degismedi} değişmedi")
    if a.yil_ozeti:
        print("\n  ABÜ yıllık toplamları (E+K, ayrıntı satırlarından):")
        for yil in sorted(a.yil_ozeti):
            print(f"    {yil}: {a.yil_ozeti[yil]:,}".replace(",", "."))

    blok("TAKMA AD ÇÖZÜMLERİ", a.takma_ad_cozuldu)
    blok("EŞLEŞMEYEN BİRİMLER (kayıt AÇILMADI)", a.birim_eslesmedi)
    blok("EŞLEŞMEYEN BÖLÜMLER (kayıt AÇILMADI)", a.bolum_eslesmedi)
    blok("ÇAKIŞMALAR", [
        f"{c['table_name']}.{c['field_name']} #{c['record_id']} "
        f"({c['record_label']}): mevcut={c['existing_value']!r} "
        f"gelen={c['incoming_value']!r}" for c in a.cakismalar])
    blok("E+K ≠ T TUTARSIZLIKLARI", a.tutarsizliklar)
    blok("NOTLAR", a.notlar)
    print("\nBetik idempotenttir; tekrar çalıştırmak kayıt eklemez.")


if __name__ == "__main__":
    raise SystemExit(main())
