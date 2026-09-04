"""İş mantığı ve ortak yardımcı fonksiyonların bulunduğu paket."""

# Router'lar sadece HTTP ile ilgilensin, tekrar eden kontroller burada dursun diye ayrıldı.
from app.services.crud_helpers import (
    apply_updates,
    ensure_code_is_unique,
    ensure_parent_exists,
    get_object_or_404,
)
from app.services.file_parser import FileParseError, detect_file_type, parse_file
from app.services.import_service import (
    build_csv_template,
    get_supported_resources,
    run_import,
)

from app.services.ranking_benchmark_service import build_comparison
from app.services.ranking_calculation_service import (
    evaluate_framework,
    persist_assessment,
)
from app.services.ranking_impact_service import build_impact_preview
from app.services.ranking_recommendation_service import build_recommendations
from app.services.ranking_student_sync_service import sync_student_metrics

__all__ = [
    "get_object_or_404",
    "ensure_code_is_unique",
    "ensure_parent_exists",
    "apply_updates",
    "FileParseError",
    "parse_file",
    "detect_file_type",
    "run_import",
    "build_csv_template",
    "get_supported_resources",
    # Modül 10 - THE / QS / YÖK değerlendirme
    "evaluate_framework",
    "persist_assessment",
    "build_recommendations",
    "build_comparison",
    "build_impact_preview",
    "sync_student_metrics",
]
