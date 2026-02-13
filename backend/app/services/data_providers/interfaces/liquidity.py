"""
LiquidityDataProvider interface.

Returns macro liquidity/conditions metrics used to compute the Liquidity Regime score.

Data Sources (FRED):
- WALCL: Fed Balance Sheet (weekly)
- RRPONTSYD: Reverse Repo (daily)
- WTREGEN: Treasury General Account (weekly)
- NFCI: Chicago Fed Financial Conditions Index (weekly)
- DGS10: 10-Year Treasury Yield (daily)
- T10YIE: 10-Year Breakeven Inflation (daily)

Real Yield Formula:
    real_yield_10y = DGS10 - T10YIE (derived, not fetched)
"""

from typing import Protocol, Dict, Any, List, Optional
from datetime import datetime

from .base import DataQuality, MetricValue, SeriesPoint


class LiquidityDataProvider(Protocol):
    """
    Protocol for liquidity data providers.

    Implementations must:
    - Be async
    - Return DataQuality with every response
    - Derive real_yield_10y from DGS10 - T10YIE
    - Handle missing data gracefully (reduce completeness, don't throw)
    """

    async def get_current(self) -> Dict[str, Any]:
        """
        Get current liquidity metrics.

        Returns:
            {
                "quality": {
                    "source": "fred|vendor|internal",
                    "as_of": "2026-02-02T14:30:00Z",
                    "is_stale": false,
                    "stale_reason": null,
                    "completeness": 0.9,
                    "confidence_score": 78
                },
                "metrics": {
                    "fed_balance_sheet": {
                        "value": 7.53e12,
                        "unit": "usd",
                        "change_1w": -0.3,
                        "change_4w": -1.1
                    },
                    "rrp": {
                        "value": 0.61e12,
                        "unit": "usd",
                        "change_1w": -8.2,
                        "change_4w": -21.5
                    },
                    "tga": {
                        "value": 0.73e12,
                        "unit": "usd",
                        "change_1w": 4.0,
                        "change_4w": 10.6
                    },
                    "fci": {
                        "value": -0.21,
                        "unit": "index",
                        "change_1w": -0.05,
                        "change_4w": -0.10
                    },
                    "real_yield_10y": {
                        "value": 1.85,
                        "unit": "pct",
                        "change_1w": 0.06,
                        "change_4w": 0.12
                    }
                }
            }

        Notes:
            - change_* are percent change for monetary series (fed_balance_sheet/rrp/tga)
            - change_* are absolute change for indices/percent series (fci/real_yield_10y)
        """
        ...

    async def get_history(
        self,
        start: str,
        end: str,
        interval: str = "1d"
    ) -> Dict[str, Any]:
        """
        Get historical liquidity metrics.

        Args:
            start: ISO-8601 datetime string
            end: ISO-8601 datetime string
            interval: "1d" (daily) or "1w" (weekly)

        Returns:
            {
                "quality": { ... },
                "series": {
                    "fed_balance_sheet": [
                        { "t": "2026-01-01T00:00:00Z", "v": 7.54e12 },
                        { "t": "2026-01-08T00:00:00Z", "v": 7.53e12 }
                    ],
                    "rrp": [ ... ],
                    "tga": [ ... ],
                    "fci": [ ... ],
                    "real_yield_10y": [ ... ]
                }
            }
        """
        ...


# Type hints for response structures
LiquidityMetrics = Dict[str, MetricValue]
LiquiditySeries = Dict[str, List[SeriesPoint]]
