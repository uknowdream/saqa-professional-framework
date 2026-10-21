import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.audit_branch_protection import audit

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "security/branch-protection-policy.json").read_text(encoding="utf-8"))


def protection(**overrides):
    contexts = list(POLICY["required_check_contexts"])
    result = {
        "required_status_checks": {
            "strict": True,
            "contexts": contexts,
            "checks": [{"context": name, "app_id": POLICY["required_check_app_id"]} for name in contexts],
        },
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "enforce_admins": {"enabled": True},
    }
    result.update(overrides)
    return result


def test_complete_main_branch_protection_passes():
    result = audit(protection(), POLICY)
    assert result["status"] == "PASS"
    assert result["ready"] is True
    assert result["missing_check_contexts"] == []
    assert result["unbound_check_contexts"] == []


def test_missing_protection_fails_closed():
    result = audit({}, POLICY)
    assert result["status"] == "FAIL"
    assert any("required_status_checks is missing" in value for value in result["failures"])


def test_missing_mandatory_context_fails():
    value = protection()
    required = value["required_status_checks"]
    missing = POLICY["required_check_contexts"][0]
    required["contexts"].remove(missing)
    required["checks"] = [check for check in required["checks"] if check["context"] != missing]
    result = audit(value, POLICY)
    assert result["status"] == "FAIL"
    assert missing in result["missing_check_contexts"]


def test_non_strict_checks_fail():
    value = protection()
    value["required_status_checks"]["strict"] = False
    assert audit(value, POLICY)["status"] == "FAIL"


def test_required_check_from_unexpected_app_fails():
    value = protection()
    value["required_status_checks"]["checks"][0]["app_id"] = 999
    result = audit(value, POLICY)
    assert result["status"] == "FAIL"
    assert POLICY["required_check_contexts"][0] in result["unbound_check_contexts"]


@pytest.mark.parametrize("field", ["allow_force_pushes", "allow_deletions"])
def test_force_pushes_and_deletions_must_be_disabled(field):
    value = protection()
    value[field] = {"enabled": True}
    result = audit(value, POLICY)
    assert result["status"] == "FAIL"
    assert any(field + ".enabled must be false" in failure for failure in result["failures"])


def test_missing_force_push_configuration_fails():
    value = protection()
    value.pop("allow_force_pushes")
    assert audit(value, POLICY)["status"] == "FAIL"


def test_legacy_unbound_contexts_fail_app_binding_policy():
    value = protection()
    value["required_status_checks"]["checks"] = []
    result = audit(value, POLICY)
    assert result["status"] == "FAIL"
    assert len(result["unbound_check_contexts"]) == len(POLICY["required_check_contexts"])


def test_admin_bypass_is_reported_as_warning_not_hidden():
    value = protection()
    value["enforce_admins"] = {"enabled": False}
    result = audit(value, POLICY)
    assert result["status"] == "PASS"
    assert any("administrators may be able to bypass" in warning for warning in result["warnings"])


@pytest.mark.parametrize("bad_policy", [None, [], {"schema": "wrong"}])
def test_invalid_policy_is_rejected(bad_policy):
    with pytest.raises(ValueError, match="unsupported branch-protection policy schema"):
        audit(protection(), bad_policy)


def test_duplicate_required_contexts_are_rejected():
    value = deepcopy(POLICY)
    value["required_check_contexts"].append(value["required_check_contexts"][0])
    with pytest.raises(ValueError, match="must be unique"):
        audit(protection(), value)


def test_non_object_protection_fails_closed():
    result = audit([], POLICY)
    assert result["status"] == "FAIL"
    assert result["ready"] is False
