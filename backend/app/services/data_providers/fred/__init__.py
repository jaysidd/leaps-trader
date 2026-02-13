"""
FRED (Federal Reserve Economic Data) provider.
"""

from .fred_service import (
    FREDService,
    get_fred_service,
    FRED_SERIES,
    STALENESS_THRESHOLDS,
)

__all__ = [
    "FREDService",
    "get_fred_service",
    "FRED_SERIES",
    "STALENESS_THRESHOLDS",
]
