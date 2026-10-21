from copy import deepcopy

import pytest

from saqa.native_mobile import SCHEMA, validate_native_mobile_evidence


def payload():
    return {
        "schema": SCHEMA, "platform": "android", "package_id": "com.example.app",
        "app_sha256": "a" * 64, "test_run_id": "run-2026-001",
        "executed_at": "2026-10-21T10:00:00Z",
        "device": {"os_version": "Android 15", "model": "Pixel_8_API_35", "runtime": "emulator"},
        "tests": [{"test_id": "launch", "status": "PASS"}, {"test_id": "navigation", "status": "PASS"}],
    }


def test_valid_native_android_evidence_passes_contract():
    result = validate_native_mobile_evidence(payload())
    assert result["status"] == "PASS"
    assert result["platform"] == "android"
    assert result["test_count"] == 2
    assert result["evidence_contract_only"] is True


def test_native_failure_is_never_hidden():
    value = payload()
    value["tests"][1]["status"] = "FAIL"
    assert validate_native_mobile_evidence(value)["status"] == "FAIL"


@pytest.mark.parametrize("status", ["BLOCKED", "UNVERIFIED"])
def test_incomplete_native_run_is_not_pass(status):
    value = payload()
    value["tests"][0]["status"] = status
    assert validate_native_mobile_evidence(value)["status"] == "UNVERIFIED"


def test_ios_requires_bundle_id():
    value = payload()
    value["platform"] = "ios"
    value["bundle_id"] = "com.example.ios"
    value.pop("package_id")
    assert validate_native_mobile_evidence(value)["app_id"] == "com.example.ios"


@pytest.mark.parametrize("bad", [None, [], "schema"])
def test_wrong_payload_schema_rejected(bad):
    with pytest.raises(ValueError, match="schema"):
        validate_native_mobile_evidence(bad)


@pytest.mark.parametrize("field", ["test_run_id", "app_sha256", "executed_at"])
def test_required_provenance_is_validated(field):
    value = payload()
    value[field] = ""
    with pytest.raises(ValueError):
        validate_native_mobile_evidence(value)


def test_timezone_naive_timestamp_rejected():
    value = payload()
    value["executed_at"] = "2026-10-21T10:00:00"
    with pytest.raises(ValueError, match="timezone"):
        validate_native_mobile_evidence(value)


def test_missing_device_metadata_rejected():
    value = payload()
    del value["device"]["runtime"]
    with pytest.raises(ValueError, match="device.runtime"):
        validate_native_mobile_evidence(value)


def test_duplicate_test_id_rejected():
    value = payload()
    value["tests"].append(deepcopy(value["tests"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_native_mobile_evidence(value)


def test_empty_tests_rejected():
    value = payload()
    value["tests"] = []
    with pytest.raises(ValueError, match="non-empty array"):
        validate_native_mobile_evidence(value)


def test_unknown_status_rejected():
    value = payload()
    value["tests"][0]["status"] = "CERTIFIED"
    with pytest.raises(ValueError, match="status is invalid"):
        validate_native_mobile_evidence(value)

@pytest.mark.parametrize("platform", [None, [], {}, "windows"])
def test_invalid_platform_is_rejected(platform):
    value = payload()
    value["platform"] = platform
    with pytest.raises(ValueError, match="platform must be android or ios"):
        validate_native_mobile_evidence(value)


def test_ios_bundle_id_missing_is_rejected_even_when_android_id_exists():
    value = payload()
    value["platform"] = "ios"
    value.pop("package_id")
    with pytest.raises(ValueError, match="bundle_id"):
        validate_native_mobile_evidence(value)


@pytest.mark.parametrize(("platform", "field", "bad"), [
    ("android", "package_id", "x y; rm -rf"),
    ("android", "package_id", "com"),
    ("ios", "bundle_id", "x y; rm -rf"),
    ("ios", "bundle_id", "com"),
])
def test_native_app_identifiers_must_match_platform_format(platform, field, bad):
    value = payload()
    value["platform"] = platform
    value.pop("package_id", None)
    value.pop("bundle_id", None)
    value[field] = bad
    with pytest.raises(ValueError, match="valid reverse-domain identifier"):
        validate_native_mobile_evidence(value)


def test_future_execution_timestamp_is_rejected():
    value = payload()
    value["executed_at"] = "2099-01-01T00:00:00Z"
    with pytest.raises(ValueError, match="must not be in the future"):
        validate_native_mobile_evidence(value)
