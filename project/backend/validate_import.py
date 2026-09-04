#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Yükleme öncesi YEREL doğrulama aracı (salt okunur).

NE İŞE YARAR
------------
Bir CSV/XLSX dosyasını sunucuya yüklemeden ÖNCE, dosyanın sistemin beklediği
sütun adlarıyla (snake_case İngilizce: name/code/faculty_code…) ve tiplerle
yazılıp yazılmadığını yerelde kontrol eder. Böylece "önizleme" denemesi boşa
gitmez. Hiçbir HTTP isteği atmaz, FastAPI başlatmaz.

TEK YETKİLİ TANIM — KOPYALAMA YOK
---------------------------------
Bu araç, doğrulama kurallarının KENDİ KOPYASINI TUTMAZ. Kurallar doğrudan
sunucunun kullandığı modülden alınır:

    app.services.import_validators.RESOURCE_SPECS   (kaynak tanımları)
    app.services.import_validators.validate_row     (satır doğrulama)
    app.services.file_parser.parse_file             (dosya okuma)

Bu bilinçli bir tercihtir. Ekipten gelen ilk sürüm RESOURCE_SPECS'in
sadeleştirilmiş bir KOPYASINI içeriyordu; sunucu tarafında bir kural
değiştiğinde (ör. faculties kaynağına `unit_type` eklenmesi) kopya sessizce
eskiyor ve araç "temiz" derken sunucu hata veriyor olurdu. Tek tanım
olduğunda böyle bir ayrışma yapısal olarak imkânsızdır.

SALT OKUNUR
-----------
Veritabanına YAZMAZ. `--db` verilirse veritabanını yalnızca `mode=ro` ile
açar ve üst kayıt (faculty_code/department_code) ile kod çakışması kontrolü
için SELECT çalıştırır. Kayıt eklemez, güncellemez, silmez, migration
çalıştırmaz.

KULLANIM
--------
    python validate_import.py faculties  faculties_yeni_birimler.csv
    python validate_import.py departments departments_yeni_bolumler.csv
    python validate_import.py programs   programs.xlsx

    # Üst kayıt ve kod çakışmasını canlı veritabanına karşı da denetle:
    python validate_import.py departments dosya.csv --db university_management.db

Çıkış kodu: 0 = HATA yok (yüklemeye hazır), 1 = en az bir HATA var.
Uyarılar (çakışma/tekrar) hata sayılmaz, ayrıca raporlanır.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Bu betik backend kökünde durur; `app` paketini içe aktarabilmesi için
# kendi dizinini yola ekler (uvicorn ile aynı çalışma dizini varsayımı).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.file_parser import parse_file  # noqa: E402
from app.services.import_validators import (  # noqa: E402
    RESOURCE_SPECS,
    validate_row,
)

#: resource_type -> gerçek tablo adı. Model üzerinden okunur; elle yazılmaz,
#: böylece bir model tablo adını değiştirirse burası kendiliğinden uyar.
def _table_name(resource_type: str) -> str:
    return RESOURCE_SPECS[resource_type].model.__tablename__


def _read_rows(path: Path) -> List[Dict[str, Any]]:
    """Dosyayı SUNUCUNUN parser'ıyla okur.

    Aynı normalizasyon (sütun adı küçültme, boşluk/tire -> alt çizgi) burada
    da geçerli olsun diye ayrı bir okuyucu yazılmamıştır.
    """
    content = path.read_bytes()
    _file_type, rows = parse_file(path.name, content)
    return rows


def _existing_codes(db_path: Optional[str], table: str,
                    column: str = "code") -> Optional[Set[str]]:
    """Tablodaki mevcut kodlar. Veritabanı SALT OKUNUR açılır."""
    if not db_path:
        return None
    if not Path(db_path).exists():
        raise SystemExit(f"Veritabanı bulunamadı: {db_path}")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(f"SELECT {column} FROM {table}").fetchall()
        return {str(r[0]).strip().upper() for r in rows if r[0] is not None}
    finally:
        con.close()


def validate(resource_type: str, path: Path, db_path: Optional[str]) -> int:
    spec = RESOURCE_SPECS[resource_type]
    rows = _read_rows(path)
    if not rows:
        print("UYARI: dosyada veri satırı bulunamadı.")
        return 0

    print(f"Kaynak      : {resource_type} ({spec.label})")
    print(f"Dosya       : {path.name}")
    print(f"Satır sayısı: {len(rows)}")
    print(f"Beklenen sütunlar: {spec.columns}")
    print(f"Zorunlu sütunlar : {spec.required}")

    dosya_sutunlari = set(rows[0].keys())
    eksik = [c for c in spec.required if c not in dosya_sutunlari]
    if eksik:
        print(f"\nHATA: zorunlu sütun(lar) dosyada hiç yok: {eksik}")
        print(f"   Dosyadaki sütunlar: {sorted(dosya_sutunlari)}")
        return 1
    taninmayan = sorted(dosya_sutunlari - set(spec.columns))
    if taninmayan:
        print(f"BİLGİ: tanınmayan (yok sayılacak) sütunlar: {taninmayan}")

    mevcut_kodlar = _existing_codes(db_path, _table_name(resource_type))
    ust_kodlar: Dict[str, Optional[Set[str]]] = {}
    for parent in spec.parents:
        ust_kodlar[parent.lookup_column] = _existing_codes(
            db_path, parent.model.__tablename__, parent.key_column)

    hata_sayisi = 0
    uyari_sayisi = 0
    dosyadaki_kodlar: Dict[str, int] = {}
    print()

    for i, row in enumerate(rows, start=1):
        cleaned, issues = validate_row(spec, row)

        for field, value, message in issues:
            hata_sayisi += 1
            print(f"HATA  satır {i:>3} [{field}={value!r}]: {message}")

        # Dosya İÇİ tekrar eden kod
        kod = str(cleaned.get("code", "") or "").strip().upper()
        if kod:
            if kod in dosyadaki_kodlar:
                uyari_sayisi += 1
                print(f"UYARI satır {i:>3}: '{kod}' kodu dosyada "
                      f"{dosyadaki_kodlar[kod]}. satırda da var (tekrar).")
            else:
                dosyadaki_kodlar[kod] = i
            # Veritabanında zaten var mı
            if mevcut_kodlar is not None and kod in mevcut_kodlar:
                uyari_sayisi += 1
                print(f"UYARI satır {i:>3}: '{kod}' kodu veritabanında "
                      f"ZATEN VAR (çakışma olarak işaretlenecek).")

        # Üst kayıt gerçekten var mı
        for parent in spec.parents:
            ham = str(row.get(parent.lookup_column, "") or "").strip().upper()
            kume = ust_kodlar.get(parent.lookup_column)
            if ham and kume is not None and ham not in kume:
                hata_sayisi += 1
                print(f"HATA  satır {i:>3}: {parent.label} kodu '{ham}' "
                      f"veritabanında bulunamadı ({parent.lookup_column}).")

        # faculties: çözülen birim türünü göster (sessiz FACULTY sürprizi olmasın)
        if spec.auto_classify_unit_type and "unit_type" in cleaned:
            ham_ut = str(row.get("unit_type", "") or "").strip()
            kaynak = "dosyadan" if ham_ut else "isimden türetildi"
            print(f"      satır {i:>3}: {cleaned.get('code')} -> "
                  f"unit_type={cleaned['unit_type']} ({kaynak})")

    print()
    print(f"SONUÇ: {hata_sayisi} hata, {uyari_sayisi} uyarı, {len(rows)} satır.")
    if hata_sayisi == 0:
        print("Dosya yüklemeye hazır görünüyor (uyarılar çakışma bilgisidir).")
    return 1 if hata_sayisi else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Yükleme öncesi yerel doğrulama (salt okunur; veritabanına yazmaz).",
        epilog="Kurallar app/services/import_validators.py'den okunur; kopya tutulmaz.",
    )
    ap.add_argument("resource_type", choices=sorted(RESOURCE_SPECS),
                    help="Doğrulanacak kaynak türü")
    ap.add_argument("file", type=Path, help="CSV veya XLSX dosyası")
    ap.add_argument("--db", default=None,
                    help="Üst kayıt / kod çakışması kontrolü için SQLite yolu "
                         "(salt okunur açılır)")
    args = ap.parse_args()

    if not args.file.exists():
        raise SystemExit(f"Dosya bulunamadı: {args.file}")
    return validate(args.resource_type, args.file, args.db)


if __name__ == "__main__":
    raise SystemExit(main())
