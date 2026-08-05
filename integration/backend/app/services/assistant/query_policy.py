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
from typing import List

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
