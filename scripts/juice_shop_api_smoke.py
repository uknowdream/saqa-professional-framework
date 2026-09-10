"""Deterministic, read-only API smoke for the local OWASP Juice Shop target."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

BASE_URL = os.getenv("SAQA_API_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
ENDPOINT = "/rest/products/search?q=apple"
OUTPUT = Path("artifacts/targets/juice-shop-api.json")
LATENCY_BUDGET_MS = int(os.getenv("SAQA_API_LATENCY_BUDGET_MS", "5000"))


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("API target must be local HTTP loopback only")


def main() -> None:
    _assert_loopback_http(BASE_URL)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    observed_at = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        response = client.get(f"{BASE_URL}{ENDPOINT}")
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    if response.status_code != 200:
        raise AssertionError(f"expected HTTP 200, got {response.status_code}")
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        raise AssertionError(f"expected JSON response, got {content_type!r}")
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise AssertionError("expected JSON object with list-valued 'data'")
    if elapsed_ms > LATENCY_BUDGET_MS:
        raise AssertionError(f"response exceeded {LATENCY_BUDGET_MS} ms budget: {elapsed_ms} ms")

    evidence = {
        "schema": "saqa.juice-shop-api.v1",
        "test_id": "juice-shop.api.products-search",
        "status": "PASS",
        "target": BASE_URL,
        "http_methods": ["GET"],
        "destructive_actions": False,
        "observed_at": observed_at,
        "details": {
            "endpoint": ENDPOINT,
            "status_code": response.status_code,
            "content_type": content_type,
            "data_items": len(payload["data"]),
            "elapsed_ms": elapsed_ms,
            "latency_budget_ms": LATENCY_BUDGET_MS,
        },
    }
    OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
