"""Fail-closed contract for real native Android/iOS execution evidence.

This validates evidence shape only; it never executes an app or upgrades missing
device execution into a PASS.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

SCHEMA = "saqa.native-mobile-evidence.v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ANDROID_PACKAGE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
IOS_BUNDLE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9-]*(\.[A-Za-z][A-Za-z0-9-]*)+$")
PLATFORMS = {"android", "ios"}
STATUSES = {"PASS", "FAIL", "BLOCKED", "UNVERIFIED"}
FUTURE_CLOCK_SKEW = timedelta(minutes=5)


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def validate_native_mobile_evidence(payload: Any) -> dict[str, Any]:
    """Validate a native test report and derive its conservative result status."""
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("unsupported native mobile evidence schema")
    platform = payload.get("platform")
    if not isinstance(platform, str) or platform not in PLATFORMS:
        raise ValueError("platform must be android or ios")
    app_id_field = "package_id" if platform == "android" else "bundle_id"
    app_id = _nonempty(payload.get(app_id_field), app_id_field)
    pattern = ANDROID_PACKAGE_ID if platform == "android" else IOS_BUNDLE_ID
    if not pattern.fullmatch(app_id):
        raise ValueError(f"{app_id_field} must be a valid reverse-domain identifier")
    app_sha = payload.get("app_sha256")
    if not isinstance(app_sha, str) or not SHA256.fullmatch(app_sha):
        raise ValueError("app_sha256 must be a lowercase SHA-256 digest")
    run_id = _nonempty(payload.get("test_run_id"), "test_run_id")
    executed_at = _nonempty(payload.get("executed_at"), "executed_at")
    try:
        timestamp = datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("executed_at must be an ISO-8601 timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("executed_at must include a timezone")
    if timestamp.astimezone(timezone.utc) > datetime.now(timezone.utc) + FUTURE_CLOCK_SKEW:
        raise ValueError("executed_at must not be in the future beyond the five-minute clock-skew allowance")
    device = payload.get("device")
    if not isinstance(device, dict):
        raise ValueError("device must be an object")
    for field in ("os_version", "model", "runtime"):
        _nonempty(device.get(field), f"device.{field}")
    normalized_device = {key: device[key].strip() for key in ("os_version", "model", "runtime")}
    if "udid" in device:
        normalized_device["udid"] = _nonempty(device["udid"], "device.udid")
    tests = payload.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("tests must be a non-empty array")
    seen = set()
    normalized = []
    for index, item in enumerate(tests):
        if not isinstance(item, dict):
            raise ValueError(f"tests[{index}] must be an object")
        test_id = _nonempty(item.get("test_id"), f"tests[{index}].test_id")
        if test_id in seen:
            raise ValueError(f"duplicate native test_id: {test_id}")
        seen.add(test_id)
        status = item.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError(f"tests[{index}].status is invalid")
        row = {"test_id": test_id, "status": status}
        if "details" in item:
            row["details"] = _nonempty(item["details"], f"tests[{index}].details")
        normalized.append(row)
    if any(item["status"] == "FAIL" for item in normalized):
        status = "FAIL"
    elif all(item["status"] == "PASS" for item in normalized):
        status = "PASS"
    else:
        status = "UNVERIFIED"
    result = {
        "schema": SCHEMA,
        "status": status,
        "platform": platform,
        "app_id": app_id,
        "app_sha256": app_sha,
        "test_run_id": run_id,
        "executed_at": timestamp.astimezone(timezone.utc).isoformat(),
        "device": normalized_device,
        "test_count": len(normalized),
        "tests": normalized,
        "evidence_contract_only": True,
        "note": "Schema validation is not proof of execution authenticity; preserve signed CI/device logs and APK/IPA provenance.",
    }
    if platform == "ios":
        result["app_sha256_scope"] = "SHA-256 of the simulator ZIP archive supplied to the smoke runner, not the extracted .app bundle or an IPA."
    return result
