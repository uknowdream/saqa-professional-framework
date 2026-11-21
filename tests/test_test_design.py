"""Tests for black-box QA test design generators and synthetic data factory."""
from __future__ import annotations

import pytest

from saqa.test_design import (
    DecisionRule,
    SyntheticDataFactory,
    boundary_value_numeric,
    boundary_value_string,
    equivalence_partitions,
    error_guessing_payloads,
    evaluate_decision_table,
    generate_decision_table_cases,
    pairwise_matrix,
    state_transition_paths,
    verify_pairwise_coverage,
)


def test_boundary_value_numeric_covers_all_7_points_and_validates_bounds():
    cases = boundary_value_numeric(1, 100, step=1, field_name="quantity")
    labels = [c.label for c in cases]
    assert labels == ["below_min", "at_min", "above_min", "nominal", "below_max", "at_max", "above_max"]
    by_label = {c.label: c for c in cases}
    assert by_label["below_min"].value == 0 and by_label["below_min"].valid is False
    assert by_label["at_min"].value == 1 and by_label["at_min"].valid is True
    assert by_label["at_max"].value == 100 and by_label["at_max"].valid is True
    assert by_label["above_max"].value == 101 and by_label["above_max"].valid is False
    assert by_label["nominal"].to_dict()["technique"] == "BVA"

    with pytest.raises(ValueError):
        boundary_value_numeric(10, 5)
    with pytest.raises(ValueError):
        boundary_value_numeric(True, 10)
    with pytest.raises(ValueError):
        boundary_value_numeric(1, 10, step=0)


def test_boundary_value_string_generates_length_and_unicode_probes():
    cases = boundary_value_string(3, 10, field_name="username")
    by_label = {c.label: c for c in cases}
    assert by_label["empty"].value == "" and by_label["empty"].valid is False
    assert len(by_label["below_min"].value) == 2 and by_label["below_min"].valid is False
    assert len(by_label["at_min"].value) == 3 and by_label["at_min"].valid is True
    assert len(by_label["at_max"].value) == 10 and by_label["at_max"].valid is True
    assert len(by_label["above_max"].value) == 11 and by_label["above_max"].valid is False
    assert by_label["whitespace_only"].valid is False
    assert by_label["unicode_multibyte"].valid is True

    with pytest.raises(ValueError):
        boundary_value_string(5, 2)
    with pytest.raises(ValueError):
        boundary_value_string(1, 5, char="ab")


def test_equivalence_partitions_labels_valid_and_invalid_classes():
    cases = equivalence_partitions(
        {"standard_age": [25, 30], "senior_age": [65]},
        {"negative_age": [-1], "non_numeric": ["abc"]},
    )
    assert len(cases) == 4
    assert sum(1 for c in cases if c.valid) == 2
    assert sum(1 for c in cases if not c.valid) == 2

    with pytest.raises(ValueError):
        equivalence_partitions({"empty": []})
    with pytest.raises(ValueError):
        equivalence_partitions({"ok": [1]}, {"bad": []})


def test_pairwise_matrix_achieves_100_percent_2way_coverage_and_reduces_cases():
    params = {
        "browser": ["chromium", "firefox", "webkit"],
        "os": ["linux", "windows", "macos"],
        "role": ["guest", "member", "admin"],
        "locale": ["en-US", "id-ID", "ja-JP"],
    }
    cases_a = pairwise_matrix(params, seed=42)
    cases_b = pairwise_matrix(params, seed=42)
    assert cases_a == cases_b  # Deterministic by seed
    report = verify_pairwise_coverage(params, cases_a)
    assert report["coverage_pct"] == 100.0
    assert report["missing_pairs"] == 0
    assert report["full_cartesian_size"] == 81
    assert report["actual_case_count"] < 25
    assert report["reduction_pct"] > 70.0

    # Single-parameter degenerate case
    single = pairwise_matrix({"env": ["dev", "staging"]})
    assert single == [{"env": "dev"}, {"env": "staging"}]
    assert verify_pairwise_coverage({"env": ["dev", "staging"]}, single)["coverage_pct"] == 100.0

    with pytest.raises(ValueError):
        pairwise_matrix({})
    with pytest.raises(ValueError):
        pairwise_matrix({"a": []})


def test_decision_table_evaluation_and_duplicate_detection():
    rules = [
        DecisionRule("R1", {"authenticated": True, "role": "admin"}, {"allow": True, "status": 200}),
        DecisionRule("R2", {"authenticated": True, "role": "viewer"}, {"allow": False, "status": 403}),
        DecisionRule("R3", {"authenticated": False, "role": "*"}, {"allow": False, "status": 401}),
    ]
    matched = evaluate_decision_table(rules, {"authenticated": False, "role": "admin"})
    assert [r.rule_id for r in matched] == ["R3"]
    cases = generate_decision_table_cases(rules)
    assert len(cases) == 3

    with pytest.raises(ValueError, match="duplicate"):
        generate_decision_table_cases([rules[0], DecisionRule("R1-dup", rules[0].conditions, {})])
    with pytest.raises(ValueError):
        generate_decision_table_cases([])


def test_state_transition_paths_generates_valid_and_negative_probes():
    transitions = {
        "DRAFT": {"submit": "REVIEW"},
        "REVIEW": {"approve": "PUBLISHED", "reject": "DRAFT"},
        "PUBLISHED": {"archive": "ARCHIVED"},
        "ARCHIVED": {},
    }
    graph = state_transition_paths("DRAFT", transitions)
    assert graph["reachable_states"] == ["ARCHIVED", "DRAFT", "PUBLISHED", "REVIEW"]
    assert len(graph["valid_transitions"]) == 4
    assert len(graph["invalid_transition_probes"]) == 12
    assert all(case["valid"] is True for case in graph["valid_transitions"])
    assert all(case["valid"] is False for case in graph["invalid_transition_probes"])

    with pytest.raises(ValueError):
        state_transition_paths("UNKNOWN", transitions)


def test_error_guessing_payloads_and_synthetic_data_factory():
    all_payloads = error_guessing_payloads("all")
    assert set(all_payloads) == {"strings", "numbers", "dates", "security_probes", "json_types"}
    assert "numbers" in error_guessing_payloads("numbers")
    with pytest.raises(ValueError):
        error_guessing_payloads("nonexistent")

    f1 = SyntheticDataFactory(seed=12345)
    f2 = SyntheticDataFactory(seed=12345)
    users1 = f1.users(3)
    users2 = f2.users(3)
    assert users1 == users2
    assert all(u["email"].endswith("@example.test") for u in users1)

    inv = f1.invoice()
    expected_subtotal = round(sum(item["line_total"] for item in inv["items"]), 2)
    assert inv["subtotal"] == expected_subtotal
    assert inv["grand_total"] == round(inv["subtotal"] + inv["tax_amount"], 2)

    with pytest.raises(ValueError):
        f1.users(0)
