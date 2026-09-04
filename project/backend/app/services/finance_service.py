"""Modül 6 — Stratejik finansal analiz servisi.

Entegrasyon notu: Gösterge formülleri Halil'in `render.py` dosyasındaki
hesaplarla birebir aynıdır (gelir/gider dengesi, öğrenci başına gelir ve
maliyet, mezun başına maliyet, personel gideri payı, araştırma geliri payı,
burs yükü, bütçe gerçekleşme oranı ve %100/%108 eşikli durum sınıflandırması).

Değişen iki şey var:
1) Veri kaynağı JSON dosyası değil, veritabanı. JSON dosyası tek süreç için
   kilitleniyordu ve aynı anda iki kullanıcı yazdığında son yazan diğerini
   eziyordu.
2) Tutarlar float yerine Decimal. Float ile 9 gider kalemi toplandığında kuruş
   sapması oluşuyor ve denge (gelir - gider) sıfır olması gereken yerde
   sıfırdan farklı çıkabiliyordu.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:  # yalnızca tip ipucu; döngüsel import olmasın
    from app.services.scope import Scope

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.decimal_types import quantize_money
from app.models import (
    Department,
    DepartmentBudget,
    FinancialEntry,
    FinancialPeriod,
)
from app.models.financial_period import ENTRY_KINDS
from app.schemas.finance import (
    DepartmentBudgetUpsert,
    FinancialEntryCreate,
    FinancialPeriodCreate,
    FinancialPeriodUpdate,
)

# Bütçe gerçekleşme eşikleri. Halil'in kodundaki %100 / %108 değerleri korundu.
BUDGET_WITHIN_LIMIT = Decimal("100")
BUDGET_SLIGHT_OVER_LIMIT = Decimal("108")

# Oran hesaplarında kullanılan kalem adları. Kalem adı bulunamazsa oran
# hesaplanmaz (None döner) — sıfır yazmak "personel gideri yok" anlamına gelirdi.
PERSONNEL_CATEGORY_KEYS = ("personel", "staff", "salaries", "maaş")
RESEARCH_CATEGORY_KEYS = ("araştırma", "research", "ar-ge", "r&d")
SCHOLARSHIP_CATEGORY_KEYS = ("burs", "scholarship")

FINANCIAL_CATEGORY_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("gross_tuition_revenue", "revenue", "Öğrenim ücretleri (brüt)", ("öğrenim", "tuition")),
    ("research_revenue", "revenue", "Araştırma gelirleri", ("araştırma", "research", "ar-ge", "r&d")),
    ("other_revenue", "revenue", "Diğer gelirler", ("diğer", "other")),
    ("scholarship_expense", "expenditure", "Burs giderleri", ("burs", "scholarship")),
    ("academic_personnel_expense", "expenditure", "Akademik personel giderleri", ("akademik personel", "academic personnel", "academic staff")),
    ("administrative_personnel_expense", "expenditure", "İdari personel giderleri", ("idari personel", "administrative personnel", "administrative staff")),
    ("education_operating_expense", "expenditure", "Eğitim ve işletme giderleri", ("eğitim ve işletme", "education operating")),
    ("research_laboratory_expense", "expenditure", "Araştırma ve laboratuvar giderleri", ("araştırma ve laboratuvar", "research and laboratory")),
    ("facility_infrastructure_expense", "expenditure", "Tesis ve altyapı giderleri", ("tesis ve altyapı", "facility and infrastructure")),
    ("technology_expense", "expenditure", "Teknoloji giderleri", ("teknoloji", "technology")),
    ("other_operating_expense", "expenditure", "Diğer işletme giderleri", ("diğer işletme", "other operating")),
)


def _ratio(numerator: Decimal, denominator: Decimal) -> Optional[Decimal]:
    """Yüzde oranı. Payda sıfırsa uydurma değer yerine None döner."""
    if not denominator:
        return None
    return quantize_money(numerator / denominator * Decimal("100"))


def _match_total(entries: List[FinancialEntry], keys: tuple) -> Optional[Decimal]:
    """Anahtar kelimelerden birini içeren kalemlerin toplamı."""
    matched = [
        e.amount for e in entries if any(k in e.category.lower() for k in keys)
    ]
    if not matched:
        return None
    return quantize_money(sum(matched, Decimal("0")))


# ----------------------------------------------------------------------------
# Dönem işlemleri
# ----------------------------------------------------------------------------


def list_periods(db: Session) -> List[FinancialPeriod]:
    """Tüm mali dönemler, yeni yıldan eskiye."""
    return list(
        db.execute(
            select(FinancialPeriod).order_by(FinancialPeriod.academic_year.desc())
        ).scalars()
    )


def get_period(db: Session, academic_year: str) -> FinancialPeriod:
    """Akademik yıla göre dönem; bulunamazsa mevcut yılları da söyleyen 404."""
    period = db.execute(
        select(FinancialPeriod)
        .options(selectinload(FinancialPeriod.entries))
        .where(FinancialPeriod.academic_year == academic_year)
    ).scalars().first()
    if period is None:
        available = [p.academic_year for p in list_periods(db)]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"'{academic_year}' için mali dönem yok. "
                f"Mevcut dönemler: {', '.join(available) if available else 'hiç yok'}."
            ),
        )
    return period


def create_period(db: Session, payload: FinancialPeriodCreate) -> FinancialPeriod:
    """Yeni mali dönem açar; istenirse kalem yapısını sıfır tutarla kopyalar."""
    existing = db.execute(
        select(FinancialPeriod).where(
            FinancialPeriod.academic_year == payload.academic_year
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{payload.academic_year}' mali dönemi zaten açılmış.",
        )

    period = FinancialPeriod(
        academic_year=payload.academic_year,
        total_students=payload.total_students,
        total_graduates=payload.total_graduates,
    )
    db.add(period)
    db.flush()

    if payload.copy_categories_from:
        source = get_period(db, payload.copy_categories_from)
        # Tutarlar sıfırlanır: yeni yılın verisi henüz girilmemiştir, önceki
        # yılın rakamlarını taşımak gerçek olmayan bir bütçe gösterirdi.
        for entry in source.entries:
            db.add(
                FinancialEntry(
                    financial_period_id=period.id,
                    kind=entry.kind,
                    category=entry.category,
                    amount=Decimal("0"),
                )
            )

    db.commit()
    db.refresh(period)
    return period


def update_period(
    db: Session, academic_year: str, payload: FinancialPeriodUpdate
) -> FinancialPeriod:
    """Öğrenci/mezun sayısını günceller."""
    period = get_period(db, academic_year)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Güncellenecek alan gönderilmedi (total_students veya total_graduates).",
        )
    for field, value in data.items():
        setattr(period, field, value)
    db.commit()
    db.refresh(period)
    return period


# ----------------------------------------------------------------------------
# Kalem işlemleri
# ----------------------------------------------------------------------------


def book_entry(
    db: Session, academic_year: str, payload: FinancialEntryCreate
) -> FinancialEntry:
    """Kalem tutarını işler. Kalem yoksa oluşturur, varsa üzerine ekler."""
    if payload.kind not in ENTRY_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind alanı {' veya '.join(ENTRY_KINDS)} olmalı.",
        )
    if payload.amount == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tutar sıfır olamaz; kayıt bir değişiklik ifade etmeli.",
        )

    period = get_period(db, academic_year)
    category = payload.category.strip()

    entry = db.execute(
        select(FinancialEntry).where(
            FinancialEntry.financial_period_id == period.id,
            FinancialEntry.kind == payload.kind,
            FinancialEntry.category == category,
        )
    ).scalars().first()

    if entry is None:
        if payload.amount < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"'{category}' kalemi henüz açılmamış; "
                    "negatif tutarla yeni kalem oluşturulamaz."
                ),
            )
        entry = FinancialEntry(
            financial_period_id=period.id,
            kind=payload.kind,
            category=category,
            amount=quantize_money(payload.amount),
        )
        db.add(entry)
    else:
        # Negatif tutar düzeltme anlamına gelir; sonuç sıfırın altına inemez.
        new_amount = entry.amount + payload.amount
        entry.amount = quantize_money(max(Decimal("0"), new_amount))

    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: Session, academic_year: str, entry_id: int) -> dict:
    """Kalemi tamamen kaldırır (yanlış açılmış kalem için)."""
    period = get_period(db, academic_year)
    entry = db.execute(
        select(FinancialEntry).where(
            FinancialEntry.id == entry_id,
            FinancialEntry.financial_period_id == period.id,
        )
    ).scalars().first()
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entry_id} numaralı kalem bu dönemde bulunamadı.",
        )
    category = entry.category
    db.delete(entry)
    db.commit()
    return {"message": f"'{category}' kalemi silindi."}


# ----------------------------------------------------------------------------
# Bölüm bütçeleri
# ----------------------------------------------------------------------------


def _budget_status(realization: Optional[Decimal]) -> str:
    """Gerçekleşme oranını eşiklere göre sınıflandırır."""
    if realization is None:
        return "bütçe tanımsız"
    if realization <= BUDGET_WITHIN_LIMIT:
        return "bütçe içinde"
    if realization <= BUDGET_SLIGHT_OVER_LIMIT:
        return "hafif aşım"
    return "bütçe aşımı"


def budget_to_dict(budget: DepartmentBudget) -> dict:
    """Bölüm bütçesini türetilmiş göstergelerle birlikte döndürür."""
    realization = _ratio(budget.expenditure, budget.allocated_budget)
    cost_per_student = (
        quantize_money(budget.expenditure * Decimal("1000") / budget.student_count)
        if budget.student_count
        else None
    )
    department = budget.department
    return {
        "id": budget.id,
        "department_id": budget.department_id,
        "department_name": department.name if department else "Bilinmiyor",
        "faculty_name": (
            department.faculty.name if department and department.faculty else "Bilinmiyor"
        ),
        "student_count": budget.student_count,
        "revenue": budget.revenue,
        "expenditure": budget.expenditure,
        "allocated_budget": budget.allocated_budget,
        "balance": quantize_money(budget.revenue - budget.expenditure),
        "cost_per_student_thousand_usd": cost_per_student,
        "budget_realization_percent": realization,
        "budget_status": _budget_status(realization),
    }


def list_department_budgets(
    db: Session, academic_year: str, scope: Optional["Scope"] = None
) -> List[DepartmentBudget]:
    """Dönemin bölüm bütçeleri — kapsam verilmişse yalnızca o kapsamdakiler.

    Süzme `department_id` ile yapılır; bölüm ADI eşleştirilmez.
    """
    period = get_period(db, academic_year)
    sorgu = (
        select(DepartmentBudget)
        .options(
            selectinload(DepartmentBudget.department).selectinload(Department.faculty)
        )
        .where(DepartmentBudget.financial_period_id == period.id)
    )
    if scope is not None and scope.department_ids is not None:
        # Boş küme "hiçbiri" demektir; `in_([])` bunu doğru karşılar.
        sorgu = sorgu.where(DepartmentBudget.department_id.in_(scope.department_ids))
    return list(
        db.execute(sorgu.order_by(DepartmentBudget.expenditure.desc()))
        .scalars().unique()
    )


def upsert_department_budget(
    db: Session, academic_year: str, payload: DepartmentBudgetUpsert
) -> DepartmentBudget:
    """Bölüm bütçesini ekler veya günceller."""
    period = get_period(db, academic_year)

    department = db.get(Department, payload.department_id)
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{payload.department_id} numaralı bölüm bulunamadı.",
        )

    budget = db.execute(
        select(DepartmentBudget).where(
            DepartmentBudget.financial_period_id == period.id,
            DepartmentBudget.department_id == payload.department_id,
        )
    ).scalars().first()

    if budget is None:
        budget = DepartmentBudget(
            financial_period_id=period.id,
            department_id=payload.department_id,
            student_count=payload.student_count,
            revenue=quantize_money(payload.revenue),
            expenditure=quantize_money(payload.expenditure),
            allocated_budget=quantize_money(payload.allocated_budget),
        )
        db.add(budget)
    else:
        budget.student_count = payload.student_count
        budget.revenue = quantize_money(payload.revenue)
        budget.expenditure = quantize_money(payload.expenditure)
        budget.allocated_budget = quantize_money(payload.allocated_budget)

    db.commit()
    db.refresh(budget)
    return budget


# ----------------------------------------------------------------------------
# Özet ve trend
# ----------------------------------------------------------------------------


def _entry_rows(entries: List[FinancialEntry], total: Decimal) -> List[dict]:
    """Kalemleri büyükten küçüğe, payıyla birlikte döndürür."""
    rows = [
        {
            "id": e.id,
            "kind": e.kind,
            "category": e.category,
            "amount": e.amount,
            "share_percent": _ratio(e.amount, total),
            "source_type": "authoritative",
            "source_label": "Yetkili mali dönem kalemi",
            "provenance": "Yetkili kurumsal kayıt",
            "is_synthetic": False,
            "uploaded_source_id": None,
            "filename": None,
        }
        for e in entries
    ]
    rows.sort(key=lambda row: row["amount"], reverse=True)
    return rows


def _governed_exact(db: Session, metric_key: str, academic_year: str, scope) -> Optional[dict]:
    """Tek bir kapsam/yıl/metrik için izlenebilir ikincil değer."""
    from app.services import data_source_service

    resolved = data_source_service.uploaded_value(db, metric_key, academic_year, scope)
    if not resolved:
        return None
    return {
        "value": quantize_money(Decimal(str(resolved["value"]))),
        **data_source_service.source_provenance(resolved["source"]),
    }


def _fallback_counts(db: Session, academic_year: str, scope) -> tuple[int, int]:
    """Finans oranları için mevcut en güvenilir kapsam paydaları."""
    from app.services import academic_success_service, student_count

    students = int(student_count.total_for_scope(db, scope, academic_year) or 0)
    graduates = 0
    try:
        graduates = int(
            academic_success_service.university_overview(
                db, academic_year, scope
            ).get("graduate_count")
            or 0
        )
    except HTTPException:
        pass
    return students, graduates


def _uploaded_entry_rows(
    db: Session, academic_year: str, scope, kind: str, total: Decimal,
    *, native_entries: Optional[List[FinancialEntry]] = None,
) -> List[dict]:
    """Yetkili kalemi olmayan analitik kategorileri tamamlar."""
    native_entries = native_entries or []
    rows: List[dict] = []
    for index, (metric_key, spec_kind, label, tokens) in enumerate(
        FINANCIAL_CATEGORY_SPECS, start=1
    ):
        if spec_kind != kind:
            continue
        if any(
            any(token in entry.category.casefold() for token in tokens)
            for entry in native_entries
        ):
            continue
        resolved = _governed_exact(db, metric_key, academic_year, scope)
        if resolved is None:
            continue
        rows.append(
            {
                "id": -index,
                "kind": kind,
                "category": label,
                "amount": resolved["value"],
                "share_percent": _ratio(resolved["value"], total),
                **{key: value for key, value in resolved.items() if key != "value"},
            }
        )
    return rows


def _summary_provenance(rows: List[dict], has_native: bool) -> dict:
    uploaded = [row for row in rows if row.get("source_type") == "uploaded"]
    if not uploaded:
        return {
            "source_type": "authoritative",
            "source_label": "Yetkili mali dönem kaydı",
            "provenance": "Yetkili kurumsal kayıt",
            "is_synthetic": False,
            "uploaded_source_id": None,
            "filename": None,
        }
    if has_native:
        return {
            "source_type": "mixed",
            "source_label": "Yetkili mali kayıtlar + yönetilen analitik kalemler",
            "provenance": "Karma kaynak; her mali kalemde yetkili kayıt önceliklidir",
            "is_synthetic": any(row.get("is_synthetic") for row in uploaded),
            "uploaded_source_id": None,
            "filename": None,
        }
    ids = {row.get("uploaded_source_id") for row in uploaded}
    labels = {row.get("source_label") for row in uploaded}
    filenames = {row.get("filename") for row in uploaded}
    return {
        "source_type": "uploaded",
        "source_label": next(iter(labels)) if len(labels) == 1 else "Yüklenmiş yönetilen mali metrikler",
        "provenance": "SYNTHETIC_GENERATED" if any(row.get("is_synthetic") for row in uploaded) else "Yüklenmiş veri",
        "is_synthetic": any(row.get("is_synthetic") for row in uploaded),
        "uploaded_source_id": next(iter(ids)) if len(ids) == 1 else None,
        "filename": next(iter(filenames)) if len(filenames) == 1 else None,
    }


def _governed_financial_summary(db: Session, academic_year: str, scope) -> dict:
    """Mali dönem/bütçe yoksa tam kapsam eşleşmeli ikincil özet."""
    revenue = _governed_exact(db, "total_income", academic_year, scope)
    expenditure = _governed_exact(db, "total_expense", academic_year, scope)
    if revenue is None or expenditure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{scope.label}' için {academic_year} mali verisi yok.",
        )
    total_revenue = revenue["value"]
    total_expenditure = expenditure["value"]
    balance = quantize_money(total_revenue - total_expenditure)
    students, graduates = _fallback_counts(db, academic_year, scope)
    revenue_rows = (
        _uploaded_entry_rows(db, academic_year, scope, "revenue", total_revenue)
        if scope.is_university else []
    )
    expenditure_rows = (
        _uploaded_entry_rows(db, academic_year, scope, "expenditure", total_expenditure)
        if scope.is_university else []
    )
    personnel = _governed_exact(db, "personnel_cost", academic_year, scope)
    research = next(
        (row["amount"] for row in revenue_rows if row["category"] == "Araştırma gelirleri"),
        None,
    )
    scholarship = next(
        (row["amount"] for row in expenditure_rows if row["category"] == "Burs giderleri"),
        None,
    )
    all_source_rows = revenue_rows + expenditure_rows + [revenue, expenditure]
    return {
        "academic_year": academic_year,
        "total_revenue": total_revenue,
        "total_expenditure": total_expenditure,
        "balance": balance,
        "balance_status": "fazla" if balance >= 0 else "açık",
        "total_students": students,
        "total_graduates": graduates,
        "revenue_per_student_usd": (
            quantize_money(total_revenue * Decimal("1000000") / students)
            if students else None
        ),
        "cost_per_student_usd": (
            quantize_money(total_expenditure * Decimal("1000000") / students)
            if students else None
        ),
        "revenue_per_student_thousand_usd": (
            quantize_money(total_revenue * Decimal("1000") / students)
            if students else None
        ),
        "cost_per_student_thousand_usd": (
            quantize_money(total_expenditure * Decimal("1000") / students)
            if students else None
        ),
        "cost_per_graduate_million_usd": (
            quantize_money(total_expenditure / graduates) if graduates else None
        ),
        "personnel_expense_share_percent": (
            _ratio(personnel["value"], total_expenditure) if personnel else None
        ),
        "research_revenue_share_percent": (
            _ratio(research, total_revenue) if research is not None else None
        ),
        "scholarship_impact_percent": (
            _ratio(scholarship, total_revenue) if scholarship is not None else None
        ),
        "revenue_breakdown": sorted(revenue_rows, key=lambda row: row["amount"], reverse=True),
        "expenditure_breakdown": sorted(expenditure_rows, key=lambda row: row["amount"], reverse=True),
        **_summary_provenance(all_source_rows, has_native=False),
    }


def financial_summary(
    db: Session, academic_year: str, scope: Optional["Scope"] = None
) -> dict:
    """Mali dönem özeti ve tüm oran göstergeleri.

    KAPSAM
    ------
    Gelir/gider kalemleri (`financial_entries`) ÜNİVERSİTE seviyesindedir;
    bir bölüme ya da programa ait değildirler. Bu yüzden dar bir kapsam
    seçildiğinde üniversite toplamını döndürmek, kullanıcının gördüğü
    başlıkla veriyi çelişkiye düşürürdü ("Yazılım Mühendisliği · Toplam
    gelir 622 M$").

    Davranış:
      * üniversite kapsamı → bugünkü tam özet
      * fakülte/bölüm kapsamı → yalnızca o kapsamdaki BÖLÜM BÜTÇELERİNDEN
        toplanan özet; kalem kırılımı boş döner (kalemler birime bağlı değil)
      * program kapsamı → mali veri program seviyesinde TUTULMUYOR; 404
    """
    if scope is None:
        from app.services.scope import Scope
        scope = Scope()

    try:
        period = get_period(db, academic_year)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
        return _governed_financial_summary(db, academic_year, scope)

    if not scope.is_university:
        try:
            return _scoped_financial_summary(db, period, scope)
        except HTTPException as exc:
            if exc.status_code != status.HTTP_404_NOT_FOUND:
                raise
            return _governed_financial_summary(db, academic_year, scope)

    revenues = [e for e in period.entries if e.kind == "revenue"]
    expenditures = [e for e in period.entries if e.kind == "expenditure"]

    uploaded_revenue = None if revenues else _governed_exact(
        db, "total_income", academic_year, scope
    )
    uploaded_expenditure = None if expenditures else _governed_exact(
        db, "total_expense", academic_year, scope
    )
    total_revenue = (
        quantize_money(sum((e.amount for e in revenues), Decimal("0")))
        if revenues else uploaded_revenue and uploaded_revenue["value"]
    )
    total_expenditure = (
        quantize_money(sum((e.amount for e in expenditures), Decimal("0")))
        if expenditures else uploaded_expenditure and uploaded_expenditure["value"]
    )
    if total_revenue is None or total_expenditure is None:
        return _governed_financial_summary(db, academic_year, scope)
    balance = quantize_money(total_revenue - total_expenditure)

    personnel = _match_total(expenditures, PERSONNEL_CATEGORY_KEYS)
    research = _match_total(revenues, RESEARCH_CATEGORY_KEYS)
    scholarship = _match_total(expenditures, SCHOLARSHIP_CATEGORY_KEYS)

    students, graduates = _fallback_counts(db, academic_year, scope)
    students = period.total_students or students
    graduates = period.total_graduates or graduates
    revenue_rows = _entry_rows(revenues, total_revenue)
    expenditure_rows = _entry_rows(expenditures, total_expenditure)
    revenue_rows.extend(
        _uploaded_entry_rows(
            db, academic_year, scope, "revenue", total_revenue,
            native_entries=revenues,
        )
    )
    expenditure_rows.extend(
        _uploaded_entry_rows(
            db, academic_year, scope, "expenditure", total_expenditure,
            native_entries=expenditures,
        )
    )
    if personnel is None:
        uploaded_personnel = _governed_exact(
            db, "personnel_cost", academic_year, scope
        )
        personnel = uploaded_personnel and uploaded_personnel["value"]
    if research is None:
        research = next(
            (row["amount"] for row in revenue_rows if row["category"] == "Araştırma gelirleri"),
            None,
        )
    if scholarship is None:
        scholarship = next(
            (row["amount"] for row in expenditure_rows if row["category"] == "Burs giderleri"),
            None,
        )
    provenance_rows = revenue_rows + expenditure_rows
    if uploaded_revenue:
        provenance_rows.append(uploaded_revenue)
    if uploaded_expenditure:
        provenance_rows.append(uploaded_expenditure)

    return {
        "academic_year": period.academic_year,
        "total_revenue": total_revenue,
        "total_expenditure": total_expenditure,
        "balance": balance,
        "balance_status": "fazla" if balance >= 0 else "açık",
        "total_students": students,
        "total_graduates": graduates,
        # Tam USD: milyon USD × 1.000.000 / öğrenci sayısı.
        "revenue_per_student_usd": (
            quantize_money(total_revenue * Decimal("1000000") / students)
            if students
            else None
        ),
        "cost_per_student_usd": (
            quantize_money(total_expenditure * Decimal("1000000") / students)
            if students
            else None
        ),
        # Tutarlar milyon USD; bin USD'ye çevirmek için 1000 ile çarpılıyor.
        "revenue_per_student_thousand_usd": (
            quantize_money(total_revenue * Decimal("1000") / students)
            if students
            else None
        ),
        "cost_per_student_thousand_usd": (
            quantize_money(total_expenditure * Decimal("1000") / students)
            if students
            else None
        ),
        "cost_per_graduate_million_usd": (
            quantize_money(total_expenditure / graduates)
            if graduates
            else None
        ),
        "personnel_expense_share_percent": (
            _ratio(personnel, total_expenditure) if personnel is not None else None
        ),
        "research_revenue_share_percent": (
            _ratio(research, total_revenue) if research is not None else None
        ),
        "scholarship_impact_percent": (
            _ratio(scholarship, total_revenue) if scholarship is not None else None
        ),
        "revenue_breakdown": sorted(
            revenue_rows, key=lambda row: row["amount"], reverse=True
        ),
        "expenditure_breakdown": sorted(
            expenditure_rows, key=lambda row: row["amount"], reverse=True
        ),
        **_summary_provenance(provenance_rows, has_native=bool(revenues or expenditures)),
    }


def _scoped_financial_summary(db: Session, period, scope: "Scope") -> dict:
    """Fakülte/bölüm kapsamı için bölüm bütçelerinden toplanan özet."""
    if scope.is_program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Mali veri program seviyesinde tutulmuyor. '{scope.label}' "
                "için bütçe kaydı yok; en yakın mali kırılım bölüm bütçesidir."
            ),
        )

    butceler = list_department_budgets(db, period.academic_year, scope)
    if not butceler:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{scope.label}' için {period.academic_year} bütçe kaydı yok.",
        )

    # Bölüm bütçeleri tam USD tutulur; üniversite özeti milyon USD.
    # Aynı birimde sunmak için milyona çevriliyor.
    MILYON = Decimal("1000000")
    gelir = quantize_money(sum((b.revenue for b in butceler), Decimal("0")) / MILYON)
    gider = quantize_money(
        sum((b.expenditure for b in butceler), Decimal("0")) / MILYON
    )
    ogrenci = sum(b.student_count for b in butceler)
    denge = quantize_money(gelir - gider)

    return {
        "academic_year": period.academic_year,
        "total_revenue": gelir,
        "total_expenditure": gider,
        "balance": denge,
        "balance_status": "fazla" if denge >= 0 else "açık",
        "total_students": ogrenci,
        # Mezun sayısı bölüm bütçesinde tutulmuyor; üniversite sayısını
        # buraya yazmak kapsam sızıntısı olurdu.
        "total_graduates": 0,
        "revenue_per_student_usd": (
            quantize_money(gelir * MILYON / ogrenci) if ogrenci else None
        ),
        "cost_per_student_usd": (
            quantize_money(gider * MILYON / ogrenci) if ogrenci else None
        ),
        "revenue_per_student_thousand_usd": (
            quantize_money(gelir * Decimal("1000") / ogrenci) if ogrenci else None
        ),
        "cost_per_student_thousand_usd": (
            quantize_money(gider * Decimal("1000") / ogrenci) if ogrenci else None
        ),
        # Aşağıdakiler yalnızca üniversite seviyesinde anlamlıdır: kalem
        # kırılımı birime bağlı değildir. Uydurmak yerine None bırakılır.
        "cost_per_graduate_million_usd": None,
        "personnel_expense_share_percent": None,
        "research_revenue_share_percent": None,
        "scholarship_impact_percent": None,
        "revenue_breakdown": [],
        "expenditure_breakdown": [],
        "source_type": "authoritative",
        "source_label": "Yetkili bölüm bütçeleri",
        "provenance": "Yetkili kurumsal kayıt",
        "is_synthetic": False,
        "uploaded_source_id": None,
        "filename": None,
    }


def financial_trend(db: Session) -> List[dict]:
    """Yıllara göre gelir/gider ve değişim oranları."""
    periods = sorted(list_periods(db), key=lambda p: p.academic_year)
    if not periods:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Henüz mali dönem tanımlanmamış.",
        )

    rows: List[dict] = []
    previous: Optional[dict] = None
    for period in periods:
        entries = list(
            db.execute(
                select(FinancialEntry).where(
                    FinancialEntry.financial_period_id == period.id
                )
            ).scalars()
        )
        revenue = quantize_money(
            sum((e.amount for e in entries if e.kind == "revenue"), Decimal("0"))
        )
        expenditure = quantize_money(
            sum((e.amount for e in entries if e.kind == "expenditure"), Decimal("0"))
        )
        row = {
            "academic_year": period.academic_year,
            "total_revenue": revenue,
            "total_expenditure": expenditure,
            "balance": quantize_money(revenue - expenditure),
            # İlk yılda karşılaştırma tabanı yok; 0% yazmak "değişim olmadı"
            # anlamına gelirdi, bu yüzden None bırakılıyor.
            "revenue_change_percent": (
                _ratio(revenue - previous["total_revenue"], previous["total_revenue"])
                if previous
                else None
            ),
            "expenditure_change_percent": (
                _ratio(
                    expenditure - previous["total_expenditure"],
                    previous["total_expenditure"],
                )
                if previous
                else None
            ),
        }
        rows.append(row)
        previous = row
    return rows
