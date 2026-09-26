import json
import pytest
from scripts.generate_release_report import main

def _write_manifest(tmp_path, details, status="PASS"):
    evidence = tmp_path/"evidence"
    evidence.mkdir()
    (evidence/"one.json").write_text(json.dumps({"test_id":"A","status":status,"target":"http://127.0.0.1:3000","observed_at":"2026-09-27T00:00:00+00:00","details":details}))
    from saqa.result_aggregation import aggregate
    manifest = evidence/"evidence-manifest.json"
    aggregate(evidence, manifest)
    return manifest

def test_release_report_marks_verified_manifest(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path, {"tested_sha":"abc","source_sha":"source"})
    out = tmp_path/"release.json"
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest)); monkeypatch.setenv("SAQA_RELEASE_REPORT", str(out)); monkeypatch.setenv("SAQA_TESTED_SHA","abc")
    assert main() == 0
    data = json.loads(out.read_text())
    assert data["certified"] is True
    assert data["commit_sha"] == "abc"
    assert data["manifest_verified"] is True
    assert data["source_shas"] == ["source"]

def test_release_report_rejects_mismatched_commit(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path, {"tested_sha":"source-sha"})
    out = tmp_path/"release.json"
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest)); monkeypatch.setenv("SAQA_RELEASE_REPORT", str(out)); monkeypatch.setenv("SAQA_TESTED_SHA","different-sha")
    with pytest.raises(SystemExit, match="tested-SHA provenance mismatch"):
        main()
