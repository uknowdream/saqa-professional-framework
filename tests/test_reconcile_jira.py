from __future__ import annotations

from urllib.request import Request

from scripts.reconcile_jira import SafeArtifactRedirectHandler


def test_artifact_redirect_strips_authorization_cross_host() -> None:
    request = Request(
        "https://api.github.com/repos/example/repo/actions/artifacts/1/zip",
        headers={"Authorization": "Bearer secret"},
    )
    redirected = SafeArtifactRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {"Location": "https://storage.example.test/artifact.zip"},
        "https://storage.example.test/artifact.zip",
    )
    assert redirected is not None
    assert redirected.get_header("Authorization") is None


def test_artifact_redirect_preserves_authorization_same_host() -> None:
    request = Request(
        "https://api.github.com/repos/example/repo/actions/artifacts/1/zip",
        headers={"Authorization": "Bearer secret"},
    )
    redirected = SafeArtifactRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {"Location": "https://api.github.com/repos/example/repo/actions/artifacts/1/zip?retry=1"},
        "https://api.github.com/repos/example/repo/actions/artifacts/1/zip?retry=1",
    )
    assert redirected is not None
    assert redirected.get_header("Authorization") == "Bearer secret"


def test_completed_runs_continues_after_full_filtered_page(monkeypatch):
    import scripts.reconcile_jira as module

    first_page = [
        {"id": i, "event": "pull_request", "status": "completed", "head_branch": "main", "head_sha": f"sha-{i}"}
        for i in range(100)
    ]
    second_page = [
        {"id": 101, "event": "pull_request_target", "status": "completed", "head_branch": "main", "head_sha": "pr-target"},
        {"id": 102, "event": "push", "status": "completed", "head_branch": "main", "head_sha": "push-sha"},
    ]
    calls = []

    def fake_gh_get(path):
        calls.append(path)
        return {"workflow_runs": first_page if "page=1" in path else second_page}

    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    monkeypatch.setattr(module, "gh_get", fake_gh_get)
    result = module.completed_runs("SAQA CI", 123, max_pages=3)

    assert len(calls) == 2
    assert [run["id"] for run in result] == [102]
