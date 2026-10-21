import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_container_security_manifest import REQUIRED_FILES, SCHEMA, build_manifest, main


IMAGE = "bkimminich/juice-shop@sha256:8739101ade29358abb5469ee66ae78e582c97ed0a5543a4ad102e5fa5193526b"
SCANNER = "0.76.0"
SHA = "a" * 40
RUN = "12345"


def make_artifacts(root: Path):
    root.mkdir(parents=True)
    raw_report = json.dumps({"ArtifactName": IMAGE, "Results": []}, separators=(",", ":")).encode()
    (root / "juice-shop-trivy.json").write_bytes(raw_report)
    sbom = {
        "spdxVersion": "SPDX-2.3", "SPDXID": "SPDXRef-DOCUMENT", "name": "juice-shop",
        "documentNamespace": "https://example.invalid/spdx/juice-shop",
        "creationInfo": {"creators": ["Tool: Syft"]},
        "packages": [{"SPDXID": "SPDXRef-Package-1", "name": "demo"}],
    }
    sbom_raw = json.dumps(sbom, separators=(",", ":")).encode()
    (root / "juice-shop-sbom.spdx.json").write_bytes(sbom_raw)
    sbom_sha = hashlib.sha256(sbom_raw).hexdigest()
    (root / "juice-shop-sbom-validation.json").write_text(json.dumps({
        "schema": "saqa.sbom-validation.v1", "status": "PASS", "sha256": sbom_sha, "package_count": 1,
    }), encoding="utf-8")
    (root / "trivy-version.txt").write_text(f"Version: {SCANNER}\n", encoding="utf-8")
    (root / "training-image-ref.txt").write_text(IMAGE + "\n", encoding="utf-8")
    raw_sha = hashlib.sha256(raw_report).hexdigest()
    summary = {
        "schema": "saqa.container-security-summary.v1", "image": IMAGE,
        "scanned_artifact_name": IMAGE, "scanner": f"trivy-{SCANNER}",
        "source_report_sha256": raw_sha, "finding_count": 0, "findings": [],
        "by_severity": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0},
    }
    (root / "juice-shop-trivy-summary.json").write_text(json.dumps(summary), encoding="utf-8")
    policy = {
        "schema": "saqa.container-security-policy-result.v1", "image": IMAGE,
        "scanned_artifact_name": IMAGE, "source_report_sha256": raw_sha,
        "status": "REPORT_ONLY", "release_gate_eligible": False,
    }
    (root / "juice-shop-security-policy-result.json").write_text(json.dumps(policy), encoding="utf-8")


def build(root):
    return build_manifest(
        root, image=IMAGE, scanner_version=SCANNER, source_sha=SHA, execution_sha=SHA,
        event="pull_request", ref="refs/pull/16/merge", run_id=RUN, run_attempt="1",
        workflow_ref="owner/repo/.github/workflows/saqa-container-security.yml@refs/pull/16/merge",
        workflow_sha=SHA,
    )


def test_manifest_binds_required_artifact_hashes_and_run_provenance(tmp_path):
    root = tmp_path / "security"
    make_artifacts(root)
    result = build(root)
    assert result["schema"] == SCHEMA
    assert result["status"] == "PASS"
    assert result["execution_commit_sha"] == SHA
    assert result["run_id"] == int(RUN)
    assert {item["name"] for item in result["files"]} == set(REQUIRED_FILES)
    assert result["raw_trivy_report_sha256"] == hashlib.sha256((root / "juice-shop-trivy.json").read_bytes()).hexdigest()


def test_manifest_fails_if_raw_report_is_changed_after_summary(tmp_path):
    root = tmp_path / "security"
    make_artifacts(root)
    with (root / "juice-shop-trivy.json").open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="does not bind the exact raw Trivy report digest"):
        build(root)


@pytest.mark.parametrize("field", ["image", "scanned_artifact_name", "source_report_sha256", "finding_count", "findings"])
def test_manifest_rejects_summary_inconsistency(tmp_path, field):
    root = tmp_path / "security"
    make_artifacts(root)
    path = root / "juice-shop-trivy-summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary[field] = "spoofed" if field in {"image", "scanned_artifact_name", "source_report_sha256"} else (True if field == "finding_count" else {})
    path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises((ValueError, TypeError), match="summary|image|source|findings|finding_count"):
        build(root)


def test_manifest_rejects_sbom_digest_mismatch(tmp_path):
    root = tmp_path / "security"
    make_artifacts(root)
    (root / "juice-shop-sbom.spdx.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SBOM validation digest"):
        build(root)


@pytest.mark.parametrize(("status", "eligible"), [("PASS", True), ("REPORT_ONLY", True), ("BLOCKED", False)])
def test_manifest_requires_explicit_non_release_eligible_training_policy(tmp_path, status, eligible):
    root = tmp_path / "security"
    make_artifacts(root)
    path = root / "juice-shop-security-policy-result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result.update({"status": status, "release_gate_eligible": eligible})
    path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="REPORT_ONLY|release-gate eligible"):
        build(root)


def test_manifest_requires_expected_scanner_version_and_all_files(tmp_path):
    root = tmp_path / "security"
    make_artifacts(root)
    (root / "trivy-version.txt").write_text("Version: 0.75.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="version file"):
        build(root)
    (root / "trivy-version.txt").write_text(f"Version: {SCANNER}\n", encoding="utf-8")
    (root / "juice-shop-trivy.json").unlink()
    with pytest.raises(ValueError, match="missing or not a regular file"):
        build(root)


def test_manifest_rejects_symlink_artifact(tmp_path):
    root = tmp_path / "security"
    make_artifacts(root)
    original = root / "juice-shop-trivy.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(ValueError, match="missing or not a regular file"):
        build(root)


@pytest.mark.parametrize("field,value", [
    ("source_sha", "bad"), ("execution_sha", "A" * 40), ("workflow_sha", "bad"),
    ("run_id", "0"), ("run_attempt", "-1"),
])
def test_manifest_rejects_invalid_run_metadata(tmp_path, field, value):
    root = tmp_path / "security"
    make_artifacts(root)
    args = {
        "image": IMAGE, "scanner_version": SCANNER, "source_sha": SHA, "execution_sha": SHA,
        "event": "pull_request", "ref": "refs/pull/16/merge", "run_id": RUN, "run_attempt": "1",
        "workflow_ref": "owner/repo/.github/workflows/saqa-container-security.yml@refs/pull/16/merge",
        "workflow_sha": SHA,
    }
    args[field] = value
    with pytest.raises(ValueError):
        build_manifest(root, **args)


def test_manifest_requires_complete_nonempty_artifact_set(tmp_path):
    with pytest.raises(ValueError, match="directory does not exist"):
        build(tmp_path / "missing")
    root = tmp_path / "security"
    make_artifacts(root)
    (root / "trivy-version.txt").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        build(root)



def test_manifest_cli_can_write_manifest_inside_uploaded_artifact_directory(tmp_path, capsys):
    root = tmp_path / "security"
    make_artifacts(root)
    output = root / "juice-shop-security-artifact-manifest.json"
    status = main([
        "--artifact-dir", str(root),
        "--output", str(output),
        "--image", IMAGE,
        "--scanner-version", SCANNER,
        "--source-sha", SHA,
        "--execution-sha", SHA,
        "--event", "pull_request",
        "--ref", "refs/pull/16/merge",
        "--run-id", RUN,
        "--run-attempt", "1",
        "--workflow-ref", "owner/repo/.github/workflows/saqa-container-security.yml@refs/pull/16/merge",
        "--workflow-sha", SHA,
    ])
    assert status == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert len(result["files"]) == len(REQUIRED_FILES)
    assert output.name not in {item["name"] for item in result["files"]}
