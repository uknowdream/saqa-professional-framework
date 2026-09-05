# Jira CI integration

The framework verifies read-only access to Jira Cloud at runtime.

## Required GitHub Actions secret

Create a repository secret named `JIRA_API_TOKEN`. The token is never stored in source code, artifacts, or test evidence.

## Runtime configuration

- `JIRA_BASE_URL=https://dreamedx.atlassian.net`
- `JIRA_EMAIL=teukusaiful7@gmail.com`
- `JIRA_PROJECT_KEY=QA`
- `JIRA_API_TOKEN` comes only from GitHub Actions Secrets

The CI check performs a read-only `GET /rest/api/3/project/{projectKey}` request and validates the returned project key and name.
