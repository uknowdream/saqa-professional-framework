import json

import pytest

from saqa.api import ApiResponse, assert_json_fields


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
