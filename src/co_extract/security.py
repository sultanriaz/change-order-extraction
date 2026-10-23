"""Non-authoritative injection hints and privacy-safe structured logging."""
from __future__ import annotations

import json
import logging
import re

INJECTIONS = [
    re.compile(r'(?i)ignore\s+(?:all\s+)?previous\s+instructions'),
    re.compile(r'(?i)(?:system|developer)\s+(?:prompt|message)\s*:'),
    re.compile(r'(?i)(?:set|replace|overwrite)\s+(?:the\s+)?total\s+(?:to|with)\s+\d+'),
    re.compile(r'(?i)do\s+not\s+(?:cite|mention|report)\s+this'),
]
EMAIL = re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')
PHONE = re.compile(r'(?<!\d)(?:\+?\d{1,3}[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)')


def detect_injection(text: str) -> bool:
    """Heuristic review signal, not a guarantee against prompt injection."""
    return any(pattern.search(text) for pattern in INJECTIONS)


def redact(text: str) -> str:
    """Replace common emails and phone formats before any log emission."""
    return PHONE.sub('[PHONE]', EMAIL.sub('[EMAIL]', text))


def log_event(name: str, trace_id: str, *, status: str, extra: dict | None = None) -> None:
    """Emit structured metadata only; never log source documents or secret API keys."""
    payload = {'event': name, 'trace_id': trace_id, 'status': status}
    if extra:
        payload.update({str(key): redact(str(value))[:120] for key, value in extra.items()})
    logging.getLogger('co_extract').info(json.dumps(payload, ensure_ascii=True))
