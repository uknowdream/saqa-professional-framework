"""Deterministic retry/resilience primitives for safe test doubles."""
from __future__ import annotations
from collections.abc import Callable

def retry_read_only(operation:Callable[[],object], *, attempts:int=3)->tuple[object,int]:
    if attempts<1: raise ValueError("attempts must be >= 1")
    last=None
    for attempt in range(1,attempts+1):
        try: return operation(),attempt
        except (TimeoutError,ConnectionError) as exc:
            last=exc
    raise last  # type: ignore[misc]
