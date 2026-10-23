"""LLM extraction, schema repair, page-window overlap, and conflicting-field merge."""
from __future__ import annotations

import json
from collections import defaultdict

from pydantic import ValidationError

from co_extract.ingest import Document
from co_extract.llm import LLMClient, LLMResponse, ModelError
from co_extract.prompts import page_prompt
from co_extract.schema import ChangeOrder, LLMOutput, from_llm, iter_fields


def windows(document: Document, size: int = 4, overlap: int = 1):
    """Produce bounded windows with overlap and stable page indices."""
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError('Invalid window configuration')
    step = size - overlap
    for start in range(0, len(document.pages), step):
        chunk = document.pages[start:start+size]
        if chunk:
            yield chunk
        if start+size >= len(document.pages):
            break


def parse_reply(reply: str) -> LLMOutput:
    """Validate the raw returned text, never trusting the SDK parsed object alone."""
    return LLMOutput.model_validate_json(reply)


def merge_orders(collection: list[ChangeOrder]) -> list[ChangeOrder]:
    """Merge matching CO IDs; retain conflicts as flags, never silently overwrite."""
    grouped: dict[str, ChangeOrder] = {}
    anonymous: list[ChangeOrder] = []
    for order in collection:
        key = str(order.change_order_number.value or '').strip().casefold()
        if not key:
            anonymous.append(order)
            continue
        if key not in grouped:
            grouped[key] = order
            continue
        master = grouped[key]
        for name, item in iter_fields(order):
            if '[' in name:  # preserve distinct lines below, don't merge by array index
                continue
            dest = getattr(master, name)
            if dest.value is None and item.value is not None:
                setattr(master, name, item.model_copy(deep=True))
            elif dest.value is not None and item.value is not None and str(dest.value) != str(item.value):
                flag = 'conflict:' + str(item.value)[:60]
                if flag not in dest.flags:
                    dest.flags.append(flag)
                if 'conflicting_candidates' not in dest.flags:
                    dest.flags.append('conflicting_candidates')
        existing = {(str(it.description.value), str(it.amount.value), it.description.page) for it in master.line_items}
        for line in order.line_items:
            keyline = (str(line.description.value), str(line.amount.value), line.description.page)
            if keyline not in existing:
                master.line_items.append(line)
                existing.add(keyline)
        for sig in order.signatures:
            if sig not in master.signatures:
                master.signatures.append(sig)
    return list(grouped.values())+anonymous


def extract_document(document: Document, client: LLMClient, *, self_consistency: int = 1,
                     use_cache: bool = True, validation_retry: bool = True,
                     vision: bool = False) -> tuple[list[ChangeOrder], list[LLMResponse], list[str], dict[str, float]]:
    """Extract every page window with bounded JSON-validation feedback and optional agreement."""
    responses: list[LLMResponse] = []
    orders: list[ChangeOrder] = []
    warnings: list[str] = []
    repetitions: list[list[ChangeOrder]] = []
    for part in windows(document):
        prompt = page_prompt(part)
        feedback = ''
        parsed = None
        for attempt in range(3 if validation_retry else 1):
            try:
                pdf_bytes = None
                if vision and any(p.source == 'ocr' for p in part) and document.path.endswith('.pdf'):
                    pdf_bytes = __import__('pathlib').Path(document.path).read_bytes()
                answer = client.complete(prompt, source_hash=document.source_hash,
                                         feedback=feedback, use_cache=use_cache,
                                         pdf_bytes=pdf_bytes, structured=attempt == 0)
                responses.append(answer)
                parsed = parse_reply(answer.text)
                if not parsed.orders:
                    raise ValueError('No orders returned by the model')
                break
            except (ValidationError, ValueError) as exc:
                feedback = str(exc)[:1200]
                warnings.append(f'Invalid model JSON, retry {attempt+1}: {type(exc).__name__}')
        if parsed is None or not parsed.orders:
            raise ModelError('Failed schema validation after bounded repair attempts')
        orders.extend(from_llm(row) for row in parsed.orders)
        if self_consistency > 1:
            for _ in range(self_consistency-1):
                try:
                    answer = client.complete(prompt, source_hash=document.source_hash, temperature=.5,
                                             use_cache=use_cache)
                    responses.append(answer)
                    repetitions.append([from_llm(row) for row in parse_reply(answer.text).orders])
                except (ModelError, ValidationError):
                    warnings.append('Self-consistency sample failed; agreement unavailable')
    combined = merge_orders(orders)
    agreement: dict[str, float] = {}
    if repetitions:
        for i, primary in enumerate(combined):
            for name, field in iter_fields(primary):
                values = []
                for sample in repetitions:
                    matched = next((it for it in sample if it.change_order_number.value == primary.change_order_number.value), None)
                    if matched is not None and '[' not in name:
                        values.append(getattr(matched, name).value)
                if values and field.value is not None:
                    agreement[f'{i}:{name}'] = sum(str(v)==str(field.value) for v in values)/len(values)
    return combined, responses, warnings, agreement
