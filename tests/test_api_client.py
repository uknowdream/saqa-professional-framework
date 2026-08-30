from saqa.api_client import ApiResponse, assert_json_fields


def test_json_fields_are_validated():
    response = ApiResponse(200, {"content-type": "application/json"}, b'{"id": 1, "name": "QA"}', 1.5)
    assert assert_json_fields(response, ("id", "name"))["id"] == 1


def test_missing_json_field_is_rejected():
    response = ApiResponse(200, {}, b'{"id": 1}', 1.0)
    try:
        assert_json_fields(response, ("id", "email"))
    except AssertionError as exc:
        assert "email" in str(exc)
    else:
        raise AssertionError("missing field was not rejected")


def test_non_json_response_is_not_silently_accepted():
    response = ApiResponse(200, {}, b"not-json", 1.0)
    try:
        response.json()
    except ValueError:
        pass
    else:
        raise AssertionError("invalid JSON was accepted")
