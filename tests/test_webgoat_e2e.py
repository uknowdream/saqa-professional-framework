from __future__ import annotations

import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("webgoat_e2e", Path("scripts/webgoat_e2e.py"))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_local_webgoat_target_is_allowed() -> None:
    MODULE.validate_target("http://127.0.0.1:8080/WebGoat/")
    MODULE.validate_target("http://localhost:8080/WebGoat/")


def test_external_webgoat_target_is_rejected() -> None:
    for url in (
        "https://127.0.0.1:8080/WebGoat/",
        "http://example.com/WebGoat/",
        "http://192.168.1.10:8080/WebGoat/",
    ):
        try:
            MODULE.validate_target(url)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe target accepted: {url}")
