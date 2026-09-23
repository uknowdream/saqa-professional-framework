import hashlib
import json
from pathlib import Path

from jsonschema import Draft4Validator

from scripts.contract_gate import CONTRACT, _schema

CONTRACT = Path("contracts/juice-shop.openapi.json")


def test_reference_contract_is_valid_openapi_shape():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert document["openapi"].startswith("3.")
    schema = document["paths"]["/rest/products/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    Draft4Validator.check_schema(schema)


def test_reference_contract_accepts_expected_fixture():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    schema = document["paths"]["/rest/products/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    Draft4Validator(schema).validate({"data": [{"id": 1, "name": "Apple Juice"}]})


def test_reference_contract_rejects_missing_data():
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))
    schema = document["paths"]["/rest/products/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    try:
        Draft4Validator(schema).validate({"items": []})
    except Exception as exc:
        assert "data" in str(exc)
    else:
        raise AssertionError("invalid payload unexpectedly passed contract")


def test_schema_evidence_digest_matches_contract_bytes():
    schema, digest = _schema()
    assert schema["type"] == "object"
    assert digest == hashlib.sha256(CONTRACT.read_bytes()).hexdigest()


def test_contract_gate_writes_contract_digest(monkeypatch, tmp_path):
    import scripts.contract_gate as gate

    class Response:
        status_code = 200
        content = b'{"data":[{"id":1,"name":"Apple Juice"}]}'
        headers = {"content-type": "application/json"}
        def json(self):
            return {"data": [{"id": 1, "name": "Apple Juice"}]}

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def get(self, *args, **kwargs):
            return Response()

    output = tmp_path / "contract.json"
    monkeypatch.setattr(gate, "OUTPUT", output)
    monkeypatch.setattr(gate.httpx, "Client", Client)
    assert gate.main() == 0
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert evidence["details"]["contract_sha256"] == hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
