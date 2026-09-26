"""Build commit-bound Allure, history, flaky and release-index evidence from canonical records."""
from __future__ import annotations
import hashlib, json, os
from dataclasses import asdict
from pathlib import Path
from saqa.allure import write_allure_results
from saqa.evidence import EvidenceRecord, canonical_json, verify_manifest
from saqa.flaky import analyze_history
from saqa.history import append_history, verify_history
from saqa.result_aggregation import load_results

def load_canonical_records(evidence: Path, manifest: Path) -> list[EvidenceRecord]:
    if not verify_manifest(manifest):
        raise SystemExit("evidence manifest integrity verification failed")
    payload=json.loads(manifest.read_text(encoding="utf-8"))
    expected=payload.get("records")
    if not isinstance(expected,list): raise SystemExit("manifest records must be a list")
    records=load_results(evidence)
    actual=[asdict(r) for r in records]
    if canonical_json(actual) != canonical_json(expected):
        raise SystemExit("observability evidence differs from verified canonical manifest")
    return records

def main() -> int:
    evidence=Path(os.getenv("SAQA_EVIDENCE_DIR","artifacts/evidence"))
    manifest=Path(os.getenv("SAQA_MANIFEST","artifacts/evidence-manifest.json"))
    out=Path(os.getenv("SAQA_OBSERVABILITY_DIR","artifacts/observability"))
    sha=os.getenv("SAQA_TESTED_SHA") or os.getenv("GITHUB_SHA")
    if not sha: raise SystemExit("tested SHA required")
    records=load_canonical_records(evidence,manifest)
    out.mkdir(parents=True,exist_ok=True)
    allure_dir=out/"allure-results"
    write_allure_results(records,allure_dir,commit_sha=sha)
    history=Path(os.getenv("SAQA_HISTORY_PATH",str(out/"quality-history.jsonl")))
    append_history(records,history,commit_sha=sha)
    if not verify_history(history): raise SystemExit("quality history verification failed")
    by_test={}
    for r in records: by_test.setdefault(r.test_id,[]).append(r.status)
    flaky={}
    for test_id,statuses in by_test.items():
        analysis=analyze_history(statuses)
        flaky[test_id]={**analysis.__dict__,"quarantine_recommended":analysis.status=="FLAKY","quarantine_action":"REPORT_ONLY"}
    (out/"flaky-telemetry.json").write_text(json.dumps({"schema":"saqa.flaky-telemetry.v1","commit_sha":sha,"tests":flaky},sort_keys=True,indent=2)+"\n",encoding="utf-8")
    blob=hashlib.sha256(history.read_bytes()).hexdigest()
    index={"schema":"saqa.release-evidence-index.v1","commit_sha":sha,"history_sha256":blob,"allure_result_count":len(list(allure_dir.glob("*-result.json"))),"flaky_test_count":sum(1 for v in flaky.values() if v["status"]=="FLAKY")}
    index["index_sha256"]=hashlib.sha256(canonical_json(index)).hexdigest()
    (out/f"release-index-{sha}.json").write_text(json.dumps(index,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return 0
if __name__=="__main__": raise SystemExit(main())
