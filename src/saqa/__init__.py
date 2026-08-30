"""SAQA Professional QA Automation Framework."""

__version__ = "2.1.0"

from .contracts import Evidence, ResultStatus, is_certification_safe, validate_evidence

__all__ = ["Evidence", "ResultStatus", "is_certification_safe", "validate_evidence", "__version__"]
