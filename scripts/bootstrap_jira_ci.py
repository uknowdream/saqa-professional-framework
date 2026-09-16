#!/usr/bin/env python3
"""Create the initial SAQA QA work backlog in Jira, idempotently.

This is intentionally a controlled bootstrap: it creates Tasks only, uses a
stable label for deduplication, and never logs credentials.
"""
from __future__ import annotations

from saqa.jira import JiraClient, JiraConfig

WORK_ITEMS = [
    ("SAQA | Test Management Foundation", "Establish Jira as the QA control plane for SAQA test planning, execution traceability, evidence, and quality reporting.", ["saqa-bootstrap", "qa-management"]),
    ("SAQA | Web E2E Automation", "Track browser end-to-end automation coverage and regression evidence for authorized QA targets.", ["saqa-bootstrap", "web-e2e"]),
    ("SAQA | Cross-Browser Matrix", "Track Chromium, Firefox, and WebKit execution, compatibility defects, and regression evidence.", ["saqa-bootstrap", "cross-browser"]),
    ("SAQA | API Quality Gate", "Track API functional checks, status-code assertions, schema validation, response-time thresholds, and evidence.", ["saqa-bootstrap", "api-testing"]),
    ("SAQA | Security Regression Gate", "Track safe security regression checks, authorization policy, and prohibited-target safeguards.", ["saqa-bootstrap", "security"]),
    ("SAQA | Accessibility Gate", "Track accessibility checks, keyboard navigation, semantic assertions, and accessibility evidence.", ["saqa-bootstrap", "accessibility"]),
    ("SAQA | Performance Quality Gate", "Track bounded performance smoke checks, response-time regression, and performance evidence.", ["saqa-bootstrap", "performance"]),
    ("SAQA | Evidence & Allure Traceability", "Track immutable evidence, SHA-256 integrity, Allure reporting, and CI-to-test traceability.", ["saqa-bootstrap", "evidence"]),
    ("SAQA | Certification Readiness", "Track objective exit criteria for framework certification and prevent certification claims without sufficient evidence.", ["saqa-bootstrap", "certification"]),
]


def main() -> None:
    with JiraClient(JiraConfig.from_env()) as client:
        project = client.verify_access()
        existing = client.find_bootstrap_issues()
        created = 0
        skipped = 0
        print(f"Jira project: PASS ({project.key} / {project.name})")
        for summary, description, labels in WORK_ITEMS:
            if summary in existing:
                skipped += 1
                print(f"EXISTS {existing[summary].key} | {summary}")
                continue
            issue = client.create_task(summary, description, labels)
            created += 1
            print(f"CREATED {issue.key} | {summary} | {issue.url}")
        print(f"Jira bootstrap: PASS (created={created}, existing={skipped}, total={len(WORK_ITEMS)})")


if __name__ == "__main__":
    main()
