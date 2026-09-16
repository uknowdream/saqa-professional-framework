"""Guarded smoke test for explicitly authorized real websites."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx


class TargetPolicyError(ValueError):
    """Raised when a real-web target violates the explicit authorization policy."""


def _allowed_hosts() -> set[str]:
    raw = os.getenv("SAQA_REAL_WEB_ALLOWLIST", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def validate_target(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise TargetPolicyError("Target must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise TargetPolicyError("Credentials in target URLs are forbidden")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host not in _allowed_hosts():
        raise TargetPolicyError(f"Host {host!r} is not in SAQA_REAL_WEB_ALLOWLIST; explicit authorization is required")
    if parsed.scheme != "https" and os.getenv("SAQA_ALLOW_HTTP_REAL_WEB") != "1":
        raise TargetPolicyError("Real-web targets require HTTPS")
    return parsed.geturl(), host


def _redirect_target(current: str, location: str) -> str:
    return urljoin(current, location)


def _bounded_body(response: httpx.Response, limit: int = 500_000) -> bytes:
    """Read at most ``limit`` bytes so a large authorized response cannot exhaust memory."""
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        remaining = limit - total
        if remaining <= 0:
            break
        piece = chunk[:remaining]
        chunks.append(piece)
        total += len(piece)
    return b"".join(chunks)


def run(target: str) -> dict[str, object]:
    current, host = validate_target(target)
    timeout = float(os.getenv("SAQA_REAL_WEB_TIMEOUT", "10"))
    max_redirects = int(os.getenv("SAQA_REAL_WEB_MAX_REDIRECTS", "3"))
    started = time.perf_counter()
    redirects: list[str] = []
    body = b""

    with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": "SAQA-Authorized-Web-Smoke/1.0"}) as client:
        for _ in range(max_redirects + 1):
            validated, host = validate_target(current)
            with client.stream("GET", validated) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise TargetPolicyError("Redirect response has no Location header")
                    current = _redirect_target(validated, location)
                    validate_target(current)
                    redirects.append(current)
                    continue
                status_code = response.status_code
                headers = response.headers
                body = _bounded_body(response)
                break
        else:
            raise TargetPolicyError("Maximum redirect count exceeded")

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    content_type = headers.get("content-type", "")
    lower = body.decode("utf-8", errors="replace").lower()
    title_present = "<title" in lower and "</title>" in lower
    security_headers = {name: headers.get(name) for name in ("content-security-policy", "strict-transport-security", "x-content-type-options", "referrer-policy") if headers.get(name)}
    status = "PASS" if 200 <= status_code < 400 else "FAIL"
    evidence = {
        "schema": "saqa.real-web-smoke.v2", "test_id": "real-web.authorized-read-only-smoke", "status": status,
        "target": validated, "host": host, "http_methods": ["GET"], "destructive_actions": False,
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "details": {"status_code": status_code, "content_type": content_type, "title_present": title_present, "response_time_ms": elapsed_ms, "response_bytes_sampled": len(body), "response_body_limit_bytes": 500_000, "redirects": redirects, "security_headers_present": sorted(security_headers)},
    }
    output = Path(os.getenv("SAQA_REAL_WEB_EVIDENCE", "artifacts/targets/real-web-smoke.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    if status != "PASS":
        raise AssertionError(f"Authorized real-web smoke returned HTTP {status_code}")
    return evidence


if __name__ == "__main__":
    target = os.getenv("SAQA_REAL_WEB_TARGET")
    if not target:
        raise SystemExit("SAQA_REAL_WEB_TARGET is required; no real website is selected by default")
    run(target)
