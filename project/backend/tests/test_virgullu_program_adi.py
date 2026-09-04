"""Virgül, program adının parçasıdır — ayırıcı değil.

BURADA KORUNAN ŞEY
------------------
`is_aggregate_label` içinde "adında virgül varsa bu bir program
listesidir" kuralı vardı. Türkçede virgül sıralama bağlacıdır ve YÖK
program adlarının kendi yazımında geçer. Kural yüzünden şu programlar
hiçbir zaman kanonik anahtar alamadı ve veritabanına HİÇ giremedi
(ölçüldü: virgül içeren satır sayısı 0); 781 kayıt incelemeye düştü.

Testler iki yönü birden tutar: virgüllü gerçek programlar artık
anahtar alıyor VE gerçek toplu satırlar hâlâ ayıklanıyor.
"""

from __future__ import annotations

import pytest

from app.services.program_equivalence import (
    canonical_program_key,
    is_aggregate_label,
)


@pytest.mark.parametrize("ad", [
    "Radyo, Televizyon ve Sinema",
    "Radyo, Televizyon ve Sinema (Burslu)",
    "Elektrik Enerjisi Üretim, İletim ve Dağıtımı",
    "İngilizce, Fransızca Mütercim ve Tercümanlık",
    "Dezenfeksiyon, Sterilizasyon ve Antisepsi Teknikerliği",
])
def test_virgullu_gercek_program_anahtar_alir(ad):
    """Hepsi tek YÖK programıdır ve tek program kodu taşır."""
    assert not is_aggregate_label(ad), f"{ad!r} toplu sayıldı"
    assert canonical_program_key(ad), f"{ad!r} anahtar üretmedi"


@pytest.mark.parametrize("ad", [
    "Mühendislik Programları",
    "İktisadi ve İdari Bilimler Programları",
    "Tüm Programlar",
    "Diğer Programlar",
    "Mühendislik Fakültesi",
])
def test_gercek_toplu_satirlar_hala_ayiklanir(ad):
    """Toplu tespiti noktalamaya değil AÇIK toplu sözcüklere dayanır."""
    assert is_aggregate_label(ad), f"{ad!r} artık toplu sayılmıyor"
    assert canonical_program_key(ad) is None


def test_farkli_programlar_birlesmez():
    """Noktalama temizliği anlamsal kimliği bozmamalı."""
    ciftler = [
        ("Yazılım Mühendisliği", "Bilgisayar Mühendisliği"),
        ("Psikoloji", "Rehberlik ve Psikolojik Danışmanlık"),
        ("İşletme", "Uluslararası Ticaret ve İşletmecilik"),
        # Virgüllü ad, virgülsüz benzeriyle de karışmamalı.
        ("Radyo, Televizyon ve Sinema", "Sinema ve Televizyon"),
    ]
    for a, b in ciftler:
        assert canonical_program_key(a) != canonical_program_key(b), \
            f"{a!r} ile {b!r} aynı anahtara düştü"


def test_virgulsuz_adlarin_anahtari_degismedi():
    """Düzeltme YALNIZCA virgüllü adları etkilemeli.

    Virgülsüz bir adın anahtarı kaysaydı mevcut veritabanı kayıtlarıyla
    eşleşme kopar ve birleştirme duplicate üretirdi.
    """
    beklenen = {
        "Bilgisayar Mühendisliği": "COMPUTER_ENG",
        "Yazılım Mühendisliği": "SOFTWARE_ENG",
        "Psikoloji": "PSYCHOLOGY",
        "Hukuk Fakültesi": None,          # toplu; öyle kalmalı
    }
    for ad, anahtar in beklenen.items():
        assert canonical_program_key(ad) == anahtar
