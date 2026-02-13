"""
VolatilityDataProvider interface.

Returns volatility structure metrics used to compute the Vol Structure score.

Data Sources (yfinance):
- ^VIX: CBOE Volatility Index
- ^VIX3M: CBOE 3-Month Volatility Index (fallback: ^VXV)
- ^VVIX: CBOE VIX of VIX (optional)

Derived:
    term_slope: VIX3M - VIX (positive = contango = calm)
"""

from typing import Protocol, Dict, Any


class VolatilityDataProvider(Protocol):
    """
    Protocol for volatility structure data providers.

    Implementations must:
    - Be async
    - Return DataQuality with every response
    - Derive term_slope from VIX3M - VIX
    - Treat VVIX as optional (reduce completeness if missing, don't fail)
    - Handle missing data gracefully
    """

    async def get_current(self) -> Dict[str, Any]:
        """
        Get current volatility structure metrics.

        Returns:
            {
                "quality": {
                    "source": "yfinance",
                    "as_of": "2026-02-04T16:00:00",
                    "is_stale": false,
                    "completeness": 1.0,
                    "confidence_score": 100
                },
                "metrics": {
                    "vix": {
                        "value": 16.5,
                        "unit": "index",
                        "available": true
                    },
                    "term_slope": {
                        "value": 1.8,
                        "unit": "points",
                        "available": true
                    },
                    "vvix": {
                        "value": 82.0,
                        "unit": "index",
                        "available": true
                    }
                }
            }
        """
        ...
