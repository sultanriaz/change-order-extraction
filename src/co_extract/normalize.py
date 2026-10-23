"""Conservative locale-aware normalization; ambiguity is an explicit failed normalization."""
from __future__ import annotations

import datetime as dt
import re

import pycountry

from co_extract.schema import ChangeOrder, ExtractedField, iter_fields

MONEY_FIELDS = {"subtotal", "markup", "tax", "total_amount", "original_contract_sum", "revised_contract_sum", "amount", "unit_cost", "quantity"}
DATES = {"date_issued", "original_completion_date", "new_completion_date", "date"}
REASONS = {"owner_request", "unforeseen_condition", "design_error", "code_requirement", "value_engineering", "other"}
CHANGE_TYPES = {"additive", "deductive", "no_cost", "time_only"}
STATUSES = {"draft", "pending", "approved", "rejected", "void"}


def parse_number(value: str | float | int | None) -> float | None:
    """Parse US/EU-formatted numbers, parentheses, or credits; reject TBD."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return float(value)
    text = value.strip()
    if not text or re.search(r"(?i)\b(tbd|pending|negotiat(?:ed|ion)|unknown|n/a)\b", text):
        return None
    negative = bool(re.search(r"(?i)\bcredit\b", text)) or text.startswith("(") or "-" in text[:2]
    numbers = re.findall(r"\d[\d,.\s]*\d|\d", text)
    if len(numbers) != 1:
        return None
    num = numbers[0].replace(" ", "")
    if "," in num and "." in num:
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif num.count(",") == 1:
        a, b = num.split(",")
        num = (a + "." + b) if len(b) in (1, 2) else (a + b)
    elif num.count(".") == 1:
        a, b = num.split(".")
        if len(b) == 3 and len(a) <= 3:
            num = a+b
    else:
        num = num.replace(",", "").replace(".", "", num.count(".")-1) if num.count(".") > 1 else num.replace(",", "")
    try:
        result = float(num)
        return -abs(result) if negative else result
    except ValueError:
        return None


def parse_date(value: str | None) -> tuple[str | None, bool]:
    """Return ISO date and whether locale ambiguity prevents safe parsing."""
    if value is None:
        return None, False
    text = value.strip()
    try:
        return dt.date.fromisoformat(text).isoformat(), False
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text)
    if m:
        a, b, year = map(int, m.groups())
        if 1 <= a <= 12 and 1 <= b <= 12:
            return None, True
        if a > 12:
            day, month = a, b
        else:
            month, day = a, b
        try:
            return dt.date(year, month, day).isoformat(), False
        except ValueError:
            return None, False
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat(), False
        except ValueError:
            continue
    return None, False


def valid_currency(code: str | None) -> bool:
    """Check ISO-4217 alpha-3 against locally packaged standard codes."""
    return bool(code and pycountry.currencies.get(alpha_3=code.upper()))


def normalize_field(name: str, item: ExtractedField) -> None:
    """Write normalized value separately; never silently modify extracted source value."""
    if item.value is None:
        return
    short = name.rsplit(".", 1)[-1]
    if short in DATES:
        iso, ambiguous = parse_date(str(item.value))
        item.normalized_value = iso
        if ambiguous and "ambiguous_date" not in item.flags:
            item.flags.append("ambiguous_date")
        if iso is None and "unparseable_date" not in item.flags and not ambiguous:
            item.flags.append("unparseable_date")
    elif short in MONEY_FIELDS:
        item.normalized_value = parse_number(item.value)
        if item.normalized_value is None and "unparseable_number" not in item.flags:
            item.flags.append("unparseable_number")
    elif short == "currency":
        item.normalized_value = str(item.value).upper()
    else:
        item.normalized_value = item.value


def normalize_order(order: ChangeOrder) -> ChangeOrder:
    """Normalize each nested field in place, preserving the document's verbatim value."""
    for name, field in iter_fields(order):
        normalize_field(name, field)
    return order
