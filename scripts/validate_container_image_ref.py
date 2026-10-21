"""Validate a registry-qualified immutable OCI image reference for security scanning."""
from __future__ import annotations

import argparse
import json
import re
from typing import Any

# Require a registry host, repository path, and immutable SHA-256 digest.
# Tags, floating references, credentials, whitespace, and shell-like input are rejected.
_IMAGE_REF = re.compile(
    r"^(?P<registry>[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?)/"
    r"(?P<path>[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*(?:/[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*)*)"
    r"@sha256:(?P<digest>[0-9a-f]{64})$"
)


def validate_image_ref(value: Any) -> str:
    """Return the immutable image reference or raise a precise validation error."""
    if not isinstance(value, str) or not value:
        raise ValueError("image reference must be a non-empty string")
    if value != value.strip() or any(character.isspace() for character in value):
        raise ValueError("image reference must not contain whitespace")
    if "://" in value or "@" not in value:
        raise ValueError("image reference must be registry-qualified and pinned with @sha256:<64 lowercase hex>")
    match = _IMAGE_REF.fullmatch(value)
    if not match:
        raise ValueError("image reference must match registry/repository@sha256:<64 lowercase hex>; tags and credentials are not accepted")
    port = match.group("registry").rsplit(":", 1)
    if len(port) == 2:
        port_value = int(port[1])
        if not 1 <= port_value <= 65535:
            raise ValueError("registry port must be between 1 and 65535")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-ref", required=True)
    args = parser.parse_args(argv)
    try:
        validated = validate_image_ref(args.image_ref)
    except ValueError as exc:
        print(json.dumps({"schema": "saqa.oci-image-ref-validation.v1", "status": "BLOCKED", "error": str(exc)}, indent=2))
        return 2
    print(json.dumps({"schema": "saqa.oci-image-ref-validation.v1", "status": "PASS", "image_ref": validated,
                      "digest_pinned": True, "registry_qualified": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
