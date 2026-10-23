"""Separate minimal Gemini-facing schema from stricter evidence-aware internal results."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class StrField(BaseModel):
    value: str | None = None
    evidence: str | None = None
    page: int | None = None
    model_confidence: float | None = Field(default=None, ge=0, le=1)


class FloatField(BaseModel):
    value: float | None = None
    evidence: str | None = None
    page: int | None = None
    model_confidence: float | None = Field(default=None, ge=0, le=1)


class IntField(BaseModel):
    value: int | None = None
    evidence: str | None = None
    page: int | None = None
    model_confidence: float | None = Field(default=None, ge=0, le=1)


class DateField(StrField):
    pass


class EnumField(StrField):
    pass


class LLMLineItem(BaseModel):
    description: StrField = Field(default_factory=StrField)
    quantity: FloatField = Field(default_factory=FloatField)
    unit: StrField = Field(default_factory=StrField)
    unit_cost: FloatField = Field(default_factory=FloatField)
    amount: FloatField = Field(default_factory=FloatField)
    cost_code: StrField = Field(default_factory=StrField)


class LLMSignature(BaseModel):
    name: StrField = Field(default_factory=StrField)
    role: StrField = Field(default_factory=StrField)
    date: DateField = Field(default_factory=DateField)
    signed: EnumField = Field(default_factory=EnumField)


class LLMChangeOrder(BaseModel):
    project_name: StrField = Field(default_factory=StrField)
    project_number: StrField = Field(default_factory=StrField)
    change_order_number: StrField = Field(default_factory=StrField)
    contract_number: StrField = Field(default_factory=StrField)
    revision_number: StrField = Field(default_factory=StrField)
    date_issued: DateField = Field(default_factory=DateField)
    owner: StrField = Field(default_factory=StrField)
    contractor: StrField = Field(default_factory=StrField)
    architect_or_engineer: StrField = Field(default_factory=StrField)
    requested_by: StrField = Field(default_factory=StrField)
    title: StrField = Field(default_factory=StrField)
    description: StrField = Field(default_factory=StrField)
    reason: EnumField = Field(default_factory=EnumField)
    change_type: EnumField = Field(default_factory=EnumField)
    line_items: list[LLMLineItem] = Field(default_factory=list)
    subtotal: FloatField = Field(default_factory=FloatField)
    markup: FloatField = Field(default_factory=FloatField)
    tax: FloatField = Field(default_factory=FloatField)
    total_amount: FloatField = Field(default_factory=FloatField)
    currency: EnumField = Field(default_factory=EnumField)
    original_contract_sum: FloatField = Field(default_factory=FloatField)
    revised_contract_sum: FloatField = Field(default_factory=FloatField)
    schedule_impact_days: IntField = Field(default_factory=IntField)
    original_completion_date: DateField = Field(default_factory=DateField)
    new_completion_date: DateField = Field(default_factory=DateField)
    status: EnumField = Field(default_factory=EnumField)
    signatures: list[LLMSignature] = Field(default_factory=list)


class LLMOutput(BaseModel):
    orders: list[LLMChangeOrder] = Field(default_factory=list)


class ExtractedField(BaseModel):
    value: str | float | int | bool | None = None
    normalized_value: str | float | int | bool | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: str | None = None
    page: int | None = Field(default=None, ge=1)
    flags: list[str] = Field(default_factory=list)
    model_confidence: float | None = Field(default=None, ge=0, le=1)


class LineItem(BaseModel):
    description: ExtractedField = Field(default_factory=ExtractedField)
    quantity: ExtractedField = Field(default_factory=ExtractedField)
    unit: ExtractedField = Field(default_factory=ExtractedField)
    unit_cost: ExtractedField = Field(default_factory=ExtractedField)
    amount: ExtractedField = Field(default_factory=ExtractedField)
    cost_code: ExtractedField = Field(default_factory=ExtractedField)


class Signature(BaseModel):
    name: ExtractedField = Field(default_factory=ExtractedField)
    role: ExtractedField = Field(default_factory=ExtractedField)
    date: ExtractedField = Field(default_factory=ExtractedField)
    signed: ExtractedField = Field(default_factory=ExtractedField)


class ChangeOrder(BaseModel):
    project_name: ExtractedField = Field(default_factory=ExtractedField)
    project_number: ExtractedField = Field(default_factory=ExtractedField)
    change_order_number: ExtractedField = Field(default_factory=ExtractedField)
    contract_number: ExtractedField = Field(default_factory=ExtractedField)
    revision_number: ExtractedField = Field(default_factory=ExtractedField)
    date_issued: ExtractedField = Field(default_factory=ExtractedField)
    owner: ExtractedField = Field(default_factory=ExtractedField)
    contractor: ExtractedField = Field(default_factory=ExtractedField)
    architect_or_engineer: ExtractedField = Field(default_factory=ExtractedField)
    requested_by: ExtractedField = Field(default_factory=ExtractedField)
    title: ExtractedField = Field(default_factory=ExtractedField)
    description: ExtractedField = Field(default_factory=ExtractedField)
    reason: ExtractedField = Field(default_factory=ExtractedField)
    change_type: ExtractedField = Field(default_factory=ExtractedField)
    line_items: list[LineItem] = Field(default_factory=list)
    subtotal: ExtractedField = Field(default_factory=ExtractedField)
    markup: ExtractedField = Field(default_factory=ExtractedField)
    tax: ExtractedField = Field(default_factory=ExtractedField)
    total_amount: ExtractedField = Field(default_factory=ExtractedField)
    currency: ExtractedField = Field(default_factory=ExtractedField)
    original_contract_sum: ExtractedField = Field(default_factory=ExtractedField)
    revised_contract_sum: ExtractedField = Field(default_factory=ExtractedField)
    schedule_impact_days: ExtractedField = Field(default_factory=ExtractedField)
    original_completion_date: ExtractedField = Field(default_factory=ExtractedField)
    new_completion_date: ExtractedField = Field(default_factory=ExtractedField)
    status: ExtractedField = Field(default_factory=ExtractedField)
    signatures: list[Signature] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    field: str
    message: str


class RunMetadata(BaseModel):
    model: str = "none"
    prompt_version: str = "none"
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_estimate: float | None = None
    source_hash: str = ""
    pipeline_version: str = "0.1.0"
    trace_id: str = ""
    cache_hit: bool = False
    confidence_mode: str = "heuristic_uncalibrated"


class DocumentResult(BaseModel):
    orders: list[ChangeOrder] = Field(default_factory=list)
    document_confidence: float = Field(default=0, ge=0, le=1)
    needs_review: bool = True
    validation_report: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: RunMetadata = Field(default_factory=RunMetadata)


def from_llm(model: LLMChangeOrder) -> ChangeOrder:
    """Convert narrow model schema to rich internal schema without losing raw evidence."""
    data = model.model_dump()
    data["line_items"] = [LineItem(**line) for line in data["line_items"]]
    data["signatures"] = [Signature(**sig) for sig in data["signatures"]]
    return ChangeOrder.model_validate(data)


def iter_fields(order: ChangeOrder):
    """Yield dotted paths and all evidence-bearing field objects."""
    for key in ChangeOrder.model_fields:
        obj = getattr(order, key)
        if isinstance(obj, ExtractedField):
            yield key, obj
        elif isinstance(obj, list):
            for idx, nested in enumerate(obj):
                for child in type(nested).model_fields:
                    yield f"{key}[{idx}].{child}", getattr(nested, child)
