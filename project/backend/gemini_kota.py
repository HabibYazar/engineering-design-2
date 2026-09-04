"""Gemini kotasının HANGİSİNİN dolduğunu söyler.

NEDEN
-----
"Kullanım sınırına ulaşıldı" tek başına eyleme dönüşmez. Üç ayrı sınır
var ve çözümleri farklı:

    dakikalık istek (RPM)   → beklemek çözer
    günlük istek   (RPD)    → beklemek ÇÖZMEZ; ertesi güne kadar biter
    dakikalık token (TPM)   → soruyu kısaltmak çözer

Kullanıcı 40 dakika bekleyip aynı hatayı aldıysa sınır dakikalık
değildir. Bu betik tek bir küçük istek atıp Google'ın döndürdüğü kota
kimliğini ve önerdiği bekleme süresini OLDUĞU GİBİ basar.

Tek istek harcar — kota zaten doluysa o isteği de reddedecektir, yani
durumu kötüleştirmez.

KULLANIM
--------
    python gemini_kota.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings  # noqa: E402


def main() -> int:
    if not settings.GEMINI_API_KEY:
        print("GEMINI_API_KEY tanımlı değil.")
        return 2

    model = settings.GEMINI_MODEL
    print(f"Model: {model}\n")

    try:
        r = httpx.post(
            f"{settings.GEMINI_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.GEMINI_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": model, "max_tokens": 1,
                  "messages": [{"role": "user", "content": "ok"}]},
            timeout=40,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"BAĞLANTI HATASI: {type(exc).__name__}: {str(exc)[:200]}")
        return 1

    if r.status_code == 200:
        print("KOTA AÇIK — model şu an cevap veriyor.")
        print("Sorun kotaysa yalnızca yoğun anlarda görülüyor demektir.")
        return 0

    print(f"HTTP {r.status_code}\n")
    try:
        govde = r.json()
    except ValueError:
        print(r.text[:800])
        return 1

    print(json.dumps(govde, ensure_ascii=False, indent=2)[:2000])

    if r.status_code != 429:
        return 1

    # GÖVDE LİSTE DE OLABİLİR: [{"error": {...}}]
    if isinstance(govde, list):
        govde = next((x for x in govde if isinstance(x, dict)), {})
    hata = (govde.get("error") or {}) if isinstance(govde, dict) else {}
    kimlikler, bekleme = [], ""
    for d in hata.get("details") or []:
        if not isinstance(d, dict):
            continue
        for ih in d.get("violations") or []:
            if isinstance(ih, dict):
                kimlikler.append(str(ih.get("quotaId")
                                     or ih.get("quotaMetric") or "?"))
        if d.get("retryDelay"):
            bekleme = str(d["retryDelay"])

    print("\n" + "=" * 62)
    print("DOLAN KOTA :", ", ".join(kimlikler) or "(gövdede belirtilmemiş)")
    print("BEKLEME    :", bekleme or "(belirtilmemiş)")

    metin = str(hata.get("message") or "")
    sade = (" ".join(kimlikler) + " " + metin).lower() \
        .replace("-", "").replace("_", "")
    if any(iz in sade for iz in ("perday", "daily", "requestsperday")):
        print("\nSONUÇ: GÜNLÜK kota. Beklemek çözmez.")
        print("  • Kota Pasifik saatiyle gece yarısı sıfırlanır.")
        print("  • Hemen devam için: Google AI Studio'da faturalandırmayı açın")
        print("    ya da .env içinde GEMINI_MODEL=gemini-2.5-flash deneyin")
        print("    (farklı modelin günlük kotası ayrıdır).")
    elif "perminute" in sade or bekleme:
        print(f"\nSONUÇ: DAKİKALIK kota. {bekleme or 'Kısa süre'} sonra geçer.")
    elif "token" in sade:
        print("\nSONUÇ: TOKEN kotası. Soruyu kısaltmak ya da yeni konuşma "
              "başlatmak yardımcı olur.")
    else:
        print("\nSONUÇ: Kota kimliği tanınmadı; yukarıdaki ham gövde belirleyici.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
