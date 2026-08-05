"""Arayüzün ortak kullandığı referans sözlükleri.

Neden var: veritabanındaki fakülte/bölüm/program adları İngilizce ve modül
kodlarıyla birebir eşleşiyor. Bu adları değiştirmek mevcut testleri ve modüller
arası kod eşleşmesini bozardı. Bunun yerine görünen ad sözlüğü ayrı tutuluyor
ve arayüz burayı okuyor. Böylece Türkçe karşılıklar tek bir yerde durur;
her ekran kendi çeviri tablosunu taşımaz.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/reference", tags=["Referans"])

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "display_names.json"


class DisplayNamesResponse(BaseModel):
    """Kod → Türkçe görünen ad eşlemeleri."""

    faculties: Dict[str, str] = Field(description="Fakülte kodu → Türkçe ad")
    departments: Dict[str, str] = Field(description="Bölüm kodu → Türkçe ad")
    programs: Dict[str, str] = Field(description="Program kodu → Türkçe ad")


@lru_cache(maxsize=1)
def _load() -> Dict[str, Dict[str, str]]:
    # Dosya her istekte okunmasın; sözlük süreç ömrü boyunca sabittir.
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return {
        "faculties": raw.get("faculties", {}),
        "departments": raw.get("departments", {}),
        "programs": raw.get("programs", {}),
    }


@router.get(
    "/display-names",
    response_model=DisplayNamesResponse,
    summary="Fakülte, bölüm ve program adlarının Türkçe karşılıkları",
)
def get_display_names() -> DisplayNamesResponse:
    """Karşılığı tanımlı olmayan kod için arayüz veritabanındaki adı kullanır."""
    return DisplayNamesResponse(**_load())
