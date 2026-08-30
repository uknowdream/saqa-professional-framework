import pytest

from saqa.target_registry import (
    DEFAULT_TARGETS,
    Deployment,
    Target,
    TargetKind,
    require_certifiable,
)


def test_default_targets_are_authorized_and_reproducible():
    assert {target.name for target in DEFAULT_TARGETS} == {
        "owasp-juice-shop",
        "owasp-webgoat",
    }
    assert all(target.certifiable for target in DEFAULT_TARGETS)
    assert all(target.deployment == Deployment.CONTAINER for target in DEFAULT_TARGETS)


def test_remote_target_cannot_be_primary_certification_target():
    target = Target(
        name="remote-api",
        kind=TargetKind.API,
        deployment=Deployment.REMOTE,
        base_url="https://example.invalid",
        authorized=True,
    )
    assert not target.certifiable
    with pytest.raises(ValueError, match="not eligible"):
        require_certifiable(target)


def test_unauthorized_local_target_is_rejected():
    target = Target(
        name="unknown-local",
        kind=TargetKind.WEB,
        deployment=Deployment.LOCAL,
        base_url="http://127.0.0.1:3000",
        authorized=False,
    )
    assert not target.certifiable
    with pytest.raises(ValueError, match="not eligible"):
        require_certifiable(target)
