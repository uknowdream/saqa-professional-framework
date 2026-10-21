"""Compare repeated, metadata-matched k6 run sets against a measured baseline."""
from __future__ import annotations
import argparse, hashlib, json, math, statistics, re, sys
from pathlib import Path
from typing import Any

# Running this file by path sets sys.path[0] to scripts/, not the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_performance_run_set import canonical_policy_sha256, extract_sample, read_json

SCHEMA = "saqa.performance-run-set.v1"
METADATA = ("target_profile", "workload_profile", "policy_id", "policy_version", "policy_sha256", "environment_fingerprint")
METRICS = ("median_ms", "p95_ms", "p99_ms", "error_rate", "throughput_rps", "check_pass_rate")
MIN_SAMPLES = 5
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be a finite number")
    return converted



def validate_sources(value: dict[str, Any], label: str) -> None:
    sources = value.get("sample_sources")
    samples = value.get("samples")
    if not isinstance(sources, list) or not isinstance(samples, list) or len(sources) != len(samples):
        raise ValueError(f"{label} sample_sources must match the sample count")
    seen_paths = set()
    seen_digests = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or not isinstance(source.get("path"), str) or not source["path"].strip():
            raise ValueError(f"{label} sample_sources[{index}].path must be a non-empty string")
        normalized_path = str(Path(source["path"]))
        if normalized_path in seen_paths:
            raise ValueError(f"{label} sample_sources contains duplicate path: {normalized_path}")
        seen_paths.add(normalized_path)
        digest = source.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ValueError(f"{label} sample_sources[{index}].sha256 must be a lowercase SHA-256 digest")
        if digest in seen_digests:
            raise ValueError(f"{label} sample_sources contains duplicate SHA-256 digest; repeated raw summaries are not independent samples")
        seen_digests.add(digest)



def verify_source_files(run_set: dict[str, Any], source_root: Path, label: str, policy: dict[str, Any] | None = None) -> None:
    """Verify raw source hashes and bind metric rows to raw JSON when policy is supplied."""
    root = source_root.resolve()
    seen_resolved_paths: set[Path] = set()
    for index, source in enumerate(run_set["sample_sources"]):
        candidate = (root / source["path"]).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"{label} sample_sources[{index}] escapes source root")
        if candidate in seen_resolved_paths:
            raise ValueError(f"{label} sample_sources contains duplicate resolved file: {source['path']}")
        seen_resolved_paths.add(candidate)
        if not candidate.is_file():
            raise ValueError(f"{label} source file does not exist: {source['path']}")
        try:
            raw = candidate.read_bytes()
        except OSError as exc:
            raise ValueError(f"{label} cannot read source file {source['path']}: {exc}") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source["sha256"]:
            raise ValueError(f"{label} source SHA-256 mismatch: {source['path']}")
        if policy is not None:
            try:
                summary = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
                raise ValueError(f"{label} source is not valid UTF-8 JSON: {source['path']}") from exc
            source_sample = extract_sample(summary, policy, f"{label} source {source['path']}")
            declared_sample = run_set["samples"][index]
            for metric_name in METRICS:
                if not math.isclose(source_sample[metric_name], declared_sample[metric_name], rel_tol=0.0, abs_tol=1e-9):
                    raise ValueError(f"{label} sample/source metric mismatch: {source['path']}:{metric_name}")

def load_run_set(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
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
    if not isinstance(data.get("policy_sha256"), str) or not SHA256_RE.fullmatch(data["policy_sha256"]):
        raise ValueError(f"{path}: policy_sha256 must be a lowercase SHA-256 digest")
    samples = data.get("samples")
    if not isinstance(samples, list) or len(samples) < MIN_SAMPLES:
        raise ValueError(f"{path}: at least {MIN_SAMPLES} samples are required")
    rows = []
    for i, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(f"{path}: samples[{i}] must be an object")
        row = {key: number(sample.get(key), f"samples[{i}].{key}") for key in METRICS}
        if any(row[key] < 0 for key in ("median_ms", "p95_ms", "p99_ms", "throughput_rps")):
            raise ValueError(f"{path}: samples[{i}] latency/throughput must be non-negative")
        if row["median_ms"] > row["p95_ms"]:
            raise ValueError(f"{path}: samples[{i}] median_ms must not exceed p95_ms")
        if row["p95_ms"] > row["p99_ms"]:
            raise ValueError(f"{path}: samples[{i}] p95_ms must not exceed p99_ms")
        if any(not 0 <= row[key] <= 1 for key in ("error_rate", "check_pass_rate")):
            raise ValueError(f"{path}: samples[{i}] rates must be between 0 and 1")
        rows.append(row)
    validate_sources({**data, "samples": rows}, str(path))
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
        if not isinstance(value.get("policy_sha256"), str) or not SHA256_RE.fullmatch(value["policy_sha256"]):
            raise ValueError(f"{label} policy_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(value.get("schema"), str) or value["schema"] != SCHEMA:
            raise ValueError(f"{label} has unsupported run-set schema")
        for field in METADATA:
            if field == "policy_version":
                if isinstance(value.get(field), bool) or not isinstance(value.get(field), int) or value[field] < 1:
                    raise ValueError(f"{label} policy_version must be a positive integer")
            elif not isinstance(value.get(field), str) or not value[field].strip():
                raise ValueError(f"{label} {field} must be a non-empty string")
        if not isinstance(value.get("samples"), list) or len(value["samples"]) < MIN_SAMPLES:
            raise ValueError(f"{label} requires at least {MIN_SAMPLES} samples")
        validate_sources(value, label)

    baseline_digests = {source["sha256"] for source in baseline["sample_sources"]}
    candidate_digests = {source["sha256"] for source in candidate["sample_sources"]}
    reused_digests = sorted(baseline_digests & candidate_digests)
    if reused_digests:
        raise ValueError(
            "baseline/candidate reuse raw sample SHA-256 digests; "
            "run sets must be derived from independent raw summaries"
        )

    def medians(run_set):
        values = {key: [] for key in METRICS}
        for i, sample in enumerate(run_set["samples"]):
            if not isinstance(sample, dict):
                raise ValueError(f"samples[{i}] must be an object")
            row = {key: number(sample.get(key), f"samples[{i}].{key}") for key in METRICS}
            if any(row[key] < 0 for key in ("median_ms", "p95_ms", "p99_ms", "throughput_rps")):
                raise ValueError(f"samples[{i}] latency/throughput must be non-negative")
            if row["median_ms"] > row["p95_ms"]:
                raise ValueError(f"samples[{i}] median_ms must not exceed p95_ms")
            if row["p95_ms"] > row["p99_ms"]:
                raise ValueError(f"samples[{i}] p95_ms must not exceed p99_ms")
            if any(not 0 <= row[key] <= 1 for key in ("error_rate", "check_pass_rate")):
                raise ValueError(f"samples[{i}] rates must be between 0 and 1")
            for key in METRICS:
                values[key].append(row[key])
        return {key: statistics.median(items) for key, items in values.items()}

    before, after = medians(baseline), medians(candidate)
    for key in ("median_ms", "p95_ms", "p99_ms", "throughput_rps"):
        if before[key] <= 0:
            raise ValueError(f"baseline median {key} must be greater than zero")
    checks = []
    for key in ("median_ms", "p95_ms", "p99_ms"):
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
    candidate_check_failures = [
        {"sample_index": index, "check_pass_rate": sample["check_pass_rate"]}
        for index, sample in enumerate(candidate["samples"])
        if not math.isclose(sample["check_pass_rate"], 1.0, rel_tol=0.0, abs_tol=1e-12)
    ]
    checks.append({
        "id": "functional_check_pass_rate",
        "baseline_median": before["check_pass_rate"],
        "candidate_median": after["check_pass_rate"],
        "limit": 1.0,
        "candidate_failed_sample_count": len(candidate_check_failures),
        "candidate_failed_samples": candidate_check_failures,
        "passed": not candidate_check_failures,
    })
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
    parser.add_argument("--baseline-source-root", required=True, type=Path, help="root directory containing raw samples referenced by the baseline run set")
    parser.add_argument("--candidate-source-root", required=True, type=Path, help="root directory containing raw samples referenced by the candidate run set")
    parser.add_argument("--policy", required=True, type=Path, help="versioned policy used to derive samples from raw k6 summaries")
    parser.add_argument("--max-latency-regression-pct", type=float, default=10.0)
    parser.add_argument("--max-throughput-drop-pct", type=float, default=10.0)
    parser.add_argument("--max-error-rate-increase", type=float, default=0.005,
                        help="absolute error-rate increase; 0.005 means 0.5 percentage points")
    args = parser.parse_args(argv)
    try:
        baseline = load_run_set(args.baseline)
        candidate = load_run_set(args.candidate)
        policy = read_json(args.policy)
        if not isinstance(policy, dict) or policy.get("schema") != "saqa.performance-guardrails.v1":
            raise ValueError("unsupported performance policy schema")
        policy_digest = canonical_policy_sha256(policy)
        for label, run_set in (("baseline", baseline), ("candidate", candidate)):
            if run_set["policy_id"] != policy.get("policy_id") or run_set["policy_version"] != policy.get("version"):
                raise ValueError(f"{label} run-set policy ID/version does not match the supplied policy")
            if run_set["policy_sha256"] != policy_digest:
                raise ValueError(f"{label} run-set policy SHA-256 does not match the supplied policy")
        verify_source_files(baseline, args.baseline_source_root, "baseline", policy)
        verify_source_files(candidate, args.candidate_source_root, "candidate", policy)
        result = compare_run_sets(baseline, candidate,
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
