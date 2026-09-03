"""Read-only API contract smoke for the local OWASP Juice Shop target."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Keep this executable script runnable directly from a clean Docker checkout.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from saqa.api import request
from saqa.api_contract import validate_json_contract

BASE_URL = os.environ.get("SAQA_API_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
PATH = "/rest/products/search?q=apple"
ARTIFACT_DIR = Path(os.environ.get("SAQA_ARTIFACT_DIR", "artifacts/targets"))


def main() -> int:
    if not BASE_URL.startswith("http://127.0.0.1:"):
        raise SystemExit("API contract smoke is restricted to loopback HTTP targets")

    started = time.perf_counter()
    response = request(f"{BASE_URL}{PATH}", method="GET", timeout=10)
    elapsed_ms = (time.perf_counter() - started) * 1000

    if response.error:
        raise AssertionError(response.error)
    if response.status_code != 200:
        raise AssertionError(f"expected HTTP 200, got {response.status_code}")
    content_type = response.headers.get("Content-Type", "")
    if "json" not in content_type.lower():
        raise AssertionError(f"expected JSON content type, got {content_type!r}")

    payload = response.json()
    validate_json_contract(payload, required_object_fields=("data",), list_fields=("data",))

    result = {
        "schema": "saqa.api-contract.v1",
        "target": BASE_URL,
        "path": PATH,
        "method": "GET",
        "status_code": response.status_code,
        "content_type": content_type,
        "elapsed_ms": round(elapsed_ms, 3),
        "contract": {"required_fields": ["data"], "list_fields": ["data"]},
        "destructive_actions": False,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    output = ARTIFACT_DIR / "juice-shop-api-contract.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
