from __future__ import annotations

import pytest

from scripts.sync_jira_ci import (
    ISSUE_SUMMARIES,
    RunSummary,
    ensure_managed_issues,
    job_result,
    run_label,
    transition_targets,
)
from src.saqa.jira import JiraIssueResult, JiraIssueState


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


class BootstrapOnlyJiraStub:
    def __init__(self, summaries: dict[str, JiraIssueResult]) -> None:
        self.summaries = summaries
        self.created = 0
        self.label_updates: list[tuple[str, tuple[str, ...]]] = []

    def find_project_issues(self) -> dict[str, JiraIssueResult]:
        return dict(self.summaries)

    def get_issue_state(self, issue_key: str) -> JiraIssueState:
        return JiraIssueState(issue_key, "To Do", ("saqa-bootstrap", "saqa-automation"))

    def update_labels(self, issue_key: str, *, add=(), remove=()) -> None:
        self.label_updates.append((issue_key, tuple(add)))

    def create_task(self, **_: object) -> JiraIssueResult:
        self.created += 1
        raise AssertionError("CI synchronization must never create missing managed Jira tasks")


def test_ensure_managed_issues_is_fail_closed_without_self_healing() -> None:
    client = BootstrapOnlyJiraStub({})
    with pytest.raises(RuntimeError, match="will not self-heal"):
        ensure_managed_issues(client)  # type: ignore[arg-type]
    assert client.created == 0


def test_ensure_managed_issues_resolves_existing_bootstrapped_items() -> None:
    summaries = {
        summary: JiraIssueResult(f"{key}", str(index), f"https://jira.example/browse/{key}")
        for index, (key, summary) in enumerate(ISSUE_SUMMARIES.items(), start=1)
    }
    client = BootstrapOnlyJiraStub(summaries)
    managed = ensure_managed_issues(client)  # type: ignore[arg-type]
    assert set(managed) == set(ISSUE_SUMMARIES)
    assert client.created == 0
