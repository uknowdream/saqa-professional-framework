"""Dependency-light API validation primitives for SAQA.

The client is intentionally transport-light so API checks can run in CI without
requiring a browser runtime. It performs bounded requests only; it does not
retry non-idempotent methods automatically.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    elapsed_ms: float
    error: str | None = None

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400 and self.error is None


def request(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: Any = None,
    timeout: float = 10.0,
) -> ApiResponse:
    """Execute one bounded HTTP request and return observable evidence.

    GET/HEAD/OPTIONS are the default-safe methods. Callers may explicitly use
    other methods for an authorized test target, but no automatic retry is
    performed for those methods.
    """
    if timeout <= 0 or timeout > 60:
        raise ValueError("timeout must be between 0 and 60 seconds")
    method = method.upper()
    payload: bytes | None = None
    request_headers = dict(headers or {})
    if body is not None:
        payload = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read()
            return ApiResponse(
                response.status,
                dict(response.headers.items()),
                content,
                (time.perf_counter() - started) * 1000,
            )
    except urllib.error.HTTPError as exc:
        content = exc.read()
        return ApiResponse(
            exc.code,
            dict(exc.headers.items()),
            content,
            (time.perf_counter() - started) * 1000,
            error=f"HTTP {exc.code}",
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return ApiResponse(
            0,
            {},
            b"",
            (time.perf_counter() - started) * 1000,
            error=f"transport error: {exc}",
        )


def assert_json_fields(response: ApiResponse, fields: tuple[str, ...]) -> None:
    """Raise AssertionError when the response is not JSON or misses fields."""
    if response.error:
        raise AssertionError(response.error)
    try:
        payload = response.json()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssertionError("response body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise AssertionError("expected a JSON object")
    missing = [field for field in fields if field not in payload]
    if missing:
        raise AssertionError(f"missing JSON fields: {', '.join(missing)}")
