# Guarded Real-Web Smoke Testing

SAQA now supports a **real-web smoke adapter** for websites that the operator has explicit authorization to test.

This is intentionally separate from the primary certification targets. OWASP Juice Shop and OWASP WebGoat remain the deterministic local/containerized reference targets. OWASP documents Juice Shop as a deliberately insecure application suitable for security tooling and Docker-based local use, and WebGoat as a self-contained environment for safe application-security testing. See the official OWASP guides before changing target profiles.

## Safety model

The real-web runner fails closed unless all of the following are true:

- `SAQA_REAL_WEB_TARGET` is explicitly provided.
- Its hostname exactly matches one entry in `SAQA_REAL_WEB_ALLOWLIST`.
- HTTPS is used by default.
- Only `GET` requests are issued.
- Redirects are not automatically trusted; every redirect destination is revalidated against the allowlist.
- No credentials, login, form submission, mutation, crawling, brute force, or exploitation is performed.

## Run

```bash
export SAQA_REAL_WEB_TARGET='https://authorized.example/'
export SAQA_REAL_WEB_ALLOWLIST='authorized.example'
python scripts/real_web_smoke.py
```

Evidence is written to:

```text
artifacts/targets/real-web-smoke.json
```

The result includes HTTP status, content type, title presence, response time, redirect chain, and selected security-header presence.

## Important

Do **not** put a public website into the allowlist merely because it is reachable. The operator must have permission to automate against that host. The runner is an authorization guard, not a permission grant.

HTTP can only be enabled deliberately with:

```bash
export SAQA_ALLOW_HTTP_REAL_WEB=1
```

This should only be used for an explicitly authorized HTTP test environment.
