"""YÖK Akademik toplayıcı verisini üretim veritabanına aktarır.

===========================================================================
NE YAPAR
--------
`yok-akademik-ankara-crawler/data/yok_akademik.db` içindeki GERÇEK veriyi
mevcut modellere yazar. Demo seed'in yerini alır.

    universities  →  benchmark_institutions   (Ankara'daki 22 rakip/karşılaştırma kurumu)
    academics     →  faculties / departments / academic_programs / academic_staff
    publications  →  academic_staff.publication_count
    courses       →  academic_staff.teaching_load_hours
    theses        →  academic_staff.advising_count

HEDEF KURUM
-----------
Sistem Ankara Bilim Üniversitesi'nin karar destek sistemidir. Bu yüzden
YALNIZCA ABÜ'nün akademik yapısı `faculties/departments/programs/staff`
tablolarına yazılır; diğer 22 üniversite karşılaştırma kurumu olur.

VERİ UYDURULMAZ
---------------
Toplayıcıda karşılığı olmayan hiçbir alan doldurulmaz:

  * öğrenci, kontenjan, doluluk, mezuniyet, terk   → tablo BOŞ kalır
  * mali dönem, gelir, gider, maaş                 → tablo BOŞ kalır
  * fiziksel mekân, derslik, laboratuvar           → tablo BOŞ kalır
  * KPI ölçümleri, akademik başarı, sanayi katkısı → tablo BOŞ kalır
  * atıf sayısı, patent, proje                     → toplayıcı tabloları BOŞ

Bu alanları 0 veya örnek değerle doldurmak, "veri yok" ile "değer sıfır"ı
karıştırmak olurdu. Arayüz bu boşlukları "veri yok" olarak gösterir.

KAYNAK İZLENEBİLİRLİĞİ
----------------------
Her kayıtta toplayıcının `source_url`, `first_seen_at` ve `last_seen_at`
bilgisi korunur (açıklama alanlarında ve `notes` içinde).

ÇALIŞTIRMA
----------
    python import_yok_collector.py                      # varsayılan yol
    python import_yok_collector.py --db <yok_akademik.db yolu>
    python import_yok_collector.py --purge              # önce mevcut veriyi sil
    python import_yok_collector.py --university "ANKARA BİLİM ÜNİVERSİTESİ"

Betik IDEMPOTENTTİR: aynı veriyle ikinci kez çalıştırılırsa yeni kayıt
eklenmez, mevcutlar güncellenir.
===========================================================================
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import SessionLocal, init_db  # noqa: E402
from app.models import (  # noqa: E402
    AcademicProgram,
    AcademicStaff,
    AcademicStaffCourse,
    BenchmarkInstitution,
    Department,
    Faculty,
    UniversityProfile,
)
from app.services.unit_types import ADMINISTRATIVE, classify_unit  # noqa: E402

# Hedef kurum — sistemin sahibi.
HEDEF_KURUM = "ANKARA BİLİM ÜNİVERSİTESİ"

# Toplayıcı veritabanının varsayılan konumu (depo köküne göre).
VARSAYILAN_DB = (
    BACKEND_DIR.parent
    / "data" / "yok-akademik" / "yok_akademik.db"
)

# Personel kayıtlarının hangi akademik yıla ait sayılacağı. Toplayıcı akademik
# yıl bilgisi taşımıyor; en güncel ders döneminden türetilir, bulunamazsa
# `VARSAYILAN_YIL` kullanılır ve raporda belirtilir.
VARSAYILAN_YIL = "2025-2026"


# ---------------------------------------------------------------------------
# Ad normalizasyonu
# ---------------------------------------------------------------------------

_TR_HARF = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def sadelestir(metin: str) -> str:
    """Türkçe harfleri sadeleştirir; kod üretimi ve eşleştirme için."""
    if not metin:
        return ""
    d = unicodedata.normalize("NFKD", metin.translate(_TR_HARF))
    return "".join(ch for ch in d if not unicodedata.combining(ch)).upper()


# Kod üretiminde atılacak jenerik sözcükler — kod anlamlı kalsın diye.
_ATILACAK = {
    "FAKULTESI", "FAKULTESI.", "BOLUMU", "BOLUM", "ANABILIM", "DALI",
    "PROGRAMI", "PR.", "PR", "YUKSEKOKULU", "VE", "ILE",
}


def kod_uret(ad: str, uzunluk: int = 12) -> str:
    """Ad'dan okunabilir, tekrarlanabilir bir kod üretir.

    "BİLGİSAYAR MÜHENDİSLİĞİ BÖLÜMÜ" → "BILMUH"
    Kod, ilgili tabloda tekil olmalı; tekilliği çağıran `_tekil_kod` sağlar.
    """
    sozcukler = [w for w in re.split(r"[^A-Za-z0-9]+", sadelestir(ad)) if w]
    sozcukler = [w for w in sozcukler if w not in _ATILACAK] or sozcukler
    if not sozcukler:
        return "KOD"
    if len(sozcukler) == 1:
        return sozcukler[0][:uzunluk]
    parca = "".join(w[:3] for w in sozcukler[:3])
    return parca[:uzunluk] or sozcukler[0][:uzunluk]


def _tekil_kod(taban: str, kullanilan: set) -> str:
    kod = taban
    i = 2
    while kod in kullanilan:
        kod = f"{taban[:10]}{i}"
        i += 1
    kullanilan.add(kod)
    return kod


def ad_ayir(tam_ad: str) -> Tuple[str, str]:
    """YÖK "AD SOYAD" biçimini ad/soyad olarak ayırır.

    Türkçe adlarda soyad SONDADIR ve çoğunlukla tek sözcüktür; birden çok
    ad olabilir. Ayrım yapılamazsa soyad boş bırakılmaz — tam ad soyada
    yazılır ki kimse kaybolmasın.
    """
    parcalar = [p for p in (tam_ad or "").split() if p]
    if not parcalar:
        return ("", "")
    if len(parcalar) == 1:
        return (parcalar[0][:100], parcalar[0][:100])
    return (" ".join(parcalar[:-1])[:100], parcalar[-1][:100])


def derece_seviyesi(program_adi: str) -> str:
    """Program adından derece seviyesini çıkarır. Belirsizse "Bilinmiyor"."""
    m = sadelestir(program_adi)
    if "DOKTORA" in m or "PHD" in m:
        return "Doktora"
    if "YUKSEK LISANS" in m or "TEZLI" in m or "TEZSIZ" in m:
        return "Yüksek Lisans"
    if "ANABILIM DALI" in m:
        # Anabilim dalı lisansüstü yapıdır ama derece belirtmez.
        return "Bilinmiyor"
    if "ONLISANS" in m or "MESLEK" in m:
        return "Ön Lisans"
    if "PR." in program_adi or "PR" in m.split():
        return "Lisans"
    return "Bilinmiyor"


# ---------------------------------------------------------------------------
# Toplayıcıdan okuma
# ---------------------------------------------------------------------------


def toplayici_ac(yol: Path) -> sqlite3.Connection:
    if not yol.exists():
        raise SystemExit(f"Toplayıcı veritabanı bulunamadı: {yol}")
    # Salt okunur aç: kaynak dosya asla değiştirilmez.
    conn = sqlite3.connect(f"file:{yol}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def ders_saati(data_json: str) -> Tuple[Optional[str], int]:
    """Ders kaydından (dönem, haftalık saat) çıkarır."""
    try:
        d = json.loads(data_json or "{}")
    except json.JSONDecodeError:
        return (None, 0)
    donem = d.get("Dönem") or d.get("donem")
    saat = d.get("Saat") or d.get("saat") or "0"
    try:
        return (donem, int(re.sub(r"[^0-9]", "", str(saat)) or 0))
    except ValueError:
        return (donem, 0)


def akademik_yil_normalize(donem: Optional[str]) -> Optional[str]:
    """"2024-2025" biçimini doğrular; başka biçimi reddeder."""
    if not donem:
        return None
    m = re.match(r"^(\d{4})\s*[-/]\s*(\d{4})$", str(donem).strip())
    return f"{m.group(1)}-{m.group(2)}" if m else None


# ---------------------------------------------------------------------------
# Aktarım
# ---------------------------------------------------------------------------


class Aktarim:
    def __init__(self, kaynak: sqlite3.Connection, oturum: Session,
                 hedef_kurum: str):
        self.k = kaynak
        self.db = oturum
        self.hedef = hedef_kurum
        self.sayac: Counter = Counter()
        self.bosluklar: List[str] = []

    # --- 1. karşılaştırma kurumları ---
    def kurumlari_aktar(self) -> None:
        satirlar = self.k.execute(
            "SELECT name, city, type, source_url, academic_count_discovered,"
            "       first_seen_at, last_seen_at"
            " FROM universities ORDER BY name"
        ).fetchall()

        for r in satirlar:
            ad = (r["name"] or "").strip()
            if not ad or sadelestir(ad) == sadelestir(self.hedef):
                continue  # kendi kurumumuz karşılaştırma kurumu değildir

            mevcut = self.db.execute(
                select(BenchmarkInstitution).where(BenchmarkInstitution.name == ad)
            ).scalar_one_or_none()

            # Kaynak izlenebilirliği notta korunur.
            not_metni = (
                f"Kaynak: YÖK Akademik toplayıcısı · {r['source_url'] or '—'} · "
                f"ilk görülme {r['first_seen_at'] or '—'} · "
                f"son görülme {r['last_seen_at'] or '—'} · "
                f"keşfedilen akademisyen {r['academic_count_discovered'] or 0}"
            )
            # VAKIF üniversiteleri doğrudan rakip; DEVLET karşılaştırma.
            tur = "competitor" if (r["type"] or "").upper() == "VAKIF" else "similar"

            if mevcut:
                mevcut.city = r["city"] or mevcut.city
                mevcut.country = "Türkiye"
                mevcut.institution_type = tur
                mevcut.is_competitor = tur == "competitor"
                mevcut.notes = not_metni
                self.sayac["kurum_guncellendi"] += 1
            else:
                self.db.add(BenchmarkInstitution(
                    name=ad, country="Türkiye", city=r["city"] or None,
                    institution_type=tur, is_competitor=tur == "competitor",
                    notes=not_metni, is_active=True,
                ))
                self.sayac["kurum_eklendi"] += 1

        self.db.flush()

    # --- 1b. karşılaştırma profili: kurum başına kadro büyüklüğü ---
    def kurum_profillerini_aktar(self) -> None:
        """Ankara'daki HER kurum için akademisyen ve yayın sayısı.

        Rakip analizi bütün kurumlarda AYNI göstergeyi ister. Toplayıcı
        23 kurumun tamamında keşif taramasını tamamladığı için kadro
        sayısı karşılaştırılabilirdir.

        Yayın sayısı KISMİDİR: profil ayrıntısı yalnızca birkaç kurum
        için indirilmiştir. Sayıyı yine de saklıyoruz — izlenebilirlik
        için — ama karşılaştırma servisi kapsama kuralı gereği bu
        göstergeyi kapatacaktır. Eksik kurumlara 0 YAZILMAZ; NULL kalır,
        çünkü "yayını yok" ile "yayını taranmadı" farklı şeylerdir.
        """
        kadro = {
            (r["university_name"] or "").strip(): r["n"]
            for r in self.k.execute(
                "SELECT university_name, COUNT(*) AS n FROM academics"
                " WHERE university_name IS NOT NULL AND university_name <> ''"
                " GROUP BY university_name"
            )
        }
        yayin = {
            (r["university_name"] or "").strip(): (r["yayin"], r["kisi"])
            for r in self.k.execute(
                "SELECT a.university_name AS university_name,"
                "       COUNT(p.id) AS yayin,"
                "       COUNT(DISTINCT p.author_id) AS kisi"
                "  FROM academics a"
                "  JOIN publications p ON p.author_id = a.author_id"
                " GROUP BY a.university_name"
            )
        }
        turler = {
            (r["name"] or "").strip(): (r["type"], r["city"])
            for r in self.k.execute("SELECT name, type, city FROM universities")
        }

        for ad, adet in kadro.items():
            if not ad:
                continue
            tur, sehir = turler.get(ad, (None, None))
            y, kisi = yayin.get(ad, (None, None))
            mevcut = self.db.execute(
                select(UniversityProfile).where(
                    UniversityProfile.university_name == ad)
            ).scalar_one_or_none()
            if mevcut is None:
                mevcut = UniversityProfile(university_name=ad)
                self.db.add(mevcut)
                self.sayac["kurum_profili_eklendi"] += 1
            else:
                self.sayac["kurum_profili_guncellendi"] += 1
            mevcut.university_type = tur or mevcut.university_type
            mevcut.city = sehir or mevcut.city
            mevcut.academic_staff_count = adet
            mevcut.total_publications = y
            mevcut.academics_with_publications = kisi
            mevcut.staff_source = "yok_akademik_collector"

        self.db.flush()

    # --- 2. akademik yapı ---
    def yapi_ve_personel_aktar(self) -> None:
        akademisyenler = self.k.execute(
            "SELECT author_id, full_name, title, faculty, department, program,"
            "       profile_url, email, orcid, basic_field, specialty,"
            # `academics` tablosunda ilk görülme sütununun adı `discovered_at`.
            "       section_counts_json, last_scraped_at,"
            "       discovered_at AS first_seen_at, last_seen_at"
            "  FROM academics"
            " WHERE UPPER(university_name) = UPPER(?)"
            " ORDER BY full_name",
            (self.hedef,),
        ).fetchall()

        if not akademisyenler:
            raise SystemExit(
                f"Toplayıcıda '{self.hedef}' için akademisyen kaydı yok. "
                "--university ile doğru adı verin."
            )

        # --- detay sayımları (yalnızca bu kurumun yazarları için) ---
        yazarlar = [a["author_id"] for a in akademisyenler]
        yayin = self._sayim("publications", yazarlar)
        tez = self._sayim("theses", yazarlar)
        ders_yuk, son_donem = self._ders_yuku(yazarlar)

        akademik_yil = son_donem or VARSAYILAN_YIL
        if not son_donem:
            self.bosluklar.append(
                "Ders dönemi bulunamadı; personel kayıtları varsayılan akademik "
                f"yıl ({VARSAYILAN_YIL}) ile yazıldı."
            )

        fakulte_kodlari, bolum_kodlari, program_kodlari = set(), set(), set()
        fakulteler: Dict[str, Faculty] = {}
        bolumler: Dict[Tuple[str, str], Department] = {}
        programlar: Dict[Tuple[str, str], AcademicProgram] = {}
        bolumsuz = 0

        for a in akademisyenler:
            fak_ad = (a["faculty"] or "").strip()
            bol_ad = (a["department"] or "").strip()
            prog_ad = (a["program"] or "").strip()

            if not fak_ad:
                bolumsuz += 1
                continue

            # --- fakülte ---
            fak = fakulteler.get(fak_ad)
            if fak is None:
                fak = self._fakulte(fak_ad, fakulte_kodlari)
                fakulteler[fak_ad] = fak

            # --- bölüm ---
            # Bölümü olmayan kayıtlar (ör. REKTÖRLÜK) fakülte adıyla aynı adı
            # taşıyan bir "idari birim" bölümüne bağlanır: personel kaybolmasın,
            # ama uydurma bir bölüm adı da üretilmesin.
            etkin_bolum = bol_ad or fak_ad
            anahtar = (fak_ad, etkin_bolum)
            bol = bolumler.get(anahtar)
            if bol is None:
                bol = self._bolum(etkin_bolum, fak, bolum_kodlari,
                                  idari=not bol_ad)
                bolumler[anahtar] = bol

            # --- program ---
            if prog_ad:
                p_anahtar = (etkin_bolum, prog_ad)
                if p_anahtar not in programlar:
                    programlar[p_anahtar] = self._program(
                        prog_ad, bol, program_kodlari)

            # --- personel ---
            self._personel(a, bol, akademik_yil,
                           yayin.get(a["author_id"], 0),
                           tez.get(a["author_id"], 0),
                           ders_yuk.get(a["author_id"], 0))

        self.db.flush()
        # Ders satırları personel yazıldıktan SONRA aktarılır: her ders bir
        # akademisyene bağlanır ve sahipsiz satır kalmaz.
        self.dersleri_aktar(yazarlar)
        if bolumsuz:
            self.bosluklar.append(
                f"{bolumsuz} akademisyen kaydında fakülte bilgisi yok; "
                "bu kayıtlar aktarılmadı."
            )

    # --- yardımcılar ---

    def _sayim(self, tablo: str, yazarlar: List[str]) -> Dict[str, int]:
        """Bir detay tablosunda yazar başına kayıt sayısı."""
        if not yazarlar:
            return {}
        ph = ",".join("?" * len(yazarlar))
        rows = self.k.execute(
            f"SELECT author_id, COUNT(*) n FROM {tablo}"
            f" WHERE author_id IN ({ph}) GROUP BY author_id", yazarlar
        ).fetchall()
        return {r["author_id"]: r["n"] for r in rows}

    def _ders_yuku(self, yazarlar: List[str]) -> Tuple[Dict[str, int], Optional[str]]:
        """EN GÜNCEL dönemdeki haftalık ders saati toplamı.

        Bütün dönemleri toplamak, on yıllık yükü tek yıla yazmak olurdu.
        """
        if not yazarlar:
            return ({}, None)
        ph = ",".join("?" * len(yazarlar))
        rows = self.k.execute(
            f"SELECT author_id, data_json FROM courses WHERE author_id IN ({ph})",
            yazarlar
        ).fetchall()

        donem_bazli: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for r in rows:
            donem, saat = ders_saati(r["data_json"])
            yil = akademik_yil_normalize(donem)
            if not yil:
                continue
            donem_bazli[yil][r["author_id"]] += saat

        if not donem_bazli:
            return ({}, None)
        son = max(donem_bazli)
        return (dict(donem_bazli[son]), son)

    def dersleri_aktar(self, yazarlar: List[str]) -> None:
        """Akademisyenlerin verdiği dersleri YIL BAZINDA yazar.

        `teaching_load_hours` yalnızca en güncel yılın toplamıdır; ham
        satırlar burada saklanır ki "bu akademisyen hangi dersleri
        veriyor?" sorusu cevaplanabilsin. Ders KODU kaynakta yoktur ve
        müfredat dosyasıyla ad üzerinden eşleştirilmez — aynı adın iki
        farklı ders olması mümkündür.
        """
        if not yazarlar:
            return
        # staff_number = toplayıcının author_id'si (doğal anahtar).
        personel = {
            p.staff_number: p.id
            for p in self.db.execute(select(AcademicStaff)).scalars()
        }
        ph = ",".join("?" * len(yazarlar))
        satirlar = self.k.execute(
            f"SELECT author_id, data_json, source_url FROM courses"
            f" WHERE author_id IN ({ph})", yazarlar
        ).fetchall()

        mevcut = {
            (c.academic_staff_id, c.academic_year, c.course_name, c.language)
            for c in self.db.execute(select(AcademicStaffCourse)).scalars()
        }
        for r in satirlar:
            personel_id = personel.get(r["author_id"])
            if personel_id is None:
                # Akademisyen aktarılmamış (ör. fakültesi yok); dersi de
                # sahipsiz bırakmak yerine atlanır ve sayılır.
                self.sayac["ders_sahipsiz"] += 1
                continue
            try:
                d = json.loads(r["data_json"] or "{}")
            except json.JSONDecodeError:
                self.sayac["ders_bozuk_json"] += 1
                continue

            yil = akademik_yil_normalize(d.get("Dönem") or d.get("donem"))
            ders_adi = (d.get("Ders Adı") or d.get("ders_adi") or "").strip()
            if not yil or not ders_adi:
                # Yıl veya ders adı yoksa satır anlamsızdır; uydurulmaz.
                self.sayac["ders_eksik_alan"] += 1
                continue

            dil = (d.get("Dili") or d.get("dili") or "").strip() or None
            ham_saat = str(d.get("Saat") or d.get("saat") or "").strip()
            rakam = re.sub(r"[^0-9]", "", ham_saat)
            # Okunamayan saat 0 DEĞİL, NULL: "sıfır saat ders veriyor" ile
            # "saat bilgisi yok" farklı şeylerdir.
            saat = int(rakam) if rakam else None

            anahtar = (personel_id, yil, ders_adi[:300], dil)
            if anahtar in mevcut:
                self.sayac["ders_mevcut"] += 1
                continue
            mevcut.add(anahtar)
            self.db.add(AcademicStaffCourse(
                academic_staff_id=personel_id, academic_year=yil,
                course_name=ders_adi[:300], language=dil, weekly_hours=saat,
                source_dataset="yok_akademik_courses",
                source_url=r["source_url"],
            ))
            self.sayac["ders_eklendi"] += 1
        self.db.flush()

    def _fakulte(self, ad: str, kullanilan: set) -> Faculty:
        # Üniversitenin her çocuğu fakülte değildir: REKTÖRLÜK idari birim,
        # MESLEK YÜKSEKOKULU meslek yüksekokuludur. Tür bir kez burada
        # belirlenir ve sütuna yazılır; sonraki filtrelemeler ad değil,
        # `unit_type` + ID ilişkisi üzerinden yapılır.
        tur = classify_unit(ad)
        mevcut = self.db.execute(
            select(Faculty).where(Faculty.name == ad)).scalar_one_or_none()
        if mevcut:
            # Tür sınıflandırması sonradan düzeltilmiş olabilir; mevcut
            # kayıtta da güncellenir (aktarım idempotent kalır).
            if mevcut.unit_type != tur:
                mevcut.unit_type = tur
                self.sayac["fakulte_turu_duzeltildi"] += 1
            self.sayac["fakulte_mevcut"] += 1
            kullanilan.add(mevcut.code)
            return mevcut
        kod = _tekil_kod(kod_uret(ad), kullanilan | self._kodlar(Faculty))
        f = Faculty(name=ad, code=kod, is_active=True, unit_type=tur,
                    description="Kaynak: YÖK Akademik toplayıcısı")
        self.db.add(f)
        self.db.flush()
        self.sayac["fakulte_eklendi" if tur != ADMINISTRATIVE
                   else "idari_ust_birim_eklendi"] += 1
        return f

    def _bolum(self, ad: str, fakulte: Faculty, kullanilan: set,
               idari: bool = False) -> Department:
        mevcut = self.db.execute(
            select(Department).where(Department.name == ad)).scalar_one_or_none()
        if mevcut:
            self.sayac["bolum_mevcut"] += 1
            kullanilan.add(mevcut.code)
            return mevcut
        kod = _tekil_kod(kod_uret(ad), kullanilan | self._kodlar(Department))
        d = Department(
            name=ad, code=kod, faculty_id=fakulte.id, is_active=True,
            description=("İdari birim — toplayıcıda bölüm bilgisi yok"
                         if idari else "Kaynak: YÖK Akademik toplayıcısı"),
        )
        self.db.add(d)
        self.db.flush()
        self.sayac["bolum_eklendi" if not idari else "idari_birim_eklendi"] += 1
        return d

    def _program(self, ad: str, bolum: Department, kullanilan: set) -> AcademicProgram:
        mevcut = self.db.execute(
            select(AcademicProgram).where(AcademicProgram.name == ad)
        ).scalar_one_or_none()
        if mevcut:
            self.sayac["program_mevcut"] += 1
            kullanilan.add(mevcut.code)
            return mevcut
        kod = _tekil_kod(kod_uret(ad), kullanilan | self._kodlar(AcademicProgram))
        seviye = derece_seviyesi(ad)
        p = AcademicProgram(
            name=ad, code=kod, department_id=bolum.id,
            degree_level=seviye,
            # Kontenjan ve süre toplayıcıda YOK → NULL bırakılıyor.
            # 0 yazmak "kontenjan sıfır / süre sıfır" anlamına gelirdi ve
            # doluluk oranını yanlış hesaplatırdı. NULL = "veri yok".
            duration_years=None, quota=None,
            description=("Kaynak: YÖK Akademik toplayıcısı. "
                         "Kontenjan ve öğrenim süresi bilgisi kaynakta yok."),
            is_active=True,
        )
        self.db.add(p)
        self.db.flush()
        self.sayac["program_eklendi"] += 1
        if seviye == "Bilinmiyor":
            self.sayac["program_derece_bilinmiyor"] += 1
        return p

    def _personel(self, a: sqlite3.Row, bolum: Department, akademik_yil: str,
                  yayin: int, tez: int, ders_saat: int) -> None:
        ad, soyad = ad_ayir(a["full_name"])
        # Unvan parantezli ek bilgi taşıyabiliyor ("(Unvan:Doçent)"); ana
        # unvan alınır, ek bilgi kaybolmasın diye tam hâli korunmaz —
        # gruplama unvana göre yapılıyor.
        unvan = re.split(r"\s*\(", (a["title"] or "Bilinmiyor").strip())[0][:60]

        mevcut = self.db.execute(
            select(AcademicStaff).where(AcademicStaff.staff_number == a["author_id"])
        ).scalar_one_or_none()

        alanlar = dict(
            first_name=ad, last_name=soyad, title=unvan,
            department_id=bolum.id, academic_year=akademik_yil,
            publication_count=yayin,
            advising_count=tez,
            teaching_load_hours=ders_saat,
            # Aşağıdakiler toplayıcıda YOK; 0 bırakılıyor ve rapora yazılıyor.
            citation_count=0, project_count=0, patent_count=0,
            community_engagement_score=0,
            annual_salary_usd=Decimal("0.00"),
            has_administrative_duty=False,
            has_industry_collaboration=False,
            is_active=True,
        )
        if mevcut:
            for k, v in alanlar.items():
                setattr(mevcut, k, v)
            self.sayac["personel_guncellendi"] += 1
        else:
            self.db.add(AcademicStaff(staff_number=a["author_id"], **alanlar))
            self.sayac["personel_eklendi"] += 1

    def _kodlar(self, model) -> set:
        return {c for (c,) in self.db.execute(select(model.code))}


# ---------------------------------------------------------------------------
# Temizlik
# ---------------------------------------------------------------------------


def demo_veriyi_sil(db: Session) -> Counter:
    """Aktarımdan önce mevcut (demo) kayıtları siler.

    Bağımlılık sırası önemlidir: önce yapraklar, sonra kökler.
    """
    from app.models import (
        AcademicSuccessRecord, FinancialEntry, FinancialPeriod,
        PhysicalFacility, ProgramAcademicStaffAllocation,
        ProgramFacilityAllocation, ProgramEnrollmentSnapshot, Student,
        StudentAcademicRecord,
    )
    from app.models.engagement import (
        IndustryCollaborationRecord, RegionalContributionRecord,
    )
    sayac = Counter()
    sirali = [
        AcademicStaffCourse,
        StudentAcademicRecord, ProgramEnrollmentSnapshot,
        ProgramAcademicStaffAllocation, ProgramFacilityAllocation,
        Student, AcademicSuccessRecord,
        IndustryCollaborationRecord, RegionalContributionRecord,
        FinancialEntry, FinancialPeriod, PhysicalFacility,
        AcademicStaff, AcademicProgram, Department, Faculty,
        BenchmarkInstitution,
    ]
    for model in sirali:
        n = db.query(model).delete()
        if n:
            sayac[model.__tablename__] = n
    db.flush()
    return sayac


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------


BOS_KALAN_TABLOLAR = [
    ("students / student_academic_records", "öğrenci kaydı, not, GPA"),
    ("program_enrollment_snapshots", "kontenjan, yerleşen, doluluk"),
    ("financial_periods / financial_entries", "gelir, gider, maaş, bütçe"),
    ("physical_facilities", "derslik, laboratuvar, kapasite"),
    ("strategic_kpis", "KPI hedef ve ölçümleri"),
    ("academic_success_records", "ders başarısı, geçme oranı"),
    ("engagement_records", "sanayi ve bölgesel katkı"),
    ("program_*_allocations", "program bazlı kadro/mekân tahsisi"),
]

BOS_KALAN_ALANLAR = [
    ("academic_staff.citation_count", "toplayıcıda atıf sayısı yok"),
    ("academic_staff.project_count", "projects tablosu boş"),
    ("academic_staff.patent_count", "toplayıcıda patent verisi yok"),
    ("academic_staff.annual_salary_usd", "toplayıcıda maaş verisi yok"),
    ("academic_staff.has_administrative_duty", "administrative_duties tablosu boş"),
    ("academic_staff.has_industry_collaboration", "toplayıcıda karşılığı yok"),
    ("academic_programs.quota", "toplayıcıda kontenjan yok"),
    ("academic_programs.duration_years", "toplayıcıda öğrenim süresi yok"),
]


def yonetici_hesabi_ac(db: Session, kullanici: str, parola: str) -> str:
    """Sisteme girebilmek için bir yönetici hesabı oluşturur.

    NEDEN BURADA
    ------------
    Toplayıcıda kullanıcı/rol verisi YOKTUR ve olamaz da — YÖK Akademik
    bir kimlik sağlayıcısı değildir. Ancak hesap olmadan hiç kimse
    uygulamayı açamaz; bu, "veri" değil KURULUM ADIMIDIR.

    Bu yüzden burada UYDURULMUŞ bir analiz verisi üretilmiyor; yalnızca
    sistemi açacak tek bir yönetici hesabı tanımlanıyor. Parola düz metin
    saklanmaz (PBKDF2-HMAC-SHA256 + salt). `--no-admin` ile atlanabilir.
    """
    from app.models import SystemUser
    from app.services.auth_service import hash_password

    mevcut = db.execute(
        select(SystemUser).where(SystemUser.username == kullanici)
    ).scalars().first()
    if mevcut is not None:
        return f"'{kullanici}' zaten var, dokunulmadı."

    salt, digest = hash_password(parola)
    db.add(SystemUser(
        username=kullanici, full_name="Sistem Yöneticisi",
        password_salt=salt, password_hash=digest, role="Admin",
        faculty_id=None, department_id=None,
    ))
    return f"'{kullanici}' oluşturuldu (rol: Admin)."


def main() -> int:
    ap = argparse.ArgumentParser(description="YÖK toplayıcı verisini aktarır.")
    ap.add_argument("--db", type=Path, default=VARSAYILAN_DB,
                    help="yok_akademik.db yolu")
    ap.add_argument("--university", default=HEDEF_KURUM,
                    help="Hedef kurumun toplayıcıdaki adı")
    ap.add_argument("--purge", action="store_true",
                    help="Aktarımdan önce mevcut veriyi sil (demo dâhil)")
    ap.add_argument("--admin-user", default="admin",
                    help="Oluşturulacak yönetici hesabının kullanıcı adı")
    ap.add_argument("--admin-password", default="demo1234",
                    help="Yönetici parolası. SUNUMDAN ÖNCE DEĞİŞTİRİN.")
    ap.add_argument("--no-admin", action="store_true",
                    help="Yönetici hesabı oluşturma (hesap zaten varsa)")
    args = ap.parse_args()

    print("=" * 68)
    print("YÖK AKADEMİK TOPLAYICI → ÜRETİM VERİTABANI")
    print("=" * 68)
    print(f"Kaynak : {args.db}")
    print(f"Kurum  : {args.university}")

    init_db()
    kaynak = toplayici_ac(args.db)
    db = SessionLocal()
    try:
        if args.purge:
            silinen = demo_veriyi_sil(db)
            print("\n[1/4] Mevcut veri silindi")
            for t, n in silinen.items():
                print(f"      {t:44s} {n:>7,}")
            if not silinen:
                print("      (silinecek kayıt yoktu)")

        aktarim = Aktarim(kaynak, db, args.university)
        print("\n[2/4] Karşılaştırma kurumları…")
        aktarim.kurumlari_aktar()
        aktarim.kurum_profillerini_aktar()
        print("\n[3/4] Akademik yapı ve personel…")
        aktarim.yapi_ve_personel_aktar()

        # Resmî öğrenci sayısı: bu aşamada ÖSYM verisi henüz yoktur, ama
        # varsa (ekdata daha önce yüklendiyse) sayı korunur/yenilenir.
        # Böylece iki betiğin çalışma sırası sayıyı bozmaz.
        from app.services import student_count
        student_count.refresh_stored_counts(db)

        print("\n[4/4] Yönetici hesabı…")
        if args.no_admin:
            print("      --no-admin verildi, atlandı.")
        else:
            print("      " + yonetici_hesabi_ac(
                db, args.admin_user, args.admin_password))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        kaynak.close()

    print("\n" + "-" * 68)
    print("AKTARILAN KAYITLAR")
    print("-" * 68)
    for k in sorted(aktarim.sayac):
        print(f"  {k:34s} {aktarim.sayac[k]:>7,}")

    print("\n" + "-" * 68)
    print("KAYNAKTA OLMAYAN — BOŞ BIRAKILDI (demo değerle DOLDURULMADI)")
    print("-" * 68)
    for tablo, aciklama in BOS_KALAN_TABLOLAR:
        print(f"  {tablo:44s} {aciklama}")
    print()
    for alan, aciklama in BOS_KALAN_ALANLAR:
        print(f"  {alan:44s} {aciklama}")

    if aktarim.bosluklar:
        print("\n" + "-" * 68)
        print("NOTLAR")
        print("-" * 68)
        for n in aktarim.bosluklar:
            print(f"  · {n}")

    print("\nTamamlandı. Betik idempotenttir; tekrar çalıştırmak kayıt eklemez.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
