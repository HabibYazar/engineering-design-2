"""BÜTÜN gerçek veriyi tek komutla yükler.

Sıra ÖNEMLİDİR ve keyfî değildir:

    1. import_yok_collector.py   YÖK Akademik toplayıcısı
       → fakülte / bölüm / program / akademik kadro / karşılaştırma kurumları
       Hiyerarşinin OMURGASINI kurar. Diğer kaynaklar bu ağaca bağlanır.

    2. import_ekdata.py          data/ekdata altındaki ek gerçek kümeler
       → ÖSYM yerleştirme, müfredat
       Var olan birimlere bağlanır; bulamadığını (gerçekse) ekler.

    6. import_yok_atlas_ankara.py  Ankara YÖK Atlas 2022-2024
       → yalnızca eksik dış karşılaştırma metriklerini tamamlayan,
         resmî/kurumsal tabloları ezmeyen ikincil kaynak.

Ters sırada çalıştırılırsa ÖSYM'nin "Bilgisayar Programcılığı" satırı
bağlanacak bir program bulamaz ve yeni bir bölüm açar; YÖK sonradan
geldiğinde aynı birim ikinci kez oluşur. Bu yüzden sıra bu betikte
sabitlenmiştir.

İkisi de İDEMPOTENTTİR: bu betik istendiği kadar çalıştırılabilir.

ÇALIŞTIRMA
----------
    python import_all_real_data.py
    python import_all_real_data.py --purge          # önce mevcut veriyi sil
    python import_all_real_data.py --collector-db <yol> --ekdata-dir <yol>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
KOK = BACKEND_DIR.parent

VARSAYILAN_TOPLAYICI = (
    KOK / "data" / "yok-akademik" / "yok_akademik.db"
)
VARSAYILAN_EKDATA = KOK / "data" / "ekdata"
VARSAYILAN_PART2 = KOK / "data" / "ekdata" / "part2"

#: part3 ÖNCE depo içine (integration/data) bakar: taze bir `git clone`
#: yalnızca `integration/` ile veritabanını kurabilmelidir. Bulunamazsa
#: eski yerleşim (depo kökü) denenir.
_PART3_ADAYLARI = (
    BACKEND_DIR.parent / "data" / "ekdata" / "part3",
    KOK / "data" / "ekdata" / "part3",
)
VARSAYILAN_PART3 = next(
    (p for p in _PART3_ADAYLARI if p.exists()), _PART3_ADAYLARI[0])

#: Yabancı öğrenci sayıları (2025-2026) — tek dosya, ekdata kökünde.
#: part3 gibi önce depo içine, sonra depo köküne bakar.
_YABANCI_ADAYLARI = (
    BACKEND_DIR.parent / "data" / "ekdata"
    / "ankara_bilim_yabanci_ogrenci_2025_2026.xlsx",
    KOK / "data" / "ekdata" / "ankara_bilim_yabanci_ogrenci_2025_2026.xlsx",
)
VARSAYILAN_YABANCI = next(
    (p for p in _YABANCI_ADAYLARI if p.exists()), _YABANCI_ADAYLARI[0])

VARSAYILAN_YOK_ATLAS = (
    KOK / "data" / "yokatlas_ankara_2022_plus_output"
)


def _calistir(baslik: str, komut: list) -> None:
    print("\n" + "#" * 68)
    print(f"# {baslik}")
    print("#" * 68)
    sonuc = subprocess.run(komut, cwd=BACKEND_DIR)
    if sonuc.returncode != 0:
        raise SystemExit(f"BAŞARISIZ: {baslik} (çıkış kodu {sonuc.returncode})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Tüm gerçek veriyi yükler.")
    ap.add_argument("--collector-db", type=Path, default=VARSAYILAN_TOPLAYICI)
    ap.add_argument("--ekdata-dir", type=Path, default=VARSAYILAN_EKDATA)
    ap.add_argument("--part2-dir", type=Path, default=VARSAYILAN_PART2)
    ap.add_argument("--part3-dir", type=Path, default=VARSAYILAN_PART3)
    ap.add_argument("--foreign-file", type=Path, default=VARSAYILAN_YABANCI,
                    help="Yabancı öğrenci sayıları çalışma kitabı (.xlsx)")
    ap.add_argument("--yok-atlas-dir", type=Path, default=VARSAYILAN_YOK_ATLAS,
                    help="Ankara YÖK Atlas 2022-2024 kaynak klasörü")
    ap.add_argument("--purge", action="store_true",
                    help="Aktarımdan önce mevcut veriyi sil (demo dâhil)")
    ap.add_argument("--admin-password", default=None,
                    help="Yönetici parolası (varsayılan: import betiğinin varsayılanı)")
    args = ap.parse_args()

    eksik = [p for p in (args.collector_db, args.ekdata_dir) if not p.exists()]
    if eksik:
        for p in eksik:
            print(f"BULUNAMADI: {p}", file=sys.stderr)
        return 1

    py = sys.executable

    yok = [py, "import_yok_collector.py", "--db", str(args.collector_db)]
    if args.purge:
        yok.append("--purge")
    if args.admin_password:
        yok += ["--admin-password", args.admin_password]
    _calistir("1/6  YÖK Akademik toplayıcısı", yok)

    _calistir(
        "2/6  data/ekdata ek gerçek veri kümeleri",
        [py, "import_ekdata.py", "--dir", str(args.ekdata_dir)],
    )

    # part2 AYRI bir adımdır ve AYRI bir betikle yürür. Sebebi:
    # `import_ekdata.py` yalnızca .csv/.json/.xlsx tanır ve part2
    # dosyaları eski BIFF .xls'tir — o betiğe .xls desteği eklemek,
    # kanıtlanmış part-1 akışını riske atardı. Klasör yoksa adım
    # sessizce atlanır; part2 opsiyoneldir.
    if args.part2_dir.exists():
        _calistir(
            "3/6  data/ekdata/part2 YÖK kayıt defteri + öğrenci sayıları",
            [py, "import_yok_registry.py", "--dir", str(args.part2_dir)],
        )
    else:
        print(f"\nATLANDI: {args.part2_dir} bulunamadı (part2 opsiyoneldir).")

    # part3: derslik envanteri ve eğitim ücretleri. part2'den SONRA
    # çalışır çünkü derslikleri fakültelere, ücretleri programlara
    # bağlarken hiyerarşinin kurulmuş olması gerekir.
    if args.part3_dir.exists():
        _calistir(
            "4/6  data/ekdata/part3 derslik envanteri + eğitim ücretleri",
            [py, "import_part3.py", "--dir", str(args.part3_dir)],
        )
    else:
        print(f"\nATLANDI: {args.part3_dir} bulunamadı (part3 opsiyoneldir).")

    # Yabancı öğrenci sayıları (2025-2026). EN SONA konur: satırlar
    # fakülte/bölüm/program kimliklerine bağlanır, dolayısıyla hiyerarşi
    # bu noktada tam kurulmuş olmalıdır. Dosya yoksa adım atlanır.
    if args.foreign_file.exists():
        _calistir(
            "5/6  yabancı öğrenci sayıları (2025-2026)",
            [py, "import_foreign_students.py", "--file", str(args.foreign_file)],
        )
    else:
        print(f"\nATLANDI: {args.foreign_file} bulunamadı "
              "(yabancı öğrenci dosyası opsiyoneldir).")

    # Ankara YÖK Atlas EN SONDA ve AYRI tabloda yüklenir. Bu sıra,
    # ABÜ'nin daha önce yüklenmiş yetkili ÖSYM/YKS değerlerini önce
    # görüp çakışmaları "kept_existing" olarak kaydetmesini sağlar.
    if args.yok_atlas_dir.exists():
        atlas = [
            py,
            "import_yok_atlas_ankara.py",
            "--source-dir",
            str(args.yok_atlas_dir),
        ]
        if args.purge:
            atlas.append("--purge")
        _calistir(
            "6/6  Ankara YÖK Atlas 2022-2024 ikincil karşılaştırma verisi",
            atlas,
        )
    else:
        print(f"\nATLANDI: {args.yok_atlas_dir} bulunamadı "
              "(YÖK Atlas ikincil kaynağı opsiyoneldir).")

    print("\n" + "=" * 68)
    print("TÜM GERÇEK VERİ YÜKLENDİ")
    print("=" * 68)
    print("Demo/örnek veri YÜKLENMEDİ. Örnek veri yalnızca")
    print("`python seed_all_demo_data.py` ile, bilinçli olarak yüklenir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
