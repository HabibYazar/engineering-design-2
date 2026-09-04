"""SEMANTİK KAT HARİTASI — otomatik çıkarım + elle düzeltme birleşimi.

İki kaynak KESİNLİKLE ayrı tutulur:

    floor_semantic_maps.json        `build_semantic_map.py` üretir.
                                    Extractor her çalıştığında SIFIRDAN
                                    yazılır; elle düzenlenmez.

    semantic_map_overrides.json     Elle bakım dosyası. Extractor bu
                                    dosyayı ne okur ne de yazar, bu
                                    yüzden yeniden üretim düzeltmeleri
                                    SİLEMEZ.

Birleştirme burada, okuma anında yapılır. Karıştırılmış tek bir dosya
tutmak da mümkündü ama o zaman ilk `build_semantic_map.py` çalıştırması
bütün elle emeği sessizce silerdi — düzeltmelerin ömrü, onları kimsenin
yeniden üretmeyi hatırlamasına bağlı kalırdı. Ayrı dosya bu kaybı
yapısal olarak imkânsız kılar.

Uygulama sırası: remove → update → add. Her oda `origin` alanıyla
damgalanır ("auto" | "manual"), böylece arayüz ve sonraki bakımcı bir
poligonun nereden geldiğini tahmin etmek zorunda kalmaz.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

TURETILMIS = (Path(__file__).resolve().parents[3]
              / "data" / "infrastructure" / "derived")
OTOMATIK = TURETILMIS / "floor_semantic_maps.json"
DUZELTME = TURETILMIS / "semantic_map_overrides.json"


def _oku(yol: Path) -> Dict[str, Any]:
    if not yol.exists():
        return {}
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # Bozuk düzeltme dosyası yüzünden HARİTANIN TAMAMI kaybolmamalı;
        # hata görünür kılınır, otomatik katman çalışmaya devam eder.
        return {"_hata": f"{yol.name} okunamadı: {e}"}


def kat_haritalari() -> Dict[str, Any]:
    oto = _oku(OTOMATIK)
    if not oto:
        return {"available": False, "floors": {},
                "note": ("Semantik kat haritası üretilmemiş. "
                         "`python build_semantic_map.py` çalıştırın.")}

    duz = _oku(DUZELTME)
    uyari = duz.get("_hata")
    katlar = oto.get("floors", {})

    sil: List[str] = [str(x) for x in duz.get("remove", [])]
    guncelle = {d["area_id"]: d for d in duz.get("update", [])
                if isinstance(d, dict) and d.get("area_id")}
    eklenecek = [d for d in duz.get("add", [])
                 if isinstance(d, dict) and d.get("area_id") and d.get("polygon")]

    sayim = {"removed": 0, "updated": 0, "added": 0, "unmatched_update": []}
    uygulanan: set[str] = set()

    for f in katlar.values():
        odalar = []
        for oda in f.get("rooms", []):
            if oda["area_id"] in sil:
                sayim["removed"] += 1
                continue
            oda = {**oda, "origin": "auto"}
            yama = guncelle.get(oda["area_id"])
            if yama:
                # `area_id`, `polygon` ve `floor` GÜNCELLENMEZ: bunlar
                # kimlik ve geometridir. Düzeltme katmanı yalnızca
                # semantiği (tür/etiket/alan) taşır; geometri değişikliği
                # istenirse remove + add ile açıkça yapılır.
                for k in ("room_type", "architectural_label", "area_m2"):
                    if k in yama:
                        oda[k] = yama[k]
                oda["origin"] = "manual-update"
                oda["override_source"] = yama.get("source")
                sayim["updated"] += 1
                uygulanan.add(oda["area_id"])
            odalar.append(oda)
        f["rooms"] = odalar

    mevcut_kimlik = {o["area_id"] for f in katlar.values() for o in f["rooms"]}
    for d in eklenecek:
        kat = str(d.get("floor"))
        if kat not in katlar:
            continue
        if d["area_id"] in mevcut_kimlik:
            # Otomatik çıkarım aynı odayı bulmaya başladıysa elle kopya
            # EKLENMEZ; aksi hâlde iki poligon üst üste biner ve kullanıcı
            # aynı dersliği iki kez eşleştirebilirdi.
            continue
        katlar[kat].setdefault("rooms", []).append({
            "area_id": d["area_id"],
            "architectural_label": d.get("architectural_label", d["area_id"]),
            "room_type": d.get("room_type", "CLASSROOM"),
            "area_m2": d.get("area_m2"),
            "polygon": d["polygon"],
            "origin": "manual",
            "override_source": d.get("source"),
        })
        mevcut_kimlik.add(d["area_id"])
        sayim["added"] += 1

    # Hedefi bulunamayan düzeltme SESSİZCE YUTULMAZ. Otomatik çıkarım bir
    # `area_id` üretmeyi bıraktıysa (ör. tohum konumu kaydığı için kimlik
    # değiştiyse) o düzeltme artık hiçbir şeye uygulanmıyordur; bunu
    # yanıtta göstermek, "düzelttim sanıyordum" durumunu engeller.
    sayim["unmatched_update"] = sorted(guncelle.keys() - uygulanan)

    sonuc = {"available": True, **oto, "overrides": sayim}
    if uyari:
        sonuc["override_warning"] = uyari
    return sonuc
