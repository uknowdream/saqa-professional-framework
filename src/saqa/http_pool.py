"""Persistent HTTP keep-alive connection pool for high-throughput SAQA suites & crawlers.

Uses ``httpx.Client`` connection pooling automatically when ``httpx`` is installed,
and falls back transparently to ``saqa.api.request`` in stdlib-only environments.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping

from .api import ApiResponse, request as stdlib_request


@contextmanager
def create_pooled_requester(*, max_connections: int = 20) -> Iterator[Callable[..., ApiResponse]]:
    """Yield a thread-safe keep-alive requester compatible with ``saqa.api.request``."""
    try:
        import httpx
    except ImportError:
        yield stdlib_request
        return

    limits = httpx.Limits(max_connections=max_connections, max_keepalive_connections=max_connections)
    client_follow = httpx.Client(follow_redirects=True, trust_env=False, limits=limits)
    client_no_follow = httpx.Client(follow_redirects=False, trust_env=False, limits=limits)

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
        active = client_follow if follow_redirects else client_no_follow
        started = time.perf_counter()
        try:
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
