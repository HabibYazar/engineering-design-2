"""Kullanıcının yazdığı birim adını gerçek kayıtla eşleştirir.

Kullanıcı "Bilgisayar Mühendisliği", "Computer Engineering" veya "CENG"
yazabilir. Model bu adlardan bir kimlik uyduramaz; eşleştirme burada,
veritabanındaki gerçek kayıtlar ve Türkçe ad sözlüğü üzerinden yapılır.

TASARIM KARARI — TAHMİN YOK
---------------------------
Bu çözümleyici "en yakın sonucu bul" mantığıyla çalışmaz. Üç sonuç vardır:

* Tam olarak bir eşleşme  → kimlik döndürülür.
* Birden fazla eşleşme    → seçenekler döndürülür, kullanıcıdan seçim istenir.
* Hiç eşleşme yok         → hata döndürülür.

Belirsiz bir adı "muhtemelen bunu kastetti" diye çözmek, yanlış bölümün
bütçesini doğru cevap gibi sunmak demektir. Bir karar destek sisteminde bu,
cevap vermemekten daha kötüdür.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcademicProgram, Department, Faculty

DISPLAY_NAMES_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "display_names.json"
)

# Türkçe harfleri ASCII'ye indirger. "Mühendisliği" ile "muhendisligi"
# aynı sayılmalı; kullanıcı şapkalı harf yazmak zorunda değil.
_TR_MAP = str.maketrans(
    {
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
        "â": "a", "î": "i", "û": "u", "Â": "a", "Î": "i", "Û": "u",
    }
)

# Eşleştirmede anlam taşımayan sözcükler.
#
# "lisans", "yüksek" ve "master" BİLİNÇLİ OLARAK LİSTEDE DEĞİL. Bunlar
# atıldığında "Yazılım Mühendisliği Lisans Programı" ile "Yazılım Mühendisliği
# Yüksek Lisans Programı" aynı sözcük kümesine indirgeniyor ve tam adını
# yazan kullanıcı bile "belirsiz" hatası alıyordu. Derece bilgisi ayırt
# edicidir; atılmaz.
_STOPWORDS = {
    "programi", "program", "bolumu", "bolum", "fakultesi", "fakulte",
    "faculty", "of", "department", "s",
}


def normalize(text: str) -> str:
    """Karşılaştırma için metni sadeleştirir."""
    if not text:
        return ""
    lowered = unicodedata.normalize("NFC", text).translate(_TR_MAP).lower()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _tokens(text: str) -> frozenset:
    """Anlamlı sözcükler kümesi."""
    return frozenset(w for w in normalize(text).split() if w and w not in _STOPWORDS)


class EntityResolutionError(Exception):
    """Birim adı çözülemedi.

    `kind` alanı çağıranın ne yapacağını belirler:
      * "not_found"  → böyle bir birim yok
      * "ambiguous"  → birden fazla eşleşme var, kullanıcı seçmeli
    """

    def __init__(self, message: str, kind: str, candidates: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.candidates = candidates or []


@dataclass(frozen=True)
class ResolvedEntity:
    """Çözümlenmiş bir organizasyon birimi."""

    kind: str  # faculty | department | program
    id: int
    code: str
    display_name: str
    #: Veritabanındaki ad. Kullanıcıya gösterilmez, günlük/hata ayıklama için.
    raw_name: str


@dataclass
class Candidate:
    """Eşleştirme adayı."""

    entity: ResolvedEntity
    aliases: List[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _display_names() -> Dict[str, Dict[str, str]]:
    """Kod → Türkçe ad sözlüğü."""
    try:
        with DISPLAY_NAMES_PATH.open(encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return {"faculties": {}, "departments": {}, "programs": {}}
    return {
        "faculties": raw.get("faculties", {}),
        "departments": raw.get("departments", {}),
        "programs": raw.get("programs", {}),
    }


def _build_candidates(db: Session, kind: str) -> List[Candidate]:
    """Bir birim türü için tüm adayları ve takma adlarını toplar."""
    names = _display_names()

    if kind == "faculty":
        rows = db.execute(select(Faculty).where(Faculty.is_active.is_(True))).scalars().all()
        table = names["faculties"]
    elif kind == "department":
        rows = db.execute(select(Department).where(Department.is_active.is_(True))).scalars().all()
        table = names["departments"]
    elif kind == "program":
        rows = (
            db.execute(select(AcademicProgram).where(AcademicProgram.is_active.is_(True)))
            .scalars()
            .all()
        )
        table = names["programs"]
    else:  # pragma: no cover - çağıran yanlış tür veremez
        raise ValueError(f"Bilinmeyen birim türü: {kind}")

    candidates: List[Candidate] = []
    for row in rows:
        display = table.get(row.code, row.name)
        candidates.append(
            Candidate(
                entity=ResolvedEntity(
                    kind=kind,
                    id=row.id,
                    code=row.code,
                    display_name=display,
                    raw_name=row.name,
                ),
                # Kod, Türkçe ad ve veritabanındaki İngilizce ad — üçü de kabul edilir.
                aliases=[row.code, display, row.name],
            )
        )
    return candidates


def _score(query: str, candidate: Candidate) -> int:
    """Eşleşme gücü. 2 = tam, 1 = kapsayan, 0 = eşleşme yok.

    Puanlama kademeli: en güçlü kademede tek aday varsa o seçilir. Zayıf
    kademeye ancak güçlü kademede hiç aday yoksa inilir. Böylece "Bilgisayar
    Mühendisliği" ararken hem lisans hem yüksek lisans programı kapsama
    kademesinde eşleşse bile tam eşleşen tekse belirsizlik oluşmaz.

    KASITLI OLARAK YOK: "ortak sözcüğü olan" kademesi.
    Bu kademe eklendiğinde, sistemde hiç bulunmayan "Uzay Mühendisliği"
    sorgusu yalnızca "mühendisliği" sözcüğü ortak olduğu için var olan
    mühendislik programlarıyla eşleşiyor ve "belirsiz" sayılıyordu. Doğru
    cevap "böyle bir program yok"tur. Zayıf benzerlik üzerinden tahmin
    yürütmek, bir karar destek sisteminde yanlış birimin verisini doğru
    cevap gibi sunma riski taşır.
    """
    q_norm = normalize(query)
    q_tokens = _tokens(query)
    if not q_norm:
        return 0

    for alias in candidate.aliases:
        if normalize(alias) == q_norm:
            return 2

    for alias in candidate.aliases:
        a_tokens = _tokens(alias)
        if not a_tokens or not q_tokens:
            continue
        if q_tokens == a_tokens:
            return 2
        if q_tokens.issubset(a_tokens):
            return 1

    return 0


def resolve(db: Session, kind: str, query: str) -> ResolvedEntity:
    """Bir birim adını çözer. Belirsiz veya bulunamazsa hata fırlatır."""
    text = (query or "").strip()
    if not text:
        raise EntityResolutionError("Birim adı boş.", kind="not_found")

    candidates = _build_candidates(db, kind)
    label = {"faculty": "fakülte", "department": "bölüm", "program": "program"}[kind]

    scored: Dict[int, List[Candidate]] = {2: [], 1: []}
    for candidate in candidates:
        score = _score(text, candidate)
        if score:
            scored[score].append(candidate)

    for level in (2, 1):
        bucket = scored[level]
        if not bucket:
            continue
        if len(bucket) == 1:
            return bucket[0].entity
        # Aynı güçte birden fazla aday: TAHMİN ETME, kullanıcıya sor.
        options = sorted(c.entity.display_name for c in bucket)
        raise EntityResolutionError(
            f"'{text}' için birden fazla {label} eşleşti. Hangisini kastettiğinizi belirtin.",
            kind="ambiguous",
            candidates=options,
        )

    available = sorted(c.entity.display_name for c in candidates)[:10]
    raise EntityResolutionError(
        f"'{text}' adında bir {label} bulunamadı.",
        kind="not_found",
        candidates=available,
    )


def resolve_optional(db: Session, kind: str, query: Optional[str]) -> Optional[ResolvedEntity]:
    """Değer verilmişse çözer, verilmemişse None döndürür."""
    if query is None or not str(query).strip():
        return None
    return resolve(db, kind, str(query))


# ---------------------------------------------------------------------------
# Akademik yıl
# ---------------------------------------------------------------------------

ACADEMIC_YEAR_PATTERN = re.compile(r"^(\d{4})\s*[-–/]\s*(\d{4})$")


def available_academic_years(db: Session) -> List[str]:
    """Veride bulunan akademik yıllar (yeniden eskiye)."""
    from app.models import FinancialPeriod

    rows = db.execute(select(FinancialPeriod.academic_year)).scalars().all()
    return sorted(set(rows), reverse=True)


def resolve_academic_year(db: Session, value: Optional[str]) -> str:
    """Akademik yılı doğrular; verilmemişse en güncel yılı döndürür.

    Model uydurma bir yıl ("2030-2031") gönderirse hata alır; sistem sessizce
    başka bir yılın verisini döndürmez.
    """
    years = available_academic_years(db)
    if not years:
        raise EntityResolutionError(
            "Sistemde tanımlı akademik yıl yok.", kind="not_found"
        )

    if value is None or not str(value).strip():
        return years[0]

    text = str(value).strip()
    match = ACADEMIC_YEAR_PATTERN.match(text)
    normalized = f"{match.group(1)}-{match.group(2)}" if match else text

    if normalized not in years:
        raise EntityResolutionError(
            f"'{text}' akademik yılı için veri yok. Mevcut yıllar: {', '.join(years)}.",
            kind="not_found",
            candidates=years,
        )
    return normalized


def resolve_scope(
    db: Session,
    academic_year: Optional[str] = None,
    faculty: Optional[str] = None,
    department: Optional[str] = None,
    program: Optional[str] = None,
) -> Tuple[str, Optional[ResolvedEntity], Optional[ResolvedEntity], Optional[ResolvedEntity]]:
    """Araçların ortak kapsam çözümlemesi.

    Program verilmişse bölüm ve fakülte ondan TÜRETİLİR; kullanıcının veya
    modelin çelişkili bir kombinasyon göndermesi (X fakültesindeki Y programı,
    ama Y aslında Z fakültesinde) engellenir.
    """
    year = resolve_academic_year(db, academic_year)

    program_entity = resolve_optional(db, "program", program)
    department_entity = resolve_optional(db, "department", department)
    faculty_entity = resolve_optional(db, "faculty", faculty)

    if program_entity is not None:
        row = db.get(AcademicProgram, program_entity.id)
        department_entity = _entity_from_department(db, row.department_id)
        faculty_entity = _entity_from_faculty(db, row.department.faculty_id)
    elif department_entity is not None:
        row = db.get(Department, department_entity.id)
        faculty_entity = _entity_from_faculty(db, row.faculty_id)

    return year, faculty_entity, department_entity, program_entity


def _entity_from_department(db: Session, department_id: int) -> ResolvedEntity:
    row = db.get(Department, department_id)
    display = _display_names()["departments"].get(row.code, row.name)
    return ResolvedEntity("department", row.id, row.code, display, row.name)


def _entity_from_faculty(db: Session, faculty_id: int) -> ResolvedEntity:
    row = db.get(Faculty, faculty_id)
    display = _display_names()["faculties"].get(row.code, row.name)
    return ResolvedEntity("faculty", row.id, row.code, display, row.name)
