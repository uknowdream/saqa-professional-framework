#!/usr/bin/env python3
"""Evaluate a deterministic release certification from GitHub Actions evidence.

The gate is intentionally fail-closed: a release can be CERTIFIED only when
all mandatory domains have a verified PASS result. Missing, pending, blocked,
or unknown evidence cannot become PASS.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


MANDATORY = (
    "SAQA CI",
    "SAQA Accessibility",
    "SAQA Mobile Readiness",
)


@dataclass(frozen=True, slots=True)
class Decision:
    status: str
    reason: str


def normalize_runs(raw: object) -> list[dict[str, str]]:
    if isinstance(raw, dict):
        raw = raw.get("workflow_runs", [])
    if not isinstance(raw, list):
        return []
    return [
        {
            "name": str(item.get("name", "")),
            "status": str(item.get("status", "")),
            "conclusion": str(item.get("conclusion") or ""),
            "head_sha": str(item.get("head_sha", "")),
            "run_id": str(item.get("id", "")),
            "url": str(item.get("html_url", "")),
        }
        for item in raw
        if isinstance(item, dict)
    ]


def result(run: dict[str, str] | None) -> str:
    if not run:
        return "UNVERIFIED"
    if run["status"] != "completed":
        return "PENDING"
    if run["conclusion"] == "success":
        return "PASS"
    if run["conclusion"] in {"failure", "timed_out"}:
        return "FAIL"
    if run["conclusion"] in {"cancelled", "action_required", "stale"}:
        return "BLOCKED"
    return "UNVERIFIED"


def decide(results: dict[str, str]) -> Decision:
    if any(value == "FAIL" for value in results.values()):
        return Decision("NOT_CERTIFIED", "A mandatory quality domain failed.")
    if any(value == "BLOCKED" for value in results.values()):
        return Decision("NOT_CERTIFIED", "A mandatory quality domain is blocked.")
    if any(value == "PENDING" for value in results.values()):
        return Decision("NOT_CERTIFIED", "Mandatory evidence is still pending.")
    if any(value != "PASS" for value in results.values()):
        return Decision("NOT_CERTIFIED", "Mandatory evidence is missing or unverified.")
    return Decision("CERTIFIED", "All mandatory quality domains have verified PASS evidence.")


def main() -> int:
    path = Path(os.environ.get("SAQA_RUNS_JSON", ""))
    if not path.exists():
        raise SystemExit("SAQA_RUNS_JSON must point to a GitHub Actions runs JSON file")
    sha = os.environ["SAQA_HEAD_SHA"]
    runs = [r for r in normalize_runs(json.loads(path.read_text(encoding="utf-8"))) if r["head_sha"] == sha]

    latest: dict[str, dict[str, str]] = {}
    for run in runs:
        if run["name"] not in MANDATORY:
            continue
        previous = latest.get(run["name"])
        if previous is None or int(run["run_id"] or 0) > int(previous["run_id"] or 0):
            latest[run["name"]] = run

    results = {name: result(latest.get(name)) for name in MANDATORY}
    decision = decide(results)
    payload = {
        "schema": "saqa.release-certification.v1",
        "head_sha": sha,
        "status": decision.status,
        "reason": decision.reason,
        "mandatory_domains": results,
        "evidence": {name: latest.get(name, {}) for name in MANDATORY},
    }
    output = Path(os.environ.get("SAQA_CERTIFICATION_OUTPUT", "artifacts/release-certification.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if decision.status == "CERTIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
