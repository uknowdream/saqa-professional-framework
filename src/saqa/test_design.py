"""Black-box QA test design generators and deterministic synthetic test data.

Implements classic QA engineering techniques referenced in SAQA:
- Boundary Value Analysis (BVA) for numeric and string domains
- Equivalence Partitioning (EP)
- Pairwise (All-Pairs / 2-way combinatorial) test matrix generation with coverage proof
- Decision Table evaluation and case generation
- State Transition graph coverage (valid paths + invalid negative probes)
- Safe Error-Guessing edge-case payloads
- Deterministic seeded Synthetic QA Data Factory
"""
from __future__ import annotations

import itertools
import random
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class DesignedCase:
    """One labeled test-design case with expected validity semantics."""

    case_id: str
    technique: str
    label: str
    value: Any
    valid: bool
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "technique": self.technique,
            "label": self.label,
            "value": self.value,
            "valid": self.valid,
            "rationale": self.rationale,
        }


def boundary_value_numeric(
    minimum: int | float,
    maximum: int | float,
    *,
    step: int | float = 1,
    field_name: str = "value",
) -> list[DesignedCase]:
    """Generate 7-point Boundary Value Analysis cases around [minimum, maximum]."""
    if isinstance(minimum, bool) or isinstance(maximum, bool) or isinstance(step, bool):
        raise ValueError("numeric BVA bounds and step must not be booleans")
    if minimum > maximum:
        raise ValueError("minimum must not exceed maximum")
    if step <= 0:
        raise ValueError("step must be positive")

    is_int = isinstance(minimum, int) and isinstance(maximum, int) and isinstance(step, int)
    nominal: int | float = (minimum + maximum) // 2 if is_int else round((minimum + maximum) / 2.0, 6)

    candidates: list[tuple[str, int | float, bool, str]] = [
        ("below_min", minimum - step, False, f"{field_name} just below minimum bound"),
        ("at_min", minimum, True, f"{field_name} at lower inclusive bound"),
        ("above_min", minimum + step, (minimum + step) <= maximum, f"{field_name} just above lower bound"),
        ("nominal", nominal, True, f"{field_name} nominal interior value"),
        ("below_max", maximum - step, (maximum - step) >= minimum, f"{field_name} just below upper bound"),
        ("at_max", maximum, True, f"{field_name} at upper inclusive bound"),
        ("above_max", maximum + step, False, f"{field_name} just above maximum bound"),
    ]

    seen: set[tuple[Any, bool]] = set()
    cases: list[DesignedCase] = []
    for idx, (label, val, valid, rationale) in enumerate(candidates, start=1):
        val_clean = val if is_int else round(float(val), 6)
        dedupe_key = (val_clean, valid)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cases.append(
            DesignedCase(
                case_id=f"bva-num-{idx:02d}-{label}",
                technique="BVA",
                label=label,
                value=val_clean,
                valid=valid,
                rationale=rationale,
            )
        )
    return cases


def boundary_value_string(
    min_length: int,
    max_length: int,
    *,
    char: str = "a",
    field_name: str = "text",
) -> list[DesignedCase]:
    """Generate string-length Boundary Value Analysis cases including whitespace & Unicode."""
    if min_length < 0 or max_length < 0 or min_length > max_length:
        raise ValueError("string BVA requires 0 <= min_length <= max_length")
    if len(char) != 1:
        raise ValueError("char must be a single character")

    nominal_len = (min_length + max_length) // 2
    cases: list[DesignedCase] = []

    def _add(label: str, val: str, valid: bool, rationale: str) -> None:
        cases.append(
            DesignedCase(
                case_id=f"bva-str-{len(cases) + 1:02d}-{label}",
                technique="BVA",
                label=label,
                value=val,
                valid=valid,
                rationale=rationale,
            )
        )

    if min_length > 0:
        _add("empty", "", False, f"{field_name} empty string below min_length={min_length}")
        if min_length > 1:
            _add("below_min", char * (min_length - 1), False, f"{field_name} length {min_length - 1} < {min_length}")
    _add("at_min", char * min_length, True, f"{field_name} exact minimum length {min_length}")
    if nominal_len > min_length and nominal_len < max_length:
        _add("nominal", char * nominal_len, True, f"{field_name} nominal length {nominal_len}")
    if max_length != min_length:
        _add("at_max", char * max_length, True, f"{field_name} exact maximum length {max_length}")
    _add("above_max", char * (max_length + 1), False, f"{field_name} length {max_length + 1} > {max_length}")
    if max_length >= max(1, min_length):
        ws_len = max(1, min_length)
        _add("whitespace_only", " " * ws_len, False, f"{field_name} blank/whitespace-only probe")
        uni_char = "é"
        _add(
            "unicode_multibyte",
            uni_char * max(1, min(max_length, max(min_length, 3))),
            True,
            f"{field_name} multi-byte UTF-8 length accuracy probe",
        )
    return cases


def equivalence_partitions(
    valid_partitions: Mapping[str, Sequence[Any]],
    invalid_partitions: Mapping[str, Sequence[Any]] | None = None,
) -> list[DesignedCase]:
    """Build deterministic representative cases for valid and invalid equivalence classes."""
    cases: list[DesignedCase] = []
    for name, values in valid_partitions.items():
        if not values:
            raise ValueError(f"valid partition {name!r} must not be empty")
        cases.append(
            DesignedCase(
                case_id=f"ep-valid-{len(cases) + 1:02d}-{name}",
                technique="EP",
                label=name,
                value=values[0],
                valid=True,
                rationale=f"Representative value from valid equivalence class {name!r}",
            )
        )
    for name, values in (invalid_partitions or {}).items():
        if not values:
            raise ValueError(f"invalid partition {name!r} must not be empty")
        cases.append(
            DesignedCase(
                case_id=f"ep-invalid-{len(cases) + 1:02d}-{name}",
                technique="EP",
                label=name,
                value=values[0],
                valid=False,
                rationale=f"Representative value from invalid equivalence class {name!r}",
            )
        )
    return cases


def pairwise_matrix(
    parameters: Mapping[str, Sequence[Any]],
    *,
    seed: int = 20260927,
) -> list[dict[str, Any]]:
    """Generate a compact deterministic 2-way (all-pairs) combinatorial test matrix.

    Guarantees 100% coverage of every value pair across any two parameters while
    dramatically reducing combinatorial explosion compared to full Cartesian product.
    """
    if not parameters:
        raise ValueError("parameters mapping must not be empty")
    keys = list(parameters.keys())
    domains: dict[str, list[Any]] = {}
    for key in keys:
        values = list(dict.fromkeys(parameters[key]))
        if not values:
            raise ValueError(f"parameter {key!r} must have at least one value")
        domains[key] = values

    if len(keys) == 1:
        only = keys[0]
        return [{only: val} for val in domains[only]]

    # Sort parameters by descending domain size for tighter pairwise packing.
    ordered_keys = sorted(keys, key=lambda k: (-len(domains[k]), k))
    rng = random.Random(seed)

    # Start with exact Cartesian product of the two largest domains.
    first, second = ordered_keys[0], ordered_keys[1]
    rows: list[dict[str, Any]] = [
        {first: v1, second: v2}
        for v1 in domains[first]
        for v2 in domains[second]
    ]

    # IPO (In-Parameter-Order) horizontal + vertical growth for remaining parameters.
    for param_idx in range(2, len(ordered_keys)):
        param = ordered_keys[param_idx]
        prev_keys = ordered_keys[:param_idx]
        uncovered: set[tuple[str, Any, Any]] = {
            (prev_key, prev_val, new_val)
            for prev_key in prev_keys
            for prev_val in domains[prev_key]
            for new_val in domains[param]
        }

        # Horizontal extension: pick the value for `param` covering the most uncovered pairs per row.
        for row in rows:
            best_val = domains[param][0]
            best_gain = -1
            for candidate in domains[param]:
                gain = sum(1 for pk in prev_keys if (pk, row[pk], candidate) in uncovered)
                if gain > best_gain:
                    best_gain = gain
                    best_val = candidate
            row[param] = best_val
            for pk in prev_keys:
                uncovered.discard((pk, row[pk], best_val))

        # Vertical extension: add minimal new rows for any remaining uncovered pairs.
        while uncovered:
            # Pick deterministic next pair (sorted for reproducibility).
            pk, pv, nv = sorted(uncovered, key=lambda item: (item[0], str(item[1]), str(item[2])))[0]
            new_row: dict[str, Any] = {pk: pv, param: nv}
            for other_pk in prev_keys:
                if other_pk in new_row:
                    continue
                best_other = domains[other_pk][0]
                best_gain = -1
                for cand_other in domains[other_pk]:
                    gain = 1 if (other_pk, cand_other, nv) in uncovered else 0
                    if gain > best_gain:
                        best_gain = gain
                        best_other = cand_other
                if best_gain == 0:
                    best_other = rng.choice(domains[other_pk])
                new_row[other_pk] = best_other
            rows.append(new_row)
            for prev_key in prev_keys:
                uncovered.discard((prev_key, new_row[prev_key], nv))

    # Restore original caller key order in each row.
    return [{key: row[key] for key in keys} for row in rows]


def verify_pairwise_coverage(
    parameters: Mapping[str, Sequence[Any]],
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify exact 2-way pair coverage percentage of a combinatorial test suite."""
    keys = list(parameters.keys())
    if len(keys) < 2:
        total = sum(len(set(v)) for v in parameters.values())
        return {
            "total_pairs": total,
            "covered_pairs": total,
            "missing_pairs": 0,
            "coverage_pct": 100.0,
            "full_cartesian_size": total,
            "actual_case_count": len(cases),
        }

    expected_pairs: set[tuple[str, Any, str, Any]] = set()
    for k1, k2 in itertools.combinations(keys, 2):
        for v1 in dict.fromkeys(parameters[k1]):
            for v2 in dict.fromkeys(parameters[k2]):
                expected_pairs.add((k1, v1, k2, v2))

    observed_pairs: set[tuple[str, Any, str, Any]] = set()
    for case in cases:
        for k1, k2 in itertools.combinations(keys, 2):
            if k1 in case and k2 in case:
                observed_pairs.add((k1, case[k1], k2, case[k2]))

    covered = len(expected_pairs & observed_pairs)
    total = len(expected_pairs)
    cartesian = 1
    for vals in parameters.values():
        cartesian *= len(set(vals))
    pct = round((covered / total) * 100.0, 2) if total else 100.0
    return {
        "total_pairs": total,
        "covered_pairs": covered,
        "missing_pairs": total - covered,
        "coverage_pct": pct,
        "full_cartesian_size": cartesian,
        "actual_case_count": len(cases),
        "reduction_pct": round((1.0 - (len(cases) / cartesian)) * 100.0, 2) if cartesian else 0.0,
    }


@dataclass(frozen=True)
class DecisionRule:
    """Single rule row in a QA Decision Table."""

    rule_id: str
    conditions: Mapping[str, Any]
    expected_actions: Mapping[str, Any]


def evaluate_decision_table(
    rules: Sequence[DecisionRule],
    inputs: Mapping[str, Any],
) -> list[DecisionRule]:
    """Return all decision rules matching the given condition inputs (supports '*' wildcard)."""
    matched: list[DecisionRule] = []
    for rule in rules:
        if all(
            expected == "*" or (cond in inputs and inputs[cond] == expected)
            for cond, expected in rule.conditions.items()
        ):
            matched.append(rule)
    return matched


def generate_decision_table_cases(rules: Sequence[DecisionRule]) -> list[dict[str, Any]]:
    """Convert decision table rules into executable test cases and flag exact duplicates."""
    if not rules:
        raise ValueError("decision table requires at least one rule")
    seen_signatures: set[tuple[tuple[str, Any], ...]] = set()
    cases: list[dict[str, Any]] = []
    for rule in rules:
        sig = tuple(sorted(rule.conditions.items()))
        if sig in seen_signatures:
            raise ValueError(f"duplicate decision table condition signature in rule {rule.rule_id!r}")
        seen_signatures.add(sig)
        cases.append(
            {
                "rule_id": rule.rule_id,
                "inputs": dict(rule.conditions),
                "expected_actions": dict(rule.expected_actions),
            }
        )
    return cases


def state_transition_paths(
    initial_state: str,
    transitions: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Generate complete valid transition coverage and invalid negative transition probes via BFS."""
    if initial_state not in transitions:
        raise ValueError(f"initial_state {initial_state!r} must exist in transitions map")

    all_events = sorted({event for mapping in transitions.values() for event in mapping})
    visited_states: set[str] = {initial_state}
    queue: deque[tuple[str, list[tuple[str, str, str]]]] = deque([(initial_state, [])])
    paths_to_state: dict[str, list[tuple[str, str, str]]] = {initial_state: []}

    while queue:
        state, path = queue.popleft()
        for event, target in transitions.get(state, {}).items():
            if target not in visited_states:
                visited_states.add(target)
                next_path = [*path, (state, event, target)]
                paths_to_state[target] = next_path
                queue.append((target, next_path))

    valid_cases: list[dict[str, Any]] = []
    invalid_cases: list[dict[str, Any]] = []

    for state in sorted(visited_states):
        setup_path = paths_to_state[state]
        allowed_events = transitions.get(state, {})
        for event, target in sorted(allowed_events.items()):
            valid_cases.append(
                {
                    "case_id": f"st-valid-{len(valid_cases) + 1:02d}-{state}-{event}",
                    "from_state": state,
                    "event": event,
                    "expected_state": target,
                    "setup_steps": [{"from": f, "event": e, "to": t} for f, e, t in setup_path],
                    "valid": True,
                }
            )
        for event in all_events:
            if event not in allowed_events:
                invalid_cases.append(
                    {
                        "case_id": f"st-invalid-{len(invalid_cases) + 1:02d}-{state}-{event}",
                        "from_state": state,
                        "event": event,
                        "expected_state": state,
                        "setup_steps": [{"from": f, "event": e, "to": t} for f, e, t in setup_path],
                        "valid": False,
                    }
                )

    return {
        "initial_state": initial_state,
        "reachable_states": sorted(visited_states),
        "valid_transitions": valid_cases,
        "invalid_transition_probes": invalid_cases,
    }


def error_guessing_payloads(category: str = "all") -> dict[str, list[dict[str, Any]]]:
    """Curated, non-destructive QA error-guessing edge-case payloads."""
    catalog: dict[str, list[dict[str, Any]]] = {
        "strings": [
            {"label": "empty_string", "value": ""},
            {"label": "whitespace_only", "value": "   \t\n  "},
            {"label": "leading_trailing_spaces", "value": "  qa-user  "},
            {"label": "unicode_accents", "value": "Crème Brûlée — 日本語"},
            {"label": "emoji_zwj", "value": "QA 🚀👨‍👩‍👧‍👦"},
            {"label": "rtl_text", "value": "اختبار الجودة"},
            {"label": "long_string_512", "value": "A" * 512},
            {"label": "json_special_chars", "value": 'quote"backslash\\newline\n'},
        ],
        "numbers": [
            {"label": "zero", "value": 0},
            {"label": "negative_one", "value": -1},
            {"label": "small_decimal", "value": 0.0001},
            {"label": "float_precision", "value": 0.1 + 0.2},
            {"label": "int32_max", "value": 2147483647},
            {"label": "int32_overflow", "value": 2147483648},
            {"label": "negative_large", "value": -999999999},
        ],
        "dates": [
            {"label": "leap_day_valid", "value": "2024-02-29"},
            {"label": "leap_day_invalid", "value": "2025-02-29"},
            {"label": "year_end_utc", "value": "2026-12-31T23:59:59Z"},
            {"label": "timezone_offset_wib", "value": "2026-11-22T07:00:00+07:00"},
            {"label": "epoch_start", "value": "1970-01-01T00:00:00Z"},
            {"label": "malformed_date", "value": "2026-13-45"},
        ],
        "security_probes": [
            {"label": "html_angle_brackets", "value": "<b>qa-probe</b>"},
            {"label": "sqli_quote_probe", "value": "' OR '1'='1"},
            {"label": "path_traversal_probe", "value": "../../etc/hosts"},
            {"label": "template_brace_probe", "value": "{{7*7}}"},
            {"label": "null_byte_escaped", "value": "qa\\x00probe"},
        ],
        "json_types": [
            {"label": "null_value", "value": None},
            {"label": "empty_list", "value": []},
            {"label": "empty_object", "value": {}},
            {"label": "boolean_true", "value": True},
            {"label": "numeric_string", "value": "12345"},
        ],
    }
    if category == "all":
        return catalog
    if category not in catalog:
        allowed = ", ".join(sorted(catalog))
        raise ValueError(f"unsupported error-guessing category {category!r}; choose from: all, {allowed}")
    return {category: catalog[category]}


_FIRST_NAMES = (
    "Aditya", "Budi", "Citra", "Dewi", "Eka", "Fajar", "Gita", "Hendra",
    "Indah", "Joko", "Kartika", "Lestari", "Maya", "Nugroho", "Putri", "Rizky",
    "Sari", "Taufik", "Utami", "Wulan",
)
_LAST_NAMES = (
    "Pratama", "Saputra", "Wijaya", "Santoso", "Kusuma", "Hidayat", "Nugraha",
    "Setiawan", "Permata", "Ramadhan", "Siregar", "Laksana", "Mahendra", "Yusuf",
)
_CITIES = ("Jakarta", "Bandung", "Surabaya", "Yogyakarta", "Medan", "Semarang", "Denpasar", "Makassar")
_ROLES = ("qa_engineer", "viewer", "editor", "auditor")


class SyntheticDataFactory:
    """Deterministic, zero-dependency synthetic test data generator for QA workflows."""

    def __init__(self, *, seed: int = 20260927) -> None:
        self.seed = seed
        self._rng = random.Random(seed)
        self._counter = 0

    def uuid4_like(self) -> str:
        """Return a deterministic RFC-4122-formatted UUIDv4 string."""
        raw = bytearray(self._rng.getrandbits(8) for _ in range(16))
        raw[6] = (raw[6] & 0x0F) | 0x40
        raw[8] = (raw[8] & 0x3F) | 0x80
        hexed = raw.hex()
        return f"{hexed[0:8]}-{hexed[8:12]}-{hexed[12:16]}-{hexed[16:20]}-{hexed[20:32]}"

    def user(self, *, domain: str = "example.test") -> dict[str, Any]:
        """Generate one synthetic QA user record using RFC-2606 safe `.test` domain."""
        self._counter += 1
        first = self._rng.choice(_FIRST_NAMES)
        last = self._rng.choice(_LAST_NAMES)
        handle = f"{first.lower()}.{last.lower()}.{self._counter:03d}"
        phone_tail = self._rng.randint(10000000, 99999999)
        return {
            "id": self.uuid4_like(),
            "username": handle,
            "full_name": f"{first} {last}",
            "email": f"{handle}@{domain}",
            "phone": f"+62-812-{str(phone_tail)[:4]}-{str(phone_tail)[4:]}",
            "city": self._rng.choice(_CITIES),
            "role": self._rng.choice(_ROLES),
            "active": True,
        }

    def users(self, count: int = 5, *, domain: str = "example.test") -> list[dict[str, Any]]:
        if count < 1 or count > 1000:
            raise ValueError("count must be between 1 and 1000")
        return [self.user(domain=domain) for _ in range(count)]

    def invoice(self, *, currency: str = "IDR") -> dict[str, Any]:
        """Generate one deterministic synthetic order/invoice record with exact arithmetic."""
        self._counter += 1
        item_count = self._rng.randint(1, 4)
        items = []
        subtotal = 0.0
        for idx in range(1, item_count + 1):
            qty = self._rng.randint(1, 5)
            unit_price = round(self._rng.uniform(10.0, 250.0), 2)
            line_total = round(qty * unit_price, 2)
            subtotal = round(subtotal + line_total, 2)
            items.append(
                {
                    "sku": f"QA-SKU-{self._counter:03d}-{idx:02d}",
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                }
            )
        tax = round(subtotal * 0.11, 2)
        total = round(subtotal + tax, 2)
        base_dt = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=self._counter * 17)
        return {
            "invoice_id": f"INV-QA-{self._counter:05d}",
            "issued_at": base_dt.isoformat(),
            "currency": currency,
            "items": items,
            "subtotal": subtotal,
            "tax_rate": 0.11,
            "tax_amount": tax,
            "grand_total": total,
        }
