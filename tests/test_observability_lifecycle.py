from __future__ import annotations
import json
from pathlib import Path
from scripts.generate_qe_observability import main as build_observability
from scripts.generate_commit_dashboard import main as build_dashboard

def test_observability_lifecycle_is_commit_bound(tmp_path, monkeypatch):
    evidence=tmp_path/"evidence"; evidence.mkdir()
    record={"test_id":"A","status":"PASS","observed_at":"2026-09-27T00:00:00+00:00","target":"http://127.0.0.1:3000","details":{"tested_sha":"abc","source_sha":"abc"}}
    (evidence/"one.json").write_text(json.dumps(record))
    from saqa.result_aggregation import aggregate
    manifest=evidence/"evidence-manifest.json"; aggregate(evidence,manifest)
    out=tmp_path/"obs"; monkeypatch.setenv("SAQA_EVIDENCE_DIR",str(evidence)); monkeypatch.setenv("SAQA_MANIFEST",str(manifest)); monkeypatch.setenv("SAQA_OBSERVABILITY_DIR",str(out)); monkeypatch.setenv("SAQA_TESTED_SHA","abc"); monkeypatch.setenv("SAQA_HISTORY_PATH",str(out/"quality-history.jsonl"))
    assert build_observability()==0
    assert (out/"quality-history.jsonl").exists()
    assert list((out/"allure-results").glob("*-result.json"))
    telemetry=json.loads((out/"flaky-telemetry.json").read_text()); assert telemetry["commit_sha"]=="abc"
    assert telemetry["tests"]["A"]["quarantine_action"]=="REPORT_ONLY"
    index=list(out.glob("release-index-*.json"))[0]; assert json.loads(index.read_text())["commit_sha"]=="abc"
    report=tmp_path/"release.json"; report.write_text(json.dumps({"commit_sha":"abc","certified":True,"statuses":["PASS"],"record_count":1}))
    dash=tmp_path/"dashboard.json"; monkeypatch.setenv("SAQA_RELEASE_REPORT",str(report)); monkeypatch.setenv("SAQA_FLAKY_REPORT",str(out/"flaky-telemetry.json")); monkeypatch.setenv("SAQA_DASHBOARD_REPORT",str(dash))
    assert build_dashboard()==0; assert json.loads(dash.read_text())["certified"] is True
