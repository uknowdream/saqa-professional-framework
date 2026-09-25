"""Read-only API contract smoke for the local OWASP Juice Shop target."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from saqa.api import request
from saqa.api_contract import validate_json_contract

BASE_URL = os.environ.get("SAQA_API_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
PATH = "/rest/products/search?q=apple"
ARTIFACT_DIR = Path(os.environ.get("SAQA_ARTIFACT_DIR", "artifacts/targets"))


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        raise ValueError("API contract smoke target must be credential-free HTTP on 127.0.0.1")
    if parsed.port is None:
        raise ValueError("API contract smoke target must specify a loopback port")


def main() -> int:
    started = time.perf_counter()
    result = {
        "schema": "saqa.api-contract.v2", "test_id": "juice-shop.api-contract.search", "target": BASE_URL, "observed_at": datetime.now(timezone.utc).isoformat(), "path": PATH, "method": "GET",
        "status_code": 0, "content_type": "", "elapsed_ms": 0, "contract": {"required_fields": ["data"], "list_fields": ["data"]},
        "destructive_actions": False, "status": "BLOCKED", "details": {},
    }
    try:
        _assert_loopback_http(BASE_URL)
        response = request(f"{BASE_URL}{PATH}", method="GET", timeout=10, follow_redirects=False, use_environment_proxies=False)
        result["status_code"] = response.status_code
        result["content_type"] = response.headers.get("Content-Type", "")
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
        if response.error:
            raise AssertionError(response.error)
        if response.status_code != 200:
            raise AssertionError(f"expected HTTP 200, got {response.status_code}")
        media_type = result["content_type"].split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise AssertionError(f"expected application/json content type, got {result['content_type']!r}")
        payload = response.json()
        validate_json_contract(payload, required_object_fields=("data",), list_fields=("data",))
        for index, item in enumerate(payload["data"]):
            if not isinstance(item, dict):
                raise AssertionError(f"data[{index}] must be an object")
            if not isinstance(item.get("id"), int) or isinstance(item.get("id"), bool):
                raise AssertionError(f"data[{index}].id must be an integer")
            if not isinstance(item.get("name"), str):
                raise AssertionError(f"data[{index}].name must be a string")
        result["status"] = "PASS"
        result["details"] = {"response_sha256": response.sha256, "redirects_followed": False}
    except Exception as exc:
        result["status"] = "BLOCKED" if result["status_code"] == 0 else "FAIL"
        result["details"] = {"error": f"{type(exc).__name__}: {exc}", "response_sha256": getattr(response, "sha256", None), "redirects_followed": False}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    output = ARTIFACT_DIR / "juice-shop-api-contract.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
