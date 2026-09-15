from __future__ import annotations

from scripts.sync_jira_ci import RunSummary, job_result, run_label, transition_targets


def make_run(*, status: str = "completed", conclusion: str = "success") -> RunSummary:
    return RunSummary(
        name="SAQA CI",
        run_id="123",
        run_number="42",
        conclusion=conclusion,
        status=status,
        head_sha="abc123",
        branch="saqa/test",
        url="https://github.com/example/run/123",
    )


def test_run_summary_never_promotes_non_completed_to_pass() -> None:
    assert make_run(status="queued", conclusion="").result == "PENDING"


def test_run_summary_maps_failure_and_blocked_conclusions() -> None:
    assert make_run(conclusion="failure").result == "FAIL"
    assert make_run(conclusion="cancelled").result == "BLOCKED"
    assert make_run(conclusion="success").result == "PASS"


def test_job_result_requires_all_matching_jobs_to_complete_successfully() -> None:
    jobs = [
        {"name": "Juice Shop API", "status": "completed", "conclusion": "success"},
        {"name": "Juice Shop API smoke evidence", "status": "completed", "conclusion": "success"},
    ]
    assert job_result(jobs, ("Juice Shop API",)) == "PASS"

    jobs[1]["conclusion"] = "failure"
    assert job_result(jobs, ("Juice Shop API",)) == "FAIL"


def test_job_result_is_unverified_when_no_job_matches() -> None:
    assert job_result([], ("missing job",)) == "UNVERIFIED"


def test_status_labels_and_transition_targets_are_deterministic() -> None:
    assert run_label("PASS") == "saqa-ci-pass"
    assert run_label("FAIL") == "saqa-ci-fail"
    assert "Done" in transition_targets("PASS")
    assert "In Progress" in transition_targets("FAIL")
