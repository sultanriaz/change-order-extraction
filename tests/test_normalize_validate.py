import pytest
from co_extract.normalize import parse_number, parse_date, valid_currency, normalize_order
from co_extract.schema import ChangeOrder, ExtractedField, LineItem
from co_extract.validate import validate_order

@pytest.mark.parametrize(('src','target'), [('($1,250.00)',-1250.0), ('($1,250.00)',-1250.0), ('-$1,250',-1250.0), ('credit of $1,250',-1250.0), ('1.250,00 €',1250.0), ('1,250 USD',1250.0), ('TBD',None), ('',None), (0,0.0)])
def test_amounts(src,target):
    assert parse_number(src) == target

@pytest.mark.parametrize(('src','val','amb'), [('10/11/2026',None,True),('2026-08-17','2026-08-17',False),('13/11/2026','2026-11-13',False),('11/13/2026','2026-11-13',False)])
def test_dates(src,val,amb):
    assert parse_date(src)==(val,amb)

def test_currency():
    assert valid_currency('USD') and not valid_currency('XYZ')

def test_arithmetic_and_raw_preservation():
    order = ChangeOrder(total_amount=ExtractedField(value=100),subtotal=ExtractedField(value=90),markup=ExtractedField(value=1),tax=ExtractedField(value=0),line_items=[LineItem(quantity=ExtractedField(value=1),unit_cost=ExtractedField(value=10),amount=ExtractedField(value=20))])
    normalize_order(order)
    issues=validate_order(order)
    assert {'arithmetic_mismatch','line_item_mismatch'}.issubset({x.code for x in issues})
    assert order.total_amount.value == 100
    assert order.total_amount.normalized_value == 100.0
