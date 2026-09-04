"""HİYERARŞİ SAĞLAYICI DENETİMİ — kurumsal birim mi, örnek veri artığı mı?

NEDEN VAR
---------
Canlı panoda üniversite düzeyinde şu görünüyordu:

    Fakülte / Yüksekokul Öğrenci Dağılımı        merkez toplam 7.348
      Mühendislik ve Mimarlık Fakültesi   2.213
      Mühendislik ve Mimarlık Fakültesi     803
    Üniversite "Toplam Öğrenci"                                3.626

Aynı fakülte iki kez, toplam kurumun iki katı. Sebep BİRLEŞTİRME ya da
çift sayma değildi: veritabanında GERÇEKTEN iki ayrı varlık vardı.

    id=4  kod=MUHMIM  MÜHENDİSLİK VE MİMARLIK FAKÜLTESİ
          created_at 18:50:46 · established_on 2020-04-17 · yok_status AKTİF
          description "Kaynak: YÖK Akademik toplayıcısı"        → KURUMSAL

    id=8  kod=FEA     Faculty of Engineering and Architecture
          created_at 18:51:53 · established_on NULL · yok_status NULL
          description "Mühendislik ve mimarlık alanındaki..."   → ÖRNEK VERİ

Gerçek aktarım 18:50'de, örnek veri seed'i 18:51'de çalışmış; ikisi de
veritabanında kalmış (`--purge` verilmemiş). Ekranda AYNI isimle
görünmelerinin ayrı bir sebebi vardı: `display_names.json`, demo kodu
`FEA`yı "Mühendislik ve Mimarlık Fakültesi" olarak çeviriyordu. O sızıntı
`routers/reference.py` içinde kapatıldı; bu modül ise varlıkların
KENDİSİNİ ayırt eder.

AYIRT ETME KURALI — AD BENZERLİĞİ DEĞİL, SAĞLAYICI
--------------------------------------------------
Birimler ADLARINA BAKILARAK eşleştirilmez ve birleştirilmez. Ölçüt,
kaydın nereden geldiğidir: kurumsal aktarıcılar her satıra
`description = "Kaynak: <kaynak>"` damgası basar. Bu damgayı taşımayan
bir hiyerarşi satırı, kurumun resmî kaynaklarından gelmemiştir.

Bu modül hiçbir şey SİLMEZ; yalnızca kanıtı raporlar. Temizlik,
`purge_demo_hierarchy.py` ile bilinçli olarak yapılır.
"""

from __future__ import annotations

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicProgram, Department, Faculty

#: Kurumsal aktarıcıların bastığı damga. Bu ön ekle başlayan her açıklama
#: gerçek bir kaynak dosyasına işaret eder (YÖK Akademik toplayıcısı,
#: ankara_bilim_* veri kümeleri…).
KURUMSAL_DAMGA = "Kaynak:"

_TABLOLAR = (("faculties", Faculty), ("departments", Department),
             ("programs", AcademicProgram))


def _kurumsal_mi(aciklama) -> bool:
    return bool(aciklama) and str(aciklama).strip().startswith(KURUMSAL_DAMGA)


def unmarked_units(db: Session) -> Dict[str, List[dict]]:
    """Kurumsal sağlayıcıya bağlanamayan hiyerarşi satırları.

    EBEVEYN SAĞLAYICISI DA KANITTIR
    -------------------------------
    Yalnızca damgaya bakmak YANLIŞ POZİTİF üretti: gerçek aktarıcı,
    toplayıcıda bölüm bilgisi olmayan idari birim için

        departments(id=5, code=REKTORLUK,
                    description="İdari birim — toplayıcıda bölüm bilgisi yok")

    satırını yazıyor; damga yok ama satır GERÇEKTİR. Ebeveyni
    (faculties id=3 REKTÖRLÜK) kurumsal damgayı taşır.

    Bu yüzden kural zincirlidir:
      · Fakülte  → damgası varsa kurumsaldır.
      · Bölüm    → damgası VARSA ya da FAKÜLTESİ kurumsalsa kurumsaldır.
      · Program  → damgası VARSA ya da BÖLÜMÜ kurumsalsa kurumsaldır.

    Gerçek veride demo bölümlerin hepsi demo fakültelerin altındadır
    (SWE/CENG/… → FEA), dolayısıyla zincir onları doğru biçimde dışarıda
    bırakır. Ad benzerliği HİÇBİR aşamada ölçüt değildir.
    """
    fakulteler = list(db.execute(select(Faculty)).scalars())
    bolumler = list(db.execute(select(Department)).scalars())
    programlar = list(db.execute(select(AcademicProgram)).scalars())

    fak_kurumsal = {f.id: _kurumsal_mi(f.description) for f in fakulteler}
    bol_kurumsal = {
        b.id: _kurumsal_mi(b.description) or fak_kurumsal.get(b.faculty_id, False)
        for b in bolumler
    }
    prog_kurumsal = {
        p.id: _kurumsal_mi(p.description) or bol_kurumsal.get(p.department_id, False)
        for p in programlar
    }

    def _satir(k, gerekce):
        return {
            "id": k.id, "code": k.code, "name": k.name,
            "reason": gerekce,
            "created_at": (k.created_at.isoformat()
                           if getattr(k, "created_at", None) else None),
        }

    return {
        "faculties": [_satir(f, "kurumsal kaynak damgası yok")
                      for f in fakulteler if not fak_kurumsal[f.id]],
        "departments": [_satir(b, "damgası yok ve fakültesi de kurumsal değil")
                        for b in bolumler if not bol_kurumsal[b.id]],
        "programs": [_satir(p, "damgası yok ve bölümü de kurumsal değil")
                     for p in programlar if not prog_kurumsal[p.id]],
    }


def provenance_report(db: Session) -> dict:
    """Kurumsal / kaynaksız birim sayımı ve kanıt listesi."""
    kaynaksiz = unmarked_units(db)
    toplam = {}
    for anahtar, model in _TABLOLAR:
        toplam[anahtar] = len(db.execute(select(model.id)).scalars().all())

    kaynaksiz_sayi = {k: len(v) for k, v in kaynaksiz.items()}
    temiz = sum(kaynaksiz_sayi.values()) == 0
    return {
        "clean": temiz,
        "total_units": toplam,
        "unmarked_counts": kaynaksiz_sayi,
        "unmarked_units": kaynaksiz,
        "rule": (
            "Kurumsal aktarıcılar her hiyerarşi satırına "
            f'`description = "{KURUMSAL_DAMGA} <kaynak>"` damgası basar. '
            "Damgası olmayan satır resmî kaynaktan gelmemiştir. Ayırt etme "
            "AD BENZERLİĞİYLE değil, SAĞLAYICIYLA yapılır."
        ),
        "remedy": "python purge_demo_hierarchy.py --apply",
    }
