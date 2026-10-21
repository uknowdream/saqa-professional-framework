"""Audit required GitHub Actions evidence artifacts for the current main commit."""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = "saqa.artifact-retention-audit.v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_MIN_RETENTION_HOURS = 72.0
MANDATORY = (
    ("SAQA CI", ".github/workflows/saqa-ci.yml", 345839221, "saqa-canonical-evidence"),
    ("SAQA Contract Testing", ".github/workflows/saqa-contract.yml", 364893043, "saqa-contract-evidence"),
    ("SAQA Accessibility", ".github/workflows/saqa-accessibility.yml", 355591975, "saqa-accessibility-canonical-evidence"),
    ("SAQA Mobile Readiness", ".github/workflows/saqa-mobile.yml", 355328607, "saqa-mobile-canonical-evidence"),
    ("SAQA k6 Performance", ".github/workflows/saqa-k6.yml", 364897799, "saqa-k6-evidence"),
)
ALLOWED_EVENTS = {"push", "workflow_dispatch"}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _list_payload(value: Any, key: str, label: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array or object containing {key}")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label} entries must be objects")
    return value


def _run_started(run: dict[str, Any]) -> datetime | None:
    # Fail closed: the attempt start is required to validate attempt-bound artifacts.
    return _parse_time(run.get("run_started_at"))


def _eligible_run(run: dict[str, Any], *, name: str, path: str, workflow_id: int, main_sha: str) -> bool:
    return (
        run.get("name") == name
        and run.get("path") == path
        and run.get("workflow_id") == workflow_id
        and run.get("head_sha") == main_sha
        and run.get("head_branch") == "main"
        and run.get("event") in ALLOWED_EVENTS
    )


def audit_artifacts(
    runs_payload: Any,
    artifacts_payload: Any,
    *,
    main_sha: str,
    now: datetime | None = None,
    min_retention_hours: float = DEFAULT_MIN_RETENTION_HOURS,
) -> dict[str, Any]:
    """Return PASS only if every required domain has fresh, non-empty retained evidence."""
    if not isinstance(main_sha, str) or not SHA_RE.fullmatch(main_sha):
        raise ValueError("main_sha must be a 40-character lowercase commit SHA")
    if isinstance(min_retention_hours, bool) or not isinstance(min_retention_hours, (int, float)):
        raise ValueError("min_retention_hours must be a finite positive number")
    if min_retention_hours <= 0 or not math.isfinite(float(min_retention_hours)):
        raise ValueError("min_retention_hours must be a finite positive number")
    try:
        retention_window = timedelta(hours=float(min_retention_hours))
    except OverflowError as exc:
        raise ValueError("min_retention_hours must fit within a representable timedelta") from exc
    if retention_window.total_seconds() < 1:
        raise ValueError("min_retention_hours must represent at least one second")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include a timezone")
    current = current.astimezone(timezone.utc)
    try:
        earliest_acceptable_expiry = current + retention_window
    except OverflowError as exc:
        raise ValueError("min_retention_hours makes the expiry threshold unrepresentable") from exc
    runs = _list_payload(runs_payload, "workflow_runs", "workflow runs")
    artifacts = _list_payload(artifacts_payload, "artifacts", "artifacts")
    checks = []
    all_passed = True

    for name, path, workflow_id, artifact_name in MANDATORY:
        matches = [
            run for run in runs
            if _eligible_run(run, name=name, path=path, workflow_id=workflow_id, main_sha=main_sha)
        ]
        matches.sort(key=lambda run: (
            int(run.get("id", 0)) if isinstance(run.get("id"), int) and not isinstance(run.get("id"), bool) else 0,
            int(run.get("run_attempt", 0)) if isinstance(run.get("run_attempt"), int) and not isinstance(run.get("run_attempt"), bool) else 0,
        ))
        item: dict[str, Any] = {
            "domain": name, "workflow_path": path, "workflow_id": workflow_id,
            "required_artifact": artifact_name, "status": "FAIL", "reasons": [],
        }
        if not matches:
            item["reasons"].append("no exact-workflow run found for current main commit")
            checks.append(item)
            all_passed = False
            continue

        run = matches[-1]
        run_id = run.get("id")
        attempt = run.get("run_attempt")
        started = _run_started(run)
        item.update({"run_id": run_id, "run_attempt": attempt, "run_url": run.get("html_url")})
        if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
            item["reasons"].append("workflow run ID is invalid")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt <= 0:
            item["reasons"].append("workflow run attempt is invalid")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            item["reasons"].append("latest exact-workflow run is not completed successfully")
        if started is None:
            item["reasons"].append("workflow start timestamp is missing or invalid")
        elif started - current > timedelta(minutes=5):
            item["reasons"].append("workflow start timestamp is unexpectedly in the future")

        domain_artifacts = [
            artifact for artifact in artifacts
            if artifact.get("name") == artifact_name
            and isinstance(artifact.get("workflow_run"), dict)
            and artifact["workflow_run"].get("id") == run_id
        ]
        valid_artifact = None
        for artifact in domain_artifacts:
            reasons = []
            created = _parse_time(artifact.get("created_at"))
            expires = _parse_time(artifact.get("expires_at"))
            size = artifact.get("size_in_bytes")
            if artifact.get("expired") is not False:
                reasons.append("artifact is marked expired or its expiry state is unknown")
            if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
                reasons.append("artifact size is missing, invalid, or empty")
            if created is None:
                reasons.append("artifact created_at is missing or invalid")
            elif started is not None and created < started:
                reasons.append("artifact predates the selected workflow run attempt")
            if expires is None:
                reasons.append("artifact expires_at is missing or invalid")
            elif expires <= earliest_acceptable_expiry:
                reasons.append("artifact expires within the required retention safety window")
            if not reasons:
                valid_artifact = artifact
                break
            item.setdefault("artifact_rejections", []).append({
                "artifact_id": artifact.get("id"), "reasons": reasons,
            })

        if valid_artifact is None:
            if not domain_artifacts:
                item["reasons"].append("required artifact is missing for the selected workflow run")
            else:
                item["reasons"].append("no matching artifact satisfies retention and provenance checks")
        else:
            item["artifact_id"] = valid_artifact.get("id")
            item["artifact_created_at"] = valid_artifact.get("created_at")
            item["artifact_expires_at"] = valid_artifact.get("expires_at")

        if not item["reasons"]:
            item["status"] = "PASS"
        else:
            all_passed = False
        checks.append(item)

    return {
        "schema": SCHEMA,
        "status": "PASS" if all_passed else "FAIL",
        "ready": all_passed,
        "checked_at": current.isoformat(),
        "main_sha": main_sha,
        "minimum_remaining_retention_hours": float(min_retention_hours),
        "mandatory_domain_count": len(MANDATORY),
        "passed_domain_count": sum(item["status"] == "PASS" for item in checks),
        "checks": checks,
        "note": "This audit detects missing/expired/near-expiry evidence for the current main commit; it does not certify test correctness.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-file", required=True, type=Path)
    parser.add_argument("--artifacts-file", required=True, type=Path)
    parser.add_argument("--main-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--min-retention-hours", type=float, default=DEFAULT_MIN_RETENTION_HOURS)
    args = parser.parse_args(argv)
    try:
        runs = json.loads(args.runs_file.read_text(encoding="utf-8"))
        artifacts = json.loads(args.artifacts_file.read_text(encoding="utf-8"))
        result = audit_artifacts(runs, artifacts, main_sha=args.main_sha, min_retention_hours=args.min_retention_hours)
        exit_code = 0 if result["ready"] else 1
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        result = {
            "schema": SCHEMA, "status": "UNVERIFIED", "ready": False,
            "main_sha": args.main_sha, "error": str(exc),
            "note": "Invalid or unavailable Actions metadata must never be treated as retained evidence.",
        }
        exit_code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
