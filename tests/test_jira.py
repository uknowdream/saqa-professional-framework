from pathlib import Path

import httpx

from saqa.jira import JiraClient, JiraConfig


def test_jira_transition_uses_only_an_available_exact_transition() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/transitions") and request.method == "GET":
            return httpx.Response(200, json={"transitions": [{"id": "31", "name": "Complete", "to": {"name": "Done"}}]})
        if request.url.path.endswith("/QA-9") and request.method == "GET":
            return httpx.Response(200, json={"fields": {"status": {"name": "In Progress"}, "labels": []}})
        if request.url.path.endswith("/transitions") and request.method == "POST":
            return httpx.Response(204)
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    config = JiraConfig("https://jira.example", "qa@example.com", "secret-token", "QA")
    client = JiraClient(config, timeout=1.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url=config.base_url)
    try:
        assert client.transition_to_any("QA-9", ("Done",)) == "Done"
    finally:
        client.close()

    assert calls == [
        "/rest/api/3/issue/QA-9/transitions",
        "/rest/api/3/issue/QA-9",
        "/rest/api/3/issue/QA-9/transitions",
    ]
