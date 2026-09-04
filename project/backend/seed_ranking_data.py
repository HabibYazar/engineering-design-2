"""Modül 10 (THE / QS / YÖK Değerlendirme ve İzleme) başlangıç verileri.

Çalıştırma sırası:
    python seed_data.py
    python seed_scenario_data.py
    python seed_student_data.py
    python seed_ranking_data.py

Script deterministiktir ve tekrar çalıştırılabilir: aynı kayıtlar ikinci kez
eklenmez, mevcut veriler silinmez.

ÖNEMLİ UYARI
------------
Buradaki ağırlıklar, eşikler ve hedef değerler GERÇEK THE/QS/YÖK metodolojisinin
resmi kopyası DEĞİLDİR. Sistem gerçek sıralama üretmez; kurumun kendi verisiyle
iç performans izleme, veri hazırlık ve uyum takibi yapar. Benchmark kurumları
tamamen DEMO amaçlıdır ve gerçek kurumları temsil etmez.
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import (
    BenchmarkInstitution,
    BenchmarkMetricValue,
    EvaluationDimension,
    EvaluationFramework,
    EvaluationIndicator,
    InstitutionalMetricValue,
)

# Metrik verisi üretilecek akademik yıllar (trend hesaplanabilsin diye üç yıl).
ACADEMIC_YEARS: Tuple[str, ...] = ("2023-2024", "2024-2025", "2025-2026")
CURRENT_YEAR: str = "2025-2026"
PERIOD: str = "annual"


def D(value: str) -> Decimal:
    """Kısa Decimal üretici."""
    return Decimal(value)


# ===========================================================================
# ÇERÇEVELER
# ===========================================================================

FRAMEWORKS: List[dict] = [
    {
        "code": "THE",
        "name": "THE World University Rankings (2026 metodolojisi)",
        "methodology_year": 2026,
        "description": (
            "Times Higher Education 2026 metodolojisinden esinlenen iç izleme çerçevesi. "
            "Gerçek THE sıralaması üretmez; kurumsal performans ve veri hazırlık takibi içindir."
        ),
    },
    {
        "code": "QS",
        "name": "QS World University Rankings (2026 metodolojisi)",
        "methodology_year": 2026,
        "description": (
            "QS 2026 metodolojisinden esinlenen iç izleme çerçevesi. "
            "Gerçek QS sıralaması üretmez."
        ),
    },
    {
        "code": "YOK",
        "name": "YÖK Üniversite İzleme ve Değerlendirme Çerçevesi",
        "methodology_year": 2026,
        "description": (
            "YÖK Üniversite İzleme ve Değerlendirme Genel Raporu başlıklarından esinlenen "
            "iç değerlendirme çerçevesi."
        ),
    },
]


# ===========================================================================
# BOYUTLAR   (framework_code, code, name, weight, display_order)
# ===========================================================================

DIMENSIONS: List[dict] = [
    # --- THE ---
    {"framework": "THE", "code": "teaching-environment", "name": "Teaching Environment",
     "weight": D("29.50"), "order": 1,
     "description": "Öğrenme ve öğretme ortamının kalitesi."},
    {"framework": "THE", "code": "research-environment", "name": "Research Environment",
     "weight": D("29.00"), "order": 2,
     "description": "Araştırma hacmi, geliri ve itibarı."},
    {"framework": "THE", "code": "research-quality", "name": "Research Quality",
     "weight": D("30.00"), "order": 3,
     "description": "Atıf etkisi ve araştırma çıktısının kalitesi."},
    {"framework": "THE", "code": "international-outlook", "name": "International Outlook",
     "weight": D("7.50"), "order": 4,
     "description": "Uluslararası öğrenci, personel ve iş birliği düzeyi."},
    {"framework": "THE", "code": "industry-income-patents", "name": "Industry Income and Patents",
     "weight": D("4.00"), "order": 5,
     "description": "Sanayi iş birliği geliri ve patent çıktısı."},

    # --- QS ---
    {"framework": "QS", "code": "academic-reputation", "name": "Academic Reputation",
     "weight": D("30.00"), "order": 1, "description": "Akademik çevrede itibar algısı."},
    {"framework": "QS", "code": "citations-per-faculty", "name": "Citations per Faculty",
     "weight": D("20.00"), "order": 2, "description": "Öğretim üyesi başına atıf etkisi."},
    {"framework": "QS", "code": "employer-reputation", "name": "Employer Reputation",
     "weight": D("15.00"), "order": 3, "description": "İşveren gözünde mezun kalitesi algısı."},
    {"framework": "QS", "code": "employment-outcomes", "name": "Employment Outcomes",
     "weight": D("5.00"), "order": 4, "description": "Mezunların istihdam sonuçları."},
    {"framework": "QS", "code": "faculty-student-ratio", "name": "Faculty Student Ratio",
     "weight": D("10.00"), "order": 5, "description": "Öğretim üyesi başına düşen öğrenci sayısı."},
    {"framework": "QS", "code": "international-faculty-ratio", "name": "International Faculty Ratio",
     "weight": D("5.00"), "order": 6, "description": "Uluslararası akademik personel oranı."},
    {"framework": "QS", "code": "international-student-ratio", "name": "International Student Ratio",
     "weight": D("5.00"), "order": 7, "description": "Uluslararası öğrenci oranı."},
    {"framework": "QS", "code": "international-research-network",
     "name": "International Research Network",
     "weight": D("5.00"), "order": 8, "description": "Uluslararası ortak araştırma ağı genişliği."},
    {"framework": "QS", "code": "sustainability", "name": "Sustainability",
     "weight": D("5.00"), "order": 9, "description": "Çevresel ve sosyal sürdürülebilirlik."},

    # --- YÖK ---
    {"framework": "YOK", "code": "education-teaching", "name": "Eğitim ve Öğretim",
     "weight": D("30.00"), "order": 1, "description": "Eğitim öğretim süreçlerinin niteliği."},
    {"framework": "YOK", "code": "research-development",
     "name": "Araştırma, Geliştirme, Proje ve Yayın",
     "weight": D("30.00"), "order": 2, "description": "Ar-Ge, proje ve yayın çıktıları."},
    {"framework": "YOK", "code": "internationalization", "name": "Uluslararasılaşma",
     "weight": D("20.00"), "order": 3, "description": "Uluslararası öğrenci, personel ve iş birlikleri."},
    {"framework": "YOK", "code": "sustainability", "name": "Sürdürülebilirlik",
     "weight": D("10.00"), "order": 4, "description": "Kurumsal sürdürülebilirlik uygulamaları."},
    {"framework": "YOK", "code": "community-service",
     "name": "Topluma Hizmet ve Sosyal Sorumluluk",
     "weight": D("10.00"), "order": 5, "description": "Topluma hizmet ve sosyal sorumluluk faaliyetleri."},
]


# ===========================================================================
# GÖSTERGELER
# ===========================================================================
# Alanlar: framework, dimension, code, name, unit, calc, weight, direction,
#          minimum, target, maximum, source, required, auto_key,
#          impact_num, impact_den
#
# auto_key  : Modül 1/2'den otomatik doldurulacak göstergeler
# impact_*  : What-if etki analizinde pay ve paydayı etkileyen değişkenler
# ===========================================================================

INDICATORS: List[dict] = [
    # ------------------------- THE : Teaching Environment -------------------------
    {"framework": "THE", "dimension": "teaching-environment",
     "code": "the-student-staff-ratio", "name": "Student-to-staff ratio",
     "unit": "öğrenci/personel", "calc": "ratio", "weight": D("25.00"),
     "direction": "lower_is_better", "min": D("5"), "target": D("15"), "max": D("50"),
     "source": "Personel Daire Başkanlığı + Öğrenci İşleri", "required": True,
     "impact_num": "total_student_count", "impact_den": "academic_staff_count"},

    {"framework": "THE", "dimension": "teaching-environment",
     "code": "the-doctoral-to-bachelor-ratio", "name": "Doctoral-to-bachelor ratio",
     "unit": "%", "calc": "percentage", "weight": D("20.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("20"), "max": D("60"),
     "source": "Öğrenci İşleri Daire Başkanlığı", "required": True,
     "auto_key": "doctoral_to_bachelor_ratio"},

    {"framework": "THE", "dimension": "teaching-environment",
     "code": "the-doctorates-per-staff", "name": "Doctorates awarded per academic staff",
     "unit": "adet/personel", "calc": "ratio", "weight": D("20.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("0.5"), "max": D("2"),
     "source": "Lisansüstü Eğitim Enstitüsü", "required": True,
     "impact_num": "doctoral_graduate_count", "impact_den": "academic_staff_count"},

    {"framework": "THE", "dimension": "teaching-environment",
     "code": "the-institutional-income-per-staff", "name": "Institutional income per academic staff",
     "unit": "TL/personel", "calc": "ratio", "weight": D("20.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("1500000"),
     "max": D("5000000"), "source": "Strateji Geliştirme Daire Başkanlığı", "required": True},

    {"framework": "THE", "dimension": "teaching-environment",
     "code": "the-teaching-reputation", "name": "Teaching reputation score",
     "unit": "skor", "calc": "score", "weight": D("15.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("70"), "max": D("100"),
     "source": "Akademik itibar anketi (manuel giriş)", "required": False},

    # ------------------------- THE : Research Environment -------------------------
    {"framework": "THE", "dimension": "research-environment",
     "code": "the-publications-per-staff", "name": "Publications per academic staff",
     "unit": "adet/personel", "calc": "ratio", "weight": D("40.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("2.5"), "max": D("8"),
     "source": "Kütüphane ve Dokümantasyon Daire Başkanlığı (WoS/Scopus)", "required": True,
     "impact_num": "publication_count", "impact_den": "academic_staff_count"},

    {"framework": "THE", "dimension": "research-environment",
     "code": "the-research-income-per-staff", "name": "Research income per academic staff",
     "unit": "TL/personel", "calc": "ratio", "weight": D("35.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("250000"),
     "max": D("1000000"), "source": "Proje Koordinasyon Ofisi", "required": True,
     "impact_num": "research_income", "impact_den": "academic_staff_count"},

    {"framework": "THE", "dimension": "research-environment",
     "code": "the-research-reputation", "name": "Research reputation score",
     "unit": "skor", "calc": "score", "weight": D("25.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("70"), "max": D("100"),
     "source": "Araştırma itibar anketi (manuel giriş)", "required": False},

    # ------------------------- THE : Research Quality -------------------------
    {"framework": "THE", "dimension": "research-quality",
     "code": "the-citation-impact", "name": "Citation impact (normalized)",
     "unit": "atıf/yayın", "calc": "ratio", "weight": D("60.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("5"), "max": D("15"),
     "source": "Scopus / WoS atıf raporu", "required": True,
     "impact_num": "citation_count", "impact_den": "publication_count"},

    {"framework": "THE", "dimension": "research-quality",
     "code": "the-research-strength", "name": "Research strength score",
     "unit": "skor", "calc": "score", "weight": D("40.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("60"), "max": D("100"),
     "source": "Araştırma performans analizi (manuel giriş)", "required": False},

    # ------------------------- THE : International Outlook -------------------------
    {"framework": "THE", "dimension": "international-outlook",
     "code": "the-international-student-ratio", "name": "International student ratio",
     "unit": "%", "calc": "percentage", "weight": D("35.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("25"), "max": D("60"),
     "source": "Öğrenci İşleri Daire Başkanlığı", "required": True,
     "auto_key": "international_student_ratio",
     "impact_num": "international_student_count", "impact_den": "total_student_count"},

    {"framework": "THE", "dimension": "international-outlook",
     "code": "the-international-staff-ratio", "name": "International academic staff ratio",
     "unit": "%", "calc": "percentage", "weight": D("35.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("15"), "max": D("40"),
     "source": "Personel Daire Başkanlığı", "required": True,
     "impact_num": "international_academic_staff_count",
     "impact_den": "academic_staff_count"},

    {"framework": "THE", "dimension": "international-outlook",
     "code": "the-international-collaboration", "name": "International collaboration ratio",
     "unit": "%", "calc": "percentage", "weight": D("30.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("30"), "max": D("70"),
     "source": "Uluslararası İlişkiler Ofisi", "required": True},

    # ------------------------- THE : Industry Income and Patents -------------------------
    {"framework": "THE", "dimension": "industry-income-patents",
     "code": "the-industry-income-per-staff", "name": "Industry income per academic staff",
     "unit": "TL/personel", "calc": "ratio", "weight": D("60.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("100000"),
     "max": D("500000"), "source": "Teknoloji Transfer Ofisi", "required": True,
     "impact_num": "industry_income", "impact_den": "academic_staff_count"},

    {"framework": "THE", "dimension": "industry-income-patents",
     "code": "the-patent-count", "name": "Patent count",
     "unit": "adet", "calc": "raw", "weight": D("40.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("25"), "max": D("100"),
     "source": "Teknoloji Transfer Ofisi", "required": True},

    # ------------------------- QS -------------------------
    {"framework": "QS", "dimension": "academic-reputation",
     "code": "qs-academic-reputation", "name": "Academic reputation score",
     "unit": "skor", "calc": "score", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("70"), "max": D("100"),
     "source": "Akademik itibar anketi (manuel giriş)", "required": True},

    {"framework": "QS", "dimension": "citations-per-faculty",
     "code": "qs-citations-per-faculty", "name": "Citations per faculty",
     "unit": "atıf/personel", "calc": "ratio", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("40"), "max": D("150"),
     "source": "Scopus / WoS atıf raporu", "required": True,
     "impact_num": "citation_count", "impact_den": "academic_staff_count"},

    {"framework": "QS", "dimension": "employer-reputation",
     "code": "qs-employer-reputation", "name": "Employer reputation score",
     "unit": "skor", "calc": "score", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("65"), "max": D("100"),
     "source": "İşveren anketi (manuel giriş)", "required": True},

    {"framework": "QS", "dimension": "employment-outcomes",
     "code": "qs-employment-outcomes", "name": "Graduate employment rate",
     "unit": "%", "calc": "percentage", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("85"), "max": D("100"),
     "source": "Kariyer Merkezi mezun takip anketi", "required": True},

    {"framework": "QS", "dimension": "faculty-student-ratio",
     "code": "qs-faculty-student-ratio", "name": "Faculty-to-student ratio",
     "unit": "personel/öğrenci", "calc": "ratio", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("0.08"), "max": D("0.25"),
     "source": "Personel Daire Başkanlığı + Öğrenci İşleri", "required": True,
     "impact_num": "academic_staff_count", "impact_den": "total_student_count"},

    {"framework": "QS", "dimension": "international-faculty-ratio",
     "code": "qs-international-faculty-ratio", "name": "International faculty ratio",
     "unit": "%", "calc": "percentage", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("15"), "max": D("40"),
     "source": "Personel Daire Başkanlığı", "required": True,
     "impact_num": "international_academic_staff_count",
     "impact_den": "academic_staff_count"},

    {"framework": "QS", "dimension": "international-student-ratio",
     "code": "qs-international-student-ratio", "name": "International student ratio",
     "unit": "%", "calc": "percentage", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("25"), "max": D("60"),
     "source": "Öğrenci İşleri Daire Başkanlığı", "required": True,
     "auto_key": "international_student_ratio",
     "impact_num": "international_student_count", "impact_den": "total_student_count"},

    {"framework": "QS", "dimension": "international-research-network",
     "code": "qs-international-research-network", "name": "International research network score",
     "unit": "skor", "calc": "score", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("60"), "max": D("100"),
     "source": "Uluslararası ortak yayın analizi", "required": True},

    {"framework": "QS", "dimension": "sustainability",
     "code": "qs-sustainability-score", "name": "Sustainability score",
     "unit": "skor", "calc": "score", "weight": D("100.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("60"), "max": D("100"),
     "source": "Sürdürülebilirlik Ofisi raporu", "required": True},

    # ------------------------- YÖK : Eğitim ve Öğretim -------------------------
    {"framework": "YOK", "dimension": "education-teaching",
     "code": "yok-program-occupancy-rate", "name": "Program doluluk oranı",
     "unit": "%", "calc": "percentage", "weight": D("30.00"),
     "direction": "higher_is_better", "min": D("50"), "target": D("95"), "max": D("100"),
     "source": "Öğrenci İşleri Daire Başkanlığı", "required": True,
     "auto_key": "program_occupancy_rate"},

    {"framework": "YOK", "dimension": "education-teaching",
     "code": "yok-graduation-rate", "name": "Mezuniyet oranı",
     "unit": "%", "calc": "percentage", "weight": D("30.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("60"), "max": D("100"),
     "source": "Öğrenci İşleri Daire Başkanlığı", "required": True,
     "auto_key": "graduation_rate"},

    {"framework": "YOK", "dimension": "education-teaching",
     "code": "yok-attrition-rate", "name": "Öğrenci kayıp oranı",
     "unit": "%", "calc": "percentage", "weight": D("20.00"),
     "direction": "lower_is_better", "min": D("0"), "target": D("5"), "max": D("30"),
     "source": "Öğrenci İşleri Daire Başkanlığı", "required": True,
     "auto_key": "attrition_rate"},

    {"framework": "YOK", "dimension": "education-teaching",
     "code": "yok-average-graduation-duration", "name": "Ortalama mezuniyet süresi",
     "unit": "yıl", "calc": "raw", "weight": D("20.00"),
     "direction": "target_is_best", "min": D("3"), "target": D("4"), "max": D("8"),
     "source": "Öğrenci İşleri Daire Başkanlığı", "required": True,
     "auto_key": "average_graduation_duration"},

    # ------------------------- YÖK : Araştırma, Geliştirme, Proje ve Yayın -------------------------
    {"framework": "YOK", "dimension": "research-development",
     "code": "yok-publications-per-staff", "name": "Akademik personel başına yayın",
     "unit": "adet/personel", "calc": "ratio", "weight": D("35.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("2"), "max": D("6"),
     "source": "Kütüphane ve Dokümantasyon Daire Başkanlığı", "required": True,
     "impact_num": "publication_count", "impact_den": "academic_staff_count"},

    {"framework": "YOK", "dimension": "research-development",
     "code": "yok-project-income", "name": "Toplam proje geliri",
     "unit": "TL", "calc": "raw", "weight": D("35.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("50000000"),
     "max": D("200000000"), "source": "Proje Koordinasyon Ofisi", "required": True},

    {"framework": "YOK", "dimension": "research-development",
     "code": "yok-doctoral-graduate-count", "name": "Doktora mezun sayısı",
     "unit": "adet", "calc": "raw", "weight": D("30.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("60"), "max": D("200"),
     "source": "Lisansüstü Eğitim Enstitüsü", "required": True},

    # ------------------------- YÖK : Uluslararasılaşma -------------------------
    {"framework": "YOK", "dimension": "internationalization",
     "code": "yok-international-student-ratio", "name": "Uluslararası öğrenci oranı",
     "unit": "%", "calc": "percentage", "weight": D("40.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("20"), "max": D("50"),
     "source": "Öğrenci İşleri Daire Başkanlığı", "required": True,
     "auto_key": "international_student_ratio",
     "impact_num": "international_student_count", "impact_den": "total_student_count"},

    {"framework": "YOK", "dimension": "internationalization",
     "code": "yok-international-staff-ratio", "name": "Uluslararası akademik personel oranı",
     "unit": "%", "calc": "percentage", "weight": D("30.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("10"), "max": D("30"),
     "source": "Personel Daire Başkanlığı", "required": True,
     "impact_num": "international_academic_staff_count",
     "impact_den": "academic_staff_count"},

    {"framework": "YOK", "dimension": "internationalization",
     "code": "yok-exchange-student-count", "name": "Değişim programı öğrenci sayısı",
     "unit": "adet", "calc": "raw", "weight": D("30.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("150"), "max": D("500"),
     "source": "Erasmus / Uluslararası İlişkiler Ofisi", "required": True},

    # ------------------------- YÖK : Sürdürülebilirlik -------------------------
    {"framework": "YOK", "dimension": "sustainability",
     "code": "yok-sustainability-report-published", "name": "Sürdürülebilirlik raporu yayımlandı mı",
     "unit": None, "calc": "boolean", "weight": D("40.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("100"), "max": D("100"),
     "source": "Sürdürülebilirlik Ofisi", "required": True},

    {"framework": "YOK", "dimension": "sustainability",
     "code": "yok-renewable-energy-ratio", "name": "Yenilenebilir enerji kullanım oranı",
     "unit": "%", "calc": "percentage", "weight": D("35.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("30"), "max": D("100"),
     "source": "Yapı İşleri ve Teknik Daire Başkanlığı", "required": True},

    {"framework": "YOK", "dimension": "sustainability",
     "code": "yok-waste-recycling-ratio", "name": "Atık geri dönüşüm oranı",
     "unit": "%", "calc": "percentage", "weight": D("25.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("50"), "max": D("100"),
     "source": "Sağlık Kültür ve Spor Daire Başkanlığı", "required": True},

    # ------------------------- YÖK : Topluma Hizmet ve Sosyal Sorumluluk -------------------------
    {"framework": "YOK", "dimension": "community-service",
     "code": "yok-community-project-count", "name": "Topluma hizmet proje sayısı",
     "unit": "adet", "calc": "raw", "weight": D("40.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("40"), "max": D("150"),
     "source": "Sosyal Sorumluluk Koordinatörlüğü", "required": True},

    {"framework": "YOK", "dimension": "community-service",
     "code": "yok-volunteer-hours", "name": "Gönüllülük saati",
     "unit": "saat", "calc": "raw", "weight": D("30.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("15000"),
     "max": D("60000"), "source": "Sosyal Sorumluluk Koordinatörlüğü", "required": True},

    {"framework": "YOK", "dimension": "community-service",
     "code": "yok-public-training-participants", "name": "Topluma açık eğitim katılımcı sayısı",
     "unit": "kişi", "calc": "raw", "weight": D("30.00"),
     "direction": "higher_is_better", "min": D("0"), "target": D("3000"),
     "max": D("15000"), "source": "Sürekli Eğitim Merkezi", "required": True},
]


# ===========================================================================
# KURUMSAL GÖSTERGE VERİLERİ
# ===========================================================================
# Bilinçli olarak eksik ve kısmi veri örnekleri de bırakılmıştır; eksik veri
# analizi ve readiness hesabı gerçek veriyle test edilebilsin diye.
#
# Yapı: indicator_code -> {academic_year: (value, numerator, denominator, status)}
# ===========================================================================

METRIC_DATA: Dict[str, Dict[str, tuple]] = {
    # --- THE Teaching ---
    "the-student-staff-ratio": {
        "2023-2024": (None, D("115"), D("6"), "available"),
        "2024-2025": (None, D("118"), D("6.2"), "available"),
        "2025-2026": (None, D("120"), D("6.5"), "available"),
    },
    "the-doctorates-per-staff": {
        "2023-2024": (None, D("4"), D("19"), "available"),
        "2024-2025": (None, D("6"), D("19"), "available"),
        "2025-2026": (None, D("8"), D("20"), "available"),
    },
    "the-institutional-income-per-staff": {
        "2024-2025": (None, D("18000000"), D("19"), "available"),
        "2025-2026": (None, D("21000000"), D("20"), "available"),
    },
    "the-teaching-reputation": {
        "2025-2026": (D("42.00"), None, None, "estimated"),
    },
    # --- THE Research ---
    "the-publications-per-staff": {
        "2023-2024": (None, D("38"), D("19"), "available"),
        "2024-2025": (None, D("44"), D("19"), "available"),
        "2025-2026": (None, D("52"), D("20"), "available"),
    },
    "the-research-income-per-staff": {
        "2024-2025": (None, D("2400000"), D("19"), "partial"),
        "2025-2026": (None, D("3100000"), D("20"), "available"),
    },
    # the-research-reputation: bilinçli olarak EKSİK (missing örneği)
    # --- THE Research Quality ---
    "the-citation-impact": {
        "2023-2024": (None, D("96"), D("38"), "available"),
        "2024-2025": (None, D("128"), D("44"), "available"),
        "2025-2026": (None, D("172"), D("52"), "available"),
    },
    "the-research-strength": {
        "2025-2026": (D("38.00"), None, None, "estimated"),
    },
    # --- THE International ---
    "the-international-staff-ratio": {
        "2024-2025": (None, D("2"), D("19"), "available"),
        "2025-2026": (None, D("3"), D("20"), "available"),
    },
    "the-international-collaboration": {
        "2025-2026": (None, D("11"), D("52"), "partial"),
    },
    # --- THE Industry ---
    "the-industry-income-per-staff": {
        "2024-2025": (None, D("640000"), D("19"), "available"),
        "2025-2026": (None, D("900000"), D("20"), "available"),
    },
    "the-patent-count": {
        "2023-2024": (D("3"), None, None, "available"),
        "2024-2025": (D("5"), None, None, "available"),
        "2025-2026": (D("7"), None, None, "available"),
    },
    # --- QS ---
    "qs-academic-reputation": {
        "2024-2025": (D("34.00"), None, None, "estimated"),
        "2025-2026": (D("38.00"), None, None, "estimated"),
    },
    "qs-citations-per-faculty": {
        "2023-2024": (None, D("96"), D("19"), "available"),
        "2024-2025": (None, D("128"), D("19"), "available"),
        "2025-2026": (None, D("172"), D("20"), "available"),
    },
    "qs-employer-reputation": {
        "2025-2026": (D("41.00"), None, None, "estimated"),
    },
    "qs-employment-outcomes": {
        "2024-2025": (None, D("64"), D("92"), "partial"),
        "2025-2026": (None, D("71"), D("95"), "available"),
    },
    "qs-faculty-student-ratio": {
        "2023-2024": (None, D("6"), D("115"), "available"),
        "2024-2025": (None, D("6.2"), D("118"), "available"),
        "2025-2026": (None, D("6.5"), D("120"), "available"),
    },
    "qs-international-faculty-ratio": {
        "2024-2025": (None, D("2"), D("19"), "available"),
        "2025-2026": (None, D("3"), D("20"), "available"),
    },
    "qs-international-research-network": {
        "2025-2026": (D("29.00"), None, None, "partial"),
    },
    # qs-sustainability-score: bilinçli olarak EKSİK
    # --- YÖK ---
    "yok-project-income": {
        "2023-2024": (D("18000000"), None, None, "available"),
        "2024-2025": (D("24000000"), None, None, "available"),
        "2025-2026": (D("31000000"), None, None, "available"),
    },
    "yok-publications-per-staff": {
        "2024-2025": (None, D("44"), D("19"), "available"),
        "2025-2026": (None, D("52"), D("20"), "available"),
    },
    "yok-doctoral-graduate-count": {
        "2023-2024": (D("4"), None, None, "available"),
        "2024-2025": (D("6"), None, None, "available"),
        "2025-2026": (D("8"), None, None, "available"),
    },
    "yok-international-staff-ratio": {
        "2025-2026": (None, D("3"), D("20"), "available"),
    },
    "yok-exchange-student-count": {
        "2024-2025": (D("22"), None, None, "available"),
        "2025-2026": (D("31"), None, None, "available"),
    },
    "yok-sustainability-report-published": {
        "2025-2026": (D("1"), None, None, "available"),
    },
    "yok-renewable-energy-ratio": {
        "2025-2026": (None, D("8"), D("100"), "partial"),
    },
    # yok-waste-recycling-ratio: bilinçli olarak EKSİK
    "yok-community-project-count": {
        "2024-2025": (D("12"), None, None, "available"),
        "2025-2026": (D("17"), None, None, "available"),
    },
    "yok-volunteer-hours": {
        "2025-2026": (D("4200"), None, None, "available"),
    },
    "yok-public-training-participants": {
        "2025-2026": (D("860"), None, None, "estimated"),
    },
}


# ===========================================================================
# KARŞILAŞTIRMA KURUMLARI (tamamı DEMO verisidir)
# ===========================================================================

BENCHMARK_INSTITUTIONS: List[dict] = [
    {"name": "Türkiye Devlet Üniversiteleri Ortalaması (demo)", "country": "Türkiye",
     "city": None, "institution_type": "national-average", "is_competitor": False,
     "notes": "DEMO VERİ: Gerçek YÖK ortalaması değildir, örnek amaçlıdır."},
    {"name": "Demo Anadolu Teknik Üniversitesi", "country": "Türkiye", "city": "Eskişehir",
     "institution_type": "similar", "is_competitor": False,
     "notes": "DEMO VERİ: Kurgusal örnek kurumdur."},
    {"name": "Demo Ege Bilim Üniversitesi", "country": "Türkiye", "city": "İzmir",
     "institution_type": "similar", "is_competitor": False,
     "notes": "DEMO VERİ: Kurgusal örnek kurumdur."},
    {"name": "Demo Başkent Rakip Üniversitesi", "country": "Türkiye", "city": "Ankara",
     "institution_type": "competitor", "is_competitor": True,
     "notes": "DEMO VERİ: Seçilmiş rakip kurum örneğidir."},
    {"name": "Demo Boğaz Araştırma Üniversitesi", "country": "Türkiye", "city": "İstanbul",
     "institution_type": "competitor", "is_competitor": True,
     "notes": "DEMO VERİ: Seçilmiş rakip kurum örneğidir."},
]

# kurum adı -> {indicator_code: value}  (2025-2026 dönemi için)
BENCHMARK_VALUES: Dict[str, Dict[str, Decimal]] = {
    "Türkiye Devlet Üniversiteleri Ortalaması (demo)": {
        "the-student-staff-ratio": D("22.50"),
        "the-international-student-ratio": D("6.40"),
        "the-publications-per-staff": D("1.80"),
        "the-citation-impact": D("2.60"),
        "qs-citations-per-faculty": D("18.00"),
        "qs-international-student-ratio": D("6.40"),
        "yok-graduation-rate": D("48.00"),
        "yok-program-occupancy-rate": D("82.00"),
    },
    "Demo Anadolu Teknik Üniversitesi": {
        "the-student-staff-ratio": D("19.80"),
        "the-international-student-ratio": D("9.20"),
        "the-publications-per-staff": D("2.30"),
        "the-citation-impact": D("3.10"),
        "qs-citations-per-faculty": D("24.00"),
        "qs-international-student-ratio": D("9.20"),
        "yok-graduation-rate": D("54.00"),
        "yok-program-occupancy-rate": D("88.00"),
    },
    "Demo Ege Bilim Üniversitesi": {
        "the-student-staff-ratio": D("21.10"),
        "the-international-student-ratio": D("11.60"),
        "the-publications-per-staff": D("2.10"),
        "the-citation-impact": D("2.90"),
        "qs-citations-per-faculty": D("21.50"),
        "qs-international-student-ratio": D("11.60"),
        "yok-graduation-rate": D("51.00"),
        "yok-program-occupancy-rate": D("85.00"),
    },
    "Demo Başkent Rakip Üniversitesi": {
        "the-student-staff-ratio": D("16.40"),
        "the-international-student-ratio": D("18.30"),
        "the-publications-per-staff": D("3.40"),
        "the-citation-impact": D("4.70"),
        "qs-citations-per-faculty": D("38.00"),
        "qs-international-student-ratio": D("18.30"),
        "yok-graduation-rate": D("63.00"),
        "yok-program-occupancy-rate": D("97.00"),
    },
    "Demo Boğaz Araştırma Üniversitesi": {
        "the-student-staff-ratio": D("14.20"),
        "the-international-student-ratio": D("22.70"),
        "the-publications-per-staff": D("4.10"),
        "the-citation-impact": D("6.20"),
        "qs-citations-per-faculty": D("52.00"),
        "qs-international-student-ratio": D("22.70"),
        "yok-graduation-rate": D("71.00"),
        "yok-program-occupancy-rate": D("99.00"),
    },
}


# ===========================================================================
# SEED FONKSİYONLARI
# ===========================================================================


def seed_frameworks(db: Session) -> Tuple[Dict[str, EvaluationFramework], int, int]:
    """Çerçeveleri ekler; var olanları atlar."""
    created = skipped = 0
    result: Dict[str, EvaluationFramework] = {}

    for data in FRAMEWORKS:
        existing: Optional[EvaluationFramework] = (
            db.execute(
                select(EvaluationFramework)
                .where(EvaluationFramework.code == data["code"])
                .where(EvaluationFramework.methodology_year == data["methodology_year"])
            )
            .scalars()
            .first()
        )
        if existing is not None:
            result[data["code"]] = existing
            skipped += 1
            continue

        framework = EvaluationFramework(is_active=True, **data)
        db.add(framework)
        db.flush()
        result[data["code"]] = framework
        created += 1

    return result, created, skipped


def seed_dimensions(
    db: Session, frameworks: Dict[str, EvaluationFramework]
) -> Tuple[Dict[str, EvaluationDimension], int, int]:
    """Boyutları ekler; anahtar "FRAMEWORK:code" biçimindedir."""
    created = skipped = 0
    result: Dict[str, EvaluationDimension] = {}

    for data in DIMENSIONS:
        framework = frameworks[data["framework"]]
        key = f"{data['framework']}:{data['code']}"

        existing: Optional[EvaluationDimension] = (
            db.execute(
                select(EvaluationDimension)
                .where(EvaluationDimension.framework_id == framework.id)
                .where(EvaluationDimension.code == data["code"])
            )
            .scalars()
            .first()
        )
        if existing is not None:
            result[key] = existing
            skipped += 1
            continue

        dimension = EvaluationDimension(
            framework_id=framework.id,
            code=data["code"],
            name=data["name"],
            description=data.get("description"),
            weight=data["weight"],
            display_order=data["order"],
            is_active=True,
        )
        db.add(dimension)
        db.flush()
        result[key] = dimension
        created += 1

    return result, created, skipped


def seed_indicators(
    db: Session, dimensions: Dict[str, EvaluationDimension]
) -> Tuple[Dict[str, EvaluationIndicator], int, int]:
    """Göstergeleri ekler; anahtar gösterge kodudur."""
    created = skipped = 0
    result: Dict[str, EvaluationIndicator] = {}

    # Mevcut kodlar tek sorguda alınır; her gösterge için ayrı SELECT atılmaz.
    existing_by_code: Dict[str, EvaluationIndicator] = {
        indicator.code: indicator
        for indicator in db.execute(select(EvaluationIndicator)).scalars().all()
    }

    for data in INDICATORS:
        code: str = data["code"]
        if code in existing_by_code:
            result[code] = existing_by_code[code]
            skipped += 1
            continue

        dimension = dimensions[f"{data['framework']}:{data['dimension']}"]
        indicator = EvaluationIndicator(
            dimension_id=dimension.id,
            code=code,
            name=data["name"],
            description=data.get("description"),
            unit=data.get("unit"),
            calculation_type=data["calc"],
            weight=data["weight"],
            direction=data["direction"],
            minimum_value=data.get("min"),
            target_value=data.get("target"),
            maximum_value=data.get("max"),
            data_source=data.get("source"),
            required_for_readiness=data.get("required", True),
            auto_source_key=data.get("auto_key"),
            impact_numerator_variable=data.get("impact_num"),
            impact_denominator_variable=data.get("impact_den"),
            is_active=True,
        )
        db.add(indicator)
        db.flush()
        result[code] = indicator
        created += 1

    return result, created, skipped


def seed_metric_values(
    db: Session, indicators: Dict[str, EvaluationIndicator]
) -> Tuple[int, int]:
    """Kurumsal gösterge verilerini ekler."""
    created = skipped = 0

    # Mevcut kayıtlar tek sorguda alınır.
    existing_keys = {
        (metric.indicator_id, metric.academic_year, metric.period)
        for metric in db.execute(select(InstitutionalMetricValue)).scalars().all()
    }

    for code, year_data in METRIC_DATA.items():
        indicator = indicators.get(code)
        if indicator is None:
            continue

        for academic_year, (value, numerator, denominator, status) in year_data.items():
            key = (indicator.id, academic_year, PERIOD)
            if key in existing_keys:
                skipped += 1
                continue

            db.add(
                InstitutionalMetricValue(
                    indicator_id=indicator.id,
                    academic_year=academic_year,
                    period=PERIOD,
                    value=value,
                    numerator=numerator,
                    denominator=denominator,
                    data_status=status,
                    origin="manual",
                    source_reference="seed_ranking_data.py demo verisi",
                    measured_at=datetime(int(academic_year.split("-")[1]), 6, 30),
                )
            )
            created += 1

    return created, skipped


def seed_benchmarks(
    db: Session, indicators: Dict[str, EvaluationIndicator]
) -> Tuple[int, int, int, int]:
    """Karşılaştırma kurumlarını ve gösterge değerlerini ekler."""
    institution_created = institution_skipped = 0
    value_created = value_skipped = 0

    institutions: Dict[str, BenchmarkInstitution] = {
        institution.name: institution
        for institution in db.execute(select(BenchmarkInstitution)).scalars().all()
    }

    for data in BENCHMARK_INSTITUTIONS:
        if data["name"] in institutions:
            institution_skipped += 1
            continue
        institution = BenchmarkInstitution(is_active=True, **data)
        db.add(institution)
        db.flush()
        institutions[data["name"]] = institution
        institution_created += 1

    existing_keys = {
        (row.benchmark_institution_id, row.indicator_id, row.academic_year, row.period)
        for row in db.execute(select(BenchmarkMetricValue)).scalars().all()
    }

    for institution_name, values in BENCHMARK_VALUES.items():
        institution = institutions.get(institution_name)
        if institution is None:
            continue

        for code, value in values.items():
            indicator = indicators.get(code)
            if indicator is None:
                continue

            key = (institution.id, indicator.id, CURRENT_YEAR, PERIOD)
            if key in existing_keys:
                value_skipped += 1
                continue

            db.add(
                BenchmarkMetricValue(
                    benchmark_institution_id=institution.id,
                    indicator_id=indicator.id,
                    academic_year=CURRENT_YEAR,
                    period=PERIOD,
                    value=value,
                    source_reference="DEMO VERİ - seed_ranking_data.py",
                )
            )
            value_created += 1

    return institution_created, institution_skipped, value_created, value_skipped


def seed() -> None:
    """Modül 10 başlangıç verilerini ekler ve ilk değerlendirmeleri hesaplar."""
    init_db()
    db: Session = SessionLocal()

    try:
        frameworks, fw_created, fw_skipped = seed_frameworks(db)
        dimensions, dim_created, dim_skipped = seed_dimensions(db, frameworks)
        indicators, ind_created, ind_skipped = seed_indicators(db, dimensions)
        metric_created, metric_skipped = seed_metric_values(db, indicators)
        (
            inst_created,
            inst_skipped,
            bval_created,
            bval_skipped,
        ) = seed_benchmarks(db, indicators)

        db.commit()

        # --- Otomatik öğrenci verisi senkronizasyonu ---
        # Modül 1/2 verisi varsa öğrenci tarafındaki göstergeler otomatik doldurulur.
        # İçe aktarma yapılmamışsa bu adım sessizce boş geçer.
        from app.services.ranking_student_sync_service import sync_student_metrics

        sync_result = sync_student_metrics(db, CURRENT_YEAR, PERIOD)
        db.commit()

        # --- İlk değerlendirmelerin hesaplanması ---
        # Trend endpoint'i için birden fazla yıl hesaplanır.
        from app.services.ranking_calculation_service import (
            evaluate_framework,
            persist_assessment,
        )

        assessment_count: int = 0
        for framework in frameworks.values():
            for academic_year in ACADEMIC_YEARS:
                detail = evaluate_framework(db, framework, academic_year, PERIOD)
                persist_assessment(db, framework, detail)
                assessment_count += 1
        db.commit()

        print(
            "Modul 10 (THE/QS/YOK) seed tamamlandi.\n"
            f"  Cerceve         : eklenen {fw_created}, mevcut {fw_skipped}\n"
            f"  Boyut           : eklenen {dim_created}, mevcut {dim_skipped}\n"
            f"  Gosterge        : eklenen {ind_created}, mevcut {ind_skipped}\n"
            f"  Gosterge verisi : eklenen {metric_created}, mevcut {metric_skipped}\n"
            f"  Benchmark kurum : eklenen {inst_created}, mevcut {inst_skipped}\n"
            f"  Benchmark deger : eklenen {bval_created}, mevcut {bval_skipped}\n"
            f"  Otomatik sync   : {sync_result.created_count} olusturuldu, "
            f"{sync_result.updated_count} guncellendi, {sync_result.skipped_count} atlandi\n"
            f"  Degerlendirme   : {assessment_count} kayit hesaplandi"
        )
        print(
            "\nUYARI: Bu skorlar gercek THE/QS/YOK siralamasi degildir. "
            "Ic performans izleme ve veri hazirlik gostergeleridir."
        )

    except Exception as error:
        # Hata durumunda yarım veri kalmaması için tüm işlem geri alınır.
        db.rollback()
        print(f"Modul 10 seed sirasinda hata olustu: {error}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
