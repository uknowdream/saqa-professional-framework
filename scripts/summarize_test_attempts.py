"""Aggregate per-attempt pytest telemetry and fail on recovered retry failures."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

SHARD_SCHEMA = "saqa.test-attempt-shard.v1"
REPORT_SCHEMA = "saqa.test-attempt-report.v1"
PHASES = {"setup", "call", "teardown"}
PHASE_STATUSES = {"PASS", "FAIL", "SKIP"}
STATUSES = {"PASS", "FAIL", "SKIP"}


def _attempt_status(phases: dict[str, str]) -> str:
    if "FAIL" in phases.values():
        return "FAIL"
    if "SKIP" in phases.values():
        return "SKIP"
    return "PASS"


def load_shards(input_dir: Path) -> list[dict[str, Any]]:
    if not input_dir.is_dir():
        raise ValueError(f"attempt telemetry directory does not exist: {input_dir}")
    root = input_dir.resolve()
    paths = sorted(input_dir.glob("attempts-*.json"))
    if not paths:
        raise ValueError(f"no per-worker attempt telemetry shards found in {input_dir}")
    loaded: list[dict[str, Any]] = []
    shared: tuple[str, str, str, str] | None = None
    identities: set[tuple[str, str, int]] = set()
    worker_ids: set[str] = set()
    for path in paths:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"attempt telemetry shard is not a regular file inside the input directory: {path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read attempt telemetry shard {path.name}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("schema") != SHARD_SCHEMA:
            raise ValueError(f"{path.name}: unsupported attempt telemetry shard schema")
        metadata = []
        for key in ("run_id", "run_attempt", "commit_sha", "python_version", "worker_id"):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{path.name}: {key} must be a non-empty string")
            metadata.append(value)
        worker_id = metadata[4]
        if path.name != f"attempts-{worker_id}.json":
            raise ValueError(f"{path.name}: worker_id does not match shard filename")
        if worker_id in worker_ids:
            raise ValueError(f"duplicate worker telemetry shard: {worker_id}")
        worker_ids.add(worker_id)
        current_shared = tuple(metadata[:4])
        if shared is None:
            shared = current_shared
        elif current_shared != shared:
            raise ValueError(f"{path.name}: run or Python metadata does not match other shards")
        attempts = payload.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            raise ValueError(f"{path.name}: attempts must be a non-empty array")
        normalized = []
        for index, attempt in enumerate(attempts):
            prefix = f"{path.name}: attempts[{index}]"
            if not isinstance(attempt, dict):
                raise ValueError(f"{prefix} must be an object")
            nodeid = attempt.get("nodeid")
            attempt_index = attempt.get("attempt_index")
            if not isinstance(nodeid, str) or not nodeid.strip():
                raise ValueError(f"{prefix}.nodeid must be a non-empty string")
            if isinstance(attempt_index, bool) or not isinstance(attempt_index, int) or attempt_index < 1:
                raise ValueError(f"{prefix}.attempt_index must be a positive integer")
            key = (worker_id, nodeid, attempt_index)
            if key in identities:
                raise ValueError(f"duplicate test attempt record: {worker_id}/{nodeid}/{attempt_index}")
            identities.add(key)
            phases = attempt.get("phase_statuses")
            if not isinstance(phases, dict) or not phases or any(phase not in PHASES for phase in phases):
                raise ValueError(f"{prefix}.phase_statuses must contain known phases")
            if any(status not in PHASE_STATUSES for status in phases.values()):
                raise ValueError(f"{prefix}.phase_statuses contains an unsupported status")
            status = attempt.get("status")
            expected_status = _attempt_status(phases)
            if status not in STATUSES or status != expected_status:
                raise ValueError(f"{prefix}.status does not match phase outcomes")
            duration = attempt.get("duration_seconds")
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(float(duration)) or duration < 0:
                raise ValueError(f"{prefix}.duration_seconds must be a finite non-negative number")
            normalized.append({
                "nodeid": nodeid,
                "attempt_index": attempt_index,
                "status": status,
                "phase_statuses": dict(phases),
                "duration_seconds": float(duration),
                "worker_id": worker_id,
            })
        loaded.append({**{key: value for key, value in zip(("run_id", "run_attempt", "commit_sha", "python_version", "worker_id"), metadata)}, "attempts": normalized})
    return loaded


def summarize_shards(shards: list[dict[str, Any]], *, generated_at: str | None = None) -> dict[str, Any]:
    if not shards:
        raise ValueError("at least one valid telemetry shard is required")
    attempts_by_test: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for shard in shards:
        for attempt in shard["attempts"]:
            attempts_by_test[attempt["nodeid"]].append(attempt)
    tests: list[dict[str, Any]] = []
    for nodeid, attempts in sorted(attempts_by_test.items()):
        attempts.sort(key=lambda item: item["attempt_index"])
        indexes = [item["attempt_index"] for item in attempts]
        if indexes != list(range(1, len(indexes) + 1)):
            raise ValueError(f"{nodeid}: attempt indexes must be consecutive starting from 1")
        statuses = [item["status"] for item in attempts]
        varied = "PASS" in statuses and "FAIL" in statuses
        recovered = statuses[-1] == "PASS" and "FAIL" in statuses[:-1]
        tests.append({
            "nodeid": nodeid,
            "attempt_count": len(attempts),
            "retry_count": max(0, len(attempts) - 1),
            "attempt_statuses": statuses,
            "final_status": statuses[-1],
            "retry_outcome_variation": varied,
            "recovered_failure": recovered,
            "duration_seconds": round(sum(item["duration_seconds"] for item in attempts), 6),
            "workers": sorted({item["worker_id"] for item in attempts}),
        })
    variation_count = sum(item["retry_outcome_variation"] for item in tests)
    recovered_count = sum(item["recovered_failure"] for item in tests)
    final_failures = sum(item["final_status"] == "FAIL" for item in tests)
    return {
        "schema": REPORT_SCHEMA,
        "status": "RETRY_OUTCOME_VARIATION" if variation_count else ("FINAL_FAILURES" if final_failures else "CLEAN"),
        "run_id": shards[0]["run_id"],
        "run_attempt": shards[0]["run_attempt"],
        "commit_sha": shards[0]["commit_sha"],
        "python_version": shards[0]["python_version"],
        "worker_count": len(shards),
        "test_count": len(tests),
        "attempt_count": sum(item["attempt_count"] for item in tests),
        "retry_attempt_count": sum(item["retry_count"] for item in tests),
        "tests_with_retries": sum(item["retry_count"] > 0 for item in tests),
        "tests_with_retry_outcome_variation": variation_count,
        "recovered_failure_count": recovered_count,
        "final_failure_count": final_failures,
        "skip_attempt_count": sum(attempt["status"] == "SKIP" for shard in shards for attempt in shard["attempts"]),
        "tests": tests,
        "generated_at": generated_at,
        "interpretation": "Retry outcome variation is a candidate intermittent result requiring investigation; it is not by itself proof that a test is intrinsically flaky. Retry variation fails this quality gate and is not converted to PASS.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    args.output.unlink(missing_ok=True)
    try:
        payload = summarize_shards(load_shards(args.input_dir))
        exit_code = 1 if payload["status"] != "CLEAN" else 0
    except ValueError as exc:
        payload = {"schema": REPORT_SCHEMA, "status": "BLOCKED", "error": str(exc)}
        exit_code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
