"""Normalize executor outputs into the tamper-evident SAQA evidence model."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence import EvidenceRecord, verify_manifest, write_manifest

REQUIRED = {"test_id", "status", "target"}


def load_results(directory: Path) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for path in sorted(directory.glob("*.json")):
        if path.name in {"evidence-manifest.json", "run-metadata.json"}:
            continue
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else payload.get("results", [payload])
        if not isinstance(items, list):
            raise ValueError(f"invalid result envelope: {path}")
        for item in items:
            if not isinstance(item, dict) or not REQUIRED.issubset(item):
                raise ValueError(f"result missing required fields: {path}")
            records.append(EvidenceRecord(
                test_id=str(item["test_id"]),
                status=str(item["status"]),
                observed_at=str(item.get("observed_at", "unknown")),
                target=str(item["target"]),
                details=dict(item.get("details", {})),
            ))
    if not records:
        raise ValueError(f"no execution results found in {directory}")
    return records


def aggregate(input_dir: Path, output_manifest: Path) -> str:
    records = load_results(input_dir)
    digest = write_manifest(records, output_manifest)
    if not verify_manifest(output_manifest):
        raise RuntimeError("aggregated evidence manifest failed integrity verification")
    return digest
