"""
Market Data Service - Fetches indices, Fear & Greed, sectors, and VIX data
for the Command Center dashboard
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from loguru import logger

from app.config import get_settings
from app.services.cache import cache
from app.services.data_fetcher.alpaca_service import alpaca_service


@dataclass
class MarketIndex:
    """Market index data"""
    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    trend: str  # 'up', 'down', 'flat'


@dataclass
class FearGreedData:
    """CNN Fear & Greed Index data"""
    value: int
    rating: str  # 'Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'
    previous_close: int
    one_week_ago: int
    one_month_ago: int
    one_year_ago: int
    updated_at: str


@dataclass
class SectorPerformance:
    """Sector ETF performance"""
    symbol: str
    name: str
    change_percent: float
    trend: str


class MarketDataService:
    """
    Service for fetching market data for the Command Center.
    Includes indices, Fear & Greed index, sector performance, and VIX metrics.
    """

    # Key indices to track
    INDICES = {
        'SPY': 'S&P 500',
        'QQQ': 'Nasdaq 100',
        'DIA': 'Dow Jones',
        'IWM': 'Russell 2000',
    }

    # Volatility indices
    VOLATILITY = {
        '^VIX': 'VIX',
        '^VIX9D': 'VIX 9-Day',
    }

    # Sector ETFs
    SECTORS = {
        'XLK': 'Technology',
        'XLV': 'Healthcare',
        'XLF': 'Financials',
        'XLE': 'Energy',
        'XLI': 'Industrials',
        'XLY': 'Consumer Disc.',
        'XLP': 'Consumer Staples',
        'XLU': 'Utilities',
        'XLB': 'Materials',
        'XLRE': 'Real Estate',
        'XLC': 'Communication',
    }

    # Fear & Greed API endpoint (CNN's public data endpoint)
    FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

    def __init__(self):
        self.settings = get_settings()
        self._session: Optional[aiohttp.ClientSession] = None

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
    # MARKET INDICES
    # -------------------------------------------------------------------------

    async def get_market_indices(self) -> List[Dict[str, Any]]:
        """
        Get current prices and changes for major market indices.
        Uses Alpaca snapshots for real-time data.
        """
        cache_key = "command_center:indices"
        cached = cache.get(cache_key)
        if cached:
            return cached

        indices = []

        for symbol, name in self.INDICES.items():
            try:
                snapshot = await asyncio.to_thread(alpaca_service.get_snapshot, symbol)
                if not snapshot:
                    continue

                price = float(snapshot.latest_trade.price) if snapshot.latest_trade else None
                if not price and snapshot.daily_bar:
                    price = float(snapshot.daily_bar.close)

                if not price:
                    continue

                prev_close = float(snapshot.previous_daily_bar.close) if snapshot.previous_daily_bar else None
                if prev_close and prev_close > 0:
                    change = price - prev_close
                    change_pct = (change / prev_close) * 100
                else:
                    change = 0
                    change_pct = 0

                trend = 'up' if change > 0 else ('down' if change < 0 else 'flat')

                indices.append({
                    'symbol': symbol,
                    'name': name,
                    'price': round(price, 2),
                    'change': round(change, 2),
                    'change_percent': round(change_pct, 2),
                    'trend': trend,
                })
            except Exception as e:
                logger.error(f"Error fetching index {symbol}: {e}")
                continue

        # Cache for 1 minute
        if indices:
            cache.set(cache_key, indices, ttl=60)

        return indices

    # -------------------------------------------------------------------------
    # VOLATILITY METRICS
    # -------------------------------------------------------------------------

    async def get_volatility_metrics(self) -> Dict[str, Any]:
        """
        Get VIX and related volatility metrics.
        Uses Alpaca historical bars for VIX data.
        """
        cache_key = "command_center:volatility"
        cached = cache.get(cache_key)
        if cached:
            return cached

        metrics = {}

        for symbol, name in self.VOLATILITY.items():
            try:
                hist = await asyncio.to_thread(lambda s=symbol: alpaca_service.get_historical_prices(s, period="5d"))

                if hist is not None and not hist.empty:
                    close_col = 'Close' if 'Close' in hist.columns else 'close'
                    current = float(hist[close_col].iloc[-1])
                    prev = float(hist[close_col].iloc[-2]) if len(hist) >= 2 else current
                    change = current - prev
                    change_pct = (change / prev) * 100 if prev else 0

                    # VIX levels interpretation
                    if current < 15:
                        level = 'low'
                        interpretation = 'Complacency - markets calm'
                    elif current < 20:
                        level = 'normal'
                        interpretation = 'Normal volatility'
                    elif current < 25:
                        level = 'elevated'
                        interpretation = 'Elevated fear - caution advised'
                    elif current < 30:
                        level = 'high'
                        interpretation = 'High fear - consider hedging'
                    else:
                        level = 'extreme'
                        interpretation = 'Extreme fear - potential opportunity'

                    metrics[name.lower().replace(' ', '_').replace('-', '')] = {
                        'symbol': symbol,
                        'name': name,
                        'value': round(current, 2),
                        'change': round(change, 2),
                        'change_percent': round(change_pct, 2),
                        'level': level,
                        'interpretation': interpretation,
                        'trend': 'up' if change > 0 else ('down' if change < 0 else 'flat'),
                    }
            except Exception as e:
                logger.error(f"Error fetching volatility {symbol}: {e}")
                continue

        # Add VIX term structure analysis
        if 'vix' in metrics and 'vix_9day' in metrics:
            vix = metrics['vix']['value']
            vix9d = metrics['vix_9day']['value']

            if vix9d > vix:
                metrics['term_structure'] = {
                    'status': 'backwardation',
                    'interpretation': 'Near-term fear higher than usual - potential volatility spike'
                }
            else:
                metrics['term_structure'] = {
                    'status': 'contango',
                    'interpretation': 'Normal term structure - markets stable'
                }

        # Cache for 1 minute
        if metrics:
            cache.set(cache_key, metrics, ttl=60)

        return metrics

    # -------------------------------------------------------------------------
    # FEAR & GREED INDEX
    # -------------------------------------------------------------------------

    async def get_fear_greed_index(self) -> Optional[Dict[str, Any]]:
        """
        Fetch CNN Fear & Greed Index.
        Uses CNN's public data endpoint.
        """
        cache_key = "command_center:fear_greed"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            session = await self._get_session()

            # CNN's Fear & Greed data endpoint
            async with session.get(self.FEAR_GREED_URL) as response:
                if response.status == 200:
                    data = await response.json()

                    # Parse the response
                    fear_greed = data.get('fear_and_greed', {})

                    score = fear_greed.get('score', 50)

                    # Determine rating based on score
                    if score <= 25:
                        rating = 'Extreme Fear'
                        color = '#dc2626'  # red-600
                    elif score <= 45:
                        rating = 'Fear'
                        color = '#f97316'  # orange-500
                    elif score <= 55:
                        rating = 'Neutral'
                        color = '#eab308'  # yellow-500
                    elif score <= 75:
                        rating = 'Greed'
                        color = '#84cc16'  # lime-500
                    else:
                        rating = 'Extreme Greed'
                        color = '#22c55e'  # green-500

                    result = {
                        'value': round(score),
                        'rating': rating,
                        'color': color,
                        'previous_close': round(fear_greed.get('previous_close', score)),
                        'one_week_ago': round(fear_greed.get('previous_1_week', score)),
                        'one_month_ago': round(fear_greed.get('previous_1_month', score)),
                        'one_year_ago': round(fear_greed.get('previous_1_year', score)),
                        'updated_at': datetime.now().isoformat(),
                        # Individual indicators
                        'indicators': {
                            'market_momentum': data.get('market_momentum_sp500', {}).get('score'),
                            'stock_price_strength': data.get('stock_price_strength', {}).get('score'),
                            'stock_price_breadth': data.get('stock_price_breadth', {}).get('score'),
                            'put_call_ratio': data.get('put_call_options', {}).get('score'),
                            'market_volatility': data.get('market_volatility_vix', {}).get('score'),
                            'safe_haven_demand': data.get('safe_haven_demand', {}).get('score'),
                            'junk_bond_demand': data.get('junk_bond_demand', {}).get('score'),
                        }
                    }

                    # Cache for 5 minutes
                    cache.set(cache_key, result, ttl=300)

                    return result
                else:
                    logger.warning(f"Fear & Greed API returned status {response.status}, using fallback")
                    return await self._get_fear_greed_fallback()

        except Exception as e:
            logger.error(f"Error fetching Fear & Greed index: {e}")
            # Return fallback based on VIX if available
            return await self._get_fear_greed_fallback()

    async def _get_fear_greed_fallback(self) -> Optional[Dict[str, Any]]:
        """
        Fallback Fear & Greed calculation using VIX and market data.
        Used when CNN endpoint is unavailable.
        """
        try:
            volatility = await self.get_volatility_metrics()
            indices = await self.get_market_indices()

            # Simple calculation based on VIX
            vix = volatility.get('vix', {}).get('value', 20)

            # VIX to Fear/Greed score (inverse relationship)
            # VIX 10 = 90 score (extreme greed), VIX 40 = 10 score (extreme fear)
            score = max(0, min(100, 100 - ((vix - 10) * 3)))

            # Adjust based on market performance
            spy_change = next((i['change_percent'] for i in indices if i['symbol'] == 'SPY'), 0)
            score = score + (spy_change * 2)  # Adjust by market movement
            score = max(0, min(100, score))

            if score <= 25:
                rating = 'Extreme Fear'
                color = '#dc2626'
            elif score <= 45:
                rating = 'Fear'
                color = '#f97316'
            elif score <= 55:
                rating = 'Neutral'
                color = '#eab308'
            elif score <= 75:
                rating = 'Greed'
                color = '#84cc16'
            else:
                rating = 'Extreme Greed'
                color = '#22c55e'

            return {
                'value': round(score),
                'rating': rating,
                'color': color,
                'previous_close': round(score),
                'one_week_ago': round(score),
                'one_month_ago': round(score),
                'one_year_ago': round(score),
                'updated_at': datetime.now().isoformat(),
                'is_fallback': True,
                'indicators': None,
            }

        except Exception as e:
            logger.error(f"Error in Fear & Greed fallback: {e}")
            return None

    # -------------------------------------------------------------------------
    # SECTOR PERFORMANCE
    # -------------------------------------------------------------------------

    async def get_sector_performance(self) -> List[Dict[str, Any]]:
        """
        Get performance of sector ETFs for rotation analysis.
        Uses Alpaca snapshots for real-time data.
        """
        cache_key = "command_center:sectors"
        cached = cache.get(cache_key)
        if cached:
            return cached

        sectors = []

        for symbol, name in self.SECTORS.items():
            try:
                snapshot = await asyncio.to_thread(alpaca_service.get_snapshot, symbol)
                if not snapshot:
                    continue

                price = float(snapshot.latest_trade.price) if snapshot.latest_trade else None
                if not price and snapshot.daily_bar:
                    price = float(snapshot.daily_bar.close)

                if not price:
                    continue

                prev_close = float(snapshot.previous_daily_bar.close) if snapshot.previous_daily_bar else None
                if prev_close and prev_close > 0:
                    change_pct = ((price - prev_close) / prev_close) * 100
                else:
                    change_pct = 0

                sectors.append({
                    'symbol': symbol,
                    'name': name,
                    'change_percent': round(change_pct, 2),
                    'trend': 'up' if change_pct > 0 else ('down' if change_pct < 0 else 'flat'),
                })
            except Exception as e:
                logger.error(f"Error fetching sector {symbol}: {e}")
                continue

        # Sort by performance (best to worst)
        sectors.sort(key=lambda x: x['change_percent'], reverse=True)

        # Cache for 5 minutes
        if sectors:
            cache.set(cache_key, sectors, ttl=300)

        return sectors

    # -------------------------------------------------------------------------
    # MARKET SUMMARY
    # -------------------------------------------------------------------------

    async def get_market_summary(self) -> Dict[str, Any]:
        """
        Get complete market summary for Command Center.
        Combines all market data into a single response.
        """
        cache_key = "command_center:summary"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # Fetch all data concurrently
        indices_task = asyncio.create_task(self.get_market_indices())
        volatility_task = asyncio.create_task(self.get_volatility_metrics())
        fear_greed_task = asyncio.create_task(self.get_fear_greed_index())
        sectors_task = asyncio.create_task(self.get_sector_performance())

        indices = await indices_task
        volatility = await volatility_task
        fear_greed = await fear_greed_task
        sectors = await sectors_task

        # Determine overall market condition
        spy = next((i for i in indices if i['symbol'] == 'SPY'), None)
        vix = volatility.get('vix', {})
        fg_score = fear_greed.get('value', 50) if fear_greed else 50

        # Calculate market condition
        if spy:
            if spy['change_percent'] > 1 and fg_score > 60:
                condition = 'bullish'
                condition_color = '#22c55e'
            elif spy['change_percent'] < -1 and fg_score < 40:
                condition = 'bearish'
                condition_color = '#dc2626'
            elif vix.get('level') in ['high', 'extreme']:
                condition = 'volatile'
                condition_color = '#f97316'
            else:
                condition = 'neutral'
                condition_color = '#eab308'
        else:
            condition = 'unknown'
            condition_color = '#6b7280'

        # Identify leading and lagging sectors
        leading_sectors = sectors[:3] if sectors else []
        lagging_sectors = sectors[-3:] if sectors else []

        summary = {
            'timestamp': datetime.now().isoformat(),
            'market_condition': {
                'status': condition,
                'color': condition_color,
            },
            'indices': indices,
            'volatility': volatility,
            'fear_greed': fear_greed,
            'sectors': {
                'all': sectors,
                'leading': leading_sectors,
                'lagging': lagging_sectors,
            },
            # Quick stats for dashboard
            'quick_stats': {
                'spy_change': spy['change_percent'] if spy else 0,
                'vix_level': vix.get('value', 20),
                'fear_greed_score': fg_score,
                'top_sector': sectors[0]['name'] if sectors else 'N/A',
                'bottom_sector': sectors[-1]['name'] if sectors else 'N/A',
            }
        }

        # Cache for 1 minute
        cache.set(cache_key, summary, ttl=60)

        return summary


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_market_data_service: Optional[MarketDataService] = None


def get_market_data_service() -> MarketDataService:
    """Get the global MarketDataService instance."""
    global _market_data_service
    if _market_data_service is None:
        _market_data_service = MarketDataService()
    return _market_data_service
