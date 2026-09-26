"""Allure-compatible result generation from canonical SAQA evidence."""
from __future__ import annotations
import hashlib, json, os, shutil, tempfile
from datetime import datetime
from pathlib import Path
from .evidence import EvidenceRecord

STATUS_TO_ALLURE = {"PASS":"passed","FAIL":"failed","BLOCKED":"broken","UNVERIFIED":"unknown","NOT_APPLICABLE":"skipped"}

def _epoch_ms(observed_at: str) -> int:
    return int(datetime.fromisoformat(observed_at.replace("Z","+00:00")).timestamp() * 1000)

def write_allure_results(records: list[EvidenceRecord], output_dir: Path, *, commit_sha: str) -> int:
    prepared = []
    for index, record in enumerate(records):
        if record.status not in STATUS_TO_ALLURE:
            raise ValueError(f"unsupported evidence status: {record.status}")
        timestamp = _epoch_ms(record.observed_at)
        uid = hashlib.sha256(f"{commit_sha}:{record.test_id}:{record.observed_at}:{index}".encode()).hexdigest()
        prepared.append((record, uid, timestamp))

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    backup_dir = output_dir.parent / f".{output_dir.name}.backup"
    try:
        for record, uid, timestamp in prepared:
            details_name = f"{uid}-details.json"
            (temp_dir / details_name).write_text(
                json.dumps(record.details, sort_keys=True, indent=2, default=str) + "
",
                encoding="utf-8",
            )
            payload = {
                "uuid": uid,
                "historyId": hashlib.sha256(record.test_id.encode()).hexdigest(),
                "name": record.test_id,
                "fullName": record.test_id,
                "status": STATUS_TO_ALLURE[record.status],
                "statusDetails": {"message": record.status},
                "start": timestamp,
                "stop": timestamp,
                "labels": [{"name":"target","value":record.target},{"name":"commit","value":commit_sha}],
                "parameters": [{"name":"status","value":record.status}],
                "attachments": [{"name":"evidence-details","source":details_name,"type":"application/json"}],
            }
            (temp_dir / f"{uid}-result.json").write_text(
                json.dumps(payload, sort_keys=True, indent=2) + "
", encoding="utf-8"
            )

        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if output_dir.exists():
            os.replace(output_dir, backup_dir)
        try:
            os.replace(temp_dir, output_dir)
        except Exception:
            if backup_dir.exists() and not output_dir.exists():
                os.replace(backup_dir, output_dir)
            raise
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        return len(prepared)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
