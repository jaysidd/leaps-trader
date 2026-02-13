"""
Catalyst Calendar Service

Tracks and scores upcoming catalysts:
- Earnings dates
- Ex-dividend dates
- Product launches (from news)
- Analyst events
- FDA approvals (for healthcare)
- Macro events (Fed, jobs, CPI)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

from app.services.cache import cache_service


class CatalystType(str, Enum):
    """Types of catalysts."""
    EARNINGS = "earnings"
    DIVIDEND = "dividend"
    CONFERENCE = "conference"
    PRODUCT_LAUNCH = "product_launch"
    FDA_DECISION = "fda_decision"
    ANALYST_DAY = "analyst_day"
    MACRO_EVENT = "macro_event"
    SPLIT = "split"
    OTHER = "other"


class CatalystImpact(str, Enum):
    """Expected impact level."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Catalyst:
    """Represents a single catalyst event."""
    symbol: str
    catalyst_type: CatalystType
    date: datetime
    description: str
    impact: CatalystImpact = CatalystImpact.MEDIUM
    expected_move_pct: Optional[float] = None  # Historical avg move
    source: str = ""
    confirmed: bool = True


@dataclass
class CatalystCalendar:
    """Collection of catalysts for a stock."""
    symbol: str
    catalysts: List[Catalyst] = field(default_factory=list)

    # Key dates
    next_earnings_date: Optional[datetime] = None
    days_to_earnings: Optional[int] = None
    next_dividend_date: Optional[datetime] = None
    days_to_dividend: Optional[int] = None

    # Scoring
    catalyst_score: float = 0.0  # 0-100
    risk_level: str = "normal"  # low, normal, elevated, high
    recommendation: str = ""

    fetched_at: Optional[datetime] = None


class CatalystService:
    """
    Service for tracking and scoring catalysts.
    """

    CACHE_TTL = 3600  # 1 hour

    def __init__(self):
        pass

    async def get_earnings_date(self, symbol: str) -> Optional[datetime]:
        """
        Get the next earnings date for a stock using Finnhub earnings calendar.
        """
        cache_key = f"earnings_date:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            return datetime.fromisoformat(cached) if cached else None

        try:
            from app.services.command_center.news_feed import get_news_feed_service
            news_feed = get_news_feed_service()

            # Use Finnhub earnings calendar (already integrated)
            earnings = await news_feed.get_earnings_calendar()
            now = datetime.now()

            # Find this symbol's next earnings
            for item in earnings:
                if item.get('symbol') == symbol:
                    date_str = item.get('date', '')
                    if date_str:
                        try:
                            earnings_date = datetime.fromisoformat(date_str)
                            if earnings_date > now:
                                cache_service.set(
                                    cache_key,
                                    earnings_date.isoformat(),
                                    self.CACHE_TTL
                                )
                                return earnings_date
                        except (ValueError, TypeError):
                            continue

            return None

        except Exception as e:
            logger.debug(f"Error getting earnings date for {symbol}: {e}")
            return None

    async def get_dividend_date(self, symbol: str) -> Optional[datetime]:
        """
        Get the next ex-dividend date for a stock using FMP data.
        """
        cache_key = f"dividend_date:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            return datetime.fromisoformat(cached) if cached else None

        try:
            from app.services.data_fetcher.fmp_service import fmp_service
            info = fmp_service.get_stock_info(symbol)

            if info and info.get('ex_dividend_date'):
                try:
                    div_date = datetime.fromisoformat(info['ex_dividend_date'])
                    if div_date > datetime.now():
                        cache_service.set(
                            cache_key,
                            div_date.isoformat(),
                            self.CACHE_TTL
                        )
                        return div_date
                except (ValueError, TypeError):
                    pass

            return None

        except Exception as e:
            logger.debug(f"Error getting dividend date for {symbol}: {e}")
            return None

    async def get_historical_earnings_move(self, symbol: str) -> Optional[float]:
        """
        Calculate the average historical earnings move (absolute %).
        Useful for estimating expected volatility around earnings.

        Note: Without per-date earnings history, we approximate
        by calculating average daily moves (top moves as proxy).
        """
        cache_key = f"earnings_move:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            return cached

        try:
            from app.services.data_fetcher.alpaca_service import alpaca_service

            # Get 2 years of historical prices
            hist = alpaca_service.get_historical_prices(symbol, period="2y")
            if hist is None or hist.empty or len(hist) < 60:
                return None

            close_col = 'Close' if 'Close' in hist.columns else 'close'

            # Calculate daily returns
            returns = hist[close_col].pct_change().dropna().abs() * 100

            # Estimate earnings moves as the top ~8 moves in 2 years
            # (roughly 8 quarterly earnings in 2 years)
            top_n = min(8, len(returns) // 60)  # ~1 per quarter
            if top_n < 2:
                return None

            top_moves = returns.nlargest(top_n)
            avg_move = float(top_moves.mean())

            cache_service.set(cache_key, avg_move, self.CACHE_TTL * 24)
            return avg_move

        except Exception as e:
            logger.debug(f"Error calculating earnings move for {symbol}: {e}")
            return None

    async def get_catalyst_calendar(
        self,
        symbol: str,
        company_name: Optional[str] = None
    ) -> CatalystCalendar:
        """
        Get comprehensive catalyst calendar for a stock.
        """
        cache_key = f"catalyst_calendar:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            cal = CatalystCalendar(symbol=symbol)
            cal.next_earnings_date = (
                datetime.fromisoformat(cached['next_earnings_date'])
                if cached.get('next_earnings_date') else None
            )
            cal.days_to_earnings = cached.get('days_to_earnings')
            cal.next_dividend_date = (
                datetime.fromisoformat(cached['next_dividend_date'])
                if cached.get('next_dividend_date') else None
            )
            cal.days_to_dividend = cached.get('days_to_dividend')
            cal.catalyst_score = cached.get('catalyst_score', 0)
            cal.risk_level = cached.get('risk_level', 'normal')
            cal.recommendation = cached.get('recommendation', '')
            return cal

        calendar = CatalystCalendar(
            symbol=symbol,
            fetched_at=datetime.now()
        )

        # Get earnings date
        earnings_date = await self.get_earnings_date(symbol)
        if earnings_date:
            calendar.next_earnings_date = earnings_date
            calendar.days_to_earnings = (earnings_date.date() - datetime.now().date()).days

            # Add as catalyst
            expected_move = await self.get_historical_earnings_move(symbol)
            calendar.catalysts.append(Catalyst(
                symbol=symbol,
                catalyst_type=CatalystType.EARNINGS,
                date=earnings_date,
                description="Quarterly Earnings Report",
                impact=CatalystImpact.HIGH,
                expected_move_pct=expected_move,
                source="Finnhub/FMP"
            ))

        # Get dividend date
        dividend_date = await self.get_dividend_date(symbol)
        if dividend_date:
            calendar.next_dividend_date = dividend_date
            calendar.days_to_dividend = (dividend_date.date() - datetime.now().date()).days

            calendar.catalysts.append(Catalyst(
                symbol=symbol,
                catalyst_type=CatalystType.DIVIDEND,
                date=dividend_date,
                description="Ex-Dividend Date",
                impact=CatalystImpact.LOW,
                source="Finnhub/FMP"
            ))

        # Calculate catalyst score and risk level
        self._calculate_catalyst_score(calendar)

        # Cache result
        cache_data = {
            'next_earnings_date': (
                calendar.next_earnings_date.isoformat()
                if calendar.next_earnings_date else None
            ),
            'days_to_earnings': calendar.days_to_earnings,
            'next_dividend_date': (
                calendar.next_dividend_date.isoformat()
                if calendar.next_dividend_date else None
            ),
            'days_to_dividend': calendar.days_to_dividend,
            'catalyst_score': calendar.catalyst_score,
            'risk_level': calendar.risk_level,
            'recommendation': calendar.recommendation
        }
        cache_service.set(cache_key, cache_data, self.CACHE_TTL)

        return calendar

    def _calculate_catalyst_score(self, calendar: CatalystCalendar):
        """
        Calculate catalyst score and risk level.

        Score considers:
        - Proximity to earnings (closer = higher risk for options)
        - Number of upcoming catalysts
        - Impact level of catalysts
        """
        score = 50  # Start neutral
        risk_factors = []

        # Earnings timing
        if calendar.days_to_earnings is not None:
            days = calendar.days_to_earnings

            if days <= 0:
                # Just had earnings - potentially good entry
                score += 10
                calendar.recommendation = "Post-earnings entry opportunity"
            elif days <= 7:
                # Imminent earnings - high risk for options buyers
                score -= 20
                risk_factors.append("earnings_imminent")
                calendar.recommendation = "Wait for post-earnings or use spread to hedge IV"
            elif days <= 14:
                # Approaching earnings
                score -= 10
                risk_factors.append("earnings_approaching")
                calendar.recommendation = "Consider IV risk; spreads may be safer"
            elif days <= 30:
                # Moderate distance
                score += 5
                calendar.recommendation = "Favorable window for entry"
            elif days <= 60:
                # Ideal timing window
                score += 15
                calendar.recommendation = "Optimal catalyst distance for LEAPS"
            else:
                # Far from earnings
                score += 10
                calendar.recommendation = "Safe distance from earnings catalyst"

        else:
            # Unknown earnings date
            score += 5
            calendar.recommendation = "Earnings date unknown; monitor for updates"

        # Count high-impact catalysts in next 30 days
        high_impact_soon = sum(
            1 for c in calendar.catalysts
            if c.impact == CatalystImpact.HIGH
            and c.date <= datetime.now() + timedelta(days=30)
        )

        if high_impact_soon >= 2:
            score -= 10
            risk_factors.append("multiple_catalysts")

        # Normalize score
        calendar.catalyst_score = max(0, min(100, score))

        # Set risk level
        if len(risk_factors) >= 2 or "earnings_imminent" in risk_factors:
            calendar.risk_level = "high"
        elif len(risk_factors) == 1:
            calendar.risk_level = "elevated"
        elif calendar.catalyst_score >= 60:
            calendar.risk_level = "low"
        else:
            calendar.risk_level = "normal"

    async def get_macro_calendar(self) -> List[Dict[str, Any]]:
        """
        Get upcoming macro events (Fed meetings, CPI, jobs, etc.)

        Note: This would ideally use an economic calendar API.
        For now, returns a static list of known events.
        """
        # This is a placeholder - in production, use an API like
        # Trading Economics, Investing.com, or similar
        events = [
            {
                "date": "Monthly",
                "event": "CPI Report",
                "impact": "high",
                "description": "Consumer Price Index - measures inflation"
            },
            {
                "date": "Monthly",
                "event": "Jobs Report",
                "impact": "high",
                "description": "Non-farm payrolls - first Friday of month"
            },
            {
                "date": "Every 6 weeks",
                "event": "FOMC Meeting",
                "impact": "high",
                "description": "Federal Reserve interest rate decision"
            },
            {
                "date": "Quarterly",
                "event": "GDP Report",
                "impact": "medium",
                "description": "Gross Domestic Product growth"
            }
        ]
        return events


# Global singleton
_catalyst_service: Optional[CatalystService] = None


def get_catalyst_service() -> CatalystService:
    """Get the global catalyst service instance."""
    global _catalyst_service
    if _catalyst_service is None:
        _catalyst_service = CatalystService()
    return _catalyst_service
