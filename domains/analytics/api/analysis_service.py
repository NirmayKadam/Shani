"""
File Overview: Backward-compatible re-export. AnalysisService now lives in
domains.analytics.application.services.analysis_service (DDD application layer).

This shim exists so existing callers that import from the old path continue to work.
New code should import from the canonical location.
"""
# Re-export for backward compatibility
from domains.analytics.application.services.analysis_service import AnalysisService  # noqa: F401

__all__ = ["AnalysisService"]
