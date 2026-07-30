"""Modül 11 yanıt şemaları."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AlertResponse(BaseModel):
    """Üst yönetime gönderilen tek bir erken uyarı alarmı."""

    rule_key: str
    rule_name: str
    pdf_condition: str = Field(description="Alarmın karşıladığı PDF Bölüm 11 maddesi")
    severity: str = Field(description="kritik | yuksek | orta | dusuk")
    scope: str = Field(description="program | university | unit")
    scope_code: str
    scope_name: str
    academic_year: str
    message: str
    observed_value: float
    threshold_value: Optional[float] = None
    recommended_action: str
    data_source: str


class ScopeAlertCount(BaseModel):
    """Bir kapsamın aldığı alarm sayısı."""

    scope_code: str
    alert_count: int


class AlertSummaryResponse(BaseModel):
    """Alarmların önem ve kapsam bazlı özeti."""

    total_alerts: int
    by_severity: Dict[str, int]
    by_scope: Dict[str, int]
    most_at_risk: List[ScopeAlertCount]


class RuleCatalogResponse(BaseModel):
    """Tanımlı bir erken uyarı kuralı."""

    key: str
    name: str
    pdf_condition: str
    scope: str
    implemented: bool = Field(
        description="False ise kural tanımlı ancak veri kaynağı henüz bağlanmadı"
    )
    data_source: str
    thresholds: Dict[str, float]
