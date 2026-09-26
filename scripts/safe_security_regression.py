"""Safe application-security regression checks for authorized loopback targets."""
from __future__ import annotations
import os
from urllib.parse import urlparse
import httpx

BASE = os.getenv("SAQA_SECURITY_TARGET", "http://127.0.0.1:3000").rstrip("/")

def _validate_loopback_http(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None or parsed.username is not None or parsed.password is not None:
        raise SystemExit("target must be credential-free loopback HTTP")

def _validate_redirect(location: str) -> None:
    parsed = urlparse(location)
    if parsed.scheme and parsed.scheme != "http":
        raise SystemExit("redirect must remain HTTP")
    if parsed.scheme == "http" and parsed.hostname != "127.0.0.1":
        raise SystemExit("unexpected external redirect")

def main() -> int:
    _validate_loopback_http(BASE)
    with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
        response = client.get(BASE + "/")
    if response.status_code >= 400:
        raise SystemExit(f"target returned HTTP {response.status_code}")
    if 300 <= response.status_code < 400:
        _validate_redirect(response.headers.get("location", ""))
    print({"status": "PASS", "target": BASE, "method": "GET", "external_redirect": False})
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
