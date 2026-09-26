"""Generate a commit-bound release certification report from canonical evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path

from saqa.evidence import verify_manifest


def main() -> int:
    manifest = Path(os.getenv("SAQA_MANIFEST", "artifacts/evidence-manifest.json"))
    output = Path(os.getenv("SAQA_RELEASE_REPORT", "artifacts/release-certification.json"))
    sha = os.getenv("SAQA_GIT_SHA") or os.getenv("GITHUB_SHA")
    if not sha:
        raise SystemExit("commit SHA provenance is required")

    if not verify_manifest(manifest):
        raise SystemExit("evidence manifest integrity verification failed")

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    raw_records = payload.get("records", [])
    mismatched = []
    for record in raw_records:
        record_sha = str(record.get("details", {}).get("commit", ""))
        if record_sha != sha:
            mismatched.append(record.get("test_id", "unknown"))
    if mismatched:
        raise SystemExit(f"evidence commit provenance mismatch: {mismatched}")

    statuses = {str(r.get("status")) for r in raw_records}
    mandatory_ok = not statuses.intersection({"FAIL", "BLOCKED", "UNVERIFIED"})
    report = {
        "schema": "saqa.release-certification.v1",
        "commit_sha": sha,
        "record_count": len(raw_records),
        "statuses": sorted(statuses),
        "certified": mandatory_ok,
        "manifest_verified": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if mandatory_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
