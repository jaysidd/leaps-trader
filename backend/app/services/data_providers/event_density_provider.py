"""
Concrete implementation of EventDensityDataProvider.

Uses existing NewsFeedService calendars to compute event density:
- Economic calendar events with impact-weighted points
- Earnings calendar with capped contribution

Scoring:
    Event points: high=3, medium=2, low=1
    Earnings capped at EVENT_EARNINGS_CAP points
    Score = clamp(0, 100, 100 * total_points / EVENT_DENSITY_MAX_POINTS)
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger

from .interfaces import DataQuality


class EventDensityDataProviderImpl:
    """
    EventDensityDataProvider implementation using NewsFeedService.

    Uses get_economic_calendar() and get_earnings_calendar() to compute
    weighted event density for the upcoming 7-day window.
    """

    def __init__(self, news_feed_service=None):
        self._news_feed = news_feed_service

    def _get_news_feed(self):
        """Lazy-load NewsFeedService to avoid circular imports."""
        if self._news_feed is None:
            from app.services.command_center.news_feed import get_news_feed_service
            self._news_feed = get_news_feed_service()
        return self._news_feed

    async def get_current(self) -> Dict[str, Any]:
        """
        Get current event density metrics.

        Returns:
            {
                "quality": DataQuality dict,
                "metrics": {
                    "total_points": float,
                    "high_impact_count": int,
                    "economic_event_count": int,
                    "earnings_count": int,
                    "events": List[dict]  (top 10 for UI display)
                }
            }
        """
        from app.services.command_center.catalyst_config import get_catalyst_config
        config = get_catalyst_config()

        point_weights = config.EVENT_POINT_WEIGHTS
        earnings_cap = config.EVENT_EARNINGS_CAP

        news_feed = self._get_news_feed()
        economic_events = []
        earnings_events = []
        errors = []

        # Fetch economic calendar
        try:
            economic_events = await news_feed.get_economic_calendar(days_ahead=7)
        except Exception as e:
            logger.error(f"EventDensityProvider: Failed to fetch economic calendar: {e}")
            errors.append("economic_calendar")

        # Fetch earnings calendar
        try:
            earnings_events = await news_feed.get_earnings_calendar(days_ahead=7)
        except Exception as e:
            logger.error(f"EventDensityProvider: Failed to fetch earnings calendar: {e}")
            errors.append("earnings_calendar")

        # Compute economic event points
        economic_points = 0.0
        high_impact_count = 0
        for event in economic_events:
            impact = event.get("impact", "low")
            points = point_weights.get(impact, 1)
            economic_points += points
            if impact == "high":
                high_impact_count += 1

        # Compute earnings points (capped)
        earnings_points = min(len(earnings_events) * point_weights.get("medium", 2), earnings_cap)

        total_points = economic_points + earnings_points

        # Build top events list for UI (top 10 by impact, sorted by datetime)
        ui_events = []
        for event in economic_events:
            ui_events.append({
                "name": event.get("name", "Unknown"),
                "datetime": event.get("datetime", ""),
                "impact": event.get("impact", "low"),
                "category": "economic",
                "source": "finnhub",
            })

        for event in earnings_events[:10]:
            ui_events.append({
                "name": f"{event.get('symbol', '?')} Earnings",
                "datetime": event.get("date", ""),
                "impact": "medium",
                "category": "earnings",
                "source": "finnhub",
            })

        # Sort by impact (high first) then datetime
        impact_order = {"high": 0, "medium": 1, "low": 2}
        ui_events.sort(key=lambda x: (impact_order.get(x["impact"], 3), x.get("datetime", "")))
        ui_events = ui_events[:10]

        # Build quality
        has_economic = "economic_calendar" not in errors
        has_earnings = "earnings_calendar" not in errors
        completeness = (int(has_economic) + int(has_earnings)) / 2.0

        quality = DataQuality(
            source="finnhub",
            as_of=datetime.utcnow(),
            is_stale=False,
            completeness=completeness,
            confidence_score=completeness * 100,
        )

        return {
            "quality": quality.to_dict(),
            "metrics": {
                "total_points": round(total_points, 1),
                "high_impact_count": high_impact_count,
                "economic_event_count": len(economic_events),
                "earnings_count": len(earnings_events),
                "events": ui_events,
            },
        }


# Singleton instance
_event_density_provider: Optional[EventDensityDataProviderImpl] = None


def get_event_density_provider() -> EventDensityDataProviderImpl:
    """Get singleton event density provider instance."""
    global _event_density_provider
    if _event_density_provider is None:
        _event_density_provider = EventDensityDataProviderImpl()
    return _event_density_provider
