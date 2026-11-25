"""Self-contained interactive HTML dashboard, Markdown reporter, JUnit XML, and SARIF v2.1.0 exporters (EN/ID)."""
from __future__ import annotations

import html
import json
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import Any

from . import __version__
from .evidence import EvidenceRecord
from .i18n import normalize_lang, tr, translate_finding_or_reason, translate_recommendation


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _record_dict(item: EvidenceRecord | Mapping[str, Any]) -> dict[str, Any]:
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


def render_junit_xml(
    analytics: Mapping[str, Any],
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    *,
    suite_name: str = "saqa-suite",
) -> str:
    """Export SAQA evidence records into standard JUnit XML for GitHub/GitLab/Jenkins/Jira Xray."""
    norm_records = [_record_dict(r) for r in records]
    counts = analytics["status_counts"]
    total_time_s = 0.0
    for rec in norm_records:
        ms = rec["details"].get("elapsed_ms", rec["details"].get("duration_ms", 0.0))
        if isinstance(ms, (int, float)):
            total_time_s += float(ms) / 1000.0

    skipped_count = int(counts.get("BLOCKED", 0)) + int(counts.get("NOT_APPLICABLE", 0)) + int(counts.get("UNVERIFIED", 0))
    suites_el = ET.Element("testsuites")
    suite_el = ET.SubElement(
        suites_el,
        "testsuite",
        {
            "name": suite_name,
            "tests": str(len(norm_records)),
            "failures": str(counts.get("FAIL", 0)),
            "errors": "0",
            "skipped": str(skipped_count),
            "time": f"{total_time_s:.3f}",
        },
    )
    props_el = ET.SubElement(suite_el, "properties")
    for prop_name, prop_val in (
        ("saqa.version", __version__),
        ("saqa.health_score", str(analytics.get("health_score", ""))),
        ("saqa.health_grade", str(analytics.get("health_grade", ""))),
        ("saqa.manifest_sha256", str(analytics.get("manifest_sha256") or "")),
    ):
        ET.SubElement(props_el, "property", {"name": prop_name, "value": prop_val})

    for rec in norm_records:
        det = rec["details"]
        ms = det.get("elapsed_ms", det.get("duration_ms", 0.0))
        sec = (float(ms) / 1000.0) if isinstance(ms, (int, float)) else 0.0
        case_el = ET.SubElement(
            suite_el,
            "testcase",
            {
                "classname": str(det.get("suite") or suite_name),
                "name": rec["test_id"],
                "time": f"{sec:.3f}",
            },
        )
        status = rec["status"]
        reasons = det.get("failure_reasons") or ([] if not det.get("error") else [str(det["error"])])
        msg = "; ".join(str(r) for r in reasons) if reasons else f"Status: {status}"
        if status == "FAIL":
            fail_el = ET.SubElement(case_el, "failure", {"message": msg[:500], "type": "SAQAQualityGateFailure"})
            fail_el.text = json.dumps(det, indent=2, sort_keys=True)
        elif status in {"BLOCKED", "NOT_APPLICABLE", "UNVERIFIED"}:
            ET.SubElement(case_el, "skipped", {"message": msg[:500], "type": status})

    xml_body = ET.tostring(suites_el, encoding="unicode")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + xml_body + "\n"


def render_sarif_report(
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    *,
    suite_name: str = "saqa-suite",
) -> dict[str, Any]:
    """Export SAQA security, accessibility, and quality findings as SARIF v2.1.0 for GitHub Code Scanning."""
    norm_records = [_record_dict(r) for r in records]
    rules: list[dict[str, Any]] = []
    seen_rules: set[str] = set()
    sarif_results: list[dict[str, Any]] = []

    for rec in norm_records:
        rule_id = rec["test_id"]
        det = rec["details"]
        case_name = str(det.get("case_name") or rule_id)
        if rule_id not in seen_rules:
            seen_rules.add(rule_id)
            rules.append({
                "id": rule_id,
                "name": rule_id.replace(".", "_").replace("-", "_"),
                "shortDescription": {"text": case_name},
                "properties": {"tags": list(det.get("tags") or []), "suite": suite_name},
            })

        failures = [str(f) for f in (det.get("failure_reasons") or [])]
        warnings = [str(w) for w in (det.get("warnings") or [])]

        if rec["status"] == "FAIL":
            message_text = "; ".join(failures) if failures else f"{case_name} failed verification"
            sarif_results.append({
                "ruleId": rule_id,
                "level": "error",
                "message": {"text": message_text},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": rec["target"]},
                        }
                    }
                ],
            })
        elif warnings:
            for warn in warnings:
                sarif_results.append({
                    "ruleId": rule_id,
                    "level": "warning",
                    "message": {"text": warn},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": rec["target"]},
                            }
                        }
                    ],
                })

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "SAQA Professional Framework",
                        "version": __version__,
                        "informationUri": "https://github.com/uknowdream/saqa-professional-framework",
                        "rules": rules,
                    }
                },
                "results": sarif_results,
            }
        ],
    }


def render_markdown_report(
    analytics: Mapping[str, Any],
    *,
    diff: Mapping[str, Any] | None = None,
    history: Mapping[str, Any] | None = None,
    title: str = "SAQA Quality Report",
    lang: str = "en",
) -> str:
    """Render an executive GitHub-flavored Markdown QA summary (EN/ID)."""
    code = normalize_lang(lang)
    counts = analytics["status_counts"]
    latency = analytics["latency"]
    lines = [
        f"# {title}",
        "",
        f"- **{tr('rpt_overall_status', code)}:** `{analytics['overall_status']}`",
        f"- **{tr('rpt_health_score', code)}:** `{analytics['health_score']} / 100` (Grade **{analytics['health_grade']}**)",
        f"- **{tr('rpt_pass_rate', code)}:** `{analytics['pass_rate_pct']}%` ({counts['PASS']} PASS / {counts['FAIL']} FAIL / {counts['BLOCKED']} BLOCKED / {counts['UNVERIFIED']} UNVERIFIED)",
    ]
    if analytics.get("manifest_sha256"):
        lines.append(f"- **Evidence SHA-256:** `{analytics['manifest_sha256']}`")
    if latency["count"] > 0:
        lines.append(
            f"- **{'Latensi (ms)' if code == 'id' else 'Latency (ms)'}:** min `{latency['min_ms']}` · p50 `{latency['p50_ms']}` · "
            f"p95 `{latency['p95_ms']}` · p99 `{latency['p99_ms']}` · max `{latency['max_ms']}`"
        )

    lines.extend([
        "",
        f"## {tr('rpt_summary_metrics', code)}",
        "",
        f"| {tr('rpt_metric', code)} | {tr('rpt_value', code)} |",
        "|---|---|",
    ])
    lines.append(f"| {tr('rpt_total_records', code)} | {analytics['total_records']} |")
    lines.append(f"| {tr('rpt_applicable_records', code)} | {analytics['applicable_records']} |")
    lines.append(f"| {tr('rpt_pass_rate', code)} | {analytics['pass_rate_pct']}% |")
    lines.append(f"| {tr('rpt_fail_rate', code)} | {analytics['fail_rate_pct']}% |")
    lines.append(f"| {tr('rpt_health_score', code)} | {analytics['health_score']} ({analytics['health_grade']}) |")

    if analytics.get("failing_tests"):
        lines.extend([
            "",
            f"## {tr('rpt_failing_tests', code)}",
            "",
            f"| {tr('col_test_id', code)} | {tr('col_target', code)} | {tr('rpt_reasons', code)} |",
            "|---|---|---|",
        ])
        for item in analytics["failing_tests"]:
            reasons = "; ".join(translate_finding_or_reason(str(r), code) for r in (item.get("reasons") or ["Failed without detail"]))
            lines.append(f"| `{item['test_id']}` | `{item['target']}` | {reasons} |")

    if analytics.get("slowest_tests"):
        lines.extend([
            "",
            f"## {tr('rpt_slowest_tests', code)}",
            "",
            f"| {tr('col_test_id', code)} | {tr('col_status', code)} | {'Latensi (ms)' if code == 'id' else 'Latency (ms)'} | {tr('col_target', code)} |",
            "|---|---|---|---|",
        ])
        for item in analytics["slowest_tests"][:5]:
            lines.append(f"| `{item['test_id']}` | `{item['status']}` | {item['elapsed_ms']} | `{item['target']}` |")

    if diff is not None:
        lines.extend([
            "",
            f"## Baseline Comparison (`{diff['verdict']}`)",
            "",
            f"- **Pass Rate Delta:** `{diff['pass_rate_delta_pct']:+.2f}%`",
            f"- **Health Score Delta:** `{diff['health_score_delta']:+.2f}`",
            f"- **New Failures:** `{len(diff['new_failures'])}` | **Fixed:** `{len(diff['fixed'])}` | "
            f"**Latency Regressions:** `{len(diff['latency_regressions'])}`",
        ])
        if diff["new_failures"]:
            lines.append("")
            for item in diff["new_failures"]:
                lines.append(
                    f"  - Regression `{item['test_id']}`: `{item['baseline_status']}` -> `{item['current_status']}`"
                )
        if diff["latency_regressions"]:
            lines.append("")
            for item in diff["latency_regressions"]:
                lines.append(
                    f"  - Latency regression `{item['test_id']}`: "
                    f"`{item['baseline_ms']}ms` -> `{item['current_ms']}ms` (`+{item['delta_pct']}%`)"
                )

    if history is not None:
        flaky = history["flakiness"]
        lines.extend([
            "",
            "## Historical Stability & Flakiness",
            "",
            f"- **Commits Tracked:** `{history['commit_count']}` (Hash Chain Verified: `{history['chain_verified']}`)",
            f"- **Latest Pass Rate Trend:** `{history['pass_rate_trend_delta_pct']:+.2f}%`",
            f"- **Flaky Tests Detected:** `{len(flaky['flaky_tests'])}` | "
            f"**Quarantine Candidates:** `{len(flaky['quarantine_candidates'])}`",
        ])
        if flaky["flaky_tests"]:
            lines.extend(["", "| Test ID | Flakiness Score | Pass Rate | Transitions | Quarantine |", "|---|---|---|---|---|"])
            for item in flaky["flaky_tests"][:10]:
                lines.append(
                    f"| `{item['test_id']}` | {item['flakiness_score']} | "
                    f"{round(item['pass_rate'] * 100, 1)}% | {item['transition_count']} | "
                    f"`{'YES' if item['quarantine_recommended'] else 'NO'}` |"
                )

    rec_hdr = "Rekomendasi" if code == "id" else "Recommendations"
    lines.extend(["", f"## {rec_hdr}", ""])
    for rec in analytics.get("recommendations", []):
        lines.append(f"- {translate_recommendation(str(rec), code)}")

    return "\n".join(lines) + "\n"


def render_html_report(
    analytics: Mapping[str, Any],
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    *,
    diff: Mapping[str, Any] | None = None,
    history: Mapping[str, Any] | None = None,
    manifest_sha256: str | None = None,
    title: str = "SAQA Quality Report",
    lang: str = "en",
) -> str:
    """Render a self-contained, offline-ready, XSS-safe interactive HTML QA dashboard (EN/ID)."""
    code = normalize_lang(lang)
    norm_records = [_record_dict(rec) for rec in records]
    counts = analytics["status_counts"]
    latency = analytics["latency"]
    sha = manifest_sha256 or analytics.get("manifest_sha256") or "unhashed-in-memory"
    total = max(1, analytics["total_records"])

    pass_w = round((counts["PASS"] / total) * 100, 2)
    fail_w = round((counts["FAIL"] / total) * 100, 2)
    blocked_w = round((counts["BLOCKED"] / total) * 100, 2)
    unverified_w = round((counts["UNVERIFIED"] / total) * 100, 2)

    rows_html: list[str] = []
    for rec in norm_records:
        status = rec["status"]
        details = rec["details"]
        elapsed = details.get("elapsed_ms", details.get("duration_ms", "-"))
        elapsed_str = f"{elapsed} ms" if isinstance(elapsed, (int, float)) else "-"
        reasons = details.get("failure_reasons") or ([] if not details.get("error") else [str(details["error"])])
        passed_suffix = "pemeriksaan lulus" if code == "id" else "check(s) passed"
        summary_msg = "; ".join(translate_finding_or_reason(str(r), code) for r in reasons) if reasons else f"{len(details.get('checks_passed', []))} {passed_suffix}"
        pretty_json = _esc(json.dumps(details, indent=2, sort_keys=True))
        rows_html.append(
            f'<tr class="case-row" data-status="{_esc(status)}" data-search="{_esc(rec["test_id"].lower() + " " + rec["target"].lower() + " " + summary_msg.lower())}">'
            f'<td><span class="badge status-{_esc(status)}">{_esc(status)}</span></td>'
            f'<td><code>{_esc(rec["test_id"])}</code></td>'
            f'<td><code>{_esc(rec["target"])}</code></td>'
            f'<td class="num">{_esc(elapsed_str)}</td>'
            f'<td>{_esc(summary_msg)}<details><summary>{_esc(tr("rpt_details_json", code))}</summary><pre>{pretty_json}</pre></details></td>'
            f"</tr>"
        )

    diff_html = ""
    if diff is not None:
        diff_items = []
        for item in diff["new_failures"]:
            diff_items.append(
                f"<li><span class='badge status-FAIL'>NEW FAIL</span> <code>{_esc(item['test_id'])}</code> "
                f"({_esc(item['baseline_status'])} &rarr; {_esc(item['current_status'])})</li>"
            )
        for item in diff["fixed"]:
            diff_items.append(
                f"<li><span class='badge status-PASS'>FIXED</span> <code>{_esc(item['test_id'])}</code> "
                f"({_esc(item['baseline_status'])} &rarr; {_esc(item['current_status'])})</li>"
            )
        for item in diff["latency_regressions"]:
            diff_items.append(
                f"<li><span class='badge status-BLOCKED'>SLOWER</span> <code>{_esc(item['test_id'])}</code> "
                f"{_esc(item['baseline_ms'])}ms &rarr; {_esc(item['current_ms'])}ms (+{_esc(item['delta_pct'])}%)</li>"
            )
        diff_list = "".join(diff_items) or "<li>No regressions or status transitions detected against baseline.</li>"
        diff_html = f"""
        <section class="panel">
          <h2>Baseline Comparison &mdash; <span class="badge status-{'FAIL' if diff['verdict'] == 'REGRESSED' else 'PASS'}">{_esc(diff['verdict'])}</span></h2>
          <p class="muted">Pass Rate Delta: <strong>{diff['pass_rate_delta_pct']:+.2f}%</strong> &middot;
          Health Score Delta: <strong>{diff['health_score_delta']:+.2f}</strong> &middot;
          New Failures: <strong>{len(diff['new_failures'])}</strong> &middot;
          Fixed: <strong>{len(diff['fixed'])}</strong></p>
          <ul class="clean-list">{diff_list}</ul>
        </section>
        """

    history_html = ""
    if history is not None:
        flaky = history["flakiness"]
        flaky_rows = "".join(
            f"<tr><td><code>{_esc(item['test_id'])}</code></td><td>{_esc(item['flakiness_score'])}</td>"
            f"<td>{round(item['pass_rate'] * 100, 1)}%</td><td>{_esc(item['transition_count'])}</td>"
            f"<td><span class='badge {'status-FAIL' if item['quarantine_recommended'] else 'status-PASS'}'>"
            f"{'QUARANTINE' if item['quarantine_recommended'] else 'MONITOR'}</span></td></tr>"
            for item in flaky["flaky_tests"]
        ) or "<tr><td colspan='5' class='muted'>No flaky tests detected across tracked commits.</td></tr>"
        history_html = f"""
        <section class="panel">
          <h2>Historical Stability &amp; Flakiness ({_esc(history['commit_count'])} commits)</h2>
          <table>
            <thead><tr><th>Test ID</th><th>Flakiness Score</th><th>Pass Rate</th><th>Transitions</th><th>Action</th></tr></thead>
            <tbody>{flaky_rows}</tbody>
          </table>
        </section>
        """

    recs_html = "".join(f"<li>{_esc(translate_recommendation(str(rec), code))}</li>" for rec in analytics.get("recommendations", []))

    return f"""<!DOCTYPE html>
<html lang="{code}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{_esc(title)}</title>
<style>
  :root {{
    --bg: #0f172a; --panel: #1e293b; --border: #334155; --text: #e2e8f0; --muted: #94a3b8;
    --pass: #22c55e; --fail: #ef4444; --blocked: #f59e0b; --unverified: #a855f7; --accent: #38bdf8;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
  .wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
  header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 20px; }}
  h1 {{ margin: 0; font-size: 1.6rem; }}
  h2 {{ margin: 0 0 12px 0; font-size: 1.1rem; }}
  .muted {{ color: var(--muted); font-size: 0.9rem; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 20px; }}
  .kpi {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }}
  .kpi-label {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
  .kpi-val {{ font-size: 1.7rem; font-weight: 700; margin-top: 4px; }}
  .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 18px; margin-bottom: 18px; }}
  .bar {{ display: flex; height: 14px; border-radius: 999px; overflow: hidden; background: #0b1220; margin: 10px 0 6px; }}
  .seg-pass {{ background: var(--pass); }} .seg-fail {{ background: var(--fail); }}
  .seg-blocked {{ background: var(--blocked); }} .seg-unverified {{ background: var(--unverified); }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }}
  .btn {{ background: #0f172a; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 0.85rem; }}
  .btn.active, .btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  input[type="search"] {{ background: #0f172a; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; min-width: 240px; margin-left: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ color: var(--muted); font-weight: 600; }}
  td.num {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
  code {{ background: #0b1220; padding: 2px 6px; border-radius: 6px; font-size: 0.85em; }}
  pre {{ background: #0b1220; padding: 10px; border-radius: 8px; overflow-x: auto; font-size: 0.8rem; margin: 8px 0 0; }}
  details summary {{ cursor: pointer; color: var(--accent); font-size: 0.8rem; margin-top: 4px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 700; }}
  .status-PASS {{ background: rgba(34,197,94,0.18); color: #86efac; }}
  .status-FAIL {{ background: rgba(239,68,68,0.2); color: #fca5a5; }}
  .status-BLOCKED {{ background: rgba(245,158,11,0.2); color: #fcd34d; }}
  .status-UNVERIFIED {{ background: rgba(168,85,247,0.2); color: #d8b4fe; }}
  .status-NOT_APPLICABLE {{ background: rgba(148,163,184,0.2); color: #cbd5e1; }}
  .clean-list {{ margin: 0; padding-left: 18px; }}
  .sha {{ font-family: monospace; font-size: 0.78rem; color: var(--muted); word-break: break-all; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>{_esc(title)}</h1>
      <div class="sha">Evidence SHA-256: {_esc(sha)}</div>
    </div>
    <span class="badge status-{_esc(analytics['overall_status'])}">{_esc(analytics['overall_status'])}</span>
  </header>

  <div class="kpi-grid">
    <div class="kpi"><div class="kpi-label">{_esc(tr('rpt_health_score', code))}</div><div class="kpi-val">{_esc(analytics['health_score'])} <span class="muted">({_esc(analytics['health_grade'])})</span></div></div>
    <div class="kpi"><div class="kpi-label">{_esc(tr('rpt_pass_rate', code))}</div><div class="kpi-val">{_esc(analytics['pass_rate_pct'])}%</div></div>
    <div class="kpi"><div class="kpi-label">{_esc(tr('rpt_checks_executed', code))}</div><div class="kpi-val">{_esc(analytics['total_records'])}</div></div>
    <div class="kpi"><div class="kpi-label">{'Latensi P95' if code == 'id' else 'Latency P95'}</div><div class="kpi-val">{_esc(latency['p95_ms'])} <span class="muted">ms</span></div></div>
    <div class="kpi"><div class="kpi-label">{'Latensi Rata-rata' if code == 'id' else 'Latency Mean'}</div><div class="kpi-val">{_esc(latency['mean_ms'])} <span class="muted">ms</span></div></div>
  </div>

  <section class="panel">
    <h2>{_esc(tr('rpt_status_dist', code))}</h2>
    <div class="bar">
      <div class="seg-pass" style="width:{pass_w}%"></div>
      <div class="seg-fail" style="width:{fail_w}%"></div>
      <div class="seg-blocked" style="width:{blocked_w}%"></div>
      <div class="seg-unverified" style="width:{unverified_w}%"></div>
    </div>
    <div class="muted">PASS: {counts['PASS']} &middot; FAIL: {counts['FAIL']} &middot; BLOCKED: {counts['BLOCKED']} &middot; UNVERIFIED: {counts['UNVERIFIED']} &middot; N/A: {counts['NOT_APPLICABLE']}</div>
  </section>

  {diff_html}
  {history_html}

  <section class="panel">
    <h2>{_esc(tr('rpt_recommendations', code))}</h2>
    <ul class="clean-list">{recs_html}</ul>
  </section>

  <section class="panel">
    <h2>{_esc(tr('rpt_executed_evidence', code))}</h2>
    <div class="controls">
      <button class="btn active" data-filter="ALL">{_esc(tr('rpt_all', code))} ({analytics['total_records']})</button>
      <button class="btn" data-filter="PASS">PASS ({counts['PASS']})</button>
      <button class="btn" data-filter="FAIL">FAIL ({counts['FAIL']})</button>
      <button class="btn" data-filter="BLOCKED">BLOCKED ({counts['BLOCKED']})</button>
      <button class="btn" data-filter="UNVERIFIED">UNVERIFIED ({counts['UNVERIFIED']})</button>
      <input type="search" id="qa-search" placeholder="{_esc(tr('rpt_search_placeholder', code))}" />
    </div>
    <table>
      <thead><tr><th>{_esc(tr('col_status', code))}</th><th>{_esc(tr('col_test_id', code))}</th><th>{_esc(tr('col_target', code))}</th><th>{_esc(tr('col_latency', code))}</th><th>{_esc(tr('rpt_checks_details', code))}</th></tr></thead>
      <tbody id="qa-rows">{''.join(rows_html)}</tbody>
    </table>
  </section>
</div>
<script>
(function() {{
  var activeFilter = 'ALL';
  var searchEl = document.getElementById('qa-search');
  var rows = Array.prototype.slice.call(document.querySelectorAll('.case-row'));
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.btn[data-filter]'));
  function applyFilters() {{
    var q = (searchEl.value || '').trim().toLowerCase();
    rows.forEach(function(row) {{
      var statusOk = activeFilter === 'ALL' || row.getAttribute('data-status') === activeFilter;
      var textOk = !q || (row.getAttribute('data-search') || '').indexOf(q) !== -1;
      row.style.display = (statusOk && textOk) ? '' : 'none';
    }});
  }}
  buttons.forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      buttons.forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      activeFilter = btn.getAttribute('data-filter');
      applyFilters();
    }});
  }});
  searchEl.addEventListener('input', applyFilters);
}})();
</script>
</body>
</html>
"""
