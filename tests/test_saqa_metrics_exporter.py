import json
from scripts.saqa_metrics_exporter import collect

def test_exporter_exposes_quality_and_release_metrics(tmp_path, monkeypatch):
    targets=tmp_path/"targets"; targets.mkdir()
    (targets/"a.json").write_text(json.dumps({"test_id":"A","status":"PASS"}))
    report=tmp_path/"release.json"
    report.write_text(json.dumps({"certified":True,"commit_sha":"abc"}))
    flaky=tmp_path/"flaky.json"
    flaky.write_text(json.dumps({"tests":{"A":{"status":"FLAKY"},"B":{"status":"STABLE_PASS"}}}))
    monkeypatch.setenv("SAQA_EVIDENCE_DIR",str(targets))
    monkeypatch.setenv("SAQA_RELEASE_REPORT",str(report))
    monkeypatch.setenv("SAQA_FLAKY_REPORT",str(flaky))
    # module-level paths are resolved at import time, so reload after env setup.
    import importlib
    import scripts.saqa_metrics_exporter as exporter
    exporter.EVIDENCE_DIR=targets
    exporter.RELEASE_REPORT=report
    exporter.FLAKY_REPORT=flaky
    body=exporter.collect()
    assert 'saqa_release_certified{commit_sha="abc"} 1' in body
    assert "saqa_flaky_test_total 1" in body
    assert 'saqa_quality_status{test_id="A",status="PASS"} 1' in body
