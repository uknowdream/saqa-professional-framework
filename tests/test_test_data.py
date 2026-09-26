from saqa.test_data import TestDataScope
import pytest

def test_cleanup_is_lifo_and_idempotent():
    events=[]
    with TestDataScope() as scope:
        scope.register(lambda: events.append("first"))
        scope.register(lambda: events.append("second"))
    assert events==["second","first"]
    scope.close()
    assert events==["second","first"]

def test_cleanup_failure_is_not_silent():
    events=[]
    scope=TestDataScope()
    scope.register(lambda: events.append("ok"))
    def bad():
        events.append("bad")
        raise RuntimeError("cleanup")
    scope.register(bad)
    with pytest.raises(RuntimeError,match="cleanup operation"):
        scope.close()
    assert scope.closed
    assert events==["bad","ok"]

def test_register_after_close_is_rejected():
    scope=TestDataScope(); scope.close()
    with pytest.raises(RuntimeError,match="already closed"):
        scope.register(lambda: None)
