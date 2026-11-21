"""Tests for declarative QA suite runner (saqa.runner)."""
from __future__ import annotations

import json

import pytest

from saqa.api import ApiResponse
from saqa.evidence import verify_manifest
from saqa.runner import create_starter_suite, load_suite_file, run_suite


def _fake_response(
    status: int = 200,
    body: object = None,
    *,
    headers: dict[str, str] | None = None,
    elapsed_ms: float = 18.5,
    error: str | None = None,
) -> ApiResponse:
    if isinstance(body, (dict, list)):
        raw = json.dumps(body).encode("utf-8")
    elif isinstance(body, str):
        raw = body.encode("utf-8")
    elif isinstance(body, bytes):
        raw = body
    else:
        raw = b""
    return ApiResponse(
        status_code=status,
        headers=headers or {"Content-Type": "application/json; charset=utf-8"},
        body=raw,
        elapsed_ms=elapsed_ms,
        error=error,
    )


def test_run_suite_passes_all_assertions_and_writes_verified_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("SAQA_DEMO_TOKEN", "safe-header-marker")
    suite = {
        "name": "demo-api-suite",
        "base_url": "http://127.0.0.1:3000",
        "variables": {"term": "apple"},
        "default_headers": {"X-Trace": "{{env:SAQA_DEMO_TOKEN}}"},
        "cases": [
            {
                "id": "search-ok",
                "path": "/rest/products/search",
                "query": {"q": "{{term}}"},
                "expect": {
                    "status": 200,
                    "max_ms": 200,
                    "headers": {"content-type": {"contains": "application/json"}},
                    "json_required_fields": ["status", "data"],
                    "json_paths": [
                        {"path": "status", "equals": "success", "type": "string"},
                        {"path": "data[0].price", "type": "number", "min": 1, "max": 100},
                        {"path": "data[0].name", "regex": "^Apple"},
                    ],
                    "body_contains": ["Apple Juice"],
                    "body_not_contains": ["Traceback"],
                    "schema_snapshot_keys": ["status", "data"],
                },
            }
        ],
    }

    seen_calls: list[tuple[str, dict[str, str]]] = []

    def fake_requester(url, *, method, headers, timeout, follow_redirects, use_environment_proxies):
        seen_calls.append((url, dict(headers)))
        return _fake_response(
            200,
            {"status": "success", "data": [{"name": "Apple Juice", "price": 12.5}]},
        )

    out_dir = tmp_path / "suite-out"
    result = run_suite(suite, output_dir=out_dir, requester=fake_requester)
    assert result.passed is True
    assert result.manifest_path is not None and verify_manifest(result.manifest_path)
    assert result.summary_path is not None and result.summary_path.is_file()
    assert seen_calls[0][0] == "http://127.0.0.1:3000/rest/products/search?q=apple"
    assert seen_calls[0][1]["X-Trace"] == "safe-header-marker"


def test_run_suite_records_failures_transport_retries_and_blocked_state(tmp_path):
    attempts_seen = {"flaky-net": 0}

    def fake_requester(url, **kwargs):
        if "flaky-net" in url:
            attempts_seen["flaky-net"] += 1
            if attempts_seen["flaky-net"] == 1:
                return _fake_response(0, b"", error="transport error: reset")
            return _fake_response(200, {"ok": True})
        if "down" in url:
            return _fake_response(0, b"", error="transport error: refused")
        return _fake_response(200, {"status": "bad", "extra": 1}, elapsed_ms=999.0)

    suite = {
        "name": "resilience-suite",
        "base_url": "http://127.0.0.1:3000",
        "max_retries": 1,
        "cases": [
            {"id": "recovers", "path": "/flaky-net", "expect": {"status": 200}},
            {"id": "blocked-down", "path": "/down", "expect": {"status": 200}},
            {
                "id": "fails-sla-and-drift",
                "path": "/slow",
                "expect": {
                    "status": 200,
                    "max_ms": 100,
                    "schema_snapshot_keys": ["status"],
                },
            },
        ],
    }

    result = run_suite(suite, output_dir=tmp_path / "out", requester=fake_requester)
    assert result.passed is False
    by_id = {r.test_id: r for r in result.records}
    assert by_id["recovers"].status == "PASS"
    assert by_id["recovers"].details["attempts"] == 2
    assert by_id["blocked-down"].status == "BLOCKED"
    assert by_id["fails-sla-and-drift"].status == "FAIL"
    assert len(by_id["fails-sla-and-drift"].details["failure_reasons"]) == 2


def test_run_suite_enforces_safety_guards_and_starter_template(tmp_path):
    starter = create_starter_suite()
    suite_file = tmp_path / "starter.json"
    suite_file.write_text(json.dumps(starter), encoding="utf-8")
    loaded = load_suite_file(suite_file)
    assert loaded["name"] == "saqa-api-smoke"

    # Remote host blocked by default
    remote_suite = {
        "name": "remote-blocked",
        "base_url": "https://example.com",
        "cases": [{"id": "c1", "path": "/"}],
    }
    with pytest.raises(ValueError, match="remote host"):
        run_suite(remote_suite)

    # Non-read-only method rejected
    mutating_suite = {
        "name": "mutating-blocked",
        "base_url": "http://127.0.0.1:3000",
        "cases": [{"id": "c1", "path": "/", "method": "POST"}],
    }
    with pytest.raises(ValueError, match="read-only methods"):
        run_suite(mutating_suite)
