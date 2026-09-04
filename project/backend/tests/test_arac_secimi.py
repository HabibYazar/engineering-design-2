"""Araç seçimi ve token bütçesi.

NEDEN VAR
---------
Bulut sağlayıcı dakikalık bir token bütçesi uyguluyor. 19 aracın şeması +
sistem yönergesi 7.404 token tutuyordu; kullanıcı daha soruyu yazmadan
bütçe doluyor ve her istek HTTP 413 ile dönüyordu.

Bu dosya iki şeyi korur:
  * sabit yükün tavanı (bir daha sessizce dolmasın),
  * seçimin GENİŞ kalması (yanlış eleme, tasarruftan pahalıdır).
"""

from __future__ import annotations

import json

import pytest

from app.services.assistant import tools as _t  # noqa: F401  (kayıt için)
from app.services.assistant import tools_extended as _te  # noqa: F401
from app.services.assistant import tool_selection
from app.services.assistant.chat_service import SYSTEM_PROMPT
from app.services.assistant.tool_registry import registry

#: Kaba token tahmini. Kesin sayaç yerine oran kullanılıyor çünkü asıl
#: soru "tavana yaklaşıyor muyuz" — birkaç token sapma önemli değil.
TOKEN = 3.3

#: Sabit yük tavanı. Sağlayıcı dakikalık bir token bütçesi uyguluyor; soru,
#: kurumsal bağlam, araç sonuçları ve cevap için pay bırakılmalı.
#: Yönerge + seçilen araç şemalarının üst sınırı (token).
#:
#: 5000 → 5300. Tavan bir bütçe koruması; keyfî bir sayı değil ve
#: yükseltmesi de keyfî değil. İki bilinçli değişiklik yükü ~%1 artırdı:
#:
#:   1. `query_canonical_data` artık HER soruda sunuluyor. Önceden "son
#:      çare" listesindeydi ve tam da kurumsal veri sorularında modele
#:      hiç sunulmuyordu — merkezî veritabanına erişimin tek kapısı
#:      kapalı kalıyordu (ölçüldü: 5 yıllık taban puan sorusu bu yüzden
#:      fallback'e düşüyordu).
#:   2. Sistem yönergesine merkezî veritabanını tanıtan iki madde.
#:
#: Asıl kısıt sağlayıcının dakikalık token bütçesiydi (~7.400). 5.300
#: hâlâ onun belirgin şekilde altında; koruma işlevini sürdürüyor.
SABIT_YUK_TAVANI = 5300


def _token(metin: str) -> float:
    return len(metin) / TOKEN


def _sema_token(semalar) -> float:
    return _token(json.dumps(semalar, ensure_ascii=False))


@pytest.mark.parametrize("soru", [
    "son beş yıldaki üniversiteler arasındaki bilgisayar mühendisliği trendini yorumla",
    "Toplam öğrenci sayımız kaç?",
    "Kaç dersliğimiz var?",
    "Maaşlara %10 zam yapılırsa ne olur?",
    "Rakip üniversitelerle ücret karşılaştırmasını göster",
    "Müfredatımızda kaç ders var?",
    "En yüksek performans puanlı akademisyenler kim?",
    "Merhaba",
])
def test_sabit_yuk_tavani_asilmaz(soru):
    """Yönerge + seçilen araç şemaları tavanın altında kalmalı."""
    secilen = tool_selection.suz(registry.schemas(), soru)
    yuk = _token(SYSTEM_PROMPT) + _sema_token(secilen)
    assert yuk < SABIT_YUK_TAVANI, (
        f"Sabit yük {yuk:.0f} token — tavan {SABIT_YUK_TAVANI}. "
        f"Yönerge ya da araç şemaları büyümüş."
    )


def test_secim_asla_bos_donmez():
    """Boş araç listesi, asistanın kurumsal soruya cevap verememesi demek."""
    for soru in ("", "asdfghjkl", "🙂", "x" * 500):
        secilen = tool_selection.suz(registry.schemas(), soru)
        assert secilen, f"{soru!r} için araç listesi boş"
        assert len(secilen) >= tool_selection.EN_AZ


def test_ilgili_arac_elenmez():
    """Sorunun açıkça işaret ettiği araç listede olmalı."""
    beklenen = {
        "Kaç dersliğimiz var?": ("get_facility_inventory", "get_capacity_summary"),
        "Müfredatımızda kaç ders var?": ("get_curriculum_summary",),
        "Maaşlara %10 zam yapılırsa": ("run_staff_salary_scenario",),
        "Rakip üniversitelerin ücretleri": ("get_tuition_comparison",),
        "Stratejik hedeflerimiz ne durumda?": ("get_strategic_kpis",),
        "Yıllara göre kontenjan trendi": ("get_program_quota_trend",),
        "En çok ders veren akademisyen kim?": ("get_teaching_load", "list_academic_staff"),
    }
    for soru, adaylar in beklenen.items():
        adlar = {s["function"]["name"]
                 for s in tool_selection.suz(registry.schemas(), soru)}
        assert adlar & set(adaylar), f"{soru!r} → {adaylar} hiçbiri seçilmedi"


def test_zorunlu_arac_her_zaman_kalir():
    """Backend niyet yönlendirmesi araç seçiminden ÖNCE gelir."""
    secilen = tool_selection.suz(
        registry.schemas(), "merhaba nasılsın", zorunlu="get_early_warnings")
    assert "get_early_warnings" in {s["function"]["name"] for s in secilen}


def test_her_aracin_anahtar_kelimesi_var():
    """Yeni araç eklendiğinde anahtar kelimesi de eklenmeli.

    Eklenmezse araç sessizce kaybolmaz (çekirdek listeye girerse yine
    görünür) ama seçilme şansı düşer. Bu test o unutmayı yakalar.
    """
    kayitli = {t.name for t in registry.all()}
    tanimli = (set(tool_selection.ANAHTARLAR)
               | set(tool_selection.CEKIRDEK)
               | set(tool_selection.HER_ZAMAN)
               # SON_CARE araçları bilerek anahtar kelimesizdir: hangi
               # kelimenin geçtiğine göre değil, ÖZEL BİR ARAÇ EŞLEŞMEDİĞİ
               # için devreye girerler.
               | set(tool_selection.SON_CARE))
    eksik = kayitli - tanimli
    assert not eksik, f"Anahtar kelimesi tanımlanmamış araç: {sorted(eksik)}"


def test_az_arac_varsa_eleme_yapilmaz():
    """Bütçe sorunu yokken eleme yalnızca risk getirir."""
    az = registry.schemas()[:4]
    assert tool_selection.suz(az, "herhangi bir soru") == az


def test_none_girdi_none_doner():
    """"Araç sunma" kararı korunmalı."""
    assert tool_selection.suz(None, "soru") is None


def test_grafik_araci_her_soruda_listede_kalir():
    """`render_chart` anahtar kelimeyle SEÇİLMEZ; daima sunulur.

    Kelimeye bağlansaydı ("grafik", "göster", "çiz") elemeye takıldığı
    her soruda grafik sessizce imkânsız hale gelirdi — yeni kaldırdığımız
    regex kalıbının aynısını bu sefer araç seçiminde kurmuş olurduk.
    """
    for soru in ("son beş yıldaki bilgisayar mühendisliği trendini yorumla",
                 "toplam öğrenci sayımız kaç",
                 "bunu görselleştir",
                 "akademisyen performansı"):
        secilen = tool_selection.ilgili_araclar(soru, registry.names())
        assert "render_chart" in secilen, f"grafik aracı düştü: {soru!r}"


def test_grafik_araci_tavani_yemez():
    """Daimi araç, veri araçlarının yerini almamalı.

    ÖLÇÜT DEĞİŞTİ, KORUNAN ŞEY DEĞİŞMEDİ. `EN_AZ` doldurması artık
    koşulludur: soru kendi araçlarını bulduysa liste çekirdekle
    şişirilmez (bkz. `_CEKIRDEKSIZ_ESIK`). O yüzden "en az 5 veri aracı"
    beklemek, elemenin amacını tersine çeviren bir ölçüttü.
    Test artık asıl korunanı ölçer: `render_chart` listeye girdi diye
    veri araçları dışarıda kalmaz.
    """
    soru = "bölüm bazında öğrenci dağılımını göster"
    secilen = tool_selection.ilgili_araclar(soru, registry.names())
    veri_araclari = [a for a in secilen if a != "render_chart"]
    assert "render_chart" in secilen          # grafik aracı yerinde
    assert veri_araclari                      # veri araçları ezilmedi

    # Grafik aracı OLMASAYDI seçilecek veri araçlarının hepsi hâlâ
    # listede olmalı: daimi araç kimsenin yerini almadı.
    grafiksiz = [a for a in registry.names() if a != "render_chart"]
    beklenen = tool_selection.ilgili_araclar(soru, grafiksiz)
    assert set(beklenen) <= set(veri_araclari)
