"""Shared URL redaction contract for SAQA evidence."""
from __future__ import annotations

from urllib.parse import urlparse


def redact_url(url: str) -> str:
    """Persist only scheme, host, and port; never credentials, path, params, query, or fragment."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return parsed._replace(
            netloc=f"{host}{port}",
            path="",
            params="",
            query="",
            fragment="",
        ).geturl()
    except ValueError:
        return "<invalid-url>"
