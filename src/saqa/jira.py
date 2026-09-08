"""Secure Jira Cloud integration for CI verification and controlled write-back."""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any
import httpx

@dataclass(frozen=True, slots=True)
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    project_key: str
    @classmethod
    def from_env(cls) -> "JiraConfig":
        values = {
            "base_url": os.getenv("JIRA_BASE_URL", "").strip().rstrip("/"),
            "email": os.getenv("JIRA_EMAIL", "").strip(),
            "api_token": os.getenv("JIRA_API_TOKEN", ""),
            "project_key": os.getenv("JIRA_PROJECT_KEY", "").strip(),
        }
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise ValueError("Missing Jira configuration: " + ", ".join(missing))
        if not values["base_url"].startswith("https://"):
            raise ValueError("JIRA_BASE_URL must use HTTPS")
        return cls(**values)

@dataclass(frozen=True, slots=True)
class JiraProjectResult:
    key: str
    name: str
    project_type: str

@dataclass(frozen=True, slots=True)
class JiraIssueResult:
    key: str
    id: str
    url: str

class JiraClient:
    """Jira Cloud client with read-only verification and idempotent write-back."""
    def __init__(self, config: JiraConfig, timeout: float = 15.0) -> None:
        self.config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            auth=(config.email, config.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
            follow_redirects=False,
        )
    def close(self) -> None:
        self._client.close()
    def __enter__(self) -> "JiraClient":
        return self
    def __exit__(self, *_: object) -> None:
        self.close()
    def verify_access(self) -> JiraProjectResult:
        response = self._client.get(f"/rest/api/3/project/{self.config.project_key}")
        if response.status_code in {401, 403}:
            raise RuntimeError(f"Jira authentication/authorization failed (HTTP {response.status_code})")
        response.raise_for_status()
        payload = response.json()
        return JiraProjectResult(str(payload.get("key", "")), str(payload.get("name", "")), str(payload.get("projectTypeKey", "")))
    def find_bootstrap_issues(self) -> dict[str, JiraIssueResult]:
        """Return existing SAQA bootstrap work items, keyed by exact summary."""
        response = self._client.get("/rest/api/3/search/jql", params={
            "jql": f"project = {self.config.project_key} AND labels = saqa-bootstrap",
            "maxResults": 100,
            "fields": "summary",
        })
        if response.status_code in {401, 403}:
            raise RuntimeError(f"Jira authentication/authorization failed (HTTP {response.status_code})")
        response.raise_for_status()
        issues = response.json().get("issues", [])
        return {str(i["fields"]["summary"]): JiraIssueResult(str(i["key"]), str(i["id"]), f"{self.config.base_url}/browse/{i['key']}") for i in issues if i.get("key") and i.get("fields", {}).get("summary")}
    def create_task(self, summary: str, description: str, labels: list[str]) -> JiraIssueResult:
        """Create a Jira Task using Atlassian Document Format."""
        payload: dict[str, Any] = {"fields": {
            "project": {"key": self.config.project_key},
            "issuetype": {"name": "Task"},
            "summary": summary,
            "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]},
            "labels": labels,
        }}
        response = self._client.post("/rest/api/3/issue", json=payload)
        if response.status_code in {401, 403}:
            raise RuntimeError(f"Jira write authorization failed (HTTP {response.status_code})")
        response.raise_for_status()
        result = response.json()
        key = str(result["key"])
        return JiraIssueResult(key, str(result["id"]), f"{self.config.base_url}/browse/{key}")

def verify_from_env() -> JiraProjectResult:
    with JiraClient(JiraConfig.from_env()) as client:
        return client.verify_access()
