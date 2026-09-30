from __future__ import annotations
import json
from scripts.saqa_metrics_exporter import collect, _escape_label

def test_collect_exposes_valid_evidence(tmp_path, monkeypatch):
    evidence_dir=tmp_path/"targets"; evidence_dir.mkdir()
    (evidence_dir/"contract.json").write_text(json.dumps({"test_id":"contract","status":"PASS"}))
    monkeypatch.setattr("scripts.saqa_metrics_exporter.EVIDENCE_DIR",evidence_dir)
    metrics=collect(); assert 'saqa_quality_status{test_id="contract",status="PASS"} 1\n' in metrics; assert "saqa_quality_evidence_total 1\n" in metrics

def test_collect_maps_unknown_status_fail_closed_for_telemetry(tmp_path, monkeypatch):
    evidence_dir=tmp_path/"targets"; evidence_dir.mkdir()
    (evidence_dir/"unknown.json").write_text(json.dumps({"test_id":"unknown","status":"NEW"}))
    monkeypatch.setattr("scripts.saqa_metrics_exporter.EVIDENCE_DIR",evidence_dir)
    assert 'saqa_quality_status{test_id="unknown",status="NEW"} -3\n' in collect()

def test_collect_ignores_non_object_json(tmp_path, monkeypatch):
    evidence_dir=tmp_path/"targets"; evidence_dir.mkdir()
    (evidence_dir/"list.json").write_text("[1,2,3]")
    monkeypatch.setattr("scripts.saqa_metrics_exporter.EVIDENCE_DIR",evidence_dir)
    assert "saqa_quality_evidence_total 0\n" in collect()

def test_collect_escapes_prometheus_label_values(tmp_path, monkeypatch):
    evidence_dir=tmp_path/"targets"; evidence_dir.mkdir()
    raw_test_id='a"b\\c\nd'; raw_status='PASS\nd"'
    (evidence_dir/"escaped.json").write_text(json.dumps({"test_id":raw_test_id,"status":raw_status}))
    monkeypatch.setattr("scripts.saqa_metrics_exporter.EVIDENCE_DIR",evidence_dir)
    expected='saqa_quality_status{test_id="a\\"b\\\\c\\nd",status="PASS\\nD\\""} -3\n'
    assert expected in collect()

def test_collect_exposes_commit_certification_and_flaky_metrics(tmp_path, monkeypatch):
    evidence_dir=tmp_path/"targets"; evidence_dir.mkdir()
    report=tmp_path/"release.json"; report.write_text(json.dumps({"status":"CERTIFIED","commit_sha":"abc"}))
    flaky=tmp_path/"flaky.json"; flaky.write_text(json.dumps({"tests":{"A":{"status":"FLAKY"},"B":{"status":"STABLE_PASS"}}}))
    monkeypatch.setattr("scripts.saqa_metrics_exporter.EVIDENCE_DIR",evidence_dir); monkeypatch.setattr("scripts.saqa_metrics_exporter.RELEASE_REPORT",report); monkeypatch.setattr("scripts.saqa_metrics_exporter.FLAKY_REPORT",flaky)
    metrics=collect()
    assert 'saqa_release_certified{commit_sha="abc"} 1\n' in metrics
    assert "saqa_flaky_test_total 1\n" in metrics
    assert 'saqa_release_report_info{reported="true"} 1\n' in metrics
    assert 'saqa_flaky_report_info{reported="true"} 1\n' in metrics

def test_collect_fail_closed_when_release_report_is_not_object(tmp_path, monkeypatch):
    report=tmp_path/"release.json"; report.write_text("[]"); monkeypatch.setattr("scripts.saqa_metrics_exporter.RELEASE_REPORT",report)
    metrics=collect()
    assert 'saqa_release_report_info{reported="false"} 1\n' in metrics

def test_collect_marks_missing_flaky_report(tmp_path, monkeypatch):
    missing=tmp_path/"missing.json"; monkeypatch.setattr("scripts.saqa_metrics_exporter.FLAKY_REPORT",missing)
    assert 'saqa_flaky_report_info{reported="false"} 1\n' in collect()
