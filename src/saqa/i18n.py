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
        "methodology_mode": "SDLC Methodology",
        "governance_gate": "Release Gate Decision",
        "hmac_signature": "HMAC-SHA256 Provenance",
        "sec_1_exec": "1. Executive Quality & Governance Summary",
        "sec_2_matrix": "2. Automated Test Execution Matrix ({count} Scenarios)",
        "sec_3_findings": "3. Audit Findings, Evidence & Recommendations",
        "sec_4_governance": "4. {methodology} Governance Gate, SLA & Requirement Traceability (RTM)",
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
        "methodology_mode": "Metodologi SDLC",
        "governance_gate": "Keputusan Gerbang Rilis",
        "hmac_signature": "Tanda Tangan HMAC-SHA256",
        "sec_1_exec": "1. Ringkasan Eksekutif Kualitas & Tata Kelola",
        "sec_2_matrix": "2. Matriks Eksekusi Pengujian Otomatis ({count} Skenario)",
        "sec_3_findings": "3. Temuan Audit, Bukti & Rekomendasi Perbaikan",
        "sec_4_governance": "4. Gerbang Tata Kelola {methodology}, SLA & Matriks Kebutuhan (RTM)",
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


_CASE_NAME_ID_MAP: dict[str, str] = {
    "Pillar 1 — TLS/SSL Protocol & Certificate Expiry Audit": "Pilar 1 — Audit Protokol TLS/SSL & Masa Berlaku Sertifikat",
    "Pillar 1 — TLS/SSL Audit (HTTP target)": "Pilar 1 — Audit TLS/SSL (Target HTTP)",
    "Pillar 2 — OWASP Security Headers & Cookie Hygiene Audit": "Pilar 2 — Audit Header Keamanan OWASP & Sanitasi Cookie",
    "Pillar 3 — WCAG 2.2 Semantic DOM Accessibility Audit": "Pilar 3 — Audit Aksesibilitas DOM Semantik WCAG 2.2",
    "Pillar 4 — SEO Metadata, JSON-LD & Discoverability Audit": "Pilar 4 — Audit Metadata SEO, JSON-LD & Keterlacakan Situs",
    "Pillar 5 — Automated Broken Link, Static Asset & Mixed-Content Crawler": "Pilar 5 — Perayap Tautan Rusak, Aset Statis & Mixed-Content",
    "Pillar 6 — Read-Only Sensitive Dotfile Exposure Hygiene Audit": "Pilar 6 — Audit Proteksi Eksposur File Sensitif (.env / .git)",
    "Pillar 7 — Multi-Sample Performance, Payload & Cache Profile": "Pilar 7 — Profil Performa Multi-Sampel, Ukuran Muatan & Cache",
    "Pillar 8 — Post-JS SPA Rendered DOM, Core Web Vitals & Runtime Audit": "Pilar 8 — Audit DOM Pasca-Render JS (SPA), Core Web Vitals & Runtime",
    "Pillar 9 — CORS, SRI, RFC 9116, Mobile App-Links & GraphQL Security Audit": "Pilar 9 — Audit Keamanan CORS, SRI, RFC 9116, Universal Links Mobile & GraphQL",
    "Responsive Multi-Viewport Matrix (Desktop / Tablet / Mobile)": "Matriks Responsif Multi-Layar (Desktop / Tablet / Mobile)",
    "Mobile Pillar 1 — Package SHA-256 Integrity, Size Budget & Code Signing": "Pilar Mobile 1 — Integritas Paket SHA-256, Batas Ukuran & Tanda Tangan Kode",
    "Mobile Pillar 2 — App Manifest, Debuggability & HTTPS Transport Security": "Pilar Mobile 2 — Manifes Aplikasi, Proteksi Debug & Keamanan Transpor HTTPS",
    "Mobile Pillar 3 — Runtime Permissions & Store Privacy Compliance": "Pilar Mobile 3 — Izin Akses Perangkat & Kepatuhan Privasi App Store/Play Store",
    "Mobile Pillar 4 — Embedded Secret Scan & 64-Bit Store ABI Readiness": "Pilar Mobile 4 — Pemindaian Kredensial Tertanam & Kesiapan ABI 64-Bit",
    "Mobile Pillar 5 — Maestro E2E Mobile UI Flow": "Pilar Mobile 5 — Alur UI E2E Aplikasi Mobile (Maestro)",
    "Landing page reachability": "Keterjangkauan Halaman Utama",
}

_FINDING_SUBSTR_ID_MAP: tuple[tuple[str, str], ...] = (
    (
        "Both Content-Security-Policy and Content-Security-Policy-Report-Only are sent simultaneously",
        "Header Content-Security-Policy dan Content-Security-Policy-Report-Only dikirim bersamaan",
    ),
    ("Recommended baseline headers absent:", "Header keamanan dasar yang disarankan belum terpasang:"),
    ("Missing Cache-Control header on landing page", "Header Cache-Control tidak ditemukan pada halaman utama"),
    ("Missing <meta name='description'>", "Elemen <meta name='description'> tidak ditemukan"),
    ("Missing <link rel='canonical'>", "Elemen <link rel='canonical'> tidak ditemukan"),
    ("Incomplete OpenGraph metadata (og:title / og:description)", "Metadata OpenGraph belum lengkap (og:title / og:description)"),
    ("No <main> landmark found in initial HTML", "Elemen landmark <main> belum ditemukan pada HTML awal"),
    (
        "No <h1> landmark heading found in initial server HTML (may be client-rendered)",
        "Elemen <h1> belum ditemukan pada HTML awal server (dirender di sisi klien)",
    ),
    ("Missing lang attribute on <html> element", "Atribut lang tidak ditemukan pada elemen <html>"),
    ("Missing or empty <title> element", "Elemen <title> kosong atau tidak ditemukan"),
    ("Viewport meta disables pinch-to-zoom", "Meta viewport menonaktifkan fitur perbesar layar (pinch-to-zoom)"),
    ("Horizontal layout overflow on", "Tata letak meluap secara horizontal pada layar"),
    ("broken link/asset(s) found:", "tautan/aset rusak ditemukan:"),
    ("CRITICAL: Sensitive file exposed at", "KRITIS: File sensitif terekspos secara publik pada"),
    ("CRITICAL: Hardcoded secret(s) detected inside mobile bundle:", "KRITIS: Kredensial rahasia tertanam ditemukan di dalam paket mobile:"),
    ("GraphQL Introspection is publicly enabled on /graphql", "GraphQL Introspection aktif secara publik pada /graphql"),
    ("external third-party <script> tag(s) missing Subresource Integrity (SRI)", "tag <script> pihak ketiga belum dilengkapi Subresource Integrity (SRI)"),
    ("WCAG 2.2 AA low color contrast detected", "Kontras warna rendah terdeteksi (di bawah standar WCAG 2.2 AA)"),
    ("android:debuggable=\"true\" enabled in manifest", "android:debuggable=\"true\" aktif pada manifes Android"),
    ("unprotected android:exported=\"true\" component(s)", "komponen android:exported=\"true\" tanpa izin proteksi ditemukan"),
)


def translate_case_name(case_name: str, lang: str = "en") -> str:
    """Localize canonical SAQA scenario / pillar names into Bahasa Indonesia when lang='id'."""
    if normalize_lang(lang) != "id":
        return case_name
    if case_name in _CASE_NAME_ID_MAP:
        return _CASE_NAME_ID_MAP[case_name]
    if case_name.startswith("Multi-Page Sitemap & BFS Deep Site Crawler ("):
        suffix = case_name.removeprefix("Multi-Page Sitemap & BFS Deep Site Crawler (").replace("page(s))", "halaman)")
        return f"Perayap Mendalam Multi-Halaman Sitemap & BFS ({suffix}"
    if case_name.startswith("Concurrent HTTP Load & SLA Stress Gate ("):
        suffix = case_name.removeprefix("Concurrent HTTP Load & SLA Stress Gate (")
        return f"Gerbang Uji Beban Konkuren & SLA HTTP ({suffix}"
    return case_name


def translate_finding_or_reason(text: str, lang: str = "en") -> str:
    """Localize technical QA findings, warnings, and failure reasons into Bahasa Indonesia when lang='id'."""
    if normalize_lang(lang) != "id":
        return text
    out = text
    for en_sub, id_sub in _FINDING_SUBSTR_ID_MAP:
        if en_sub in out:
            out = out.replace(en_sub, id_sub)
    return out
