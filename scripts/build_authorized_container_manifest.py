"""Bind authorized-container security outputs to immutable target and workflow-run provenance."""
from __future__ import annotations
import argparse, hashlib, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from scripts.validate_container_image_ref import validate_image_ref

SCHEMA = "saqa.authorized-container-security-manifest.v1"
REQUIRED_FILES = (
    "image-ref.txt", "resolved-repo-digests.json", "application-container.spdx.json",
    "application-container-sbom-validation.json", "trivy-version.txt",
    "application-container-trivy.json", "application-container-trivy-summary.json",
    "application-container-security-policy-result.json",
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"cannot read JSON evidence {path.name}: {exc}") from exc


def build_manifest(artifact_dir: Path, policy_path: Path, *, image_ref: str,
                   scanner_version: str, source_sha: str, run_id: str,
                   run_attempt: str, event: str, ref: str, workflow_ref: str,
                   workflow_sha: str) -> dict[str, Any]:
    image_ref = validate_image_ref(image_ref)
    for label, value in (("source_sha", source_sha), ("workflow_sha", workflow_sha)):
        if not isinstance(value, str) or not SHA1.fullmatch(value):
            raise ValueError(f"{label} must be a full lowercase commit SHA")
    for label, value in (("run_id", run_id), ("run_attempt", run_attempt)):
        if not isinstance(value, str) or not value.isdigit() or int(value) <= 0:
            raise ValueError(f"{label} must be a positive integer string")
    for label, value in (("event", event), ("ref", ref), ("workflow_ref", workflow_ref), ("scanner_version", scanner_version)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a non-empty string")
    root = artifact_dir.resolve()
    if not root.is_dir():
        raise ValueError("security artifact directory does not exist")
    records = []
    for name in REQUIRED_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"required security evidence is missing, empty, or not a regular file: {name}")
        records.append({"name": name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    by_name = {item["name"]: item for item in records}
    if (root / "image-ref.txt").read_text(encoding="utf-8").strip() != image_ref:
        raise ValueError("image-ref.txt does not match requested immutable target")
    resolved = _json(root / "resolved-repo-digests.json")
    if not isinstance(resolved, list) or image_ref not in resolved:
        raise ValueError("resolved repository digests do not contain exact requested image reference")
    version_text = (root / "trivy-version.txt").read_text(encoding="utf-8")
    if f"Version: {scanner_version}" not in version_text:
        raise ValueError("Trivy runtime version does not match expected version")
    sbom_validation = _json(root / "application-container-sbom-validation.json")
    if not isinstance(sbom_validation, dict) or sbom_validation.get("status") != "PASS":
        raise ValueError("SPDX SBOM validation did not PASS")
    if sbom_validation.get("sha256") != by_name["application-container.spdx.json"]["sha256"]:
        raise ValueError("SBOM validation does not bind exact SBOM bytes")
    summary = _json(root / "application-container-trivy-summary.json")
    raw_report_sha = by_name["application-container-trivy.json"]["sha256"]
    if not isinstance(summary, dict) or summary.get("schema") != "saqa.container-security-summary.v1":
        raise ValueError("normalized Trivy summary schema is invalid")
    if summary.get("image") != image_ref or summary.get("scanned_artifact_name") != image_ref:
        raise ValueError("normalized summary image identity does not match scanned image")
    if summary.get("source_report_sha256") != raw_report_sha:
        raise ValueError("normalized summary is not bound to the raw Trivy report digest")
    if summary.get("scanner") != f"trivy-{scanner_version}":
        raise ValueError("normalized summary scanner version mismatch")
    if not isinstance(summary.get("findings"), list) or summary.get("finding_count") != len(summary["findings"]):
        raise ValueError("normalized summary findings/count are invalid")
    policy = _json(policy_path)
    policy_result = _json(root / "application-container-security-policy-result.json")
    if not isinstance(policy_result, dict) or policy_result.get("schema") != "saqa.container-security-policy-result.v1":
        raise ValueError("container security policy result schema is invalid")
    if policy_result.get("policy_id") != policy.get("policy_id") or policy_result.get("policy_version") != policy.get("version"):
        raise ValueError("policy result does not match checked-in policy identity")
    if policy_result.get("image") != image_ref or policy_result.get("scanned_artifact_name") != image_ref:
        raise ValueError("policy result image identity mismatch")
    if policy_result.get("source_report_sha256") != raw_report_sha:
        raise ValueError("policy result does not bind raw Trivy report digest")
    if policy_result.get("release_gate_eligible") is not True or policy_result.get("enforcement_mode") != "blocking":
        raise ValueError("application image scan must use blocking, release-eligible policy mode")
    if policy_result.get("status") not in {"PASS", "FAIL"}:
        raise ValueError("application security decision must be PASS or FAIL")
    if not isinstance(policy.get("version"), int) or isinstance(policy.get("version"), bool) or policy["version"] < 1:
        raise ValueError("checked-in security policy version is invalid")
    return {
        "schema": SCHEMA, "status": "VERIFIED", "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": os.getenv("GITHUB_REPOSITORY", ""), "source_commit_sha": source_sha,
        "event": event, "ref": ref, "run_id": int(run_id), "run_attempt": int(run_attempt),
        "workflow_ref": workflow_ref, "workflow_sha": workflow_sha, "image": image_ref,
        "scanner": f"trivy-{scanner_version}", "policy_id": policy["policy_id"], "policy_version": policy["version"],
        "policy_sha256": sha256_file(policy_path), "raw_trivy_report_sha256": raw_report_sha,
        "sbom_sha256": by_name["application-container.spdx.json"]["sha256"],
        "policy_status": policy_result["status"], "release_gate_eligible": policy_result["status"] == "PASS",
        "files": records,
        "interpretation": "Evidence integrity and workflow provenance only; PASS applies to this configured scan policy and does not prove overall security.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--scanner-version", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--workflow-ref", required=True)
    parser.add_argument("--workflow-sha", required=True)
    args = parser.parse_args(argv)
    if args.output.resolve() in {(args.artifact_dir / name).resolve() for name in REQUIRED_FILES}:
        print(json.dumps({"schema": SCHEMA, "status": "UNVERIFIED", "error": "manifest output must not overwrite an input artifact"}, indent=2))
        return 2
    try:
        payload = build_manifest(args.artifact_dir, args.policy, image_ref=args.image_ref,
                                 scanner_version=args.scanner_version, source_sha=args.source_sha,
                                 run_id=args.run_id, run_attempt=args.run_attempt, event=args.event,
                                 ref=args.ref, workflow_ref=args.workflow_ref, workflow_sha=args.workflow_sha)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError, TypeError, KeyError) as exc:
        payload = {"schema": SCHEMA, "status": "UNVERIFIED", "release_gate_eligible": False,
                   "error": str(exc), "note": "Security evidence identity/integrity could not be verified."}
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError as write_exc:
            payload["output_write_error"] = str(write_exc)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "UNVERIFIED", "error": str(exc), "release_gate_eligible": False}, indent=2))
        return 2
    print(json.dumps({"status": payload["status"], "policy_status": payload["policy_status"], "release_gate_eligible": payload["release_gate_eligible"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
