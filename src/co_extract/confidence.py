"""Citation grounding, conservative field confidence and DEV-fitted logistic calibration."""
from __future__ import annotations

import json
import math
from pathlib import Path

from rapidfuzz import fuzz

from co_extract.ingest import Document
from co_extract.schema import ChangeOrder, ExtractedField, iter_fields

CRITICAL = ('change_order_number', 'total_amount', 'date_issued', 'owner', 'contractor')


def ground_score(field: ExtractedField, document: Document) -> float:
    """Compare a quote to the cited source page; missing/wrong page is never grounded."""
    if field.value is None:
        return 0.0
    if not field.evidence or not field.page:
        return 0.0
    page = next((p for p in document.pages if p.num == field.page), None)
    if page is None:
        return 0.0
    quoted = ' '.join(field.evidence.split())
    source = ' '.join((page.text + '\n' + '\n'.join(page.tables)).split())
    if quoted in source:
        return 1.0
    return float(fuzz.partial_ratio(quoted, source))/100 if quoted else 0.0


def features(field: ExtractedField, document: Document, agreement: float | None = None,
             *, grounding_enabled: bool = True) -> list[float]:
    """Order of features is versioned in saved parameters; model confidence is minor."""
    grounding = ground_score(field, document) if grounding_enabled else 0.5
    bad = any(x in str(field.flags) for x in ('mismatch', 'invalid_', 'ambiguous_', 'conflict:', 'suspicious', 'unparseable'))
    quality = 1.0 if next((p.source for p in document.pages if p.num == field.page), 'ocr') == 'text' else .45
    return [grounding, 0.0 if bad else 1.0, agreement if agreement is not None else .5,
            quality, field.model_confidence if field.model_confidence is not None else .5]


def heuristic_score(fs: list[float]) -> float:
    """Pre-calibration fallback, explicitly NOT a measured probability of correctness."""
    g, valid, agreement, quality, model = fs
    return max(0.0, min(1.0, (.55*g + .19*valid + .12*agreement + .11*quality + .03*model) * (.25 if g < .80 else 1)))


def predict(fs: list[float], params: dict | None) -> float:
    """Use DEV-fitted logistic weights when applicable or mark as heuristic."""
    if params and 'weights' in params:
        z = params['intercept'] + sum(x*w for x, w in zip(fs, params['weights']))
        return float(1/(1+math.exp(-max(-30,min(30,z)))))
    return heuristic_score(fs)


def score_orders(orders: list[ChangeOrder], document: Document, *, params: dict | None = None,
                 agreement: dict[str, float] | None = None, grounding_enabled: bool = True) -> float:
    """Populate scores and flags and return min-confidence across critical fields."""
    critical_scores = []
    for idx, order in enumerate(orders):
        for name, field in iter_fields(order):
            if field.value is None:
                continue
            grounded = ground_score(field, document)
            if grounded < .94:
                if 'not_grounded' not in field.flags:
                    field.flags.append('not_grounded')
            fs = features(field, document, (agreement or {}).get(f'{idx}:{name}'),
                          grounding_enabled=grounding_enabled)
            field.confidence = round(min(predict(fs, params), .20 if grounded < .94 else 1.0), 4)
        critical_scores.extend(getattr(order, key).confidence for key in CRITICAL)
    return round(min(critical_scores, default=0.0), 4)


def fit_dev(feature_rows: list[list[float]], correct: list[int], model_id: str,
            *, target_precision: float = .95) -> dict:
    """Fit DEV-only logistic calibration, pick threshold with measured DEV precision."""
    from sklearn.linear_model import LogisticRegression
    if len(feature_rows) != len(correct) or not feature_rows:
        raise ValueError('Mismatched or empty calibration inputs')
    if len(set(correct)) < 2:
        # Underidentified calibration must be reported, not presented as calibrated.
        return {'model_id': model_id, 'calibrated': False, 'reason': 'only_one_outcome_class',
                'review_threshold': 1.01, 'dev_size': len(correct)}
    clf = LogisticRegression(max_iter=500, class_weight='balanced', random_state=11)
    clf.fit(feature_rows, correct)
    probs = clf.predict_proba(feature_rows)[:, 1].tolist()
    eligible = []
    for t in sorted(set(round(x, 4) for x in probs)):
        sel = [y for p, y in zip(probs, correct) if p >= t]
        if sel and sum(sel)/len(sel) >= target_precision:
            eligible.append((t, len(sel)))
    threshold = min((x[0] for x in eligible), default=1.01)
    return {'model_id': model_id, 'calibrated': True, 'feature_names': ['grounding','validation','agreement','source_quality','model_reported'],
            'weights': clf.coef_[0].tolist(), 'intercept': float(clf.intercept_[0]),
            'review_threshold': threshold, 'dev_size': len(correct), 'target_dev_precision': target_precision}


def load_params(path: Path, model_id: str) -> dict | None:
    """Prevent accidentally applying MockLLM calibration weights to Gemini outputs."""
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return data if data.get('model_id') == model_id and data.get('calibrated') else None
