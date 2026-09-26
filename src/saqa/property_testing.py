"""Deterministic property-style API contract generators without external services."""
from __future__ import annotations
import random
from collections.abc import Callable
from urllib.parse import urlparse

def deterministic_cases(seed: int = 20260927, count: int = 32) -> list[dict]:
    rng = random.Random(seed)
    cases = []
    for _ in range(count):
        q = rng.choice(["apple", "", "A" * rng.randint(1, 64), "0", "special-!@#$"])
        cases.append({"q": q})
    return cases

def assert_read_only_request(method: str, url: str) -> None:
    if method.upper() != "GET":
        raise AssertionError("property suite permits GET only")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise AssertionError("property suite permits credential-free loopback HTTP targets only")
    if parsed.username is not None or parsed.password is not None:
        raise AssertionError("property suite rejects credential-bearing targets")

def exercise_contract_cases(cases: list[dict], executor: Callable[[dict], tuple[int, str]]) -> dict:
    outcomes = []
    for case in cases:
        status, content_type = executor(case)
        if status != 200 or content_type.lower().split(";", 1)[0].strip() != "application/json":
            raise AssertionError(f"contract case failed: {case!r} -> {status}/{content_type}")
        outcomes.append({"case": case, "status": status, "content_type": content_type})
    return {"count": len(outcomes), "passed": len(outcomes)}
