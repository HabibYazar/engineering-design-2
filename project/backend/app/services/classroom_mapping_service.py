"""DERSLİK EŞLEŞTİRME MODU — kullanıcı tanımlı kroki alanları (kalıcı).

NE SAKLAR
---------
Kullanıcının kat planı üzerinde ELLE çizdiği alanları ve bu alanlara
atadığı gerçek derslik kodlarını.

NEDEN AYRI DOSYA
----------------
`room_geometry.json` her `build_infrastructure_map.py` çalışmasında
YENİDEN ÜRETİLİR (üzerine yazılır). Kullanıcının elle yaptığı
eşleştirmeler oraya yazılsaydı, üretici bir daha koştuğunda sessizce
SİLİNİRDİ. Bu yüzden kullanıcı verisi kendi dosyasında durur:

    derived/room_schedule_mapping.json     ← ELLE, kalıcı (bu servis)
    derived/room_geometry.json             ← ÜRETİLMİŞ, üzerine yazılır

Okuma sırasında ikisi birleştirilir; çakışmada KULLANICI kazanır.

NEDEN VERİTABANI DEĞİL
----------------------
Bu bir kurumsal kayıt değil, bir görselleştirme yapılandırmasıdır.
Şemaya tablo eklemek, mevcut fiziksel kaynak kayıtlarıyla karıştırma
riski doğururdu. Dosya, süreç yeniden başlasa da kalıcıdır.

YAZMA GÜVENLİĞİ
---------------
Yazma ATOMİKTİR: önce geçici dosyaya yazılır, sonra `os.replace` ile
yerine taşınır. Yazma sırasında süreç ölse bile yarım JSON kalmaz.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TURETILMIS = (Path(__file__).resolve().parents[3]
              / "data" / "infrastructure" / "derived")
ESLESME_DOSYASI = TURETILMIS / "room_schedule_mapping.json"

SEMA_SURUMU = 1


class EslesmeHatasi(ValueError):
    """Doğrulama hatası — çağıran 400/409'a çevirir."""

    def __init__(self, mesaj: str, ayrinti: Optional[dict] = None):
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.ayrinti = ayrinti or {}


def _bos() -> dict:
    return {"version": SEMA_SURUMU, "updated_at": None, "areas": []}


def esleme_oku() -> dict:
    """Kalıcı dosyayı okur. Yoksa boş yapı döner (hata değil).

    ÖNBELLEK YOK: dosya küçüktür ve kaydetme sonrası anında görünmesi,
    bayat bir önbellekten daha değerlidir.
    """
    if not ESLESME_DOSYASI.exists():
        return _bos()
    try:
        veri = json.loads(ESLESME_DOSYASI.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Bozuk dosya sessizce "boş" sayılmaz: kullanıcı verisi kaybolmuş
        # gibi davranmak yerine durum bildirilir.
        return {**_bos(), "error": "Eşleştirme dosyası okunamadı (bozuk JSON)."}
    if not isinstance(veri, dict) or not isinstance(veri.get("areas"), list):
        return {**_bos(), "error": "Eşleştirme dosyası beklenen yapıda değil."}
    return veri


def _gecerli_oda_kodlari() -> Dict[str, dict]:
    """Excel envanterindeki GERÇEK derslikler: kod → oda.

    Atanabilir kod listesi buradan gelir; arayüz de bunu gösterir.
    Envanterde olmayan bir kod kabul EDİLMEZ — uydurma oda oluşmaz.
    """
    yol = TURETILMIS / "classroom_usage.json"
    if not yol.exists():
        return {}
    veri = json.loads(yol.read_text(encoding="utf-8"))
    return {o["room_code"]: o for o in veri.get("rooms", [])}


def _gecerli_katlar() -> set:
    yol = TURETILMIS / "classroom_usage.json"
    if not yol.exists():
        return set()
    veri = json.loads(yol.read_text(encoding="utf-8"))
    return {f["floor"] for f in veri.get("floors", [])}


def _sekil_dogrula(sekil: object, nerede: str) -> dict:
    """Yalnızca 0–1 normalize dikdörtgen kabul edilir.

    Normalize koordinat, arka plan görseli yeniden ölçeklendiğinde
    alanın kaymamasını garanti eder. Sınır dışı ya da sıfır alanlı
    dikdörtgen, ekranda görünmeyen "hayalet" eşleştirme yaratırdı.
    """
    if not isinstance(sekil, dict) or sekil.get("type") != "rect":
        raise EslesmeHatasi(f"{nerede}: yalnızca 'rect' şekli desteklenir.")
    try:
        d = {k: float(sekil[k]) for k in ("x", "y", "w", "h")}
    except (KeyError, TypeError, ValueError):
        raise EslesmeHatasi(f"{nerede}: rect için x/y/w/h sayısal olmalıdır.")
    if d["w"] <= 0 or d["h"] <= 0:
        raise EslesmeHatasi(f"{nerede}: genişlik ve yükseklik sıfırdan büyük olmalıdır.")
    if not (0 <= d["x"] <= 1 and 0 <= d["y"] <= 1):
        raise EslesmeHatasi(f"{nerede}: x/y 0–1 aralığında olmalıdır.")
    if d["x"] + d["w"] > 1.0001 or d["y"] + d["h"] > 1.0001:
        raise EslesmeHatasi(f"{nerede}: alan planın dışına taşıyor.")
    return {"type": "rect", **{k: round(v, 5) for k, v in d.items()}}


def _poligon_dogrula(ham: object, nerede: str):
    """Kullanıcının çizdiği poligon. PDF punto koordinatlarında.

    En az 3 nokta gerekir: iki nokta bir alan tanımlamaz ve ekranda
    görünmez bir "hayalet" eşleştirme yaratırdı. Koordinatlar plan
    kutusuyla aynı sistemde olduğu için ölçekten bağımsızdır.
    """
    if ham in (None, ""):
        return None
    if not isinstance(ham, list) or len(ham) < 3:
        raise EslesmeHatasi(f"{nerede}: poligon en az 3 nokta içermelidir.")
    nokta = []
    for i, n in enumerate(ham):
        if not isinstance(n, (list, tuple)) or len(n) != 2:
            raise EslesmeHatasi(f"{nerede}: {i + 1}. nokta [x, y] olmalıdır.")
        try:
            x, y = float(n[0]), float(n[1])
        except (TypeError, ValueError):
            raise EslesmeHatasi(f"{nerede}: {i + 1}. nokta sayısal değil.")
        if not (0 <= x <= 5000 and 0 <= y <= 5000):
            raise EslesmeHatasi(f"{nerede}: {i + 1}. nokta plan sınırları dışında.")
        nokta.append([round(x, 2), round(y, 2)])
    return nokta


def esleme_dogrula(gelen: object) -> Tuple[dict, List[dict]]:
    """Tam yükü doğrular. Dönüş: (temiz_veri, uyarilar)."""
    if not isinstance(gelen, dict):
        raise EslesmeHatasi("Gövde bir nesne olmalıdır.")
    alanlar = gelen.get("areas")
    if not isinstance(alanlar, list):
        raise EslesmeHatasi("'areas' bir dizi olmalıdır.")

    kodlar = _gecerli_oda_kodlari()
    katlar = _gecerli_katlar()
    temiz: List[dict] = []
    gorulen_kod: Dict[str, str] = {}
    gorulen_id: set = set()
    uyarilar: List[dict] = []

    for i, a in enumerate(alanlar):
        nerede = f"Alan #{i + 1}"
        if not isinstance(a, dict):
            raise EslesmeHatasi(f"{nerede}: nesne olmalıdır.")

        aid = str(a.get("area_id") or "").strip() or f"a{i + 1}"
        if aid in gorulen_id:
            raise EslesmeHatasi(f"{nerede}: yinelenen area_id '{aid}'.")
        gorulen_id.add(aid)

        try:
            kat = int(a.get("floor"))
        except (TypeError, ValueError):
            raise EslesmeHatasi(f"{nerede}: 'floor' tam sayı olmalıdır.")
        if katlar and kat not in katlar:
            raise EslesmeHatasi(
                f"{nerede}: kat {kat} planlarda yok "
                f"(geçerli: {sorted(katlar)}).")

        # DERSLİK ALANI = KULLANICININ ÇİZDİĞİ POLİGON
        # --------------------------------------------
        # Otomatik oda çıkarımı kaldırıldı: plandan "kapalı alan"
        # bularak oda üretmek koridoru, şaftı ve cephe boşluğunu da
        # derslik sanıyordu. Artık sınırı KULLANICI belirler; base plan
        # yalnızca mimari çizimdir.
        poligon = _poligon_dogrula(a.get("polygon"), nerede)
        # Eski sürümden kalan dikdörtgen kayıtları da okunabilsin.
        sekil = _sekil_dogrula(a.get("shape"), nerede) if a.get("shape") else None
        if poligon is None and sekil is None:
            raise EslesmeHatasi(
                f"{nerede}: alanın `polygon` (en az 3 nokta) tanımı yok.")

        kod = a.get("room_code")
        kod = str(kod).strip() if kod not in (None, "") else None
        if kod is not None:
            if kodlar and kod not in kodlar:
                raise EslesmeHatasi(
                    f"{nerede}: '{kod}' Excel derslik envanterinde yok.",
                    {"invalid_room_code": kod})
            # YİNELENEN DERSLİK — sessizce kabul edilmez.
            if kod in gorulen_kod:
                raise EslesmeHatasi(
                    f"'{kod}' zaten başka bir alana atanmış.",
                    {"duplicate_room_code": kod,
                     "existing_area_id": gorulen_kod[kod],
                     "conflicting_area_id": aid})
            gorulen_kod[kod] = aid
            # Kat tutarlılığı: uyarı, engel değil — kullanıcı planı bizden
            # iyi biliyor olabilir; ama sessiz de kalınmaz.
            oda = kodlar.get(kod)
            if oda and oda.get("floor") != kat:
                uyarilar.append({
                    "area_id": aid, "room_code": kod,
                    "message": (f"'{kod}' Excel'de kat {oda['floor']} olarak "
                                f"kayıtlı, alan ise kat {kat} üzerinde."),
                })

        temiz.append({
            "area_id": aid,
            "floor": kat,
            "polygon": poligon,
            "shape": sekil,
            "label": (str(a.get("label")).strip() or None) if a.get("label") else None,
            "room_code": kod,
        })

    return {
        "version": SEMA_SURUMU,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "areas": temiz,
    }, uyarilar


def esleme_yaz(gelen: object) -> dict:
    """Doğrular ve ATOMİK olarak diske yazar."""
    veri, uyarilar = esleme_dogrula(gelen)
    TURETILMIS.mkdir(parents=True, exist_ok=True)

    # Aynı dizine geçici dosya: `os.replace` yalnızca aynı dosya
    # sisteminde atomiktir.
    gecici = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=TURETILMIS,
                prefix=".room_mapping_", suffix=".tmp", delete=False) as f:
            gecici = Path(f.name)
            json.dump(veri, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, ESLESME_DOSYASI)
        gecici = None
    finally:
        if gecici and gecici.exists():
            gecici.unlink(missing_ok=True)

    return {"saved": True, "area_count": len(veri["areas"]),
            "updated_at": veri["updated_at"], "warnings": uyarilar,
            "file": ESLESME_DOSYASI.name}


def esleme_durumu() -> dict:
    """GET yanıtı: kalıcı alanlar + atanabilir derslik listesi."""
    veri = esleme_oku()
    kodlar = _gecerli_oda_kodlari()
    atanmis = {a.get("room_code") for a in veri.get("areas", []) if a.get("room_code")}
    return {
        "version": veri.get("version", SEMA_SURUMU),
        "updated_at": veri.get("updated_at"),
        "areas": veri.get("areas", []),
        "error": veri.get("error"),
        # Açılır listede GERÇEK derslikler; hangileri zaten atanmış da
        # bildirilir ki arayüz çakışmayı tıklamadan önce gösterebilsin.
        "assignable_rooms": [
            {"room_code": k, "floor": o.get("floor"), "name": o.get("name"),
             "class_capacity": o.get("class_capacity"),
             "already_assigned": k in atanmis}
            for k, o in sorted(kodlar.items())
        ],
        "storage_file": ESLESME_DOSYASI.name,
    }
