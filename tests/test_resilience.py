import httpx
import pytest

from saqa.resilience import retry_read_only


def test_success_returns_value_and_attempt_number():
    value, attempts = retry_read_only(lambda: {"ok": True})
    assert value == {"ok": True}
    assert attempts == 1


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), ConnectionError("connection"), httpx.ConnectError("connect")])
def test_transient_transport_errors_retry_until_success(failure):
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise failure
        return "recovered"

    value, attempts = retry_read_only(operation, attempts=3)
    assert value == "recovered"
    assert attempts == 3
    assert calls == 3


def test_exhaustion_raises_last_transient_exception():
    errors = [TimeoutError("first"), ConnectionError("last")]
    calls = 0

    def operation():
        nonlocal calls
        error = errors[calls]
        calls += 1
        raise error

    with pytest.raises(ConnectionError, match="last"):
        retry_read_only(operation, attempts=2)
    assert calls == 2


def test_non_transient_exception_is_not_retried():
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        raise ValueError("invalid input")

    with pytest.raises(ValueError, match="invalid input"):
        retry_read_only(operation, attempts=5)
    assert calls == 1


@pytest.mark.parametrize("attempts", [0, -1, True, False, 1.5, "3", None])
def test_attempt_count_must_be_positive_integer(attempts):
    with pytest.raises(ValueError, match="positive integer"):
        retry_read_only(lambda: None, attempts=attempts)
