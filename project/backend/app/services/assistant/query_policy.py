"""Kurumsal soru politikası.

NEDEN VAR
---------
Sistem yönergesi modele "kurumsal sayıları yalnızca araç sonuçlarından al"
diyor. Ama yönerge bir RİCADIR, garanti değil. Canlı testte model
"Bilgisayar Mühendisliği programının mevcut öğrenci sayısı nedir?" sorusuna
hiç araç çağırmadan cevap üretti ve sistem bunu `general_model_knowledge`
etiketiyle kullanıcıya sundu.

Bir karar destek sisteminde bu kabul edilemez. Kural sunucu tarafında
uygulanır: soru kurumsal veri gerektiriyorsa, araç sonucu olmadan üretilen
cevap KULLANICIYA ULAŞMAZ.

NASIL ÇALIŞIR
-------------
1. Soru sınıflandırılır (kurumsal / genel sohbet).
2. Kurumsal ise araçlar sunulur.
3. Model araç çağırmadan metin üretirse o metin ATILIR ve modele kısa bir
   uyarı gönderilip ikinci bir şans verilir.
4. İkinci denemede de araç yoksa kontrollü bir "veriye erişilemedi" cevabı
   döner. `data_source` asla `general_model_knowledge` olmaz.

"Merhaba" gibi genel sohbette bu zorunluluk uygulanmaz.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Kurumsal veri işaretleri. Türkçe çekim ekleri nedeniyle kökler aranır;
# tam sözcük eşleşmesi "öğrencinin", "bütçesi" gibi biçimleri kaçırırdı.
INSTITUTIONAL_PATTERNS: List[str] = [
    # --- Sayılar ve ölçüler ---
    r"kaç\b", r"\bne kadar\b", r"\bsayısı\b", r"\bsayisi\b", r"\badet\b",
    r"\boran[ıi]\b", r"\byüzde\b", r"%\s*\d", r"\btoplam\b", r"\bortalama\b",
    # --- Öğrenci ---
    r"öğrenci", r"ogrenci", r"kontenjan", r"doluluk", r"kayıt", r"kayit",
    r"mezun", r"bırak", r"birak", r"terk", r"dropout", r"başarı", r"basari",
    # --- Personel ---
    r"personel", r"akademisyen", r"öğretim üyesi", r"ogretim uyesi", r"kadro",
    r"maaş", r"maas", r"zam\b", r"bordro",
    # --- Mali ---
    r"gelir", r"gider", r"bütçe", r"butce", r"mali", r"harcama", r"maliyet",
    r"finans", r"burs", r"gelir-gider", r"denge", r"usd", r"dolar",
    # --- Kapasite ---
    r"kapasite", r"derslik", r"laboratuvar", r"laboratuar", r"mekân", r"mekan",
    r"sınıf", r"sinif", r"alan\b",
    # --- Organizasyon ---
    r"fakülte", r"fakulte", r"bölüm", r"bolum", r"program", r"üniversite",
    r"universite", r"mühendisli", r"muhendisli",
    # --- Senaryo ---
    r"senaryo", r"simülasyon", r"simulasyon", r"artarsa", r"azalırsa",
    r"azalirsa", r"artar mı", r"yapılırsa", r"yapilirsa", r"olursa",
    r"ne olur", r"etkile", r"varsayalım", r"varsayalim", r"projeksiyon",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INSTITUTIONAL_PATTERNS]

# Bu ifadelerden biri TEK BAŞINA mesajı oluşturuyorsa genel sohbettir.
# "Merhaba" içinde "ha" geçmesi kurumsal soru yapmaz.
GREETING_ONLY = re.compile(
    r"^\W*(merhaba|selam|günaydın|gunaydin|iyi (günler|gunler|akşamlar|aksamlar)|"
    r"nasılsın|nasilsin|teşekkür|tesekkur|sağ ol|sag ol|görüşürüz|gorusuruz|"
    r"kimsin|sen kimsin|ne yapabilirsin|yardım|yardim)\W*$",
    re.IGNORECASE,
)

# Kullanıcıya ve modele gösterilecek metinler.
RETRY_INSTRUCTION = (
    "Bu soru kurumsal veri gerektiriyor. Uygun aracı çağırmadan cevap verme. "
    "Kurum verisine erişmek için sana tanımlanan araçlardan uygun olanı çağır."
)

NO_TOOL_RESULT_MESSAGE = (
    "Kurumsal veriye güvenilir biçimde erişilemediği için sayısal cevap "
    "oluşturulmadı. Soruyu bir program, bölüm veya akademik yıl belirterek "
    "yeniden sorabilirsiniz."
)

NO_DATABASE_MESSAGE = (
    "Bu soru kurum verisi gerektiriyor ancak veri oturumu oluşturulamadı. "
    "Sayısal bir cevap üretilmedi."
)

# data_source değerleri.
SOURCE_INSTITUTIONAL = "institutional_data"
SOURCE_GENERAL = "general_model_knowledge"
SOURCE_UNAVAILABLE = "institutional_data_unavailable"


def is_institutional_query(message: str) -> bool:
    """Soru kurum verisi gerektiriyor mu?

    Yanlış pozitif tarafına eğimlidir: kararsız kalınan bir soruda araç
    zorunlu kılmak, uydurma sayı üretmekten iyidir. Model gerçekten araca
    ihtiyaç duymuyorsa yine de metin cevabı verebilir — yalnızca ikinci bir
    tur harcanmış olur.
    """
    text = (message or "").strip()
    if not text:
        return False
    if GREETING_ONLY.match(text):
        return False
    return any(pattern.search(text) for pattern in _COMPILED)


# ===========================================================================
# SENARYO NİYETİ — deterministik yönlendirme
# ===========================================================================
#
# NEDEN BACKEND'DE
# ----------------
# Canlı testte model "Akademik personel maaşlarına %2 zam yapılırsa bütçe
# nasıl etkilenir?" sorusuna `get_financial_summary` çağırdı. O araç mevcut
# bütçeyi döndürür; zammın etkisini HESAPLAMAZ. Model doğru soruyu yanlış
# araca yöneltti ve sistem bunu kabul etti.
#
# Araç seçimi bir muhakeme işi değil, bir yönlendirme işidir. "Maaşlara zam
# yapılırsa" ifadesi tek bir aracı gerektirir. Bu karar artık kural tabanlı
# ve deterministiktir; model yalnızca sonucu yorumlar.

INTENT_STAFF_SALARY = "staff_salary_scenario"
INTENT_ENROLLMENT_CHANGE = "enrollment_change_scenario"
INTENT_CURRENT_STATE = "current_state_query"
INTENT_GENERAL = "general_chat"

# Bir varsayım/senaryo sorulduğunu gösteren ifadeler.
SCENARIO_TRIGGERS = re.compile(
    r"artarsa|artırılırsa|artirilirsa|arttırılırsa|arttirilirsa|"
    r"azalırsa|azalirsa|azaltılırsa|azaltilirsa|düşerse|duserse|"
    r"yapılırsa|yapilirsa|değişirse|degisirse|olursa|"
    r"ne olur|nasıl etkilen|nasil etkilen|etkisi ne|"
    r"senaryo|simülasyon|simulasyon|varsayalım|varsayalim|"
    r"yükselirse|yukselirse|artır(?:ıl)?|artir(?:il)?|azalt(?:ıl)?|azalt(?:il)?",
    re.IGNORECASE,
)

# Maaş senaryosunun konusu.
SALARY_SUBJECT = re.compile(
    r"maaş|maas|ücret|ucret|zam\b|bordro|özlük|ozluk|"
    r"personel gider|personel maliyet|maaş gider|maas gider",
    re.IGNORECASE,
)

# Öğrenci sayısı senaryosunun konusu.
ENROLLMENT_SUBJECT = re.compile(
    r"öğrenci|ogrenci|kayıt say|kayit say|kontenjan|"
    r"öğrenci say|ogrenci say|mevcut say|enrollment",
    re.IGNORECASE,
)

# Yüzde değeri: "%2", "yüzde 2", "2 oranında", "%15'lik".
PERCENT_PATTERNS = [
    re.compile(r"%\s*(-?\d+(?:[.,]\d+)?)"),
    re.compile(r"y[üu]zde\s+(-?\d+(?:[.,]\d+)?)", re.IGNORECASE),
    re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(?:%|yüzde|yuzde)", re.IGNORECASE),
    re.compile(r"(-?\d+(?:[.,]\d+)?)\s*oran[ıi]nda", re.IGNORECASE),
]

# Yazıyla yazılmış yüzdeler. Kullanıcı "yüzde iki" yazabiliyor.
WRITTEN_NUMBERS: Dict[str, int] = {
    "bir": 1, "iki": 2, "üç": 3, "uc": 3, "dört": 4, "dort": 4, "beş": 5,
    "bes": 5, "altı": 6, "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
    "on": 10, "onbeş": 15, "onbes": 15, "yirmi": 20, "yirmibeş": 25,
    "yirmibes": 25, "otuz": 30, "kırk": 40, "kirk": 40, "elli": 50,
}
WRITTEN_PERCENT = re.compile(
    r"y[üu]zde\s+(on\s*beş|on\s*bes|yirmi\s*beş|yirmi\s*bes|"
    + "|".join(sorted(WRITTEN_NUMBERS, key=len, reverse=True))
    + r")",
    re.IGNORECASE,
)

# Azalma yönü: "azalırsa" negatif yüzde demektir.
DECREASE_HINT = re.compile(
    r"azal|düş|dus|azalt|kesinti|indirim|eksil", re.IGNORECASE
)

# Bir programın kendi göstergelerini soran ifadeler.
#
# "doluluk" BİLİNÇLİ OLARAK YOK: mekân doluluğu da aynı sözcüğü kullanıyor ve
# "Mekânların doluluk oranı ne kadar?" sorusu program özeti aracına
# yönlendiriliyordu. Bu liste yalnızca ÖĞRENCİ göstergelerini kapsar; ayrıca
# zorunluluk, cümlede gerçekten bir program adı geçmesine bağlıdır
# (bkz. chat_service).
PROGRAM_METRIC_SUBJECT = re.compile(
    r"öğrenci say|ogrenci say|kaç öğrenci|kac ogrenci|öğrencisi var|ogrencisi var|"
    r"kontenjan|mezuniyet oran|bırakma oran|birakma oran|dropout|"
    r"program doluluğu|program dolulugu",
    re.IGNORECASE,
)

ACADEMIC_YEAR_IN_TEXT = re.compile(r"\b(20\d{2})\s*[-–/]\s*(20\d{2})\b")


@dataclass
class QueryIntent:
    """Bir kullanıcı mesajının deterministik sınıflandırması.

    `required_tool` doluysa o araç MUTLAKA çalıştırılır; model başka bir araç
    seçse bile sonuç kabul edilmez.
    """

    institutional: bool
    intent: str
    required_tool: Optional[str] = None
    #: Backend'in mesajdan çıkardığı araç parametreleri.
    parameters: Dict[str, object] = field(default_factory=dict)
    #: Kullanıcı açıkça planlama dönemini istedi mi?
    wants_planning_period: bool = False
    #: Mesajda açıkça yazılmış akademik yıl.
    explicit_academic_year: Optional[str] = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "institutional": self.institutional,
            "intent": self.intent,
            "required_tool": self.required_tool,
        }


def extract_percentage(message: str) -> Optional[float]:
    """Mesajdaki yüzde değerini çıkarır. Bulamazsa None.

    Yön de belirlenir: "azalırsa" negatif işaret verir. Model bu çıkarımı
    yapmaz; sayı doğrudan metinden alınır ve Pydantic ile doğrulanır.
    """
    text = message or ""
    value: Optional[float] = None

    for pattern in PERCENT_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                value = float(match.group(1).replace(",", "."))
            except ValueError:
                continue
            break

    if value is None:
        written = WRITTEN_PERCENT.search(text)
        if written:
            word = re.sub(r"\s+", "", written.group(1)).lower()
            value = WRITTEN_NUMBERS.get(word)
            if value is None:
                # "onbeş" gibi birleşik yazımlar sözlükte var; yoksa vazgeç.
                return None
            value = float(value)

    if value is None:
        return None

    # Yön: kullanıcı "azalırsa" dediyse ve sayı pozitif yazıldıysa negatiftir.
    if value > 0 and DECREASE_HINT.search(text):
        value = -value
    return value


def extract_academic_year(message: str) -> Optional[str]:
    """Mesajda açıkça yazılmış akademik yılı çıkarır."""
    match = ACADEMIC_YEAR_IN_TEXT.search(message or "")
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def classify(message: str) -> QueryIntent:
    """Mesajı deterministik olarak sınıflandırır.

    Sıralama önemlidir: senaryo niyeti mevcut durum sorusundan ÖNCE
    denetlenir. "Maaşlara %2 zam yapılırsa bütçe nasıl etkilenir?" hem
    "bütçe" (mevcut durum) hem "zam yapılırsa" (senaryo) içerir; senaryo
    baskındır.
    """
    text = (message or "").strip()
    if not text:
        return QueryIntent(institutional=False, intent=INTENT_GENERAL)

    institutional = is_institutional_query(text)
    explicit_year = extract_academic_year(text)
    wants_planning = bool(explicit_year) or _mentions_planning(text)

    if not institutional:
        return QueryIntent(
            institutional=False,
            intent=INTENT_GENERAL,
            wants_planning_period=wants_planning,
            explicit_academic_year=explicit_year,
        )

    is_scenario = bool(SCENARIO_TRIGGERS.search(text))
    percentage = extract_percentage(text)

    if is_scenario and SALARY_SUBJECT.search(text):
        parameters: Dict[str, object] = {}
        if percentage is not None:
            parameters["salary_change_percentage"] = percentage
        return QueryIntent(
            institutional=True,
            intent=INTENT_STAFF_SALARY,
            required_tool="run_staff_salary_scenario",
            parameters=parameters,
            wants_planning_period=wants_planning,
            explicit_academic_year=explicit_year,
        )

    if is_scenario and ENROLLMENT_SUBJECT.search(text):
        parameters = {}
        if percentage is not None:
            parameters["student_change_percentage"] = percentage
        return QueryIntent(
            institutional=True,
            intent=INTENT_ENROLLMENT_CHANGE,
            required_tool="run_enrollment_change_scenario",
            parameters=parameters,
            wants_planning_period=wants_planning,
            explicit_academic_year=explicit_year,
        )

    # Kurumsal ama senaryo değil: mevcut durum sorgusu.
    #
    # Soru belirli bir PROGRAMIN öğrenci göstergelerini soruyorsa araç yine
    # bellidir. Serbest bırakıldığında model bu soruya mali özet aracını
    # çağırıp "toplam gelir 50,4 milyon USD" diye cevap verebiliyordu:
    # başarılı ama alakasız bir araç çağrısı kapıyı geçiyordu.
    requires_program_summary = bool(PROGRAM_METRIC_SUBJECT.search(text))
    return QueryIntent(
        institutional=True,
        intent=INTENT_CURRENT_STATE,
        required_tool="get_program_summary" if requires_program_summary else None,
        wants_planning_period=wants_planning,
        explicit_academic_year=explicit_year,
    )


def _mentions_planning(message: str) -> bool:
    """Planlama dönemi ipucu. entity_resolver ile aynı kalıbı kullanır."""
    from app.services.assistant import entity_resolver

    return entity_resolver.mentions_planning_period(message)


REQUIRED_TOOL_INSTRUCTION = (
    "Bu soru bir senaryo hesabı gerektiriyor. Mevcut durumu döndüren araçlar "
    "yeterli değildir; '{tool}' aracını çağırmalısın."
)
