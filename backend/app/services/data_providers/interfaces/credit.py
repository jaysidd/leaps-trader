"""
CreditDataProvider interface.

Returns credit spread metrics used to compute the Credit Stress score.

Data Sources (FRED):
- BAMLH0A0HYM2: ICE BofA US High Yield OAS (daily)
- BAMLC0A0CM: ICE BofA US Corporate IG OAS (daily)

Derived:
    hy_oas_change_4w: 4-week absolute change in HY OAS
"""

from typing import Protocol, Dict, Any


class CreditDataProvider(Protocol):
    """
    Protocol for credit spread data providers.

    Implementations must:
    - Be async
    - Return DataQuality with every response
    - Compute hy_oas_change_4w from historical data
    - Handle missing data gracefully (reduce completeness, don't throw)
    """

    async def get_current(self) -> Dict[str, Any]:
        """
        Get current credit spread metrics.

        Returns:
            {
                "quality": {
                    "source": "fred",
                    "as_of": "2026-02-04T00:00:00",
                    "is_stale": false,
                    "completeness": 1.0,
                    "confidence_score": 100
                },
                "metrics": {
                    "hy_oas": {
                        "value": 3.45,
                        "unit": "pct",
                        "change_1w": 0.05,
                        "change_4w": 0.12,
                        "available": true
                    },
                    "ig_oas": {
                        "value": 1.15,
                        "unit": "pct",
                        "change_1w": 0.02,
                        "change_4w": 0.05,
                        "available": true
                    },
                    "hy_oas_change_4w": {
                        "value": 0.12,
                        "unit": "pct_abs",
                        "available": true
                    }
                }
            }
        """
        ...
