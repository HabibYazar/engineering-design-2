"""Niyet farkında deterministik cevap — model susarsa devreye girer.

NEDEN
-----
Model geçici olarak final metni üretemediğinde kullanıcıya şu gösteriliyordu:

    "5 kayıt · 4 farklı university_name · value: en düşük 446.4 ·
     en yüksek 528.4 · ortalama 471.9 · medyan 463.3"

Bu bir veri kümesi istatistiğidir ve kullanıcının sorusundan BAĞIMSIZDIR.
"En düşük taban puanı olan üniversiteler hangileri?" diye soran birine
medyan söylemek cevap değildir; elde gerçek satırlar dururken üstelik
gereksizdir.

Buradaki üretici aynı satırları kullanır ama SORUNUN NİYETİNE göre
biçimlendirir: sıralama sorusuna sıralı liste, tekil değer sorusuna tek
sayı, eğilim sorusuna yıl-değer dizisi.

Bu bir kestirme ya da uydurma değildir: her sayı araç sonucundan gelir,
hiçbiri hesaplanmaz. Model yalnızca CÜMLE kurmak için gerekliydi;
cümleyi kuramadığında veriyi saklamak için bir sebep yok.

İstatistik özeti tamamen kalkmaz — kullanıcı gerçekten dağılım sorduysa
(`aggregation` niyeti) o zaman doğru cevaptır.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.assistant import veri_ailesi

logger = logging.getLogger(__name__)

#: Bir satırda kaç alan gösterilir. Yönetici cevabı kısa olmalı.
_EN_FAZLA_ALAN = 4
#: Listelerde kaç satır gösterilir.
_EN_FAZLA_SATIR = 10

_KIMLIK = re.compile(
    r"(name|ad|title|label|universite|university|program|bolum|department|"
    r"faculty|fakulte|room|kod|code)", re.I)
_YIL = re.compile(r"^(academic_year|year|yil)$", re.I)


def _sayi(deger: Any) -> Optional[float]:
    if isinstance(deger, bool) or deger is None:
        return None
    if isinstance(deger, (int, float)):
        return float(deger)
    try:
        return float(str(deger).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _bicimle(deger: Any) -> str:
    """Sayıyı okunabilir yaz; NULL'u sıfıra çevirme."""
    if deger is None:
        return "—"                      # ölçülmemiş; sıfır DEĞİL
    s = _sayi(deger)
    if s is None:
        return str(deger)
    if abs(s - round(s)) < 1e-9:
        return f"{int(round(s)):,}".replace(",", ".")
    return f"{s:,.1f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _olcum_alanlari(satirlar: Sequence[Dict[str, Any]],
                    plan: veri_ailesi.SorguPlani) -> List[str]:
    """Sorulan metriğe karşılık gelen sayısal alanlar.

    Önce planın metriğiyle eşleşen sütun aranır; yalnızca o yoksa
    herhangi bir sayısal alana düşülür. Sıra önemli: kullanıcı taban
    puan sorduysa kontenjan sütununu göstermek yanlış cevaptır.
    """
    if not satirlar:
        return []
    ilk = satirlar[0]
    sayisal = [a for a, v in ilk.items() if _sayi(v) is not None
               and not _YIL.match(a)]
    if not plan.kavramlar:
        return sayisal[:_EN_FAZLA_ALAN]

    istenen: List[str] = []
    for anahtar in plan.kavramlar:
        kav = next((k for k in veri_ailesi.KAVRAMLAR
                    if k.anahtar == anahtar), None)
        if not kav:
            continue
        for alan in sayisal:
            sade = veri_ailesi.sadelestir(alan)
            if any(ip in sade for ip in kav.sutun) and alan not in istenen:
                istenen.append(alan)
    return (istenen or sayisal)[:_EN_FAZLA_ALAN]


def _kimlik_alani(satirlar: Sequence[Dict[str, Any]]) -> Optional[str]:
    if not satirlar:
        return None
    return next((a for a in satirlar[0] if _KIMLIK.search(a)), None)


def _yil_alani(satirlar: Sequence[Dict[str, Any]]) -> Optional[str]:
    if not satirlar:
        return None
    return next((a for a in satirlar[0] if _YIL.match(a)), None)


def _satir_metni(satir: Dict[str, Any], kimlik: Optional[str],
                 olcumler: Sequence[str]) -> str:
    bas = str(satir.get(kimlik, "")).strip() if kimlik else ""
    degerler = " · ".join(
        f"{a}: {_bicimle(satir.get(a))}" for a in olcumler)
    return f"{bas} — {degerler}" if bas else degerler


# ---------------------------------------------------------------------------
# Niyete göre biçimlendiriciler
# ---------------------------------------------------------------------------
def _ranking(satirlar, plan, kimlik, olcumler) -> str:
    yon = "en düşükten" if plan.artan else "en yüksekten"
    satir_metni = "\n".join(
        f"{i}. {_satir_metni(r, kimlik, olcumler)}"
        for i, r in enumerate(satirlar[:_EN_FAZLA_SATIR], 1))
    return f"Sıralama ({yon} başlayarak):\n{satir_metni}"


def _trend(satirlar, plan, kimlik, olcumler) -> str:
    yil = _yil_alani(satirlar)
    if not yil or not olcumler:
        return ""
    olcum = olcumler[0]
    sirali = sorted(satirlar, key=lambda r: str(r.get(yil)))
    satir_metni = "\n".join(
        f"- {r.get(yil)}: {_bicimle(r.get(olcum))}"
        + (f" ({r.get(kimlik)})" if kimlik and len(
            {str(x.get(kimlik)) for x in sirali}) > 1 else "")
        for r in sirali[:_EN_FAZLA_SATIR])
    return f"{olcum} — dönemlere göre:\n{satir_metni}"


def _tekil(satirlar, plan, kimlik, olcumler) -> str:
    if not olcumler:
        return ""
    satir = satirlar[0]
    parca = " · ".join(f"{a}: {_bicimle(satir.get(a))}" for a in olcumler)
    bas = str(satir.get(kimlik, "")).strip() if kimlik else ""
    return f"{bas} — {parca}" if bas else parca


def _liste(satirlar, plan, kimlik, olcumler) -> str:
    return "\n".join(f"- {_satir_metni(r, kimlik, olcumler)}"
                     for r in satirlar[:_EN_FAZLA_SATIR])


def _toplam(satirlar, plan, kimlik, olcumler) -> str:
    """Toplama YALNIZCA sayılabilir alanlarda; oranların toplamı anlamsız."""
    if not olcumler:
        return ""
    parcalar = []
    for alan in olcumler:
        sade = veri_ailesi.sadelestir(alan)
        degerler = [_sayi(r.get(alan)) for r in satirlar]
        gecerli = [d for d in degerler if d is not None]
        if not gecerli:
            continue
        if any(ip in sade for ip in ("percent", "pct", "oran", "yuzde",
                                     "rate", "ortalama", "avg")):
            # ORANLARIN TOPLAMI DA ORTALAMASI DA YANLIŞTIR.
            parcalar.append(
                f"{alan}: {_bicimle(min(gecerli))} – {_bicimle(max(gecerli))} "
                f"aralığında ({len(gecerli)} kayıt)")
        else:
            parcalar.append(
                f"{alan}: toplam {_bicimle(sum(gecerli))} "
                f"({len(gecerli)} kayıt)")
    return "\n".join(f"- {p}" for p in parcalar)


_BICIMLEYICI = {
    "ranking": _ranking,
    "trend": _trend,
    "comparison": _liste,
    "list": _liste,
    "aggregation": _toplam,
    "single_value": _tekil,
}


def uret(soru: str, kumeler: Sequence[Tuple[str, List[Dict[str, Any]]]]
         ) -> str:
    """Araç sonuçlarından niyete uygun deterministik cevap.

    `kumeler`: (kaynak adı, satırlar) çiftleri — araç çıktıları.
    Boş dönerse çağıran taraf kendi geri düşüşünü kullanır.
    """
    gercek = [(ad, satir) for ad, satir in kumeler if satir]
    if not gercek:
        return ""
    try:
        plan = veri_ailesi.plan_cikar(soru or "")
    except Exception:  # noqa: BLE001
        logger.debug("plan çıkarılamadı", exc_info=True)
        return ""

    bicimleyici = _BICIMLEYICI.get(plan.niyet, _liste)
    bloklar: List[str] = []
    for ad, satirlar in gercek[:2]:
        kimlik = _kimlik_alani(satirlar)
        olcumler = _olcum_alanlari(satirlar, plan)
        if not olcumler:
            continue
        govde = bicimleyici(satirlar, plan, kimlik, olcumler)
        if govde:
            bloklar.append(f"**{ad}**\n{govde}")

    if not bloklar:
        return ""
    return "\n\n".join(bloklar)
