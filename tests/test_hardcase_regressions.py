"""Train-split hard-case tests, so held-out TEST remains unavailable for tuning."""
import json
from pathlib import Path
import pytest
from co_extract.pipeline import Pipeline
from co_extract.llm import MockLLM

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=json.loads((ROOT/'data/synthetic/manifest.json').read_text())
TAGS=sorted({tag for row in MANIFEST if row['split']=='train' for tag in row['tags']})

@pytest.mark.parametrize('tag',TAGS)
def test_train_hard_case_tag(tag):
    spec=next(row for row in MANIFEST if row['split']=='train' and tag in row['tags'])
    result=Pipeline(MockLLM()).run(ROOT/spec['source'])
    assert result.orders, (tag,result.warnings)
    assert result.metadata.source_hash
    if tag=='non_summing':
        assert any(issue.code=='arithmetic_mismatch' for issue in result.validation_report)
    if tag=='ambiguous_date':
        assert any(issue.code=='ambiguous_date' for issue in result.validation_report)
    if tag=='prompt_injection':
        assert result.needs_review and 'possible_prompt_injection' in result.warnings
        assert result.orders[0].total_amount.value != 0
    if tag=='tbd':
        assert result.orders[0].total_amount.value is None
        assert 'unpriced_tbd' in result.orders[0].total_amount.flags
        assert result.orders[0].total_amount.evidence
