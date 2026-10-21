"""Summarize test-result variation across retained main-branch CI runs.

This is trend telemetry, not retry-aware flaky-test proof: failures across different
commits may reflect code changes, and results are never converted into PASS.
"""
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "saqa.test-stability-history.v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PYTHON_DIR_RE = re.compile(r"^python-(\d+\.\d+)$")
EXPECTED_PYTHON_VERSIONS = ("3.11", "3.12", "3.13")
ERROR_STATUSES = {"FAIL", "ERROR"}


def parse_junit(path: Path) -> dict[str, str]:
    """Return one unambiguous outcome per fully qualified JUnit test ID."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"cannot parse JUnit XML {path}: {exc}") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError(f"unsupported JUnit root element in {path}: {root.tag}")
    outcomes: dict[str, str] = {}
    for case in root.iter("testcase"):
        name = case.get("name", "")
        classname = case.get("classname", "")
        if not name:
            raise ValueError(f"JUnit testcase without name in {path}")
        test_id = f"{classname}::{name}" if classname else name
        if test_id in outcomes:
            raise ValueError(f"duplicate JUnit test ID {test_id!r} in {path}")
        if case.find("failure") is not None:
            status = "FAIL"
        elif case.find("error") is not None:
            status = "ERROR"
        elif case.find("skipped") is not None:
            status = "SKIP"
        else:
            status = "PASS"
        outcomes[test_id] = status
    if not outcomes:
        raise ValueError(f"JUnit report contains no test cases: {path}")
    return outcomes


def _read_run_metadata(path: Path, run_id_from_path: str, python_version: str | None) -> dict[str, str]:
    metadata_path = path / "run-metadata.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"cannot read run metadata {metadata_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"run metadata must be a JSON object: {metadata_path}")
    run_id = payload.get("run_id")
    head_sha = payload.get("head_sha")
    conclusion = payload.get("conclusion")
    event = payload.get("event")
    branch = payload.get("head_branch")
    if not isinstance(run_id, str) or not run_id.isdigit() or run_id != run_id_from_path:
        raise ValueError(f"run metadata ID does not match directory {run_id_from_path}")
    if not isinstance(head_sha, str) or not SHA_RE.fullmatch(head_sha):
        raise ValueError(f"run {run_id}: head_sha must be a full lowercase commit SHA")
    if not isinstance(conclusion, str) or not conclusion.strip():
        raise ValueError(f"run {run_id}: conclusion must be non-empty")
    if event not in {"push", "schedule"} or branch != "main":
        raise ValueError(f"run {run_id}: history is restricted to push/schedule runs on main")
    return {
        "run_id": run_id,
        "head_sha": head_sha,
        "conclusion": conclusion,
        "event": event,
        "head_branch": branch,
        "python_version": python_version or "",
        "created_at": str(payload.get("created_at", "")),
    }


def build_history(input_root: Path, *, min_runs: int = 3, generated_at: datetime | None = None) -> dict[str, Any]:
    if isinstance(min_runs, bool) or not isinstance(min_runs, int) or min_runs < 2:
        raise ValueError("min_runs must be an integer of at least 2")
    if generated_at is not None and (generated_at.tzinfo is None or generated_at.utcoffset() is None):
        raise ValueError("generated_at must be timezone-aware")
    now = generated_at or datetime.now(timezone.utc)
    root = input_root.resolve()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "status": "INSUFFICIENT_HISTORY",
        "minimum_runs_per_python_version": min_runs,
        "input_root": str(input_root),
        "issues": [],
        "artifact_gaps": [],
        "runs": [],
        "cohorts": [],
        "tests": [],
        "summary": {
            "run_count": 0,
            "python_cohort_count": 0,
            "tests_observed": 0,
            "tests_with_cross_commit_variation": 0,
            "tests_with_same_commit_variation": 0,
            "issues_count": 0,
            "artifact_gap_count": 0,
        },
        "notes": [
            "Outcome variation across different commits can indicate a code regression or a changed test, not necessarily flakiness.",
            "Same-commit PASS and FAIL/ERROR across distinct workflow runs is a candidate intermittent result, not retry-rate proof.",
            "This report is advisory telemetry and never changes a failed test or release decision into PASS.",
        ],
    }
    if not root.is_dir():
        report["issues"].append(f"input root does not exist: {input_root}")
        report["summary"]["issues_count"] = len(report["issues"])
        return report

    # Each workflow run downloads artifacts under <run-id>/python-X.Y/.
    # Record expected artifacts independently so missing entire cohorts remain visible.
    run_dirs = sorted(
        path for path in root.iterdir()
        if path.is_dir() and path.name.isdigit() and (path / "run-metadata.json").is_file()
    )
    rejected_run_ids: set[str] = set()
    for run_dir in run_dirs:
        try:
            _read_run_metadata(run_dir, run_dir.name, None)
        except ValueError as exc:
            rejected_run_ids.add(run_dir.name)
            report["issues"].append(str(exc))
            for python_version in EXPECTED_PYTHON_VERSIONS:
                report["artifact_gaps"].append({
                    "run_id": run_dir.name,
                    "python_version": python_version,
                    "expected_artifact": f"saqa-python-{python_version}",
                    "reason": "run metadata invalid; this run/version cannot be included in history",
                })
            continue
        for python_version in EXPECTED_PYTHON_VERSIONS:
            expected_junit = run_dir / f"python-{python_version}" / "junit.xml"
            if not expected_junit.is_file():
                report["artifact_gaps"].append({
                    "run_id": run_dir.name,
                    "python_version": python_version,
                    "expected_artifact": f"saqa-python-{python_version}",
                    "reason": "JUnit file missing or unavailable from retained workflow artifact",
                })

    junit_paths = sorted(root.rglob("junit.xml"))
    if not junit_paths:
        report["issues"].append("no retained JUnit artifacts were found")
        report["summary"]["artifact_gap_count"] = len(report["artifact_gaps"])
        report["summary"]["issues_count"] = len(report["issues"])
        if report["artifact_gaps"]:
            report["status"] = "INCOMPLETE_ARTIFACT_COVERAGE"
        return report

    grouped: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for path in junit_paths:
        try:
            cohort_name = path.parent.name
            match = PYTHON_DIR_RE.fullmatch(cohort_name)
            run_id = path.parents[1].name
            if match is None or not run_id.isdigit():
                report["issues"].append(f"unrecognized JUnit path layout: {path.relative_to(root)}")
                continue
            grouped[(run_id, match.group(1))].append(path)
        except (IndexError, ValueError):
            report["issues"].append(f"unrecognized JUnit path layout: {path}")

    observations: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    distinct_runs: dict[str, set[str]] = defaultdict(set)
    seen_run_versions: set[tuple[str, str]] = set()
    for (run_id, python_version), paths in sorted(grouped.items()):
        if run_id in rejected_run_ids:
            continue
        if len(paths) != 1:
            message = f"run {run_id} Python {python_version}: expected one JUnit report, found {len(paths)}"
            report["issues"].append(message)
            report["artifact_gaps"].append({
                "run_id": run_id, "python_version": python_version,
                "expected_artifact": f"saqa-python-{python_version}", "reason": message,
            })
            continue
        try:
            metadata = _read_run_metadata(root / run_id, run_id, python_version)
            outcomes = parse_junit(paths[0])
        except ValueError as exc:
            message = str(exc)
            if message not in report["issues"]:
                report["issues"].append(message)
            report["artifact_gaps"].append({
                "run_id": run_id, "python_version": python_version,
                "expected_artifact": f"saqa-python-{python_version}",
                "reason": "run metadata or JUnit content invalid; this observation was excluded",
            })
            continue
        key = (run_id, python_version)
        if key in seen_run_versions:
            message = f"duplicate run/version observation: {run_id}/{python_version}"
            report["issues"].append(message)
            report["artifact_gaps"].append({
                "run_id": run_id, "python_version": python_version,
                "expected_artifact": f"saqa-python-{python_version}", "reason": message,
            })
            continue
        seen_run_versions.add(key)
        distinct_runs[python_version].add(run_id)
        report["runs"].append({
            **metadata,
            "test_count": len(outcomes),
            "failed_count": sum(value == "FAIL" for value in outcomes.values()),
            "error_count": sum(value == "ERROR" for value in outcomes.values()),
            "skipped_count": sum(value == "SKIP" for value in outcomes.values()),
            "junit_path": str(paths[0].relative_to(root)),
        })
        for test_id, status in outcomes.items():
            observations[(python_version, test_id)].append({
                "run_id": run_id, "head_sha": metadata["head_sha"],
                "conclusion": metadata["conclusion"], "event": metadata["event"], "status": status,
            })

    for python_version in sorted(set(distinct_runs) | {key[0] for key in observations}):
        runs_for_version = sorted(distinct_runs[python_version])
        report["cohorts"].append({
            "python_version": python_version,
            "run_count": len(runs_for_version),
            "run_ids": runs_for_version,
            "sufficient_history": len(runs_for_version) >= min_runs,
        })

    same_commit_variations = 0
    cross_commit_variations = 0
    for (python_version, test_id), items in sorted(observations.items()):
        statuses = {item["status"] for item in items}
        errors = statuses.intersection(ERROR_STATUSES)
        has_pass = "PASS" in statuses
        cross_variation = has_pass and bool(errors)
        sha_statuses: dict[str, set[str]] = defaultdict(set)
        sha_run_ids: dict[str, set[str]] = defaultdict(set)
        for item in items:
            sha_statuses[item["head_sha"]].add(item["status"])
            sha_run_ids[item["head_sha"]].add(item["run_id"])
        same_sha_inconsistent = any(
            len(sha_run_ids[sha]) >= 2 and "PASS" in sha_statuses[sha]
            and bool(sha_statuses[sha].intersection(ERROR_STATUSES))
            for sha in sha_statuses
        )
        same_commit_variations += int(same_sha_inconsistent)
        cross_commit_variations += int(cross_variation)
        report["tests"].append({
            "python_version": python_version,
            "test_id": test_id,
            "observation_count": len(items),
            "pass_count": sum(item["status"] == "PASS" for item in items),
            "fail_count": sum(item["status"] == "FAIL" for item in items),
            "error_count": sum(item["status"] == "ERROR" for item in items),
            "skip_count": sum(item["status"] == "SKIP" for item in items),
            "cross_commit_outcome_variation": cross_variation,
            "same_commit_outcome_variation": same_sha_inconsistent,
            "observations": sorted(items, key=lambda item: (item["run_id"], item["status"])),
        })

    cohorts_sufficient = bool(report["cohorts"]) and all(item["sufficient_history"] for item in report["cohorts"])
    if same_commit_variations:
        report["status"] = "SAME_COMMIT_OUTCOME_VARIATION"
    elif cross_commit_variations:
        report["status"] = "CROSS_COMMIT_OUTCOME_VARIATION"
    elif report["artifact_gaps"]:
        report["status"] = "INCOMPLETE_ARTIFACT_COVERAGE"
    elif cohorts_sufficient:
        report["status"] = "NO_VARIATION_OBSERVED"
    else:
        report["status"] = "INSUFFICIENT_HISTORY"
    report["summary"] = {
        "run_count": len(report["runs"]),
        "python_cohort_count": len(report["cohorts"]),
        "tests_observed": len(report["tests"]),
        "tests_with_cross_commit_variation": cross_commit_variations,
        "tests_with_same_commit_variation": same_commit_variations,
        "issues_count": len(report["issues"]),
        "artifact_gap_count": len(report["artifact_gaps"]),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-runs", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        report = build_history(args.input_root, min_runs=args.min_runs)
    except ValueError as exc:
        report = {"schema": SCHEMA, "status": "BLOCKED", "error": str(exc)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": report.get("schema", SCHEMA),
        "status": report.get("status", "BLOCKED"),
        "summary": report.get("summary", {}),
        "issues": report.get("issues", []),
    }, indent=2))
    return 2 if report.get("schema") != SCHEMA or report.get("status") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
