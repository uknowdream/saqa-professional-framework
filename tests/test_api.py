import hashlib
import json

import pytest

from saqa.api import ApiResponse, assert_json_contract, assert_json_fields, assert_json_list_cardinality


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


def test_api_response_sha256_is_deterministic_for_exact_body():
    body = b'{"status":"ok"}'
    response = ApiResponse(200, {}, body, 1.0)
    assert response.sha256 == hashlib.sha256(body).hexdigest()


def test_api_response_sha256_changes_when_body_changes():
    first = ApiResponse(200, {}, b'{"status":"ok"}', 1.0)
    second = ApiResponse(200, {}, b'{"status":"changed"}', 1.0)
    assert first.sha256 != second.sha256


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


def test_json_contract_accepts_list_minimum_and_maximum():
    response = ApiResponse(200, {}, b'{"data":["ok","qa"]}', 1.0)
    assert_json_contract(response, list_min_items={"data": 1}, list_max_items={"data": 2})


def test_json_contract_rejects_list_below_minimum():
    response = ApiResponse(200, {}, b'{"data":[]}', 1.0)
    with pytest.raises(AssertionError, match="expected at least 1"):
        assert_json_contract(response, list_min_items={"data": 1})


def test_json_contract_rejects_list_above_maximum():
    response = ApiResponse(200, {}, b'{"data":[1,2,3]}', 1.0)
    with pytest.raises(AssertionError, match="expected at most 2"):
        assert_json_contract(response, list_max_items={"data": 2})


def test_json_contract_rejects_negative_cardinality_configuration():
    response = ApiResponse(200, {}, b'{"data":[]}', 1.0)
    with pytest.raises(ValueError, match="cannot be negative"):
        assert_json_contract(response, list_min_items={"data": -1})


def test_json_list_cardinality_is_separate_from_structural_contract():
    response = ApiResponse(200, {}, b'{"data":[]}', 1.0)
    assert_json_contract(response, required_fields=("data",), field_types={"data": list})
    with pytest.raises(AssertionError, match="expected at least 1"):
        assert_json_list_cardinality(response, field="data", minimum=1)


def test_json_list_cardinality_rejects_inverted_bounds():
    response = ApiResponse(200, {}, b'{"data":[]}', 1.0)
    with pytest.raises(ValueError, match="cannot exceed maximum"):
        assert_json_list_cardinality(response, field="data", minimum=2, maximum=1)
