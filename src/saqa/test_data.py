"""Cross-service test-data lifecycle primitives with deterministic cleanup tracking."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class TestDataScope:
    # Prevent pytest from treating this imported runtime helper as a test class.
    __test__ = False
    _cleanup: list[Callable[[], None]] = field(default_factory=list)
    closed: bool = False

    def register(self, cleanup: Callable[[], None]) -> None:
        if self.closed:
            raise RuntimeError("test-data scope is already closed")
        self._cleanup.append(cleanup)

    def close(self) -> None:
        if self.closed:
            return
        errors: list[Exception] = []
        for cleanup in reversed(self._cleanup):
            try:
                cleanup()
            except Exception as exc:
                errors.append(exc)
        self.closed = True
        if errors:
            details = "; ".join(str(error) for error in errors)
            raise RuntimeError(
                f"{len(errors)} test-data cleanup operation(s) failed: {details}"
            ) from errors[0]

    def __enter__(self) -> "TestDataScope":
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.close()
        except RuntimeError as cleanup_error:
            if exc is not None:
                if hasattr(exc, "add_note"):
                    exc.add_note(str(cleanup_error))
                return False
            raise
        return False
