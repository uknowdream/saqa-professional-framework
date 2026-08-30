"""Safe, deterministic HTTP client primitives for SAQA API testing."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ApiResponse:
    status_code: int | None
    headers: dict[str, str]
    body: bytes
    elapsed_ms: float
    error: str | None = None

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> object:
        return json.loads(self.body.decode("utf-8"))


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 10.0,
) -> ApiResponse:
    """Execute one HTTP request without automatic mutation retries."""
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    request_obj = Request(url, data=body, headers=headers or {}, method=method.upper())
    started = time.perf_counter()
    try:
        with urlopen(request_obj, timeout=timeout) as response:
            payload = response.read()
            return ApiResponse(
                response.status,
                dict(response.headers.items()),
                payload,
                (time.perf_counter() - started) * 1000,
            )
    except HTTPError as exc:
        payload = exc.read()
        return ApiResponse(
            exc.code,
            dict(exc.headers.items()),
            payload,
            (time.perf_counter() - started) * 1000,
            error=str(exc),
        )
    except (URLError, TimeoutError, OSError) as exc:
        return ApiResponse(
            None,
            {},
            b"",
            (time.perf_counter() - started) * 1000,
            error=str(exc),
        )


def assert_json_fields(response: ApiResponse, fields: tuple[str, ...]) -> dict:
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError("expected a JSON object")
    missing = [field for field in fields if field not in payload]
    if missing:
        raise AssertionError(f"missing JSON fields: {missing}")
    return payload
