#!/usr/bin/env python3
"""Fail-closed release certification from exact, fresh GitHub Actions evidence."""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MANDATORY = (
    "SAQA CI",
    "SAQA Contract Testing",
    "SAQA Accessibility",
    "SAQA Mobile Readiness",
    "SAQA k6 Performance",
)
MANDATORY_WORKFLOW_IDENTITIES = {
    "SAQA CI": (".github/workflows/saqa-ci.yml", "345839221"),
    "SAQA Contract Testing": (".github/workflows/saqa-contract.yml", "364893043"),
    "SAQA Accessibility": (".github/workflows/saqa-accessibility.yml", "355591975"),
    "SAQA Mobile Readiness": (".github/workflows/saqa-mobile.yml", "355328607"),
    "SAQA k6 Performance": (".github/workflows/saqa-k6.yml", "364897799"),
}
ALLOWED_RELEASE_EVENTS = {"push", "workflow_dispatch"}
DEFAULT_MAX_AGE_HOURS = 6.0
FUTURE_SKEW_MINUTES = 5.0


@dataclass(frozen=True, slots=True)
class Decision:
    status: str
    reason: str


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def normalize_runs(raw: object) -> list[dict[str, str]]:
    if isinstance(raw, dict):
        raw = raw.get("workflow_runs", [])
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        normalized.append({
            "name": str(item.get("name", "")),
            "path": str(item.get("path", "")),
            "workflow_id": str(item.get("workflow_id", "")),
            "status": str(item.get("status", "")),
            "conclusion": str(item.get("conclusion") or ""),
            "head_sha": str(item.get("head_sha", "")),
            "head_branch": str(item.get("head_branch", "")),
            "event": str(item.get("event", "")),
            "run_id": str(raw_id) if raw_id is not None else "",
            "run_attempt": str(item.get("run_attempt", "")),
            "created_at": str(item.get("created_at", "")),
            "run_started_at": str(item.get("run_started_at", "")),
            "updated_at": str(item.get("updated_at", "")),
            "url": str(item.get("html_url", "")),
        })
    return normalized


def result(
    run: dict[str, str] | None,
    *,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> str:
    if not run:
        return "UNVERIFIED"
    if run.get("status") != "completed":
        return "PENDING"
    if run.get("conclusion") in {"failure", "timed_out", "startup_failure"}:
        return "FAIL"
    if run.get("conclusion") in {"cancelled", "action_required", "stale"}:
        return "BLOCKED"
    if run.get("conclusion") != "success":
        return "UNVERIFIED"
    max_age_seconds = max_age_hours * 3600
    if (
        not math.isfinite(max_age_hours)
        or max_age_hours <= 0
        or not math.isfinite(max_age_seconds)
        or max_age_seconds > timedelta.max.total_seconds()
    ):
        raise ValueError("max_age_hours must be finite, positive, and representable as a timedelta")
    attempt = run.get("run_attempt", "")
    if not attempt.isdigit() or int(attempt) <= 0:
        return "UNVERIFIED"
    raw_start = run.get("run_started_at", "")
    started = _parse_time(raw_start) if raw_start else _parse_time(run.get("created_at"))
    if started is None:
        return "UNVERIFIED"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include a timezone")
    age = (current.astimezone(timezone.utc) - started).total_seconds()
    if age < -timedelta(minutes=FUTURE_SKEW_MINUTES).total_seconds():
        return "UNVERIFIED"
    if age > max_age_seconds
        return "STALE"
    return "PASS"


def decide(results: dict[str, str]) -> Decision:
    if any(results.get(name) == "FAIL" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "A mandatory quality domain failed.")
    if any(results.get(name) == "BLOCKED" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "A mandatory quality domain is blocked.")
    if any(results.get(name) == "PENDING" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "Mandatory evidence is still pending.")
    if any(results.get(name) == "STALE" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "At least one mandatory workflow run is older than the release freshness limit.")
    if any(results.get(name) != "PASS" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "Mandatory evidence is missing, stale, or unverified.")
    return Decision("CERTIFIED", "All mandatory quality domains have fresh, completed PASS evidence.")


def select_runs(raw: object, sha: str, event: str | None = None) -> list[dict[str, str]]:
    if event is not None and event not in ALLOWED_RELEASE_EVENTS:
        raise ValueError("release event must be push or workflow_dispatch")
    allowed_events = {event} if event else ALLOWED_RELEASE_EVENTS
    return [
        run for run in normalize_runs(raw)
        if run["head_sha"] == sha
        and run["head_branch"] == "main"
        and run["event"] in allowed_events
    ]


def latest_by_workflow(runs: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    seen: dict[tuple[str, int, int], tuple[str, ...]] = {}
    fingerprint_fields = (
        "path", "workflow_id", "status", "conclusion", "head_sha",
        "head_branch", "event", "created_at", "run_started_at",
    )
    for run in runs:
        name = run.get("name", "")
        if name not in MANDATORY:
            continue
        expected_path, expected_workflow_id = MANDATORY_WORKFLOW_IDENTITIES[name]
        if run.get("path") != expected_path:
            raise ValueError(f"workflow path mismatch for mandatory domain: {name}")
        workflow_id = run.get("workflow_id", "")
        if not workflow_id.isdigit() or workflow_id != expected_workflow_id:
            raise ValueError(f"workflow ID mismatch for mandatory domain: {name}")
        run_id_text = run.get("run_id", "")
        attempt_text = run.get("run_attempt", "")
        if not run_id_text.isdigit() or int(run_id_text) <= 0:
            raise ValueError(f"invalid workflow run ID for mandatory domain: {name}")
        if not attempt_text.isdigit() or int(attempt_text) <= 0:
            raise ValueError(f"invalid workflow run attempt for mandatory domain: {name} run_id={run_id_text}")
        run_id, attempt = int(run_id_text), int(attempt_text)
        identity = (name, run_id, attempt)
        fingerprint = tuple(run.get(field, "") for field in fingerprint_fields)
        if identity in seen:
            if seen[identity] != fingerprint:
                raise ValueError(f"conflicting duplicate workflow run identity: {name} run_id={run_id} attempt={attempt}")
            continue
        seen[identity] = fingerprint
        previous = latest.get(name)
        if previous is None or (run_id, attempt) > (int(previous["run_id"]), int(previous["run_attempt"])):
            latest[name] = run
    return latest


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OSError(f"refusing non-regular certification output: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise OSError(f"certification output changed to a non-regular file: {path}")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    path = Path(os.environ.get("SAQA_RUNS_JSON", ""))
    if not path.is_file():
        raise SystemExit("SAQA_RUNS_JSON must point to a GitHub Actions runs JSON file")
    sha = os.environ.get("SAQA_HEAD_SHA", "").strip()
    if len(sha) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in sha):
        raise SystemExit("SAQA_HEAD_SHA must be a full 40-character commit SHA")
    event = os.environ.get("SAQA_REQUIRED_EVENT", "").strip()
    if event and event not in ALLOWED_RELEASE_EVENTS:
        raise SystemExit("SAQA_REQUIRED_EVENT must be push or workflow_dispatch")
    raw_max_age = os.environ.get("SAQA_RELEASE_MAX_AGE_HOURS", str(DEFAULT_MAX_AGE_HOURS))
    policy_error = None
    try:
        max_age = float(raw_max_age)
    except ValueError:
        max_age = DEFAULT_MAX_AGE_HOURS
        policy_error = "SAQA_RELEASE_MAX_AGE_HOURS must be numeric"
    max_age_seconds = max_age * 3600
    if (
        not math.isfinite(max_age)
        or max_age <= 0
        or not math.isfinite(max_age_seconds)
        or max_age_seconds > timedelta.max.total_seconds()
    ):
        max_age = DEFAULT_MAX_AGE_HOURS
        policy_error = "SAQA_RELEASE_MAX_AGE_HOURS must be finite, positive, and representable as a timedelta"
    try:
        if policy_error:
            raise ValueError(policy_error)
        raw = json.loads(path.read_text(encoding="utf-8"))
        runs = select_runs(raw, sha, event or None)
        latest = latest_by_workflow(runs)
        results = {name: result(latest.get(name), max_age_hours=max_age) for name in MANDATORY}
        decision = decide(results)
        selection_error = None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        latest = {}
        results = {name: "UNVERIFIED" for name in MANDATORY}
        decision = Decision("NOT_CERTIFIED", f"Workflow run evidence is invalid: {exc}")
        selection_error = str(exc)
    payload = {
        "schema": "saqa.release-certification.v5",
        "head_sha": sha,
        "required_branch": "main",
        "required_event": event or None,
        "allowed_events": sorted(ALLOWED_RELEASE_EVENTS),
        "max_age_hours": max_age,
        "status": decision.status,
        "reason": decision.reason,
        "selection_error": selection_error,
        "mandatory_domains": results,
        "evidence": {name: latest.get(name, {}) for name in MANDATORY},
    }
    output = Path(os.environ.get("SAQA_CERTIFICATION_OUTPUT", "artifacts/release-certification.json"))
    try:
        _write_report(output, payload)
    except OSError as exc:
        print(f"RELEASE_CERTIFICATION_OUTPUT_FAIL {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if decision.status == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
