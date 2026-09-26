import json
from pathlib import Path
from scripts.generate_release_report import main

def test_release_report_marks_verified_manifest(tmp_path,monkeypatch):
    evidence=tmp_path/"evidence"; evidence.mkdir()
    (evidence/"one.json").write_text(json.dumps({"test_id":"A","status":"PASS","target":"http://127.0.0.1:3000","observed_at":"2026-09-27T00:00:00+00:00","details":{}}))
    from saqa.result_aggregation import aggregate
    manifest=evidence/"evidence-manifest.json"; aggregate(evidence,manifest)
    out=tmp_path/"release.json"
    monkeypatch.setenv("SAQA_MANIFEST",str(manifest)); monkeypatch.setenv("SAQA_RELEASE_REPORT",str(out)); monkeypatch.setenv("GITHUB_SHA","abc")
    assert main()==0
    data=json.loads(out.read_text())
    assert data["certified"] is True
    assert data["commit_sha"]=="abc"
