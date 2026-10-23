"""Fail-closed orchestration: ingestion -> extraction -> normalize -> validate -> confidence."""
from __future__ import annotations

import time
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from co_extract.config import Settings
from co_extract.confidence import load_params, score_orders
from co_extract.extract import extract_document
from co_extract.ingest import load_document
from co_extract.llm import LLMClient
from co_extract.normalize import normalize_order
from co_extract.prompts import PROMPT_VERSION
from co_extract.schema import DocumentResult, RunMetadata, iter_fields
from co_extract.security import detect_injection, log_event
from co_extract.validate import validate_order


class Pipeline:
    """Thread-safe wrapper with one LLM client; always returns an auditable result."""
    def __init__(self, client: LLMClient, settings: Settings | None = None,
                 calibration_path: Path | None = None):
        self.client = client
        self.settings = settings or Settings.from_env()
        self.params = load_params(calibration_path, client.model_id) if calibration_path else None

    def run(self, source: Path | str, *, self_consistency: int = 1, use_cache: bool = True,
            validation_retry: bool = True, grounding_enabled: bool = True, vision: bool = False) -> DocumentResult:
        """Never crash a batch: failure results have needs_review=True and no invented fields."""
        trace = uuid4().hex[:16]
        begin = time.perf_counter()
        result = DocumentResult(metadata=RunMetadata(model=self.client.model_id, prompt_version=PROMPT_VERSION,
                                trace_id=trace, confidence_mode='dev_fitted' if self.params else 'heuristic_uncalibrated'))
        try:
            document = load_document(source)
            result.metadata.source_hash = document.source_hash
            injected = any(detect_injection(page.text) for page in document.pages)
            if injected:
                result.warnings.append('possible_prompt_injection')
            orders, responses, warnings, agreement = extract_document(
                document, self.client, self_consistency=self_consistency, use_cache=use_cache,
                validation_retry=validation_retry, vision=vision)
            result.orders = orders
            result.warnings.extend(warnings)
            for order in orders:
                # Explicitly retain unpriced/TBD evidence with a null numeric value.
                if order.total_amount.value is None:
                    for page in document.pages:
                        match = re.search(r'(?im)^\s*Total Amount:\s*(?:TBD|to be negotiated|time and materials)[^\n]*', page.text)
                        if match:
                            order.total_amount.evidence = match.group(0).strip()
                            order.total_amount.page = page.num
                            if 'unpriced_tbd' not in order.total_amount.flags:
                                order.total_amount.flags.append('unpriced_tbd')
                            result.warnings.append('unpriced_total_requires_review')
                            break
                normalize_order(order)
                result.validation_report.extend(validate_order(order))
            result.document_confidence = score_orders(orders, document, params=self.params,
                                                      agreement=agreement, grounding_enabled=grounding_enabled)
            result.metadata.input_tokens = sum(x.input_tokens for x in responses)
            result.metadata.output_tokens = sum(x.output_tokens for x in responses)
            result.metadata.cache_hit = all(x.cache_hit for x in responses)
            if self.client.model_id.startswith('mock-'):
                result.metadata.cost_estimate = 0.0
            else:
                result.metadata.cost_estimate = round((result.metadata.input_tokens * self.settings.input_usd_per_m +
                                                      result.metadata.output_tokens * self.settings.output_usd_per_m)/1_000_000, 8)
            threshold = self.params['review_threshold'] if self.params else self.settings.review_threshold
            result.needs_review = (result.document_confidence < threshold or not orders or injected or
                                   bool(result.validation_report) or 'unpriced_total_requires_review' in result.warnings or
                                   any('not_grounded' in f.flags or 'conflicting_candidates' in f.flags
                                       for order in orders for _, f in iter_fields(order)))
        except Exception as exc:
            result.needs_review = True
            # Do not copy exception messages: provider errors can include request contents.
            result.warnings.append(f'pipeline_error:{type(exc).__name__}')
            log_event('failed', trace, status='review', extra={'error_type': type(exc).__name__})
        result.metadata.latency_ms = round((time.perf_counter()-begin)*1000)
        log_event('completed', trace, status='review' if result.needs_review else 'accepted',
                  extra={'order_count': len(result.orders), 'confidence': result.document_confidence})
        return result

    def batch(self, files: list[Path], **kwargs) -> list[DocumentResult]:
        """Bounded concurrency, same ordering, failures isolated per input."""
        with ThreadPoolExecutor(max_workers=self.settings.concurrency) as pool:
            return list(pool.map(lambda p: self.run(p, **kwargs), files))
