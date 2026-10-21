import pytest

from scripts.validate_container_image_ref import validate_image_ref


@pytest.mark.parametrize("value", [
    "ghcr.io/acme/my-app@sha256:" + "a" * 64,
    "docker.io/library/alpine@sha256:" + "0" * 64,
    "registry.example.com:5000/team/service_api@sha256:" + "f" * 64,
])
def test_accepts_registry_qualified_digest_pinned_references(value):
    assert validate_image_ref(value) == value


@pytest.mark.parametrize("value", [
    "",
    None,
    "docker.io/library/alpine:latest",
    "docker.io/library/alpine",
    "alpine@sha256:" + "a" * 64,
    "https://ghcr.io/acme/app@sha256:" + "a" * 64,
    "ghcr.io/acme/app@sha256:" + "A" * 64,
    "ghcr.io/acme/app@sha256:" + "a" * 63,
    "ghcr.io/acme/app:latest@sha256:" + "a" * 64,
    "user:password@ghcr.io/acme/app@sha256:" + "a" * 64,
    "ghcr.io/acme/app@sha256:" + "a" * 64 + " ",
    "ghcr.io/acme/../app@sha256:" + "a" * 64,
    "ghcr.io/acme/app;echo bad@sha256:" + "a" * 64,
    "registry.example.com:99999/team/app@sha256:" + "a" * 64,
])
def test_rejects_floating_credential_or_malformed_references(value):
    with pytest.raises(ValueError):
        validate_image_ref(value)
