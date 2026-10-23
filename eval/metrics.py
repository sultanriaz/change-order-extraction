"""Deterministic matching and metrics, separated from extraction/calibration."""
from __future__ import annotations

from collections import defaultdict

from rapidfuzz import fuzz

from co_extract.normalize import DATES, MONEY_FIELDS
from co_extract.schema import ChangeOrder, ExtractedField


FIELDS = [name for name in ChangeOrder.model_fields if name not in {'line_items','signatures'}]


def equal(field: str, predicted: object, expected: object) -> bool:
    """Typed matching: numeric tolerance; normalized dates; fuzzy free text."""
    if predicted is None or expected is None:
        return predicted is expected
    if field in MONEY_FIELDS or field == 'schedule_impact_days':
        try:
            return abs(float(predicted)-float(expected)) <= 0.02
        except (TypeError, ValueError):
            return False
    if field in DATES or field.endswith('_date'):
        return str(predicted) == str(expected)
    if field in {'change_order_number','contract_number','project_number','revision_number',
                 'currency','reason','status','change_type','cost_code'}:
        return str(predicted).strip().casefold() == str(expected).strip().casefold()
    return fuzz.ratio(str(predicted).strip().casefold(), str(expected).strip().casefold()) >= 90


def align_orders(orders: list[ChangeOrder], references: list[dict]) -> list[tuple[ChangeOrder | None, dict | None]]:
    """Prefer CO-number identity; account for unmatched references and predicted extras."""
    output = []
    used: set[int] = set()
    for ref in references:
        index = next((i for i, order in enumerate(orders) if i not in used and
                      equal('change_order_number', order.change_order_number.value, ref.get('change_order_number'))), None)
        if index is None:
            index = next((i for i in range(len(orders)) if i not in used), None)
        if index is None:
            output.append((None, ref))
        else:
            used.add(index)
            output.append((orders[index], ref))
    output.extend((order, None) for i, order in enumerate(orders) if i not in used)
    return output


def flatten(pairs):
    """Return field-level evaluation rows for every expected and predicted order."""
    rows = []
    for order, ref in pairs:
        for name in FIELDS:
            obj: ExtractedField = getattr(order, name) if order is not None else ExtractedField()
            raw = obj.normalized_value if obj.normalized_value is not None else (
                None if ('ambiguous_date' in obj.flags or 'unparseable_date' in obj.flags) else obj.value)
            expected = (ref or {}).get(name)
            if expected is None and raw is None:
                classification = 'tn'
            elif expected is None:
                classification = 'fp'
            elif raw is None:
                classification = 'fn'
            elif equal(name, raw, expected):
                classification = 'tp'
            else:
                classification = 'wrong'  # wrong counts as both FP and FN
            rows.append({'field':name, 'result':classification, 'confidence':obj.confidence if raw is not None else None,
                         'expected':expected, 'predicted':raw})
    return rows


def summarize(rows) -> dict:
    """Compute per-field and overall binary extraction precision/recall/F1, null quality."""
    c = defaultdict(int)
    for row in rows:
        c[row['result']]+=1
    tp, fp, fn = c['tp'], c['fp']+c['wrong'], c['fn']+c['wrong']
    precision = tp/(tp+fp) if tp+fp else 0.0
    recall = tp/(tp+fn) if tp+fn else 0.0
    return {'precision': precision,'recall':recall, 'f1':(2*precision*recall/(precision+recall)) if precision+recall else 0.0,
            'true_positive':tp,'false_positive':fp,'false_negative':fn,
            'correct_null_rate':c['tn']/(c['tn']+c['fp']) if c['tn']+c['fp'] else None,
            'hallucination_rate':c['fp']/(c['tn']+c['fp']) if c['tn']+c['fp'] else None,
            'n_rows':len(rows)}


def line_item_f1(pairs) -> float:
    """Greedy item match by grounded description, cost code and amount."""
    tp=fp=fn=0
    for order, ref in pairs:
        predicted = list(order.line_items if order else [])
        expected = list((ref or {}).get('line_items', []))
        used = set()
        for truth in expected:
            hit = next((i for i, line in enumerate(predicted) if i not in used and
                        equal('description', line.description.value, truth.get('description')) and
                        equal('amount', line.amount.normalized_value, truth.get('amount'))), None)
            if hit is None:
                fn+=1
            else:
                tp+=1; used.add(hit)
        fp+=len(predicted)-len(used)
    return 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0


def ece(rows, bins: int = 10) -> tuple[float, list[dict]]:
    """ECE conditional on predicted non-null fields; excludes abstained nulls."""
    predictions = [(r['confidence'], int(r['result']=='tp')) for r in rows if r['confidence'] is not None]
    if not predictions:
        return 0.0, []
    buckets=[]; total=0
    for idx in range(bins):
        lo=idx/bins; hi=(idx+1)/bins
        batch=[(p,y) for p,y in predictions if lo<=p<hi or (idx==bins-1 and p==1)]
        if batch:
            conf=sum(p for p,_ in batch)/len(batch)
            accuracy=sum(y for _,y in batch)/len(batch)
            total+=abs(conf-accuracy)*len(batch)/len(predictions)
            buckets.append({'bin':idx,'count':len(batch),'confidence':conf,'accuracy':accuracy})
    return total,buckets


def accept_curve(rows):
    """Documented field-level selective-risk curve; does not imply document acceptance."""
    data = [(r['confidence'],int(r['result']=='tp')) for r in rows if r['confidence'] is not None]
    return [{'threshold':t,'coverage':sum(p>=t for p,_ in data)/len(data) if data else 0.0,
             'error_rate': (sum(1-y for p,y in data if p>=t)/sum(p>=t for p,_ in data)
                            if sum(p>=t for p,_ in data) else None)} for t in [0,.2,.4,.6,.8,.9,.95,1.0]]
