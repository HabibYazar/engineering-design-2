"""Soruyu konuya eşler ve ilgili kurumsal bağlamı derler.

DİKKAT — Bu bir yapay zekâ değildir. Burada yapılan iş anahtar kelime
eşleştirmesidir ve öyle sunulur. Sistem soruyu "anlamaz", yalnızca hangi
verilerin toplanacağına karar verir. Cevap üretimi bu katmanın işi değildir;
bir dil modeli bağlandığında burada derlenen bağlam modele girdi olacaktır.
"""

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.assistant.data_access import TOPIC_COLLECTORS
from app.services.assistant.schemas import (
    ContextItem,
    ContextResponse,
    SampleQuestion,
)
from app.services.scope import Scope

# Konu -> tetikleyici anahtar kelimeler. Sözlük tabanlı olması bilinçli:
# kuralın ne olduğu okunabilir ve tahmin edilebilir olsun diye.
TOPIC_KEYWORDS = {
    "öğrenci talebi": [
        "öğrenci", "doluluk", "kontenjan", "talep", "kayıt", "yerleşen",
        "taban puan", "tercih", "mezun", "bırakma",
    ],
    "mali durum": [
        "gelir", "gider", "bütçe", "maliyet", "mali", "finans", "burs",
        "ücret", "harcama", "denge", "açık",
    ],
    "akademik performans": [
        "yayın", "atıf", "araştırma", "akademik personel", "öğretim üyesi",
        "proje", "patent", "ar-ge",
    ],
    "fiziksel kapasite": [
        "derslik", "laboratuvar", "kapasite", "mekân", "mekan", "bina",
        "ofis", "doluluk oranı", "alan", "metrekare",
    ],
    "risk ve uyarı": [
        "risk", "uyarı", "tehlike", "kritik", "sorun", "düşüş", "azalma",
        "erken uyarı",
    ],
    "performans göstergeleri": [
        "kpi", "gösterge", "hedef", "performans", "karne", "başarı oranı",
        "stratejik",
    ],
}

NOTICE = (
    "Bu bir dil modeli cevabı DEĞİLDİR. Sisteme bağlı bir LLM bulunmadığı için "
    "sistem cevap üretmez; aşağıda yalnızca sorunuza cevap verilebilmesi için "
    "gerekli olan kurumsal veriler listelenmiştir. Bu veriler gerçek "
    "veritabanından okunmuştur."
)


def match_topic(question: str) -> Tuple[str, int]:
    """Soruyu bir konuya eşler ve kaç anahtar kelimenin tuttuğunu döndürür."""
    text = question.lower()
    best_topic = "genel"
    best_score = 0
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_topic, best_score = topic, score
    return best_topic, best_score


def build_context(db: Session, question: str,
                  scope: Optional[Scope] = None,
                  academic_year: Optional[str] = None) -> ContextResponse:
    """Soru için kurumsal bağlamı derler."""
    from app.services.data_period_service import latest_operating_period

    topic, score = match_topic(question)
    collectors = TOPIC_COLLECTORS.get(topic, TOPIC_COLLECTORS["genel"])
    scope = scope or Scope()
    year = academic_year or latest_operating_period(db)

    items: List[ContextItem] = []
    for collector in collectors:
        # Bir modül veri döndüremezse tüm bağlam boşa çıkmasın; her toplayıcı
        # kendi hatasını "veri yok" satırı olarak zaten bildiriyor.
        items.extend(collector(db, scope, year))

    return ContextResponse(
        question=question,
        # Hiçbir anahtar kelime tutmadıysa eşleşme olduğunu iddia etmiyoruz.
        matched_topic=topic if score > 0 else None,
        context_items=items,
        academic_year=year,
        scope={"level": scope.level, "label": scope.label},
        notice=NOTICE,
    )


def sample_questions() -> List[SampleQuestion]:
    """Arayüzde gösterilecek örnek sorular.

    Bunlar "sistemin cevaplayabildiği sorular" değil, "sistemin doğru veriyi
    toplayabildiği sorulardır". Fark önemli ve arayüzde de böyle anlatılıyor.
    """
    return [
        SampleQuestion(
            question="Hangi programların doluluk oranı düşüyor?",
            topic="öğrenci talebi",
            covered_modules=[
                "Modül 2 — Öğrenci Analitiği",
                "Modül 7 — Program Sürdürülebilirliği",
            ],
        ),
        SampleQuestion(
            question="Öğrenim ücreti %10 artarsa gelir ve burs yükü nasıl etkilenir?",
            topic="mali durum",
            covered_modules=[
                "Modül 6 — Finansal Analiz",
                "Modül 8 — Performans Yönetimi",
            ],
        ),
        SampleQuestion(
            question="Araştırma performansı en zayıf olan alanlar hangileri?",
            topic="akademik performans",
            covered_modules=[
                "Modül 4 — Akademik Personel",
                "Modül 10 — THE/QS/YÖK Değerlendirme",
            ],
        ),
        SampleQuestion(
            question="Derslik ve laboratuvar kapasitesi yeterli mi?",
            topic="fiziksel kapasite",
            covered_modules=[
                "Modül 5 — Fiziksel Kaynaklar",
                "Modül 2 — Öğrenci Analitiği",
            ],
        ),
        SampleQuestion(
            question="Şu anda hangi kritik riskler var?",
            topic="risk ve uyarı",
            covered_modules=[
                "Modül 11 — Erken Uyarı",
                "Modül 7 — Program Sürdürülebilirliği",
            ],
        ),
        SampleQuestion(
            question="Stratejik hedeflere ulaşma durumumuz nedir?",
            topic="performans göstergeleri",
            covered_modules=[
                "Modül 8 — Performans Yönetimi",
                "Modül 10 — THE/QS/YÖK Değerlendirme",
            ],
        ),
    ]
