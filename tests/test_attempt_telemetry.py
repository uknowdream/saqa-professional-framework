import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.pytest_attempt_telemetry import AttemptTelemetryPlugin, SHARD_SCHEMA
from scripts.summarize_test_attempts import REPORT_SCHEMA, load_shards, main, summarize_shards


def _attempt(nodeid, index, status="PASS", worker="gw0", duration=0.01):
    phases = {"setup": "PASS", "call": status, "teardown": "PASS"}
    return {"nodeid": nodeid, "attempt_index": index, "status": status,
            "phase_statuses": phases, "duration_seconds": duration, "worker_id": worker}


def _shard(worker="gw0", attempts=None, **metadata):
    value = {
        "schema": SHARD_SCHEMA,
        "run_id": "123",
        "run_attempt": "1",
        "commit_sha": "a" * 40,
        "python_version": "3.12",
        "worker_id": worker,
        "attempts": attempts or [_attempt("tests/test_x.py::test_ok", 1, worker=worker)],
    }
    value.update(metadata)
    return value


def _write_shard(directory: Path, value):
    path = directory / f"attempts-{value['worker_id']}.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_clean_single_attempt_report(tmp_path):
    _write_shard(tmp_path, _shard())
    report = summarize_shards(load_shards(tmp_path))
    assert report["schema"] == REPORT_SCHEMA
    assert report["status"] == "CLEAN"
    assert report["attempt_count"] == 1
    assert report["retry_attempt_count"] == 0
    assert report["tests_with_retry_outcome_variation"] == 0


def test_recovered_failure_is_explicit_variation_and_blocks(tmp_path):
    attempts = [
        _attempt("tests/test_x.py::test_sometimes_fails", 1, "FAIL"),
        _attempt("tests/test_x.py::test_sometimes_fails", 2, "PASS"),
    ]
    _write_shard(tmp_path, _shard(attempts=attempts))
    report = summarize_shards(load_shards(tmp_path))
    test = report["tests"][0]
    assert report["status"] == "RETRY_OUTCOME_VARIATION"
    assert report["tests_with_retries"] == 1
    assert report["recovered_failure_count"] == 1
    assert test["attempt_statuses"] == ["FAIL", "PASS"]
    assert test["retry_outcome_variation"] is True


def test_repeat_failure_is_not_mislabelled_as_recovered_or_variation(tmp_path):
    attempts = [
        _attempt("tests/test_x.py::test_always_fails", 1, "FAIL"),
        _attempt("tests/test_x.py::test_always_fails", 2, "FAIL"),
    ]
    _write_shard(tmp_path, _shard(attempts=attempts))
    report = summarize_shards(load_shards(tmp_path))
    assert report["status"] == "FINAL_FAILURES"
    assert report["recovered_failure_count"] == 0
    assert report["tests_with_retry_outcome_variation"] == 0
    assert report["final_failure_count"] == 1


def test_skipped_attempts_are_counted_but_not_called_flaky(tmp_path):
    attempts = [_attempt("tests/test_x.py::test_skip", 1, "SKIP")]
    _write_shard(tmp_path, _shard(attempts=attempts))
    report = summarize_shards(load_shards(tmp_path))
    assert report["status"] == "CLEAN"
    assert report["skip_attempt_count"] == 1


@pytest.mark.parametrize("bad_attempt", [
    {**_attempt("x", 1), "attempt_index": True},
    {**_attempt("x", 1), "duration_seconds": float("nan")},
    {**_attempt("x", 1), "status": "PASS", "phase_statuses": {"call": "FAIL"}},
    {**_attempt("x", 1), "phase_statuses": {"unknown-phase": "PASS"}},
])
def test_invalid_attempt_record_is_rejected(tmp_path, bad_attempt):
    _write_shard(tmp_path, _shard(attempts=[bad_attempt]))
    with pytest.raises(ValueError):
        load_shards(tmp_path)


def test_invalid_commit_sha_is_rejected(tmp_path):
    _write_shard(tmp_path, _shard(commit_sha="not-a-sha"))
    with pytest.raises(ValueError, match="commit_sha must be a full lowercase SHA or unknown"):
        load_shards(tmp_path)


def test_shard_run_metadata_must_match(tmp_path):
    _write_shard(tmp_path, _shard())
    _write_shard(tmp_path, _shard("gw1", [_attempt("tests/test_y.py::test_ok", 1, worker="gw1")], run_id="999"))
    with pytest.raises(ValueError, match="metadata does not match"):
        load_shards(tmp_path)


def test_attempt_indexes_must_be_consecutive():
    shard = _shard(attempts=[
        _attempt("tests/test_x.py::test_gap", 1),
        _attempt("tests/test_x.py::test_gap", 3),
    ])
    with pytest.raises(ValueError, match="consecutive"):
        summarize_shards([shard])


def test_duplicate_test_attempt_is_rejected(tmp_path):
    _write_shard(tmp_path, _shard(attempts=[
        _attempt("tests/test_x.py::test_dup", 1),
        _attempt("tests/test_x.py::test_dup", 1),
    ]))
    with pytest.raises(ValueError, match="duplicate test attempt"):
        load_shards(tmp_path)


def test_cli_writes_blocked_report_when_no_shards(tmp_path):
    output = tmp_path / "result.json"
    assert main(["--input-dir", str(tmp_path / "missing"), "--output", str(output)]) == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "BLOCKED"


def test_hook_captures_real_execution_count_per_phase(tmp_path, monkeypatch):
    monkeypatch.setenv("SAQA_ATTEMPT_TELEMETRY_DIR", str(tmp_path))
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    plugin = AttemptTelemetryPlugin(config=None)
    item = SimpleNamespace(nodeid="tests/test_x.py::test_retry", execution_count=1)

    class Report:
        when = "call"
        outcome = "failed"
        duration = 0.125
        failed = True
        skipped = False

    generator = plugin.pytest_runtest_makereport(item, SimpleNamespace())
    next(generator)
    with pytest.raises(StopIteration):
        generator.send(SimpleNamespace(get_result=lambda: Report()))

    item.execution_count = 2

    class RetryReport:
        when = "call"
        outcome = "passed"
        duration = 0.25
        failed = False
        skipped = False

    generator = plugin.pytest_runtest_makereport(item, SimpleNamespace())
    next(generator)
    with pytest.raises(StopIteration):
        generator.send(SimpleNamespace(get_result=lambda: RetryReport()))

    plugin.pytest_sessionfinish(None, 0)
    shard = json.loads((tmp_path / "attempts-gw0.json").read_text(encoding="utf-8"))
    assert [x["attempt_index"] for x in shard["attempts"]] == [1, 2]
    assert [x["status"] for x in shard["attempts"]] == ["FAIL", "PASS"]


def test_cli_exit_code_fails_on_retry_variation(tmp_path):
    _write_shard(tmp_path, _shard(attempts=[
        _attempt("tests/test_x.py::test_retry", 1, "FAIL"),
        _attempt("tests/test_x.py::test_retry", 2, "PASS"),
    ]))
    output = tmp_path / "report.json"
    assert main(["--input-dir", str(tmp_path), "--output", str(output)]) == 1
    assert json.loads(output.read_text())["status"] == "RETRY_OUTCOME_VARIATION"
