"""ÖRNEK VERİ HİYERARŞİ ARTIKLARINI TEMİZLER — bilinçli, kanıt gösteren.

NE ZAMAN GEREKİR
----------------
`import_all_real_data.py` **--purge olmadan** çalıştırıldıysa, daha önce
yüklenmiş örnek (demo) veri veritabanında kalır. Gerçek ve örnek
hiyerarşi yan yana durur; pano üniversite düzeyinde ikisini birden
toplar. Canlıda gözlenen:

    Fakülte dağılımı toplamı        7.348   (3.348 gerçek + 4.000 örnek)
    Üniversite YÖK öğrenci sayısı   3.626
    "Mühendislik ve Mimarlık Fakültesi" listede İKİ KEZ

NASIL AYIRT EDER
----------------
AD BENZERLİĞİNE BAKMAZ. Ölçüt sağlayıcı damgasıdır: kurumsal aktarıcılar
her satıra `description = "Kaynak: <kaynak>"` yazar. Damgası olmayan
hiyerarşi satırı resmî kaynaklardan gelmemiştir.

GÜVENLİK
--------
· Varsayılan KURU ÇALIŞMADIR; `--apply` verilmedikçe hiçbir şey silinmez.
· Silmeden önce ne silineceğini kimlik/kod/ad ile listeler.
· Bağlı kayıtlar (öğrenci, kadro, yerleştirme…) da temizlenir; yetim
  satır bırakmak, sayıları daha da bozardı.
· Geri alma yolu: `python import_all_real_data.py --purge` ile gerçek
  veri sıfırdan kurulur.

KULLANIM
    python purge_demo_hierarchy.py            # yalnızca rapor
    python purge_demo_hierarchy.py --apply    # sil
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import AcademicProgram, Department, Faculty
from app.services.hierarchy_provenance import provenance_report


def _yazdir(baslik: str, satirlar) -> None:
    print(f"\n{baslik} ({len(satirlar)})")
    for r in satirlar:
        print(f"   id={r['id']:>4}  kod={str(r['code']):<14} {r['name']}")


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument("--apply", action="store_true",
                             help="Bulunan kayıtları GERÇEKTEN siler.")
    args = ayristirici.parse_args()

    db = SessionLocal()
    try:
        rapor = provenance_report(db)
        print("=" * 70)
        print("HİYERARŞİ SAĞLAYICI DENETİMİ")
        print("=" * 70)
        print(rapor["rule"])
        print(f"\nToplam birim: {rapor['total_units']}")
        print(f"Damgasız    : {rapor['unmarked_counts']}")

        if rapor["clean"]:
            print("\nTemiz: kaynaksız hiyerarşi satırı yok. Yapılacak bir şey yok.")
            return 0

        _yazdir("KAYNAKSIZ FAKÜLTELER", rapor["unmarked_units"]["faculties"])
        _yazdir("KAYNAKSIZ BÖLÜMLER", rapor["unmarked_units"]["departments"])
        _yazdir("KAYNAKSIZ PROGRAMLAR", rapor["unmarked_units"]["programs"])

        if not args.apply:
            print("\nKURU ÇALIŞMA — hiçbir şey silinmedi.")
            print("Silmek için: python purge_demo_hierarchy.py --apply")
            return 0

        program_ids = [r["id"] for r in rapor["unmarked_units"]["programs"]]
        bolum_ids = [r["id"] for r in rapor["unmarked_units"]["departments"]]
        fakulte_ids = [r["id"] for r in rapor["unmarked_units"]["faculties"]]

        # Bağlı kayıtlar önce: yetim satır bırakmak sayıları bozardı.
        silinen = {}
        for model_adi, model, sutun, degerler in _bagli_kayitlar(
                program_ids, bolum_ids):
            if not degerler:
                continue
            sonuc = db.execute(delete(model).where(sutun.in_(degerler)))
            if sonuc.rowcount:
                silinen[model_adi] = sonuc.rowcount

        for model, ids in ((AcademicProgram, program_ids),
                           (Department, bolum_ids),
                           (Faculty, fakulte_ids)):
            if ids:
                sonuc = db.execute(delete(model).where(model.id.in_(ids)))
                silinen[model.__tablename__] = sonuc.rowcount
        db.commit()

        print("\nSİLİNDİ:")
        for ad, n in sorted(silinen.items()):
            print(f"   {ad:<34} {n}")

        kalan = provenance_report(db)
        print(f"\nDoğrulama — damgasız kalan: {kalan['unmarked_counts']}")
        return 0 if kalan["clean"] else 1
    finally:
        db.close()


def _bagli_kayitlar(program_ids, bolum_ids):
    """Silinecek birimlere bağlı kayıtlar (model, sütun, değerler)."""
    from app.models import (
        AcademicStaff,
        ProgramEnrollmentSnapshot,
        Student,
        YksPlacementRecord,
    )

    return [
        ("students", Student, Student.academic_program_id, program_ids),
        ("yks_placement_records", YksPlacementRecord,
         YksPlacementRecord.academic_program_id, program_ids),
        ("program_enrollment_snapshots", ProgramEnrollmentSnapshot,
         ProgramEnrollmentSnapshot.academic_program_id, program_ids),
        ("academic_staff", AcademicStaff, AcademicStaff.department_id, bolum_ids),
    ]


if __name__ == "__main__":
    sys.exit(main())
