"""Multi-channel real-time QA alerting for Slack, Discord, Telegram, and Generic Webhooks."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse


def _validate_webhook_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError(f"invalid webhook URL: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("webhook URL must not contain embedded credentials in authority")
    return cleaned


def _send_json_payload(url: str, payload: Mapping[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    validated = _validate_webhook_url(url)
    raw = json.dumps(dict(payload)).encode("utf-8")
    # Passing `data=raw` causes urllib.request.Request to send an HTTP POST payload cleanly.
    req = urllib.request.Request(  # noqa: S310
        validated,
        data=raw,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "SAQA-Webhook-Notifier/2.5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310 - scheme validated above
            return {"ok": 200 <= resp.status < 300, "status_code": resp.status}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code, "error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "status_code": 0, "error": str(exc)}


def format_alert_message(
    analytics: Mapping[str, Any],
    *,
    suite_name: str = "saqa-suite",
    target: str = "",
    jira_url: str = "",
) -> str:
    status = str(analytics.get("overall_status", "UNVERIFIED"))
    icon = "✅" if status == "PASS" else ("❌" if status == "FAIL" else "⚠️")
    counts = analytics.get("status_counts", {})
    lat = analytics.get("latency", {})
    lines = [
        f"{icon} *SAQA Quality Alert — {suite_name}*",
        f"• Status: `{status}` | Health: `{analytics.get('health_score')}/100 ({analytics.get('health_grade')})`",
        f"• Pass Rate: `{analytics.get('pass_rate_pct')}%` ({counts.get('PASS', 0)}/{analytics.get('total_records', 0)}) | P95 Latency: `{lat.get('p95_ms', 0)} ms`",
    ]
    if target:
        lines.append(f"• Target: `{target}`")
    failing = analytics.get("failing_tests") or []
    if failing:
        failed_ids = ", ".join(str(f.get("test_id")) for f in failing[:5])
        lines.append(f"• Failing Checks: `{failed_ids}`")
    if jira_url:
        lines.append(f"• Jira Control Plane: {jira_url}")
    return "\n".join(lines)


def dispatch_notifications(
    analytics: Mapping[str, Any],
    *,
    suite_name: str = "saqa-suite",
    target: str = "",
    jira_url: str = "",
    webhook_urls: tuple[str, ...] | list[str] = (),
    only_on_failure: bool = False,
    sender=_send_json_payload,
) -> list[dict[str, Any]]:
    """Send QA execution alerts to configured Slack, Discord, Telegram, and generic webhooks."""
    status = str(analytics.get("overall_status", "UNVERIFIED"))
    if only_on_failure and status == "PASS":
        return []

    text = format_alert_message(analytics, suite_name=suite_name, target=target, jira_url=jira_url)
    deliveries: list[dict[str, Any]] = []

    slack_url = os.getenv("SAQA_SLACK_WEBHOOK_URL", "").strip()
    if slack_url:
        res = sender(slack_url, {"text": text})
        deliveries.append({"channel": "slack", **res})

    discord_url = os.getenv("SAQA_DISCORD_WEBHOOK_URL", "").strip()
    if discord_url:
        res = sender(discord_url, {"content": text})
        deliveries.append({"channel": "discord", **res})

    tg_token = os.getenv("SAQA_TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.getenv("SAQA_TELEGRAM_CHAT_ID", "").strip()
    if tg_token and tg_chat:
        tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        res = sender(tg_url, {"chat_id": tg_chat, "text": text})
        deliveries.append({"channel": "telegram", **res})

    env_generic = os.getenv("SAQA_WEBHOOK_URL", "").strip()
    all_generic = [u for u in ([env_generic] if env_generic else []) + list(webhook_urls) if u.strip()]
    for url in all_generic:
        low = url.lower()
        if "hooks.slack.com" in low:
            payload: dict[str, Any] = {"text": text}
            channel = "slack"
        elif "discord.com/api/webhooks" in low or "discordapp.com/api/webhooks" in low:
            payload = {"content": text}
            channel = "discord"
        else:
            payload = {
                "schema": "saqa.webhook-alert.v1",
                "suite_name": suite_name,
                "target": target,
                "overall_status": status,
                "health_score": analytics.get("health_score"),
                "health_grade": analytics.get("health_grade"),
                "pass_rate_pct": analytics.get("pass_rate_pct"),
                "message": text,
            }
            channel = "webhook"
        res = sender(url, payload)
        deliveries.append({"channel": channel, **res})

    return deliveries
