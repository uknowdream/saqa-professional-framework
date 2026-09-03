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
