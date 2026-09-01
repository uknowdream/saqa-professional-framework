"""Generate a deterministic CI evidence envelope for a SAQA run."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .evidence import EvidenceRecord, utc_now, verify_manifest, write_manifest


def generate(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = os.getenv("GITHUB_RUN_ID", "local")
    sha = os.getenv("GITHUB_SHA", "unknown")
    ref = os.getenv("GITHUB_REF", "unknown")

    record = EvidenceRecord(
        test_id="CI-BOOTSTRAP",
        status="PASS",
        observed_at=utc_now(),
        target="saqa-framework",
        details={"run_id": run_id, "sha": sha, "ref": ref},
    )
    manifest = output_dir / "evidence-manifest.json"
    digest = write_manifest([record], manifest)
    if not verify_manifest(manifest):
        raise RuntimeError("freshly generated evidence manifest failed integrity verification")

    envelope = {
        "schema_version": "1.0",
        "run_id": run_id,
        "commit_sha": sha,
        "ref": ref,
        "manifest_sha256": digest,
        "integrity_verified": True,
    }
    (output_dir / "run-metadata.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    generate(Path(os.getenv("SAQA_EVIDENCE_DIR", "artifacts/evidence")))
    print("SAQA evidence integrity: PASS")
