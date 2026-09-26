"""Generate a commit-bound release certification report from canonical evidence."""
from __future__ import annotations
import json,os
from pathlib import Path
from saqa.evidence import verify_manifest
from saqa.result_aggregation import load_results

def main()->int:
    manifest=Path(os.getenv("SAQA_MANIFEST","artifacts/evidence-manifest.json"))
    output=Path(os.getenv("SAQA_RELEASE_REPORT","artifacts/release-certification.json"))
    sha=os.getenv("GITHUB_SHA","unknown")
    if not verify_manifest(manifest): raise SystemExit("evidence manifest integrity verification failed")
    records=load_results(manifest.parent,exclude=manifest)
    statuses={r.status for r in records}
    mandatory_ok=not statuses.intersection({"FAIL","BLOCKED","UNVERIFIED"})
    report={"schema":"saqa.release-certification.v1","commit_sha":sha,"record_count":len(records),"statuses":sorted(statuses),"certified":mandatory_ok,"manifest_verified":True}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if mandatory_ok else 1

if __name__=="__main__": raise SystemExit(main())
