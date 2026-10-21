"""Build a measured performance run set from at least five raw k6 summary files."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from typing import Any

SUMMARY_SCHEMA = "saqa.k6-summary.v1"
POLICY_SCHEMA = "saqa.performance-guardrails.v1"
RUNSET_SCHEMA = "saqa.performance-run-set.v1"
MIN_SAMPLES = 5

def finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be a finite number")
    return converted


def canonical_policy_sha256(policy: dict[str, Any]) -> str:
    """Return the canonical digest shared by run-set producers and comparators."""
    try:
        raw = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"cannot canonically encode performance policy: {exc}") from exc
    return hashlib.sha256(raw).hexdigest()

def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"cannot read JSON object {path}: root must be an object")
    return value

def extract_sample(summary: Any, policy: dict[str, Any], label: str) -> dict[str, float]:
    if not isinstance(summary, dict) or summary.get("schema") != SUMMARY_SCHEMA:
        raise ValueError(f"{label}: unsupported k6 summary schema")
    metric_map, metrics = policy.get("metrics"), summary.get("metrics")
    if not isinstance(metric_map, dict) or not isinstance(metrics, dict):
        raise ValueError(f"{label}: policy mappings and summary metrics must be objects")
    for field in ("latency", "error_rate", "throughput", "functional_checks"):
        metric_name = metric_map.get(field)
        if not isinstance(metric_name, str) or not metric_name.strip():
            raise ValueError(f"{label}: policy metric mapping for {field} must be a non-empty string")
    def metric(name: Any, key: str) -> float:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label}: policy metric name for field {key} must be a non-empty string")
        record = metrics.get(name)
        values = record.get("values") if isinstance(record, dict) else None
        if not isinstance(values, dict):
            raise ValueError(f"{label}: missing metric {name}.{key}")
        return finite(values.get(key), f"{label}: {name}.{key}")
    sample = {"median_ms": metric(metric_map.get("latency"), "med"),
              "p95_ms": metric(metric_map.get("latency"), "p(95)"),
              "p99_ms": metric(metric_map.get("latency"), "p(99)"),
              "error_rate": metric(metric_map.get("error_rate"), "rate"),
              "throughput_rps": metric(metric_map.get("throughput"), "rate"),
              "check_pass_rate": metric(metric_map.get("functional_checks"), "rate")}
    if any(sample[k] < 0 for k in ("median_ms", "p95_ms", "p99_ms", "throughput_rps")):
        raise ValueError(f"{label}: latency and throughput must be non-negative")
    if sample["median_ms"] > sample["p95_ms"]: raise ValueError(f"{label}: median must not exceed p95")
    if sample["p95_ms"] > sample["p99_ms"]: raise ValueError(f"{label}: p95 must not exceed p99")
    if any(not 0 <= sample[k] <= 1 for k in ("error_rate", "check_pass_rate")):
        raise ValueError(f"{label}: rates must be between 0 and 1")
    return sample

def build_run_set(summary_paths: list[Path], policy: Any, *, target_profile: str, workload_profile: str, environment_fingerprint: str, workload_script: Path, source_root: Path | None = None, runner_image_version: str | None = None) -> dict[str, Any]:
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA: raise ValueError("unsupported performance policy schema")
    if not isinstance(policy.get("policy_id"), str) or not policy["policy_id"].strip(): raise ValueError("policy_id must be a non-empty string")
    version = policy.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1: raise ValueError("policy version must be a positive integer")
    for name, value in (("target_profile", target_profile), ("workload_profile", workload_profile), ("environment_fingerprint", environment_fingerprint)):
        if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} must be a non-empty string")
    if runner_image_version is not None and (not isinstance(runner_image_version, str) or not runner_image_version.strip()):
        raise ValueError("runner_image_version must be a non-empty string when provided")
    if len(summary_paths) < MIN_SAMPLES: raise ValueError(f"at least {MIN_SAMPLES} raw summary files are required")
    samples, sources = [], []
    seen_paths = set()
    seen_digests = set()
    root = source_root.resolve() if source_root is not None else None
    for path in summary_paths:
        resolved_path = path.resolve()
        if resolved_path in seen_paths:
            raise ValueError(f"duplicate raw summary path: {path}")
        seen_paths.add(resolved_path)
        resolved_path = path.resolve()
        if root is not None and not resolved_path.is_relative_to(root):
            raise ValueError(f"raw summary path escapes source root: {path}")
        raw = resolved_path.read_bytes()
        try: summary = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc: raise ValueError(f"cannot parse k6 summary {path}: {exc}") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen_digests:
            raise ValueError(f"duplicate raw summary content (SHA-256): {path}")
        seen_digests.add(digest)
        samples.append(extract_sample(summary, policy, str(path)))
        stored_path = resolved_path.relative_to(root).as_posix() if root is not None else str(path)
        sources.append({"path": stored_path, "sha256": digest})
    policy_digest = canonical_policy_sha256(policy)
    workload_path = workload_script.resolve()
    if not workload_path.is_file(): raise ValueError(f"workload script does not exist: {workload_script}")
    try: workload_digest = hashlib.sha256(workload_path.read_bytes()).hexdigest()
    except OSError as exc: raise ValueError(f"cannot read workload script {workload_script}: {exc}") from exc
    result = {"schema": RUNSET_SCHEMA, "target_profile": target_profile.strip(), "workload_profile": workload_profile.strip(),
              "workload_sha256": workload_digest, "policy_id": policy["policy_id"].strip(), "policy_version": version, "policy_sha256": policy_digest, "environment_fingerprint": environment_fingerprint.strip(),
              "samples": samples, "sample_sources": sources,
              "provenance_note": "SHA-256 identifies input bytes but does not authenticate origin; preserve trusted artifact attestations separately."}
    if runner_image_version is not None:
        result["runner_image_version"] = runner_image_version.strip()
    return result

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="append", type=Path, required=True, help="repeat at least five times")
    parser.add_argument("--policy", type=Path, required=True); parser.add_argument("--target-profile", required=True)
    parser.add_argument("--workload-profile", required=True); parser.add_argument("--environment-fingerprint", required=True)
    parser.add_argument("--workload-script", type=Path, required=True, help="exact k6 script whose SHA-256 will be bound into the run set")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, help="store source paths relative to this root and reject files outside it")
    parser.add_argument("--runner-image-version", help="exact runner image version for reporting; compatibility checks use environment fingerprint")
    args = parser.parse_args(argv)
    try:
        result = build_run_set(args.summary, read_json(args.policy), target_profile=args.target_profile,
                               workload_profile=args.workload_profile, environment_fingerprint=args.environment_fingerprint,
                               workload_script=args.workload_script, source_root=args.source_root,
                               runner_image_version=args.runner_image_version)
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema": RUNSET_SCHEMA, "status": "BLOCKED", "error": str(exc)}, indent=2)); return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "BUILT", "sample_count": len(result["samples"]), "output": str(args.output)}, indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())