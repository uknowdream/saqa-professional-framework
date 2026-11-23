"""SAQA Professional QA Automation Framework."""

__version__ = "2.2.0"

from .analytics import analyze_history_file, analyze_manifest, analyze_records, compare_manifests, compute_latency_stats
from .contracts import Evidence, ResultStatus, is_certification_safe, validate_evidence
from .jira_sync import sync_manifest_to_jira, sync_records_to_jira
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

__all__ = [
    "DecisionRule",
    "DesignedCase",
    "Evidence",
    "ResultStatus",
    "SuiteExecutionResult",
    "SyntheticDataFactory",
    "__version__",
    "analyze_history_file",
    "analyze_manifest",
    "analyze_records",
    "boundary_value_numeric",
    "boundary_value_string",
    "compare_manifests",
    "compute_latency_stats",
    "create_starter_suite",
    "equivalence_partitions",
    "error_guessing_payloads",
    "evaluate_decision_table",
    "generate_decision_table_cases",
    "is_certification_safe",
    "load_suite_file",
    "pairwise_matrix",
    "render_html_report",
    "render_markdown_report",
    "run_suite",
    "state_transition_paths",
    "sync_manifest_to_jira",
    "sync_records_to_jira",
    "validate_evidence",
    "verify_pairwise_coverage",
]
