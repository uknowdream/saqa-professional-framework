"""Secure Jira Cloud integration for runtime CI verification.

Credentials are intentionally read from environment variables only. Never log
or persist the API token.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

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


class JiraClient:
    """Minimal read-only Jira Cloud client suitable for CI health checks."""

    def __init__(self, config: JiraConfig, timeout: float = 15.0) -> None:
        self.config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            auth=(config.email, config.api_token),
            headers={"Accept": "application/json"},
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
        """Verify authentication and read-only access to the configured project."""
        response = self._client.get(
            f"/rest/api/3/project/{self.config.project_key}"
        )
        if response.status_code in {401, 403}:
            raise RuntimeError(
                f"Jira authentication/authorization failed (HTTP {response.status_code})"
            )
        response.raise_for_status()
        payload = response.json()
        return JiraProjectResult(
            key=str(payload.get("key", "")),
            name=str(payload.get("name", "")),
            project_type=str(payload.get("projectTypeKey", "")),
        )


def verify_from_env() -> JiraProjectResult:
    with JiraClient(JiraConfig.from_env()) as client:
        return client.verify_access()
