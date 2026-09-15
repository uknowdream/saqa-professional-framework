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
    payload = _json_object(response)
    missing = [field for field in fields if field not in payload]
    if missing:
        raise AssertionError(f"missing JSON fields: {', '.join(missing)}")


def assert_json_contract(
    response: ApiResponse,
    *,
    required_fields: tuple[str, ...] = (),
    field_types: Mapping[str, type | tuple[type, ...]] | None = None,
    list_item_types: Mapping[str, type | tuple[type, ...]] | None = None,
    list_min_items: Mapping[str, int] | None = None,
    list_max_items: Mapping[str, int] | None = None,
) -> None:
    """Validate a deterministic structural JSON object contract.

    Required fields, strict JSON-compatible field types, list item types, and
    optional cardinality checks cover stable response contracts while remaining
    dependency-light. ``bool`` is treated distinctly from ``int``.

    Use :func:`assert_json_list_cardinality` when a cardinality rule represents
    a target-data/fixture expectation rather than a universal structural rule.
    """
    payload = _json_object(response)
    required = tuple(required_fields)
    missing = [field for field in required if field not in payload]
    if missing:
        raise AssertionError(f"missing JSON fields: {', '.join(missing)}")

    for field, expected in (field_types or {}).items():
        if field not in payload:
            raise AssertionError(f"missing JSON field for type check: {field}")
        if not _json_type_matches(payload[field], expected):
            raise AssertionError(
                f"JSON field {field!r} has type {type(payload[field]).__name__}, "
                f"expected {_type_names(expected)}"
            )

    for field, expected in (list_item_types or {}).items():
        if field not in payload:
            raise AssertionError(f"missing JSON list field: {field}")
        value = payload[field]
        if not isinstance(value, list):
            raise AssertionError(f"JSON field {field!r} must be a list")
        invalid_index = next(
            (index for index, item in enumerate(value) if not _json_type_matches(item, expected)),
            None,
        )
        if invalid_index is not None:
            item = value[invalid_index]
            raise AssertionError(
                f"JSON list field {field!r} item {invalid_index} has type "
                f"{type(item).__name__}, expected {_type_names(expected)}"
            )

    for field, minimum in (list_min_items or {}).items():
        if minimum < 0:
            raise ValueError(f"minimum list size for {field!r} cannot be negative")
        value = _require_list(payload, field)
        if len(value) < minimum:
            raise AssertionError(
                f"JSON list field {field!r} has {len(value)} item(s), expected at least {minimum}"
            )

    for field, maximum in (list_max_items or {}).items():
        if maximum < 0:
            raise ValueError(f"maximum list size for {field!r} cannot be negative")
        value = _require_list(payload, field)
        if len(value) > maximum:
            raise AssertionError(
                f"JSON list field {field!r} has {len(value)} item(s), expected at most {maximum}"
            )


def assert_json_list_cardinality(
    response: ApiResponse,
    *,
    field: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> None:
    """Validate list cardinality as an explicit data/fixture expectation.

    This keeps seeded-data assumptions separate from universal structural API
    contract rules while reusing the same deterministic JSON parsing path.
    """
    if minimum is not None and minimum < 0:
        raise ValueError(f"minimum list size for {field!r} cannot be negative")
    if maximum is not None and maximum < 0:
        raise ValueError(f"maximum list size for {field!r} cannot be negative")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"minimum list size for {field!r} cannot exceed maximum")
    payload = _json_object(response)
    value = _require_list(payload, field)
    if minimum is not None and len(value) < minimum:
        raise AssertionError(
            f"JSON list field {field!r} has {len(value)} item(s), expected at least {minimum}"
        )
    if maximum is not None and len(value) > maximum:
        raise AssertionError(
            f"JSON list field {field!r} has {len(value)} item(s), expected at most {maximum}"
        )


def _json_object(response: ApiResponse) -> dict[str, Any]:
    if response.error:
        raise AssertionError(response.error)
    try:
        payload = response.json()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssertionError("response body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise AssertionError("expected a JSON object")
    return payload


def _require_list(payload: dict[str, Any], field: str) -> list[Any]:
    if field not in payload:
        raise AssertionError(f"missing JSON list field: {field}")
    value = payload[field]
    if not isinstance(value, list):
        raise AssertionError(f"JSON field {field!r} must be a list")
    return value


def _json_type_matches(value: Any, expected: type | tuple[type, ...]) -> bool:
    expected_types = expected if isinstance(expected, tuple) else (expected,)
    for expected_type in expected_types:
        if expected_type is int and isinstance(value, bool):
            continue
        if isinstance(value, expected_type):
            return True
    return False


def _type_names(expected: type | tuple[type, ...]) -> str:
    expected_types = expected if isinstance(expected, tuple) else (expected,)
    return " or ".join(item.__name__ for item in expected_types)
