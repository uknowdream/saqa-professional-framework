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


def test_preflight_main_rejects_missing_required_directory(monkeypatch, tmp_path):
    import scripts.quality_preflight as module

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    try:
        module.main()
    except SystemExit as exc:
        assert "required directory missing: scripts" in str(exc)
    else:
        raise AssertionError("preflight accepted a missing required directory")
