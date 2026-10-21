"""Summarize JUnit quality signals and validate an expiring test-quarantine registry."""
from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "saqa.test-quarantine-policy.v1"
REPORT_SCHEMA = "saqa.test-quality-report.v1"
STATUSES = {"failure", "error", "skipped"}


def validate_quarantine_policy(policy: Any, *, today: date | None = None) -> dict[str, Any]:
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        raise ValueError("unsupported test quarantine policy schema")
    version = policy.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("quarantine policy version must be a positive integer")
    entries = policy.get("quarantines")
    if not isinstance(entries, list):
        raise ValueError("quarantines must be an array")
    today = today or datetime.now(timezone.utc).date()
    seen: set[str] = set()
    for i, item in enumerate(entries):
        required = {"test_id", "owner", "reason", "ticket", "expires_on"}
        if not isinstance(item, dict) or not required.issubset(item):
            raise ValueError(f"quarantines[{i}] missing required fields")
        for field in required:
            if not isinstance(item[field], str) or not item[field].strip():
                raise ValueError(f"quarantines[{i}].{field} must be a non-empty string")
        test_id = item["test_id"]
        if test_id in seen:
            raise ValueError(f"duplicate quarantine entry for {test_id}")
        seen.add(test_id)
        try:
            expiry = date.fromisoformat(item["expires_on"])
        except ValueError as exc:
            raise ValueError(f"quarantines[{i}].expires_on must be an ISO-8601 date") from exc
        if expiry <= today:
            raise ValueError(f"quarantines[{i}] expired or expires today: {test_id}")
    return {"version": version, "quarantines": entries}


def summarize_junit(xml_path: Path, policy: Any, *, today: date | None = None,
                    generated_at: datetime | None = None, slow_test_limit: int = 10) -> dict[str, Any]:
    validated = validate_quarantine_policy(policy, today=today)
    if isinstance(slow_test_limit, bool) or not isinstance(slow_test_limit, int) or slow_test_limit < 1:
        raise ValueError("slow_test_limit must be a positive integer")
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"cannot parse JUnit XML: {exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if root.tag not in {"testsuite", "testsuites"} or not suites:
        raise ValueError("JUnit XML must contain testsuite data")
    cases = []
    for suite in suites:
        for case in suite.findall("testcase"):
            classname = case.get("classname", "")
            name = case.get("name", "")
            if not name:
                raise ValueError("JUnit testcase missing name")
            try:
                duration = float(case.get("time", "0"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"JUnit testcase {name} has invalid duration") from exc
            if not math.isfinite(duration) or duration < 0:
                raise ValueError(f"JUnit testcase {name} duration must be finite and non-negative")
            outcome = "PASS"
            if case.find("failure") is not None:
                outcome = "FAIL"
            elif case.find("error") is not None:
                outcome = "ERROR"
            elif case.find("skipped") is not None:
                outcome = "SKIP"
            nodeid = f"{classname}::{name}" if classname else name
            cases.append({"test_id": nodeid, "name": name, "classname": classname, "duration_seconds": duration, "status": outcome})
    if not cases:
        raise ValueError("JUnit report contains no test cases")
    quarantines = {item["test_id"]: item for item in validated["quarantines"]}
    known_ids = {case["test_id"] for case in cases}
    stale = sorted(set(quarantines) - known_ids)
    expired_or_unknown = []
    for case in cases:
        case["quarantined"] = case["test_id"] in quarantines
        if case["quarantined"] and case["status"] in {"FAIL", "ERROR"}:
            expired_or_unknown.append(case["test_id"])
    failures = sum(case["status"] in {"FAIL", "ERROR"} for case in cases)
    skipped = sum(case["status"] == "SKIP" for case in cases)
    total_duration = sum(case["duration_seconds"] for case in cases)
    now = generated_at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": now.astimezone(timezone.utc).isoformat(),
        "source": str(xml_path),
        "quarantine_policy_version": validated["version"],
        "test_count": len(cases),
        "failure_count": failures,
        "skipped_count": skipped,
        "pass_count": len(cases) - failures - skipped,
        "failure_rate": failures / len(cases),
        "skipped_rate": skipped / len(cases),
        "total_test_duration_seconds": round(total_duration, 3),
        "slowest_tests": sorted(cases, key=lambda case: case["duration_seconds"], reverse=True)[:slow_test_limit],
        "quarantine_count": len(quarantines),
        "stale_quarantine_ids": stale,
        "quarantined_failures": sorted(expired_or_unknown),
        "status": "FAIL" if failures or stale or expired_or_unknown else "PASS",
        "notes": [
            "JUnit alone cannot reliably measure retry rate or historical flakiness; those require retry-aware runner events and cross-run history.",
            "A quarantined test failure remains visible and is not converted to PASS.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.resolve() in {args.junit.resolve(), args.policy.resolve()}:
        print(json.dumps({
            "schema": REPORT_SCHEMA, "status": "BLOCKED",
            "error": "quality report output must differ from JUnit and policy inputs",
        }, indent=2))
        return 2
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        report = summarize_junit(args.junit, policy)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        report = {
            "schema": REPORT_SCHEMA, "status": "BLOCKED",
            "error": str(exc),
            "note": "Malformed or unavailable input is not a PASS; inspect and regenerate evidence.",
        }
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError:
            pass
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(json.dumps({
            "schema": REPORT_SCHEMA, "status": "BLOCKED",
            "error": f"could not write quality report: {exc}",
        }, indent=2))
        return 2
    print(json.dumps({key: report[key] for key in ("status", "test_count", "failure_count", "skipped_count", "failure_rate", "total_test_duration_seconds", "quarantine_count")}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
