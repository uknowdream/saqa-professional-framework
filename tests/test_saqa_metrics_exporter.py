from __future__ import annotations

import json
from pathlib import Path

from scripts.saqa_metrics_exporter import collect


def test_collect_exposes_valid_evidence(tmp_path, monkeypatch):
    evidence_dir = tmp_path / "targets"
    evidence_dir.mkdir()
    (evidence_dir / "contract.json").write_text(
        json.dumps({"test_id": "contract", "status": "PASS"}), encoding="utf-8"
    )
    monkeypatch.setattr("scripts.saqa_metrics_exporter.EVIDENCE_DIR", evidence_dir)
    metrics = collect()
    assert 'saqa_quality_status{test_id="contract",status="PASS"} 1\n' in metrics
    assert "saqa_quality_evidence_total 1\n" in metrics


def test_collect_maps_unknown_status_fail_closed_for_telemetry(tmp_path, monkeypatch):
    evidence_dir = tmp_path / "targets"
    evidence_dir.mkdir()
    (evidence_dir / "unknown.json").write_text(
        json.dumps({"test_id": "unknown", "status": "NEW"}), encoding="utf-8"
    )
    monkeypatch.setattr("scripts.saqa_metrics_exporter.EVIDENCE_DIR", evidence_dir)
    metrics = collect()
    assert 'saqa_quality_status{test_id="unknown",status="NEW"} -3\n' in metrics
