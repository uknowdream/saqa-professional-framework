#!/usr/bin/env python3
"""Evaluate a deterministic release certification from GitHub Actions evidence."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

MANDATORY = (
    "SAQA CI",
    "SAQA Contract Testing",
    "SAQA Accessibility",
    "SAQA Mobile Readiness",
    "SAQA k6 Performance",
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
    return [{"name": str(item.get("name","")), "status": str(item.get("status","")),
             "conclusion": str(item.get("conclusion") or ""), "head_sha": str(item.get("head_sha","")),
             "head_branch": str(item.get("head_branch","")), "run_id": str(item.get("id","")),
             "url": str(item.get("html_url",""))}
            for item in raw
            if isinstance(item, dict)
            and str(item.get("id", "")).isdigit()
            and int(item.get("id", 0)) > 0]

def result(run: dict[str, str] | None) -> str:
    if not run: return "UNVERIFIED"
    if run["status"] != "completed": return "PENDING"
    if run["conclusion"] == "success": return "PASS"
    if run["conclusion"] in {"failure","timed_out"}: return "FAIL"
    if run["conclusion"] in {"cancelled","action_required","stale"}: return "BLOCKED"
    return "UNVERIFIED"

def decide(results: dict[str, str]) -> Decision:
    if any(results.get(name) == "FAIL" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "A mandatory quality domain failed.")
    if any(results.get(name) == "BLOCKED" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "A mandatory quality domain is blocked.")
    if any(results.get(name) == "PENDING" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "Mandatory evidence is still pending.")
    if any(results.get(name) != "PASS" for name in MANDATORY):
        return Decision("NOT_CERTIFIED", "Mandatory evidence is missing or unverified.")
    return Decision("CERTIFIED", "All mandatory quality domains have verified PASS evidence.")

def main() -> int:
    path = Path(os.environ.get("SAQA_RUNS_JSON", ""))
    if not path.is_file(): raise SystemExit("SAQA_RUNS_JSON must point to a GitHub Actions runs JSON file")
    sha = os.environ["SAQA_HEAD_SHA"]
    runs = [r for r in normalize_runs(json.loads(path.read_text(encoding="utf-8")))
            if r["head_sha"] == sha and r["head_branch"] == "main"]
    latest: dict[str, dict[str, str]] = {}
    for run in runs:
        if run["name"] not in MANDATORY: continue
        previous = latest.get(run["name"])
        if previous is None or int(run["run_id"] or 0) > int(previous["run_id"] or 0):
            latest[run["name"]] = run
    results = {name: result(latest.get(name)) for name in MANDATORY}
    decision = decide(results)
    payload = {"schema":"saqa.release-certification.v3","head_sha":sha,"required_branch":"main",
               "status":decision.status,"reason":decision.reason,"mandatory_domains":results,
               "evidence":{name:latest.get(name,{}) for name in MANDATORY}}
    output = Path(os.environ.get("SAQA_CERTIFICATION_OUTPUT","artifacts/release-certification.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if decision.status == "CERTIFIED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
