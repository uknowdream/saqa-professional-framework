import json

from saqa.ci_evidence import generate
from saqa.evidence import verify_manifest


def test_ci_evidence_is_integrity_verified(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_SHA", "abc")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/test")

    manifest = generate(tmp_path)

    assert manifest.exists()
    assert verify_manifest(manifest)
    metadata = json.loads((tmp_path / "run-metadata.json").read_text())
    assert metadata["integrity_verified"] is True
    assert metadata["manifest_sha256"]
