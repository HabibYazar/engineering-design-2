"""Asistan sohbet servisi.

Sorumluluk: sistem yönergesini hazırlamak, konuşma geçmişini tutmak, ARAÇ
ÇAĞRI DÖNGÜSÜNÜ yürütmek ve sağlayıcıyı çağırmak. HTTP ayrıntısı bilmez (o
router'ın işi), Gemini ayrıntısı bilmez (o sağlayıcının işi), araç
doğrulaması yapmaz (o `tool_runner`ın işi).

ARAÇ ÇAĞRI DÖNGÜSÜ
------------------
1. Kullanıcı mesajı + sistem yönergesi + araç tanımları modele gönderilir.
2. Model bir veya birden fazla araç çağırır.
3. Her çağrı `tool_runner` tarafından doğrulanıp çalıştırılır.
4. Sonuçlar `tool` rolüyle konuşmaya eklenir.
5. Model gerekiyorsa başka araç çağırır (en fazla MAX_TOOL_STEPS tur).
6. Adım ya da süre sınırına gelinirse model araçsız olarak son cevabı yazar.

Model kurumsal bir sayıyı yalnızca backend tarafından hazırlanmış bağlamdan
veya başarılı araç sonucundan alabilir. İkisi de yoksa "veri bulunamadı"
demesi beklenir.

Konuşmalar bellekte tutulur, veritabanına yazılmaz.
"""

import json
import logging
import re
import time
import uuid
from datetime import datetime
from collections import OrderedDict
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple


from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.assistant.base import AssistantProvider
from app.services.assistant.provider_shared import AssistantProviderError
from app.services.assistant import provider_factory
from app.services.assistant import (
    context_builder,
    data_catalog,
    entity_resolver,
    query_policy,
    response_composer,
    ui_spec_builder,
)
from app.services.assistant import tools as _tools  # noqa: F401  (kayıt için)
# EK ARAÇLAR — erişilemeyen veri kümelerini açar. Ayrı modül: `tools.py`
# içindeki yedi aracın davranışı değişmesin, gerekirse bu satır silinerek
# eski hâle dönülebilsin.
from app.services.assistant import tools_extended as _tools_ext  # noqa: F401
# Grafik aracının kayıt defterine girmesi için içe aktarılır. Kaldırılırsa
# `render_chart` sessizce yok olur ve model grafik çizemez.
from app.services.assistant import chart_tool as _chart_tool  # noqa: F401
# Son iki günde eklenen canonical veri kümelerini asistanın erişimine
# açan araçlar. Sağlayıcıya, yönergeye ya da döngüye dokunmaz; yalnızca
# kayıt defterine yeni araçlar ekler.
from app.services.assistant import tools_newdata as _tools_newdata  # noqa: F401
# Serbest keşif ve salt okunur sorgu. Modelin hangi veriye bakacağına
# kendisi karar edebilmesi için; sağlayıcıya dokunmaz.
from app.services.assistant import tools_generic as _tools_generic
from app.services.assistant import coklu_metrik
from app.services.assistant import grafik_donustur
from app.services.assistant import grafik_uret
from app.services.assistant import grounded_cevap
from app.services.assistant import kisi_adi
from app.services.assistant import veri_ailesi
from app.services.assistant import veri_ozeti  # noqa: F401
from app.services.assistant import tool_compaction
from app.services.assistant import tool_selection
from app.services.assistant.tool_registry import registry
from app.services.assistant.tool_runner import ToolCallRecord, ToolSession

logger = logging.getLogger(__name__)

# Modelin bir soruda yapabileceği en fazla araç turu.
# 5 → 8: araç sayısı 7'den 18'e çıktı ve gerçek bir kıyas sorusu artık
# birkaç kaynağı sırayla toplamayı gerektiriyor ("bizim doluluğumuz" →
# "akranların doluluğu" → "kadro" → yorum). Beş tur bu zinciri yarıda
# kesiyordu.
#: SAĞLAYICIYA YAPILAN GERÇEK İSTEK SAYISI — SERT TAVAN.
#:
#: NEDEN 3
#: -------
#: Buradaki değer 8'di ve döngü her araç turundan sonra sağlayıcıyı
#: yeniden çağırdığı için TEK KULLANICI SORUSU 9 API isteğine kadar
#: çıkabiliyordu. Gemini'nin ücretsiz katmanında günlük sınır 20 istek
#: (ölçüldü: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`,
#: quotaValue 20). Yani tek bir soru günlük hakkın yarısını yakıyordu;
#: serbest keşif araçları eklendikten sonra da döngü tamamlanamadan
#: kota bitiyor ve kullanıcı HİÇ CEVAP ALAMIYORDU.
#:
#: 3 tur şu akışa yeter ve fazlasına izin vermez:
#:     1. soru → model araç ister
#:     2. araç sonucu → model ikinci (farklı alandan) araç isteyebilir
#:     3. son sonuç → MODEL CEVABI YAZAR (bu turda araç sunulmaz)
MAX_LLM_ROUNDS_PER_USER_MESSAGE = 3

#: Bir kullanıcı mesajında çalıştırılacak en fazla VERİ çağrısı.
#: Grafik çizimi buna sayılmaz: `render_chart` yeni veri getirmez,
#: eldeki araç sonucunu çizer.
MAX_DATA_TOOL_CALLS = 2

#: Veri getirmeyen, dolayısıyla bütçeye sayılmayan araçlar.
BUTCE_DISI_ARACLAR = frozenset({"render_chart"})

#: Geriye dönük ad. Döngü artık tur sayısını `MAX_LLM_ROUNDS...`
#: üzerinden sınırlar; bu sabit yalnızca dışa aktarım listesinde
#: kalan eski adı kırmamak için duruyor.
MAX_TOOL_STEPS = MAX_LLM_ROUNDS_PER_USER_MESSAGE

# =====================================================================
# SÜRE BÜTÇESİ — TEK YER
# =====================================================================
# ÖLÇÜLEN OLAY: `.env` içinde GEMINI_TIMEOUT_SECONDS=120 vardı. Bu değer
# `_effective_timeout()` üzerinden `httpx.Client(timeout=...)`e gidiyordu,
# yani TEK BİR HTTP isteğinin sınırıydı — turun tamamının değil. Model
# yanıt vermeyince istek 120 saniye askıda kalıyor, sonunda 504 dönüyordu.
# Üç tur × 120 sn = teorik 360 saniye. Sunumda kullanılamaz.
#
# Artık iki ayrı sınır var ve ikisi de burada tanımlı:
#
#   GEMINI_ROUND_TIMEOUT_SECONDS  bir model çağrısı en fazla bu kadar bekler
#   MAX_USER_TURN_SECONDS         kullanıcı mesajının başından cevaba kadar
#
# Turun tamamı her zaman üstündür: kalan süre tur sınırından azsa model
# çağrısı KALAN SÜRE kadar bekler (bkz. `_tur_timeout`). "Üç turu
# tamamlayayım" diye toplam sınır aşılmaz.

#: Tek bir Gemini çağrısının üst sınırı (saniye).
#:
#: 25 → 40 → 120. Ölçülen olay: 40 saniyeye çıkarıldıktan SONRA bile
#: `ROUND 3 TIMEOUT duration=40.4` görüldü. Yani sınır neredeyse tam
#: dolduruluyordu; model cevabı yazmaya başlamadan kesiliyordu.
#:
#: BURADAKİ TERCİH AÇIKÇA SÖYLENMELİ: bu bir AI kokpiti. Kullanıcı
#: fallback özeti değil, modelin gerçek analizini okumak istiyor. Süre
#: ve token tasarrufu, cevap üretme güvenilirliğinin ARKASINDADIR.
#: Gerekirse bir dakika beklenir; normal bir analiz sorusunda cevap
#: zaman aşımıyla kesilmez.
#:
#: Tur SAYISI yine artırılmadı: üç tur ve iki veri çağrısı aynı. Sorun
#: turların sayısı değil, var olan turların kesilmesiydi.
#:
#: Not: gecikmenin ASIL sebebi bu sınır değildi — modele hiç düşünme
#: seviyesi gönderilmiyordu (bkz. `GEMINI_REASONING_EFFORT`). Bu sınır
#: yine de yükseltildi ki tavan, ağır sorularda dar gelmesin.
GEMINI_ROUND_TIMEOUT_SECONDS = 120.0

#: Kullanıcı mesajının tamamı için üst sınır (saniye).
#: Model turları + araç çalıştırma + finalizasyon hepsi bunun içinde.
#:
#: 45 → 90 → 240. Üç tur × 120 saniye teorik olarak 360 eder; 240
#: bilinçli bir orta yoldur: üçüncü tur global sınır yüzünden boğulmaz
#: (asıl şikâyet buydu), ama istek de sonsuza kadar askıda kalmaz.
MAX_USER_TURN_SECONDS = 240.0

#: Zaman aşımı özetinde gösterilecek en fazla araç / satır / alan.
#: Amaç kullanıcıya işe yarar bir kesit vermek; ham 500 satır JSON
#: basmak değil.
_OZET_ARAC = 2
_OZET_SATIR = 5
_OZET_ALAN = 4

#: Model çağrısından sonra cevabı hazırlamak için ayrılan pay (saniye).
#: Ayrıştırma + özet + yanıtın yazılması bu süreye sığar.
_TUR_SONU_MARJI = 1.5

#: Kalan süre bunun altındaysa yeni model çağrısı başlatılmaz: anlamlı
#: bir yanıt gelmeyecek kadar kısa bir pencerede beklemek kullanıcıyı
#: boşuna oyalar.
_EN_AZ_TUR_PAYI = 2.0

#: Veri araçlarının üst sınırı (saniye). Kayıtlı araçların kendi
#: değerleri 10–30 sn arasındaydı; hepsi yerel SQLite/CSV okuması
#: yaptığı için bu tavan uygulanır. Kendi sınırı zaten daha düşük olan
#: araç OLDUĞU GİBİ KALIR — hiçbir aracın süresi uzatılmaz.
DATA_TOOL_TIMEOUT_SECONDS = 10.0

# Geriye dönük ad: eski `MAX_TOOL_WALL_SECONDS` artık turun toplam
# sınırıyla aynı şeydir. 180 → 45.
MAX_TOOL_WALL_SECONDS = MAX_USER_TURN_SECONDS

# SAĞLAYICI TOKEN BÜTÇESİ.
# ---------------------------------------------------------------------
# Bulut sağlayıcı dakikalık bir token bütçesi uyguluyor ve bu bütçe TÜM
# turların TOPLAMIDIR. Ölçüldü: iki turluk bir kıyas sorusu ~7.700 token
# harcıyor; üçüncü tur bütçeyi aşıyor ve sağlayıcı isteği HTTP 413 ile
# reddediyor — kullanıcı da yalnızca bir hata balonu görüyor.
#
# Bütçeyi sağlayıcının reddetmesine bırakmak yerine KENDİMİZ izliyoruz:
# sınıra yaklaşınca araç sunmayı bırakır, modele "elindeki veriyle
# cevabı yaz" deriz. Eksik ama gerçek bir cevap, hiç cevap vermemekten
# iyidir.
#
# BÜTÇE KÜMÜLATİFTİR — TEK İSTEK DEĞİL.
# İlk sürümüm tek isteğin boyutuna bakıyordu ve hiç devreye girmiyordu:
# her tur ayrı ayrı 5.000'in altında kalıyor ama dört tur toplamda
# 17.700 token harcıyordu. TPM dakikadaki TOPLAMI sayar; kontrol de
# toplamı saymalı.
#
# BU SAYI SAĞLAYICIYA BAĞLIDIR — SABİT DEĞİL.
# Değer önce 3.000'di ve Groq'un 8.000 TPM sınırı için ÖLÇÜLMÜŞTÜ:
#
#     eşik 5.500 → 3 tur, 2'si araçlı → 10.942 token   TAŞAR
#     eşik 3.500 → 3 tur, 2'si araçlı → 10.942 token   TAŞAR
#     eşik 3.000 → 2 tur, 1'i araçlı  →  5.981 token   geçer
#
# O ölçüm doğruydu ama VARSAYIMI Gemini'ye geçince çürüdü: Gemini'nin
# ücretsiz katmanında darboğaz token değil İSTEK SAYISIDIR (ölçüldü:
# dakikada 5). Token tavanı 3.000'de kalınca sabit yük (yönerge + 8
# şema ≈ 3.200) ilk turdan sonra bütçeyi doldurup araçları kapatıyordu.
#
# Bunun görünen sonucu şuydu: model veriyi çekiyor, sonra grafik
# çizdirmek için ikinci aracı çağıramıyordu — grafik özelliği,
# artık geçerli olmayan bir sağlayıcının sınırı yüzünden imkânsızdı.
# Ölçülen kanıt: "Token butcesi doldu (kumulatif ~3998); araclar
# kapatildi."
#
# Bu yüzden değer artık `.env`den okunur. Sağlayıcı değişince kod
# değil ayar değişir; eski sağlayıcının sınırı yeni sağlayıcıya
# sessizce miras kalmaz.
MAX_PROMPT_TOKENS = settings.ASSISTANT_MAX_PROMPT_TOKENS
#: KARMAŞIK TURDA BİRAZ DAHA GENİŞ BÜTÇE.
#: Grafik, karşılaştırma, sıralama ve eğilim soruları hem daha çok araç
#: sonucu hem daha uzun cevap gerektiriyor; bütçe dolduğunda araçlar
#: kapanıyor ve ikinci veri turu imkânsız hale geliyordu. Artış ORANSAL
#: ve yalnızca bu turlara özgü: basit sorular eski bütçeyle çalışmaya
#: devam eder, dolayısıyla ortalama gecikme değişmez.
_KARMASIK_BUTCE_CARPANI = 1.5
_KARMASIK_NIYET = ("ranking", "trend", "comparison")


def _tur_butcesi(plan, grafik_istendi: bool) -> float:
    """Bu turun istem bütçesi. Varsayılan korunur, karmaşıkta genişler."""
    karmasik = bool(grafik_istendi) or (
        plan is not None and getattr(plan, "niyet", "") in _KARMASIK_NIYET)
    return MAX_PROMPT_TOKENS * (_KARMASIK_BUTCE_CARPANI if karmasik else 1.0)
# Kaba tahmin; kesin sayaç yerine oran yeterli çünkü karar "tavana
# yaklaştık mı" sorusudur.
_KARAKTER_BASINA_TOKEN = 3.3


def _tahmini_token(messages, tools=None) -> float:
    """İsteğin kabaca kaç token tutacağı."""
    govde = json.dumps(messages, ensure_ascii=False, default=str)
    if tools:
        govde += json.dumps(tools, ensure_ascii=False, default=str)
    return len(govde) / _KARAKTER_BASINA_TOKEN

# Senaryo sonucu zorunlu alanları taşımıyorsa kullanıcıya gösterilen metin.
MISSING_METRIC_MESSAGE = (
    "Senaryo sonucu eksik üretildi; bazı zorunlu göstergeler hesaplanamadı. "
    "Güvenilir olmayan bir sonuç göstermemek için sayısal cevap "
    "oluşturulmadı."
)

SYSTEM_PROMPT = """Sen, Ankara Bilim Üniversitesi Karar Destek Sistemi'nde çalışan bir yönetim asistanısın. Üst yönetime kurum verisine dayalı, doğrulanabilir cevaplar verirsin.

KAPALI DÜNYA
0. İnternete erişimin YOKTUR: internet üzerinden arama yapamaz, sayfa açamaz, dış kaynaktan veri getiremezsin. "İnternetten baktım", "güncel veriye göre" gibi ifadeler kullanma.
0a. Kurum dışı bilgi sorulursa: "Bu bilgi sistemdeki veriler arasında yok ve dışarıdan veri getiremiyorum" de.
0b. Genel kavramları açıklayabilirsin. Ama SAYI, TARİH, SIRALAMA veya KURUM ADI içeren hiçbir iddiayı kendi ön bilginden üretme.

MERKEZİ VERİ TABANI
0c. Kurumun bütün kaynak verisi tek veritabanında: 62 tablo, 36.020 satır. `query_canonical_data` ile eriş; kaynak adları `kds_` ile başlar. Emin değilsen `explore_data_sources` ile TÜRKÇE ara ("öğrenci sayısı", "taban puan", "ücret", "derslik") — kaynak adları İngilizce olsa da bulunur.
0d. Çok yıllı taban puan için `kds_yks_ankara_taban_puan_5yil` kaynağı Ankara'nın 2021-2025 puanlarını tek eksende verir. Bu kaynaklarda gruplama/toplama yoktur; `order_by`, `filters`, `limit` ile daralt.

KİŞİ ADLARI
0e. KURUMSAL BİR KİŞİNİN ADINI ASLA UYDURMA, TAHMİN ETME VE TAMAMLAMA. Akademisyen, öğretim üyesi/görevlisi, araştırma görevlisi, bölüm başkanı, dekan, rektör, yönetici, danışman ve personel adları buna dahildir.
0f. Bir kişinin adını YALNIZCA o kişi backend bağlamında ya da başarılı bir araç sonucunda AÇIKÇA geçiyorsa yazabilirsin. Geçmiyorsa adı yazma; "bir öğretim üyesi", "ilgili bölüm başkanı" gibi genel ifadelerle cevabı tamamla.
0g. Bu kural yalnızca KİŞİ adları içindir. Üniversite, fakülte, bölüm, program ve şehir adlarını serbestçe kullanabilir; yorum, analiz ve öneri yapmaya devam edebilirsin.

VERİ KULLANIMI
1. Kurumsal sayıları YALNIZCA backend bağlamından veya başarılı araç sonuçlarından al. Hiçbir rakamı kendi bilginden üretme.
2. Değer bağlamda varsa onu kullan, tekrar araç çağırma. Yoksa aracı çağır. İkisinde de yoksa UYDURMA: "Bu bilgi için gerekli veriye ulaşamadım" de.
3. Kafandan hesap YAPMA. Toplama, çıkarma, yüzde gerekiyorsa aracı çağır; dönen değerleri olduğu gibi aktar.
4. Araç hata döndürür ve değer bağlamda da yoksa sayı verme; hatanın sebebini sade dille açıkla.
5. Araç çıktısındaki "notes" uyarılarını ve kaynak bilgisini cevabına taşı.

SENARYO
6. "Artarsa", "azalırsa", "zam yapılırsa", "ne olur" gibi VARSAYIM sorularında SENARYO aracını çağır. Mevcut durumu döndüren özet araçları değişimin etkisini hesaplamaz.
7. Yalnızca mevcut durum soruluyorsa senaryo ÇALIŞTIRMA.
7a. Senaryo sonucu sana hazır verilmişse yeni araç çağırma, yorumla.
7b. "Hesaplanan sonuçlar" bölümü kullanıcıya aynen gösterilir. O değerleri değiştirme, yeniden hesaplama, yuvarlama, tekrar listeleme; yalnızca etkilerini yorumla.

GRAFİK
7c. Kullanıcı grafik, çizim, görselleştirme istiyorsa ya da "göster" diyorsa: önce veriyi getiren aracı çağır, sonra render_chart aracını çağır. Grafiği metinle tarif etme, ÇİZ.
7d. render_chart'a sayı YAZMAZSIN; hangi araç sonucundan hangi alanların çizileceğini söylersin. Alan adlarını o aracın çıktısında gördüğün adlardan seç.
7e. Zaman serisi (x_field="year") DAİMA chart_type="line" olmalı; yıllarda çubuk kullanma. Tek bir yılın birim/kurum karşılaştırmasında "bar" kullan.
7g. Birden çok kurum/birim çizdiriyorsan series_field'i MUTLAKA ver (örneğin "university"). Vermezsen seriler isimsiz kalır ve grafik okunmaz.
7f. Grafik çizildiyse sayıları metinde tekrar sıralama; yorumu yaz.
7h. CEVAP METNİNE GRAFİK KODU YAZMA: render_chart bloğu, JSON payload, kod çiti. Grafiği araçla istersin; metinde yalnızca yorum olur.

CEVAP BİÇİMİ
8. Her zaman Türkçe.
9. Başta akademik yılı ve kapsamı (üniversite/fakülte/bölüm/program) belirt.
10. Para değerlerini USD ve okunabilir yaz (35.960.000 USD).
11. Veri eksikse "veri bulunamadı" de; sıfır yazma.
12. Hesaplanmış sonuç ile genel bilgiyi ayır; genel yöntem anlatıyorsan kurum verisi olmadığını söyle.
13. Teknik araç adlarını YAZMA; "öğrenci kayıtları", "mali dönem kayıtları" gibi anlaşılır kaynak adları kullan.
14. Yönetici odaklı ver: kısa, madde işaretli, eyleme dönük.

BİRİM ADLARI
15. Bölüm/program adını kullanıcı nasıl yazdıysa araca öyle ver; eşleştirmeyi sistem yapar.
16. "Birden fazla eşleşme" hatasında seçenekleri sun ve sor. Kendin seçme.

KAPSAM VE KAYNAK DÜRÜSTLÜĞÜ — PAZARLIK YOK
17. Ekrandaki seçim VARSAYILAN kapsamdır. Soruda açıkça başka birim adı geçerse o kazanır. Yıl, açıkça yazılmadıkça seçili yıldır.
18. Kapsamda veri yoksa ÜNİVERSİTE GENELİ değerini o kapsamınmış gibi SUNMA. Üst kapsamdan veriyorsan açıkça söyle.
19. Eksik veriyi SIFIR sayma. "Veri yok" ile "sıfır" farklıdır.
20. Kişi, sayı, metrik, kaynak, yıl, kıyas, kayıt UYDURMA.
21. Sana verilmeyen bir veriyi sorguladığını, gördüğünü, hesapladığını İDDİA ETME.
22. Değer türünü ayırt et ve gerektiğinde belirt: yetkili kayıt / türetilmiş-tahmini / kullanıcı yüklemesi / erişilemeyen.
23. YÖK Atlas ve YKS yerleştirmelerinden türeyen öğrenci değerleri KOHORT TAHMİNİDİR; resmî kayıtlı sayı olmadığını yaz.
24. Kullanıcının yüklediği veriyi kullanıyorsan bunu belirt.
25. Personel adı, unvanı ve performans puanı bu panelde açıktır; veri geldiyse gizleme, gelmediyse uydurma.
26. Puan gerekçesini YALNIZCA bileşenlerden (yayın, atıf, ders yükü, danışmanlık, proje) kur; bileşen yoksa gerekçe icat etme.
27. "Kontrol ediyorum", "verileri çekeceğim" gibi gelecek vaadi verme. Veri verildiyse açıkla, verilmediyse yok de.
28. Katalogdan yapılandırılmış satırlar verildiyse sayıları tekrar yazma ve "veri yok" deme; kısa, sayısız yönetici yorumu yap.
29. Sorunun tanımlı bir niyete uymaması verinin yok olduğu anlamına gelmez; katalogdaki her yetkili metriği kullanabilirsin.

ANALİZ — SEN BİR ARAMA KUTUSU DEĞİLSİN
30. Sayıları YORUMLA. Değeri aktarmak başlangıçtır: büyük mü küçük mü, neye göre, hangi yöne gidiyor, yönetici ne çıkarmalı. Yorum yasak değil; SAYI UYDURMAK yasak.
31. Tek araç yetmiyorsa BİRDEN ÇOK ARAÇ ÇAĞIR. "Rakiplere göre nerede?" kendi değerimizi, akranınkini ve gerekiyorsa kadro/kapasiteyi ister.
32. Bir aracın sonucu diğerinin parametresini belirleyebilir: önce genel resim, sonra dikkat çeken birime in.
33. ORAN, FARK, SIRALAMA, EĞİLİM çıkarabilirsin ("iki katı", "üç yıldır düşüyor", "21 kurumda 18'inci"). Bu uydurma değil, verilen sayıların okunmasıdır. Karmaşık hesabı kafandan yapma; araç varsa çağır.
34. Veriler çelişiyorsa çelişkiyi SÖYLE ve hangi kaynağın yetkili olduğunu belirt. Sessizce birini seçme.
35. Soru belirsizse en olası okumayla cevapla, varsayımını tek cümleyle yaz. Soru sorup kullanıcıyı bekletme.
36. Bulgunun yönetimsel anlamını yazabilirsin. Öneriyi temkinli kur, dayanağını göster. Dayanaksız tavsiye verme.
37. Grafik istenirse veriyi grafiğe uygun kırılımda topla (yıl serisi, birim kırılımı). Görseli sistem üretir; senin işin doğru veriyi getirip ne anlattığını yazmak.
"""


class ChatValidationError(ValueError):
    """Kullanıcı mesajı kurallara uymuyor."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class ConversationStore:
    """Bellekte tutulan konuşma geçmişi (LRU)."""

    def __init__(self, max_conversations: int, max_messages: int) -> None:
        self._data: "OrderedDict[str, List[Dict[str, str]]]" = OrderedDict()
        self.max_conversations = max_conversations
        self.max_messages = max_messages

    def get(self, conversation_id: Optional[str]) -> List[Dict[str, str]]:
        if not conversation_id:
            return []
        history = self._data.get(conversation_id)
        if history is None:
            return []
        self._data.move_to_end(conversation_id)
        return list(history)

    def append(self, conversation_id: str, role: str, content: str) -> None:
        history = self._data.setdefault(conversation_id, [])
        history.append({"role": role, "content": content})
        if len(history) > self.max_messages:
            del history[: len(history) - self.max_messages]
        self._data.move_to_end(conversation_id)
        while len(self._data) > self.max_conversations:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


_store = ConversationStore(
    max_conversations=settings.ASSISTANT_MAX_CONVERSATIONS,
    max_messages=settings.ASSISTANT_MAX_HISTORY_MESSAGES,
)

# Structured catalog memory powers safe follow-ups such as "Grafiğini
# göster".  It stores backend rows, never numbers parsed from model prose.
_catalog_datasets: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def _remember_catalog_dataset(conversation_id: str, dataset: Dict[str, Any]) -> None:
    _catalog_datasets[conversation_id] = dataset
    _catalog_datasets.move_to_end(conversation_id)
    while len(_catalog_datasets) > settings.ASSISTANT_MAX_CONVERSATIONS:
        _catalog_datasets.popitem(last=False)


_CATALOG_INTERPRETATION_REJECT = re.compile(
    r"veri\s+(?:yok|bulunamad|bulunmuyor)|ulaşılamad|"
    r"kontrol\s+ediyorum|kontrol\s+etmeni|sorguluyorum|çekeceğim|"
    r"sunacağım|bakacağım|araştıracağım",
    re.IGNORECASE,
)


def _catalog_grounding(dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Provide the full numeric truth from dataset to ground the LLM."""
    metrics = []
    for metric in dataset.get("metrics") or []:
        rows = [
            {
                "entity": row.get("label"),
                "entity_type": row.get("entity_type_label") or row.get("entity_type"),
                "value": row.get("value"),
                "unit": row.get("unit") or metric.get("unit"),
                "source": row.get("source_label"),
            }
            for row in (metric.get("rows") or [])
            if row.get("value") is not None
        ]
        metrics.append(
            {
                "metric": metric.get("label") or metric.get("canonical_label"),
                "unit": metric.get("unit"),
                "rows": rows,
            }
        )
    return {
        "academic_year": dataset.get("academic_year"),
        "operation": dataset.get("operation"),
        "intent": dataset.get("intent"),
        "metrics": metrics,
        "derived_metrics": dataset.get("derived_metrics") or [],
        "growth_summary": dataset.get("growth_summary") or [],
        "executive_priorities": dataset.get("executive_priorities") or [],
        "executive_recommendations": dataset.get("executive_recommendations") or [],
        "analysis_findings": dataset.get("analysis_findings") or [],
        "unavailable_metrics": [
            f"{item['label']}: {item['reason']}"
            for item in (dataset.get("unavailable_metrics") or [])
        ],
        "notes": dataset.get("notes") or [],
    }



UNSUPPORTED_SPECULATION_WORDS = (
    "ders kalitesi",
    "ders kalitesini",
    "mezuniyet oran",
    "yüksek maliyetli",
    "kaynak verimlili",
    "kadro verimsiz",
    "kapasite yönetimi",
    "risk seviyesi",
    "tehdit eder",
    "tehdit ediyor",
)


def _compact_source_names(sources: Sequence[str]) -> List[str]:
    compact = []
    seen = set()
    for s in sources:
        sl = s.lower()
        if "yök resmî" in sl or "yok resmi" in sl:
            name = "YÖK resmî kayıtlı öğrenci sayısı"
        elif "ösym" in sl or "yks" in sl or "yerleştirme" in sl:
            name = "ÖSYM/YKS"
        elif "yök atlas" in sl or "yokatlas" in sl:
            name = "YÖK Atlas"
        elif "akademik personel" in sl or "akademisyen" in sl:
            name = "Akademik Personel"
        elif "oran" in sl or "büyüklüğü /" in sl:
            continue
        elif "fiziksel" in sl:
            name = "Fiziksel Envanter"
        elif "müfredat" in sl:
            name = "Müfredat Kayıtları"
        elif "ücret" in sl:
            name = "Ücret Verisi"
        else:
            name = s.split("·")[0].strip()
        if name and name not in seen:
            seen.add(name)
            compact.append(name)
    return compact


def _format_source_footer(dataset: Dict[str, Any]) -> str:
    sources = _compact_source_names(dataset.get("data_sources") or [])
    has_derived = any(
        row.get("source_type") == data_catalog.SOURCE_DERIVED
        for m in (dataset.get("metrics") or [])
        for row in (m.get("rows") or [])
    ) or bool(dataset.get("derived_metrics")) or bool(dataset.get("growth_summary")) or bool(dataset.get("analysis_findings"))
    lines = []
    if sources:
        lines.append("Kaynak: " + " · ".join(sources))
    if has_derived:
        lines.append("Not: Alt birim öğrenci değerleri kohort bazlı tahminidir; resmî kayıtlı öğrenci sayısı değildir.")
    return ("\n\n" + "\n".join(lines)) if lines else ""


def _catalog_executive_answer(
    provider: AssistantProvider, question: str, dataset: Dict[str, Any]
) -> str:
    """Produce executive, grounded response using the single structured truth."""
    if dataset.get("finding_answer"):
        return dataset["finding_answer"] + _format_source_footer(dataset)

    if not provider.etkin_model() and not provider.resolve_model():
        return data_catalog.render_answer(dataset, question)


    grounding = _catalog_grounding(dataset)
    system_prompt = (
        "Sen Ankara Bilim Üniversitesi Rektörlük / Üst Yönetim Karar Destek Sistemi kıdemli analitik asistanısın.\n"
        "Görevin üst yöneticiye doğrudan, net, 10 saniyede okunabilir, analitik ve eyleme dönük bir karar özeti sunmaktır.\n\n"
        "KAT'İ KURALLAR:\n"
        "1. ASLA '#' veya '##' veya '###' başlık formatı KULLANMA. Başlık yazma.\n"
        "2. 'Durum:', 'Risk:', 'Gerekçe:', 'Kaynak:' gibi ara başlıklar ASLA KULLANMA.\n"
        "3. Her maddeyi tek bir kısa satırda tut. Maksimum 3-5 kısa satır/madde yaz. Paragraf veya rapor yazma.\n"
        "4. Tablo oluşturma.\n"
        "5. Sadece verilen gerçek ve türetilmiş sayıları (derived_metrics, executive_priorities) kullan. Sayı uydurma. Metriklerde yer almayan spekülatif yorumlar (ör. 'ders kalitesini tehdit ediyor', 'mezuniyet oranını düşürüyor', 'maliyetli', 'verimsiz', 'riskli', 'risk seviyesi', 'kapasite yönetimi') ASLA YAPMA. 'Risk' kelimesini kullanma.\n"
        "6. Yalnızca somut göstergeleri doğrudan belirt (ör. 'İnsan ve Toplum Bilimleri — 1219 öğrenci / 972 kapasite → %25,4 aşım (39,3 öğrenci/akademisyen)').\n"
        "7. Eğer 'unavailable_metrics' listesinde bir metrik verilmişse (ör. 'Fakülte Düzeyi Öğrenim Ücreti'), bunu tek bir kısa satırda belirt (ör. 'Ücret: fakülte düzeyinde mevcut değil.').\n"
        "8. Karar, öncelik veya öneri isteniyorsa, gerçek kanıtlara dayalı 3 net konu ve 3 kısa öneri maddesi ekle. Önerilerde 'değerlendirilebilir', 'incelenmeli', 'önceliklendirilebilir' gibi temkinli ifadeler kullan.\n"
        "9. Basit sorularda (ör. toplam öğrenci) tek bir net cümle yaz (ör. '2025-2026 toplam öğrenci sayısı: 3.626.').\n\n"
        "ÖRNEK FORMAT:\n"
        "En kritik 3 konu:\n"
        "1. Fiziksel kapasite — İnsan ve Toplum Bilimleri %125,4 kapasite kullanımında (247 aşım).\n"
        "2. Akademik yük — Yazılım Mühendisliğinde 74 öğrenci/akademisyen ile en yüksek yük var.\n"
        "3. Büyüme fırsatı — Endüstri Mühendisliği 102 öğrenci ile YÖK Atlas benzer program medyanı 236'nın altında.\n\n"
        "Öneri:\n"
        "- İnsan ve Toplum Bilimleri için ek derslik tahsisi ve şube planlaması değerlendirilebilir.\n"
        "- Yazılım Mühendisliği için akademik kadro takviyesi veya ders yükü dengelemesi incelenebilir.\n"
        "- Endüstri Mühendisliği için talep ve kontenjan artırma stratejisi planlanabilir."
    )


    user_prompt = f"SORU: {question}\n\nGERÇEK VERİLER:\n{json.dumps(grounding, ensure_ascii=False, indent=2)}"


    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        tool_calls, visible, _thinking = provider.chat_with_tools(prompt, None)
    except AssistantProviderError:
        logger.warning("Model executive yanit uretemedi; deterministik formata donuluyor.")
        return data_catalog.render_answer(dataset, question)

    raw_text = (visible or "").strip()
    if tool_calls or not raw_text:
        return data_catalog.render_answer(dataset, question)

    if _CATALOG_INTERPRETATION_REJECT.search(raw_text):
        logger.warning("Model yaniti gecersiz iddia icerdigi icin elendi; deterministik formata donuluyor.")
        return data_catalog.render_answer(dataset, question)

    clean_lines = []
    for line in raw_text.splitlines():
        line = line.lstrip("#").strip()
        if not line:
            continue
        if line.lower().startswith("kaynak:") or line.lower().startswith("not:"):
            continue
        line = re.sub(r"^\s*(?:\*|-|\d+\.)?\s*\*\*(?:Durum|Risk|Gerekçe|Kaynak)\s*:\*\*\s*", "", line, flags=re.I)
        for bad_word in UNSUPPORTED_SPECULATION_WORDS:
            if bad_word in line.lower():
                line = re.sub(r",\s*[^,.]*?(?:risk|tehdit|verimsiz|maliyet|kalite)[^,.]*", "", line, flags=re.I)
        clean_lines.append(line)
    cleaned_text = "\n".join(clean_lines).strip()

    footer = _format_source_footer(dataset)
    return cleaned_text + footer



#: Backward-compatibility alias for tests
_catalog_interpretation = _catalog_executive_answer




def _catalog_scope(dataset: Dict[str, Any]) -> Dict[str, str]:
    entities = dataset.get("entities") or []
    if not entities and dataset.get("parent"):
        entities = [dataset["parent"]]
    if not entities:
        return {}
    return {
        "entities": "; ".join(
            f"{entity.get('label')} ({entity.get('entity_type_label')})"
            for entity in entities
        )
    }


def get_provider() -> AssistantProvider:
    """Yapılandırılmış sağlayıcıyı döndürür.

    ESKİDEN DOĞRUDAN yerel sağlayıcıyı ÜRETİYORDU ve kayıt defterini
    (`provider_factory`) atlıyordu. Sonuç: `.env` içinde LLM_PROVIDER ne
    yazarsa yazsın hep aynı sağlayıcı çalışıyordu — yani sağlayıcı ayarı
    aslında hiçbir şeyi değiştirmiyordu.

    Artık seçim tek yerden yapılır. Tanınmayan bir ad yazılırsa fabrika
    `NoProviderConfigured` döndürür ve sistem sessizce başka bir
    sağlayıcıya düşmez.
    """
    return provider_factory.get_provider()


def validate_message(message: str) -> str:
    """Kullanıcı mesajını doğrular ve temizler."""
    cleaned = (message or "").strip()
    if not cleaned:
        raise ChatValidationError("Mesaj boş olamaz.")
    limit = settings.ASSISTANT_MAX_MESSAGE_LENGTH
    if len(cleaned) > limit:
        raise ChatValidationError(
            f"Mesaj çok uzun. En fazla {limit} karakter gönderebilirsiniz "
            f"(gönderilen: {len(cleaned)})."
        )
    return cleaned


def build_messages(user_message: str, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Modele gönderilecek mesaj listesini kurar: system + geçmiş + yeni soru."""
    # Sistem yönergesinin ÇEKİRDEĞİ DEĞİŞMEZ. Eğilim kuralı yalnızca
    # SORU EĞİLİM SORDUĞUNDA eklenir: her mesaja iliştirmek hem boşuna
    # token harcar hem de "yeni konuşma temiz başlar" sözleşmesini
    # gereksizce kalabalıklaştırırdı.
    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if _EGILIM_SORUSU.search(user_message or ""):
        messages.append({"role": "system", "content": _EGILIM_KURALI})
    messages.extend(
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("role") in ("user", "assistant")
    )
    messages.append({"role": "user", "content": user_message})
    return messages


def _prepare(message: str, conversation_id: Optional[str]) -> Tuple[str, List[Dict[str, str]]]:
    """Doğrulama + geçmiş + konuşma kimliği."""
    cleaned = validate_message(message)
    conversation = conversation_id or str(uuid.uuid4())
    history = _store.get(conversation_id)
    # Günlüğe mesajın tamamı yazılmaz; yalnızca uzunluğu.
    logger.info(
        "Asistan istegi: konusma=%s gecmis=%d mesaj_uzunlugu=%d",
        conversation[:8],
        len(history),
        len(cleaned),
    )
    return conversation, build_messages(cleaned, history)



_CONTEXT_STOPWORDS = {
    "acaba", "bizim", "bize", "bu", "kaç", "kac", "ne", "nedir", "kadar",
    "sayısı", "sayisi", "sayımız", "sayimiz", "olan", "var", "kaçtır", "kactir",
    "toplamı", "toplami", "mevcut", "şu", "su",
}


#: KÜÇÜK, AÇIK EŞ ANLAM KÖPRÜSÜ.
#: Kullanıcı "akademisyen" der, bağlam etiketi "Akademik personel" yazar;
#: ortak sözcük olmadığı için doğru satır eleniyordu. Bu tablo tahmin
#: yapmaz, yalnızca elle yazılmış birebir karşılıkları ekler.
_CONTEXT_ESANLAM = {
    "akademisyen": {"akademik", "personel"},
    "akademisyenler": {"akademik", "personel"},
    "hoca": {"akademik", "personel"},
    "hocalar": {"akademik", "personel"},
    "kadro": {"akademik", "personel"},
    "ogretim": {"akademik", "personel"},
    "öğretim": {"akademik", "personel"},
    "ogrenci": {"öğrenci", "ogrenci", "toplam"},
    "öğrenci": {"toplam"},
    "doluluk": {"doluluk", "oranı"},
    "kontenjan": {"kontenjan"},
}


def _context_tokens(value: str) -> set[str]:
    """Bağlam öğesi ile sorunun aynı metriğe işaret edip etmediğini ölçmek için
    küçük, deterministik bir sözcük kümesi üretir.

    Amaç semantik tahmin yapmak değil; yalnızca "toplam öğrenci sayısı" gibi
    açık eşleşmelerde backend bağlamını güvenli grounding olarak kabul etmektir.
    """
    import re as _re

    tokens = {
        token
        for token in _re.findall(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]+", (value or "").lower())
        if len(token) >= 3 and token not in _CONTEXT_STOPWORDS
    }
    return tokens


def _backend_context_for_question(
    db: Optional[Session],
    user_message: str,
    ui_scope: Optional[Dict[str, str]],
) -> Tuple[Optional[str], List[str]]:
    """Soruya doğrudan karşılık gelen backend ContextItem'larını modele ekler.

    KAPSAMLI SORULAR DA BAĞLAM ALIR
    -------------------------------
    Eskiden bu fonksiyon, arayüzde bir fakülte/bölüm/program seçiliyse
    HİÇ bağlam döndürmüyordu; dar kapsam tümüyle modelin doğru aracı
    seçmesine bırakılmıştı. Model aracı çağırmadığında ortada ne bağlam
    ne araç sonucu kalıyor ve "Bu bölümde kaç akademisyen var?" gibi
    cevabı hazır duran bir soru bile reddediliyordu.

    Artık bağlam SEÇİLİ KAPSAMLA üretilir. Kapsam yapısal kimliklerden
    (`scope.resolve`) çözülür; ad tahmini yapılmaz. Böylece dar kapsamda
    da üst kapsamın sayısı sızmaz: `build_context` kapsamı zaten
    süzgeçten geçirir.

    Context builder geniş bir konu bağlamı döndürebildiği için her gelen öğeyi
    grounding saymıyoruz. Yalnızca soru ile label/key arasında açık sözcük
    kesişimi bulunan öğeler modele verilir. Böylece "maaş kaç?" sorusu, yalnızca
    başka mali göstergeler geldi diye grounded kabul edilmez.
    """
    if db is None:
        return None, []

    scope = ui_scope or {}
    # Yapısal kimlikler router tarafından konur; ad alanları yalnızca
    # araçlar içindir ve kapsam çözümlemede KULLANILMAZ.
    try:
        from app.services.scope import resolve as _resolve_scope

        cozulen = _resolve_scope(
            db,
            faculty_id=scope.get("faculty_id"),
            department_id=scope.get("department_id"),
            academic_program_id=scope.get("academic_program_id"),
        )
    except Exception:  # noqa: BLE001
        cozulen = None

    try:
        prepared = context_builder.build_context(
            db, user_message, scope=cozulen,
            academic_year=scope.get("academic_year"))
    except Exception:  # noqa: BLE001
        logger.exception("Backend kurumsal baglami hazirlanamadi")
        return None, []

    items = list(getattr(prepared, "context_items", None) or [])
    if not items:
        return None, []

    question_tokens = _context_tokens(user_message)
    if not question_tokens:
        return None, []
    for token in list(question_tokens):
        question_tokens |= _CONTEXT_ESANLAM.get(token, set())

    relevant = []
    for item in items:
        key = str(getattr(item, "key", "") or "")
        label = str(getattr(item, "label", "") or "")
        value = str(getattr(item, "value", "") or "").strip()
        if not value:
            continue

        # Açık "veri yok" satırları grounding değildir.
        lowered_value = value.lower()
        if any(
            phrase in lowered_value
            for phrase in (
                "veri yok",
                "veri bulunamad",
                "bulunmuyor",
                "ulaşılamadı",
                "ulasilamadi",
                "none",
                "null",
            )
        ):
            continue

        item_tokens = _context_tokens(f"{key} {label}")
        overlap = question_tokens & item_tokens
        if not overlap:
            continue

        relevant.append(item)

    if not relevant:
        return None, []

    year = scope.get("academic_year")
    kapsam_adi = getattr(cozulen, "label", None) or "Üniversite geneli"
    lines = [
        "BACKEND KURUMSAL BAĞLAMI — bu bölümdeki gerçekleri kullanabilirsin.",
        f"Bu bağlam ŞU KAPSAMA aittir: {kapsam_adi}."
        + (f" Seçili akademik yıl: {year}." if year else ""),
        "Başka bir kapsamın değeriymiş gibi sunma.",
        "Bağlamda bulunmayan sayıyı üretme; gerekirse araç çağır.",
    ]
    sources: List[str] = []
    for item in relevant:
        source = str(getattr(item, "source_module", "") or "Kurumsal veri")
        label = str(getattr(item, "label", "") or getattr(item, "key", "Gösterge"))
        value = str(getattr(item, "value", "") or "")
        lines.append(f"- {label}: {value} [Kaynak: {source}]")
        if source not in sources:
            sources.append(source)

    return "\n".join(lines), sources


#: Model sustuğunda yapılacak ek deneme sayısı. İkiden fazlası hem
#: kullanıcıyı bekletir hem kotayı yakar; ölçüldü ki ikinci denemede
#: gelmeyen metin üçüncüde de gelmiyor.
EK_DENEME_SAYISI = 2

#: Zaman aşımı sonrası hızlı denemenin üst sınırı (saniye).
#:
#: Tam tur tavanı (120 sn) burada kullanılamaz: kullanıcı zaten bir kez
#: o kadar bekledi. Bu tur yalnızca "eldeki veriyle cümleyi yaz" işidir;
#: araç yok, bağlam sadeleştirilmiş, düşünme seviyesi düşük. 20 saniye
#: bu iş için fazlasıyla yeterli, yetmiyorsa zaten gelmeyecektir.
_HIZLI_RETRY_SANIYE = 20.0

_FINALIZASYON = (
    "Yukarıdaki araç sonuçlarını ve bağlamı kullanarak kullanıcının "
    "sorusunu ŞİMDİ doğrudan cevapla. Yeni araç çağırma. Türkçe, kısa ve "
    "sayısal yaz. Yalnızca final cevabı ver. Kanıtta geçmeyen hiçbir "
    "kurumsal kişi adı yazma. Grafik kodu ya da JSON yazma."
)

_SADELESTIRME = (
    "Aşağıdaki soruyu Türkçe, kısa ve doğrudan cevapla. Elindeki veriler "
    "varsa onları kullan; yoksa kendi bilginle genel bir cevap ver ve "
    "kurumsal veritabanından geldiğini İDDİA ETME. Kurumsal bir kişinin "
    "adını uydurma."
)


def _son_sans(provider, messages, soru: str, session, *, tur_kimligi: str,
              gecen: float, olcum: Dict[str, Any]) -> str:
    """Model metin üretemediyse iki ek deneme — ikisi de ARAÇSIZ.

    Neden araçsız: ilk turlarda model zaten araçları gördü. Metin
    üretememesinin en sık sebebi araç döngüsünde takılmasıdır; aynı
    araçları tekrar sunmak aynı döngüyü davet eder. Burada tek iş
    kalmıştır — cümleyi yazmak.

    Boş string dönerse çağıran taraf deterministik geri düşüşe iner.
    """
    if provider is None:
        return ""
    # Kota dolmuşsa ya da süre bittiyse yeni istek kullanıcıyı boşuna
    # bekletir; eldekiyle devam edilir.
    if olcum.get("rate_limited"):
        logger.info("[AI TURN %s] RETRY atlandı (kota)", tur_kimligi)
        return ""
    zaman_asimi = bool(olcum.get("timed_out"))
    if gecen >= MAX_USER_TURN_SECONDS - _EN_AZ_TUR_PAYI:
        logger.info("[AI TURN %s] RETRY atlandı (süre)", tur_kimligi)
        return ""

    ozet = _elde_ne_var(session, soru)

    # ZAMAN AŞIMI SONRASI: TEK VE HIZLI DENEME.
    # ------------------------------------------------------------------
    # Zaman aşımı da bir cevap şansı hak eder — ama ağır zincir baştan
    # çalıştırılmaz. Daha önce elde edilmiş araç/structured sonuçlar
    # KORUNUR (`ozet`), model yalnızca cümleyi yazar.
    #
    # Üç şey bilinçli olarak farklı:
    #   · TEK deneme (iki değil): model zaten yavaş olduğunu gösterdi.
    #   · SADELEŞTİRİLMİŞ bağlam: uzun konuşma geçmişi ilk turun
    #     yavaşlamasının en olası sebebi; onu taşımak aynı sonucu davet
    #     eder.
    #   · KISA tavan (`_HIZLI_RETRY_SANIYE`): kullanıcı bir kez
    #     bekledi; ikinci kez tam tur süresi beklemesi kabul edilemez.
    #
    # `reasoning_effort` zaten `low` (bkz. config.GEMINI_REASONING_EFFORT);
    # düşünme bütçesi bu turda da düşük kalır.
    hizli_istem = [
        {"role": "system", "content": _FINALIZASYON},
        {"role": "user",
         "content": (soru + (f"\n\nEldeki veriler:\n{ozet}"
                             if ozet else ""))},
    ]
    if zaman_asimi:
        denemeler = [("timeout_retry", hizli_istem)]
    else:
        denemeler = [
            ("finalization", list(messages) + [
                {"role": "system", "content": _FINALIZASYON}]),
            ("minimal", [
                {"role": "system", "content": _SADELESTIRME},
                {"role": "user",
                 "content": (soru + (f"\n\nEldeki veriler:\n{ozet}"
                                     if ozet else ""))}]),
        ][:EK_DENEME_SAYISI]

    for sira, (ad, gonderilecek) in enumerate(denemeler, 1):
        logger.info("[AI TURN %s] gemini_attempt=%d %s",
                    tur_kimligi, olcum["llm_rounds"] + sira, ad)
        try:
            _, metin, _ = _saglayici_cagir(
                provider, gonderilecek, None,
                tur_no=olcum["llm_rounds"] + sira, tur_kimligi=tur_kimligi,
                gecen=gecen,
                sinir_ustu=(_HIZLI_RETRY_SANIYE if zaman_asimi else None))
        except AssistantProviderError as exc:
            logger.warning("[AI TURN %s] RETRY %d (%s) başarısız: %s",
                           tur_kimligi, sira, ad, getattr(exc, "kind", "") or
                           exc.__class__.__name__)
            if getattr(exc, "kind", "") == "rate_limit":
                olcum["rate_limited"] = True
                break
            continue
        if (metin or "").strip():
            logger.info("[AI TURN %s] answer_mode=%s (gemini_attempt=%d)",
                        tur_kimligi,
                        "timeout_retry_gemini" if zaman_asimi
                        else "retry_gemini",
                        olcum["llm_rounds"] + sira)
            olcum["retries"] = olcum.get("retries", 0) + sira
            # Zaman aşımı bayrağı DÜŞÜRÜLÜR: model sonunda cevap verdi,
            # arayüzde "zaman aşımı" izlenimi bırakmak yanlış olurdu.
            olcum["timed_out"] = False
            return metin
        logger.info("[AI TURN %s] gemini_attempt=%d %s → metin yok",
                    tur_kimligi, olcum["llm_rounds"] + sira, ad)
    olcum["retries"] = olcum.get("retries", 0) + len(denemeler)
    return ""


# ===========================================================================
# SAĞLAYICI ARIZASI — TEK MERKEZİ POLİTİKA
# ===========================================================================
# Kota ya da hız sınırı, MODEL KATMANININ kullanılamaması demektir.
# Backend'in o ana kadar topladığı veri hâlâ geçerlidir ve kullanıcının
# hakkıdır. Cevap seçimi bu sırayla yapılır — soru türünden bağımsız,
# her soru için aynı:
#
#   1. Birincil Gemini cevabı
#   2. Yapılandırılmış ALTERNATİF BULUT Gemini modeli
#   3. Eldeki yapılandırılmış veriden deterministik cevap
#   4. Hiçbiri yoksa dürüst bir sağlayıcı mesajı
#
# YEREL MODEL HİÇBİR AŞAMADA YOKTUR. Ollama ve yerel çıkarım projeden
# kaldırıldı; kota bir ağ sınırıdır ve yerel bir modele düşmek, başka
# bir sistemin cevabını Gemini cevabı gibi sunmak olurdu.

#: Kota bildirimi — cevabın BAŞINA backend tarafından eklenir.
#: Gemini'ye yazdırılmaz: kota dolduğunda model zaten konuşamıyor
#: olabilir, o yüzden uyarı ancak deterministik eklenirse doğru olur.
#: Hiçbir yol kalmadığında gösterilen kontrollü mesaj.
#: Tek yerde tanımlıdır ki sağlayıcı arızası yönetimi onu TANIYIP
#: gerektiğinde kaldırabilsin — kota sebebi belliyken bu belirsiz
#: cümleyi göstermek kullanıcıyı yanıltır.
KONTROLLU_MESAJ = (
    "Bu isteğe şu anda güvenilir bir yanıt üretilemedi. "
    "Soruyu daha dar bir kapsamla tekrar deneyebilirsiniz.")

KOTA_NOTU_ALTERNATIF = (
    "Not: Birincil Gemini modelinin kullanım kotasına ulaşıldı. Yanıt "
    "alternatif Gemini modeli üzerinden oluşturuldu.")
KOTA_NOTU_VERIDEN = (
    "Not: Gemini kullanım kotasına ulaşıldı. Aşağıdaki yanıt doğrudan "
    "sistemdeki mevcut verilere dayanarak oluşturuldu.")
KOTA_NOTU_VERI_YOK = (
    "Not: Gemini kullanım kotasına ulaşıldı ve bu soru için sistemde "
    "kullanılabilir kurumsal veri bulunmuyor.")


def _alternatif_modeller() -> List[str]:
    """Yapılandırılmış alternatif BULUT modelleri (`.env`)."""
    from app.core.config import settings
    ham = (getattr(settings, "GEMINI_FALLBACK_MODELS", "") or "").strip()
    return [m.strip() for m in ham.split(",") if m.strip()]


def _alternatif_model_dene(provider, messages, soru: str, session, *,
                           tur_kimligi: str, gecen: float,
                           olcum: Dict[str, Any]) -> str:
    """Kota dolduğunda alternatif bulut modeliyle TEK deneme.

    Aynı modeli tekrar çağırmak anlamsızdır: günlük ya da model başına
    kota, bekleyerek çözülmez ve her deneme kullanıcıyı bekletir. Farklı
    bir modelin kotası ise ayrıdır — denemeye değer.

    Deneme ARAÇSIZ ve sadeleştirilmiş bağlamla yapılır; ağır araç
    zinciri baştan çalıştırılmaz. Eldeki araç sonuçları korunur ve
    isteme özet olarak eklenir.
    """
    adaylar = _alternatif_modeller()
    if not adaylar or provider is None:
        return ""
    if gecen >= MAX_USER_TURN_SECONDS - _EN_AZ_TUR_PAYI:
        logger.info("[AI TURN %s] alternatif model atlandı (süre)",
                    tur_kimligi)
        return ""

    ozet = _elde_ne_var(session, soru)
    istem = [
        {"role": "system", "content": _FINALIZASYON},
        {"role": "user",
         "content": soru + (f"\n\nEldeki veriler:\n{ozet}" if ozet else "")},
    ]
    eski_model = getattr(provider, "model", None)
    for ad in adaylar[:2]:
        logger.info("[AI TURN %s] provider=fallback_gemini model=%s",
                    tur_kimligi, ad)
        try:
            provider.model = ad
            _, metin, _ = _saglayici_cagir(
                provider, istem, None, tur_no=olcum["llm_rounds"] + 1,
                tur_kimligi=tur_kimligi, gecen=gecen,
                sinir_ustu=_HIZLI_RETRY_SANIYE)
        except AssistantProviderError as exc:
            logger.info("[AI TURN %s] provider_result=%s model=%s",
                        tur_kimligi, getattr(exc, "kind", "") or "error", ad)
            continue
        finally:
            if eski_model is not None:
                provider.model = eski_model
        if (metin or "").strip():
            logger.info("[AI TURN %s] provider_result=success "
                        "answer_mode=fallback_gemini", tur_kimligi)
            olcum["alternatif_model"] = ad
            return metin
    return ""


def _elde_ne_var(session, soru: str = "") -> str:
    """Başarılı araç sonuçlarından DETERMİNİSTİK ÖZET — model çağrılmadan.

    Modelin yorum turu zaman aşımına uğradığında devreye girer.
    Önceki sürüm ham satır döküyordu ("ilk 5 kayıt"); ölçüldü ki 67
    satırlık gerçek veri kullanıcıya beş satırlık liste olarak
    yansıyordu ve karar üretmiyordu. Artık aynı veriden kayıt/kurum
    sayısı, en düşük–en yüksek, ortalama ve medyan hesaplanır; iki
    karşılaştırılabilir küme varsa aradaki fark da verilir.

    Hesap kuralları `veri_ozeti` modülünde: anlamı bilinmeyen alanda
    aritmetik yapılmaz, oranların ortalaması alınmaz.
    """
    if session is None:
        return ""
    # ÇOK METRİKLİ KANIT ZATEN DETERMİNİSTİK BİR CEVAPTIR.
    # Backend onu satırlardan değil, hesaplanmış sayılardan kurdu;
    # yeniden özetlemek bilgi kaybı olurdu. Sağlayıcı sustuğunda ya da
    # kota dolduğunda kullanıcının göreceği metin budur.
    for kayit in session.records:
        if kayit.name == coklu_metrik.ARAC_ADI and kayit.success:
            if (kayit.content or "").strip():
                return kayit.content
    kumeler = []
    for kayit in session.records:
        if not kayit.success or kayit.output is None:
            continue
        try:
            veri = kayit.output.model_dump(mode="json")
        except Exception:  # noqa: BLE001
            continue
        satirlar = veri.get("rows") if isinstance(veri.get("rows"), list) else None
        baslik = next((str(veri[a]) for a in ("title", "summary", "label",
                                              "source", "metric")
                       if veri.get(a)), kayit.name)
        if satirlar and all(isinstance(r, dict) for r in satirlar):
            kumeler.append((baslik, satirlar))
        else:
            sayilar = ", ".join(
                f"{k}={v}" for k, v in veri.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool))
            if sayilar:
                kumeler.append((baslik, [dict(_tekil=1, **{
                    k: v for k, v in veri.items()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)})]))

    if not kumeler:
        return ""

    # ÖNCE NİYETE UYGUN CEVAP, SONRA İSTATİSTİK.
    # ------------------------------------------------------------------
    # Ölçülen sorun: model susunca kullanıcı "5 kayıt · ortalama 471,9 ·
    # medyan 463,3" görüyordu. Bu bir veri kümesi istatistiğidir ve
    # sorudan bağımsızdır — "hangi üniversiteler?" diye sorana medyan
    # söylemek cevap değildir, üstelik gerçek satırlar elde dururken.
    #
    # `grounded_cevap` aynı satırları kullanır ama sorunun NİYETİNE göre
    # biçimlendirir: sıralamaya sıralı liste, tekil değere tek sayı,
    # eğilime yıl-değer dizisi. Hiçbir sayı hesaplanmaz, hepsi araç
    # sonucundan gelir.
    #
    # İstatistik özeti kalkmaz: kullanıcı gerçekten dağılım sorduysa ya
    # da niyete uygun bir biçim çıkarılamadıysa yine o kullanılır.
    if soru:
        try:
            niyetli = grounded_cevap.uret(soru, kumeler)
            if niyetli:
                return niyetli
        except Exception:  # noqa: BLE001
            logger.debug("niyetli cevap üretilemedi", exc_info=True)

    parcalar = [veri_ozeti.veri_kumesi_ozeti(ad, satirlar)
                for ad, satirlar in kumeler[:_OZET_ARAC]]
    kiyas = veri_ozeti.karsilastirma(kumeler[:2])
    if kiyas:
        parcalar.append(kiyas)
    return "\n\n".join(p for p in parcalar if p)

#: Son turda modele verilen görev. Kısa tutuluyor: bu turda amaç yeni
#: veri aramak değil, ELDEKİ sonuçtan karar cümlesi kurmak.
#: SON TUR NOTU — KISA TUTULUR.
#:
#: Uzun bir görev listesi, modelin "önce planlayayım" moduna girmesine
#: yol açıyor; ölçülen sonuç, cevabın yazılmaya hiç başlanmaması.
#: Not tek amaca indirildi: ŞİMDİ YAZ. Biçim beklentisi iki satırda
#: kalır, çünkü sistem yönergesi zaten üslubu tarif ediyor.
_SON_TUR_GOREVI = (
    "Elindeki verilerle ŞİMDİ final cevabı yaz.\n"
    "Yeni araç çağırma. Yeni analiz turu başlatma. İç muhakemeyi uzatma.\n"
    "Türkçe, kısa ve SAYISAL yaz; grafik anlamlıysa render_chart kullan.\n"
    "Cevabı hemen tamamla."
)

#: İkinci tur notu: veri yeterliyse ÜÇÜNCÜ tura sürüklenme.
#: Fazladan bir keşif turu hem süreyi hem kotayı harcıyor, üstelik
#: cevabın kalitesini artırmıyordu — gerekli sayılar zaten elde.
_ERKEN_FINAL_NOTU = (
    "Elindeki araç sonuçları kullanıcının sorusunu cevaplamaya YETİYORSA "
    "şimdi final cevabı yaz; yeni araç çağırma. Yalnızca gerçekten eksik "
    "bir veri varsa bir araç daha çağır."
)

#: Sorunun eğilim isteyip istemediğini anlayan kalıp. Yeni bir niyet
#: ayrıştırıcı DEĞİL: yalnızca ek sistem notunun ne zaman ekleneceğini
#: belirler; yanlış eşleşse bile kural zararsızdır.
_EGILIM_SORUSU = re.compile(
    r"(trend|eğilim|egilim|değişim|degisim|seyir|yıllara|yillara|"
    r"yıl bazında|artış|artis|azalış|azalis|gelişim|gelisim)", re.I)

#: Eğilim (trend) semantiği. Tek akademik yıl bir eğilim göstermez;
#: model bunu bilmezse "2025-2026 trendi" gibi bir soruda tek yıllık
#: veriyle eğilim yorumu uydurur.
_EGILIM_KURALI = (
    "EĞİLİM = EN AZ İKİ DÖNEM. Kullanıcı 'trend', 'eğilim', 'değişim', "
    "'seyir', 'yıllara göre' gibi bir şey sorduysa tek bir akademik yıl "
    "yeterli DEĞİLDİR: veri çağrısını çok yıllı yap (sistemde 2020-2021 – "
    "2026-2027 arası mevcuttur). Kullanıcı ayrıca belirli bir yıl da "
    "söylediyse o yılı 'son durum', önceki yılları 'eğilim' için kullan. "
    "Tek yıllık veriyle eğilim yorumu yazma."
)


def _tur_timeout(gecen: float) -> float:
    """Bu model çağrısının bekleyebileceği en uzun süre.

    Turun toplam sınırı her zaman üstündür: 45 saniyenin 38'i harcanmışsa
    çağrı 25 değil 7 saniye bekler. Böylece "üç turu tamamlayayım" diye
    toplam süre aşılamaz. Alt sınır 1 saniyedir; sıfır/negatif timeout
    httpx'te anlamsızdır ve çağrı zaten yapılmayacaktır.
    """
    # Güvenlik marjı: çağrı tam deadline'da bitmemeli. Yanıtın
    # ayrıştırılması, özetin kurulması ve HTTP'ye yazılması da zaman
    # alır; marj bırakılmazsa model tam zamanında dönse bile tur
    # sınırı aşılır ve kullanıcı yine boş kalır.
    kalan = MAX_USER_TURN_SECONDS - gecen - _TUR_SONU_MARJI
    return max(1.0, min(GEMINI_ROUND_TIMEOUT_SECONDS, kalan))


def _boyut(mesajlar, semalar) -> tuple:
    """Bağlam boyutunu ÖLÇER — kırpmaz.

    Bu turda bilerek yalnızca ölçüm var. Bir sonraki gerçek soruda
    "1. tur hızlı, 2. tur zaman aşımı" görülürse, 2. turun bağlamının
    gerçekten büyüyüp büyümediğini tahminle değil bu sayılarla
    tartışabiliriz.
    """
    mesaj_k = sum(len(str(m.get("content") or "")) for m in mesajlar)
    sema_k = len(json.dumps(semalar, ensure_ascii=False)) if semalar else 0
    arac_k = sum(len(str(m.get("content") or "")) for m in mesajlar
                 if m.get("role") == "tool")
    return mesaj_k, sema_k, arac_k


def _saglayici_cagir(provider, messages, offered_tools, *, tur_no: int,
                     tur_kimligi: str, gecen: float,
                     sinir_ustu: Optional[float] = None):
    """Tek bir model çağrısı: sert timeout + telemetri.

    Sağlayıcının modeli, istemi, üretim ayarları ve yanıt ayrıştırması
    DEĞİŞMEZ. Burada yalnızca `timeout_seconds` alanı bu çağrı süresince
    daraltılır; `_istemci()` her istekte bu alanı okuduğu için tek
    dokunuş yeterlidir ve çağrı bitince eski değer geri konur.

    `sinir_ustu`: bu çağrıya özel, DAHA KISA bir tavan. Zaman aşımı
    sonrası hızlı deneme için var — kullanıcı bir kez beklemişken ikinci
    kez tam tur süresi beklemesin.
    """
    sinir = _tur_timeout(gecen)
    if sinir_ustu is not None:
        sinir = max(1.0, min(sinir, float(sinir_ustu)))
    mesaj_k, sema_k, arac_k = _boyut(messages, offered_tools)
    logger.info(
        "[AI TURN %s] ROUND %d START tools_offered=%d messages=%d "
        "prompt_chars=%d tool_schema_chars=%d tool_result_chars=%d "
        "elapsed_turn=%.1f remaining_deadline=%.1f round_timeout=%.1f",
        tur_kimligi, tur_no, len(offered_tools or []), len(messages),
        mesaj_k, sema_k, arac_k, gecen,
        max(0.0, MAX_USER_TURN_SECONDS - gecen), sinir)

    eski_sinir = getattr(provider, "timeout_seconds", None)
    basladi = time.monotonic()
    try:
        if eski_sinir is not None:
            provider.timeout_seconds = sinir
        sonuc = provider.chat_with_tools(messages, offered_tools)
    except AssistantProviderError as exc:
        sure = time.monotonic() - basladi
        tur = getattr(exc, "kind", "") or "error"
        etiket = {"timeout": "TIMEOUT", "rate_limit": "RATE_LIMIT"}.get(
            tur, "ERROR")
        logger.warning(
            "[AI TURN %s] ROUND %d %s duration=%.1f remaining_deadline=%.1f "
            "type=%s", tur_kimligi, tur_no, etiket, sure,
            max(0.0, MAX_USER_TURN_SECONDS - (gecen + sure)),
            exc.__class__.__name__)
        raise
    finally:
        if eski_sinir is not None:
            provider.timeout_seconds = eski_sinir

    cagrilar, gorunen, _dusunme = sonuc
    sure = time.monotonic() - basladi
    logger.info(
        "[AI TURN %s] ROUND %d END duration=%.1f finish_type=%s "
        "requested_tools=%s", tur_kimligi, tur_no, sure,
        "tool_call" if cagrilar else "text",
        ",".join(c.get("name", "?") for c in cagrilar) or "-")
    return sonuc


def answer(
    message: str,
    conversation_id: Optional[str] = None,
    db: Optional[Session] = None,
    permissions: Optional[List[str]] = None,
    ui_scope: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Araç çağrı döngüsünü yürütür ve son cevabı üretir.

    KURUMSAL SORU POLİTİKASI
    ------------------------
    Soru kurum verisi gerektiriyorsa cevap ancak backend tarafından hazırlanmış,
    soruyla doğrudan eşleşen kurumsal bağlama VEYA başarılı araç sonucuna
    dayanıyorsa kullanıcıya verilir. İkisi de yoksa model metni reddedilir.
    """
    conversation, messages = _prepare(message, conversation_id)
    user_content = messages[-1]["content"]
    institutional = query_policy.is_institutional_query(user_content)

    # Context builder'ın doğrudan desteklediği, soruyla açıkça eşleşen gerçekler
    # de araç sonucu kadar geçerli grounding sayılır. Sistem mesajı kullanıcının
    # sorusundan hemen önce eklenir.
    backend_context_text, backend_context_sources = _backend_context_for_question(
        db, user_content, ui_scope
    )
    context_data_available = bool(backend_context_text)
    # Katalog yolunun durumu. Aşağıda doldurulur; `return` yerine bağlam
    # olarak kullanılır.
    catalog_dataset: Optional[Dict[str, Any]] = None
    catalog_available = False
    catalog_fallback: Optional[str] = None
    catalog_sources: List[str] = []
    if backend_context_text:
        messages.insert(
            len(messages) - 1,
            {"role": "system", "content": backend_context_text},
        )

    # Veri oturumu yoksa kurumsal soru için MODEL HİÇ ÇAĞRILMAZ. Modelden
    # "genel bilgi" cevabı istemek, kullanıcıya kurum verisi gibi görünen bir
    # metin üretme riskini boşuna alır.
    if institutional and db is None:
        logger.warning("Kurumsal soru veri oturumu olmadan geldi; model cagrilmadi.")
        _store.append(conversation, "user", user_content)
        _store.append(conversation, "assistant", query_policy.NO_DATABASE_MESSAGE)
        provider = get_provider()
        return {
            "conversation_id": conversation,
            "answer": query_policy.NO_DATABASE_MESSAGE,
            "provider": provider.name,
            "model": provider.model,
            "used_tools": [],
            "model_charts": [],
            "data_sources": [],
            "academic_year": None,
            "scope": {},
            "data_source": query_policy.SOURCE_UNAVAILABLE,
            "structured_result": None,
            "ui_spec": None,
        }

    provider = get_provider()

    # ------------------------------------------------------------------
    # GENERIC READ-ONLY DATA CATALOG
    # ------------------------------------------------------------------
    # Retrieve first.  The same structured rows ground the prose below and
    # are later passed to chart_builder by the router.  Missing legacy intent
    # code is therefore no longer treated as missing institutional data.
    if db is not None:
        catalog_result = data_catalog.query_question(
            db,
            user_content,
            ui_scope=ui_scope,
            previous_dataset=_catalog_datasets.get(conversation),
        )
        # KATALOG ARTIK CEVAP DEĞİL, BAĞLAMDIR.
        # ------------------------------------------------------------------
        # Eskiden burada `return` vardı: katalog soruyu tanıdıysa fonksiyon
        # oracıkta biterdi. Sonuçları ölçtük ve şunu gördük:
        #
        #   * Araç döngüsü, muhakeme ve grafik üretimi HİÇ çalışmıyordu;
        #     `ui_spec` sabit `None` dönüyordu.
        #   * Modelin tek işi tek bir veri kümesini cümleye çevirmekti —
        #     Sağlayıcı erişilemezken bile cevap gelmesi bunu kanıtladı.
        #   * Katalog 32 metrik tanıyor ve eşleşme SORU KALIBINA bağlı:
        #     "Toplam derslik sayımız kaç?" tutuyor, "Kaç dersliğimiz var?"
        #     tutmuyordu. Aynı veri, iki cümlede iki farklı sonuç.
        #
        # Yeni davranış: katalog veriyi GETİRİR ve modele bağlam olarak
        # verilir; akış normal ajan döngüsüyle devam eder. Model bağlamı
        # yeterli bulursa oradan cevaplar (ek araç çağırmaz), yetersiz
        # bulursa 19 araçtan uygun olanı çağırır. Karar artık soru
        # kalıbında değil modelde.
        #
        # GÜVENLİK: katalogun deterministik cevabı ATILMAZ, yedek olarak
        # saklanır. Ajan yolu boş dönerse o cevap gösterilir — yani en
        # kötü ihtimalle bugünkü davranışa düşeriz, altına değil.
        if catalog_result.get("handled"):
            catalog_dataset = catalog_result["dataset"]
            catalog_available = bool(catalog_result.get("available"))
            if catalog_available:
                _remember_catalog_dataset(conversation, catalog_dataset)
                catalog_fallback = data_catalog.render_answer(
                    catalog_dataset, user_content
                )
                catalog_sources = list(catalog_dataset.get("data_sources") or [])
                # Sayısal gerçekler modele AYNEN verilir; model bunları
                # yeniden hesaplamaz, yalnızca yorumlar ve birleştirir.
                messages.insert(
                    len(messages) - 1,
                    {
                        "role": "system",
                        "content": (
                            "KURUMSAL VERİ KATALOĞU — soruyla eşleşen gerçek "
                            "değerler aşağıdadır. Bu sayıları AYNEN kullan, "
                            "yeniden hesaplama, yuvarlama. Soruyu tam "
                            "cevaplamak için ek veri gerekiyorsa araçları "
                            "çağır.\n"
                            + json.dumps(
                                _catalog_grounding(catalog_dataset),
                                ensure_ascii=False, default=str,
                            )
                        ),
                    },
                )
            else:
                # Katalog soruyu tanıdı ama değeri yok. Bu bir CEVAP DEĞİL,
                # bir ipucudur: model bunu bilerek başka bir araç deneyebilir.
                messages.insert(
                    len(messages) - 1,
                    {
                        "role": "system",
                        "content": (
                            "KATALOG NOTU: " + (
                                catalog_result.get("answer")
                                or data_catalog.UNAVAILABLE_MESSAGE
                            ) + " Başka bir araçla deneyebilirsin."
                        ),
                    },
                )

    session: Optional[ToolSession] = None
    tool_schemas: Optional[List[Dict]] = None
    if db is not None:
        session = ToolSession(
            db=db, permissions=permissions, registry=registry,
            # Arayüzdeki birim seçimi araçlara VARSAYILAN kapsam olur.
            ui_scope=ui_scope,
            # Kaynak seçimi sorudan çıkarılan plana dayanır; keşif aracı
            # sorunun tamamını görmeli (bkz. tool_runner.user_question).
            user_question=message,
        )
        tool_schemas = registry.schemas(permissions)
        # TOKEN BÜTÇESİ — 19 ARACIN HEPSİ GÖNDERİLMEZ.
        # --------------------------------------------------------------
        # Şemaların toplamı 5.078 token; sistem yönergesiyle birlikte
        # sabit yük 7.404. Sağlayıcının dakikalık bütçesi
        # 8.000 olduğu için her istek HTTP 413 ile geri dönüyordu:
        # kullanıcı daha soruyu yazmadan bütçe doluyordu.
        #
        # Süzgeç GENİŞ tutulur ve fail-open çalışır: eşleşme bulunmazsa
        # çekirdek araçlar gider, her şey elenirse tam liste geri döner.
        # Yanlış aracı elemek, tasarruftan çok daha pahalı bir hatadır.
        tool_schemas = tool_selection.suz(tool_schemas, user_content)

    # ------------------------------------------------------------------
    # ZORUNLU SENARYO ARACI — karar modele bırakılmaz.
    #
    # Canlı testte model "maaşlara %2 zam yapılırsa" sorusuna mevcut bütçeyi
    # döndüren aracı çağırdı; o araç zammın etkisini hesaplamaz. Araç seçimi
    # bir muhakeme işi değil yönlendirme işidir: backend niyeti belirler,
    # parametreleri metinden çıkarır ve aracı KENDİSİ çalıştırır. Model
    # yalnızca sonucu yorumlar.
    # ------------------------------------------------------------------
    intent = query_policy.classify(user_content)
    forced_tool: Optional[str] = None
    composed: Optional[response_composer.ComposedResponse] = None

    # Kullanıcı adını verdiği bir birim sistemde yoksa MODELE HİÇ SORULMAZ.
    # Aksi halde model soruyu alakasız bir araçla cevaplayabiliyor ve
    # başarılı bir araç çağrısı olduğu için sistem bunu kabul ediyordu.
    if session is not None and intent.institutional:
        missing_unit = entity_resolver.unresolved_unit_in_text(db, user_content)
        if missing_unit:
            logger.info("Bulunamayan birim adi: %s", missing_unit)
            message_text = (
                f"'{missing_unit}' adında bir program, bölüm veya fakülte "
                f"sistemde bulunamadı. Lütfen adı kontrol edip yeniden sorun."
            )
            _store.append(conversation, "user", user_content)
            _store.append(conversation, "assistant", message_text)
            return {
                "conversation_id": conversation,
                "answer": message_text,
                "provider": provider.name,
                "model": provider.model,
                "used_tools": [],
            "model_charts": [],
                "data_sources": [],
                "academic_year": None,
                "scope": {},
                "data_source": query_policy.SOURCE_UNAVAILABLE,
                "structured_result": None,
                "ui_spec": None,
            }

    # Program özeti zorunluluğu, cümlede GERÇEKTEN bir program adı geçmesine
    # bağlıdır. "Mekânların doluluk oranı ne kadar?" bir program sorusu
    # değildir; zorunlu kılınırsa model hiç cevaplayamaz.
    if (
        session is not None
        and intent.required_tool == "get_program_summary"
        and entity_resolver.find_in_text(db, "program", user_content) is None
    ):
        intent.required_tool = None

    if session is not None and intent.required_tool:
        forced_tool = intent.required_tool
        arguments = _build_forced_arguments(
            db, intent, user_content,
            (ui_scope or {}).get("academic_year"))
        if arguments is not None:
            record = session.run(forced_tool, arguments)
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": forced_tool, "arguments": arguments}}
                    ],
                }
            )
            messages.append(
                {"role": "tool", "name": record.name, "content": record.content}
            )
            if record.success and response_composer.supports(forced_tool):
                # ZORUNLU GERÇEKLER burada üretilir. Model bir metriği
                # atlarsa cevap eksik kalmasın diye bu bölüm backend
                # tarafından yazılır ve final cevaba mutlaka eklenir.
                try:
                    composed = response_composer.compose(forced_tool, record.output)
                except response_composer.MissingMetricError as exc:
                    logger.error("Senaryo sonucu eksik uretildi: %s", exc.missing)
                    _store.append(conversation, "user", user_content)
                    _store.append(conversation, "assistant", MISSING_METRIC_MESSAGE)
                    return {
                        "conversation_id": conversation,
                        "answer": MISSING_METRIC_MESSAGE,
                        "provider": provider.name,
                        "model": provider.model,
                        "used_tools": session.used_tools(),
                        "model_charts": [],
                        "data_sources": session.data_sources(),
                        "academic_year": session.academic_year(),
                        "scope": session.scope(),
                        "data_source": query_policy.SOURCE_UNAVAILABLE,
                        "structured_result": None,
                        "ui_spec": None,
                    }

                messages.append(
                    {
                        "role": "system",
                        "content": (
                            response_composer.COMPOSER_INSTRUCTION
                            + "\n\n"
                            + composed.facts_markdown
                        ),
                    }
                )
                tool_schemas = None
            elif record.success:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Senaryo sonucu yukarıda hazır. Yeni araç çağırma; "
                            "bu sonucu kullanıcıya Türkçe olarak yorumla. "
                            "Kullandığın akademik yılı ve kapsamı belirt."
                        ),
                    }
                )
                tool_schemas = None
        else:
            # Parametreler metinden çıkarılamadı: modele YALNIZCA gerekli araç
            # sunulur, başka araç seçemez.
            logger.info("Zorunlu arac parametreleri cikarilamadi: %s", forced_tool)
            tool_schemas = [
                schema
                for schema in (tool_schemas or [])
                if schema["function"]["name"] == forced_tool
            ]
            messages.append(
                {
                    "role": "system",
                    "content": query_policy.REQUIRED_TOOL_INSTRUCTION.format(
                        tool=forced_tool
                    ),
                }
            )

    started = time.monotonic()
    steps = 0
    visible = ""
    # Kurumsal soruda modele araçsız cevap için verilen ikinci şans.
    forced_retry_used = False
    # Sağlayıcıya bu soru için şimdiye kadar gönderilen token toplamı.
    harcanan_token = 0.0
    #: Bu turda çalıştırılan VERİ araçlarının sayısı (grafik hariç).
    veri_cagrisi = 0
    #: Hafif ölçüm — gerçek istek yapmadan bütçe davranışını görebilmek
    #: için. Kullanıcıya gösterilmez, yalnızca günlüğe yazılır.
    olcum = {"llm_rounds": 0, "tool_calls": 0, "data_tool_calls": 0,
             "cache_hits": 0, "tools": [], "budget_exhausted": False,
             "finalization_forced": False, "rate_limited": False,
             "timed_out": False}
    #: Günlükte turları birbirinden ayırmak için kısa kimlik.
    tur_kimligi = uuid.uuid4().hex[:8]

    # AI İZİ — TEK SATIRDA OKUNABİLİR TEŞHİS.
    # ------------------------------------------------------------------
    # Bir soru beklenmedik cevap verdiğinde sebebi aramak, üç ayrı log
    # satırını birleştirmeyi gerektiriyordu. Burada turun BAŞINDA
    # sorudan çıkarılan plan yazılır; sonda hangi kaynakların
    # kullanıldığı ve cevabın nereden geldiği. Hassas veri ya da anahtar
    # yazılmaz — yalnızca niyet, metrik adı, kaynak adı ve satır sayısı.
    _kanit = None
    try:
        _rag_t0 = time.perf_counter()
        _plan = veri_ailesi.plan_cikar(message)
        logger.info("[AI TURN %s] PLAN %s", tur_kimligi, _plan.ozet())
        _adaylar = [a for a, _ in veri_ailesi.aday_kaynaklar(_plan)][:4]
        if _adaylar:
            logger.info("[AI TURN %s] CANDIDATES %s rag_ms=%.1f",
                        tur_kimligi, ",".join(_adaylar),
                        (time.perf_counter() - _rag_t0) * 1000)
        elif _plan.metrik_bilinmiyor:
            # METRİK BİLİNMİYOR ARTIK DURDURUCU DEĞİL.
            # ==============================================================
            # ÖNCEKİ DAVRANIŞ: kaynak seçilmiyor, kullanıcıya "Hangi
            # ölçüyü karşılaştırmamı istersiniz?" diye tek cümlelik bir
            # netleştirme sorusu dönüyordu. Gerekçe savunulabilirdi —
            # rastgele bir ölçü seçip analiz etmek, kendinden emin
            # görünen yanlış bir cevap üretir.
            #
            # Ama sorun ölçüyü BİLMEMEK değil, TEK ölçü seçme
            # zorunluluğuydu. Kullanıcı "hangi mühendislikler yükseldi"
            # diye sorduğunda tek bir sayı değil gidişat soruyor; taban
            # puanı yükselirken doluluğun düşmesi bir çelişki değil,
            # cevabın kendisidir.
            #
            # YENİ DAVRANIŞ: bu kapsam ve zaman için ANLAMLI olan
            # ölçülerin hepsi bulunur, gerçekten verisi olanlar
            # backend'de AYRI AYRI hesaplanır ve tek yapılandırılmış
            # kanıt olarak modele verilir. Rastgele metrik riski ortadan
            # kalkar çünkü seçim YAPILMAZ; her satırda hangi ölçünün
            # anlatıldığı yazılıdır.
            #
            # Kapsam dar: yalnızca metrik belirsizliği. Entity
            # çözümleme, kaynak seçimi, grounding, sağlayıcı politikası
            # ve model-only davranışı DEĞİŞMEZ.
            _kanit = coklu_metrik.kanit_uret(_plan)
            if _kanit.var:
                logger.info(
                    "[AI TURN %s] MULTI_METRIC metric=UNKNOWN %s "
                    "rag_ms=%.1f answer_mode=multi_metric",
                    tur_kimligi, coklu_metrik.iz(_kanit),
                    (time.perf_counter() - _rag_t0) * 1000)
                _adaylar = _kanit.kaynaklar()[:4]
                _coklu = coklu_metrik.metin(_kanit)
                # KANIT ARAÇ SONUCU GİBİ KAYDEDİLİR.
                # Grounding, `data_sources`, deterministik özet ve kota
                # politikası hep `session.records` üzerinden çalışıyor.
                # Kanıtı oraya koymak, o sistemlerin hiçbirine
                # dokunmadan çok metrikli cevabın da "gerçekten veriye
                # dayanan" sayılmasını sağlar.
                if session is not None:
                    session.records.append(ToolCallRecord(
                        name=coklu_metrik.ARAC_ADI,
                        arguments={"metrics": [m.metrik
                                               for m in _kanit.metrikler],
                                   "sources": _kanit.kaynaklar()},
                        success=True, content=_coklu,
                        data_source=coklu_metrik.VERI_KAYNAGI))
                messages.append({"role": "system", "content": _coklu})
            else:
                # HİÇBİR ANLAMLI ÖLÇÜDE VERİ YOK.
                # `data_not_found` ANCAK burada geçerlidir. Tek bir
                # metriğin bulunamaması bu duruma girmez; model kendi
                # bilgisiyle cevap vermeye devam eder (model-only).
                logger.info(
                    "[AI TURN %s] DATA_NOT_FOUND metric=UNKNOWN "
                    "skipped=%d rag_ms=%.1f", tur_kimligi,
                    len(_kanit.atlanan),
                    (time.perf_counter() - _rag_t0) * 1000)
    except Exception:  # noqa: BLE001
        logger.debug("[AI TURN %s] plan izi çıkarılamadı", tur_kimligi,
                     exc_info=True)
        _plan, _adaylar = None, []

    # AŞAMA 1'İ BACKEND YAPAR — MODEL KÖR TAHMİN ETMEZ.
    # ------------------------------------------------------------------
    # Model `query_canonical_data` aracını görüyor ama hangi kaynak adını
    # yazacağını bilmiyor: 60 kaynak var ve adları İngilizce. Kaynak
    # adlarını öğrenmesinin tek yolu `explore_data_sources` çağırmaktı,
    # o da her soruda sunulmuyor (bilinçli: pahalı bir keşif turu).
    #
    # ÖLÇÜLEN SONUÇ: eğilim ve çok metrikli sorularda model HİÇ araç
    # çağırmıyor, merkezî veritabanı hiç okunmuyordu.
    #
    # Çözüm, keşfi zorunlu kılmak değil — backend zaten planı çıkardı,
    # aday kaynakları da biliyor. Bunlar tek satırlık bir not olarak
    # modele verilir. Model hâlâ SEÇER ve başka kaynak da isteyebilir;
    # yalnızca kör tahmin etmesi gerekmez. Not KISA tutulur: kaynak
    # adları ve kapsamları, şema dökümü değil.
    # Bu turun istem bütçesi — plan ve grafik niyeti belli olduktan sonra.
    _tur_token_tavani = _tur_butcesi(_plan, grafik_uret.istendi_mi(message))

    if _adaylar:
        _oneri = []
        _prof = veri_ailesi.profiller()
        for _ad in _adaylar[:3]:
            _p = _prof.get(_ad)
            _yil = (f" ({_p.yil_araligi[0]}-{_p.yil_araligi[1]})"
                    if _p and _p.yil_araligi else "")
            _oneri.append(f"{_ad}{_yil}")
        messages.append({
            "role": "system",
            "content": (
                "Bu soru için uygun veri kaynakları (query_canonical_data "
                "ile sorgula): " + ", ".join(_oneri)
                + ". Başka kaynak gerekiyorsa explore_data_sources ile ara."
            )})

    while True:
        elapsed = time.monotonic() - started
        # Araç şemaları da bütçeye dahildir: onları göndermemek tek
        # başına birkaç bin token kazandırır ve bir sonraki turu
        # kurtarabilir.
        tahmin = _tahmini_token(messages, tool_schemas)
        token_doldu = harcanan_token >= _tur_token_tavani
        if token_doldu:
            logger.info(
                "Token butcesi doldu (kumulatif ~%.0f); araclar kapatildi.",
                harcanan_token,
            )
        # SON TUR ARAÇSIZ ÇALIŞIR.
        # `steps` o ana kadar yapılan araç turlarını sayar; bir sonraki
        # sağlayıcı çağrısı `steps + 1`inci turdur. Son tura gelindiğinde
        # araç şeması GÖNDERİLMEZ, böylece model yeni araç isteyemez ve
        # eldeki sonuçlarla cevabı yazmak zorunda kalır.
        son_tur = (steps + 1) >= MAX_LLM_ROUNDS_PER_USER_MESSAGE
        veri_butcesi_doldu = veri_cagrisi >= MAX_DATA_TOOL_CALLS
        out_of_budget = (son_tur
                         or veri_butcesi_doldu
                         or elapsed >= MAX_TOOL_WALL_SECONDS
                         or token_doldu)
        offered_tools = None if (out_of_budget or not tool_schemas) else tool_schemas
        # Bu turun maliyeti, bir sonraki turun kararı için biriktirilir.
        harcanan_token += _tahmini_token(messages, offered_tools)

        # SON TURDA GÖREV NET SÖYLENİR.
        # Ölçülen davranış: araç sonuçları geldikten sonra model ikinci
        # turda yeniden keşfe çıkıyor, uzun bir metin kurmaya çalışıyor
        # ve 25 saniyeye sığmıyordu. Burada ne yapması gerektiği tek
        # cümleyle sınırlanır; sistem yönergesinin çekirdeği DEĞİŞMEZ,
        # yalnızca bu tura özel bir görev notu eklenir.
        # SON TURDA TEK VE NET GÖREV.
        # Eskiden burada iki ayrı not vardı ("araç sınırına ulaşıldı" ve
        # görev sırası); ikisi örtüşüyor, model için gürültü üretiyordu.
        # Tek mesajda toplandı: bu son tur, yeni araç yok, cevabı yaz.
        if (son_tur or out_of_budget) and session is not None and steps > 0:
            messages.append(
                {
                    "role": "system",
                    # Ek cümle EKLENMEZ. Her ek satır, modele "önce
                    # durumu değerlendir" sinyali veriyor; asıl istenen
                    # cevabın yazılmaya başlanması.
                    "content": _SON_TUR_GOREVI,
                }
            )

        # SÜRE DOLDUYSA YENİ İSTEK YOK.
        # Kalan süre yeni bir çağrıyı anlamlı kılmayacak kadar azsa
        # (veya hiç kalmadıysa) modele gitmek yalnızca kullanıcıyı daha
        # fazla bekletir. Elde ne varsa onunla bitirilir.
        if elapsed >= MAX_USER_TURN_SECONDS - _EN_AZ_TUR_PAYI and steps > 0:
            olcum["timed_out"] = True
            logger.warning(
                "[AI TURN %s] DEADLINE elapsed=%.1f limit=%.1f — yeni model "
                "cagrisi yapilmadi", tur_kimligi, elapsed, MAX_USER_TURN_SECONDS)
            tool_calls, visible, thinking = [], "", ""
            break

        # İKİNCİ TUR: veri geldiyse üçüncü tura sürüklenme.
        if (not son_tur and steps == 1 and session is not None
                and session.any_success()):
            messages.append({"role": "system", "content": _ERKEN_FINAL_NOTU})

        olcum["llm_rounds"] += 1
        if out_of_budget and steps > 0:
            olcum["budget_exhausted"] = True
            olcum["finalization_forced"] = True
        try:
            tool_calls, visible, thinking = _saglayici_cagir(
                provider, messages, offered_tools,
                tur_no=olcum["llm_rounds"], tur_kimligi=tur_kimligi,
                gecen=elapsed)
        except AssistantProviderError as exc:
            # HIZ SINIRINDA YENİDEN DENEME YOK.
            # Aynı turda tekrar istek atmak sorunu büyütür; kotayı daha
            # da yakar ve kullanıcı yine cevap alamaz. Eldeki araç
            # sonuçları KORUNUR ve döngü biter.
            # ZAMAN AŞIMI VE HIZ SINIRINDA YENİDEN DENEME YOK.
            # Aynı istemi tekrar göndermek, başka modele düşmek ya da
            # bekleyip yeniden denemek kullanıcıyı ikinci kez bekletir
            # ve kotayı daha da yakar. Bu turda model yolu kapanır;
            # eldeki araç sonuçları KORUNUR.
            _kind = getattr(exc, "kind", "")
            if _kind in ("rate_limit", "timeout"):
                if _kind == "rate_limit":
                    olcum["rate_limited"] = True
                else:
                    olcum["timed_out"] = True
                logger.warning(
                    "[AI TURN %s] tur sonlandirildi (%s); yeniden deneme "
                    "yok, eldeki sonuclarla devam ediliyor.",
                    tur_kimligi, _kind)
                tool_calls, visible, thinking = [], "", ""
                break
            # Hesaplanan sonuçlar hazırsa modelin yorumu olmadan da cevap
            # verilir. Model boş metin döndürdü diye doğru hesaplanmış bir
            # senaryoyu kullanıcıdan saklamak yanlış olur.
            #
            # KATALOG DA AYNI KORUMAYA GİRER. Katalog veriyi zaten
            # veritabanından okudu; model erişilemez diye o sayıyı
            # kullanıcıdan saklamak, eskiden çalışan bir cevabı
            # kaybetmek demektir. Sağlayıcı erişilemezken tüm katalog
            # cevaplarının 503'e düşmesinin sebebi buydu.
            # ELDEKİ ARAÇ SONUÇLARI ÇÖPE ATILMAZ.
            # Sağlayıcı erişilemese bile veritabanından okunmuş
            # sonuçlar varsa kullanıcı boş ekran görmemeli.
            # SAĞLAYICININ BOZUK/BOŞ CEVABI AĞ GEÇİDİ ARIZASI DEĞİLDİR.
            # `invalid_response`, modele ulaşıldığı ama gelen gövdenin
            # ayrıştırılamadığı (malformed candidate, parse hatası, boş
            # aday listesi) durumdur. Bunu yukarı fırlatmak router'da
            # 502'ye dönüşüyor ve kullanıcı elinde hiçbir şey olmadan
            # "Bad Gateway" görüyordu. Böyle bir durumda bile aşağıdaki
            # kapı kontrollü bir uygulama cevabı üretir; istek 200 döner.
            # Yukarı yalnızca ANLAMLI ve DÜRÜST durumlar fırlatılır:
            # sağlayıcıya hiç ulaşılamaması (503) gibi.
            if _kind == "invalid_response":
                logger.warning(
                    "[AI TURN %s] saglayici bozuk cevap dondu; 502 yerine "
                    "kontrollu cevaba dusuluyor.", tur_kimligi)
            elif (composed is None and not catalog_available
                    and not (session is not None and session.any_success())):
                raise
            logger.warning(
                "Model yorum uretemedi; elde olan sonuclarla devam ediliyor."
            )
            tool_calls, visible, thinking = [], "", ""
            break
        if thinking:
            logger.debug(
                "Model dusunme metni uretti (%d karakter), kullaniciya gonderilmedi",
                len(thinking),
            )

        if tool_calls and session is not None and offered_tools is not None:
            steps += 1
            messages.append(
                {
                    "role": "assistant",
                    "content": visible,
                    # Çağrı kimliği SAĞLAYICIDAN GELDİĞİ GİBİ taşınır.
                    # OpenAI uyumlu uçlar, araç sonucunu geri alırken
                    # hangi çağrıya ait olduğunu bu kimlikle eşler.
                    "tool_calls": [
                        {
                            **({"id": c["id"]} if c.get("id") else {}),
                            "function": {"name": c["name"],
                                         "arguments": c["arguments"]},
                        }
                        for c in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                ad = call["name"]
                # BÜTÇE DOLDUYSA VERİ ARACI ÇALIŞTIRILMAZ.
                # Hata fırlatılmaz: modele yapılandırılmış bir "artık
                # veri getirilemiyor" sonucu döner ve elindekiyle cevap
                # yazmaya yönlendirilir. Kullanıcıya hata gösterilmez.
                veri_araci = ad not in BUTCE_DISI_ARACLAR
                if veri_araci and veri_cagrisi >= MAX_DATA_TOOL_CALLS:
                    olcum["budget_exhausted"] = True
                    messages.append({
                        "role": "tool", "name": ad,
                        "content": json.dumps({
                            "budget_exhausted": True,
                            "message": ("Bu tur için ek veri getirilemiyor. "
                                        "Şimdiye kadar alınan sonuçlarla "
                                        "cevabı yaz."),
                        }, ensure_ascii=False),
                    })
                    continue

                onceden = session.already_called(ad, call.get("arguments") or {})
                record = session.run(ad, call.get("arguments"))
                olcum["tool_calls"] += 1
                olcum["tools"].append(ad)
                if onceden:
                    # AYNI ÇAĞRI BÜTÇE YEMEZ.
                    # `ToolSession` sonucu zaten önbellekten döndürüyor;
                    # veritabanına da bütçeye de dokunulmaz.
                    olcum["cache_hits"] += 1
                elif veri_araci:
                    veri_cagrisi += 1
                    olcum["data_tool_calls"] += 1
                messages.append(
                    {
                        "role": "tool",
                        "name": record.name,
                        # MODELE GİDEN KOPYA SIKIŞTIRILIR.
                        # ------------------------------------------------
                        # Ham JSON, 19 üniversite × 5 yıl gibi çıktılarda
                        # her hücre için anahtar adını tekrar yazıyor ve
                        # tek başına ~3.000 token tutuyordu. İki tur
                        # sağlayıcının dakikalık token bütçesini
                        # bitiriyordu.
                        #
                        # Sıkıştırma yalnızca BİÇİM değiştirir; sayı
                        # yuvarlanmaz, satır atılmaz. `record.content`
                        # ham hâliyle duruyor ve grafik/ui_spec onu
                        # kullanmaya devam ediyor.
                        "content": tool_compaction.sikistir(record.content),
                        **({"tool_call_id": call["id"]} if call.get("id") else {}),
                    }
                )
            continue

        # --- Araç çağrısı yok. Kurumsal soruda bu yeterli değil. ---
        needs_tool_result = (
            institutional
            and session is not None
            and not context_data_available
            and not session.any_success()
            and offered_tools is not None
        )
        if needs_tool_result and not forced_retry_used:
            logger.info("Kurumsal soruya aracsiz cevap uretildi; ikinci sans veriliyor.")
            forced_retry_used = True
            # Modelin araçsız metni ATILIR: kullanıcıya gösterilmeyecek bir
            # cevabı konuşma geçmişine koymak modeli aynı hataya iter.
            messages.append(
                {"role": "system", "content": query_policy.RETRY_INSTRUCTION}
            )
            visible = ""
            continue

        break

    # TUR ÖLÇÜMÜ — yalnızca günlüğe. Gerçek istek yapmadan bütçe
    # davranışını görebilmek için; kullanıcı arayüzüne gitmez ve
    # hiçbir gizli değer içermez.
    _durum = ("rate_limit" if olcum["rate_limited"]
              else "timeout" if olcum["timed_out"]
              else "budget" if olcum["budget_exhausted"] else "ok")
    logger.info(
        "[AI TURN %s] TURN END total=%.1f status=%s llm_rounds=%d "
        "tool_calls=%d data_tool_calls=%d cache_hits=%d finalization=%s "
        "tools=%s", tur_kimligi, time.monotonic() - started, _durum,
        olcum["llm_rounds"], olcum["tool_calls"], olcum["data_tool_calls"],
        olcum["cache_hits"], olcum["finalization_forced"],
        ",".join(olcum["tools"][:8]) or "-")

    used_tools = session.used_tools() if session else []
    data_sources = session.data_sources() if session else []
    # Turun NASIL bittiği router'a taşınır: grafik çizilemediğinde
    # "veri yok" mu yoksa "yorum turu yetişmedi" mi denecek, bu ayrımı
    # yalnızca burası bilir. Yanıt şemasına GİRMEZ; router okuyup atar.
    tur_zaman_asimi = bool(olcum["timed_out"] or olcum["rate_limited"])
    for source in list(backend_context_sources) + list(catalog_sources):
        if source not in data_sources:
            data_sources.append(source)
    scope = session.scope() if session else {}
    if not scope and catalog_dataset is not None:
        scope = _catalog_scope(catalog_dataset)
    academic_year = session.academic_year() if session else None
    if academic_year is None and ui_scope:
        academic_year = ui_scope.get("academic_year")
    tool_data_available = session is not None and session.any_success()
    # KATALOG DA GROUNDING'DİR. Veriyi veritabanından okudu ve modele
    # aynen verdi; araç sonucundan daha az güvenilir değil. Bu satır
    # olmadan politika, katalogla cevaplanan soruları "araçsız" sayıp
    # reddederdi — yani bugün çalışan cevaplar bozulurdu.
    grounded_data_available = (
        tool_data_available or context_data_available or catalog_available
    )

    # ZORUNLU ARAÇ KONTROLÜ: gerekli senaryo aracı başarıyla çalışmadıysa
    # modelin serbest metni kullanıcıya GÖSTERİLMEZ. Yanlış araçla üretilmiş
    # bir "mevcut bütçe" özeti, senaryo sorusunun cevabı değildir.
    required_tool_ran = True
    if forced_tool is not None and session is not None:
        required_tool_ran = any(
            record.name == forced_tool and record.success for record in session.records
        )
        if not required_tool_ran:
            logger.warning(
                "Zorunlu arac calismadi (%s); model metni reddedildi.", forced_tool
            )

    # GROUNDING ÖNCELİKLİDİR, ZORUNLU DEĞİLDİR.
    # ======================================================================
    # ÖNCEKİ DAVRANIŞ: kurumsal bir soruda backend bağlamı ya da başarılı
    # araç sonucu yoksa modelin ÜRETTİĞİ METİN SİLİNİYOR, yerine
    # "güvenilir yanıt üretilemedi" konuyordu. Logda da şu ikili
    # görünüyordu ve yanıltıcıydı:
    #
    #   "…model metni reddedildi."
    #   "MODEL METNİ YOK (empty_or_invalid_response)"
    #
    # İkinci satır modelin sustuğunu ima ediyor; oysa model konuşmuştu,
    # metni BURADA silinmişti. Kullanıcı, Gemini'nin yazdığı geçerli bir
    # cevabı hiç görmeden teknik bir mesajla karşılaşıyordu.
    #
    # YENİ DAVRANIŞ: retrieval başarısızlığı bir cevabı yok etme sebebi
    # değildir. Sıralama şudur:
    #
    #   grounded cevap  >  yalnızca-model cevabı  >  hata
    #
    # Grounding hâlâ birinci tercihtir ve RAG katmanı olduğu gibi durur;
    # yalnızca "veri bulunamadı" durumu artık sessizliğe değil, modelin
    # kendi cevabına düşer. Durum `grounding_status` ile İÇERİDE
    # işaretlenir; arayüz teknik ayrıntı görmez.
    #
    # KORUNAN TEK İSTİSNA: `required_tool_ran`. Senaryo soruları ("ücret
    # %10 artarsa ne olur") backend'in hesap motorunu ZORUNLU kılar.
    # Model o hesabı kendi başına yaparsa uydurma sayı üretir — bu,
    # grounding yokluğundan farklı bir risktir: yanlış cevap, eksik
    # cevaptan tehlikelidir. Orada metin yine tutulur ama kurumsal veri
    # iddiası taşımaz.
    grounding_status = "grounded" if grounded_data_available else "model_only"
    model_text_received = bool((visible or "").strip())

    if institutional and not grounded_data_available:
        logger.warning(
            "[AI TURN %s] GROUNDING YOK — model metni KORUNUYOR "
            "(model_text_received=%s, model_text_rejected=no)",
            tur_kimligi, "yes" if model_text_received else "no")
        # Kurumsal veri iddiası edilmez: sayı geldiyse bile kaynağı
        # veritabanı değildir.
        data_source = query_policy.SOURCE_GENERAL
    elif institutional and not required_tool_ran:
        logger.warning(
            "[AI TURN %s] ZORUNLU ARAÇ ÇALIŞMADI (%s) — metin korunuyor, "
            "kurumsal veri iddiası edilmiyor", tur_kimligi, forced_tool)
        grounding_status = "model_only"
        data_source = query_policy.SOURCE_GENERAL
    elif grounded_data_available:
        data_source = query_policy.SOURCE_INSTITUTIONAL
    else:
        data_source = query_policy.SOURCE_GENERAL

    # ZORUNLU GERÇEKLER + MODEL YORUMU.
    #
    # Model yorumu boş olsa bile hesaplanan sonuçlar kullanıcıya ulaşır:
    # canlı testte model 370 → 426 değişimini yazmayı atlamıştı.
    structured_result: Optional[Dict[str, Any]] = None
    ui_spec_payload: Optional[Dict[str, Any]] = None
    # Katalog veri kümesi yapılandırılmış sonuç olarak taşınır. Eskiden
    # katalog yolunda `ui_spec` sabit `None` idi ve bu veri hiçbir yere
    # gitmiyordu; grafik üretimi için tek girdi burasıdır.
    if catalog_dataset is not None and catalog_available:
        structured_result = catalog_dataset
    interpretation: Optional[str] = None
    facts_markdown = ""
    if composed is not None and data_source == query_policy.SOURCE_INSTITUTIONAL:
        structured_result = composed.structured_result
        interpretation = _clean_interpretation(visible, composed.facts_markdown)
        facts_markdown = composed.facts_markdown
        visible = composed.facts_markdown
        if interpretation:
            visible += "\n\n" + interpretation

    # DİNAMİK SONUÇ PENCERESİ.
    # ------------------------------------------------------------------
    # Kartlar ve grafikler modelin METNİNDEN DEĞİL, `structured_result`tan
    # üretilir; bu kural değişmedi.
    #
    # Değişen şey KOŞUL. Üretim eskiden `composed is not None` içine
    # gömülüydü ve `composed` yalnızca dört composer'dan biri, yalnızca
    # zorunlu araç dalında çalıştığında doluyordu. Sonuç: 19 aracın
    # 15'i ve bütün katalog cevapları grafiksizdi — katalog yolunda
    # `ui_spec` zaten sabit `None` yazılıydı.
    #
    # Artık tek koşul var: elde yapılandırılmış bir sonuç varsa pencere
    # denenir. Üretilemezse sohbet cevabı yine gösterilir; pencere
    # isteğe bağlı bir katman olarak kalır.
    if structured_result and data_source == query_policy.SOURCE_INSTITUTIONAL:
        try:
            spec = ui_spec_builder.build_ui_spec(
                structured_result,
                data_sources=data_sources,
                calculated_at=datetime.now(),
                interpretation=interpretation,
                markdown=facts_markdown,
            )
            ui_spec_payload = spec.model_dump(mode="json") if spec else None
        except Exception:  # noqa: BLE001
            logger.exception("Dinamik pencere tanimi uretilemedi")
            ui_spec_payload = None

    # KATALOG YEDEĞİ.
    # ------------------------------------------------------------------
    # Katalog veriyi bulduysa kullanıcı en azından o sayıyı görmeli.
    # Model yolu boş dönerse (zaman aşımı, geçersiz çıktı, politika reddi)
    # eski deterministik cevaba düşülür. Bu, değişikliğin taban çizgisi:
    # yeni akış en kötü ihtimalle bugünkü davranışı verir, altına inmez.
    if catalog_available and catalog_fallback:
        if not visible or visible == query_policy.NO_TOOL_RESULT_MESSAGE:
            logger.info("Model yolu bos dondu; katalog cevabina donuluyor.")
            visible = catalog_fallback
            data_source = query_policy.SOURCE_INSTITUTIONAL

    # MODEL SUSTUYSA ÖNCE ONA BİR ŞANS DAHA VERİLİR.
    # ======================================================================
    # Deterministik geri düşüş iyi bir güvenlik ağıdır ama BİRİNCİ tercih
    # değildir: kullanıcı bir veri kümesi özeti değil, cevap bekliyor.
    # Model ilk turda metin üretemediyse bunun en sık sebebi araç
    # döngüsünün son turunda takılıp kalmasıdır — elde veri vardır,
    # yalnızca cümle kurulmamıştır.
    #
    # İki ek deneme yapılır, ikisi de ARAÇSIZ:
    #   1. FİNALİZASYON — konuşma ve araç sonuçları korunur, modele tek
    #      iş verilir: "şimdi cevabı yaz". Araç şeması gönderilmez ki
    #      yeniden araç çağırıp aynı döngüye girmesin.
    #   2. SADELEŞTİRME — geçmiş atılır, yalnızca soru ve eldeki
    #      sonuçların özeti gönderilir. Bağlam uzunluğu ya da bozuk bir
    #      araç mesajı sorunun kaynağıysa bu tur onu aşar.
    #
    # Sonsuz denenmez: toplam iki ek çağrı. Süre bütçesi de korunur —
    # kalan süre yoksa hiç denenmez.
    if not visible or visible == query_policy.NO_TOOL_RESULT_MESSAGE:
        # KOTA DOLDUYSA ÖNCE ALTERNATİF BULUT MODELİ.
        # `_son_sans` kotada bilinçli olarak hiç denemez — aynı modeli
        # tekrar çağırmak sonucu değiştirmez. Ama BAŞKA bir modelin
        # kotası ayrıdır; yapılandırılmışsa bir kez denenir.
        if olcum.get("rate_limited"):
            visible = _alternatif_model_dene(
                provider, messages, message, session,
                tur_kimligi=tur_kimligi, gecen=time.monotonic() - started,
                olcum=olcum) or visible
        if not visible or visible == query_policy.NO_TOOL_RESULT_MESSAGE:
            visible = _son_sans(
                provider, messages, message, session,
                tur_kimligi=tur_kimligi, gecen=time.monotonic() - started,
                olcum=olcum) or visible

    # MODELDEN METİN GELMEDİYSE — SEBEBİ NE OLURSA OLSUN — İSTEK ÖLMEZ.
    # ------------------------------------------------------------------
    # ÖLÇÜLEN ARIZA: bu koşul eskiden `rate_limited or timed_out` idi.
    # Model geçerli ama BOŞ bir metin döndürdüğünde (zaman aşımı yok,
    # kota yok — yalnızca boş ya da sadece araç çağrısı içeren yanıt)
    # kapı kapalı kalıyor, `visible` boş kalıyor ve devamındaki `raise`
    # çalışıyordu. Router `invalid_response` türünü 502'ye eşlediği için
    # kullanıcı "Bad Gateway" görüyordu — üstelik veri araçları başarıyla
    # çalışmış, veritabanından sayılar okunmuş olduğu hâlde.
    #
    # Sağlayıcının susması bir AĞ GEÇİDİ ARIZASI DEĞİLDİR. Elde gerçek
    # veri varken isteği öldürmek, kullanıcının hakkı olan cevabı teknik
    # bir ayrıntı uğruna atmak olur. Kapı artık sebepten bağımsızdır:
    # metin yoksa ne bulunduysa o gösterilir.
    #
    # Zaman aşımı ya da kota da aynı kapıdan geçer; bunlar ALTYAPI
    # OLAYIDIR ve yeri günlüktür (`ROUND N TIMEOUT` satırı loglarda
    # aynen durur). Ekranda yalnızca elde edilen sonuç gösterilir.
    if not visible or visible == query_policy.NO_TOOL_RESULT_MESSAGE:
        # Sebep yalnızca günlüğe; kullanıcı teknik ayrıntı görmez.
        _sebep = ("rate_limit" if olcum["rate_limited"]
                  else "timeout" if olcum["timed_out"]
                  else "empty_or_invalid_response")
        ozet = _elde_ne_var(session, message)
        logger.warning("[AI TURN %s] MODEL METNİ YOK (%s); fallback=%s",
                       tur_kimligi, _sebep,
                       "veri_ozeti" if ozet else "kontrollu_mesaj")
        # KULLANICI TEKNİK AYRINTI GÖRMEZ.
        # ------------------------------------------------------------------
        # "Modelin yorum turu zaman aşımına uğradı" cümlesi bir sunumda
        # sistemin çöktüğü izlenimi veriyor; oysa veriler okunmuş,
        # sayılar hesaplanmış durumda. Zaman aşımının kendisi bir
        # ALTYAPI OLAYIDIR ve yeri günlüktür — nitekim `ROUND N TIMEOUT`
        # satırı loglarda aynen duruyor. Ekranda yalnızca elde edilen
        # sonuç gösterilir.
        if ozet:
            visible = ("Veriler başarıyla analiz edildi. Aşağıdaki özet "
                       "doğrudan sistem kayıtlarından oluşturuldu.\n\n"
                       + ozet)
            data_source = query_policy.SOURCE_INSTITUTIONAL
        elif catalog_fallback:
            # Katalog veriyi zaten okumuştu; model sussa da o sayı
            # kullanıcıdan saklanmaz.
            visible = catalog_fallback
            data_source = query_policy.SOURCE_INSTITUTIONAL
        else:
            # Elde hiçbir şey yok. Yine de 502 değil: kullanıcı ne
            # yapacağını bilsin diye anlaşılır bir uygulama cevabı.
            visible = KONTROLLU_MESAJ
            data_source = query_policy.SOURCE_UNAVAILABLE

    # KOTA BİLDİRİMİ — CEVABIN BAŞINA, BACKEND TARAFINDAN.
    # ======================================================================
    # Kullanıcı neden farklı bir cevap aldığını bilmeli. Ama bu satır
    # YALNIZCA gerçekten kota/hız sınırı yaşandığında eklenir; zaman
    # aşımı, boş cevap, netleştirme, normal model-only cevap ve "veri
    # bulunamadı" durumlarında EKLENMEZ — oralarda kota yoktur ve
    # yanlış bilgi vermek olurdu.
    #
    # Bildirim Gemini'ye yazdırılmaz: kota dolduğunda model zaten
    # konuşamıyor olabilir. Deterministik olarak eklenirse her zaman
    # doğrudur.
    #
    # Teknik ayrıntı yazılmaz: quotaId, HTTP kodu, retryDelay, model
    # yönlendirmesi, anahtar — hiçbiri kullanıcının işine yaramaz.
    provider_status = "ok"
    answer_mode = "grounded_gemini" if grounded_data_available else (
        "model_only_gemini")
    if olcum.get("rate_limited"):
        provider_status = "quota_exceeded"
        _grounded_metin = (
            session is not None and session.any_success()) or catalog_available
        if olcum.get("alternatif_model"):
            answer_mode = "fallback_gemini"
            kota_notu = KOTA_NOTU_ALTERNATIF
        elif _grounded_metin:
            answer_mode = "deterministic_grounded"
            kota_notu = KOTA_NOTU_VERIDEN
        else:
            answer_mode = "provider_unavailable"
            kota_notu = KOTA_NOTU_VERI_YOK
            # ELDE VERİ YOKKEN BİLE "güvenilir yanıt üretilemedi"
            # DEMEK YANLIŞTIR: sebep BELLİ ve söylenebilir. Belirsiz
            # cümle, kullanıcıya sorusunu yeniden yazdırır; oysa yapması
            # gereken tek şey kotanın yenilenmesini beklemek.
            if (not visible
                    or visible == query_policy.NO_TOOL_RESULT_MESSAGE
                    or visible.strip() == KONTROLLU_MESAJ):
                visible = ""
        visible = (kota_notu + ("\n\n" + visible if visible.strip() else ""))
        logger.info(
            "[AI TURN %s] provider_result=quota structured_evidence=%s "
            "answer_mode=%s quota_notice=yes",
            tur_kimligi, "yes" if _grounded_metin else "no", answer_mode)

    logger.info(
        "[AI TURN %s] RESULT sources=%s rows=%d answer=%s chars=%d",
        tur_kimligi,
        ",".join(session.data_sources()) if session else "-",
        sum(len((getattr(k.output, "rows", None) or []))
            for k in (session.records if session else [])
            if k.success and k.output is not None),
        "fallback" if (session and session.any_success()
                       and "doğrudan sistem kayıtlarından" in (visible or "")
                       ) else ("model" if visible else "yok"),
        len(visible or ""))

    # `raise` KALDIRILDI. Yukarıdaki kapı her yolda bir metin üretir;
    # 502 artık yalnızca gerçekten beklenmeyen bir iç hatadan (router'ın
    # genel `except` dalı) çıkabilir, sağlayıcının susmasından değil.

    # GRAFİK KODU GÖRÜNÜR METİNDE KALMAZ.
    # ------------------------------------------------------------------
    # Model bazen grafiği araç çağırarak değil, cevabın içine gömdüğü
    # bir ```render_chart bloğuyla istiyor. O blok araç katmanına hiç
    # ulaşmıyor ve kullanıcı ekranda grafik yerine ham JSON görüyordu.
    #
    # Yönerge katmanı (SYSTEM_PROMPT 7h) ilk savunma; bu ikincisi ve
    # deterministik. Kişi adı sanitizer'ıyla AYNI ilke: sorunlu PARÇA
    # temizlenir, cevap değil. Blok çıktıktan sonra kalan doğal dil
    # aynen gider; hiçbir şey kalmazsa `answer_mode` değişmez, yalnızca
    # metin boşalır ve alttaki mevcut kapılar devreye girer.
    _kod_sonucu = grafik_donustur.kod_bloklarini_ayikla(visible)
    if _kod_sonucu.kaldirilan:
        logger.info("[AI TURN %s] CHART_CODE_STRIPPED blocks=%d",
                    tur_kimligi, _kod_sonucu.kaldirilan)
        visible = _kod_sonucu.metin

    # KURUMSAL KİŞİ ADI KORUMASI — CEVAP KULLANICIYA GİTMEDEN HEMEN ÖNCE.
    # ------------------------------------------------------------------
    # Yönerge katmanı (SYSTEM_PROMPT 0e-0g) ilk savunmadır; bu, ikinci
    # savunma. Model yine de doğrulanmamış bir ad yazarsa CEVAP
    # REDDEDİLMEZ: yalnızca ad aralığı, bağlamına uygun genel bir
    # ifadeyle değiştirilir. `answer_mode`, `data_source`, grounding ve
    # sağlayıcı politikası bu adımdan ETKİLENMEZ — burada yapılan tek
    # şey metnin içindeki adı değiştirmek.
    #
    # Kanca tek noktada: kota notu, deterministik özet, model-only ve
    # zaman aşımı cevaplarının hepsi buradan geçer. İkinci bir LLM
    # çağrısı yoktur; ölçülen maliyet cümle başına ~0,05 ms.
    _ad_sonucu = kisi_adi.sanitize(
        visible, kisi_adi.grounded_adlar(
            session, ek_metinler=[backend_context_text or ""]))
    if _ad_sonucu.bulunan:
        logger.info(
            "[AI TURN %s] PERSON_NAMES detected=%d grounded=%d sanitized=%d",
            tur_kimligi, _ad_sonucu.bulunan, _ad_sonucu.grounded,
            _ad_sonucu.temizlenen)
    visible = _ad_sonucu.metin

    _store.append(conversation, "user", user_content)
    _store.append(conversation, "assistant", visible)

    # MODELİN ÇİZDİRDİĞİ GRAFİKLER.
    # Değerler `render_chart`ın okuduğu araç çıktısından gelir; modelin
    # yazdığı metinden DEĞİL. Grafik ile cevap metni böylece aynı
    # sorgudan beslenir, ayrışamaz.
    model_charts: List[Dict[str, Any]] = []
    for kayit in (session.records if session else []):
        if kayit.name == "render_chart" and kayit.success:
            grafik = getattr(kayit.output, "chart", None)
            if grafik:
                model_charts.append(grafik)

    # GRAFİK ARTIK MODELİN İSTEĞİNE BAĞLI DEĞİL.
    # ------------------------------------------------------------------
    # Yukarıdaki döngü yalnızca model `render_chart` çağırdıysa grafik
    # bulur. Model çağırmadığında — ya da çağıramadığında — çizilecek
    # veri elde durduğu hâlde grafik çıkmıyordu. Çağıramadığı bir durum
    # yapısal olarak da var: çok metrikli analiz yolunda veriyi backend
    # çekiyor, modelin `source_tool` olarak gösterebileceği bir araç
    # çağrısı bulunmuyor.
    #
    # Kullanıcı grafik istediyse ve elde veri varsa, grafik AYNI turun
    # verisinden türetilir. Yeni sorgu yok, uydurma sayı yok; metin ve
    # grafik aynı kaynağı tüketir. Türetilemezse metin cevabı olduğu
    # gibi kalır — grafiğin çıkmaması cevabı düşürmez.
    _grafik_istendi = grafik_uret.istendi_mi(message)
    _grafik_gerekce = ""
    # SAF TÜR DEĞİŞİMİNDE YENİ GRAFİK TÜRETİLMEZ.
    # "donut yap" bir grafik İSTEĞİ gibi görünür ama içinde ne metrik
    # ne varlık ne yıl vardır; ondan türetilecek grafik kullanıcının
    # ekranda gördüğü grafik DEĞİLDİR. Dönüştürme katmanı hatırlanan
    # grafiği çevirir; burada boşa iş yapmak hem yanlış veri üretir
    # hem de gereksiz sorgu açar.
    _sadece_tur = grafik_donustur.istek_oku(message).sadece_tur
    if _grafik_istendi and not model_charts and not _sadece_tur:
        _turetilen = grafik_uret.uret(message, plan=_plan, kanit=_kanit,
                                      session=session)
        if _turetilen:
            model_charts = _turetilen
            logger.info("[AI TURN %s] CHART derived=%d source=%s",
                        tur_kimligi, len(_turetilen),
                        "multi_metric" if _kanit is not None
                        and getattr(_kanit, "var", False) else "tool_rows")
        else:
            _grafik_gerekce = grafik_uret.sebep(False, bool(data_sources))
    if _grafik_istendi and model_charts:
        logger.info("[AI TURN %s] CHART requested=yes count=%d",
                    tur_kimligi, len(model_charts))

    return {
        "conversation_id": conversation,
        "answer": visible,
        "model_charts": model_charts,
        "chart_requested": _grafik_istendi,
        "chart_reason": _grafik_gerekce,
        "provider": provider.name,
        "model": provider.model,
        "used_tools": used_tools,
        "data_sources": data_sources,
        "academic_year": academic_year,
        "scope": scope,
        "data_source": data_source,
        "structured_result": structured_result,
        "ui_spec": ui_spec_payload,
        "timed_out": tur_zaman_asimi,
    }


def _clean_interpretation(text: str, facts_markdown: str) -> str:
    """Modelin yorumunu hazırlar.

    Model bazen zorunlu gerçekler bölümünü kopyalıyor; aynı sayılar iki kez
    görünmesin diye tekrar eden satırlar atılır. Model yorumu boşsa boş
    dizge döner — gerçekler bölümü yine de kullanıcıya gider.
    """
    if not text:
        return ""

    fact_lines = {line.strip() for line in facts_markdown.splitlines() if line.strip()}
    kept: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and stripped in fact_lines:
            continue
        if stripped.startswith("### Hesaplanan sonuçlar"):
            continue
        kept.append(line)

    cleaned = "\n".join(kept).strip()
    if not cleaned:
        return ""
    # Model başlıkları hiç yazmadıysa en azından bir başlık altına alınır;
    # başlıksız serbest metin, kapsamı belirsiz bir yorum demektir.
    if not any(
        heading in cleaned for heading in response_composer.INTERPRETATION_HEADINGS
    ):
        cleaned = f"{response_composer.INTERPRETATION_HEADING}\n{cleaned}"
    return cleaned


def _build_forced_arguments(
    db: Session, intent: "query_policy.QueryIntent", message: str,
    default_academic_year: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Zorunlu senaryo aracının parametrelerini metinden çıkarır.

    Hepsi çıkarılamazsa None döner ve karar modele bırakılır — ama model
    yalnızca gerekli aracı görebilir, başkasını seçemez.

    Akademik yıl POLİTİKAYLA belirlenir: kullanıcı açıkça yazmadıysa
    `current` dönem seçilir, planlama dönemi seçilmez.
    """
    try:
        year = entity_resolver.resolve_academic_year(
            db,
            intent.explicit_academic_year or default_academic_year,
            allow_planning=intent.wants_planning_period,
        )
    except entity_resolver.EntityResolutionError:
        return None

    if intent.intent == query_policy.INTENT_STAFF_SALARY:
        percentage = intent.parameters.get("salary_change_percentage")
        if percentage is None:
            return None
        return {"academic_year": year, "salary_change_percentage": percentage}

    if intent.required_tool == "get_program_summary":
        program = entity_resolver.find_in_text(db, "program", message)
        if program is None:
            return None
        return {"academic_year": year, "program": program.code}

    if intent.intent == query_policy.INTENT_ENROLLMENT_CHANGE:
        percentage = intent.parameters.get("student_change_percentage")
        if percentage is None:
            return None
        program = entity_resolver.find_in_text(db, "program", message)
        if program is None:
            return None
        return {
            "academic_year": year,
            "program": program.code,
            "student_change_percentage": percentage,
        }

    return None


def stream_answer(
    message: str, conversation_id: Optional[str] = None
) -> Tuple[str, Iterator[str]]:
    """Cevabı parça parça üretir.

    NOT: Akış modunda araç çağrısı YAPILMAZ. Araç turları arasında akışı
    bölmek kullanıcıya yarım cümleler gösterirdi; araçlı sorular tek seferlik
    `/chat` uç noktasından cevaplanır.
    """
    conversation, messages = _prepare(message, conversation_id)
    provider = get_provider()
    user_content = messages[-1]["content"]

    def generate() -> Iterator[str]:
        collected: List[str] = []
        for piece in provider.stream_chat(messages):
            collected.append(piece)
            yield piece
        full = "".join(collected).strip()
        if full:
            _store.append(conversation, "user", user_content)
            _store.append(conversation, "assistant", full)

    return conversation, generate()


def status() -> Dict[str, Any]:
    """Asistanın kullanıcıya gösterilecek durumu. Hata FIRLATMAZ."""
    provider = get_provider()

    if not settings.ASSISTANT_ENABLED:
        return {
            "provider": provider.name,
            "model": provider.model,
            "enabled": False,
            "service_available": False,
            "model_available": False,
            "ready": False,
            "message": "Akıllı Asistan yapılandırmada devre dışı bırakıldı.",
            "installed_models": [],
            "tool_count": len(registry.names()),
        }

    # DURUM UCU ASLA ÇÖKMEZ.
    # ------------------------------------------------------------------
    # Bu uç nokta hata fırlatırsa asistan ekranı hiç açılamaz ve
    # kullanıcı sorunun ne olduğunu göremez — yani teşhis aracının
    # kendisi arızayla birlikte kaybolur. Sağlayıcıdan gelen BEKLENMEYEN
    # her hata (eksik bağımlılık, yapılandırma çakışması) burada
    # yakalanır ve "hazır değil" olarak bildirilir.
    try:
        health = provider.health()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Saglayici durum sorgusu basarisiz: %s", type(exc).__name__)
        return {
            "provider": provider.name,
            "model": getattr(provider, "model", ""),
            "enabled": True,
            "service_available": False,
            "model_available": False,
            "ready": False,
            "message": ("Sağlayıcı durumu okunamadı. Sunucu günlüklerinde "
                        "ayrıntı var."),
            "installed_models": [],
            "tool_count": len(registry.names()),
        }
    return {
        "provider": provider.name,
        # Otomatik seçim yapıldıysa ETKİN model adı bildirilir; boş dize
        # göndermek arayüzde "Gemini bağlı · " gibi yarım bir rozet üretir.
        "model": (provider.etkin_model() if hasattr(provider, "etkin_model")
                  else provider.model),
        "enabled": True,
        "service_available": health.service_available,
        "model_available": health.model_available,
        "ready": health.ready,
        "message": health.message,
        "installed_models": list(health.installed_models),
        "tool_count": len(registry.names()),
    }


def reset_conversations() -> None:
    """Bellekteki tüm konuşmaları siler."""
    _store.clear()
    _catalog_datasets.clear()


__all__ = [
    "AssistantProviderError",
    "ChatValidationError",
    "MAX_TOOL_STEPS",
    "query_policy",
    "MAX_TOOL_WALL_SECONDS",
    "SYSTEM_PROMPT",
    "answer",
    "build_messages",
    "reset_conversations",
    "status",
    "stream_answer",
    "validate_message",
]
