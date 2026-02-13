"""
Data provider interfaces.

All providers must:
1. Be async
2. Return DataQuality with every response
3. Raise typed exceptions (not raw strings)
4. Support mocking for tests
"""

from .base import (
    # Exceptions
    ProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUpstreamFormatError,
    ProviderUnavailableError,
    # Data types
    DataQuality,
    SeriesPoint,
    TimeInterval,
    TimeRange,
    MetricValue,
    Driver,
    ProviderResponse,
)

from .liquidity import (
    LiquidityDataProvider,
    LiquidityMetrics,
    LiquiditySeries,
)

from .credit import CreditDataProvider
from .volatility import VolatilityDataProvider
from .event_density import EventDensityDataProvider

__all__ = [
    # Exceptions
    "ProviderError",
    "ProviderAuthError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderUpstreamFormatError",
    "ProviderUnavailableError",
    # Data types
    "DataQuality",
    "SeriesPoint",
    "TimeInterval",
    "TimeRange",
    "MetricValue",
    "Driver",
    "ProviderResponse",
    # Liquidity
    "LiquidityDataProvider",
    "LiquidityMetrics",
    "LiquiditySeries",
    # Credit
    "CreditDataProvider",
    # Volatility
    "VolatilityDataProvider",
    # Event Density
    "EventDensityDataProvider",
]
