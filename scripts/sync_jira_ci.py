#!/usr/bin/env python3
"""Synchronize verified SAQA CI evidence into the Jira QA control plane."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from saqa.analytics import analyze_records
from saqa.evidence import EvidenceRecord, utc_now
from saqa.jira import JiraClient, JiraConfig, JiraIssueResult, JiraServiceUnavailableError
from saqa.jira_sync import (
    DOMAIN_PRIORITIES,
    DOMAIN_TIMELINE_OFFSETS,
    WIB,
    _adf_heading,
    _adf_paragraph,
    _adf_status_lozenge,
    _adf_text,
    _ensure_epics_and_issues,
    _resolve_stale_auto_bugs,
    build_environment_adf,
)
from saqa.reporting import render_markdown_report
from saqa.visual_evidence import render_scorecard_png

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
MONITORED_WORKFLOWS = {"SAQA CI", "SAQA Contract Testing", "SAQA Accessibility", "SAQA Mobile Readiness", "SAQA k6 Performance"}
PASS_CONCLUSIONS = {"success"}
FAIL_CONCLUSIONS = {"failure", "timed_out"}
BLOCKED_CONCLUSIONS = {"cancelled", "action_required", "stale"}
STATUS_LABELS = {"saqa-ci-pass", "saqa-ci-fail", "saqa-ci-blocked", "saqa-ci-pending", "saqa-ci-unverified"}
VALID_EVIDENCE_STATUSES = {"PASS", "FAIL", "BLOCKED"}


def classify_run(status: str, conclusion: str) -> str:
    if status != "completed":
        return "PENDING"
    if conclusion in PASS_CONCLUSIONS:
        return "PASS"
    if conclusion in FAIL_CONCLUSIONS:
        return "FAIL"
    if conclusion in BLOCKED_CONCLUSIONS:
        return "BLOCKED"
    return "UNVERIFIED"


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
        return classify_run(self.status, self.conclusion)


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
    if conclusions & FAIL_CONCLUSIONS:
        return "FAIL"
    if conclusions & BLOCKED_CONCLUSIONS:
        return "BLOCKED"
    return "UNVERIFIED"


def aggregate_performance_result(results: dict[str, str]) -> str:
    """Reduce the two mandatory performance signals into one deterministic QA-7 state."""
    required = ("SAQA CI performance", "SAQA k6 Performance")
    values = [results.get(name, "UNVERIFIED") for name in required]
    if any(value == "FAIL" for value in values):
        return "FAIL"
    if any(value == "BLOCKED" for value in values):
        return "BLOCKED"
    if any(value == "PENDING" for value in values):
        return "PENDING"
    if all(value == "PASS" for value in values):
        return "PASS"
    return "UNVERIFIED"


def contract_evidence_result(path_value: str | None, expected_sha: str, expected_target: str = "http://127.0.0.1:3000") -> str:
    """Classify contract status from exact-SHA evidence, never from workflow conclusion."""
    if not path_value:
        return "UNVERIFIED"
    try:
        evidence = load_json(path_value, None)
        if not isinstance(evidence, dict):
            return "UNVERIFIED"
        if evidence.get("source_sha") != expected_sha:
            return "UNVERIFIED"
        if evidence.get("schema") != "saqa.contract-gate.v2":
            return "UNVERIFIED"
        if evidence.get("test_id") != "juice-shop.api.openapi-contract":
            return "UNVERIFIED"
        if evidence.get("target") != expected_target:
            return "UNVERIFIED"
        if evidence.get("http_methods") != ["GET"]:
            return "UNVERIFIED"
        if evidence.get("destructive_actions") is not False:
            return "UNVERIFIED"
        status = str(evidence.get("status", ""))
        if status not in VALID_EVIDENCE_STATUSES:
            return "UNVERIFIED"
        if status == "PASS":
            details = evidence.get("details")
            if not isinstance(details, dict):
                return "UNVERIFIED"
            if details.get("status_code") != 200:
                return "UNVERIFIED"
            if details.get("validation_errors") != []:
                return "UNVERIFIED"
        return status
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return "UNVERIFIED"

def run_label(result: str) -> str:
    """Map every supported result to exactly one Jira automation status label."""
    labels = {
        "PASS": "saqa-ci-pass",
        "FAIL": "saqa-ci-fail",
        "BLOCKED": "saqa-ci-blocked",
        "PENDING": "saqa-ci-pending",
        "UNVERIFIED": "saqa-ci-unverified",
    }
    try:
        return labels[result]
    except KeyError as exc:
        raise ValueError(f"Unsupported SAQA result: {result!r}") from exc


def certification_overall(current_results: dict[str, str], contract_result: str) -> str:
    """Aggregate release-level status while requiring verified contract evidence."""
    relevant = [current_results.get(name, "PENDING") for name in MONITORED_WORKFLOWS]
    if any(value == "FAIL" for value in relevant):
        return "FAIL"
    if any(value == "BLOCKED" for value in relevant):
        return "BLOCKED"
    if any(value == "PENDING" for value in relevant):
        return "PENDING"
    if current_results.get("SAQA Contract Testing") == "PASS" and contract_result != "PASS":
        return "UNVERIFIED"
    if all(value == "PASS" for value in relevant):
        return "PASS"
    return "UNVERIFIED"


def transition_targets(result: str) -> tuple[str, ...]:
    if result == "PASS": return ("Done", "Closed")
    if result == "FAIL": return ("In Progress", "Reopened")
    if result == "BLOCKED": return ("Blocked", "In Progress")
    return ("In Progress", "Open", "To Do")


def ensure_managed_issues(client: JiraClient) -> dict[str, JiraIssueResult]:
    """Resolve pre-bootstrapped QA issues without creating them during CI sync."""
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


def _build_ci_comment_adf(key: str, result: str, body: str, marker: str, run: RunSummary, start_date: str, due_date: str) -> dict[str, Any]:
    panel_type = "success" if result == "PASS" else ("error" if result == "FAIL" else "warning")
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "panel",
                "attrs": {"panelType": panel_type},
                "content": [
                    _adf_paragraph(
                        _adf_text(f"CI Control-Plane Sync — {key} ({ISSUE_SUMMARIES.get(key, key)})  ", bold=True),
                        _adf_status_lozenge(result),
                    ),
                    _adf_paragraph(
                        _adf_text("Workflow: ", bold=True),
                        _adf_text(f"{run.name} #{run.run_number}", code=True),
                        _adf_text(" | Commit: ", bold=True),
                        _adf_text(run.head_sha[:12], code=True),
                        _adf_text(" | Timeline: ", bold=True),
                        _adf_text(f"{start_date} -> {due_date}", code=True),
                    ),
                ],
            },
            _adf_heading(4, "CI Evidence Details"),
            {"type": "codeBlock", "attrs": {"language": "text"}, "content": [_adf_text(body)]},
            _adf_paragraph(_adf_text(marker, code=True)),
        ],
    }


def sync_issue(
    client: JiraClient,
    key: str,
    issue: JiraIssueResult,
    result: str,
    body: str,
    marker: str,
    run: RunSummary,
    *,
    epic_key: str | None = None,
    assignee_id: str | None = None,
) -> None:
    state = client.get_issue_state(issue.key)
    label = run_label(result)
    remove = tuple(existing for existing in STATUS_LABELS if existing in state.labels and existing != label)
    add = tuple(label_name for label_name in ("saqa-automation", f"saqa-{key.lower()}", label) if label_name not in state.labels)
    if add or remove:
        client.update_labels(issue.key, add=add, remove=remove)

    today = datetime.now(WIB)
    start_off, due_off = DOMAIN_TIMELINE_OFFSETS.get(key, (-7, 7))
    start_date = (today + timedelta(days=start_off)).strftime("%Y-%m-%d")
    due_date = (today + timedelta(days=due_off)).strftime("%Y-%m-%d")

    if hasattr(client, "update_issue_fields"):
        priority_name = "Highest" if result == "FAIL" else DOMAIN_PRIORITIES.get(key, "High")
        fields_payload: dict[str, Any] = {
            "customfield_10015": start_date,
            "duedate": due_date,
            "priority": {"name": priority_name},
            "environment": build_environment_adf(
                target_display=run.url or f"github:{run.branch}",
                suite_name=run.name,
                manifest_sha256=run.head_sha,
            ),
        }
        if epic_key:
            fields_payload["parent"] = {"key": epic_key}
        if assignee_id:
            fields_payload["assignee"] = {"accountId": assignee_id}
        client.update_issue_fields(issue.key, fields_payload)

    if hasattr(client, "add_adf_comment_once"):
        comment_adf = _build_ci_comment_adf(key, result, body, marker, run, start_date, due_date)
        added = client.add_adf_comment_once(issue.key, comment_adf, marker)
    else:
        added = client.add_comment_once(issue.key, body, marker)

    transitioned = client.transition_to_any(issue.key, transition_targets(result))
    defect = create_failure_bug_once(client, key, issue, run, result, body)
    resolved_bugs = []
    if result == "PASS":
        resolved_bugs = _resolve_stale_auto_bugs(
            client,
            domain_key=key,
            suite_name=run.name,
            manifest_sha256=run.head_sha,
            today_str=today.strftime("%Y-%m-%d"),
        )
    print(
        f"JIRA {key} ({issue.key}): result={result} timeline={start_date}..{due_date} "
        f"comment={'added' if added else 'exists'} transition={transitioned or 'unchanged'} "
        f"defect={defect.key if defect else 'none'} resolved_bugs={len(resolved_bugs)}"
    )


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
    performance_records = load_json(os.environ.get("JIRA_PERFORMANCE_JSON"), {})
    current_results: dict[str, str] = {}
    current_run_ids: dict[str, int] = {}
    for item in all_runs:
        if item.head_sha != run.head_sha:
            continue
        run_id = int(item.run_id or 0)
        if run_id > current_run_ids.get(item.name, -1):
            current_results[item.name] = item.result
            current_run_ids[item.name] = run_id
    api_ci_result = current_results.get("SAQA CI", "PENDING")
    api_contract_result = current_results.get("SAQA Contract Testing", "UNVERIFIED")
    evidence_path = os.environ.get("JIRA_CONTRACT_EVIDENCE_JSON")
    if run.name == "SAQA Contract Testing":
        api_contract_result = contract_evidence_result(evidence_path, run.head_sha)
    elif evidence_path:
        api_contract_result = contract_evidence_result(evidence_path, run.head_sha)
    api_results = (api_ci_result, api_contract_result)
    if "FAIL" in api_results:
        api_overall = "FAIL"
    elif "BLOCKED" in api_results:
        api_overall = "BLOCKED"
    elif all(value == "PASS" for value in api_results):
        api_overall = "PASS"
    elif "PENDING" in api_results:
        api_overall = "PENDING"
    else:
        api_overall = "UNVERIFIED"

    overall = certification_overall(current_results, api_contract_result)

    performance_result = aggregate_performance_result({
        "SAQA CI performance": str(performance_records.get("SAQA CI performance", "UNVERIFIED")),
        "SAQA k6 Performance": str(performance_records.get("SAQA k6 Performance", "UNVERIFIED")),
    })
    if run.name == "SAQA CI":
        domain_results = {
            "QA-1": "PASS",
            "QA-2": job_result(jobs, ("Juice Shop E2E", "WebGoat E2E")),
            "QA-3": job_result(jobs, ("Browser readiness", "Juice Shop E2E", "WebGoat E2E")),
            "QA-4": api_overall,
            "QA-5": job_result(
                jobs,
                (
                    "Dependency, SBOM, and secret hygiene",
                    "Dependency and secret hygiene",
                    "Target authorization policy",
                    "Docker authorized target smoke",
                ),
            ),
            "QA-7": performance_result,
            "QA-8": job_result(jobs, ("Canonical evidence aggregation",)),
            "QA-9": overall,
        }
    elif run.name == "SAQA Contract Testing":
        domain_results = {"QA-1": "PASS", "QA-4": api_overall, "QA-9": overall}
    elif run.name == "SAQA Accessibility":
        domain_results = {"QA-1": "PASS", "QA-3": run.result, "QA-6": run.result, "QA-9": overall}
    elif run.name == "SAQA k6 Performance":
        domain_results = {"QA-1": "PASS", "QA-7": performance_result, "QA-9": overall}
    else:
        domain_results = {"QA-1": "PASS", "QA-3": run.result, "QA-9": overall}

    workflow_body = (f"SAQA automated CI synchronization\nWorkflow: {run.name}\nRun: #{run.run_number} ({run.run_id})\nResult: {run.result}\nCommit: {run.head_sha}\nBranch: {run.branch}\nURL: {run.url}\nCertification aggregate for {run.head_sha}: {overall}\nNo PASS is inferred when evidence is missing.")
    fail_on_unavailable = os.environ.get("SAQA_JIRA_FAIL_ON_UNAVAILABLE", "true").strip().lower() not in {"0", "false", "no"}
    try:
        with JiraClient(JiraConfig.from_env()) as client:
            project = client.verify_access()
            print(f"JIRA project verified: {project.key} / {project.name}")
            managed = ensure_managed_issues(client)
            today = datetime.now(WIB)
            assignee_id = client.get_myself_account_id() if hasattr(client, "get_myself_account_id") else None
            _, epic_key_by_domain, _ = _ensure_epics_and_issues(client, today=today, assignee_id=assignee_id)
            for key, result_value in domain_results.items():
                issue = managed[key]
                marker = f"[SAQA-AUTO-SYNC:{run.run_id}:{key}]"
                sync_issue(
                    client,
                    key,
                    issue,
                    result_value,
                    f"{workflow_body}\nDomain issue: {ISSUE_SUMMARIES[key]}\n{marker}",
                    marker,
                    run,
                    epic_key=epic_key_by_domain.get(key),
                    assignee_id=assignee_id,
                )

            # Attach visual CI scorecard PNG and Markdown executive report to QA-1, QA-8, QA-9
            if hasattr(client, "upload_attachment"):
                ci_records = [
                    EvidenceRecord(
                        test_id=f"{dom}-{ISSUE_SUMMARIES[dom]}",
                        status=res if res in {"PASS", "FAIL", "BLOCKED", "UNVERIFIED"} else "UNVERIFIED",
                        observed_at=utc_now(),
                        target=run.url or f"https://github.com/commit/{run.head_sha}",
                        details={"workflow": run.name, "commit_sha": run.head_sha, "elapsed_ms": 100.0},
                    )
                    for dom, res in sorted(domain_results.items())
                ]
                ci_analytics = analyze_records(ci_records, manifest_sha256=run.head_sha)
                with tempfile.TemporaryDirectory(prefix="saqa-ci-jira-") as tmp_dir:
                    scorecard_png = render_scorecard_png(
                        ci_analytics,
                        ci_records,
                        Path(tmp_dir) / "qa-ci-scorecard.png",
                        title=f"SAQA CI | {run.name}",
                    )
                    ci_md = Path(tmp_dir) / "qa-ci-report.md"
                    ci_md.write_text(
                        render_markdown_report(ci_analytics, title=f"SAQA CI Report — {run.name} ({run.head_sha[:7]})"),
                        encoding="utf-8",
                    )
                    for attach_key in ("QA-1", "QA-8", "QA-9"):
                        if attach_key in managed:
                            client.upload_attachment(managed[attach_key].key, scorecard_png)
                            client.upload_attachment(managed[attach_key].key, ci_md)
    except JiraServiceUnavailableError as exc:
        diagnostic = {
            "status": "BLOCKED",
            "reason": str(exc),
            "http_status": exc.status_code,
            "jira_url": exc.url,
            "workflow": run.name,
            "commit_sha": run.head_sha,
            "action_required": "Reactivate the Atlassian Cloud Jira site or update repository variable JIRA_BASE_URL.",
        }
        print(json.dumps(diagnostic, indent=2))
        print(f"::warning title=Jira Cloud Unavailable (BLOCKED)::{exc}")
        summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_file:
            with Path(summary_file).open("a", encoding="utf-8") as handle:
                handle.write(
                    "### Jira QA Synchronization: `BLOCKED`\n\n"
                    f"- **Reason:** `{exc}`\n"
                    f"- **Workflow / Commit:** `{run.name}` (`{run.head_sha[:12]}`)\n"
                    "- **Action Required:** Reactivate the Atlassian Cloud site or set repository variable `JIRA_BASE_URL`.\n"
                    "- **Certification Note:** Jira sync did not succeed and is recorded as `BLOCKED`, never `PASS`.\n"
                )
        if fail_on_unavailable:
            raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
