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


def test_qa5_security_job_pattern_matches_sbom_job_name() -> None:
    jobs = [
        {"name": "Dependency, SBOM, and secret hygiene", "status": "completed", "conclusion": "failure"},
        {"name": "Target authorization policy", "status": "completed", "conclusion": "success"},
        {"name": "Docker authorized target smoke", "status": "completed", "conclusion": "success"},
    ]
    assert job_result(
        jobs,
        (
            "Dependency, SBOM, and secret hygiene",
            "Dependency and secret hygiene",
            "Target authorization policy",
            "Docker authorized target smoke",
        ),
    ) == "FAIL"


def test_sync_jira_handles_service_unavailable_with_structured_blocked_diagnostic(tmp_path, monkeypatch, capsys) -> None:
    import json
    import scripts.sync_jira_ci as sync_mod
    from saqa.jira import JiraServiceUnavailableError

    summary_file = tmp_path / "step-summary.md"
    jobs_file = tmp_path / "jobs.json"
    runs_file = tmp_path / "runs.json"
    perf_file = tmp_path / "perf.json"
    jobs_file.write_text("[]", encoding="utf-8")
    runs_file.write_text("[]", encoding="utf-8")
    perf_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("JIRA_WORKFLOW_NAME", "SAQA CI")
    monkeypatch.setenv("JIRA_RUN_ID", "999")
    monkeypatch.setenv("JIRA_RUN_NUMBER", "1")
    monkeypatch.setenv("JIRA_RUN_CONCLUSION", "success")
    monkeypatch.setenv("JIRA_RUN_STATUS", "completed")
    monkeypatch.setenv("JIRA_HEAD_SHA", "a" * 40)
    monkeypatch.setenv("JIRA_HEAD_BRANCH", "main")
    monkeypatch.setenv("JIRA_RUN_URL", "https://github.com/example/run/999")
    monkeypatch.setenv("JIRA_JOBS_JSON", str(jobs_file))
    monkeypatch.setenv("JIRA_ALL_RUNS_JSON", str(runs_file))
    monkeypatch.setenv("JIRA_PERFORMANCE_JSON", str(perf_file))
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example")
    monkeypatch.setenv("JIRA_EMAIL", "qa@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "runtime-only-token")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "QA")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    class UnavailableClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def verify_access(self):
            raise JiraServiceUnavailableError("Jira unavailable", status_code=503, url="https://jira.example/rest/api/3/project/QA")

    monkeypatch.setattr(sync_mod, "JiraClient", UnavailableClient)

    # Non-strict mode reports BLOCKED cleanly without raising
    monkeypatch.setenv("SAQA_JIRA_FAIL_ON_UNAVAILABLE", "false")
    sync_mod.main()
    out = capsys.readouterr().out
    assert '"status": "BLOCKED"' in out
    assert "BLOCKED" in summary_file.read_text(encoding="utf-8")

    # Strict mode still fails closed
    monkeypatch.setenv("SAQA_JIRA_FAIL_ON_UNAVAILABLE", "true")
    with pytest.raises(SystemExit) as exc_info:
        sync_mod.main()
    assert exc_info.value.code == 1


def test_sync_manifest_to_jira_updates_all_9_domains_and_creates_bug_on_failure(tmp_path):
    from saqa.evidence import EvidenceRecord, utc_now, write_manifest
    from saqa.jira import JiraConfig, JiraProjectResult
    from saqa.jira_sync import ISSUE_SUMMARIES, sync_manifest_to_jira

    class FakeSuiteJiraClient:
        def __init__(self) -> None:
            self.config = JiraConfig("https://jira.example", "qa@example.com", "token", "QA")
            self.issues = {
                summary: JiraIssueResult(key, str(idx), f"https://jira.example/browse/{key}")
                for idx, (key, summary) in enumerate(ISSUE_SUMMARIES.items(), start=1)
            }
            self.labels_updated: list[tuple[str, tuple[str, ...]]] = []
            self.transitions: list[tuple[str, str]] = []
            self.comments: list[tuple[str, str]] = []
            self.bugs: list[str] = []

        def verify_access(self) -> JiraProjectResult:
            return JiraProjectResult("QA", "SAQA Quality", "software")

        def find_project_issues(self) -> dict[str, JiraIssueResult]:
            return dict(self.issues)

        def get_issue_state(self, issue_key: str) -> JiraIssueState:
            return JiraIssueState(issue_key, "Backlog", ("saqa-bootstrap", "saqa-ci-fail"))

        def update_labels(self, issue_key: str, *, add=(), remove=()) -> None:
            self.labels_updated.append((issue_key, tuple(add)))

        def transition_to_any(self, issue_key: str, target_statuses) -> str:
            first = next(iter(target_statuses))
            self.transitions.append((issue_key, first))
            return first

        def add_comment_once(self, issue_key: str, body: str, marker: str) -> bool:
            self.comments.append((issue_key, marker))
            return True

        def search_issues(self, jql: str, max_results: int = 100):
            return []

        def create_bug(self, summary: str, description: str, labels: list[str]) -> JiraIssueResult:
            self.bugs.append(summary)
            return JiraIssueResult("QA-99", "99", "https://jira.example/browse/QA-99")

        def close(self) -> None:
            pass

    manifest_path = tmp_path / "suite-manifest.json"
    write_manifest(
        [
            EvidenceRecord(
                test_id="web-home",
                status="PASS",
                observed_at=utc_now(),
                target="https://www.dreamex.tech",
                details={"suite": "dreamex-suite", "tags": ["web", "smoke"], "elapsed_ms": 120.0},
            ),
            EvidenceRecord(
                test_id="api-broken",
                status="FAIL",
                observed_at=utc_now(),
                target="https://www.dreamex.tech",
                details={"suite": "dreamex-suite", "tags": ["api"], "elapsed_ms": 210.0},
            ),
        ],
        manifest_path,
    )

    fake_client = FakeSuiteJiraClient()
    summary = sync_manifest_to_jira(manifest_path, client=fake_client)  # type: ignore[arg-type]
    assert summary["project_key"] == "QA"
    assert summary["suite_name"] == "dreamex-suite"
    assert len(summary["synced_issues"]) == 9
    by_domain = {item["domain"]: item for item in summary["synced_issues"]}
    assert by_domain["QA-2"]["status"] == "PASS"
    assert by_domain["QA-4"]["status"] == "FAIL"
    assert len(fake_client.comments) == 9
    assert len(summary["created_bugs"]) >= 1


def test_sync_manifest_to_jira_uploads_visuals_epics_timeline_and_resolves_stale_bugs(tmp_path):
    from saqa.evidence import EvidenceRecord, utc_now, write_manifest
    from saqa.jira import JiraConfig, JiraProjectResult
    from saqa.jira_sync import ISSUE_SUMMARIES, sync_manifest_to_jira

    class EnterpriseFakeJiraClient:
        def __init__(self) -> None:
            self.config = JiraConfig("https://jira.example", "qa@example.com", "token", "QA")
            self.issues = {
                summary: JiraIssueResult(key, str(idx), f"https://jira.example/browse/{key}")
                for idx, (key, summary) in enumerate(ISSUE_SUMMARIES.items(), start=1)
            }
            self.issues["[SAQA-AUTO] QA-4 | SAQA CI | run 100"] = JiraIssueResult(
                "QA-10", "10", "https://jira.example/browse/QA-10"
            )
            self.epics: list[str] = []
            self.field_updates: list[tuple[str, dict]] = []
            self.attachments: list[tuple[str, str]] = []
            self.adf_comments: list[str] = []
            self.statuses: dict[str, str] = {"QA-10": "Backlog"}

        def verify_access(self) -> JiraProjectResult:
            return JiraProjectResult("QA", "SAQA Quality", "software")

        def get_myself_account_id(self) -> str:
            return "acc-123"

        def find_project_issues(self) -> dict[str, JiraIssueResult]:
            return dict(self.issues)

        def create_epic(self, summary, description_adf, labels, *, start_date=None, due_date=None, assignee_id=None):
            key = f"QA-{20 + len(self.epics)}"
            self.epics.append(key)
            issue = JiraIssueResult(key, str(20 + len(self.epics)), f"https://jira.example/browse/{key}")
            self.issues[summary] = issue
            return issue

        def get_issue_state(self, issue_key: str) -> JiraIssueState:
            return JiraIssueState(issue_key, self.statuses.get(issue_key, "Backlog"), ("saqa-bootstrap",))

        def update_labels(self, issue_key: str, *, add=(), remove=()) -> None:
            pass

        def update_issue_fields(self, issue_key: str, fields) -> None:
            self.field_updates.append((issue_key, dict(fields)))

        def transition_to_any(self, issue_key: str, target_statuses) -> str:
            first = next(iter(target_statuses))
            self.statuses[issue_key] = first
            return first

        def add_adf_comment_once(self, issue_key: str, adf_doc, marker: str) -> bool:
            self.adf_comments.append(issue_key)
            return True

        def upload_attachment(self, issue_key: str, file_path, *, replace_existing: bool = True):
            self.attachments.append((issue_key, file_path.name))
            return {"filename": file_path.name}

        def close(self) -> None:
            pass

    manifest_path = tmp_path / "evidence-manifest.json"
    write_manifest(
        [
            EvidenceRecord(
                test_id="api-ok",
                status="PASS",
                observed_at=utc_now(),
                target="https://www.dreamex.tech",
                details={"suite": "dreamex-suite", "tags": ["api", "web"], "elapsed_ms": 95.0},
            )
        ],
        manifest_path,
    )

    client = EnterpriseFakeJiraClient()
    summary = sync_manifest_to_jira(manifest_path, client=client)  # type: ignore[arg-type]
    assert len(summary["synced_epics"]) == 3
    assert "QA-10" in summary["resolved_bugs"]
    uploaded_names = {name for _, name in client.attachments}
    assert {"qa-scorecard.png", "qa-analytics-chart.svg", "qa-test-matrix.csv", "report.html", "report.md"}.issubset(uploaded_names)
    assert any("customfield_10015" in fields and "duedate" in fields for _, fields in client.field_updates)
