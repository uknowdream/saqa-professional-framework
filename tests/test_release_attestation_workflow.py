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
