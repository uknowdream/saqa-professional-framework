"""Zero-dependency ISO 32000 PDF 1.4 Executive QA Report & Client UAT Sign-Off Certificate Generator (EN/ID)."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .evidence import EvidenceRecord
from .i18n import normalize_lang, translate_case_name, translate_finding_or_reason, translate_recommendation

WIB = timezone(timedelta(hours=7))


def _pdf_escape(text: str) -> str:
    """Sanitize and escape text into PDF WinAnsi/Latin-1 safe literal string."""
    safe = (
        str(text)
        .replace("—", "-")
        .replace("–", "-")
        .replace("→", "->")
        .replace("·", "|")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )
    encoded = safe.encode("latin-1", errors="replace").decode("latin-1")
    return encoded.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


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


class _PdfPageStream:
    """Helper for drawing vector rectangles, lines, and positioned text on an A4 page (595 x 842 pt)."""

    def __init__(self) -> None:
        self.ops: list[str] = []

    def rect_fill(self, x: float, y: float, w: float, h: float, rgb: tuple[float, float, float]) -> None:
        r, g, b = rgb
        self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f")

    def rect_stroke(self, x: float, y: float, w: float, h: float, rgb: tuple[float, float, float], width: float = 0.8) -> None:
        r, g, b = rgb
        self.ops.append(f"{width:.2f} w {r:.3f} {g:.3f} {b:.3f} RG {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S")

    def line(self, x1: float, y1: float, x2: float, y2: float, rgb: tuple[float, float, float], width: float = 0.6) -> None:
        r, g, b = rgb
        self.ops.append(f"{width:.2f} w {r:.3f} {g:.3f} {b:.3f} RG {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def text(
        self,
        x: float,
        y: float,
        value: str,
        *,
        font: str = "F1",
        size: float = 9.5,
        rgb: tuple[float, float, float] = (0.08, 0.12, 0.20),
    ) -> None:
        r, g, b = rgb
        self.ops.append(f"BT /{font} {size:.1f} Tf {r:.3f} {g:.3f} {b:.3f} rg {x:.1f} {y:.1f} Td ({_pdf_escape(value)}) Tj ET")

    def build(self) -> bytes:
        return "\n".join(self.ops).encode("latin-1")


def _assemble_pdf(page_streams: list[bytes]) -> bytes:
    """Assemble valid PDF 1.4 binary bytes with catalog, pages tree, 3 standard Type1 fonts, and xref table."""
    objects: list[bytes] = []

    def add_obj(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_regular = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    font_mono = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")

    pages_tree_placeholder_idx = add_obj(b"")  # Reserved for /Pages
    page_obj_ids: list[int] = []

    for stream in page_streams:
        content_id = add_obj(
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
        )
        page_dict = (
            f"<< /Type /Page /Parent {pages_tree_placeholder_idx} 0 R "
            f"/MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R /F3 {font_mono} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("latin-1")
        page_obj_ids.append(add_obj(page_dict))

    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[pages_tree_placeholder_idx - 1] = (
        f"<< /Type /Pages /Kids [{kids_str}] /Count {len(page_obj_ids)} >>".encode("latin-1")
    )
    catalog_id = add_obj(f"<< /Type /Catalog /Pages {pages_tree_placeholder_idx} 0 R >>".encode("latin-1"))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = [0]
    for idx, obj_bytes in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("latin-1"))
        out.extend(obj_bytes)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    out.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(out)


def render_pdf_report(
    analytics: Mapping[str, Any],
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    output_path: Path | None = None,
    *,
    manifest_sha256: str | None = None,
    hmac_sha256: str | None = None,
    title: str | None = None,
    lang: str = "en",
) -> bytes:
    """Render an executive multi-page A4 PDF QA report & UAT Sign-Off Certificate (EN/ID)."""
    code = normalize_lang(lang)
    norm_records = [_record_dict(r) for r in records]
    counts = analytics["status_counts"]
    lat = analytics["latency"]
    overall = str(analytics.get("overall_status", "UNVERIFIED"))
    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
    sha = manifest_sha256 or str(analytics.get("manifest_sha256") or "unhashed-in-memory")

    doc_title = title or (
        "LAPORAN EKSEKUTIF AUDIT QA & SERTIFIKAT UAT" if code == "id" else "EXECUTIVE QA AUDIT & UAT SIGN-OFF REPORT"
    )
    subtitle = (
        f"SAQA Professional Framework v{__version__}  |  Tanggal: {now_wib}  |  Bahasa: Indonesia (ID)"
        if code == "id"
        else f"SAQA Professional Framework v{__version__}  |  Generated: {now_wib}  |  Language: English (EN)"
    )

    c_navy = (0.06, 0.09, 0.16)
    c_slate = (0.38, 0.45, 0.55)
    c_border = (0.82, 0.86, 0.91)
    c_card = (0.96, 0.97, 0.99)
    c_green = (0.09, 0.64, 0.29)
    c_red = (0.86, 0.15, 0.15)
    c_amber = (0.85, 0.47, 0.02)
    badge_rgb = c_green if overall == "PASS" else (c_red if overall == "FAIL" else c_amber)

    pages: list[bytes] = []
    first = _PdfPageStream()

    # Top Navy Header Banner
    first.rect_fill(0, 760, 595, 82, c_navy)
    first.rect_fill(0, 756, 595, 4, badge_rgb)
    first.text(36, 804, doc_title[:58], font="F2", size=14.5, rgb=(1.0, 1.0, 1.0))
    first.text(36, 784, subtitle[:88], font="F1", size=8.5, rgb=(0.72, 0.78, 0.88))
    first.rect_fill(472, 782, 87, 28, badge_rgb)
    first.text(493, 792, overall[:8], font="F2", size=11.0, rgb=(1.0, 1.0, 1.0))

    # 4 KPI Cards
    kpi_items = (
        [
            ("SKOR KESEHATAN", f"{analytics['health_score']}/100 ({analytics['health_grade']})"),
            ("TINGKAT LULUS", f"{analytics['pass_rate_pct']}%"),
            ("TOTAL SKENARIO", f"{counts['PASS']} / {analytics['total_records']} PASS"),
            ("LATENSI P50 / P95", f"{lat['p50_ms']} / {lat['p95_ms']} ms"),
        ]
        if code == "id"
        else [
            ("HEALTH SCORE", f"{analytics['health_score']}/100 ({analytics['health_grade']})"),
            ("PASS RATE", f"{analytics['pass_rate_pct']}%"),
            ("SCENARIOS PASSED", f"{counts['PASS']} / {analytics['total_records']} PASS"),
            ("LATENCY P50 / P95", f"{lat['p50_ms']} / {lat['p95_ms']} ms"),
        ]
    )
    for idx, (k_lbl, k_val) in enumerate(kpi_items):
        kx = 36 + idx * 133
        first.rect_fill(kx, 686, 124, 54, c_card)
        first.rect_stroke(kx, 686, 124, 54, c_border)
        first.text(kx + 8, 724, k_lbl, font="F2", size=7.5, rgb=c_slate)
        first.text(kx + 8, 701, k_val[:18], font="F2", size=10.5, rgb=c_navy)

    # Provenance & Integrity Bar
    first.rect_fill(36, 640, 523, 36, c_card)
    first.rect_stroke(36, 640, 523, 36, c_border)
    sha_lbl = "Sidik Jari Bukti SHA-256:" if code == "id" else "Evidence SHA-256 Digest:"
    first.text(44, 661, f"{sha_lbl} {sha[:64]}", font="F3", size=7.3, rgb=c_navy)
    sig_line = (
        f"HMAC-SHA256 Signature: {hmac_sha256[:48]}..."
        if hmac_sha256
        else (
            f"Distribusi: PASS={counts['PASS']} | FAIL={counts['FAIL']} | BLOCKED={counts['BLOCKED']} | UNVERIFIED={counts['UNVERIFIED']}"
            if code == "id"
            else f"Distribution: PASS={counts['PASS']} | FAIL={counts['FAIL']} | BLOCKED={counts['BLOCKED']} | UNVERIFIED={counts['UNVERIFIED']}"
        )
    )
    first.text(44, 647, sig_line, font="F1", size=7.8, rgb=c_slate)

    # Table Header helper
    def draw_table_header(stream: _PdfPageStream, y_top: float) -> float:
        sec_title = (
            "MATRIKS EKSEKUSI PENGUJIAN OTOMATIS"
            if code == "id"
            else "AUTOMATED TEST EXECUTION MATRIX"
        )
        stream.text(36, y_top + 12, sec_title, font="F2", size=10.5, rgb=c_navy)
        hy = y_top - 14
        stream.rect_fill(36, hy, 523, 18, c_navy)
        stream.text(42, hy + 5, "#", font="F2", size=8.0, rgb=(1, 1, 1))
        stream.text(62, hy + 5, "ID UJI / SKENARIO" if code == "id" else "TEST ID / SCENARIO", font="F2", size=8.0, rgb=(1, 1, 1))
        stream.text(330, hy + 5, "TARGET", font="F2", size=8.0, rgb=(1, 1, 1))
        stream.text(452, hy + 5, "LATENSI" if code == "id" else "LATENCY", font="F2", size=8.0, rgb=(1, 1, 1))
        stream.text(508, hy + 5, "STATUS", font="F2", size=8.0, rgb=(1, 1, 1))
        return hy - 20

    curr_stream = first
    row_y = draw_table_header(curr_stream, 614)

    for idx, rec in enumerate(norm_records, start=1):
        if row_y < 145:
            # Footer page number & open new page
            pages.append(curr_stream.build())
            curr_stream = _PdfPageStream()
            curr_stream.rect_fill(0, 796, 595, 46, c_navy)
            curr_stream.text(36, 814, doc_title[:60], font="F2", size=11.0, rgb=(1, 1, 1))
            row_y = draw_table_header(curr_stream, 764)

        det = rec["details"]
        raw_case = str(det.get("case_name") or rec["test_id"])
        loc_case = translate_case_name(raw_case, code)
        ms = det.get("elapsed_ms", det.get("duration_ms", "-"))
        ms_str = f"{ms:.1f} ms" if isinstance(ms, (int, float)) else "-"
        st = rec["status"]
        st_color = c_green if st == "PASS" else (c_red if st == "FAIL" else c_amber)

        if idx % 2 == 0:
            curr_stream.rect_fill(36, row_y - 4, 523, 22, c_card)
        curr_stream.line(36, row_y - 4, 559, row_y - 4, c_border, 0.5)

        curr_stream.text(42, row_y + 7, str(idx), font="F1", size=8.0, rgb=c_navy)
        curr_stream.text(62, row_y + 9, loc_case[:48], font="F2", size=8.0, rgb=c_navy)

        failures = det.get("failure_reasons") or []
        if failures:
            sub_detail = translate_finding_or_reason(str(failures[0]), code)[:58]
        else:
            chk_cnt = len(det.get("checks_passed") or [])
            sub_detail = f"{rec['test_id'][:34]} ({chk_cnt} {'cek lulus' if code == 'id' else 'checks ok'})"
        curr_stream.text(62, row_y - 1, sub_detail, font="F1", size=7.0, rgb=c_slate)

        curr_stream.text(330, row_y + 5, rec["target"][:24], font="F3", size=7.2, rgb=c_slate)
        curr_stream.text(452, row_y + 5, ms_str, font="F3", size=7.5, rgb=c_navy)
        curr_stream.text(508, row_y + 5, st[:10], font="F2", size=8.2, rgb=st_color)
        row_y -= 24

    # Recommendations & Formal UAT Sign-Off Block at bottom of final page
    if row_y < 185:
        pages.append(curr_stream.build())
        curr_stream = _PdfPageStream()
        curr_stream.rect_fill(0, 796, 595, 46, c_navy)
        curr_stream.text(36, 814, doc_title[:60], font="F2", size=11.0, rgb=(1, 1, 1))
        row_y = 760

    rec_y = row_y - 10
    curr_stream.text(
        36,
        rec_y,
        "REKOMENDASI & KESIMPULAN AUDIT" if code == "id" else "RECOMMENDATIONS & AUDIT CONCLUSION",
        font="F2",
        size=9.5,
        rgb=c_navy,
    )
    rec_y -= 14
    for r_item in list(analytics.get("recommendations") or [])[:3]:
        curr_stream.text(44, rec_y, "- " + translate_recommendation(str(r_item), code)[:86], font="F1", size=8.0, rgb=c_slate)
        rec_y -= 12

    # Sign-off signature boxes
    sign_y = 52
    curr_stream.rect_stroke(36, sign_y, 250, 68, c_border)
    curr_stream.rect_stroke(309, sign_y, 250, 68, c_border)
    curr_stream.text(
        46,
        sign_y + 52,
        "Disiapkan & Diverifikasi Otomatis Oleh:" if code == "id" else "Automated QA Verification By:",
        font="F2",
        size=8.0,
        rgb=c_navy,
    )
    curr_stream.text(46, sign_y + 36, f"SAQA Engine v{__version__} (Fail-Closed Gate)", font="F1", size=8.0, rgb=c_slate)
    curr_stream.text(46, sign_y + 12, f"Status: {overall}  |  {now_wib}", font="F2", size=8.0, rgb=badge_rgb)

    curr_stream.text(
        319,
        sign_y + 52,
        "Persetujuan Klien / QA Lead (UAT Sign-Off):" if code == "id" else "Client / QA Lead Approval (UAT Sign-Off):",
        font="F2",
        size=8.0,
        rgb=c_navy,
    )
    curr_stream.line(319, sign_y + 20, 545, sign_y + 20, c_border, 0.7)
    curr_stream.text(
        319,
        sign_y + 8,
        "Nama, Tanda Tangan & Tanggal" if code == "id" else "Name, Signature & Date",
        font="F1",
        size=7.5,
        rgb=c_slate,
    )

    pages.append(curr_stream.build())
    pdf_bytes = _assemble_pdf(pages)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)
    return pdf_bytes
