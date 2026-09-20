#!/usr/bin/env python3
"""Synchronize verified SAQA CI evidence into the Jira QA control plane."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from saqa.jira import JiraClient, JiraConfig, JiraIssueResult

ISSUE_SUMMARIES = {
    "QA-1": "SAQA | Test Management Foundation",
    "QA-2": "SAQA | Web E2E Automation",
    "QA-3": "SAQA | Cross-Browser Matrix",
    "QA-4": "SAQA | API Quality Gate",
    "QA-5": "SAQA | Security Regression Gate",
    "QA-6": "SAQA | Accessibility Gate",
    "QA-7": "SAQA | Performance Quality Gate",
    "QA-8": "SAQA | Evidence & Allure Traceability",
    "QA-9": "SAQA | Certification Readiness",
}
MONITORED_WORKFLOWS = {"SAQA CI", "SAQA Accessibility", "SAQA Mobile Readiness"}
PASS_CONCLUSIONS = {"success"}
FAIL_CONCLUSIONS = {"failure", "timed_out"}
BLOCKED_CONCLUSIONS = {"cancelled", "action_required", "stale"}
STATUS_LABELS = {"saqa-ci-pass", "saqa-ci-fail", "saqa-ci-blocked", "saqa-ci-pending", "saqa-ci-unverified"}


@dataclass(frozen=True, slots=True)
class RunSummary:
    name: str
    run_id: str
    run_number: str
    conclusion: str
    status: str
    head_sha: str
    branch: str
    url: str

    @property
    def result(self) -> str:
        if self.status != "completed":
            return "PENDING"
        if self.conclusion in PASS_CONCLUSIONS:
            return "PASS"
        if self.conclusion in FAIL_CONCLUSIONS:
            return "FAIL"
        if self.conclusion in BLOCKED_CONCLUSIONS:
            return "BLOCKED"
        return "UNVERIFIED"


def load_json(path_value: str | None, default: Any) -> Any:
    if not path_value:
        return default
    return json.loads(Path(path_value).read_text(encoding="utf-8"))


def normalize_runs(raw: Any) -> list[RunSummary]:
    if isinstance(raw, dict):
        raw = raw.get("workflow_runs", [])
    if not isinstance(raw, list):
        return []
    return [
        RunSummary(
            name=str(item.get("name", "")), run_id=str(item.get("id", "")), run_number=str(item.get("run_number", "")),
            conclusion=str(item.get("conclusion") or ""), status=str(item.get("status") or ""),
            head_sha=str(item.get("head_sha", "")), branch=str(item.get("head_branch", "")), url=str(item.get("html_url", "")),
        )
        for item in raw if isinstance(item, dict) and item.get("name") in MONITORED_WORKFLOWS and item.get("id")
    ]


def job_result(jobs: list[dict[str, Any]], patterns: tuple[str, ...]) -> str:
    matched = [job for job in jobs if any(pattern.casefold() in str(job.get("name", "")).casefold() for pattern in patterns)]
    if not matched:
        return "UNVERIFIED"
    if any(job.get("status") != "completed" for job in matched):
        return "PENDING"
    conclusions = {str(job.get("conclusion") or "") for job in matched}
    if conclusions == {"success"}:
        return "PASS"
    if conclusions & {"failure", "timed_out"}:
        return "FAIL"
    if conclusions & {"cancelled", "action_required", "stale"}:
        return "BLOCKED"
    return "UNVERIFIED"


def run_label(result: str) -> str:
    return {"PASS": "saqa-ci-pass", "FAIL": "saqa-ci-fail", "BLOCKED": "saqa-ci-blocked", "PENDING": "saqa-ci-pending", "UNVERIFIED": "saqa-ci-unverified"}[result]


def transition_targets(result: str) -> tuple[str, ...]:
    if result == "PASS": return ("Done", "Closed")
    if result == "FAIL": return ("In Progress", "Reopened")
    if result == "BLOCKED": return ("Blocked", "In Progress")
    return ("In Progress", "Open", "To Do")


def ensure_managed_issues(client: JiraClient) -> dict[str, JiraIssueResult]:
    """Resolve pre-bootstrapped QA issues without creating them during CI sync.

    The bootstrap is intentionally manual-only. CI synchronization must not perform
    lookup-then-create self-healing because independent workflow runs can race and
    Jira does not provide a uniqueness constraint on summaries. Missing control-plane
    items are therefore a fail-closed configuration error requiring bootstrap/recovery.

    Discovery and mutation are deliberately separated: if any managed issue is
    missing, the function raises before performing any Jira label writes. This keeps
    fail-closed synchronization free of partial side effects.
    """
    project_issues = client.find_project_issues()
    managed: dict[str, JiraIssueResult] = {}
    missing: list[str] = []
    for key, summary in ISSUE_SUMMARIES.items():
        existing = project_issues.get(summary)
        if not existing:
            missing.append(f"{key}: {summary}")
            continue
        managed[key] = existing

    if missing:
        details = "; ".join(missing)
        raise RuntimeError(
            "Jira managed QA issues are missing; CI synchronization will not self-heal them because "
            f"lookup-then-create is race-prone. Run the manual bootstrap/recovery workflow first. Missing: {details}"
        )

    for issue in managed.values():
        state = client.get_issue_state(issue.key)
        missing_labels = [label for label in ("saqa-bootstrap", "saqa-automation") if label not in state.labels]
        if missing_labels:
            client.update_labels(issue.key, add=missing_labels)
    return managed


def create_failure_bug_once(client: JiraClient, key: str, issue: JiraIssueResult, run: RunSummary, result: str, body: str) -> JiraIssueResult | None:
    if result != "FAIL" or key in {"QA-1", "QA-9"}:
        return None
    summary = f"[SAQA-AUTO] {key} | {run.name} | run {run.run_id}"
    existing = client.find_project_issues().get(summary)
    if existing:
        print(f"JIRA defect exists: {existing.key} for {key} run {run.run_id}")
        return existing
    return client.create_bug(
        summary=summary,
        description=(f"Automated defect generated from a verified SAQA quality failure.\nControl issue: {issue.key}\nWorkflow: {run.name}\nRun: #{run.run_number} ({run.run_id})\nCommit: {run.head_sha}\nBranch: {run.branch}\nCI URL: {run.url}\n\nEvidence:\n{body}\nClassification: AUTOMATED_VERIFIED_FAILURE\nRetest is expected on the next qualifying commit."),
        labels=["saqa-auto-defect", "saqa-ci-fail", "saqa-automation"],
    )


def sync_issue(client: JiraClient, key: str, issue: JiraIssueResult, result: str, body: str, marker: str, run: RunSummary) -> None:
    state = client.get_issue_state(issue.key)
    label = run_label(result)
    remove = tuple(existing for existing in STATUS_LABELS if existing in state.labels and existing != label)
    add = tuple(label_name for label_name in ("saqa-automation", label) if label_name not in state.labels)
    if add or remove:
        client.update_labels(issue.key, add=add, remove=remove)
    added = client.add_comment_once(issue.key, body, marker)
    transitioned = client.transition_to_any(issue.key, transition_targets(result))
    defect = create_failure_bug_once(client, key, issue, run, result, body)
    print(f"JIRA {key} ({issue.key}): result={result} comment={'added' if added else 'exists'} transition={transitioned or 'unchanged'} defect={defect.key if defect else 'none'}")


def main() -> None:
    run = RunSummary(
        name=os.environ["JIRA_WORKFLOW_NAME"], run_id=os.environ["JIRA_RUN_ID"], run_number=os.environ.get("JIRA_RUN_NUMBER", ""),
        conclusion=os.environ.get("JIRA_RUN_CONCLUSION", ""), status=os.environ.get("JIRA_RUN_STATUS", ""),
        head_sha=os.environ["JIRA_HEAD_SHA"], branch=os.environ.get("JIRA_HEAD_BRANCH", ""), url=os.environ.get("JIRA_RUN_URL", ""),
    )
    if run.name not in MONITORED_WORKFLOWS:
        raise SystemExit(f"Unsupported workflow for Jira synchronization: {run.name}")
    if run.branch != "main" and not run.branch.startswith("saqa/"):
        raise SystemExit(f"Unsupported branch for Jira synchronization: {run.branch!r}")
    if not run.head_sha:
        raise SystemExit("JIRA_HEAD_SHA is required for deterministic synchronization")

    jobs = load_json(os.environ.get("JIRA_JOBS_JSON"), [])
    all_runs = normalize_runs(load_json(os.environ.get("JIRA_ALL_RUNS_JSON"), []))
    current_results = {item.name: item.result for item in all_runs if item.head_sha == run.head_sha}
    relevant = [current_results.get(name, "PENDING") for name in MONITORED_WORKFLOWS]
    if any(value == "FAIL" for value in relevant): overall = "FAIL"
    elif any(value == "BLOCKED" for value in relevant): overall = "BLOCKED"
    elif all(value == "PASS" for value in relevant): overall = "PASS"
    elif any(value == "PENDING" for value in relevant): overall = "PENDING"
    else: overall = "UNVERIFIED"

    if run.name == "SAQA CI":
        domain_results = {"QA-1": "PASS", "QA-2": job_result(jobs, ("Juice Shop E2E", "WebGoat E2E")), "QA-3": job_result(jobs, ("Browser readiness", "Juice Shop E2E", "WebGoat E2E")), "QA-4": job_result(jobs, ("Juice Shop API",)), "QA-5": job_result(jobs, ("Dependency & secret hygiene", "Target authorization policy", "Docker authorized target smoke")), "QA-7": job_result(jobs, ("Juice Shop performance",)), "QA-8": job_result(jobs, ("Canonical evidence aggregation",)), "QA-9": overall}
    elif run.name == "SAQA Accessibility":
        domain_results = {"QA-1": "PASS", "QA-3": run.result, "QA-6": run.result, "QA-9": overall}
    else:
        domain_results = {"QA-1": "PASS", "QA-3": run.result, "QA-9": overall}

    workflow_body = (f"SAQA automated CI synchronization\nWorkflow: {run.name}\nRun: #{run.run_number} ({run.run_id})\nResult: {run.result}\nCommit: {run.head_sha}\nBranch: {run.branch}\nURL: {run.url}\nCertification aggregate for {run.head_sha}: {overall}\nNo PASS is inferred when evidence is missing.")
    with JiraClient(JiraConfig.from_env()) as client:
        project = client.verify_access()
        print(f"JIRA project verified: {project.key} / {project.name}")
        managed = ensure_managed_issues(client)
        for key, result_value in domain_results.items():
            issue = managed[key]
            marker = f"[SAQA-AUTO-SYNC:{run.run_id}:{key}]"
            sync_issue(client, key, issue, result_value, f"{workflow_body}\nDomain issue: {ISSUE_SUMMARIES[key]}\n{marker}", marker, run)


if __name__ == "__main__":
    main()
