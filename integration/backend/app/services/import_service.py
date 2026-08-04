"""Toplu veri aktarımının ana iş mantığı.

Dosya okuma (file_parser) ve satır doğrulama (import_validators) adımlarını birleştirip
veritabanına yazma ve raporlama işini yürütür.
"""

import csv
import io
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import ImportJob
from app.schemas.data_integration import ImportResult, RowIssue
from app.services.file_parser import FileParseError, parse_file
from app.services.import_validators import (
    RESOURCE_SPECS,
    ResourceSpec,
    get_resource_spec,
    normalize_code,
    validate_row,
)

# Ön izlemede kullanıcıya gösterilecek örnek kayıt sayısı.
PREVIEW_LIMIT: int = 10


def _normalize_key_part(value: Any) -> str:
    """Benzersizlik anahtarının tek bir parçasını karşılaştırılabilir metne çevirir."""
    # Kod ve numaralar büyük harfe çevrilir; sayısal id'ler metne dönüştürülür.
    # Böylece "SWE" ile "swe " ya da 5 ile "5" aynı anahtar sayılır.
    return str(value if value is not None else "").strip().upper()


def _load_existing_keys(db: Session, spec: ResourceSpec) -> Set[Tuple[str, ...]]:
    """Hedef tabloda hâlihazırda bulunan benzersizlik anahtarlarını getirir."""
    # Her satır için ayrı sorgu atmak yerine anahtarları tek seferde belleğe alıyoruz.
    # Bu, büyük dosyalarda yüzlerce gereksiz sorgu yapılmasını önler.
    columns = [getattr(spec.model, field_name) for field_name in spec.unique_fields]
    statement = select(*columns)
    return {
        tuple(_normalize_key_part(value) for value in row)
        for row in db.execute(statement).all()
    }


def _row_key(spec: ResourceSpec, cleaned: Dict[str, Any]) -> Tuple[str, ...]:
    """Temizlenmiş satır verisinden benzersizlik anahtarını üretir."""
    return tuple(_normalize_key_part(cleaned.get(name)) for name in spec.unique_fields)


def _key_display(spec: ResourceSpec, key: Tuple[str, ...]) -> str:
    """Anahtarı kullanıcıya gösterilecek okunabilir metne çevirir."""
    # Tek alanlı anahtarlarda sadece değeri, bileşik anahtarlarda tüm parçaları gösteriyoruz.
    return " | ".join(key)


def _load_parent_maps(db: Session, spec: ResourceSpec) -> Dict[str, Dict[str, int]]:
    """Her üst kaynak için kod -> id eşlemesini hazırlar.

    Dosyada faculty_code / indicator_code / benchmark_institution_name geliyor ama
    veritabanı id istiyor. Bu sözlükler sayesinde dönüşüm satır başına sorgu
    atmadan yapılabiliyor. Bir kaynağın birden fazla üst kaydı olabilir.
    """
    maps: Dict[str, Dict[str, int]] = {}
    for parent in spec.parents:
        key_column = getattr(parent.model, parent.key_column)
        statement = select(key_column, parent.model.id)
        maps[parent.lookup_column] = {
            normalize_code(code): row_id for code, row_id in db.execute(statement).all()
        }
    return maps


def _create_job_record(
    db: Session,
    result: ImportResult,
) -> Optional[int]:
    """Sonuç raporunu ImportJob tablosuna kaydeder ve iş id'sini döndürür."""
    # Ön izlemeler de kaydedilir; böylece kullanıcının hangi dosyayı ne zaman
    # denediği geçmişte görünür.
    job = ImportJob(
        resource_type=result.resource_type,
        file_name=result.file_name,
        file_type=result.file_type,
        preview=result.preview,
        total_rows=result.total_rows,
        valid_rows=result.valid_rows,
        imported_rows=result.imported_rows,
        error_rows=result.error_rows,
        conflict_rows=result.conflict_rows,
        status=result.status,
        message=result.message,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.id


def run_import(
    db: Session,
    resource_type: str,
    file_name: str,
    content: bytes,
    preview: bool,
) -> ImportResult:
    """Yüklenen dosyayı doğrular, gerekiyorsa veritabanına aktarır ve rapor döndürür."""
    spec: ResourceSpec = get_resource_spec(resource_type)

    # 1) Dosyayı oku. Okuma hatası olursa başarısız bir iş kaydı bırakıp hatayı yukarı iletiyoruz.
    try:
        file_type, rows = parse_file(file_name, content)
    except FileParseError as error:
        failed_result = ImportResult(
            resource_type=resource_type,
            file_name=file_name,
            file_type=file_name.split(".")[-1].lower() if "." in file_name else "unknown",
            preview=preview,
            status="failed",
            message=error.message,
        )
        _create_job_record(db, failed_result)
        raise

    result = ImportResult(
        resource_type=resource_type,
        file_name=file_name,
        file_type=file_type,
        preview=preview,
        total_rows=len(rows),
    )

    existing_keys: Set[Tuple[str, ...]] = _load_existing_keys(db, spec)
    parent_maps: Dict[str, Dict[str, int]] = _load_parent_maps(db, spec)

    # Dosya içindeki tekrarları yakalamak için gördüğümüz anahtarları biriktiriyoruz.
    seen_keys: Set[Tuple[str, ...]] = set()

    # Hata mesajlarında hangi alanın çakıştığını göstermek için kullanılır.
    unique_field_label: str = ", ".join(spec.unique_fields)

    issues: List[RowIssue] = []
    importable_rows: List[Dict[str, Any]] = []
    error_row_count: int = 0
    conflict_row_count: int = 0

    # 2) Satırları tek tek doğrula
    for index, row in enumerate(rows, start=1):
        cleaned, row_issues = validate_row(spec, row)

        # Üst kayıt kontrolü: her kod geçerli mi?
        parent_codes: Dict[str, str] = cleaned.pop("_parent_codes", {}) or {}
        for parent in spec.parents:
            parent_code: str = str(parent_codes.get(parent.lookup_column, "") or "")
            if parent_code == "":
                # Zorunlu alan kontrolü bunu zaten yakalar; burada tekrar hata eklemiyoruz.
                continue

            lookup_map: Dict[str, int] = parent_maps.get(parent.lookup_column, {})
            if parent_code not in lookup_map:
                row_issues.append(
                    (
                        parent.lookup_column,
                        parent_code,
                        f"'{parent_code}' koduna sahip {parent.label} bulunamadı.",
                    )
                )
            else:
                cleaned[parent.fk_field] = lookup_map[parent_code]

        if row_issues:
            error_row_count += 1
            for field_name, value, message in row_issues:
                issues.append(
                    RowIssue(
                        row=index,
                        field=field_name,
                        value=value,
                        message=message,
                        issue_type="error",
                    )
                )
            continue

        # 3) Çakışma kontrolü: satır doğrulamayı geçti ama anahtar zaten kullanılıyor olabilir.
        row_key: Tuple[str, ...] = _row_key(spec, cleaned)
        key_text: str = _key_display(spec, row_key)

        if row_key in seen_keys:
            conflict_row_count += 1
            issues.append(
                RowIssue(
                    row=index,
                    field=unique_field_label,
                    value=key_text,
                    message=f"'{key_text}' kodu dosya içinde birden fazla kez kullanılmış.",
                    issue_type="conflict",
                )
            )
            continue

        seen_keys.add(row_key)

        if row_key in existing_keys:
            conflict_row_count += 1
            issues.append(
                RowIssue(
                    row=index,
                    field=unique_field_label,
                    value=key_text,
                    message=f"'{key_text}' kodu veritabanında zaten mevcut.",
                    issue_type="conflict",
                )
            )
            continue

        # Aktarılmaya hazır satır
        importable_rows.append(cleaned)

    # 4) Sayısal özeti doldur
    result.error_rows = error_row_count
    result.conflict_rows = conflict_row_count
    result.valid_rows = result.total_rows - error_row_count
    result.errors = issues
    result.preview_rows = [dict(row) for row in importable_rows[:PREVIEW_LIMIT]]

    # 5) Ön izleme modunda veritabanına hiçbir şey yazmıyoruz.
    if preview:
        result.imported_rows = 0
        result.status = "preview"
        result.message = (
            f"Ön izleme: {len(importable_rows)} satır aktarılmaya hazır. "
            "Veritabanına hiçbir kayıt yazılmadı."
        )
        result.job_id = _create_job_record(db, result)
        return result

    # 6) Gerçek aktarım
    imported_count: int = 0
    try:
        for offset, row_data in enumerate(importable_rows):
            # begin_nested() her satır için bir SAVEPOINT açar.
            # Böylece bir satırda beklenmedik bir veritabanı hatası olursa
            # sadece o satır geri alınır, önceki geçerli satırlar korunur.
            try:
                with db.begin_nested():
                    db.add(spec.model(**row_data))
                imported_count += 1
            except SQLAlchemyError as row_error:
                # Satır bazlı hata: kaydı atla, kullanıcıya bildir, işleme devam et.
                issues.append(
                    RowIssue(
                        row=offset + 1,
                        field=None,
                        value=_key_display(spec, _row_key(spec, row_data)),
                        message=f"Kayıt eklenemedi: {row_error.__class__.__name__}",
                        issue_type="error",
                    )
                )

        # Tüm satırlar işlendikten sonra tek bir commit ile kalıcı hâle getiriyoruz.
        db.commit()

    except SQLAlchemyError as error:
        # Beklenmeyen bir hata (bağlantı kopması, disk hatası vb.) olursa
        # yarım kalmış veri bırakmamak için tüm işlem geri alınır.
        db.rollback()
        result.imported_rows = 0
        result.status = "failed"
        result.message = f"Aktarım sırasında veritabanı hatası oluştu, işlem geri alındı: {error}"
        result.job_id = _create_job_record(db, result)
        return result

    result.imported_rows = imported_count

    # Durum bilgisi kullanıcıya tek bakışta sonucu anlatır:
    #   completed -> her satır aktarıldı
    #   partial   -> bir kısmı aktarıldı, bir kısmı atlandı
    #   skipped   -> hiçbir satır aktarılamadı ama sistemsel bir hata yok
    #                (tüm satırlar hatalı veya zaten mevcut)
    #   failed    -> dosya okunamadı ya da veritabanı hatası oluştu
    if imported_count == result.total_rows:
        result.status = "completed"
        result.message = f"{imported_count} satır başarıyla aktarıldı."
    elif imported_count == 0:
        result.status = "skipped"
        result.message = (
            "Hiçbir satır aktarılmadı: "
            f"{error_row_count} satır hatalı, {conflict_row_count} satır zaten mevcut."
        )
    else:
        result.status = "partial"
        result.message = (
            f"{imported_count} satır aktarıldı, "
            f"{error_row_count} satır hatalı, {conflict_row_count} satır çakışmalı olduğu için atlandı."
        )

    result.errors = issues
    result.job_id = _create_job_record(db, result)
    return result


def build_csv_template(resource_type: str) -> str:
    """Kaynak için sadece başlık satırından oluşan boş CSV şablonu üretir."""
    # Kullanıcının hangi sütunları hangi isimle göndermesi gerektiğini
    # tahmin etmesini beklemek yerine hazır şablon sunuyoruz.
    spec: ResourceSpec = get_resource_spec(resource_type)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(spec.columns)
    return buffer.getvalue()


def get_supported_resources() -> List[str]:
    """Desteklenen kanonik kaynak türlerinin listesini döndürür."""
    # Takma adlar (alt çizgili yazımlar) listede tekrar gösterilmez;
    # arayüzde tek bir kanonik isim listesi görünsün diye ayıklanır.
    from app.services.import_validators import RESOURCE_TYPE_ALIASES

    return [key for key in RESOURCE_SPECS if key not in RESOURCE_TYPE_ALIASES]


def get_resource_aliases() -> Dict[str, str]:
    """Takma ad -> kanonik isim eşlemesini döndürür."""
    from app.services.import_validators import RESOURCE_TYPE_ALIASES

    return dict(RESOURCE_TYPE_ALIASES)
