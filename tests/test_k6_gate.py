import json
from pathlib import Path

import pytest

from scripts.k6_gate import evaluate_summary, repo_path, validate_script_thresholds

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "performance/baselines/juice-shop-local-v1.json").read_text(encoding="utf-8"))
K6_SCRIPT = ROOT / "performance/k6/juice-shop.js"


def summary(*, p95=400, p99=700, error_rate=0, throughput=8, check_rate=1):
    return {
        "metrics": {
            "http_req_duration": {"values": {"p(95)": p95, "p(99)": p99}},
            "http_req_failed": {"values": {"rate": error_rate}},
            "http_reqs": {"values": {"rate": throughput}},
            "checks": {"values": {"rate": check_rate}},
        }
    }


def test_shipped_policy_is_versioned_and_evaluable():
    result = evaluate_summary(summary(), POLICY)
    assert result["status"] == "PASS"
    assert result["policy_id"] == POLICY["policy_id"]
    assert result["policy_version"] == POLICY["version"]
    assert result["metrics"]["p95_ms"] == 400
    assert result["metrics"]["p99_ms"] == 700
    assert result["metrics"]["throughput_rps"] == 8


def test_exact_inclusive_guardrail_boundaries_pass():
    result = evaluate_summary(
        summary(p95=1000, p99=1500, error_rate=0.01, throughput=1.0, check_rate=1.0),
        POLICY,
    )
    assert result["status"] == "PASS"
    assert result["failed_checks"] == []
    assert all(item["passed"] for item in result["checks"])


@pytest.mark.parametrize(
    ("measurement", "expected"),
    [
        ({"p95": 1001, "p99": 1200}, "p95_latency"),
        ({"p99": 1501}, "p99_latency"),
        ({"error_rate": 0.02}, "http_error_rate"),
        ({"throughput": 0.5}, "throughput"),
        ({"check_rate": 0.99}, "check_pass_rate"),
    ],
)
def test_each_guardrail_fails_closed(measurement, expected):
    result = evaluate_summary(summary(**measurement), POLICY)
    assert result["status"] == "FAIL"
    assert expected in result["failed_checks"]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda value: value["metrics"].pop("checks"), "checks.rate"),
        (lambda value: value["metrics"]["http_reqs"]["values"].pop("rate"), "http_reqs.rate"),
        (lambda value: value["metrics"]["http_req_duration"]["values"].pop("p(99)"), "p\\(99\\)"),
    ],
)
def test_missing_later_metrics_fail_closed(mutate, expected):
    broken = summary()
    mutate(broken)
    with pytest.raises(ValueError, match=expected):
        evaluate_summary(broken, POLICY)


def test_boolean_measurement_is_rejected_as_non_numeric():
    with pytest.raises(ValueError, match="http_req_failed.rate"):
        evaluate_summary(summary(error_rate=True), POLICY)


def test_unsupported_policy_schema_is_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        evaluate_summary(summary(), {**POLICY, "schema": "unknown"})


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_measurements_are_rejected(bad_value):
    with pytest.raises(ValueError, match="must be finite"):
        evaluate_summary(summary(p95=bad_value), POLICY)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), True, "1000"])
def test_non_numeric_or_non_finite_policy_limit_is_rejected(bad_value):
    bad_policy = {**POLICY, "limits": {**POLICY["limits"], "p95_max_ms": bad_value}}
    with pytest.raises(ValueError, match="must be a finite number"):
        evaluate_summary(summary(), bad_policy)


def test_missing_policy_limit_is_rejected():
    limits = {key: value for key, value in POLICY["limits"].items() if key != "p99_max_ms"}
    with pytest.raises(ValueError, match="missing required limits"):
        evaluate_summary(summary(), {**POLICY, "limits": limits})


def test_missing_policy_metric_mapping_is_rejected():
    metrics = {key: value for key, value in POLICY["metrics"].items() if key != "functional_checks"}
    with pytest.raises(ValueError, match="metric mappings"):
        evaluate_summary(summary(), {**POLICY, "metrics": metrics})


def test_k6_rate_metric_shape_is_consumed_directly():
    assert evaluate_summary(summary(check_rate=0.75), POLICY)["metrics"]["check_pass_rate"] == 0.75


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("error_rate", -0.1, "between 0 and 1"),
        ("error_rate", 1.1, "between 0 and 1"),
        ("check_rate", 1.1, "between 0 and 1"),
        ("p95", -1, "non-negative"),
        ("p99", -1, "non-negative"),
        ("throughput", -1, "non-negative"),
    ],
)
def test_out_of_range_measurements_are_rejected(field, value, message):
    with pytest.raises(ValueError, match=message):
        evaluate_summary(summary(**{field: value}), POLICY)


@pytest.mark.parametrize(
    ("limit", "value", "message"),
    [
        ("error_rate_max", 1.1, "between 0 and 1"),
        ("check_pass_rate_min", -0.1, "between 0 and 1"),
        ("p95_max_ms", -1, "non-negative"),
        ("p99_max_ms", -1, "non-negative"),
        ("throughput_min_rps", -1, "non-negative"),
    ],
)
def test_out_of_range_policy_limits_are_rejected(limit, value, message):
    bad_policy = {**POLICY, "limits": {**POLICY["limits"], limit: value}}
    with pytest.raises(ValueError, match=message):
        evaluate_summary(summary(), bad_policy)


def test_policy_metadata_is_validated():
    for bad_policy, message in [
        ({**POLICY, "policy_id": " "}, "policy_id"),
        ({**POLICY, "version": True}, "positive integer"),
        ({**POLICY, "version": 0}, "positive integer"),
        ({**POLICY, "target_profile": ""}, "target_profile"),
    ]:
        with pytest.raises(ValueError, match=message):
            evaluate_summary(summary(), bad_policy)


def test_policy_rejects_p95_limit_above_p99_limit():
    bad_policy = {**POLICY, "limits": {**POLICY["limits"], "p95_max_ms": 1600}}
    with pytest.raises(ValueError, match="p95_max_ms must not exceed p99_max_ms"):
        evaluate_summary(summary(), bad_policy)


def test_summary_rejects_p95_above_p99():
    with pytest.raises(ValueError, match="p95_ms must not exceed p99_ms"):
        evaluate_summary(summary(p95=800, p99=700), POLICY)


def test_k6_runtime_thresholds_match_versioned_policy():
    validate_script_thresholds(K6_SCRIPT.read_text(encoding="utf-8"), POLICY)


def test_k6_runtime_threshold_drift_is_rejected():
    script_text = K6_SCRIPT.read_text(encoding="utf-8").replace('"p(95)<=1000"', '"p(95)<=999"')
    with pytest.raises(ValueError, match="p95 does not match"):
        validate_script_thresholds(script_text, POLICY)


def test_repo_path_resolves_relative_overrides_from_repo_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAQA_TEST_PATH", "custom/summary.json")
    assert repo_path("SAQA_TEST_PATH", "unused.json") == ROOT / "custom/summary.json"


def test_repo_path_preserves_absolute_overrides(monkeypatch, tmp_path):
    absolute = tmp_path / "summary.json"
    monkeypatch.setenv("SAQA_TEST_PATH", str(absolute))
    assert repo_path("SAQA_TEST_PATH", "unused.json") == absolute
