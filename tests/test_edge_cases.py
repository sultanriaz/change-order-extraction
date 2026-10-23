"""Branch-level adversarial regression cases for core deterministic safeguards."""
from __future__ import annotations

import json

import pytest

from co_extract.confidence import features, fit_dev, ground_score, heuristic_score, load_params, predict, score_orders
from co_extract.ingest import Document, Page
from co_extract.normalize import normalize_order, normalize_field, parse_number, parse_date, valid_currency
from co_extract.schema import ChangeOrder, ExtractedField
from co_extract.validate import validate_order


def fld(value):
    return ExtractedField(value=value, evidence=f'anything {value}', page=1)


@pytest.mark.parametrize('s,expected', [
    ('unknown', None), ('0.5', .5), ('250.00', 250), ('1.250.000', 1250000),
    ('$1,234.56', 1234.56), ('5 000', 5000), ('(50)', -50), ('12 and 13', None),
    ('-$45', -45), (False, None), (None,None), ('1,250,000', 1250000),
])
def test_parse_number_more(s,expected):
    assert parse_number(s)==expected


@pytest.mark.parametrize('src,iso,ambiguous', [
    ('Feb 19, 2026','2026-02-19',False), ('19 February 2026','2026-02-19',False),
    ('31/13/2026',None,False), ('not a date',None,False), ('12.02.2026',None,True),
    (None,None,False),
])
def test_parse_date_more(src,iso,ambiguous):
    assert parse_date(src)==(iso,ambiguous)


def test_fields_error_flags():
    broken=ExtractedField(value='not_a_date')
    normalize_field('date_issued',broken)
    assert 'unparseable_date' in broken.flags
    number=ExtractedField(value='TBD')
    normalize_field('total_amount',number)
    assert 'unparseable_number' in number.flags
    assert not valid_currency('XYZ')


def test_full_validation_matrix():
    order=ChangeOrder(
        change_order_number=fld('555-555-5555'), currency=fld('XYZ'),
        change_type=fld('no_cost'), status=fld('invalid'), reason=fld('inferred'),
        total_amount=fld(-100), original_contract_sum=fld(1000), revised_contract_sum=fld(2000),
        original_completion_date=fld('2026-12-08'),new_completion_date=fld('2026-12-01'),
        schedule_impact_days=fld(9), date_issued=fld('03/04/2026'),
    )
    normalize_order(order)
    issues=validate_order(order)
    codes={r.code for r in issues}
    assert {'invalid_enum','invalid_currency','suspicious_identifier','sign_type_mismatch',
            'contract_sum_mismatch','reverse_schedule','schedule_mismatch','ambiguous_date'} <= codes
    assert all(i.severity in ('warning','error') for i in issues)


def test_normalized_date_and_amount_remain_distinct():
    order=ChangeOrder(total_amount=fld('($1,250.00)'), currency=fld('eur'), date_issued=fld('2026-01-03'))
    normalize_order(order)
    assert order.total_amount.value=='($1,250.00)'
    assert order.total_amount.normalized_value == -1250
    assert order.currency.normalized_value == 'EUR'
    assert not validate_order(order)


def test_grounding_missing_page_and_fuzzy():
    doc=Document(pages=[Page(num=1,text='Change Order Number: CO-01')],source_hash='x',path='a.txt')
    assert ground_score(fld('absent'),doc) < .94
    assert ground_score(ExtractedField(value='CO-01',evidence=None,page=1),doc)==0
    assert ground_score(ExtractedField(value='CO-01',evidence='quote',page=7),doc)==0
    assert ground_score(ExtractedField(value=None,evidence='quote',page=1),doc)==0
    assert ground_score(ExtractedField(value='CO-01',evidence='Change Order Number: CO-01',page=1),doc)==1
    vals=features(fld('absent'),doc,agreement=0.25,grounding_enabled=False)
    assert len(vals)==5 and vals[0]==.5 and vals[2]==.25
    assert 0<=heuristic_score(vals)<=1
    assert 0<=predict(vals,None)<=1


def test_confidence_dev_fit_and_guard(tmp_path):
    points=[[1,1,.5,1,.6]]*7+[[0,0,.5,0,.1]]*5
    y=[1]*7+[0]*5
    params=fit_dev(points,y,'mock-regex-v1')
    assert params['calibrated'] and len(params['weights'])==5
    assert 0<=predict(points[0],params)<=1
    path=tmp_path/'params.json'
    path.write_text(json.dumps(params))
    assert load_params(path,'mock-regex-v1')==params
    assert load_params(path,'gemini-3.8-flash') is None
    assert load_params(tmp_path/'missing.json','mock-regex-v1') is None
    one_class=fit_dev([[1]*5,[1]*5],[1,1],'mock-regex-v1')
    assert not one_class['calibrated']
    with pytest.raises(ValueError):
        fit_dev([[1]*5],[0,1],'mock-regex-v1')


def test_no_grounding_ablation_must_not_mark_flag():
    doc=Document(pages=[Page(num=1,text='abc')],source_hash='x',path='a.txt')
    order=ChangeOrder(change_order_number=ExtractedField(value='C-13',page=1,evidence='made up quote'))
    score_orders([order],doc,grounding_enabled=False)
    assert 'not_grounded' not in order.change_order_number.flags
