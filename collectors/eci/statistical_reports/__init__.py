"""ECI statistical-report acquisition package (capture-only; no canonical mutation)."""

from collectors.eci.statistical_reports.capture import (
    COLLECTOR_NAME,
    COLLECTOR_VERSION,
    CaptureReport,
    capture_report,
)

__all__ = [
    "COLLECTOR_NAME",
    "COLLECTOR_VERSION",
    "CaptureReport",
    "capture_report",
]
