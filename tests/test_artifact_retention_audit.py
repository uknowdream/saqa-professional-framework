import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.audit_artifact_retention import MANDATORY, audit_artifacts, main

NOW = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)
MAIN_SHA = "a" * 40


def payloads():
    runs, artifacts = [], []
    for index, (name, path, workflow_id, artifact_name) in enumerate(MANDATORY):
        run_id = 9000 + index
        started = NOW - timedelta(minutes=15)
        runs.append({
            "id": run_id, "run_attempt": 1, "name": name, "path": path,
            "workflow_id": workflow_id, "head_sha": MAIN_SHA, "head_branch": "main",
            "event": "push", "status": "completed", "conclusion": "success",
            "created_at": started.isoformat(), "run_started_at": started.isoformat(),
            "html_url": f"https://github.com/example/repo/actions/runs/{run_id}",
        })
        artifacts.append({
            "id": 10000 + index, "name": artifact_name, "expired": False,
            "size_in_bytes": 256, "created_at": (started + timedelta(seconds=10)).isoformat(),
            "expires_at": (NOW + timedelta(days=7)).isoformat(),
            "workflow_run": {"id": run_id},
        })
    return runs, artifacts


def test_all_mandatory_artifacts_pass_with_current_run_provenance():
    runs, artifacts = payloads()
    result = audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW)
    assert result["status"] == "PASS"
    assert result["passed_domain_count"] == 5
    assert all(item["artifact_id"] for item in result["checks"])


def test_missing_exact_sha_workflow_run_fails_closed():
    runs, artifacts = payloads()
    runs[0]["head_sha"] = "b" * 40
    result = audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW)
    assert result["status"] == "FAIL"
    assert "no exact-workflow run found" in result["checks"][0]["reasons"][0]


def test_wrong_workflow_identity_cannot_substitute():
    runs, artifacts = payloads()
    runs[0]["workflow_id"] += 1
    result = audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW)
    assert result["checks"][0]["status"] == "FAIL"


def test_failed_or_in_progress_latest_run_blocks_artifact_audit():
    runs, artifacts = payloads()
    runs[0]["conclusion"] = "failure"
    result = audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW)
    assert result["status"] == "FAIL"
    assert any("not completed successfully" in reason for reason in result["checks"][0]["reasons"])


def test_missing_artifact_fails():
    runs, artifacts = payloads()
    artifacts = artifacts[1:]
    result = audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW)
    assert result["checks"][0]["status"] == "FAIL"
    assert "required artifact is missing" in result["checks"][0]["reasons"][0]


@pytest.mark.parametrize("mutation,reason", [
    (lambda a: a.update(expired=True), "marked expired"),
    (lambda a: a.update(size_in_bytes=0), "empty"),
    (lambda a: a.update(expires_at=(NOW + timedelta(hours=2)).isoformat()), "expires within"),
    (lambda a: a.update(created_at=(NOW - timedelta(hours=1)).isoformat()), "predates"),
])
def test_expired_empty_near_expiry_or_old_attempt_artifacts_fail(mutation, reason):
    runs, artifacts = payloads()
    mutation(artifacts[0])
    result = audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW)
    assert result["checks"][0]["status"] == "FAIL"
    assert reason in json.dumps(result["checks"][0]["artifact_rejections"])


def test_artifact_from_different_workflow_run_cannot_substitute():
    runs, artifacts = payloads()
    artifacts[0]["workflow_run"]["id"] = 999999
    result = audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW)
    assert result["checks"][0]["status"] == "FAIL"


def test_latest_attempt_wins_and_old_attempt_artifact_is_not_reused():
    runs, artifacts = payloads()
    retry = copy.deepcopy(runs[0])
    retry.update({"run_attempt": 2, "status": "completed", "conclusion": "failure",
                  "created_at": (NOW - timedelta(minutes=2)).isoformat(),
                  "run_started_at": (NOW - timedelta(minutes=2)).isoformat()})
    runs.append(retry)
    result = audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW)
    assert result["checks"][0]["run_attempt"] == 2
    assert result["checks"][0]["status"] == "FAIL"


@pytest.mark.parametrize("bad_sha", ["main", "A" * 40, "a" * 39])
def test_invalid_main_sha_rejected(bad_sha):
    runs, artifacts = payloads()
    with pytest.raises(ValueError, match="40-character lowercase commit SHA"):
        audit_artifacts(runs, artifacts, main_sha=bad_sha, now=NOW)


def test_naive_audit_clock_rejected():
    runs, artifacts = payloads()
    with pytest.raises(ValueError, match="timezone"):
        audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=datetime(2026, 10, 21, 15, 0))


def test_cli_emits_fail_closed_report_for_bad_metadata(tmp_path):
    runs_file, artifacts_file = tmp_path / "runs.json", tmp_path / "artifacts.json"
    output = tmp_path / "out" / "report.json"
    runs_file.write_text("[]", encoding="utf-8")
    artifacts_file.write_text("[]", encoding="utf-8")
    assert main(["--runs-file", str(runs_file), "--artifacts-file", str(artifacts_file),
                 "--main-sha", MAIN_SHA, "--output", str(output)]) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "FAIL"
    assert result["ready"] is False


@pytest.mark.parametrize("hours", [0, -1, float("nan"), float("inf"), True, 1e308, 1e-12])
def test_invalid_retention_window_is_rejected(hours):
    runs, artifacts = payloads()
    with pytest.raises(ValueError, match="min_retention_hours"):
        audit_artifacts(runs, artifacts, main_sha=MAIN_SHA, now=NOW, min_retention_hours=hours)
