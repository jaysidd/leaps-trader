"""
FRED API client for macro economic data.

FRED (Federal Reserve Economic Data) provides free access to economic data.
API Documentation: https://fred.stlouisfed.org/docs/api/fred/

Series used for liquidity analysis:
- WALCL: Fed Balance Sheet Total Assets (weekly, Wednesday)
- RRPONTSYD: Overnight Reverse Repurchase Agreements (daily)
- WTREGEN: Treasury General Account (weekly, Wednesday)
- NFCI: Chicago Fed National Financial Conditions Index (weekly, Wednesday)
- DGS10: 10-Year Treasury Constant Maturity Rate (daily)
- T10YIE: 10-Year Breakeven Inflation Rate (daily)
"""

import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger

from app.config import get_settings
from ..interfaces import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUpstreamFormatError,
    ProviderUnavailableError,
    DataQuality,
    SeriesPoint,
)


# FRED series IDs for liquidity metrics
FRED_SERIES = {
    "fed_balance_sheet": "WALCL",      # Fed Total Assets (weekly)
    "rrp": "RRPONTSYD",                 # Reverse Repo (daily)
    "tga": "WTREGEN",                   # Treasury General Account (weekly)
    "fci": "NFCI",                      # Financial Conditions Index (weekly)
    "dgs10": "DGS10",                   # 10Y Treasury Yield (daily)
    "t10yie": "T10YIE",                 # 10Y Breakeven Inflation (daily)
    "hy_oas": "BAMLH0A0HYM2",           # ICE BofA US High Yield OAS (daily)
    "ig_oas": "BAMLC0A0CM",             # ICE BofA US Corporate IG OAS (daily)
}

# Default staleness thresholds (hours)
STALENESS_THRESHOLDS = {
    "fed_balance_sheet": 168,  # 7 days (weekly data)
    "rrp": 48,                  # 2 days (daily data)
    "tga": 168,                 # 7 days (weekly data)
    "fci": 168,                 # 7 days (weekly data)
    "dgs10": 48,                # 2 days (daily data)
    "t10yie": 48,               # 2 days (daily data)
    "hy_oas": 72,               # 3 days (daily data, weekend-safe)
    "ig_oas": 72,               # 3 days (daily data, weekend-safe)
}


class FREDService:
    """
    FRED API client for fetching economic data series.

    Rate limits: 120 requests per minute for registered users.
    """

    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.FRED_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_request_time: Optional[datetime] = None
        self._min_request_interval = 0.5  # 500ms between requests

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _rate_limit(self):
        """Simple rate limiting."""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            if elapsed < self._min_request_interval:
                await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = datetime.utcnow()

    async def get_series(
        self,
        series_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Fetch observations for a FRED series.

        Args:
            series_id: FRED series ID (e.g., "WALCL")
            start_date: Start date (YYYY-MM-DD format)
            end_date: End date (YYYY-MM-DD format)
            limit: Maximum number of observations (default 100)

        Returns:
            {
                "series_id": "WALCL",
                "observations": [
                    {"date": "2026-01-01", "value": 7530000.0},
                    ...
                ],
                "last_updated": "2026-01-15T14:00:00Z",
                "is_stale": false
            }

        Raises:
            ProviderAuthError: Invalid API key
            ProviderRateLimitError: Rate limit exceeded
            ProviderTimeoutError: Request timeout
            ProviderUpstreamFormatError: Unexpected response format
            ProviderUnavailableError: Service unavailable
        """
        if not self.api_key:
            raise ProviderAuthError("FRED API key not configured")

        await self._rate_limit()

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }

        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date

        session = await self._get_session()

        try:
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status == 401:
                    raise ProviderAuthError("Invalid FRED API key")
                if response.status == 429:
                    raise ProviderRateLimitError(
                        "FRED rate limit exceeded",
                        retry_after_seconds=60
                    )
                if response.status >= 500:
                    raise ProviderUnavailableError(
                        f"FRED service unavailable (status {response.status})"
                    )
                if response.status != 200:
                    text = await response.text()
                    raise ProviderUpstreamFormatError(
                        f"FRED API error (status {response.status}): {text[:200]}"
                    )

                data = await response.json()

        except asyncio.TimeoutError:
            raise ProviderTimeoutError("FRED API request timed out")
        except aiohttp.ClientError as e:
            raise ProviderUnavailableError(f"FRED API connection error: {str(e)}")

        # Parse observations
        if "observations" not in data:
            raise ProviderUpstreamFormatError(
                f"FRED response missing 'observations' for series {series_id}"
            )

        observations = []
        last_valid_date = None

        for obs in data["observations"]:
            date_str = obs.get("date")
            value_str = obs.get("value")

            # Skip missing values (FRED uses "." for missing)
            if value_str == "." or value_str is None:
                continue

            try:
                value = float(value_str)
                observations.append({
                    "date": date_str,
                    "value": value,
                })
                if last_valid_date is None:
                    last_valid_date = date_str
            except (ValueError, TypeError):
                logger.warning(f"FRED: Invalid value '{value_str}' for {series_id} on {date_str}")
                continue

        # Determine staleness
        is_stale = False
        if last_valid_date:
            try:
                last_date = datetime.strptime(last_valid_date, "%Y-%m-%d")
                age_hours = (datetime.utcnow() - last_date).total_seconds() / 3600

                # Get threshold for this series
                metric_name = next(
                    (k for k, v in FRED_SERIES.items() if v == series_id),
                    None
                )
                threshold = STALENESS_THRESHOLDS.get(metric_name, 72)
                is_stale = age_hours > threshold
            except ValueError:
                pass

        return {
            "series_id": series_id,
            "observations": observations,
            "last_updated": last_valid_date,
            "is_stale": is_stale,
        }

    async def get_latest_value(self, series_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent value for a FRED series.

        Returns:
            {"date": "2026-01-15", "value": 7530000.0, "is_stale": false}
            or None if no data available
        """
        result = await self.get_series(series_id, limit=1)

        if result["observations"]:
            obs = result["observations"][0]
            return {
                "date": obs["date"],
                "value": obs["value"],
                "is_stale": result["is_stale"],
            }
        return None

    async def get_series_with_changes(
        self,
        series_id: str,
        lookback_weeks: int = 5,
    ) -> Dict[str, Any]:
        """
        Get latest value with 1-week and 4-week change calculations.

        Args:
            series_id: FRED series ID
            lookback_weeks: Number of weeks of history to fetch

        Returns:
            {
                "value": 7530000.0,
                "date": "2026-01-15",
                "change_1w": -0.3,  # percent for monetary, absolute for indices
                "change_4w": -1.1,
                "is_stale": false
            }
        """
        # Fetch enough data for change calculations
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(weeks=lookback_weeks)).strftime("%Y-%m-%d")

        result = await self.get_series(
            series_id,
            start_date=start_date,
            end_date=end_date,
            limit=50,
        )

        observations = result["observations"]
        if not observations:
            return {
                "value": None,
                "date": None,
                "change_1w": None,
                "change_4w": None,
                "is_stale": True,
            }

        # Latest value (observations are sorted desc)
        latest = observations[0]
        latest_value = latest["value"]
        latest_date = latest["date"]

        # Find values from ~1 week and ~4 weeks ago
        # FRED data has varying frequencies, so we look for closest date
        value_1w_ago = None
        value_4w_ago = None

        latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
        target_1w = latest_dt - timedelta(days=7)
        target_4w = latest_dt - timedelta(days=28)

        for obs in observations[1:]:
            obs_date = datetime.strptime(obs["date"], "%Y-%m-%d")

            # Find closest to 1 week ago
            if value_1w_ago is None and obs_date <= target_1w:
                value_1w_ago = obs["value"]

            # Find closest to 4 weeks ago
            if value_4w_ago is None and obs_date <= target_4w:
                value_4w_ago = obs["value"]

            if value_1w_ago is not None and value_4w_ago is not None:
                break

        # Calculate changes
        # For monetary series (WALCL, RRPONTSYD, WTREGEN): percent change
        # For indices (NFCI, DGS10, T10YIE): absolute change
        is_monetary = series_id in ["WALCL", "RRPONTSYD", "WTREGEN"]

        change_1w = None
        change_4w = None

        if value_1w_ago is not None and value_1w_ago != 0:
            if is_monetary:
                change_1w = round(((latest_value - value_1w_ago) / value_1w_ago) * 100, 2)
            else:
                change_1w = round(latest_value - value_1w_ago, 4)

        if value_4w_ago is not None and value_4w_ago != 0:
            if is_monetary:
                change_4w = round(((latest_value - value_4w_ago) / value_4w_ago) * 100, 2)
            else:
                change_4w = round(latest_value - value_4w_ago, 4)

        return {
            "value": latest_value,
            "date": latest_date,
            "change_1w": change_1w,
            "change_4w": change_4w,
            "is_stale": result["is_stale"],
        }

    async def get_multiple_series(
        self,
        series_ids: List[str],
        lookback_weeks: int = 5,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch multiple series concurrently with change calculations.

        Args:
            series_ids: List of FRED series IDs
            lookback_weeks: Number of weeks of history to fetch

        Returns:
            {
                "WALCL": {"value": ..., "change_1w": ..., ...},
                "RRPONTSYD": {"value": ..., "change_1w": ..., ...},
                ...
            }
        """
        tasks = [
            self.get_series_with_changes(sid, lookback_weeks)
            for sid in series_ids
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for series_id, result in zip(series_ids, results):
            if isinstance(result, Exception):
                logger.error(f"FRED: Error fetching {series_id}: {result}")
                output[series_id] = {
                    "value": None,
                    "date": None,
                    "change_1w": None,
                    "change_4w": None,
                    "is_stale": True,
                    "error": str(result),
                }
            else:
                output[series_id] = result

        return output


# Singleton instance
_fred_service: Optional[FREDService] = None


def get_fred_service() -> FREDService:
    """Get singleton FRED service instance."""
    global _fred_service
    if _fred_service is None:
        _fred_service = FREDService()
    return _fred_service
