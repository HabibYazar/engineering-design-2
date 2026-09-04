"""EĞİTİM ÜCRETİ SERVİSİ — kendi programlarımız ve rakip kıyası.

KAPSAM KURALI
-------------
Ücret PROGRAM düzeyinde ölçülür. Kapsam süzmesi GERÇEK KİMLİKLER
üzerinden yürür ve hiçbir seviyede yukarı taşmaz:

    program    → yalnızca o programın ücretleri
    bölüm      → o bölümün programları
    fakülte    → o fakültenin bölümlerindeki programlar
    üniversite → hepsi

Programa çözülemeyen (ama fakültesi bilinen) satır, kapsam fakülte ya da
üniversite iken görünür; bölüm/program kapsamında görünmez — çünkü o
satırın hangi bölüme ait olduğu BİLİNMİYOR ve varsaymak sızıntı olurdu.

İKİ ÜCRET TÜRÜ AYNI PROGRAMIN İKİ FİYATIDIR
-------------------------------------------
Kaynak aynı programı "Ücretli" ve "%50 Burslu" satırlarıyla yayımlar.
Bunlar farklı ürünlerdir, tekrar değildir; "tipik ücret" sorulduğunda
hangi türden bahsedildiği AÇIKÇA belirtilir.

RAKİP KIYASI KAPSAMI TAKİP EDER
-------------------------------
Dış kurumların iç HİYERARŞİSİNİ modellemiyoruz, ama rakip tablosunda
PROGRAM ADI var. Bu yüzden kıyas kapsama göre iki ayrı biçimde yapılır:

    üniversite kapsamı  → kurum geneli medyan (eskiden beri böyle)
    fakülte / bölüm /   → yalnızca EŞDEĞER PROGRAMLAR; eşleşme
    program kapsamı       `program_equivalence` sözlüğüyle, birebir
                          kanonik anahtar eşitliğiyle kurulur

Dar kapsamda bir rakip kurumun eşdeğer programı yoksa o kurum grafikten
ÇIKARILIR; yerine kurum geneli medyanı KONMAZ. Aksi hâlde ekranda
"Yazılım Mühendisliği kıyası" yazarken sayı kurum ortalaması olurdu —
düzeltilen hata tam olarak buydu.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import CompetitorTuitionFee, Department, ProgramTuitionFee
from app.models.tuition_fee import (
    FEE_FULL,
    FEE_HALF_SCHOLARSHIP,
    FEE_TYPE_LABELS,
    LEVEL_LABELS,
)
from app.models.university_headcount import HOME_UNIVERSITY
from app.services import program_equivalence as esdeger
from app.services import tuition_provenance as prov

if TYPE_CHECKING:
    from app.services.scope import Scope


def _ondalik(d: Optional[Decimal]) -> Optional[float]:
    return None if d is None else float(d)


def _medyan(degerler: List[float]) -> Optional[float]:
    if not degerler:
        return None
    s = sorted(degerler)
    n = len(s)
    return round(float(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2), 2)


def available_years(db: Session) -> List[str]:
    return [y for (y,) in db.execute(
        select(ProgramTuitionFee.academic_year)
        .group_by(ProgramTuitionFee.academic_year)
        .order_by(ProgramTuitionFee.academic_year.desc()))]


def _kapsamli_sorgu(scope: Optional["Scope"]):
    sorgu = select(ProgramTuitionFee).options(
        selectinload(ProgramTuitionFee.academic_program),
        selectinload(ProgramTuitionFee.department),
        selectinload(ProgramTuitionFee.faculty),
    )
    if scope is None:
        return sorgu
    # EN DAR bilinen alan kullanılır. Program kimliği olmayan satır dar
    # kapsamda DIŞARIDA kalır — kapsamı bilinmeyen satırı içeride tutmak
    # tam olarak önlemek istediğimiz sızıntıdır.
    if scope.program_ids is not None and scope.level in ("program", "department"):
        return sorgu.where(
            ProgramTuitionFee.academic_program_id.in_(scope.program_ids))
    if scope.faculty_ids is not None:
        return sorgu.where(ProgramTuitionFee.faculty_id.in_(scope.faculty_ids))
    return sorgu


def _satir(f: ProgramTuitionFee) -> dict:
    return {
        "id": f.id,
        "academic_year": f.academic_year,
        "academic_program_id": f.academic_program_id,
        "program_name": (f.academic_program.name if f.academic_program
                         else f.source_program_name),
        "source_program_name": f.source_program_name,
        "department_id": f.department_id,
        "department_name": f.department.name if f.department else None,
        "faculty_id": f.faculty_id,
        "faculty_name": f.faculty.name if f.faculty else f.source_faculty_name,
        "education_language": f.education_language,
        "fee_type": f.fee_type,
        "fee_type_label": FEE_TYPE_LABELS.get(f.fee_type, f.fee_type),
        "source_fee_label": f.source_fee_label,
        "annual_fee": _ondalik(f.annual_fee),
        "currency": f.currency,
        "first_five_choice_fee": _ondalik(f.first_five_choice_fee),
        "upfront_payment_fee": _ondalik(f.upfront_payment_fee),
        "additional_fee_note": f.additional_fee_note,
        # Program kimliğine bağlanamamış satır GİZLENMEZ; işaretlenir.
        "is_matched_to_program": f.academic_program_id is not None,
    }


# ---------------------------------------------------------------------------
# ABÜ'NÜN ÜCRETİ — TEK YETKİLİ HESAP
# ---------------------------------------------------------------------------


def home_scoped_fee(db: Session, scope: Optional["Scope"],
                    academic_year: str, fee_type: str) -> dict:
    """Kapsamın kendi ücreti. EKRANDAKİ HER ABÜ SAYISI BURADAN GELİR.

    Ana ücret paneli, rakip kıyasındaki ★ çubuğu ve detay tablosu artık
    aynı fonksiyonu çağırır. Daha önce üçü de kendi medyanını ayrı ayrı
    hesaplıyordu; bugünkü veride aynı çıkıyorlardı ama bunu zorlayan bir
    şey yoktu. Aynı sayının iki yerde iki kez hesaplanması, o iki yerin
    er ya da geç ayrışması demektir.

    Kaynak DAİMA `program_tuition_fees`'tir (part3 ABÜ ücret dosyası).
    Rakip tablosu bu hesaba HİÇ girmez — orada bir "Ankara Bilim" satırı
    bulunsa bile.
    """
    sorgu = _kapsamli_sorgu(scope).where(
        ProgramTuitionFee.academic_year == academic_year,
        ProgramTuitionFee.fee_type == fee_type,
    )
    ham: List[dict] = []
    for f in db.execute(sorgu).scalars():
        ad = (f.academic_program.name if f.academic_program
              else f.source_program_name)
        ham.append({
            # Kimlik: program kaydı varsa ID, yoksa kaynaktaki ad.
            # Dil kopyalarının aynı programa ait olduğunu bu alan söyler.
            "identity": f.academic_program_id or prov._sade(ad),
            "program_name": esdeger.display_program_name(ad),
            "canonical_key": esdeger.canonical_program_key(ad),
            "academic_program_id": f.academic_program_id,
            "education_language": f.education_language
                                  or esdeger.program_language(ad),
            "annual_fee": _ondalik(f.annual_fee),
            "fee_text": "" if f.annual_fee is None else str(f.annual_fee),
            "academic_year": f.academic_year,
            "fee_type": f.fee_type,
            "source": prov.SOURCE_HOME,
            "source_dataset": f.source_dataset,
            "source_file": f.source_file,
        })

    ozet = prov.aggregate(ham)
    return {
        "university_name": HOME_UNIVERSITY,
        "is_home_institution": True,
        "authoritative": True,
        "source": prov.SOURCE_HOME,
        "academic_year": academic_year,
        "fee_type": fee_type,
        "fee_type_label": FEE_TYPE_LABELS.get(fee_type, fee_type),
        "scope_level": getattr(scope, "level", "university"),
        "scope_label": getattr(scope, "label", "Üniversite geneli"),
        **ozet,
    }


def program_fees(db: Session, scope: Optional["Scope"] = None,
                 academic_year: Optional[str] = None) -> dict:
    """Kapsamdaki programların ücret listesi ve özeti."""
    yillar = available_years(db)
    if not yillar:
        return {"available": False, "years": [], "rows": [],
                "note": "Eğitim ücreti verisi yüklenmemiş."}

    yil = academic_year or yillar[0]
    sorgu = _kapsamli_sorgu(scope).where(ProgramTuitionFee.academic_year == yil)
    satirlar = [_satir(f) for f in db.execute(sorgu).scalars()]
    satirlar.sort(key=lambda r: (-(r["annual_fee"] or 0), r["program_name"]))

    def _ozet(tur: str) -> dict:
        """Panelin KPI'ı — rakip kıyasındaki ★ çubuğuyla AYNI hesap.

        Eskiden buradaki medyan yerinde hesaplanıyordu; kıyas paneli de
        kendi medyanını ayrıca hesaplıyordu. İki hesap iki farklı yerde
        durdukça, birinin kapsamı/dil kopyalarını diğerinden farklı ele
        alması an meselesiydi. Artık ikisi de `home_scoped_fee`."""
        yetkili = home_scoped_fee(db, scope, yil, tur)
        return {
            "fee_type": tur,
            "label": FEE_TYPE_LABELS.get(tur, tur),
            "program_count": yetkili["measured_count"],
            "min_fee": yetkili["min_fee"],
            "max_fee": yetkili["max_fee"],
            "median_fee": yetkili["median_fee"],
            "aggregation": yetkili["aggregation"],
            "source": yetkili["source"],
            # Dil kopyası olduğu için medyana bir kez giren satırlar.
            "collapsed_duplicate_count": len(yetkili["collapsed_duplicate_rows"]),
        }

    return {
        "available": bool(satirlar),
        "academic_year": yil,
        "years": yillar,
        "rows": satirlar,
        "row_count": len(satirlar),
        "matched_row_count": sum(1 for r in satirlar
                                 if r["is_matched_to_program"]),
        "by_fee_type": [_ozet(t) for t in (FEE_FULL, FEE_HALF_SCHOLARSHIP)],
        "currency": "TRY",
        "source": "Ankara Bilim Üniversitesi eğitim ücretleri (part3)",
    }


def fee_trend(db: Session, scope: Optional["Scope"] = None,
              fee_type: str = FEE_HALF_SCHOLARSHIP,
              academic_year: Optional[str] = None) -> dict:
    """Kapsamın yıllara göre ücret seyri.

    Karşılaştırılabilirlik için TEK ücret türü üzerinden gidilir: tam
    ücret ile %50 burslu satırları aynı seride toplamak, indirim
    dağılımı değiştiğinde sahte bir artış/azalış üretirdi.
    """
    sorgu = _kapsamli_sorgu(scope).where(ProgramTuitionFee.fee_type == fee_type)
    if academic_year:
        # Geçmiş bir tarife dönemi seçiliyken daha sonraki ücretleri
        # grafiğe taşımak dönem sızıntısıdır.
        sorgu = sorgu.where(ProgramTuitionFee.academic_year <= academic_year)
    yillik: Dict[str, List[float]] = {}
    kaynaklar: Dict[str, List[dict]] = {}
    yetkili_program_yillari: Set[tuple[str, int]] = set()
    for f in db.execute(sorgu).scalars():
        if f.annual_fee is None:
            continue
        yillik.setdefault(f.academic_year, []).append(float(f.annual_fee))
        kaynaklar.setdefault(f.academic_year, []).append({
            "source_type": "authoritative",
            "source_label": "Kurumun yayımladığı yetkili eğitim ücreti tarifesi",
            "provenance": "Yetkili tarife",
            "is_synthetic": False,
            "uploaded_source_id": None,
            "filename": f.source_file,
        })
        if f.academic_program_id is not None:
            yetkili_program_yillari.add((f.academic_year, f.academic_program_id))

    # Yalnızca %50 burslu seri için, gerçek tarifenin bulunmadığı geçmiş
    # program-yıl kimliklerini yönetilen backcast satırlarıyla tamamla.
    # Aynı program-yılda gerçek satır varsa yukarıdaki kimlik kümesi her
    # koşulda kazanır; yüklenmiş değer grafiğe hiç girmez.
    if fee_type == FEE_HALF_SCHOLARSHIP:
        from app.services import data_source_service

        governed = data_source_service.governed_records(
            db,
            metric_keys=("historical_half_tuition_fee_estimate",),
            scope=scope,
            record_scope_type="program",
            entity_type="academic_program",
        )
        for row in governed:
            year = row["academic_year"]
            program_id = row["program_id"]
            if academic_year and year > academic_year:
                continue
            if program_id is None or (year, program_id) in yetkili_program_yillari:
                continue
            yillik.setdefault(year, []).append(float(row["value"]))
            kaynaklar.setdefault(year, []).append({
                "source_type": row.get("source_type"),
                "source_label": row.get("source_label"),
                "provenance": row.get("provenance"),
                "is_synthetic": row.get("is_synthetic", False),
                "uploaded_source_id": row.get("uploaded_source_id"),
                "filename": row.get("filename"),
            })

    seri = []
    for i, yil in enumerate(sorted(yillik)):
        degerler = yillik[yil]
        onceki = sorted(yillik)[i - 1] if i else None
        onceki_medyan = _medyan(yillik[onceki]) if onceki else None
        medyan = _medyan(degerler)
        yil_kaynaklari = kaynaklar.get(yil, [])
        sentetik = [row for row in yil_kaynaklari if row.get("is_synthetic")]
        yetkili = [row for row in yil_kaynaklari if not row.get("is_synthetic")]
        if sentetik and yetkili:
            source_type = "mixed"
            source_label = "Yetkili tarife + yönetilen tarihsel tahmin"
            provenance = "Karma kaynak; program-yıl bazında yetkili tarife önceliklidir"
            uploaded_source_id = None
            filename = None
        elif sentetik:
            source_type = "uploaded"
            source_label = sentetik[0].get("source_label")
            provenance = "SYNTHETIC_GENERATED"
            ids = {row.get("uploaded_source_id") for row in sentetik}
            files = {row.get("filename") for row in sentetik if row.get("filename")}
            uploaded_source_id = next(iter(ids)) if len(ids) == 1 else None
            filename = next(iter(files)) if len(files) == 1 else None
        else:
            source_type = "authoritative"
            source_label = "Kurumun yayımladığı yetkili eğitim ücreti tarifesi"
            provenance = "Yetkili tarife"
            uploaded_source_id = None
            filename = next((row.get("filename") for row in yetkili if row.get("filename")), None)
        seri.append({
            "academic_year": yil,
            "program_count": len(degerler),
            "median_fee": medyan,
            "min_fee": min(degerler),
            "max_fee": max(degerler),
            "change_percent": (
                round((medyan - onceki_medyan) / onceki_medyan * 100, 2)
                if medyan is not None and onceki_medyan else None),
            "source_type": source_type,
            "source_label": source_label,
            "provenance": provenance,
            "is_synthetic": bool(sentetik),
            "uploaded_source_id": uploaded_source_id,
            "filename": filename,
        })
    return {
        "available": len(seri) > 0,
        "requested_period": academic_year,
        "fee_type": fee_type,
        "fee_type_label": FEE_TYPE_LABELS.get(fee_type, fee_type),
        "years": seri,
        "currency": "TRY",
        "source_type": (
            "mixed" if any(row["is_synthetic"] for row in seri)
            and any(not row["is_synthetic"] for row in seri)
            else (seri[0]["source_type"] if seri else None)
        ),
        "provenance": (
            "Karma kaynak; gerçek program-yıl tarifesi yönetilen tahmini geçersiz kılar"
            if any(row["is_synthetic"] for row in seri)
            and any(not row["is_synthetic"] for row in seri)
            else (seri[0]["provenance"] if seri else None)
        ),
    }


# ---------------------------------------------------------------------------
# Rakip kıyası — KAPSAMA GÖRE
# ---------------------------------------------------------------------------


def competitor_years(db: Session) -> List[str]:
    return [y for (y,) in db.execute(
        select(CompetitorTuitionFee.academic_year)
        .group_by(CompetitorTuitionFee.academic_year)
        .order_by(CompetitorTuitionFee.academic_year.desc()))]


def _kapsam_program_anahtarlari(
    db: Session, scope: Optional["Scope"], yil: str, fee_type: str,
) -> tuple:
    """Kapsamdaki programların kanonik anahtarları ve öğretim dilleri.

    Anahtar kümesi KAPSAMDAN çıkar: hangi programları kıyaslayacağımıza
    seçili bölüm/fakülte karar verir. Anahtarı olmayan (toplu) kendi
    satırlarımız da elenir — kendi tarafımızda da kurum ortalaması
    kullanmayız.
    """
    sorgu = _kapsamli_sorgu(scope).where(
        ProgramTuitionFee.academic_year == yil,
        ProgramTuitionFee.fee_type == fee_type,
    )
    anahtarlar: Dict[str, dict] = {}
    for f in db.execute(sorgu).scalars():
        ad = (f.academic_program.name if f.academic_program
              else f.source_program_name)
        k = esdeger.canonical_program_key(ad)
        if not k:
            continue
        kayit = anahtarlar.setdefault(k, {"adlar": set(), "diller": set(),
                                          "ucretler": [], "satirlar": []})
        gosterim = esdeger.display_program_name(ad)
        kayit["adlar"].add(gosterim)
        # Dil önce sütundan, yoksa adın parantezinden okunur; yoksa None.
        dil = f.education_language or esdeger.program_language(ad)
        if dil:
            kayit["diller"].add(dil)
        if f.annual_fee is not None:
            kayit["ucretler"].append(float(f.annual_fee))
        kayit["satirlar"].append({
            "program_name": gosterim, "canonical_key": k, "level": None,
            "education_language": dil, "annual_fee": _ondalik(f.annual_fee),
            "fee_text": "", "unit_name": None,
        })
    return anahtarlar


def _rakip_program_kohortu(
    db: Session, yil: str, fee_type: str, anahtarlar: Dict[str, dict],
) -> Dict[str, dict]:
    """Eşdeğer programı olan rakip kurumlar.

    KURAL: kanonik anahtar BİREBİR eşit olacak. Toplu satırlar (kurum ya
    da fakülte geneli fiyatlar) `canonical_program_key` tarafından zaten
    `None` döndüğü için buraya hiç gelmez.
    """
    bizim_diller: Set[str] = set()
    for v in anahtarlar.values():
        bizim_diller |= v["diller"]

    kurumlar: Dict[str, dict] = {}
    elenen_ev: List[dict] = []
    sorgu = select(CompetitorTuitionFee).where(
        CompetitorTuitionFee.academic_year == yil,
        CompetitorTuitionFee.fee_type == fee_type,
    )
    for f in db.execute(sorgu).scalars():
        k = esdeger.canonical_program_key(f.program_name)
        if not k or k not in anahtarlar:
            continue
        # KAYNAK ÖNCELİĞİ: rakip tablosunda kendi kurumumuza ait bir satır
        # bulunursa AKRAN SAYILMAZ. ABÜ'nün ücreti yalnızca yetkili
        # kaynaktan (program_tuition_fees) okunur. Satır sessizce
        # yutulmaz; hangi satırın neden elendiği bildirilir.
        if prov.is_home_university(f.university_name):
            elenen_ev.append({
                "university_name": f.university_name,
                "program_name": f.program_name,
                "academic_year": f.academic_year,
                "fee_type": f.fee_type,
                "annual_fee": _ondalik(f.annual_fee),
                "fee_text": f.fee_text,
                "source": prov.SOURCE_COMPETITOR,
                "reason": ("Kendi kurumumuzun ücreti yetkili kaynaktan "
                           "okunur; rakip dosyasındaki kopyası kullanılmaz."),
            })
            continue
        dil = esdeger.program_language(f.program_name)
        kurum = kurumlar.setdefault(f.university_name, {
            "university_name": f.university_name,
            "benchmark_institution_id": f.benchmark_institution_id,
            "is_home_institution": False,
            "eslesen": [],
        })
        kurum["eslesen"].append({
            # Kimlik: dil kopyalarını tanımak için program adının
            # DİLDEN ARINDIRILMIŞ hâli kullanılır.
            "identity": (f.university_name, k),
            "program_name": f.program_name,
            "canonical_key": k,
            "level": f.level,
            "education_language": dil,
            "annual_fee": _ondalik(f.annual_fee),
            "fee_text": f.fee_text,
            "unit_name": f.unit_name,
            "academic_year": f.academic_year,
            "fee_type": f.fee_type,
            "source": prov.SOURCE_COMPETITOR,
            "source_dataset": f.source_dataset,
            "source_file": f.source_file,
        })

    # DİL TERCİHİ: aynı dilde eşdeğer varsa yalnızca onlar kullanılır.
    # Dil bilgisi yoksa satır ELENMEZ; sınırlılık üst veride bildirilir.
    for kurum in kurumlar.values():
        ayni = [r for r in kurum["eslesen"]
                if r["education_language"] and r["education_language"] in bizim_diller]
        if ayni and bizim_diller:
            kurum["eslesen"] = ayni
            kurum["language_match"] = "ayni"
        elif any(r["education_language"] for r in kurum["eslesen"]) and bizim_diller:
            kurum["language_match"] = "farkli"
        else:
            kurum["language_match"] = "belirtilmemis"
    return kurumlar, elenen_ev


def scoped_competitor_comparison(
    db: Session, scope: Optional["Scope"] = None,
    academic_year: Optional[str] = None,
    fee_type: str = FEE_HALF_SCHOLARSHIP,
    level: Optional[str] = None,
) -> dict:
    """Kapsamı takip eden rakip ücret kıyası.

    Üniversite kapsamında kurum medyanlarına düşer (eski davranış).
    Fakülte/bölüm/program kapsamında YALNIZCA eşdeğer programları
    kıyaslar; eşdeğeri olmayan kurum listeden çıkar.

    Akademik yıl SEÇİLDİĞİ GİBİ kullanılır. Seçili yılda kıyaslanabilir
    veri yoksa başka yıla düşülmez; sonuç "veri yok" olur.
    """
    seviye = getattr(scope, "level", None) or "university"
    if scope is None or seviye == "university":
        return competitor_fee_comparison(db, academic_year, fee_type,
                                        level, scope)

    yillar = competitor_years(db)
    kendi_yillar = available_years(db)
    if not yillar:
        return {"available": False, "mode": "program", "universities": [],
                "years": [], "unavailable_reason": "Rakip ücret verisi yüklenmemiş."}

    # SESSİZ YIL DEĞİŞTİRME YOK: kullanıcı bir dönem seçtiyse o dönem
    # kullanılır. Seçim yoksa en güncel rakip yılı alınır.
    yil = academic_year or yillar[0]
    kapsam_adi = getattr(scope, "label", "Seçili kapsam")

    anahtarlar = _kapsam_program_anahtarlari(db, scope, yil, fee_type)
    tur_etiketi = FEE_TYPE_LABELS.get(fee_type, fee_type)

    if not anahtarlar:
        neden = (f"{kapsam_adi} için {yil} döneminde {tur_etiketi} "
                 f"ücret kaydı yok.")
        if yil not in kendi_yillar:
            neden = (f"{yil} döneminde kendi ücret verimiz bulunmuyor; "
                     f"başka bir yılın ücreti KULLANILMAZ.")
        return {"available": False, "mode": "program", "universities": [],
                "years": yillar, "academic_year": yil, "fee_type": fee_type,
                "fee_type_label": tur_etiketi, "scope_label": kapsam_adi,
                "scope_level": seviye, "program_labels": [],
                "unavailable_reason": neden}

    kurumlar, elenen_ev = _rakip_program_kohortu(db, yil, fee_type, anahtarlar)

    satirlar = []
    metin_sayisi = 0
    for kurum in kurumlar.values():
        # AKRANLAR DA AYNI KURALLA toplanır: dil kopyaları birleşir,
        # medyan alınır. Ev sahibiyle akranın farklı kurallarla
        # hesaplanması kıyası anlamsız kılardı.
        ozet = prov.aggregate(kurum["eslesen"])
        metin_sayisi += ozet["text_only_count"]
        satirlar.append({
            "university_name": kurum["university_name"],
            "benchmark_institution_id": kurum["benchmark_institution_id"],
            "is_home_institution": False,
            "authoritative": False,
            "source": prov.SOURCE_COMPETITOR,
            "program_count": len(kurum["eslesen"]),
            "text_only_count": ozet["text_only_count"],
            "measured_count": ozet["measured_count"],
            "median_fee": ozet["median_fee"],
            "min_fee": ozet["min_fee"],
            "max_fee": ozet["max_fee"],
            "aggregation": ozet["aggregation"],
            "language_match": kurum["language_match"],
            "matched_programs": ozet["source_rows"],
            "collapsed_duplicate_rows": ozet["collapsed_duplicate_rows"],
        })

    # KENDİ DEĞERİMİZ — YETKİLİ KAYNAKTAN, ana ücret paneliyle AYNI
    # fonksiyondan. Burada ayrı bir medyan hesaplanmaz.
    yetkili = home_scoped_fee(db, scope, yil, fee_type)
    kendi_adlar = sorted({a for v in anahtarlar.values() for a in v["adlar"]})
    kendi_diller = sorted({d for v in anahtarlar.values() for d in v["diller"]})
    if yetkili["measured_count"]:
        satirlar.append({
            "university_name": HOME_UNIVERSITY,
            "benchmark_institution_id": None,
            "is_home_institution": True,
            "authoritative": True,
            "source": yetkili["source"],
            "program_count": yetkili["measured_count"],
            "text_only_count": yetkili["text_only_count"],
            "measured_count": yetkili["measured_count"],
            "median_fee": yetkili["median_fee"],
            "min_fee": yetkili["min_fee"],
            "max_fee": yetkili["max_fee"],
            "aggregation": yetkili["aggregation"],
            "language_match": "ayni",
            "matched_programs": yetkili["source_rows"],
            "collapsed_duplicate_rows": yetkili["collapsed_duplicate_rows"],
        })

    olculen = [r for r in satirlar if r["median_fee"] is not None]
    olculen.sort(key=lambda r: -r["median_fee"])
    for i, r in enumerate(olculen, start=1):
        r["rank"] = i
    satirlar.sort(key=lambda r: (r["median_fee"] is None, -(r["median_fee"] or 0)))

    biz = next((r for r in olculen if r["is_home_institution"]), None)
    rakip_sayisi = len([r for r in olculen if not r["is_home_institution"]])
    kohort_medyani = _medyan([r["median_fee"] for r in olculen])

    # Etiketler KENDİ program adlarımızdır: kanonik anahtar bir kimliktir,
    # ekranda gösterilecek ad değildir.
    etiketler = kendi_adlar or esdeger.describe_keys(anahtarlar.keys())
    program_adi = (etiketler[0] if len(etiketler) == 1
                   else esdeger.display_program_name(kapsam_adi))

    if seviye == "faculty":
        baslik = ("Rakip Üniversitelerde "
                  f"{esdeger.display_program_name(kapsam_adi)} "
                  "Programları Ücret Karşılaştırması")
        kapsam_notu = "fakültedeki programların eşdeğerleri"
    else:
        baslik = f"Rakip Üniversitelerde {program_adi} Ücret Karşılaştırması"
        kapsam_notu = "aynı/eşdeğer programlar"

    dil_notu = ""
    if kendi_diller:
        farkli = [r for r in satirlar
                  if not r["is_home_institution"]
                  and r["language_match"] != "ayni"]
        if farkli:
            dil_notu = (f" · {len(farkli)} kurumda öğretim dili "
                        f"eşleşmedi/belirtilmemiş")

    return {
        "available": rakip_sayisi >= 1,
        "mode": "program",
        "scope_level": seviye,
        "scope_label": kapsam_adi,
        "academic_year": yil,
        "years": yillar,
        "fee_type": fee_type,
        "fee_type_label": tur_etiketi,
        "level": level,
        "level_label": LEVEL_LABELS.get(level) if level else "Tüm düzeyler",
        "program_keys": sorted(anahtarlar.keys()),
        "program_labels": etiketler,
        "home_program_names": kendi_adlar,
        "home_languages": kendi_diller,
        "universities": satirlar,
        "university_count": len(satirlar),
        "measured_university_count": len(olculen),
        "competitor_count": rakip_sayisi,
        "title": baslik,
        "subtitle": f"{yil} · {tur_etiketi} · {kapsam_notu}{dil_notu}",
        "coverage_note": (f"{rakip_sayisi} rakip kurumda eşdeğer program"
                          if rakip_sayisi else "eşdeğer program bulunamadı"),
        "text_only_row_count": metin_sayisi,
        "cohort_median": kohort_medyani,
        "aggregation": prov.AGGREGATION_MEDIAN,
        "home_source": prov.SOURCE_HOME,
        "peer_source": prov.SOURCE_COMPETITOR,
        # Rakip dosyasında kendi kurumumuza ait satır çıkarsa burada
        # görünür; akran havuzuna ALINMAZ.
        "excluded_home_rows_from_peer_source": elenen_ev,
        "home": ({
            "university_name": HOME_UNIVERSITY,
            "median_fee": biz["median_fee"],
            "min_fee": biz["min_fee"],
            "max_fee": biz["max_fee"],
            "rank": biz["rank"],
            "cohort_size": len(olculen),
            "program_names": kendi_adlar,
            "difference_from_median": (round(biz["median_fee"] - kohort_medyani, 2)
                                       if kohort_medyani is not None else None),
        } if biz else None),
        "currency": "TRY",
        "unavailable_reason": (None if rakip_sayisi else
                               (f"{yil} döneminde {tur_etiketi} türünde "
                                f"karşılaştırılabilir program verisi yok.")),
        "note": ("Kurum geneli medyanlar KULLANILMAZ; eşdeğer programı "
                 "olmayan kurum listeye alınmaz."),
    }


def competitor_fee_comparison(
    db: Session, academic_year: Optional[str] = None,
    fee_type: str = FEE_HALF_SCHOLARSHIP, level: Optional[str] = None,
    scope: Optional["Scope"] = None,
) -> dict:
    """Kurum başına ücret aralığı ve medyan — kendi kurumumuz dâhil.

    Aralık metni olarak yayımlanan ücretler (ör. "386.000 TL - 410.000
    TL") sayısal olmadığı için hesaba GİRMEZ; kaç satırın bu yüzden
    dışarıda kaldığı ayrıca bildirilir.
    """
    yillar = [y for (y,) in db.execute(
        select(CompetitorTuitionFee.academic_year)
        .group_by(CompetitorTuitionFee.academic_year)
        .order_by(CompetitorTuitionFee.academic_year.desc()))]
    if not yillar:
        return {"available": False, "universities": [], "years": []}

    yil = academic_year or yillar[0]

    sorgu = select(CompetitorTuitionFee).where(
        CompetitorTuitionFee.academic_year == yil,
        CompetitorTuitionFee.fee_type == fee_type,
    )
    if level:
        sorgu = sorgu.where(CompetitorTuitionFee.level == level)

    kurumlar: Dict[str, dict] = {}
    elenen_ev: List[dict] = []
    metin_sayisi = 0
    for f in db.execute(sorgu).scalars():
        # KAYNAK ÖNCELİĞİ üniversite kapsamında da geçerlidir: rakip
        # dosyasındaki bir ABÜ satırı ikinci bir ABÜ çubuğu üretemez.
        if prov.is_home_university(f.university_name):
            elenen_ev.append({
                "university_name": f.university_name,
                "program_name": f.program_name,
                "academic_year": f.academic_year, "fee_type": f.fee_type,
                "annual_fee": _ondalik(f.annual_fee), "fee_text": f.fee_text,
                "source": prov.SOURCE_COMPETITOR,
                "reason": ("Kendi kurumumuzun ücreti yetkili kaynaktan "
                           "okunur; rakip dosyasındaki kopyası kullanılmaz."),
            })
            continue
        k = kurumlar.setdefault(f.university_name, {
            "university_name": f.university_name,
            "benchmark_institution_id": f.benchmark_institution_id,
            "is_home_institution": False,
            "fees": [], "text_only_count": 0, "program_count": 0,
        })
        k["program_count"] += 1
        if f.annual_fee is None:
            k["text_only_count"] += 1
            metin_sayisi += 1
            continue
        k["fees"].append(float(f.annual_fee))

    # KENDİ DEĞERİMİZ — ana ücret paneliyle AYNI yetkili fonksiyondan.
    # Eskiden burada kapsamsız, ayrı bir sorgu vardı; o sorgu kapsam ne
    # olursa olsun ÜNİVERSİTE GENELİ medyanı döndürüyordu.
    yetkili = home_scoped_fee(db, scope, yil, fee_type)
    if yetkili["measured_count"]:
        kurumlar[HOME_UNIVERSITY] = {
            "university_name": HOME_UNIVERSITY,
            "benchmark_institution_id": None,
            "is_home_institution": True,
            "yetkili": yetkili,
            "fees": [r["annual_fee"] for r in yetkili["source_rows"]
                     if r["annual_fee"] is not None],
            "text_only_count": yetkili["text_only_count"],
            "program_count": yetkili["measured_count"],
        }

    satirlar = []
    for k in kurumlar.values():
        if not k["fees"]:
            # Yalnızca aralık metni yayımlamış kurum: sayı YOK, uydurulmaz.
            satirlar.append({**{a: k[a] for a in
                                ("university_name", "benchmark_institution_id",
                                 "is_home_institution", "program_count",
                                 "text_only_count")},
                             "median_fee": None, "min_fee": None,
                             "max_fee": None, "measured_count": 0})
            continue
        y = k.get("yetkili")
        satirlar.append({
            "university_name": k["university_name"],
            "benchmark_institution_id": k["benchmark_institution_id"],
            "is_home_institution": k["is_home_institution"],
            "authoritative": bool(y),
            "source": prov.SOURCE_HOME if y else prov.SOURCE_COMPETITOR,
            "program_count": k["program_count"],
            "text_only_count": k["text_only_count"],
            "measured_count": y["measured_count"] if y else len(k["fees"]),
            "median_fee": y["median_fee"] if y else _medyan(k["fees"]),
            "min_fee": y["min_fee"] if y else min(k["fees"]),
            "max_fee": y["max_fee"] if y else max(k["fees"]),
            "aggregation": prov.AGGREGATION_MEDIAN,
        })

    olculen = [r for r in satirlar if r["median_fee"] is not None]
    olculen.sort(key=lambda r: -r["median_fee"])
    for i, r in enumerate(olculen, start=1):
        r["rank"] = i
    satirlar.sort(key=lambda r: (r["median_fee"] is None,
                                 -(r["median_fee"] or 0)))

    biz = next((r for r in olculen if r["is_home_institution"]), None)
    medyanlar = [r["median_fee"] for r in olculen]
    kohort_medyani = _medyan(medyanlar)

    return {
        "available": len(olculen) >= 2,
        "mode": "university",
        "scope_level": "university",
        "scope_label": "Üniversite geneli",
        "title": "Rakip Üniversitelerle Ücret Karşılaştırması",
        "subtitle": (f"{yil} · {FEE_TYPE_LABELS.get(fee_type, fee_type)} · "
                     "kurum medyanları"),
        "academic_year": yil,
        "years": yillar,
        "fee_type": fee_type,
        "fee_type_label": FEE_TYPE_LABELS.get(fee_type, fee_type),
        "level": level,
        "level_label": LEVEL_LABELS.get(level) if level else "Tüm düzeyler",
        "universities": satirlar,
        "university_count": len(satirlar),
        "measured_university_count": len(olculen),
        "coverage_note": f"{len(olculen)} / {len(satirlar)} kurumda sayısal ücret",
        "text_only_row_count": metin_sayisi,
        "cohort_median": kohort_medyani,
        "aggregation": prov.AGGREGATION_MEDIAN,
        "home_source": prov.SOURCE_HOME,
        "peer_source": prov.SOURCE_COMPETITOR,
        # Rakip dosyasında kendi kurumumuza ait satır çıkarsa burada
        # görünür; akran havuzuna ALINMAZ.
        "excluded_home_rows_from_peer_source": elenen_ev,
        "home": ({
            "university_name": HOME_UNIVERSITY,
            "median_fee": biz["median_fee"],
            "min_fee": biz["min_fee"],
            "max_fee": biz["max_fee"],
            "rank": biz["rank"],
            "cohort_size": len(olculen),
            "difference_from_median": (round(biz["median_fee"] - kohort_medyani, 2)
                                       if kohort_medyani is not None else None),
        } if biz else None),
        "currency": "TRY",
        "note": ("Aralık olarak yayımlanan ücretler sayısal olmadığı için "
                 "medyan/min/maks hesabına girmez."),
    }
