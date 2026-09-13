import json

import pytest

from saqa.api import ApiResponse, assert_json_contract, assert_json_fields


def test_json_field_validation_accepts_expected_object():
    response = ApiResponse(200, {"content-type": "application/json"}, json.dumps({"id": 1, "name": "QA"}).encode(), 2.5)
    assert response.ok
    assert_json_fields(response, ("id", "name"))


def test_json_field_validation_reports_missing_fields():
    response = ApiResponse(200, {}, b'{"id":1}', 1.0)
    with pytest.raises(AssertionError, match="missing JSON fields: name"):
        assert_json_fields(response, ("id", "name"))


def test_transport_error_is_not_treated_as_success():
    response = ApiResponse(0, {}, b"", 10.0, error="transport error")
    assert not response.ok
    with pytest.raises(AssertionError, match="transport error"):
        assert_json_fields(response, ("id",))


def test_non_json_response_is_rejected():
    response = ApiResponse(200, {}, b"not-json", 1.0)
    with pytest.raises(AssertionError, match="not valid JSON"):
        assert_json_fields(response, ("id",))


def test_json_contract_accepts_field_and_list_item_types():
    response = ApiResponse(
        200,
        {},
        json.dumps({"count": 2, "data": ["apple", "banana"]}).encode(),
        2.0,
    )
    assert_json_contract(
        response,
        required_fields=("count", "data"),
        field_types={"count": int},
        list_item_types={"data": str},
    )


def test_json_contract_rejects_bool_for_integer_field():
    response = ApiResponse(200, {}, b'{"count":true}', 1.0)
    with pytest.raises(AssertionError, match="JSON field 'count' has type bool"):
        assert_json_contract(response, field_types={"count": int})


def test_json_contract_rejects_wrong_list_item_type():
    response = ApiResponse(200, {}, b'{"data":["ok",3]}', 1.0)
    with pytest.raises(AssertionError, match="item 1 has type int"):
        assert_json_contract(response, list_item_types={"data": str})
