"""
News Feed Service - Aggregates financial news from multiple sources
including Finnhub, Alpha Vantage, and economic calendars
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from loguru import logger

from app.config import get_settings
from app.services.cache import cache


class NewsImpact(str, Enum):
    """Impact level for news/events"""
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


class NewsCategory(str, Enum):
    """News category types"""
    EARNINGS = 'earnings'
    ECONOMIC = 'economic'
    FED = 'fed'
    COMPANY = 'company'
    MARKET = 'market'
    CRYPTO = 'crypto'
    POLITICAL = 'political'
    OTHER = 'other'


@dataclass
class NewsItem:
    """A news article or event"""
    id: str
    headline: str
    summary: str
    source: str
    url: str
    published_at: str
    category: str
    impact: str
    related_symbols: List[str]
    sentiment: Optional[float] = None  # -1 to 1


@dataclass
class EconomicEvent:
    """An economic calendar event"""
    id: str
    name: str
    country: str
    datetime: str
    impact: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None


class NewsFeedService:
    """
    Service for aggregating financial news and economic events.
    Uses Finnhub (free tier) and Alpha Vantage for news data.
    """

    # Finnhub endpoints (free tier: 60 calls/min)
    FINNHUB_BASE = "https://finnhub.io/api/v1"

    # Alpha Vantage endpoint (free tier: 25 calls/day)
    ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"

    # High-impact event keywords
    HIGH_IMPACT_KEYWORDS = [
        'fed', 'fomc', 'interest rate', 'rate decision', 'powell',
        'cpi', 'inflation', 'employment', 'jobs report', 'nonfarm',
        'gdp', 'recession', 'earnings',
    ]

    MEDIUM_IMPACT_KEYWORDS = [
        'earnings', 'guidance', 'upgrade', 'downgrade',
        'merger', 'acquisition', 'ipo', 'split',
        'dividend', 'buyback',
    ]

    def __init__(self):
        self.settings = get_settings()
        self._session: Optional[aiohttp.ClientSession] = None
        self._finnhub_key = getattr(self.settings, 'FINNHUB_API_KEY', None)
        self._alpha_vantage_key = self.settings.ALPHA_VANTAGE_API_KEY

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()

    # -------------------------------------------------------------------------
    # FINNHUB NEWS (Primary source - 60 calls/min free)
    # -------------------------------------------------------------------------

    async def _fetch_finnhub_general_news(self, category: str = 'general') -> List[Dict]:
        """
        Fetch general market news from Finnhub.
        Categories: general, forex, crypto, merger
        """
        if not self._finnhub_key:
            return []

        try:
            session = await self._get_session()

            params = {
                'category': category,
                'token': self._finnhub_key,
            }

            async with session.get(f"{self.FINNHUB_BASE}/news", params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"Finnhub news returned status {response.status}")
                    return []

        except Exception as e:
            logger.error(f"Error fetching Finnhub news: {e}")
            return []

    async def _fetch_finnhub_company_news(self, symbol: str, days: int = 7) -> List[Dict]:
        """
        Fetch company-specific news from Finnhub.
        """
        if not self._finnhub_key:
            return []

        try:
            session = await self._get_session()

            from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')

            params = {
                'symbol': symbol,
                'from': from_date,
                'to': to_date,
                'token': self._finnhub_key,
            }

            async with session.get(f"{self.FINNHUB_BASE}/company-news", params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return []

        except Exception as e:
            logger.error(f"Error fetching Finnhub company news for {symbol}: {e}")
            return []

    async def _fetch_finnhub_calendar(self) -> Dict[str, Any]:
        """
        Fetch economic calendar from Finnhub.
        """
        if not self._finnhub_key:
            return {}

        try:
            session = await self._get_session()

            params = {
                'token': self._finnhub_key,
            }

            async with session.get(f"{self.FINNHUB_BASE}/calendar/economic", params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {}

        except Exception as e:
            logger.error(f"Error fetching Finnhub calendar: {e}")
            return {}

    async def _fetch_finnhub_earnings(self, from_date: str = None, to_date: str = None) -> List[Dict]:
        """
        Fetch earnings calendar from Finnhub.
        """
        if not self._finnhub_key:
            return []

        try:
            session = await self._get_session()

            if not from_date:
                from_date = datetime.now().strftime('%Y-%m-%d')
            if not to_date:
                to_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')

            params = {
                'from': from_date,
                'to': to_date,
                'token': self._finnhub_key,
            }

            async with session.get(f"{self.FINNHUB_BASE}/calendar/earnings", params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('earningsCalendar', [])
                else:
                    return []

        except Exception as e:
            logger.error(f"Error fetching Finnhub earnings: {e}")
            return []

    # -------------------------------------------------------------------------
    # ALPHA VANTAGE NEWS (Secondary source - 25 calls/day free)
    # -------------------------------------------------------------------------

    async def _fetch_alpha_vantage_news(self, tickers: str = None, topics: str = None) -> List[Dict]:
        """
        Fetch news with sentiment from Alpha Vantage.
        Limited to 25 calls/day on free tier.
        """
        if not self._alpha_vantage_key or self._alpha_vantage_key == 'demo':
            return []

        try:
            session = await self._get_session()

            params = {
                'function': 'NEWS_SENTIMENT',
                'apikey': self._alpha_vantage_key,
            }

            if tickers:
                params['tickers'] = tickers
            if topics:
                params['topics'] = topics

            async with session.get(self.ALPHA_VANTAGE_BASE, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('feed', [])
                else:
                    return []

        except Exception as e:
            logger.error(f"Error fetching Alpha Vantage news: {e}")
            return []

    # -------------------------------------------------------------------------
    # NEWS PROCESSING
    # -------------------------------------------------------------------------

    def _determine_impact(self, headline: str, summary: str = '') -> str:
        """
        Determine the impact level of a news item.
        """
        text = f"{headline} {summary}".lower()

        for keyword in self.HIGH_IMPACT_KEYWORDS:
            if keyword in text:
                return NewsImpact.HIGH.value

        for keyword in self.MEDIUM_IMPACT_KEYWORDS:
            if keyword in text:
                return NewsImpact.MEDIUM.value

        return NewsImpact.LOW.value

    def _categorize_news(self, headline: str, summary: str = '', source: str = '') -> str:
        """
        Categorize news item.
        """
        text = f"{headline} {summary}".lower()

        if any(kw in text for kw in ['fed', 'fomc', 'powell', 'rate decision', 'federal reserve']):
            return NewsCategory.FED.value
        elif any(kw in text for kw in ['earnings', 'eps', 'revenue report', 'quarterly results']):
            return NewsCategory.EARNINGS.value
        elif any(kw in text for kw in ['cpi', 'gdp', 'jobs', 'employment', 'inflation', 'economic']):
            return NewsCategory.ECONOMIC.value
        elif any(kw in text for kw in ['bitcoin', 'crypto', 'ethereum', 'btc']):
            return NewsCategory.CRYPTO.value
        elif any(kw in text for kw in ['trump', 'biden', 'election', 'congress', 'tariff']):
            return NewsCategory.POLITICAL.value
        elif any(kw in text for kw in ['market', 's&p', 'dow', 'nasdaq', 'stocks']):
            return NewsCategory.MARKET.value
        else:
            return NewsCategory.COMPANY.value

    def _format_finnhub_news(self, news_list: List[Dict]) -> List[Dict]:
        """
        Format Finnhub news into standardized format.
        """
        formatted = []

        for item in news_list:
            headline = item.get('headline', '')
            summary = item.get('summary', '')

            formatted.append({
                'id': str(item.get('id', hash(headline))),
                'headline': headline,
                'summary': summary[:300] + '...' if len(summary) > 300 else summary,
                'source': item.get('source', 'Unknown'),
                'url': item.get('url', ''),
                'published_at': datetime.fromtimestamp(item.get('datetime', 0)).isoformat() if item.get('datetime') else None,
                'category': self._categorize_news(headline, summary),
                'impact': self._determine_impact(headline, summary),
                'related_symbols': [item.get('related', '')] if item.get('related') else [],
                'image': item.get('image'),
                'sentiment': None,
            })

        return formatted

    def _format_alpha_vantage_news(self, news_list: List[Dict]) -> List[Dict]:
        """
        Format Alpha Vantage news into standardized format.
        """
        formatted = []

        for item in news_list:
            headline = item.get('title', '')
            summary = item.get('summary', '')

            # Extract ticker symbols
            tickers = [t.get('ticker', '') for t in item.get('ticker_sentiment', [])]

            # Get overall sentiment
            sentiment = float(item.get('overall_sentiment_score', 0))

            formatted.append({
                'id': str(hash(headline)),
                'headline': headline,
                'summary': summary[:300] + '...' if len(summary) > 300 else summary,
                'source': item.get('source', 'Unknown'),
                'url': item.get('url', ''),
                'published_at': item.get('time_published'),
                'category': self._categorize_news(headline, summary),
                'impact': self._determine_impact(headline, summary),
                'related_symbols': tickers[:5],  # Limit to 5 symbols
                'image': item.get('banner_image'),
                'sentiment': sentiment,
                'sentiment_label': item.get('overall_sentiment_label'),
            })

        return formatted

    # -------------------------------------------------------------------------
    # PUBLIC API METHODS
    # -------------------------------------------------------------------------

    async def get_market_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get general market news aggregated from multiple sources.
        """
        cache_key = "news:market"
        cached = cache.get(cache_key)
        if cached:
            return cached[:limit]

        all_news = []

        # Fetch from Finnhub (primary source)
        finnhub_news = await self._fetch_finnhub_general_news('general')
        all_news.extend(self._format_finnhub_news(finnhub_news))

        # Add crypto news
        crypto_news = await self._fetch_finnhub_general_news('crypto')
        all_news.extend(self._format_finnhub_news(crypto_news))

        # Sort by published date (newest first)
        all_news.sort(key=lambda x: x.get('published_at', ''), reverse=True)

        # Remove duplicates by headline
        seen = set()
        unique_news = []
        for item in all_news:
            if item['headline'] not in seen:
                seen.add(item['headline'])
                unique_news.append(item)

        # Cache for 5 minutes
        cache.set(cache_key, unique_news, ttl=300)

        return unique_news[:limit]

    async def get_company_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get news for a specific company/symbol.
        """
        cache_key = f"news:company:{symbol}"
        cached = cache.get(cache_key)
        if cached:
            return cached[:limit]

        finnhub_news = await self._fetch_finnhub_company_news(symbol)
        formatted = self._format_finnhub_news(finnhub_news)

        # Cache for 10 minutes
        cache.set(cache_key, formatted, ttl=600)

        return formatted[:limit]

    async def get_economic_calendar(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """
        Get upcoming economic events.
        """
        cache_key = f"news:economic_calendar:{days_ahead}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        calendar_data = await self._fetch_finnhub_calendar()
        events = calendar_data.get('economicCalendar', [])

        # Format and filter events
        formatted_events = []
        cutoff = datetime.now() + timedelta(days=days_ahead)

        for event in events:
            event_time = event.get('time', '')
            if event_time:
                try:
                    event_dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                    if event_dt > cutoff:
                        continue
                except:
                    pass

            # Determine impact
            impact_raw = event.get('impact', 'low')
            if isinstance(impact_raw, int):
                impact = 'high' if impact_raw >= 3 else ('medium' if impact_raw >= 2 else 'low')
            else:
                impact = impact_raw

            formatted_events.append({
                'id': str(hash(f"{event.get('event', '')}{event_time}")),
                'name': event.get('event', 'Unknown Event'),
                'country': event.get('country', 'US'),
                'datetime': event_time,
                'impact': impact,
                'actual': event.get('actual'),
                'forecast': event.get('estimate'),
                'previous': event.get('prev'),
                'unit': event.get('unit', ''),
            })

        # Sort by date
        formatted_events.sort(key=lambda x: x.get('datetime', ''))

        # Cache for 1 hour
        cache.set(cache_key, formatted_events, ttl=3600)

        return formatted_events

    async def get_earnings_calendar(self, days_ahead: int = 14) -> List[Dict[str, Any]]:
        """
        Get upcoming earnings announcements.
        """
        cache_key = f"news:earnings_calendar:{days_ahead}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        to_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        earnings = await self._fetch_finnhub_earnings(to_date=to_date)

        # Format earnings
        formatted = []
        for item in earnings:
            formatted.append({
                'symbol': item.get('symbol', ''),
                'date': item.get('date', ''),
                'time': item.get('hour', 'Unknown'),  # 'bmo' (before market open), 'amc' (after market close)
                'eps_estimate': item.get('epsEstimate'),
                'eps_actual': item.get('epsActual'),
                'revenue_estimate': item.get('revenueEstimate'),
                'revenue_actual': item.get('revenueActual'),
                'quarter': item.get('quarter'),
                'year': item.get('year'),
            })

        # Sort by date
        formatted.sort(key=lambda x: x.get('date', ''))

        # Cache for 1 hour
        cache.set(cache_key, formatted, ttl=3600)

        return formatted

    async def get_catalyst_feed(self, limit: int = 20) -> Dict[str, Any]:
        """
        Get combined catalyst feed for Command Center.
        Combines news, economic events, and earnings into prioritized feed.
        """
        cache_key = "news:catalyst_feed"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Fetch all data concurrently
        news_task = asyncio.create_task(self.get_market_news(limit=30))
        econ_task = asyncio.create_task(self.get_economic_calendar(days_ahead=7))
        earnings_task = asyncio.create_task(self.get_earnings_calendar(days_ahead=14))

        news = await news_task
        economic = await econ_task
        earnings = await earnings_task

        # Build unified feed
        feed_items = []

        # Add high-impact news
        high_impact_news = [n for n in news if n['impact'] == 'high']
        for item in high_impact_news[:5]:
            feed_items.append({
                'type': 'news',
                'icon': '📰',
                'title': item['headline'],
                'subtitle': item['source'],
                'datetime': item['published_at'],
                'impact': item['impact'],
                'category': item['category'],
                'url': item['url'],
                'symbols': item['related_symbols'],
            })

        # Add upcoming high-impact economic events
        today = datetime.now().date()
        for event in economic:
            if event['impact'] == 'high':
                try:
                    event_date = datetime.fromisoformat(event['datetime'].replace('Z', '+00:00')).date()
                    days_until = (event_date - today).days
                    if 0 <= days_until <= 3:
                        time_label = 'TODAY' if days_until == 0 else f'In {days_until} day{"s" if days_until > 1 else ""}'
                        feed_items.append({
                            'type': 'economic',
                            'icon': '🏛️',
                            'title': event['name'],
                            'subtitle': f"{event['country']} | {time_label}",
                            'datetime': event['datetime'],
                            'impact': event['impact'],
                            'category': 'economic',
                            'forecast': event['forecast'],
                            'previous': event['previous'],
                        })
                except:
                    continue

        # Add upcoming major earnings (next 3 days)
        for earning in earnings[:20]:
            try:
                earning_date = datetime.strptime(earning['date'], '%Y-%m-%d').date()
                days_until = (earning_date - today).days
                if 0 <= days_until <= 3:
                    time_label = earning['time'].upper() if earning['time'] != 'Unknown' else ''
                    feed_items.append({
                        'type': 'earnings',
                        'icon': '💼',
                        'title': f"{earning['symbol']} Earnings",
                        'subtitle': f"{earning['date']} {time_label}",
                        'datetime': earning['date'],
                        'impact': 'medium',
                        'category': 'earnings',
                        'symbol': earning['symbol'],
                        'eps_estimate': earning['eps_estimate'],
                    })
            except:
                continue

        # Sort by datetime (soonest first for events, newest first for news)
        # For simplicity, sort by impact then datetime
        impact_order = {'high': 0, 'medium': 1, 'low': 2}
        feed_items.sort(key=lambda x: (impact_order.get(x.get('impact', 'low'), 2), x.get('datetime', '')))

        result = {
            'timestamp': datetime.now().isoformat(),
            'feed': feed_items[:limit],
            'summary': {
                'news_count': len(news),
                'high_impact_news': len(high_impact_news),
                'upcoming_events': len([e for e in economic if e['impact'] in ['high', 'medium']]),
                'upcoming_earnings': len(earnings),
            }
        }

        # Cache for 5 minutes
        cache.set(cache_key, result, ttl=300)

        return result

    # -------------------------------------------------------------------------
    # SHORT INTEREST (Finnhub)
    # -------------------------------------------------------------------------

    async def get_short_interest(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get short interest data from Finnhub.

        Returns:
            Dict with short_interest, short_ratio, days_to_cover, etc.
        """
        if not self._finnhub_key:
            return None

        cache_key = f"short_interest:{symbol}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            session = await self._get_session()
            params = {
                'symbol': symbol.upper(),
                'token': self._finnhub_key,
            }

            async with session.get(
                f"{self.FINNHUB_BASE}/stock/short-interest",
                params=params
            ) as response:
                if response.status != 200:
                    logger.warning(f"Finnhub short interest returned {response.status} for {symbol}")
                    return None

                data = await response.json()
                if not data or not isinstance(data, dict):
                    return None

                # Finnhub returns {"data": [...], "symbol": "AAPL"}
                entries = data.get('data', [])
                if not entries:
                    return None

                # Most recent entry
                latest = entries[0]
                result = {
                    'symbol': symbol.upper(),
                    'short_interest': latest.get('shortInterest'),
                    'short_ratio': latest.get('shortRatio'),
                    'days_to_cover': latest.get('daysToCover'),
                    'short_percent_float': latest.get('shortPercentFloat'),
                    'settlement_date': latest.get('settlementDate'),
                    'data_points': len(entries),
                }

                # Cache for 6 hours (short interest updates infrequently)
                cache.set(cache_key, result, ttl=21600)
                return result

        except Exception as e:
            logger.error(f"Error fetching short interest for {symbol}: {e}")
            return None


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_news_feed_service: Optional[NewsFeedService] = None


def get_news_feed_service() -> NewsFeedService:
    """Get the global NewsFeedService instance."""
    global _news_feed_service
    if _news_feed_service is None:
        _news_feed_service = NewsFeedService()
    return _news_feed_service
