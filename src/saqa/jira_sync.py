"""Enterprise Jira Cloud synchronization with Timeline Epics, Rich ADF Tables, and Report Attachments."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from . import __version__
from .analytics import analyze_records, load_verified_manifest
from .evidence import EvidenceRecord
from .jira import JiraClient, JiraConfig, JiraIssueResult
from .reporting import render_html_report, render_markdown_report
from .visual_evidence import (
    capture_web_screenshot,
    export_csv_matrix,
    render_analytics_svg,
    render_scorecard_png,
)

WIB = timezone(timedelta(hours=7))

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

DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "QA-1": "Master QA control-plane governance, declarative suite orchestration, test inventory, and release readiness.",
    "QA-2": "End-to-end Web functional verification, routing, TLS redirects, DOM integrity, and user journey validation.",
    "QA-3": "Cross-browser & multi-viewport compatibility matrix across Chromium, Firefox, WebKit, and PWA assets.",
    "QA-4": "REST API & Web Manifest contract validation, JSON schema enforcement, XML/RSS feed integrity, and status gates.",
    "QA-5": "Application security regression gate: CSP, HSTS, X-Frame-Options, XCTO, COOP, CORP, Permissions-Policy, and safe target scope.",
    "QA-6": "Web accessibility readiness (WCAG 2.2 semantic landmarks, HTML lang, headings, metadata, and axe-core oracle correlation).",
    "QA-7": "Performance & SLA latency quality gate across min, mean, median (P50), P90, P95, P99, and maximum response time budgets.",
    "QA-8": "Cryptographic SHA-256 evidence manifest verification, tamper-evident artifact retention, and execution provenance.",
    "QA-9": "Final fail-closed release certification gate aggregating all mandatory quality engineering domains.",
}

DOMAIN_PRIORITIES: dict[str, str] = {
    "QA-1": "Highest",
    "QA-2": "High",
    "QA-3": "High",
    "QA-4": "High",
    "QA-5": "Highest",
    "QA-6": "High",
    "QA-7": "High",
    "QA-8": "Highest",
    "QA-9": "Highest",
}

EPIC_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "phase_id": "PHASE-1",
        "summary": "SAQA Epic | Phase 1 — Core Foundation, Web & Cross-Browser QE",
        "description": "Phase 1 QA Roadmap covering Test Management Governance (QA-1), Web E2E Automation (QA-2), and Cross-Browser Matrix (QA-3).",
        "domains": ("QA-1", "QA-2", "QA-3"),
        "start_offset_days": -21,
        "end_offset_days": -11,
        "labels": ["saqa-epic", "saqa-phase-1", "saqa-automation"],
    },
    {
        "phase_id": "PHASE-2",
        "summary": "SAQA Epic | Phase 2 — API Contract, Security & Accessibility Gates",
        "description": "Phase 2 QA Roadmap covering API & Manifest Contract Validation (QA-4), Security Headers & Regression Gate (QA-5), and Accessibility Gate (QA-6).",
        "domains": ("QA-4", "QA-5", "QA-6"),
        "start_offset_days": -14,
        "end_offset_days": -4,
        "labels": ["saqa-epic", "saqa-phase-2", "saqa-automation"],
    },
    {
        "phase_id": "PHASE-3",
        "summary": "SAQA Epic | Phase 3 — Performance, Evidence Traceability & Release Certification",
        "description": "Phase 3 QA Roadmap covering Performance Latency SLAs (QA-7), SHA-256 Evidence Traceability (QA-8), and Final Release Certification (QA-9).",
        "domains": ("QA-7", "QA-8", "QA-9"),
        "start_offset_days": -7,
        "end_offset_days": 7,
        "labels": ["saqa-epic", "saqa-phase-3", "saqa-automation"],
    },
)

# Staggered timeline offsets (start_offset_days, due_offset_days) relative to execution date
DOMAIN_TIMELINE_OFFSETS: dict[str, tuple[int, int]] = {
    "QA-1": (-21, -15),
    "QA-2": (-18, -13),
    "QA-3": (-15, -11),
    "QA-4": (-14, -9),
    "QA-5": (-11, -6),
    "QA-6": (-8, -4),
    "QA-7": (-7, -2),
    "QA-8": (-4, 2),
    "QA-9": (-2, 7),
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


def _adf_text(text: str, *, bold: bool = False, code: bool = False) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": str(text)}
    marks = []
    if bold:
        marks.append({"type": "strong"})
    if code:
        marks.append({"type": "code"})
    if marks:
        node["marks"] = marks
    return node


def _adf_status_lozenge(status: str) -> dict[str, Any]:
    color_map = {
        "PASS": "green",
        "CERTIFIED": "green",
        "A": "green",
        "B": "blue",
        "FAIL": "red",
        "BLOCKED": "yellow",
        "PENDING": "yellow",
        "UNVERIFIED": "purple",
    }
    return {
        "type": "status",
        "attrs": {
            "text": str(status),
            "color": color_map.get(str(status).upper(), "neutral"),
        },
    }


def _adf_paragraph(*inline_nodes: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(inline_nodes)}


def _adf_heading(level: int, text: str) -> dict[str, Any]:
    return {"type": "heading", "attrs": {"level": level}, "content": [_adf_text(text)]}


def _adf_cell(content_nodes: list[dict[str, Any]], *, header: bool = False) -> dict[str, Any]:
    return {
        "type": "tableHeader" if header else "tableCell",
        "attrs": {},
        "content": content_nodes,
    }


def _adf_row(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "tableRow", "content": cells}


def build_domain_adf_document(
    *,
    domain_key: str,
    domain_status: str,
    domain_records: Sequence[dict[str, Any]],
    analytics: Mapping[str, Any],
    suite_name: str,
    target_display: str,
    manifest_sha256: str | None,
    start_date: str,
    due_date: str,
    epic_key: str | None,
    attached_files: Sequence[str] = (),
    marker: str | None = None,
) -> dict[str, Any]:
    """Build a rich enterprise Atlassian Document Format (ADF) report for Jira."""
    now_utc = datetime.now(timezone.utc)
    now_wib = now_utc.astimezone(WIB)
    lat = analytics["latency"]
    counts = analytics["status_counts"]
    panel_type = "success" if domain_status == "PASS" else ("error" if domain_status == "FAIL" else "warning")

    banner_panel = {
        "type": "panel",
        "attrs": {"panelType": panel_type},
        "content": [
            _adf_paragraph(
                _adf_text(f"{domain_key} — {ISSUE_SUMMARIES[domain_key]}  ", bold=True),
                _adf_status_lozenge(domain_status),
                _adf_text("   |   Health Grade: ", bold=True),
                _adf_status_lozenge(f"{analytics['health_score']}/100 ({analytics['health_grade']})"),
            ),
            _adf_paragraph(
                _adf_text(DOMAIN_DESCRIPTIONS.get(domain_key, "")),
            ),
        ],
    }

    kpi_rows = [
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text("Metric / Governance Field", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Observed Value", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Metric / SLA Benchmark", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Observed Value", bold=True))], header=True),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text("QA Suite Name", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(suite_name, code=True))]),
            _adf_cell([_adf_paragraph(_adf_text("Domain Gate Status", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_status_lozenge(domain_status))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text("Target Endpoint(s)", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(target_display, code=True))]),
            _adf_cell([_adf_paragraph(_adf_text("Suite Health Score", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{analytics['health_score']} / 100 (Grade {analytics['health_grade']})", bold=True))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text("Timeline Schedule", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{start_date}  ->  {due_date}", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text("Suite Pass Rate", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{analytics['pass_rate_pct']}% ({counts['PASS']} PASS / {counts['FAIL']} FAIL / {counts['BLOCKED']} BLOCKED)"))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text("Parent Roadmap Epic", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(epic_key or "Standalone", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text("Latency (Min / P50 / Mean)", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{lat['min_ms']} ms / {lat['p50_ms']} ms / {lat['mean_ms']} ms", code=True))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text("Executed At (WIB / UTC)", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{now_wib.strftime('%Y-%m-%d %H:%M:%S WIB')} ({now_utc.strftime('%H:%M:%S UTC')})", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text("Latency (P95 / P99 / Max)", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{lat['p95_ms']} ms / {lat['p99_ms']} ms / {lat['max_ms']} ms", code=True))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text("Evidence SHA-256 Digest", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(manifest_sha256 or "unhashed-in-memory", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text("Framework Engine", bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"SAQA Professional Framework v{__version__}", code=True))]),
        ]),
    ]

    kpi_table = {
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
        "content": kpi_rows,
    }

    test_rows = [
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text("#", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Test ID", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Scenario & Quality Check", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Target", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("HTTP", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Latency", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Verified Assertions", bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text("Status", bold=True))], header=True),
        ])
    ]

    for idx, rec in enumerate(domain_records, start=1):
        det = rec["details"]
        case_name = str(det.get("case_name") or rec["test_id"])
        method = str(det.get("http_method") or (det.get("http_methods") or ["GET"])[0])
        code = det.get("status_code", 200)
        elapsed = det.get("elapsed_ms", det.get("duration_ms", "-"))
        elapsed_str = f"{elapsed} ms" if isinstance(elapsed, (int, float)) else "-"
        checks = det.get("checks_passed") or []
        failures = det.get("failure_reasons") or []
        if failures:
            assertions_str = "FAIL: " + "; ".join(str(f) for f in failures)
        elif checks:
            assertions_str = f"{len(checks)} passed ({', '.join(str(c) for c in checks[:4])})"
        else:
            assertions_str = "Verified"

        test_rows.append(
            _adf_row([
                _adf_cell([_adf_paragraph(_adf_text(str(idx)))]),
                _adf_cell([_adf_paragraph(_adf_text(rec["test_id"], code=True))]),
                _adf_cell([_adf_paragraph(_adf_text(case_name))]),
                _adf_cell([_adf_paragraph(_adf_text(rec["target"], code=True))]),
                _adf_cell([_adf_paragraph(_adf_text(f"{method} ({code})", code=True))]),
                _adf_cell([_adf_paragraph(_adf_text(elapsed_str, code=True))]),
                _adf_cell([_adf_paragraph(_adf_text(assertions_str))]),
                _adf_cell([_adf_paragraph(_adf_status_lozenge(rec["status"]))]),
            ])
        )

    test_table = {
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
        "content": test_rows,
    }

    rec_items = []
    for rec_text in analytics.get("recommendations", []):
        rec_items.append({"type": "listItem", "content": [_adf_paragraph(_adf_text(rec_text))]})
    if attached_files:
        rec_items.append({
            "type": "listItem",
            "content": [
                _adf_paragraph(
                    _adf_text("Attached Audit Reports & Evidence Artifacts: ", bold=True),
                    _adf_text(", ".join(attached_files), code=True),
                )
            ],
        })

    content: list[dict[str, Any]] = [
        banner_panel,
        _adf_heading(3, "1. Executive Quality & Governance Summary"),
        kpi_table,
        _adf_heading(3, f"2. Automated Test Execution Matrix ({len(domain_records)} Scenarios)"),
        test_table,
        _adf_heading(3, "3. Audit Findings, Evidence & Recommendations"),
        {"type": "bulletList", "content": rec_items or [{"type": "listItem", "content": [_adf_paragraph(_adf_text("All quality gates satisfied."))]}]},
    ]

    if marker:
        content.append(_adf_paragraph(_adf_text(marker, code=True)))

    return {"type": "doc", "version": 1, "content": content}


def build_environment_adf(
    *,
    target_display: str,
    suite_name: str,
    manifest_sha256: str | None,
) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            _adf_paragraph(
                _adf_text("Target: ", bold=True),
                _adf_text(target_display, code=True),
                _adf_text(" | Suite: ", bold=True),
                _adf_text(suite_name, code=True),
                _adf_text(" | Engine: ", bold=True),
                _adf_text(f"SAQA v{__version__}", code=True),
                _adf_text(" | Evidence SHA-256: ", bold=True),
                _adf_text((manifest_sha256 or "in-memory")[:24], code=True),
            )
        ],
    }


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

    timed = [rec for rec in records if "elapsed_ms" in rec["details"]]
    perf_subset = timed if timed else list(records)
    results["QA-7"] = (_aggregate_statuses([r["status"] for r in perf_subset]), perf_subset)

    ev_status = "PASS" if analytics.get("manifest_sha256") else overall
    results["QA-8"] = (ev_status, list(records))

    results["QA-9"] = (overall, list(records))

    return results


def _ensure_epics_and_issues(
    client: JiraClient,
    *,
    today: datetime,
    assignee_id: str | None,
) -> tuple[dict[str, JiraIssueResult], dict[str, str], dict[str, JiraIssueResult]]:
    """Ensure 3 Phase Epics and 9 Domain Tasks exist, returning (issues_by_domain, epic_key_by_domain, epics_by_phase)."""
    existing = client.find_project_issues()
    epics_by_phase: dict[str, JiraIssueResult] = {}
    epic_key_by_domain: dict[str, str] = {}

    if hasattr(client, "create_epic"):
        for epic_def in EPIC_DEFINITIONS:
            summary = epic_def["summary"]
            start_d = (today + timedelta(days=int(epic_def["start_offset_days"]))).strftime("%Y-%m-%d")
            due_d = (today + timedelta(days=int(epic_def["end_offset_days"]))).strftime("%Y-%m-%d")
            desc_adf = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "panel",
                        "attrs": {"panelType": "info"},
                        "content": [_adf_paragraph(_adf_text(epic_def["description"], bold=True))],
                    },
                    _adf_paragraph(
                        _adf_text("Timeline Window: ", bold=True),
                        _adf_text(f"{start_d} -> {due_d}", code=True),
                        _adf_text(" | Covered Domains: ", bold=True),
                        _adf_text(", ".join(epic_def["domains"]), code=True),
                    ),
                ],
            }
            epic_issue = existing.get(summary)
            if epic_issue is None:
                epic_issue = client.create_epic(
                    summary=summary,
                    description_adf=desc_adf,
                    labels=list(epic_def["labels"]),
                    start_date=start_d,
                    due_date=due_d,
                    assignee_id=assignee_id,
                )
            elif hasattr(client, "update_issue_fields"):
                update_fields: dict[str, Any] = {
                    "description": desc_adf,
                    "customfield_10015": start_d,
                    "duedate": due_d,
                }
                if assignee_id:
                    update_fields["assignee"] = {"accountId": assignee_id}
                client.update_issue_fields(epic_issue.key, update_fields)
            epics_by_phase[epic_def["phase_id"]] = epic_issue
            for dom in epic_def["domains"]:
                epic_key_by_domain[dom] = epic_issue.key

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
    return resolved, epic_key_by_domain, epics_by_phase


def _resolve_stale_auto_bugs(
    client: JiraClient,
    *,
    domain_key: str,
    suite_name: str,
    manifest_sha256: str | None,
    today_str: str,
) -> list[str]:
    """Auto-close open [SAQA-AUTO] Bug tickets for a domain once it passes verification."""
    resolved_keys: list[str] = []
    try:
        existing_issues = client.find_project_issues()
    except Exception:
        return resolved_keys

    for summary, issue in existing_issues.items():
        if not summary.startswith("[SAQA-AUTO]"):
            continue
        if f" {domain_key} " not in f" {summary} " and f" {domain_key} |" not in summary and f"in {domain_key} (" not in summary:
            continue
        try:
            state = client.get_issue_state(issue.key)
            if state.status.casefold() in {"done", "closed", "resolved"}:
                continue
            if hasattr(client, "update_issue_fields"):
                client.update_issue_fields(
                    issue.key,
                    {
                        "customfield_10015": today_str,
                        "duedate": today_str,
                    },
                )
            client.update_labels(
                issue.key,
                add=("saqa-auto-resolved", "saqa-ci-pass"),
                remove=("saqa-ci-fail",),
            )
            marker = f"[SAQA-AUTO-RESOLVED:{domain_key}:{(manifest_sha256 or suite_name)[:16]}]"
            resolution_adf = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "panel",
                        "attrs": {"panelType": "success"},
                        "content": [
                            _adf_paragraph(
                                _adf_text(f"Automated Verification Recovery ({domain_key})  ", bold=True),
                                _adf_status_lozenge("PASS"),
                            ),
                            _adf_paragraph(
                                _adf_text(
                                    f"Automatically resolved because {domain_key} passed fresh SAQA verification "
                                    f"(suite={suite_name}, digest={manifest_sha256 or 'verified'})."
                                )
                            ),
                        ],
                    },
                    _adf_paragraph(_adf_text(marker, code=True)),
                ],
            }
            if hasattr(client, "add_adf_comment_once"):
                client.add_adf_comment_once(issue.key, resolution_adf, marker)
            else:
                client.add_comment_once(issue.key, f"Auto-resolved by SAQA PASS {marker}", marker)
            client.transition_to_any(issue.key, _transition_targets("PASS"))
            resolved_keys.append(issue.key)
        except Exception:
            continue
    return resolved_keys


def sync_records_to_jira(
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    *,
    suite_name: str = "saqa-suite",
    manifest_sha256: str | None = None,
    attachments: Sequence[Path] = (),
    artifact_dir: Path | None = None,
    auto_generate_visuals: bool = True,
    capture_screenshots: bool = False,
    auto_resolve_bugs: bool = True,
    client: JiraClient | None = None,
) -> dict[str, Any]:
    """Synchronize SAQA evidence, Timeline Epics, Rich ADF tables, Visual Photos, and Report Documents to Jira."""
    norm_records = [_normalize_record(r) for r in records]
    analytics = analyze_records(norm_records, manifest_sha256=manifest_sha256)
    domain_map = _compute_domain_results(norm_records, analytics)
    sha_short = (manifest_sha256 or "in-memory")[:16]
    targets = sorted({rec["target"] for rec in norm_records})
    target_display = ", ".join(targets) if targets else "unknown"
    today = datetime.now(WIB)
    today_str = today.strftime("%Y-%m-%d")

    owns_client = client is None
    active_client = client or JiraClient(JiraConfig.from_env())
    synced_issues: list[dict[str, Any]] = []
    synced_epics: list[dict[str, Any]] = []
    uploaded_attachments: list[dict[str, str]] = []
    created_bugs: list[str] = []
    resolved_bugs: list[str] = []

    temp_ctx = tempfile.TemporaryDirectory(prefix="saqa-jira-visuals-") if artifact_dir is None else None
    work_dir = Path(temp_ctx.name) if temp_ctx is not None else Path(artifact_dir)

    try:
        all_attachments: list[Path] = [Path(p) for p in attachments if Path(p).is_file()]
        existing_names = {p.name for p in all_attachments}

        if auto_generate_visuals and hasattr(active_client, "upload_attachment"):
            work_dir.mkdir(parents=True, exist_ok=True)
            scorecard_png = work_dir / "qa-scorecard.png"
            render_scorecard_png(analytics, norm_records, scorecard_png, title=f"SAQA | {suite_name}")
            if scorecard_png.name not in existing_names:
                all_attachments.append(scorecard_png)
                existing_names.add(scorecard_png.name)

            chart_svg = work_dir / "qa-analytics-chart.svg"
            render_analytics_svg(analytics, norm_records, chart_svg, title=f"SAQA Analytics — {suite_name}")
            if chart_svg.name not in existing_names:
                all_attachments.append(chart_svg)
                existing_names.add(chart_svg.name)

            csv_matrix = work_dir / "qa-test-matrix.csv"
            export_csv_matrix(norm_records, csv_matrix)
            if csv_matrix.name not in existing_names:
                all_attachments.append(csv_matrix)
                existing_names.add(csv_matrix.name)

            if "report.html" not in existing_names:
                html_path = work_dir / "report.html"
                html_path.write_text(
                    render_html_report(
                        analytics,
                        norm_records,
                        manifest_sha256=manifest_sha256,
                        title=f"SAQA Report — {suite_name}",
                    ),
                    encoding="utf-8",
                )
                all_attachments.append(html_path)
                existing_names.add(html_path.name)

            if "report.md" not in existing_names:
                md_path = work_dir / "report.md"
                md_path.write_text(
                    render_markdown_report(analytics, title=f"SAQA Report — {suite_name}"),
                    encoding="utf-8",
                )
                all_attachments.append(md_path)
                existing_names.add(md_path.name)

        if capture_screenshots and targets and hasattr(active_client, "upload_attachment"):
            primary_target = next((t for t in targets if t.startswith(("http://", "https://"))), None)
            if primary_target:
                work_dir.mkdir(parents=True, exist_ok=True)
                desktop_png = capture_web_screenshot(primary_target, work_dir / "screenshot-desktop.png", width=1440, height=900)
                if desktop_png and desktop_png.name not in existing_names:
                    all_attachments.append(desktop_png)
                    existing_names.add(desktop_png.name)
                mobile_png = capture_web_screenshot(primary_target, work_dir / "screenshot-mobile.png", width=390, height=844)
                if mobile_png and mobile_png.name not in existing_names:
                    all_attachments.append(mobile_png)
                    existing_names.add(mobile_png.name)

        photo_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
        photo_attachments = [p for p in all_attachments if p.suffix.lower() in photo_exts]
        attachment_names = [p.name for p in all_attachments]

        project = active_client.verify_access()
        assignee_id = active_client.get_myself_account_id() if hasattr(active_client, "get_myself_account_id") else None
        managed, epic_key_by_domain, epics_by_phase = _ensure_epics_and_issues(
            active_client,
            today=today,
            assignee_id=assignee_id,
        )

        # Transition Epics based on aggregate status of their child domains
        for epic_def in EPIC_DEFINITIONS:
            phase_id = epic_def["phase_id"]
            if phase_id not in epics_by_phase:
                continue
            epic_issue = epics_by_phase[phase_id]
            child_statuses = [domain_map[d][0] for d in epic_def["domains"]]
            epic_status = _aggregate_statuses(child_statuses)
            epic_transition = active_client.transition_to_any(epic_issue.key, _transition_targets(epic_status))
            synced_epics.append({
                "phase_id": phase_id,
                "epic_key": epic_issue.key,
                "epic_url": epic_issue.url,
                "status": epic_status,
                "transitioned_to": epic_transition,
            })

        for domain_key in sorted(ISSUE_SUMMARIES):
            issue = managed[domain_key]
            domain_status, domain_records = domain_map[domain_key]
            label = _status_label(domain_status)
            phase_label = "saqa-phase-1" if domain_key in {"QA-1", "QA-2", "QA-3"} else (
                "saqa-phase-2" if domain_key in {"QA-4", "QA-5", "QA-6"} else "saqa-phase-3"
            )
            state = active_client.get_issue_state(issue.key)
            stale_labels = tuple(sorted((set(state.labels) & STATUS_LABELS) - {label}))
            active_client.update_labels(
                issue.key,
                add=("saqa-automation", f"saqa-{domain_key.lower()}", phase_label, label),
                remove=stale_labels,
            )

            start_off, due_off = DOMAIN_TIMELINE_OFFSETS.get(domain_key, (-7, 7))
            start_date = (today + timedelta(days=start_off)).strftime("%Y-%m-%d")
            due_date = (today + timedelta(days=due_off)).strftime("%Y-%m-%d")
            parent_epic_key = epic_key_by_domain.get(domain_key)

            if domain_key in {"QA-1", "QA-8", "QA-9"}:
                files_for_domain = all_attachments
            elif domain_key in {"QA-2", "QA-3"}:
                files_for_domain = photo_attachments
            else:
                files_for_domain = []
            domain_attachment_names = [p.name for p in files_for_domain]

            rich_description_adf = build_domain_adf_document(
                domain_key=domain_key,
                domain_status=domain_status,
                domain_records=domain_records,
                analytics=analytics,
                suite_name=suite_name,
                target_display=target_display,
                manifest_sha256=manifest_sha256,
                start_date=start_date,
                due_date=due_date,
                epic_key=parent_epic_key,
                attached_files=domain_attachment_names,
            )

            if hasattr(active_client, "update_issue_fields"):
                priority_name = "Highest" if domain_status == "FAIL" else DOMAIN_PRIORITIES.get(domain_key, "High")
                field_payload: dict[str, Any] = {
                    "description": rich_description_adf,
                    "customfield_10015": start_date,
                    "duedate": due_date,
                    "priority": {"name": priority_name},
                    "environment": build_environment_adf(
                        target_display=target_display,
                        suite_name=suite_name,
                        manifest_sha256=manifest_sha256,
                    ),
                }
                if parent_epic_key:
                    field_payload["parent"] = {"key": parent_epic_key}
                if assignee_id:
                    field_payload["assignee"] = {"accountId": assignee_id}
                active_client.update_issue_fields(issue.key, field_payload)

            transitioned_to = active_client.transition_to_any(
                issue.key,
                _transition_targets(domain_status),
            )

            marker = f"[SAQA-ADF-SYNC:{suite_name}:{sha_short}:{domain_key}]"
            comment_adf = build_domain_adf_document(
                domain_key=domain_key,
                domain_status=domain_status,
                domain_records=domain_records,
                analytics=analytics,
                suite_name=suite_name,
                target_display=target_display,
                manifest_sha256=manifest_sha256,
                start_date=start_date,
                due_date=due_date,
                epic_key=parent_epic_key,
                attached_files=domain_attachment_names,
                marker=marker,
            )
            if hasattr(active_client, "add_adf_comment_once"):
                commented = active_client.add_adf_comment_once(issue.key, comment_adf, marker)
            else:
                commented = active_client.add_comment_once(issue.key, f"SAQA sync {marker}", marker)

            # Upload full documents & visual photos directly to Jira
            if files_for_domain and hasattr(active_client, "upload_attachment"):
                for file_path in files_for_domain:
                    att = active_client.upload_attachment(issue.key, file_path)
                    if att:
                        uploaded_attachments.append({"issue_key": issue.key, "filename": file_path.name})

            if domain_status == "FAIL":
                bug_summary = f"[SAQA-AUTO] {suite_name} failure in {domain_key} ({target_display})"
                existing_map = active_client.find_project_issues()
                if bug_summary not in existing_map:
                    bug = active_client.create_bug(
                        bug_summary,
                        f"Automated failure detected in {domain_key} for suite {suite_name} ({target_display}). Evidence SHA-256: {manifest_sha256}",
                        ["saqa-automation", "saqa-auto-defect", f"saqa-{domain_key.lower()}"],
                    )
                    created_bugs.append(bug.key)
            elif domain_status == "PASS" and auto_resolve_bugs:
                resolved_bugs.extend(
                    _resolve_stale_auto_bugs(
                        active_client,
                        domain_key=domain_key,
                        suite_name=suite_name,
                        manifest_sha256=manifest_sha256,
                        today_str=today_str,
                    )
                )

            synced_issues.append(
                {
                    "domain": domain_key,
                    "issue_key": issue.key,
                    "issue_url": issue.url,
                    "parent_epic": parent_epic_key,
                    "start_date": start_date,
                    "due_date": due_date,
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
            "synced_epics": synced_epics,
            "synced_issues": synced_issues,
            "uploaded_attachments": uploaded_attachments,
            "attachment_names": attachment_names,
            "created_bugs": created_bugs,
            "resolved_bugs": sorted(set(resolved_bugs)),
        }
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()
        if owns_client:
            active_client.close()


def sync_manifest_to_jira(
    manifest_path: Path,
    *,
    suite_name: str | None = None,
    attachments: Sequence[Path] | None = None,
    auto_generate_visuals: bool = True,
    capture_screenshots: bool = False,
    auto_resolve_bugs: bool = True,
    client: JiraClient | None = None,
) -> dict[str, Any]:
    """Verify a SAQA evidence manifest file and synchronize its results, timeline, photos, and reports to Jira."""
    records, sha = load_verified_manifest(manifest_path)
    inferred_suite = suite_name
    if not inferred_suite and records:
        inferred_suite = str(records[0].get("details", {}).get("suite") or manifest_path.stem)

    parent = manifest_path.parent
    discovered: list[Path] = [
        p
        for p in (
            manifest_path,
            parent / "suite-summary.json",
            parent / "report.html",
            parent / "report.md",
            parent / "qa-test-matrix.csv",
            parent / "qa-scorecard.png",
            parent / "qa-analytics-chart.svg",
            parent / "screenshot-desktop.png",
            parent / "screenshot-mobile.png",
        )
        if p.is_file()
    ]
    if attachments:
        seen = {p.resolve() for p in discovered}
        for extra in attachments:
            ep = Path(extra)
            if ep.is_file() and ep.resolve() not in seen:
                discovered.append(ep)
                seen.add(ep.resolve())

    return sync_records_to_jira(
        records,
        suite_name=inferred_suite or "saqa-suite",
        manifest_sha256=sha,
        attachments=discovered,
        artifact_dir=parent,
        auto_generate_visuals=auto_generate_visuals,
        capture_screenshots=capture_screenshots,
        auto_resolve_bugs=auto_resolve_bugs,
        client=client,
    )
