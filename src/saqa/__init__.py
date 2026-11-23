"""SAQA Professional QA Automation Framework."""
from __future__ import annotations

__version__ = "2.3.0"

from .analytics import analyze_history_file, analyze_manifest, analyze_records, compare_manifests, compute_latency_stats
from .contracts import Evidence, ResultStatus, is_certification_safe, validate_evidence
from .openapi_audit import audit_openapi_spec, generate_suite_from_openapi, load_openapi_spec
from .reporting import render_html_report, render_markdown_report
from .runner import SuiteExecutionResult, create_starter_suite, load_suite_file, run_suite
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
from .visual_evidence import (
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
    "ResultStatus",
    "SuiteExecutionResult",
    "SyntheticDataFactory",
    "__version__",
    "analyze_history_file",
    "analyze_manifest",
    "analyze_records",
    "audit_openapi_spec",
    "boundary_value_numeric",
    "boundary_value_string",
    "capture_web_screenshot",
    "compare_manifests",
    "compute_latency_stats",
    "create_starter_suite",
    "equivalence_partitions",
    "error_guessing_payloads",
    "evaluate_decision_table",
    "export_csv_matrix",
    "generate_decision_table_cases",
    "generate_suite_from_openapi",
    "is_certification_safe",
    "load_openapi_spec",
    "load_suite_file",
    "pairwise_matrix",
    "render_analytics_svg",
    "render_html_report",
    "render_markdown_report",
    "render_scorecard_png",
    "run_deep_web_audit",
    "run_suite",
    "state_transition_paths",
    "sync_manifest_to_jira",
    "sync_records_to_jira",
    "validate_evidence",
    "verify_pairwise_coverage",
]


def __getattr__(name: str):
    """Lazily expose httpx-dependent Jira sync helpers so stdlib-only imports never require httpx."""
    if name in {"sync_manifest_to_jira", "sync_records_to_jira"}:
        from . import jira_sync

        return getattr(jira_sync, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
