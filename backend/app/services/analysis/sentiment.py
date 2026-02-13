"""
Sentiment Analysis Service

Combines data from multiple sources to produce a comprehensive
sentiment score for stock analysis.

Scoring Components:
- News sentiment (headlines, tone)
- Analyst ratings (upgrades/downgrades, price targets)
- Insider activity (buys vs sells)
- Catalyst timing (earnings proximity)
- Social sentiment (future enhancement)
"""

from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

from app.services.data_fetcher.sentiment import (
    SentimentFetcher,
    SentimentData,
    get_sentiment_fetcher
)
from app.services.analysis.catalyst import (
    CatalystService,
    CatalystCalendar,
    get_catalyst_service
)
from app.services.cache import cache_service


@dataclass
class SentimentScore:
    """
    Comprehensive sentiment score for a stock.
    All scores are 0-100 (higher = more bullish).
    """
    symbol: str

    # Component scores (0-100)
    news_score: float = 50.0
    analyst_score: float = 50.0
    insider_score: float = 50.0
    catalyst_score: float = 50.0

    # Overall sentiment (0-100)
    overall_score: float = 50.0
    sentiment_label: str = "neutral"  # bearish, neutral, bullish

    # Metadata
    news_count: int = 0
    analyst_rating: Optional[str] = None
    price_target_upside: Optional[float] = None
    days_to_earnings: Optional[int] = None
    insider_buy_sell_ratio: Optional[float] = None

    # Flags
    has_recent_upgrade: bool = False
    has_recent_downgrade: bool = False
    insider_buying: bool = False
    insider_selling: bool = False
    earnings_risk: bool = False

    # Explanations
    bullish_signals: list = None
    bearish_signals: list = None
    recommendation: str = ""

    def __post_init__(self):
        if self.bullish_signals is None:
            self.bullish_signals = []
        if self.bearish_signals is None:
            self.bearish_signals = []


class SentimentAnalyzer:
    """
    Analyzes and scores sentiment from multiple data sources.
    """

    CACHE_TTL = 1800  # 30 minutes

    # Weights for overall score
    WEIGHTS = {
        'news': 0.25,
        'analyst': 0.35,
        'insider': 0.20,
        'catalyst': 0.20
    }

    def __init__(self):
        self.sentiment_fetcher = get_sentiment_fetcher()
        self.catalyst_service = get_catalyst_service()

    async def analyze(
        self,
        symbol: str,
        company_name: Optional[str] = None,
        current_price: Optional[float] = None
    ) -> SentimentScore:
        """
        Perform comprehensive sentiment analysis for a stock.

        Args:
            symbol: Stock ticker symbol
            company_name: Company name for news search
            current_price: Current stock price for target calculations

        Returns:
            SentimentScore with all component scores
        """
        cache_key = f"sentiment_score:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            return SentimentScore(**cached)

        score = SentimentScore(symbol=symbol)

        try:
            # Fetch sentiment data and catalyst calendar concurrently
            import asyncio

            sentiment_task = self.sentiment_fetcher.get_sentiment_data(
                symbol, company_name
            )
            catalyst_task = self.catalyst_service.get_catalyst_calendar(
                symbol, company_name
            )

            sentiment_data, catalyst_calendar = await asyncio.gather(
                sentiment_task, catalyst_task
            )

            # Score each component
            self._score_news(score, sentiment_data)
            self._score_analyst(score, sentiment_data, current_price)
            self._score_insider(score, sentiment_data)
            self._score_catalyst(score, catalyst_calendar)

            # Calculate overall score
            self._calculate_overall(score)

            # Generate recommendation
            self._generate_recommendation(score, catalyst_calendar)

            # Cache result
            cache_data = {
                'symbol': score.symbol,
                'news_score': score.news_score,
                'analyst_score': score.analyst_score,
                'insider_score': score.insider_score,
                'catalyst_score': score.catalyst_score,
                'overall_score': score.overall_score,
                'sentiment_label': score.sentiment_label,
                'news_count': score.news_count,
                'analyst_rating': score.analyst_rating,
                'price_target_upside': score.price_target_upside,
                'days_to_earnings': score.days_to_earnings,
                'insider_buy_sell_ratio': score.insider_buy_sell_ratio,
                'has_recent_upgrade': score.has_recent_upgrade,
                'has_recent_downgrade': score.has_recent_downgrade,
                'insider_buying': score.insider_buying,
                'insider_selling': score.insider_selling,
                'earnings_risk': score.earnings_risk,
                'bullish_signals': score.bullish_signals,
                'bearish_signals': score.bearish_signals,
                'recommendation': score.recommendation
            }
            cache_service.set(cache_key, cache_data, self.CACHE_TTL)

            return score

        except Exception as e:
            logger.error(f"Error analyzing sentiment for {symbol}: {e}")
            return score

    def _score_news(self, score: SentimentScore, data: SentimentData):
        """Score news sentiment (0-100)."""
        if not data.news_items:
            score.news_score = 50.0  # Neutral if no news
            return

        score.news_count = len(data.news_items)

        # Convert -100 to 100 scale to 0-100
        raw_score = data.news_sentiment_score  # -100 to 100
        score.news_score = (raw_score + 100) / 2  # 0 to 100

        # Add signals
        if raw_score >= 30:
            score.bullish_signals.append(f"Positive news sentiment ({score.news_count} articles)")
        elif raw_score <= -30:
            score.bearish_signals.append(f"Negative news sentiment ({score.news_count} articles)")

    def _score_analyst(
        self,
        score: SentimentScore,
        data: SentimentData,
        current_price: Optional[float]
    ):
        """Score analyst sentiment (0-100)."""
        # Convert -100 to 100 scale to 0-100
        raw_score = data.analyst_sentiment_score  # -100 to 100
        score.analyst_score = (raw_score + 100) / 2  # 0 to 100

        # Track rating changes
        if data.analyst_actions:
            for action in data.analyst_actions[:5]:
                action_type = action.action.lower() if hasattr(action, 'action') else ''
                if 'upgrade' in action_type:
                    score.has_recent_upgrade = True
                    score.bullish_signals.append("Recent analyst upgrade")
                elif 'downgrade' in action_type:
                    score.has_recent_downgrade = True
                    score.bearish_signals.append("Recent analyst downgrade")

        # Add signals based on score
        if score.analyst_score >= 70:
            score.bullish_signals.append("Strong analyst consensus (buy rating)")
        elif score.analyst_score <= 30:
            score.bearish_signals.append("Weak analyst consensus (sell rating)")

    def _score_insider(self, score: SentimentScore, data: SentimentData):
        """Score insider activity (0-100)."""
        buys = data.insider_buys_90d
        sells = data.insider_sells_90d
        total = buys + sells

        if total == 0:
            score.insider_score = 50.0  # Neutral if no activity
            return

        # Calculate buy ratio
        buy_ratio = buys / total
        score.insider_buy_sell_ratio = buy_ratio

        # Convert to 0-100 score
        # 100% buys = 100, 100% sells = 0, 50/50 = 50
        score.insider_score = buy_ratio * 100

        # Set flags and signals
        if buy_ratio >= 0.7:
            score.insider_buying = True
            score.bullish_signals.append(f"Strong insider buying ({buys} buys vs {sells} sells)")
        elif buy_ratio <= 0.3:
            score.insider_selling = True
            score.bearish_signals.append(f"Heavy insider selling ({sells} sells vs {buys} buys)")

    def _score_catalyst(self, score: SentimentScore, calendar: CatalystCalendar):
        """Score catalyst timing (0-100)."""
        score.catalyst_score = calendar.catalyst_score
        score.days_to_earnings = calendar.days_to_earnings

        # Earnings risk flag
        if calendar.days_to_earnings is not None and calendar.days_to_earnings <= 14:
            score.earnings_risk = True
            score.bearish_signals.append(
                f"Earnings in {calendar.days_to_earnings} days (IV risk)"
            )

        # Favorable catalyst timing
        if calendar.catalyst_score >= 70:
            score.bullish_signals.append("Favorable catalyst timing")

    def _calculate_overall(self, score: SentimentScore):
        """Calculate weighted overall sentiment score."""
        weighted_sum = (
            score.news_score * self.WEIGHTS['news'] +
            score.analyst_score * self.WEIGHTS['analyst'] +
            score.insider_score * self.WEIGHTS['insider'] +
            score.catalyst_score * self.WEIGHTS['catalyst']
        )

        score.overall_score = round(weighted_sum, 1)

        # Set sentiment label
        if score.overall_score >= 65:
            score.sentiment_label = "bullish"
        elif score.overall_score <= 35:
            score.sentiment_label = "bearish"
        else:
            score.sentiment_label = "neutral"

    def _generate_recommendation(
        self,
        score: SentimentScore,
        calendar: CatalystCalendar
    ):
        """Generate a sentiment-based recommendation."""
        parts = []

        # Overall sentiment direction
        if score.sentiment_label == "bullish":
            parts.append("Sentiment is bullish")
        elif score.sentiment_label == "bearish":
            parts.append("Sentiment is bearish")
        else:
            parts.append("Sentiment is neutral")

        # Highlight strongest signal
        if score.has_recent_upgrade:
            parts.append("with recent analyst upgrades")
        elif score.insider_buying:
            parts.append("with notable insider buying")
        elif score.has_recent_downgrade:
            parts.append("with analyst downgrades")
        elif score.insider_selling:
            parts.append("with insider selling")

        # Catalyst warning
        if score.earnings_risk:
            parts.append(f"- CAUTION: earnings in {score.days_to_earnings} days")
        elif calendar.recommendation:
            parts.append(f"- {calendar.recommendation}")

        score.recommendation = ". ".join(parts) if parts else "Insufficient data for recommendation"

    def get_sentiment_summary(self, score: SentimentScore) -> Dict[str, Any]:
        """
        Get a summary dict suitable for API response.
        """
        return {
            'symbol': score.symbol,
            'overall_score': score.overall_score,
            'sentiment_label': score.sentiment_label,
            'scores': {
                'news': score.news_score,
                'analyst': score.analyst_score,
                'insider': score.insider_score,
                'catalyst': score.catalyst_score
            },
            'metadata': {
                'news_count': score.news_count,
                'analyst_rating': score.analyst_rating,
                'price_target_upside': score.price_target_upside,
                'days_to_earnings': score.days_to_earnings,
                'insider_buy_sell_ratio': score.insider_buy_sell_ratio
            },
            'flags': {
                'has_recent_upgrade': score.has_recent_upgrade,
                'has_recent_downgrade': score.has_recent_downgrade,
                'insider_buying': score.insider_buying,
                'insider_selling': score.insider_selling,
                'earnings_risk': score.earnings_risk
            },
            'signals': {
                'bullish': score.bullish_signals,
                'bearish': score.bearish_signals
            },
            'recommendation': score.recommendation
        }


# Global singleton
_sentiment_analyzer: Optional[SentimentAnalyzer] = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """Get the global sentiment analyzer instance."""
    global _sentiment_analyzer
    if _sentiment_analyzer is None:
        _sentiment_analyzer = SentimentAnalyzer()
    return _sentiment_analyzer
