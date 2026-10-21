from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/saqa-container-security.yml"


def test_container_security_uses_verified_immutable_image_and_scanner_digests():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "bkimminich/juice-shop@sha256:8739101ade29358abb5469ee66ae78e582c97ed0a5543a4ad102e5fa5193526b" in workflow
    assert "aquasec/trivy@sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222" in workflow
    assert "docker pull \"$TRAINING_IMAGE\"" in workflow
    assert '--image-src remote' in workflow
    assert "--image-config-scanners misconfig,secret" in workflow


def test_scanner_does_not_receive_docker_socket_or_root_equivalent_host_access():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "/var/run/docker.sock" not in workflow
    assert "anchore/syft:v1.30.0 \"registry:docker.io/$TRAINING_IMAGE\"" in workflow


def test_source_bound_manifest_is_built_after_policy_and_before_upload():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    policy_step = workflow.index("Record expected findings for intentionally vulnerable training image")
    manifest_step = workflow.index("Build source-bound container security artifact manifest")
    upload_step = workflow.index("Upload container security evidence")
    assert policy_step < manifest_step < upload_step
    assert "--source-sha \"$SOURCE_SHA\"" in workflow
    assert "--execution-sha \"$EXECUTION_SHA\"" in workflow
    assert "--workflow-sha \"$WORKFLOW_SHA\"" in workflow
    assert "juice-shop-security-artifact-manifest.json" in workflow


def test_manifest_is_required_in_uploaded_evidence_and_digest_is_explicit():
    manifest = (ROOT / "scripts/build_container_security_manifest.py").read_text(encoding="utf-8")
    assert '"training-image-ref.txt"' in manifest
    assert 'recorded_image != image or "@sha256:" not in recorded_image' in manifest
    assert '"juice-shop-trivy-summary.json"' in manifest
    assert '"juice-shop-security-policy-result.json"' in manifest


def test_security_sbom_and_manifest_are_attested_only_from_trusted_main_job():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    attest_job = workflow.split("  attest-reference-sbom:", 1)[1]
    assert "if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'" in attest_job
    assert "needs: scan-reference-image" in attest_job
    assert "id-token: write" in attest_job
    assert "attestations: write" in attest_job
    assert "subject-path: artifacts/security/juice-shop-sbom.spdx.json" in attest_job
    assert "subject-path: artifacts/security/juice-shop-security-artifact-manifest.json" in attest_job
    assert "juice-shop-security-artifact-manifest.json --repo" in attest_job
    assert "--signer-workflow" in attest_job
