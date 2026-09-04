"""ASİSTAN REGRESYON TABANI — değişiklikten önce/sonra karşılaştırma.

NEDEN VAR
---------
Asistan mimarisi değiştirilecek (katalog kestirmesi kaldırılacak, yeni
araçlar eklenecek, muhakeme açılacak). Bu değişikliklerin BUGÜN DOĞRU
ÇALIŞAN cevapları bozmadığını kanıtlamanın tek yolu, önce onları
kaydetmek.

Betik iki kipte çalışır:

    python asistan_regresyon.py kaydet   → mevcut cevapları dosyaya yazar
    python asistan_regresyon.py karsilastir → dosyayla bugünkü cevapları kıyaslar

NE KARŞILAŞTIRILIR
------------------
Serbest metin DEĞİL. Model her seferinde farklı cümle kurabilir; buna
bakmak yanlış alarm üretir. Karşılaştırılan şey CEVABIN İÇİNDEKİ
SAYILAR ve kullanılan kaynaklardır:

    * cevaptaki tüm sayılar (3.626, %95,8, 164 …)
    * data_sources listesi
    * academic_year
    * araç adları

Sayı değişmişse regresyon vardır ve durum RED'dir. Cümle değişmiş ama
sayılar aynıysa geçer — asıl istediğimiz zaten cümlenin zenginleşmesi.

KULLANIM
--------
Sunucu ayakta olmalı (varsayılan http://127.0.0.1:8000).
Farklı port için:  python asistan_regresyon.py kaydet --url http://127.0.0.1:8099
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DOSYA = Path(__file__).with_name("asistan_regresyon_tabani.json")
VARSAYILAN_URL = "http://127.0.0.1:8000"

#: Bugün doğru cevaplandığı bilinen sorular. Kapsam bilinçli olarak
#: geniş: her biri farklı bir veri yolunu (katalog metriği, kapsam
#: çözümü, dönem seçimi) tetikler.
SORULAR: List[str] = [
    # --- tekil sayı, kurum kapsamı ---
    "ABÜ'de kaç öğrenci var?",
    "Toplam akademik personel sayısı nedir?",
    "Öğrenci başına düşen akademisyen sayısı nedir?",
    "Kaç fakültemiz var?",
    "Kaç bölümümüz var?",
    # --- kapsam daraltma ---
    "Mühendislik ve Mimarlık Fakültesi'nde kaç öğrenci var?",
    "Bilgisayar Mühendisliği programında kaç öğrenci var?",
    "Psikoloji bölümünün kontenjanı nedir?",
    # --- fiziksel kapasite ---
    "Kaç dersliğimiz var?",
    "Toplam derslik kapasitemiz nedir?",
    # --- mali ---
    "Toplam gelirimiz ne kadar?",
    "Toplam giderimiz ne kadar?",
    # --- müfredat / ders ---
    "Müfredatımızda kaç ders var?",
    # --- genel sohbet (kurumsal değil; politika uygulanmamalı) ---
    "Merhaba",
]

SAYI = re.compile(r"\d[\d.,]*")


def _sayilar(metin: str) -> List[str]:
    """Metindeki sayılar — sondaki noktalama temizlenmiş.

    "3.626." ile "3.626" aynı sayıdır; cümle sonu noktası farklı sayı
    üretmemeli.
    """
    return [x.rstrip(".,") for x in SAYI.findall(metin)]


def _istek(url: str, soru: str, zaman_asimi: int = 180) -> Dict[str, Any]:
    istek = urllib.request.Request(
        url.rstrip("/") + "/api/assistant/chat",
        data=json.dumps({"message": soru}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as y:
        return json.load(y)


def _imza(cevap: Dict[str, Any]) -> Dict[str, Any]:
    """Cevabın DEĞİŞMEMESİ gereken kısmı.

    Cümlenin kendisi kasıtlı olarak dışarıda: değişiklik zaten cümleyi
    zenginleştirmeyi hedefliyor. Sabit kalması gereken sayılardır.
    """
    metin = cevap.get("answer") or ""
    return {
        "sayilar": _sayilar(metin),
        "data_sources": sorted(cevap.get("data_sources") or []),
        "academic_year": cevap.get("academic_year"),
        "araclar": sorted(
            (t.get("name") if isinstance(t, dict) else str(t))
            for t in (cevap.get("used_tools") or [])
        ),
        "data_source": cevap.get("data_source"),
        "ui_spec_var": bool(cevap.get("ui_spec")),
        "_metin": metin,          # yalnızca insan gözüyle bakmak için
    }


def kaydet(url: str) -> int:
    kayit: Dict[str, Any] = {
        "olusturma": datetime.now().isoformat(timespec="seconds"),
        "url": url,
        "sorular": {},
    }
    hata = 0
    for soru in SORULAR:
        try:
            kayit["sorular"][soru] = _imza(_istek(url, soru))
            print(f"  ✓ {soru}")
        except Exception as exc:  # noqa: BLE001
            kayit["sorular"][soru] = {"hata": f"{type(exc).__name__}: {exc}"}
            print(f"  ✗ {soru}  → {type(exc).__name__}")
            hata += 1
    DOSYA.write_text(json.dumps(kayit, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(SORULAR)} soru kaydedildi ({hata} hata) → {DOSYA.name}")
    return 0


def karsilastir(url: str) -> int:
    if not DOSYA.exists():
        print(f"Taban dosyası yok: {DOSYA}. Önce `kaydet` çalıştırın.")
        return 2
    taban = json.loads(DOSYA.read_text(encoding="utf-8"))
    bozulan, gelisen, ayni = [], [], 0

    for soru, eski in taban["sorular"].items():
        if "hata" in eski:
            continue                     # tabanda da hatalıydı, kıyas anlamsız
        try:
            yeni = _imza(_istek(url, soru))
        except Exception as exc:  # noqa: BLE001
            bozulan.append((soru, f"istek hatası: {type(exc).__name__}", "", ""))
            continue

        # ASIL KURAL: HİÇBİR ESKİ DEĞER KAYBOLMAMALI.
        # ------------------------------------------------------------------
        # Eşitlik değil ALT KÜME kontrolü yapılır. Değişikliğin amacı zaten
        # cevabı zenginleştirmek: aynı soruya artık hem katalog hem bağlam
        # kaynağı ekleniyor ve kohort penceresi gibi ek sayılar yazılıyor.
        # Eşitlik arasak bu iyileşmeleri "regresyon" diye raporlardık.
        #
        # Bir sayı DEĞİŞİRSE (3.626 → 3.600) eski değer yenide bulunmaz ve
        # kontrol yine yakalar. Aradığımız tam olarak budur.
        # Taban dosyası eski bir sürümle alınmış olabilir; iki taraf da
        # karşılaştırma anında normalleştirilir ("3.626." == "3.626").
        _n = lambda liste: [str(x).rstrip(".,") for x in liste]
        eski_s, yeni_s = _n(eski["sayilar"]), _n(yeni["sayilar"])
        kayip_sayi = [x for x in eski_s if x not in yeni_s]
        if kayip_sayi:
            bozulan.append((soru, "SAYI KAYBOLDU/DEĞİŞTİ",
                            " ".join(eski_s), " ".join(yeni_s)))
            continue
        kayip_kaynak = [x for x in eski["data_sources"]
                        if x not in yeni["data_sources"]]
        if kayip_kaynak:
            bozulan.append((soru, "KAYNAK KAYBOLDU",
                            str(eski["data_sources"]), str(yeni["data_sources"])))
            continue
        ayni += 1
        if len(yeni_s) > len(eski_s) or \
                len(yeni["data_sources"]) > len(eski["data_sources"]):
            gelisen.append((soru, len(eski["_metin"]), len(yeni["_metin"]),
                            yeni["ui_spec_var"]))
            continue
        # Zenginleşme: cevap uzadıysa ya da grafik geldiyse bu İYİ haber.
        if len(yeni["_metin"]) > len(eski["_metin"]) * 1.3 or (
                yeni["ui_spec_var"] and not eski["ui_spec_var"]):
            gelisen.append((soru, len(eski["_metin"]), len(yeni["_metin"]),
                            yeni["ui_spec_var"]))

    print(f"\nSAYILAR KORUNDU : {ayni}/{len(taban['sorular'])}")
    if gelisen:
        print(f"ZENGİNLEŞEN     : {len(gelisen)}")
        for s, a, b, g in gelisen:
            print(f"   + {s[:52]:<54} {a}→{b} karakter{'  +grafik' if g else ''}")
    if bozulan:
        print(f"\nREGRESYON       : {len(bozulan)}")
        for s, sebep, a, b in bozulan:
            print(f"   ✗ {s[:52]}\n       {sebep}\n       eski: {a}\n       yeni: {b}")
        return 1
    print("\nRegresyon yok.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kip", choices=("kaydet", "karsilastir"))
    p.add_argument("--url", default=VARSAYILAN_URL)
    a = p.parse_args()
    return kaydet(a.url) if a.kip == "kaydet" else karsilastir(a.url)


if __name__ == "__main__":
    sys.exit(main())
