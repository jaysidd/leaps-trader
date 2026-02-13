"""
Concrete implementation of CreditDataProvider.

Combines FRED data to provide credit spread metrics:
- HY OAS (BAMLH0A0HYM2): ICE BofA US High Yield OAS
- IG OAS (BAMLC0A0CM): ICE BofA US Corporate IG OAS
- HY OAS 4-week change (derived from FRED change data)
"""

from datetime import datetime
from typing import Dict, Any, Optional
from loguru import logger

from .interfaces import DataQuality, ProviderError
from .fred import FREDService, get_fred_service


# FRED series IDs for credit spreads
CREDIT_SERIES = {
    "hy_oas": "BAMLH0A0HYM2",
    "ig_oas": "BAMLC0A0CM",
}


class CreditDataProviderImpl:
    """
    CreditDataProvider implementation using FRED data.

    HY OAS 4-week change is derived from the FRED change computation.
    """

    def __init__(self, fred_service: Optional[FREDService] = None):
        self._fred = fred_service or get_fred_service()

    async def get_current(self) -> Dict[str, Any]:
        """
        Get current credit spread metrics.

        Returns:
            {
                "quality": DataQuality dict,
                "metrics": {
                    "hy_oas": MetricValue dict,
                    "ig_oas": MetricValue dict,
                    "hy_oas_change_4w": MetricValue dict
                }
            }
        """
        series_to_fetch = list(CREDIT_SERIES.values())

        try:
            raw_data = await self._fred.get_multiple_series(
                series_to_fetch,
                lookback_weeks=5,
            )
        except ProviderError as e:
            logger.error(f"CreditProvider: Failed to fetch FRED data: {e}")
            return self._build_error_response(str(e))

        metrics = {}
        stale_series = []
        missing_series = []
        latest_date = None

        # HY OAS (value is in percentage points, e.g., 3.45 = 345 bps)
        hy_data = raw_data.get("BAMLH0A0HYM2", {})
        hy_change_4w = None
        if hy_data.get("value") is not None:
            metrics["hy_oas"] = {
                "value": hy_data["value"],
                "unit": "pct",
                "change_1w": hy_data.get("change_1w"),
                "change_4w": hy_data.get("change_4w"),
                "available": True,
            }
            hy_change_4w = hy_data.get("change_4w")
            if hy_data.get("is_stale"):
                stale_series.append("hy_oas")
            if hy_data.get("date"):
                latest_date = self._update_latest_date(latest_date, hy_data["date"])
        else:
            metrics["hy_oas"] = self._missing_metric("pct")
            missing_series.append("hy_oas")

        # IG OAS
        ig_data = raw_data.get("BAMLC0A0CM", {})
        if ig_data.get("value") is not None:
            metrics["ig_oas"] = {
                "value": ig_data["value"],
                "unit": "pct",
                "change_1w": ig_data.get("change_1w"),
                "change_4w": ig_data.get("change_4w"),
                "available": True,
            }
            if ig_data.get("is_stale"):
                stale_series.append("ig_oas")
            if ig_data.get("date"):
                latest_date = self._update_latest_date(latest_date, ig_data["date"])
        else:
            metrics["ig_oas"] = self._missing_metric("pct")
            missing_series.append("ig_oas")

        # HY OAS 4-week change (derived)
        if hy_change_4w is not None:
            metrics["hy_oas_change_4w"] = {
                "value": hy_change_4w,
                "unit": "pct_abs",
                "available": True,
            }
        else:
            metrics["hy_oas_change_4w"] = {
                "value": None,
                "unit": "pct_abs",
                "available": False,
            }
            missing_series.append("hy_oas_change_4w")

        # Build quality metadata
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
                "hy_oas": self._missing_metric("pct"),
                "ig_oas": self._missing_metric("pct"),
                "hy_oas_change_4w": {"value": None, "unit": "pct_abs", "available": False},
            },
        }


# Singleton instance
_credit_provider: Optional[CreditDataProviderImpl] = None


def get_credit_provider() -> CreditDataProviderImpl:
    """Get singleton credit provider instance."""
    global _credit_provider
    if _credit_provider is None:
        _credit_provider = CreditDataProviderImpl()
    return _credit_provider
