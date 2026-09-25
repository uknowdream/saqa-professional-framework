"""Deterministic, read-only performance gate for the local OWASP Juice Shop target."""
from __future__ import annotations

import json
import os
import statistics
import time
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

BASE_URL = os.getenv("SAQA_API_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
ENDPOINT = "/rest/products/search?q=apple"
OUTPUT = Path("artifacts/targets/juice-shop-performance.json")
REQUESTS = int(os.getenv("SAQA_PERF_REQUESTS", "5"))
P95_BUDGET_MS = float(os.getenv("SAQA_API_P95_BUDGET_MS", "5000"))


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.port is None
    ):
        raise ValueError("performance target must be credential-free local HTTP loopback with an explicit port")


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("cannot calculate percentile without observations")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    observed_at = datetime.now(timezone.utc).isoformat()
    latencies: list[float] = []
    status_codes: list[int] = []
    content_types: list[str] = []
    evidence = {
        "schema": "saqa.juice-shop-performance.v1",
        "test_id": "juice-shop.performance.products-search",
        "status": "BLOCKED",
        "target": BASE_URL,
        "http_methods": ["GET"],
        "destructive_actions": False,
        "observed_at": observed_at,
        "details": {
            "endpoint": ENDPOINT,
            "requests": REQUESTS,
            "status_codes": [],
            "content_types": [],
            "p95_budget_ms": P95_BUDGET_MS,
        },
    }

    try:
        _assert_loopback_http(BASE_URL)
        if REQUESTS < 3:
            raise ValueError("SAQA_PERF_REQUESTS must be at least 3")
        if not math.isfinite(P95_BUDGET_MS) or P95_BUDGET_MS < 0:
            raise ValueError("SAQA_API_P95_BUDGET_MS must be finite and non-negative")

        with httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            for _ in range(REQUESTS):
                started = time.perf_counter()
                response = client.get(f"{BASE_URL}{ENDPOINT}")
                latencies.append(round((time.perf_counter() - started) * 1000, 2))
                status_codes.append(response.status_code)
                content_types.append(response.headers.get("content-type", ""))
                if response.status_code != 200:
                    raise AssertionError(f"expected HTTP 200, got {response.status_code}")
                if "application/json" not in content_types[-1].lower():
                    raise AssertionError(f"expected JSON response, got {content_types[-1]!r}")

        p95_ms = round(_percentile(latencies, 0.95), 2)
        evidence["status"] = "PASS" if p95_ms <= P95_BUDGET_MS else "FAIL"
        evidence["details"].update({
            "status_codes": status_codes,
            "content_types": sorted(set(content_types)),
            "min_ms": min(latencies),
            "median_ms": round(statistics.median(latencies), 2),
            "p95_ms": p95_ms,
            "max_ms": max(latencies),
            "p95_budget_ms": P95_BUDGET_MS,
        })
        if evidence["status"] != "PASS":
            raise AssertionError(f"p95 latency exceeded budget: {p95_ms} ms > {P95_BUDGET_MS} ms")
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as exc:
        evidence["status"] = "BLOCKED"
        evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        evidence["status"] = "FAIL"
        evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(evidence, indent=2))
    if evidence["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
