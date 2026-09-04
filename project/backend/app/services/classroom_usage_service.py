"""DERSLİK KULLANIM HARİTASI — salt-okunur veri servisi.

KAYNAK
------
`data/infrastructure/derived/` altındaki türetilmiş dosyalar. Bunlar
`build_infrastructure_map.py` tarafından ham PDF/XLSX'ten üretilir.

NEDEN VERİTABANI DEĞİL
----------------------
Bu veri kümesi bir DÖNEMİN ders programının anlık görüntüsüdür ve
kurumun yetkili fiziksel kaynak kayıtlarıyla (physical_facilities)
aynı şey DEĞİLDİR. Veritabanına yazmak iki ayrı gerçeği tek tabloda
karıştırır ve mevcut kapasite kayıtlarını kirletirdi. Bu yüzden servis
dosyayı okur, hiçbir şey yazmaz.

Dosya süreç ömrü boyunca bir kez okunup önbelleğe alınır; disk her
istekte okunmaz.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

#: app/services/bu_dosya.py → parents: [0]=services [1]=app [2]=backend
#: [3]=integration. Türetilmiş veri `integration/data/` altındadır.
TURETILMIS = (Path(__file__).resolve().parents[3]
              / "data" / "infrastructure" / "derived")

_onbellek: Optional[dict] = None


def _oku(ad: str) -> dict:
    yol = TURETILMIS / ad
    if not yol.exists():
        return {}
    return json.loads(yol.read_text(encoding="utf-8"))


def _yukle() -> dict:
    global _onbellek
    if _onbellek is not None:
        return _onbellek

    veri = _oku("classroom_usage.json")
    if not veri:
        _onbellek = {
            "available": False,
            "note": ("Türetilmiş derslik veri kümesi bulunamadı. "
                     "`python build_infrastructure_map.py` çalıştırın."),
            "floors": [], "rooms": [], "time_slots": [], "days": [],
        }
        return _onbellek

    geometri = _oku("room_geometry.json")
    rapor = _oku("room_match_report.json")
    konumlar = (geometri or {}).get("rooms", {})

    odalar: List[dict] = []
    for r in veri["rooms"]:
        k = konumlar.get(r["room_key"])
        odalar.append({
            **r,
            # Plan üzerinde konumu KANITLANMIŞ odalar işaretlenir; gerisi
            # arayüzde ızgarada gösterilir (gizlenmez, uydurulmaz).
            "plan_position": ({"x": k["x"], "y": k["y"], "source": k["source"]}
                              if k else None),
        })

    _onbellek = {
        "available": True,
        "meta": veri["meta"],
        "days": veri["meta"]["days"],
        "floors": veri["floors"],
        "time_slots": veri["time_slots"],
        "rooms": odalar,
        "coverage": {
            "rooms_total": len(odalar),
            "rooms_with_schedule": sum(1 for r in odalar if r["has_schedule"]),
            "rooms_without_schedule": sum(1 for r in odalar if not r["has_schedule"]),
            "rooms_placed_on_plan": sum(1 for r in odalar if r["plan_position"]),
            "unmatched": (rapor or {}).get("unmatched_rooms_without_schedule", []),
            "sheets_without_inventory": (rapor or {}).get(
                "schedule_sheets_without_inventory", []),
            "plan_placement_note": ((rapor or {}).get("plan_placement", {})
                                    .get("reason_unplaced")),
        },
        "floor_mapping_evidence": (rapor or {}).get("floor_mapping_evidence"),
    }
    return _onbellek


def classroom_usage_map() -> dict:
    """Tüm veri kümesi tek seferde.

    Gün/saat/kat süzgeçleri arayüzde uygulanır: veri kümesi küçüktür ve
    her açılır liste değişiminde ağ isteği atmak gereksiz gecikme
    yaratırdı. Sunucu tek bir doğruyu yayınlar, istemci onu keser.
    """
    return _yukle()
