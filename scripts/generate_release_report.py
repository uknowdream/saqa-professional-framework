"""Generate a commit-bound release certification report from canonical evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path

from saqa.evidence import verify_manifest

CANONICAL_STATUSES = {"PASS", "FAIL", "BLOCKED", "UNVERIFIED", "PENDING", "NOT_APPLICABLE"}


def main() -> int:
    manifest = Path(os.getenv("SAQA_MANIFEST", "artifacts/evidence-manifest.json"))
    output = Path(os.getenv("SAQA_RELEASE_REPORT", "artifacts/release-certification.json"))
    sha = os.getenv("SAQA_TESTED_SHA") or os.getenv("GITHUB_SHA")
    if not sha:
        raise SystemExit("tested commit SHA provenance is required")
    if not verify_manifest(manifest):
        raise SystemExit("evidence manifest integrity verification failed")

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    raw_records = payload.get("records", [])
    if not isinstance(raw_records, list) or not raw_records:
        raise SystemExit("release certification requires at least one evidence record")

    mismatched = []
    statuses = set()
    source_shas = set()
    for record in raw_records:
        if not isinstance(record, dict):
            mismatched.append("unknown")
            statuses.add("UNVERIFIED")
            continue
        details = record.get("details")
        if not isinstance(details, dict):
            mismatched.append(record.get("test_id", "unknown"))
            statuses.add("UNVERIFIED")
            continue
        record_sha = str(details.get("tested_sha", ""))
        if record_sha != sha:
            mismatched.append(record.get("test_id", "unknown"))
        source_sha = str(details.get("source_sha", ""))
        if source_sha:
            source_shas.add(source_sha)
        status = record.get("status")
        statuses.add(status if status in CANONICAL_STATUSES else "UNVERIFIED")

    if mismatched:
        raise SystemExit(f"evidence tested-SHA provenance mismatch: {mismatched}")

    mandatory_ok = bool(raw_records) and not statuses.intersection(
        {"FAIL", "BLOCKED", "UNVERIFIED", "PENDING"}
    )
    report = {
        "schema": "saqa.release-certification.v1",
        "commit_sha": sha,
        "source_shas": sorted(source_shas),
        "record_count": len(raw_records),
        "statuses": sorted(statuses),
        "certified": mandatory_ok,
        "manifest_verified": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
