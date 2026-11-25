"""Multi-target competitive & multi-environment QA benchmark matrix engine."""
from __future__ import annotations

import csv
import html
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Sequence

from .web_audit import DeepAuditResult, run_deep_web_audit


def run_multi_target_benchmark(
    urls: Sequence[str],
    *,
    output_dir: Path | None = None,
    include_spa_audit: bool = False,
    workers: int = 4,
    auditor: Callable[..., DeepAuditResult] = run_deep_web_audit,
) -> dict[str, Any]:
    """Audit multiple HTTP(S) targets in parallel and produce a comparative QA benchmark matrix."""
    cleaned = [u.strip() for u in urls if u and u.strip()]
    if len(cleaned) < 1:
        raise ValueError("benchmark requires at least one target URL")

    def _audit_one(idx_and_url: tuple[int, str]) -> tuple[int, DeepAuditResult]:
        idx, target_url = idx_and_url
        sub_dir = (output_dir / f"target-{idx + 1:02d}") if output_dir is not None else None
        res = auditor(target_url, output_dir=sub_dir, include_spa_audit=include_spa_audit)
        return idx, res

    max_w = max(1, min(workers, len(cleaned)))
    if max_w == 1:
        ordered_pairs = [_audit_one((i, u)) for i, u in enumerate(cleaned)]
    else:
        with ThreadPoolExecutor(max_workers=max_w) as pool:
            ordered_pairs = sorted(pool.map(_audit_one, enumerate(cleaned)), key=lambda item: item[0])

    entries: list[dict[str, Any]] = []
    for _, res in ordered_pairs:
        by_id = {r.test_id: r for r in res.records}
        tls_det = by_id["pillar-1.tls-certificate-audit"].details if "pillar-1.tls-certificate-audit" in by_id else {}
        sec_det = by_id["pillar-2.security-headers-and-cookies"].details if "pillar-2.security-headers-and-cookies" in by_id else {}
        link_det = by_id["pillar-5.broken-links-and-assets"].details if "pillar-5.broken-links-and-assets" in by_id else {}
        lat = res.analytics["latency"]

        entries.append({
            "target_url": res.target_url,
            "overall_status": res.analytics["overall_status"],
            "health_score": res.analytics["health_score"],
            "health_grade": res.analytics["health_grade"],
            "pass_rate_pct": res.analytics["pass_rate_pct"],
            "pillars_passed": res.analytics["status_counts"]["PASS"],
            "pillars_total": res.analytics["total_records"],
            "tls_protocol": tls_det.get("protocol", "N/A"),
            "tls_days_remaining": tls_det.get("days_remaining"),
            "owasp_header_score_pct": sec_det.get("security_header_score_pct", 0.0),
            "broken_links_count": len(link_det.get("broken_links") or []),
            "findings_count": len(res.findings),
            "p50_ms": lat["p50_ms"],
            "p95_ms": lat["p95_ms"],
            "manifest_sha256": res.manifest_sha256,
        })

    ranked = sorted(entries, key=lambda e: (-e["health_score"], e["p95_ms"], e["target_url"]))
    for rank_idx, item in enumerate(ranked, start=1):
        item["rank"] = rank_idx

    benchmark = {
        "schema": "saqa.benchmark.v1",
        "target_count": len(ranked),
        "leader": ranked[0]["target_url"] if ranked else None,
        "rankings": ranked,
    }

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "benchmark.json").write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
        (output_dir / "benchmark.md").write_text(_render_benchmark_markdown(benchmark), encoding="utf-8")
        (output_dir / "benchmark.html").write_text(_render_benchmark_html(benchmark), encoding="utf-8")
        _write_benchmark_csv(ranked, output_dir / "benchmark.csv")

    return benchmark


def _render_benchmark_markdown(benchmark: dict[str, Any]) -> str:
    lines = [
        "# SAQA Multi-Target Quality Benchmark Matrix",
        "",
        f"- **Targets Audited:** `{benchmark['target_count']}`",
        f"- **Top Ranked Target:** `{benchmark['leader']}`",
        "",
        "| Rank | Target | Status | Health | OWASP Headers | TLS Days | Broken Links | P50 (ms) | P95 (ms) | Findings |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in benchmark["rankings"]:
        lines.append(
            f"| #{item['rank']} | `{item['target_url']}` | `{item['overall_status']}` | "
            f"**{item['health_score']} ({item['health_grade']})** | {item['owasp_header_score_pct']}% | "
            f"{item['tls_days_remaining'] if item['tls_days_remaining'] is not None else 'N/A'} | "
            f"{item['broken_links_count']} | {item['p50_ms']} | {item['p95_ms']} | {item['findings_count']} |"
        )
    return "\n".join(lines) + "\n"


def _render_benchmark_html(benchmark: dict[str, Any]) -> str:
    rows = []
    for item in benchmark["rankings"]:
        esc_u = html.escape(str(item["target_url"]))
        st = html.escape(str(item["overall_status"]))
        badge_cls = "pass" if st == "PASS" else "fail"
        rows.append(
            f"<tr><td><strong>#{item['rank']}</strong></td><td><code>{esc_u}</code></td>"
            f"<td><span class='badge {badge_cls}'>{st}</span></td>"
            f"<td><strong>{item['health_score']}</strong> ({html.escape(str(item['health_grade']))})</td>"
            f"<td>{item['owasp_header_score_pct']}%</td>"
            f"<td>{item['tls_days_remaining'] if item['tls_days_remaining'] is not None else 'N/A'}</td>"
            f"<td>{item['broken_links_count']}</td><td>{item['p50_ms']} ms</td><td>{item['p95_ms']} ms</td>"
            f"<td>{item['findings_count']}</td></tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>SAQA Benchmark Matrix</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 28px; }}
  .wrap {{ max-width: 1180px; margin: 0 auto; background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 24px; }}
  h1 {{ margin-top: 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 16px; }}
  th, td {{ padding: 10px 8px; border-bottom: 1px solid #334155; text-align: left; }}
  th {{ color: #94a3b8; }}
  code {{ background: #0b1220; padding: 2px 6px; border-radius: 6px; }}
  .badge {{ padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 700; }}
  .pass {{ background: rgba(34,197,94,0.2); color: #86efac; }}
  .fail {{ background: rgba(239,68,68,0.2); color: #fca5a5; }}
</style></head><body><div class="wrap">
<h1>SAQA Multi-Target Quality Benchmark Matrix</h1>
<p>Targets Audited: <strong>{benchmark['target_count']}</strong> &middot; Leader: <code>{html.escape(str(benchmark['leader'] or ''))}</code></p>
<table><thead><tr><th>Rank</th><th>Target</th><th>Status</th><th>Health</th><th>OWASP Headers</th><th>TLS Days</th><th>Broken Links</th><th>P50</th><th>P95</th><th>Findings</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></body></html>
"""


def _write_benchmark_csv(rankings: Sequence[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Rank", "Target URL", "Status", "Health Score", "Grade", "OWASP Header %", "TLS Days Remaining", "Broken Links", "P50 (ms)", "P95 (ms)", "Findings"])
        for item in rankings:
            writer.writerow([
                item["rank"],
                item["target_url"],
                item["overall_status"],
                item["health_score"],
                item["health_grade"],
                item["owasp_header_score_pct"],
                item["tls_days_remaining"],
                item["broken_links_count"],
                item["p50_ms"],
                item["p95_ms"],
                item["findings_count"],
            ])
