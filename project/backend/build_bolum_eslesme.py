"""Bölüm eşleştirme filtresinin kaynağını Excel'den türetir.

NE ÜRETİR
---------
`data/bolum_eslesme/bolum_eslesme.csv` — dört sütunlu küçük bir arama
tablosu:

    abu_program_key, peer_program_key, relation, peer_university

Bu dosya `Aynı Bölümler` / `Benzer Bölümler` süzgecinin TEK yetkili
kaynağıdır.

NEDEN ARA BİR DOSYA
-------------------
Excel'i her HTTP isteğinde açmak kabul edilemez: bir açılır menü
değişimi bile çalışma kitabını baştan ayrıştırmayı gerektirirdi.
Alternatif olarak Excel'i sürece bir kez yükleyip bellekte tutmak da
mümkündü ama o zaman kaynak dosya çalışma zamanında da gerekli olurdu;
`team_changes/` bir teslimat klasörü, çalışma zamanı bağımlılığı değil.

Türetilmiş dosya küçük (birkaç yüz satır), sürüm kontrolüne girebilir
ve `data/` altındaki diğer türetilmiş kaynaklarla aynı yerde durur.

YALNIZCA EŞLEŞTİRME SÜTUNLARI ALINIR
------------------------------------
Excel'de kontenjan, yerleşen, taban puan, başarı sırası, burs türü,
öğretim dili gibi sütunlar da var. HİÇBİRİ ALINMAZ. Bu dosya bir
ÖLÇÜM kaynağı değil, bir İLİŞKİ kaynağıdır: "hangi programlar
karşılaştırmaya girsin" sorusunu cevaplar. Grafiklerdeki sayılar
eskisi gibi canonical veritabanından gelir.

İLİŞKİYİ EXCEL BELİRLER
-----------------------
Kaynağın kendi `Metadata` sayfası iki sınıfı şöyle tanımlıyor:

  AYNI   YÖK'ün kendi `birimGrupAdi` alanı. İki program aynı bölüm
         grubundaysa aynıdır. Kaynağın sınıflandırması, metin
         benzerliği değil.
  BENZER Her ABÜ bölümü için ELLE tanımlanmış anahtar kelimeler
         (örn. Bilgisayar Mühendisliği → "yazılım mühendis").

İki sınıf iki AYRI sayfada; bu betik onları birleştirmez, ayrı tutar.

KULLANIM
--------
    python build_bolum_eslesme.py

Deterministiktir: aynı Excel'den her seferinde aynı satırlar, aynı
sırayla üretilir. Kaynak Excel OKUNUR, asla değiştirilmez.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))

from app.services.program_equivalence import canonical_program_key  # noqa: E402

#: Kaynak Excel — SALT OKUNUR.
KAYNAK_ADI = "Ankara_Bilim_Ayni_Benzer_Bolumler_TAM.xlsx"

#: Üretilecek arama tablosu (çalışma zamanı bunu okur).
CIKTI = KOK.parent / "data" / "bolum_eslesme" / "bolum_eslesme.csv"

#: İnceleme gerektiren satırlar (çelişki vb.).
INCELEME = CIKTI.parent / "bolum_eslesme_inceleme.csv"

SAYFA_AYNI = "Aynı Bölümler"
SAYFA_BENZER = "Benzer Bölümler"

ILISKI_AYNI = "same"
ILISKI_BENZER = "similar"


def kaynagi_bul() -> Optional[Path]:
    """Yetkili Excel'i yukarı doğru arar.

    İki yerleşim desteklenir:
      * TESLİM PAKETİ — `data_sources/department_matching/`
      * GELİŞTİRME DEPOSU — `team_changes/newdata/filtre/`

    Teslim paketi kendi kendine yeter: geliştirme deposunun klasör
    düzenine ihtiyaç duymaz. İkisi de aranır ki betik her iki ortamda
    da çalışsın.
    """
    goreli = (
        ("data_sources", "department_matching"),
        ("team_changes", "newdata", "filtre"),
    )
    for ata in [KOK, *KOK.parents]:
        for parcalar in goreli:
            aday = ata.joinpath(*parcalar) / KAYNAK_ADI
            if aday.is_file():
                return aday
    return None


def _metin(v) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _kod(v) -> Optional[str]:
    s = _metin(v)
    if not s:
        return None
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


def _satirlari_cikar(df: pd.DataFrame, program_sutunu: str,
                     iliski: str) -> List[Dict[str, str]]:
    """Bir sayfadan yalnızca EŞLEŞTİRME sütunlarını okur."""
    cikan: List[Dict[str, str]] = []
    for _, r in df.iterrows():
        abu = _metin(r.get("abu_bolumu"))
        peer_ad = _metin(r.get(program_sutunu))
        uni = _metin(r.get("universite"))
        if not (abu and peer_ad and uni):
            continue

        # Kanonik anahtarlar PROJENİN KENDİ kurallarıyla üretilir.
        # Kendi normalizasyonumu yazsaydım Excel tarafı ile veritabanı
        # tarafı farklı anahtar üretir ve hiçbir şey eşleşmezdi.
        abu_key = canonical_program_key(abu)
        peer_key = canonical_program_key(peer_ad)
        if not (abu_key and peer_key):
            continue

        cikan.append({
            "abu_program_key": abu_key,
            "peer_program_key": peer_key,
            "relation": iliski,
            "peer_university": uni,
            # Program kodu KİMLİK olarak taşınır: aynı anahtara düşen
            # burs/dil varyantlarını ayırt etmeye ve kaynağa geri
            # dönmeye yarar. Ölçüm DEĞİLDİR.
            "peer_program_code": _kod(r.get("program_kodu")) or "",
        })
    return cikan


def uret() -> int:
    kaynak = kaynagi_bul()
    if kaynak is None:
        print(f"Kaynak bulunamadı. Aranan yerler:\n"
              f"  …/data_sources/department_matching/{KAYNAK_ADI}\n"
              f"  …/team_changes/newdata/filtre/{KAYNAK_ADI}")
        return 2

    xl = pd.ExcelFile(kaynak)
    eksik = [s for s in (SAYFA_AYNI, SAYFA_BENZER) if s not in xl.sheet_names]
    if eksik:
        print(f"Beklenen sayfa yok: {eksik} — bulunanlar: {xl.sheet_names}")
        return 2

    ham = (_satirlari_cikar(xl.parse(SAYFA_AYNI), "program_adi", ILISKI_AYNI)
           + _satirlari_cikar(xl.parse(SAYFA_BENZER), "benzer_program",
                              ILISKI_BENZER))

    # TEKİLLEŞTİRME.
    # Excel program-varyantı düzeyinde: aynı bölüm çifti burslu/ücretli/
    # İngilizce satırlarıyla birkaç kez geçer. Süzgeç için ilişki BÖLÜM
    # düzeyinde anlamlıdır; varyantlar aynı satıra düşer ve arayüzde
    # tek seri üretir.
    # ÜNİVERSİTE ANAHTARIN PARÇASIDIR.
    # İlk sürümde anahtar (abu, peer, ilişki) üçlüsüydü ve "Bilgisayar
    # Mühendisliği" gibi bir bölüm ONLARCA üniversitede aynı kanonik
    # anahtara düştüğü için hepsi TEK satıra iniyordu: 373 "aynı"
    # satırı 25'e düşüyor, hangi kurumda bulunduğu kayboluyordu.
    tekil: Dict[Tuple[str, str, str, str], Dict[str, str]] = {}
    for s in ham:
        anahtar = (s["abu_program_key"], s["peer_program_key"],
                   s["relation"], s["peer_university"])
        tekil.setdefault(anahtar, s)

    # ÇELİŞKİ: aynı çift hem "same" hem "similar" ise.
    # Aynı (ABÜ bölümü, kurum, peer bölüm) üçlüsü iki farklı sınıfta
    # görünüyorsa çelişki vardır.
    ciftler = Counter((s["abu_program_key"], s["peer_university"],
                       s["peer_program_key"]) for s in tekil.values())
    celiskili = {c for c, n in ciftler.items() if n > 1}

    satirlar = sorted(
        tekil.values(),
        key=lambda s: (s["abu_program_key"], s["relation"],
                       s["peer_university"], s["peer_program_key"]))

    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    alanlar = ["abu_program_key", "peer_program_key", "relation",
               "peer_university", "peer_program_code"]
    with open(CIKTI, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=alanlar)
        w.writeheader()
        w.writerows(satirlar)

    inceleme = [
        {"abu_program_key": a, "peer_university": u, "peer_program_key": p,
         "sebep": "aynı üçlü hem 'same' hem 'similar' olarak geçiyor",
         "karar": "kaynağın sınıflandırması korundu; ikisi de listede"}
        for a, u, p in sorted(celiskili)
    ]
    if inceleme:
        with open(INCELEME, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(inceleme[0]))
            w.writeheader()
            w.writerows(inceleme)

    ayni = sum(1 for s in satirlar if s["relation"] == ILISKI_AYNI)
    benzer = len(satirlar) - ayni
    print(f"Kaynak   : {kaynak.name}")
    print(f"Çıktı    : {CIKTI.relative_to(KOK.parent)}")
    print(f"ABÜ bölümü: {len({s['abu_program_key'] for s in satirlar})}")
    print(f"AYNI      : {ayni}")
    print(f"BENZER    : {benzer}")
    print(f"Ham satır : {len(ham)} → tekil {len(satirlar)}")
    print(f"Çelişkili çift: {len(celiskili)}"
          + (f"  (bkz. {INCELEME.name})" if celiskili else ""))
    return 0


if __name__ == "__main__":
    sys.exit(uret())
