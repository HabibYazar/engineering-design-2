"""GEÇERLİ DÖNEM ÇÖZÜCÜSÜ — panonun "hangi akademik yıl" sorusunun tek yanıtı.

SORUN
-----
Dönem seçici `/api/education-analytics/academic-years` ucundan besleniyordu.
O uç `program_enrollment_snapshots` tablosunu okur; bu tablo ÖRNEK (demo)
veri modülüne aittir ve içinde ileri tarihli planlama yılları bulunabilir.
Sonuç: arayüz açılışta **2026-2027**'yi seçiyor, oysa panonun gerçek
veri kümeleri (ÖSYM yerleştirmeleri, YÖK kayıtlı öğrenci sayısı, ders
yükü) 2025-2026'da bitiyor. Kullanıcı, hiçbir şey yapmadan, bütün gerçek
panelleri boş gösteren bir yıl seçilmiş hâlde karşılanıyordu.

KURAL
-----
Panonun VARSAYILAN dönemi, **çekirdek işletim veri kümelerinin hepsinde
verisi olan en güncel yıldır**:

    · ÖSYM yerleştirme kayıtları   (öğrenci, kontenjan, burs panelleri)
    · YÖK kayıtlı öğrenci sayıları (kurum büyüklüğü ve trend)
    · Akademisyen ders kayıtları   (ders yükü panelleri)

İleriye dönük fiyat listeleri (`program_tuition_fees` 2026-2027 içerir)
çekirdeğe DAHİL DEĞİLDİR: bir sonraki yılın ücret tarifesi yayımlandı
diye kurumun işletim dönemi değişmez. Bu ayrım olmadan seçici yine
2026-2027'ye kayardı.

NE YAPILMAZ
-----------
· Seçilen yılda verisi olmayan bir gösterge SIFIR gösterilmez.
· Seçilen yılın etiketi altında BAŞKA bir yılın sayısı gösterilmez.
Her veri kümesinin kendi yıl listesi ayrıca döner; arayüz "bu gösterge
bu dönemde ölçülmemiş" durumunu bu listeye bakarak yazar.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AcademicStaffCourse,
    UniversityStudentHeadcount,
    YksPlacementRecord,
)

#: Panonun işletim dönemini belirleyen veri kümeleri. Sıra önemsizdir;
#: kesişim alınır.
CEKIRDEK = ("yks_placements", "enrolled_headcount", "teaching_load")

#: Kullanıcıya gösterilecek okunur adlar.
ETIKETLER = {
    "yks_placements": "ÖSYM yerleştirme kayıtları",
    "enrolled_headcount": "YÖK kayıtlı öğrenci sayıları",
    "teaching_load": "Akademisyen ders kayıtları",
    "program_tuition": "Program eğitim ücretleri",
    "competitor_tuition": "Rakip kurum ücretleri",
}


def _yillar(db: Session, sutun) -> List[str]:
    return sorted(
        y for (y,) in db.execute(select(sutun).distinct()).all() if y
    )


def dataset_years(db: Session) -> Dict[str, List[str]]:
    """Her veri kümesinin sahip olduğu akademik yıllar."""
    out: Dict[str, List[str]] = {
        "yks_placements": _yillar(db, YksPlacementRecord.academic_year),
        "enrolled_headcount": _yillar(db, UniversityStudentHeadcount.academic_year),
        "teaching_load": _yillar(db, AcademicStaffCourse.academic_year),
    }
    # Ücret tabloları isteğe bağlıdır (part3 aktarılmamış olabilir).
    try:
        from app.models import ProgramTuitionFee  # type: ignore

        out["program_tuition"] = _yillar(db, ProgramTuitionFee.academic_year)
    except Exception:
        out["program_tuition"] = []
    try:
        from app.models import CompetitorTuitionFee  # type: ignore

        out["competitor_tuition"] = _yillar(db, CompetitorTuitionFee.academic_year)
    except Exception:
        out["competitor_tuition"] = []
    return out


def latest_operating_period(db: Session) -> Optional[str]:
    """Çekirdek veri kümelerinin HEPSİNDE verisi olan en güncel yıl.

    Kesişim boşsa (ör. ders kayıtları hiç aktarılmamışsa) kural
    gevşetilir ve verisi OLAN çekirdek kümelerin kesişimi kullanılır.
    Hiçbiri yoksa `None` döner — uydurma bir yıl seçilmez.
    """
    yillar = dataset_years(db)
    kumeler = [set(yillar[k]) for k in CEKIRDEK if yillar.get(k)]
    if not kumeler:
        return None
    kesisim = set.intersection(*kumeler)
    if not kesisim:
        # Kesişim yoksa en dar ortak paydaya inmek yerine, EN AZ bir
        # çekirdek kümenin en güncel yılını vermek daha dürüsttür;
        # hangi kümelerin o yılda verisi olduğu ayrıca dönüyor.
        kesisim = set().union(*kumeler)
    return max(kesisim)


def period_summary(db: Session) -> dict:
    """Dönem seçicisinin tükettiği tam özet."""
    yillar = dataset_years(db)
    varsayilan = latest_operating_period(db)

    # SEÇİLEBİLİR YILLAR: bütün veri kümelerinin BİRLEŞİMİ değil.
    # `academic_staff_courses` akademisyenlerin geçmiş kariyerini de
    # taşır ve 1992'ye kadar iner; birleşim alınsaydı seçiciye 34 yıl
    # düşer, bunların 26'sında pano boş kalırdı. Bir yıl ancak EN AZ İKİ
    # çekirdek veri kümesinde kaydı varsa kurumun işletim dönemi sayılır.
    sayac: Dict[str, int] = {}
    for anahtar in CEKIRDEK:
        for y in yillar.get(anahtar, []):
            sayac[y] = sayac.get(y, 0) + 1
    secilebilir = sorted(y for y, n in sayac.items() if n >= 2)
    if not secilebilir:                      # tek kümede veri varsa ona düş
        secilebilir = sorted(sayac)

    # Her yıl için: o yılda verisi olan veri kümeleri. Arayüz, seçilen
    # yılda ölçülmeyen göstergeyi bu listeye bakarak "veri yok" olarak
    # işaretler; sıfır basmaz.
    kapsam = {
        y: sorted(k for k, v in yillar.items() if y in v)
        for y in secilebilir
    }
    return {
        "available": bool(secilebilir),
        "default_period": varsayilan,
        "selectable_periods": secilebilir,
        "core_datasets": list(CEKIRDEK),
        "dataset_years": yillar,
        "dataset_labels": ETIKETLER,
        "coverage_by_period": kapsam,
        "note": (
            "Varsayılan dönem, ÖSYM yerleştirme + YÖK kayıtlı öğrenci + "
            "ders yükü veri kümelerinin hepsinde kaydı olan en güncel "
            "yıldır. İleri tarihli ücret tarifeleri bu seçimi etkilemez."
        ),
    }


# ---------------------------------------------------------------------------
# VERİ KAYNAĞI DURUMU — "ekrandaki sayılar nereden geliyor?"
# ---------------------------------------------------------------------------


def data_source_state(db: Session) -> dict:
    """Panonun hangi veri temeli üzerinde çalıştığını söyler.

    NEDEN VAR
    ---------
    Canlı kurulumda pano, kurumun GERÇEK verisi yerine ÖRNEK (demo)
    veritabanı üzerinde çalışıyordu ve bunu hiçbir yerde söylemiyordu.
    Ekranda "Faculty of Engineering and Architecture", 216 akademisyen,
    2.062 yayın gibi tamamen uydurma değerler kurumsal gerçekmiş gibi
    sunuluyordu; gerçek veri tablolarının HEPSİ boştu:

        yks_placement_records          0
        university_student_headcounts  0
        academic_staff_courses         0
        curriculum_canonical_courses   0

    Bir karar destek sisteminin yapabileceği en kötü hata budur. Bu uç,
    durumu ölçülebilir hâle getirir; arayüz bunu kapatılamaz bir uyarı
    şeridi olarak gösterir.

    `mode`:
      · "real"    → çekirdek gerçek veri kümeleri dolu
      · "partial" → bir kısmı dolu (aktarım yarım kalmış)
      · "demo"    → çekirdeğin tamamı boş ama ekranda sayı üreten
                    örnek tablolar dolu → GÖSTERİLEN SAYILAR UYDURMA
      · "empty"   → hiç veri yok
    """
    from sqlalchemy import func as _f

    from app.models import AcademicStaff, Student

    yillar = dataset_years(db)
    dolu = [k for k in CEKIRDEK if yillar.get(k)]
    bos = [k for k in CEKIRDEK if not yillar.get(k)]

    ogrenci_satiri = db.execute(
        select(_f.count()).select_from(Student)).scalar_one()
    kadro_satiri = db.execute(
        select(_f.count()).select_from(AcademicStaff)).scalar_one()

    # HİYERARŞİ SAĞLAYICI DENETİMİ
    # Gerçek veri yüklü olsa bile, `--purge` verilmeden yapılan bir
    # aktarımda ESKİ ÖRNEK hiyerarşi kayıtları yerinde kalır ve pano
    # ikisini birden toplar (canlıda fakülte dağılımı 7.348 çıkıyordu:
    # 3.348 gerçek + 4.000 örnek). Bu durum "gerçek veri var" diye
    # sessizce geçilemez.
    from app.services import hierarchy_provenance

    sağlayıcı = hierarchy_provenance.provenance_report(db)

    if not dolu and (ogrenci_satiri or kadro_satiri):
        mod = "demo"
    elif not dolu:
        mod = "empty"
    elif not sağlayıcı["clean"]:
        mod = "mixed"
    elif bos:
        mod = "partial"
    else:
        mod = "real"

    kaynaksiz = sağlayıcı["unmarked_counts"]
    ornek_fakulteler = ", ".join(
        f"{r['name']} (id={r['id']}, kod={r['code']})"
        for r in sağlayıcı["unmarked_units"]["faculties"][:4])

    mesaj = {
        "real": None,
        "mixed": (
            "DİKKAT: Veritabanında GERÇEK ve ÖRNEK hiyerarşi bir arada. "
            f"Kurumsal kaynak damgası taşımayan birim: {kaynaksiz}. "
            f"Örnek fakülteler: {ornek_fakulteler}. "
            "Bu yüzden fakülte dağılımı kurumun gerçek büyüklüğünden "
            "fazla çıkar. Temizlemek için: "
            "python purge_demo_hierarchy.py --apply"),
        "partial": ("Gerçek veri aktarımı YARIM: "
                    + ", ".join(ETIKETLER.get(k, k) for k in bos)
                    + " yüklenmemiş. Bu kaynaklara dayanan paneller boş kalır."),
        "demo": ("DİKKAT: Bu pano ÖRNEK (demo) veritabanı üzerinde çalışıyor. "
                 "Ekrandaki bütün sayılar UYDURMADIR, kurumun gerçek verisi "
                 "değildir. Gerçek veriyi yüklemek için: "
                 "python import_all_real_data.py --purge"),
        "empty": ("Veritabanı boş. Gerçek veriyi yüklemek için: "
                  "python import_all_real_data.py --purge"),
    }[mod]

    return {
        "mode": mod,
        "is_trustworthy": mod in ("real", "partial"),
        "hierarchy_provenance": sağlayıcı,
        "message": mesaj,
        "core_datasets_present": dolu,
        "core_datasets_missing": bos,
        "dataset_labels": ETIKETLER,
        "sample_table_rows": {"students": ogrenci_satiri,
                              "academic_staff": kadro_satiri},
    }
