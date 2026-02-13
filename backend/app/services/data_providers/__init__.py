"""
Data providers for external data sources.

All providers:
1. Are async
2. Return DataQuality with every response
3. Raise typed exceptions (not raw strings)
4. Support mocking for tests

Structure:
- interfaces/: Protocol definitions and base types
- fred/: FRED API client
- liquidity_provider.py: LiquidityDataProvider implementation
- credit_provider.py: CreditDataProvider implementation
- volatility_provider.py: VolatilityDataProvider implementation
- event_density_provider.py: EventDensityDataProvider implementation
"""

from .interfaces import (
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
    # Protocols
    LiquidityDataProvider,
    CreditDataProvider,
    VolatilityDataProvider,
    EventDensityDataProvider,
)

from .fred import (
    FREDService,
    get_fred_service,
    FRED_SERIES,
)

from .liquidity_provider import (
    LiquidityDataProviderImpl,
    get_liquidity_provider,
)

from .credit_provider import (
    CreditDataProviderImpl,
    get_credit_provider,
)

from .volatility_provider import (
    VolatilityDataProviderImpl,
    get_volatility_provider,
)

from .event_density_provider import (
    EventDensityDataProviderImpl,
    get_event_density_provider,
)

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
    # Protocols
    "LiquidityDataProvider",
    "CreditDataProvider",
    "VolatilityDataProvider",
    "EventDensityDataProvider",
    # FRED
    "FREDService",
    "get_fred_service",
    "FRED_SERIES",
    # Liquidity
    "LiquidityDataProviderImpl",
    "get_liquidity_provider",
    # Credit
    "CreditDataProviderImpl",
    "get_credit_provider",
    # Volatility
    "VolatilityDataProviderImpl",
    "get_volatility_provider",
    # Event Density
    "EventDensityDataProviderImpl",
    "get_event_density_provider",
]
