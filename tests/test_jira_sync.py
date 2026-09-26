from __future__ import annotations

import pytest

from scripts.sync_jira_ci import (
    ISSUE_SUMMARIES,
    MONITORED_WORKFLOWS,
    RunSummary,
    ensure_managed_issues,
    aggregate_performance_result,
    contract_evidence_result,
    certification_overall,
    job_result,
    run_label,
    transition_targets,
)
from saqa.jira import JiraIssueResult, JiraIssueState


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


def test_run_label_rejects_unknown_results() -> None:
    with pytest.raises(ValueError, match="Unsupported SAQA result"):
        run_label("NOT_A_RESULT")


def test_status_labels_and_transition_targets_are_deterministic() -> None:
    assert run_label("PASS") == "saqa-ci-pass"
    assert run_label("FAIL") == "saqa-ci-fail"
    assert "Done" in transition_targets("PASS")
    assert "In Progress" in transition_targets("FAIL")


class BootstrapOnlyJiraStub:
    def __init__(self, summaries: dict[str, JiraIssueResult], labels: tuple[str, ...] = ("saqa-bootstrap", "saqa-automation")) -> None:
        self.summaries = summaries
        self.labels = labels
        self.created = 0
        self.label_updates: list[tuple[str, tuple[str, ...]]] = []

    def find_project_issues(self) -> dict[str, JiraIssueResult]:
        return dict(self.summaries)

    def get_issue_state(self, issue_key: str) -> JiraIssueState:
        return JiraIssueState(issue_key, "To Do", self.labels)

    def update_labels(self, issue_key: str, *, add=(), remove=()) -> None:
        self.label_updates.append((issue_key, tuple(add)))

    def create_task(self, **_: object) -> JiraIssueResult:
        self.created += 1
        raise AssertionError("CI synchronization must never create missing managed Jira tasks")


def test_ensure_managed_issues_is_fail_closed_without_self_healing_or_partial_writes() -> None:
    summaries = {
        ISSUE_SUMMARIES["QA-1"]: JiraIssueResult("QA-1", "1", "https://jira.example/browse/QA-1")
    }
    client = BootstrapOnlyJiraStub(summaries, labels=())
    with pytest.raises(RuntimeError, match="will not self-heal"):
        ensure_managed_issues(client)  # type: ignore[arg-type]
    assert client.created == 0
    assert client.label_updates == []


def test_ensure_managed_issues_resolves_existing_bootstrapped_items_and_repairs_labels() -> None:
    summaries = {
        summary: JiraIssueResult(f"{key}", str(index), f"https://jira.example/browse/{key}")
        for index, (key, summary) in enumerate(ISSUE_SUMMARIES.items(), start=1)
    }
    client = BootstrapOnlyJiraStub(summaries, labels=("saqa-bootstrap",))
    managed = ensure_managed_issues(client)  # type: ignore[arg-type]
    assert set(managed) == set(ISSUE_SUMMARIES)
    assert client.created == 0
    assert {key for key, _ in client.label_updates} == {issue.key for issue in managed.values()}
    assert all(add == ("saqa-automation",) for _, add in client.label_updates)


def test_jira_sync_fail_closed_mappings():

    pending = RunSummary("SAQA CI", "1", "1", "", "in_progress", "sha", "main", "")
    unknown = RunSummary("SAQA CI", "2", "2", "", "completed", "sha", "main", "")
    assert pending.result == "PENDING"
    assert unknown.result == "UNVERIFIED"
    assert job_result([{"name": "gate", "status": "in_progress", "conclusion": None}], ("gate",)) == "PENDING"
    assert run_label("BLOCKED") == "saqa-ci-blocked"
    assert run_label("PENDING") == "saqa-ci-pending"
    assert run_label("UNVERIFIED") == "saqa-ci-unverified"
    assert transition_targets("BLOCKED") == ("Blocked", "In Progress")
    assert transition_targets("PENDING") == ("In Progress", "Open", "To Do")
    assert transition_targets("UNVERIFIED") == ("In Progress", "Open", "To Do")


def test_certification_overall_requires_contract_evidence_for_release_pass() -> None:
    results = {name: "PASS" for name in MONITORED_WORKFLOWS}
    assert certification_overall(results, "PASS") == "PASS"
    assert certification_overall(results, "UNVERIFIED") == "UNVERIFIED"


def test_certification_overall_preserves_fail_closed_precedence() -> None:
    results = {name: "PASS" for name in MONITORED_WORKFLOWS}
    results["SAQA CI"] = "FAIL"
    assert certification_overall(results, "UNVERIFIED") == "FAIL"


def test_aggregate_performance_result_is_order_independent_and_fail_closed() -> None:
    assert aggregate_performance_result({
        "SAQA CI performance": "PASS",
        "SAQA k6 Performance": "PASS",
    }) == "PASS"
    assert aggregate_performance_result({
        "SAQA CI performance": "PASS",
        "SAQA k6 Performance": "FAIL",
    }) == "FAIL"
    assert aggregate_performance_result({
        "SAQA CI performance": "FAIL",
        "SAQA k6 Performance": "PASS",
    }) == "FAIL"
    assert aggregate_performance_result({
        "SAQA CI performance": "BLOCKED",
        "SAQA k6 Performance": "PASS",
    }) == "BLOCKED"
    assert aggregate_performance_result({
        "SAQA CI performance": "PENDING",
        "SAQA k6 Performance": "PASS",
    }) == "PENDING"
    assert aggregate_performance_result({
        "SAQA CI performance": "PASS",
    }) == "UNVERIFIED"



def test_aggregate_performance_result_precedence_is_fail_closed() -> None:
    assert aggregate_performance_result({"SAQA CI performance": "FAIL", "SAQA k6 Performance": "BLOCKED"}) == "FAIL"
    assert aggregate_performance_result({"SAQA CI performance": "BLOCKED", "SAQA k6 Performance": "PENDING"}) == "BLOCKED"
    assert aggregate_performance_result({"SAQA CI performance": "PENDING", "SAQA k6 Performance": "PENDING"}) == "PENDING"
    assert aggregate_performance_result({}) == "UNVERIFIED"


def test_contract_evidence_requires_exact_source_sha(tmp_path) -> None:
    evidence = {
        "schema": "saqa.contract-gate.v2",
        "test_id": "juice-shop.api.openapi-contract",
        "status": "PASS",
        "target": "http://127.0.0.1:3000",
        "http_methods": ["GET"],
        "destructive_actions": False,
        "source_sha": "expected",
        "details": {"status_code": 200, "validation_errors": []},
    }
    path = tmp_path / "contract.json"
    path.write_text(__import__("json").dumps(evidence), encoding="utf-8")
    assert contract_evidence_result(str(path), "expected") == "PASS"
    assert contract_evidence_result(str(path), "different") == "UNVERIFIED"


def test_contract_evidence_rejects_missing_provenance(tmp_path) -> None:
    evidence = {
        "schema": "saqa.contract-gate.v2",
        "test_id": "juice-shop.api.openapi-contract",
        "status": "PASS",
        "target": "http://127.0.0.1:3000",
        "http_methods": ["GET"],
        "destructive_actions": False,
        "details": {"status_code": 200, "validation_errors": []},
    }
    path = tmp_path / "contract.json"
    path.write_text(__import__("json").dumps(evidence), encoding="utf-8")
    assert contract_evidence_result(str(path), "expected") == "UNVERIFIED"
