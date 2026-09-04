"""Soruya göre araç seçimi — token bütçesi için.

NEDEN GEREKTİ
-------------
19 aracın şeması 5.078 token tutuyor. Sistem yönergesiyle birlikte sabit
yük 7.404 token; Gemini'nin dakikalık token bütçesi. Yani
kullanıcı daha soruyu yazmadan bütçenin %93'ü doluyordu ve her istek
HTTP 413 ile geri dönüyordu.

Ölçüm: `get_program_summary` gibi tek bir aracın şeması ~330 token.
İlgisiz 13 aracı göndermemek ~4.000 token kazandırıyor.

TASARIM İLKESİ: ELEMEK RİSKLİ, O YÜZDEN GENİŞ TUTULUR
------------------------------------------------------
Yanlış aracı elemek, asistanın o soruya hiç cevap verememesi demektir —
üstelik sebebi görünmez, model sadece "veriye ulaşamadım" der. Bu, token
tasarrufundan çok daha pahalı bir hata.

Bu yüzden seçim üç katmanlıdır ve her katman AÇMA yönünde çalışır:

  1. Anahtar kelime eşleşen araçlar seçilir.
  2. Hiçbiri eşleşmezse ÇEKİRDEK araçlar gönderilir (boş liste asla).
  3. Seçilen sayı `EN_AZ`ın altındaysa çekirdekle tamamlanır.

Ayrıca `EN_FAZLA` sınırına ulaşılmazsa eleme yapılmaz: az araç varsa
zaten sorun yoktur.

BAKIM NOTU
----------
Yeni bir araç eklendiğinde buraya anahtar kelimesi de eklenmelidir.
Eklenmezse araç yalnızca çekirdek listeye girerse görünür — sessizce
kaybolmaz ama seçilme şansı azalır. `test_arac_secimi.py` her aracın
en az bir anahtar kelimesi olduğunu doğrular.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

#: Türkçe büyük/küçük harf sorunları için katlama tablosu.
_KATLA = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def _sadelestir(metin: str) -> str:
    return (metin or "").translate(_KATLA).lower()


#: HER SORUDA GÖNDERİLEN ÇEKİRDEK ARAÇLAR.
#: Bunlar en sık sorulan konulardır; eşleşme bulunamadığında da
#: gönderilirler ki asistan tamamen sağır kalmasın.
#: HER SORUDA LİSTEDE KALAN ARAÇ.
#:
#: `render_chart` veri getirmez; MODELİN ÇEKTİĞİ veriyi çizer. Anahtar
#: kelimeyle seçilseydi ("grafik", "göster", "çiz") elemeye takıldığı her
#: soruda grafik sessizce imkânsız hale gelirdi — kaldırdığımız regex
#: kalıbının aynısını, bu sefer araç seçiminde kurmuş olurduk.
#: Bedeli tek bir şema (~150 token); gerekmediğinde model çağırmaz.
HER_ZAMAN: tuple = ("render_chart", "query_canonical_data")

#: `query_canonical_data` NEDEN HER SORUDA SUNULUR
#: -----------------------------------------------
#: Bu araç artık MERKEZİ VERİ TABANININ (`abu_kds.db`, 62 tablo, 36.020
#: satır) tek kapısıdır. Önceden `SON_CARE` listesindeydi ve yalnızca
#: hiçbir özel araç eşleşmediğinde sunuluyordu.
#:
#: ÖLÇÜLEN ARIZA: "Ankara'daki son 5 yıldaki en düşük mühendislik taban
#: puanı olan üniversiteler nelerdir?" sorusunda `get_program_metrics`
#: ve `compare_with_peer_universities` anahtar kelimeyle eşleşiyor,
#: dolayısıyla `query_canonical_data` HİÇ SUNULMUYORDU. Veri
#: veritabanında hazır dururken model ona erişebileceği aracı
#: göremiyor, "backend bağlamı olmadan cevaplandı" uyarısı çıkıyor ve
#: kullanıcı kontrollü fallback okuyordu.
#:
#: Sorun guard değildi; guard doğru çalışıyordu. Sorun, gerçek verinin
#: modele ulaştırılamamasıydı — tam olarak bu satırda.
#:
#: Bedeli tek bir şema (~300 token). Karşılığı, her kurumsal soruda
#: 36 bin satırlık merkezi kaynağa erişim. `explore_data_sources`
#: SON_CARE'de KALIR: o pahalı bir keşif turudur ve her soruda
#: sunulması daha önce ölçülen kota tükenmesinin sebebiydi.

#: SERBEST ARAŞTIRMA ARAÇLARI — SON ÇARE, VARSAYILAN DEĞİL.
#:
#: Bu ikisi bir önceki turda `HER_ZAMAN` listesindeydi ve HER soruda
#: modele sunuluyordu. Sonuç ölçüldü: model "merhaba" gibi sorularda
#: bile keşif → sorgu → yeniden düşün zincirine giriyor, tek kullanıcı
#: sorusu günlük API kotasını (20 istek) bitiriyordu.
#:
#: Artık yalnızca soru ÖZEL BİR ARAÇLA KARŞILANAMIYORSA sunulurlar.
#: Özgürlük kaldırılmadı, sıraya kondu: önce hızlı özel araç, sonra
#: hedefli sorgu, en son "elimde ne var" keşfi.
SON_CARE: tuple = ("explore_data_sources",)

#: Özel araç eşleşmesi bu sayının altındaysa soru muhtemelen
#: kataloğun dışında; serbest araştırma araçları o zaman devreye girer.
SON_CARE_ESIGI = 2

#: Serbest araştırma için gereken en az kelime sayısı.
#: "Merhaba", "teşekkürler" gibi mesajlarda hiçbir veri aracına gerek
#: yoktur; ilk sürümde bunlar da "eşleşme yok" sayılıp en pahalı
#: araçları tetikliyordu — düzeltmek istediğimiz davranışın tam
#: kendisi.
SON_CARE_EN_AZ_KELIME = 4

#: Yeni canonical veri araçlarının anahtar kelimeleri.
#: Sadeleştirilmiş biçimde yazılır (Türkçe harfler katlanır).
_YENI_ANAHTARLAR = {
    "get_program_metrics": (
        "kontenjan", "yerlesen", "doluluk", "taban puan", "basari sira",
        "sirala", "ucret", "fiyat", "burs", "tercih", "cinsiyet", "kiz",
        "erkek", "mezun", "liseli", "program metrik", "yks", "yok atlas",
        "2021", "2022", "2023", "2024", "2025", "2026"),
    "get_institution_metrics": (
        "kadro", "ogretim eleman", "ogretim uye", "profesor", "docent",
        "arastirma gorevli", "akademisyen say", "personel say",
        "ogrenci basina", "kurum metrik", "beyan", "celisk", "farkli kaynak",
        "kurulus"),
    "get_equivalent_programs": (
        "ayni bolum", "benzer bolum", "esdeger", "hangi universitede",
        "karsilastirilabilir", "muadil", "benzer program"),
    "list_available_metrics": (
        "hangi metrik", "hangi veri", "neler var", "metrik listesi",
        "veri katalog"),
}

CEKIRDEK: tuple = (
    "get_program_summary",
    "get_organization_structure",
    "get_academic_staff_summary",
    "get_financial_summary",
)

#: Araç → o aracı çağrıştıran kelimeler (sadeleştirilmiş biçimde).
#: Kelimeler PARÇA olarak aranır: "ogrenci" hem "öğrenci" hem
#: "öğrencilerimiz" içinde eşleşir.
#:
#: TÜRKÇE ÜNSÜZ YUMUŞAMASI YÜZÜNDEN KÖKLER KISA TUTULUR.
#: "derslik" yazarsak "dersliğimiz" EŞLEŞMEZ: ek alınca k→ğ dönüşür ve
#: sadeleştirme onu "derslig" yapar. Bu yüzden "dersli" kullanılır.
#: Aynı tuzak "yük→yükü", "renk→rengi" gibi her k/ğ çiftinde vardır.
ANAHTARLAR: Dict[str, tuple] = {
    "get_program_summary": (
        "ogrenci", "bolum", "program", "kontenjan", "doluluk", "mezun",
    ),
    "get_organization_structure": (
        "fakulte", "bolum", "yapi", "organizasyon", "birim", "kac program",
        "meslek yuksekokulu", "myo", "idari",
    ),
    "get_academic_staff_summary": (
        "akademisyen", "akademik personel", "ogretim uyesi", "ogretim gorevlisi",
        "kadro", "maas", "personel",
    ),
    "list_academic_staff": (
        "kim", "isim", "ad soyad", "listele", "hangi akademisyen", "unvan",
        "performans puan", "en yuksek performans",
    ),
    "get_financial_summary": (
        "gelir", "gider", "butce", "mali", "finans", "para", "usd", "maliyet",
    ),
    "get_capacity_summary": (
        "kapasite", "dersli", "laboratuvar", "lab", "koltuk", "siniflar",
        "es zamanli", "fiziksel",
    ),
    "get_facility_inventory": (
        "dersli", "laboratuvar", "lab", "mekan", "envanter", "kac dersli",
        "amfi", "koltuk",
    ),
    "get_classroom_usage": (
        "dersli kullanim", "ders programi", "yogunluk", "bos derslik",
        "kullanim orani", "haftalik",
    ),
    "get_curriculum_summary": (
        "mufredat", "ders sayisi", "kac ders", "akts", "kredi", "ders plani",
    ),
    "get_teaching_load": (
        "ders yuk", "ders veren", "kac ders veriyor", "yuk dagilimi",
        "en cok ders",
    ),
    "get_tuition_comparison": (
        "ucret", "fiyat", "pahali", "ucuz", "burs", "ogrenim ucreti",
        "rakip ucret",
    ),
    "compare_with_peer_universities": (
        "rakip", "akran", "kiyas", "karsilastir", "diger universite",
        "ankara'daki", "universiteler arasi", "bilkent", "odtu", "hacettepe",
        "gazi", "baskent", "atilim", "cankaya",
    ),
    "get_program_quota_trend": (
        "kontenjan", "yerlesen", "doluluk", "trend", "yillara gore", "seyir",
        "son bes yil", "gecmis yillar", "2021", "2022", "2023", "2024", "2025",
    ),
    "get_student_headcount_trend": (
        "ogrenci sayisi", "buyume", "yillara gore ogrenci", "artis", "azalis",
        "trend", "kayitli ogrenci",
    ),
    "get_strategic_kpis": (
        "kpi", "hedef", "stratejik", "gosterge", "performans hedefi", "plan",
    ),
    "get_early_warnings": (
        "risk", "uyari", "sorun", "tehlike", "dikkat", "erken uyari",
    ),
    "get_ranking_frameworks": (
        "siralama", "the", "qs", "yok", "akreditasyon", "cerceve",
        "degerlendirme",
    ),
    "run_enrollment_change_scenario": (
        "artarsa", "azalirsa", "senaryo", "ne olur", "olsaydi", "varsayalim",
        "%", "yuzde",
    ),
    "run_staff_salary_scenario": (
        "zam", "maas art", "senaryo", "ne olur", "olsaydi", "varsayalim",
        "personel gideri",
    ),
}

#: Bu sayının altında araç varsa eleme YAPILMAZ; zaten bütçe sorunu yok.
ELEME_ESIGI = 8
#: Gönderilecek en fazla araç. Eşleşme daha fazlaysa çekirdek öncelikli
#: olacak şekilde kırpılır.
# Yeni araçlar anahtar sözlüğüne katılır (tek kaynak korunur).
ANAHTARLAR = {**ANAHTARLAR, **_YENI_ANAHTARLAR}

EN_FAZLA = 8
#: Gönderilecek en az araç. Az eşleşme olursa çekirdekle tamamlanır.
EN_AZ = 5

#: SORU KENDİ ARAÇLARINI BULDUYSA ÇEKİRDEK EKLENMEZ.
#:
#: Bu kadar araç anahtar kelimeyle eşleştiyse soru kataloğun içindedir;
#: çekirdeği de eklemek modelin önüne konuyla ilgisiz seçenekler koyar
#: ve iki çağrılık veri bütçesini yakar (ölçülen örnek: trend sorusunda
#: `get_organization_structure` çağrılması).
#:
#: İki seçildi, bir değil: tek eşleşme bir kelimeye dayanabilir ve
#: yanlış olabilir; o durumda ağı geniş tutmak hâlâ doğrudur.
_CEKIRDEKSIZ_ESIK = 2


def ilgili_araclar(soru: str, mevcut: Sequence[str]) -> List[str]:
    """Soruyla ilgili araç adlarını döndürür.

    `mevcut`, izin süzgecinden geçmiş araç adlarıdır; burada yalnızca
    ONLARIN arasından seçim yapılır — yetki kararı bu modülün işi değil.
    """
    mevcut_kume = list(mevcut)
    if len(mevcut_kume) <= ELEME_ESIGI:
        # Zaten az; elemek kazanç getirmez, risk getirir.
        return mevcut_kume

    # Grafik aracı eleme dışıdır ve tavana sayılmaz (bkz. HER_ZAMAN).
    daimi = [a for a in HER_ZAMAN if a in mevcut_kume]
    son_care = [a for a in SON_CARE if a in mevcut_kume]
    mevcut_kume = [a for a in mevcut_kume
                   if a not in daimi and a not in son_care]

    metin = _sadelestir(soru)
    puan: Dict[str, int] = {}
    for ad in mevcut_kume:
        kelimeler = ANAHTARLAR.get(ad, ())
        vurus = sum(1 for k in kelimeler if _sadelestir(k) in metin)
        if vurus:
            puan[ad] = vurus

    # Çok vuruş alan önce gelsin; eşitlikte kayıt sırası korunur.
    secilen = sorted(puan, key=lambda a: (-puan[a], mevcut_kume.index(a)))

    # ÇEKİRDEK BİR AĞ, HER SORUYA EKLENEN BİR EK DEĞİL.
    # ------------------------------------------------------------------
    # ÖLÇÜLEN ARIZA: "Elektrik ve bilgisayar arasındaki trend farkları"
    # sorusunda seçilen araçlar arasında `get_organization_structure`
    # vardı ve model onu ÇAĞIRDI. Soru iki programın eğilimini soruyor;
    # kurumsal hiyerarşinin bu cevapta hiçbir işi yok. Araç bütçesi
    # ikiyle sınırlı olduğu için bu çağrı, gerçekten gereken ikinci
    # trend sorgusunun yerini yiyordu.
    #
    # Sebep bu döngüydü: çekirdek KOŞULSUZ ekleniyordu. Oysa çekirdeğin
    # gerekçesi tek bir cümleydi — "hiçbir şey eşleşmezse asistan sağır
    # kalmasın". Soru zaten kendi araçlarını bulduysa o gerekçe ortadan
    # kalkar; çekirdeği yine de eklemek, modelin önüne konuyla ilgisiz
    # seçenekler koymak demektir.
    #
    # Kural GENELDİR: hiçbir programa, bölüme ya da araca özel dal yok.
    # Ölçüt yalnızca "soru yeterince eşleşti mi".
    yeterli_eslesme = len(puan) >= _CEKIRDEKSIZ_ESIK
    if not yeterli_eslesme:
        for ad in CEKIRDEK:
            if ad in mevcut_kume and ad not in secilen:
                secilen.append(ad)

    if len(secilen) > EN_FAZLA:
        secilen = secilen[:EN_FAZLA]
    # EN_AZ tamamlaması da aynı gerekçeye bağlıdır. Eşleşme güçlüyken
    # listeyi rastgele araçlarla doldurmak, elemenin amacını tersine
    # çevirirdi: az araç göndermek için yazılmış kod, alakasız araç
    # eklemeye başlardı.
    if not yeterli_eslesme and len(secilen) < EN_AZ:
        for ad in mevcut_kume:
            if ad not in secilen:
                secilen.append(ad)
            if len(secilen) >= EN_AZ:
                break

    # ÖZEL ARAÇ ÖNCE, SERBEST ARAŞTIRMA SONRA.
    # Anahtar kelimeyle gerçekten eşleşen özel araç varsa soru
    # kataloğun içindedir; pahalı keşif turuna gerek yoktur.
    # Eşleşme yoksa model kendi araştırmasını yapabilsin diye
    # `query_canonical_data` ve `explore_data_sources` eklenir.
    kelime = len((soru or "").split())
    if len(puan) < SON_CARE_ESIGI and kelime >= SON_CARE_EN_AZ_KELIME:
        return daimi + son_care + secilen
    return daimi + secilen


def suz(
    semalar: Optional[List[Dict]], soru: str, zorunlu: Optional[str] = None
) -> Optional[List[Dict]]:
    """Şema listesini soruyla ilgili olanlara indirger.

    `zorunlu` verilirse o araç HER HÂLÜKÂRDA listede kalır: backend'in
    niyet yönlendirmesi (senaryo soruları) araç seçiminden önce gelir.

    `None` girdi `None` döner — "araç sunma" kararı korunur.
    """
    if not semalar:
        return semalar

    adlar = [s["function"]["name"] for s in semalar]
    istenen = set(ilgili_araclar(soru, adlar))
    if zorunlu:
        istenen.add(zorunlu)

    suzulmus = [s for s in semalar if s["function"]["name"] in istenen]
    # Güvenlik ağı: süzgeç bir şekilde her şeyi elerse eski listeye dön.
    # Boş araç listesi göndermek, modele "araç yok" demektir ve asistan
    # kurumsal soruya cevap veremez.
    return suzulmus or semalar
