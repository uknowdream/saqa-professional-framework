"""Deterministic retry/resilience primitives for safe test doubles."""
from __future__ import annotations
from collections.abc import Callable
import httpx

def retry_read_only(operation: Callable[[], object], *, attempts: int = 3) -> tuple[object, int]:
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation(), attempt
        except (TimeoutError, ConnectionError, httpx.TransportError) as exc:
            last = exc
    assert last is not None
    raise last
