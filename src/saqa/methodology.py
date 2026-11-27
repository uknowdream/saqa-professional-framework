"""Agile (Scrum/Kanban) & Waterfall (V-Model Stage-Gate) QA Governance, RTM & Release Sign-Off Engine (EN/ID).

Provides dual-methodology QA control-plane semantics for Jira Cloud and executive PDF/CSV/Markdown
documentation:
- Agile Mode: Sprint iterations, Definition of Done (DoD) automated checklist, dynamic Story Points,
  Defect Severity/SLA matrix (P0..P3), and Scrum Sprint sync.
- Waterfall Mode: Strict sequential non-overlapping V-Model Stage Gates (Stage 1 SIT -> Stage 2
  Security & Compliance -> Stage 3 UAT & Go/No-Go Sign-Off), Formal Requirement Traceability Matrix
  (RTM), and Go/No-Go Release Certificate (BAST).
"""
from __future__ import annotations

import csv
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .evidence import EvidenceRecord
from .i18n import normalize_lang, translate_case_name

SUPPORTED_METHODOLOGIES = ("agile", "waterfall")
WIB = timezone(timedelta(hours=7))

WATERFALL_EPIC_TEXT_I18N: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "PHASE-1": {
            "summary": "SAQA Waterfall | Stage 1 — Test Plan, Requirements Baseline & SIT",
            "description": "Sequential Waterfall Stage 1 covering Test Plan Governance (QA-1), System Integration Testing E2E (QA-2), and Environment Compatibility Matrix (QA-3). Must pass Exit Gate before Stage 2.",
        },
        "PHASE-2": {
            "summary": "SAQA Waterfall | Stage 2 — API Contract, Security & Compliance Gate",
            "description": "Sequential Waterfall Stage 2 covering API/Schema Verification (QA-4), Security & Penetration Readiness (QA-5), and WCAG Accessibility Compliance (QA-6). Must pass Exit Gate before Stage 3.",
        },
        "PHASE-3": {
            "summary": "SAQA Waterfall | Stage 3 — Performance Stress, UAT & Go/No-Go Sign-Off",
            "description": "Sequential Waterfall Stage 3 covering Performance SLA Stress Testing (QA-7), Requirement Traceability & Evidence Archive (QA-8), and Final Go/No-Go Production Sign-Off (QA-9).",
        },
    },
    "id": {
        "PHASE-1": {
            "summary": "SAQA Waterfall | Tahap 1 — Rencana Uji, Baseline Kebutuhan & SIT",
            "description": "Tahap 1 Waterfall sekuensial mencakup Tata Kelola Rencana Uji (QA-1), Pengujian Integrasi Sistem E2E (QA-2), dan Matriks Kompatibilitas Perangkat (QA-3). Wajib lulus Exit Gate sebelum Tahap 2.",
        },
        "PHASE-2": {
            "summary": "SAQA Waterfall | Tahap 2 — Verifikasi API, Keamanan Siber & Kepatuhan",
            "description": "Tahap 2 Waterfall sekuensial mencakup Validasi Kontrak API (QA-4), Kesiapan Keamanan & Proteksi Celah (QA-5), dan Kepatuhan Aksesibilitas WCAG (QA-6). Wajib lulus Exit Gate sebelum Tahap 3.",
        },
        "PHASE-3": {
            "summary": "SAQA Waterfall | Tahap 3 — Uji Beban, UAT & Persetujuan Go/No-Go (BAST)",
            "description": "Tahap 3 Waterfall sekuensial mencakup Uji Beban & Performa SLA (QA-7), Matriks Ketertelusuran Kebutuhan RTM & Arsip Bukti (QA-8), serta Keputusan Akhir Go/No-Go Produksi (QA-9).",
        },
    },
}

# Canonical Requirement Catalog mapped automatically from SAQA test IDs & tags
DEFAULT_REQUIREMENTS: tuple[dict[str, Any], ...] = (
    {
        "req_id": "REQ-SEC-01",
        "domain": "QA-5",
        "title_en": "Transport Security (TLS 1.2+/1.3) & Certificate Validity",
        "title_id": "Keamanan Transpor (TLS 1.2+/1.3) & Masa Berlaku Sertifikat",
        "match_prefixes": ("pillar-1.", "mobile-2."),
        "match_tags": ("tls",),
        "severity": "P0-Blocker",
    },
    {
        "req_id": "REQ-SEC-02",
        "domain": "QA-5",
        "title_en": "OWASP Headers, CORS, SRI, Dotfile Protection & Secret Hygiene",
        "title_id": "Header OWASP, CORS, SRI, Proteksi File Sensitif & Bebas Kredensial Tertanam",
        "match_prefixes": ("pillar-2.", "pillar-6.", "pillar-9.", "mobile-1.", "mobile-4."),
        "match_tags": ("security", "headers", "cors", "sri"),
        "severity": "P0-Blocker",
    },
    {
        "req_id": "REQ-A11Y-01",
        "domain": "QA-6",
        "title_en": "WCAG 2.2 Accessibility, Contrast, Semantic Landmarks & Privacy",
        "title_id": "Aksesibilitas WCAG 2.2, Kontras Warna, Semantik DOM & Kepatuhan Privasi",
        "match_prefixes": ("pillar-3.", "mobile-3."),
        "match_tags": ("a11y", "accessibility"),
        "severity": "P1-Critical",
    },
    {
        "req_id": "REQ-API-01",
        "domain": "QA-4",
        "title_en": "API Contract, OpenAPI Schema, SEO Structured Data & Discoverability",
        "title_id": "Kontrak API, Skema OpenAPI, Data Terstruktur SEO & Keterlacakan Endpoint",
        "match_prefixes": ("pillar-4.",),
        "match_tags": ("api", "contract", "seo", "graphql"),
        "severity": "P1-Critical",
    },
    {
        "req_id": "REQ-WEB-01",
        "domain": "QA-2",
        "title_en": "Web/SPA Functional E2E, Multi-Page Navigation & Zero Broken Assets",
        "title_id": "Fungsional E2E Web/SPA, Navigasi Multi-Halaman & Nol Aset Rusak",
        "match_prefixes": ("pillar-5.", "pillar-8.", "multi-page."),
        "match_tags": ("web", "smoke", "crawl", "journey"),
        "severity": "P1-Critical",
    },
    {
        "req_id": "REQ-MOB-01",
        "domain": "QA-3",
        "title_en": "Responsive Multi-Viewport Layout (Desktop/Tablet/Mobile) & Native Readiness",
        "title_id": "Tata Letak Responsif Multi-Layar (Desktop/Tablet/Mobile) & Kesiapan Mobile",
        "match_prefixes": ("responsive.", "mobile-5."),
        "match_tags": ("responsive", "mobile", "browser"),
        "severity": "P2-Major",
    },
    {
        "req_id": "REQ-PERF-01",
        "domain": "QA-7",
        "title_en": "Response Latency SLA, Core Web Vitals (FCP/LCP/CLS) & Concurrent Load",
        "title_id": "SLA Latensi Respons, Core Web Vitals (FCP/LCP/CLS) & Ketahanan Beban Konkuren",
        "match_prefixes": ("pillar-7.", "load-test."),
        "match_tags": ("performance",),
        "severity": "P1-Critical",
    },
)


def normalize_methodology(methodology: str | None = None) -> str:
    """Resolve methodology mode ('agile' or 'waterfall'), defaulting to SAQA_METHODOLOGY env or 'agile'."""
    raw = (methodology or os.getenv("SAQA_METHODOLOGY") or "agile").strip().lower()
    if raw in {"agile", "scrum", "kanban"}:
        return "agile"
    if raw in {"waterfall", "v-model", "vmodel", "sequential", "stage-gate"}:
        return "waterfall"
    raise ValueError(f"Unsupported methodology {methodology!r}; choose 'agile' or 'waterfall'")


def classify_defect_severity(domain_key: str, records: Sequence[Mapping[str, Any]], *, lang: str = "en") -> dict[str, Any]:
    """Classify defect severity, Jira priority, Story Points, and remediation SLA."""
    code = normalize_lang(lang)
    failed = [r for r in records if r.get("status") == "FAIL"]
    fail_count = len(failed)
    if domain_key in {"QA-5", "QA-8", "QA-9"} or any("CRITICAL" in str(r.get("details", {})) for r in failed):
        return {
            "severity": "P0-Blocker",
            "priority": "Highest",
            "story_points": 5 if fail_count <= 2 else 8,
            "sla": "4 Jam (Hotfix Segera)" if code == "id" else "4 Hours (Immediate Hotfix)",
        }
    if domain_key in {"QA-2", "QA-4", "QA-7"}:
        return {
            "severity": "P1-Critical",
            "priority": "High",
            "story_points": 3 if fail_count <= 2 else 5,
            "sla": "24 Jam (Wajib Selesai Sebelum Rilis)" if code == "id" else "24 Hours (Release Blocker)",
        }
    if domain_key in {"QA-3", "QA-6"}:
        return {
            "severity": "P2-Major",
            "priority": "Medium",
            "story_points": 2 if fail_count <= 2 else 3,
            "sla": "3 Hari Kerja" if code == "id" else "3 Business Days",
        }
    return {
        "severity": "P3-Minor",
        "priority": "Low",
        "story_points": 1,
        "sla": "Sprint Berikutnya" if code == "id" else "Next Sprint",
    }


def compute_waterfall_timeline_window(
    *,
    today: datetime,
    sprint_start: str | None = None,
    sprint_end: str | None = None,
) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """Compute strict sequential, non-overlapping Waterfall V-Model stage dates for Jira Timeline Gantt."""
    if sprint_start and sprint_end:
        s_dt = datetime.strptime(sprint_start, "%Y-%m-%d").replace(tzinfo=WIB)
        e_dt = datetime.strptime(sprint_end, "%Y-%m-%d").replace(tzinfo=WIB)
        if s_dt > e_dt:
            raise ValueError("sprint_start must not be after sprint_end")
    else:
        s_dt = today - timedelta(days=21)
        e_dt = today + timedelta(days=9)

    total_days = max(6, (e_dt - s_dt).days)
    s1_end = s_dt + timedelta(days=max(1, total_days // 3))
    s2_start = min(e_dt, s1_end + timedelta(days=1))
    s2_end = min(e_dt, s_dt + timedelta(days=max(2, (total_days * 2) // 3)))
    if s2_end < s2_start:
        s2_end = s2_start
    s3_start = min(e_dt, s2_end + timedelta(days=1))

    epic_dates = {
        "PHASE-1": (s_dt.strftime("%Y-%m-%d"), s1_end.strftime("%Y-%m-%d")),
        "PHASE-2": (s2_start.strftime("%Y-%m-%d"), s2_end.strftime("%Y-%m-%d")),
        "PHASE-3": (s3_start.strftime("%Y-%m-%d"), e_dt.strftime("%Y-%m-%d")),
    }

    def _split_stage(start_d: datetime, end_d: datetime, keys: tuple[str, str, str]) -> dict[str, tuple[str, str]]:
        span = max(0, (end_d - start_d).days)
        out: dict[str, tuple[str, str]] = {}
        for idx, k in enumerate(keys):
            k_s = start_d + timedelta(days=round(span * (idx / 3)))
            k_e = start_d + timedelta(days=round(span * ((idx + 1) / 3)))
            if k_e < k_s:
                k_e = k_s
            out[k] = (k_s.strftime("%Y-%m-%d"), min(end_d, k_e).strftime("%Y-%m-%d"))
        return out

    domain_dates: dict[str, tuple[str, str]] = {}
    domain_dates.update(_split_stage(s_dt, s1_end, ("QA-1", "QA-2", "QA-3")))
    domain_dates.update(_split_stage(s2_start, s2_end, ("QA-4", "QA-5", "QA-6")))
    domain_dates.update(_split_stage(s3_start, e_dt, ("QA-7", "QA-8", "QA-9")))
    return epic_dates, domain_dates


def build_rtm_matrix(
    records: Sequence[EvidenceRecord | Mapping[str, Any]],
    *,
    manifest_sha256: str | None = None,
    custom_requirements: Sequence[Mapping[str, Any]] | None = None,
    lang: str = "en",
) -> list[dict[str, Any]]:
    """Build a formal Requirement Traceability Matrix (RTM) mapping Requirements <-> Test Cases <-> Jira Domains."""
    code = normalize_lang(lang)
    catalog = list(custom_requirements) if custom_requirements else list(DEFAULT_REQUIREMENTS)
    norm_recs: list[dict[str, Any]] = []
    for item in records:
        if isinstance(item, EvidenceRecord):
            norm_recs.append({
                "test_id": item.test_id,
                "status": item.status,
                "target": item.target,
                "details": dict(item.details),
            })
        else:
            norm_recs.append({
                "test_id": str(item["test_id"]),
                "status": str(item["status"]),
                "target": str(item["target"]),
                "details": dict(item.get("details") or {}),
            })

    rows: list[dict[str, Any]] = []
    for req in catalog:
        req_id = str(req["req_id"])
        title = str(req.get(f"title_{code}") or req.get("title_en") or req.get("title") or req_id)
        prefixes = tuple(str(p) for p in (req.get("match_prefixes") or ()))
        tags = {str(t).lower() for t in (req.get("match_tags") or ())}

        matched = [
            r for r in norm_recs
            if any(r["test_id"].startswith(pref) for pref in prefixes)
            or bool(tags & {str(t).lower() for t in (r["details"].get("tags") or [])})
        ]
        if not matched:
            status = "NOT_TESTED"
        elif any(r["status"] == "FAIL" for r in matched):
            status = "FAIL"
        elif any(r["status"] == "BLOCKED" for r in matched):
            status = "BLOCKED"
        elif all(r["status"] in {"PASS", "NOT_APPLICABLE"} for r in matched):
            status = "PASS"
        else:
            status = "UNVERIFIED"

        rows.append({
            "req_id": req_id,
            "requirement": title,
            "jira_domain": str(req.get("domain") or "QA-1"),
            "severity": str(req.get("severity") or "P1-Critical"),
            "test_count": len(matched),
            "test_ids": [r["test_id"] for r in matched],
            "scenarios": [translate_case_name(str(r["details"].get("case_name") or r["test_id"]), code) for r in matched],
            "status": status,
            "evidence_sha256": (manifest_sha256 or "in-memory")[:16],
        })
    return rows


def evaluate_methodology_governance(
    domain_statuses: Mapping[str, str],
    analytics: Mapping[str, Any],
    *,
    methodology: str = "agile",
    lang: str = "en",
) -> dict[str, Any]:
    """Evaluate Agile Definition-of-Done (DoD) or Waterfall Sequential Stage-Gate Go/No-Go Sign-Off."""
    meth = normalize_methodology(methodology)
    code = normalize_lang(lang)

    def _stage_ok(keys: tuple[str, ...]) -> bool:
        return all(domain_statuses.get(k, "UNVERIFIED") == "PASS" for k in keys)

    s1_ok = _stage_ok(("QA-1", "QA-2", "QA-3"))
    s2_ok = _stage_ok(("QA-4", "QA-5", "QA-6"))
    s3_ok = _stage_ok(("QA-7", "QA-8", "QA-9"))
    all_ok = s1_ok and s2_ok and s3_ok

    if meth == "waterfall":
        stage_gates = [
            {
                "stage": "STAGE-1",
                "name": "Tahap 1 — Exit Gate Rencana Uji & SIT" if code == "id" else "Stage 1 — Test Plan & SIT Exit Gate",
                "status": "PASS" if s1_ok else "FAIL",
                "domains": ["QA-1", "QA-2", "QA-3"],
            },
            {
                "stage": "STAGE-2",
                "name": "Tahap 2 — Exit Gate API, Keamanan & Kepatuhan" if code == "id" else "Stage 2 — API, Security & Compliance Exit Gate",
                "status": ("PASS" if s2_ok else "FAIL") if s1_ok else "BLOCKED",
                "domains": ["QA-4", "QA-5", "QA-6"],
            },
            {
                "stage": "STAGE-3",
                "name": "Tahap 3 — UAT & Keputusan Go/No-Go Produksi (BAST)" if code == "id" else "Stage 3 — Performance, UAT & Production Go/No-Go Gate",
                "status": ("PASS" if s3_ok else "FAIL") if (s1_ok and s2_ok) else "BLOCKED",
                "domains": ["QA-7", "QA-8", "QA-9"],
            },
        ]
        decision = (
            ("GO — LAYAK RILIS PRODUKSI" if code == "id" else "GO — APPROVED FOR PRODUCTION")
            if all_ok
            else ("NO-GO — DITAHAN OLEH GERBANG TAHAP" if code == "id" else "NO-GO — BLOCKED BY STAGE GATE")
        )
        return {
            "methodology": "waterfall",
            "decision": decision,
            "approved": all_ok,
            "stage_gates": stage_gates,
            "checklist": [
                {"item": sg["name"], "passed": sg["status"] == "PASS", "status": sg["status"]}
                for sg in stage_gates
            ],
        }

    # Agile Mode: Objective Definition of Done (DoD) Checklist
    dod_items = [
        (
            "Fungsional Web/App & E2E Lulus (QA-2)" if code == "id" else "Functional Web/App E2E Verified (QA-2)",
            domain_statuses.get("QA-2") == "PASS",
        ),
        (
            "Kompatibilitas Multi-Layar & Browser Lulus (QA-3)" if code == "id" else "Cross-Browser & Responsive Matrix Verified (QA-3)",
            domain_statuses.get("QA-3") == "PASS",
        ),
        (
            "Kontrak API & Skema Terverifikasi (QA-4)" if code == "id" else "API & Schema Contracts Verified (QA-4)",
            domain_statuses.get("QA-4") == "PASS",
        ),
        (
            "Gerbang Keamanan Siber Nol Celah Kritis (QA-5)" if code == "id" else "Zero Critical Security Findings (QA-5)",
            domain_statuses.get("QA-5") == "PASS",
        ),
        (
            "Kepatuhan Aksesibilitas WCAG 2.2 (QA-6)" if code == "id" else "WCAG 2.2 Accessibility Readiness (QA-6)",
            domain_statuses.get("QA-6") == "PASS",
        ),
        (
            "SLA Performa & Bukti Kriptografi SHA-256 Utuh (QA-7/QA-8)" if code == "id" else "Performance SLA & Cryptographic Evidence Intact (QA-7/QA-8)",
            domain_statuses.get("QA-7") == "PASS" and domain_statuses.get("QA-8") == "PASS",
        ),
    ]
    decision = (
        ("DOD TERPENUHI — SIAP RILIS SPRINT" if code == "id" else "DOD SATISFIED — READY TO SHIP SPRINT")
        if all_ok
        else ("DOD BELUM TERPENUHI — PERLU PERBAIKAN" if code == "id" else "DOD NOT MET — ACTION REQUIRED")
    )
    return {
        "methodology": "agile",
        "decision": decision,
        "approved": all_ok,
        "health_score": analytics.get("health_score"),
        "checklist": [
            {"item": lbl, "passed": ok, "status": "PASS" if ok else "FAIL"}
            for lbl, ok in dod_items
        ],
    }


def export_rtm_csv(rtm_rows: Sequence[Mapping[str, Any]], output_path: Path, *, lang: str = "en") -> Path:
    """Export formal Requirement Traceability Matrix (RTM) to UTF-8 BOM Excel-ready CSV."""
    code = normalize_lang(lang)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = (
        ["ID Kebutuhan", "Deskripsi Kebutuhan", "Domain Jira", "Tingkat Keparahan", "Jumlah Uji", "Daftar ID Uji", "Status", "Bukti SHA-256"]
        if code == "id"
        else ["Requirement ID", "Requirement Description", "Jira Domain", "Severity", "Test Count", "Mapped Test IDs", "Status", "Evidence SHA-256"]
    )
    with output_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for row in rtm_rows:
            writer.writerow([
                row["req_id"],
                row["requirement"],
                row["jira_domain"],
                row["severity"],
                row["test_count"],
                ", ".join(row.get("test_ids") or []),
                row["status"],
                row["evidence_sha256"],
            ])
    return output_path


def render_release_signoff_markdown(
    governance: Mapping[str, Any],
    rtm_rows: Sequence[Mapping[str, Any]],
    analytics: Mapping[str, Any],
    *,
    suite_name: str,
    manifest_sha256: str | None = None,
    lang: str = "en",
) -> str:
    """Render formal Agile DoD / Waterfall Go-No-Go Release Closure & RTM Sign-Off Document (Markdown)."""
    code = normalize_lang(lang)
    meth = str(governance.get("methodology", "agile")).upper()
    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
    title = (
        f"# Berita Acara Sertifikasi Rilis & Matriks RTM ({meth}) — {suite_name}"
        if code == "id"
        else f"# Release Sign-Off Certificate & RTM ({meth}) — {suite_name}"
    )
    lines = [
        title,
        "",
        f"- **{'Metodologi SDLC' if code == 'id' else 'SDLC Methodology'}:** `{meth}`",
        f"- **{'Keputusan Rilis' if code == 'id' else 'Release Decision'}:** **`{governance['decision']}`**",
        f"- **{'Skor Kesehatan' if code == 'id' else 'Health Score'}:** `{analytics['health_score']}/100 ({analytics['health_grade']})`",
        f"- **{'Waktu Verifikasi' if code == 'id' else 'Verified At'}:** `{now_wib}`",
        f"- **Evidence SHA-256:** `{manifest_sha256 or 'in-memory'}`",
        "",
        f"## 1. {'Daftar Periksa Tata Kelola' if code == 'id' else 'Governance Gate Checklist'} ({meth})",
        "",
    ]
    for item in governance.get("checklist", []):
        mark = "x" if item["passed"] else " "
        lines.append(f"- [{mark}] **{item['status']}** — {item['item']}")

    lines.extend([
        "",
        f"## 2. {'Matriks Ketertelusuran Kebutuhan (RTM)' if code == 'id' else 'Requirement Traceability Matrix (RTM)'}",
        "",
        f"| {'ID Kebutuhan' if code == 'id' else 'Req ID'} | {'Kebutuhan' if code == 'id' else 'Requirement'} | Jira | {'Keparahan' if code == 'id' else 'Severity'} | {'Uji' if code == 'id' else 'Tests'} | Status |",
        "|---|---|---|---|---|---|",
    ])
    for row in rtm_rows:
        lines.append(
            f"| `{row['req_id']}` | {row['requirement']} | `{row['jira_domain']}` | `{row['severity']}` | {row['test_count']} | `{row['status']}` |"
        )
    return "\n".join(lines) + "\n"
