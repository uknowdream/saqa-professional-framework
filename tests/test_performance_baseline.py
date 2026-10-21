import json
from pathlib import Path
import pytest
from scripts.compare_performance_baseline import SCHEMA, compare_run_sets, load_run_set, verify_source_files


def run_set(*, p95=400, p99=700, error=0.0, throughput=8.0, checks=1.0, **metadata):
    result = {
        "schema": SCHEMA, "target_profile": "juice-shop-v20.2.0-local-loopback",
        "workload_profile": "products-search-v1", "policy_id": "juice-shop-local-performance",
        "policy_version": 1, "environment_fingerprint": "ubuntu-24.04-k6-1.2.0",
        "samples": [{"p95_ms": p95, "p99_ms": p99, "error_rate": error,
                     "throughput_rps": throughput, "check_pass_rate": checks} for _ in range(5)],
        "sample_sources": [{"path": f"run-{i}.json", "sha256": "a" * 64} for i in range(5)],
    }
    result.update(metadata)
    return result


def write_run_set(tmp_path, value):
    path = tmp_path / "runs.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return load_run_set(path)


def test_identical_runs_pass():
    result = compare_run_sets(run_set(), run_set())
    assert result["status"] == "PASS"
    assert result["failed_checks"] == []


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"p95": 450}, "p95_ms_regression"), ({"p99": 800}, "p99_ms_regression"),
    ({"throughput": 6.0}, "throughput_drop"), ({"error": 0.01}, "error_rate_increase"),
    ({"checks": 0.99}, "functional_check_pass_rate"),
])
def test_regressions_fail(kwargs, expected):
    result = compare_run_sets(run_set(), run_set(**kwargs))
    assert result["status"] == "FAIL"
    assert expected in result["failed_checks"]


@pytest.mark.parametrize("field", ["target_profile", "workload_profile", "policy_id", "policy_version", "environment_fingerprint"])
def test_metadata_mismatch_blocks_comparison(field):
    value = "different" if field != "policy_version" else 2
    with pytest.raises(ValueError, match="metadata mismatch"):
        compare_run_sets(run_set(), run_set(**{field: value}))


def test_insufficient_samples_rejected(tmp_path):
    data = run_set()
    data["samples"] = data["samples"][:4]
    path = tmp_path / "short.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="at least 5 samples"):
        load_run_set(path)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "400", None])
def test_invalid_metric_rejected(tmp_path, value):
    data = run_set()
    data["samples"][0]["p95_ms"] = value
    with pytest.raises(ValueError, match="finite number"):
        write_run_set(tmp_path, data)


def test_percentile_order_rejected(tmp_path):
    with pytest.raises(ValueError, match="p95_ms must not exceed p99_ms"):
        write_run_set(tmp_path, run_set(p95=800, p99=700))


def test_zero_baseline_denominator_rejected():
    with pytest.raises(ValueError, match="greater than zero"):
        compare_run_sets(run_set(p95=0), run_set(p95=0))


def test_negative_threshold_rejected():
    with pytest.raises(ValueError, match="finite non-negative"):
        compare_run_sets(run_set(), run_set(), max_latency_regression_pct=-1)


def test_bad_schema_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported run-set schema"):
        load_run_set(path)


def test_malformed_json_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read run set"):
        load_run_set(path)


@pytest.mark.parametrize(("field", "value", "message"), [
    ("error_rate", 1.5, "rates must be between 0 and 1"),
    ("check_pass_rate", -0.1, "rates must be between 0 and 1"),
    ("p95_ms", -1, "latency/throughput must be non-negative"),
    ("throughput_rps", -1, "latency/throughput must be non-negative"),
    ("p95_ms", float("nan"), "finite number"),
])
def test_comparison_api_validates_samples_even_without_loader(field, value, message):
    baseline = run_set()
    candidate = run_set()
    candidate["samples"][0][field] = value
    with pytest.raises(ValueError, match=message):
        compare_run_sets(baseline, candidate)


def test_comparison_api_rejects_wrong_schema_without_loader():
    baseline = run_set()
    candidate = run_set()
    candidate["schema"] = "unknown"
    with pytest.raises(ValueError, match="unsupported run-set schema"):
        compare_run_sets(baseline, candidate)


def test_comparison_api_rejects_boolean_policy_version():
    baseline = run_set()
    candidate = run_set()
    candidate["policy_version"] = True
    baseline["policy_version"] = True
    with pytest.raises(ValueError, match="positive integer"):
        compare_run_sets(baseline, candidate)


def test_missing_source_hashes_are_rejected(tmp_path):
    data = run_set()
    data["sample_sources"][0]["sha256"] = "not-a-hash"
    path = tmp_path / "bad-sources.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="lowercase SHA-256 digest"):
        load_run_set(path)


def test_source_count_must_match_sample_count():
    baseline = run_set()
    candidate = run_set()
    candidate["sample_sources"] = candidate["sample_sources"][:4]
    with pytest.raises(ValueError, match="sample_sources must match"):
        compare_run_sets(baseline, candidate)


def test_source_files_are_hash_verified_and_path_confined(tmp_path):
    import hashlib
    raw = tmp_path / "run-0.json"
    raw.write_text('{"metrics": "actual"}', encoding="utf-8")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    data = run_set()
    data["sample_sources"] = [{"path": "run-0.json", "sha256": digest} for _ in data["samples"]]
    verify_source_files(data, tmp_path, "baseline")

    data["sample_sources"][0]["sha256"] = "a" * 64
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_source_files(data, tmp_path, "baseline")


def test_source_paths_cannot_escape_root(tmp_path):
    import hashlib
    outside = tmp_path.parent / "outside-saqa-run.json"
    outside.write_text("private", encoding="utf-8")
    data = run_set()
    data["sample_sources"] = [{"path": "../outside-saqa-run.json", "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()} for _ in data["samples"]]
    with pytest.raises(ValueError, match="escapes source root"):
        verify_source_files(data, tmp_path, "candidate")
