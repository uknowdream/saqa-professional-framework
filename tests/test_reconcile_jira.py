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
