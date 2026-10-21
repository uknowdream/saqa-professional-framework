from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/qa-release-certification.yml"


def test_release_certification_attests_only_successful_certification() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    assert "name: Attest certified release decision provenance" in workflow
    assert "if: success()" in workflow
    assert "subject-path: artifacts/release-certification.json" in workflow
    assert "name: Independently verify release decision attestation" in workflow
    assert "jq -r '.status' artifacts/release-certification.json" in workflow
    assert "gh attestation verify artifacts/release-certification.json --repo" in workflow


def test_release_attestation_privileges_are_only_on_certify_job() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    top_level = workflow.split("concurrency:", 1)[0]
    readiness = workflow.split("  readiness:", 1)[1].split("  certify:", 1)[0]
    certify = workflow.split("  certify:", 1)[1]
    assert "id-token: write" not in top_level
    assert "attestations: write" not in top_level
    assert "id-token: write" not in readiness
    assert "attestations: write" not in readiness
    assert "id-token: write" in certify
    assert "attestations: write" in certify
    assert "signer-workflow" in certify
