"""SAQA Professional QA Automation Framework."""
from __future__ import annotations

__version__ = "2.6.0"

from .analytics import analyze_history_file, analyze_manifest, analyze_records, compare_manifests, compute_latency_stats
from .benchmark import run_multi_target_benchmark
from .contracts import Evidence, ResultStatus, is_certification_safe, validate_evidence
from .evidence import compute_hmac_sha256, verify_manifest, write_manifest
from .http_pool import create_pooled_requester
from .i18n import (
    SUPPORTED_LANGUAGES,
    get_issue_summaries,
    normalize_lang,
    tr,
    translate_case_name,
    translate_finding_or_reason,
)
from .load_test import run_load_test
from .mobile_audit import MobileAuditResult, audit_mobile_package
from .notifications import dispatch_notifications, format_alert_message
from .openapi_audit import audit_openapi_spec, generate_suite_from_openapi, load_openapi_spec
from .pdf_report import render_pdf_report
from .reporting import render_html_report, render_junit_xml, render_markdown_report, render_sarif_report
from .runner import SuiteExecutionResult, create_starter_suite, load_suite_file, run_suite
from .spa_audit import (
    build_responsive_audit_record,
    build_spa_audit_record,
    inspect_responsive_viewports,
    inspect_spa_runtime,
    load_journey_file,
    run_browser_journey,
)
from .test_design import (
    DecisionRule,
    DesignedCase,
    SyntheticDataFactory,
    boundary_value_numeric,
    boundary_value_string,
    equivalence_partitions,
    error_guessing_payloads,
    evaluate_decision_table,
    generate_decision_table_cases,
    pairwise_matrix,
    state_transition_paths,
    verify_pairwise_coverage,
)
from .visual_diff import VisualDiffResult, compare_png_images, decode_png_rgb, parse_mask_spec
from .visual_evidence import (
    capture_viewport_matrix,
    capture_web_screenshot,
    export_csv_matrix,
    render_analytics_svg,
    render_scorecard_png,
)
from .web_audit import DeepAuditResult, run_deep_web_audit

__all__ = [
    "DecisionRule",
    "DeepAuditResult",
    "DesignedCase",
    "Evidence",
    "MobileAuditResult",
    "ResultStatus",
    "SUPPORTED_LANGUAGES",
    "SuiteExecutionResult",
    "SyntheticDataFactory",
    "VisualDiffResult",
    "__version__",
    "analyze_history_file",
    "analyze_manifest",
    "analyze_records",
    "audit_mobile_package",
    "audit_openapi_spec",
    "boundary_value_numeric",
    "boundary_value_string",
    "build_responsive_audit_record",
    "build_spa_audit_record",
    "capture_viewport_matrix",
    "capture_web_screenshot",
    "compare_manifests",
    "compare_png_images",
    "compute_hmac_sha256",
    "compute_latency_stats",
    "create_pooled_requester",
    "create_starter_suite",
    "decode_png_rgb",
    "dispatch_notifications",
    "equivalence_partitions",
    "error_guessing_payloads",
    "evaluate_decision_table",
    "export_csv_matrix",
    "format_alert_message",
    "generate_decision_table_cases",
    "generate_suite_from_openapi",
    "get_issue_summaries",
    "inspect_responsive_viewports",
    "inspect_spa_runtime",
    "is_certification_safe",
    "load_journey_file",
    "load_openapi_spec",
    "load_suite_file",
    "normalize_lang",
    "pairwise_matrix",
    "parse_mask_spec",
    "render_analytics_svg",
    "render_html_report",
    "render_junit_xml",
    "render_markdown_report",
    "render_pdf_report",
    "render_sarif_report",
    "render_scorecard_png",
    "run_browser_journey",
    "run_deep_web_audit",
    "run_load_test",
    "run_multi_target_benchmark",
    "run_suite",
    "state_transition_paths",
    "sync_manifest_to_jira",
    "sync_records_to_jira",
    "tr",
    "translate_case_name",
    "translate_finding_or_reason",
    "validate_evidence",
    "verify_manifest",
    "verify_pairwise_coverage",
    "write_manifest",
]


def __getattr__(name: str):
    """Lazily expose httpx-dependent Jira sync helpers so stdlib-only imports never require httpx."""
    if name in {"sync_manifest_to_jira", "sync_records_to_jira"}:
        from . import jira_sync

        return getattr(jira_sync, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
