"""Dosya tabanlı ikincil veri kaynağı API şemaları."""

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_sheet: Optional[str] = Field(default=None, max_length=255)
    selected_table: Optional[str] = Field(default=None, max_length=255)


class SourceValidationRequest(SourceSelection):
    mapping: Dict[str, str]


class SourceImportRequest(SourceValidationRequest):
    confirm: bool = True

