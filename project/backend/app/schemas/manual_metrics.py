"""Manuel gösterge API şemaları."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ScopeType = Literal["university", "faculty", "department", "program"]


class ManualMetricScope(BaseModel):
    scope_type: ScopeType
    faculty_id: Optional[int] = Field(default=None, ge=1)
    department_id: Optional[int] = Field(default=None, ge=1)
    program_id: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


class ManualMetricCreate(ManualMetricScope):
    metric_key: str = Field(min_length=1, max_length=80)
    screen_key: str = Field(min_length=1, max_length=40)
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    numeric_value: Optional[Decimal] = None
    text_value: Optional[str] = Field(default=None, max_length=4000)
    unit: Optional[str] = Field(default=None, max_length=40)
    source_note: Optional[str] = Field(default=None, max_length=500)
    note: Optional[str] = Field(default=None, max_length=4000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("numeric_value")
    @classmethod
    def finite_number(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and not value.is_finite():
            raise ValueError("Sayısal değer sonlu olmalıdır.")
        return value

    @model_validator(mode="after")
    def one_value(self):
        if self.numeric_value is None and not (self.text_value or "").strip():
            raise ValueError("numeric_value veya text_value alanlarından biri gereklidir.")
        if self.numeric_value is not None and (self.text_value or "").strip():
            raise ValueError("Aynı kayıtta hem sayısal hem metin değer gönderilemez.")
        return self


class ManualMetricUpdate(BaseModel):
    numeric_value: Optional[Decimal] = None
    text_value: Optional[str] = Field(default=None, max_length=4000)
    unit: Optional[str] = Field(default=None, max_length=40)
    source_note: Optional[str] = Field(default=None, max_length=500)
    note: Optional[str] = Field(default=None, max_length=4000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("numeric_value")
    @classmethod
    def finite_number(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and not value.is_finite():
            raise ValueError("Sayısal değer sonlu olmalıdır.")
        return value

    @model_validator(mode="after")
    def non_empty(self):
        if not self.model_fields_set:
            raise ValueError("Güncellenecek en az bir alan gönderilmelidir.")
        if "numeric_value" in self.model_fields_set and self.numeric_value is None:
            raise ValueError("numeric_value boş bırakılamaz.")
        if self.numeric_value is not None and (self.text_value or "").strip():
            raise ValueError("Aynı kayıtta hem sayısal hem metin değer gönderilemez.")
        return self


class ManualMetricEntryResponse(BaseModel):
    id: int
    metric_key: str
    metric_label: str
    screen_key: str
    scope_type: ScopeType
    scope_label: str
    faculty_id: Optional[int] = None
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    academic_year: str
    numeric_value: Optional[Decimal] = None
    text_value: Optional[str] = None
    unit: Optional[str] = None
    source_note: Optional[str] = None
    note: Optional[str] = None
    source_type: Literal["manual"] = "manual"
    source_label: str = "Manuel veri"
    editable: bool = True
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ManualMetricAvailability(BaseModel):
    definition: dict[str, Any]
    scope: dict[str, Any]
    academic_year: str
    status: Literal["unavailable", "manual", "authoritative"]
    can_add: bool
    reason: Optional[str] = None
    resolved_value: Optional[Decimal] = None
    unit: Optional[str] = None
    source_type: Optional[Literal["manual", "authoritative"]] = None
    source_label: Optional[str] = None
    editable: bool = False
    manual_entry: Optional[ManualMetricEntryResponse] = None

