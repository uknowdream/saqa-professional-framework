import pytest

from saqa.test_data import TestDataScope as DataScope


def test_cleanup_is_lifo_and_idempotent():
    events = []
    with DataScope() as scope:
        scope.register(lambda: events.append("first"))
        scope.register(lambda: events.append("second"))
    assert events == ["second", "first"]
    scope.close()
    assert events == ["second", "first"]


def test_cleanup_failure_is_not_silent():
    events = []
    scope = DataScope()
    scope.register(lambda: events.append("ok"))

    def bad():
        events.append("bad")
        raise RuntimeError("cleanup")

    scope.register(bad)
    with pytest.raises(RuntimeError, match="cleanup operation") as exc_info:
        scope.close()
    assert "cleanup" in str(exc_info.value)
    assert scope.closed
    assert events == ["bad", "ok"]


def test_cleanup_does_not_replace_body_failure():
    scope = DataScope()

    def bad():
        raise RuntimeError("cleanup")

    scope.register(bad)
    with pytest.raises(ValueError, match="body") as exc_info:
        with scope:
            raise ValueError("body")
    assert "cleanup operation" in str(exc_info.value)


def test_register_after_close_is_rejected():
    scope = DataScope()
    scope.close()
    with pytest.raises(RuntimeError, match="already closed"):
        scope.register(lambda: None)
