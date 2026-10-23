"""Deliberately modest label-anchored heuristic extractor, also backing offline MockLLM."""
from __future__ import annotations

import re

from co_extract.normalize import parse_number
from co_extract.schema import LLMChangeOrder, LLMOutput

LABELS = {
    'project_name': 'Project Name', 'project_number': 'Project Number',
    'change_order_number': 'Change Order Number', 'contract_number': 'Contract Number',
    'revision_number': 'Revision Number', 'date_issued': 'Date Issued',
    'owner': 'Owner', 'contractor': 'Contractor',
    'architect_or_engineer': 'Architect/Engineer', 'requested_by': 'Requested By',
    'title': 'Title', 'description': 'Description', 'reason': 'Reason',
    'change_type': 'Change Type', 'subtotal': 'Subtotal', 'markup': 'Markup',
    'tax': 'Tax', 'total_amount': 'Total Amount', 'currency': 'Currency',
    'original_contract_sum': 'Original Contract Sum', 'revised_contract_sum': 'Revised Contract Sum',
    'schedule_impact_days': 'Schedule Impact Days',
    'original_completion_date': 'Original Completion Date',
    'new_completion_date': 'New Completion Date', 'status': 'Status',
}
NUMS = {'subtotal', 'markup', 'tax', 'total_amount', 'original_contract_sum', 'revised_contract_sum'}


def baseline(pages) -> LLMOutput:
    """Parse explicit field labels without Gemini; this is NOT a learned AI system."""
    chunks = []
    for page in pages:
        segments = re.split(r'(?=^Change Order Number\s*:)', page.text, flags=re.M)
        for seg in segments:
            if 'Change Order Number:' in seg:
                chunks.append((page.num, seg))
            elif chunks:
                prev_num, prev = chunks[-1]
                chunks[-1] = (prev_num, prev + '\n' + seg)
    if not chunks:
        chunks = [(p.num, p.text) for p in pages if p.text.strip()]
    orders = []
    for pnum, chunk in chunks:
        data = {}
        for name, label in LABELS.items():
            match = re.search(r'^\s*' + re.escape(label) + r':\s*(.+)$', chunk, flags=re.M | re.I)
            if not match:
                continue
            raw = match.group(1).strip()
            value = raw
            if name in NUMS:
                value = parse_number(raw)
            elif name == 'schedule_impact_days':
                try:
                    value = int(raw)
                except ValueError:
                    value = None
            if value is None:
                continue
            data[name] = {'value': value, 'evidence': match.group(0).strip(), 'page': pnum,
                          'model_confidence': 0.60}
        line_items = []
        for line in re.findall(r'^Item:\s*(.+)$', chunk, flags=re.M):
            fragments = [x.strip() for x in line.split('|')]
            labels = ('description','quantity','unit','unit_cost','amount','cost_code')
            item = {}
            for index, fragment in enumerate(fragments[:6]):
                text = fragment.split(':', 1)[-1].strip()
                value = parse_number(text) if labels[index] in {'quantity','unit_cost','amount'} else text
                if value is None:
                    continue
                item[labels[index]] = {'value': value, 'evidence': 'Item: '+line, 'page': pnum,
                                       'model_confidence': 0.60}
            if item:
                line_items.append(item)
        if line_items:
            data['line_items'] = line_items
        if data:
            orders.append(LLMChangeOrder.model_validate(data))
    return LLMOutput(orders=orders)
