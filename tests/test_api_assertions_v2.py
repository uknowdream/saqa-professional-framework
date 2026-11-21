"""Tests for precision API assertions and suite flakiness analytics."""
from __future__ import annotations

import json

import pytest

from saqa.api import (
    ApiResponse,
    assert_header,
    assert_json_path,
    assert_response_time,
    assert_status,
    resolve_json_path,
)
from saqa.flaky import analyze_history, analyze_suite_flakiness


def _resp(payload: object, *, status: int = 200, elapsed_ms: float = 25.0, headers: dict[str, str] | None = None):
    raw = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
    return ApiResponse(status_code=status, headers=headers or {"Content-Type": "application/json"}, body=raw, elapsed_ms=elapsed_ms)


def test_api_response_helpers_and_json_path_assertions():
    resp = _resp({"status": "ok", "items": [{"id": 7, "code": "QA-007", "tags": ["a", "b"]}]})
    assert resp.header("content-type") == "application/json"
    assert resp.header("x-missing", "fallback") == "fallback"
    assert '"status": "ok"' in resp.text

    assert_status(resp, 200)
    assert_status(resp, [200, 201])
    assert_response_time(resp, max_ms=50.0)
    assert_header(resp, "CONTENT-TYPE", equals="application/json", contains="json", regex=r"application/\w+")
    assert resolve_json_path(resp.json(), "$.items[0].id") == 7
    assert_json_path(resp, "items[0].id", equals=7, expected_type=int, min_value=1, max_value=10)
    assert_json_path(resp, "items[0].code", regex=r"^QA-\d{3}$", min_length=6, max_length=6)
    assert_json_path(resp, "items[0].tags", expected_type=list, min_length=2, max_length=5)

    with pytest.raises(AssertionError):
        assert_status(resp, 404)
    with pytest.raises(AssertionError):
        assert_response_time(resp, max_ms=10.0)
    with pytest.raises(AssertionError):
        assert_header(resp, "X-Not-There")
    with pytest.raises(AssertionError):
        assert_json_path(resp, "items[5].id")
    with pytest.raises(AssertionError):
        assert_json_path(resp, "items[0].id", min_value=100)


def test_flaky_metrics_and_suite_ranking():
    analysis = analyze_history(["PASS", "FAIL", "PASS", "FAIL"])
    assert analysis.is_flaky is True
    assert analysis.pass_rate == 0.5
    assert analysis.fail_rate == 0.5
    assert analysis.flakiness_score == 1.0
    assert analysis.quarantine_recommended is True

    suite = analyze_suite_flakiness(
        {
            "stable": ["PASS", "PASS", "PASS"],
            "mild-flaky": ["PASS", "PASS", "PASS", "FAIL"],
            "severe-flaky": ["PASS", "FAIL", "PASS", "FAIL"],
        }
    )
    assert suite["total_tests"] == 3
    assert [t["test_id"] for t in suite["flaky_tests"]] == ["severe-flaky", "mild-flaky"]
    assert "severe-flaky" in suite["quarantine_candidates"]
