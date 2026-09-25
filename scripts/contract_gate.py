"""Read-only OpenAPI contract gate for authorized local targets."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from jsonschema import Draft4Validator

BASE_URL = os.getenv("SAQA_API_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
CONTRACT = Path(os.getenv("SAQA_CONTRACT_FILE", "contracts/juice-shop.openapi.json"))
OUTPUT = Path(os.getenv("SAQA_CONTRACT_OUTPUT", "artifacts/targets/juice-shop-contract.json"))
ENDPOINT = "/rest/products/search?q=apple"


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    return parsed._replace(netloc=f"{hostname}{port}", query="", fragment="").geturl()


def _assert_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
        or parsed.port is None
    ):
        raise ValueError("contract target must be credential-free HTTP on 127.0.0.1 with a port")


def _schema() -> tuple[dict, str]:
    contract_bytes = CONTRACT.read_bytes()
    document = json.loads(contract_bytes)
    schema = document["paths"]["/rest/products/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    return schema, hashlib.sha256(contract_bytes).hexdigest()


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    evidence = {
        "schema": "saqa.contract-gate.v2",
        "test_id": "juice-shop.api.openapi-contract",
        "status": "BLOCKED",
        "target": _redact_url(BASE_URL),
        "http_methods": ["GET"],
        "destructive_actions": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "details": {"contract": str(CONTRACT), "endpoint": ENDPOINT},
    }
    try:
        _assert_loopback_http(BASE_URL)
        schema, contract_sha256 = _schema()
        evidence["details"]["contract_sha256"] = contract_sha256
        Draft4Validator.check_schema(schema)
        with httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            response = client.get(f"{BASE_URL}{ENDPOINT}")
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        if response.status_code != 200:
            raise AssertionError(f"expected HTTP 200, got {response.status_code}")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise AssertionError("response content-type is not application/json")
        payload = response.json()
        errors = sorted(Draft4Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
        if errors:
            rendered = [{"path": list(error.path), "message": error.message} for error in errors[:20]]
            raise AssertionError(json.dumps(rendered, sort_keys=True))
        evidence["status"] = "PASS"
        evidence["details"].update(
            {
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "contract_sha256": contract_sha256,
                "response_sha256": hashlib.sha256(response.content).hexdigest(),
                "elapsed_ms": elapsed_ms,
                "validation_errors": [],
            }
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as exc:
        evidence["status"] = "BLOCKED"
        evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        evidence["status"] = "FAIL"
        evidence["details"]["error"] = f"{type(exc).__name__}: {exc}"
    OUTPUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
