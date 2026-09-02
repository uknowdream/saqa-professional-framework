"""Target registry primitives for reproducible and authorized QA environments."""

from dataclasses import dataclass, field
from enum import Enum


class TargetKind(str, Enum):
    WEB = "web"
    API = "api"
    MOBILE = "mobile"
    SECURITY = "security"


class Deployment(str, Enum):
    LOCAL = "local"
    CONTAINER = "container"
    REMOTE = "remote"


@dataclass(frozen=True)
class Target:
    name: str
    kind: TargetKind
    deployment: Deployment
    base_url: str
    authorized: bool = False
    version: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)

    @property
    def certifiable(self) -> bool:
        """Only explicitly authorized local/container targets are primary cert targets."""
        return self.authorized and self.deployment in {
            Deployment.LOCAL,
            Deployment.CONTAINER,
        }


def require_certifiable(target: Target) -> None:
    if not target.certifiable:
        raise ValueError(
            f"Target {target.name!r} is not eligible for primary certification; "
            "use an explicitly authorized local/container deployment."
        )


DEFAULT_TARGETS = (
    Target(
        name="owasp-juice-shop",
        kind=TargetKind.SECURITY,
        deployment=Deployment.CONTAINER,
        base_url="http://127.0.0.1:3000",
        authorized=True,
        tags=frozenset({"web", "api", "security", "docker"}),
    ),
    Target(
        name="owasp-webgoat",
        kind=TargetKind.SECURITY,
        deployment=Deployment.CONTAINER,
        base_url="http://127.0.0.1:8080",
        authorized=True,
        tags=frozenset({"web", "api", "security", "java", "docker"}),
    ),
)
