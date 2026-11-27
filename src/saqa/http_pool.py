"""Persistent HTTP keep-alive connection pool with Anti-SSRF redirect validation for SAQA.

Uses ``httpx.Client`` connection pooling automatically when ``httpx`` is installed,
and falls back transparently to ``saqa.api.request`` in stdlib-only environments.
When auditing public HTTP(S) targets, redirects jumping into private RFC1918,
loopback, or cloud-metadata (169.254.169.254) IP ranges are blocked fail-closed.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any
from urllib.parse import urljoin, urlparse

from .api import ApiResponse
from .api import request as stdlib_request
from .ssrf import host_is_private_or_local, validate_safe_outbound_url

_MAX_REDIRECT_HOPS = 10


@contextmanager
def create_pooled_requester(
    *,
    max_connections: int = 20,
    block_private_redirects: bool = True,
    transport: Any = None,
) -> Iterator[Callable[..., ApiResponse]]:
    """Yield a thread-safe keep-alive requester compatible with ``saqa.api.request``."""
    try:
        import httpx
    except ImportError:
        yield stdlib_request
        return

    limits = httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections)
    client_kwargs: dict[str, Any] = {"trust_env": False, "limits": limits}
    if transport is not None:
        client_kwargs["transport"] = transport
    client_no_follow = httpx.Client(follow_redirects=False, **client_kwargs)
    client_follow = httpx.Client(follow_redirects=True, **client_kwargs)

    def _pooled_request(
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
        body: Any = None,
        timeout: float = 10.0,
        follow_redirects: bool = True,
        use_environment_proxies: bool = False,
    ) -> ApiResponse:
        if use_environment_proxies or body is not None:
            return stdlib_request(
                url,
                method=method,
                headers=headers,
                body=body,
                timeout=timeout,
                follow_redirects=follow_redirects,
                use_environment_proxies=use_environment_proxies,
            )

        parsed_initial = urlparse(url)
        initial_host = parsed_initial.hostname or ""
        initial_is_local = host_is_private_or_local(initial_host, resolve_dns=False)
        started = time.perf_counter()

        try:
            # If target is public & follow_redirects=True & SSRF protection enabled, validate every redirect hop!
            if follow_redirects and block_private_redirects and not initial_is_local:
                current_url = url
                req_headers = dict(headers or {})
                resp = None
                for _ in range(_MAX_REDIRECT_HOPS):
                    resp = client_no_follow.request(method.upper(), current_url, headers=req_headers, timeout=timeout)
                    if resp.status_code in {301, 302, 303, 307, 308} and resp.headers.get("location"):
                        next_url = urljoin(current_url, resp.headers["location"])
                        try:
                            validate_safe_outbound_url(next_url, allow_private=False, resolve_dns=True, label="redirect")
                        except ValueError as ssrf_exc:
                            return ApiResponse(
                                0,
                                {},
                                b"",
                                (time.perf_counter() - started) * 1000.0,
                                error=str(ssrf_exc),
                            )
                        # Strip sensitive headers across cross-origin redirect
                        if urlparse(next_url).netloc.lower() != urlparse(current_url).netloc.lower():
                            req_headers.pop("Authorization", None)
                            req_headers.pop("Cookie", None)
                        current_url = next_url
                        continue
                    break
                if resp is None:  # pragma: no cover
                    return ApiResponse(0, {}, b"", 0.0, error="no response")
            else:
                active = client_follow if follow_redirects else client_no_follow
                resp = active.request(method.upper(), url, headers=dict(headers or {}), timeout=timeout)

            elapsed_ms = (time.perf_counter() - started) * 1000.0
            err = f"HTTP {resp.status_code}" if resp.status_code >= 400 else None
            return ApiResponse(
                resp.status_code,
                dict(resp.headers.items()),
                resp.content,
                elapsed_ms,
                error=err,
            )
        except httpx.HTTPError as exc:
            return ApiResponse(
                0,
                {},
                b"",
                (time.perf_counter() - started) * 1000.0,
                error=f"transport error: {exc}",
            )

    try:
        yield _pooled_request
    finally:
        client_follow.close()
        client_no_follow.close()
