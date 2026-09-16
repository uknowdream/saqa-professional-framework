"""Deterministic, read-only API smoke for the local OWASP Juice Shop target."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from saqa.api import ApiResponse, assert_json_contract, assert_json_list_cardinality

BASE_URL = os.getenv("SAQA_API_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
ENDPOINT = "/rest/products/search?q=apple"
OUTPUT = Path("artifacts/targets/juice-shop-api.json")
LATENCY_BUDGET_MS = int(os.getenv("SAQA_API_LATENCY_BUDGET_MS", "5000"))
LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS or parsed.username or parsed.password or parsed.port is None:
        raise ValueError("API target must be credential-free HTTP on an approved loopback host with a port")


def main() -> int:
    _assert_loopback_http(BASE_URL)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    observed_at = datetime.now(timezone.utc).isoformat()
    evidence = {"schema": "saqa.juice-shop-api.v6", "test_id": "juice-shop.api.products-search", "status": "FAIL", "target": BASE_URL, "http_methods": ["GET"], "destructive_actions": False, "observed_at": observed_at, "details": {}}
    response = None
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.get(f"{BASE_URL}{ENDPOINT}")
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200:
            raise AssertionError(f"expected HTTP 200, got {response.status_code}")
        if "application/json" not in content_type.lower():
            raise AssertionError(f"expected JSON response, got {content_type!r}")
        contract_response = ApiResponse(response.status_code, response.headers, response.content, elapsed_ms)
        assert_json_contract(contract_response, required_fields=("data",), field_types={"data": list})
        assert_json_list_cardinality(contract_response, field="data", minimum=1)
        if elapsed_ms > LATENCY_BUDGET_MS:
            raise AssertionError(f"response exceeded {LATENCY_BUDGET_MS} ms budget: {elapsed_ms} ms")
        payload = contract_response.json()
        evidence["status"] = "PASS"
        evidence["contract"] = {"required_fields": ["data"], "field_types": {"data": "list"}}
        evidence["data_expectations"] = {"field": "data", "minimum_items": 1, "kind": "seeded_fixture_expectation"}
        evidence["details"] = {"endpoint": ENDPOINT, "status_code": response.status_code, "content_type": content_type, "response_bytes": len(response.content), "response_sha256": contract_response.sha256, "data_items": len(payload["data"]), "elapsed_ms": elapsed_ms, "latency_budget_ms": LATENCY_BUDGET_MS}
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        evidence["details"] = {"endpoint": ENDPOINT, "status_code": response.status_code if response is not None else None, "response_bytes": len(response.content) if response is not None else 0, "response_sha256": ApiResponse(response.status_code, response.headers, response.content, elapsed_ms).sha256 if response is not None else None, "elapsed_ms": elapsed_ms, "latency_budget_ms": LATENCY_BUDGET_MS, "error": f"{type(exc).__name__}: {exc}"}

    OUTPUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
