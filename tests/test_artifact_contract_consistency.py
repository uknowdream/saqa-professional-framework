import re
from pathlib import Path

from scripts.audit_artifact_retention import MANDATORY


ROOT = Path(__file__).resolve().parents[1]
PRODUCERS = {
    ".github/workflows/saqa-ci.yml",
    ".github/workflows/saqa-contract.yml",
    ".github/workflows/saqa-accessibility.yml",
    ".github/workflows/saqa-mobile.yml",
    ".github/workflows/saqa-k6.yml",
}


def test_mandatory_retention_artifacts_match_their_producer_upload_names():
    assert {path for _, path, _, _ in MANDATORY} == PRODUCERS
    for workflow_name, workflow_path, _, artifact_name in MANDATORY:
        source = (ROOT / workflow_path).read_text(encoding="utf-8")
        pattern = rf"(?m)^\s+name:\s*{re.escape(artifact_name)}\s*$"
        assert re.search(pattern, source), (
            f"{workflow_name} producer no longer uploads the required artifact {artifact_name!r}"
        )


def test_release_readiness_table_matches_the_retention_audit_contract():
    release_workflow = (ROOT / ".github/workflows/qa-release-certification.yml").read_text(encoding="utf-8")
    for workflow_name, workflow_path, workflow_id, artifact_name in MANDATORY:
        row = f"{workflow_name}|{workflow_path}|{workflow_id}|{artifact_name}"
        assert row in release_workflow, f"release readiness contract drifted: {row}"


def test_readiness_requires_attempt_bound_artifact_and_retention_window():
    source = (ROOT / ".github/workflows/qa-release-certification.yml").read_text(encoding="utf-8")
    assert "(.run_started_at | (try fromdateiso8601 catch 0))" in source
    assert "(.created_at | (try fromdateiso8601 catch 0)) >= $started" in source
    assert "(.expires_at | (try fromdateiso8601 catch 0)) > $retention_floor" in source
    assert "GitHub failed to return artifact metadata" in source
