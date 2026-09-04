"""SEMANTİK KAT HARİTASI — temiz, sadeleştirilmiş plan üretir.

AMAÇ
----
PDF yalnızca GEOMETRİ VE METİN KAYNAĞIDIR. Ekranda mimari pafta
gösterilmez: ne lejant, ne kot çizgisi, ne ölçülendirme, ne pafta
çerçevesi, ne de 20 binden fazla CAD ilkeli.

Üretilen çıktı:

    data/infrastructure/derived/floor_semantic_maps.json
      { floor, outline, corridors, rooms[], landmarks[] }

YÖNTEM — ETİKET GÜDÜMLÜ ODA ÇIKARIMI
------------------------------------
"Kapalı alan = oda" varsayımı YAPILMAZ (o yöntem koridoru, şaftı ve
pafta boşluğunu da oda sanıyordu). Bunun yerine:

    GÜVENİLİR ODA ETİKETİ  ("13 - SINIF-b", "AMFİ-3", "FİZİK LAB.")
              ↓
    ETİKETİN MERKEZİ = SEED
              ↓
    SEED'İ ÇEVRELEYEN DUVAR BÖLGESİ  (kapı boşlukları morfolojik
              ↓                       kapama ile köprülenir)
    ODA POLİGONU

Etiketi olmayan hiçbir bölge derslik sayılmaz. Kapama yarıçapı kapı
genişliği kadardır; koridoru komşu odayla birleştirecek kadar agresif
değildir.

BEYAZ LİSTE
-----------
Etkileşimli oda YALNIZCA ders programıyla ilgili olabilecek türlerdir:
SINIF / LAB / LABORATUVAR / AMFİ / STÜDYO / ATÖLYE.
WC, koridor, şaft, merdiven, depo, idari oda vb. etkileşimli DEĞİLDİR;
haritada yalnızca yön bulma amaçlı sade referans olarak görünür.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pymupdf

KOK = Path(__file__).resolve().parent.parent
HAM = KOK / "data" / "infrastructure" / "raw"
TURETILMIS = KOK / "data" / "infrastructure" / "derived"

KATLAR = [
    {"floor": 0, "pdf": "0. Kat.pdf"},
    {"floor": 1, "pdf": "1. Kat.pdf"},
    {"floor": 2, "pdf": "2. Kat.pdf"},
]

#: Izgara çözünürlüğü (punto/hücre).
IZ = 1.0
#: Kapı köprüleme yarıçapı (hücre). Kapı ≈ 6pt; 3 hücrelik kapama
#: (dilate→erode) 6pt'lik boşluğu kapatır ama koridoru odaya bağlamaz.
KAPI = 3
#: Oda alan aralığı (pt²). Plan ölçeğinde 1pt² ≈ 0.022 m².
MIN_ALAN = 500.0
MAX_ALAN = 13000.0

# ---------------------------------------------------------------------------
# ETİKET SÖZLÜĞÜ
# ---------------------------------------------------------------------------

#: Ders programıyla ilgili olabilecek mekân türleri (BEYAZ LİSTE).
TUR_KALIPLARI = [
    ("AMPHI", re.compile(r"AMF[İI]", re.I)),
    ("LAB", re.compile(r"\bLAB\b|LABORATUVAR", re.I)),
    ("STUDIO", re.compile(r"STÜDYO|STUDYO|ATÖLYE|ATOLYE", re.I)),
    ("CLASSROOM", re.compile(r"SINIF|DERSL[İI]K", re.I)),
]

#: Etkileşimli oda OLMAYAN mekânlar. Bunlar haritada sade referans
#: alanı olarak kalır; occupancy poligonu değildir.
DISLANAN = re.compile(
    r"\bWC\b|KOR[İI]DOR|HOL\b|FUAYE|ŞAFT|SAFT|MERD[İI]VEN|ASANSÖR|ASANSOR|"
    r"DEPO|TEKN[İI]K|[İI]DAR[İI]|REKTÖR|REKTOR|SEKRETER|MESC[İI]T|MUTFAK|"
    r"TERAS|KAFE|BANYO|ARŞ[İI]V|ARSIV|S[İI]STEM|PANO|MÜTEVELL[İI]|"
    r"TOPLANTI|[İI]HALE|PUAYE|SOSYAL|OTOPARK|SIĞINAK|SIGINAK", re.I)

#: Yön bulma işaretleri (etkileşimsiz).
LANDMARK = re.compile(r"MERD[İI]VEN|ASANSÖR|ASANSOR|\bWC\b|FUAYE", re.I)

#: GERÇEK ODA ETİKETİ Mİ?
#: Pafta lejantında da "SINIF-a", "SINIF-c" gibi çıplak anahtarlar var.
#: Bunlar oda DEĞİL, açıklama satırıdır. Gerçek oda etiketi ya bir oda
#: numarası taşır ("13 - SINIF-b") ya da adlandırılmış bir mekândır
#: ("AMFİ-3", "FİZİK LAB.", "LAB 08").
NUMARALI = re.compile(r"^\s*(\d{1,2})\s*[-–]\s*(.+)$")
ADLANDIRILMIS = re.compile(
    r"AMF[İI]\s*[-\s]?\s*\d+|LAB\s*[-\s]?\s*\d+|LABORATUVAR\w*\s*\d*|"
    r"[A-ZÇĞİÖŞÜ]{3,}\s+LAB\.?|STÜDYO\w*", re.I)


def oda_turu(metin: str) -> Optional[str]:
    if DISLANAN.search(metin):
        return None
    for tur, kalip in TUR_KALIPLARI:
        if kalip.search(metin):
            return tur
    return None


def gercek_oda_etiketi(metin: str) -> bool:
    """Lejant satırını gerçek oda etiketinden ayırır."""
    m = NUMARALI.match(metin)
    if m:
        return True
    return bool(ADLANDIRILMIS.search(metin))


# ---------------------------------------------------------------------------
# DUVAR MASKESİ + MORFOLOJİ
# ---------------------------------------------------------------------------

def duvar_maskesi(sayfa) -> Tuple[bytearray, int, int]:
    G, Y = float(sayfa.rect.width), float(sayfa.rect.height)
    gw, gh = int(G / IZ) + 2, int(Y / IZ) + 2
    m = bytearray(gw * gh)

    def parca(x0, y0, x1, y1):
        n = int(max(abs(x1 - x0), abs(y1 - y0)) / IZ) + 1
        for i in range(n + 1):
            t = i / n if n else 0.0
            cx = int((x0 + (x1 - x0) * t) / IZ)
            cy = int((y0 + (y1 - y0) * t) / IZ)
            if 0 <= cx < gw and 0 <= cy < gh:
                m[cy * gw + cx] = 1

    for g in sayfa.get_drawings():
        kutu = g.get("rect")
        # Pafta çerçevesi ve sayfa boyu dikdörtgenler duvar değildir.
        if kutu is not None and kutu.width * kutu.height > 700000:
            continue
        for it in g["items"]:
            if it[0] == "l":
                parca(it[1].x, it[1].y, it[2].x, it[2].y)
            elif it[0] == "c":
                a, b, c, d = it[1], it[2], it[3], it[4]
                onceki = (a.x, a.y)
                for k in range(1, 9):
                    t = k / 8
                    mt = 1 - t
                    x = (mt ** 3 * a.x + 3 * mt * mt * t * b.x
                         + 3 * mt * t * t * c.x + t ** 3 * d.x)
                    y = (mt ** 3 * a.y + 3 * mt * mt * t * b.y
                         + 3 * mt * t * t * c.y + t ** 3 * d.y)
                    parca(onceki[0], onceki[1], x, y)
                    onceki = (x, y)
            elif it[0] == "qu":
                q = it[1]
                pts = [q.ul, q.ur, q.lr, q.ll, q.ul]
                for i in range(4):
                    parca(pts[i].x, pts[i].y, pts[i + 1].x, pts[i + 1].y)
            elif it[0] == "re":
                r = it[1]
                parca(r.x0, r.y0, r.x1, r.y0); parca(r.x0, r.y1, r.x1, r.y1)
                parca(r.x0, r.y0, r.x0, r.y1); parca(r.x1, r.y0, r.x1, r.y1)
    return m, gw, gh


def _genislet(m, gw, gh, k):
    """Morfolojik genişletme (kare yapı elemanı, ayrık iki geçiş)."""
    ara = bytearray(gw * gh)
    for y in range(gh):                       # yatay
        satir = y * gw
        for x in range(gw):
            if m[satir + x]:
                for dx in range(-k, k + 1):
                    nx = x + dx
                    if 0 <= nx < gw:
                        ara[satir + nx] = 1
    son = bytearray(gw * gh)
    for x in range(gw):                       # dikey
        for y in range(gh):
            if ara[y * gw + x]:
                for dy in range(-k, k + 1):
                    ny = y + dy
                    if 0 <= ny < gh:
                        son[ny * gw + x] = 1
    return son


def _daralt(m, gw, gh, k):
    """Morfolojik aşındırma — genişletmenin tersi."""
    ters = bytearray(1 - v for v in m)
    ters = _genislet(ters, gw, gh, k)
    return bytearray(1 - v for v in ters)


def kapi_kapat(m, gw, gh):
    """Kapama = genişlet → daralt. Kapı boşluklarını köprüler,
    duvar kalınlığını korur, koridoru odaya BAĞLAMAZ."""
    return _daralt(_genislet(m, gw, gh, KAPI), gw, gh, KAPI)


# ---------------------------------------------------------------------------
# BÖLGE ÇIKARIMI
# ---------------------------------------------------------------------------

def _dolgu(m, gw, gh, sx, sy, sinir, yasak=None):
    i0 = sy * gw + sx
    if m[i0] or (yasak and i0 in yasak):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (0, 2),
                       (-2, 0), (0, -2), (3, 0), (0, 3)):
            nx, ny = sx + dx, sy + dy
            if 0 <= nx < gw and 0 <= ny < gh:
                j = ny * gw + nx
                if not m[j] and not (yasak and j in yasak):
                    sx, sy, i0 = nx, ny, j
                    break
        else:
            return None
    gor = bytearray(gw * gh)
    gor[i0] = 1
    kuy = deque([i0])
    hep = []
    while kuy:
        i = kuy.popleft()
        hep.append(i)
        if len(hep) > sinir:
            return None                      # sızdı → oda değil
        x, y = i % gw, i // gw
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < gw and 0 <= ny < gh:
                j = ny * gw + nx
                if not gor[j] and not m[j]:
                    gor[j] = 1
                    kuy.append(j)
    return hep


def _sinir(hucreler: List[int], gw: int, olcek: float = IZ):
    kume = set(hucreler)
    kenar: Dict[Tuple[float, float], List[Tuple[float, float]]] = defaultdict(list)
    for i in kume:
        x, y = i % gw, i // gw
        x0, y0 = x * olcek, y * olcek
        x1, y1 = x0 + olcek, y0 + olcek
        if (i - gw) not in kume: kenar[(x0, y0)].append((x1, y0))
        if (i + gw) not in kume: kenar[(x1, y1)].append((x0, y1))
        if (i - 1) not in kume or x == 0: kenar[(x0, y1)].append((x0, y0))
        if (i + 1) not in kume or x == gw - 1: kenar[(x1, y0)].append((x1, y1))
    if not kenar:
        return []
    bas = min(kenar)
    halka = [bas]; su = bas
    for _ in range(len(kenar) * 4 + 16):
        if su not in kenar or not kenar[su]:
            break
        nx = kenar[su].pop()
        if not kenar[su]:
            del kenar[su]
        halka.append(nx); su = nx
        if su == bas:
            break
    return _sadelestir(halka)


def _sadelestir(p):
    if len(p) < 3:
        return p
    c = [p[0]]
    for i in range(1, len(p) - 1):
        ax, ay = c[-1]; bx, by = p[i]; cx, cy = p[i + 1]
        if (abs(ax - bx) < .01 and abs(bx - cx) < .01) or \
           (abs(ay - by) < .01 and abs(by - cy) < .01):
            continue
        c.append(p[i])
    c.append(p[-1])
    return [[round(x, 1), round(y, 1)] for x, y in c]


def etiketleri_topla(sayfa):
    cikti = []
    for b in sayfa.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                t = re.sub(r"\s+", " ", (s.get("text") or "")).strip()
                if not t or len(t) > 40:
                    continue
                bb = s["bbox"]
                cikti.append({"t": t, "x": (bb[0] + bb[2]) / 2,
                              "y": (bb[1] + bb[3]) / 2, "boy": s.get("size", 6)})
    return cikti


def kat_uret(kat: int, pdf_adi: str) -> dict:
    belge = pymupdf.open(HAM / pdf_adi)
    sayfa = belge[0]
    G, Y = float(sayfa.rect.width), float(sayfa.rect.height)
    ham, gw, gh = duvar_maskesi(sayfa)
    maske = kapi_kapat(ham, gw, gh)
    etiketler = etiketleri_topla(sayfa)
    belge.close()

    # BİNA İÇİ: sayfa kenarından erişilebilen boşluk DIŞARIDIR.
    dis = _dolgu(maske, gw, gh, 1, 1, gw * gh)
    dis_kume = set(dis or [])

    sinir_hucre = int(MAX_ALAN / (IZ * IZ))
    min_hucre = int(MIN_ALAN / (IZ * IZ))

    odalar, kullanilan = [], set()
    sayac = {"etiket": 0, "poligon_yok": 0, "sizdi": 0, "kucuk": 0, "cakisti": 0}

    # PAFTANIN GERÇEK ETİKET YAPISI
    # -----------------------------
    # Oda ADI odanın İÇİNDE yazmaz. İçeride yalnızca "13-86.7 m²" gibi
    # ODA NUMARASI + ALAN vardır; mekân TÜRÜ ise paftanın kenarındaki
    # lejantta "13- SINIF-c" olarak listelenir. Bu yüzden:
    #     lejant   → numara ➜ tür/etiket
    #     oda içi  → numara ➜ konum (seed)
    # ikisi numara üzerinden birleştirilir. Lejant satırının kendisi
    # bina dışında olduğu için seed OLARAK KULLANILMAZ (kullanılsaydı
    # dolgu tüm sayfaya sızardı — önceki sürümün "sızdı" sayıları buydu).
    LEJANT = re.compile(r"^\s*(\d{1,2})\s*[-–]\s*([A-Za-zÇĞİÖŞÜçğıöşü].*)$")
    ODA_ICI = re.compile(r"^\s*(\d{1,2})\s*[-–]\s*(\d{1,3}[.,]\d+)")

    lejant = {}
    for e in etiketler:
        m = LEJANT.match(e["t"])
        if m and oda_turu(m.group(2)):
            lejant[int(m.group(1))] = m.group(2).strip()

    tohumlar = []
    for e in etiketler:
        m = ODA_ICI.match(e["t"])
        if m:                                   # numaralı oda: türü lejanttan
            no = int(m.group(1))
            if no in lejant:
                tohumlar.append({**e, "no": no, "ad": lejant[no],
                                 "alan_m2": float(m.group(2).replace(",", "."))})
            continue
        # Doğrudan adlandırılmış mekân (AMFİ-3, FİZİK LAB., LAB-1, STÜDYOSU)
        if oda_turu(e["t"]) and ADLANDIRILMIS.search(e["t"]):
            tohumlar.append({**e, "no": None, "ad": e["t"], "alan_m2": None})

    # ÜÇÜNCÜ ETİKET YAPISI — 0. kat paftası
    # -------------------------------------
    # Bu paftada numara/lejant eşlemesi yok: mekân TÜRÜ odanın içine
    # çıplak yazılmış ("SINIF"), alan ise komşu bir span'de ("132.70 m²").
    # Tür sözcüğü zaten konumun kendisi olduğu için doğrudan tohumdur.
    ALAN_SPAN = re.compile(r"^\s*(\d{1,4}(?:[.,]\d+)?)\s*m²\s*$")
    alan_spanlari = [(a, float(m.group(1).replace(",", ".")))
                     for a in etiketler
                     for m in [ALAN_SPAN.match(a["t"])] if m]
    for e in etiketler:
        if NUMARALI.match(e["t"]) or ADLANDIRILMIS.search(e["t"]):
            continue
        if len(e["t"]) > 24 or not oda_turu(e["t"]):
            continue
        yakin = min(((a, v, math.hypot(a["x"] - e["x"], a["y"] - e["y"]))
                     for a, v in alan_spanlari),
                    key=lambda p: p[2], default=None)
        tohumlar.append({**e, "no": None, "ad": e["t"],
                         "alan_m2": yakin[1] if yakin and yakin[2] <= 45 else None})

    sayac["etiket"] = len(tohumlar)

    for e in sorted(tohumlar, key=lambda t: (t["no"] is None, t["no"] or 0)):
        sx, sy = int(e["x"] / IZ), int(e["y"] / IZ)
        if not (0 <= sx < gw and 0 <= sy < gh):
            sayac["poligon_yok"] += 1; continue
        # BİNA DIŞINDAKİ ETİKET ODA DEĞİLDİR. Paftanın kenarındaki lejant
        # kopyaları buradan elenir; onlar tohum yapılırsa dolgu bina
        # dışındaki boşlukta yayılıp bütün sayfayı "oda" sanır.
        if (sy * gw + sx) in dis_kume:
            sayac["poligon_yok"] += 1; continue
        h = _dolgu(maske, gw, gh, sx, sy, sinir_hucre)
        if h is None:
            sayac["sizdi"] += 1; continue
        if len(h) < min_hucre:
            sayac["kucuk"] += 1; continue
        kume = set(h)
        if kume & kullanilan:
            sayac["cakisti"] += 1; continue
        poligon = _sinir(h, gw)
        if len(poligon) < 4:
            sayac["poligon_yok"] += 1; continue
        kullanilan |= kume
        tur = oda_turu(e["ad"]) or "CLASSROOM"
        alan_m2 = (e["alan_m2"] if e["alan_m2"] is not None
                   else round(len(h) * IZ * IZ * 0.0222, 1))

        # KİMLİK BENZERSİZ OLMAK ZORUNDA. 0. kat paftasında oda numarası
        # yoktur; her etiket çıplak "SINIF" yazar. Yalnızca ada dayanan
        # bir kimlik orada 15 odayı aynı `area_id` altında toplar ve
        # kullanıcının derslik eşleştirmesi sessizce yanlış odaya
        # bağlanırdı. Numara yoksa kimlik SEED KONUMUNDAN türetilir:
        # konum paftaya özgüdür ve yeniden üretimde kararlıdır.
        if e["no"] is not None:
            kimlik = str(e["no"])
            etiket = f"{e['no']} - {e['ad']}"
        else:
            ad_kok = re.sub(r"[^A-Za-z0-9]", "", e["ad"])[:10] or "oda"
            kimlik = f"{ad_kok}_{int(e['x'])}x{int(e['y'])}"
            etiket = (f"{e['ad']} · {alan_m2} m²" if e["alan_m2"] is not None
                      else e["ad"])
        odalar.append({
            "area_id": f"floor{kat}_{tur.lower()}_{kimlik}",
            "architectural_label": etiket,
            "room_type": tur,
            "area_m2": alan_m2,
            "polygon": poligon,
        })

    # KORİDOR / ORTAK ALAN: bina içinde kalan, odaya ait olmayan büyük
    # boşluklar. Etkileşimsizdir; yalnızca yön bulma için çizilir.
    koridorlar = []
    gorulen = set(kullanilan) | dis_kume
    for i in range(gw * gh):
        if maske[i] or i in gorulen:
            continue
        h = _dolgu(maske, gw, gh, i % gw, i // gw, gw * gh, yasak=gorulen)
        if not h:
            gorulen.add(i); continue
        gorulen |= set(h)
        if len(h) < 3000:                     # küçük boşluk/şaft → çizilmez
            continue
        p = _sinir(h, gw)
        if len(p) >= 4:
            koridorlar.append({"polygon": p})

    # BİNA SINIRI: dış boşluğun tümleyeni.
    ic = [i for i in range(gw * gh) if i not in dis_kume]
    outline = _sinir(ic, gw) if ic else []

    # YÖN BULMA İŞARETLERİ (etkileşimsiz nokta etiketleri).
    landmarks = [{"label": e["t"], "x": round(e["x"], 1), "y": round(e["y"], 1)}
                 for e in etiketler if LANDMARK.search(e["t"])][:40]

    return {"floor": kat, "width": G, "height": Y,
            "viewBox": f"0 0 {G:.0f} {Y:.0f}",
            "outline": outline, "corridors": koridorlar,
            "rooms": odalar, "landmarks": landmarks,
            "stats": {**sayac, "oda": len(odalar), "koridor": len(koridorlar)}}


def main() -> None:
    if not (HAM / KATLAR[0]["pdf"]).exists():
        raise SystemExit(f"Ham plan bulunamadı: {HAM}")
    TURETILMIS.mkdir(parents=True, exist_ok=True)
    katlar = {}
    for k in KATLAR:
        v = kat_uret(k["floor"], k["pdf"])
        katlar[str(k["floor"])] = v
        s = v["stats"]
        print(f"  Kat {k['floor']}: {s['oda']}/{s['etiket']} oda "
              f"(sızdı {s['sizdi']}, küçük {s['kucuk']}, çakıştı {s['cakisti']}, "
              f"dışarıda {s['poligon_yok']}) · {s['koridor']} koridor · "
              f"{len(v['landmarks'])} işaret")
    yol = TURETILMIS / "floor_semantic_maps.json"
    yol.write_text(json.dumps(
        {"meta": {"generated_by": "build_semantic_map.py",
                  "source": [k["pdf"] for k in KATLAR],
                  "note": ("Etiket güdümlü oda çıkarımı. Pafta, lejant, kot ve "
                           "CAD detayı İÇERMEZ.")},
         "floors": katlar}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    print(f"  {yol.name}: {yol.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
