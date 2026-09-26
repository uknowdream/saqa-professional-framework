"""Generate a static commit certification dashboard payload from release evidence."""
from __future__ import annotations
import json, os
from pathlib import Path

def main() -> int:
    report=Path(os.getenv("SAQA_RELEASE_REPORT","artifacts/release-certification.json"))
    telemetry=Path(os.getenv("SAQA_FLAKY_REPORT","artifacts/observability/flaky-telemetry.json"))
    out=Path(os.getenv("SAQA_DASHBOARD_REPORT","artifacts/observability/commit-dashboard.json"))
    release=json.loads(report.read_text(encoding="utf-8"))
    flaky=json.loads(telemetry.read_text(encoding="utf-8"))
    dashboard={
        "schema":"saqa.commit-dashboard.v1",
        "commit_sha":release["commit_sha"],
        "certified":release["certified"],
        "statuses":release["statuses"],
        "record_count":release["record_count"],
        "flaky_tests":[k for k,v in flaky["tests"].items() if v["status"]=="FLAKY"],
        "history_source":"artifacts/observability/quality-history.jsonl",
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dashboard,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
