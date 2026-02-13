"""
Financial Modeling Prep (FMP) data fetcher with rate limiting and caching.

Replaces Yahoo Finance for:
- Company profile / stock info
- Fundamental ratios (P/E, P/B, ROE, margins, etc.)
- Income statements (revenue/earnings growth)
- Insider trading (SEC Form 4)
- Analyst ratings / grades

FMP API docs: https://site.financialmodelingprep.com/developer/docs
Base URL (stable): https://financialmodelingprep.com/stable
Base URL (v3):     https://financialmodelingprep.com/api/v3
"""

import asyncio
import aiohttp
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from loguru import logger

from app.config import get_settings
from app.services.cache import cache
from app.services.data_fetcher.rate_limiter import RateLimiter

settings = get_settings()

# FMP stable API base (recommended for new integrations)
FMP_BASE_STABLE = "https://financialmodelingprep.com/stable"
# FMP v3 API base (fallback for endpoints not yet on stable)
FMP_BASE_V3 = "https://financialmodelingprep.com/api/v3"


class FMPService:
    """Service for fetching data from Financial Modeling Prep API."""

    def __init__(self):
        self.api_key = settings.FMP_API_KEY
        # FMP Ultimate: 3000 calls/min → 50/sec
        self.rate_limiter = RateLimiter(max_requests=50, time_window=1)
        self._session: Optional[aiohttp.ClientSession] = None
        # Dedicated event loop for sync wrappers (avoids "event loop closed" errors)
        self._bg_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bg_thread: Optional[threading.Thread] = None

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def _ensure_bg_loop(self):
        """Start a background thread with a persistent event loop for sync calls."""
        if self._bg_loop is None or self._bg_loop.is_closed():
            self._bg_loop = asyncio.new_event_loop()
            self._bg_thread = threading.Thread(
                target=self._bg_loop.run_forever, daemon=True
            )
            self._bg_thread.start()

    def _run_sync(self, coro):
        """Run an async coroutine from synchronous code using the background loop."""
        self._ensure_bg_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._bg_loop)
        return future.result(timeout=60)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _cache_key(self, prefix: str, symbol: str, **kwargs) -> str:
        parts = [f"fmp:{prefix}", symbol.upper()]
        for k, v in sorted(kwargs.items()):
            parts.append(f"{k}:{v}")
        return ":".join(parts)

    async def _fetch(self, url: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Make an authenticated GET request to FMP."""
        if not self.is_available:
            logger.warning("FMP API key not configured")
            return None

        # Use non-blocking rate limit check — run blocking wait_if_needed in thread
        # to avoid blocking the event loop
        await asyncio.to_thread(self.rate_limiter.wait_if_needed)

        if params is None:
            params = {}
        params["apikey"] = self.api_key

        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status == 401:
                    logger.error("FMP authentication failed — check FMP_API_KEY")
                    return None
                if resp.status == 429:
                    logger.warning("FMP rate limit hit")
                    return None
                if resp.status != 200:
                    logger.warning(f"FMP returned status {resp.status} for {url}")
                    return None
                data = await resp.json()
                # FMP returns [] for missing symbols and {"Error Message": ...} for errors
                if isinstance(data, dict) and "Error Message" in data:
                    logger.warning(f"FMP error: {data['Error Message']}")
                    return None
                return data
        except Exception as e:
            logger.error(f"FMP request failed for {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Profile / Stock Info
    # ------------------------------------------------------------------

    async def _fetch_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch and cache the raw FMP profile (single source of truth)."""
        ck = self._cache_key("profile_raw", symbol)
        cached = cache.get(ck)
        if cached:
            return cached

        data = await self._fetch(
            f"{FMP_BASE_STABLE}/profile",
            params={"symbol": symbol.upper()},
        )
        if not data:
            return None

        # FMP returns a list — take first element
        profile = data[0] if isinstance(data, list) and data else data
        if not profile or not isinstance(profile, dict):
            return None

        cache.set(ck, profile, ttl=settings.CACHE_TTL_FUNDAMENTALS)
        return profile

    def get_stock_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Synchronous wrapper — matches yahoo_service.get_stock_info() interface.

        Returns dict with keys the screening engine expects:
            symbol, name, sector, industry, market_cap, current_price,
            exchange, currency, country
        """
        return self._run_sync(self._get_stock_info_async(symbol))

    async def _get_stock_info_async(self, symbol: str) -> Optional[Dict[str, Any]]:
        ck = self._cache_key("stock_info", symbol)
        cached = cache.get(ck)
        if cached:
            logger.debug(f"Cache hit for {symbol} FMP stock info")
            return cached

        profile = await self._fetch_profile(symbol)
        if not profile:
            return None

        data = {
            "symbol": symbol.upper(),
            "name": profile.get("companyName"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "market_cap": profile.get("marketCap") or profile.get("mktCap"),
            "current_price": profile.get("price"),
            "exchange": profile.get("exchange") or profile.get("exchangeShortName"),
            "currency": profile.get("currency"),
            "country": profile.get("country"),
        }

        cache.set(ck, data, ttl=settings.CACHE_TTL_FUNDAMENTALS)
        return data

    # ------------------------------------------------------------------
    # Fundamentals (ratios + key metrics + income growth)
    # ------------------------------------------------------------------

    def get_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Synchronous wrapper — matches yahoo_service.get_fundamentals() interface.

        Returns dict with keys the screening engine expects:
            market_cap, enterprise_value, trailing_pe, forward_pe, peg_ratio,
            price_to_book, price_to_sales, revenue, revenue_growth,
            earnings_growth, profit_margins, operating_margins, roe, roa,
            debt_to_equity, current_ratio, quick_ratio, earnings_per_share,
            dividend_yield, beta
        """
        return self._run_sync(self._get_fundamentals_async(symbol))

    async def _get_fundamentals_async(self, symbol: str) -> Optional[Dict[str, Any]]:
        ck = self._cache_key("fundamentals", symbol)
        cached = cache.get(ck)
        if cached:
            logger.debug(f"Cache hit for {symbol} FMP fundamentals")
            return cached

        # Fetch profile, ratios-ttm, and key-metrics-ttm in parallel
        profile_task = self._fetch_profile(symbol)
        ratios_task = self._fetch(
            f"{FMP_BASE_STABLE}/ratios-ttm",
            params={"symbol": symbol.upper()},
        )
        metrics_task = self._fetch(
            f"{FMP_BASE_STABLE}/key-metrics-ttm",
            params={"symbol": symbol.upper()},
        )

        profile, ratios_raw, metrics_raw = await asyncio.gather(
            profile_task, ratios_task, metrics_task
        )

        if not profile:
            return None

        # Extract first element from list responses
        ratios = {}
        if ratios_raw:
            ratios = ratios_raw[0] if isinstance(ratios_raw, list) and ratios_raw else ratios_raw
            if not isinstance(ratios, dict):
                ratios = {}

        metrics = {}
        if metrics_raw:
            metrics = metrics_raw[0] if isinstance(metrics_raw, list) and metrics_raw else metrics_raw
            if not isinstance(metrics, dict):
                metrics = {}

        # Compute revenue/earnings growth from income statements
        revenue_growth, earnings_growth = await self._compute_growth(symbol)

        data = {
            # From profile
            "market_cap": profile.get("marketCap") or profile.get("mktCap"),
            "beta": profile.get("beta"),

            # From ratios-ttm (stable API field names)
            "trailing_pe": ratios.get("priceToEarningsRatioTTM") or ratios.get("peRatioTTM"),
            "forward_pe": ratios.get("forwardPriceToEarningsGrowthRatioTTM") or ratios.get("priceToEarningsRatioTTM"),
            "peg_ratio": ratios.get("priceToEarningsGrowthRatioTTM") or ratios.get("pegRatioTTM"),
            "price_to_book": ratios.get("priceToBookRatioTTM"),
            "price_to_sales": ratios.get("priceToSalesRatioTTM"),
            "profit_margins": ratios.get("netProfitMarginTTM"),
            "operating_margins": ratios.get("operatingProfitMarginTTM"),
            "debt_to_equity": ratios.get("debtToEquityRatioTTM") or ratios.get("debtEquityRatioTTM"),
            "current_ratio": ratios.get("currentRatioTTM"),
            "quick_ratio": ratios.get("quickRatioTTM"),
            "dividend_yield": ratios.get("dividendYieldTTM"),

            # From key-metrics-ttm (ROE, ROA, EV, EPS are here on stable API)
            "roe": metrics.get("returnOnEquityTTM"),
            "roa": metrics.get("returnOnAssetsTTM"),
            "enterprise_value": metrics.get("enterpriseValueTTM"),
            "earnings_per_share": metrics.get("netIncomePerShareTTM"),
            "revenue": metrics.get("revenuePerShareTTM"),

            # Computed from income statements
            "revenue_growth": revenue_growth,
            "earnings_growth": earnings_growth,
        }

        cache.set(ck, data, ttl=settings.CACHE_TTL_FUNDAMENTALS)
        return data

    async def _compute_growth(self, symbol: str) -> tuple:
        """
        Compute YoY revenue and earnings growth from the last 4 quarterly
        income statements.

        Returns (revenue_growth, earnings_growth) as floats (e.g. 0.25 = 25%)
        or (None, None) if insufficient data.
        """
        data = await self._fetch(
            f"{FMP_BASE_STABLE}/income-statement",
            params={"symbol": symbol.upper(), "period": "quarter", "limit": "8"},
        )
        if not data or not isinstance(data, list) or len(data) < 5:
            return (None, None)

        # Statements come most-recent-first
        try:
            latest_rev = data[0].get("revenue")
            year_ago_rev = data[4].get("revenue")
            latest_ni = data[0].get("netIncome")
            year_ago_ni = data[4].get("netIncome")

            rev_growth = None
            if latest_rev and year_ago_rev and year_ago_rev != 0:
                rev_growth = (latest_rev - year_ago_rev) / abs(year_ago_rev)

            earn_growth = None
            if latest_ni and year_ago_ni and year_ago_ni != 0:
                earn_growth = (latest_ni - year_ago_ni) / abs(year_ago_ni)

            return (rev_growth, earn_growth)
        except (TypeError, IndexError, ZeroDivisionError):
            return (None, None)

    # ------------------------------------------------------------------
    # Current Price (from profile — lightweight)
    # ------------------------------------------------------------------

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from cached profile data."""
        return self._run_sync(self._get_current_price_async(symbol))

    async def _get_current_price_async(self, symbol: str) -> Optional[float]:
        profile = await self._fetch_profile(symbol)
        if profile:
            return profile.get("price")
        return None

    # ------------------------------------------------------------------
    # Insider Trading (SEC Form 4)
    # ------------------------------------------------------------------

    async def get_insider_trades(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch insider trading data from FMP.

        Returns list of dicts with keys:
            insider_name, title, trade_type (buy/sell), shares, price, value, date
        """
        ck = self._cache_key("insider", symbol)
        cached = cache.get(ck)
        if cached:
            return cached

        data = await self._fetch(
            f"{FMP_BASE_STABLE}/insider-trading",
            params={"symbol": symbol.upper(), "limit": str(limit)},
        )
        if not data or not isinstance(data, list):
            return []

        trades = []
        for row in data:
            try:
                tx_type = (row.get("transactionType") or "").lower()
                if "purchase" in tx_type or "buy" in tx_type or tx_type == "p-purchase":
                    trade_type = "buy"
                elif "sale" in tx_type or "sell" in tx_type or tx_type == "s-sale":
                    trade_type = "sell"
                else:
                    continue

                shares = abs(int(row.get("securitiesTransacted") or 0))
                price = float(row.get("price") or 0)
                value = shares * price

                trade_date = row.get("transactionDate") or row.get("filingDate")
                if trade_date and isinstance(trade_date, str):
                    trade_date = datetime.strptime(trade_date[:10], "%Y-%m-%d")
                else:
                    trade_date = datetime.now()

                trades.append({
                    "insider_name": row.get("reportingName") or row.get("reportingCik") or "Unknown",
                    "title": row.get("typeOfOwner") or "",
                    "trade_type": trade_type,
                    "shares": shares,
                    "price": price,
                    "value": value,
                    "date": trade_date,
                })
            except Exception as e:
                logger.debug(f"Error parsing FMP insider trade: {e}")
                continue

        cache.set(ck, trades, ttl=3600)  # 1 hour
        return trades

    # ------------------------------------------------------------------
    # Analyst Ratings / Grades
    # ------------------------------------------------------------------

    async def get_analyst_ratings(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch analyst grade history.

        Returns dict:
            has_upgrade: bool (upgrade in last 90 days)
            recent_grades: list of recent grade changes
            consensus: str (e.g. "Buy", "Hold")
            price_target: float or None
        """
        ck = self._cache_key("analyst", symbol)
        cached = cache.get(ck)
        if cached:
            return cached

        grades_data = await self._fetch(
            f"{FMP_BASE_STABLE}/grades",
            params={"symbol": symbol.upper(), "limit": "20"},
        )

        result = {
            "has_upgrade": False,
            "recent_grades": [],
            "consensus": None,
            "price_target": None,
        }

        if not grades_data or not isinstance(grades_data, list):
            cache.set(ck, result, ttl=21600)  # 6 hours
            return result

        cutoff = datetime.now() - timedelta(days=90)
        upgrades = 0
        downgrades = 0
        recent = []

        for g in grades_data[:20]:
            try:
                grade_date_str = g.get("date")
                if grade_date_str:
                    grade_date = datetime.strptime(grade_date_str[:10], "%Y-%m-%d")
                else:
                    continue

                action = (g.get("newGrade") or "").lower()
                prev = (g.get("previousGrade") or "").lower()

                # Determine if upgrade or downgrade
                buy_terms = {"buy", "strong buy", "outperform", "overweight", "positive"}
                hold_terms = {"hold", "neutral", "equal-weight", "market perform", "sector perform", "in-line"}
                sell_terms = {"sell", "strong sell", "underperform", "underweight", "negative", "reduce"}

                def _rank(grade):
                    gl = grade.lower()
                    if gl in buy_terms:
                        return 3
                    if gl in hold_terms:
                        return 2
                    if gl in sell_terms:
                        return 1
                    return 2  # default to hold

                new_rank = _rank(action)
                prev_rank = _rank(prev) if prev else 2

                is_upgrade = new_rank > prev_rank
                is_downgrade = new_rank < prev_rank

                if grade_date >= cutoff:
                    if is_upgrade:
                        upgrades += 1
                    if is_downgrade:
                        downgrades += 1

                recent.append({
                    "firm": g.get("gradingCompany"),
                    "date": grade_date_str,
                    "new_grade": g.get("newGrade"),
                    "previous_grade": g.get("previousGrade"),
                    "action": "upgrade" if is_upgrade else ("downgrade" if is_downgrade else "maintain"),
                })
            except Exception as e:
                logger.debug(f"Error parsing FMP grade: {e}")
                continue

        result["has_upgrade"] = upgrades > 0
        result["recent_grades"] = recent[:10]

        # Simple consensus from latest grades
        if recent:
            buy_count = sum(1 for r in recent[:10] if r.get("new_grade", "").lower() in
                           {"buy", "strong buy", "outperform", "overweight"})
            total = min(len(recent), 10)
            if total > 0:
                ratio = buy_count / total
                if ratio >= 0.6:
                    result["consensus"] = "Buy"
                elif ratio >= 0.3:
                    result["consensus"] = "Hold"
                else:
                    result["consensus"] = "Sell"

        # Fetch price target from analyst-estimates
        estimates = await self._fetch(
            f"{FMP_BASE_STABLE}/analyst-estimates",
            params={"symbol": symbol.upper(), "limit": "1"},
        )
        if estimates and isinstance(estimates, list) and estimates:
            est = estimates[0]
            result["price_target"] = est.get("estimatedRevenue")  # placeholder
            # Some FMP endpoints provide price targets differently
            # We'll rely on the grades consensus for now

        cache.set(ck, result, ttl=21600)  # 6 hours
        return result

    # ------------------------------------------------------------------
    # News (from FMP — supplementary to Finnhub)
    # ------------------------------------------------------------------

    async def get_company_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch company-specific news from FMP."""
        ck = self._cache_key("news", symbol)
        cached = cache.get(ck)
        if cached:
            return cached

        data = await self._fetch(
            f"{FMP_BASE_STABLE}/stock-news",
            params={"symbol": symbol.upper(), "limit": str(limit)},
        )
        if not data or not isinstance(data, list):
            return []

        news = []
        for item in data:
            news.append({
                "title": item.get("title"),
                "source": item.get("site") or item.get("publishedDate", ""),
                "published": item.get("publishedDate"),
                "url": item.get("url"),
                "summary": item.get("text"),
                "sentiment": item.get("sentiment"),
            })

        cache.set(ck, news, ttl=1800)  # 30 minutes
        return news

    # =========================================================================
    # Technical Indicators (for Strategy Selection)
    # =========================================================================

    def get_technical_indicator(
        self, symbol: str, indicator_type: str, period: int = 14
    ) -> Optional[float]:
        """
        Fetch a single pre-calculated technical indicator from FMP.
        Returns the latest value or None.

        indicator_type: "rsi", "sma", "ema", "atr"
        """
        return self._run_sync(
            self._get_technical_indicator_async(symbol, indicator_type, period)
        )

    async def _get_technical_indicator_async(
        self, symbol: str, indicator_type: str, period: int
    ) -> Optional[float]:
        ck = self._cache_key("technical", symbol, type=indicator_type, period=period)
        cached = cache.get(ck)
        if cached is not None:
            return cached

        data = await self._fetch(
            f"{FMP_BASE_V3}/technical_indicator/daily/{symbol.upper()}",
            params={"type": indicator_type, "period": period},
        )
        if not data or not isinstance(data, list) or len(data) == 0:
            return None

        # FMP returns list sorted by date desc — take the latest
        latest = data[0]
        value = latest.get(indicator_type)
        if value is not None:
            try:
                value = float(value)
            except (ValueError, TypeError):
                return None
            cache.set(ck, value, ttl=settings.CACHE_TTL_TECHNICAL_INDICATORS)
        return value

    def get_strategy_metrics(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch all technical metrics needed for strategy selection in one call.
        Returns: {rsi, sma20, sma50, sma200, atr, ema12, ema26, adx}
        Cached for 1 hour.
        """
        return self._run_sync(self._get_strategy_metrics_async(symbol))

    async def _get_strategy_metrics_async(self, symbol: str) -> Optional[Dict[str, Any]]:
        ck = self._cache_key("strategy_metrics", symbol)
        cached = cache.get(ck)
        if cached is not None:
            logger.debug(f"Cache hit for {symbol} FMP strategy metrics")
            return cached

        # Fetch all indicators in parallel
        tasks = [
            self._get_technical_indicator_async(symbol, "rsi", 14),
            self._get_technical_indicator_async(symbol, "sma", 20),
            self._get_technical_indicator_async(symbol, "sma", 50),
            self._get_technical_indicator_async(symbol, "sma", 200),
            self._get_technical_indicator_async(symbol, "atr", 14),
            self._get_technical_indicator_async(symbol, "ema", 12),
            self._get_technical_indicator_async(symbol, "ema", 26),
            self._get_technical_indicator_async(symbol, "adx", 14),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Unpack, treating exceptions as None
        def safe(val):
            return val if not isinstance(val, Exception) else None

        metrics = {
            "rsi": safe(results[0]),
            "sma20": safe(results[1]),
            "sma50": safe(results[2]),
            "sma200": safe(results[3]),
            "atr": safe(results[4]),
            "ema12": safe(results[5]),
            "ema26": safe(results[6]),
            "adx": safe(results[7]),
        }

        # Only cache if we got at least some data
        if any(v is not None for v in metrics.values()):
            cache.set(ck, metrics, ttl=settings.CACHE_TTL_TECHNICAL_INDICATORS)
            return metrics

        return None

    # ------------------------------------------------------------------
    # Stock Screener (Dynamic Universe)
    # ------------------------------------------------------------------

    async def _get_screener_universe_async(
        self,
        market_cap_min: int = 500_000_000,
        market_cap_max: int = 100_000_000_000,
        price_min: float = 5.0,
        price_max: float = 500.0,
        volume_min: int = 100_000,
        sector: Optional[str] = None,
        limit: int = 1000,
    ) -> List[str]:
        """
        Fetch a dynamic stock universe from FMP's company screener.

        Returns a list of ticker symbols matching the given criteria.
        Results are cached in Redis for 4 hours.
        """
        import hashlib

        # Build a stable cache key from params
        param_str = f"{market_cap_min}:{market_cap_max}:{price_min}:{price_max}:{volume_min}:{sector}:{limit}"
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:12]
        ck = f"fmp:screener_universe:{param_hash}"

        cached = cache.get(ck)
        if cached is not None:
            logger.info(f"FMP screener universe cache hit ({len(cached)} symbols)")
            return cached

        params = {
            "marketCapMoreThan": str(market_cap_min),
            "marketCapLowerThan": str(market_cap_max),
            "priceMoreThan": str(price_min),
            "priceLowerThan": str(price_max),
            "volumeMoreThan": str(volume_min),
            "isActivelyTrading": "true",
            "isEtf": "false",
            "isFund": "false",
            "country": "US",
            "exchange": "NYSE,NASDAQ,AMEX",
            "limit": str(limit),
        }
        if sector:
            params["sector"] = sector

        data = await self._fetch(
            f"{FMP_BASE_STABLE}/company-screener",
            params=params,
        )

        if not data or not isinstance(data, list):
            logger.warning("FMP screener returned no data, falling back to hardcoded universe")
            return []

        symbols = []
        for item in data:
            symbol = item.get("symbol")
            if symbol and isinstance(symbol, str) and "." not in symbol and "-" not in symbol:
                symbols.append(symbol.upper())

        # Cache for 4 hours
        cache.set(ck, symbols, ttl=14400)
        logger.info(f"FMP screener universe: {len(symbols)} symbols (cached 4h)")
        return symbols

    def get_screener_universe(
        self,
        market_cap_min: int = 500_000_000,
        market_cap_max: int = 100_000_000_000,
        price_min: float = 5.0,
        price_max: float = 500.0,
        volume_min: int = 100_000,
        sector: Optional[str] = None,
        limit: int = 1000,
    ) -> List[str]:
        """Synchronous wrapper for get_screener_universe."""
        return self._run_sync(
            self._get_screener_universe_async(
                market_cap_min=market_cap_min,
                market_cap_max=market_cap_max,
                price_min=price_min,
                price_max=price_max,
                volume_min=volume_min,
                sector=sector,
                limit=limit,
            )
        )

    def get_bulk_strategy_metrics(self, symbols: list) -> Dict[str, Dict[str, Any]]:
        """
        Fetch strategy metrics for multiple symbols.
        Returns: {symbol: {rsi, sma20, sma50, ...}, ...}
        """
        return self._run_sync(self._get_bulk_strategy_metrics_async(symbols))

    async def _get_bulk_strategy_metrics_async(
        self, symbols: list
    ) -> Dict[str, Dict[str, Any]]:
        # Limit concurrency to avoid overwhelming FMP API
        # Each symbol triggers up to 8 indicator fetches internally
        sem = asyncio.Semaphore(5)

        async def limited(s):
            async with sem:
                return await self._get_strategy_metrics_async(s)

        tasks = [limited(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        bulk = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch strategy metrics for {symbol}: {result}")
                bulk[symbol] = None
            else:
                bulk[symbol] = result
        return bulk


# Singleton instance
fmp_service = FMPService()
