"""
Polymarket Integration Service - Fetches prediction market data
for trading-relevant events (Fed decisions, elections, economic indicators)
"""

import asyncio
import aiohttp
import math
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from statistics import stdev
from loguru import logger

from app.config import get_settings
from app.services.cache import cache


# =============================================================================
# MACRO CONFIGURATION
# =============================================================================

@dataclass
class MacroConfig:
    """Configuration for MRI and macro signal calculations."""
    # Quality thresholds
    MIN_QUALITY_THRESHOLD: float = 0.5
    MIN_MARKETS_PER_CATEGORY: int = 2

    # Liquidity thresholds (for quality scoring)
    LIQUIDITY_HIGH: int = 100000
    LIQUIDITY_MEDIUM: int = 50000
    LIQUIDITY_LOW: int = 10000

    # Time-to-expiry thresholds (days)
    EXPIRY_FULL: int = 30
    EXPIRY_MEDIUM: int = 14
    EXPIRY_LOW: int = 7
    EXPIRY_MINIMUM: int = 3  # Below this = minimal weight (not zero)

    # Staleness thresholds
    STALE_THRESHOLD_MINUTES: int = 30
    STALE_ALERT_SUPPRESS: bool = True

    # Category weights for MRI calculation
    CATEGORY_WEIGHTS: Dict[str, float] = field(default_factory=lambda: {
        'fed_policy': 0.30,
        'recession': 0.25,
        'elections': 0.20,
        'trade': 0.15,
        'crypto': 0.10,
    })


# Default configuration instance
_macro_config = MacroConfig()


@dataclass
class PredictionMarket:
    """A prediction market with current odds"""
    id: str
    title: str
    outcomes: List[Dict[str, Any]]
    volume: float
    liquidity: float
    end_date: Optional[str]
    category: str
    change_24h: Optional[float] = None


@dataclass
class OddsChange:
    """Tracks significant odds changes for alerts"""
    market_id: str
    market_title: str
    outcome: str
    previous_odds: float
    current_odds: float
    change_percent: float
    timeframe: str  # '1h', '4h', '24h'
    significance: str  # 'notable', 'significant', 'major'


class PolymarketService:
    """
    Service for fetching prediction market data from Polymarket.
    Focuses on markets relevant to trading: Fed policy, elections, economics.
    """

    # Polymarket API endpoints
    BASE_URL = "https://gamma-api.polymarket.com"
    CLOB_URL = "https://clob.polymarket.com"

    # Categories relevant to trading
    TRADING_CATEGORIES = [
        'politics',
        'economics',
        'crypto',
        'fed',
        'elections',
    ]

    # Keywords for filtering trading-relevant markets
    TRADING_KEYWORDS = [
        'fed', 'federal reserve', 'interest rate', 'rate cut', 'rate hike', 'fomc',
        'trump', 'biden', 'election', 'president', '2026', '2028', 'congress', 'senate',
        'recession', 'gdp', 'inflation', 'cpi', 'unemployment', 'jobs', 'employment',
        'bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'solana', 'sol',
        's&p', 'stock market', 'dow', 'nasdaq', 'spy', 'qqq',
        'tariff', 'trade war', 'china', 'trade deal',
        'ai', 'nvidia', 'tech', 'earnings',
    ]

    # Key markets to always track (by slug or ID) - updated for 2025/2026
    KEY_MARKET_SLUGS = [
        'federal-reserve',
        'rate-cut',
        'recession',
        'bitcoin',
        'trump',
        'congress',
    ]

    def __init__(self):
        self.settings = get_settings()
        self._session: Optional[aiohttp.ClientSession] = None
        self._odds_history: Dict[str, List[Dict]] = {}  # Track odds over time

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={
                    'Accept': 'application/json',
                    'User-Agent': 'LEAPS-Trader/1.0'
                }
            )
        return self._session

    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()

    # -------------------------------------------------------------------------
    # CORE API METHODS
    # -------------------------------------------------------------------------

    async def _fetch_markets(self, limit: int = 100, active: bool = True) -> List[Dict]:
        """
        Fetch markets from Polymarket API.
        Filters for active, non-closed markets with future end dates.
        """
        try:
            session = await self._get_session()

            # Get current date for filtering - only show markets ending in the future
            now = datetime.now()
            min_end_date = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            params = {
                'limit': limit,
                'active': str(active).lower(),
                'closed': 'false',  # Only open markets
                'end_date_min': min_end_date,  # Only markets ending in the future
                'volume_num_min': 10000,  # Filter out low-activity markets
                'order': 'volume',  # Sort by volume (most active first)
                'ascending': 'false',  # Descending order
            }

            async with session.get(f"{self.BASE_URL}/markets", params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data if isinstance(data, list) else data.get('markets', [])
                    logger.info(f"Polymarket: Fetched {len(markets)} active markets with future end dates")
                    return markets
                else:
                    logger.warning(f"Polymarket API returned status {response.status}, trying fallback")
                    return await self._fetch_markets_fallback(limit)

        except Exception as e:
            logger.error(f"Error fetching Polymarket markets: {e}")
            return await self._fetch_markets_fallback(limit)

    async def _fetch_markets_fallback(self, limit: int = 100) -> List[Dict]:
        """
        Fallback method with minimal filters if primary fetch fails.
        Manually filters out old/closed markets.
        """
        try:
            session = await self._get_session()
            params = {
                'limit': limit * 2,  # Fetch more to account for filtering
                'closed': 'false',
            }

            async with session.get(f"{self.BASE_URL}/markets", params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data if isinstance(data, list) else data.get('markets', [])

                    # Manually filter out old markets
                    now = datetime.now()
                    active_markets = []
                    for m in markets:
                        end_date = m.get('endDate')
                        if end_date:
                            try:
                                # Handle various date formats
                                end_str = end_date.replace('Z', '+00:00')
                                end_dt = datetime.fromisoformat(end_str)
                                if end_dt.replace(tzinfo=None) > now:
                                    active_markets.append(m)
                            except Exception:
                                # If can't parse, check if it looks like a future year
                                if '2025' in end_date or '2026' in end_date or '2027' in end_date:
                                    active_markets.append(m)
                        else:
                            # Markets without end dates might be perpetual - include them
                            active_markets.append(m)

                    # Sort by volume
                    active_markets.sort(key=lambda x: float(x.get('volume', 0)), reverse=True)
                    logger.info(f"Polymarket fallback: Filtered to {len(active_markets)} active markets")
                    return active_markets[:limit]
                return []
        except Exception as e:
            logger.error(f"Polymarket fallback failed: {e}")
            return []

    async def _fetch_market_detail(self, market_id: str) -> Optional[Dict]:
        """
        Fetch detailed data for a specific market.
        """
        try:
            session = await self._get_session()

            async with session.get(f"{self.BASE_URL}/markets/{market_id}") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None

        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return None

    # -------------------------------------------------------------------------
    # TRADING-RELEVANT MARKETS
    # -------------------------------------------------------------------------

    def _is_trading_relevant(self, market: Dict) -> bool:
        """
        Check if a market is relevant for trading decisions.
        """
        title = market.get('question', '').lower()
        description = market.get('description', '').lower()
        tags = [t.lower() for t in market.get('tags', [])]

        # Check keywords in title/description
        text = f"{title} {description}"
        for keyword in self.TRADING_KEYWORDS:
            if keyword in text:
                return True

        # Check tags
        for tag in tags:
            if tag in self.TRADING_CATEGORIES:
                return True

        return False

    def _categorize_market(self, market: Dict) -> str:
        """
        Categorize a market for display grouping.
        """
        title = market.get('question', '').lower()
        description = market.get('description', '').lower()
        text = f"{title} {description}"

        if any(kw in text for kw in ['fed', 'rate cut', 'rate hike', 'federal reserve', 'fomc', 'interest rate']):
            return 'fed_policy'
        elif any(kw in text for kw in ['trump', 'biden', 'election', 'president', 'congress', 'senate', 'governor', 'midterm']):
            return 'elections'
        elif any(kw in text for kw in ['recession', 'gdp', 'inflation', 'cpi', 'unemployment', 'jobs report', 'employment']):
            return 'recession'  # Use 'recession' for MRI compatibility
        elif any(kw in text for kw in ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'solana', 'sol']):
            return 'crypto'
        elif any(kw in text for kw in ['tariff', 'china', 'trade deal', 'trade war']):
            return 'trade'
        elif any(kw in text for kw in ['ai', 'nvidia', 'tech', 'earnings', 's&p', 'nasdaq', 'stock']):
            return 'markets'
        else:
            return 'other'

    async def get_trading_markets(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get prediction markets relevant to trading decisions.
        Filters and categorizes markets for the Command Center.
        """
        cache_key = "polymarket:trading_markets"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            all_markets = await self._fetch_markets(limit=200)

            trading_markets = []
            for market in all_markets:
                if not self._is_trading_relevant(market):
                    continue

                # Parse outcomes and odds
                outcomes = []
                outcome_prices = market.get('outcomePrices', '[]')

                # Handle string or list format
                if isinstance(outcome_prices, str):
                    try:
                        import json
                        outcome_prices = json.loads(outcome_prices)
                    except:
                        outcome_prices = []

                outcome_names = market.get('outcomes', '[]')
                if isinstance(outcome_names, str):
                    try:
                        import json
                        outcome_names = json.loads(outcome_names)
                    except:
                        outcome_names = ['Yes', 'No']

                for i, name in enumerate(outcome_names):
                    price = float(outcome_prices[i]) if i < len(outcome_prices) else 0.5
                    outcomes.append({
                        'name': name,
                        'price': round(price, 3),
                        'percent': round(price * 100, 1),
                    })

                # Get primary outcome (usually "Yes" or the first option)
                primary_odds = outcomes[0]['percent'] if outcomes else 50

                # Calculate 24h change if we have history
                market_id = market.get('id', '')
                change_24h = self._calculate_change(market_id, primary_odds, '24h')

                trading_markets.append({
                    'id': market_id,
                    'title': market.get('question', 'Unknown Market'),
                    'slug': market.get('slug', ''),
                    'category': self._categorize_market(market),
                    'outcomes': outcomes,
                    'primary_odds': primary_odds,
                    'change_24h': change_24h,
                    'volume': float(market.get('volume', 0)),
                    'liquidity': float(market.get('liquidity', 0)),
                    'end_date': market.get('endDate'),
                    'url': f"https://polymarket.com/event/{market.get('slug', '')}",
                })

                # Store in history for change tracking
                self._update_odds_history(market_id, primary_odds)

            # Sort by volume (most active first)
            trading_markets.sort(key=lambda x: x['volume'], reverse=True)

            # Limit results
            trading_markets = trading_markets[:limit]

            # Cache for 5 minutes
            cache.set(cache_key, trading_markets, ttl=300)

            return trading_markets

        except Exception as e:
            logger.error(f"Error getting trading markets: {e}")
            return []

    # -------------------------------------------------------------------------
    # ODDS TRACKING AND ALERTS
    # -------------------------------------------------------------------------

    def _update_odds_history(self, market_id: str, current_odds: float):
        """
        Update odds history for change tracking.
        """
        if market_id not in self._odds_history:
            self._odds_history[market_id] = []

        self._odds_history[market_id].append({
            'odds': current_odds,
            'timestamp': datetime.now().isoformat(),
        })

        # Keep only last 24 hours of history
        cutoff = datetime.now() - timedelta(hours=24)
        self._odds_history[market_id] = [
            entry for entry in self._odds_history[market_id]
            if datetime.fromisoformat(entry['timestamp']) > cutoff
        ]

    def _calculate_change(self, market_id: str, current_odds: float, timeframe: str) -> Optional[float]:
        """
        Calculate odds change over a timeframe.
        """
        if market_id not in self._odds_history:
            return None

        history = self._odds_history[market_id]
        if len(history) < 2:
            return None

        # Determine cutoff based on timeframe
        if timeframe == '1h':
            cutoff = datetime.now() - timedelta(hours=1)
        elif timeframe == '4h':
            cutoff = datetime.now() - timedelta(hours=4)
        else:  # 24h
            cutoff = datetime.now() - timedelta(hours=24)

        # Find oldest entry within timeframe
        for entry in history:
            entry_time = datetime.fromisoformat(entry['timestamp'])
            if entry_time >= cutoff:
                previous_odds = entry['odds']
                change = current_odds - previous_odds
                return round(change, 1)

        return None

    async def get_significant_changes(self, threshold: float = 5.0) -> List[Dict[str, Any]]:
        """
        Get markets with significant odds changes.
        Used for alerts in the Command Center.

        Args:
            threshold: Minimum percentage change to consider significant
        """
        cache_key = f"polymarket:changes:{threshold}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        markets = await self.get_trading_markets(limit=50)
        changes = []

        for market in markets:
            change_24h = market.get('change_24h')
            if change_24h is not None and abs(change_24h) >= threshold:
                # Determine significance level
                if abs(change_24h) >= 15:
                    significance = 'major'
                    emoji = '🔴'
                elif abs(change_24h) >= 10:
                    significance = 'significant'
                    emoji = '🟠'
                else:
                    significance = 'notable'
                    emoji = '🟡'

                changes.append({
                    'market_id': market['id'],
                    'title': market['title'],
                    'category': market['category'],
                    'current_odds': market['primary_odds'],
                    'change_24h': change_24h,
                    'direction': 'up' if change_24h > 0 else 'down',
                    'significance': significance,
                    'emoji': emoji,
                    'url': market['url'],
                })

        # Sort by absolute change (biggest moves first)
        changes.sort(key=lambda x: abs(x['change_24h']), reverse=True)

        # Cache for 5 minutes
        cache.set(cache_key, changes, ttl=300)

        return changes

    # -------------------------------------------------------------------------
    # CURATED KEY MARKETS
    # -------------------------------------------------------------------------

    async def get_key_markets(self) -> Dict[str, Any]:
        """
        Get curated list of key markets for the dashboard.
        Returns categorized markets with formatted data.
        """
        cache_key = "polymarket:key_markets"
        cached = cache.get(cache_key)
        if cached:
            return cached

        markets = await self.get_trading_markets(limit=50)

        # Organize by category
        categorized = {
            'fed_policy': [],
            'elections': [],
            'recession': [],
            'crypto': [],
            'trade': [],
            'markets': [],
            'other': [],
        }

        for market in markets:
            category = market['category']
            if category in categorized:
                categorized[category].append(market)

        # Select top market from each category
        key_markets = {}
        for category, category_markets in categorized.items():
            if category_markets:
                # Get the highest volume market in this category
                top_market = category_markets[0]
                key_markets[category] = {
                    'title': top_market['title'],
                    'primary_outcome': top_market['outcomes'][0]['name'] if top_market['outcomes'] else 'Yes',
                    'odds': top_market['primary_odds'],
                    'change_24h': top_market['change_24h'],
                    'volume': top_market['volume'],
                    'url': top_market['url'],
                }

        result = {
            'timestamp': datetime.now().isoformat(),
            'key_markets': key_markets,
            'all_markets': categorized,
            'total_count': len(markets),
        }

        # Cache for 5 minutes
        cache.set(cache_key, result, ttl=300)

        return result

    # -------------------------------------------------------------------------
    # MARKET SUMMARY FOR DASHBOARD
    # -------------------------------------------------------------------------

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Get summarized Polymarket data for the Command Center dashboard.
        """
        cache_key = "polymarket:dashboard"
        cached = cache.get(cache_key)
        if cached:
            return cached

        key_markets = await self.get_key_markets()
        changes = await self.get_significant_changes(threshold=5.0)

        # Format for dashboard widget
        dashboard_items = []

        km = key_markets.get('key_markets', {})

        def truncate_title(title: str, max_len: int = 30) -> str:
            """Truncate title to max length with ellipsis"""
            return title[:max_len] + '...' if len(title) > max_len else title

        # Fed Policy
        if 'fed_policy' in km:
            fed = km['fed_policy']
            dashboard_items.append({
                'icon': '🏛️',
                'label': truncate_title(fed['title'], 25),
                'value': f"{fed['odds']}%",
                'change': fed.get('change_24h'),
                'category': 'fed_policy',
            })

        # Elections
        if 'elections' in km:
            elec = km['elections']
            dashboard_items.append({
                'icon': '🗳️',
                'label': truncate_title(elec['title'], 30),
                'value': f"{elec['odds']}%",
                'change': elec.get('change_24h'),
                'category': 'elections',
            })

        # Economic/Recession
        if 'recession' in km:
            econ = km['recession']
            dashboard_items.append({
                'icon': '📉',
                'label': truncate_title(econ['title'], 25),
                'value': f"{econ['odds']}%",
                'change': econ.get('change_24h'),
                'category': 'recession',
            })

        # Crypto
        if 'crypto' in km:
            crypto = km['crypto']
            dashboard_items.append({
                'icon': '₿',
                'label': truncate_title(crypto['title'], 25),
                'value': f"{crypto['odds']}%",
                'change': crypto.get('change_24h'),
                'category': 'crypto',
            })

        # Markets/Tech (new category)
        if 'markets' in km:
            markets_cat = km['markets']
            dashboard_items.append({
                'icon': '📈',
                'label': truncate_title(markets_cat['title'], 25),
                'value': f"{markets_cat['odds']}%",
                'change': markets_cat.get('change_24h'),
                'category': 'markets',
            })

        result = {
            'timestamp': datetime.now().isoformat(),
            'items': dashboard_items,
            'significant_changes': changes[:5],  # Top 5 movers
            'total_markets_tracked': key_markets.get('total_count', 0),
        }

        # Cache for 5 minutes
        cache.set(cache_key, result, ttl=300)

        return result


    # -------------------------------------------------------------------------
    # MARKET QUALITY SCORING (MRI Support)
    # -------------------------------------------------------------------------

    def calculate_market_quality_score(self, market: Dict, config: MacroConfig = None) -> float:
        """
        Compute quality score for eligibility filtering.
        Markets below MIN_QUALITY_THRESHOLD are excluded from aggregation.

        Args:
            market: Market data dictionary from API
            config: MacroConfig instance (uses default if not provided)

        Returns:
            Quality score from 0 to 1
        """
        if config is None:
            config = _macro_config

        score = 0.0

        # 1. Liquidity/Volume (40% weight)
        liquidity = market.get('liquidity', 0) or 0
        if isinstance(liquidity, str):
            try:
                liquidity = float(liquidity)
            except ValueError:
                liquidity = 0

        if liquidity >= config.LIQUIDITY_HIGH:
            score += 0.4
        elif liquidity >= config.LIQUIDITY_MEDIUM:
            score += 0.3
        elif liquidity >= config.LIQUIDITY_LOW:
            score += 0.2
        else:
            score += 0.1

        # 2. Time to expiry (30% weight) - DECAY CURVE, not hard cliffs
        days_to_resolution = self._compute_days_to_resolution(market)

        if days_to_resolution >= config.EXPIRY_FULL:
            score += 0.3
        elif days_to_resolution >= config.EXPIRY_MEDIUM:
            # Linear decay: 0.3 -> 0.2 over 14-30 days
            decay = 0.2 + 0.1 * ((days_to_resolution - config.EXPIRY_MEDIUM) /
                                (config.EXPIRY_FULL - config.EXPIRY_MEDIUM))
            score += decay
        elif days_to_resolution >= config.EXPIRY_LOW:
            # Linear decay: 0.2 -> 0.1 over 7-14 days
            decay = 0.1 + 0.1 * ((days_to_resolution - config.EXPIRY_LOW) /
                                (config.EXPIRY_MEDIUM - config.EXPIRY_LOW))
            score += decay
        elif days_to_resolution >= config.EXPIRY_MINIMUM:
            # Minimal but non-zero: 0.05-0.1 for 3-7 days
            score += 0.05
        else:
            # < 3 days: minimal weight (0.02) - don't fully exclude "event mode" markets
            score += 0.02

        # 3. Market clarity (20% weight)
        title = market.get('question', market.get('title', '')).lower()
        if any(kw in title for kw in ['will', 'by', 'before', 'in 202', 'during']):
            score += 0.2
        else:
            score += 0.1

        # 4. Trade activity (10% weight)
        volume_24h = market.get('volume_24h', market.get('volume', 0)) or 0
        if isinstance(volume_24h, str):
            try:
                volume_24h = float(volume_24h)
            except ValueError:
                volume_24h = 0

        if volume_24h > 10000:
            score += 0.1
        elif volume_24h > 1000:
            score += 0.05

        return min(score, 1.0)

    def _compute_days_to_resolution(self, market: Dict) -> int:
        """
        Compute days until market resolution from Gamma API fields.
        Handles endDate, closeTime, resolutionTime fields.

        Args:
            market: Market data dictionary

        Returns:
            Days until resolution (0 if unknown or past)
        """
        # Try multiple possible field names from Gamma API
        end_date_str = (
            market.get('endDate') or
            market.get('closeTime') or
            market.get('resolutionTime') or
            market.get('end_date')
        )

        if not end_date_str:
            return 0  # Unknown = treat as near-term

        try:
            # Handle ISO format with/without timezone
            if isinstance(end_date_str, str):
                end_date_str = end_date_str.replace('Z', '+00:00')
                end_date = datetime.fromisoformat(end_date_str)
            else:
                end_date = end_date_str

            now = datetime.now(timezone.utc)
            # Ensure end_date has timezone
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)

            delta = end_date - now
            return max(0, delta.days)
        except Exception:
            return 0

    async def get_markets_by_category(self, category: str) -> List[Dict]:
        """
        Get all markets for a specific category with quality scores.

        Args:
            category: Category name (fed_policy, recession, elections, trade, crypto)

        Returns:
            List of markets with quality_score and implied_probability added
        """
        # No mapping needed now - categories are consistent
        search_category = category

        # Get all trading markets
        all_markets = await self.get_trading_markets(limit=100)

        # Filter by category
        category_markets = []
        for market in all_markets:
            if market.get('category') == search_category:
                # Add quality score
                market['quality_score'] = self.calculate_market_quality_score(market)
                # Add implied probability (use primary_odds)
                market['implied_probability'] = market.get('primary_odds', 50)
                category_markets.append(market)

        return category_markets

    async def get_category_aggregate(
        self, category: str, config: MacroConfig = None
    ) -> Dict[str, Any]:
        """
        Quality-weighted probability for a category.

        Key design choices:
        - Liquidity weight uses log1p to prevent whale market dominance
        - Confidence is numeric (0-100) for consistent handling
        - Includes dispersion stats (min/max/stddev) for trust assessment
        - key_market is top contributor by computed weight, not first eligible

        Args:
            category: Category name
            config: MacroConfig instance

        Returns:
            Dictionary with aggregate probability, confidence, dispersion stats
        """
        if config is None:
            config = _macro_config

        markets = await self.get_markets_by_category(category)

        # Filter by quality
        eligible = [m for m in markets if m.get('quality_score', 0) >= config.MIN_QUALITY_THRESHOLD]

        if not eligible:
            return {
                "category": category,
                "aggregate_probability": None,
                "confidence_score": 0,
                "confidence_label": "none",
                "markets_used": 0,
                "total_liquidity": 0,
                "dispersion": None,
                "key_market": None,
            }

        # Compute weights using LOG-NORMALIZED liquidity (prevents whale dominance)
        for m in eligible:
            liquidity = m.get('liquidity') or 0
            if isinstance(liquidity, str):
                try:
                    liquidity = float(liquidity)
                except ValueError:
                    liquidity = 0
            # log1p handles zero gracefully, caps extreme values
            liquidity_weight = math.log1p(liquidity) if liquidity > 0 else 1.0
            m['_weight'] = m.get('quality_score', 0.5) * liquidity_weight

        total_weight = sum(m['_weight'] for m in eligible)

        # Quality-weighted average probability
        weighted_prob = sum(
            m.get('implied_probability', 50) * m['_weight'] for m in eligible
        ) / total_weight if total_weight > 0 else 50

        # Dispersion stats (critical for trust assessment)
        probabilities = [m.get('implied_probability', 50) for m in eligible]
        prob_min = min(probabilities)
        prob_max = max(probabilities)
        prob_range = prob_max - prob_min
        prob_stddev = stdev(probabilities) if len(probabilities) > 1 else 0

        dispersion = {
            "min": round(prob_min, 1),
            "max": round(prob_max, 1),
            "stddev": round(prob_stddev, 2),
            "range": round(prob_range, 1),
        }

        # Total liquidity
        total_liquidity = sum(
            float(m.get('liquidity', 0) or 0) for m in eligible
        )

        # Confidence score (0-100) - numeric for consistent handling
        confidence_score = self._calculate_category_confidence(
            markets_used=len(eligible),
            total_liquidity=total_liquidity,
            dispersion_stddev=prob_stddev,
        )

        # Map to label for UI
        if confidence_score >= 70:
            confidence_label = "high"
        elif confidence_score >= 40:
            confidence_label = "medium"
        else:
            confidence_label = "low"

        # Key market = TOP CONTRIBUTOR by weight (not first eligible)
        sorted_by_weight = sorted(eligible, key=lambda m: m['_weight'], reverse=True)
        key_market = None
        if sorted_by_weight:
            km = sorted_by_weight[0]
            key_market = {
                "id": km.get('id'),
                "title": km.get('title'),
                "implied_probability": km.get('implied_probability'),
                "quality_score": km.get('quality_score'),
                "liquidity": km.get('liquidity'),
            }

        # Clean up temp weight field
        for m in eligible:
            if '_weight' in m:
                del m['_weight']

        return {
            "category": category,
            "aggregate_probability": round(weighted_prob, 1),
            "confidence_score": round(confidence_score, 0),
            "confidence_label": confidence_label,
            "markets_used": len(eligible),
            "total_liquidity": total_liquidity,
            "dispersion": dispersion,
            "key_market": key_market,
        }

    def _calculate_category_confidence(
        self,
        markets_used: int,
        total_liquidity: float,
        dispersion_stddev: float,
    ) -> float:
        """
        Compute confidence score (0-100) for a category aggregate.
        Higher when: more markets, more liquidity, less disagreement.

        Args:
            markets_used: Number of markets in aggregate
            total_liquidity: Sum of liquidity across markets
            dispersion_stddev: Standard deviation of probabilities

        Returns:
            Confidence score from 0 to 100
        """
        score = 0.0

        # Market count (max 35 points)
        if markets_used >= 5:
            score += 35
        elif markets_used >= 3:
            score += 25
        elif markets_used >= 2:
            score += 15
        else:
            score += 5

        # Liquidity (max 35 points)
        if total_liquidity >= 500000:
            score += 35
        elif total_liquidity >= 200000:
            score += 25
        elif total_liquidity >= 50000:
            score += 15
        else:
            score += 5

        # Dispersion penalty (max 30 points, higher stddev = lower confidence)
        # stddev < 5 = good agreement, stddev > 15 = high disagreement
        if dispersion_stddev <= 5:
            score += 30
        elif dispersion_stddev <= 10:
            score += 20
        elif dispersion_stddev <= 15:
            score += 10
        else:
            score += 0  # High disagreement = no confidence bonus

        return min(score, 100)

    async def get_all_category_aggregates(self) -> Dict[str, Dict]:
        """
        Get aggregates for all MRI categories.

        Returns:
            Dictionary mapping category name to aggregate data
        """
        categories = ['fed_policy', 'recession', 'elections', 'trade', 'crypto']
        aggregates = {}

        for category in categories:
            aggregates[category] = await self.get_category_aggregate(category)

        return aggregates


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_polymarket_service: Optional[PolymarketService] = None


def get_polymarket_service() -> PolymarketService:
    """Get the global PolymarketService instance."""
    global _polymarket_service
    if _polymarket_service is None:
        _polymarket_service = PolymarketService()
    return _polymarket_service
