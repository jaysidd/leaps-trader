"""
News and Sentiment Data Fetcher Service

Fetches news and sentiment data from multiple sources:
- FMP for company news, analyst ratings, insider trades
- NewsAPI for headlines
- Finviz for analyst ratings/news
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from loguru import logger
import aiohttp

from app.config import get_settings
from app.services.cache import cache_service


@dataclass
class NewsItem:
    """Represents a news article."""
    title: str
    source: str
    published: datetime
    url: str
    summary: Optional[str] = None
    sentiment_score: Optional[float] = None  # -1 to 1
    relevance_score: Optional[float] = None  # 0 to 1


@dataclass
class AnalystAction:
    """Represents an analyst rating change."""
    firm: str
    action: str  # upgrade, downgrade, maintain, initiate
    from_rating: Optional[str] = None
    to_rating: str = ""
    price_target: Optional[float] = None
    prior_target: Optional[float] = None
    date: Optional[datetime] = None


@dataclass
class InsiderTrade:
    """Represents an insider transaction."""
    insider_name: str
    title: str
    trade_type: str  # buy, sell
    shares: int
    price: float
    value: float
    date: datetime


@dataclass
class SentimentData:
    """Aggregated sentiment data for a stock."""
    symbol: str
    news_items: List[NewsItem] = field(default_factory=list)
    analyst_actions: List[AnalystAction] = field(default_factory=list)
    insider_trades: List[InsiderTrade] = field(default_factory=list)

    # Computed scores
    news_sentiment_score: float = 0.0  # -100 to 100
    analyst_sentiment_score: float = 0.0  # -100 to 100
    insider_sentiment_score: float = 0.0  # -100 to 100
    overall_sentiment_score: float = 0.0  # 0 to 100

    # Metadata
    news_count_7d: int = 0
    analyst_actions_30d: int = 0
    insider_buys_90d: int = 0
    insider_sells_90d: int = 0
    fetched_at: Optional[datetime] = None


class SentimentFetcher:
    """
    Fetches sentiment data from multiple sources.

    Uses:
    - FMP for company news, analyst ratings, insider trades
    - NewsAPI (free tier: 100 requests/day)
    - Finviz (for analyst ratings)
    """

    CACHE_TTL_NEWS = 1800  # 30 minutes
    CACHE_TTL_SENTIMENT = 3600  # 1 hour

    def __init__(self):
        self.settings = get_settings()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # -------------------------------------------------------------------------
    # Company News (FMP)
    # -------------------------------------------------------------------------

    async def fetch_company_news(self, symbol: str) -> List[NewsItem]:
        """
        Fetch news from FMP (Financial Modeling Prep).
        """
        cache_key = f"fmp_news:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            return [NewsItem(**item) for item in cached]

        try:
            from app.services.data_fetcher.fmp_service import fmp_service
            articles = await fmp_service.get_company_news(symbol, limit=15)

            news_items = []
            for article in articles:
                try:
                    pub_str = article.get('publishedDate', '')
                    pub_time = datetime.fromisoformat(pub_str) if pub_str else datetime.now()

                    news_item = NewsItem(
                        title=article.get('title', ''),
                        source=article.get('site', 'Unknown'),
                        published=pub_time,
                        url=article.get('url', ''),
                        summary=article.get('text', '')[:200] if article.get('text') else None
                    )
                    news_items.append(news_item)
                except Exception as e:
                    logger.debug(f"Error parsing FMP news item: {e}")
                    continue

            # Cache results
            cache_data = [
                {
                    'title': n.title,
                    'source': n.source,
                    'published': n.published.isoformat(),
                    'url': n.url,
                    'summary': n.summary
                }
                for n in news_items
            ]
            cache_service.set(cache_key, cache_data, self.CACHE_TTL_NEWS)

            return news_items

        except Exception as e:
            logger.error(f"Error fetching FMP news for {symbol}: {e}")
            return []

    # Keep old name as alias for backwards compatibility
    async def fetch_yahoo_news(self, symbol: str) -> List[NewsItem]:
        """Alias for fetch_company_news (backwards compatibility)."""
        return await self.fetch_company_news(symbol)

    # -------------------------------------------------------------------------
    # NewsAPI (Optional - requires API key)
    # -------------------------------------------------------------------------

    async def fetch_newsapi_headlines(
        self,
        query: str,
        days_back: int = 7
    ) -> List[NewsItem]:
        """
        Fetch news from NewsAPI.
        Requires NEWSAPI_KEY in config.
        Free tier: 100 requests/day, 1 month old news max.
        """
        api_key = getattr(self.settings, 'NEWSAPI_KEY', None)
        if not api_key:
            return []

        cache_key = f"newsapi:{query}:{days_back}"
        cached = cache_service.get(cache_key)
        if cached:
            return [NewsItem(**item) for item in cached]

        try:
            session = await self._get_session()

            from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

            url = "https://newsapi.org/v2/everything"
            params = {
                'q': query,
                'from': from_date,
                'sortBy': 'relevancy',
                'language': 'en',
                'pageSize': 20,
                'apiKey': api_key
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"NewsAPI returned status {response.status}")
                    return []

                data = await response.json()

                if data.get('status') != 'ok':
                    logger.warning(f"NewsAPI error: {data.get('message')}")
                    return []

                news_items = []
                for article in data.get('articles', []):
                    try:
                        pub_str = article.get('publishedAt', '')
                        pub_time = datetime.fromisoformat(
                            pub_str.replace('Z', '+00:00')
                        )

                        news_item = NewsItem(
                            title=article.get('title', ''),
                            source=article.get('source', {}).get('name', 'Unknown'),
                            published=pub_time,
                            url=article.get('url', ''),
                            summary=article.get('description')
                        )
                        news_items.append(news_item)
                    except Exception as e:
                        logger.debug(f"Error parsing NewsAPI item: {e}")
                        continue

                # Cache results
                cache_data = [
                    {
                        'title': n.title,
                        'source': n.source,
                        'published': n.published.isoformat(),
                        'url': n.url,
                        'summary': n.summary
                    }
                    for n in news_items
                ]
                cache_service.set(cache_key, cache_data, self.CACHE_TTL_NEWS)

                return news_items

        except Exception as e:
            logger.error(f"Error fetching NewsAPI for {query}: {e}")
            return []

    # -------------------------------------------------------------------------
    # Simple Sentiment Scoring (Keyword-based)
    # -------------------------------------------------------------------------

    def score_headline_sentiment(self, headline: str) -> float:
        """
        Simple keyword-based sentiment scoring.
        Returns -1 to 1 score.

        For production, consider using:
        - FinBERT (finance-specific BERT model)
        - OpenAI/Claude API for more nuanced analysis
        - VADER (general purpose)
        """
        headline_lower = headline.lower()

        # Positive keywords and their weights
        positive_keywords = {
            'surge': 0.8, 'soar': 0.8, 'jump': 0.6, 'rally': 0.7,
            'beat': 0.6, 'beats': 0.6, 'exceed': 0.6, 'exceeds': 0.6,
            'upgrade': 0.7, 'upgrades': 0.7, 'bullish': 0.7,
            'strong': 0.4, 'growth': 0.3, 'profit': 0.3, 'gains': 0.5,
            'breakthrough': 0.7, 'launch': 0.3, 'partnership': 0.4,
            'acquisition': 0.3, 'record': 0.5, 'outperform': 0.6,
            'buy': 0.5, 'positive': 0.4, 'success': 0.5, 'winner': 0.5,
            'rise': 0.4, 'rises': 0.4, 'raised': 0.4, 'raises': 0.4,
            'higher': 0.3, 'boost': 0.5, 'boosts': 0.5
        }

        # Negative keywords and their weights
        negative_keywords = {
            'crash': -0.9, 'plunge': -0.8, 'tank': -0.7, 'tumble': -0.7,
            'miss': -0.6, 'misses': -0.6, 'disappoints': -0.6,
            'downgrade': -0.7, 'downgrades': -0.7, 'bearish': -0.7,
            'weak': -0.4, 'loss': -0.5, 'losses': -0.5, 'decline': -0.4,
            'decline': -0.4, 'declines': -0.4, 'drops': -0.5, 'drop': -0.5,
            'fall': -0.4, 'falls': -0.4, 'fell': -0.5,
            'lawsuit': -0.5, 'investigation': -0.5, 'fraud': -0.8,
            'recall': -0.6, 'warning': -0.5, 'concern': -0.3,
            'sell': -0.4, 'negative': -0.4, 'failure': -0.6,
            'lower': -0.3, 'cuts': -0.4, 'cut': -0.4, 'layoffs': -0.6
        }

        # Calculate score
        score = 0.0
        word_count = 0

        for word, weight in positive_keywords.items():
            if word in headline_lower:
                score += weight
                word_count += 1

        for word, weight in negative_keywords.items():
            if word in headline_lower:
                score += weight  # weight is already negative
                word_count += 1

        # Normalize to -1 to 1
        if word_count > 0:
            score = max(-1.0, min(1.0, score / max(word_count, 1)))

        return score

    # -------------------------------------------------------------------------
    # Analyst Ratings (from FMP)
    # -------------------------------------------------------------------------

    async def fetch_analyst_info(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch analyst recommendations and price targets from FMP.
        """
        cache_key = f"analyst_info:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            return cached

        try:
            from app.services.data_fetcher.fmp_service import fmp_service
            ratings = await fmp_service.get_analyst_ratings(symbol)

            if not ratings:
                return {}

            # Build recommendations from recent grades
            recommendations = None
            recent_grades = ratings.get('recent_grades', [])
            if recent_grades:
                recommendations = recent_grades[:10]

            # Build price targets from FMP data
            consensus = ratings.get('consensus', {})
            price_targets = {
                'current': consensus.get('current_price'),
                'target_mean': consensus.get('price_target'),
                'target_high': consensus.get('price_target_high'),
                'target_low': consensus.get('price_target_low'),
                'num_analysts': consensus.get('num_analysts'),
                'recommendation': consensus.get('consensus'),
                'recommendation_mean': consensus.get('recommendation_mean')
            }

            result = {
                'recommendations': recommendations,
                'price_targets': price_targets
            }

            cache_service.set(cache_key, result, self.CACHE_TTL_SENTIMENT)
            return result

        except Exception as e:
            logger.error(f"Error fetching analyst info for {symbol}: {e}")
            return {}

    # -------------------------------------------------------------------------
    # Insider Trading (from FMP)
    # -------------------------------------------------------------------------

    async def fetch_insider_trades(self, symbol: str) -> List[InsiderTrade]:
        """
        Fetch recent insider transactions from FMP.
        """
        cache_key = f"insider_trades:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            return [InsiderTrade(**trade) for trade in cached]

        try:
            from app.services.data_fetcher.fmp_service import fmp_service
            raw_trades = await fmp_service.get_insider_trades(symbol, limit=20)

            if not raw_trades:
                return []

            trades = []
            for row in raw_trades:
                try:
                    trade_type = row.get('trade_type', '').lower()
                    if trade_type not in ('buy', 'sell'):
                        continue

                    shares = abs(int(row.get('shares', 0)))
                    price = abs(float(row.get('price', 0)))
                    value = abs(float(row.get('value', 0)))
                    if value == 0 and shares > 0 and price > 0:
                        value = shares * price

                    date_str = row.get('date', '')
                    try:
                        date = datetime.fromisoformat(date_str) if date_str else datetime.now()
                    except (ValueError, TypeError):
                        date = datetime.now()

                    trade = InsiderTrade(
                        insider_name=row.get('insider_name', 'Unknown'),
                        title=row.get('title', ''),
                        trade_type=trade_type,
                        shares=shares,
                        price=price,
                        value=value,
                        date=date
                    )
                    trades.append(trade)
                except Exception as e:
                    logger.debug(f"Error parsing insider trade: {e}")
                    continue

            # Cache results
            cache_data = [
                {
                    'insider_name': t.insider_name,
                    'title': t.title,
                    'trade_type': t.trade_type,
                    'shares': t.shares,
                    'price': t.price,
                    'value': t.value,
                    'date': t.date.isoformat() if isinstance(t.date, datetime) else str(t.date)
                }
                for t in trades
            ]
            cache_service.set(cache_key, cache_data, self.CACHE_TTL_SENTIMENT)

            return trades

        except Exception as e:
            logger.error(f"Error fetching insider trades for {symbol}: {e}")
            return []

    # -------------------------------------------------------------------------
    # Aggregate Sentiment Data
    # -------------------------------------------------------------------------

    async def get_sentiment_data(
        self,
        symbol: str,
        company_name: Optional[str] = None
    ) -> SentimentData:
        """
        Get comprehensive sentiment data for a stock.
        Aggregates news, analyst, and insider data.
        """
        cache_key = f"sentiment_data:{symbol}"
        cached = cache_service.get(cache_key)
        if cached:
            # Reconstruct SentimentData from cache
            data = SentimentData(symbol=symbol)
            data.news_sentiment_score = cached.get('news_sentiment_score', 0)
            data.analyst_sentiment_score = cached.get('analyst_sentiment_score', 0)
            data.insider_sentiment_score = cached.get('insider_sentiment_score', 0)
            data.overall_sentiment_score = cached.get('overall_sentiment_score', 0)
            data.news_count_7d = cached.get('news_count_7d', 0)
            data.analyst_actions_30d = cached.get('analyst_actions_30d', 0)
            data.insider_buys_90d = cached.get('insider_buys_90d', 0)
            data.insider_sells_90d = cached.get('insider_sells_90d', 0)
            return data

        # Fetch all data concurrently
        news_task = self.fetch_company_news(symbol)
        analyst_task = self.fetch_analyst_info(symbol)
        insider_task = self.fetch_insider_trades(symbol)

        # Also try NewsAPI if we have company name
        newsapi_task = None
        if company_name:
            newsapi_task = self.fetch_newsapi_headlines(
                f"{symbol} OR {company_name}",
                days_back=7
            )

        # Gather results
        results = await asyncio.gather(
            news_task,
            analyst_task,
            insider_task,
            newsapi_task if newsapi_task else asyncio.sleep(0),
            return_exceptions=True
        )

        fmp_news = results[0] if not isinstance(results[0], Exception) else []
        analyst_info = results[1] if not isinstance(results[1], Exception) else {}
        insider_trades = results[2] if not isinstance(results[2], Exception) else []
        newsapi_news = results[3] if newsapi_task and not isinstance(results[3], Exception) else []

        # Combine news sources
        all_news = list(fmp_news) + list(newsapi_news or [])

        # Score news sentiment
        for news_item in all_news:
            news_item.sentiment_score = self.score_headline_sentiment(news_item.title)

        # Calculate aggregate scores
        sentiment_data = SentimentData(
            symbol=symbol,
            news_items=all_news,
            insider_trades=insider_trades if isinstance(insider_trades, list) else [],
            fetched_at=datetime.now()
        )

        # News sentiment score (-100 to 100)
        if all_news:
            avg_sentiment = sum(n.sentiment_score or 0 for n in all_news) / len(all_news)
            sentiment_data.news_sentiment_score = avg_sentiment * 100
            sentiment_data.news_count_7d = len(all_news)

        # Analyst sentiment score
        if analyst_info:
            price_targets = analyst_info.get('price_targets', {})
            rec_mean = price_targets.get('recommendation_mean')

            # recommendationMean: 1 = Strong Buy, 5 = Sell
            if rec_mean:
                # Convert to -100 to 100 scale
                # 1 = 100 (strong buy), 3 = 0 (hold), 5 = -100 (sell)
                sentiment_data.analyst_sentiment_score = (3 - rec_mean) * 50

            # Count recent recommendations
            recs = analyst_info.get('recommendations', [])
            if recs:
                sentiment_data.analyst_actions_30d = len(recs)

        # Insider sentiment score
        if insider_trades:
            buys = [t for t in insider_trades if t.trade_type == 'buy']
            sells = [t for t in insider_trades if t.trade_type == 'sell']

            sentiment_data.insider_buys_90d = len(buys)
            sentiment_data.insider_sells_90d = len(sells)

            # Calculate value-weighted insider sentiment
            total_buy_value = sum(t.value for t in buys)
            total_sell_value = sum(t.value for t in sells)
            total_value = total_buy_value + total_sell_value

            if total_value > 0:
                # More buys = positive, more sells = negative
                buy_ratio = total_buy_value / total_value
                sentiment_data.insider_sentiment_score = (buy_ratio - 0.5) * 200

        # Overall sentiment (weighted average)
        weights = {
            'news': 0.4,
            'analyst': 0.4,
            'insider': 0.2
        }

        weighted_sum = (
            sentiment_data.news_sentiment_score * weights['news'] +
            sentiment_data.analyst_sentiment_score * weights['analyst'] +
            sentiment_data.insider_sentiment_score * weights['insider']
        )

        # Convert to 0-100 scale
        sentiment_data.overall_sentiment_score = max(0, min(100, 50 + weighted_sum / 2))

        # Cache the result
        cache_data = {
            'news_sentiment_score': sentiment_data.news_sentiment_score,
            'analyst_sentiment_score': sentiment_data.analyst_sentiment_score,
            'insider_sentiment_score': sentiment_data.insider_sentiment_score,
            'overall_sentiment_score': sentiment_data.overall_sentiment_score,
            'news_count_7d': sentiment_data.news_count_7d,
            'analyst_actions_30d': sentiment_data.analyst_actions_30d,
            'insider_buys_90d': sentiment_data.insider_buys_90d,
            'insider_sells_90d': sentiment_data.insider_sells_90d
        }
        cache_service.set(cache_key, cache_data, self.CACHE_TTL_SENTIMENT)

        return sentiment_data


# Global singleton
_sentiment_fetcher: Optional[SentimentFetcher] = None


def get_sentiment_fetcher() -> SentimentFetcher:
    """Get the global sentiment fetcher instance."""
    global _sentiment_fetcher
    if _sentiment_fetcher is None:
        _sentiment_fetcher = SentimentFetcher()
    return _sentiment_fetcher
