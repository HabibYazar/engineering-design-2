"""Merkezî veri tabanı (`abu_kds.db`) asistana gerçekten ulaşıyor mu.

ÖLÇÜLEN ARIZA
-------------
Loglarda şu görülüyordu:

    "Kurumsal soru backend bağlamı/araç sonucu olmadan cevaplandı;
     model metni reddedildi."

Örnek soru: "Ankara'daki son 5 yıldaki en düşük mühendislik taban puanı
olan üniversiteler nelerdir?"

Sorun guard DEĞİLDİ — guard doğru çalışıyordu. Sorun, veri veritabanında
hazır dururken retrieval katmanının onu modele ulaştıramamasıydı. İki
ayrı kopukluk ölçüldü:

1. `query_canonical_data` — merkezî veritabanının tek kapısı — "son
   çare" listesindeydi. Kurumsal sorularda özel araçlar anahtar
   kelimeyle eşleştiği için bu araç modele HİÇ SUNULMUYORDU.

2. Taban puan beş yıl için üç ayrı tabloda, üç ayrı sütun adıyla
   duruyordu. Modelin bunu keşfetmesi gerçekçi değildi.

Buradaki testler iki kopukluğun da geri gelmemesini sağlar. GERÇEK
GEMINI İSTEĞİ YAPILMAZ; yalnızca veri ve araç katmanı ölçülür.
"""

from __future__ import annotations

import pytest

from app.services.assistant import abu_kds_store as store
from app.services.assistant import tool_selection
from app.services.assistant.tool_registry import registry
from app.services.assistant.tool_runner import ToolSession

pytestmark = pytest.mark.skipif(
    not store.kullanilabilir(),
    reason="abu_kds.db yok; veri tabanı bağımlı testler atlanır.")


# --------------------------------------------------------------- 1
def test_veritabani_baglandi():
    o = store.ozet()
    assert o["available"] is True
    # Ekip paketinin ölçüsü: 59 gerçek tablo + türetilmiş görünümler.
    assert o["tables"] >= 59
    assert o["rows"] > 30000
    assert "yks" in o["categories"] and "students" in o["categories"]


# --------------------------------------------------------------- 2
def test_baglanti_salt_okunur():
    """Yazma girişimi SQLite düzeyinde reddedilmeli."""
    import sqlite3
    con = store._baglan()
    try:
        with pytest.raises(sqlite3.OperationalError):
            con.execute("CREATE TABLE sizinti (x INTEGER)")
    finally:
        con.close()


# --------------------------------------------------------------- 3
def test_bes_yillik_taban_puan_gercek_veri_donuyor():
    """ASIL REGRESYON. 2021-2025'in tamamı tek kaynaktan gelmeli."""
    satirlar = store.satirlar(
        "kds_yks_ankara_taban_puan_5yil",
        secilen=["academic_year", "university_name", "program_name",
                 "base_score"],
        kosullar=[("program_name", "LIKE", "%Mühendisli%")],
        sirala="base_score", sinir=50)
    assert satirlar, "5 yıllık mühendislik taban puanı boş döndü"
    yillar = {r["academic_year"] for r in satirlar}
    # KAPSAMA AYRI ÖLÇÜLÜR. Satır sınırı (200) yüzünden tek bir sorgu
    # bütün yılları göremeyebilir; her yıl için ayrı ayrı sorulur.
    # Asıl korunan şey: beş yılın HİÇBİRİ kaynakta eksik olmamalı.
    for yil in (2021, 2022, 2023, 2024, 2025):
        yillik = store.satirlar(
            "kds_yks_ankara_taban_puan_5yil",
            secilen=["academic_year", "base_score"],
            kosullar=[("program_name", "LIKE", "%Mühendisli%"),
                      ("academic_year", "=", yil)],
            sinir=5)
        assert yillik, f"{yil} yılı için mühendislik taban puanı yok"
    assert all(r["base_score"] is not None for r in satirlar)
    # Sıralama artan: ilk kayıt gerçekten en düşük olmalı.
    puanlar = [r["base_score"] for r in satirlar]
    assert puanlar == sorted(puanlar)
    assert yillar  # kullanılmayan değişken uyarısı olmasın


# --------------------------------------------------------------- 4
def test_null_sifira_donusturulmuyor():
    """NULL = 0 DEĞİLDİR. Ölçülmemiş değer sıfır gibi görünmemeli."""
    satirlar = store.satirlar(
        "kds_yks_ankara_history_2023_2025",
        secilen=["base_score"], sinir=200)
    degerler = [r["base_score"] for r in satirlar]
    # Kaynakta ölçülmemiş taban puanlar var; bunlar None kalmalı.
    assert any(v is None for v in degerler), \
        "Beklenen NULL değerler kaybolmuş — sıfıra dönüştürülmüş olabilir"
    assert 0 not in [v for v in degerler if v is not None]


# --------------------------------------------------------------- 5
def test_arac_secimi_veritabani_kapisini_her_zaman_sunar():
    """1. KOPUKLUK. Kurumsal soruda `query_canonical_data` sunulmalı."""
    adlar = sorted(set(list(tool_selection.ANAHTARLAR)
                       + list(tool_selection.HER_ZAMAN)
                       + list(tool_selection.SON_CARE)))
    sorular = [
        "Ankara'daki son 5 yıldaki en düşük mühendislik taban puanı "
        "olan üniversiteler nelerdir?",
        "Toplam öğrenci sayımız kaç?",
        "Kaç akademisyenimiz var?",
        "Psikoloji programının son yıllardaki kontenjan ve doluluk "
        "durumunu karşılaştır.",
    ]
    for soru in sorular:
        secilen = tool_selection.ilgili_araclar(soru, adlar)
        assert "query_canonical_data" in secilen, (
            f"Merkezî veritabanının kapısı sunulmadı: {soru!r}")


# --------------------------------------------------------------- 6
def test_turkce_arama_ingilizce_tabloyu_buluyor(db_session):
    """2. KOPUKLUK. Türkçe soru, İngilizce adlı tabloyu bulmalı."""
    s = ToolSession(db=db_session)
    beklenen = {
        "öğrenci sayısı": "kds_students",
        "akademisyen": "kds_academic_staff",
        "ücret": "kds_fees",
        "derslik": "kds_",
    }
    for terim, onek in beklenen.items():
        kayit = s.run("explore_data_sources", {"search": terim})
        assert kayit.success, f"{terim!r} keşfi başarısız"
        veri = kayit.output.model_dump(mode="json")
        kaynaklar = [k["source"] for k in veri["sources"]]
        assert any(k.startswith(onek) for k in kaynaklar), (
            f"{terim!r} için {onek}* kaynağı bulunamadı: {kaynaklar[:8]}")


# --------------------------------------------------------------- 7
def test_arac_uzerinden_uctan_uca_sorgu(db_session):
    """Model'in kullanacağı yol: query_canonical_data → gerçek satırlar."""
    s = ToolSession(db=db_session)
    kayit = s.run("query_canonical_data", {
        "source": "kds_yks_ankara_taban_puan_5yil",
        "fields": ["academic_year", "university_name", "base_score"],
        "filters": {"program_name": "Mühendisli"},
        "order_by": "base_score", "limit": 5})
    assert kayit.success, f"sorgu başarısız: {kayit.content[:200]}"
    veri = kayit.output.model_dump(mode="json")
    assert veri["row_count"] == 5
    assert all(r.get("base_score") for r in veri["rows"])
    # Kökeni cevaba taşınabilsin diye not olarak döner.
    assert any("2021" in n for n in veri["notes"])


# --------------------------------------------------------------- 8
def test_model_serbest_sql_calistiramaz():
    """Yazma, çok ifadeli sorgu ve bilinmeyen sütun reddedilmeli."""
    with pytest.raises(ValueError):
        store.satirlar("kds_occupancy_by_year", secilen=["olmayan_sutun"])
    with pytest.raises(ValueError):
        store.satirlar("kds_occupancy_by_year",
                       kosullar=[("quota", "DROP", 1)])
    with pytest.raises(ValueError):
        store.satirlar("kds_occupancy_by_year", sirala="1; DROP TABLE x")
    # Önek olmadan erişim yok: canonical tabloyla karışmasın.
    with pytest.raises(ValueError):
        store.satirlar("occupancy_by_year")


# --------------------------------------------------------------- 9
def test_satir_siniri_uygulanir():
    """36 bin satır model bağlamına basılamaz."""
    satirlar = store.satirlar("kds_occupancy_by_year", sinir=10_000)
    assert len(satirlar) <= store.EN_FAZLA_SATIR


# --------------------------------------------------------------- 10
def test_kaynak_kokeni_bildiriliyor():
    """"Bu sayı nereden geldi" veritabanının içinden cevaplanmalı."""
    not_ = store.kaynak_notu("kds_occupancy_by_year")
    assert not_ and ("Kaynak" in not_ or "kontenjan" in not_.lower())
    assert store.kategori("kds_students_by_university_2020_2026") == "students"
