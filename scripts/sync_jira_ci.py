#!/usr/bin/env python3
"""Synchronize authorized SAQA CI results into the Jira QA control plane.

The script is intentionally idempotent: every CI run gets one deterministic
Jira comment marker, and status transitions are attempted only when Jira
exposes an exact matching transition. It never fabricates PASS from missing
GitHub evidence.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from saqa.jira import JiraClient, JiraConfig


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
    return [
        RunSummary(
            name=str(item.get("name", "")),
            run_id=str(item.get("id", "")),
            run_number=str(item.get("run_number", "")),
            conclusion=str(item.get("conclusion") or ""),
            status=str(item.get("status") or ""),
            head_sha=str(item.get("head_sha", "")),
            branch=str(item.get("head_branch", "")),
            url=str(item.get("html_url", "")),
        )
        for item in raw
        if item.get("name") in MONITORED_WORKFLOWS and item.get("id")
    ]


def job_result(jobs: list[dict[str, Any]], patterns: tuple[str, ...]) -> str:
    matched = [j for j in jobs if any(pattern.casefold() in str(j.get("name", "")).casefold() for pattern in patterns)]
    if not matched:
        return "UNVERIFIED"
    if any(j.get("status") != "completed" for j in matched):
        return "PENDING"
    conclusions = {str(j.get("conclusion") or "") for j in matched}
    if conclusions == {"success"}:
        return "PASS"
    if conclusions & {"failure", "timed_out"}:
        return "FAIL"
    if conclusions & {"cancelled", "action_required"}:
        return "BLOCKED"
    return "UNVERIFIED"


def run_label(result: str) -> str:
    return {
        "PASS": "saqa-ci-pass",
        "FAIL": "saqa-ci-fail",
        "BLOCKED": "saqa-ci-blocked",
        "PENDING": "saqa-ci-pending",
        "UNVERIFIED": "saqa-ci-unverified",
    }[result]


def transition_targets(result: str) -> tuple[str, ...]:
    if result == "PASS":
        return ("Done", "Closed")
    if result == "FAIL":
        return ("In Progress", "Reopened")
    if result == "BLOCKED":
        return ("Blocked", "In Progress")
    return ("In Progress", "Open", "To Do")


def sync_issue(client: JiraClient, key: str, result: str, body: str, marker: str) -> None:
    state = client.get_issue_state(key)
    status_labels = {"saqa-ci-pass", "saqa-ci-fail", "saqa-ci-blocked", "saqa-ci-pending", "saqa-ci-unverified"}
    client.update_labels(
        key,
        add=("saqa-automation", run_label(result)),
        remove=(label for label in status_labels if label in state.labels and label != run_label(result)),
    )
    added = client.add_comment_once(key, body, marker)
    transitioned = client.transition_to_any(key, transition_targets(result))
    print(f"JIRA {key}: result={result} comment={'added' if added else 'exists'} transition={transitioned or 'unchanged'}")


def main() -> None:
    run = RunSummary(
        name=os.environ["JIRA_WORKFLOW_NAME"],
        run_id=os.environ["JIRA_RUN_ID"],
        run_number=os.environ.get("JIRA_RUN_NUMBER", ""),
        conclusion=os.environ.get("JIRA_RUN_CONCLUSION", ""),
        status=os.environ.get("JIRA_RUN_STATUS", ""),
        head_sha=os.environ["JIRA_HEAD_SHA"],
        branch=os.environ.get("JIRA_HEAD_BRANCH", ""),
        url=os.environ.get("JIRA_RUN_URL", ""),
    )
    jobs = load_json(os.environ.get("JIRA_JOBS_JSON"), [])
    all_runs = normalize_runs(load_json(os.environ.get("JIRA_ALL_RUNS_JSON"), []))

    overall = "UNVERIFIED"
    current_results = {item.name: item.result for item in all_runs if item.head_sha == run.head_sha}
    relevant = [current_results.get(name, "PENDING") for name in MONITORED_WORKFLOWS]
    if any(value == "FAIL" for value in relevant):
        overall = "FAIL"
    elif any(value == "BLOCKED" for value in relevant):
        overall = "BLOCKED"
    elif all(value == "PASS" for value in relevant):
        overall = "PASS"
    elif any(value == "PENDING" for value in relevant):
        overall = "PENDING"

    domain_results = {
        "QA-1": run.result,
        "QA-2": job_result(jobs, ("Juice Shop", "WebGoat")) if run.name == "SAQA CI" else run.result,
        "QA-3": run.result,
        "QA-4": job_result(jobs, ("Juice Shop API",)) if run.name == "SAQA CI" else run.result,
        "QA-5": job_result(jobs, ("Dependency & secret hygiene", "Target authorization", "Docker authorized")) if run.name == "SAQA CI" else run.result,
        "QA-6": run.result if run.name == "SAQA Accessibility" else "UNVERIFIED",
        "QA-7": job_result(jobs, ("Juice Shop performance",)) if run.name == "SAQA CI" else "UNVERIFIED",
        "QA-8": job_result(jobs, ("Canonical evidence aggregation",)) if run.name == "SAQA CI" else run.result,
        "QA-9": overall,
    }

    workflow_body = (
        f"SAQA automated CI synchronization\n"
        f"Workflow: {run.name}\n"
        f"Run: #{run.run_number} ({run.run_id})\n"
        f"Result: {run.result}\n"
        f"Commit: {run.head_sha}\n"
        f"Branch: {run.branch}\n"
        f"URL: {run.url}\n"
        f"Certification aggregate for {run.head_sha}: {overall}\n"
        f"No PASS is inferred when evidence is missing."
    )

    with JiraClient(JiraConfig.from_env()) as client:
        client.verify_access()
        existing = client.find_bootstrap_issues()
        missing = [key for key in ISSUE_SUMMARIES if ISSUE_SUMMARIES[key] not in existing]
        if missing:
            raise RuntimeError("Jira bootstrap items missing: " + ", ".join(missing))
        for key, result in domain_results.items():
            if result == "UNVERIFIED" and key != "QA-9":
                continue
            marker = f"[SAQA-AUTO-SYNC:{run.run_id}:{key}]"
            sync_issue(client, key, result, f"{workflow_body}\nDomain issue: {ISSUE_SUMMARIES[key]}\n{marker}", marker)


if __name__ == "__main__":
    main()
