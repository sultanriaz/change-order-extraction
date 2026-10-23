from co_extract.schema import ChangeOrder, DocumentResult, LLMChangeOrder, from_llm

def test_schema_round_trip():
    output = from_llm(LLMChangeOrder.model_validate({"change_order_number": {"value": "CO-101", "evidence": "CO-101", "page": 1}}))
    assert ChangeOrder.model_validate(output.model_dump()).change_order_number.value == "CO-101"
    assert DocumentResult.model_validate(DocumentResult(orders=[output]).model_dump()).needs_review
