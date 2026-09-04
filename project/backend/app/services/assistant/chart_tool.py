"""`render_chart` — modelin grafik çizdirebildiği araç.

NEDEN VAR
---------
Grafik üretimi eskiden elle yazılmış SEKİZ regex kalıbına bağlıydı
(`chart_builder._KONU`). Kullanıcının sorusu o kalıplardan birine
uymazsa, model doğru aracı çağırıp gerçek veriyi almış olsa bile
"Grafik oluşturulamadı" yazılıyordu. Ölçülen örnek:

    "son beş yıldaki üniversiteler arasındaki bilgisayar mühendisliği
     trendini yorumla"
        grafik istendi mi? EVET
        kalıp eşleşti mi?  HAYIR   →  grafik yok

Model `get_program_quota_trend` aracını çağırmış, 19 üniversitenin 5
yıllık kontenjan ve doluluk verisi elde durmuş, ama çizecek kod o
veriyi hiç görmemişti: iki ayrı yol, birbirinden habersiz.

Bir kalıp listesi hiçbir zaman tamamlanmaz. Her yeni soru biçimi yeni
bir regex ister ve eksik olan tek şey sessizce "veri yok" olarak
görünür. Bu araç kalıbı ortadan kaldırır: hangi verinin çizileceğine
MODEL karar verir.

MODEL SAYI YAZAMAZ — YAPISAL GÜVENCE
------------------------------------
Bu aracın girdi şemasında SAYISAL DEĞER ALANI YOKTUR. Model yalnızca
şunları söyleyebilir:

    hangi araç sonucundan  (source_tool)
    hangi alan yatay eksen (x_field)
    hangi alan değer       (y_field)
    hangi alan seri        (series_field)
    hangi tür, hangi başlık

Değerlerin kendisi, o araç ÇALIŞTIĞINDA veritabanından dönen kayıttan
okunur. Model uydurma bir sayı yazmak isterse yazacak yer yoktur; bir
alan adı uydurursa araç hata döndürür ve grafik çizilmez. Yani
"sayılar backend'den gelir" güvencesi kısıtla değil, ŞEMAYLA korunur.

TASARIM: MODEL YOL BİLMEZ
-------------------------
Araç çıktıları iç içedir. `get_program_quota_trend` şöyle döner:

    {"universities": [{"university": "...", "series":
        [{"year": 2022, "quota": 1215.0, ...}, ...]}, ...]}

Modelden `universities[].series[].quota` gibi bir yol istemek, yazım
hatasının sessiz başarısızlığa dönüştüğü kırılgan bir sözleşme olurdu.
Bunun yerine model yalnızca ALAN ADLARINI söyler; `_tablolari_bul`
çıktının tamamını gezip o alanları İÇEREN kayıt listelerini kendisi
bulur. Yapı değişse de araç çalışmaya devam eder.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.services.assistant import chart_builder
from app.services.assistant.tool_registry import (
    ToolDefinition,
    ToolExecutionError,
    registry,
)

logger = logging.getLogger(__name__)

#: Tek grafikte gösterilecek en fazla seri. Üstü okunmaz hale gelir.
EN_FAZLA_SERI = 25

#: Bir kayıt listesinin "tablo" sayılması için gereken en az kayıt.
EN_AZ_SATIR = 2

#: ZAMAN EKSENİNDE çubuk grafiğin okunur kaldığı en fazla seri sayısı.
#: Üstünde çubuklar birbirine girer; çizgi hem daha okunur hem de
#: sürekliliği doğru gösterir.
EN_FAZLA_CUBUK_SERI = 3


class RenderChartInput(BaseModel):
    """Grafik isteği. DİKKAT: burada sayısal veri alanı YOKTUR.

    Model neyin çizileceğini tarif eder; ne çizileceğini veri belirler.
    """

    # `extra="forbid"`: model tanımsız bir alan uydurursa (`data`,
    # `values`, `series` gibi) istek SESSİZCE YOK SAYILMAZ, reddedilir.
    # Yok sayma da güvenlidir ama model o alanı yazdığını sanıp
    # sayıları çizdirdiğini varsayar; hata mesajı almak onu doğru yola
    # sokar.
    model_config = {"extra": "forbid"}

    source_tool: str = Field(
        description=("Verinin alınacağı aracın adı. Bu araç bu turda daha "
                     "önce başarıyla çağrılmış olmalıdır."))
    x_field: str = Field(
        description=("Yatay eksende yer alacak alanın adı, örneğin 'year' "
                     "ya da 'faculty'."))
    y_field: str = Field(
        description=("Çizilecek değerin alan adı, örneğin 'quota' ya da "
                     "'occupancy_percent'."))
    series_field: Optional[str] = Field(
        default=None,
        description=("Birden çok çizgi/çubuk gerekiyorsa serileri ayıran "
                     "alan adı, örneğin 'university'. Tek seri için boş "
                     "bırakın."))
    series_fields: Optional[List[str]] = Field(
        default=None,
        description=("Seriyi AYIRT ETMEK İÇİN birden çok alan gerekiyorsa "
                     "kullanın. Tek sorguda iki bölümün hem kontenjanı hem "
                     "yerleşeni geldiğinde tek alan yetmez: "
                     "['program_name', 'metric'] verilirse seriler "
                     "'Bilgisayar Mühendisliği — quota' gibi ayrı ayrı "
                     "çizilir. Boş bırakılırsa series_field kullanılır."))
    chart_type: str = Field(
        default="line",
        description=("Grafik türü: line, bar, hbar, grouped, stacked, "
                     "donut, scatter."))
    title: str = Field(description="Grafiğin başlığı.")
    y_label: Optional[str] = Field(
        default=None, description="Dikey eksen etiketi (birim).")


class RenderChartOutput(BaseModel):
    """Aracın modele döndürdüğü ÖZET.

    Grafiğin kendisi `chart` alanında arayüze gider; modele giden özet
    yalnızca kaç seri ve kaç nokta çizildiğini söyler. Modelin
    değerleri tekrar okuyup metne yazmasına gerek yoktur — zaten
    çağırdığı araçtan görmüştür.
    """

    rendered: bool
    series_count: int = 0
    point_count: int = 0
    message: str = ""
    # `exclude=True`: grafik gövdesi ARAYÜZE gider, MODELE gitmez.
    # Yüzlerce sayı içeren bir yapıyı modele geri okutmak hem token
    # bütçesini yakar hem de modelin o sayıları metne kopyalamasını
    # teşvik eder. Router bunu Python nesnesinden okur (`record.output`),
    # serileştirmeye ihtiyaç duymaz.
    chart: Optional[Dict[str, Any]] = Field(default=None, exclude=True)


# ---------------------------------------------------------------------------
# Çıktı içinde tablo arama
# ---------------------------------------------------------------------------
def _tablolari_bul(
    dugum: Any,
    alanlar: Tuple[str, ...],
    miras: Optional[Dict[str, Any]] = None,
) -> List[Tuple[List[Dict], Dict[str, Any]]]:
    """İstenen alanları içeren kayıt listelerini, ATA BAĞLAMIYLA döndürür.

    `miras`, listenin bulunduğu sözlüğün düz (sayı/metin) alanlarıdır.
    Buna ihtiyaç var çünkü seriyi ayıran alan çoğu zaman satırın
    kendisinde DEĞİL, üstündeki nesnededir:

        {"university": "ODTÜ", "series": [{"year": 2022, "quota": 1034}]}

    Burada `series_field="university"` satırlarda bulunmaz; ata
    bağlamından gelir. Bu olmadan çok seri li grafik kurulamazdı.
    """
    miras = miras or {}
    bulunan: List[Tuple[List[Dict], Dict[str, Any]]] = []

    if isinstance(dugum, dict):
        yerel = {
            k: v for k, v in dugum.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
        yeni_miras = {**miras, **yerel}
        for deger in dugum.values():
            bulunan.extend(_tablolari_bul(deger, alanlar, yeni_miras))
        return bulunan

    if isinstance(dugum, list):
        satirlar = [x for x in dugum if isinstance(x, dict)]
        if len(satirlar) >= EN_AZ_SATIR:
            mevcut = set()
            for s in satirlar:
                mevcut.update(s.keys())
            if all(a in mevcut for a in alanlar):
                bulunan.append((satirlar, miras))
        for x in dugum:
            bulunan.extend(_tablolari_bul(x, alanlar, miras))
        return bulunan

    return bulunan


def _ayirt_edici_alan(miraslar: List[Dict[str, Any]]) -> Optional[str]:
    """Serileri birbirinden ayıran METİN alanını kendiliğinden bulur.

    NEDEN GEREKLİ
    -------------
    Model `series_field` vermeyi unutabilir. Eskiden bu durumda
    seriler "Seri 1", "Seri 2" … diye adlandırılıyordu; ekranda 14
    tane numaralı efsane çıkıyor ve grafik OKUNAMAZ hale geliyordu —
    hangi çizginin hangi üniversite olduğu hiçbir yerde yazmıyordu.

    Oysa ad zaten elimizde: her tablo bir üniversite/birim nesnesinin
    altından geliyor ve o nesnenin adı `miras` içinde duruyor. Burada
    yapılan iş, tablolar arasında FARKLILAŞAN metin alanını seçmek —
    yani serileri gerçekten ayırt eden alan hangisiyse onu.
    """
    if len(miraslar) < 2:
        return None
    ortak = set(miraslar[0])
    for m in miraslar[1:]:
        ortak &= set(m)

    en_iyi, en_iyi_uzunluk = None, -1
    for k in sorted(ortak):
        degerler = [m.get(k) for m in miraslar]
        if not all(isinstance(v, str) and v.strip() for v in degerler):
            continue
        if len(set(degerler)) != len(miraslar):
            continue          # ayırt etmiyor
        # Birden çok aday varsa en açıklayıcı olanı (en uzun metin) seç:
        # "ODTÜ" adı, "TR" gibi bir koddan daha bilgilendiricidir.
        uzunluk = sum(len(v) for v in degerler) / len(degerler)
        if uzunluk > en_iyi_uzunluk:
            en_iyi, en_iyi_uzunluk = k, uzunluk
    return en_iyi


def _seri_adi(miras: Dict[str, Any], satir: Dict[str, Any],
              alan: Optional[str], sira: int) -> str:
    if alan:
        for kaynak in (satir, miras):
            deger = kaynak.get(alan)
            if deger not in (None, ""):
                return str(deger)
    return f"Seri {sira + 1}"


def _sayi(deger: Any) -> Optional[float]:
    if deger is None or isinstance(deger, bool):
        return None
    try:
        return float(deger)
    except (TypeError, ValueError):
        return None


def kur(veri: Any, istek: RenderChartInput) -> RenderChartOutput:
    """Araç çıktısından grafiği kurar. Veritabanına DOKUNMAZ."""
    if istek.chart_type not in chart_builder.CHART_TYPES:
        raise ToolExecutionError(
            f"Desteklenmeyen grafik türü: {istek.chart_type}. "
            f"Kullanılabilir: {', '.join(chart_builder.CHART_TYPES)}.",
            kind="invalid_arguments")

    tablolar = _tablolari_bul(veri, (istek.x_field, istek.y_field))
    if not tablolar:
        # ALAN ADI UYDURULAMAZ: hangi alanların gerçekten var olduğunu
        # söyle ki model körlemesine tekrar denemesin.
        mevcut = sorted(_alan_adlari(veri))[:40]
        raise ToolExecutionError(
            f"'{istek.source_tool}' çıktısında '{istek.x_field}' ve "
            f"'{istek.y_field}' alanlarını birlikte içeren kayıt yok. "
            f"Çıktıdaki alanlar: {', '.join(mevcut) or '(yok)'}.",
            kind="invalid_arguments")

    # Aynı alanları taşıyan birden çok tablo varsa (her üniversitenin
    # kendi `series` listesi gibi) hepsi ayrı bir seri olur.
    kategoriler: List[str] = []
    for satirlar, _ in tablolar:
        for s in satirlar:
            etiket = s.get(istek.x_field)
            if etiket is None:
                continue
            metin = str(etiket)
            if metin not in kategoriler:
                kategoriler.append(metin)

    if not kategoriler:
        raise ToolExecutionError(
            f"'{istek.x_field}' alanı boş; grafiğin yatay ekseni kurulamadı.",
            kind="no_data")

    # Sayısal eksen ise doğal sırada dursun (2021, 2022, … gibi).
    if all(_sayi(k) is not None for k in kategoriler):
        kategoriler.sort(key=lambda k: _sayi(k) or 0.0)

    # BİLEŞİK SERİ ALANI.
    # ------------------------------------------------------------------
    # Tek sorgu artık iki bölümün üç metriğini birden getirebiliyor.
    # O sonuçta seriyi tek alan ayıramaz: `series_field="program_name"`
    # seçilirse aynı (program, yıl) çiftine düşen `quota` ve `placed`
    # değerleri aynı sözlük anahtarını paylaşır ve BİRİ DİĞERİNİ EZER.
    # Ölçüldü: 2 program × 2 metrik = 4 seri beklenirken 2 seri
    # çiziliyor, yarısı sessizce kayboluyordu.
    #
    # `series_fields` verildiğinde anahtar alanların birleşimidir;
    # verilmediğinde davranış AYNEN ESKİSİ GİBİ kalır.
    seri_alanlari = [a for a in (istek.series_fields or []) if a]

    # SERİ ADI KENDİLİĞİNDEN BULUNUR (bkz. `_ayirt_edici_alan`).
    seri_alani = istek.series_field
    if not seri_alani and not seri_alanlari and len(tablolar) > 1:
        seri_alani = _ayirt_edici_alan([m for _, m in tablolar])
        if seri_alani:
            logger.info("series_field verilmedi; %r alanı kullanıldı.",
                        seri_alani)

    seriler: List[Dict[str, Any]] = []
    for sira, (satirlar, miras) in enumerate(tablolar):
        gecerli = [a for a in seri_alanlari if a in satirlar[0]]
        if gecerli:
            # Bileşik anahtar: her alan bileşimi ayrı bir seri.
            gruplar: Dict[str, Dict[str, Optional[float]]] = {}
            for s in satirlar:
                ad = " — ".join(str(s.get(a)) for a in gecerli
                                if s.get(a) is not None)
                gruplar.setdefault(ad, {})[str(s.get(istek.x_field))] = _sayi(
                    s.get(istek.y_field))
            for ad, esleme in gruplar.items():
                seriler.append({"name": ad,
                                "data": [esleme.get(k) for k in kategoriler]})
        elif seri_alani and seri_alani in satirlar[0]:
            # Seri alanı satırların İÇİNDE: tek tabloyu gruplara böl.
            gruplar: Dict[str, Dict[str, Optional[float]]] = {}
            for s in satirlar:
                ad = str(s.get(seri_alani) or "")
                gruplar.setdefault(ad, {})[str(s.get(istek.x_field))] = _sayi(
                    s.get(istek.y_field))
            for ad, esleme in gruplar.items():
                seriler.append({"name": ad,
                                "data": [esleme.get(k) for k in kategoriler]})
        else:
            esleme = {str(s.get(istek.x_field)): _sayi(s.get(istek.y_field))
                      for s in satirlar}
            seriler.append({
                # Tek seri varsa numara anlamsız: ÖLÇÜNÜN adı yazılır
                # ("Kontenjan"), çünkü efsanenin işi seriyi ayırt etmek
                # ve ayırt edilecek ikinci seri yok.
                "name": (_seri_adi(miras, satirlar[0], seri_alani, sira)
                         if (seri_alani or len(tablolar) > 1)
                         else (istek.y_label or istek.y_field)),
                "data": [esleme.get(k) for k in kategoriler],
            })

    # Tamamen boş seriler (ölçülmemiş yıllar) grafikte yer kaplamasın.
    seriler = [s for s in seriler if any(v is not None for v in s["data"])]
    if not seriler:
        raise ToolExecutionError(
            f"'{istek.y_field}' alanında sayısal değer bulunamadı; "
            "sahte grafik çizilmez.",
            kind="no_data")

    kirpildi = False
    if len(seriler) > EN_FAZLA_SERI:
        # En çok veri taşıyanlar kalır; sıralama değeri DEĞİŞTİRMEZ.
        seriler.sort(key=lambda s: sum(1 for v in s["data"] if v is not None),
                     reverse=True)
        seriler = seriler[:EN_FAZLA_SERI]
        kirpildi = True

    # GRAFİK TÜRÜ GÜVENLİK AĞI.
    # ------------------------------------------------------------------
    # Model türü seçer, ama bazı seçimler ÖLÇÜLEBİLİR biçimde okunmaz.
    # Gerçekte yaşandı: 14 seri × 5 yıl "bar" olarak çizilince ekranda
    # 70 ince çubuk çıktı; hangi çubuğun hangi kuruma ait olduğu
    # ayırt edilemiyordu.
    #
    # Kural dar tutuldu: YALNIZCA yatay eksen ZAMAN ise (sayısal ve
    # artan, yıl gibi) ve çok seri varsa çubuk çizgiye çevrilir. Zaman
    # ekseninde çubuk zaten yanlış gösterimdir — süreklilik taşıyan
    # bir değişkeni kesikli kutucuklarla göstermek okuyucuyu yanıltır.
    # Kategori eksenlerinde (fakülte, bölüm) çubuk doğrudur ve
    # DOKUNULMAZ.
    tur = istek.chart_type
    zaman_ekseni = all(_sayi(k) is not None for k in kategoriler)
    if (tur in ("bar", "hbar", "grouped", "stacked", "stacked_bar")
            and zaman_ekseni and len(seriler) > EN_FAZLA_CUBUK_SERI):
        logger.info("Okunabilirlik: %r → 'line' (%d seri, zaman ekseni)",
                    tur, len(seriler))
        tur = "line"

    notlar = []
    if kirpildi:
        notlar.append(f"Okunabilirlik için en veri dolu {EN_FAZLA_SERI} seri "
                      "gösteriliyor.")

    grafik = chart_builder._chart(
        tur, istek.title, kategoriler, seriler,
        y_label=istek.y_label, x_label=istek.x_field,
        source_label=istek.source_tool, notes=notlar,
    )
    if grafik is None:
        raise ToolExecutionError(
            "Grafik doğrulamadan geçmedi; yarım grafik çizilmez.",
            kind="no_data")

    nokta = sum(1 for s in grafik["series"] for v in s["data"] if v is not None)
    return RenderChartOutput(
        rendered=True,
        series_count=len(grafik["series"]),
        point_count=nokta,
        message=(f"Grafik hazırlandı: {len(grafik['series'])} seri, "
                 f"{nokta} veri noktası. Kullanıcı grafiği görüyor; "
                 "sayıları metinde tekrarlamana gerek yok."),
        chart=grafik,
    )


def _alan_adlari(dugum: Any, derinlik: int = 0) -> set:
    """Çıktıdaki tüm alan adları — hata mesajını yol gösterici yapmak için."""
    if derinlik > 6:
        return set()
    if isinstance(dugum, dict):
        adlar = set(dugum.keys())
        for v in dugum.values():
            adlar |= _alan_adlari(v, derinlik + 1)
        return adlar
    if isinstance(dugum, list):
        adlar = set()
        for v in dugum[:5]:
            adlar |= _alan_adlari(v, derinlik + 1)
        return adlar
    return set()


# ---------------------------------------------------------------------------
# Araç bağlantısı
# ---------------------------------------------------------------------------
def handler(db: Session, payload: RenderChartInput,
            session: Any = None) -> RenderChartOutput:
    """Oturumdaki önceki araç sonucundan grafiği kurar.

    `session` olmadan çalışamaz: bu araç veritabanını değil, MODELİN
    BU TURDA ÇEKTİĞİ VERİYİ çizer. Böylece grafikteki sayılarla
    metindeki sayılar aynı sorgudan gelir; ikisi ayrışamaz.
    """
    if session is None:
        raise ToolExecutionError(
            "Grafik aracı oturum bağlamı olmadan çalıştırılamaz.",
            kind="error")

    kayit = None
    for r in reversed(getattr(session, "records", [])):
        if r.name == payload.source_tool and r.success:
            kayit = r
            break

    if kayit is None:
        cagrilanlar = sorted({r.name for r in getattr(session, "records", [])
                              if r.success and r.name != "render_chart"})
        raise ToolExecutionError(
            f"'{payload.source_tool}' bu turda başarıyla çağrılmadı. "
            "Önce veriyi getiren aracı çağırın. Bu turda çalışan araçlar: "
            + (", ".join(cagrilanlar) or "(yok)"),
            kind="invalid_arguments")

    try:
        veri = json.loads(kayit.content)
    except (ValueError, TypeError) as exc:
        raise ToolExecutionError(
            "Kaynak araç çıktısı okunamadı.", kind="error") from exc

    return kur(veri, payload)


registry.register(ToolDefinition(
    name="render_chart",
    description=(
        "Bu turda çağırdığın BAŞKA bir aracın sonucundan grafik çizer. "
        "Kullanıcı grafik, çizim, görselleştirme ya da 'göster' isterse "
        "önce veriyi getiren aracı çağır, sonra bunu çağır. Sayı YAZMAZSIN: "
        "yalnızca hangi araç sonucundan hangi alanların çizileceğini "
        "söylersin; değerler o araçtan okunur. Zaman serisi için "
        "chart_type='line' ve x_field='year'; kategori karşılaştırması "
        "için 'bar' kullan. Birden çok üniversite/birim çizdirmek için "
        "series_field ver."
    ),
    input_model=RenderChartInput,
    output_model=RenderChartOutput,
    handler=handler,
    timeout_seconds=15.0,
    required_permission=None,
    data_source="Önceki araç sonucundan çizilen grafik",
    needs_session=True,
))
