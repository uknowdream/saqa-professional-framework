from saqa.api_contract import validate_json_contract


def test_json_object_contract_and_list_field():
    validate_json_contract(
        {"data": [], "query": "apple"},
        required_object_fields=("data", "query"),
        list_fields=("data",),
    )


def test_json_contract_rejects_missing_field():
    try:
        validate_json_contract({"data": []}, required_object_fields=("data", "query"))
    except AssertionError as exc:
        assert "query" in str(exc)
    else:
        raise AssertionError("missing contract field was accepted")


def test_json_contract_rejects_wrong_list_type():
    try:
        validate_json_contract({"data": {}}, list_fields=("data",))
    except AssertionError as exc:
        assert "data" in str(exc)
    else:
        raise AssertionError("wrong list type was accepted")

def test_api_contract_target_redaction_removes_path_query_credentials_and_preserves_ipv6():
    from scripts.api_contract_smoke import _redact_url
    assert _redact_url("http://user:secret@127.0.0.1:3000/private/token?q=hidden#x") == "http://127.0.0.1:3000"
    assert _redact_url("http://[::1]:3000/private") == "http://[::1]:3000"
