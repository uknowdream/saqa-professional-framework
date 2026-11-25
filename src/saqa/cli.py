"""Unified command-line interface for the SAQA Professional Framework."""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .analytics import (
    analyze_history_file,
    analyze_manifest,
    compare_manifests,
    load_verified_manifest,
)
from .benchmark import run_multi_target_benchmark
from .evidence import verify_manifest
from .history import append_history
from .i18n import normalize_lang
from .load_test import run_load_test
from .mobile_audit import audit_mobile_package
from .notifications import dispatch_notifications
from .openapi_audit import audit_openapi_spec, generate_suite_from_openapi, load_openapi_spec
from .pdf_report import render_pdf_report
from .reporting import render_html_report, render_junit_xml, render_markdown_report, render_sarif_report
from .runner import create_starter_suite, load_suite_file, run_suite
from .spa_audit import load_journey_file, run_browser_journey
from .target_registry import DEFAULT_TARGETS
from .test_design import (
    SyntheticDataFactory,
    boundary_value_numeric,
    boundary_value_string,
    error_guessing_payloads,
    pairwise_matrix,
    verify_pairwise_coverage,
)
from .visual_diff import compare_png_images, parse_mask_spec
from .visual_evidence import capture_viewport_matrix, capture_web_screenshot
from .web_audit import run_deep_web_audit


def _check_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _parse_header_kv(items: Sequence[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in items:
        if ":" not in raw:
            raise ValueError(f"Header must use 'Key: Value' format, got {raw!r}")
        k, v = raw.split(":", 1)
        headers[k.strip()] = v.strip()
    return headers


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
    run_parser.add_argument("--pdf", type=Path, default=None, help="Optional path to write Executive PDF UAT report.")
    run_parser.add_argument("--junit", type=Path, default=None, help="Optional path to write JUnit XML report.")
    run_parser.add_argument("--sarif", type=Path, default=None, help="Optional path to write SARIF v2.1.0 report.")
    run_parser.add_argument("--baseline", type=Path, default=None, help="Optional baseline manifest for regression diff.")
    run_parser.add_argument("--history", type=Path, default=None, help="Optional hash-chained history JSONL file.")
    run_parser.add_argument("--commit-sha", default=None, help="Commit SHA recorded when appending to --history.")
    run_parser.add_argument("--lang", default=None, help="Client language for Jira & reports: 'en' (English) or 'id' (Bahasa Indonesia).")
    run_parser.add_argument(
        "--sync-jira",
        action="store_true",
        help="Automatically synchronize suite evidence, Timeline Epics, Rich ADF tables, photos, and reports to Jira.",
    )
    run_parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Capture live Desktop, Tablet & Mobile PNG screenshots of the target URL and attach them to Jira.",
    )
    run_parser.add_argument(
        "--attach",
        action="append",
        type=Path,
        default=[],
        help="Additional document/photo path(s) to upload to Jira (repeatable).",
    )
    run_parser.add_argument("--workers", type=int, default=None, help="Concurrent worker count for independent suite cases.")
    run_parser.add_argument("--sprint-start", default=None, help="Custom Jira Timeline sprint start date (YYYY-MM-DD).")
    run_parser.add_argument("--sprint-end", default=None, help="Custom Jira Timeline sprint due date (YYYY-MM-DD).")
    run_parser.add_argument("--webhook", action="append", default=[], help="Webhook URL(s) for Slack/Discord/generic alerts.")
    run_parser.add_argument("--notify-on-fail", action="store_true", help="Send webhook notifications only when status != PASS.")
    run_parser.add_argument("--json", action="store_true", dest="as_json", help="Print full analytics JSON to stdout.")

    sync_jira_parser = subparsers.add_parser(
        "sync-jira",
        help="Synchronize a verified SAQA evidence manifest, visual PNGs, and reports directly into Jira Cloud (EN/ID).",
    )
    sync_jira_parser.add_argument("manifest", type=Path, help="Path to verified evidence manifest JSON.")
    sync_jira_parser.add_argument("--suite-name", default=None, help="Optional suite name override.")
    sync_jira_parser.add_argument("--lang", default=None, help="Jira & report language: 'en' (English) or 'id' (Bahasa Indonesia).")
    sync_jira_parser.add_argument("--sprint-start", default=None, help="Custom Jira Timeline sprint start date (YYYY-MM-DD).")
    sync_jira_parser.add_argument("--sprint-end", default=None, help="Custom Jira Timeline sprint due date (YYYY-MM-DD).")
    sync_jira_parser.add_argument("--no-waivers", action="store_true", help="Ignore two-way Jira governance waiver labels.")
    sync_jira_parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Capture live responsive PNG screenshots of the target URL and attach them to Jira.",
    )
    sync_jira_parser.add_argument(
        "--attach",
        action="append",
        type=Path,
        default=[],
        help="Additional document/photo path(s) to upload to Jira (repeatable).",
    )
    sync_jira_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    shot_parser = subparsers.add_parser(
        "capture-screenshot",
        help="Capture a deterministic animation-frozen PNG screenshot of an authorized HTTP(S) website.",
    )
    shot_parser.add_argument("url", help="Target HTTP(S) URL.")
    shot_parser.add_argument("output", type=Path, help="Destination PNG file path.")
    shot_parser.add_argument("--width", type=int, default=1440, help="Viewport width in pixels.")
    shot_parser.add_argument("--height", type=int, default=900, help="Viewport height in pixels.")
    shot_parser.add_argument("--no-freeze-animations", action="store_true", help="Do not freeze CSS animations/transitions.")

    deep_parser = subparsers.add_parser(
        "deep-audit",
        help="Run a multi-pillar automated deep website/app QA audit (TLS, OWASP, WCAG, SEO, Links, Hygiene, Perf, SPA CWV, Modern Security, Responsive, Crawl).",
    )
    deep_parser.add_argument("url", help="Authorized target HTTP(S) URL to audit.")
    deep_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/deep-audit"),
        help="Directory for manifest, HTML/MD/CSV/JUnit/SARIF reports, PNG scorecard, SVG chart, and screenshots.",
    )
    deep_parser.add_argument("--max-links", type=int, default=18, help="Maximum unique internal links/assets to verify.")
    deep_parser.add_argument("--samples", type=int, default=3, help="Number of latency samples for performance profile.")
    deep_parser.add_argument("--spa", action="store_true", help="Enable Pillar 8 live headless browser SPA rendered DOM & Core Web Vitals audit.")
    deep_parser.add_argument("--modern-security", action="store_true", help="Enable Pillar 9 CORS, SRI, RFC 9116 security.txt, Mobile App-Links & GraphQL audit.")
    deep_parser.add_argument("--responsive", action="store_true", help="Enable Desktop/Tablet/Mobile multi-viewport layout overflow & tap-target audit.")
    deep_parser.add_argument("--crawl-pages", type=int, default=1, help="Crawl and audit up to N internal pages via Sitemap + BFS (>1 enables multi-page crawler).")
    deep_parser.add_argument("--header", action="append", default=[], help="Custom HTTP header 'Key: Value' (repeatable, e.g. for staging auth).")
    deep_parser.add_argument("--cookies", default=None, help="Optional Cookie header string for authenticated web sessions.")
    deep_parser.add_argument("--lang", default=None, help="Client language for Jira & reports: 'en' (English) or 'id' (Bahasa Indonesia).")
    deep_parser.add_argument("--screenshot", action="store_true", help="Capture animation-frozen Desktop, Tablet & Mobile screenshots.")
    deep_parser.add_argument("--sync-jira", action="store_true", help="Automatically sync deep audit results, photos, and reports to Jira.")
    deep_parser.add_argument("--sprint-start", default=None, help="Custom Jira Timeline sprint start date (YYYY-MM-DD).")
    deep_parser.add_argument("--sprint-end", default=None, help="Custom Jira Timeline sprint due date (YYYY-MM-DD).")
    deep_parser.add_argument("--webhook", action="append", default=[], help="Webhook URL(s) for Slack/Discord/generic alerts.")
    deep_parser.add_argument("--notify-on-fail", action="store_true", help="Send webhook notifications only when status != PASS.")
    deep_parser.add_argument("--attach", action="append", type=Path, default=[], help="Extra files to attach to Jira.")
    deep_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    journey_parser = subparsers.add_parser(
        "run-journey",
        help="Execute declarative interactive browser UI user journeys (click, fill, assert_text, screenshot, auth storage_state).",
    )
    journey_parser.add_argument("journey", type=Path, help="Path to declarative browser journey JSON file.")
    journey_parser.add_argument("--output-dir", type=Path, default=Path("artifacts/journey"), help="Directory for journey evidence and screenshots.")
    journey_parser.add_argument("--lang", default=None, help="Jira & report language: 'en' (English) or 'id' (Bahasa Indonesia).")
    journey_parser.add_argument("--sync-jira", action="store_true", help="Synchronize journey evidence & step screenshots to Jira.")
    journey_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    mobile_parser = subparsers.add_parser(
        "audit-mobile",
        help="Audit an Android (.apk/.aab) or iOS (.ipa/.app.zip) package for signing, manifest security, permissions, secrets, ABI & Maestro flows.",
    )
    mobile_parser.add_argument("app", type=Path, help="Path to client mobile package (.apk, .aab, .ipa, or .app.zip).")
    mobile_parser.add_argument("--output-dir", type=Path, default=Path("artifacts/mobile-audit"), help="Output directory for mobile audit reports.")
    mobile_parser.add_argument("--maestro-flow", type=Path, default=None, help="Optional Maestro YAML flow to execute on emulator/device.")
    mobile_parser.add_argument("--lang", default=None, help="Client language for Jira & reports: 'en' or 'id'.")
    mobile_parser.add_argument("--sprint-start", default=None, help="Custom Jira Timeline sprint start date (YYYY-MM-DD).")
    mobile_parser.add_argument("--sprint-end", default=None, help="Custom Jira Timeline sprint due date (YYYY-MM-DD).")
    mobile_parser.add_argument("--sync-jira", action="store_true", help="Automatically sync mobile audit reports (PDF/HTML/PNG/SARIF) to Jira.")
    mobile_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    load_parser = subparsers.add_parser(
        "load-test",
        help="Run a bounded read-only concurrent HTTP load & SLA stress gate (RPS, error rate, P50/P95/P99).",
    )
    load_parser.add_argument("url", help="Target HTTP(S) URL (loopback by default; pass --allow-remote for authorized targets).")
    load_parser.add_argument("--requests", type=int, default=30, help="Total concurrent GET requests (1-1000).")
    load_parser.add_argument("--concurrency", type=int, default=6, help="Worker concurrency (1-50).")
    load_parser.add_argument("--max-p95-ms", type=float, default=2500.0, help="Maximum allowed P95 latency SLA in milliseconds.")
    load_parser.add_argument("--max-error-pct", type=float, default=1.0, help="Maximum allowed error rate percentage.")
    load_parser.add_argument("--allow-remote", action="store_true", help="Allow authorized non-loopback target URL.")
    load_parser.add_argument("--output-dir", type=Path, default=Path("artifacts/load-test"), help="Output directory for load reports.")
    load_parser.add_argument("--lang", default=None, help="Client language for Jira & reports: 'en' or 'id'.")
    load_parser.add_argument("--sync-jira", action="store_true", help="Automatically sync load test SLA evidence & PDF report to Jira.")
    load_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    vdiff_parser = subparsers.add_parser(
        "visual-diff",
        help="Pixel-by-pixel PNG visual regression comparator with region masking, anti-aliasing tolerance, and diff heatmap.",
    )
    vdiff_parser.add_argument("baseline", type=Path, help="Baseline PNG screenshot.")
    vdiff_parser.add_argument("current", type=Path, help="Current PNG screenshot.")
    vdiff_parser.add_argument("--output", type=Path, default=None, help="Optional path to save visual diff heatmap PNG.")
    vdiff_parser.add_argument("--tolerance", type=int, default=10, help="Per-channel RGB tolerance (0-255).")
    vdiff_parser.add_argument("--threshold", type=float, default=0.5, help="Maximum allowed mismatch percentage (0-100).")
    vdiff_parser.add_argument("--mask", action="append", default=[], help="Ignore bounding box 'x,y,w,h' (repeatable).")
    vdiff_parser.add_argument("--ignore-antialiasing", action="store_true", help="Ignore 1px high-contrast font/vector anti-aliased edge deltas.")
    vdiff_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    bench_parser = subparsers.add_parser(
        "benchmark",
        help="Audit and rank multiple websites/environments side-by-side (HTML, Markdown, CSV, JSON).",
    )
    bench_parser.add_argument("urls", nargs="+", help="Target HTTP(S) URLs to benchmark.")
    bench_parser.add_argument("--output-dir", type=Path, default=Path("artifacts/benchmark"), help="Output directory for benchmark matrix.")
    bench_parser.add_argument("--spa", action="store_true", help="Include Pillar 8 SPA browser runtime audit.")
    bench_parser.add_argument("--workers", type=int, default=4, help="Parallel target audit workers.")
    bench_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

    openapi_parser = subparsers.add_parser(
        "audit-openapi",
        help="Auto-generate and/or execute read-only contract tests from an OpenAPI 3.x / Swagger 2.0 JSON spec.",
    )
    openapi_parser.add_argument("spec", type=Path, help="Path to OpenAPI/Swagger JSON file.")
    openapi_parser.add_argument("--base-url", default="http://127.0.0.1:3000", help="Target API base URL.")
    openapi_parser.add_argument("--allow-remote", action="store_true", help="Allow authorized non-loopback target URL.")
    openapi_parser.add_argument("--export-suite", type=Path, default=None, help="Export generated SAQA suite JSON without executing.")
    openapi_parser.add_argument("--output-dir", type=Path, default=Path("artifacts/openapi-audit"), help="Directory for execution evidence.")
    openapi_parser.add_argument("--lang", default=None, help="Jira & report language: 'en' or 'id'.")
    openapi_parser.add_argument("--sync-jira", action="store_true", help="Synchronize audit results directly to Jira.")
    openapi_parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON output.")

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
        help="Generate interactive HTML, Markdown, JUnit XML, and/or SARIF v2.1.0 QA reports from a verified manifest.",
    )
    report_parser.add_argument("manifest", type=Path, help="Path to verified evidence manifest JSON.")
    report_parser.add_argument("--html", type=Path, default=None, help="Path to write interactive HTML report.")
    report_parser.add_argument("--md", type=Path, default=None, help="Path to write Markdown report.")
    report_parser.add_argument("--pdf", type=Path, default=None, help="Path to write Executive PDF UAT report.")
    report_parser.add_argument("--junit", type=Path, default=None, help="Path to write JUnit XML report.")
    report_parser.add_argument("--sarif", type=Path, default=None, help="Path to write SARIF v2.1.0 JSON report.")
    report_parser.add_argument("--baseline", type=Path, default=None, help="Optional baseline manifest for comparison.")
    report_parser.add_argument("--history", type=Path, default=None, help="Optional history JSONL for flakiness panel.")
    report_parser.add_argument("--lang", default=None, help="Report language: 'en' (English) or 'id' (Bahasa Indonesia).")
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
        "ruff": _check_module("ruff"),
        "mypy": _check_module("mypy"),
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
        lang_code = normalize_lang(args.lang)
        suite = load_suite_file(args.suite)
        result = run_suite(suite, output_dir=args.output_dir, workers=args.workers)

        diff = None
        if args.baseline is not None and result.manifest_path is not None:
            diff = compare_manifests(args.baseline, result.manifest_path)

        history_stats = None
        if args.history is not None:
            if args.commit_sha:
                append_history(list(result.records), args.history, commit_sha=args.commit_sha)
            if args.history.exists():
                history_stats = analyze_history_file(args.history)

        r_title = f"{'Laporan Kualitas SAQA' if lang_code == 'id' else 'SAQA Report'} — {result.suite_name}"
        if args.html is not None:
            args.html.parent.mkdir(parents=True, exist_ok=True)
            args.html.write_text(
                render_html_report(
                    result.analytics,
                    result.records,
                    diff=diff,
                    history=history_stats,
                    manifest_sha256=result.manifest_sha256,
                    title=r_title,
                    lang=lang_code,
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
                    title=r_title,
                    lang=lang_code,
                ),
                encoding="utf-8",
            )
        if args.pdf is not None:
            render_pdf_report(
                result.analytics,
                result.records,
                args.pdf,
                manifest_sha256=result.manifest_sha256,
                title=r_title,
                lang=lang_code,
            )
        if args.junit is not None:
            args.junit.parent.mkdir(parents=True, exist_ok=True)
            args.junit.write_text(
                render_junit_xml(result.analytics, result.records, suite_name=result.suite_name),
                encoding="utf-8",
            )
        if args.sarif is not None:
            args.sarif.parent.mkdir(parents=True, exist_ok=True)
            args.sarif.write_text(
                json.dumps(render_sarif_report(result.records, suite_name=result.suite_name), indent=2),
                encoding="utf-8",
            )

        jira_summary = None
        if args.sync_jira:
            from .jira_sync import sync_records_to_jira

            attach_list: list[Path] = []
            for candidate in (result.manifest_path, result.summary_path, args.html, args.md, args.junit, args.sarif, *args.attach):
                if candidate is not None and candidate.is_file():
                    attach_list.append(candidate)
            jira_summary = sync_records_to_jira(
                result.records,
                suite_name=result.suite_name,
                manifest_sha256=result.manifest_sha256,
                attachments=attach_list,
                artifact_dir=args.output_dir,
                auto_generate_visuals=True,
                capture_screenshots=bool(args.screenshot),
                sprint_start=args.sprint_start,
                sprint_end=args.sprint_end,
                lang=lang_code,
            )

        dispatch_notifications(
            result.analytics,
            suite_name=result.suite_name,
            webhook_urls=args.webhook,
            only_on_failure=bool(args.notify_on_fail),
        )

        if args.as_json:
            print(json.dumps({"analytics": result.analytics, "diff": diff, "jira": jira_summary}, indent=2))
        else:
            a = result.analytics
            jira_msg = (
                f" | Jira {jira_summary['project_key']} [{jira_summary['language'].upper()}] ("
                f"{len(jira_summary.get('synced_epics', []))} epics, "
                f"{len(jira_summary['synced_issues'])} issues, "
                f"{len(jira_summary.get('uploaded_attachments', []))} attachments)"
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
        from .jira_sync import sync_manifest_to_jira

        jira_summary = sync_manifest_to_jira(
            args.manifest,
            suite_name=args.suite_name,
            attachments=args.attach or None,
            auto_generate_visuals=True,
            capture_screenshots=bool(args.screenshot),
            sprint_start=args.sprint_start,
            sprint_end=args.sprint_end,
            lang=args.lang,
            respect_waivers=not bool(args.no_waivers),
        )
        if args.as_json:
            print(json.dumps(jira_summary, indent=2))
        else:
            print(
                f"JIRA_SYNC_PASS: project={jira_summary['project_key']} "
                f"lang={jira_summary['language'].upper()} "
                f"suite={jira_summary['suite_name']} status={jira_summary['overall_status']} "
                f"epics_synced={len(jira_summary.get('synced_epics', []))} "
                f"issues_synced={len(jira_summary['synced_issues'])} "
                f"attachments_uploaded={len(jira_summary.get('uploaded_attachments', []))} "
                f"waived={len(jira_summary.get('waived_domains', []))} "
                f"bugs_resolved={len(jira_summary.get('resolved_bugs', []))}"
            )
            for ep in jira_summary.get("synced_epics", []):
                print(f"  * EPIC {ep['epic_key']} ({ep['phase_id']}): {ep['status']} -> {ep['transitioned_to'] or 'unchanged'} | {ep['epic_url']}")
            for item in jira_summary["synced_issues"]:
                print(
                    f"  - {item['issue_key']} ({item['domain']} — {item.get('summary', '')}): {item['status']} "
                    f"[{item['label']}] epic={item.get('parent_epic')} "
                    f"timeline={item.get('start_date')}..{item.get('due_date')} "
                    f"-> {item['transitioned_to'] or 'unchanged'} | {item['issue_url']}"
                )
            if jira_summary.get("resolved_bugs"):
                print(f"  * AUTO_RESOLVED_BUGS: {', '.join(jira_summary['resolved_bugs'])}")
        return 0

    if args.command == "capture-screenshot":
        saved = capture_web_screenshot(
            args.url,
            args.output,
            width=args.width,
            height=args.height,
            freeze_animations=not bool(args.no_freeze_animations),
        )
        if saved is None:
            print("SCREENSHOT_UNAVAILABLE: neither Playwright nor Chromium/Edge binary was found", file=sys.stderr)
            return 1
        print(f"SCREENSHOT_SAVED: {saved}")
        return 0

    if args.command == "deep-audit":
        lang_code = normalize_lang(args.lang)
        extra_hdrs = _parse_header_kv(args.header) if args.header else None
        deep_res = run_deep_web_audit(
            args.url,
            output_dir=args.output_dir,
            max_links=args.max_links,
            perf_samples=args.samples,
            include_spa_audit=bool(args.spa),
            include_modern_security=bool(args.modern_security),
            include_responsive_audit=bool(args.responsive),
            crawl_max_pages=int(args.crawl_pages),
            extra_headers=extra_hdrs,
            cookies=args.cookies,
            lang=lang_code,
        )
        captured: list[Path] = []
        if args.screenshot:
            captured = capture_viewport_matrix(args.url, args.output_dir, freeze_animations=True)

        jira_summary = None
        if args.sync_jira and deep_res.manifest_path is not None:
            from .jira_sync import sync_manifest_to_jira

            jira_summary = sync_manifest_to_jira(
                deep_res.manifest_path,
                attachments=[*captured, *args.attach] or None,
                auto_generate_visuals=True,
                capture_screenshots=False,
                sprint_start=args.sprint_start,
                sprint_end=args.sprint_end,
                lang=lang_code,
            )

        dispatch_notifications(
            deep_res.analytics,
            suite_name=f"deep-audit:{args.url}",
            target=args.url,
            webhook_urls=args.webhook,
            only_on_failure=bool(args.notify_on_fail),
        )

        if args.as_json:
            print(json.dumps({"analytics": deep_res.analytics, "findings": list(deep_res.findings), "jira": jira_summary}, indent=2))
        else:
            a = deep_res.analytics
            jira_msg = (
                f" | Jira {jira_summary['project_key']} [{jira_summary['language'].upper()}] "
                f"({len(jira_summary['synced_issues'])} issues, {len(jira_summary.get('uploaded_attachments', []))} attachments)"
                if jira_summary
                else ""
            )
            print(
                f"DEEP_AUDIT {deep_res.target_url}: {a['overall_status']} | "
                f"Health {a['health_score']}/100 ({a['health_grade']}) | "
                f"Pass {a['pass_rate_pct']}% ({a['status_counts']['PASS']}/{a['total_records']}) | "
                f"Findings {len(deep_res.findings)} | Lang {lang_code.upper()} | Out {args.output_dir}{jira_msg}"
            )
        return 0 if deep_res.passed else 1

    if args.command == "run-journey":
        lang_code = normalize_lang(args.lang)
        spec = load_journey_file(args.journey)
        j_records, j_analytics = run_browser_journey(spec, output_dir=args.output_dir)
        jira_summary = None
        manifest_file = args.output_dir / "evidence-manifest.json"
        if args.sync_jira and manifest_file.is_file():
            from .jira_sync import sync_manifest_to_jira

            shots = sorted(args.output_dir.glob("*.png"))
            jira_summary = sync_manifest_to_jira(manifest_file, attachments=shots, lang=lang_code)
        if args.as_json:
            print(json.dumps({"analytics": j_analytics, "jira": jira_summary}, indent=2))
        else:
            print(
                f"JOURNEY {spec.get('name', 'journey')}: {j_analytics['overall_status']} | "
                f"Health {j_analytics['health_score']}/100 ({j_analytics['health_grade']}) | Out {args.output_dir}"
            )
        return 0 if j_analytics["overall_status"] == "PASS" else 1

    if args.command == "audit-mobile":
        lang_code = normalize_lang(args.lang)
        mob_res = audit_mobile_package(
            args.app,
            output_dir=args.output_dir,
            maestro_flow=args.maestro_flow,
            lang=lang_code,
        )
        jira_summary = None
        if args.sync_jira and mob_res.manifest_path is not None:
            from .jira_sync import sync_manifest_to_jira

            jira_summary = sync_manifest_to_jira(
                mob_res.manifest_path,
                sprint_start=args.sprint_start,
                sprint_end=args.sprint_end,
                lang=lang_code,
            )
        if args.as_json:
            print(
                json.dumps(
                    {
                        "platform": mob_res.platform,
                        "app_sha256": mob_res.app_sha256,
                        "metadata": mob_res.metadata,
                        "analytics": mob_res.analytics,
                        "findings": list(mob_res.findings),
                        "jira": jira_summary,
                    },
                    indent=2,
                )
            )
        else:
            a = mob_res.analytics
            jira_msg = (
                f" | Jira {jira_summary['project_key']} [{jira_summary['language'].upper()}] "
                f"({len(jira_summary['synced_issues'])} issues, {len(jira_summary.get('uploaded_attachments', []))} attachments)"
                if jira_summary
                else ""
            )
            print(
                f"MOBILE_AUDIT {mob_res.platform.upper()} {args.app.name}: {a['overall_status']} | "
                f"Health {a['health_score']}/100 ({a['health_grade']}) | "
                f"Pass {a['pass_rate_pct']}% | Findings {len(mob_res.findings)} | "
                f"Lang {lang_code.upper()} | Out {args.output_dir}{jira_msg}"
            )
        return 0 if mob_res.passed else 1

    if args.command == "load-test":
        lang_code = normalize_lang(args.lang)
        load_res = run_load_test(
            args.url,
            total_requests=args.requests,
            concurrency=args.concurrency,
            max_p95_ms=args.max_p95_ms,
            max_error_rate_pct=args.max_error_pct,
            allow_remote=bool(args.allow_remote),
            output_dir=args.output_dir,
            lang=lang_code,
        )
        jira_summary = None
        if args.sync_jira and load_res.get("manifest_path"):
            from .jira_sync import sync_manifest_to_jira

            jira_summary = sync_manifest_to_jira(Path(load_res["manifest_path"]), lang=lang_code)
        if args.as_json:
            print(json.dumps({**load_res, "jira": jira_summary}, indent=2))
        else:
            status_lbl = "PASS" if load_res["passed"] else "FAIL"
            print(
                f"LOAD_TEST {load_res['target_url']}: {status_lbl} | "
                f"RPS {load_res['throughput_rps']} | P95 {load_res['latency']['p95_ms']}ms | "
                f"Errors {load_res['error_rate_pct']}% ({load_res['error_count']}/{load_res['total_requests']}) | "
                f"Out {args.output_dir}"
            )
        return 0 if load_res["passed"] else 1

    if args.command == "visual-diff":
        masks = [parse_mask_spec(m) for m in args.mask]
        vdiff = compare_png_images(
            args.baseline,
            args.current,
            diff_output_path=args.output,
            pixel_tolerance=args.tolerance,
            max_mismatch_pct=args.threshold,
            mask_regions=masks,
            ignore_antialiasing=bool(args.ignore_antialiasing),
        )
        if args.as_json:
            print(json.dumps(vdiff.to_dict(), indent=2))
        else:
            status_str = "PASS" if vdiff.passed else "FAIL"
            print(
                f"VISUAL_DIFF {status_str}: mismatch={vdiff.mismatch_pct}% "
                f"({vdiff.mismatch_pixels}/{vdiff.total_pixels} px, masked={vdiff.masked_pixels}, "
                f"antialiased={vdiff.antialiased_pixels}, threshold={vdiff.threshold_pct}%) "
                f"diff_image={vdiff.diff_image_path}"
            )
        return 0 if vdiff.passed else 1

    if args.command == "benchmark":
        bench = run_multi_target_benchmark(
            args.urls,
            output_dir=args.output_dir,
            include_spa_audit=bool(args.spa),
            workers=args.workers,
        )
        if args.as_json:
            print(json.dumps(bench, indent=2))
        else:
            print(f"BENCHMARK COMPLETE: {bench['target_count']} target(s) | Leader: {bench['leader']} | Out: {args.output_dir}")
            for item in bench["rankings"]:
                print(
                    f"  #{item['rank']} {item['target_url']} -> {item['overall_status']} "
                    f"Health {item['health_score']} ({item['health_grade']}) | P95 {item['p95_ms']}ms"
                )
        return 0

    if args.command == "audit-openapi":
        if args.export_suite is not None:
            spec = load_openapi_spec(args.spec)
            suite = generate_suite_from_openapi(spec, base_url=args.base_url, allow_remote=args.allow_remote)
            args.export_suite.parent.mkdir(parents=True, exist_ok=True)
            args.export_suite.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
            print(f"OPENAPI_SUITE_EXPORTED: {args.export_suite} ({len(suite['cases'])} GET endpoint(s))")
            return 0
        result = audit_openapi_spec(
            args.spec,
            base_url=args.base_url,
            allow_remote=args.allow_remote,
            output_dir=args.output_dir,
        )
        jira_summary = None
        if args.sync_jira and result.manifest_path is not None:
            from .jira_sync import sync_manifest_to_jira

            jira_summary = sync_manifest_to_jira(result.manifest_path, auto_generate_visuals=True, lang=args.lang)
        if args.as_json:
            print(json.dumps({"analytics": result.analytics, "jira": jira_summary}, indent=2))
        else:
            a = result.analytics
            print(
                f"OPENAPI_AUDIT {result.suite_name}: {a['overall_status']} | "
                f"Health {a['health_score']}/100 ({a['health_grade']}) | "
                f"Pass {a['pass_rate_pct']}% | Manifest {result.manifest_path}"
            )
        return 0 if result.passed else 1

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
        lang_code = normalize_lang(args.lang)
        records, sha = load_verified_manifest(args.manifest)
        stats = analyze_manifest(args.manifest)
        diff = compare_manifests(args.baseline, args.manifest) if args.baseline is not None else None
        history_stats = analyze_history_file(args.history) if args.history is not None else None
        if args.html is None and args.md is None and args.pdf is None and args.junit is None and args.sarif is None:
            print(render_markdown_report(stats, diff=diff, history=history_stats, title=args.title, lang=lang_code))
            return 0
        if args.pdf is not None:
            render_pdf_report(stats, records, args.pdf, manifest_sha256=sha, title=args.title, lang=lang_code)
            print(f"PDF_REPORT: {args.pdf}")
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
                    lang=lang_code,
                ),
                encoding="utf-8",
            )
            print(f"HTML_REPORT: {args.html}")
        if args.md is not None:
            args.md.parent.mkdir(parents=True, exist_ok=True)
            args.md.write_text(
                render_markdown_report(stats, diff=diff, history=history_stats, title=args.title, lang=lang_code),
                encoding="utf-8",
            )
            print(f"MD_REPORT: {args.md}")
        if args.junit is not None:
            args.junit.parent.mkdir(parents=True, exist_ok=True)
            args.junit.write_text(
                render_junit_xml(stats, records, suite_name=args.manifest.stem),
                encoding="utf-8",
            )
            print(f"JUNIT_REPORT: {args.junit}")
        if args.sarif is not None:
            args.sarif.parent.mkdir(parents=True, exist_ok=True)
            args.sarif.write_text(
                json.dumps(render_sarif_report(records, suite_name=args.manifest.stem), indent=2),
                encoding="utf-8",
            )
            print(f"SARIF_REPORT: {args.sarif}")
        return 0

    if args.command == "generate-data":
        return _cmd_generate_data(args)

    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
