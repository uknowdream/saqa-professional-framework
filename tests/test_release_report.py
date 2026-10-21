import hashlib
import json
from datetime import datetime, timezone, timedelta
import pytest
from scripts.generate_release_report import main
from saqa.evidence import canonical_json, utc_now

def _write_manifest(tmp_path, details, status="PASS"):
    evidence = tmp_path/"evidence"
    evidence.mkdir()
    (evidence/"one.json").write_text(json.dumps({"test_id":"A","status":status,"target":"http://127.0.0.1:3000","observed_at":utc_now(),"details":details}))
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

def test_release_report_rejects_non_object_details(tmp_path, monkeypatch):
    records = [{"test_id":"A","status":"PASS","target":"http://127.0.0.1:3000","observed_at":"2026-09-27T00:00:00+00:00","details":"not-an-object"}]
    manifest = tmp_path/"manifest.json"
    manifest.write_text(json.dumps({"records":records,"sha256":hashlib.sha256(canonical_json(records)).hexdigest()}))
    out = tmp_path/"release.json"
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest)); monkeypatch.setenv("SAQA_RELEASE_REPORT", str(out)); monkeypatch.setenv("SAQA_TESTED_SHA","abc")
    with pytest.raises(SystemExit, match="evidence manifest integrity verification failed"):
        main()

def test_release_report_fails_ci_when_certification_is_not_clean(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path, {"tested_sha":"abc"}, status="FAIL")
    out = tmp_path/"release.json"
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest)); monkeypatch.setenv("SAQA_RELEASE_REPORT", str(out)); monkeypatch.setenv("SAQA_TESTED_SHA","abc")
    assert main() == 1
    data = json.loads(out.read_text())
    assert data["certified"] is False


@pytest.mark.parametrize("status", ["NOT_APPLICABLE", "UNVERIFIED", "BLOCKED"])
def test_release_report_does_not_certify_non_pass_evidence(tmp_path, monkeypatch, status):
    manifest = _write_manifest(tmp_path, {"tested_sha": "abc"}, status=status)
    out = tmp_path / "release.json"
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest))
    monkeypatch.setenv("SAQA_RELEASE_REPORT", str(out))
    monkeypatch.setenv("SAQA_TESTED_SHA", "abc")
    assert main() == 1
    data = json.loads(out.read_text())
    assert data["certified"] is False


def test_release_report_does_not_certify_mixed_pass_and_not_applicable(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "pass.json").write_text(json.dumps({"test_id":"A","status":"PASS","target":"local","observed_at":utc_now(),"details":{"tested_sha":"abc"}}))
    (evidence / "na.json").write_text(json.dumps({"test_id":"B","status":"NOT_APPLICABLE","target":"local","observed_at":utc_now(),"details":{"tested_sha":"abc"}}))
    from saqa.result_aggregation import aggregate
    manifest = evidence / "evidence-manifest.json"
    aggregate(evidence, manifest)
    out = tmp_path / "release.json"
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest))
    monkeypatch.setenv("SAQA_RELEASE_REPORT", str(out))
    monkeypatch.setenv("SAQA_TESTED_SHA", "abc")
    assert main() == 1
    assert json.loads(out.read_text())["certified"] is False


def test_release_report_rejects_stale_evidence(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path, {"tested_sha": "abc"})
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    from saqa.evidence import canonical_json
    payload["records"][0]["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    payload["sha256"] = __import__("hashlib").sha256(canonical_json(payload["records"])).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest))
    monkeypatch.setenv("SAQA_RELEASE_REPORT", str(tmp_path / "release.json"))
    monkeypatch.setenv("SAQA_TESTED_SHA", "abc")
    with pytest.raises(SystemExit, match="stale or invalid evidence timestamps"):
        main()


def test_release_report_rejects_timestamp_without_timezone(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path, {"tested_sha": "abc"})
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["records"][0]["observed_at"] = "2026-10-20T00:00:00"
    payload["sha256"] = __import__("hashlib").sha256(canonical_json(payload["records"])).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest))
    monkeypatch.setenv("SAQA_RELEASE_REPORT", str(tmp_path / "release.json"))
    monkeypatch.setenv("SAQA_TESTED_SHA", "abc")
    with pytest.raises(SystemExit, match="stale or invalid evidence timestamps"):
        main()


def test_release_report_exposes_freshness_policy(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path, {"tested_sha": "abc"})
    out = tmp_path / "release.json"
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest))
    monkeypatch.setenv("SAQA_RELEASE_REPORT", str(out))
    monkeypatch.setenv("SAQA_TESTED_SHA", "abc")
    monkeypatch.setenv("SAQA_MAX_EVIDENCE_AGE_HOURS", "48")
    assert main() == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["freshness_verified"] is True
    assert report["evidence_max_age_hours"] == 48


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "not-a-number"])
def test_release_report_rejects_invalid_freshness_policy(tmp_path, monkeypatch, value):
    manifest = _write_manifest(tmp_path, {"tested_sha": "abc"})
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest))
    monkeypatch.setenv("SAQA_RELEASE_REPORT", str(tmp_path / "release.json"))
    monkeypatch.setenv("SAQA_TESTED_SHA", "abc")
    monkeypatch.setenv("SAQA_MAX_EVIDENCE_AGE_HOURS", value)
    with pytest.raises(SystemExit, match="SAQA_MAX_EVIDENCE_AGE_HOURS"):
        main()


def test_release_report_rejects_far_future_evidence(tmp_path, monkeypatch):
    manifest = _write_manifest(tmp_path, {"tested_sha": "abc"})
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["records"][0]["observed_at"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    payload["sha256"] = hashlib.sha256(canonical_json(payload["records"])).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest))
    monkeypatch.setenv("SAQA_RELEASE_REPORT", str(tmp_path / "release.json"))
    monkeypatch.setenv("SAQA_TESTED_SHA", "abc")
    with pytest.raises(SystemExit, match="stale or invalid evidence timestamps"):
        main()


def test_failed_regeneration_removes_stale_certified_report(tmp_path, monkeypatch):
    manifest = tmp_path / "broken-manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")
    out = tmp_path / "release.json"
    out.write_text(json.dumps({"certified": True, "commit_sha": "old"}), encoding="utf-8")
    monkeypatch.setenv("SAQA_MANIFEST", str(manifest))
    monkeypatch.setenv("SAQA_RELEASE_REPORT", str(out))
    monkeypatch.setenv("SAQA_TESTED_SHA", "new")
    with pytest.raises(SystemExit, match="evidence manifest integrity verification failed"):
        main()
    assert not out.exists()
