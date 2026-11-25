"""Bilingual localization engine (English 'en' & Bahasa Indonesia 'id') for Jira & QA Reports."""
from __future__ import annotations

import os
from typing import Any

SUPPORTED_LANGUAGES = ("en", "id")

ISSUE_SUMMARIES_I18N: dict[str, dict[str, str]] = {
    "en": {
        "QA-1": "SAQA | Test Management Foundation",
        "QA-2": "SAQA | Web E2E Automation",
        "QA-3": "SAQA | Cross-Browser Matrix",
        "QA-4": "SAQA | API Quality Gate",
        "QA-5": "SAQA | Security Regression Gate",
        "QA-6": "SAQA | Accessibility Gate",
        "QA-7": "SAQA | Performance Quality Gate",
        "QA-8": "SAQA | Evidence & Allure Traceability",
        "QA-9": "SAQA | Certification Readiness",
    },
    "id": {
        "QA-1": "SAQA | Fondasi Manajemen Pengujian",
        "QA-2": "SAQA | Otomasi E2E Web & Aplikasi",
        "QA-3": "SAQA | Matriks Lintas Browser & Perangkat",
        "QA-4": "SAQA | Gerbang Kualitas Kontrak API",
        "QA-5": "SAQA | Gerbang Regresi Keamanan",
        "QA-6": "SAQA | Gerbang Aksesibilitas WCAG",
        "QA-7": "SAQA | Gerbang Kualitas Performa & SLA",
        "QA-8": "SAQA | Ketertelusuran Bukti & Allure",
        "QA-9": "SAQA | Kesiapan Sertifikasi Rilis",
    },
}

DOMAIN_DESCRIPTIONS_I18N: dict[str, dict[str, str]] = {
    "en": {
        "QA-1": "Master QA control-plane governance, declarative suite orchestration, test inventory, and release readiness.",
        "QA-2": "End-to-end Web & Mobile-Web functional verification, multi-page crawling, TLS redirects, DOM integrity, and user journeys.",
        "QA-3": "Cross-browser & multi-viewport responsive compatibility matrix across Desktop, Tablet, Mobile, and PWA/App-Link assets.",
        "QA-4": "REST/GraphQL API & OpenAPI contract validation, JSON schema enforcement, XML/RSS feed integrity, and status gates.",
        "QA-5": "Application security regression gate: TLS, OWASP headers, CORS, SRI, security.txt, dotfile exposure, and safe target scope.",
        "QA-6": "Web & mobile accessibility readiness (WCAG 2.2 semantic landmarks, HTML lang, headings, tap targets, and ARIA labels).",
        "QA-7": "Performance, Core Web Vitals (FCP/LCP/CLS), & SLA latency quality gate across P50, P90, P95, P99, and asset budgets.",
        "QA-8": "Cryptographic SHA-256 evidence manifest verification, JUnit/SARIF exports, visual diffs, and tamper-evident provenance.",
        "QA-9": "Final fail-closed release certification gate aggregating all mandatory quality engineering domains and governance waivers.",
    },
    "id": {
        "QA-1": "Tata kelola pusat kendali QA, orkestrasi suite deklaratif, inventaris pengujian, dan kesiapan rilis produksi.",
        "QA-2": "Verifikasi fungsional E2E Web & Aplikasi Klien, perayapan multi-halaman, pengalihan TLS, integritas DOM, dan alur pengguna.",
        "QA-3": "Matriks kompatibilitas responsif lintas browser & ukuran layar (Desktop, Tablet, Mobile) serta aset PWA/Universal Links.",
        "QA-4": "Validasi kontrak REST/GraphQL API & OpenAPI, penegakan skema JSON, integritas feed XML/RSS, dan gerbang status HTTP.",
        "QA-5": "Gerbang regresi keamanan aplikasi: TLS, Header OWASP, CORS, SRI, security.txt, proteksi file sensitif, dan cakupan aman.",
        "QA-6": "Kesiapan aksesibilitas Web & Aplikasi (standar WCAG 2.2, atribut lang, hierarki heading, ukuran tombol sentuh, dan label ARIA).",
        "QA-7": "Gerbang kualitas performa, Core Web Vitals (FCP/LCP/CLS), & latensi SLA pada P50, P90, P95, P99, serta batas ukuran aset.",
        "QA-8": "Verifikasi manifes bukti kriptografi SHA-256, ekspor JUnit/SARIF, regresi visual piksel, dan ketertelusuran audit.",
        "QA-9": "Gerbang sertifikasi rilis akhir (fail-closed) yang menggabungkan seluruh domain kualitas wajib dan persetujuan risiko.",
    },
}

EPIC_TEXT_I18N: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "PHASE-1": {
            "summary": "SAQA Epic | Phase 1 — Core Foundation, Web & Cross-Browser QE",
            "description": "Phase 1 QA Roadmap covering Test Management Governance (QA-1), Web E2E Automation (QA-2), and Cross-Browser Matrix (QA-3).",
        },
        "PHASE-2": {
            "summary": "SAQA Epic | Phase 2 — API Contract, Security & Accessibility Gates",
            "description": "Phase 2 QA Roadmap covering API & Manifest Contract Validation (QA-4), Security Headers & Regression Gate (QA-5), and Accessibility Gate (QA-6).",
        },
        "PHASE-3": {
            "summary": "SAQA Epic | Phase 3 — Performance, Evidence Traceability & Release Certification",
            "description": "Phase 3 QA Roadmap covering Performance Latency SLAs (QA-7), SHA-256 Evidence Traceability (QA-8), and Final Release Certification (QA-9).",
        },
    },
    "id": {
        "PHASE-1": {
            "summary": "SAQA Epic | Fase 1 — Fondasi Inti, Otomasi Web & Matriks Lintas Perangkat",
            "description": "Peta Jalan QA Fase 1 mencakup Tata Kelola Manajemen Pengujian (QA-1), Otomasi E2E Web/Aplikasi (QA-2), dan Matriks Lintas Browser/Perangkat (QA-3).",
        },
        "PHASE-2": {
            "summary": "SAQA Epic | Fase 2 — Kontrak API, Keamanan Siber & Aksesibilitas",
            "description": "Peta Jalan QA Fase 2 mencakup Validasi Kontrak API & Manifes (QA-4), Gerbang Regresi Keamanan (QA-5), dan Gerbang Aksesibilitas WCAG (QA-6).",
        },
        "PHASE-3": {
            "summary": "SAQA Epic | Fase 3 — Performa SLA, Bukti Kriptografi & Sertifikasi Rilis",
            "description": "Peta Jalan QA Fase 3 mencakup Performa & Latensi SLA (QA-7), Ketertelusuran Bukti SHA-256 (QA-8), dan Sertifikasi Rilis Akhir (QA-9).",
        },
    },
}

UI_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "health_grade": "Health Grade",
        "metric_gov_field": "Metric / Governance Field",
        "observed_value": "Observed Value",
        "metric_sla_bench": "Metric / SLA Benchmark",
        "suite_name": "QA Suite Name",
        "domain_gate_status": "Domain Gate Status",
        "target_endpoints": "Target Endpoint(s)",
        "suite_health_score": "Suite Health Score",
        "timeline_schedule": "Timeline Schedule",
        "suite_pass_rate": "Suite Pass Rate",
        "parent_epic": "Parent Roadmap Epic",
        "latency_min_p50_mean": "Latency (Min / P50 / Mean)",
        "executed_at": "Executed At (WIB / UTC)",
        "latency_p95_p99_max": "Latency (P95 / P99 / Max)",
        "evidence_sha": "Evidence SHA-256 Digest",
        "framework_engine": "Framework Engine",
        "active_sprint": "Active Jira Sprint",
        "report_language": "Client Language",
        "sec_1_exec": "1. Executive Quality & Governance Summary",
        "sec_2_matrix": "2. Automated Test Execution Matrix ({count} Scenarios)",
        "sec_3_findings": "3. Audit Findings, Evidence & Recommendations",
        "col_test_id": "Test ID",
        "col_scenario": "Scenario & Quality Check",
        "col_target": "Target",
        "col_http": "HTTP",
        "col_latency": "Latency",
        "col_assertions": "Verified Assertions",
        "col_status": "Status",
        "attached_files": "Attached Audit Reports & Evidence Artifacts: ",
        "all_gates_ok": "All quality gates satisfied.",
        "waiver_applied": "Governance Risk Waiver Active in Jira (labels: {labels}) — failure suppressed per QA Lead approval.",
        "auto_recovery_title": "Automated Verification Recovery ({domain})  ",
        "auto_recovery_body": "Automatically resolved because {domain} passed fresh SAQA verification (suite={suite}, digest={digest}).",
        "auto_bug_prefix": "[SAQA-AUTO] {suite} failure in {domain} ({target})",
        "auto_bug_desc": "Automated failure detected in {domain} for suite {suite} ({target}). Evidence SHA-256: {sha}",
        "timeline_window": "Timeline Window: ",
        "covered_domains": " | Covered Domains: ",
        "bootstrap_desc": "SAQA automated control-plane item for {key} ({summary}).",
        "lang_label": "English (EN)",
        # Reporting strings
        "rpt_overall_status": "Overall Status",
        "rpt_health_score": "Health Score",
        "rpt_pass_rate": "Pass Rate",
        "rpt_summary_metrics": "Summary Metrics",
        "rpt_metric": "Metric",
        "rpt_value": "Value",
        "rpt_total_records": "Total Records",
        "rpt_applicable_records": "Applicable Records",
        "rpt_fail_rate": "Fail Rate",
        "rpt_failing_tests": "Failing Tests",
        "rpt_reasons": "Reasons",
        "rpt_slowest_tests": "Slowest Tests",
        "rpt_recommendations": "Actionable QA Recommendations",
        "rpt_status_dist": "Status Distribution",
        "rpt_executed_evidence": "Executed Test Evidence",
        "rpt_checks_executed": "Checks Executed",
        "rpt_search_placeholder": "Filter by test ID, target, or error...",
        "rpt_all": "All",
        "rpt_details_json": "Details JSON",
        "rpt_checks_details": "Checks & Details",
    },
    "id": {
        "health_grade": "Predikat Kesehatan",
        "metric_gov_field": "Metrik / Bidang Tata Kelola",
        "observed_value": "Nilai Terukur",
        "metric_sla_bench": "Metrik / Tolok Ukur SLA",
        "suite_name": "Nama Suite QA",
        "domain_gate_status": "Status Gerbang Domain",
        "target_endpoints": "Target Pengujian (Web/App)",
        "suite_health_score": "Skor Kesehatan Kualitas",
        "timeline_schedule": "Jadwal Linimasa Sprint",
        "suite_pass_rate": "Tingkat Kelulusan Suite",
        "parent_epic": "Induk Epic Roadmap",
        "latency_min_p50_mean": "Latensi (Min / P50 / Rata-rata)",
        "executed_at": "Waktu Eksekusi (WIB / UTC)",
        "latency_p95_p99_max": "Latensi (P95 / P99 / Maks)",
        "evidence_sha": "Sidik Jari Bukti SHA-256",
        "framework_engine": "Mesin Otomasi QA",
        "active_sprint": "Sprint Jira Aktif",
        "report_language": "Bahasa Laporan Klien",
        "sec_1_exec": "1. Ringkasan Eksekutif Kualitas & Tata Kelola",
        "sec_2_matrix": "2. Matriks Eksekusi Pengujian Otomatis ({count} Skenario)",
        "sec_3_findings": "3. Temuan Audit, Bukti & Rekomendasi Perbaikan",
        "col_test_id": "ID Uji",
        "col_scenario": "Skenario & Pemeriksaan Kualitas",
        "col_target": "Target",
        "col_http": "HTTP",
        "col_latency": "Latensi",
        "col_assertions": "Asersi Terverifikasi",
        "col_status": "Status",
        "attached_files": "Lampiran Dokumen Laporan & Bukti Visual Audit: ",
        "all_gates_ok": "Seluruh gerbang kualitas terpenuhi tanpa kendala.",
        "waiver_applied": "Pengecualian Risiko (Waiver) Aktif di Jira (label: {labels}) — kegagalan ditekan sesuai persetujuan QA Lead.",
        "auto_recovery_title": "Pemulihan Verifikasi Otomatis ({domain})  ",
        "auto_recovery_body": "Ditutup otomatis karena domain {domain} telah lulus verifikasi ulang SAQA (suite={suite}, digest={digest}).",
        "auto_bug_prefix": "[SAQA-AUTO] Kegagalan {suite} pada {domain} ({target})",
        "auto_bug_desc": "Kegagalan otomatis terdeteksi pada domain {domain} untuk suite {suite} ({target}). Bukti SHA-256: {sha}",
        "timeline_window": "Rentang Linimasa: ",
        "covered_domains": " | Cakupan Domain: ",
        "bootstrap_desc": "Item kendali otomasi SAQA untuk {key} ({summary}).",
        "lang_label": "Bahasa Indonesia (ID)",
        # Reporting strings
        "rpt_overall_status": "Status Keseluruhan",
        "rpt_health_score": "Skor Kesehatan",
        "rpt_pass_rate": "Tingkat Kelulusan",
        "rpt_summary_metrics": "Ringkasan Metrik Kualitas",
        "rpt_metric": "Metrik",
        "rpt_value": "Nilai",
        "rpt_total_records": "Total Skenario Uji",
        "rpt_applicable_records": "Skenario Berlaku",
        "rpt_fail_rate": "Tingkat Kegagalan",
        "rpt_failing_tests": "Skenario Gagal",
        "rpt_reasons": "Alasan Kegagalan",
        "rpt_slowest_tests": "Skenario Paling Lambat",
        "rpt_recommendations": "Rekomendasi Tindak Lanjut QA",
        "rpt_status_dist": "Distribusi Status Pengujian",
        "rpt_executed_evidence": "Rincian Bukti Eksekusi Pengujian",
        "rpt_checks_executed": "Pemeriksaan Dieksekusi",
        "rpt_search_placeholder": "Saring berdasarkan ID uji, target, atau pesan...",
        "rpt_all": "Semua",
        "rpt_details_json": "Rincian JSON",
        "rpt_checks_details": "Pemeriksaan & Rincian",
    },
}


def normalize_lang(lang: str | None = None) -> str:
    """Resolve and validate language code ('en' or 'id'), defaulting to env SAQA_LANG/JIRA_LANG or 'en'."""
    raw = (lang or os.getenv("SAQA_LANG") or os.getenv("JIRA_LANG") or "en").strip().lower()
    if raw in {"id", "id-id", "ind", "indonesia", "bahasa"}:
        return "id"
    if raw in {"en", "en-us", "en-gb", "eng", "english"}:
        return "en"
    raise ValueError(f"Unsupported language {lang!r}; choose 'en' (English) or 'id' (Bahasa Indonesia)")


def tr(msg_id: str, lang: str = "en", **kwargs: Any) -> str:
    """Translate a UI/Jira key into 'en' or 'id' with optional format arguments."""
    code = normalize_lang(lang)
    template = UI_STRINGS[code].get(msg_id) or UI_STRINGS["en"].get(msg_id) or msg_id
    return template.format(**kwargs) if kwargs else template


def get_issue_summaries(lang: str = "en") -> dict[str, str]:
    return dict(ISSUE_SUMMARIES_I18N[normalize_lang(lang)])


def get_all_summary_variants(domain_key: str) -> tuple[str, ...]:
    """Return all localized summary variants for a domain key (e.g. EN and ID) for duplicate-free lookup."""
    return tuple(ISSUE_SUMMARIES_I18N[code][domain_key] for code in SUPPORTED_LANGUAGES if domain_key in ISSUE_SUMMARIES_I18N[code])


def get_all_epic_summary_variants(phase_id: str) -> tuple[str, ...]:
    """Return all localized Epic summary variants for a phase ID."""
    return tuple(EPIC_TEXT_I18N[code][phase_id]["summary"] for code in SUPPORTED_LANGUAGES if phase_id in EPIC_TEXT_I18N[code])


def translate_recommendation(rec: str, lang: str = "en") -> str:
    """Translate standard analytics recommendation messages when Bahasa Indonesia is active."""
    if normalize_lang(lang) != "id":
        return rec
    exact_map = {
        "All executed checks passed with clean evidence integrity.": "Seluruh pemeriksaan yang dieksekusi lulus dengan integritas bukti kriptografi yang bersih.",
    }
    if rec in exact_map:
        return exact_map[rec]
    out = rec
    out = out.replace("Resolve failing test(s) before release certification:", "Perbaiki skenario uji yang gagal sebelum sertifikasi rilis:")
    out = out.replace("Unblock environment/target dependencies for:", "Buka hambatan lingkungan/target pengujian untuk:")
    out = out.replace("Investigate high P95 latency", "Investigasi latensi P95 yang tinggi")
    return out
