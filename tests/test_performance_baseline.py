import json
import hashlib
from itertools import count
from pathlib import Path
import subprocess
import sys
import pytest
from scripts.build_performance_run_set import build_run_set
from scripts.compare_performance_baseline import SCHEMA, compare_run_sets, load_run_set, verify_source_files, main
from scripts.k6_gate import ROOT

K6_SCRIPT = ROOT / "performance/k6/juice-shop.js"

POLICY = json.loads((ROOT / "performance/baselines/juice-shop-local-v1.json").read_text(encoding="utf-8"))
_RUN_SET_IDS = count()


def run_set(*, median=250, p95=400, p99=700, error=0.0, throughput=8.0, checks=1.0, **metadata):
    run_set_id = next(_RUN_SET_IDS)
    result = {
        "schema": SCHEMA, "target_profile": "juice-shop-v20.2.0-local-loopback",
        "workload_profile": "products-search-v1", "workload_sha256": hashlib.sha256(K6_SCRIPT.read_bytes()).hexdigest(), "policy_id": "juice-shop-local-performance",
        "policy_version": 1, "policy_sha256": hashlib.sha256(json.dumps(POLICY, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest(), "environment_fingerprint": "ubuntu-24.04-k6-1.2.0",
        "samples": [{"median_ms": median, "p95_ms": p95, "p99_ms": p99, "error_rate": error,
                     "throughput_rps": throughput, "check_pass_rate": checks} for _ in range(5)],
        "sample_sources": [{"path": f"run-{i}.json", "sha256": hashlib.sha256(f"raw-run-set-{run_set_id}-{i}".encode()).hexdigest()} for i in range(5)],
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
    ({"median": 300}, "median_ms_regression"),
    ({"p95": 450}, "p95_ms_regression"), ({"p99": 800}, "p99_ms_regression"),
    ({"throughput": 6.0}, "throughput_drop"), ({"error": 0.01}, "error_rate_increase"),
    ({"checks": 0.99}, "functional_check_pass_rate"),
])
def test_regressions_fail(kwargs, expected):
    result = compare_run_sets(run_set(), run_set(**kwargs))
    assert result["status"] == "FAIL"
    assert expected in result["failed_checks"]


@pytest.mark.parametrize("field", ["target_profile", "workload_profile", "workload_sha256", "policy_id", "policy_version", "policy_sha256", "environment_fingerprint"])
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


def test_median_above_p95_is_rejected():
    with pytest.raises(ValueError, match="median_ms must not exceed p95_ms"):
        compare_run_sets(run_set(median=500), run_set(median=500))


def test_zero_baseline_denominator_rejected():
    with pytest.raises(ValueError, match="greater than zero"):
        compare_run_sets(run_set(median=0, p95=0), run_set(median=0, p95=0))


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
    ("median_ms", -1, "latency/throughput must be non-negative"),
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
    data = run_set()
    sources = []
    for index in range(len(data["samples"])):
        raw = tmp_path / f"run-{index}.json"
        raw.write_text(json.dumps({"sample": index}), encoding="utf-8")
        sources.append({"path": raw.name, "sha256": hashlib.sha256(raw.read_bytes()).hexdigest()})
    data["sample_sources"] = sources
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



def test_baseline_and_candidate_must_not_reuse_raw_sample_digests():
    baseline = run_set()
    candidate = run_set()
    candidate["sample_sources"][0] = dict(baseline["sample_sources"][0])
    with pytest.raises(ValueError, match="reuse raw sample SHA-256 digests"):
        compare_run_sets(baseline, candidate)


def test_baseline_and_candidate_allow_disjoint_raw_sample_digests():
    baseline = run_set()
    candidate = run_set()
    candidate["sample_sources"] = [
        {"path": f"candidate-{i}.json", "sha256": hashlib.sha256(f"candidate-{i}".encode()).hexdigest()}
        for i in range(5)
    ]
    assert compare_run_sets(baseline, candidate)["status"] == "PASS"


def test_duplicate_sample_source_paths_are_rejected():
    baseline = run_set()
    candidate = run_set()
    candidate["sample_sources"] = [dict(baseline["sample_sources"][0]) for _ in candidate["samples"]]
    with pytest.raises(ValueError, match="duplicate path"):
        compare_run_sets(baseline, candidate)


def test_source_metrics_are_bound_to_raw_k6_summary(tmp_path):
    import hashlib

    def raw_summary(p95=400, p99=700, error=0.0, throughput=8.0, checks=1.0):
        return {
            "schema": "saqa.k6-summary.v1",
            "metrics": {
                "http_req_duration": {"values": {"med": 250, "p(95)": p95, "p(99)": p99}},
                "http_req_failed": {"values": {"rate": error}},
                "http_reqs": {"values": {"rate": throughput}},
                "checks": {"values": {"rate": checks}},
            },
        }

    data = run_set()
    sources = []
    for i, sample in enumerate(data["samples"]):
        path = tmp_path / f"raw-{i}.json"
        raw = json.dumps(raw_summary()).encode("utf-8")
        path.write_bytes(raw)
        sources.append({"path": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
    data["sample_sources"] = sources

    verify_source_files(data, tmp_path, "baseline", POLICY)
    data["samples"][0]["p95_ms"] = 401
    with pytest.raises(ValueError, match="sample/source metric mismatch"):
        verify_source_files(data, tmp_path, "baseline", POLICY)


def test_resolved_aliases_cannot_reuse_one_raw_sample(tmp_path):
    import hashlib
    raw = tmp_path / "run-0.json"
    raw.write_text('{"sample":"one"}', encoding="utf-8")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    data = run_set()
    data["sample_sources"] = [
        {"path": "run-0.json", "sha256": digest},
        {"path": "./run-0.json", "sha256": digest},
        *[{"path": f"run-{i}.json", "sha256": "a" * 64} for i in range(2, 5)],
    ]
    with pytest.raises(ValueError, match="duplicate resolved file"):
        verify_source_files(data, tmp_path, "candidate")


def test_policy_digest_must_be_valid_sha256(tmp_path):
    data = run_set()
    data["policy_sha256"] = "not-a-digest"
    path = tmp_path / "bad-policy-digest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="policy_sha256 must be a lowercase SHA-256 digest"):
        load_run_set(path)


def test_direct_comparison_rejects_malformed_policy_digest():
    with pytest.raises(ValueError, match="policy_sha256 must be a lowercase SHA-256 digest"):
        compare_run_sets(run_set(policy_sha256="bogus"), run_set(policy_sha256="bogus"))


def test_direct_comparison_rejects_duplicate_raw_summary_digests():
    baseline = run_set()
    candidate = run_set()
    candidate["sample_sources"] = [
        {"path": f"different-name-{i}.json", "sha256": "f" * 64} for i in range(5)
    ]
    with pytest.raises(ValueError, match="duplicate SHA-256 digest"):
        compare_run_sets(baseline, candidate)


def test_comparator_cli_imports_when_run_from_outside_repository(tmp_path):
    script = ROOT / "scripts" / "compare_performance_baseline.py"
    result = subprocess.run([sys.executable, str(script), "--help"], cwd=tmp_path,
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0
    assert "--baseline-source-root" in result.stdout


def test_main_blocks_run_set_with_wrong_policy_digest(tmp_path, capsys):
    def raw_summary(p95):
        return {
            "schema": "saqa.k6-summary.v1",
            "metrics": {
                "http_req_duration": {"values": {"med": 250, "p(95)": p95, "p(99)": p95 + 300}},
                "http_req_failed": {"values": {"rate": 0.0}},
                "http_reqs": {"values": {"rate": 8.0}},
                "checks": {"values": {"rate": 1.0}},
            },
        }

    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(POLICY), encoding="utf-8")
    runsets = []
    roots = []
    for side in ("baseline", "candidate"):
        raw_root = tmp_path / side / "raw-runs"
        raw_root.mkdir(parents=True)
        paths = []
        for index in range(5):
            path = raw_root / f"run-{index}.json"
            path.write_text(json.dumps(raw_summary(400 + index)), encoding="utf-8")
            paths.append(path)
        run_set_value = build_run_set(
            paths, POLICY,
            target_profile="juice-shop-v20.2.0-local-loopback",
            workload_profile="products-search-v1",
            environment_fingerprint="ubuntu-24.04-k6-1.2.0",
            workload_script=K6_SCRIPT,
            source_root=raw_root,
        )
        run_set_path = tmp_path / side / "run-set.json"
        run_set_path.write_text(json.dumps(run_set_value), encoding="utf-8")
        runsets.append(run_set_path)
        roots.append(raw_root)
    bad = json.loads(runsets[0].read_text(encoding="utf-8"))
    bad["policy_sha256"] = "0" * 64
    runsets[0].write_text(json.dumps(bad), encoding="utf-8")
    code = main([
        "--baseline", str(runsets[0]), "--candidate", str(runsets[1]),
        "--baseline-source-root", str(roots[0]), "--candidate-source-root", str(roots[1]),
        "--policy", str(policy_path), "--workload-script", str(K6_SCRIPT),
    ])
    assert code == 2
    assert "policy SHA-256 does not match" in capsys.readouterr().out


def test_any_candidate_sample_with_failed_functional_check_blocks():
    baseline = run_set()
    candidate = run_set()
    candidate["samples"][0]["check_pass_rate"] = 0.0
    result = compare_run_sets(baseline, candidate)
    check = next(item for item in result["checks"] if item["id"] == "functional_check_pass_rate")
    assert result["status"] == "FAIL"
    assert check["candidate_median"] == 1.0
    assert check["candidate_failed_sample_count"] == 1
    assert check["candidate_failed_samples"] == [{"sample_index": 0, "check_pass_rate": 0.0}]
    assert "functional_check_pass_rate" in result["failed_checks"]


def test_oversized_json_integer_is_blocked_instead_of_overflowing(tmp_path, capsys):
    data = run_set()
    data["samples"][0]["p95_ms"] = 10 ** 400
    path = tmp_path / "oversized.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="finite number"):
        load_run_set(path)
    with pytest.raises(ValueError, match="finite number"):
        compare_run_sets(run_set(), {**run_set(), "samples": [{**run_set()["samples"][0], "p95_ms": 10 ** 400}, *run_set()["samples"][1:]]})


def test_load_run_set_rejects_invalid_workload_script_digest(tmp_path):
    data = run_set(workload_sha256="not-a-digest")
    path = tmp_path / "bad-workload-digest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="workload_sha256 must be a lowercase SHA-256 digest"):
        load_run_set(path)


def test_direct_comparison_rejects_invalid_workload_script_digest():
    with pytest.raises(ValueError, match="workload_sha256 must be a lowercase SHA-256 digest"):
        compare_run_sets(run_set(workload_sha256="bogus"), run_set(workload_sha256="bogus"))


def test_direct_comparison_rejects_different_workload_script_hashes():
    with pytest.raises(ValueError, match="metadata mismatch: workload_sha256"):
        compare_run_sets(run_set(), run_set(workload_sha256="f" * 64))
