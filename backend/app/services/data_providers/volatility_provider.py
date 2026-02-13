"""
Concrete implementation of VolatilityDataProvider.

Uses Alpaca to fetch volatility structure metrics:
- ^VIX: CBOE Volatility Index
- ^VIX3M: CBOE 3-Month Volatility Index (fallback: ^VXV)
- ^VVIX: CBOE VIX of VIX (optional)

Derived:
    term_slope = VIX3M - VIX (positive contango = calm, negative backwardation = stress)
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from loguru import logger

from .interfaces import DataQuality
from app.services.data_fetcher.alpaca_service import alpaca_service


# Staleness threshold for daily market data (72h = weekend-safe)
VOL_STALENESS_HOURS = 72

# Ticker symbols
VIX_TICKER = "^VIX"
VIX3M_TICKERS = ["^VIX3M", "^VXV"]  # VXV as fallback
VVIX_TICKER = "^VVIX"


def _fetch_ticker_price(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch latest price for a ticker using Alpaca historical bars (blocking).

    Returns:
        {"value": float, "date": str, "is_stale": bool} or None
    """
    try:
        hist = alpaca_service.get_historical_prices(symbol, period="5d")

        if hist is None or hist.empty:
            return None

        close_col = 'Close' if 'Close' in hist.columns else 'close'
        value = float(hist[close_col].iloc[-1])
        latest_date = hist.index[-1]

        # Check staleness
        if hasattr(latest_date, 'to_pydatetime'):
            latest_dt = latest_date.to_pydatetime().replace(tzinfo=None)
        else:
            latest_dt = latest_date

        age_hours = (datetime.utcnow() - latest_dt).total_seconds() / 3600
        is_stale = age_hours > VOL_STALENESS_HOURS

        date_str = latest_date.strftime("%Y-%m-%d") if hasattr(latest_date, 'strftime') else str(latest_date)[:10]

        return {
            "value": round(value, 2),
            "date": date_str,
            "is_stale": is_stale,
        }
    except Exception as e:
        logger.warning(f"VolatilityProvider: Failed to fetch {symbol}: {e}")
        return None


class VolatilityDataProviderImpl:
    """
    VolatilityDataProvider implementation using Alpaca.

    term_slope is derived as VIX3M - VIX.
    VVIX is optional — reduces completeness if missing.
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=3)

    async def get_current(self) -> Dict[str, Any]:
        """
        Get current volatility structure metrics.

        Returns:
            {
                "quality": DataQuality dict,
                "metrics": {
                    "vix": MetricValue dict,
                    "term_slope": MetricValue dict,
                    "vvix": MetricValue dict
                }
            }
        """
        loop = asyncio.get_event_loop()

        # Fetch VIX, VIX3M, and VVIX concurrently via thread pool
        vix_future = loop.run_in_executor(self._executor, _fetch_ticker_price, VIX_TICKER)
        vix3m_future = loop.run_in_executor(self._executor, self._fetch_vix3m)
        vvix_future = loop.run_in_executor(self._executor, _fetch_ticker_price, VVIX_TICKER)

        vix_data, vix3m_data, vvix_data = await asyncio.gather(
            vix_future, vix3m_future, vvix_future
        )

        metrics = {}
        stale_series = []
        missing_series = []
        latest_date = None

        # VIX
        if vix_data is not None:
            metrics["vix"] = {
                "value": vix_data["value"],
                "unit": "index",
                "available": True,
            }
            if vix_data["is_stale"]:
                stale_series.append("vix")
            latest_date = self._update_latest_date(latest_date, vix_data["date"])
        else:
            metrics["vix"] = {"value": None, "unit": "index", "available": False}
            missing_series.append("vix")

        # Term slope (VIX3M - VIX)
        if vix_data is not None and vix3m_data is not None:
            term_slope = round(vix3m_data["value"] - vix_data["value"], 2)
            metrics["term_slope"] = {
                "value": term_slope,
                "unit": "points",
                "available": True,
            }
            if vix3m_data["is_stale"]:
                stale_series.append("term_slope")
            latest_date = self._update_latest_date(latest_date, vix3m_data["date"])
        else:
            metrics["term_slope"] = {"value": None, "unit": "points", "available": False}
            missing_series.append("term_slope")

        # VVIX (optional)
        if vvix_data is not None:
            metrics["vvix"] = {
                "value": vvix_data["value"],
                "unit": "index",
                "available": True,
            }
            if vvix_data["is_stale"]:
                stale_series.append("vvix")
            latest_date = self._update_latest_date(latest_date, vvix_data["date"])
        else:
            metrics["vvix"] = {"value": None, "unit": "index", "available": False}
            missing_series.append("vvix")

        # Build quality — VVIX missing only reduces completeness, not a hard failure
        # Core metrics: vix + term_slope (2). Optional: vvix (1). Total = 3.
        total_metrics = 3
        available_count = total_metrics - len(missing_series)
        completeness = available_count / total_metrics

        is_stale = len(stale_series) > 0
        stale_reason = None
        if is_stale:
            stale_reason = f"Stale series: {', '.join(stale_series)}"

        confidence = 100.0
        confidence -= len(missing_series) * 15
        confidence -= len(stale_series) * 10

        if is_stale and confidence > 40:
            confidence = 40.0

        confidence = max(0.0, min(100.0, confidence))

        quality = DataQuality(
            source="alpaca",
            as_of=datetime.strptime(latest_date, "%Y-%m-%d") if latest_date else datetime.utcnow(),
            is_stale=is_stale,
            stale_reason=stale_reason,
            completeness=completeness,
            confidence_score=confidence,
        )

        return {
            "quality": quality.to_dict(),
            "metrics": metrics,
        }

    def _fetch_vix3m(self) -> Optional[Dict[str, Any]]:
        """Fetch VIX3M with fallback to VXV."""
        for ticker in VIX3M_TICKERS:
            result = _fetch_ticker_price(ticker)
            if result is not None:
                return result
        return None

    def _update_latest_date(self, current: Optional[str], new: str) -> str:
        """Update latest date if new is more recent."""
        if current is None:
            return new
        try:
            current_dt = datetime.strptime(current, "%Y-%m-%d")
            new_dt = datetime.strptime(new, "%Y-%m-%d")
            return new if new_dt > current_dt else current
        except ValueError:
            return current


# Singleton instance
_volatility_provider: Optional[VolatilityDataProviderImpl] = None


def get_volatility_provider() -> VolatilityDataProviderImpl:
    """Get singleton volatility provider instance."""
    global _volatility_provider
    if _volatility_provider is None:
        _volatility_provider = VolatilityDataProviderImpl()
    return _volatility_provider
