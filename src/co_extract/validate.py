"""Deterministic cross-field consistency and business-rule validation."""
from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from co_extract.normalize import CHANGE_TYPES, REASONS, STATUSES, valid_currency
from co_extract.schema import ChangeOrder, ExtractedField, ValidationIssue


def validate_order(order: ChangeOrder, *, tolerance: float = 0.02) -> list[ValidationIssue]:
    """Return machine-readable issues without changing the extraction or fixing totals."""
    issues: list[ValidationIssue] = []

    def emit(code: str, field: str, message: str, *, level: str = "warning") -> None:
        severity: Literal["info", "warning", "error"] = "error" if level == "error" else "warning"
        issues.append(ValidationIssue(code=code, severity=severity, field=field, message=message))
        obj: ExtractedField | None = getattr(order, field, None)
        if isinstance(obj, ExtractedField) and code not in obj.flags:
            obj.flags.append(code)

    def num(name: str) -> float | None:
        value = getattr(order, name).normalized_value
        return float(value) if isinstance(value, (int, float)) else None

    def mismatch(lhs: float, rhs: float) -> bool:
        return abs(lhs - rhs) > tolerance + 1e-9

    for name, choices in (("reason", REASONS), ("change_type", CHANGE_TYPES), ("status", STATUSES)):
        value = getattr(order, name).value
        if value is not None and str(value).lower() not in choices:
            emit("invalid_enum", name, f"Invalid {name} enum", level="error")
    curr = order.currency.value
    if curr is not None and not valid_currency(str(curr)):
        emit("invalid_currency", "currency", "Not an ISO 4217 alpha-3 currency", level="error")
    ident = order.change_order_number.value
    if ident is not None and (len(str(ident)) > 40 or len(str(ident)) < 3 or
                              str(ident).isdigit() and int(str(ident)) <= 150 or
                              len(re.sub(r"\D", "", str(ident))) >= 10):
        emit("suspicious_identifier", "change_order_number", "CO identifier resembles page/phone number")

    item_amounts = [item.amount.normalized_value for item in order.line_items]
    if order.line_items and all(isinstance(v, (float, int)) for v in item_amounts) and num("subtotal") is not None:
        subtotal_val = num("subtotal") or 0.0
        line_total = sum(float(v) for v in item_amounts if isinstance(v, (float, int)))
        if mismatch(line_total, subtotal_val):
            emit("arithmetic_mismatch", "subtotal", "Line-item sum differs from document subtotal", level="error")
    for i, item in enumerate(order.line_items):
        q, unit, amt = (getattr(item, k).normalized_value for k in ("quantity", "unit_cost", "amount"))
        if all(isinstance(v, (float, int)) for v in (q, unit, amt)) and mismatch(float(q)*float(unit), float(amt)):
            issues.append(ValidationIssue(code="line_item_mismatch", severity="error", field=f"line_items[{i}].amount",
                                          message="Quantity × unit cost differs from amount"))
            item.amount.flags.append("line_item_mismatch")
    parts = [num(k) for k in ("subtotal", "markup", "tax")]
    total = num("total_amount")
    if all(v is not None for v in parts) and total is not None:
        parts_sum = sum(float(v) for v in parts if v is not None)
        if mismatch(parts_sum, total):
            emit("arithmetic_mismatch", "total_amount", "Subtotal + markup + tax differs from total", level="error")
    original, revised = num("original_contract_sum"), num("revised_contract_sum")
    if original is not None and revised is not None and total is not None and mismatch(original+total, revised):
        emit("contract_sum_mismatch", "revised_contract_sum", "Original + change differs from revised contract")
    kind = order.change_type.value
    if kind and total is not None and ((kind == "additive" and total < 0) or
                                       (kind == "deductive" and total > 0) or
                                       (kind in ("no_cost", "time_only") and abs(total) > tolerance)):
        emit("sign_type_mismatch", "change_type", "Change type contradicts signed total")
    for name in ("date_issued", "original_completion_date", "new_completion_date"):
        field = getattr(order, name)
        if "ambiguous_date" in field.flags:
            emit("ambiguous_date", name, "Date order cannot be inferred from the document")
        elif field.value is not None and field.normalized_value is None:
            emit("invalid_date", name, "Unable to normalize date")
    start, end = order.original_completion_date.normalized_value, order.new_completion_date.normalized_value
    if isinstance(start, str) and isinstance(end, str):
        duration = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
        if duration < 0:
            emit("reverse_schedule", "new_completion_date", "New completion precedes original completion")
        impact = num("schedule_impact_days")
        if impact is not None and mismatch(impact, duration):
            emit("schedule_mismatch", "schedule_impact_days", "Schedule impact differs from date delta")
    return issues
