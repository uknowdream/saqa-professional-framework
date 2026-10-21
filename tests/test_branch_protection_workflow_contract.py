import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "security/branch-protection-policy.json").read_text(encoding="utf-8"))

CONTEXT_WORKFLOW = {
    "Dependency, SBOM, and secret hygiene": ".github/workflows/saqa-ci.yml",
    "Isolated database quality gate": ".github/workflows/saqa-ci.yml",
    "Target authorization policy": ".github/workflows/saqa-ci.yml",
    "Docker authorized target smoke": ".github/workflows/saqa-ci.yml",
    "Juice Shop API quality gate": ".github/workflows/saqa-ci.yml",
    "OpenAPI contract gate": ".github/workflows/saqa-contract.yml",
    "Contract gate against deterministic mock": ".github/workflows/saqa-contract-mock.yml",
    "Canonical evidence aggregation": ".github/workflows/saqa-ci.yml",
    "Accessibility canonical evidence aggregation": ".github/workflows/saqa-accessibility.yml",
    "Mobile canonical evidence aggregation": ".github/workflows/saqa-mobile.yml",
    "k6 local performance gate": ".github/workflows/saqa-k6.yml",
    "Validate framework structure and safety": ".github/workflows/framework-integrity.yml",
    "Advanced QE regression": ".github/workflows/saqa-advanced-qe.yml",
    "Scan pinned reference image": ".github/workflows/saqa-container-security.yml",
}


def test_policy_context_names_track_current_workflow_job_names():
    expected = set(POLICY["required_check_contexts"])
    assert expected == set(CONTEXT_WORKFLOW) | {
        "Python quality (3.11)",
        "Python quality (3.12)",
        "Python quality (3.13)",
    }
    for context, relative_path in CONTEXT_WORKFLOW.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert f"name: {context}" in source, f"required context drifted: {context} in {relative_path}"


def test_python_matrix_contexts_are_present_in_ci_workflow():
    source = (ROOT / ".github/workflows/saqa-ci.yml").read_text(encoding="utf-8")
    assert "name: Python quality" in source
    for version in ("3.11", "3.12", "3.13"):
        assert f"'{version}'" in source


def test_branch_protection_audit_never_runs_with_pull_request_secrets():
    source = (ROOT / ".github/workflows/saqa-branch-protection-audit.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert "schedule:" in source
    assert "\n  pull_request:" not in source
    assert "SAQA_REPO_ADMIN_AUDIT_TOKEN" in source
    assert "if: always()" in source
    assert "UNVERIFIED" in source
    assert "gh api \"/repos/${GITHUB_REPOSITORY}/branches/main/protection\"" in source


def test_audit_policy_does_not_claim_to_configure_protection():
    script = (ROOT / "scripts/audit_branch_protection.py").read_text(encoding="utf-8")
    docs = (ROOT / "docs/BRANCH_PROTECTION_AUDIT.md").read_text(encoding="utf-8")
    assert "does not change branch protection" in script
    assert "does not edit branch settings" in docs
