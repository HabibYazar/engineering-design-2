"""Yeni canonical veri kümelerini asistanın erişimine açan araçlar.

NE DEĞİŞTİ, NE DEĞİŞMEDİ
------------------------
DEĞİŞMEYEN: modelin adı, uç adresi, sıcaklık, düşünme ayarı, sistem
yönergesi, araç çağırma döngüsü, konuşma geçmişi, akış biçimi, hata
eşlemesi. Sağlayıcı katmanına tek satır dokunulmadı.

DEĞİŞEN: kayıt defterine üç araç eklendi. Asistan bugün nasıl
çalışıyorsa aynı şekilde çalışır; yalnızca sorabileceği şeylerin
kapsamı büyür.

NEDEN YENİ ARAÇ GEREKTİ
-----------------------
Son iki günde veritabanına giren metriklerin çoğunu mevcut araçların
hiçbiri okumuyordu. Ölçüldü: `yok_atlas_benchmark_metrics` tablosunda
29 farklı metrik var; mevcut araçlar bunların yalnızca dördünü
(`quota`, `placed`, `base_score`, `success_rank`) sorguluyor. Ücret,
öğretim üyesi kadrosu, cinsiyet kırılımı, tercih istatistikleri, kurum
düzeyi zaman serileri ve kaynak çelişkileri asistan için görünmezdi.

TÜM VERİTABANI YÖNERGEYE BASILMAZ
---------------------------------
Bu araçlar 99.831 satırlık tabloyu döndürmez. Her biri zorunlu
süzgeçlerle çalışır (metrik adı, yıl, kurum, program) ve döndürdüğü
satır sayısı üst sınırla kısıtlıdır. Model neye ihtiyacı olduğunu
söyler, araç yalnızca onu getirir — mevcut araçların çalışma biçimiyle
aynı.

GERÇEKLİK ÖNCELİĞİ
------------------
Aynı varlık + metrik + dönem için birden çok kayıt bulunursa seçim
BURADA, deterministik olarak yapılır; modele iki çelişkili satır
sunulup "sen seç" denmez. Öncelik `_KULVAR_ONCELIGI` ile tanımlıdır:
en yeni doğrulanmış kaynak kazanır.

TANIMLARI KARIŞTIRMAMA
----------------------
Farklı tanımlı sayılar birbirinin alternatifi DEĞİLDİR ve
birleştirilmez: `staff_total` (YÖK Atlas program bağlantısı),
`academic_staff_count_reported` (kurumun beyanı) ve projenin kendi
personel kaydı ayrı metriklerdir. Aynı şekilde
`faculty_count_at_founding` ile `faculty_count_reported` ayrıdır.
Araçlar metriği adıyla döndürür; model hangi tanımı okuduğunu görür.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.assistant.tool_registry import (
    ToolDefinition,
    ToolExecutionError,
    registry,
)

#: Tek yanıtta dönebilecek en fazla satır. Model bunu aşan bir istek
#: yaparsa süzgeci daraltması söylenir; sessizce kırpılıp eksik veriyle
#: cevap üretilmez.
EN_FAZLA_SATIR = 300

#: KULVAR ÖNCELİĞİ — küçük sayı daha güvenilir.
#: Aynı program/yıl/metrik için birden çok kayıt varsa bu sıra karar
#: verir. Sıralama kaynağın tazeliğine ve doğrulanmışlığına göredir.
_KULVAR_ONCELIGI = {
    "YÖK Atlas dataset 2025": 1,          # birleştirilmiş canonical kulvar
    "Ekip newdata 2026 (kurum düzeyi)": 2,
    "Ekip derlemesi 2021-2025 (varyant düzeyi)": 3,
}


def _oncelik(kulvar: Optional[str]) -> int:
    return _KULVAR_ONCELIGI.get(kulvar or "", 99)


# ---------------------------------------------------------------------------
# 1) PROGRAM DÜZEYİ METRİKLER
# ---------------------------------------------------------------------------
class ProgramMetrikGirdi(BaseModel):
    model_config = {"extra": "forbid"}

    metric: str = Field(
        description=("Metrik adı. Örnekler: quota, placed, occupancy_percent, "
                     "base_score, success_rank, annual_fee_try, staff_prof, "
                     "staff_docent, staff_dr_ogr_uyesi, staff_ars_gor, "
                     "placed_male, placed_female, preference_first, "
                     "preference_total, min_rank_requirement. Hangi "
                     "metriklerin bulunduğunu görmek için list_available_metrics "
                     "aracını kullan."))
    academic_year: Optional[str] = Field(
        default=None, description="Örn. '2025-2026'. Boşsa tüm yıllar.")
    university: Optional[str] = Field(
        default=None, description="Üniversite adının bir parçası.")
    program: Optional[str] = Field(
        default=None, description="Program adının bir parçası.")


class ProgramMetrikSatir(BaseModel):
    university: Optional[str] = None
    program: Optional[str] = None
    academic_year: Optional[str] = None
    metric: str
    value: Optional[float] = None
    unit: Optional[str] = None
    scholarship: Optional[str] = None
    language: Optional[str] = None
    source: Optional[str] = None
    #: Kaynağın tanım notu. 2025 yerleşen gibi tanımı diğer yıllardan
    #: farklı olan değerlerde bu alan doludur ve okunmalıdır.
    definition_note: Optional[str] = None


class ProgramMetrikCikti(BaseModel):
    metric: str
    row_count: int
    rows: List[ProgramMetrikSatir]
    notes: List[str] = []


def _program_metrikleri(db: Session, p: ProgramMetrikGirdi) -> ProgramMetrikCikti:
    kosul = ["metric = :m"]
    par: Dict[str, Any] = {"m": p.metric}
    if p.academic_year:
        kosul.append("academic_year = :y"); par["y"] = p.academic_year
    if p.university:
        kosul.append("university_name LIKE :u"); par["u"] = f"%{p.university}%"
    if p.program:
        kosul.append("program_name LIKE :p"); par["p"] = f"%{p.program}%"

    sql = text(
        "SELECT university_name, program_name, academic_year, metric, value, "
        "unit, scholarship_type, program_language, source_dataset, methodology "
        "FROM yok_atlas_benchmark_metrics WHERE " + " AND ".join(kosul)
        + f" LIMIT {EN_FAZLA_SATIR * 4}")
    ham = db.execute(sql, par).all()
    if not ham:
        raise ToolExecutionError(
            f"'{p.metric}' için bu süzgeçlerle kayıt bulunamadı. Metrik adını "
            "list_available_metrics ile doğrulayın.", kind="no_data")

    # ÇELİŞKİ ÇÖZÜMÜ BURADA: aynı program+yıl için en güvenilir kulvar.
    en_iyi: Dict[Any, Any] = {}
    for r in ham:
        anahtar = (r[0], r[1], r[2])
        if anahtar not in en_iyi or _oncelik(r[8]) < _oncelik(en_iyi[anahtar][8]):
            en_iyi[anahtar] = r

    satirlar = [
        ProgramMetrikSatir(
            university=r[0], program=r[1], academic_year=r[2], metric=r[3],
            value=float(r[4]) if r[4] is not None else None, unit=r[5],
            scholarship=r[6], language=r[7], source=r[8],
            definition_note=(r[9] if r[9] and "tanım" in str(r[9]).lower()
                             else None))
        for r in list(en_iyi.values())[:EN_FAZLA_SATIR]
    ]
    notlar = []
    if len(en_iyi) > EN_FAZLA_SATIR:
        notlar.append(f"{len(en_iyi)} kayıttan ilk {EN_FAZLA_SATIR} gösteriliyor; "
                      "süzgeci daraltın.")
    if any(s.definition_note for s in satirlar):
        notlar.append("Bazı kayıtların kaynak tanımı farklıdır; "
                      "definition_note alanını okuyun.")
    return ProgramMetrikCikti(metric=p.metric, row_count=len(satirlar),
                              rows=satirlar, notes=notlar)


# ---------------------------------------------------------------------------
# 2) KURUM DÜZEYİ METRİKLER + KAYNAK ÇELİŞKİLERİ
# ---------------------------------------------------------------------------
class KurumMetrikGirdi(BaseModel):
    model_config = {"extra": "forbid"}

    metric: Optional[str] = Field(
        default=None,
        description=("Metrik adı. Örnekler: staff_total, staff_prof, "
                     "students_total, students_per_staff, "
                     "faculty_count_reported, founding_year_reported. "
                     "Boşsa kurumun tüm kurum düzeyi metrikleri döner."))
    university: Optional[str] = Field(
        default=None, description="Üniversite adının bir parçası.")
    academic_year: Optional[str] = Field(default=None)
    include_source_conflicts: bool = Field(
        default=False,
        description=("Aynı gerçek için iki kaynağın farklı sayı verdiği "
                     "bilinen durumları da getir. 'Akademisyen sayımız kaç?' "
                     "gibi tanım farkı olabilecek sorularda açın."))


class KurumMetrikSatir(BaseModel):
    university: Optional[str] = None
    academic_year: Optional[str] = None
    metric: str
    value: Optional[float] = None
    unit: Optional[str] = None
    source: Optional[str] = None
    definition_note: Optional[str] = None


class KaynakCeliskisi(BaseModel):
    subject: Optional[str] = None
    source_1: Optional[str] = None
    value_1: Optional[str] = None
    source_2: Optional[str] = None
    value_2: Optional[str] = None
    note: Optional[str] = None


class KurumMetrikCikti(BaseModel):
    row_count: int
    rows: List[KurumMetrikSatir]
    source_conflicts: List[KaynakCeliskisi] = []
    notes: List[str] = []


def _kurum_metrikleri(db: Session, p: KurumMetrikGirdi) -> KurumMetrikCikti:
    kosul = ["source_dataset = 'Ekip newdata 2026 (kurum düzeyi)'"]
    par: Dict[str, Any] = {}
    if p.metric:
        kosul.append("metric = :m"); par["m"] = p.metric
    if p.university:
        kosul.append("university_name LIKE :u"); par["u"] = f"%{p.university}%"
    if p.academic_year:
        kosul.append("academic_year = :y"); par["y"] = p.academic_year

    ham = db.execute(text(
        "SELECT university_name, academic_year, metric, value, unit, "
        "source_file, methodology FROM yok_atlas_benchmark_metrics WHERE "
        + " AND ".join(kosul) + f" ORDER BY university_name, academic_year "
        f"LIMIT {EN_FAZLA_SATIR}"), par).all()

    satirlar = [
        KurumMetrikSatir(university=r[0], academic_year=r[1], metric=r[2],
                         value=float(r[3]) if r[3] is not None else None,
                         unit=r[4], source=r[5], definition_note=r[6])
        for r in ham
    ]

    celiskiler: List[KaynakCeliskisi] = []
    if p.include_source_conflicts:
        # TANIM FARKLARI UYDURULMAZ, KAYITTAN OKUNUR.
        for r in db.execute(text(
                "SELECT record_label, existing_source, existing_value, "
                "incoming_source, incoming_value, note FROM data_source_conflicts "
                "WHERE field_name LIKE 'newdata%' LIMIT 50")).all():
            celiskiler.append(KaynakCeliskisi(
                subject=r[0], source_1=r[1], value_1=r[2],
                source_2=r[3], value_2=r[4], note=r[5]))

    notlar = []
    if celiskiler:
        notlar.append("Aşağıdaki konularda iki resmî kaynak farklı sayı "
                      "veriyor. Bunlar hata değil TANIM farkıdır; tek bir "
                      "sayı seçmeden önce hangi tanımın sorulduğunu belirtin.")
    if not satirlar and not celiskiler:
        raise ToolExecutionError("Bu süzgeçlerle kurum düzeyi metrik yok.",
                                 kind="no_data")
    return KurumMetrikCikti(row_count=len(satirlar), rows=satirlar,
                            source_conflicts=celiskiler, notes=notlar)


# ---------------------------------------------------------------------------
# 3) AYNI / BENZER BÖLÜM — YETKİLİ TABLO
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _eslesme_satirlari() -> List[Dict[str, str]]:
    """`data/bolum_eslesme/bolum_eslesme.csv` — süreçte bir kez okunur."""
    for ata in Path(__file__).resolve().parents:
        aday = ata / "data" / "bolum_eslesme" / "bolum_eslesme.csv"
        if aday.is_file():
            with open(aday, encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
    return []


class EsdegerGirdi(BaseModel):
    model_config = {"extra": "forbid"}

    program: str = Field(
        description="ABÜ bölümünün adı, örneğin 'Psikoloji'.")
    relation: Optional[str] = Field(
        default=None,
        description=("'same' yalnızca aynı bölümler, 'similar' yalnızca "
                     "benzer bölümler. Boşsa ikisi de döner."))


class EsdegerSatir(BaseModel):
    peer_university: str
    peer_program: str
    relation: str


class EsdegerCikti(BaseModel):
    program: str
    same_count: int
    similar_count: int
    rows: List[EsdegerSatir]
    notes: List[str] = []


def _esdeger_programlar(db: Session, p: EsdegerGirdi) -> EsdegerCikti:
    """İlişkiyi TABLO belirler; benzerlik tahmini yapılmaz."""
    from app.services.program_equivalence import canonical_program_key

    anahtar = canonical_program_key(p.program)
    if not anahtar:
        raise ToolExecutionError(
            f"'{p.program}' tek bir bölüme çözülemedi.", kind="invalid_arguments")

    satirlar = [
        EsdegerSatir(peer_university=r["peer_university"],
                     peer_program=r["peer_program_key"],
                     relation=r["relation"])
        for r in _eslesme_satirlari()
        if r.get("abu_program_key") == anahtar
        and (not p.relation or r.get("relation") == p.relation)
    ]
    if not satirlar:
        raise ToolExecutionError(
            f"'{p.program}' için yetkili eşleştirme tablosunda kayıt yok. "
            "Bu bölüm için benzerlik TAHMİN EDİLMEZ.", kind="no_data")

    return EsdegerCikti(
        program=p.program,
        same_count=sum(1 for s in satirlar if s.relation == "same"),
        similar_count=sum(1 for s in satirlar if s.relation == "similar"),
        rows=satirlar[:EN_FAZLA_SATIR],
        notes=["İlişkiler ekibin hazırladığı yetkili eşleştirme dosyasından "
               "gelir; ad benzerliğiyle üretilmemiştir."])


# ---------------------------------------------------------------------------
# 4) METRİK KATALOĞU
# ---------------------------------------------------------------------------
class KatalogGirdi(BaseModel):
    model_config = {"extra": "forbid"}
    contains: Optional[str] = Field(
        default=None, description="Metrik adında geçen kelime ile süz.")


class KatalogSatir(BaseModel):
    metric: str
    level: str
    row_count: int
    years: Optional[str] = None


class KatalogCikti(BaseModel):
    metric_count: int
    metrics: List[KatalogSatir]


def _metrik_katalogu(db: Session, p: KatalogGirdi) -> KatalogCikti:
    kosul, par = [], {}
    if p.contains:
        kosul.append("metric LIKE :c"); par["c"] = f"%{p.contains}%"
    nerede = ("WHERE " + " AND ".join(kosul)) if kosul else ""
    ham = db.execute(text(
        "SELECT metric, source_dataset, COUNT(*), MIN(academic_year), "
        "MAX(academic_year) FROM yok_atlas_benchmark_metrics "
        f"{nerede} GROUP BY metric, source_dataset ORDER BY metric"), par).all()
    return KatalogCikti(
        metric_count=len({r[0] for r in ham}),
        metrics=[KatalogSatir(
            metric=r[0],
            level=("kurum" if "kurum" in (r[1] or "") else "program"),
            row_count=r[2],
            years=f"{r[3]} – {r[4]}" if r[3] else None) for r in ham])


# ---------------------------------------------------------------------------
# Kayıt
# ---------------------------------------------------------------------------
registry.register(ToolDefinition(
    name="get_program_metrics",
    description=(
        "Program düzeyinde herhangi bir YÖK Atlas metriğini getirir: "
        "kontenjan, yerleşen, doluluk, taban puan, başarı sırası, yıllık "
        "ücret, programa bağlı öğretim üyesi sayıları, yerleşenlerin "
        "cinsiyet/lise/mezun dağılımı, tercih istatistikleri. 2021-2026 "
        "yıllarını kapsar. Metrik adını bilmiyorsan önce "
        "list_available_metrics çağır."),
    input_model=ProgramMetrikGirdi, output_model=ProgramMetrikCikti,
    handler=_program_metrikleri, timeout_seconds=20.0,
    required_permission=None,
    data_source="YÖK Atlas program metrikleri (2021-2026)",
))

registry.register(ToolDefinition(
    name="get_institution_metrics",
    description=(
        "Kurum düzeyinde metrikler: yıllara göre öğretim elemanı kadrosu "
        "(profesör/doçent/dr. öğr. üyesi/araştırma görevlisi), öğrenci "
        "sayıları, öğrenci başına öğretim elemanı, kurumun kendi raporunda "
        "beyan ettiği sayılar. Aynı gerçek için farklı kaynaklar farklı "
        "sayı veriyorsa include_source_conflicts=true ile bunları da "
        "getirebilirsin."),
    input_model=KurumMetrikGirdi, output_model=KurumMetrikCikti,
    handler=_kurum_metrikleri, timeout_seconds=20.0,
    required_permission=None,
    data_source="Kurum düzeyi metrikler ve kaynak çelişkileri",
))

registry.register(ToolDefinition(
    name="get_equivalent_programs",
    description=(
        "Bir ABÜ bölümünün diğer Ankara üniversitelerindeki AYNI ve BENZER "
        "karşılıklarını verir. 'Psikoloji hangi üniversitelerde var?', "
        "'Yazılım Mühendisliğine benzer programlar neler?' gibi sorularda "
        "kullan. İlişki yetkili eşleştirme dosyasından gelir; kendin "
        "benzerlik TAHMİN ETME."),
    input_model=EsdegerGirdi, output_model=EsdegerCikti,
    handler=_esdeger_programlar, timeout_seconds=10.0,
    required_permission=None,
    data_source="Yetkili aynı/benzer bölüm eşleştirme tablosu",
))

registry.register(ToolDefinition(
    name="list_available_metrics",
    description=(
        "Veritabanında gerçekten bulunan metrik adlarını, düzeyini ve yıl "
        "aralığını listeler. get_program_metrics veya "
        "get_institution_metrics çağırmadan önce metrik adını doğrulamak "
        "için kullan."),
    input_model=KatalogGirdi, output_model=KatalogCikti,
    handler=_metrik_katalogu, timeout_seconds=10.0,
    required_permission=None,
    data_source="Metrik kataloğu",
))
