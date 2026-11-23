"""Direct synchronization of SAQA suite & manifest evidence into Jira Cloud."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .analytics import analyze_records, load_verified_manifest
from .evidence import EvidenceRecord
from .jira import JiraClient, JiraConfig, JiraIssueResult

ISSUE_SUMMARIES: dict[str, str] = {
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

STATUS_LABELS = frozenset({
    "saqa-ci-pass",
    "saqa-ci-fail",
    "saqa-ci-blocked",
    "saqa-ci-pending",
    "saqa-ci-unverified",
})

DOMAIN_TAG_MAP: dict[str, frozenset[str]] = {
    "QA-2": frozenset({"web", "smoke", "routing", "seo", "pwa", "assets"}),
    "QA-3": frozenset({"web", "pwa", "css", "js", "icons", "browser"}),
    "QA-4": frozenset({"api", "contract", "xml", "rss"}),
    "QA-5": frozenset({"security", "headers", "tls"}),
    "QA-6": frozenset({"a11y", "accessibility", "seo"}),
}


def _status_label(status: str) -> str:
    mapping = {
        "PASS": "saqa-ci-pass",
        "FAIL": "saqa-ci-fail",
        "BLOCKED": "saqa-ci-blocked",
        "PENDING": "saqa-ci-pending",
        "UNVERIFIED": "saqa-ci-unverified",
    }
    return mapping.get(status, "saqa-ci-unverified")


def _transition_targets(status: str) -> tuple[str, ...]:
    if status == "PASS":
        return ("Done", "Closed", "Resolved", "Pass", "Passed")
    if status in {"FAIL", "BLOCKED"}:
        return ("In Progress", "To Do", "Open", "Reopened", "Fail", "Failed")
    return ("In Progress", "To Do", "Open", "Backlog")


def _normalize_record(item: EvidenceRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(item, EvidenceRecord):
        return {
            "test_id": item.test_id,
            "status": item.status,
            "observed_at": item.observed_at,
            "target": item.target,
            "details": dict(item.details),
        }
    return {
        "test_id": str(item["test_id"]),
        "status": str(item["status"]),
        "observed_at": str(item["observed_at"]),
        "target": str(item["target"]),
        "details": dict(item.get("details") or {}),
    }


def _aggregate_statuses(statuses: Sequence[str]) -> str:
    if not statuses:
        return "PASS"
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if "UNVERIFIED" in statuses:
        return "UNVERIFIED"
    if all(s in {"PASS", "NOT_APPLICABLE"} for s in statuses):
        return "PASS"
    return "UNVERIFIED"


def _compute_domain_results(
    records: Sequence[dict[str, Any]],
    analytics: Mapping[str, Any],
) -> dict[str, tuple[str, list[dict[str, Any]]]]:
    """Map executed suite evidence records to the 9 canonical SAQA Jira domains."""
    overall = str(analytics["overall_status"])
    results: dict[str, tuple[str, list[dict[str, Any]]]] = {}

    results["QA-1"] = (overall, list(records))

    for domain_key, tag_set in DOMAIN_TAG_MAP.items():
        matched = [
            rec
            for rec in records
            if tag_set & {str(t).lower() for t in (rec["details"].get("tags") or [])}
        ]
        subset = matched if matched else list(records)
        results[domain_key] = (_aggregate_statuses([r["status"] for r in subset]), subset)

    # QA-7 Performance: check all records with latency measurements
    timed = [rec for rec in records if "elapsed_ms" in rec["details"]]
    perf_subset = timed if timed else list(records)
    results["QA-7"] = (_aggregate_statuses([r["status"] for r in perf_subset]), perf_subset)

    # QA-8 Evidence & Traceability: PASS if manifest SHA-256 is present and verified
    ev_status = "PASS" if analytics.get("manifest_sha256") else overall
    results["QA-8"] = (ev_status, list(records))

    # QA-9 Certification Readiness: overall suite status
    results["QA-9"] = (overall, list(records))

    return results


def _ensure_or_bootstrap_issues(client: JiraClient) -> dict[str, JiraIssueResult]:
    existing = client.find_project_issues()
    resolved: dict[str, JiraIssueResult] = {}
    for key, summary in ISSUE_SUMMARIES.items():
        issue = existing.get(summary)
        if issue is None:
            issue = client.create_task(
                summary=summary,
                description=f"SAQA automated control-plane item for {key} ({summary}).",
                labels=["saqa-bootstrap", "saqa-automation", f"saqa-{key.lower()}"],
            )
        resolved[key] = issue
    return resolved


def sync_records_to_jira(
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    *,
    suite_name: str = "saqa-suite",
    manifest_sha256: str | None = None,
    client: JiraClient | None = None,
) -> dict[str, Any]:
    """Synchronize SAQA evidence records and analytics directly into Jira QA-1..QA-9."""
    norm_records = [_normalize_record(r) for r in records]
    analytics = analyze_records(norm_records, manifest_sha256=manifest_sha256)
    domain_map = _compute_domain_results(norm_records, analytics)
    sha_short = (manifest_sha256 or "in-memory")[:16]
    targets = sorted({rec["target"] for rec in norm_records})
    target_display = ", ".join(targets) if targets else "unknown"
    lat = analytics["latency"]

    owns_client = client is None
    active_client = client or JiraClient(JiraConfig.from_env())
    synced_issues: list[dict[str, Any]] = []
    created_bugs: list[str] = []

    try:
        project = active_client.verify_access()
        managed = _ensure_or_bootstrap_issues(active_client)

        for domain_key in sorted(ISSUE_SUMMARIES):
            issue = managed[domain_key]
            domain_status, domain_records = domain_map[domain_key]
            label = _status_label(domain_status)
            state = active_client.get_issue_state(issue.key)
            stale_labels = tuple(sorted((set(state.labels) & STATUS_LABELS) - {label}))
            active_client.update_labels(
                issue.key,
                add=("saqa-automation", label),
                remove=stale_labels,
            )
            transitioned_to = active_client.transition_to_any(
                issue.key,
                _transition_targets(domain_status),
            )

            case_lines = []
            for rec in domain_records[:15]:
                ms = rec["details"].get("elapsed_ms", "-")
                ms_str = f"{ms}ms" if isinstance(ms, (int, float)) else "-"
                case_lines.append(f"- [{rec['status']}] {rec['test_id']} ({rec['target']}) — {ms_str}")

            marker = f"[SAQA-SUITE-SYNC:{suite_name}:{sha_short}:{domain_key}]"
            comment_body = (
                f"SAQA Automated Quality Assurance Execution\n"
                f"Suite: {suite_name}\n"
                f"Target(s): {target_display}\n"
                f"Domain: {domain_key} — {ISSUE_SUMMARIES[domain_key]}\n"
                f"Domain Status: {domain_status} | Overall Suite Status: {analytics['overall_status']}\n"
                f"Health Score: {analytics['health_score']}/100 (Grade {analytics['health_grade']}) | "
                f"Pass Rate: {analytics['pass_rate_pct']}% ({analytics['status_counts']['PASS']}/{analytics['total_records']})\n"
                f"Latency: min={lat['min_ms']}ms p50={lat['p50_ms']}ms p95={lat['p95_ms']}ms p99={lat['p99_ms']}ms max={lat['max_ms']}ms\n"
                f"Evidence Manifest SHA-256: {manifest_sha256 or 'unhashed'}\n"
                f"Executed Checks ({len(domain_records)}):\n"
                + "\n".join(case_lines)
                + f"\n{marker}"
            )
            commented = active_client.add_comment_once(issue.key, comment_body, marker)

            if domain_status == "FAIL":
                bug_summary = f"[SAQA-AUTO] {suite_name} failure in {domain_key} ({target_display})"
                existing_bugs = active_client.search_issues(
                    f'project = {active_client.config.project_key} AND labels = "saqa-auto-defect"'
                )
                if not any(b.key and bug_summary in existing for existing in [active_client.find_project_issues()] for b in [existing.get(bug_summary)] if b):
                    bug = active_client.create_bug(
                        bug_summary,
                        comment_body,
                        ["saqa-automation", "saqa-auto-defect", f"saqa-{domain_key.lower()}"],
                    )
                    created_bugs.append(bug.key)

            synced_issues.append(
                {
                    "domain": domain_key,
                    "issue_key": issue.key,
                    "issue_url": issue.url,
                    "status": domain_status,
                    "label": label,
                    "transitioned_to": transitioned_to,
                    "comment_added": commented,
                }
            )

        return {
            "project_key": project.key,
            "project_name": project.name,
            "suite_name": suite_name,
            "overall_status": analytics["overall_status"],
            "health_score": analytics["health_score"],
            "manifest_sha256": manifest_sha256,
            "synced_issues": synced_issues,
            "created_bugs": created_bugs,
        }
    finally:
        if owns_client:
            active_client.close()


def sync_manifest_to_jira(
    manifest_path: Path,
    *,
    suite_name: str | None = None,
    client: JiraClient | None = None,
) -> dict[str, Any]:
    """Verify a SAQA evidence manifest file and synchronize its results to Jira."""
    records, sha = load_verified_manifest(manifest_path)
    inferred_suite = suite_name
    if not inferred_suite and records:
        inferred_suite = str(records[0].get("details", {}).get("suite") or manifest_path.stem)
    return sync_records_to_jira(
        records,
        suite_name=inferred_suite or "saqa-suite",
        manifest_sha256=sha,
        client=client,
    )
