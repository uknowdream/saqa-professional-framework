import json
import hashlib
from pathlib import Path
import pytest
from scripts.build_performance_run_set import build_run_set, finite
from scripts.compare_performance_baseline import load_run_set
from scripts.k6_gate import ROOT
POLICY = json.loads((ROOT / "performance/baselines/juice-shop-local-v1.json").read_text(encoding="utf-8"))
WORKLOAD_SCRIPT = ROOT / "performance/k6/juice-shop.js"

def summary(p95=400, p99=700, error=0.0, throughput=8.0, checks=1.0):
    return {"schema": "saqa.k6-summary.v1", "metrics": {
        "http_req_duration": {"values": {"med": 250, "p(95)": p95, "p(99)": p99}},
        "http_req_failed": {"values": {"rate": error}}, "http_reqs": {"values": {"rate": throughput}},
        "checks": {"values": {"rate": checks}}}}

def write_summary(folder, name, data):
    path = folder / name; path.write_text(json.dumps(data), encoding="utf-8"); return path

def build(paths):
    return build_run_set(paths, POLICY, target_profile="juice-shop-v20.2.0-local-loopback",
                         workload_profile="products-search-v1", environment_fingerprint="runner-x-k6-1.2.0", workload_script=WORKLOAD_SCRIPT)

def test_builds_run_set_with_hashes_and_compatible_schema(tmp_path):
    paths = [write_summary(tmp_path, f"run-{i}.json", summary(p95=400+i, p99=700+i)) for i in range(5)]
    result = build(paths)
    assert len(result["samples"]) == len(result["sample_sources"]) == 5
    assert all(len(source["sha256"]) == 64 for source in result["sample_sources"])
    expected_policy_digest = hashlib.sha256(json.dumps(POLICY, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    assert result["policy_sha256"] == expected_policy_digest
    out = tmp_path / "run-set.json"; out.write_text(json.dumps(result), encoding="utf-8")
    assert len(load_run_set(out)["samples"]) == 5

def test_requires_five_raw_summaries(tmp_path):
    with pytest.raises(ValueError, match="at least 5 raw summary files"): build([write_summary(tmp_path, "one.json", summary())])

def test_rejects_wrong_summary_schema(tmp_path):
    paths = [write_summary(tmp_path, f"run-{i}.json", {"schema": "wrong"}) for i in range(5)]
    with pytest.raises(ValueError, match="unsupported k6 summary schema"): build(paths)

@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), "400", None])
def test_rejects_invalid_metric(tmp_path, bad):
    paths = [write_summary(tmp_path, f"run-{i}.json", summary(p95=bad if i == 0 else 400)) for i in range(5)]
    with pytest.raises(ValueError, match="finite number"): build(paths)

def test_rejects_percentile_inconsistency(tmp_path):
    paths = [write_summary(tmp_path, f"run-{i}.json", summary(p95=800, p99=700)) for i in range(5)]
    with pytest.raises(ValueError, match="p95 must not exceed p99"): build(paths)

def test_rejects_missing_metrics(tmp_path):
    data = summary(); del data["metrics"]["checks"]
    paths = [write_summary(tmp_path, f"run-{i}.json", data) for i in range(5)]
    with pytest.raises(ValueError, match="missing metric"): build(paths)

def test_rejects_duplicate_raw_summary_path(tmp_path):
    path = write_summary(tmp_path, "same.json", summary())
    with pytest.raises(ValueError, match="duplicate raw summary path"):
        build([path, path, path, path, path])


def test_builder_records_source_paths_relative_to_explicit_root(tmp_path):
    paths = [write_summary(tmp_path, f"run-{i}.json", summary(p95=400 + i, p99=700 + i)) for i in range(5)]
    result = build_run_set(paths, POLICY, target_profile="juice-shop-v20.2.0-local-loopback",
                           workload_profile="products-search-v1", environment_fingerprint="runner-x-k6-1.2.0",
                           workload_script=WORKLOAD_SCRIPT, source_root=tmp_path)
    assert result["sample_sources"][0]["path"] == "run-0.json"
    assert all(not Path(source["path"]).is_absolute() for source in result["sample_sources"])


def test_builder_rejects_summary_outside_source_root(tmp_path):
    outside = write_summary(tmp_path, "outside.json", summary())
    root = tmp_path / "root"
    root.mkdir()
    paths = [outside] * 5
    with pytest.raises(ValueError, match="escapes source root"):
        build_run_set(paths, POLICY, target_profile="target", workload_profile="workload",
                      environment_fingerprint="runner", workload_script=WORKLOAD_SCRIPT, source_root=root)


def test_rejects_duplicate_raw_summary_content(tmp_path):
    same = [write_summary(tmp_path, f"copy-{i}.json", summary(p95=400, p99=700)) for i in range(5)]
    with pytest.raises(ValueError, match="duplicate raw summary content"):
        build(same)


def test_huge_integer_metric_becomes_validation_error():
    with pytest.raises(ValueError, match="finite number"):
        finite(10 ** 400, "oversized metric")


@pytest.mark.parametrize(("bad_field", "bad_value", "message"), [
    ("median", 500, "median must not exceed p95"),
    ("p95", -1, "latency and throughput must be non-negative"),
    ("error", 1.1, "rates must be between 0 and 1"),
    ("checks", -0.1, "rates must be between 0 and 1"),
])
def test_extract_sample_rejects_median_range_and_rate_errors(tmp_path, bad_field, bad_value, message):
    paths = []
    for i in range(5):
        item = summary(p95=400 + i, p99=700 + i)
        metric_values = item["metrics"]["http_req_duration"]["values"]
        if bad_field == "median":
            metric_values["med"] = bad_value
        elif bad_field == "p95":
            metric_values["p(95)"] = bad_value
        elif bad_field == "error":
            item["metrics"]["http_req_failed"]["values"]["rate"] = bad_value
        elif bad_field == "checks":
            item["metrics"]["checks"]["values"]["rate"] = bad_value
        paths.append(write_summary(tmp_path, f"bad-{i}.json", item))
    with pytest.raises(ValueError, match=message):
        build(paths)


@pytest.mark.parametrize(("mapping_key", "value"), [
    ("latency", []), ("latency", {}), ("latency", None),
    ("error_rate", []), ("throughput", {}),
    ("functional_checks", " "),
])
def test_rejects_non_string_or_blank_policy_metric_name(tmp_path, mapping_key, value):
    policy = json.loads(json.dumps(POLICY))
    policy["metrics"][mapping_key] = value
    paths = [write_summary(tmp_path, f"metric-{i}.json", summary()) for i in range(5)]
    with pytest.raises(ValueError, match="policy metric mapping"):
        build_run_set(paths, policy, target_profile="target", workload_profile="workload",
                      environment_fingerprint="runner", workload_script=WORKLOAD_SCRIPT)


def test_rejects_deeply_nested_summary_without_traceback(tmp_path):
    path = tmp_path / "deep.json"
    path.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
    with pytest.raises(ValueError, match="cannot read"):
        from scripts.build_performance_run_set import read_json
        read_json(path)
