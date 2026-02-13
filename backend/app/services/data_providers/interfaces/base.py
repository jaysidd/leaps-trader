"""
Base types, exceptions, and protocols for data providers.

All providers must:
1. Be async
2. Return DataQuality with every response
3. Raise typed exceptions (not raw strings)
4. Support mocking for tests
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


# =============================================================================
# EXCEPTIONS
# =============================================================================

class ProviderError(Exception):
    """Base exception for all provider errors."""
    pass


class ProviderAuthError(ProviderError):
    """Authentication failure with provider."""
    pass


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after_seconds: Optional[int] = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderTimeoutError(ProviderError):
    """Request timeout."""
    pass


class ProviderUpstreamFormatError(ProviderError):
    """Upstream API returned unexpected format."""
    pass


class ProviderUnavailableError(ProviderError):
    """Provider service is unavailable."""
    pass


# =============================================================================
# DATA QUALITY
# =============================================================================

@dataclass
class DataQuality:
    """
    Metadata about data quality and freshness.

    Rules:
    - completeness ∈ [0, 1]
    - confidence_score ∈ [0, 100]
    - is_stale=True implies confidence_score <= 40 unless explicitly justified
    """
    source: str
    as_of: datetime
    is_stale: bool = False
    stale_reason: Optional[str] = None
    completeness: float = 1.0  # 0-1, proportion of expected fields present
    confidence_score: float = 100.0  # 0-100

    def __post_init__(self):
        # Clamp values to valid ranges
        self.completeness = max(0.0, min(1.0, self.completeness))
        self.confidence_score = max(0.0, min(100.0, self.confidence_score))

        # Enforce staleness confidence cap
        if self.is_stale and self.confidence_score > 40:
            self.confidence_score = 40.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "is_stale": self.is_stale,
            "stale_reason": self.stale_reason,
            "completeness": self.completeness,
            "confidence_score": self.confidence_score,
        }


# =============================================================================
# TIME SERIES TYPES
# =============================================================================

@dataclass
class SeriesPoint:
    """A single point in a time series."""
    t: datetime  # timestamp
    v: float     # value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "t": self.t.isoformat() if self.t else None,
            "v": self.v,
        }


class TimeInterval(str, Enum):
    """Supported time intervals for historical data."""
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"


@dataclass
class TimeRange:
    """Time range specification for historical queries."""
    start: datetime
    end: datetime
    interval: TimeInterval = TimeInterval.ONE_DAY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "interval": self.interval.value,
        }


# =============================================================================
# METRIC TYPES
# =============================================================================

@dataclass
class MetricValue:
    """A single metric with optional change tracking."""
    value: Optional[float]
    unit: str
    change_1w: Optional[float] = None  # Percent change for monetary, absolute for indices
    change_4w: Optional[float] = None
    available: bool = True

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "value": self.value,
            "unit": self.unit,
            "available": self.available,
        }
        if self.change_1w is not None:
            result["change_1w"] = self.change_1w
        if self.change_4w is not None:
            result["change_4w"] = self.change_4w
        return result


@dataclass
class Driver:
    """A driver/contributor to a score with its contribution."""
    name: str
    value: float
    contribution: float  # Points contributed to score
    direction: str = "neutral"  # "bullish", "bearish", "neutral"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "contribution": self.contribution,
            "direction": self.direction,
        }


# =============================================================================
# RESPONSE WRAPPER
# =============================================================================

@dataclass
class ProviderResponse:
    """
    Standard wrapper for provider responses.

    All provider methods should return data wrapped in this structure
    to ensure consistent quality metadata.
    """
    quality: DataQuality
    data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quality": self.quality.to_dict(),
            **self.data,
        }
