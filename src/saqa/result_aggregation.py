"""Normalize executor outputs into the tamper-evident SAQA evidence model."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence import EvidenceRecord, verify_manifest, write_manifest

REQUIRED = {"test_id", "status", "target"}


def load_results(directory: Path, *, exclude: Path | None = None) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    excluded = exclude.resolve() if exclude is not None else None
    for path in sorted(directory.rglob("*.json")):
        if excluded is not None and path.resolve() == excluded:
            continue
        if path.name in {"evidence-manifest.json", "run-metadata.json"}:
            continue
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("results", [payload])
        else:
            raise ValueError(f"invalid result envelope: {path}")
        if not isinstance(items, list):
            raise ValueError(f"invalid result envelope: {path}")
        for item in items:
            if not isinstance(item, dict) or not REQUIRED.issubset(item):
                raise ValueError(f"result missing required fields: {path}")
            details = item.get("details", {})
            if not isinstance(details, dict):
                raise ValueError(f"result details must be an object: {path}")
            status = str(item["status"])
            if status == "N/A":
                status = "NOT_APPLICABLE"
            observed_at = item.get("observed_at")
            if not isinstance(observed_at, str) or not observed_at.strip() or observed_at == "unknown":
                raise ValueError(f"result missing observed_at: {path}")
            preserved = {
                key: item[key]
                for key in ("schema", "browser", "http_methods", "redirects_followed", "destructive_actions")
                if key in item
            }
            preserved.update(details)
            records.append(EvidenceRecord(
                test_id=str(item["test_id"]),
                status=status,
                observed_at=observed_at,
                target=str(item["target"]),
                details=preserved,
            ))
    if not records:
        raise ValueError(f"no execution results found in {directory}")
    return records


def aggregate(input_dir: Path, output_manifest: Path) -> str:
    records = load_results(input_dir, exclude=output_manifest)
    digest = write_manifest(records, output_manifest)
    if not verify_manifest(output_manifest):
        raise RuntimeError("aggregated evidence manifest failed integrity verification")
    return digest
