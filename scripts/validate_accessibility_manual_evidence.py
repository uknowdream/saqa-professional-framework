"""Validate human-executed keyboard and screen-reader accessibility evidence."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = "saqa.accessibility-manual-evidence.v1"
SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
STATUSES = {"PASS", "FAIL", "BLOCKED", "UNVERIFIED", "N/A"}
KEYBOARD_IDS = {f"KBD-{index:02d}" for index in range(1, 9)}
SCREEN_READER_IDS = {f"SR-{index:02d}" for index in range(1, 7)}
REQUIRED_TEST_IDS = KEYBOARD_IDS | SCREEN_READER_IDS
FUTURE_SKEW = timedelta(minutes=5)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > datetime.now(timezone.utc) + FUTURE_SKEW:
        raise ValueError(f"{field} must not be in the future beyond the five-minute clock-skew allowance")
    return parsed


def _evidence_refs(value: Any, field: str, *, required: bool) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or (required and not value):
        raise ValueError(f"{field} must be a non-empty array of evidence references" if required else f"{field} must be an array")
    refs = []
    for index, ref in enumerate(value):
        text = _text(ref, f"{field}[{index}]")
        if text.lower() in {"todo", "tbd", "example", "not available", "none"}:
            raise ValueError(f"{field}[{index}] cannot be a placeholder")
        refs.append(text)
    if len(refs) != len(set(refs)):
        raise ValueError(f"{field} contains duplicate references")
    return refs


def validate_manual_accessibility_evidence(payload: Any) -> dict[str, Any]:
    """Validate every required manual test; never infer PASS for missing evidence."""
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("unsupported manual accessibility evidence schema")
    target = payload.get("target")
    if not isinstance(target, dict):
        raise ValueError("target must be an object")
    target_url = _text(target.get("url"), "target.url")
    build = _text(target.get("build"), "target.build")
    commit_sha = _text(target.get("commit_sha"), "target.commit_sha")
    if not SHA_RE.fullmatch(commit_sha):
        raise ValueError("target.commit_sha must be a 40- or 64-character lowercase hexadecimal SHA")
    tester = _text(payload.get("tester"), "tester")
    run_id = _text(payload.get("run_id"), "run_id")
    recorded_at = _timestamp(payload.get("recorded_at"), "recorded_at")

    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("records must be a non-empty array")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_records):
        field = f"records[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{field} must be an object")
        test_id = _text(raw.get("test_id"), f"{field}.test_id")
        if test_id not in REQUIRED_TEST_IDS:
            raise ValueError(f"{field}.test_id is not in the required manual test matrix: {test_id}")
        if test_id in seen:
            raise ValueError(f"duplicate manual accessibility test ID: {test_id}")
        seen.add(test_id)
        status = raw.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError(f"{field}.status is invalid")
        tested_at = _timestamp(raw.get("tested_at"), f"{field}.tested_at")
        environment = raw.get("environment")
        if not isinstance(environment, dict):
            raise ValueError(f"{field}.environment must be an object")
        env = {key: _text(environment.get(key), f"{field}.environment.{key}")
               for key in ("platform", "os_version", "browser", "browser_version", "viewport",
                           "assistive_technology", "assistive_technology_version")}
        if test_id in SCREEN_READER_IDS and any(
            env[key].strip().lower() in {"none", "n/a", "not used", "not applicable", "unknown"}
            for key in ("assistive_technology", "assistive_technology_version")
        ):
            raise ValueError(f"{field} is a screen-reader test and requires the actual assistive technology and version")

        refs = _evidence_refs(raw.get("evidence_refs"), f"{field}.evidence_refs",
                              required=status in {"PASS", "FAIL"})
        record: dict[str, Any] = {
            "test_id": test_id,
            "status": status,
            "tested_at": tested_at.isoformat(),
            "environment": env,
            "evidence_refs": refs,
        }
        if status in {"PASS", "FAIL"}:
            record["steps_summary"] = _text(raw.get("steps_summary"), f"{field}.steps_summary")
            record["expected"] = _text(raw.get("expected"), f"{field}.expected")
            record["actual"] = _text(raw.get("actual"), f"{field}.actual")
        elif status in {"BLOCKED", "UNVERIFIED"}:
            record["reason"] = _text(raw.get("reason"), f"{field}.reason")
        elif status == "N/A":
            record["na_reason"] = _text(raw.get("na_reason"), f"{field}.na_reason")
            record["reviewer"] = _text(raw.get("reviewer"), f"{field}.reviewer")
        if "defect_id" in raw:
            record["defect_id"] = _text(raw.get("defect_id"), f"{field}.defect_id")
        records.append(record)

    missing = sorted(REQUIRED_TEST_IDS - seen)
    if missing:
        raise ValueError(f"manual accessibility matrix is incomplete; missing: {', '.join(missing)}")
    counts = Counter(record["status"] for record in records)
    if counts["FAIL"]:
        status = "FAIL"
    elif any(counts[key] for key in ("BLOCKED", "UNVERIFIED")):
        status = "UNVERIFIED"
    else:
        status = "PASS"
    return {
        "schema": SCHEMA,
        "status": status,
        "target": {"url": target_url, "build": build, "commit_sha": commit_sha},
        "tester": tester,
        "run_id": run_id,
        "recorded_at": recorded_at.isoformat(),
        "test_count": len(records),
        "status_counts": {key: counts.get(key, 0) for key in sorted(STATUSES)},
        "records": sorted(records, key=lambda record: record["test_id"]),
        "evidence_contract_only": True,
        "note": "This validates reported manual results; it cannot execute a screen reader, authenticate evidence references, or prove WCAG conformance by itself.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.input.resolve() == args.output.resolve():
        print(json.dumps({"schema": SCHEMA, "status": "UNVERIFIED",
                          "error": "input and output must be different files"}, indent=2))
        return 2
    args.output.unlink(missing_ok=True)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = validate_manual_accessibility_evidence(payload)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "UNVERIFIED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"status": result["status"], "test_count": result["test_count"],
                      "status_counts": result["status_counts"]}, indent=2))
    return 1 if result["status"] == "FAIL" else (0 if result["status"] == "PASS" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
