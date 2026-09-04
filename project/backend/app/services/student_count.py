"""RESMÎ ÖĞRENCİ SAYISI — sistemin tek öğrenci sayısı kaynağı.

TANIM
-----
Bir programın öğrenci sayısı, ÖSYM'nin yayımladığı **en güncel en çok 4
yerleştirme yılındaki** yerleşen öğrenci sayılarının toplamıdır:

    student_count = Σ placed_students   (son ≤ 4 yerleştirme yılı)

Dört yıl, lisans programının normal öğrenim süresidir: o anda okuyan
öğrenci gövdesi, son dört kohortun toplamıdır.

NEDEN BÖYLE
-----------
Elimizdeki gerçek veride BİREYSEL öğrenci kaydı yok — ÖSYM kaç kişinin
yerleştiğini söyler, kim olduklarını söylemez. Sistemin öğrenci sayısına
ihtiyacı olan her yeri (doluluk, öğrenci/öğretim üyesi oranı, kapasite,
senaryo, AI araçları) çalıştırmak için iki yol vardı:

  1. Sahte öğrenci satırları üretmek → YASAK. Var olmayan kişileri
     veritabanına yazmak, sistemin bütün veri dürüstlüğünü çökertirdi.
  2. Sayıyı gerçek yerleştirme kayıtlarından TÜRETMEK → bu dosya.

ÇİFT SAYMA KORUMASI
-------------------
ÖSYM aynı programı aynı yıl birden çok YERLEŞTİRME PROGRAMI olarak
yayımlar (Burslu / %50 İndirimli / Ücretli, Türkçe / İngilizce). Bunlar
FARKLI kişilerdir, aynı kişinin tekrarı değildir — dolayısıyla toplanır.
Tekrar riski, aynı (yıl, program adı, puan türü, burs türü) satırının iki
kez sayılmasıdır; buna `yks_placement_records` üzerindeki tekillik kısıtı
zaten izin vermiyor.

EKSİK YIL SIFIR DEĞİLDİR
------------------------
Bir program 2023'te açılmışsa 2022 satırı YOKTUR. O yılı 0 sayıp dört yıla
bölmek programı olduğundan küçük gösterirdi. Toplam, yalnızca VERİSİ OLAN
yıllar üzerinden alınır ve kaç yıl kullanıldığı ayrıca kaydedilir.
Aynı şekilde `placed_students` NULL olan bir satır (ÖSYM açıklamamış)
sıfır sayılmaz, toplamın dışında kalır.

KULLANICIYA NASIL GÖRÜNÜR
-------------------------
Sadece **"Öğrenci Sayısı" / `student_count`** olarak. "Tahmini",
"yaklaşık" gibi bir ibare GÖSTERİLMEZ; bu, kurumun kabul ettiği resmî
sayıdır. Kaynak bilgisi (`source_method`, kullanılan yıllar) yalnızca
İZLENEBİLİRLİK için veritabanında ve iç API alanlarında durur.

YEDEK DAVRANIŞ
--------------
Bir programın hiç ÖSYM kaydı yoksa, sistemde gerçek `students` satırları
varsa onlar sayılır (demo veri kümesi ve ileride yüklenecek gerçek öğrenci
bilgi sistemi bu yoldan çalışır). İkisi de yoksa sonuç `None`'dır —
"0 öğrenci" değil, "veri yok".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Final, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AcademicProgram, Student, YksPlacementRecord

#: Toplamaya girecek en fazla yerleştirme yılı sayısı.
RECENT_COHORT_YEARS: Final[int] = 4

#: İzlenebilirlik etiketi. Kullanıcıya GÖSTERİLMEZ.
OFFICIAL_SOURCE_METHOD: Final[str] = "yks_recent_4_cohorts"

#: ÖSYM kaydı olmayan ama gerçek öğrenci satırı bulunan programlar için.
STUDENT_RECORD_SOURCE_METHOD: Final[str] = "student_records"


@dataclass(frozen=True)
class ProgramStudentCount:
    """Bir programın resmî öğrenci sayısı ve nereden geldiği."""

    academic_program_id: int
    #: Kullanıcıya gösterilen sayı. `None` = veri yok (0 DEĞİL).
    student_count: Optional[int]
    #: "yks_recent_4_cohorts" | "student_records" | None
    source_method: Optional[str]
    #: Toplamaya giren yerleştirme yılları, eskiden yeniye.
    years: Sequence[int] = ()

    @property
    def year_span(self) -> Optional[str]:
        """"2022-2025" — izlenebilirlik için kısa gösterim."""
        if not self.years:
            return None
        if len(self.years) == 1:
            return str(self.years[0])
        return f"{min(self.years)}-{max(self.years)}"


def _yks_counts(db: Session, program_ids: Optional[Sequence[int]] = None,
                donem: Optional[str] = None
                ) -> Dict[int, ProgramStudentCount]:
    """ÖSYM kayıtlarından program başına resmî sayıyı hesaplar.

    DÖNEM PENCEREYİ BİTİRİR
    -----------------------
    Öğrenci gövdesi "en güncel ≤4 yerleştirme yılının toplamı"dır.
    `donem` verildiğinde pencere O YILDA BİTER: 2024-2025 seçilirse
    2021…2024 kohortları toplanır, 2025 kohortu SAYILMAZ. Böylece
    seçilen yılın etiketi altında sonraki yılın öğrencisi görünmez.
    """
    bitis_yili = _donem_yili(donem)
    sorgu = select(
        YksPlacementRecord.academic_program_id,
        YksPlacementRecord.placement_year,
        func.sum(YksPlacementRecord.placed_students),
    ).where(
        # NULL yerleşen "sıfır kişi yerleşti" demek değildir; toplamın
        # dışında kalır. SUM zaten NULL'ları atlar ama satırın o yılı
        # "veri var" saymasını da engellemek gerekiyor.
        YksPlacementRecord.placed_students.isnot(None)
    ).group_by(
        YksPlacementRecord.academic_program_id,
        YksPlacementRecord.placement_year,
    )
    if program_ids is not None:
        sorgu = sorgu.where(
            YksPlacementRecord.academic_program_id.in_(program_ids)
        )
    if bitis_yili is not None:
        sorgu = sorgu.where(YksPlacementRecord.placement_year <= bitis_yili)

    # program -> {yıl: o yılın toplamı}
    yil_bazli: Dict[int, Dict[int, int]] = {}
    for program_id, yil, toplam in db.execute(sorgu):
        if toplam is None:
            continue
        yil_bazli.setdefault(program_id, {})[int(yil)] = int(toplam)

    sonuc: Dict[int, ProgramStudentCount] = {}
    for program_id, yillar in yil_bazli.items():
        # EN GÜNCEL en çok 4 yıl. Aradaki boşluk yıl SAYILMAZ; "son 4
        # takvim yılı" değil, "verisi olan son 4 yıl" alınır.
        secilen = sorted(yillar)[-RECENT_COHORT_YEARS:]
        sonuc[program_id] = ProgramStudentCount(
            academic_program_id=program_id,
            student_count=sum(yillar[y] for y in secilen),
            source_method=OFFICIAL_SOURCE_METHOD,
            years=tuple(secilen),
        )
    return sonuc


def _student_record_counts(db: Session,
                           program_ids: Optional[Sequence[int]] = None
                           ) -> Dict[int, int]:
    """Gerçek öğrenci satırlarından sayım (yedek yol)."""
    sorgu = (
        select(Student.academic_program_id, func.count(Student.id))
        .where(Student.is_active.is_(True))
        .group_by(Student.academic_program_id)
    )
    if program_ids is not None:
        sorgu = sorgu.where(Student.academic_program_id.in_(program_ids))
    return {pid: int(adet) for pid, adet in db.execute(sorgu) if pid is not None}


def _donem_yili(donem: Optional[str]) -> Optional[int]:
    """"2024-2025" → 2024. Biçim tanınmazsa None (süzgeç uygulanmaz)."""
    if not donem:
        return None
    bas = str(donem).split("-")[0].strip()
    return int(bas) if bas.isdigit() else None


def program_counts(db: Session, scope=None,
                   donem: Optional[str] = None) -> Dict[int, ProgramStudentCount]:
    """Kapsam içindeki her programın resmî öğrenci sayısı.

    ÖSYM verisi olan program için o kullanılır; yoksa gerçek öğrenci
    satırları sayılır. İkisi de yoksa program sözlüğe GİRMEZ — çağıran
    taraf "veri yok" ile "sıfır öğrenci"yi ayırt edebilsin diye.
    """
    program_ids = None
    if scope is not None and getattr(scope, "program_ids", None) is not None:
        program_ids = list(scope.program_ids)
        if not program_ids:
            return {}

    sonuc = _yks_counts(db, program_ids, donem)
    # `students` tablosu cari aktiflik durumunu taşır; tarihsel bir anlık
    # görüntü değildir. Açık bir dönem seçilmişken bu satırları o döneme ait
    # saymak sessiz dönem geri dönüşü olurdu. Bu yedek yalnızca dönem
    # belirtilmediğinde güvenlidir.
    yedek_sayimlar = (
        _student_record_counts(db, program_ids) if donem is None else {}
    )
    for program_id, adet in yedek_sayimlar.items():
        if program_id in sonuc:
            # ÖSYM verisi varsa o RESMÎDİR; öğrenci satırları onu ezmez.
            continue
        sonuc[program_id] = ProgramStudentCount(
            academic_program_id=program_id,
            student_count=adet,
            source_method=STUDENT_RECORD_SOURCE_METHOD,
        )
    return sonuc


def program_count(db: Session, academic_program_id: int) -> Optional[int]:
    """Tek programın resmî öğrenci sayısı. Veri yoksa `None`."""
    kayit = program_counts(db).get(academic_program_id)
    return kayit.student_count if kayit else None


def total_for_scope_detailed(db: Session, scope=None,
                             donem: Optional[str] = None) -> tuple:
    """Kapsamın yetkili öğrenci sayısı ve o sayının KAYNAĞI.

    ÜNİVERSİTE KAPSAMINDA YÖK SAYISI YETKİLİDİR
    -------------------------------------------
    ÖSYM türevi toplam (son ≤4 kohort) yalnızca YERLEŞTİRME ile geleni
    sayar; lisansüstü, yatay geçiş ve DGS ile gelen öğrenciyi kapsamaz.
    YÖK'ün bildirdiği kayıtlı öğrenci sayısı kurumun fiilî gövdesidir ve
    üniversite düzeyinde bundan daha doğrudur (ABÜ 2025-2026: 3.626'ya
    karşı ÖSYM türevi 3.348).

    NEDEN BURADA, EKRANDA DEĞİL
    ---------------------------
    Bu düzeltme daha önce yalnızca gezinme ağacında (frontend) yapılıyordu.
    Sonuç: `/staffing` 3.348, kayıtlı öğrenci ucu 3.626 diyordu; aynı
    ekranın iki kutusu aynı soruya iki farklı cevap veriyordu. Düzeltme
    tek kaynağa —bu fonksiyona— alınınca oran hesapları (öğrenci/akademisyen,
    kapasite, senaryo, AI araçları) dahil HER tüketici otomatik olarak
    aynı sayıyı görür; ayrışma yapısal olarak imkânsızlaşır.

    ALT KAPSAMA SIZDIRILMAZ
    -----------------------
    YÖK verisinin fakülte/bölüm kırılımı yoktur. Üniversite toplamını bir
    fakülteye yazmak uydurma olurdu; alt kapsamlarda ÖSYM türevi toplam
    aynen korunur.

    Döner: (sayı, kaynak) — kaynak "yok_kayitli" ya da "yks_turevi".
    """
    yks, alt_kaynak = _yks_turevi_toplam_kaynakli(db, scope, donem)
    if scope is not None and not scope.is_university:
        return yks, alt_kaynak

    # Üniversite kapsamı (scope=None dâhil): YÖK sayısı varsa o yetkilidir.
    from app.services import university_headcount_service as kayitli
    ozet = kayitli.enrolled_headcount(db, scope, donem=donem)
    if ozet.get("available") and ozet.get("student_count"):
        return int(ozet["student_count"]), "yok_kayitli"
    return yks, alt_kaynak


def _yks_turevi_toplam_kaynakli(db: Session, scope=None,
                                donem: Optional[str] = None) -> tuple:
    """Program bazlı toplam ve o toplamın GERÇEK kaynağı.

    KAYNAK ETİKETİ NEDEN HESAPLANIYOR
    ---------------------------------
    `program_counts` her programı ayrı ayrı etiketler: ÖSYM yerleştirme
    kaydı varsa resmî yöntem, yoksa öğrenci satırı sayımı. Toplam ise
    eskiden KOŞULSUZ `"yks_turevi"` olarak damgalanıyordu.

    Canlıda bunun sonucu şuydu: `yks_placement_records` tablosu BOŞken
    ekrandaki dağılım paneli "ÖSYM yerleştirmelerinden türetilen program
    öğrenci sayıları" diyor, hemen yanındaki trend paneli ise doğru
    biçimde "Bu kapsamda yerleştirme kaydı yok" diyordu. Aynı kapsam için
    iki panel birbirini yalanlıyordu — sayı öğrenci kayıtlarından
    geliyordu ama ÖSYM etiketiyle sunuluyordu.

    Artık etiket VERİDEN türetilir:
      · hepsi ÖSYM        → "yks_turevi"
      · hepsi kayıt sayımı→ "ogrenci_kaydi"
      · karışık           → "karisik"
    """
    kayitlar = [k for k in program_counts(db, scope, donem).values()
                if k.student_count is not None]
    if not kayitlar:
        return None, None
    toplam = sum(k.student_count for k in kayitlar)
    yontemler = {k.source_method for k in kayitlar}
    if yontemler == {OFFICIAL_SOURCE_METHOD}:
        return toplam, "yks_turevi"
    if yontemler == {STUDENT_RECORD_SOURCE_METHOD}:
        return toplam, "ogrenci_kaydi"
    return toplam, "karisik"


def total_for_scope(db: Session, scope=None,
                    donem: Optional[str] = None) -> Optional[int]:
    """Kapsamın yetkili öğrenci sayısı (kaynak bilgisi olmadan).

    Ayrıntı ve gerekçe için `total_for_scope_detailed`.
    """
    return total_for_scope_detailed(db, scope, donem)[0]


def _yks_turevi_toplam(db: Session, scope=None,
                       donem: Optional[str] = None) -> Optional[int]:
    """Kapsamdaki programların ÖSYM türevi toplam öğrenci sayısı.

    HİYERARŞİ: kapsam neyi içeriyorsa o toplanır —
      program    → yalnızca o program
      bölüm      → o bölümün programları
      fakülte    → o fakültenin bütün programları
      üniversite → bütün akademik programlar

    Toplama daima PROGRAM düzeyinde yapılır; üst düzeyde ayrıca bir sayı
    tutulmaz. İki yerde tutulan aynı toplam er ya da geç ayrışır.

    Hiçbir programda veri yoksa `None` döner — "0 öğrenci" demek, veri
    olmadığını gizlemek olurdu.
    """
    kayitlar = [k for k in program_counts(db, scope).values()
                if k.student_count is not None]
    if not kayitlar:
        return None
    return sum(k.student_count for k in kayitlar)


def refresh_stored_counts(db: Session) -> Dict[str, int]:
    """Hesaplanan sayıları `academic_programs` üzerine yazar.

    NEDEN SAKLANIYOR: sayı SQL'de sıralanabilir/filtrelenebilir olmalı ve
    her istekte yeniden hesaplanmamalı. Türetme kuralı yine tek yerde
    (bu dosyada) durur; sütun onun ÖNBELLEĞİDİR.

    Aktarım sonunda çağrılır ve idempotenttir: aynı veriyle ikinci kez
    çalıştırmak hiçbir değeri değiştirmez.
    """
    hesap = program_counts(db)
    sayac = {"guncellendi": 0, "degismedi": 0, "veri_yok": 0}

    for program in db.execute(select(AcademicProgram)).scalars():
        kayit = hesap.get(program.id)
        yeni_sayi = kayit.student_count if kayit else None
        yeni_yontem = kayit.source_method if kayit else None
        yeni_yillar = kayit.year_span if kayit else None

        if (program.student_count == yeni_sayi
                and program.student_count_source_method == yeni_yontem
                and program.student_count_year_span == yeni_yillar):
            sayac["degismedi" if yeni_sayi is not None else "veri_yok"] += 1
            continue

        program.student_count = yeni_sayi
        program.student_count_source_method = yeni_yontem
        program.student_count_year_span = yeni_yillar
        sayac["guncellendi" if yeni_sayi is not None else "veri_yok"] += 1

    db.flush()
    return sayac
