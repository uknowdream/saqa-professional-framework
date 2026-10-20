"""Compare repeated, metadata-matched k6 run sets against a measured baseline."""
from __future__ import annotations
import argparse, json, math, statistics
from pathlib import Path
from typing import Any

SCHEMA = "saqa.performance-run-set.v1"
METADATA = ("target_profile", "workload_profile", "policy_id", "policy_version", "environment_fingerprint")
METRICS = ("p95_ms", "p99_ms", "error_rate", "throughput_rps", "check_pass_rate")
MIN_SAMPLES = 5


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def load_run_set(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read run set {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: unsupported run-set schema")
    for field in METADATA:
        if field == "policy_version":
            continue
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"{path}: {field} must be a non-empty string")
    if isinstance(data.get("policy_version"), bool) or not isinstance(data.get("policy_version"), int) or data["policy_version"] < 1:
        raise ValueError(f"{path}: policy_version must be a positive integer")
    samples = data.get("samples")
    if not isinstance(samples, list) or len(samples) < MIN_SAMPLES:
        raise ValueError(f"{path}: at least {MIN_SAMPLES} samples are required")
    rows = []
    for i, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(f"{path}: samples[{i}] must be an object")
        row = {key: number(sample.get(key), f"samples[{i}].{key}") for key in METRICS}
        if any(row[key] < 0 for key in ("p95_ms", "p99_ms", "throughput_rps")):
            raise ValueError(f"{path}: samples[{i}] latency/throughput must be non-negative")
        if row["p95_ms"] > row["p99_ms"]:
            raise ValueError(f"{path}: samples[{i}] p95_ms must not exceed p99_ms")
        if any(not 0 <= row[key] <= 1 for key in ("error_rate", "check_pass_rate")):
            raise ValueError(f"{path}: samples[{i}] rates must be between 0 and 1")
        rows.append(row)
    return {**data, "samples": rows}


def compare_run_sets(baseline: dict[str, Any], candidate: dict[str, Any], *,
                     max_latency_regression_pct: float = 10.0,
                     max_throughput_drop_pct: float = 10.0,
                     max_error_rate_increase: float = 0.005) -> dict[str, Any]:
    """Compare medians of repeated runs; not a statistical significance test."""
    for name, threshold in (("max_latency_regression_pct", max_latency_regression_pct),
                            ("max_throughput_drop_pct", max_throughput_drop_pct),
                            ("max_error_rate_increase", max_error_rate_increase)):
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(float(threshold)) or threshold < 0:
            raise ValueError(f"{name} must be a finite non-negative number")
    for field in METADATA:
        if baseline.get(field) != candidate.get(field):
            raise ValueError(f"baseline/candidate metadata mismatch: {field}")
    for label, value in (("baseline", baseline), ("candidate", candidate)):
        if not isinstance(value.get("samples"), list) or len(value["samples"]) < MIN_SAMPLES:
            raise ValueError(f"{label} requires at least {MIN_SAMPLES} samples")

    def medians(run_set):
        values = {key: [] for key in METRICS}
        for i, sample in enumerate(run_set["samples"]):
            if not isinstance(sample, dict):
                raise ValueError(f"samples[{i}] must be an object")
            for key in METRICS:
                values[key].append(number(sample.get(key), f"samples[{i}].{key}"))
        return {key: statistics.median(items) for key, items in values.items()}

    before, after = medians(baseline), medians(candidate)
    for key in ("p95_ms", "p99_ms", "throughput_rps"):
        if before[key] <= 0:
            raise ValueError(f"baseline median {key} must be greater than zero")
    checks = []
    for key in ("p95_ms", "p99_ms"):
        delta = (after[key] - before[key]) / before[key] * 100
        checks.append({"id": key + "_regression", "baseline_median": before[key], "candidate_median": after[key],
                       "change_pct": round(delta, 4), "limit_pct": max_latency_regression_pct,
                       "passed": delta <= max_latency_regression_pct})
    drop = (before["throughput_rps"] - after["throughput_rps"]) / before["throughput_rps"] * 100
    checks.append({"id": "throughput_drop", "baseline_median": before["throughput_rps"], "candidate_median": after["throughput_rps"],
                   "change_pct": round(drop, 4), "limit_pct": max_throughput_drop_pct, "passed": drop <= max_throughput_drop_pct})
    error_delta = after["error_rate"] - before["error_rate"]
    checks.append({"id": "error_rate_increase", "baseline_median": before["error_rate"], "candidate_median": after["error_rate"],
                   "change_absolute": round(error_delta, 6), "limit_absolute": max_error_rate_increase,
                   "passed": error_delta <= max_error_rate_increase})
    checks.append({"id": "functional_check_pass_rate", "baseline_median": before["check_pass_rate"],
                   "candidate_median": after["check_pass_rate"], "limit": 1.0, "passed": after["check_pass_rate"] >= 1.0})
    failed = [item["id"] for item in checks if not item["passed"]]
    return {"schema": "saqa.performance-baseline-comparison.v1", "status": "FAIL" if failed else "PASS",
            "baseline_sample_count": len(baseline["samples"]), "candidate_sample_count": len(candidate["samples"]),
            "metadata": {field: baseline[field] for field in METADATA}, "baseline_medians": before,
            "candidate_medians": after, "checks": checks, "failed_checks": failed,
            "note": "Median-based regression screen only; not statistical significance or production SLO certification."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--max-latency-regression-pct", type=float, default=10.0)
    parser.add_argument("--max-throughput-drop-pct", type=float, default=10.0)
    parser.add_argument("--max-error-rate-increase", type=float, default=0.005,
                        help="absolute error-rate increase; 0.005 means 0.5 percentage points")
    args = parser.parse_args(argv)
    try:
        result = compare_run_sets(load_run_set(args.baseline), load_run_set(args.candidate),
                                  max_latency_regression_pct=args.max_latency_regression_pct,
                                  max_throughput_drop_pct=args.max_throughput_drop_pct,
                                  max_error_rate_increase=args.max_error_rate_increase)
    except ValueError as exc:
        print(json.dumps({"schema": "saqa.performance-baseline-comparison.v1", "status": "BLOCKED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
