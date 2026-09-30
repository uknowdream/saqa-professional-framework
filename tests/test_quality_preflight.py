from scripts.quality_preflight import ROOT, run


def test_preflight_root_points_to_repository():
    assert (ROOT / "pyproject.toml").is_file()


def test_preflight_run_propagates_failure(monkeypatch):
    class Result:
        returncode = 7

    def fake_run(*args, **kwargs):
        return Result()

    monkeypatch.setattr("scripts.quality_preflight.subprocess.run", fake_run)
    try:
        run("synthetic failure", ["false"])
    except SystemExit as exc:
        assert "synthetic failure" in str(exc)
    else:
        raise AssertionError("preflight failure was not propagated")


def test_preflight_run_accepts_success(monkeypatch):
    class Result:
        returncode = 0

    monkeypatch.setattr("scripts.quality_preflight.subprocess.run", lambda *args, **kwargs: Result())
    assert run("synthetic success", ["true"]) is None
