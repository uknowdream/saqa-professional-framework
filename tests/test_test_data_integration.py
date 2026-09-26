from saqa.test_data import TestDataScope

def test_cross_service_scope_runs_cleanup_in_reverse_order():
    events=[]
    with TestDataScope() as scope:
        for service in ("api","db","queue"):
            scope.register(lambda service=service: events.append(service))
    assert events==["queue","db","api"]

def test_cross_service_scope_failure_is_fail_closed():
    scope=TestDataScope()
    scope.register(lambda: (_ for _ in ()).throw(RuntimeError("db cleanup")))
    try:
        scope.close()
    except RuntimeError as exc:
        assert "cleanup operation" in str(exc)
    else:
        raise AssertionError("cleanup failure was swallowed")
