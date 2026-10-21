import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.test_stability_history import SCHEMA, build_history, parse_junit


def _write_run(root: Path, run_id: str, sha: str, *, version="3.12", event="push",
               conclusion="success", outcomes=None):
    run_dir = root / run_id
    cohort = run_dir / f"python-{version}"
    cohort.mkdir(parents=True, exist_ok=True)
    (run_dir / "run-metadata.json").write_text(json.dumps({
        "run_id": run_id, "head_sha": sha, "conclusion": conclusion,
        "event": event, "head_branch": "main", "created_at": "2026-10-21T00:00:00Z",
    }), encoding="utf-8")
    cases = []
    for test_id, status in (outcomes or {"tests.test_api::test_ok": "PASS"}).items():
        if "::" in test_id:
            classname, name = test_id.split("::", 1)
        else:
            classname, name = "", test_id
        if status == "FAIL":
            result = "<failure message='failed'>assert False</failure>"
        elif status == "ERROR":
            result = "<error message='error'>exception</error>"
        elif status == "SKIP":
            result = "<skipped message='skip'/>"
        else:
            result = ""
        cases.append(f"<testcase classname='{classname}' name='{name}' time='0.01'>{result}</testcase>")
    (cohort / "junit.xml").write_text(
        "<testsuites><testsuite name='pytest'>" + "".join(cases) + "</testsuite></testsuites>",
        encoding="utf-8",
    )


def test_no_history_returns_advisory_insufficient_status(tmp_path):
    report = build_history(tmp_path)
    assert report["schema"] == SCHEMA
    assert report["status"] == "INSUFFICIENT_HISTORY"
    assert report["summary"]["run_count"] == 0


def test_outcomes_across_commits_are_reported_not_called_flaky(tmp_path):
    root = tmp_path / "history"
    _write_run(root, "101", "a" * 40, outcomes={"tests.test_api::test_item": "PASS"})
    _write_run(root, "102", "b" * 40, outcomes={"tests.test_api::test_item": "FAIL"})
    _write_run(root, "103", "c" * 40, outcomes={"tests.test_api::test_item": "PASS"})
    report = build_history(root, min_runs=3)
    item = next(test for test in report["tests"] if test["test_id"] == "tests.test_api::test_item")
    assert report["status"] == "CROSS_COMMIT_OUTCOME_VARIATION"
    assert item["cross_commit_outcome_variation"] is True
    assert item["same_commit_outcome_variation"] is False


def test_same_commit_pass_and_failure_is_a_candidate_intermittent_result(tmp_path):
    root = tmp_path / "history"
    sha = "c" * 40
    _write_run(root, "201", sha, event="push", outcomes={"tests.test_api::test_item": "PASS"})
    _write_run(root, "202", sha, event="schedule", outcomes={"tests.test_api::test_item": "FAIL"})
    _write_run(root, "203", sha, event="schedule", outcomes={"tests.test_api::test_item": "PASS"})
    report = build_history(root, min_runs=3)
    item = next(test for test in report["tests"] if test["test_id"] == "tests.test_api::test_item")
    assert report["status"] == "SAME_COMMIT_OUTCOME_VARIATION"
    assert item["same_commit_outcome_variation"] is True
    assert item["observation_count"] == 3


def test_python_versions_are_kept_in_separate_cohorts(tmp_path):
    root = tmp_path / "history"
    _write_run(root, "301", "a" * 40, version="3.11", outcomes={"tests.test_api::test_item": "PASS"})
    _write_run(root, "302", "a" * 40, version="3.12", outcomes={"tests.test_api::test_item": "FAIL"})
    report = build_history(root, min_runs=2)
    assert {test["python_version"] for test in report["tests"]} == {"3.11", "3.12"}
    assert all(test["observation_count"] == 1 for test in report["tests"])


def test_invalid_branch_metadata_is_rejected_and_reported(tmp_path):
    root = tmp_path / "history"
    _write_run(root, "401", "a" * 40, outcomes={"tests.test_api::test_item": "PASS"})
    metadata = root / "401" / "run-metadata.json"
    value = json.loads(metadata.read_text())
    value["head_branch"] = "feature"
    metadata.write_text(json.dumps(value), encoding="utf-8")
    report = build_history(root)
    assert report["runs"] == []
    assert report["issues"]
    assert report["status"] == "INSUFFICIENT_HISTORY"


def test_insufficient_history_is_not_falsely_certified(tmp_path):
    root = tmp_path / "history"
    _write_run(root, "501", "a" * 40)
    report = build_history(root, min_runs=3)
    assert report["status"] == "INSUFFICIENT_HISTORY"
    assert report["cohorts"][0]["sufficient_history"] is False


def test_junit_parser_rejects_ambiguous_duplicate_test_ids(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(
        "<testsuite><testcase classname='test_x' name='test_y'/>"
        "<testcase classname='test_x' name='test_y'/></testsuite>", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate JUnit test ID"):
        parse_junit(path)


def test_junit_parser_classifies_error_skip_and_pass(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(
        "<testsuite><testcase classname='x' name='ok'/>"
        "<testcase classname='x' name='err'><error/></testcase>"
        "<testcase classname='x' name='skip'><skipped/></testcase></testsuite>",
        encoding="utf-8",
    )
    assert parse_junit(path) == {"x::ok": "PASS", "x::err": "ERROR", "x::skip": "SKIP"}


def test_min_runs_and_timezone_validation(tmp_path):
    with pytest.raises(ValueError, match="at least 2"):
        build_history(tmp_path, min_runs=1)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_history(tmp_path, generated_at=datetime(2026, 1, 1))


def test_cli_exits_blocked_for_invalid_min_runs(tmp_path):
    from scripts.test_stability_history import main

    output = tmp_path / "report.json"
    exit_code = main([
        "--input-root", str(tmp_path / "empty"),
        "--min-runs", "1",
        "--output", str(output),
    ])
    assert exit_code == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "BLOCKED"


def test_missing_matrix_artifacts_are_explicit_history_gaps(tmp_path):
    root = tmp_path / "history"
    _write_run(root, "601", "d" * 40, version="3.11",
               outcomes={"tests.test_api::test_item": "PASS"})
    report = build_history(root, min_runs=2)
    gaps = {(item["run_id"], item["python_version"]) for item in report["artifact_gaps"]}
    assert gaps == {("601", "3.12"), ("601", "3.13")}
    assert report["summary"]["artifact_gap_count"] == 2
    assert report["status"] == "INCOMPLETE_ARTIFACT_COVERAGE"
