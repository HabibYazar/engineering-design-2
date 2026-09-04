"""ASİSTAN GRAFİKLERİ — sayıyı MODEL DEĞİL, BACKEND üretir.

TASARIM KARARI
--------------
Dil modeli grafik verisi ÜRETMEZ. Ne sayı, ne kod, ne yürütülebilir
yapılandırma. Modelden gelen tek şey düz metindir; grafiğin sayıları bu
modülde, mevcut servislerden okunarak hesaplanır.

Sebebi basit: bir modelin ürettiği sayı doğru görünür ama doğrulanamaz.
"Fakültelere göre öğrenci sayısını çiz" isteğine model kendi kafasından
yedi sayı yazsa, ekranda gerçek bir grafik gibi durur ve kimse fark
etmez. Bu yüzden akış tersine çevrilmiştir:

    kullanıcı isteği → DETERMİNİSTİK niyet çözümleme (bu modül)
                     → mevcut servislerden GERÇEK veri
                     → kapalı şema ile doğrulanmış grafik
                     → model yalnızca yorum cümlesini yazar

Model hiçbir aşamada sayıya dokunmaz. Grafik üretilemiyorsa grafik
ÜRETİLMEZ; sahte grafik çizmektense hiç çizmemek doğrudur.

KAPSAM VE DÖNEM
---------------
Her grafik, arayüzde seçili kapsam ve akademik yılla üretilir. Üst
kapsamın sayısı alt kapsamın sayısıymış gibi GÖSTERİLMEZ; veri yoksa
grafik yerine "veri yok" döner.

SENARYO AYRIMI
--------------
What-If senaryo değerleri gerçek kurum verisi DEĞİLDİR. Senaryo içeren
her grafik `is_scenario=True` taşır ve üzerinde bunu söyleyen bir not
bulunur.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.scope import Scope

logger = logging.getLogger(__name__)

#: Desteklenen grafik türleri — KAPALI liste. Bunun dışındaki bir değer
#: arayüze GİTMEZ.
CHART_TYPES = ("bar", "hbar", "line", "grouped", "donut", "scatter", "bubble", "stacked", "stacked_bar")


#: Kaynak sınıfı. Arayüz bunu etikete çevirir.
SOURCE_AUTHORITATIVE = "authoritative"   # kurumun resmî kayıtları
SOURCE_DERIVED = "derived"               # kohort tahmini / hesaplanmış
SOURCE_SCENARIO = "scenario"             # What-If çıktısı
SOURCE_UPLOAD = "upload"                 # kullanıcının yüklediği veri
SOURCE_MIXED = "mixed"                    # aynı seride birden çok kaynak sınıfı

SCENARIO_NOTE = ("Bu değer What-If senaryosudur; gerçekleşmiş kurum "
                 "verisi değildir.")


# ---------------------------------------------------------------------------
# Niyet çözümleme — anahtar sözcüklerle, deterministik
# ---------------------------------------------------------------------------

_GRAFIK_ISTEGI = re.compile(
    r"grafi[kğ]|çiz|cizel|görsel|gorsel|şema|grafikle|"
    r"sütun|sutun|çubuk|cubuk|pasta|donut|trend|dağılımını göster",
    re.IGNORECASE)


_TAKIP_ISTEGI = re.compile(
    r"^\s*(bunu[nu]?|onu[nu]?|şunu[nu]?|bu sonucu|grafi[kğ]ini|grafi[kğ]i)\b"
    r"|grafi[kğ]ini (göster|çiz|oluştur)|bunu grafikle",
    re.IGNORECASE)

_TUR_ISTEGI = (
    (re.compile(r"pasta|donut|pay dağılımı", re.I), "donut"),
    (re.compile(r"çizgi|cizgi|trend|yıllara göre|zaman", re.I), "line"),
    (re.compile(r"yatay|sırala|siralama|ranking|ilk \d+", re.I), "hbar"),
    (re.compile(r"sütun|sutun|dikey|bar", re.I), "bar"),
)

# KONU KALIPLARI KALDIRILDI.
# ---------------------------------------------------------------------
# Burada `_KONU` adında sekiz elemanlı bir regex listesi vardı; grafiğin
# konusu kullanıcının cümlesini bu kalıplarla eşleştirerek bulunuyordu.
# Kalıba uymayan her soru, model doğru aracı çağırıp gerçek veriyi almış
# olsa bile "Grafik oluşturulamadı" ile bitiyordu. Ölçülen örnek:
#
#     "son beş yıldaki üniversiteler arasındaki bilgisayar mühendisliği
#      trendini yorumla"  →  hiçbir kalıp eşleşmedi  →  grafik yok
#
# Bir kalıp listesi hiçbir zaman tamamlanmaz ve eksiği sessizce "veri
# yok" gibi görünür. Ne çizileceğine artık model karar veriyor:
# `chart_tool.render_chart`. Değerler yine backend'den gelir — o araç
# sayı değil yalnızca ALAN ADI kabul eder.
#
# `build_dataset_charts` (katalog yolu) burada değildir: o, kalıba değil
# `data_catalog`ın çözdüğü satırlara dayanır ve olduğu gibi korunur.


def wants_chart(message: str) -> bool:
    """Kullanıcı görselleştirme istiyor mu?"""
    return bool(_GRAFIK_ISTEGI.search(message or ""))


def is_followup_chart(message: str) -> bool:
    """"Grafiğini göster" gibi, öncekine atıf yapan bir istek mi?"""
    return bool(_TAKIP_ISTEGI.search(message or ""))


def requested_chart_type(message: str) -> Optional[str]:
    """Kullanıcı belirli bir tür istediyse onu döndürür."""
    for kalip, tur in _TUR_ISTEGI:
        if kalip.search(message or ""):
            return tur
    return None


# ---------------------------------------------------------------------------
# Kapalı şema
# ---------------------------------------------------------------------------


def _chart(chart_type: str, title: str, categories: List[str],
           series: List[Dict[str, Any]], **ek) -> Optional[Dict[str, Any]]:
    """Grafiği KAPALI şemaya göre kurar ve doğrular.

    Doğrulamadan geçmeyen grafik `None` döner — yarım bir grafik
    çizmektense hiç çizmemek doğrudur.
    """
    if chart_type not in CHART_TYPES:
        logger.warning("Desteklenmeyen grafik turu reddedildi: %r", chart_type)
        return None
    if not categories or not series:
        return None

    temiz_seri = []
    for s in series:
        veri = s.get("data") or []
        if len(veri) != len(categories):
            logger.warning("Seri uzunlugu kategori sayisiyla uyusmuyor")
            return None
        # Sayı olmayan değer `None` olur: "ölçülmedi" demektir, SIFIR DEĞİL.
        sayilar = []
        precision = ek.get("display_precision")
        for v in veri:
            if v is None:
                sayilar.append(None)
                continue
            try:
                fv = float(v)
                if precision is not None:
                    sayilar.append(round(fv, precision))
                elif 0 < abs(fv) < 0.1:
                    sayilar.append(round(fv, 4))
                else:
                    sayilar.append(round(fv, 2))
            except (TypeError, ValueError):
                sayilar.append(None)
        if all(v is None for v in sayilar):
            continue
        temiz_seri.append({"name": str(s.get("name") or ""), "data": sayilar,
                           "unit": s.get("unit")})
    if not temiz_seri:
        return None

    grafik = {
        "type": "chart",
        "chart_type": chart_type,
        "title": str(title),
        "subtitle": ek.get("subtitle"),
        "x_label": ek.get("x_label"),
        "y_label": ek.get("y_label"),
        "categories": [str(c) for c in categories],
        "series": temiz_seri,
        "academic_year": ek.get("academic_year"),
        "scope": ek.get("scope") or {},
        "source_type": ek.get("source_type", SOURCE_AUTHORITATIVE),
        "source_label": ek.get("source_label"),
        "is_scenario": bool(ek.get("is_scenario")),
        "measure_type": ek.get("measure_type", "count"),
        "display_precision": ek.get("display_precision"),
        "display_unit": ek.get("display_unit"),
        "additive": ek.get("additive", True),
        "entity_level": ek.get("entity_level"),
        "notes": list(ek.get("notes") or []),
    }
    if grafik["is_scenario"] and SCENARIO_NOTE not in grafik["notes"]:
        grafik["notes"].append(SCENARIO_NOTE)
    return grafik


def _kpi(label: str, value, unit: str = "", source: str = SOURCE_AUTHORITATIVE):
    """KPI kartı. Değer yoksa 'Veri yok' — sıfır YAZILMAZ."""
    return {"label": label,
            "value": None if value is None else value,
            "display": "Veri yok" if value is None else f"{value:,.0f}".replace(",", ".") + (f" {unit}" if unit else ""),
            "unit": unit, "source_type": source}


# ---------------------------------------------------------------------------
# Veri üreticiler — hepsi MEVCUT servisleri çağırır
# ---------------------------------------------------------------------------


def _scope_dict(scope: Optional[Scope]) -> Dict[str, Any]:
    if scope is None:
        return {"level": "university", "label": "Üniversite geneli"}
    return {"level": scope.level, "label": scope.label}


# `build_charts` ve altındaki altı üretici de kalıp yoluna aitti;
# `render_chart` onların yerini alınca kaldırıldılar. Grafiği üreten tek
# genel kod yolu artık `chart_tool.kur`, tek katalog yolu ise aşağıdaki
# `build_dataset_charts`.


def build_dataset_charts(
    dataset: Optional[Dict[str, Any]], message: str
) -> Dict[str, Any]:
    """Render catalog rows without performing an independent data query.

    ``data_catalog`` already resolved entities, discovered metrics and read the
    trusted services.  Re-querying here would recreate the old split-brain
    architecture where prose and chart could disagree.  Every series value
    below is copied from the exact row that grounded the assistant prose.
    """
    if not dataset or dataset.get("type") != "catalog_query":
        return {"charts": [], "topic": None, "unavailable": False}
    if not dataset.get("available"):
        return {"charts": [], "topic": "catalog_query", "unavailable": True}

    # 1. Analitik Görsel Planlar (Visual Plans) varsa soruya/bulgulara özel analitik grafikleri çiz:
    raw_vps = dataset.get("visual_plans") or ([dataset["visual_plan"]] if dataset.get("visual_plan") else [])
    if raw_vps and isinstance(raw_vps, list):

        out_charts = []
        for visual_plan in raw_vps:
            if not isinstance(visual_plan, dict):
                continue
            vp_type = visual_plan.get("chart_type")
            if vp_type in ("bubble", "scatter"):
                graph = {
                    "type": "chart",
                    "chart_type": vp_type,
                    "title": visual_plan.get("title") or "Fakültelerde Fiziksel ve Akademik Baskı Analizi",
                    "subtitle": visual_plan.get("subtitle") or dataset.get("academic_year"),
                    "x_label": visual_plan.get("x_label") or "Fiziksel Kapasite Kullanımı (%)",
                    "y_label": visual_plan.get("y_label") or "Öğrenci / Akademisyen Oranı",
                    "size_label": visual_plan.get("size_label") or "Öğrenci Sayısı",
                    "points": visual_plan.get("points") or [],
                    "reference_lines": visual_plan.get("reference_lines") or [],
                    "academic_year": dataset.get("academic_year"),
                    "scope": {"level": "catalog", "label": "Analitik Karar Desteği"},
                    "source_type": SOURCE_DERIVED,
                    "source_label": visual_plan.get("source_label") or "ÖSYM/YKS · Fiziksel Envanter · Akademik Personel",
                    "is_scenario": bool(visual_plan.get("is_scenario")),
                    "notes": list(dataset.get("notes") or []) + list(visual_plan.get("notes") or []),
                    "metric": visual_plan.get("metric") or dataset.get("metric") or "student_count",
                    "data_rows": visual_plan.get("data_rows") or dataset.get("rows") or [],
                }
                out_charts.append(graph)
            elif vp_type == "grouped":
                graph = _chart(
                    "grouped",
                    visual_plan.get("title") or "Karşılaştırma",
                    visual_plan.get("categories") or [],
                    visual_plan.get("series") or [],
                    subtitle=visual_plan.get("subtitle") or dataset.get("academic_year"),
                    academic_year=dataset.get("academic_year"),
                    scope={"level": "catalog", "label": "Analitik Karşılaştırma"},
                    source_type=SOURCE_DERIVED,
                    source_label=visual_plan.get("source_label") or "ÖSYM/YKS · YÖK Atlas",
                    is_scenario=bool(visual_plan.get("is_scenario")),
                    measure_type=visual_plan.get("measure_type", "count"),
                    display_precision=visual_plan.get("display_precision"),
                    display_unit=visual_plan.get("display_unit"),
                    additive=visual_plan.get("additive", False),
                    entity_level=visual_plan.get("entity_level"),
                    notes=list(dataset.get("notes") or []) + list(visual_plan.get("notes") or []),
                )
                if graph:
                    graph["metric"] = visual_plan.get("metric") or dataset.get("metric") or (dataset.get("metrics")[0]["key"] if dataset.get("metrics") else "student_count")
                    graph["data_rows"] = visual_plan.get("data_rows") or dataset.get("rows") or []
                    out_charts.append(graph)
            elif vp_type in ("stacked", "stacked_bar"):
                graph = _chart(
                    "stacked",
                    visual_plan.get("title") or "Hiyerarşik Dağılım",
                    visual_plan.get("categories") or [],
                    visual_plan.get("series") or [],
                    subtitle=visual_plan.get("subtitle") or dataset.get("academic_year"),
                    academic_year=dataset.get("academic_year"),
                    scope={"level": "catalog", "label": "Hiyerarşik Yapı Analizi"},
                    source_type=SOURCE_DERIVED,
                    source_label=visual_plan.get("source_label") or "ÖSYM/YKS",
                    measure_type=visual_plan.get("measure_type", "count"),
                    display_precision=visual_plan.get("display_precision"),
                    display_unit=visual_plan.get("display_unit"),
                    additive=visual_plan.get("additive", True),
                    entity_level=visual_plan.get("entity_level"),
                    notes=list(dataset.get("notes") or []) + list(visual_plan.get("notes") or []),
                )
                if graph:
                    graph["metric"] = visual_plan.get("metric") or dataset.get("metric") or (dataset.get("metrics")[0]["key"] if dataset.get("metrics") else "student_count")
                    graph["data_rows"] = visual_plan.get("data_rows") or dataset.get("rows") or []
                    out_charts.append(graph)
            elif vp_type == "hbar":
                graph = _chart(
                    "hbar",
                    visual_plan.get("title") or "Analitik Gösterge",
                    visual_plan.get("categories") or [],
                    visual_plan.get("series") or [],
                    subtitle=visual_plan.get("subtitle") or dataset.get("academic_year"),
                    academic_year=dataset.get("academic_year"),
                    scope={"level": "catalog", "label": "Analitik Sıralama"},
                    source_type=SOURCE_DERIVED,
                    source_label=visual_plan.get("source_label") or "ÖSYM/YKS · Akademik Personel",
                    measure_type=visual_plan.get("measure_type", "count"),
                    display_precision=visual_plan.get("display_precision"),
                    display_unit=visual_plan.get("display_unit"),
                    additive=visual_plan.get("additive", False),
                    entity_level=visual_plan.get("entity_level"),
                    notes=list(dataset.get("notes") or []) + list(visual_plan.get("notes") or []),
                )
                if graph:
                    graph["metric"] = visual_plan.get("metric") or dataset.get("metric") or (dataset.get("metrics")[0]["key"] if dataset.get("metrics") else "student_count")
                    graph["data_rows"] = visual_plan.get("data_rows") or dataset.get("rows") or []
                    out_charts.append(graph)
        if out_charts:
            return {"charts": out_charts, "topic": "catalog_query", "unavailable": False}


    if not wants_chart(message) and not is_followup_chart(message):
        return {"charts": [], "topic": "catalog_query", "unavailable": False}

    charts: List[Dict[str, Any]] = []
    requested_type = requested_chart_type(message)

    operation = dataset.get("operation")
    for metric in dataset.get("metrics") or []:
        rows = [row for row in (metric.get("rows") or []) if row.get("value") is not None]
        if not rows:
            continue
        mixed_levels = len({row.get("entity_type") for row in rows}) > 1
        categories = []
        for row in rows:
            label = str(row.get("label") or "—")
            if mixed_levels:
                level = row.get("entity_type_label") or row.get("entity_type")
                label = f"{label} — {level}"
            categories.append(label)

        source_types = {row.get("source_type") for row in rows if row.get("source_type")}
        source_labels = []
        notes = list(dataset.get("notes") or [])
        for row in rows:
            source = row.get("source_label")
            if source and source not in source_labels:
                source_labels.append(source)
            note = row.get("note")
            if note and note not in notes:
                notes.append(note)

        default_type = "hbar" if operation in {"children", "staff_ranking"} else "bar"
        graph = _chart(
            requested_type or default_type,
            str(metric.get("label") or metric.get("canonical_label") or "Kurumsal Gösterge"),
            categories,
            [{
                "name": metric.get("label") or metric.get("canonical_label"),
                "data": [row["value"] for row in rows],
                "unit": metric.get("unit"),
            }],
            subtitle=dataset.get("academic_year"),
            x_label=(rows[0].get("entity_type_label") if not mixed_levels else "Birim"),
            y_label=metric.get("unit"),
            academic_year=dataset.get("academic_year"),
            scope={"level": "catalog", "label": "Kurumsal veri sorgusu"},
            source_type=(next(iter(source_types)) if len(source_types) == 1 else SOURCE_MIXED),
            source_label="; ".join(source_labels),
            notes=notes,
        )
        if graph is not None:
            # Traceability for tests/audits: categories map to catalog rows;
            # the renderer does not need this field but safely ignores it.
            graph["data_rows"] = rows
            graph["metric"] = metric.get("key")
            charts.append(graph)

    return {
        "charts": charts,
        "topic": "catalog_query",
        "unavailable": not bool(charts),
    }



# ---------------------------------------------------------------------------
# Konuşma hafızası — "grafiğini göster" için
# ---------------------------------------------------------------------------
#
# Takip isteği ("grafiğini göster") önceki cevabın METNİNDEN sayı
# ayıklayarak DEĞİL, önceki turun KONUSUNU yeniden üreterek çalışır.
# Burada saklanan tek şey konu anahtarıdır; sayılar her seferinde
# servisten taze okunur. Böylece takip grafiği de birinci grafikle aynı
# kaynaktan gelir.

_SON_KONU: Dict[str, str] = {}
_MAKS_KONUSMA = 200


def remember_topic(conversation_id: Optional[str], topic: Optional[str]) -> None:
    if not conversation_id or not topic:
        return
    if len(_SON_KONU) > _MAKS_KONUSMA:
        _SON_KONU.clear()
    _SON_KONU[conversation_id] = topic


def recall_topic(conversation_id: Optional[str]) -> Optional[str]:
    return _SON_KONU.get(conversation_id or "")


def forget(conversation_id: Optional[str]) -> None:
    _SON_KONU.pop(conversation_id or "", None)
