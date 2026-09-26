"""Small, deterministic JSON API contract assertions for authorized targets."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def validate_json_contract(
    payload: Any,
    *,
    required_object_fields: tuple[str, ...] = (),
    list_fields: tuple[str, ...] = (),
) -> None:
    """Validate a JSON object contract without mutating the target."""
    if not isinstance(payload, Mapping):
        raise AssertionError("expected a JSON object")
    missing = [field for field in required_object_fields if field not in payload]
    if missing:
        raise AssertionError(f"missing JSON fields: {', '.join(missing)}")
    wrong_type = [field for field in list_fields if not isinstance(payload.get(field), list)]
    if wrong_type:
        raise AssertionError(f"expected list fields: {', '.join(wrong_type)}")
