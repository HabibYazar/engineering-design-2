"""Gemini 400 hatasının HANGİ PARAMETREDEN geldiğini eleyerek bulur.

NEDEN
-----
Gemini "400 Bad Request" döndürüyor ama `error.message` alanı boş
geliyor; ekranda da günlükte de sebep görünmüyor. Teşhis edilemeyen
hata düzeltilemez, tahminle yama atmak da vakit kaybıdır.

Bu betik isteği en sade hâlinden başlatıp parametreleri TEK TEK ekler.
Hangi adımda kırıldığı, sebebi doğrudan söyler:

    1. yalnızca model + messages
    2. + max_tokens
    3. + temperature
    4. + tools (tek araç)
    5. + tool_choice
    6. + araç sonucu içeren çok turlu mesaj dizisi

Ayrıca her hatanın HAM gövdesini basar — `error.message` boş olsa bile
gövdenin başka bir alanında sebep yazıyor olabilir.

KULLANIM
--------
    python gemini_teshis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import settings  # noqa: E402

ARAC = {
    "type": "function",
    "function": {
        "name": "get_program_summary",
        "description": "Bir programın öğrenci sayısını döndürür.",
        "parameters": {
            "type": "object",
            "properties": {
                "program_name": {"type": "string", "description": "Program adı"}
            },
            "required": ["program_name"],
        },
    },
}

MESAJ = [{"role": "user", "content": "merhaba"}]

ARACLI_DIZI = [
    {"role": "user", "content": "Psikoloji kaç öğrenci?"},
    {"role": "assistant", "content": "",
     "tool_calls": [{"id": "call_1", "type": "function",
                     "function": {"name": "get_program_summary",
                                  "arguments": '{"program_name":"Psikoloji"}'}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": '{"students":108}'},
]


def dene(ad: str, govde: dict) -> bool:
    url = f"{settings.GEMINI_BASE_URL.rstrip('/')}/chat/completions"
    basliklar = {
        "Authorization": f"Bearer {settings.GEMINI_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = httpx.post(url, headers=basliklar, json=govde, timeout=60)
    except Exception as exc:  # noqa: BLE001
        print(f"  {ad:<44} BAĞLANTI HATASI: {type(exc).__name__}")
        return False

    if r.status_code == 200:
        try:
            icerik = ((r.json().get("choices") or [{}])[0]
                      .get("message") or {})
            metin = (icerik.get("content") or "")[:60]
            cagri = icerik.get("tool_calls")
            ek = f" [araç çağrısı: {len(cagri)}]" if cagri else ""
            print(f"  {ad:<44} ÇALIŞTI ✓  {metin!r}{ek}")
        except Exception:  # noqa: BLE001
            print(f"  {ad:<44} ÇALIŞTI ✓")
        return True

    print(f"  {ad:<44} HTTP {r.status_code}")
    print(f"      ham gövde: {r.text[:600]}")
    return False


def main() -> int:
    if not settings.GEMINI_API_KEY:
        print("GEMINI_API_KEY tanımlı değil.")
        return 2

    model = settings.GEMINI_MODEL
    print(f"Model : {model}")
    print(f"Uç    : {settings.GEMINI_BASE_URL}\n")

    adimlar = [
        ("1. yalnızca model + messages",
         {"model": model, "messages": MESAJ}),
        ("2. + max_tokens",
         {"model": model, "messages": MESAJ, "max_tokens": 100}),
        ("3. + max_completion_tokens (yeni ad)",
         {"model": model, "messages": MESAJ, "max_completion_tokens": 100}),
        ("4. + temperature=0",
         {"model": model, "messages": MESAJ, "temperature": 0.0}),
        ("5. + temperature=1",
         {"model": model, "messages": MESAJ, "temperature": 1.0}),
        ("6. + tools",
         {"model": model, "messages": MESAJ, "tools": [ARAC]}),
        ("7. + tools + tool_choice=auto",
         {"model": model, "messages": MESAJ, "tools": [ARAC],
          "tool_choice": "auto"}),
        ("8. çok turlu (araç sonucu dahil)",
         {"model": model, "messages": ARACLI_DIZI, "tools": [ARAC]}),
        ("9. TAM istek (bizim gönderdiğimiz)",
         {"model": model, "messages": MESAJ, "stream": False,
          "temperature": settings.GEMINI_TEMPERATURE,
          "max_tokens": settings.GEMINI_MAX_TOKENS,
          "tools": [ARAC], "tool_choice": "auto"}),
    ]

    print("PARAMETRE ELEME")
    sonuc = {}
    for ad, govde in adimlar:
        sonuc[ad] = dene(ad, govde)

    print("\n" + "=" * 60)
    calisan = [a for a, ok in sonuc.items() if ok]
    kirik = [a for a, ok in sonuc.items() if not ok]
    if not calisan:
        print("HİÇBİRİ ÇALIŞMADI — sorun model adı ya da anahtar.")
        print("Yukarıdaki ham gövdeler sebebi söylüyor.")
        return 1
    print(f"ÇALIŞAN  ({len(calisan)}):")
    for a in calisan:
        print(f"   {a}")
    if kirik:
        print(f"\nKIRILAN ({len(kirik)}):")
        for a in kirik:
            print(f"   {a}")
        print("\nİlk kırılan adım, sorunlu parametreyi gösterir.")
    else:
        print("\nHepsi çalıştı — sorun bu katmanda değil, mesaj içeriğinde.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
