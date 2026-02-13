"""
Concrete implementation of LiquidityDataProvider.

Combines FRED data to provide liquidity metrics:
- Fed Balance Sheet (WALCL)
- Reverse Repo (RRPONTSYD)
- Treasury General Account (WTREGEN)
- Financial Conditions Index (NFCI)
- Real Yield = DGS10 - T10YIE (derived)
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger

from .interfaces import (
    DataQuality,
    SeriesPoint,
    MetricValue,
    ProviderError,
)
from .fred import FREDService, get_fred_service, FRED_SERIES

# Liquidity-only FRED series — subset of FRED_SERIES relevant to liquidity.
# Credit series (hy_oas, ig_oas) are excluded to avoid extra FRED calls
# and polluting liquidity history output.
LIQUIDITY_FRED_SERIES = {
    k: v for k, v in FRED_SERIES.items()
    if k in ("fed_balance_sheet", "rrp", "tga", "fci", "dgs10", "t10yie")
}


class LiquidityDataProviderImpl:
    """
    LiquidityDataProvider implementation using FRED data.

    Real yield is derived as: real_yield_10y = DGS10 - T10YIE
    """

    def __init__(self, fred_service: Optional[FREDService] = None):
        self._fred = fred_service or get_fred_service()

    async def get_current(self) -> Dict[str, Any]:
        """
        Get current liquidity metrics.

        Returns:
            {
                "quality": DataQuality dict,
                "metrics": {
                    "fed_balance_sheet": MetricValue dict,
                    "rrp": MetricValue dict,
                    "tga": MetricValue dict,
                    "fci": MetricValue dict,
                    "real_yield_10y": MetricValue dict
                }
            }
        """
        # Fetch only liquidity-relevant FRED series
        series_to_fetch = list(LIQUIDITY_FRED_SERIES.values())

        try:
            raw_data = await self._fred.get_multiple_series(
                series_to_fetch,
                lookback_weeks=5,
            )
        except ProviderError as e:
            logger.error(f"LiquidityProvider: Failed to fetch FRED data: {e}")
            return self._build_error_response(str(e))

        # Build metrics from raw data
        metrics = {}
        stale_series = []
        missing_series = []
        latest_date = None

        # Fed Balance Sheet (in millions, convert to USD)
        fed_data = raw_data.get("WALCL", {})
        if fed_data.get("value") is not None:
            # WALCL is in millions
            value = fed_data["value"] * 1_000_000
            metrics["fed_balance_sheet"] = {
                "value": value,
                "unit": "usd",
                "change_1w": fed_data.get("change_1w"),
                "change_4w": fed_data.get("change_4w"),
                "available": True,
            }
            if fed_data.get("is_stale"):
                stale_series.append("fed_balance_sheet")
            if fed_data.get("date"):
                latest_date = self._update_latest_date(latest_date, fed_data["date"])
        else:
            metrics["fed_balance_sheet"] = self._missing_metric("usd")
            missing_series.append("fed_balance_sheet")

        # Reverse Repo (in billions, convert to USD)
        rrp_data = raw_data.get("RRPONTSYD", {})
        if rrp_data.get("value") is not None:
            # RRPONTSYD is in billions
            value = rrp_data["value"] * 1_000_000_000
            metrics["rrp"] = {
                "value": value,
                "unit": "usd",
                "change_1w": rrp_data.get("change_1w"),
                "change_4w": rrp_data.get("change_4w"),
                "available": True,
            }
            if rrp_data.get("is_stale"):
                stale_series.append("rrp")
            if rrp_data.get("date"):
                latest_date = self._update_latest_date(latest_date, rrp_data["date"])
        else:
            metrics["rrp"] = self._missing_metric("usd")
            missing_series.append("rrp")

        # Treasury General Account (in millions, convert to USD)
        tga_data = raw_data.get("WTREGEN", {})
        if tga_data.get("value") is not None:
            # WTREGEN is in millions
            value = tga_data["value"] * 1_000_000
            metrics["tga"] = {
                "value": value,
                "unit": "usd",
                "change_1w": tga_data.get("change_1w"),
                "change_4w": tga_data.get("change_4w"),
                "available": True,
            }
            if tga_data.get("is_stale"):
                stale_series.append("tga")
            if tga_data.get("date"):
                latest_date = self._update_latest_date(latest_date, tga_data["date"])
        else:
            metrics["tga"] = self._missing_metric("usd")
            missing_series.append("tga")

        # Financial Conditions Index
        fci_data = raw_data.get("NFCI", {})
        if fci_data.get("value") is not None:
            metrics["fci"] = {
                "value": fci_data["value"],
                "unit": "index",
                "change_1w": fci_data.get("change_1w"),
                "change_4w": fci_data.get("change_4w"),
                "available": True,
            }
            if fci_data.get("is_stale"):
                stale_series.append("fci")
            if fci_data.get("date"):
                latest_date = self._update_latest_date(latest_date, fci_data["date"])
        else:
            metrics["fci"] = self._missing_metric("index")
            missing_series.append("fci")

        # Real Yield = DGS10 - T10YIE (derived)
        dgs10_data = raw_data.get("DGS10", {})
        t10yie_data = raw_data.get("T10YIE", {})

        dgs10_value = dgs10_data.get("value")
        t10yie_value = t10yie_data.get("value")

        if dgs10_value is not None and t10yie_value is not None:
            real_yield = round(dgs10_value - t10yie_value, 4)

            # Calculate changes for real yield
            # We need the underlying changes from both series
            dgs10_change_1w = dgs10_data.get("change_1w")
            t10yie_change_1w = t10yie_data.get("change_1w")
            dgs10_change_4w = dgs10_data.get("change_4w")
            t10yie_change_4w = t10yie_data.get("change_4w")

            # Real yield change is the difference in changes (since it's a subtraction)
            change_1w = None
            change_4w = None

            if dgs10_change_1w is not None and t10yie_change_1w is not None:
                change_1w = round(dgs10_change_1w - t10yie_change_1w, 4)

            if dgs10_change_4w is not None and t10yie_change_4w is not None:
                change_4w = round(dgs10_change_4w - t10yie_change_4w, 4)

            metrics["real_yield_10y"] = {
                "value": real_yield,
                "unit": "pct",
                "change_1w": change_1w,
                "change_4w": change_4w,
                "available": True,
            }

            if dgs10_data.get("is_stale") or t10yie_data.get("is_stale"):
                stale_series.append("real_yield_10y")
            if dgs10_data.get("date"):
                latest_date = self._update_latest_date(latest_date, dgs10_data["date"])
        else:
            metrics["real_yield_10y"] = self._missing_metric("pct")
            missing_series.append("real_yield_10y")

        # Build quality metadata
        total_metrics = 5
        available_count = total_metrics - len(missing_series)
        completeness = available_count / total_metrics

        is_stale = len(stale_series) > 0
        stale_reason = None
        if is_stale:
            stale_reason = f"Stale series: {', '.join(stale_series)}"

        # Confidence score calculation
        # Start at 100, reduce for missing data and staleness
        confidence = 100.0
        confidence -= len(missing_series) * 15  # -15 per missing metric
        confidence -= len(stale_series) * 10    # -10 per stale metric

        # Cap confidence at 40 if stale (per spec)
        if is_stale and confidence > 40:
            confidence = 40.0

        confidence = max(0.0, min(100.0, confidence))

        quality = DataQuality(
            source="fred",
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

    async def get_history(
        self,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> Dict[str, Any]:
        """
        Get historical liquidity metrics.

        Args:
            start: ISO-8601 datetime string
            end: ISO-8601 datetime string
            interval: "1d" (daily) - note: some FRED series are weekly

        Returns:
            {
                "quality": DataQuality dict,
                "series": {
                    "fed_balance_sheet": [{"t": ..., "v": ...}, ...],
                    "rrp": [...],
                    "tga": [...],
                    "fci": [...],
                    "real_yield_10y": [...]
                }
            }
        """
        # Parse dates
        try:
            start_date = datetime.fromisoformat(start.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            end_date = datetime.fromisoformat(end.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except ValueError:
            # Assume already in YYYY-MM-DD format
            start_date = start[:10]
            end_date = end[:10]

        series = {}
        errors = []

        # Fetch each liquidity-relevant series
        for metric_name, series_id in LIQUIDITY_FRED_SERIES.items():
            try:
                result = await self._fred.get_series(
                    series_id,
                    start_date=start_date,
                    end_date=end_date,
                    limit=500,
                )

                # Convert to SeriesPoint format
                points = []
                for obs in result["observations"]:
                    try:
                        t = datetime.strptime(obs["date"], "%Y-%m-%d")
                        v = obs["value"]

                        # Apply unit conversions
                        if series_id == "WALCL":
                            v = v * 1_000_000  # millions to USD
                        elif series_id == "RRPONTSYD":
                            v = v * 1_000_000_000  # billions to USD
                        elif series_id == "WTREGEN":
                            v = v * 1_000_000  # millions to USD

                        points.append({"t": t.isoformat() + "Z", "v": v})
                    except (ValueError, TypeError):
                        continue

                # Reverse to chronological order
                points.reverse()
                series[metric_name] = points

            except ProviderError as e:
                logger.error(f"LiquidityProvider: Error fetching {series_id}: {e}")
                errors.append(metric_name)
                series[metric_name] = []

        # Compute real yield series
        dgs10_series = {p["t"]: p["v"] for p in series.get("dgs10", [])}
        t10yie_series = {p["t"]: p["v"] for p in series.get("t10yie", [])}

        real_yield_points = []
        for t in sorted(set(dgs10_series.keys()) & set(t10yie_series.keys())):
            real_yield = dgs10_series[t] - t10yie_series[t]
            real_yield_points.append({"t": t, "v": round(real_yield, 4)})

        series["real_yield_10y"] = real_yield_points

        # Remove the raw DGS10 and T10YIE from output (keep only derived real_yield)
        series.pop("dgs10", None)
        series.pop("t10yie", None)

        # Build quality
        expected_metrics = 5
        available = expected_metrics - len(errors)
        completeness = available / expected_metrics

        quality = DataQuality(
            source="fred",
            as_of=datetime.utcnow(),
            is_stale=False,
            completeness=completeness,
            confidence_score=completeness * 100,
        )

        return {
            "quality": quality.to_dict(),
            "series": series,
        }

    def _missing_metric(self, unit: str) -> Dict[str, Any]:
        """Create a missing metric placeholder."""
        return {
            "value": None,
            "unit": unit,
            "change_1w": None,
            "change_4w": None,
            "available": False,
        }

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

    def _build_error_response(self, error_msg: str) -> Dict[str, Any]:
        """Build error response when provider fails."""
        quality = DataQuality(
            source="fred",
            as_of=datetime.utcnow(),
            is_stale=True,
            stale_reason=f"Provider error: {error_msg}",
            completeness=0.0,
            confidence_score=0.0,
        )

        return {
            "quality": quality.to_dict(),
            "metrics": {
                "fed_balance_sheet": self._missing_metric("usd"),
                "rrp": self._missing_metric("usd"),
                "tga": self._missing_metric("usd"),
                "fci": self._missing_metric("index"),
                "real_yield_10y": self._missing_metric("pct"),
            },
        }


# Singleton instance
_liquidity_provider: Optional[LiquidityDataProviderImpl] = None


def get_liquidity_provider() -> LiquidityDataProviderImpl:
    """Get singleton liquidity provider instance."""
    global _liquidity_provider
    if _liquidity_provider is None:
        _liquidity_provider = LiquidityDataProviderImpl()
    return _liquidity_provider
