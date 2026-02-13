"""
Catalyst Service - Computes catalyst signals and Trade Readiness Score.

Integrates:
- LiquidityDataProvider for liquidity metrics
- MacroSignalService for MRI
- (Future) Earnings, Options, Credit, Volatility providers

Every output includes:
- score (0-100)
- confidence_score (0-100)
- drivers (list, top 3)
- data_stale flag
- as_of timestamp

Performance: Market-wide calls (get_liquidity, calculate_trade_readiness) are
cached server-side with a short TTL since they depend on slow-moving aggregates
(FRED weekly/daily data, MRI macro regime). This prevents redundant computation
across rapid requests and multiple users.
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.services.command_center.catalyst_config import CatalystConfig, get_catalyst_config
from app.services.data_providers import get_liquidity_provider, LiquidityDataProviderImpl, Driver
from app.services.data_providers.credit_provider import CreditDataProviderImpl, get_credit_provider
from app.services.data_providers.volatility_provider import VolatilityDataProviderImpl, get_volatility_provider
from app.services.data_providers.event_density_provider import EventDensityDataProviderImpl, get_event_density_provider
from app.models.catalyst_snapshot import CatalystSnapshot


# =============================================================================
# SERVER-SIDE TTL CACHE
# =============================================================================

class TTLCache:
    """Simple in-memory TTL cache for market-wide computations.

    Thread-safe enough for single-process async usage (FastAPI with uvicorn).
    Data sources are slow-moving aggregates (FRED weekly, MRI macro regime),
    so a 60-120s TTL is safe and prevents redundant computation.
    """

    def __init__(self, default_ttl_seconds: int = 60):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = default_ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry and time.monotonic() < entry["expires_at"]:
            return entry["data"]
        # Expired or missing
        if entry:
            del self._store[key]
        return None

    def set(self, key: str, data: Any, ttl_seconds: Optional[int] = None):
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        self._store[key] = {
            "data": data,
            "expires_at": time.monotonic() + ttl,
        }

    def clear(self):
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


# Module-level cache shared across requests (singleton per process)
_market_cache = TTLCache(default_ttl_seconds=90)


class CatalystService:
    """
    Computes catalyst signals from data providers.

    Provides:
    - Liquidity Regime Score
    - Credit Stress Score
    - Volatility Structure Score
    - Event Density Score
    - Trade Readiness Score (all 5 components)
    - Catalyst summary for API

    All scores use risk-off polarity: 0 = calm/good, 100 = stressed/bad.
    Performance: Market-wide results are cached with 90s TTL.
    """

    def __init__(
        self,
        liquidity_provider: Optional[LiquidityDataProviderImpl] = None,
        credit_provider: Optional[CreditDataProviderImpl] = None,
        volatility_provider: Optional[VolatilityDataProviderImpl] = None,
        event_density_provider: Optional[EventDensityDataProviderImpl] = None,
        config: Optional[CatalystConfig] = None,
    ):
        self._liquidity_provider = liquidity_provider or get_liquidity_provider()
        self._credit_provider = credit_provider or get_credit_provider()
        self._volatility_provider = volatility_provider or get_volatility_provider()
        self._event_density_provider = event_density_provider or get_event_density_provider()
        self._config = config or get_catalyst_config()
        self._macro_signal_service = None  # Lazy load to avoid circular import
        self._last_snapshot: Optional[CatalystSnapshot] = None
        self._cache = _market_cache

    def _get_macro_signal_service(self):
        """Lazy load MacroSignalService to avoid circular imports."""
        if self._macro_signal_service is None:
            from app.services.command_center.macro_signal import get_macro_signal_service
            self._macro_signal_service = get_macro_signal_service()
        return self._macro_signal_service

    # =========================================================================
    # LIQUIDITY SCORE
    # =========================================================================

    def _compute_liquidity_score(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute Liquidity Regime Score (0-100).

        Higher score = more risk-off (contracting liquidity)
        Lower score = more risk-on (expanding liquidity)

        Args:
            metrics: Raw metrics from LiquidityDataProvider

        Returns:
            {
                "score": 45.0,
                "confidence": 85.0,
                "drivers": [...],
                "regime": "transition"
            }
        """
        config = self._config
        weights = config.LIQUIDITY_WEIGHTS
        directions = config.LIQUIDITY_DIRECTIONS
        baselines = config.LIQUIDITY_BASELINES
        stdevs = config.LIQUIDITY_STDEVS

        contributions = []
        total_weight = 0.0
        weighted_sum = 0.0
        missing_metrics = []

        for metric_name, weight in weights.items():
            metric_data = metrics.get(metric_name, {})
            value = metric_data.get("value")

            if value is None or not metric_data.get("available", True):
                missing_metrics.append(metric_name)
                continue

            # Calculate z-score
            baseline = baselines.get(metric_name, 0)
            stdev = stdevs.get(metric_name, 1)

            if stdev == 0:
                z_score = 0
            else:
                z_score = (value - baseline) / stdev

            # Convert z-score to signal (-1 to +1 range, roughly)
            # Clamp z-score to [-3, 3] for reasonable bounds
            z_score = max(-3, min(3, z_score))

            # Apply direction (True = higher is bullish, False = higher is bearish)
            # We want higher score = more risk-off, so:
            # - If higher value is bullish, signal is negative (reduces risk-off score)
            # - If higher value is bearish, signal is positive (increases risk-off score)
            if directions.get(metric_name, True):
                signal = -z_score  # Higher value = lower risk-off score
            else:
                signal = z_score   # Higher value = higher risk-off score

            # Convert signal to contribution (scale to 0-100 space)
            # signal of +3 should add ~50 points (max risk-off)
            # signal of -3 should subtract ~50 points (max risk-on)
            contribution = signal * (50 / 3) * weight

            weighted_sum += contribution
            total_weight += weight

            contributions.append({
                "name": metric_name,
                "value": value,
                "z_score": round(z_score, 2),
                "signal": round(signal, 2),
                "contribution": round(contribution, 2),
                "weight": weight,
                "direction": "bearish" if signal > 0 else "bullish" if signal < 0 else "neutral",
            })

        # Calculate final score (base of 50 + weighted contributions)
        if total_weight > 0:
            # Normalize contributions to account for missing metrics
            scale_factor = 1.0 / total_weight
            score = 50 + (weighted_sum * scale_factor)
        else:
            score = 50  # Neutral if no data

        # Clamp to 0-100
        score = max(0, min(100, score))

        # Calculate confidence
        available_metrics = len(weights) - len(missing_metrics)
        completeness = available_metrics / len(weights) if weights else 0

        # Base confidence from completeness
        confidence = completeness * 100

        # Reduce confidence if any metrics are stale
        # (This will be handled by the provider's quality metadata)

        # Sort contributions by absolute contribution for drivers
        contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)
        drivers = contributions[:3]  # Top 3 drivers

        # Determine regime
        if score < config.LIQUIDITY_RISK_ON_THRESHOLD:
            regime = "risk_on"
        elif score > config.LIQUIDITY_RISK_OFF_THRESHOLD:
            regime = "risk_off"
        else:
            regime = "transition"

        return {
            "score": round(score, 1),
            "confidence": round(confidence, 1),
            "drivers": drivers,
            "regime": regime,
            "missing_metrics": missing_metrics,
        }

    async def get_liquidity(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Get current liquidity score with full explainability.

        Performance: Cached with 90s TTL (FRED data is daily/weekly).

        Returns:
            {
                "score": 45.0,
                "confidence_score": 85.0,
                "regime": "transition",
                "regime_label": "Transition",
                "drivers": [...],
                "metrics": {...},
                "data_stale": false,
                "as_of": "2026-02-02T14:30:00Z"
            }
        """
        # Check server-side cache first
        cached = self._cache.get("liquidity")
        if cached is not None:
            return cached

        # Fetch raw metrics from provider
        provider_response = await self._liquidity_provider.get_current()

        quality = provider_response.get("quality", {})
        metrics = provider_response.get("metrics", {})

        # Compute score
        score_result = self._compute_liquidity_score(metrics)

        # Combine provider staleness with score confidence
        is_stale = quality.get("is_stale", False)
        provider_confidence = quality.get("confidence_score", 100)

        # Final confidence is minimum of score confidence and provider confidence
        final_confidence = min(score_result["confidence"], provider_confidence)

        # Apply stale cap
        if is_stale and final_confidence > self._config.STALE_CONFIDENCE_CAP:
            final_confidence = self._config.STALE_CONFIDENCE_CAP

        # Build regime label
        regime_labels = {
            "risk_on": "Expanding Liquidity",
            "transition": "Transition",
            "risk_off": "Contracting Liquidity",
        }

        result = {
            "score": score_result["score"],
            "confidence_score": round(final_confidence, 1),
            "regime": score_result["regime"],
            "regime_label": regime_labels.get(score_result["regime"], score_result["regime"]),
            "drivers": score_result["drivers"],
            "metrics": metrics,
            "data_stale": is_stale,
            "stale_reason": quality.get("stale_reason"),
            "as_of": quality.get("as_of"),
            "completeness": quality.get("completeness", 1.0),
        }

        # Cache for 90s (FRED data is daily/weekly, no need to recompute constantly)
        self._cache.set("liquidity", result, ttl_seconds=90)

        return result

    # =========================================================================
    # CREDIT STRESS SCORE
    # =========================================================================

    def _compute_credit_stress_score(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute Credit Stress Score (0-100).

        Higher score = more stressed (risk-off polarity).
        Uses z-score normalization against baselines.

        Args:
            metrics: Raw metrics from CreditDataProvider

        Returns:
            {"score": 45.0, "confidence": 85.0, "drivers": [...], "regime": "elevated"}
        """
        config = self._config
        weights = config.CREDIT_STRESS_WEIGHTS
        directions = config.CREDIT_STRESS_DIRECTIONS
        baselines = config.CREDIT_STRESS_BASELINES
        stdevs = config.CREDIT_STRESS_STDEVS

        contributions = []
        total_weight = 0.0
        weighted_sum = 0.0
        missing_metrics = []

        for metric_name, weight in weights.items():
            metric_data = metrics.get(metric_name, {})
            value = metric_data.get("value") if isinstance(metric_data, dict) else metric_data

            if value is None or (isinstance(metric_data, dict) and not metric_data.get("available", True)):
                missing_metrics.append(metric_name)
                continue

            baseline = baselines.get(metric_name, 0)
            stdev = stdevs.get(metric_name, 1)

            if stdev == 0:
                z_score = 0
            else:
                z_score = (value - baseline) / stdev

            z_score = max(-3, min(3, z_score))

            if directions.get(metric_name, True):
                signal = -z_score
            else:
                signal = z_score

            contribution = signal * (50 / 3) * weight

            weighted_sum += contribution
            total_weight += weight

            contributions.append({
                "name": metric_name,
                "value": value,
                "z_score": round(z_score, 2),
                "signal": round(signal, 2),
                "contribution": round(contribution, 2),
                "weight": weight,
                "direction": "bearish" if signal > 0 else "bullish" if signal < 0 else "neutral",
            })

        if total_weight > 0:
            scale_factor = 1.0 / total_weight
            score = 50 + (weighted_sum * scale_factor)
        else:
            score = 50

        score = max(0, min(100, score))

        available_metrics = len(weights) - len(missing_metrics)
        completeness = available_metrics / len(weights) if weights else 0
        confidence = completeness * 100

        contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)
        drivers = contributions[:3]

        if score < config.CREDIT_LOW_STRESS_THRESHOLD:
            regime = "low_stress"
        elif score > config.CREDIT_HIGH_STRESS_THRESHOLD:
            regime = "high_stress"
        else:
            regime = "elevated"

        return {
            "score": round(score, 1),
            "confidence": round(confidence, 1),
            "drivers": drivers,
            "regime": regime,
            "missing_metrics": missing_metrics,
        }

    async def get_credit_stress(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Get current credit stress score with full explainability.

        Cached with 90s TTL.
        """
        cached = self._cache.get("credit_stress")
        if cached is not None:
            return cached

        provider_response = await self._credit_provider.get_current()

        quality = provider_response.get("quality", {})
        metrics = provider_response.get("metrics", {})

        score_result = self._compute_credit_stress_score(metrics)

        is_stale = quality.get("is_stale", False)
        provider_confidence = quality.get("confidence_score", 100)
        final_confidence = min(score_result["confidence"], provider_confidence)

        if is_stale and final_confidence > self._config.STALE_CONFIDENCE_CAP:
            final_confidence = self._config.STALE_CONFIDENCE_CAP

        regime_labels = {
            "low_stress": "Low Credit Stress",
            "elevated": "Elevated",
            "high_stress": "High Credit Stress",
        }

        result = {
            "score": score_result["score"],
            "confidence_score": round(final_confidence, 1),
            "regime": score_result["regime"],
            "regime_label": regime_labels.get(score_result["regime"], score_result["regime"]),
            "drivers": score_result["drivers"],
            "metrics": metrics,
            "data_stale": is_stale,
            "stale_reason": quality.get("stale_reason"),
            "as_of": quality.get("as_of"),
            "completeness": quality.get("completeness", 1.0),
        }

        self._cache.set("credit_stress", result, ttl_seconds=90)
        return result

    # =========================================================================
    # VOLATILITY STRUCTURE SCORE
    # =========================================================================

    def _compute_vol_structure_score(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute Volatility Structure Score (0-100).

        Higher score = more stressed (risk-off polarity).
        Uses z-score normalization against baselines.
        term_slope direction=True (contango=bullish → reduces risk-off score).

        Args:
            metrics: Raw metrics from VolatilityDataProvider

        Returns:
            {"score": 45.0, "confidence": 85.0, "drivers": [...], "regime": "calm"}
        """
        config = self._config
        weights = config.VOL_STRUCTURE_WEIGHTS
        directions = config.VOL_STRUCTURE_DIRECTIONS
        baselines = config.VOL_STRUCTURE_BASELINES
        stdevs = config.VOL_STRUCTURE_STDEVS

        contributions = []
        total_weight = 0.0
        weighted_sum = 0.0
        missing_metrics = []

        for metric_name, weight in weights.items():
            metric_data = metrics.get(metric_name, {})
            value = metric_data.get("value") if isinstance(metric_data, dict) else metric_data

            if value is None or (isinstance(metric_data, dict) and not metric_data.get("available", True)):
                missing_metrics.append(metric_name)
                continue

            baseline = baselines.get(metric_name, 0)
            stdev = stdevs.get(metric_name, 1)

            if stdev == 0:
                z_score = 0
            else:
                z_score = (value - baseline) / stdev

            z_score = max(-3, min(3, z_score))

            if directions.get(metric_name, True):
                signal = -z_score
            else:
                signal = z_score

            contribution = signal * (50 / 3) * weight

            weighted_sum += contribution
            total_weight += weight

            contributions.append({
                "name": metric_name,
                "value": value,
                "z_score": round(z_score, 2),
                "signal": round(signal, 2),
                "contribution": round(contribution, 2),
                "weight": weight,
                "direction": "bearish" if signal > 0 else "bullish" if signal < 0 else "neutral",
            })

        if total_weight > 0:
            scale_factor = 1.0 / total_weight
            score = 50 + (weighted_sum * scale_factor)
        else:
            score = 50

        score = max(0, min(100, score))

        available_metrics = len(weights) - len(missing_metrics)
        completeness = available_metrics / len(weights) if weights else 0
        confidence = completeness * 100

        contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)
        drivers = contributions[:3]

        if score < config.VOL_CALM_THRESHOLD:
            regime = "calm"
        elif score > config.VOL_STRESSED_THRESHOLD:
            regime = "stressed"
        else:
            regime = "elevated"

        return {
            "score": round(score, 1),
            "confidence": round(confidence, 1),
            "drivers": drivers,
            "regime": regime,
            "missing_metrics": missing_metrics,
        }

    async def get_vol_structure(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Get current volatility structure score with full explainability.

        Cached with 90s TTL.
        """
        cached = self._cache.get("vol_structure")
        if cached is not None:
            return cached

        provider_response = await self._volatility_provider.get_current()

        quality = provider_response.get("quality", {})
        metrics = provider_response.get("metrics", {})

        score_result = self._compute_vol_structure_score(metrics)

        is_stale = quality.get("is_stale", False)
        provider_confidence = quality.get("confidence_score", 100)
        final_confidence = min(score_result["confidence"], provider_confidence)

        if is_stale and final_confidence > self._config.STALE_CONFIDENCE_CAP:
            final_confidence = self._config.STALE_CONFIDENCE_CAP

        regime_labels = {
            "calm": "Low Volatility",
            "elevated": "Elevated",
            "stressed": "Stressed Volatility",
        }

        result = {
            "score": score_result["score"],
            "confidence_score": round(final_confidence, 1),
            "regime": score_result["regime"],
            "regime_label": regime_labels.get(score_result["regime"], score_result["regime"]),
            "drivers": score_result["drivers"],
            "metrics": metrics,
            "data_stale": is_stale,
            "stale_reason": quality.get("stale_reason"),
            "as_of": quality.get("as_of"),
            "completeness": quality.get("completeness", 1.0),
        }

        self._cache.set("vol_structure", result, ttl_seconds=90)
        return result

    # =========================================================================
    # EVENT DENSITY SCORE
    # =========================================================================

    def _compute_event_density_score(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute Event Density Score (0-100).

        Higher score = heavier event week (risk-off polarity).
        Uses max-points normalization (NOT z-score).

        Formula: score = clamp(0, 100, 100 * total_points / EVENT_DENSITY_MAX_POINTS)

        Args:
            metrics: Raw metrics from EventDensityDataProvider

        Returns:
            {"score": 45.0, "regime": "moderate", "high_impact_count": 2}
        """
        config = self._config
        total_points = metrics.get("total_points", 0)
        high_impact_count = metrics.get("high_impact_count", 0)

        # Max-points normalization
        max_points = config.EVENT_DENSITY_MAX_POINTS
        if max_points > 0:
            score = 100.0 * total_points / max_points
        else:
            score = 0

        score = max(0, min(100, score))

        # Determine regime
        if score < config.EVENT_LIGHT_THRESHOLD:
            regime = "light"
        elif score > config.EVENT_HEAVY_THRESHOLD:
            regime = "heavy"
        else:
            regime = "moderate"

        return {
            "score": round(score, 1),
            "regime": regime,
            "total_points": total_points,
            "high_impact_count": high_impact_count,
        }

    async def get_event_density(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Get current event density score with event list.

        Cached with 90s TTL.
        """
        cached = self._cache.get("event_density")
        if cached is not None:
            return cached

        provider_response = await self._event_density_provider.get_current()

        quality = provider_response.get("quality", {})
        metrics = provider_response.get("metrics", {})

        score_result = self._compute_event_density_score(metrics)

        is_stale = quality.get("is_stale", False)
        provider_confidence = quality.get("confidence_score", 100)
        confidence = provider_confidence

        if is_stale and confidence > self._config.STALE_CONFIDENCE_CAP:
            confidence = self._config.STALE_CONFIDENCE_CAP

        regime_labels = {
            "light": "Light Week",
            "moderate": "Moderate",
            "heavy": "Heavy Week",
        }

        result = {
            "score": score_result["score"],
            "confidence_score": round(confidence, 1),
            "regime": score_result["regime"],
            "regime_label": regime_labels.get(score_result["regime"], score_result["regime"]),
            "total_points": score_result["total_points"],
            "high_impact_count": score_result["high_impact_count"],
            "economic_event_count": metrics.get("economic_event_count", 0),
            "earnings_count": metrics.get("earnings_count", 0),
            "events": metrics.get("events", []),
            "data_stale": is_stale,
            "as_of": quality.get("as_of"),
            "completeness": quality.get("completeness", 1.0),
        }

        self._cache.set("event_density", result, ttl_seconds=90)
        return result

    # =========================================================================
    # TRADE READINESS
    # =========================================================================

    async def calculate_trade_readiness(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Calculate Trade Readiness Score.

        Combines all components with risk-off polarity (0=calm, 100=stressed):
        - MRI (40%)
        - Liquidity (20%)
        - Credit Stress (15%)
        - Vol Structure (15%)
        - Event Density (10%)

        No inversion — all scores feed directly into weighted sum.
        """
        # Check cache first (90s TTL - slow-moving aggregates)
        cached = self._cache.get("trade_readiness")
        if cached is not None:
            return cached

        config = self._config
        weights = config.READINESS_WEIGHTS
        defaults = config.READINESS_DEFAULTS

        components = {}
        drivers = []
        confidences = {}
        stale_components = []

        # Get MRI from MacroSignalService
        try:
            macro_service = self._get_macro_signal_service()
            mri_result = await macro_service.calculate_mri(db)
            mri_score = mri_result.get("mri_score", defaults["mri"])
            mri_confidence = mri_result.get("confidence_score", 0)

            components["mri"] = {
                "score": mri_score,
                "regime": mri_result.get("regime"),
                "available": True,
            }
            confidences["mri"] = mri_confidence

            if mri_result.get("data_stale"):
                stale_components.append("mri")

            # Add MRI as a driver (delta-from-neutral)
            mri_direction = "risk_off" if mri_score > 51 else ("risk_on" if mri_score < 49 else "neutral")
            drivers.append({
                "name": "MRI",
                "value": mri_score,
                "contribution": (mri_score - 50) * weights["mri"],
                "direction": mri_direction,
                "regime": mri_result.get("regime", "transition"),
            })

        except Exception as e:
            logger.error(f"CatalystService: Error getting MRI: {e}")
            mri_score = defaults["mri"]
            components["mri"] = {"score": mri_score, "available": False, "error": str(e)}
            confidences["mri"] = 0

        # Get Liquidity
        try:
            liquidity_result = await self.get_liquidity(db)
            liquidity_score = liquidity_result.get("score", defaults["liquidity"])
            liquidity_confidence = liquidity_result.get("confidence_score", 0)

            components["liquidity"] = {
                "score": liquidity_score,
                "regime": liquidity_result.get("regime"),
                "available": True,
            }
            confidences["liquidity"] = liquidity_confidence

            if liquidity_result.get("data_stale"):
                stale_components.append("liquidity")

            # Add liquidity as a driver (delta-from-neutral)
            liq_direction = "risk_off" if liquidity_score > 51 else ("risk_on" if liquidity_score < 49 else "neutral")
            drivers.append({
                "name": "Liquidity",
                "value": liquidity_score,
                "contribution": (liquidity_score - 50) * weights["liquidity"],
                "direction": liq_direction,
                "regime": liquidity_result.get("regime", "transition"),
            })

        except Exception as e:
            logger.error(f"CatalystService: Error getting liquidity: {e}")
            liquidity_score = defaults["liquidity"]
            components["liquidity"] = {"score": liquidity_score, "available": False, "error": str(e)}
            confidences["liquidity"] = 0

        # Tier 2 components — real implementations
        unavailable_components = []
        for component_name, getter in [
            ("credit_stress", self.get_credit_stress),
            ("vol_structure", self.get_vol_structure),
            ("event_density", self.get_event_density),
        ]:
            try:
                comp_result = await getter(db)
                comp_score = comp_result.get("score", defaults[component_name])
                components[component_name] = {
                    "score": comp_score,
                    "regime": comp_result.get("regime"),
                    "available": True,
                }
                confidences[component_name] = comp_result.get("confidence_score", 0)
                if comp_result.get("data_stale"):
                    stale_components.append(component_name)
                # Delta-from-neutral driver contribution
                comp_direction = "risk_off" if comp_score > 51 else ("risk_on" if comp_score < 49 else "neutral")
                drivers.append({
                    "name": component_name,
                    "value": comp_score,
                    "contribution": (comp_score - 50) * weights[component_name],
                    "direction": comp_direction,
                    "regime": comp_result.get("regime", "transition"),
                })
            except Exception as e:
                logger.error(f"CatalystService: Error getting {component_name}: {e}")
                components[component_name] = {
                    "score": defaults[component_name],
                    "available": False,
                    "error": str(e),
                }
                confidences[component_name] = 0
                unavailable_components.append(component_name)

        # Calculate weighted score — all scores use risk-off polarity, no inversion
        score = 0.0
        for component_name, weight in weights.items():
            component_score = components.get(component_name, {}).get("score", defaults[component_name])
            score += component_score * weight

        # Clamp score
        score = max(0, min(100, score))

        # Determine label
        if score <= config.READINESS_GREEN_THRESHOLD:
            label = "green"
        elif score <= config.READINESS_YELLOW_THRESHOLD:
            label = "yellow"
        else:
            label = "red"

        # Overall confidence is minimum of available components
        available_confidences = [
            v for k, v in confidences.items()
            if components.get(k, {}).get("available", False)
        ]
        overall_confidence = min(available_confidences) if available_confidences else 0

        # Sort drivers by absolute contribution
        drivers.sort(key=lambda x: abs(x["contribution"]), reverse=True)

        result = {
            "trade_readiness_score": round(score, 1),
            "readiness_label": label,
            "readiness_label_display": self._get_label_display(label),
            "readiness_is_partial": False,
            "components": components,
            "drivers": drivers[:3],  # Top 3
            "confidence_by_component": confidences,
            "overall_confidence": round(overall_confidence, 1),
            "data_stale": len(stale_components) > 0,
            "stale_components": stale_components if stale_components else None,
            "unavailable_components": unavailable_components if unavailable_components else None,
            "calculated_at": datetime.utcnow().isoformat() + "Z",
        }

        # Cache the result (90s TTL)
        self._cache.set("trade_readiness", result, ttl_seconds=90)

        return result

    def _get_label_display(self, label: str) -> str:
        """Get human-readable label."""
        displays = {
            "green": "Risk-On",
            "yellow": "Transition",
            "red": "Risk-Off",
        }
        return displays.get(label, label)

    # =========================================================================
    # CATALYST SUMMARY
    # =========================================================================

    async def get_catalyst_summary(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Get full catalyst summary for API.

        This is the main endpoint for the Macro Intelligence page.
        """
        readiness = await self.calculate_trade_readiness(db)

        return {
            "trade_readiness": {
                "score": readiness["trade_readiness_score"],
                "label": readiness["readiness_label"],
                "label_display": readiness["readiness_label_display"],
                "is_partial": readiness["readiness_is_partial"],
            },
            "components": readiness["components"],
            "drivers": readiness["drivers"],
            "confidence_by_component": readiness["confidence_by_component"],
            "overall_confidence": readiness["overall_confidence"],
            "data_stale": readiness["data_stale"],
            "stale_components": readiness.get("stale_components"),
            "unavailable_components": readiness.get("unavailable_components"),
            "calculated_at": readiness["calculated_at"],
        }

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    async def save_snapshot(self, db: Session) -> Optional[CatalystSnapshot]:
        """
        Calculate and save a catalyst snapshot.

        Implements smart cadence: skips storage if data unchanged.
        """
        # Get current data
        liquidity_result = await self.get_liquidity(db)
        readiness_result = await self.calculate_trade_readiness(db)

        liquidity_score = liquidity_result.get("score")
        readiness_score = readiness_result.get("trade_readiness_score")

        # Smart cadence check
        if self._config.SMART_CADENCE_ENABLED and self._last_snapshot:
            liq_change = abs((liquidity_score or 0) - (self._last_snapshot.liquidity_score or 0))
            read_change = abs((readiness_score or 0) - (self._last_snapshot.trade_readiness_score or 0))

            if liq_change < self._config.SMART_CADENCE_CHANGE_THRESHOLD and \
               read_change < self._config.SMART_CADENCE_CHANGE_THRESHOLD:
                logger.debug("CatalystService: Skipping snapshot (no significant change)")
                return None

        # Calculate 6h changes
        liquidity_change_6h = None
        readiness_change_6h = None

        try:
            six_hours_ago = datetime.utcnow() - timedelta(hours=6)
            prev_snapshot = db.query(CatalystSnapshot).filter(
                CatalystSnapshot.timestamp <= six_hours_ago
            ).order_by(desc(CatalystSnapshot.timestamp)).first()

            if prev_snapshot:
                if prev_snapshot.liquidity_score is not None and liquidity_score is not None:
                    liquidity_change_6h = round(liquidity_score - prev_snapshot.liquidity_score, 1)
                if prev_snapshot.trade_readiness_score is not None and readiness_score is not None:
                    readiness_change_6h = round(readiness_score - prev_snapshot.trade_readiness_score, 1)
        except Exception as e:
            logger.warning(f"CatalystService: Error calculating 6h changes: {e}")

        # Extract Tier 2 component scores
        credit_score = readiness_result.get("components", {}).get("credit_stress", {}).get("score")
        vol_score = readiness_result.get("components", {}).get("vol_structure", {}).get("score")
        event_score = readiness_result.get("components", {}).get("event_density", {}).get("score")

        # Create snapshot
        snapshot = CatalystSnapshot(
            timestamp=datetime.utcnow(),

            # Component scores
            liquidity_score=liquidity_score,
            options_positioning_score=None,  # Phase 3
            credit_stress_score=credit_score,
            vol_structure_score=vol_score,
            event_density_score=event_score,
            cross_asset_confirmation_score=None,  # Tier 3

            # Trade Readiness
            trade_readiness_score=readiness_score,
            readiness_label=readiness_result.get("readiness_label"),
            readiness_is_partial=False,

            # Explainability
            confidence_by_component=readiness_result.get("confidence_by_component"),
            drivers=readiness_result.get("drivers"),

            # Raw metrics
            liquidity_metrics=liquidity_result.get("metrics"),

            # Quality
            data_stale=readiness_result.get("data_stale", False),
            stale_components=readiness_result.get("stale_components"),
            last_api_success=datetime.utcnow(),
            completeness=liquidity_result.get("completeness", 1.0),
            overall_confidence=readiness_result.get("overall_confidence"),

            # Changes
            liquidity_change_6h=liquidity_change_6h,
            readiness_change_6h=readiness_change_6h,
        )

        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        self._last_snapshot = snapshot
        logger.info(
            f"CatalystService: Saved snapshot - "
            f"Liquidity={liquidity_score}, Readiness={readiness_score} ({snapshot.readiness_label})"
        )

        return snapshot

    async def get_history(
        self,
        db: Session,
        hours: int = 168,  # 7 days default
    ) -> List[Dict[str, Any]]:
        """Get catalyst history for charts."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        snapshots = db.query(CatalystSnapshot).filter(
            CatalystSnapshot.timestamp >= cutoff
        ).order_by(CatalystSnapshot.timestamp).all()

        return [s.to_dict() for s in snapshots]

    # =========================================================================
    # SECTOR MACRO WEIGHTS
    # =========================================================================

    def get_sector_macro_weights(self, sector: str) -> Dict[str, float]:
        """
        Get macro component weights for a given sector.

        Different sectors have different sensitivities to macro factors.
        Returns default weights if sector is unknown.

        Args:
            sector: Sector name (e.g., "Technology", "Financials")

        Returns:
            Dict of macro component weights summing to 1.0
        """
        sector_weights = self._config.SECTOR_MACRO_WEIGHTS

        # Normalize sector name
        sector_normalized = sector.strip().title() if sector else "Unknown"

        # Return sector-specific weights or default
        if sector_normalized in sector_weights:
            return sector_weights[sector_normalized]

        return sector_weights.get("Unknown", {
            "liquidity": 0.25,
            "fed_policy": 0.25,
            "earnings": 0.20,
            "options_positioning": 0.15,
            "event_risk": 0.15,
        })

    # =========================================================================
    # MACRO BIAS SCORE
    # =========================================================================

    def _compute_macro_bias_score(
        self,
        sector: str,
        liquidity_score: float,
        mri_score: float,
        earnings_risk_score: Optional[float] = None,
        options_positioning_score: Optional[float] = None,
        event_risk_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute macro bias score using sector-specific weights.

        Maps: 0-33 = Bearish, 34-66 = Neutral, 67-100 = Bullish

        NOTE: This is an INFORMATIONAL score, not a gate.
        Higher score = more bullish macro conditions for this ticker.

        Args:
            sector: Ticker's sector
            liquidity_score: Current liquidity score (0-100, higher = risk-off)
            mri_score: Current MRI (0-100, higher = risk-off)
            earnings_risk_score: Optional earnings risk (0-100, higher = more risk)
            options_positioning_score: Optional options fragility (0-100)
            event_risk_score: Optional event density (0-100)

        Returns:
            {
                "score": 52.0,
                "label": "neutral",
                "sector_weights": {...},
                "component_contributions": {...}
            }
        """
        weights = self.get_sector_macro_weights(sector)
        config = self._config

        # Invert risk-off scores to bullish space
        # Higher liquidity_score = risk-off = bearish = lower bias score
        # Higher MRI = risk-off = bearish = lower bias score
        liquidity_bullish = 100 - liquidity_score
        fed_policy_bullish = 100 - mri_score

        # Use defaults for unimplemented components (50 = neutral)
        earnings_bullish = 100 - (earnings_risk_score if earnings_risk_score is not None else 50)
        options_bullish = 100 - (options_positioning_score if options_positioning_score is not None else 50)
        event_bullish = 100 - (event_risk_score if event_risk_score is not None else 50)

        # Weighted sum
        contributions = {}
        score = 0.0

        component_map = {
            "liquidity": liquidity_bullish,
            "fed_policy": fed_policy_bullish,
            "earnings": earnings_bullish,
            "options_positioning": options_bullish,
            "event_risk": event_bullish,
        }

        for component, weight in weights.items():
            value = component_map.get(component, 50)
            contribution = value * weight
            score += contribution
            contributions[component] = {
                "value": round(value, 1),
                "weight": weight,
                "contribution": round(contribution, 1),
            }

        # Clamp score
        score = max(0, min(100, score))

        # Determine label
        if score <= config.MACRO_BIAS_BEARISH_THRESHOLD:
            label = "bearish"
        elif score >= config.MACRO_BIAS_BULLISH_THRESHOLD:
            label = "bullish"
        else:
            label = "neutral"

        return {
            "score": round(score, 1),
            "label": label,
            "sector": sector,
            "sector_weights": weights,
            "component_contributions": contributions,
        }

    # =========================================================================
    # TRADE COMPATIBILITY
    # =========================================================================

    def compute_trade_compatibility(
        self,
        readiness_score: float,
        earnings_risk_score: Optional[float] = None,
        earnings_days_out: Optional[int] = None,
        options_positioning_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute trade compatibility indicator.

        Values: Favorable, Mixed, Unfavorable

        IMPORTANT: This is an INFO flag, NOT a gate.
        Macro overlay informs the trade, it never replaces the trader.

        Args:
            readiness_score: Trade Readiness score (0-100)
            earnings_risk_score: Earnings risk (0-100, optional)
            earnings_days_out: Days until next earnings (optional)
            options_positioning_score: Options fragility (0-100, optional)

        Returns:
            {
                "compatibility": "mixed",
                "macro_headwind": false,
                "reasons": [...],
                "flags": {...}
            }
        """
        config = self._config
        reasons = []
        flags = {
            "readiness_favorable": False,
            "readiness_unfavorable": False,
            "earnings_imminent": False,
            "earnings_elevated": False,
            "options_fragile": False,
            "macro_headwind": False,
        }

        # Check readiness thresholds
        # Note: Lower readiness_score is better (risk-on)
        if readiness_score <= config.TRADE_COMPAT_FAVORABLE_READINESS_MIN:
            flags["readiness_favorable"] = True
            reasons.append("Macro conditions favorable")
        elif readiness_score >= config.TRADE_COMPAT_UNFAVORABLE_READINESS_MAX:
            flags["readiness_unfavorable"] = True
            flags["macro_headwind"] = True
            reasons.append(f"Trade Readiness elevated ({readiness_score:.0f})")

        # Check earnings timing
        if earnings_days_out is not None:
            if earnings_days_out <= config.TRADE_COMPAT_EARNINGS_IMMINENT_DAYS:
                flags["earnings_imminent"] = True
                reasons.append(f"Earnings in {earnings_days_out} day(s)")

        # Check earnings risk score
        if earnings_risk_score is not None:
            if earnings_risk_score > config.TRADE_COMPAT_FAVORABLE_EARNINGS_RISK_MAX:
                flags["earnings_elevated"] = True
                if not flags["earnings_imminent"]:
                    reasons.append("Elevated earnings risk")

        # Check options positioning
        if options_positioning_score is not None and options_positioning_score > 66:
            flags["options_fragile"] = True
            reasons.append("Options positioning fragile")

        # Determine compatibility
        # Unfavorable: readiness unfavorable OR earnings imminent
        if flags["readiness_unfavorable"] or flags["earnings_imminent"]:
            compatibility = "unfavorable"
        # Favorable: readiness favorable AND earnings not elevated
        elif flags["readiness_favorable"] and not flags["earnings_elevated"]:
            compatibility = "favorable"
        # Mixed: everything else
        else:
            compatibility = "mixed"

        return {
            "compatibility": compatibility,
            "macro_headwind": flags["macro_headwind"],
            "reasons": reasons if reasons else ["Macro conditions neutral"],
            "flags": flags,
        }

    # =========================================================================
    # TICKER MACRO OVERLAY (Main API Method)
    # =========================================================================

    async def get_ticker_macro_overlay(
        self,
        symbol: str,
        sector: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Get macro overlay for a specific ticker.

        This is the main API method for GET /ticker/{symbol}/macro-overlay.
        Returns contextual macro data to INFORM (not gate) trading decisions.

        IMPORTANT: This overlay provides context, not a gatekeeper.
        If macro is unclear, show uncertainty — do not hide the signal.

        Args:
            symbol: Ticker symbol
            sector: Optional sector (fetched from DB if not provided)
            db: Optional database session

        Returns:
            Full macro overlay response per spec
        """
        # Get current macro data
        try:
            readiness_result = await self.calculate_trade_readiness(db)
            liquidity_result = await self.get_liquidity(db)
        except Exception as e:
            logger.error(f"CatalystService: Error fetching macro data for {symbol}: {e}")
            # Gracefully degrade - return partial data
            return {
                "symbol": symbol,
                "macro_bias": "unknown",
                "macro_bias_score": None,
                "confidence_score": 0,
                "data_stale": True,
                "trade_compatibility": "mixed",
                "macro_headwind": False,
                "drivers": ["Macro data temporarily unavailable"],
                "earnings": None,
                "links": {"macro_intelligence": "/macro-intelligence"},
                "error": str(e),
            }

        # Get sector from ticker if not provided
        # For now, use "Unknown" if sector not provided (can be enhanced later)
        effective_sector = sector or "Unknown"

        readiness_score = readiness_result.get("trade_readiness_score", 50)
        liquidity_score = liquidity_result.get("score", 50)

        # Get MRI score from components
        mri_component = readiness_result.get("components", {}).get("mri", {})
        mri_score = mri_component.get("score", 50)

        # Compute macro bias using sector weights
        macro_bias_result = self._compute_macro_bias_score(
            sector=effective_sector,
            liquidity_score=liquidity_score,
            mri_score=mri_score,
            # earnings_risk_score=None,  # TODO: Add when implemented
            # options_positioning_score=None,  # TODO: Add when implemented
        )

        # Compute trade compatibility
        # Note: earnings_days_out and earnings_risk_score would come from
        # TickerCatalystSnapshot once Phase 2 is implemented
        compat_result = self.compute_trade_compatibility(
            readiness_score=readiness_score,
            earnings_risk_score=None,  # TODO: Add when Phase 2 implemented
            earnings_days_out=None,    # TODO: Add when Phase 2 implemented
            options_positioning_score=None,  # TODO: Add when Phase 3 implemented
        )

        # Build human-readable drivers (top 3)
        raw_drivers = readiness_result.get("drivers", [])
        human_drivers = self._format_drivers_human_readable(raw_drivers, liquidity_result)

        # Check overall staleness
        data_stale = readiness_result.get("data_stale", False) or liquidity_result.get("data_stale", False)

        # Overall confidence
        overall_confidence = readiness_result.get("overall_confidence", 0)

        return {
            "symbol": symbol,
            "sector": effective_sector,

            # Macro Bias
            "macro_bias": macro_bias_result["label"],
            "macro_bias_score": macro_bias_result["score"],

            # Confidence
            "confidence_score": overall_confidence,
            "data_stale": data_stale,

            # Trade Compatibility (INFO flag, NOT a gate)
            "trade_compatibility": compat_result["compatibility"],
            "macro_headwind": compat_result["macro_headwind"],
            "compatibility_flags": compat_result["flags"],
            "compatibility_reasons": compat_result["reasons"],

            # Drivers (human-readable, max 3)
            "drivers": human_drivers[:3],

            # Earnings (placeholder until Phase 2)
            "earnings": None,

            # Detailed breakdown (for expanded view)
            "details": {
                "trade_readiness_score": readiness_score,
                "readiness_label": readiness_result.get("readiness_label"),
                "liquidity_score": liquidity_score,
                "liquidity_regime": liquidity_result.get("regime"),
                "mri_score": mri_score,
                "mri_regime": mri_component.get("regime"),
                "sector_weights": macro_bias_result.get("sector_weights"),
            },

            # Navigation
            "links": {
                "macro_intelligence": "/macro-intelligence",
            },

            # Timestamp
            "calculated_at": datetime.utcnow().isoformat() + "Z",
        }

    def _format_drivers_human_readable(
        self,
        raw_drivers: List[Dict],
        liquidity_result: Dict[str, Any],
    ) -> List[str]:
        """
        Format drivers as human-readable strings for UI display.

        Rules:
        - Max 3 drivers
        - Human-readable, not numeric
        - Derived from existing drivers arrays

        Examples:
        - "Liquidity: Mixed (↓ RRP, ↑ TGA)"
        - "Fed Policy: Neutral"
        - "Event Risk: Earnings in 3 days"
        """
        drivers = []

        # Liquidity summary
        liquidity_regime = liquidity_result.get("regime", "transition")
        liquidity_drivers = liquidity_result.get("drivers", [])

        regime_labels = {
            "risk_on": "Expanding",
            "transition": "Mixed",
            "risk_off": "Contracting",
        }

        liquidity_label = regime_labels.get(liquidity_regime, "Mixed")

        # Add detail from top liquidity drivers
        details = []
        for d in liquidity_drivers[:2]:
            name = d.get("name", "")
            direction = d.get("direction", "")
            if direction == "bearish":
                details.append(f"↑ {name}")
            elif direction == "bullish":
                details.append(f"↓ {name}")

        if details:
            drivers.append(f"Liquidity: {liquidity_label} ({', '.join(details)})")
        else:
            drivers.append(f"Liquidity: {liquidity_label}")

        # MRI / Fed Policy
        for d in raw_drivers:
            if d.get("name") == "MRI":
                direction = d.get("direction", "")
                if direction == "risk_on":
                    drivers.append("Fed Policy: Accommodative")
                elif direction == "risk_off":
                    drivers.append("Fed Policy: Restrictive")
                else:
                    drivers.append("Fed Policy: Neutral")
                break
        else:
            drivers.append("Fed Policy: Neutral")

        # Credit stress driver
        for d in raw_drivers:
            if d.get("name") == "credit_stress":
                regime = d.get("regime", "elevated")
                if regime == "low_stress":
                    drivers.append("Credit: Calm")
                elif regime == "high_stress":
                    drivers.append("Credit: Stressed (↑ HY Spreads)")
                else:
                    drivers.append("Credit: Elevated")
                break

        # Vol structure driver
        for d in raw_drivers:
            if d.get("name") == "vol_structure":
                regime = d.get("regime", "elevated")
                if regime == "calm":
                    drivers.append("Volatility: Low")
                elif regime == "stressed":
                    drivers.append("Volatility: Elevated (↑ VIX)")
                else:
                    drivers.append("Volatility: Moderate")
                break

        # Event density driver
        for d in raw_drivers:
            if d.get("name") == "event_density":
                regime = d.get("regime", "moderate")
                if regime == "light":
                    drivers.append("Events: Light Week")
                elif regime == "heavy":
                    drivers.append("Events: Heavy Week")
                else:
                    drivers.append("Events: Moderate")
                break

        return drivers[:3]


# Singleton instance
_catalyst_service: Optional[CatalystService] = None


def get_catalyst_service() -> CatalystService:
    """Get singleton catalyst service instance."""
    global _catalyst_service
    if _catalyst_service is None:
        _catalyst_service = CatalystService()
    return _catalyst_service
