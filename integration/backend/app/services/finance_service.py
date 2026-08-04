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
from typing import Dict, List, Optional

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
        "cost_per_student_thousand_try": cost_per_student,
        "budget_realization_percent": realization,
        "budget_status": _budget_status(realization),
    }


def list_department_budgets(db: Session, academic_year: str) -> List[DepartmentBudget]:
    """Dönemin tüm bölüm bütçeleri."""
    period = get_period(db, academic_year)
    return list(
        db.execute(
            select(DepartmentBudget)
            .options(
                selectinload(DepartmentBudget.department).selectinload(Department.faculty)
            )
            .where(DepartmentBudget.financial_period_id == period.id)
            .order_by(DepartmentBudget.expenditure.desc())
        ).scalars().unique()
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
        }
        for e in entries
    ]
    rows.sort(key=lambda row: row["amount"], reverse=True)
    return rows


def financial_summary(db: Session, academic_year: str) -> dict:
    """Mali dönem özeti ve tüm oran göstergeleri."""
    period = get_period(db, academic_year)

    revenues = [e for e in period.entries if e.kind == "revenue"]
    expenditures = [e for e in period.entries if e.kind == "expenditure"]

    total_revenue = quantize_money(sum((e.amount for e in revenues), Decimal("0")))
    total_expenditure = quantize_money(
        sum((e.amount for e in expenditures), Decimal("0"))
    )
    balance = quantize_money(total_revenue - total_expenditure)

    personnel = _match_total(expenditures, PERSONNEL_CATEGORY_KEYS)
    research = _match_total(revenues, RESEARCH_CATEGORY_KEYS)
    scholarship = _match_total(expenditures, SCHOLARSHIP_CATEGORY_KEYS)

    return {
        "academic_year": period.academic_year,
        "total_revenue": total_revenue,
        "total_expenditure": total_expenditure,
        "balance": balance,
        "balance_status": "fazla" if balance >= 0 else "açık",
        "total_students": period.total_students,
        "total_graduates": period.total_graduates,
        # Tutarlar milyon TL; bin TL'ye çevirmek için 1000 ile çarpılıyor.
        "revenue_per_student_thousand_try": (
            quantize_money(total_revenue * Decimal("1000") / period.total_students)
            if period.total_students
            else None
        ),
        "cost_per_student_thousand_try": (
            quantize_money(total_expenditure * Decimal("1000") / period.total_students)
            if period.total_students
            else None
        ),
        "cost_per_graduate_million_try": (
            quantize_money(total_expenditure / period.total_graduates)
            if period.total_graduates
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
        "revenue_breakdown": _entry_rows(revenues, total_revenue),
        "expenditure_breakdown": _entry_rows(expenditures, total_expenditure),
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
