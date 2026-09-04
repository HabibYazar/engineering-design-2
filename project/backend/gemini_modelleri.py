"""Gemini bağlantısını uçtan uca teşhis eder.

NEDEN
-----
"Model bu API anahtarıyla kullanılamıyor" hatasının üç ayrı sebebi
olabilir ve ekrandaki tek satır bunları ayırt etmiyor:

  1. anahtar geçersiz,
  2. `/models` ucu bu anahtar için kapalı (liste alınamıyor),
  3. liste alınıyor ama istenen model içinde yok.

Bu betik üçünü de ayrı ayrı dener ve hangisinin geçerli olduğunu söyler.
Ayrıca gerçek bir sohbet çağrısı yapar: model listesi doğru görünse bile
sohbet ucu farklı davranabiliyor.

KULLANIM
--------
    python gemini_modelleri.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings  # noqa: E402
from app.services.assistant.gemini_provider import (  # noqa: E402
    MODEL_ELE,
    MODEL_TERCIHI,
    model_sec,
)


def _basliklar() -> dict:
    return {
        "Authorization": f"Bearer {settings.GEMINI_API_KEY}",
        "Content-Type": "application/json",
    }


def main() -> int:
    anahtar = settings.GEMINI_API_KEY
    if not anahtar:
        print("GEMINI_API_KEY tanımlı değil. backend/.env dosyasına ekleyin.")
        return 2

    print(f"Anahtar     : {anahtar[:6]}…{anahtar[-4:]}  ({len(anahtar)} karakter)")
    print(f"Uç          : {settings.GEMINI_BASE_URL}")
    print(f"İstenen model: {settings.GEMINI_MODEL}\n")

    # ------------------------------------------------------------------
    # 1) Model listesi — OpenAI uyumlu uç
    # ------------------------------------------------------------------
    print("[1] OpenAI uyumlu uçtan model listesi")
    modeller: list = []
    try:
        r = httpx.get(f"{settings.GEMINI_BASE_URL}/models",
                      headers=_basliklar(), timeout=25)
        print(f"    HTTP {r.status_code}")
        if r.status_code == 200:
            veri = (r.json() or {}).get("data") or []
            modeller = [str(m.get("id")) for m in veri if m.get("id")]
            print(f"    {len(modeller)} model döndü")
        else:
            print(f"    gövde: {r.text[:300]}")
    except Exception as exc:  # noqa: BLE001
        print(f"    BAĞLANTI HATASI: {type(exc).__name__}: {str(exc)[:160]}")

    # ------------------------------------------------------------------
    # 2) Model listesi — Google'ın kendi ucu (yedek teşhis)
    # ------------------------------------------------------------------
    if not modeller:
        print("\n[2] Google'ın kendi ucundan model listesi (yedek deneme)")
        for yol, kimlik in (
            ("https://generativelanguage.googleapis.com/v1beta/models",
             {"key": anahtar}),
            ("https://generativelanguage.googleapis.com/v1/models",
             {"key": anahtar}),
        ):
            try:
                r = httpx.get(yol, params=kimlik, timeout=25)
                print(f"    {yol.rsplit('/', 2)[-2]} → HTTP {r.status_code}")
                if r.status_code == 200:
                    veri = (r.json() or {}).get("models") or []
                    modeller = [str(m.get("name", "")).split("/")[-1]
                                for m in veri if m.get("name")]
                    print(f"    {len(modeller)} model döndü")
                    break
                print(f"    gövde: {r.text[:220]}")
            except Exception as exc:  # noqa: BLE001
                print(f"    HATA: {type(exc).__name__}: {str(exc)[:120]}")

    # ------------------------------------------------------------------
    # 3) Listeyi değerlendir
    # ------------------------------------------------------------------
    if modeller:
        sade = [m.split("/")[-1] for m in modeller]
        elenen = [m for m in sade if any(k in m.lower() for k in MODEL_ELE)]
        uygun = [m for m in sade if m not in elenen]
        print(f"\n[3] Sohbet/araç işine UYGUN görünenler ({len(uygun)}):")
        for m in sorted(uygun):
            print(f"    {m}")
        if elenen:
            print(f"\n    Elenenler — gömme/görüntü/ses ({len(elenen)}):")
            for m in sorted(elenen)[:15]:
                print(f"    {m}")

        secilen = model_sec(sade, settings.GEMINI_MODEL)
        print(f"\n    .env'deki ad listede mi : "
              f"{'EVET' if settings.GEMINI_MODEL in sade else 'HAYIR'}")
        print(f"    Sistemin seçeceği model : {secilen or '(yok)'}")
        if not secilen:
            print("\n    Tercih listesindeki hiçbir aile bulunamadı:")
            for t in MODEL_TERCIHI:
                print(f"      {t}")
            print("\n    Yukarıdaki 'uygun' listeden birini .env dosyasına")
            print("    GEMINI_MODEL=<ad> olarak yazın.")
    else:
        print("\n[3] Model listesi alınamadı — aşağıdaki sohbet denemesi belirleyici.")

    # ------------------------------------------------------------------
    # 4) GERÇEK SOHBET DENEMESİ — asıl kanıt bu
    # ------------------------------------------------------------------
    adaylar = []
    if modeller:
        s = model_sec([m.split("/")[-1] for m in modeller], settings.GEMINI_MODEL)
        if s:
            adaylar.append(s)
    for ad in (settings.GEMINI_MODEL, "gemini-2.0-flash", "gemini-1.5-flash",
               "gemini-2.5-flash"):
        if ad and ad not in adaylar:
            adaylar.append(ad)

    print("\n[4] Gerçek sohbet denemesi (her aday için tek kelimelik istek)")
    calisan = None
    for ad in adaylar[:5]:
        govde = {"model": ad,
                 "messages": [{"role": "user", "content": "merhaba"}],
                 "max_tokens": 10}
        try:
            r = httpx.post(f"{settings.GEMINI_BASE_URL}/chat/completions",
                           headers=_basliklar(), json=govde, timeout=40)
            if r.status_code == 200:
                print(f"    {ad:<28} ÇALIŞTI ✓")
                calisan = calisan or ad
            else:
                try:
                    m = ((r.json() or {}).get("error") or {}).get("message", "")
                except ValueError:
                    m = r.text[:120]
                print(f"    {ad:<28} HTTP {r.status_code} — {str(m)[:110]}")
        except Exception as exc:  # noqa: BLE001
            print(f"    {ad:<28} HATA: {type(exc).__name__}")

    print()
    if calisan:
        print(f"SONUÇ: `{calisan}` çalışıyor.")
        if calisan != settings.GEMINI_MODEL:
            print(f"       backend/.env içinde GEMINI_MODEL={calisan} yapın.")
        return 0
    print("SONUÇ: Hiçbir model çalışmadı. Yukarıdaki hata mesajları sebebi söylüyor:")
    print("       401/403 → anahtar geçersiz (AI Studio'dan yeni anahtar alın)")
    print("       404     → model adı bu anahtar için tanımsız")
    print("       429     → kota doldu")
    return 1


if __name__ == "__main__":
    sys.exit(main())
