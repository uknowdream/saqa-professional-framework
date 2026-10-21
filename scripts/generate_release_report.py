"""Generate a commit-bound release certification report from canonical evidence."""
from __future__ import annotations
import json, os, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from saqa.evidence import verify_manifest

CANONICAL_STATUSES = {"PASS","FAIL","BLOCKED","UNVERIFIED","NOT_APPLICABLE"}
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

def main() -> int:
    manifest = Path(os.getenv("SAQA_MANIFEST","artifacts/evidence-manifest.json"))
    output = Path(os.getenv("SAQA_RELEASE_REPORT","artifacts/release-certification.json"))
    # Never unlink evidence if a misconfigured output path aliases its source manifest.
    if output.resolve() == manifest.resolve():
        raise SystemExit("release report output must differ from the source evidence manifest")
    # A failed regeneration must never leave a previous CERTIFIED report in place.
    output.unlink(missing_ok=True)
    sha = os.getenv("SAQA_TESTED_SHA") or os.getenv("GITHUB_SHA")
    if not isinstance(sha, str) or not _COMMIT_SHA_RE.fullmatch(sha):
        raise SystemExit("tested commit SHA provenance must be a full lowercase 40-character commit SHA")
    if not verify_manifest(manifest):
        raise SystemExit("evidence manifest integrity verification failed")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    raw_records = payload.get("records", [])
    if not isinstance(raw_records, list) or not raw_records:
        raise SystemExit("release certification requires at least one evidence record")
    mismatched = []
    stale = []
    statuses = set()
    source_shas = set()
    try:
        max_age_hours = float(os.getenv("SAQA_MAX_EVIDENCE_AGE_HOURS", "24"))
    except ValueError as exc:
        raise SystemExit("SAQA_MAX_EVIDENCE_AGE_HOURS must be a non-negative number") from exc
    if max_age_hours < 0 or max_age_hours != max_age_hours or max_age_hours in {float("inf"), float("-inf")}:
        raise SystemExit("SAQA_MAX_EVIDENCE_AGE_HOURS must be a finite non-negative number")
    try:
        max_age = timedelta(hours=max_age_hours)
    except OverflowError as exc:
        raise SystemExit("SAQA_MAX_EVIDENCE_AGE_HOURS exceeds the supported datetime range") from exc
    now = datetime.now(timezone.utc)
    for record in raw_records:
        if not isinstance(record, dict):
            mismatched.append("unknown")
            statuses.add("UNVERIFIED")
            continue
        details = record.get("details")
        if not isinstance(details, dict):
            mismatched.append(record.get("test_id","unknown"))
            statuses.add("UNVERIFIED")
            continue
        observed_at = record.get("observed_at")
        try:
            observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00")) if isinstance(observed_at, str) else None
            if observed is None or observed.tzinfo is None:
                raise ValueError("timestamp must include a timezone")
            age = now - observed.astimezone(timezone.utc)
            if age < timedelta(minutes=-5) or age > max_age:
                stale.append(record.get("test_id", "unknown"))
        except (ValueError, OverflowError):
            stale.append(record.get("test_id", "unknown"))
        record_sha = str(details.get("tested_sha",""))
        if record_sha != sha:
            mismatched.append(record.get("test_id","unknown"))
        source_sha = str(details.get("source_sha",""))
        if source_sha:
            source_shas.add(source_sha)
        status = record.get("status")
        statuses.add(status if status in CANONICAL_STATUSES else "UNVERIFIED")
    if mismatched:
        raise SystemExit(f"evidence tested-SHA provenance mismatch: {mismatched}")
    if stale:
        raise SystemExit(f"stale or invalid evidence timestamps (max age {max_age_hours:g} hours): {stale}")
    # A release report is certified only when every included record explicitly PASSes.
    # NOT_APPLICABLE is valid for individual evidence, but cannot satisfy release certification.
    mandatory_ok = bool(raw_records) and statuses == {"PASS"}
    report = {"schema":"saqa.release-certification.v1","commit_sha":sha,"source_shas":sorted(source_shas),"record_count":len(raw_records),"statuses":sorted(statuses),"certified":mandatory_ok,"manifest_verified":True,"evidence_max_age_hours":max_age_hours,"freshness_verified":True}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if mandatory_ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
