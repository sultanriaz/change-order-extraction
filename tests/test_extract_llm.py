from co_extract.llm import MockLLM
from co_extract.ingest import Page, Document
from co_extract.prompts import page_prompt
from co_extract.extract import parse_reply, extract_document, merge_orders, windows
from co_extract.schema import ChangeOrder, ExtractedField

def test_mock_produces_schema():
    page=Page(num=1,text='Change Order Number: CO-31\nTotal Amount: ($1,250.00)\nOwner: Built Sample')
    parsed=parse_reply(MockLLM().complete(page_prompt([page]),source_hash='x').text)
    assert parsed.orders[0].total_amount.value == -1250

def test_windows():
    doc=Document(pages=[Page(num=i,text='example') for i in range(1,10)], source_hash='x',path='example.txt')
    assert [len(x) for x in windows(doc,size=4,overlap=1)] == [4,4,3]

def test_conflict_merge():
    lhs=ChangeOrder(change_order_number=ExtractedField(value='CO-1'),total_amount=ExtractedField(value=100))
    rhs=ChangeOrder(change_order_number=ExtractedField(value='CO-1'),total_amount=ExtractedField(value=250))
    order=merge_orders([lhs,rhs])[0]
    assert order.total_amount.value == 100
    assert 'conflicting_candidates' in order.total_amount.flags

def test_multiple_orders():
    p=Page(num=1,text='Change Order Number: CO-1\nTotal Amount: $10.00\nChange Order Number: CO-2\nTotal Amount: $20.00')
    doc=Document(pages=[p],source_hash='x',path='x.txt')
    orders,*_=extract_document(doc,MockLLM())
    assert [it.change_order_number.value for it in orders] == ['CO-1','CO-2']
