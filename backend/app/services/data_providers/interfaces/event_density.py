"""
EventDensityDataProvider interface.

Returns event density metrics used to compute the Event Density score.

Data Sources:
- NewsFeedService.get_economic_calendar() — economic events with impact levels
- NewsFeedService.get_earnings_calendar() — upcoming earnings announcements

Scoring:
    Event points: high=3, medium=2, low=1
    Earnings contribution capped at EVENT_EARNINGS_CAP points
    Score = clamp(0, 100, 100 * total_points / EVENT_DENSITY_MAX_POINTS)
"""

from typing import Protocol, Dict, Any


class EventDensityDataProvider(Protocol):
    """
    Protocol for event density data providers.

    Implementations must:
    - Be async
    - Return DataQuality with every response
    - Sum weighted event points (high=3, medium=2, low=1)
    - Cap earnings contribution
    - Return top events list for UI display
    """

    async def get_current(self) -> Dict[str, Any]:
        """
        Get current event density metrics.

        Returns:
            {
                "quality": {
                    "source": "finnhub",
                    "as_of": "2026-02-04T12:00:00",
                    "is_stale": false,
                    "completeness": 1.0,
                    "confidence_score": 100
                },
                "metrics": {
                    "total_points": 12.0,
                    "high_impact_count": 2,
                    "economic_event_count": 5,
                    "earnings_count": 8,
                    "events": [
                        {
                            "name": "FOMC Minutes",
                            "datetime": "2026-02-05T19:00:00Z",
                            "impact": "high",
                            "category": "economic",
                            "source": "finnhub"
                        }
                    ]
                }
            }
        """
        ...
