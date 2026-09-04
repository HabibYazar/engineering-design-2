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

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AcademicProgram, Department, Faculty
from sqlalchemy import select

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
def get_display_names(db: Session = Depends(get_db)) -> DisplayNamesResponse:
    """Türkçeleştirme sözlüğü — KURUMSAL ADLARLA ÇAKIŞMAYACAK BİÇİMDE.

    NE İŞE YARAR
    ------------
    `display_names.json`, ÖRNEK (demo) veri kümesinin İngilizce kodlarını
    (FEA, FEAS, SWE…) okunabilir Türkçe adlara çevirmek için yazılmıştı.
    Proje yalnızca demo veriyle çalışırken zararsızdı.

    NEDEN SÜZÜLÜYOR
    ---------------
    Gerçek veri yüklendikten sonra bu sözlük TEHLİKELİ hâle geldi: demo
    fakülte `FEA`yı "Mühendislik ve Mimarlık Fakültesi" olarak yazıyor ve
    kurumun GERÇEK fakültesiyle (id=4, kod MUHMIM) ekranda AYNI isimle
    yan yana duruyordu. Canlıda gözlenen sonuç:

        Fakülte / Yüksekokul Öğrenci Dağılımı
          Mühendislik ve Mimarlık Fakültesi   2.213   ← demo (id=8, FEA)
          Mühendislik ve Mimarlık Fakültesi     803   ← gerçek (id=4, MUHMIM)

    İki AYRI varlık, tek bir kurumsal etiketin arkasına gizlenmişti.

    KURAL
    -----
    Bir eşleme, kurumun GERÇEK hiyerarşisinde zaten var olan bir adı
    üretiyorsa UYGULANMAZ. Varlıklar birleştirilmez, silinmez, yeniden
    adlandırılmaz — yalnızca takma ad verilmesi engellenir; demo satır
    kendi adıyla (İngilizce) görünür ve böylece kurumsal birim sanılmaz.

    Ayrıca gerçek hiyerarşide zaten bulunan bir KOD için takma ad
    uygulanmaz: kurumun kendi adı her zaman yetkilidir.
    """
    # KARŞILAŞTIRMA TÜRKÇE KURALIYLA YAPILIR.
    # `str.casefold()` Türkçe'de yanılır: "MÜHENDİSLİK".casefold() sonucu
    # birleşik noktalı bir "i" üretir ve "Mühendislik" ile EŞLEŞMEZ. Bu
    # yüzden projenin mevcut birim adı normalleştiricisi kullanılır;
    # o, ekleri (FAKÜLTESİ, BÖLÜMÜ…) de atarak varlık kimliğine bakar.
    from app.services.unit_matching import normalize_unit_name

    sozluk = {k: dict(v) for k, v in _load().items()}

    kurumsal_adlar = set()
    for model in (Faculty, Department, AcademicProgram):
        for (ad,) in db.execute(select(model.name)):
            if ad:
                kurumsal_adlar.add(normalize_unit_name(ad))

    for tablo in sozluk.values():
        for kod in list(tablo):
            if normalize_unit_name(tablo[kod]) in kurumsal_adlar:
                # Takma ad, var olan bir kurumsal birimin adını taklit
                # ediyor. Uygulanmaz: iki ayrı varlık tek etiketin
                # arkasına gizlenmemeli.
                del tablo[kod]
    return DisplayNamesResponse(**sozluk)


@router.get("/data-periods", summary="Panonun geçerli akademik dönemleri")
def data_periods(db: Session = Depends(get_db)) -> dict:
    """Dönem seçicisinin TEK kaynağı.

    Eskiden arayüz `/api/education-analytics/academic-years` ucunu
    kullanıyordu; o uç örnek veri modülünün tablosunu okur ve ileri
    tarihli planlama yıllarını da döndürür. Sonuç, açılışta gerçek
    verisi olmayan bir yılın seçilmesiydi.
    """
    from app.services import data_period_service

    return data_period_service.period_summary(db)


@router.get("/data-source", summary="Pano hangi veri temelinde çalışıyor")
def data_source(db: Session = Depends(get_db)) -> dict:
    """Gerçek veri mi, örnek veri mi — arayüz bunu uyarı şeridinde gösterir."""
    from app.services import data_period_service

    return data_period_service.data_source_state(db)
