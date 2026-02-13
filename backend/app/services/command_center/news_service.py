"""
Financial News Service - Fetches news from multiple free RSS feeds
Sources: Yahoo Finance, CNBC, MarketWatch, Reuters, Bloomberg
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from loguru import logger
import re
import html

from app.services.cache import cache


@dataclass
class NewsItem:
    """A single news article"""
    title: str
    source: str
    url: str
    published_at: datetime
    summary: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None


class FinancialNewsService:
    """
    Service for fetching financial news from multiple RSS feeds.
    Aggregates news from Yahoo Finance, CNBC, MarketWatch, and more.
    """

    # RSS Feed URLs - all free and publicly accessible
    RSS_FEEDS = {
        'yahoo_finance': {
            'url': 'https://finance.yahoo.com/news/rssindex',
            'name': 'Yahoo Finance',
            'icon': '📈',
            'category': 'markets',
        },
        'cnbc_top': {
            'url': 'https://www.cnbc.com/id/100003114/device/rss/rss.html',
            'name': 'CNBC',
            'icon': '📺',
            'category': 'general',
        },
        'cnbc_markets': {
            'url': 'https://www.cnbc.com/id/20910258/device/rss/rss.html',
            'name': 'CNBC Markets',
            'icon': '📊',
            'category': 'markets',
        },
        'cnbc_investing': {
            'url': 'https://www.cnbc.com/id/15839069/device/rss/rss.html',
            'name': 'CNBC Investing',
            'icon': '💰',
            'category': 'investing',
        },
        'marketwatch': {
            'url': 'https://feeds.marketwatch.com/marketwatch/topstories/',
            'name': 'MarketWatch',
            'icon': '📰',
            'category': 'markets',
        },
        'marketwatch_stocks': {
            'url': 'https://feeds.marketwatch.com/marketwatch/StockstoWatch/',
            'name': 'MW Stocks',
            'icon': '📋',
            'category': 'stocks',
        },
        'reuters_business': {
            'url': 'https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best',
            'name': 'Reuters',
            'icon': '🌐',
            'category': 'business',
        },
        'investing_com': {
            'url': 'https://www.investing.com/rss/news.rss',
            'name': 'Investing.com',
            'icon': '📉',
            'category': 'markets',
        },
    }

    # Keywords for filtering market-relevant news
    MARKET_KEYWORDS = [
        'stock', 'market', 'fed', 'rate', 'earnings', 'revenue',
        'gdp', 'inflation', 'jobs', 'employment', 'retail',
        'bitcoin', 'crypto', 'oil', 'gold', 'treasury',
        's&p', 'dow', 'nasdaq', 'rally', 'drop', 'surge',
        'ipo', 'merger', 'acquisition', 'dividend',
        'options', 'calls', 'puts', 'volatility', 'vix',
    ]

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={
                    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                    'User-Agent': 'Mozilla/5.0 (compatible; LEAPS-Trader/1.0)',
                }
            )
        return self._session

    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities"""
        if not text:
            return ""
        # Decode HTML entities
        text = html.unescape(text)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Clean up whitespace
        text = ' '.join(text.split())
        return text[:300] + '...' if len(text) > 300 else text

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various RSS date formats"""
        if not date_str:
            return None

        formats = [
            '%a, %d %b %Y %H:%M:%S %z',  # RFC 822
            '%a, %d %b %Y %H:%M:%S %Z',
            '%Y-%m-%dT%H:%M:%S%z',  # ISO 8601
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%d %b %Y %H:%M:%S',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                # Convert to naive datetime for comparison
                if dt.tzinfo:
                    dt = dt.replace(tzinfo=None)
                return dt
            except ValueError:
                continue

        return None

    async def _fetch_feed(self, feed_key: str) -> List[Dict]:
        """Fetch and parse a single RSS feed"""
        feed_config = self.RSS_FEEDS.get(feed_key)
        if not feed_config:
            return []

        try:
            session = await self._get_session()
            async with session.get(feed_config['url']) as response:
                if response.status != 200:
                    logger.warning(f"Feed {feed_key} returned status {response.status}")
                    return []

                content = await response.text()

                # Parse XML
                try:
                    root = ET.fromstring(content)
                except ET.ParseError as e:
                    logger.warning(f"Failed to parse XML from {feed_key}: {e}")
                    return []

                items = []

                # Handle both RSS and Atom feeds
                # RSS format
                for item in root.findall('.//item'):
                    title = item.find('title')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    description = item.find('description')

                    if title is not None and link is not None:
                        # Try to extract image from various sources
                        image_url = None
                        media_content = item.find('.//{http://search.yahoo.com/mrss/}content')
                        if media_content is not None:
                            image_url = media_content.get('url')
                        if not image_url:
                            enclosure = item.find('enclosure')
                            if enclosure is not None and 'image' in enclosure.get('type', ''):
                                image_url = enclosure.get('url')

                        items.append({
                            'title': self._clean_html(title.text or ''),
                            'url': link.text or '',
                            'published_at': self._parse_date(pub_date.text if pub_date is not None else None),
                            'summary': self._clean_html(description.text if description is not None else ''),
                            'source': feed_config['name'],
                            'source_icon': feed_config['icon'],
                            'category': feed_config['category'],
                            'image_url': image_url,
                        })

                # Atom format (fallback)
                if not items:
                    ns = {'atom': 'http://www.w3.org/2005/Atom'}
                    for entry in root.findall('.//atom:entry', ns):
                        title = entry.find('atom:title', ns)
                        link = entry.find('atom:link', ns)
                        published = entry.find('atom:published', ns) or entry.find('atom:updated', ns)
                        summary = entry.find('atom:summary', ns) or entry.find('atom:content', ns)

                        if title is not None and link is not None:
                            items.append({
                                'title': self._clean_html(title.text or ''),
                                'url': link.get('href', ''),
                                'published_at': self._parse_date(published.text if published is not None else None),
                                'summary': self._clean_html(summary.text if summary is not None else ''),
                                'source': feed_config['name'],
                                'source_icon': feed_config['icon'],
                                'category': feed_config['category'],
                                'image_url': None,
                            })

                logger.debug(f"Fetched {len(items)} items from {feed_key}")
                return items

        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching feed {feed_key}")
            return []
        except Exception as e:
            logger.error(f"Error fetching feed {feed_key}: {e}")
            return []

    async def get_news(self, limit: int = 20, category: Optional[str] = None) -> List[Dict]:
        """
        Get aggregated news from all RSS feeds.

        Args:
            limit: Maximum number of news items to return
            category: Optional filter by category (markets, investing, stocks, general)

        Returns:
            List of news items sorted by date (newest first)
        """
        cache_key = f"news:all:{category or 'all'}:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Fetch from all feeds concurrently
        feeds_to_fetch = list(self.RSS_FEEDS.keys())

        # Filter feeds by category if specified
        if category:
            feeds_to_fetch = [
                k for k, v in self.RSS_FEEDS.items()
                if v['category'] == category
            ]

        tasks = [self._fetch_feed(feed) for feed in feeds_to_fetch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Combine all items
        all_items = []
        for result in results:
            if isinstance(result, list):
                all_items.extend(result)

        # Remove duplicates based on title similarity
        seen_titles = set()
        unique_items = []
        for item in all_items:
            # Normalize title for comparison
            normalized = item['title'].lower()[:50]
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                unique_items.append(item)

        # Filter out old news (older than 24 hours)
        cutoff = datetime.now() - timedelta(hours=24)
        recent_items = [
            item for item in unique_items
            if item['published_at'] is None or item['published_at'] > cutoff
        ]

        # Sort by date (newest first)
        recent_items.sort(
            key=lambda x: x['published_at'] or datetime.min,
            reverse=True
        )

        # Limit results
        news_items = recent_items[:limit]

        # Cache for 5 minutes
        cache.set(cache_key, news_items, ttl=300)

        logger.info(f"Aggregated {len(news_items)} news items from {len(feeds_to_fetch)} feeds")
        return news_items

    async def get_market_news(self, limit: int = 15) -> List[Dict]:
        """
        Get market-focused news filtered by keywords.
        """
        cache_key = f"news:market:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        all_news = await self.get_news(limit=100)  # Fetch more to filter

        # Filter by market keywords
        market_news = []
        for item in all_news:
            text = f"{item['title']} {item.get('summary', '')}".lower()
            if any(kw in text for kw in self.MARKET_KEYWORDS):
                market_news.append(item)

        market_news = market_news[:limit]

        # Cache for 5 minutes
        cache.set(cache_key, market_news, ttl=300)

        return market_news

    async def get_news_by_source(self, source_key: str, limit: int = 10) -> List[Dict]:
        """
        Get news from a specific source.
        """
        if source_key not in self.RSS_FEEDS:
            return []

        cache_key = f"news:{source_key}:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        items = await self._fetch_feed(source_key)
        items = items[:limit]

        cache.set(cache_key, items, ttl=300)
        return items

    def get_available_sources(self) -> List[Dict]:
        """
        Get list of available news sources.
        """
        return [
            {
                'key': key,
                'name': config['name'],
                'icon': config['icon'],
                'category': config['category'],
            }
            for key, config in self.RSS_FEEDS.items()
        ]


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_news_service: Optional[FinancialNewsService] = None


def get_news_service() -> FinancialNewsService:
    """Get the global FinancialNewsService instance."""
    global _news_service
    if _news_service is None:
        _news_service = FinancialNewsService()
    return _news_service
