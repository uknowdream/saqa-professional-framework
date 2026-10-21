"""Create a source-bound SHA-256 manifest for the container security scan artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "saqa.container-security-artifact-manifest.v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_FILES = (
    "juice-shop-sbom.spdx.json",
    "juice-shop-sbom-validation.json",
    "trivy-version.txt",
    "juice-shop-trivy.json",
    "juice-shop-trivy-summary.json",
    "juice-shop-security-policy-result.json",
    "training-image-ref.txt",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def build_manifest(
    artifact_dir: Path,
    *,
    image: str,
    scanner_version: str,
    source_sha: str,
    execution_sha: str,
    event: str,
    ref: str,
    run_id: str,
    run_attempt: str,
    workflow_ref: str,
    workflow_sha: str,
) -> dict[str, Any]:
    image = _nonempty(image, "image")
    scanner_version = _nonempty(scanner_version, "scanner_version")
    if not COMMIT_SHA.fullmatch(source_sha):
        raise ValueError("source_sha must be a full lowercase commit SHA")
    if not COMMIT_SHA.fullmatch(execution_sha):
        raise ValueError("execution_sha must be a full lowercase commit SHA")
    if not COMMIT_SHA.fullmatch(workflow_sha):
        raise ValueError("workflow_sha must be a full lowercase commit SHA")
    for name, value in (("event", event), ("ref", ref), ("workflow_ref", workflow_ref)):
        _nonempty(value, name)
    if not isinstance(run_id, str) or not run_id.isdigit() or int(run_id) <= 0:
        raise ValueError("run_id must be a positive integer string")
    if not isinstance(run_attempt, str) or not run_attempt.isdigit() or int(run_attempt) <= 0:
        raise ValueError("run_attempt must be a positive integer string")

    if not artifact_dir.is_dir():
        raise ValueError(f"security artifact directory does not exist: {artifact_dir}")
    root = artifact_dir.resolve()
    records = []
    for name in REQUIRED_FILES:
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"required security artifact is missing or not a regular file: {name}")
        size = path.stat().st_size
        if size <= 0:
            raise ValueError(f"required security artifact is empty: {name}")
        raw_sha = sha256_file(path)
        records.append({"name": name, "size_bytes": size, "sha256": raw_sha})

    by_name = {item["name"]: item for item in records}
    recorded_image = (root / "training-image-ref.txt").read_text(encoding="utf-8").strip()
    if recorded_image != image or "@sha256:" not in recorded_image:
        raise ValueError("training-image-ref.txt must record the exact immutable image digest")
    summary = json.loads((root / "juice-shop-trivy-summary.json").read_text(encoding="utf-8"))
    raw_report_sha = by_name["juice-shop-trivy.json"]["sha256"]
    if not isinstance(summary, dict) or summary.get("schema") != "saqa.container-security-summary.v1":
        raise ValueError("normalized Trivy summary schema is invalid")
    if summary.get("image") != image or summary.get("scanned_artifact_name") != image:
        raise ValueError("normalized summary image does not match requested scanned image")
    if summary.get("source_report_sha256") != raw_report_sha:
        raise ValueError("normalized summary does not bind the exact raw Trivy report digest")
    if summary.get("scanner") != f"trivy-{scanner_version}":
        raise ValueError("normalized summary scanner version does not match the invoked Trivy version")
    findings = summary.get("findings")
    if not isinstance(findings, list):
        raise ValueError("normalized summary findings must be an array")
    if isinstance(summary.get("finding_count"), bool) or not isinstance(summary.get("finding_count"), int) or summary["finding_count"] < 0:
        raise ValueError("normalized summary finding_count is invalid")
    if summary["finding_count"] != len(findings):
        raise ValueError("normalized summary finding_count does not match findings")
    version_text = (root / "trivy-version.txt").read_text(encoding="utf-8")
    if f"Version: {scanner_version}" not in version_text:
        raise ValueError("recorded Trivy version file does not match the expected version")

    sbom_result = json.loads((root / "juice-shop-sbom-validation.json").read_text(encoding="utf-8"))
    if not isinstance(sbom_result, dict) or sbom_result.get("status") != "PASS":
        raise ValueError("SPDX SBOM structural validation must PASS before provenance manifest creation")
    if sbom_result.get("sha256") != by_name["juice-shop-sbom.spdx.json"]["sha256"]:
        raise ValueError("SBOM validation digest does not match the actual SBOM file")

    policy_result = json.loads((root / "juice-shop-security-policy-result.json").read_text(encoding="utf-8"))
    if not isinstance(policy_result, dict) or policy_result.get("status") != "REPORT_ONLY":
        raise ValueError("pinned training-image policy result must explicitly remain REPORT_ONLY")
    if policy_result.get("release_gate_eligible") is not False:
        raise ValueError("intentionally vulnerable training-image findings must not be release-gate eligible")
    if policy_result.get("source_report_sha256") != raw_report_sha:
        raise ValueError("policy result is not bound to the raw Trivy report digest")
    if policy_result.get("image") != image or policy_result.get("scanned_artifact_name") != image:
        raise ValueError("policy result image identity does not match the requested image")

    return {
        "schema": SCHEMA,
        "status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": os.getenv("GITHUB_REPOSITORY", ""),
        "source_commit_sha": source_sha,
        "execution_commit_sha": execution_sha,
        "event": event,
        "ref": ref,
        "run_id": int(run_id),
        "run_attempt": int(run_attempt),
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "image": image,
        "scanner": f"trivy-{scanner_version}",
        "raw_trivy_report_sha256": raw_report_sha,
        "sbom_sha256": by_name["juice-shop-sbom.spdx.json"]["sha256"],
        "normalized_summary_sha256": by_name["juice-shop-trivy-summary.json"]["sha256"],
        "policy_result_sha256": by_name["juice-shop-security-policy-result.json"]["sha256"],
        "files": records,
        "interpretation": "Byte-integrity and workflow provenance metadata only; not a vulnerability-free or production-security claim.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--scanner-version", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--execution-sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    args = parser.parse_args(argv)
    protected_inputs = {(args.artifact_dir / name).resolve() for name in REQUIRED_FILES}
    if args.output.resolve() in protected_inputs:
        print(json.dumps({
            "schema": SCHEMA, "status": "UNVERIFIED",
            "error": "manifest output must not overwrite a required source artifact",
        }, indent=2))
        return 2
    try:
        manifest = build_manifest(
            args.artifact_dir,
            image=args.image,
            scanner_version=args.scanner_version,
            source_sha=args.source_sha,
            execution_sha=args.execution_sha,
            event=args.event,
            ref=args.ref,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            workflow_ref=args.workflow_ref,
            workflow_sha=args.workflow_sha,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError, TypeError, KeyError) as exc:
        fallback = {
            "schema": SCHEMA, "status": "UNVERIFIED", "release_gate_eligible": False,
            "error": str(exc),
            "note": "Security artifact identity or integrity could not be verified; this is not a PASS result.",
        }
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(fallback, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError as write_exc:
            fallback["output_write_error"] = str(write_exc)
        print(json.dumps(fallback, indent=2, sort_keys=True))
        return 2
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(json.dumps({
            "schema": SCHEMA, "status": "UNVERIFIED", "release_gate_eligible": False,
            "error": f"could not persist security manifest: {exc}",
        }, indent=2))
        return 2
    print(json.dumps({"status": manifest["status"], "file_count": len(manifest["files"]),
                      "raw_trivy_report_sha256": manifest["raw_trivy_report_sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
