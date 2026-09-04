"""Merkezi veri tabanı `abu_kds.db` — SALT OKUNUR erişim.

NE
--
Ekip, `data_sources/` altındaki bütün veriyi (24 Excel + 9 CSV + 3 PDF kat
planı + 2 metin belgesi) tek bir SQLite dosyasında birleştirdi:

    62 tablo · 36.020 satır · 6,7 MB

Asistanın kurumsal soruları buradan cevaplanır. Bu modül o dosyaya
erişimin TEK kapısıdır.

NEDEN AYRI BİR MODÜL
--------------------
Uygulamanın kendi veritabanı (`university_management.db`) SQLAlchemy
oturumuyla yönetiliyor ve YAZILABİLİR. `abu_kds.db` ise bir KAYNAK
dosyasıdır: değiştirilmez, taşınmaz, migrate edilmez. İkisini aynı
oturumdan geçirmek, bir gün birinin diğerine yazmasını mümkün kılardı.
Burada bağlantı `mode=ro` ile açılır — yazma girişimi SQLite düzeyinde
imkânsızdır, koda güvenmek gerekmez.

AD ÇAKIŞMASI ÖLÇÜLDÜ
--------------------
İki veritabanında aynı adı taşıyan bir tablo var: `curriculum_courses`.
Bu yüzden dışarıya açılan kaynak adları `kds_` önekiyle verilir
(`kds_occupancy_by_year`). Önek olmasaydı model hangi tabloyu
kastettiğini söyleyemez, sessizce yanlış kaynağı okurdu.

GÜVENLİK
--------
Modele serbest SQL yetkisi VERİLMEZ. Dışarıya açılan tek sorgu yolu
`satirlar()` fonksiyonudur ve şunları uygular: yalnızca SELECT, yalnızca
katalogdaki tablolar, sütun adları şemaya karşı doğrulanır, değerler
parametre olarak bağlanır, satır sayısı sınırlıdır. Çok ifadeli sorgu,
PRAGMA ve yazma ifadeleri bu yoldan geçemez çünkü SQL metnini model
değil bu modül kurar.
"""

from __future__ import annotations

import logging
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: Dışarıya açılan kaynak adlarının öneki (ad çakışması için).
ONEK = "kds_"

#: Tek sorguda dönebilecek en fazla satır. Model bağlamına 36 bin satır
#: basmanın anlamı yok; asıl iş sorgunun kendisinde daraltmaktır.
EN_FAZLA_SATIR = 200

#: Katalog tabloları — veri değil, verinin kendisi hakkında bilgi.
#: `_documents` uzun metinler taşır; sorgu sonucuna karışmasın diye
#: kaynak listesinde gösterilmez, ama aranabilir kalır.
META_TABLOLAR = ("_tables", "_source_metadata", "_documents")


# ---------------------------------------------------------------------------
# Bağlantı
# ---------------------------------------------------------------------------
def _aday_yollar() -> List[Path]:
    """Ayar boşsa denenecek proje-göreli konumlar."""
    burasi = Path(__file__).resolve()
    adaylar: List[Path] = []
    for ata in burasi.parents:
        adaylar.append(ata / "data" / "abu_kds" / "abu_kds.db")
        adaylar.append(ata / "data_sources" / "database" / "abu_kds.db")
    return adaylar


@lru_cache(maxsize=1)
def veritabani_yolu() -> Optional[Path]:
    """Dosyanın yeri. Bulunamazsa `None` — istisna atılmaz.

    Veritabanı yoksa asistan çalışmaya devam etmeli, yalnızca bu kaynak
    listede görünmemeli. Açılışta istisna atmak, dosyayı henüz almamış
    bir geliştiricide bütün uygulamayı düşürürdü.
    """
    from app.core.config import settings
    ayar = (getattr(settings, "ABU_KDS_DB_PATH", "") or "").strip()
    if ayar:
        yol = Path(ayar)
        if not yol.is_absolute():
            # Göreli yol PROJE KÖKÜNE göre çözülür, çalışma dizinine
            # göre değil: sunucu nereden başlatılırsa başlatılsın aynı
            # dosya bulunur.
            for ata in Path(__file__).resolve().parents:
                aday = ata / yol
                if aday.is_file():
                    return aday
        elif yol.is_file():
            return yol
        logger.warning("ABU_KDS_DB_PATH verildi ama dosya yok: %s", ayar)

    for aday in _aday_yollar():
        if aday.is_file():
            return aday
    return None


def kullanilabilir() -> bool:
    return veritabani_yolu() is not None


def _baglan() -> sqlite3.Connection:
    """SALT OKUNUR bağlantı.

    `mode=ro` bir tercih değil, güvencedir: bu tanıtıcı üzerinden INSERT,
    UPDATE, DELETE ya da şema değişikliği SQLite tarafından reddedilir.
    """
    yol = veritabani_yolu()
    if yol is None:
        raise FileNotFoundError(
            "abu_kds.db bulunamadı. Dosyayı integration/data/abu_kds/ "
            "altına koyun ya da ABU_KDS_DB_PATH ayarını verin.")
    con = sqlite3.connect(f"file:{yol.as_posix()}?mode=ro",
                          uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _sema() -> Dict[str, List[str]]:
    """gerçek tablo adı → sütunlar. Meta tablolar hariç."""
    if not kullanilabilir():
        return {}
    with _baglan() as con:
        tablolar = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {t: [c[1] for c in con.execute(f"PRAGMA table_info([{t}])")]
                for t in tablolar if t not in META_TABLOLAR}


@lru_cache(maxsize=1)
def _katalog() -> Dict[str, Dict[str, Any]]:
    """`_tables` kataloğu: tablo → kategori, kaynak dosya, satır sayısı, not.

    Veritabanı kendi kendini anlatıyor; bu bilgi "bu sayı nereden geldi"
    sorusunu cevaplamak için modele de aktarılır.
    """
    if not kullanilabilir():
        return {}
    with _baglan() as con:
        try:
            satirlar = con.execute("SELECT * FROM _tables").fetchall()
        except sqlite3.Error:
            return {}
        return {r["table_name"]: dict(r) for r in satirlar}


def _gercek_ad(kaynak: str) -> Optional[str]:
    """Dışarıya açılan kaynak adını gerçek tablo adına çevirir."""
    if not kaynak.startswith(ONEK):
        return None
    ad = kaynak[len(ONEK):]
    return ad if ad in _sema() or ad in TURETILMIS else None


# ---------------------------------------------------------------------------
# TÜRETİLMİŞ GÖRÜNÜMLER — çok tablolu birleştirmeler
# ---------------------------------------------------------------------------
# NEDEN GEREKLİ
# -------------
# Bazı sorular tek tabloda cevaplanmıyor ve birleştirmeyi modelin kendi
# bulması gerçekçi değil. Ölçülen örnek:
#
#   "Ankara'daki son 5 yıldaki en düşük mühendislik taban puanı olan
#    üniversiteler nelerdir?"
#
# Taban puan beş yıl için ÜÇ ayrı tabloda ve ÜÇ ayrı sütun adıyla
# duruyor: 2021 `yks_ankara_2021.puan`, 2022 `yks_ankara_2022.puan`,
# 2023-2025 `yks_ankara_history_2023_2025.base_score`. Model bunu
# keşfetmek için en az üç tur harcar ve büyük ihtimalle bulamaz — bu
# sorunun daha önce fallback'e düşmesinin sebebi tam olarak buydu.
#
# Çözüm, veritabanına VIEW yazmak DEĞİL (dosya salt okunur ve öyle
# kalmalı), sorguyu burada bir kez doğru kurmaktır. Sonuç yine gerçek
# veridir; hiçbir sayı türetilmez, yalnızca üç kaynak tek eksende
# hizalanır.
#
# `onlisans_mi = 0`: önlisans programları lisans taban puanlarıyla aynı
# ölçekte değil; karıştırılırsa "en düşük" listesi anlamını yitirir.
TURETILMIS: Dict[str, Dict[str, Any]] = {
    "yks_ankara_taban_puan_5yil": {
        "aciklama": (
            "Ankara üniversitelerinin 2021-2025 lisans taban puanları, üç "
            "kaynak tablodan tek eksende birleştirilmiş "
            "(2021 ve 2022: yks_ankara_2021/2022.puan; "
            "2023-2025: yks_ankara_history_2023_2025.base_score)."),
        "sutunlar": ["academic_year", "university_name", "program_name",
                     "faculty", "base_score", "quota", "source_table"],
        "sql": """
            SELECT 2021 AS academic_year, universite AS university_name,
                   program_adi AS program_name, fakulte AS faculty,
                   puan AS base_score, kontenjan AS quota,
                   'yks_ankara_2021' AS source_table
            FROM yks_ankara_2021
            WHERE puan IS NOT NULL AND onlisans_mi = 0
            UNION ALL
            SELECT 2022, universite, program_adi, fakulte, puan, kontenjan,
                   'yks_ankara_2022'
            FROM yks_ankara_2022
            WHERE puan IS NOT NULL AND onlisans_mi = 0
            UNION ALL
            SELECT academic_year, university_name, program_name, faculty,
                   base_score, quota, 'yks_ankara_history_2023_2025'
            FROM yks_ankara_history_2023_2025
            WHERE base_score IS NOT NULL
        """,
    },
}


# ---------------------------------------------------------------------------
# TÜRKÇE ARAMA KÖPRÜSÜ
# ---------------------------------------------------------------------------
# ÖLÇÜLEN ARIZA: kullanıcı ve model Türkçe düşünüyor, tablolar ve sütunlar
# İngilizce adlı. "öğrenci sayısı" araması `students_by_university_2020_2026`
# tablosunu BULAMIYORDU — veri elde dururken keşif boş dönüyor, model de
# "veri yok" diyordu. Aranan kelimeyle tablo adı arasındaki bu dil farkı,
# retrieval katmanının gerçek veriyi modele ulaştıramamasının başlıca
# sebebiydi.
#
# Çözüm sözlük değil, KATEGORİ köprüsü: `_tables.category` zaten her
# tabloyu bir veri ailesine bağlıyor. Aileye Türkçe karşılıklar yazmak,
# 62 tablonun tamamını tek yerden aranabilir kılar. Yeni bir tablo
# eklendiğinde burada bir şey yapmak gerekmez — kategorisi onu taşır.
KATEGORI_TERIMLERI: Dict[str, Tuple[str, ...]] = {
    "students": ("öğrenci", "ogrenci", "kayıtlı", "kayitli", "mezun",
                 "uyruk", "yabancı", "yabanci", "cinsiyet"),
    "academic_staff": ("akademisyen", "akademik", "kadro", "öğretim",
                       "ogretim", "personel", "profesör", "profesor",
                       "doçent", "docent", "araştırma görevlisi"),
    "yks": ("yks", "taban puan", "tabanpuan", "puan", "kontenjan",
            "yerleşen", "yerlesen", "doluluk", "tercih", "başarı sırası",
            "basari sirasi", "ösym", "osym", "yök atlas", "yok atlas",
            "program", "bölüm", "bolum", "üniversite", "universite"),
    "finance": ("ücret", "ucret", "fiyat", "burs", "gelir", "finans",
                "bütçe", "butce", "maliyet"),
    "infrastructure": ("derslik", "sınıf", "sinif", "amfi", "laboratuvar",
                       "lab", "kat", "mekân", "mekan", "altyapı", "altyapi",
                       "ders programı", "ders programi", "doluluk oranı"),
    "curriculum": ("müfredat", "mufredat", "ders", "course", "kredi"),
    "strategic": ("stratejik", "hedef", "kpi", "gösterge", "gosterge",
                  "amaç", "amac"),
    "department_matching": ("eşleşme", "eslesme", "benzer bölüm",
                            "aynı bölüm", "muadil", "karşılaştırılabilir"),
    "merge_reports": ("birleştirme", "birlestirme", "çelişki", "celiski",
                      "belirsiz"),
    "docs": ("belge", "doküman", "dokuman", "readme", "açıklama"),
}


def arama_etiketleri(kaynak: str) -> str:
    """Kaynağın Türkçe aranabilir etiketleri — tek metin olarak.

    Keşif aracı bu metinde de arar; böylece Türkçe bir soru İngilizce
    adlı tabloyu bulabilir.
    """
    kat = kategori(kaynak) or ""
    terimler = KATEGORI_TERIMLERI.get(kat, ())
    ad = _gercek_ad(kaynak) or ""
    return " ".join((kat, ad.replace("_", " "), *terimler))


# ---------------------------------------------------------------------------
# Dışarıya açılan yüzey
# ---------------------------------------------------------------------------
def kaynaklar() -> Dict[str, List[str]]:
    """Dışarıya açılan kaynak adı → sütunlar (önekli)."""
    cikti = {ONEK + t: list(k) for t, k in _sema().items()}
    for ad, tanim in TURETILMIS.items():
        cikti[ONEK + ad] = list(tanim["sutunlar"])
    return cikti


def kaynak_notu(kaynak: str) -> Optional[str]:
    """Kaynağın kökeni — "bu sayı nereden geldi" sorusunun cevabı."""
    ad = _gercek_ad(kaynak)
    if ad is None:
        return None
    if ad in TURETILMIS:
        return TURETILMIS[ad]["aciklama"]
    k = _katalog().get(ad)
    if not k:
        return None
    parca = [p for p in (k.get("source_file"), k.get("source_sheet")) if p]
    not_ = (k.get("note") or "").strip()
    metin = "Kaynak: " + " · ".join(parca) if parca else ""
    return (metin + (" — " + not_ if not_ else "")).strip() or None


def kategori(kaynak: str) -> Optional[str]:
    ad = _gercek_ad(kaynak)
    if ad is None:
        return None
    if ad in TURETILMIS:
        return "yks"
    return (_katalog().get(ad) or {}).get("category")


def satir_sayisi(kaynak: str) -> Optional[int]:
    ad = _gercek_ad(kaynak)
    if ad is None or ad in TURETILMIS:
        return None
    return (_katalog().get(ad) or {}).get("row_count")


def satirlar(kaynak: str, *, secilen: Optional[Sequence[str]] = None,
             kosullar: Optional[List[Tuple[str, str, Any]]] = None,
             sirala: Optional[str] = None, azalan: bool = False,
             sinir: int = 50) -> List[Dict[str, Any]]:
    """Tek bir kaynaktan satır getirir. SQL'i BU FONKSİYON kurar.

    `kosullar`: (sütun, operatör, değer) üçlüleri. Operatör yalnızca
    aşağıdaki kapalı kümeden olabilir; sütun adı şemaya karşı doğrulanır;
    değer PARAMETRE olarak bağlanır. Model bu üçlülerden fazlasını
    veremez, dolayısıyla SQL enjeksiyonu için bir yüzey kalmaz.
    """
    ad = _gercek_ad(kaynak)
    if ad is None:
        raise ValueError(f"Bilinmeyen kaynak: {kaynak!r}")

    sutunlar = kaynaklar()[ONEK + ad]
    gecerli_op = {"=", "!=", ">", ">=", "<", "<=", "LIKE", "IN"}

    def dogrula(s: str) -> str:
        if s not in sutunlar:
            raise ValueError(
                f"{kaynak} kaynağında {s!r} sütunu yok. "
                f"Mevcut sütunlar: {', '.join(sutunlar[:12])}")
        return s

    alanlar = ", ".join(f"[{dogrula(a)}]" for a in (secilen or [])) or "*"
    taban = (f"({TURETILMIS[ad]['sql']})" if ad in TURETILMIS else f"[{ad}]")

    parcalar: List[str] = []
    parametreler: List[Any] = []
    for sutun, op, deger in (kosullar or []):
        dogrula(sutun)
        op = op.upper().strip()
        if op not in gecerli_op:
            raise ValueError(f"Desteklenmeyen operatör: {op!r}")
        if op == "IN":
            liste = [d for d in (deger or [])][:50]
            if not liste:
                continue
            parcalar.append(
                f"[{sutun}] IN ({', '.join('?' for _ in liste)})")
            parametreler.extend(liste)
        else:
            parcalar.append(f"[{sutun}] {op} ?")
            parametreler.append(deger)

    sql = f"SELECT {alanlar} FROM {taban}"
    if parcalar:
        sql += " WHERE " + " AND ".join(parcalar)
    if sirala:
        # NULL'lar sona: "en düşük taban puan" sorusunda ölçülmemiş
        # kayıtların listenin başına gelmesi, veri yokluğunu en düşük
        # değer gibi gösterirdi.
        sql += (f" ORDER BY [{dogrula(sirala)}] IS NULL, [{dogrula(sirala)}]"
                + (" DESC" if azalan else " ASC"))
    sql += " LIMIT ?"
    parametreler.append(max(1, min(int(sinir), EN_FAZLA_SATIR)))

    with _baglan() as con:
        return [dict(r) for r in con.execute(sql, parametreler).fetchall()]


def yil_araligi(kaynak: str, yil_sutunu: str) -> Optional[Tuple[int, int]]:
    """Kaynağın GERÇEK yıl kapsaması — örneklemeyle değil, MIN/MAX ile.

    ÖLÇÜLEN ARIZA: kapsama ilk 200 satırdan tahmin ediliyordu.
    `occupancy_by_year` yıla göre sıralı olduğu için ilk 200 satırın
    hepsi 2021'di ve tablo "yalnızca 2021'i kapsıyor" görünüyordu. Beş
    yıllık bir soruda bu kaynak eleniyor, yerine tek yıllık tablolar
    seçiliyordu — çok kaynaklı toplama da bu yüzden hiç tetiklenmiyordu.

    Yıl iki biçimde saklanıyor: `2021` (tam sayı) ve `2020-2021` (metin).
    İkisi de aynı ölçeğe indirilir; yoksa kaynaklar karşılaştırılamaz.
    """
    ad = _gercek_ad(kaynak)
    if ad is None or yil_sutunu not in kaynaklar().get(ONEK + ad, []):
        return None
    taban = (f"({TURETILMIS[ad]['sql']})" if ad in TURETILMIS else f"[{ad}]")
    try:
        with _baglan() as con:
            satir = con.execute(
                f"SELECT MIN([{yil_sutunu}]) a, MAX([{yil_sutunu}]) b "
                f"FROM {taban}").fetchone()
    except sqlite3.Error:
        return None
    if not satir:
        return None
    import re as _re
    yillar = []
    for deger in (satir["a"], satir["b"]):
        yillar += [int(x) for x in _re.findall(r"(20\d\d)", str(deger or ""))]
    return (min(yillar), max(yillar)) if yillar else None


def belge_ara(terim: str, sinir: int = 3) -> List[Dict[str, Any]]:
    """`_documents` içinde metin arar (README ve özet belgeleri)."""
    if not kullanilabilir() or not (terim or "").strip():
        return []
    with _baglan() as con:
        try:
            satir = con.execute(
                "SELECT * FROM _documents WHERE content LIKE ? LIMIT ?",
                (f"%{terim}%", max(1, min(sinir, 5)))).fetchall()
        except sqlite3.Error:
            return []
        return [{k: (str(v)[:1500] if k == "content" else v)
                 for k, v in dict(r).items()} for r in satir]


def ozet() -> Dict[str, Any]:
    """Durum bilgisi — /api/assistant/status ve günlükler için."""
    yol = veritabani_yolu()
    if yol is None:
        return {"available": False, "path": None, "tables": 0, "rows": 0}
    kat = _katalog()
    return {
        "available": True,
        "path": str(yol),
        "tables": len(_sema()) + len(TURETILMIS),
        "rows": sum(int(v.get("row_count") or 0) for v in kat.values()),
        "categories": sorted({v.get("category") for v in kat.values()
                              if v.get("category")}),
    }
