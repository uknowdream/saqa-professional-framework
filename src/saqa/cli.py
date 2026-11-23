"""Unified command-line interface for the SAQA Professional Framework."""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .analytics import (
    analyze_history_file,
    analyze_manifest,
    compare_manifests,
    load_verified_manifest,
)
from .evidence import verify_manifest
from .history import append_history
from .jira_sync import sync_manifest_to_jira, sync_records_to_jira
from .reporting import render_html_report, render_markdown_report
from .runner import create_starter_suite, load_suite_file, run_suite
from .target_registry import DEFAULT_TARGETS
from .test_design import (
    SyntheticDataFactory,
    boundary_value_numeric,
    boundary_value_string,
    error_guessing_payloads,
    pairwise_matrix,
    verify_pairwise_coverage,
)


def _check_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saqa",
        description="SAQA Professional Framework — QA Automation Command Center",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version", help="Print the SAQA framework version.")

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check local QA workstation readiness (Python version, optional runtimes).",
    )
    doctor_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    targets_parser = subparsers.add_parser("targets", help="List registered authorized reference targets.")
    targets_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    init_parser = subparsers.add_parser("init-suite", help="Scaffold a declarative QA API/HTTP test suite JSON file.")
    init_parser.add_argument("output", type=Path, help="Output path for the suite JSON file.")
    init_parser.add_argument("--name", default="saqa-api-smoke", help="Suite name.")
    init_parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="Default local target base URL.")

    run_parser = subparsers.add_parser("run-suite", help="Execute a declarative QA suite and emit evidence & reports.")
    run_parser.add_argument("suite", type=Path, help="Path to the declarative suite JSON file.")
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/suite"),
        help="Directory for evidence-manifest.json and suite-summary.json.",
    )
    run_parser.add_argument("--html", type=Path, default=None, help="Optional path to write interactive HTML dashboard.")
    run_parser.add_argument("--md", type=Path, default=None, help="Optional path to write Markdown report.")
    run_parser.add_argument("--baseline", type=Path, default=None, help="Optional baseline manifest for regression diff.")
    run_parser.add_argument("--history", type=Path, default=None, help="Optional hash-chained history JSONL file.")
    run_parser.add_argument("--commit-sha", default=None, help="Commit SHA recorded when appending to --history.")
    run_parser.add_argument(
        "--sync-jira",
        action="store_true",
        help="Automatically synchronize suite evidence, labels, transitions, and comments to Jira.",
    )
    run_parser.add_argument("--json", action="store_true", dest="as_json", help="Print full analytics JSON to stdout.")

    sync_jira_parser = subparsers.add_parser(
        "sync-jira",
        help="Synchronize a verified SAQA evidence manifest directly into Jira Cloud (QA-1..QA-9).",
    )
    sync_jira_parser.add_argument("manifest", type=Path, help="Path to verified evidence manifest JSON.")
    sync_jira_parser.add_argument("--suite-name", default=None, help="Optional suite name override.")
    sync_jira_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    verify_parser = subparsers.add_parser(
        "verify-manifest",
        help="Verify SHA-256 integrity and schema of an evidence manifest.",
    )
    verify_parser.add_argument("path", type=Path, help="Path to the evidence manifest JSON file.")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Compute Quality Intelligence metrics for an evidence manifest (.json) or history (.jsonl).",
    )
    analyze_parser.add_argument("path", type=Path, help="Path to manifest JSON or hash-chained history JSONL.")
    analyze_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    diff_parser = subparsers.add_parser(
        "diff",
        help="Compare baseline vs current evidence manifests for regressions and latency drift.",
    )
    diff_parser.add_argument("baseline", type=Path, help="Baseline evidence manifest JSON.")
    diff_parser.add_argument("current", type=Path, help="Current evidence manifest JSON.")
    diff_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")
    diff_parser.add_argument("--md", type=Path, default=None, help="Optional path to write Markdown diff summary.")
    diff_parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when verdict is REGRESSED.",
    )

    report_parser = subparsers.add_parser(
        "report",
        help="Generate interactive HTML and/or Markdown QA reports from a verified manifest.",
    )
    report_parser.add_argument("manifest", type=Path, help="Path to verified evidence manifest JSON.")
    report_parser.add_argument("--html", type=Path, default=None, help="Path to write interactive HTML report.")
    report_parser.add_argument("--md", type=Path, default=None, help="Path to write Markdown report.")
    report_parser.add_argument("--baseline", type=Path, default=None, help="Optional baseline manifest for comparison.")
    report_parser.add_argument("--history", type=Path, default=None, help="Optional history JSONL for flakiness panel.")
    report_parser.add_argument("--title", default="SAQA Quality Report", help="Report title.")

    gen_parser = subparsers.add_parser(
        "generate-data",
        help="Generate deterministic QA test design cases or synthetic data.",
    )
    gen_parser.add_argument(
        "kind",
        choices=("bva", "bva-str", "pairwise", "users", "invoices", "edge-cases"),
        help="Type of QA data or black-box test matrix to generate.",
    )
    gen_parser.add_argument("--seed", type=int, default=20260927, help="Deterministic random seed.")
    gen_parser.add_argument("--count", type=int, default=5, help="Number of users/invoices to generate.")
    gen_parser.add_argument("--min", type=float, default=0.0, dest="min_val", help="Lower bound for BVA.")
    gen_parser.add_argument("--max", type=float, default=100.0, dest="max_val", help="Upper bound for BVA.")
    gen_parser.add_argument("--step", type=float, default=1.0, help="Step size for numeric BVA.")
    gen_parser.add_argument("--spec", type=Path, default=None, help="JSON file mapping parameter names to value lists (for pairwise).")
    gen_parser.add_argument("--category", default="all", help="Category for edge-cases (all, strings, numbers, dates, security_probes, json_types).")
    gen_parser.add_argument("--output", type=Path, default=None, help="Optional file path to write JSON output.")

    return parser


def _cmd_doctor(as_json: bool) -> int:
    py_ok = sys.version_info >= (3, 11)
    modules = {
        "httpx": _check_module("httpx"),
        "pytest": _check_module("pytest"),
        "jsonschema": _check_module("jsonschema"),
        "playwright": _check_module("playwright"),
    }
    report = {
        "framework_version": __version__,
        "python_version": platform.python_version(),
        "python_supported": py_ok,
        "platform": platform.platform(),
        "modules": modules,
        "ready": py_ok and modules["httpx"],
    }
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"SAQA Doctor v{__version__} | Python {report['python_version']} ({'OK' if py_ok else 'UNSUPPORTED <3.11'})")
        for mod, installed in modules.items():
            print(f"  - {mod}: {'installed' if installed else 'not installed'}")
        print(f"Status: {'READY' if report['ready'] else 'ACTION_REQUIRED'}")
    return 0 if report["ready"] else 1


def _coerce_numeric(value: int | float) -> int | float:
    as_float = float(value)
    return int(as_float) if as_float.is_integer() else as_float


def _cmd_generate_data(args: argparse.Namespace) -> int:
    payload: Any
    if args.kind == "bva":
        min_v = _coerce_numeric(args.min_val)
        max_v = _coerce_numeric(args.max_val)
        step_v = _coerce_numeric(args.step)
        payload = [case.to_dict() for case in boundary_value_numeric(min_v, max_v, step=step_v)]
    elif args.kind == "bva-str":
        payload = [
            case.to_dict()
            for case in boundary_value_string(int(args.min_val), int(args.max_val))
        ]
    elif args.kind == "pairwise":
        if args.spec is not None:
            params = json.loads(args.spec.read_text(encoding="utf-8"))
        else:
            params = {
                "browser": ["chromium", "firefox", "webkit"],
                "viewport": ["desktop", "tablet", "mobile"],
                "role": ["guest", "user", "admin"],
                "locale": ["en-US", "id-ID"],
            }
        cases = pairwise_matrix(params, seed=args.seed)
        payload = {
            "coverage": verify_pairwise_coverage(params, cases),
            "cases": cases,
        }
    elif args.kind == "users":
        payload = SyntheticDataFactory(seed=args.seed).users(args.count)
    elif args.kind == "invoices":
        factory = SyntheticDataFactory(seed=args.seed)
        payload = [factory.invoice() for _ in range(args.count)]
    else:
        payload = error_guessing_payloads(args.category)

    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"GENERATED_DATA: {args.output}")
    else:
        print(rendered)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(f"saqa-professional-framework {__version__}")
        return 0

    if args.command == "doctor":
        return _cmd_doctor(args.as_json)

    if args.command == "targets":
        records = [
            {
                "name": target.name,
                "kind": target.kind.value,
                "deployment": target.deployment.value,
                "base_url": target.base_url,
                "authorized": target.authorized,
                "certifiable": target.certifiable,
                "tags": sorted(target.tags),
            }
            for target in DEFAULT_TARGETS
        ]
        if args.as_json:
            print(json.dumps(records, indent=2))
        else:
            for item in records:
                print(
                    f"{item['name']} ({item['kind']}/{item['deployment']}) "
                    f"{item['base_url']} certifiable={item['certifiable']}"
                )
        return 0

    if args.command == "init-suite":
        template = create_starter_suite(name=args.name, base_url=args.base_url)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(template, indent=2) + "\n", encoding="utf-8")
        print(f"SUITE_INITIALIZED: {args.output}")
        return 0

    if args.command == "run-suite":
        suite = load_suite_file(args.suite)
        result = run_suite(suite, output_dir=args.output_dir)

        diff = None
        if args.baseline is not None and result.manifest_path is not None:
            diff = compare_manifests(args.baseline, result.manifest_path)

        history_stats = None
        if args.history is not None:
            if args.commit_sha:
                append_history(list(result.records), args.history, commit_sha=args.commit_sha)
            if args.history.exists():
                history_stats = analyze_history_file(args.history)

        if args.html is not None:
            args.html.parent.mkdir(parents=True, exist_ok=True)
            args.html.write_text(
                render_html_report(
                    result.analytics,
                    result.records,
                    diff=diff,
                    history=history_stats,
                    manifest_sha256=result.manifest_sha256,
                    title=f"SAQA Report — {result.suite_name}",
                ),
                encoding="utf-8",
            )
        if args.md is not None:
            args.md.parent.mkdir(parents=True, exist_ok=True)
            args.md.write_text(
                render_markdown_report(
                    result.analytics,
                    diff=diff,
                    history=history_stats,
                    title=f"SAQA Report — {result.suite_name}",
                ),
                encoding="utf-8",
            )

        jira_summary = None
        if args.sync_jira:
            jira_summary = sync_records_to_jira(
                result.records,
                suite_name=result.suite_name,
                manifest_sha256=result.manifest_sha256,
            )

        if args.as_json:
            print(json.dumps({"analytics": result.analytics, "diff": diff, "jira": jira_summary}, indent=2))
        else:
            a = result.analytics
            jira_msg = (
                f" | Jira {jira_summary['project_key']} ({len(jira_summary['synced_issues'])} issues synced)"
                if jira_summary
                else ""
            )
            print(
                f"SUITE {result.suite_name}: {a['overall_status']} | "
                f"Health {a['health_score']}/100 ({a['health_grade']}) | "
                f"Pass {a['pass_rate_pct']}% | P95 {a['latency']['p95_ms']}ms | "
                f"Manifest {result.manifest_path}{jira_msg}"
            )
        return 0 if result.passed else 1

    if args.command == "sync-jira":
        jira_summary = sync_manifest_to_jira(args.manifest, suite_name=args.suite_name)
        if args.as_json:
            print(json.dumps(jira_summary, indent=2))
        else:
            print(
                f"JIRA_SYNC_PASS: project={jira_summary['project_key']} "
                f"suite={jira_summary['suite_name']} status={jira_summary['overall_status']} "
                f"issues_synced={len(jira_summary['synced_issues'])}"
            )
            for item in jira_summary["synced_issues"]:
                print(
                    f"  - {item['issue_key']} ({item['domain']}): {item['status']} "
                    f"[{item['label']}] -> {item['transitioned_to'] or 'unchanged'} | {item['issue_url']}"
                )
        return 0

    if args.command == "verify-manifest":
        ok = verify_manifest(args.path)
        if ok:
            print(f"MANIFEST_VALID: {args.path}")
            return 0
        print(f"MANIFEST_INVALID: {args.path}", file=sys.stderr)
        return 1

    if args.command == "analyze":
        if args.path.suffix.lower() == ".jsonl":
            stats = analyze_history_file(args.path)
        else:
            stats = analyze_manifest(args.path)
        if args.as_json:
            print(json.dumps(stats, indent=2))
        elif stats.get("schema") == "saqa.history_analytics.v1":
            print(
                f"HISTORY: commits={stats['commit_count']} latest_pass={stats['latest_pass_rate_pct']}% "
                f"trend={stats['pass_rate_trend_delta_pct']:+.2f}% "
                f"flaky={len(stats['flakiness']['flaky_tests'])}"
            )
        else:
            print(
                f"ANALYTICS: {stats['overall_status']} | Health {stats['health_score']}/100 ({stats['health_grade']}) | "
                f"Pass {stats['pass_rate_pct']}% | P95 {stats['latency']['p95_ms']}ms"
            )
        return 0

    if args.command == "diff":
        diff = compare_manifests(args.baseline, args.current)
        if args.md is not None:
            curr_stats = analyze_manifest(args.current)
            args.md.parent.mkdir(parents=True, exist_ok=True)
            args.md.write_text(
                render_markdown_report(curr_stats, diff=diff, title="SAQA Regression Diff Report"),
                encoding="utf-8",
            )
        if args.as_json:
            print(json.dumps(diff, indent=2))
        else:
            print(
                f"DIFF {diff['verdict']} | Pass delta {diff['pass_rate_delta_pct']:+.2f}% | "
                f"New failures={len(diff['new_failures'])} Fixed={len(diff['fixed'])} "
                f"Latency regressions={len(diff['latency_regressions'])}"
            )
        if args.fail_on_regression and diff["verdict"] == "REGRESSED":
            return 1
        return 0

    if args.command == "report":
        records, sha = load_verified_manifest(args.manifest)
        stats = analyze_manifest(args.manifest)
        diff = compare_manifests(args.baseline, args.manifest) if args.baseline is not None else None
        history_stats = analyze_history_file(args.history) if args.history is not None else None
        if args.html is None and args.md is None:
            print(render_markdown_report(stats, diff=diff, history=history_stats, title=args.title))
            return 0
        if args.html is not None:
            args.html.parent.mkdir(parents=True, exist_ok=True)
            args.html.write_text(
                render_html_report(
                    stats,
                    records,
                    diff=diff,
                    history=history_stats,
                    manifest_sha256=sha,
                    title=args.title,
                ),
                encoding="utf-8",
            )
            print(f"HTML_REPORT: {args.html}")
        if args.md is not None:
            args.md.parent.mkdir(parents=True, exist_ok=True)
            args.md.write_text(
                render_markdown_report(stats, diff=diff, history=history_stats, title=args.title),
                encoding="utf-8",
            )
            print(f"MD_REPORT: {args.md}")
        return 0

    if args.command == "generate-data":
        return _cmd_generate_data(args)

    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
