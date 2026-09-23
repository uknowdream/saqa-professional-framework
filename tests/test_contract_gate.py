import json
from pathlib import Path

from jsonschema import Draft202012Validator

CONTRACT = Path("contracts/juice-shop.openapi.json")


def test_reference_contract_is_valid_openapi_shape():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert document["openapi"].startswith("3.")
    schema = document["paths"]["/rest/products/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    Draft202012Validator.check_schema(schema)


def test_reference_contract_accepts_expected_fixture():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    schema = document["paths"]["/rest/products/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    Draft202012Validator(schema).validate({"data": [{"id": 1, "name": "Apple Juice"}]})


def test_reference_contract_rejects_missing_data():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    schema = document["paths"]["/rest/products/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    try:
        Draft202012Validator(schema).validate({"items": []})
    except Exception as exc:
        assert "data" in str(exc)
    else:
        raise AssertionError("invalid payload unexpectedly passed contract")
