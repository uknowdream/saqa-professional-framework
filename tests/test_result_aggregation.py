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


def test_aggregate_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no execution results"):
        aggregate(tmp_path, tmp_path / "manifest.json")


def test_aggregate_rejects_invalid_result(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text('{"status":"PASS"}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields"):
        load_results(tmp_path)
