"""Enterprise Jira Cloud synchronization with Bilingual (EN/ID) ADF, Two-Way Waivers, Agile Sprints, Timeline Epics, and Visual Attachments."""
from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .analytics import analyze_records, load_verified_manifest
from .evidence import EvidenceRecord
from .i18n import (
    DOMAIN_DESCRIPTIONS_I18N,
    EPIC_TEXT_I18N,
    ISSUE_SUMMARIES_I18N,
    get_all_epic_summary_variants,
    get_all_summary_variants,
    normalize_lang,
    tr,
    translate_case_name,
    translate_finding_or_reason,
    translate_recommendation,
)
from .jira import JiraClient, JiraConfig, JiraIssueResult
from .pdf_report import render_pdf_report
from .reporting import render_html_report, render_junit_xml, render_markdown_report, render_sarif_report
from .visual_evidence import (
    capture_viewport_matrix,
    capture_web_screenshot,
    export_csv_matrix,
    render_analytics_svg,
    render_scorecard_png,
)

WIB = timezone(timedelta(hours=7))

ISSUE_SUMMARIES: dict[str, str] = dict(ISSUE_SUMMARIES_I18N["en"])
DOMAIN_DESCRIPTIONS: dict[str, str] = dict(DOMAIN_DESCRIPTIONS_I18N["en"])

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
        "summary": EPIC_TEXT_I18N["en"]["PHASE-1"]["summary"],
        "description": EPIC_TEXT_I18N["en"]["PHASE-1"]["description"],
        "domains": ("QA-1", "QA-2", "QA-3"),
        "start_offset_days": -21,
        "end_offset_days": -11,
        "labels": ["saqa-epic", "saqa-phase-1", "saqa-automation"],
    },
    {
        "phase_id": "PHASE-2",
        "summary": EPIC_TEXT_I18N["en"]["PHASE-2"]["summary"],
        "description": EPIC_TEXT_I18N["en"]["PHASE-2"]["description"],
        "domains": ("QA-4", "QA-5", "QA-6"),
        "start_offset_days": -14,
        "end_offset_days": -4,
        "labels": ["saqa-epic", "saqa-phase-2", "saqa-automation"],
    },
    {
        "phase_id": "PHASE-3",
        "summary": EPIC_TEXT_I18N["en"]["PHASE-3"]["summary"],
        "description": EPIC_TEXT_I18N["en"]["PHASE-3"]["description"],
        "domains": ("QA-7", "QA-8", "QA-9"),
        "start_offset_days": -7,
        "end_offset_days": 7,
        "labels": ["saqa-epic", "saqa-phase-3", "saqa-automation"],
    },
)

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

WAIVER_LABELS = frozenset({
    "saqa-waived",
    "accepted-risk",
    "wontfix",
    "false-positive",
})

DOMAIN_TAG_MAP: dict[str, frozenset[str]] = {
    "QA-2": frozenset({"web", "smoke", "routing", "seo", "pwa", "assets", "crawl", "journey"}),
    "QA-3": frozenset({"web", "pwa", "css", "js", "icons", "browser", "responsive", "mobile"}),
    "QA-4": frozenset({"api", "contract", "xml", "rss", "graphql"}),
    "QA-5": frozenset({"security", "headers", "tls", "cors", "sri"}),
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
        return ("Done", "Closed", "Resolved", "Pass", "Passed", "Selesai")
    if status in {"FAIL", "BLOCKED"}:
        return ("In Progress", "To Do", "Open", "Reopened", "Fail", "Failed", "Sedang Dikerjakan")
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
        "LULUS": "green",
        "CERTIFIED": "green",
        "WAIVED": "blue",
        "A": "green",
        "B": "blue",
        "FAIL": "red",
        "GAGAL": "red",
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
    lang: str = "en",
    active_sprint_name: str | None = None,
    waiver_labels: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a rich localized (EN/ID) enterprise Atlassian Document Format (ADF) report for Jira."""
    code = normalize_lang(lang)
    now_utc = datetime.now(timezone.utc)
    now_wib = now_utc.astimezone(WIB)
    lat = analytics["latency"]
    counts = analytics["status_counts"]
    panel_type = "success" if domain_status == "PASS" else ("error" if domain_status == "FAIL" else "warning")
    localized_summary = ISSUE_SUMMARIES_I18N[code].get(domain_key, domain_key)
    localized_desc = DOMAIN_DESCRIPTIONS_I18N[code].get(domain_key, "")

    banner_content = [
        _adf_paragraph(
            _adf_text(f"{domain_key} — {localized_summary}  ", bold=True),
            _adf_status_lozenge(domain_status),
            _adf_text(f"   |   {tr('health_grade', code)}: ", bold=True),
            _adf_status_lozenge(f"{analytics['health_score']}/100 ({analytics['health_grade']})"),
        ),
        _adf_paragraph(_adf_text(localized_desc)),
    ]
    if waiver_labels:
        banner_content.append(
            _adf_paragraph(
                _adf_status_lozenge("WAIVED"),
                _adf_text("  " + tr("waiver_applied", code, labels=", ".join(waiver_labels)), bold=True),
            )
        )

    banner_panel = {
        "type": "panel",
        "attrs": {"panelType": panel_type},
        "content": banner_content,
    }

    kpi_rows = [
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text(tr("metric_gov_field", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("observed_value", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("metric_sla_bench", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("observed_value", code), bold=True))], header=True),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text(tr("suite_name", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(suite_name, code=True))]),
            _adf_cell([_adf_paragraph(_adf_text(tr("domain_gate_status", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_status_lozenge(domain_status))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text(tr("target_endpoints", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(target_display, code=True))]),
            _adf_cell([_adf_paragraph(_adf_text(tr("suite_health_score", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{analytics['health_score']} / 100 (Grade {analytics['health_grade']})", bold=True))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text(tr("timeline_schedule", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{start_date}  ->  {due_date}", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text(tr("suite_pass_rate", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{analytics['pass_rate_pct']}% ({counts['PASS']} PASS / {counts['FAIL']} FAIL / {counts['BLOCKED']} BLOCKED)"))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text(tr("parent_epic", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(epic_key or "Standalone", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text(tr("latency_min_p50_mean", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{lat['min_ms']} ms / {lat['p50_ms']} ms / {lat['mean_ms']} ms", code=True))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text(tr("executed_at", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{now_wib.strftime('%Y-%m-%d %H:%M:%S WIB')} ({now_utc.strftime('%H:%M:%S UTC')})", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text(tr("latency_p95_p99_max", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"{lat['p95_ms']} ms / {lat['p99_ms']} ms / {lat['max_ms']} ms", code=True))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text(tr("evidence_sha", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(manifest_sha256 or "unhashed-in-memory", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text(tr("framework_engine", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(f"SAQA Professional Framework v{__version__}", code=True))]),
        ]),
        _adf_row([
            _adf_cell([_adf_paragraph(_adf_text(tr("active_sprint", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(active_sprint_name or "Timeline / Kanban", code=True))]),
            _adf_cell([_adf_paragraph(_adf_text(tr("report_language", code), bold=True))]),
            _adf_cell([_adf_paragraph(_adf_text(tr("lang_label", code), code=True))]),
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
            _adf_cell([_adf_paragraph(_adf_text(tr("col_test_id", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("col_scenario", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("col_target", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("col_http", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("col_latency", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("col_assertions", code), bold=True))], header=True),
            _adf_cell([_adf_paragraph(_adf_text(tr("col_status", code), bold=True))], header=True),
        ])
    ]

    for idx, rec in enumerate(domain_records, start=1):
        det = rec["details"]
        case_name = translate_case_name(str(det.get("case_name") or rec["test_id"]), code)
        method_val = str(det.get("http_method") or (det.get("http_methods") or ["GET"])[0])
        http_code = det.get("status_code", 200)
        elapsed = det.get("elapsed_ms", det.get("duration_ms", "-"))
        elapsed_str = f"{elapsed} ms" if isinstance(elapsed, (int, float)) else "-"
        checks = det.get("checks_passed") or []
        failures = det.get("failure_reasons") or []
        if failures:
            prefix = "GAGAL: " if code == "id" else "FAIL: "
            assertions_str = prefix + "; ".join(translate_finding_or_reason(str(f), code) for f in failures)
        elif checks:
            passed_word = "lulus" if code == "id" else "passed"
            assertions_str = f"{len(checks)} {passed_word} ({', '.join(str(c) for c in checks[:4])})"
        else:
            assertions_str = "Terverifikasi" if code == "id" else "Verified"

        test_rows.append(
            _adf_row([
                _adf_cell([_adf_paragraph(_adf_text(str(idx)))]),
                _adf_cell([_adf_paragraph(_adf_text(rec["test_id"], code=True))]),
                _adf_cell([_adf_paragraph(_adf_text(case_name))]),
                _adf_cell([_adf_paragraph(_adf_text(rec["target"], code=True))]),
                _adf_cell([_adf_paragraph(_adf_text(f"{method_val} ({http_code})", code=True))]),
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
        rec_items.append({"type": "listItem", "content": [_adf_paragraph(_adf_text(translate_recommendation(str(rec_text), code)))]})
    if attached_files:
        rec_items.append({
            "type": "listItem",
            "content": [
                _adf_paragraph(
                    _adf_text(tr("attached_files", code), bold=True),
                    _adf_text(", ".join(attached_files), code=True),
                )
            ],
        })

    content: list[dict[str, Any]] = [
        banner_panel,
        _adf_heading(3, tr("sec_1_exec", code)),
        kpi_table,
        _adf_heading(3, tr("sec_2_matrix", code, count=len(domain_records))),
        test_table,
        _adf_heading(3, tr("sec_3_findings", code)),
        {"type": "bulletList", "content": rec_items or [{"type": "listItem", "content": [_adf_paragraph(_adf_text(tr("all_gates_ok", code)))]}]},
    ]

    if marker:
        content.append(_adf_paragraph(_adf_text(marker, code=True)))

    return {"type": "doc", "version": 1, "content": content}


def build_environment_adf(
    *,
    target_display: str,
    suite_name: str,
    manifest_sha256: str | None,
    lang: str = "en",
) -> dict[str, Any]:
    code = normalize_lang(lang)
    return {
        "type": "doc",
        "version": 1,
        "content": [
            _adf_paragraph(
                _adf_text("Target: ", bold=True),
                _adf_text(target_display, code=True),
                _adf_text(" | Suite: ", bold=True),
                _adf_text(suite_name, code=True),
                _adf_text(" | Lang: ", bold=True),
                _adf_text(code.upper(), code=True),
                _adf_text(" | Engine: ", bold=True),
                _adf_text(f"SAQA v{__version__}", code=True),
                _adf_text(" | SHA-256: ", bold=True),
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


def _compute_timeline_window(
    *,
    today: datetime,
    sprint_start: str | None = None,
    sprint_end: str | None = None,
) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """Compute (epic_dates_by_phase, domain_dates_by_key) using custom sprint dates or smart defaults."""
    if sprint_start and sprint_end:
        s_dt = datetime.strptime(sprint_start, "%Y-%m-%d").replace(tzinfo=WIB)
        e_dt = datetime.strptime(sprint_end, "%Y-%m-%d").replace(tzinfo=WIB)
        if s_dt > e_dt:
            raise ValueError("sprint_start must not be after sprint_end")
        span_days = max(1, (e_dt - s_dt).days)
        p1_end = s_dt + timedelta(days=max(1, round(span_days * 0.35)))
        p2_start = s_dt + timedelta(days=max(0, round(span_days * 0.30)))
        p2_end = s_dt + timedelta(days=max(1, round(span_days * 0.70)))
        p3_start = s_dt + timedelta(days=max(0, round(span_days * 0.65)))
        epic_dates = {
            "PHASE-1": (s_dt.strftime("%Y-%m-%d"), min(e_dt, p1_end).strftime("%Y-%m-%d")),
            "PHASE-2": (min(e_dt, p2_start).strftime("%Y-%m-%d"), min(e_dt, p2_end).strftime("%Y-%m-%d")),
            "PHASE-3": (min(e_dt, p3_start).strftime("%Y-%m-%d"), e_dt.strftime("%Y-%m-%d")),
        }
        domain_keys = sorted(ISSUE_SUMMARIES)
        domain_dates: dict[str, tuple[str, str]] = {}
        for idx, dkey in enumerate(domain_keys):
            d_start = s_dt + timedelta(days=round(span_days * (idx / len(domain_keys))))
            d_end = s_dt + timedelta(days=max(1, round(span_days * ((idx + 1.5) / len(domain_keys)))))
            if d_end > e_dt:
                d_end = e_dt
            if d_start > d_end:
                d_start = d_end
            domain_dates[dkey] = (d_start.strftime("%Y-%m-%d"), d_end.strftime("%Y-%m-%d"))
        return epic_dates, domain_dates

    epic_dates = {
        ed["phase_id"]: (
            (today + timedelta(days=int(ed["start_offset_days"]))).strftime("%Y-%m-%d"),
            (today + timedelta(days=int(ed["end_offset_days"]))).strftime("%Y-%m-%d"),
        )
        for ed in EPIC_DEFINITIONS
    }
    domain_dates = {
        dkey: (
            (today + timedelta(days=s_off)).strftime("%Y-%m-%d"),
            (today + timedelta(days=e_off)).strftime("%Y-%m-%d"),
        )
        for dkey, (s_off, e_off) in DOMAIN_TIMELINE_OFFSETS.items()
    }
    return epic_dates, domain_dates


def _ensure_epics_and_issues(
    client: JiraClient,
    *,
    today: datetime,
    assignee_id: str | None,
    epic_dates: Mapping[str, tuple[str, str]] | None = None,
    lang: str = "en",
) -> tuple[dict[str, JiraIssueResult], dict[str, str], dict[str, JiraIssueResult]]:
    """Ensure 3 Phase Epics and 9 Domain Tasks exist without creating duplicates across EN/ID switches."""
    code = normalize_lang(lang)
    existing = client.find_project_issues()
    epics_by_phase: dict[str, JiraIssueResult] = {}
    epic_key_by_domain: dict[str, str] = {}

    if hasattr(client, "create_epic"):
        for epic_def in EPIC_DEFINITIONS:
            phase_id = epic_def["phase_id"]
            target_summary = EPIC_TEXT_I18N[code][phase_id]["summary"]
            target_desc = EPIC_TEXT_I18N[code][phase_id]["description"]
            if epic_dates and phase_id in epic_dates:
                start_d, due_d = epic_dates[phase_id]
            else:
                start_d = (today + timedelta(days=int(epic_def["start_offset_days"]))).strftime("%Y-%m-%d")
                due_d = (today + timedelta(days=int(epic_def["end_offset_days"]))).strftime("%Y-%m-%d")
            desc_adf = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "panel",
                        "attrs": {"panelType": "info"},
                        "content": [_adf_paragraph(_adf_text(target_desc, bold=True))],
                    },
                    _adf_paragraph(
                        _adf_text(tr("timeline_window", code), bold=True),
                        _adf_text(f"{start_d} -> {due_d}", code=True),
                        _adf_text(tr("covered_domains", code), bold=True),
                        _adf_text(", ".join(epic_def["domains"]), code=True),
                    ),
                ],
            }
            epic_issue = next((existing[v] for v in get_all_epic_summary_variants(phase_id) if v in existing), None)
            if epic_issue is None and hasattr(client, "find_project_issues_by_label"):
                phase_lbl = f"saqa-{phase_id.lower()}"
                by_lbl = client.find_project_issues_by_label(phase_lbl)
                if by_lbl:
                    epic_issue = by_lbl[0]

            if epic_issue is None:
                epic_issue = client.create_epic(
                    summary=target_summary,
                    description_adf=desc_adf,
                    labels=list(epic_def["labels"]),
                    start_date=start_d,
                    due_date=due_d,
                    assignee_id=assignee_id,
                )
            elif hasattr(client, "update_issue_fields"):
                update_fields: dict[str, Any] = {
                    "summary": target_summary,
                    "description": desc_adf,
                    "customfield_10015": start_d,
                    "duedate": due_d,
                }
                if assignee_id:
                    update_fields["assignee"] = {"accountId": assignee_id}
                client.update_issue_fields(epic_issue.key, update_fields)
            epics_by_phase[phase_id] = epic_issue
            for dom in epic_def["domains"]:
                epic_key_by_domain[dom] = epic_issue.key

    resolved: dict[str, JiraIssueResult] = {}
    target_summaries = ISSUE_SUMMARIES_I18N[code]
    for key, target_summary in target_summaries.items():
        issue = next((existing[v] for v in get_all_summary_variants(key) if v in existing), None)
        if issue is None and hasattr(client, "find_project_issues_by_label"):
            by_lbl = client.find_project_issues_by_label(f"saqa-{key.lower()}")
            if by_lbl:
                issue = by_lbl[0]
        if issue is None:
            issue = client.create_task(
                summary=target_summary,
                description=tr("bootstrap_desc", code, key=key, summary=target_summary),
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
    lang: str = "en",
) -> list[str]:
    """Auto-close open [SAQA-AUTO] Bug tickets for a domain once it passes verification."""
    code = normalize_lang(lang)
    resolved_keys: list[str] = []
    try:
        existing_issues = client.find_project_issues()
    except Exception:
        return resolved_keys

    for summary, issue in existing_issues.items():
        if not summary.startswith("[SAQA-AUTO]"):
            continue
        if (
            f" {domain_key} " not in f" {summary} "
            and f" {domain_key} |" not in summary
            and f"in {domain_key} (" not in summary
            and f"pada {domain_key} (" not in summary
        ):
            continue
        try:
            state = client.get_issue_state(issue.key)
            if state.status.casefold() in {"done", "closed", "resolved", "selesai"}:
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
                                _adf_text(tr("auto_recovery_title", code, domain=domain_key), bold=True),
                                _adf_status_lozenge("PASS"),
                            ),
                            _adf_paragraph(
                                _adf_text(
                                    tr(
                                        "auto_recovery_body",
                                        code,
                                        domain=domain_key,
                                        suite=suite_name,
                                        digest=manifest_sha256 or "verified",
                                    )
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
        except Exception:  # noqa: S112
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
    sprint_start: str | None = None,
    sprint_end: str | None = None,
    skip_unchanged_attachments: bool = True,
    lang: str | None = None,
    respect_waivers: bool = True,
    sync_agile_sprint: bool = True,
    client: JiraClient | None = None,
) -> dict[str, Any]:
    """Synchronize SAQA evidence, Bilingual (EN/ID) Rich ADF, Two-Way Waivers, Agile Sprints, Photos & Reports to Jira."""
    code = normalize_lang(lang)
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
    uploaded_attachments: list[dict[str, Any]] = []
    created_bugs: list[str] = []
    resolved_bugs: list[str] = []
    waived_domains: list[str] = []
    active_sprint: dict[str, Any] | None = None

    if artifact_dir is not None:
        temp_ctx = None
        work_dir = Path(artifact_dir)
    else:
        temp_ctx = tempfile.TemporaryDirectory(prefix="saqa-jira-visuals-")
        work_dir = Path(temp_ctx.name)

    try:
        # Discover active Scrum sprint if Agile board is present
        if sync_agile_sprint and hasattr(active_client, "find_active_sprint"):
            active_sprint = active_client.find_active_sprint()
            if active_sprint and not (sprint_start and sprint_end):
                sp_start = str(active_sprint.get("startDate") or "")[:10]
                sp_end = str(active_sprint.get("endDate") or "")[:10]
                if len(sp_start) == 10 and len(sp_end) == 10:
                    sprint_start, sprint_end = sp_start, sp_end

        epic_dates, domain_dates = _compute_timeline_window(
            today=today,
            sprint_start=sprint_start,
            sprint_end=sprint_end,
        )

        all_attachments: list[Path] = [Path(p) for p in attachments if Path(p).is_file()]
        existing_names = {p.name for p in all_attachments}

        if auto_generate_visuals and hasattr(active_client, "upload_attachment"):
            work_dir.mkdir(parents=True, exist_ok=True)
            scorecard_png = work_dir / "qa-scorecard.png"
            render_scorecard_png(analytics, norm_records, scorecard_png, title=f"SAQA | {suite_name}", lang=code)
            if scorecard_png.name not in existing_names:
                all_attachments.append(scorecard_png)
                existing_names.add(scorecard_png.name)

            chart_svg = work_dir / "qa-analytics-chart.svg"
            render_analytics_svg(analytics, norm_records, chart_svg, title=f"SAQA Analytics — {suite_name}", lang=code)
            if chart_svg.name not in existing_names:
                all_attachments.append(chart_svg)
                existing_names.add(chart_svg.name)

            csv_matrix = work_dir / "qa-test-matrix.csv"
            export_csv_matrix(norm_records, csv_matrix, lang=code)
            if csv_matrix.name not in existing_names:
                all_attachments.append(csv_matrix)
                existing_names.add(csv_matrix.name)

            report_title = f"{'Laporan Kualitas SAQA' if code == 'id' else 'SAQA Report'} — {suite_name}"
            if "report.html" not in existing_names:
                html_path = work_dir / "report.html"
                html_path.write_text(
                    render_html_report(
                        analytics,
                        norm_records,
                        manifest_sha256=manifest_sha256,
                        title=report_title,
                        lang=code,
                    ),
                    encoding="utf-8",
                )
                all_attachments.append(html_path)
                existing_names.add(html_path.name)

            if "report.md" not in existing_names:
                md_path = work_dir / "report.md"
                md_path.write_text(
                    render_markdown_report(analytics, title=report_title, lang=code),
                    encoding="utf-8",
                )
                all_attachments.append(md_path)
                existing_names.add(md_path.name)

            if "qa-executive-report.pdf" not in existing_names:
                pdf_path = work_dir / "qa-executive-report.pdf"
                render_pdf_report(
                    analytics,
                    norm_records,
                    pdf_path,
                    manifest_sha256=manifest_sha256,
                    title=report_title,
                    lang=code,
                )
                all_attachments.append(pdf_path)
                existing_names.add(pdf_path.name)

            if "junit.xml" not in existing_names:
                junit_path = work_dir / "junit.xml"
                junit_path.write_text(
                    render_junit_xml(analytics, norm_records, suite_name=suite_name),
                    encoding="utf-8",
                )
                all_attachments.append(junit_path)
                existing_names.add(junit_path.name)

            if "results.sarif" not in existing_names:
                sarif_path = work_dir / "results.sarif"
                sarif_path.write_text(
                    json.dumps(render_sarif_report(norm_records, suite_name=suite_name), indent=2),
                    encoding="utf-8",
                )
                all_attachments.append(sarif_path)
                existing_names.add(sarif_path.name)

        if capture_screenshots and targets and hasattr(active_client, "upload_attachment"):
            primary_target = next((t for t in targets if t.startswith(("http://", "https://"))), None)
            if primary_target:
                work_dir.mkdir(parents=True, exist_ok=True)
                shots = capture_viewport_matrix(primary_target, work_dir)
                if not shots:
                    # Fallback single calls if mocked in tests
                    for label_name, w, h in (("desktop", 1440, 900), ("mobile", 390, 844)):
                        s = capture_web_screenshot(primary_target, work_dir / f"screenshot-{label_name}.png", width=w, height=h)
                        if s:
                            shots.append(s)
                for shot_p in shots:
                    if shot_p.name not in existing_names:
                        all_attachments.append(shot_p)
                        existing_names.add(shot_p.name)

        photo_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
        photo_attachments = [p for p in all_attachments if p.suffix.lower() in photo_exts]
        attachment_names = [p.name for p in all_attachments]

        project = active_client.verify_access()
        assignee_id = active_client.get_myself_account_id() if hasattr(active_client, "get_myself_account_id") else None
        managed, epic_key_by_domain, epics_by_phase = _ensure_epics_and_issues(
            active_client,
            today=today,
            assignee_id=assignee_id,
            epic_dates=epic_dates,
            lang=code,
        )

        # Assign managed issues into Active Agile Sprint when present
        if active_sprint and hasattr(active_client, "move_issues_to_sprint"):
            active_client.move_issues_to_sprint(
                int(active_sprint["id"]),
                [iss.key for iss in managed.values()],
            )

        target_summaries = ISSUE_SUMMARIES_I18N[code]
        effective_domain_status: dict[str, str] = {}
        domain_waivers: dict[str, tuple[str, ...]] = {}
        domain_states: dict[str, Any] = {}

        leaf_domains = ("QA-2", "QA-3", "QA-4", "QA-5", "QA-6", "QA-7", "QA-8")
        for domain_key in sorted(ISSUE_SUMMARIES):
            issue = managed[domain_key]
            raw_status, _ = domain_map[domain_key]
            state = active_client.get_issue_state(issue.key)
            domain_states[domain_key] = state
            matched_waivers = tuple(sorted(set(state.labels) & WAIVER_LABELS)) if respect_waivers else ()
            domain_waivers[domain_key] = matched_waivers
            if raw_status == "FAIL" and matched_waivers:
                effective_domain_status[domain_key] = "PASS"
                waived_domains.append(domain_key)
            else:
                effective_domain_status[domain_key] = raw_status

        if waived_domains:
            rollup_after_waivers = _aggregate_statuses([effective_domain_status[d] for d in leaf_domains])
            for rollup_key in ("QA-1", "QA-9"):
                if not domain_waivers[rollup_key]:
                    effective_domain_status[rollup_key] = rollup_after_waivers

        # Transition Epics based on effective aggregate status of their child domains
        for epic_def in EPIC_DEFINITIONS:
            phase_id = epic_def["phase_id"]
            if phase_id not in epics_by_phase:
                continue
            epic_issue = epics_by_phase[phase_id]
            child_statuses = [effective_domain_status[d] for d in epic_def["domains"]]
            epic_status = _aggregate_statuses(child_statuses)
            epic_transition = active_client.transition_to_any(epic_issue.key, _transition_targets(epic_status))
            synced_epics.append({
                "phase_id": phase_id,
                "epic_key": epic_issue.key,
                "epic_url": epic_issue.url,
                "status": epic_status,
                "transitioned_to": epic_transition,
            })

        sprint_display = str(active_sprint["name"]) if active_sprint else None

        for domain_key in sorted(ISSUE_SUMMARIES):
            issue = managed[domain_key]
            _, domain_records = domain_map[domain_key]
            domain_status = effective_domain_status[domain_key]
            waiver_lbls = domain_waivers[domain_key]
            label = _status_label(domain_status)
            phase_label = "saqa-phase-1" if domain_key in {"QA-1", "QA-2", "QA-3"} else (
                "saqa-phase-2" if domain_key in {"QA-4", "QA-5", "QA-6"} else "saqa-phase-3"
            )
            state = domain_states[domain_key]
            stale_labels = tuple(sorted((set(state.labels) & STATUS_LABELS) - {label}))
            active_client.update_labels(
                issue.key,
                add=("saqa-automation", f"saqa-{domain_key.lower()}", phase_label, f"saqa-lang-{code}", label),
                remove=tuple(sorted(set(stale_labels) | ({f"saqa-lang-{'en' if code == 'id' else 'id'}"} & set(state.labels)))),
            )

            start_date, due_date = domain_dates.get(
                domain_key,
                ((today - timedelta(days=7)).strftime("%Y-%m-%d"), (today + timedelta(days=7)).strftime("%Y-%m-%d")),
            )
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
                lang=code,
                active_sprint_name=sprint_display,
                waiver_labels=waiver_lbls,
            )

            if hasattr(active_client, "update_issue_fields"):
                priority_name = "Highest" if domain_status == "FAIL" else DOMAIN_PRIORITIES.get(domain_key, "High")
                field_payload: dict[str, Any] = {
                    "summary": target_summaries[domain_key],
                    "description": rich_description_adf,
                    "customfield_10015": start_date,
                    "duedate": due_date,
                    "priority": {"name": priority_name},
                    "environment": build_environment_adf(
                        target_display=target_display,
                        suite_name=suite_name,
                        manifest_sha256=manifest_sha256,
                        lang=code,
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

            marker = f"[SAQA-ADF-SYNC:{suite_name}:{sha_short}:{domain_key}:{code}]"
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
                lang=code,
                active_sprint_name=sprint_display,
                waiver_labels=waiver_lbls,
            )
            if hasattr(active_client, "add_adf_comment_once"):
                commented = active_client.add_adf_comment_once(issue.key, comment_adf, marker)
            else:
                commented = active_client.add_comment_once(issue.key, f"SAQA sync {marker}", marker)

            if files_for_domain:
                if hasattr(active_client, "upload_attachments_batch"):
                    batch_res = active_client.upload_attachments_batch(
                        issue.key,
                        files_for_domain,
                        skip_if_same_size=skip_unchanged_attachments,
                    )
                    for att in batch_res:
                        uploaded_attachments.append({
                            "issue_key": issue.key,
                            "filename": str(att.get("filename", "")),
                            "skipped_unchanged": bool(att.get("skipped_unchanged", False)),
                        })
                elif hasattr(active_client, "upload_attachment"):
                    for file_path in files_for_domain:
                        single_att = active_client.upload_attachment(issue.key, file_path)
                        if single_att:
                            uploaded_attachments.append({"issue_key": issue.key, "filename": file_path.name})

            if domain_status == "FAIL" and domain_key not in {"QA-1", "QA-9"}:
                bug_summary_en = tr("auto_bug_prefix", "en", suite=suite_name, domain=domain_key, target=target_display)
                bug_summary_id = tr("auto_bug_prefix", "id", suite=suite_name, domain=domain_key, target=target_display)
                bug_summary = bug_summary_id if code == "id" else bug_summary_en
                existing_map = active_client.find_project_issues()
                if bug_summary_en not in existing_map and bug_summary_id not in existing_map:
                    bug = active_client.create_bug(
                        bug_summary,
                        tr("auto_bug_desc", code, domain=domain_key, suite=suite_name, target=target_display, sha=manifest_sha256),
                        ["saqa-automation", "saqa-auto-defect", f"saqa-{domain_key.lower()}", f"saqa-lang-{code}"],
                    )
                    created_bugs.append(bug.key)
                    if active_sprint and hasattr(active_client, "move_issues_to_sprint"):
                        active_client.move_issues_to_sprint(int(active_sprint["id"]), [bug.key])
            elif domain_status == "PASS" and auto_resolve_bugs and not waiver_lbls:
                resolved_bugs.extend(
                    _resolve_stale_auto_bugs(
                        active_client,
                        domain_key=domain_key,
                        suite_name=suite_name,
                        manifest_sha256=manifest_sha256,
                        today_str=today_str,
                        lang=code,
                    )
                )

            synced_issues.append(
                {
                    "domain": domain_key,
                    "summary": target_summaries[domain_key],
                    "issue_key": issue.key,
                    "issue_url": issue.url,
                    "parent_epic": parent_epic_key,
                    "start_date": start_date,
                    "due_date": due_date,
                    "status": domain_status,
                    "waived": bool(waiver_lbls),
                    "label": label,
                    "transitioned_to": transitioned_to,
                    "comment_added": commented,
                }
            )

        return {
            "project_key": project.key,
            "project_name": project.name,
            "language": code,
            "suite_name": suite_name,
            "overall_status": analytics["overall_status"],
            "health_score": analytics["health_score"],
            "manifest_sha256": manifest_sha256,
            "active_sprint": active_sprint,
            "waived_domains": waived_domains,
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
    sprint_start: str | None = None,
    sprint_end: str | None = None,
    skip_unchanged_attachments: bool = True,
    lang: str | None = None,
    respect_waivers: bool = True,
    sync_agile_sprint: bool = True,
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
            parent / "qa-executive-report.pdf",
            parent / "report.html",
            parent / "report.md",
            parent / "junit.xml",
            parent / "results.sarif",
            parent / "qa-test-matrix.csv",
            parent / "qa-scorecard.png",
            parent / "qa-analytics-chart.svg",
            parent / "screenshot-desktop.png",
            parent / "screenshot-tablet.png",
            parent / "screenshot-mobile.png",
            parent / "visual-diff.png",
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
        sprint_start=sprint_start,
        sprint_end=sprint_end,
        skip_unchanged_attachments=skip_unchanged_attachments,
        lang=lang,
        respect_waivers=respect_waivers,
        sync_agile_sprint=sync_agile_sprint,
        client=client,
    )
