"""Quality intelligence, latency statistics, cross-run diff, and trend analytics for SAQA."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evidence import EvidenceRecord, verify_manifest
from .flaky import analyze_suite_flakiness
from .history import verify_history


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Linear-interpolated percentile matching standard statistical definition."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return round(float(sorted_values[0]), 3)
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(float(sorted_values[lower]), 3)
    weight = rank - lower
    interpolated = sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    return round(float(interpolated), 3)


def compute_latency_stats(samples_ms: Sequence[float]) -> dict[str, float | int]:
    """Compute exact latency distribution metrics in milliseconds."""
    cleaned = sorted(
        float(v)
        for v in samples_ms
        if not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and v >= 0
    )
    if not cleaned:
        return {
            "count": 0,
            "min_ms": 0.0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p90_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "max_ms": 0.0,
            "stdev_ms": 0.0,
        }
    stdev = round(statistics.stdev(cleaned), 3) if len(cleaned) >= 2 else 0.0
    return {
        "count": len(cleaned),
        "min_ms": round(cleaned[0], 3),
        "mean_ms": round(sum(cleaned) / len(cleaned), 3),
        "p50_ms": _percentile(cleaned, 50.0),
        "p90_ms": _percentile(cleaned, 90.0),
        "p95_ms": _percentile(cleaned, 95.0),
        "p99_ms": _percentile(cleaned, 99.0),
        "max_ms": round(cleaned[-1], 3),
        "stdev_ms": stdev,
    }


def _extract_latency_ms(details: Mapping[str, Any]) -> float | None:
    for key in ("elapsed_ms", "duration_ms", "latency_ms", "response_time_ms"):
        value = details.get(key)
        if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            return float(value)
    return None


def _normalize_record(item: EvidenceRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(item, EvidenceRecord):
        return {
            "test_id": item.test_id,
            "status": item.status,
            "observed_at": item.observed_at,
            "target": item.target,
            "details": dict(item.details),
        }
    return {
        "test_id": str(item["test_id"]),
        "status": str(item["status"]),
        "observed_at": str(item["observed_at"]),
        "target": str(item["target"]),
        "details": dict(item.get("details") or {}),
    }


def load_verified_manifest(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Load and cryptographically verify a SAQA evidence manifest (fail-closed)."""
    if not verify_manifest(path):
        raise ValueError(f"evidence manifest failed integrity verification: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [dict(record) for record in data["records"]], str(data["sha256"])


def _grade_from_score(score: float) -> str:
    if score >= 95.0:
        return "A"
    if score >= 85.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 50.0:
        return "D"
    return "F"


def analyze_records(
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    *,
    manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Compute comprehensive Quality Intelligence metrics for a collection of evidence records."""
    normalized = [_normalize_record(record) for record in records]
    counts = {
        "PASS": 0,
        "FAIL": 0,
        "BLOCKED": 0,
        "UNVERIFIED": 0,
        "NOT_APPLICABLE": 0,
    }
    by_target: dict[str, dict[str, int]] = {}
    latencies: list[float] = []
    timed_tests: list[dict[str, Any]] = []
    failing_tests: list[dict[str, Any]] = []
    blocked_tests: list[str] = []
    unverified_tests: list[str] = []

    for rec in normalized:
        status = rec["status"]
        counts[status] = counts.get(status, 0) + 1

        target = rec["target"]
        bucket = by_target.setdefault(target, {"total": 0, "PASS": 0, "FAIL": 0, "BLOCKED": 0, "UNVERIFIED": 0})
        bucket["total"] += 1
        if status in bucket:
            bucket[status] += 1

        latency = _extract_latency_ms(rec["details"])
        if latency is not None:
            latencies.append(latency)
            timed_tests.append(
                {
                    "test_id": rec["test_id"],
                    "status": status,
                    "elapsed_ms": round(latency, 3),
                    "target": target,
                }
            )

        if status == "FAIL":
            reasons = rec["details"].get("failure_reasons") or rec["details"].get("error")
            failing_tests.append(
                {
                    "test_id": rec["test_id"],
                    "target": target,
                    "reasons": reasons if isinstance(reasons, list) else ([str(reasons)] if reasons else []),
                }
            )
        elif status == "BLOCKED":
            blocked_tests.append(rec["test_id"])
        elif status == "UNVERIFIED":
            unverified_tests.append(rec["test_id"])

    total = len(normalized)
    applicable = total - counts["NOT_APPLICABLE"]
    pass_rate = round((counts["PASS"] / applicable) * 100.0, 2) if applicable > 0 else 0.0
    fail_rate = round((counts["FAIL"] / applicable) * 100.0, 2) if applicable > 0 else 0.0

    # Transparent Health Score formula (0-100):
    # Starts from applicable pass rate, subtracts severity-weighted penalties for
    # verified FAILs, BLOCKED dependencies, and UNVERIFIED gaps.
    if applicable == 0:
        health_score = 0.0
    else:
        fail_penalty = (counts["FAIL"] / applicable) * 35.0
        blocked_penalty = (counts["BLOCKED"] / applicable) * 20.0
        unverified_penalty = (counts["UNVERIFIED"] / applicable) * 15.0
        health_score = round(max(0.0, min(100.0, pass_rate - fail_penalty - blocked_penalty - unverified_penalty)), 2)

    if counts["FAIL"] > 0:
        overall_status = "FAIL"
    elif counts["BLOCKED"] > 0:
        overall_status = "BLOCKED"
    elif counts["UNVERIFIED"] > 0 or total == 0:
        overall_status = "UNVERIFIED"
    else:
        overall_status = "PASS"

    slowest_tests = sorted(timed_tests, key=lambda item: (-item["elapsed_ms"], item["test_id"]))[:10]

    recommendations: list[str] = []
    if failing_tests:
        recommendations.append(
            f"Investigate {len(failing_tests)} failing test(s): {', '.join(item['test_id'] for item in failing_tests[:5])}"
        )
    if blocked_tests:
        recommendations.append(
            f"Unblock {len(blocked_tests)} blocked test(s) caused by missing dependencies or unreachable targets."
        )
    if unverified_tests:
        recommendations.append(
            f"Complete verification for {len(unverified_tests)} UNVERIFIED test(s) before release sign-off."
        )
    if not recommendations and total > 0:
        recommendations.append("All executed checks passed with clean evidence integrity.")

    return {
        "schema": "saqa.analytics.v1",
        "overall_status": overall_status,
        "manifest_sha256": manifest_sha256,
        "total_records": total,
        "applicable_records": applicable,
        "status_counts": counts,
        "pass_rate_pct": pass_rate,
        "fail_rate_pct": fail_rate,
        "health_score": health_score,
        "health_grade": _grade_from_score(health_score),
        "latency": compute_latency_stats(latencies),
        "slowest_tests": slowest_tests,
        "by_target": by_target,
        "failing_tests": failing_tests,
        "blocked_tests": sorted(blocked_tests),
        "unverified_tests": sorted(unverified_tests),
        "recommendations": recommendations,
    }


def analyze_manifest(path: Path) -> dict[str, Any]:
    """Verify and analyze a SAQA evidence manifest file."""
    records, digest = load_verified_manifest(path)
    return analyze_records(records, manifest_sha256=digest)


def compare_records(
    baseline_records: Sequence[EvidenceRecord | Mapping[str, Any]],
    current_records: Sequence[EvidenceRecord | Mapping[str, Any]],
    *,
    latency_regression_pct: float = 25.0,
    min_latency_delta_ms: float = 15.0,
) -> dict[str, Any]:
    """Compare baseline vs current evidence to pinpoint regressions, fixes, and latency drift."""
    base_norm = [_normalize_record(r) for r in baseline_records]
    curr_norm = [_normalize_record(r) for r in current_records]

    base_map = {rec["test_id"]: rec for rec in base_norm}
    curr_map = {rec["test_id"]: rec for rec in curr_norm}

    base_stats = analyze_records(base_norm)
    curr_stats = analyze_records(curr_norm)

    new_failures: list[dict[str, Any]] = []
    fixed: list[dict[str, Any]] = []
    persistent_failures: list[dict[str, Any]] = []
    status_changes: list[dict[str, Any]] = []
    latency_regressions: list[dict[str, Any]] = []
    latency_improvements: list[dict[str, Any]] = []

    shared_ids = sorted(set(base_map) & set(curr_map))
    added_tests = sorted(set(curr_map) - set(base_map))
    removed_tests = sorted(set(base_map) - set(curr_map))

    for test_id in shared_ids:
        b = base_map[test_id]
        c = curr_map[test_id]
        b_status = b["status"]
        c_status = c["status"]
        if b_status != c_status:
            change = {"test_id": test_id, "baseline_status": b_status, "current_status": c_status}
            status_changes.append(change)
            if b_status == "PASS" and c_status in {"FAIL", "BLOCKED", "UNVERIFIED"}:
                new_failures.append(change)
            elif b_status in {"FAIL", "BLOCKED", "UNVERIFIED"} and c_status == "PASS":
                fixed.append(change)
        elif c_status == "FAIL":
            persistent_failures.append({"test_id": test_id, "status": c_status})

        b_ms = _extract_latency_ms(b["details"])
        c_ms = _extract_latency_ms(c["details"])
        if b_ms is not None and c_ms is not None and b_ms > 0:
            delta_ms = round(c_ms - b_ms, 3)
            delta_pct = round(((c_ms - b_ms) / b_ms) * 100.0, 2)
            if delta_pct >= latency_regression_pct and delta_ms >= min_latency_delta_ms:
                latency_regressions.append(
                    {
                        "test_id": test_id,
                        "baseline_ms": round(b_ms, 3),
                        "current_ms": round(c_ms, 3),
                        "delta_ms": delta_ms,
                        "delta_pct": delta_pct,
                    }
                )
            elif delta_pct <= -latency_regression_pct and delta_ms <= -min_latency_delta_ms:
                latency_improvements.append(
                    {
                        "test_id": test_id,
                        "baseline_ms": round(b_ms, 3),
                        "current_ms": round(c_ms, 3),
                        "delta_ms": delta_ms,
                        "delta_pct": delta_pct,
                    }
                )

    latency_regressions.sort(key=lambda item: (-item["delta_pct"], item["test_id"]))
    latency_improvements.sort(key=lambda item: (item["delta_pct"], item["test_id"]))

    pass_rate_delta = round(curr_stats["pass_rate_pct"] - base_stats["pass_rate_pct"], 2)
    health_score_delta = round(curr_stats["health_score"] - base_stats["health_score"], 2)

    if new_failures or latency_regressions:
        verdict = "REGRESSED"
    elif curr_stats["overall_status"] == "BLOCKED":
        verdict = "BLOCKED"
    elif fixed or latency_improvements or health_score_delta > 0:
        verdict = "IMPROVED"
    else:
        verdict = "STABLE"

    return {
        "schema": "saqa.diff.v1",
        "verdict": verdict,
        "baseline_summary": {
            "total": base_stats["total_records"],
            "pass_rate_pct": base_stats["pass_rate_pct"],
            "health_score": base_stats["health_score"],
            "p95_ms": base_stats["latency"]["p95_ms"],
        },
        "current_summary": {
            "total": curr_stats["total_records"],
            "pass_rate_pct": curr_stats["pass_rate_pct"],
            "health_score": curr_stats["health_score"],
            "p95_ms": curr_stats["latency"]["p95_ms"],
        },
        "pass_rate_delta_pct": pass_rate_delta,
        "health_score_delta": health_score_delta,
        "new_failures": new_failures,
        "fixed": fixed,
        "persistent_failures": persistent_failures,
        "added_tests": added_tests,
        "removed_tests": removed_tests,
        "status_changes": status_changes,
        "latency_regressions": latency_regressions,
        "latency_improvements": latency_improvements,
    }


def compare_manifests(
    baseline_path: Path,
    current_path: Path,
    *,
    latency_regression_pct: float = 25.0,
    min_latency_delta_ms: float = 15.0,
) -> dict[str, Any]:
    """Load, verify, and compare two SAQA evidence manifests."""
    base_records, base_sha = load_verified_manifest(baseline_path)
    curr_records, curr_sha = load_verified_manifest(current_path)
    diff = compare_records(
        base_records,
        curr_records,
        latency_regression_pct=latency_regression_pct,
        min_latency_delta_ms=min_latency_delta_ms,
    )
    diff["baseline_sha256"] = base_sha
    diff["current_sha256"] = curr_sha
    return diff


def analyze_history_file(path: Path) -> dict[str, Any]:
    """Verify hash-chained quality history JSONL and compute multi-commit trend & flakiness analytics."""
    if not verify_history(path):
        raise ValueError(f"quality history failed hash-chain verification: {path}")

    commits: list[dict[str, Any]] = []
    statuses_by_test: dict[str, list[str]] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        records = entry.get("records", [])
        stats = analyze_records(records)
        commits.append(
            {
                "commit_sha": entry.get("commit_sha", ""),
                "chain_sha256": entry.get("chain_sha256", ""),
                "overall_status": stats["overall_status"],
                "total_records": stats["total_records"],
                "pass_rate_pct": stats["pass_rate_pct"],
                "health_score": stats["health_score"],
                "p95_ms": stats["latency"]["p95_ms"],
            }
        )
        for rec in records:
            statuses_by_test.setdefault(str(rec["test_id"]), []).append(str(rec["status"]))

    flakiness = analyze_suite_flakiness(statuses_by_test)
    latest_pass_rate = commits[-1]["pass_rate_pct"] if commits else 0.0
    previous_pass_rate = commits[-2]["pass_rate_pct"] if len(commits) >= 2 else latest_pass_rate
    trend_delta = round(latest_pass_rate - previous_pass_rate, 2)

    return {
        "schema": "saqa.history_analytics.v1",
        "chain_verified": True,
        "commit_count": len(commits),
        "latest_commit_sha": commits[-1]["commit_sha"] if commits else None,
        "latest_pass_rate_pct": latest_pass_rate,
        "pass_rate_trend_delta_pct": trend_delta,
        "commits": commits,
        "flakiness": flakiness,
    }
