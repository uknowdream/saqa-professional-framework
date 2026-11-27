"""SAQA Professional QA Automation Framework."""
from __future__ import annotations

__version__ = "2.7.0"

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
from .methodology import (
    SUPPORTED_METHODOLOGIES,
    build_rtm_matrix,
    classify_defect_severity,
    compute_waterfall_timeline_window,
    evaluate_methodology_governance,
    export_rtm_csv,
    normalize_methodology,
    render_release_signoff_markdown,
)
from .mobile_audit import MobileAuditResult, audit_mobile_package, parse_android_axml_manifest
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
    inspect_spa_subpages,
    load_journey_file,
    run_browser_journey,
)
from .ssrf import (
    host_is_private_or_local,
    is_private_or_metadata_ip,
    safe_parse_xml,
    validate_safe_outbound_url,
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
    "SUPPORTED_METHODOLOGIES",
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
    "build_rtm_matrix",
    "build_spa_audit_record",
    "capture_viewport_matrix",
    "capture_web_screenshot",
    "classify_defect_severity",
    "compare_manifests",
    "compare_png_images",
    "compute_hmac_sha256",
    "compute_latency_stats",
    "compute_waterfall_timeline_window",
    "create_pooled_requester",
    "create_starter_suite",
    "decode_png_rgb",
    "dispatch_notifications",
    "equivalence_partitions",
    "error_guessing_payloads",
    "evaluate_decision_table",
    "evaluate_methodology_governance",
    "export_csv_matrix",
    "export_rtm_csv",
    "format_alert_message",
    "generate_decision_table_cases",
    "generate_suite_from_openapi",
    "get_issue_summaries",
    "host_is_private_or_local",
    "inspect_responsive_viewports",
    "inspect_spa_runtime",
    "inspect_spa_subpages",
    "is_certification_safe",
    "is_private_or_metadata_ip",
    "load_journey_file",
    "load_openapi_spec",
    "load_suite_file",
    "normalize_lang",
    "normalize_methodology",
    "pairwise_matrix",
    "parse_android_axml_manifest",
    "parse_mask_spec",
    "render_analytics_svg",
    "render_html_report",
    "render_junit_xml",
    "render_markdown_report",
    "render_pdf_report",
    "render_release_signoff_markdown",
    "render_sarif_report",
    "render_scorecard_png",
    "run_browser_journey",
    "run_deep_web_audit",
    "run_load_test",
    "run_multi_target_benchmark",
    "run_suite",
    "safe_parse_xml",
    "state_transition_paths",
    "sync_manifest_to_jira",
    "sync_records_to_jira",
    "tr",
    "translate_case_name",
    "translate_finding_or_reason",
    "validate_evidence",
    "validate_safe_outbound_url",
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
