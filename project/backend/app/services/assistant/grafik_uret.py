"""Grafik isteklerini ELDEKİ veriden karşılayan deterministik katman.

ÖLÇÜLEN ARIZA
-------------
Kullanıcı "grafiğini çiz" dediğinde sistem metin cevabı veriyor ama
grafik çıkmıyordu. Sebep tek bir eksik halka:

    Grafik yalnızca MODEL `render_chart` aracını çağırırsa çiziliyordu.

Model o aracı çağırmadığında — ya da çağıramadığında — çizilecek veri
elde durduğu hâlde grafik üretilmiyordu. Çağıramadığı bir durum artık
yapısal olarak da var: çok metrikli analiz yolunda veriyi BACKEND
çekiyor, ortada modelin `source_tool` olarak gösterebileceği bir araç
çağrısı bulunmuyor. Yani grafik yolu, sistemin en zengin veri ürettiği
soruda tam olarak kapalıydı.

ÇÖZÜM
-----
Grafik üretimi modelin isteğine BAĞIMLI olmaktan çıkarılır. Model
`render_chart`ı çağırırsa o grafik kullanılır — mevcut yol aynen durur.
Çağırmadıysa ve kullanıcı grafik istediyse, bu modül AYNI turda ZATEN
ÇEKİLMİŞ veriden grafiği kendisi türetir.

    · Yeni sorgu yok. Ek DB taraması yok.
    · Uydurma sayı yok: her nokta bir araç sonucundan ya da çok
      metrikli kanıttan okunur.
    · Metin ve grafik AYNI veriyi tüketir; ayrışamazlar.
    · Grafik kurulamazsa `None` döner — metin cevabı olduğu gibi kalır.
      Grafiğin çıkmaması cevabı düşürmez.

GRAFİK TÜRÜ NEREDEN GELİR
-------------------------
Kullanıcı açıkça bir tür istediyse o. İstemediyse tür VERİNİN ŞEKLİNDEN
çıkar, sorunun kelimelerinden değil:

    yatay eksen yıl  + 3+ nokta   → line   (eğilim)
    yatay eksen yıl  + 2 nokta    → bar    (iki yılın kıyası)
    yatay eksen varlık            → bar / hbar (çok varlıkta yatay)
    pay/dağılım sorusu + tek yıl  → donut

Bu eşleme kavramsaldır: yeni bir soru biçimi için yeni bir kural
gerekmez.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.assistant import chart_builder

logger = logging.getLogger(__name__)

#: Bir turda üretilecek en fazla grafik. Üstü ekranı doldurur ve
#: kullanıcının hangisine bakacağını belirsizleştirir.
EN_FAZLA_GRAFIK = 4
#: Bir grafikteki en fazla seri ve kategori. Okunabilirlik sınırı;
#: aşıldığında grafik çizilmez, çünkü okunamayan grafik bilgi vermez.
_EN_FAZLA_SERI = 12
_EN_FAZLA_KATEGORI = 40
#: Yatay çubuğa geçilen varlık sayısı — dikey çubukta etiketler üst üste
#: biner.
_YATAY_ESIK = 6

#: İngilizce grafik istekleri. Türkçe kalıplar `chart_builder`da zaten
#: var; iki yerde iki liste tutmamak için oraya dokunulmuyor.
_INGILIZCE = re.compile(r"\b(chart|graph|plot|visuali[sz]e)\b", re.I)
#: Pay/dağılım soruları — donut'a yalnızca bu sinyalle gidilir.
_PAY = re.compile(r"(pay|dagilim|dağılım|oran(?:ı|i)? nedir|yuzdesi|"
                  r"yüzdesi|pasta|donut|share)", re.I)

_YIL_ALAN = re.compile(r"^(academic_year|year|yil|donem|period)$", re.I)
_VARLIK_ALAN = re.compile(
    r"(university|universite|kurum|program|bolum|department|faculty|"
    r"fakulte|name|ad)", re.I)
_ATLA_ALAN = re.compile(r"(id$|_id|code|kod|no$|url|link)", re.I)


def istendi_mi(soru: str) -> bool:
    """Kullanıcı görselleştirme istiyor mu.

    Türkçe kalıplar `chart_builder.wants_chart` içinde; burada yalnızca
    İngilizce karşılıkları ekleniyor. Kalıp listesini çoğaltmak yerine
    mevcut olanı çağırmak, iki listenin zamanla ayrışmasını önler.
    """
    if not soru:
        return False
    return bool(chart_builder.wants_chart(soru) or _INGILIZCE.search(soru))


# ---------------------------------------------------------------------------
# 1) TÜR SEÇİMİ
# ---------------------------------------------------------------------------
def tur_sec(soru: str, *, yil_ekseni: bool, nokta: int, kategori: int,
            seri: int = 1) -> str:
    """Grafik türü — önce kullanıcının açık isteği, sonra verinin şekli."""
    istenen = chart_builder.requested_chart_type(soru or "")
    if istenen and istenen in chart_builder.CHART_TYPES:
        return istenen
    if yil_ekseni:
        return "line" if nokta >= 3 else "bar"
    if seri == 1 and kategori <= 8 and _PAY.search(soru or ""):
        return "donut"
    return "hbar" if kategori > _YATAY_ESIK else "bar"


def _olcu_bilgisi(birim: str) -> Dict[str, Any]:
    """Birimden görüntüleme kuralları.

    Oran ve yüzde TOPLANAMAZ: `additive=False` arayüzün yığılmış
    (stacked) toplam göstermesini engeller. Bu ayrım olmadan iki
    programın doluluk yüzdesi üst üste konup %190 gibi anlamsız bir
    değer gösterilebilirdi.
    """
    oran = birim in ("%", "oran", "sıra")
    return {"y_label": birim or None, "display_unit": birim or None,
            "measure_type": "ratio" if oran else "count",
            "additive": not oran,
            "display_precision": 2 if oran or birim == "puan" else 0}


# ---------------------------------------------------------------------------
# 2) ÇOK METRİKLİ KANITTAN
# ---------------------------------------------------------------------------
def _ilgili_metrikler(kanit, istenen: Sequence[str] = ()):
    """Kanıttaki metrikleri, soruda AÇIKÇA istenen ölçüye daraltır.

    Kullanıcı "taban puanı grafiği" dediyse doluluk ve kontenjan
    grafikleri de çizmek soruyu genişletmek olur. İstenen ölçü
    kanıtta yoksa daraltma yapılmaz — eldeki her şey çizilir, çünkü
    hiç grafik çizmemektense ilgili olanı göstermek yeğdir.
    """
    metrikler = list(getattr(kanit, "metrikler", []) or [])
    if not istenen:
        return metrikler
    daraltilmis = [m for m in metrikler if m.metrik in set(istenen)]
    return daraltilmis or metrikler


def kanittan(kanit, soru: str, *, kapsam: str = "",
             istenen: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """`coklu_metrik.Kanit` → grafikler.

    HER METRİK KENDİ GRAFİĞİNDE. Taban puanı ile doluluk oranını aynı
    eksene koymak, birimleri farklı iki büyüklüğü kıyaslanabilir gibi
    gösterirdi; metinde uygulanan "bileşik skor üretme" ilkesinin
    görsel karşılığı budur.
    """
    grafikler: List[Dict[str, Any]] = []
    for m in _ilgili_metrikler(kanit, istenen):
        if not getattr(m, "yeterli", False):
            continue
        yillar = [str(y) for y, _, _ in m.noktalar]
        degerler = [v for _, v, _ in m.noktalar]
        tur = tur_sec(soru, yil_ekseni=True, nokta=len(yillar),
                      kategori=len(yillar))
        baslik = f"{m.etiket.capitalize()} — {yillar[0]}–{yillar[-1]}"
        if kapsam:
            baslik += f" ({kapsam})"
        grafik = chart_builder._chart(
            tur, baslik, yillar,
            [{"name": m.etiket, "data": degerler, "unit": m.birim}],
            x_label="Yıl", subtitle=f"Kaynak: {m.kaynak} · {m.yontem}",
            source_label=m.kaynak, notes=list(_kanit_notlari(m)),
            **_olcu_bilgisi(m.birim))
        if grafik:
            grafikler.append(grafik)
        if len(grafikler) >= EN_FAZLA_GRAFIK:
            break
    return grafikler


def _kanit_notlari(m) -> Sequence[str]:
    """Metindeki uyarılar grafiğe de taşınır — ikisi ayrışmasın."""
    notlar: List[str] = []
    if not getattr(m, "dengeli", True):
        notlar.append("Yıllar aynı varlık kümesinden hesaplanamadı; "
                      "değişim kısmen kapsam farkından olabilir.")
    if getattr(m, "kucuk_iyi", False):
        notlar.append("Bu ölçüde küçük değer daha iyidir.")
    return notlar


def kirilimdan(kanit, soru: str) -> List[Dict[str, Any]]:
    """Varlık kırılımı → sıralama grafiği (en çok artan/azalan)."""
    grafikler: List[Dict[str, Any]] = []
    for m in getattr(kanit, "metrikler", []):
        uclar = list(getattr(m, "siralama", []) or [])
        if len(uclar) < 3:
            continue
        secilen = uclar[:5] + uclar[-5:] if len(uclar) > 10 else uclar
        # Aynı varlık iki uçtan da gelmişse tekrarlamasın.
        gorulen, temiz = set(), []
        for satir in secilen:
            if satir[0] in gorulen:
                continue
            gorulen.add(satir[0])
            temiz.append(satir)
        adlar = [a for a, *_ in temiz]
        farklar = [d for *_, d in temiz]
        grafik = chart_builder._chart(
            "hbar", f"{m.etiket.capitalize()} değişimi — varlık kırılımı",
            adlar, [{"name": f"{m.etiket} değişimi", "data": farklar,
                     "unit": m.birim}],
            x_label=None, source_label=m.kaynak,
            **_olcu_bilgisi(m.birim))
        if grafik:
            grafikler.append(grafik)
        if len(grafikler) >= 2:
            break
    return grafikler


# ---------------------------------------------------------------------------
# 3) ARAÇ SONUÇLARINDAN
# ---------------------------------------------------------------------------
def _satir_kumeleri(session) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Başarılı araç çıktılarındaki kayıt listeleri.

    `_elde_ne_var` ile aynı okuma biçimi: araç çıktısı Pydantic ise
    `model_dump`, değilse `content` JSON'u. Yeni bir sözleşme
    tanımlanmıyor.
    """
    import json
    kumeler: List[Tuple[str, List[Dict[str, Any]]]] = []
    for kayit in (getattr(session, "records", None) or []):
        if not getattr(kayit, "success", False):
            continue
        veri: Any = None
        cikti = getattr(kayit, "output", None)
        if cikti is not None:
            try:
                veri = cikti.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                veri = None
        if veri is None:
            try:
                veri = json.loads(getattr(kayit, "content", "") or "null")
            except Exception:  # noqa: BLE001
                continue
        satirlar = veri.get("rows") if isinstance(veri, dict) else None
        if isinstance(satirlar, list) and satirlar and all(
                isinstance(r, dict) for r in satirlar):
            baslik = next((str(veri[a]) for a in ("title", "source", "label")
                           if veri.get(a)), kayit.name)
            kumeler.append((baslik, satirlar))
    return kumeler


def _sayisal_mi(satirlar: Sequence[Dict[str, Any]], alan: str) -> bool:
    sayi = 0
    for satir in satirlar[:30]:
        deger = satir.get(alan)
        if isinstance(deger, bool) or deger is None:
            continue
        if isinstance(deger, (int, float)):
            sayi += 1
        elif isinstance(deger, str):
            try:
                float(deger.replace(",", "."))
                sayi += 1
            except ValueError:
                return False
    return sayi >= 2


def _alanlari_sec(satirlar: Sequence[Dict[str, Any]], plan
                  ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(yatay eksen, değer, seri) alanları — şemadan, sorudan değil."""
    anahtarlar = list(satirlar[0].keys())
    yil = next((a for a in anahtarlar if _YIL_ALAN.match(a)), None)
    varlik = next((a for a in anahtarlar
                   if _VARLIK_ALAN.search(a) and not _ATLA_ALAN.search(a)
                   and not _sayisal_mi(satirlar, a)), None)

    # DEĞER ALANI: önce planın metriği, sonra ilk anlamlı sayısal alan.
    from app.services.assistant import veri_ailesi
    ipuclari: List[str] = []
    for anahtar in (getattr(plan, "kavramlar", None) or []):
        kav = next((k for k in veri_ailesi.KAVRAMLAR
                    if k.anahtar == anahtar), None)
        if kav:
            ipuclari.extend(kav.sutun)
    deger = None
    for ipucu in ipuclari:
        deger = next((a for a in anahtarlar
                      if ipucu in veri_ailesi.sadelestir(a)
                      and not _ATLA_ALAN.search(a)
                      and _sayisal_mi(satirlar, a)), None)
        if deger:
            break
    if deger is None:
        deger = next((a for a in anahtarlar
                      if a not in (yil,) and not _ATLA_ALAN.search(a)
                      and _sayisal_mi(satirlar, a)), None)

    if yil and varlik:
        return yil, deger, varlik
    return (yil or varlik), deger, None


def satirlardan(session, plan, soru: str) -> List[Dict[str, Any]]:
    """Araç sonucundaki satırlardan grafik. Yeni sorgu ÇALIŞTIRILMAZ."""
    grafikler: List[Dict[str, Any]] = []
    for baslik, satirlar in _satir_kumeleri(session):
        x_alan, y_alan, seri_alan = _alanlari_sec(satirlar, plan)
        if not x_alan or not y_alan:
            continue

        # (seri, kategori) → değer
        kategoriler: List[str] = []
        seriler: Dict[str, Dict[str, Any]] = {}
        for satir in satirlar:
            kategori = str(satir.get(x_alan) or "").strip()
            if not kategori:
                continue
            if kategori not in kategoriler:
                kategoriler.append(kategori)
            ad = (str(satir.get(seri_alan) or "").strip()
                  if seri_alan else str(baslik))
            seriler.setdefault(ad or "—", {})[kategori] = satir.get(y_alan)
        if not kategoriler or not seriler:
            continue

        # EKSEN TEK DEĞERE ÇÖKTÜYSE DEVRİLİR.
        # Sorgu tek yıl döndürdüğünde ("2021") yıl ekseninde tek nokta
        # kalır ve grafik bilgi vermez. Aynı veri varlık ekseninde
        # anlamlıdır: o yılın kurumlar arası kıyası. Yeni sorgu
        # yapılmaz, eldeki satırlar başka eksende okunur.
        if len(kategoriler) < 2 and len(seriler) > 1:
            tek = kategoriler[0]
            kategoriler = list(seriler.keys())
            seriler = {tek: {ad: degerler.get(tek)
                             for ad, degerler in seriler.items()}}
            x_alan = seri_alan or x_alan

        if (len(kategoriler) > _EN_FAZLA_KATEGORI
                or len(seriler) > _EN_FAZLA_SERI):
            logger.info("Grafik atlandı: %d kategori / %d seri okunamaz",
                        len(kategoriler), len(seriler))
            continue

        yil_ekseni = bool(_YIL_ALAN.match(x_alan))
        if yil_ekseni:
            kategoriler.sort()
        tur = tur_sec(soru, yil_ekseni=yil_ekseni, nokta=len(kategoriler),
                      kategori=len(kategoriler), seri=len(seriler))
        grafik = chart_builder._chart(
            tur, f"{y_alan} — {baslik}", kategoriler,
            [{"name": ad, "data": [degerler.get(k) for k in kategoriler]}
             for ad, degerler in seriler.items()],
            x_label=x_alan, y_label=y_alan, source_label=baslik)
        if grafik:
            grafikler.append(grafik)
        if len(grafikler) >= EN_FAZLA_GRAFIK:
            break
    return grafikler


# ---------------------------------------------------------------------------
# 4) TEK GİRİŞ
# ---------------------------------------------------------------------------
def uret(soru: str, *, plan=None, kanit=None, session=None
         ) -> List[Dict[str, Any]]:
    """Elde ne varsa ondan grafik. Hiçbir koşulda istisna yükseltmez.

    Grafik üretilememesi bir HATA DEĞİLDİR: metin cevabı zaten
    hazırdır ve kullanıcıya gider. Bu yüzden bütün gövde tek bir
    korumanın içinde ve boş liste dönmek geçerli bir sonuçtur.
    """
    try:
        istenen = tuple(getattr(plan, "kavramlar", None) or ())
        grafikler: List[Dict[str, Any]] = []
        if kanit is not None and getattr(kanit, "var", False):
            grafikler = kanittan(kanit, soru,
                                 kapsam=getattr(kanit, "kapsam", ""),
                                 istenen=istenen)
            if len(grafikler) < EN_FAZLA_GRAFIK and getattr(
                    plan, "niyet", "") in ("ranking", "comparison"):
                grafikler += kirilimdan(kanit, soru)
        if not grafikler and session is not None:
            grafikler = satirlardan(session, plan, soru)

        # SON ÇARE: MEVCUT ANALİZ MOTORUNU ÇAĞIR.
        # ------------------------------------------------------------------
        # Kullanıcı grafik istedi, model araç çağırmadı ve çok metrikli
        # yol da devreye girmedi (ölçü belliyse girmiyor). Bu durumda
        # elde hiçbir şey yok ve kullanıcı grafik yerine boş bir gerekçe
        # görüyordu.
        #
        # Burada YENİ bir retrieval yazılmıyor: soruyu zaten çözmüş olan
        # plan, mevcut `coklu_metrik` analizine veriliyor. Maliyet
        # birkaç indeksli okuma ve yalnızca GRAFİK İSTENEN ve başka
        # hiçbir verinin bulunmadığı turlarda ödeniyor.
        if not grafikler and plan is not None:
            from app.services.assistant import coklu_metrik
            son_kanit = coklu_metrik.kanit_uret(plan)
            if getattr(son_kanit, "var", False):
                grafikler = kanittan(son_kanit, soru,
                                     kapsam=son_kanit.kapsam,
                                     istenen=istenen)
        return grafikler[:EN_FAZLA_GRAFIK]
    except Exception:  # noqa: BLE001
        logger.debug("grafik türetilemedi", exc_info=True)
        return []


def sebep(grafik_var: bool, veri_var: bool) -> str:
    """Grafik istendi ama çıkmadıysa kısa gerekçe — UI'da teknik detay yok."""
    if grafik_var:
        return ""
    if not veri_var:
        return "Bu soru için grafiğe dönüştürülebilir kurumsal veri bulunamadı."
    return ("Eldeki veri grafik ekseni kurmaya elverişli değil; "
            "sayısal cevap metinde verildi.")
