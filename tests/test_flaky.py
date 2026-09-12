import pytest

from saqa.flaky import analyze_history


def test_single_observation_is_insufficient() -> None:
    result = analyze_history(["PASS"])
    assert result.status == "INSUFFICIENT_DATA"
    assert result.executions == 1


def test_pass_fail_history_is_flaky() -> None:
    result = analyze_history(["PASS", "PASS", "FAIL", "PASS"])
    assert result.status == "FLAKY"
    assert result.pass_count == 3
    assert result.fail_count == 1
    assert result.transition_count == 2
    assert result.is_flaky


def test_all_pass_is_stable() -> None:
    result = analyze_history(["PASS", "PASS", "PASS"])
    assert result.status == "STABLE_PASS"
    assert not result.is_flaky


def test_all_fail_is_stable_failure() -> None:
    result = analyze_history(["FAIL", "FAIL"])
    assert result.status == "STABLE_FAIL"
    assert result.fail_count == 2


def test_non_terminal_history_is_not_flaky() -> None:
    result = analyze_history(["SKIP", "BLOCKED"])
    assert result.status == "NON_TERMINAL"
    assert result.other_count == 2


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported execution status"):
        analyze_history(["PASS", "BROKEN"])
