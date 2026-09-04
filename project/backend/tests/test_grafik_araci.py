"""`render_chart` — modelin çizdirdiği grafiğin doğruluk güvenceleri.

BURADA DOĞRULANAN ŞEY
---------------------
Grafik üretimi artık elle yazılmış kalıplara değil MODELİN KARARINA
bağlı. Bu esnekliğin bedeli, yeni bir yanlışlık kapısı açma riskidir:
model grafiğe kendi uydurduğu sayıları sokabilseydi, ekrandaki eğri
kurum verisi gibi görünüp gerçekte modelin tahmini olurdu — ve bunu
kimse fark etmezdi.

Bu dosya o kapının YAPISAL olarak kapalı olduğunu kanıtlar: araç sayı
kabul etmez, veriyi kendisi okur, okuyamazsa çizmez.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.services.assistant import chart_tool
from app.services.assistant.chart_tool import (
    RenderChartInput,
    _tablolari_bul,
    kur,
)
from app.services.assistant.tool_registry import ToolExecutionError, registry

# `get_program_quota_trend` çıktısının gerçek biçimi (kısaltılmış).
IC_ICE = {
    "program_label": "Bilgisayar Mühendisliği",
    "years": [2022, 2023, 2024],
    "universities": [
        {"university": "BİLKENT", "has_program": True, "series": [
            {"year": 2022, "quota": 1215.0, "occupancy_percent": 100.0},
            {"year": 2023, "quota": 1191.0, "occupancy_percent": 100.0},
            {"year": 2024, "quota": 1153.0, "occupancy_percent": 100.0}]},
        {"university": "ODTÜ", "has_program": True, "series": [
            {"year": 2022, "quota": 1034.0, "occupancy_percent": 100.0},
            {"year": 2023, "quota": 1014.0, "occupancy_percent": 100.0},
            {"year": 2024, "quota": 1039.0, "occupancy_percent": 89.51}]},
    ],
}

DUZ = {"rows": [
    {"faculty": "Mühendislik", "students": 1450},
    {"faculty": "İİBF", "students": 980},
    {"faculty": "Hukuk", "students": 610},
]}


def _istek(**kw) -> RenderChartInput:
    temel = {"source_tool": "get_program_quota_trend", "x_field": "year",
             "y_field": "quota", "series_field": "university",
             "chart_type": "line", "title": "Kontenjan trendi"}
    temel.update(kw)
    return RenderChartInput(**temel)


# ---------------------------------------------------------------------------
# EN KRİTİK BÖLÜM — MODEL SAYI YAZAMAZ
# ---------------------------------------------------------------------------
def test_girdi_semasinda_sayisal_veri_alani_yok():
    """Şemaya sayı ya da SAYI DİZİSİ girecek bir alan olmamalı.

    Bu testin koruduğu şey bir davranış değil bir İMKÂNSIZLIK: grafiğin
    değerleri yalnızca araç çıktısından gelebilsin, modelin yazdığı
    metinden asla. Şemaya ileride `values: List[float]` gibi bir alan
    eklenirse test o anda kırılır.

    Kural "hiç dizi olmasın" DEĞİL, "sayı taşıyan alan olmasın"dır.
    `series_fields: List[str]` gibi ALAN ADI listeleri sayı taşımaz;
    hangi sütunun seriyi ayırdığını söyler, değerleri yine araç çıktısı
    belirler. İlk sürümde kural kaba biçimde "array yasak" yazılmıştı ve
    bu ayrımı yapamıyordu.
    """
    sema = RenderChartInput.model_json_schema()
    for ad, alan in sema["properties"].items():
        secenekler = [alan] + list(alan.get("anyOf", []))
        turler = {x.get("type") for x in secenekler}
        assert "number" not in turler, f"{ad}: sayısal alan eklenmiş"
        assert "integer" not in turler, f"{ad}: sayısal alan eklenmiş"
        assert "object" not in turler, f"{ad}: serbest nesne eklenmiş"
        for x in secenekler:
            if x.get("type") != "array":
                continue
            icerik = (x.get("items") or {}).get("type")
            assert icerik == "string", (
                f"{ad}: dizi yalnızca metin (alan adı) taşıyabilir, "
                f"gelen: {icerik!r}")


def test_modelin_yazdigi_deger_grafige_giremez():
    """Fazladan alan gönderilse bile reddedilir ya da yok sayılır."""
    with pytest.raises(ValidationError):
        RenderChartInput(
            source_tool="x", x_field="year", y_field="quota",
            title="t", data=[9999, 8888],  # type: ignore[call-arg]
        )


def test_grafikteki_sayilar_arac_ciktisindan_gelir():
    """Değerler kaynak çıktının AYNISI olmalı — yeniden hesaplanmaz."""
    sonuc = kur(IC_ICE, _istek())
    seri = {s["name"]: s["data"] for s in sonuc.chart["series"]}
    assert sonuc.chart["categories"] == ["2022", "2023", "2024"]
    assert seri["BİLKENT"] == [1215.0, 1191.0, 1153.0]
    assert seri["ODTÜ"] == [1034.0, 1014.0, 1039.0]


# ---------------------------------------------------------------------------
# KALIPSIZ ÇALIŞMA — ASIL DÜZELTİLEN ARIZA
# ---------------------------------------------------------------------------
def test_ic_ice_yapida_seri_alani_atadan_okunur():
    """Seriyi ayıran alan satırda değil ÜST nesnede olabilir.

    `{"university": "ODTÜ", "series": [{"year": ..., "quota": ...}]}`
    yapısında `university` satırlarda yoktur. Bu olmadan üniversiteler
    arası karşılaştırma — kullanıcının sorduğu şey — çizilemezdi.
    """
    sonuc = kur(IC_ICE, _istek())
    assert sonuc.series_count == 2
    assert {s["name"] for s in sonuc.chart["series"]} == {"BİLKENT", "ODTÜ"}


def test_duz_tabloda_da_calisir():
    """Tek seviyeli çıktı için ayrı bir kod yolu gerekmemeli."""
    sonuc = kur(DUZ, _istek(source_tool="x", x_field="faculty",
                            y_field="students", series_field=None,
                            chart_type="bar", title="Fakülte dağılımı"))
    assert sonuc.chart["categories"] == ["Mühendislik", "İİBF", "Hukuk"]
    assert sonuc.chart["series"][0]["data"] == [1450, 980, 610]


def test_ayni_veriden_farkli_metrik_cizilebilir():
    """Kalıp yokken metrik seçimi de serbesttir."""
    sonuc = kur(IC_ICE, _istek(y_field="occupancy_percent",
                               title="Doluluk", y_label="%"))
    seri = {s["name"]: s["data"] for s in sonuc.chart["series"]}
    assert seri["ODTÜ"] == [100.0, 100.0, 89.51]


def test_yillar_dogal_sirada():
    karisik = {"rows": [{"year": 2024, "v": 3}, {"year": 2022, "v": 1},
                        {"year": 2023, "v": 2}]}
    sonuc = kur(karisik, _istek(x_field="year", y_field="v",
                                series_field=None))
    assert sonuc.chart["categories"] == ["2022", "2023", "2024"]
    assert sonuc.chart["series"][0]["data"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# SAHTE GRAFİK ÇİZİLMEZ
# ---------------------------------------------------------------------------
def test_olcusuz_yil_sifir_olmaz():
    """`null` "ölçülmedi" demektir; sıfır çizmek veriyi bozar."""
    eksikli = {"rows": [{"year": 2021, "quota": None},
                        {"year": 2022, "quota": 1215.0},
                        {"year": 2023, "quota": None}]}
    sonuc = kur(eksikli, _istek(series_field=None))
    assert sonuc.chart["series"][0]["data"] == [None, 1215.0, None]


def test_olmayan_alan_hata_verir_ve_mevcut_alanlari_soyler():
    """Model alan adı uydurursa grafik çizilmez; doğrusu söylenir."""
    with pytest.raises(ToolExecutionError) as hata:
        kur(IC_ICE, _istek(y_field="kontenjan"))
    mesaj = str(hata.value)
    assert "kontenjan" in mesaj
    assert "quota" in mesaj, "modele mevcut alanlar söylenmeli"


def test_tum_degerler_bossa_grafik_yok():
    with pytest.raises(ToolExecutionError):
        kur({"rows": [{"year": 2021, "quota": None},
                      {"year": 2022, "quota": None}]},
            _istek(series_field=None))


def test_desteklenmeyen_tur_reddedilir():
    with pytest.raises(ToolExecutionError):
        kur(IC_ICE, _istek(chart_type="pasta"))


def test_cok_fazla_seri_kirpilir_ama_deger_degismez():
    veri = {"rows": [{"grup": f"G{i}", "yil": y, "v": i * 10 + y}
                     for i in range(40) for y in (1, 2)]}
    sonuc = kur(veri, _istek(source_tool="x", x_field="yil", y_field="v",
                             series_field="grup", title="t"))
    assert sonuc.series_count == chart_tool.EN_FAZLA_SERI
    assert any("okunabilirlik" in n.lower()
               for n in sonuc.chart["notes"])
    # Kalan serilerin değerleri BOZULMAMIŞ olmalı.
    ad = sonuc.chart["series"][0]["name"]
    i = int(ad[1:])
    assert sonuc.chart["series"][0]["data"] == [i * 10 + 1, i * 10 + 2]


# ---------------------------------------------------------------------------
# Oturum bağlantısı
# ---------------------------------------------------------------------------
class _Kayit:
    def __init__(self, name, content, success=True):
        self.name, self.content, self.success = name, content, success


class _Oturum:
    def __init__(self, records):
        self.records = records


def test_cagirilmayan_araca_grafik_istenirse_uyarir():
    oturum = _Oturum([_Kayit("get_program_summary", "{}")])
    with pytest.raises(ToolExecutionError) as hata:
        chart_tool.handler(None, _istek(), oturum)
    assert "get_program_summary" in str(hata.value)


def test_basarisiz_arac_kaynak_olamaz():
    oturum = _Oturum([_Kayit("get_program_quota_trend", "{}", success=False)])
    with pytest.raises(ToolExecutionError):
        chart_tool.handler(None, _istek(), oturum)


def test_oturumdaki_gercek_ciktidan_cizer():
    oturum = _Oturum([_Kayit("get_program_quota_trend",
                             json.dumps(IC_ICE, ensure_ascii=False))])
    sonuc = chart_tool.handler(None, _istek(), oturum)
    assert sonuc.rendered
    assert sonuc.point_count == 6


def test_grafik_govdesi_modele_gonderilmez():
    """Yüzlerce sayıyı modele geri okutmak token yakar ve kopyalamayı teşvik eder."""
    sonuc = kur(IC_ICE, _istek())
    modele_giden = json.loads(sonuc.model_dump_json())
    assert "chart" not in modele_giden
    assert modele_giden["series_count"] == 2


# ---------------------------------------------------------------------------
# Kayıt defteri
# ---------------------------------------------------------------------------
def test_arac_kayitli_ve_oturum_istiyor():
    tanim = registry.get("render_chart")
    assert tanim.needs_session is True
    assert tanim.required_permission is None


def test_tablo_arama_kucuk_listeleri_yok_sayar():
    """Tek satırlık liste tablo değildir; gürültü seri üretmemeli."""
    assert _tablolari_bul({"rows": [{"a": 1, "b": 2}]}, ("a", "b")) == []


# ---------------------------------------------------------------------------
# OKUNABİLİRLİK — GRAFİĞİN İŞE YARAMASI
# ---------------------------------------------------------------------------
def test_series_field_verilmezse_seri_adlari_kendiliginden_bulunur():
    """"Seri 1..14" bir efsane değildir; hiçbir şey anlatmaz.

    Gerçekte yaşandı: model `series_field` vermeyi unutunca ekranda 14
    numaralı seri çıktı ve hangi çizginin hangi üniversite olduğu
    hiçbir yerde yazmıyordu. Ad zaten veride duruyordu.
    """
    sonuc = kur(IC_ICE, _istek(series_field=None))
    adlar = {s["name"] for s in sonuc.chart["series"]}
    assert adlar == {"BİLKENT", "ODTÜ"}
    assert not any(a.startswith("Seri ") for a in adlar)


def test_ayirt_etmeyen_alan_seri_adi_olarak_secilmez():
    """Hepsinde aynı olan alan serileri ayırmaz; seçilmemeli."""
    veri = {"kurumlar": [
        {"ulke": "TR", "ad": "A", "series": [{"y": 1, "v": 1}, {"y": 2, "v": 2}]},
        {"ulke": "TR", "ad": "B", "series": [{"y": 1, "v": 3}, {"y": 2, "v": 4}]},
    ]}
    sonuc = kur(veri, _istek(source_tool="x", x_field="y", y_field="v",
                             series_field=None, title="t"))
    assert {s["name"] for s in sonuc.chart["series"]} == {"A", "B"}


def test_tek_seride_numara_yerine_olcunun_adi():
    sonuc = kur(DUZ, _istek(source_tool="x", x_field="faculty",
                            y_field="students", series_field=None,
                            chart_type="bar", title="t", y_label="Öğrenci"))
    assert sonuc.chart["series"][0]["name"] == "Öğrenci"


def test_zaman_ekseninde_cok_serili_cubuk_cizgiye_cevrilir():
    """14 seri × 5 yıl = 70 ince çubuk; okunmaz ve yanıltıcıdır.

    Zaman sürekli bir değişkendir; kesikli kutucuklarla göstermek
    yanlış gösterimdir. Kural DAR: yalnızca eksen sayısal (yıl) ve
    seri sayısı fazlaysa devreye girer.
    """
    kalabalik = {"universities": [
        {"university": f"Ü{i}", "series": [{"year": y, "quota": 100.0 + i}
                                           for y in (2022, 2023, 2024)]}
        for i in range(14)]}
    sonuc = kur(kalabalik, _istek(chart_type="bar"))
    assert sonuc.series_count == 14
    assert sonuc.chart["chart_type"] == "line"


def test_kategori_ekseninde_cubuk_korunur():
    """Fakülte/bölüm karşılaştırmasında çubuk DOĞRU gösterimdir."""
    sonuc = kur(DUZ, _istek(source_tool="x", x_field="faculty",
                            y_field="students", series_field=None,
                            chart_type="bar", title="t"))
    assert sonuc.chart["chart_type"] == "bar"


def test_az_serili_zaman_cubugu_korunur():
    """Kural yalnızca KALABALIK grafiklerde devreye girmeli."""
    sonuc = kur(IC_ICE, _istek(chart_type="bar"))
    assert sonuc.chart["chart_type"] == "bar"
