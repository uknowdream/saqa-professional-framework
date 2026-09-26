"""Cross-service test-data lifecycle primitives with deterministic cleanup tracking."""
from __future__ import annotations
from dataclasses import dataclass,field
from collections.abc import Callable

@dataclass
class TestDataScope:
    _cleanup: list[Callable[[],None]]=field(default_factory=list)
    closed: bool=False

    def register(self, cleanup:Callable[[],None])->None:
        if self.closed: raise RuntimeError("test-data scope is already closed")
        self._cleanup.append(cleanup)

    def close(self)->None:
        if self.closed: return
        errors=[]
        for cleanup in reversed(self._cleanup):
            try: cleanup()
            except Exception as exc: errors.append(exc)
        self.closed=True
        if errors: raise RuntimeError(f"{len(errors)} test-data cleanup operation(s) failed")

    def __enter__(self)->"TestDataScope": return self
    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
