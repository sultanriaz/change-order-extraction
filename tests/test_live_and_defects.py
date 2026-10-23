"""Regression tests for pre-submission audit findings and schema compatibility."""
import json
from unittest.mock import patch
from co_extract.schema import (
    LLMOutput, LLMChangeOrder, StrField, FloatField, from_llm, ChangeOrder
)
from co_extract.normalize import valid_currency
from co_extract.config import Settings
import co_extract.normalize as norm_mod


def test_schema_gemini_compatibility_no_bounds():
    """Ensure LLMOutput does not inject nested numeric range bounds that trigger Gemini 400."""
    schema = LLMOutput.model_json_schema()
    raw_schema_str = json.dumps(schema)
    assert "minimum" not in raw_schema_str
    assert "maximum" not in raw_schema_str


def test_llm_fields_ignore_extra_confidence():
    """Ensure legacy or mock payloads with model_confidence are accepted cleanly."""
    raw = {"value": "CO-999", "evidence": "CO-999", "page": 1, "model_confidence": 0.85}
    field = StrField.model_validate(raw)
    assert field.value == "CO-999"
    assert field.evidence == "CO-999"
    assert field.page == 1
    # Extra field model_confidence should be ignored without raising ValidationError
    assert not hasattr(field, "model_confidence")


def test_from_llm_conversion_preserves_internal_fields():
    """Verify conversion from LLMChangeOrder to internal ChangeOrder with ExtractedField."""
    llm_co = LLMChangeOrder.model_validate({
        "change_order_number": {"value": "CO-001", "evidence": "Change Order #001", "page": 1},
        "total_amount": {"value": 5000.0, "evidence": "$5,000.00", "page": 1},
    })
    co = from_llm(llm_co)
    assert isinstance(co, ChangeOrder)
    assert co.change_order_number.value == "CO-001"
    assert co.change_order_number.page == 1
    assert co.change_order_number.confidence == 0.0
    assert co.total_amount.value == 5000.0


def test_currency_fallback_without_pycountry():
    """Verify currency validation works both with pycountry and with internal fallback set."""
    assert valid_currency("USD") is True
    assert valid_currency("EUR") is True
    assert valid_currency("CAD") is True
    assert valid_currency("XYZ") is False
    assert valid_currency("") is False
    assert valid_currency(None) is False

    # Force pycountry=None to test fallback branch
    with patch.object(norm_mod, "pycountry", None):
        assert valid_currency("USD") is True
        assert valid_currency("EUR") is True
        assert valid_currency("XYZ") is False


def test_settings_default_model():
    """Verify default model is valid and supported."""
    settings = Settings.from_env()
    assert settings.model in {"gemini-2.5-flash", "gemini-3.8-flash"}
    assert settings.rpm >= 1
    assert settings.concurrency >= 1
