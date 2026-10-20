import json
from pathlib import Path

import pytest

from saqa.result_aggregation import aggregate, load_results
from saqa.evidence import verify_manifest


def test_aggregate_multiple_executor_results(tmp_path: Path) -> None:
    (tmp_path / "api.json").write_text(
        '{"results":[{"test_id":"API-001","status":"PASS","target":"local-api","observed_at":"2026-09-10T00:00:00Z","details":{"status_code":200}}]}',
        encoding="utf-8",
    )
    (tmp_path / "web.json").write_text(
        '{"test_id":"WEB-001","status":"FAIL","target":"juice-shop","observed_at":"2026-09-10T00:00:01Z","details":{"browser":"chromium"}}',
        encoding="utf-8",
    )
    records = load_results(tmp_path)
    assert [r.test_id for r in records] == ["API-001", "WEB-001"]
    manifest = tmp_path / "manifest.json"
    digest = aggregate(tmp_path, manifest)
    assert len(digest) == 64
    assert verify_manifest(manifest)
    digest_again = aggregate(tmp_path, manifest)
    assert digest_again == digest
    assert [r.test_id for r in load_results(tmp_path, exclude=manifest)] == ["API-001", "WEB-001"]


def test_aggregate_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no execution results"):
        aggregate(tmp_path, tmp_path.parent / "empty-manifest.json")


def test_aggregate_rejects_invalid_result(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text('{"status":"PASS"}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        load_results(tmp_path)


def test_aggregate_rejects_scalar_json(tmp_path: Path) -> None:
    (tmp_path / "scalar.json").write_text("null", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid result envelope"):
        load_results(tmp_path)

@pytest.mark.parametrize("observed_at", ["unknown", " UNKNOWN ", "   "])
def test_aggregate_rejects_invalid_observed_at_variants(tmp_path: Path, observed_at: str) -> None:
    (tmp_path / "bad.json").write_text(
        '{"test_id":"T-001","status":"PASS","target":"local","observed_at":%s,"details":{}}'
        % json.dumps(observed_at),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing observed_at"):
        load_results(tmp_path)


def test_aggregate_preserves_top_level_provenance_when_nested_value_is_null(tmp_path: Path) -> None:
    (tmp_path / "provenance.json").write_text(
        json.dumps({
            "test_id": "API-PROV-001",
            "status": "PASS",
            "target": "local-api",
            "observed_at": "2026-10-20T00:00:00Z",
            "provenance": {"run_id": "123", "commit_sha": "abc123"},
            "details": {"provenance": None, "status_code": 200},
        }),
        encoding="utf-8",
    )
    records = load_results(tmp_path)
    assert records[0].details["provenance"] == {"run_id": "123", "commit_sha": "abc123"}
    assert records[0].details["status_code"] == 200


def test_verify_manifest_returns_false_for_malformed_json_and_wrong_root(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not-json", encoding="utf-8")
    assert verify_manifest(malformed) is False

    wrong_root = tmp_path / "wrong-root.json"
    wrong_root.write_text("[]", encoding="utf-8")
    assert verify_manifest(wrong_root) is False


def test_verify_manifest_rejects_tampered_records(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text(
        json.dumps({"test_id": "T-001", "status": "PASS", "target": "local",
                    "observed_at": "2026-10-20T00:00:00Z", "details": {"count": 1}}),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    aggregate(tmp_path, manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["records"][0]["details"]["count"] = 2
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_manifest(manifest) is False


def test_verify_manifest_rejects_invalid_record_even_with_matching_digest(tmp_path: Path) -> None:
    import hashlib
    from saqa.evidence import canonical_json

    records = [{"test_id": "T-001", "status": ["PASS"], "observed_at": "now",
                "target": "local", "details": {}}]
    digest = hashlib.sha256(canonical_json(records)).hexdigest()
    manifest = tmp_path / "invalid-record.json"
    manifest.write_text(json.dumps({"records": records, "sha256": digest}), encoding="utf-8")
    assert verify_manifest(manifest) is False


def test_verify_manifest_rejects_malformed_digest(tmp_path: Path) -> None:
    manifest = tmp_path / "bad-digest.json"
    manifest.write_text(json.dumps({"records": [], "sha256": "not-a-sha256"}), encoding="utf-8")
    assert verify_manifest(manifest) is False
