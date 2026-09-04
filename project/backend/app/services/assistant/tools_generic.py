"""Asistanın canonical veri evrenini KENDİSİ keşfedip sorgulaması.

NE DEĞİŞMEDİ
------------
Sağlayıcı katmanı (`gemini_provider.py`, `provider_factory.py`,
`provider_shared.py`), model adı, uç adresi, sıcaklık, düşünme ayarı,
sistem yönergesi, konuşma geçmişi, akış biçimi, hata eşlemesi — hiçbiri
bu dosyadan etkilenmez. Buraya eklenen şey yalnızca iki araçtır.

NEDEN GEREKTİ
-------------
Mevcut araçların her biri BELİRLİ bir soruya cevap veriyordu ve
`tool_selection` hangi aracın sunulacağını anahtar kelimeyle seçiyordu.
Bu iki katman birlikte modelin veri evrenini önceden daraltıyordu:
"Yazılım Mühendisliğinde bizi en çok zorlayan şey ne?" gibi bir soruda
hangi veriye bakılacağına kod karar veriyor, model kendi araştırmasını
yapamıyordu.

Ölçüldü: veritabanında 35 dolu tablo ve 111.368 satır var; özel
araçlar bunların küçük bir bölümünü görüyordu.

Buradaki iki araç o kararı modele bırakır:

    explore_data_sources   "elimde ne var?"  — canlı şema + metrik kataloğu
    query_canonical_data   "şunu getir"      — yapılandırılmış, salt okunur

Özel araçlar SİLİNMEDİ. Model hızlı yol isterse onları, serbest
araştırma isterse bunları kullanır; seçim modelindir.

SALT OKUNURLUK KODLA GARANTİ EDİLİR
-----------------------------------
Model SQL YAZMAZ. `query_canonical_data` alan adları, süzgeçler ve
toplama işlevi kabul eder; SQL cümlesini bu modül kurar. Tablo ve
sütun adları çalışma anındaki gerçek şemaya karşı doğrulanır, bağlama
parametreleriyle geçirilir. Yazma ifadesi geçirebilecek bir yüzey
yoktur — yasaklamak için yönergeye güvenilmez.

GERÇEKLİK ÖNCELİĞİ MODELE BIRAKILMAZ
------------------------------------
Aynı varlık + metrik + dönem için birden çok kayıt varsa seçimi
`tools_newdata._oncelik` yapar. Modele iki çelişkili satır sunulup
"sen seç" denmez.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.assistant import abu_kds_store
from app.services.assistant import veri_ailesi
from app.services.assistant.tool_registry import (
    ToolDefinition,
    ToolExecutionError,
    registry,
)
from app.services.assistant.tools_newdata import _oncelik

#: Varsayılan ve en fazla satır. Model isterse büyütür, tavanı aşamaz;
#: amaç veri alanını daraltmak değil, yanıt boyutunu sınırlamak.
#: Aramasız keşifte kaç kaynaktan sonra ayrıntı kısaltılsın.
_KOMPAKT_ESIGI = 8
#: Kompakt modda kaynak başına gösterilecek sütun / metrik sayısı.
_KOMPAKT_SUTUN = 8
_KOMPAKT_METRIK = 10

VARSAYILAN_SATIR = 50
EN_FAZLA_SATIR = 500

#: Kullanıcı verisi taşımayan tablolar keşiften çıkarılır.
#: Kara liste DEĞİL beyaz liste yokluğudur: yeni bir iş tablosu
#: eklendiğinde koda dokunmadan keşfedilir.
_GIZLE = ("sqlite_", "alembic_", "system_users")

#: Toplama işlevleri. Model bunların dışında bir şey yazamaz.
_TOPLAMA = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX",
            "count": "COUNT"}

#: Alan/tablo adı biçimi. Şema doğrulamasından ÖNCE gelen ilk savunma.
_AD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: TÜRKÇE ARAMA TERİMİ → ŞEMADAKİ İNGİLİZCE PARÇA.
#:
#: Ölçüldü: model "tercih", "kadro", "ücret" diye aradığında keşif boş
#: dönüyordu — sütun ve metrik adları İngilizce (`preference_first`,
#: `staff_prof`, `annual_fee_try`). Soru Türkçe, şema İngilizce.
#:
#: Bu bir METRİK BEYAZ LİSTESİ DEĞİLDİR: arama yine CANLI şemada
#: yapılır, burada yalnızca aranacak kelime genişletilir. Yarın yeni bir
#: `preference_*` metriği eklendiğinde bu sözlüğe dokunmadan
#: keşfedilir.
_ARAMA_KOPRUSU: Dict[str, tuple] = {
    "tercih": ("preference", "choice"),
    "kadro": ("staff", "academic_staff", "title"),
    "akademisyen": ("staff", "academic"),
    "ogretim": ("staff", "teaching"),
    "öğretim": ("staff", "teaching"),
    "ucret": ("fee", "tuition", "price"),
    "ücret": ("fee", "tuition", "price"),
    "ogrenci": ("student", "headcount", "enrollment"),
    "öğrenci": ("student", "headcount", "enrollment"),
    "kontenjan": ("quota",),
    "yerlesen": ("placed",),
    "yerleşen": ("placed",),
    "doluluk": ("occupancy",),
    "puan": ("score",),
    "sira": ("rank",),
    "sıra": ("rank",),
    "siralama": ("rank",),
    "sıralama": ("rank",),
    "celisk": ("conflict",),
    "çelişk": ("conflict",),
    "benzer": ("bolum_eslesme", "equivalence", "similar"),
    "ayni": ("bolum_eslesme", "same"),
    "aynı": ("bolum_eslesme", "same"),
    "bolum": ("department", "program", "bolum"),
    "bölüm": ("department", "program", "bolum"),
    "fakulte": ("faculty",),
    "fakülte": ("faculty",),
    "mufredat": ("curriculum", "course"),
    "müfredat": ("curriculum", "course"),
    "ders": ("course", "teaching", "curriculum"),
    "derslik": ("classroom", "facility"),
    "mali": ("financial", "budget", "fee"),
    "butce": ("budget", "financial"),
    "bütçe": ("budget", "financial"),
    "yayin": ("publication",),
    "yayın": ("publication",),
    "burs": ("scholarship",),
    "cinsiyet": ("gender", "male", "female"),
    "mezun": ("graduate",),
    "kpi": ("kpi", "strategic", "indicator"),
    "stratejik": ("strategic", "kpi"),
    "kapasite": ("capacity", "facility"),
    "senaryo": ("scenario",),
}


def _arama_terimleri(ara: str) -> List[str]:
    """Kullanıcının terimi + şemadaki İngilizce karşılıkları."""
    ara = (ara or "").strip().lower()
    if not ara:
        return []
    terimler = [ara]
    for tr, ing in _ARAMA_KOPRUSU.items():
        if tr in ara or ara in tr:
            terimler.extend(ing)
    return list(dict.fromkeys(terimler))


# ---------------------------------------------------------------------------
# Şema keşfi (süreçte bir kez)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _sema(db_url: str) -> Dict[str, List[str]]:
    """tablo → sütunlar. Anahtar yalnızca önbellek içindir."""
    from app.database import engine
    with engine.connect() as con:
        tablolar = [
            r[0] for r in con.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'")).all()
            if not any(r[0].startswith(g) or r[0] == g for g in _GIZLE)
        ]
        return {t: [c[1] for c in con.execute(text(f"PRAGMA table_info([{t}])")).all()]
                for t in tablolar}


def _sema_al(db: Session) -> Dict[str, List[str]]:
    return _sema("canonical")


@lru_cache(maxsize=1)
def _kds_kaynaklar() -> Dict[str, List[str]]:
    """`abu_kds.db` kaynakları — önekli ad → sütunlar."""
    try:
        return abu_kds_store.kaynaklar()
    except Exception:  # noqa: BLE001
        # Veritabanı yoksa ya da okunamıyorsa asistan çalışmaya DEVAM
        # eder; yalnızca bu kaynaklar listede görünmez. Açılışta patlamak
        # dosyayı henüz almamış bir geliştiricide her şeyi düşürürdü.
        logger.warning("abu_kds.db kaynakları okunamadı", exc_info=True)
        return {}


def _kds_sorgula(p: SorguGirdi, session=None) -> SorguCikti:
    """`kds_*` kaynağını salt okunur sorgular.

    Aracın mevcut sözleşmesi KORUNUR: model aynı `filters`,
    `filters_any`, `filters_range`, `order_by`, `limit` alanlarını
    kullanır. Burada onlar `abu_kds_store.satirlar()` fonksiyonunun
    kapalı (sütun, operatör, değer) biçimine çevrilir — SQL metnine
    model girdisi hiçbir noktada yazılmaz.

    `group_by`/`aggregate` bu kaynaklarda DESTEKLENMEZ ve sessizce
    yok sayılmaz: yanlış toplama (özellikle yüzde ortalaması) sessiz
    bir yanlış sayı üretirdi. Model açık bir not alır.
    """
    sutunlar = _kds_kaynaklar().get(p.source)
    if sutunlar is None:
        raise ToolExecutionError(
            f"Bilinmeyen kaynak: {p.source!r}. explore_data_sources ile "
            "kullanılabilir kaynakları görün.", kind="invalid_arguments")

    kosullar: List[tuple] = []
    for alan, deger in (p.filters or {}).items():
        _dogrula(alan, sutunlar, "sütun")
        metin = str(deger)
        sayisal = metin.replace(".", "", 1).replace("-", "", 1).isdigit()
        if sayisal:
            kosullar.append((alan, "=", float(metin) if "." in metin
                             else int(metin)))
        else:
            kosullar.append((alan, "LIKE", f"%{metin}%"))

    for alan, degerler in (p.filters_any or {}).items():
        _dogrula(alan, sutunlar, "sütun")
        temiz = [d for d in (degerler or []) if str(d).strip()][:50]
        if temiz:
            kosullar.append((alan, "IN", temiz))

    for alan, sinirlar in (p.filters_range or {}).items():
        _dogrula(alan, sutunlar, "sütun")
        if not sinirlar or len(sinirlar) != 2:
            continue
        alt, ust = sinirlar
        kosullar.append((alan, ">=", alt))
        kosullar.append((alan, "<=", ust))

    notlar: List[str] = []
    if p.aggregate or p.group_by:
        # SESSİZ YANLIŞ SAYI ÜRETMEKTENSE AÇIKÇA SÖYLE.
        notlar.append(
            "Bu kaynakta gruplama/toplama uygulanmadı; ham satırlar "
            "döndü. Oran sütunlarının ortalaması yanlış sonuç verir, "
            "toplamı backend hesaplar.")

    satirlar = abu_kds_store.satirlar(
        p.source, secilen=p.fields or None, kosullar=kosullar,
        sirala=p.order_by or None, azalan=bool(p.descending),
        sinir=p.limit)

    if not satirlar:
        raise ToolExecutionError(
            "Bu süzgeçlerle kayıt yok. Boş sonuç SIFIR DEĞİLDİR: değer "
            "ölçülmemiş olabilir.", kind="no_data")

    # SONUCU PLANA KARŞI DENETLE.
    # ------------------------------------------------------------------
    # Sorgu teknik olarak başarılı olabilir ve yine de soruyu
    # cevaplamıyor olabilir: "üniversiteler" sorulup tek kurum dönmesi,
    # beş yıl istenip iki yıl gelmesi, program sorusuna kurum toplamı
    # dönmesi. Bunlar sessiz yanlışlardır — sayı doğru görünür, cevap
    # yanlıştır. Uyarılar sonucu ENGELLEMEZ, modele not olarak gider ki
    # cevabında kapsamı doğru söylesin ya da eksik kaynağı istesin.
    soru = getattr(session, "user_question", None)
    if soru:
        try:
            plan = veri_ailesi.plan_cikar(soru)
            notlar.extend(veri_ailesi.dogrula(plan, satirlar))
        except Exception:  # noqa: BLE001
            logger.debug("retrieval denetimi atlandı", exc_info=True)

    koken = abu_kds_store.kaynak_notu(p.source)
    if koken:
        notlar.append(koken[:400])
    return SorguCikti(source=p.source, row_count=len(satirlar),
                      rows=satirlar, truncated=False, notes=notlar)


@lru_cache(maxsize=1)
def _turetilmis_kaynaklar() -> Dict[str, Path]:
    """Veritabanı dışındaki yetkili türetilmiş dosyalar."""
    bulunan: Dict[str, Path] = {}
    for ata in Path(__file__).resolve().parents:
        aday = ata / "data" / "bolum_eslesme" / "bolum_eslesme.csv"
        if aday.is_file():
            bulunan["bolum_eslesme"] = aday
            break
    return bulunan


# ---------------------------------------------------------------------------
# 1) KEŞİF
# ---------------------------------------------------------------------------
class KesifGirdi(BaseModel):
    model_config = {"extra": "forbid"}
    search: Optional[str] = Field(
        default=None,
        description=("Aradığın konu, örneğin 'tercih', 'kadro', 'ücret', "
                     "'öğrenci'. Tablo adı, sütun adı ve metrik adlarında "
                     "aranır. Boşsa bütün kaynakların özeti döner."))


class KaynakOzeti(BaseModel):
    source: str
    kind: str
    row_count: Optional[int] = None
    columns: List[str] = []
    metrics: List[str] = []
    years: Optional[str] = None
    note: Optional[str] = None


class KesifCikti(BaseModel):
    source_count: int
    sources: List[KaynakOzeti]
    notes: List[str] = []


def _kesfet(db: Session, p: KesifGirdi, session=None) -> KesifCikti:
    # AŞAMA 1 — KAYNAK KEŞFİ, PLANA GÖRE.
    # ------------------------------------------------------------------
    # Kaynak sıralaması artık yalnızca arama terimine değil, SORUNUN
    # KENDİSİNDEN çıkarılan plana dayanır: niyet (sıralama/eğilim/tekil
    # değer), metrik ailesi, istenen yıl aralığı ve seviye (program mı
    # kurum mu). Model keşif aracına yalnızca "taban puan" yazsa bile,
    # sorudaki "son 5 yıl" ve "üniversiteler" bilgisi burada devreye
    # girer — bu bilgi olmadan üç yıllık bir tablo beş yıllık soruya
    # doğru cevap sanılıyordu.
    soru = (getattr(session, "user_question", None) or p.search or "")
    plan = veri_ailesi.plan_cikar(soru) if soru else None
    ara = (p.search or "").strip().lower()
    terimler = _arama_terimleri(ara)

    def gecer(metin: str) -> bool:
        m = (metin or "").lower()
        return any(t in m for t in terimler)

    sema = _sema_al(db)
    cikan: List[KaynakOzeti] = []

    for tablo, sutunlar in sorted(sema.items()):
        eslesti = (not ara or gecer(tablo)
                   or any(gecer(s) for s in sutunlar))
        metrikler: List[str] = []
        yillar = None

        # Uzun formatlı tablolarda metrik adları da aranabilir olmalı;
        # asıl bilgi sütun adında değil `metric` değerlerinde saklı.
        if "metric" in sutunlar:
            ham = db.execute(text(
                f"SELECT DISTINCT metric FROM [{tablo}] LIMIT 200")).all()
            hepsi = sorted(r[0] for r in ham if r[0])
            metrikler = [m for m in hepsi if not ara or gecer(m)]
            if metrikler:
                eslesti = True
            elif not ara:
                metrikler = hepsi[:40]
        if eslesti and "academic_year" in sutunlar:
            r = db.execute(text(
                f"SELECT MIN(academic_year), MAX(academic_year) FROM [{tablo}]")).first()
            if r and r[0]:
                yillar = f"{r[0]} – {r[1]}"

        if not eslesti:
            continue
        n = db.execute(text(f"SELECT COUNT(*) FROM [{tablo}]")).scalar()
        if not n:
            continue
        cikan.append(KaynakOzeti(
            source=tablo, kind="table", row_count=int(n),
            columns=sutunlar, metrics=metrikler[:60], years=yillar))

    # MERKEZİ VERİ TABANI (`abu_kds.db`) KAYNAKLARI.
    # ------------------------------------------------------------------
    # Ekip 41 kaynak dosyayı tek SQLite'ta birleştirdi (62 tablo, 36.020
    # satır). Bu kaynaklar YENİ BİR ARAÇ açılarak değil, mevcut keşif
    # aracının evrenine katılarak sunulur: modelin öğrenmesi gereken bir
    # araç daha olmaz, yalnızca görebildiği kaynak sayısı artar.
    #
    # Adlar `kds_` öneklidir. Ölçüldü: `curriculum_courses` her iki
    # veritabanında da var; önek olmasaydı model hangisini kastettiğini
    # söyleyemez, sessizce yanlış tabloyu okurdu.
    # PLANA GÖRE SIRALANMIŞ ADAYLAR ÖNCE.
    # `aday_kaynaklar` yalnızca doğru veri ailesindeki kaynakları döndürür
    # ve istenen yıl aralığı tek kaynağa sığmıyorsa eksik yılları kapayan
    # kaynakları da ekler. Model böylece ilk tabloyu bulup durmaz.
    plan_sirasi: List[str] = []
    if plan and plan.aileler:
        plan_sirasi = [ad for ad, _ in veri_ailesi.aday_kaynaklar(plan)]

    kds_eslesen: List[tuple] = []
    for kds_ad, kds_sutunlar in _kds_kaynaklar().items():
        kds_not = abu_kds_store.kaynak_notu(kds_ad) or ""
        etiket = abu_kds_store.arama_etiketleri(kds_ad)
        # Türkçe soru → İngilizce tablo köprüsü (bkz. abu_kds_store).
        adda = gecer(kds_ad)
        sutunda = any(gecer(c) for c in kds_sutunlar)
        planda = kds_ad in plan_sirasi
        if ara and not (planda or adda or sutunda
                        or gecer(kds_not) or gecer(etiket)):
            continue
        # İLGİLİLİK SIRASI — alfabe değil.
        # Plandan gelen sıra en güçlü sinyaldir: niyeti, metriği, yılı ve
        # seviyeyi birlikte tartar. Sonra ad, sonra sütun eşleşmesi.
        if planda:
            oncelik = (0, plan_sirasi.index(kds_ad))
        else:
            oncelik = (1 if adda else (2 if sutunda else 3), 0)
        kds_eslesen.append((oncelik, kds_ad, KaynakOzeti(
            source=kds_ad, kind="table",
            row_count=abu_kds_store.satir_sayisi(kds_ad),
            columns=kds_sutunlar,
            note=(kds_not[:400] or None))))
    # PLANLA EŞLEŞENLER LİSTENİN BAŞINA.
    # ------------------------------------------------------------------
    # Ölçüldü: plan sıralaması yalnızca kds kaynakları arasında
    # çalışıyor, ama liste başında uygulamanın kendi canonical tabloları
    # duruyordu. Model ilk gördüğü kaynağa yönelme eğiliminde olduğu
    # için, doğru kaynak dördüncü sıraya düşünce keşif işe yaramıyordu.
    sirali_kds = sorted(kds_eslesen, key=lambda x: (x[0], x[1]))
    plan_ust = [k for oncelik, _, k in sirali_kds if oncelik[0] == 0]
    kalan_kds = [k for oncelik, _, k in sirali_kds if oncelik[0] != 0]
    if plan_ust:
        cikan[:0] = plan_ust
    cikan.extend(kalan_kds)

    for ad, yol in _turetilmis_kaynaklar().items():
        with open(yol, encoding="utf-8") as fh:
            okur = csv.DictReader(fh)
            basliklar = okur.fieldnames or []
            adet = sum(1 for _ in okur)
        if ara and not gecer(ad) and not any(gecer(b) for b in basliklar):
            continue
        cikan.append(KaynakOzeti(
            source=ad, kind="lookup", row_count=adet, columns=basliklar,
            note=("Yetkili aynı/benzer bölüm ilişkileri. ÖLÇÜM KAYNAĞI "
                  "DEĞİLDİR: sayı içermez, yalnızca hangi programların "
                  "karşılaştırılabilir olduğunu söyler.")))

    if not cikan:
        raise ToolExecutionError(
            f"'{p.search}' ile eşleşen veri kaynağı yok. Aramayı "
            "genelleştirin ya da search boş bırakıp tüm kaynakları görün.",
            kind="no_data")

    # ARAMASIZ KEŞİF KOMPAKT DÖNER.
    # ------------------------------------------------------------------
    # Ölçüldü: `search` boşken çıktı 35 kaynağın BÜTÜN sütunlarını ve
    # metrik listelerini içeriyor, ~13.800 karakter (kabaca 4.000 token)
    # tutuyordu. Bu, modelin bağlamının önemli bir kısmını daha ilk
    # turda dolduruyor ve onu "önce her şeyi gez" davranışına itiyordu.
    #
    # Kaynak SAYISI azaltılmaz — model hâlâ evrenin tamamını görür.
    # Kısaltılan yalnızca her kaynağın AYRINTISIDIR. Bir kaynağın tüm
    # sütunları gerektiğinde `search` ile o kaynağa inilir.
    kompakt = not ara and len(cikan) > _KOMPAKT_ESIGI
    if kompakt:
        # Uyarı kaynak başına DEĞİL, bir kez `notes` içinde verilir:
        # 35 kaynağa ayrı ayrı yazmak kısaltmanın kazandırdığı yerin
        # büyük kısmını geri harcıyordu (ölçüldü).
        cikan = [k.model_copy(update={
            "columns": k.columns[:_KOMPAKT_SUTUN],
            "metrics": k.metrics[:_KOMPAKT_METRIK],
        }) for k in cikan]

    return KesifCikti(
        source_count=len(cikan), sources=cikan,
        notes=([f"Kaynak listesi tam, ayrıntı kısaltıldı: sütun/metrik "
                f"başına ilk {_KOMPAKT_SUTUN}/{_KOMPAKT_METRIK} gösterildi. "
                "Bir kaynağın tamamı için search ile daraltın."]
               if kompakt else [])
              + ([f"Sorudan çıkarılan plan → {plan.ozet()}. Yukarıdaki "
                  "kaynaklar bu plana göre sıralandı; ilk sıradakiler en "
                  "uygun olanlardır."] if plan and plan.aileler else [])
              + ["Sorgulamak için query_canonical_data aracını kullanın.",
               "Aynı gerçek için birden çok kaynak varsa öncelik backend'de "
               "uygulanır; en güvenilir değer döner."])


# ---------------------------------------------------------------------------
# 2) SALT OKUNUR SORGU
# ---------------------------------------------------------------------------
class SorguGirdi(BaseModel):
    model_config = {"extra": "forbid"}

    source: str = Field(
        description="explore_data_sources çıktısındaki kaynak adı.")
    fields: Optional[List[str]] = Field(
        default=None,
        description="Getirilecek sütunlar. Boşsa kaynağın tümü döner.")
    filters: Optional[Dict[str, str]] = Field(
        default=None,
        description=("Sütun → aranan değer. Metin sütunlarında İÇERİR, "
                     "sayısal sütunlarda EŞİTTİR olarak uygulanır. "
                     "Örnek: {\"metric\": \"quota\", \"academic_year\": "
                     "\"2025-2026\", \"university_name\": \"BİLİM\"}"))
    filters_any: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description=("Sütun → KABUL EDİLEN DEĞERLER. Bir sütun için birden "
                     "çok değer aynı anda istendiğinde kullanın; böylece "
                     "üç ayrı çağrı yerine tek çağrı yeterli olur. Örnek: "
                     "{\"metric\": [\"quota\", \"placed\", "
                     "\"success_rank\"]}. `filters` ile birlikte "
                     "kullanılabilir; ikisi VE ile birleşir."))
    filters_range: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description=("Sütun → [alt_sinir, ust_sinir] — İKİSİ DE DAHİL. "
                     "Bir aralığın tüm değerlerini tek tek yazmak yerine "
                     "kullanın. Örnek: {\"academic_year\": "
                     "[\"2021-2022\", \"2026-2027\"]}. Metin "
                     "sütunlarında sözlük sırasına göre, sayısal "
                     "sütunlarda sayı olarak karşılaştırılır."))
    group_by: Optional[List[str]] = Field(
        default=None, description="Gruplanacak sütunlar.")
    aggregate: Optional[str] = Field(
        default=None, description="sum | avg | min | max | count")
    aggregate_field: Optional[str] = Field(
        default=None, description="Toplanacak sayısal sütun.")
    order_by: Optional[str] = Field(default=None)
    descending: bool = Field(default=False)
    limit: int = Field(default=VARSAYILAN_SATIR)


class SorguCikti(BaseModel):
    source: str
    row_count: int
    rows: List[Dict[str, Any]]
    truncated: bool = False
    notes: List[str] = []


def _dogrula(ad: str, gecerli: List[str], tur: str) -> str:
    if not _AD.match(ad or "") or ad not in gecerli:
        raise ToolExecutionError(
            f"Geçersiz {tur}: {ad!r}. Kullanılabilir: {', '.join(gecerli[:25])}",
            kind="invalid_arguments")
    return ad


def _sorgula(db: Session, p: SorguGirdi, session=None) -> SorguCikti:
    # --- MERKEZİ VERİ TABANI (`abu_kds.db`) ---
    # Salt okunur; SQL'i `abu_kds_store` kurar, model değil.
    if p.source.startswith(abu_kds_store.ONEK):
        return _kds_sorgula(p, session)

    # --- Türetilmiş dosya kaynağı ---
    if p.source in _turetilmis_kaynaklar():
        with open(_turetilmis_kaynaklar()[p.source], encoding="utf-8") as fh:
            satirlar = list(csv.DictReader(fh))
        for k, v in (p.filters or {}).items():
            satirlar = [r for r in satirlar
                        if str(v).lower() in str(r.get(k, "")).lower()]
        sinir = max(1, min(p.limit, EN_FAZLA_SATIR))
        return SorguCikti(source=p.source, row_count=min(len(satirlar), sinir),
                          rows=satirlar[:sinir], truncated=len(satirlar) > sinir,
                          notes=["Yetkili ilişki tablosu; ölçüm içermez."])

    # --- Veritabanı kaynağı ---
    sema = _sema_al(db)
    if p.source not in sema:
        raise ToolExecutionError(
            f"Bilinmeyen kaynak: {p.source!r}. explore_data_sources ile "
            "kullanılabilir kaynakları görün.", kind="invalid_arguments")
    sutunlar = sema[p.source]

    secilen = [_dogrula(a, sutunlar, "sütun") for a in (p.fields or [])]
    gruplar = [_dogrula(a, sutunlar, "sütun") for a in (p.group_by or [])]

    if p.aggregate:
        islev = _TOPLAMA.get(p.aggregate.lower())
        if not islev:
            raise ToolExecutionError(
                f"Desteklenmeyen toplama: {p.aggregate!r}. "
                f"Kullanılabilir: {', '.join(_TOPLAMA)}", kind="invalid_arguments")
        hedef = _dogrula(p.aggregate_field or "", sutunlar, "sütun")
        # NOT: SUM(placed)/SUM(quota) gibi türev oranlar burada
        # hesaplanmaz; onlar için mevcut servis araçları kullanılır.
        # Yüzdelerin ortalamasını almak yanlış sonuç verir.
        secme = ([f"[{g}]" for g in gruplar]
                 + [f"{islev}([{hedef}]) AS {p.aggregate}_{hedef}"])
    else:
        secme = [f"[{a}]" for a in secilen] or ["*"]

    kosul, par = [], {}
    for i, (alan, deger) in enumerate((p.filters or {}).items()):
        _dogrula(alan, sutunlar, "sütun")
        anahtar = f"f{i}"
        if isinstance(deger, str) and not deger.replace(".", "").isdigit():
            kosul.append(f"[{alan}] LIKE :{anahtar}"); par[anahtar] = f"%{deger}%"
        else:
            kosul.append(f"[{alan}] = :{anahtar}"); par[anahtar] = deger

    # ÇOKLU DEĞER — TEK ÇAĞRIDA BİRDEN ÇOK METRİK.
    # Ölçülen sorun: model "quota", "placed" ve "success_rank" için üç
    # ayrı çağrı yapıyordu; her çağrı bir model turu daha demekti ve
    # günlük kota bu şekilde tükeniyordu. Tek çağrıda IN listesi bunu
    # bire indirir. Değerler yine PARAMETRE olarak bağlanır; SQL metnine
    # kullanıcı/model girdisi yazılmaz.
    for j, (alan, degerler) in enumerate((p.filters_any or {}).items()):
        _dogrula(alan, sutunlar, "sütun")
        temiz = [d for d in (degerler or []) if str(d).strip()][:20]
        if not temiz:
            continue
        adlar = []
        for k, d in enumerate(temiz):
            anahtar = f"c{j}_{k}"
            par[anahtar] = d
            adlar.append(f":{anahtar}")
        kosul.append(f"[{alan}] IN ({', '.join(adlar)})")

    # ARALIK — "2021'den 2026'ya" tek koşulda.
    # `filters_any` ile altı akademik yılı tek tek saymak da mümkündü,
    # ama model bunu yapmak zorunda kalmasın diye aralık ayrıca
    # destekleniyor. Sınırlar yine PARAMETRE olarak bağlanır.
    for j, (alan, sinirlar) in enumerate((p.filters_range or {}).items()):
        _dogrula(alan, sutunlar, "sütun")
        ikili = [str(d).strip() for d in (sinirlar or []) if str(d).strip()]
        if len(ikili) != 2:
            raise ToolExecutionError(
                f"filters_range[{alan!r}] iki değer bekler: [alt, üst]. "
                f"Gelen: {sinirlar!r}", kind="invalid_arguments")
        alt, ust = sorted(ikili)
        par[f"r{j}a"], par[f"r{j}b"] = alt, ust
        kosul.append(f"[{alan}] BETWEEN :r{j}a AND :r{j}b")

    sinir = max(1, min(p.limit, EN_FAZLA_SATIR))
    sql = f"SELECT {', '.join(secme)} FROM [{p.source}]"
    if kosul:
        sql += " WHERE " + " AND ".join(kosul)
    if gruplar:
        sql += " GROUP BY " + ", ".join(f"[{g}]" for g in gruplar)
    if p.order_by:
        sql += f" ORDER BY [{_dogrula(p.order_by, sutunlar, 'sütun')}]" \
               + (" DESC" if p.descending else "")
    sql += f" LIMIT {sinir + 1}"

    ham = db.execute(text(sql), par).mappings().all()
    kirpildi = len(ham) > sinir
    satirlar = [dict(r) for r in ham[:sinir]]

    # ÇELİŞKİ ÇÖZÜMÜ: aynı varlık+metrik+dönem için en güvenilir kulvar.
    notlar: List[str] = []
    # ÇELİŞKİ ÇÖZÜMÜ YALNIZCA AYIRT EDİCİ ALANLAR ELDEYKEN YAPILIR.
    #
    # HATA: koşul tablonun sütunlarına bakıyordu, DÖNEN SATIRLARINKİNE
    # değil. `fields` ile yalnız üç sütun seçildiğinde `program_name`,
    # `metric` ve `source_dataset` satırlarda yoktu; hepsi
    # (None, None, None, None) anahtarına düşüp TEK SATIRA iniyordu.
    # Ölçüldü: 6 yıllık doluluk serisi 1 satıra, 21 kurumluk çok seri
    # grafiği tek seriye düşüyordu — sessiz veri kaybı.
    #
    # Artık çözüm yalnızca ayırt edici alanlar GERÇEKTEN döndüyse
    # çalışır. Dönmediyse zaten iki kaydı ayırt edecek bilgi yoktur ve
    # eleme yapmak veri silmek olur.
    donen = set(satirlar[0]) if satirlar else set()
    if (not p.aggregate and "source_dataset" in donen
            and {"metric", "academic_year"} <= donen):
        en_iyi: Dict[Any, Dict[str, Any]] = {}
        for r in satirlar:
            anahtar = (r.get("university_name"), r.get("program_name"),
                       r.get("academic_year"), r.get("metric"))
            mevcut = en_iyi.get(anahtar)
            if (mevcut is None
                    or _oncelik(r.get("source_dataset"))
                    < _oncelik(mevcut.get("source_dataset"))):
                en_iyi[anahtar] = r
        if len(en_iyi) < len(satirlar):
            notlar.append(
                f"{len(satirlar) - len(en_iyi)} satır, aynı gerçek için daha "
                "güvenilir bir kaynak bulunduğu için elendi.")
            satirlar = list(en_iyi.values())

    if not satirlar:
        raise ToolExecutionError(
            "Bu süzgeçlerle kayıt yok. Boş sonuç SIFIR DEĞİLDİR: değer "
            "ölçülmemiş olabilir.", kind="no_data")
    if kirpildi:
        notlar.append(f"İlk {sinir} satır gösteriliyor; süzgeci daraltın ya "
                      "da aggregate kullanın.")
    return SorguCikti(source=p.source, row_count=len(satirlar), rows=satirlar,
                      truncated=kirpildi, notes=notlar)


# ---------------------------------------------------------------------------
# Kayıt
# ---------------------------------------------------------------------------
registry.register(ToolDefinition(
    name="explore_data_sources",
    description=(
        "Kurumun veri evreninde NE OLDUĞUNU keşfeder: tablolar, sütunlar, "
        "metrik adları, kapsanan yıllar ve yetkili eşleştirme dosyaları. "
        "Bir soruya hangi verinin cevap vereceğinden emin değilsen ÖNCE "
        "bunu çağır; örneğin 'tercih', 'kadro', 'ücret', 'çelişki' diye "
        "arayabilirsin. Sonra query_canonical_data ile veriyi getir."),
    input_model=KesifGirdi, output_model=KesifCikti,
    handler=_kesfet, timeout_seconds=20.0, required_permission=None,
    needs_session=True,
    data_source="Canonical veri kataloğu",
))

registry.register(ToolDefinition(
    name="query_canonical_data",
    description=(
        "Canonical veriyi SALT OKUNUR sorgular. Kaynağı, sütunları, "
        "süzgeçleri, gruplamayı ve toplamayı sen seçersin; SQL yazmazsın. "
        "Özel araçların kapsamadığı bir soruyu kendi başına araştırmak "
        "için kullan. Kaynak ve sütun adlarını explore_data_sources ile "
        "öğren. Boş sonuç sıfır demek değildir. "
        "Birden çok bölüm, metrik veya yıl aynı soruda geçiyorsa "
        "`filters_any` ve `filters_range` ile hepsini TEK çağrıda "
        "isteyebilirsin; buna mecbur değilsin, ayrı ayrı sormak da "
        "geçerlidir."),
    input_model=SorguGirdi, output_model=SorguCikti,
    handler=_sorgula, timeout_seconds=25.0, required_permission=None,
    needs_session=True,
    data_source="Canonical veritabanı (salt okunur)",
))
