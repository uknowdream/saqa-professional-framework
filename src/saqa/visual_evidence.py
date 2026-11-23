"""Visual QA evidence & document exporters: PNG scorecards, live browser screenshots, SVG charts, and CSV matrices."""
from __future__ import annotations

import csv
import html
import os
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .evidence import EvidenceRecord

# Minimal 5x7 crisp uppercase/digit/symbol bitmap font for dependency-free PNG scorecards
_FONT_5X7: dict[str, tuple[str, ...]] = {
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11100", "10010", "10001", "10001", "10001", "10010", "11100"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10011", "10101", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("01110", "10000", "11110", "10001", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "|": ("00100", "00100", "00100", "00100", "00100", "00100", "00100"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
}


def _record_dict(item: EvidenceRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(item, EvidenceRecord):
        return {
            "test_id": item.test_id,
            "status": item.status,
            "observed_at": item.observed_at,
            "target": item.target,
            "details": dict(item.details),
        }
    return {
        "test_id": str(item["test_id"]),
        "status": str(item["status"]),
        "observed_at": str(item["observed_at"]),
        "target": str(item["target"]),
        "details": dict(item.get("details") or {}),
    }


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _encode_rgb_png(width: int, height: int, pixels: bytearray) -> bytes:
    raw_rows = bytearray()
    stride = width * 3
    for y in range(height):
        raw_rows.append(0)  # Filter type 0 (None)
        start = y * stride
        raw_rows.extend(pixels[start : start + stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw_rows), level=6))
        + _png_chunk(b"IEND", b"")
    )


class _Canvas:
    def __init__(self, width: int, height: int, bg: tuple[int, int, int]) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(bg) * (width * height))

    def fill_rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        row_bytes = bytes(color) * (x1 - x0)
        for py in range(y0, y1):
            offset = (py * self.width + x0) * 3
            self.pixels[offset : offset + len(row_bytes)] = row_bytes

    def stroke_rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int], thickness: int = 1) -> None:
        self.fill_rect(x, y, w, thickness, color)
        self.fill_rect(x, y + h - thickness, w, thickness, color)
        self.fill_rect(x, y, thickness, h, color)
        self.fill_rect(x + w - thickness, y, thickness, h, color)

    def draw_text(self, x: int, y: int, text: str, color: tuple[int, int, int], scale: int = 2) -> None:
        cursor = x
        for ch in text.upper():
            glyph = _FONT_5X7.get(ch, _FONT_5X7[" "])
            for row_i, row in enumerate(glyph):
                for col_i, bit in enumerate(row):
                    if bit == "1":
                        self.fill_rect(cursor + col_i * scale, y + row_i * scale, scale, scale, color)
            cursor += 6 * scale


def render_scorecard_png(
    analytics: Mapping[str, Any],
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    output_path: Path,
    *,
    title: str = "SAQA QUALITY SCORECARD",
) -> Path:
    """Render a crisp, dependency-free 960x540 PNG QA scorecard & latency chart."""
    width, height = 960, 540
    bg = (15, 23, 42)
    panel = (30, 41, 59)
    border = (51, 65, 85)
    text_main = (226, 232, 240)
    text_muted = (148, 163, 184)
    c_pass = (34, 197, 94)
    c_fail = (239, 68, 68)
    c_blocked = (245, 158, 11)
    c_accent = (56, 189, 248)

    canvas = _Canvas(width, height, bg)

    overall = str(analytics.get("overall_status", "UNVERIFIED"))
    badge_color = c_pass if overall == "PASS" else (c_fail if overall == "FAIL" else c_blocked)

    # Top header banner
    canvas.fill_rect(24, 20, width - 48, 66, panel)
    canvas.stroke_rect(24, 20, width - 48, 66, border, 2)
    canvas.fill_rect(24, 20, 8, 66, badge_color)
    canvas.draw_text(48, 36, title[:42], text_main, scale=2)
    canvas.draw_text(48, 62, f"STATUS: {overall}  |  GRADE: {analytics.get('health_grade', 'N/A')}", text_muted, scale=1)
    canvas.fill_rect(width - 170, 34, 128, 36, badge_color)
    canvas.draw_text(width - 150, 44, overall[:8], bg, scale=2)

    # 4 KPI Cards
    counts = analytics["status_counts"]
    lat = analytics["latency"]
    kpis = [
        ("HEALTH SCORE", f"{analytics['health_score']}/100", c_pass if analytics["health_score"] >= 85 else c_fail),
        ("PASS RATE", f"{analytics['pass_rate_pct']}%", c_accent),
        ("CHECKS PASSED", f"{counts['PASS']}/{analytics['total_records']}", c_pass),
        ("LATENCY P95", f"{lat['p95_ms']} MS", c_accent),
    ]
    card_w = 216
    for idx, (label, val, accent) in enumerate(kpis):
        cx = 24 + idx * (card_w + 16)
        cy = 104
        canvas.fill_rect(cx, cy, card_w, 86, panel)
        canvas.stroke_rect(cx, cy, card_w, 86, border, 1)
        canvas.fill_rect(cx, cy, card_w, 4, accent)
        canvas.draw_text(cx + 14, cy + 16, label, text_muted, scale=1)
        canvas.draw_text(cx + 14, cy + 42, val[:14], text_main, scale=2)

    # Status Distribution Stacked Bar
    canvas.fill_rect(24, 206, width - 48, 66, panel)
    canvas.stroke_rect(24, 206, width - 48, 66, border, 1)
    canvas.draw_text(40, 218, "STATUS DISTRIBUTION", text_muted, scale=1)
    bar_x, bar_y, bar_w, bar_h = 40, 236, width - 80, 18
    canvas.fill_rect(bar_x, bar_y, bar_w, bar_h, bg)
    total = max(1, int(analytics["total_records"]))
    pass_w = int(bar_w * (counts["PASS"] / total))
    fail_w = int(bar_w * (counts["FAIL"] / total))
    blk_w = int(bar_w * (counts["BLOCKED"] / total))
    canvas.fill_rect(bar_x, bar_y, pass_w, bar_h, c_pass)
    canvas.fill_rect(bar_x + pass_w, bar_y, fail_w, bar_h, c_fail)
    canvas.fill_rect(bar_x + pass_w + fail_w, bar_y, blk_w, bar_h, c_blocked)
    canvas.draw_text(
        40,
        258,
        f"PASS: {counts['PASS']}  FAIL: {counts['FAIL']}  BLOCKED: {counts['BLOCKED']}  UNVERIFIED: {counts['UNVERIFIED']}",
        text_muted,
        scale=1,
    )

    # Latency Horizontal Bar Chart (top 7 executed tests)
    canvas.fill_rect(24, 286, width - 48, 200, panel)
    canvas.stroke_rect(24, 286, width - 48, 200, border, 1)
    canvas.draw_text(40, 298, "EXECUTED SCENARIOS & RESPONSE LATENCY (MS)", text_muted, scale=1)

    norm_records = [_record_dict(r) for r in records]
    timed = []
    for rec in norm_records:
        ms = rec["details"].get("elapsed_ms", rec["details"].get("duration_ms", 0.0))
        timed.append((rec["test_id"], rec["status"], float(ms) if isinstance(ms, (int, float)) else 0.0))
    top_rows = sorted(timed, key=lambda item: (-item[2], item[0]))[:7]
    max_ms = max((item[2] for item in top_rows), default=1.0) or 1.0

    for i, (test_id, status, ms) in enumerate(top_rows):
        ry = 320 + i * 22
        row_color = c_pass if status == "PASS" else (c_fail if status == "FAIL" else c_blocked)
        canvas.draw_text(40, ry + 3, test_id[:28], text_main, scale=1)
        chart_x = 240
        chart_max_w = 560
        fill_w = max(4, int(chart_max_w * (ms / max_ms)))
        canvas.fill_rect(chart_x, ry, chart_max_w, 14, bg)
        canvas.fill_rect(chart_x, ry, fill_w, 14, row_color)
        canvas.draw_text(chart_x + chart_max_w + 14, ry + 3, f"{ms:.1f} MS ({status})", text_muted, scale=1)

    # Cryptographic Footer
    sha = str(analytics.get("manifest_sha256") or "UNHASHED")
    canvas.draw_text(24, 504, f"EVIDENCE SHA256: {sha[:64]}", text_muted, scale=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_encode_rgb_png(width, height, canvas.pixels))
    return output_path


def render_analytics_svg(
    analytics: Mapping[str, Any],
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    output_path: Path,
    *,
    title: str = "SAQA Quality Analytics",
) -> Path:
    """Render a crisp scalable SVG analytics & latency chart."""
    counts = analytics["status_counts"]
    lat = analytics["latency"]
    overall = str(analytics["overall_status"])
    badge_bg = "#22c55e" if overall == "PASS" else ("#ef4444" if overall == "FAIL" else "#f59e0b")

    norm_records = [_record_dict(r) for r in records]
    bars: list[str] = []
    timed = []
    for rec in norm_records:
        ms = rec["details"].get("elapsed_ms", rec["details"].get("duration_ms", 0.0))
        timed.append((rec["test_id"], rec["status"], float(ms) if isinstance(ms, (int, float)) else 0.0))
    top_rows = sorted(timed, key=lambda item: (-item[2], item[0]))[:10]
    max_ms = max((item[2] for item in top_rows), default=1.0) or 1.0

    for i, (test_id, status, ms) in enumerate(top_rows):
        y = 185 + i * 28
        w = max(6, round(460 * (ms / max_ms), 1))
        fill = "#22c55e" if status == "PASS" else ("#ef4444" if status == "FAIL" else "#f59e0b")
        bars.append(
            f'<text x="32" y="{y + 14}" fill="#e2e8f0" font-size="12" font-family="monospace">{html.escape(test_id[:30])}</text>'
            f'<rect x="270" y="{y}" width="460" height="18" rx="4" fill="#0f172a"/>'
            f'<rect x="270" y="{y}" width="{w}" height="18" rx="4" fill="{fill}"/>'
            f'<text x="742" y="{y + 14}" fill="#94a3b8" font-size="12" font-family="monospace">{ms:.1f} ms ({html.escape(status)})</text>'
        )

    svg_height = max(320, 215 + len(top_rows) * 28)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{svg_height}" viewBox="0 0 900 {svg_height}">
  <rect width="900" height="{svg_height}" rx="12" fill="#0f172a"/>
  <rect x="20" y="20" width="860" height="64" rx="10" fill="#1e293b" stroke="#334155"/>
  <text x="38" y="50" fill="#f8fafc" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{html.escape(title)}</text>
  <text x="38" y="70" fill="#94a3b8" font-size="12" font-family="monospace">Health: {analytics['health_score']}/100 ({html.escape(str(analytics['health_grade']))}) | Pass Rate: {analytics['pass_rate_pct']}% | P50: {lat['p50_ms']}ms | P95: {lat['p95_ms']}ms</text>
  <rect x="756" y="34" width="104" height="34" rx="17" fill="{badge_bg}"/>
  <text x="808" y="56" text-anchor="middle" fill="#0f172a" font-size="14" font-weight="700" font-family="system-ui, sans-serif">{html.escape(overall)}</text>
  <rect x="20" y="100" width="205" height="62" rx="8" fill="#1e293b" stroke="#334155"/>
  <text x="36" y="122" fill="#94a3b8" font-size="11" font-family="system-ui, sans-serif">PASS / TOTAL</text>
  <text x="36" y="148" fill="#86efac" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{counts['PASS']} / {analytics['total_records']}</text>
  <rect x="238" y="100" width="205" height="62" rx="8" fill="#1e293b" stroke="#334155"/>
  <text x="254" y="122" fill="#94a3b8" font-size="11" font-family="system-ui, sans-serif">HEALTH SCORE</text>
  <text x="254" y="148" fill="#38bdf8" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{analytics['health_score']} ({html.escape(str(analytics['health_grade']))})</text>
  <rect x="456" y="100" width="205" height="62" rx="8" fill="#1e293b" stroke="#334155"/>
  <text x="472" y="122" fill="#94a3b8" font-size="11" font-family="system-ui, sans-serif">LATENCY P95</text>
  <text x="472" y="148" fill="#f8fafc" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{lat['p95_ms']} ms</text>
  <rect x="674" y="100" width="206" height="62" rx="8" fill="#1e293b" stroke="#334155"/>
  <text x="690" y="122" fill="#94a3b8" font-size="11" font-family="system-ui, sans-serif">FAIL / BLOCKED</text>
  <text x="690" y="148" fill="#fca5a5" font-size="20" font-weight="700" font-family="system-ui, sans-serif">{counts['FAIL']} / {counts['BLOCKED']}</text>
  {''.join(bars)}
</svg>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    return output_path


def export_csv_matrix(
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    output_path: Path,
) -> Path:
    """Export executed QA evidence into an Excel-compatible UTF-8 CSV test matrix."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    norm_records = [_record_dict(r) for r in records]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "Test ID",
            "Scenario",
            "Target",
            "Status",
            "HTTP Method",
            "HTTP Status",
            "Latency (ms)",
            "Tags",
            "Checks Passed",
            "Failure Reasons",
            "Observed At",
        ])
        for rec in norm_records:
            det = rec["details"]
            writer.writerow([
                rec["test_id"],
                det.get("case_name") or rec["test_id"],
                rec["target"],
                rec["status"],
                det.get("http_method") or "GET",
                det.get("status_code", ""),
                det.get("elapsed_ms", det.get("duration_ms", "")),
                ", ".join(str(t) for t in (det.get("tags") or [])),
                "; ".join(str(c) for c in (det.get("checks_passed") or [])),
                "; ".join(str(f) for f in (det.get("failure_reasons") or [])),
                rec["observed_at"],
            ])
    return output_path


def _find_chromium_binary() -> str | None:
    candidates = [
        os.getenv("SAQA_CHROME_BIN", ""),
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        shutil.which("msedge") or "",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


def capture_web_screenshot(
    url: str,
    output_path: Path,
    *,
    width: int = 1440,
    height: int = 900,
    timeout_s: int = 30,
) -> Path | None:
    """Capture a live PNG screenshot of an authorized HTTP(S) URL via Playwright or headless Chrome/Edge."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid screenshot target URL: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("screenshot URL must not contain embedded credentials")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Try Playwright first when installed
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
                page.screenshot(path=str(output_path), full_page=False)
                if output_path.is_file() and output_path.stat().st_size > 0:
                    return output_path
            finally:
                browser.close()
    except Exception:
        pass

    # 2. Fallback to system headless Chrome / Chromium / Edge
    binary = _find_chromium_binary()
    if not binary:
        return None

    cmd = [
        binary,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        "--virtual-time-budget=5000",
        f"--screenshot={output_path.resolve()}",
        url,
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, timeout=timeout_s)
    if completed.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
        return output_path
    return None
