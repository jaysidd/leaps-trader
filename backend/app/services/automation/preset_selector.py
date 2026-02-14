"""
Market-Adaptive Preset Selector — The conductor's brain.

Reads cached market intelligence (MRI, regime, Fear & Greed, Trade Readiness)
and selects appropriate screening presets for current market conditions.

Uses a WEIGHTED SCORING system — all signals contribute proportionally
instead of any single signal vetoing the classification.

Reads cached data when available. Stale/missing cache triggers fresh Alpaca fetches.
"""
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Version — bump when scoring logic, weights, or thresholds change
# ---------------------------------------------------------------------------
SELECTOR_VERSION = "1.1.0"


# ---------------------------------------------------------------------------
# Market condition → preset mapping
# ---------------------------------------------------------------------------

MARKET_CONDITIONS = {
    "aggressive_bull": {
        "presets": ["aggressive", "growth_leaps", "swing_momentum"],
        "max_positions": 2,
        "description": "Strong bullish — aggressive growth plays",
    },
    "moderate_bull": {
        "presets": ["moderate", "blue_chip_leaps", "swing_breakout"],
        "max_positions": 2,
        "description": "Moderate bullish — balanced growth + quality",
    },
    "neutral": {
        "presets": ["moderate", "low_iv_entry", "deep_value"],
        "max_positions": 1,
        "description": "Mixed signals — focus on value and low IV",
    },
    "cautious": {
        "presets": ["conservative", "blue_chip_leaps"],
        "max_positions": 1,
        "description": "Elevated caution — defensive plays only",
    },
    "defensive": {
        "presets": ["conservative"],
        "max_positions": 1,
        "description": "Risk-off — minimal exposure",
    },
    "skip": {
        "presets": [],
        "max_positions": 0,
        "description": "Extreme fear — skip scanning entirely",
    },
}

# ---------------------------------------------------------------------------
# Signal weights for composite scoring
# ---------------------------------------------------------------------------
# Each signal contributes to an overall market score on a -100 to +100 scale.
# Positive = bullish, Negative = bearish.  Weights sum to 1.0.

SIGNAL_WEIGHTS = {
    "regime":      0.35,  # Market regime (VIX/SPY/SMA) — most reliable directional signal
    "mri":         0.30,  # Macro Risk Index (Polymarket) — macro headwinds/tailwinds
    "fear_greed":  0.20,  # CNN Fear & Greed — sentiment gauge
    "readiness":   0.15,  # Trade Readiness — catalyst/liquidity composite
}

# Score → condition thresholds (on the -100 to +100 scale)
CONDITION_THRESHOLDS = {
    "aggressive_bull": 50,   # Score >= 50 → aggressive
    "moderate_bull":   20,   # Score >= 20 → moderate bull
    "neutral":          0,   # Score >=  0 → neutral
    "cautious":       -20,   # Score >= -20 → cautious
    "defensive":      -50,   # Score >= -50 → defensive
    # Below -50 with extreme signals → skip
}


class PresetSelector:
    """Select screening presets based on current market conditions."""

    async def select_presets(self, db: Session) -> Dict[str, Any]:
        """
        Gather market intelligence and map to appropriate presets.

        Returns dict with:
            condition: str — market condition label
            presets: list — preset IDs to scan
            max_positions: int — suggested position limit
            reasoning: str — human-readable explanation
            market_snapshot: dict — raw intelligence values
        """
        snapshot = await self._gather_market_snapshot(db)
        score, signal_scores = self._compute_composite_score(snapshot)
        condition = self._classify_condition(score, snapshot)
        mapping = MARKET_CONDITIONS[condition]

        reasoning = self._build_reasoning(condition, score, signal_scores, snapshot)

        # Lazy import to avoid circular deps at module load time
        from app.data.presets_catalog import get_catalog_hash

        result = {
            "condition": condition,
            "presets": mapping["presets"],
            "max_positions": mapping["max_positions"],
            "reasoning": reasoning,
            "market_snapshot": {**snapshot, "composite_score": round(score, 1)},
            "selector_version": SELECTOR_VERSION,
            "catalog_hash": get_catalog_hash(),
        }

        logger.info(
            f"[PresetSelector] {condition} (score={score:.1f}) → {mapping['presets']} "
            f"(MRI={snapshot.get('mri', '?')}, regime={snapshot.get('regime', '?')}, "
            f"F&G={snapshot.get('fear_greed', '?')}, readiness={snapshot.get('readiness_label', '?')})"
        )

        return result

    async def _gather_market_snapshot(self, db: Session) -> Dict[str, Any]:
        """
        Read cached market intelligence from existing services.
        All data comes from caches — no external API calls.
        """
        snapshot: Dict[str, Any] = {
            "mri": None,
            "mri_regime": None,
            "regime": None,
            "risk_mode": None,
            "regime_confidence": None,
            "fear_greed": None,
            "readiness": None,
            "readiness_label": None,
            "timestamp": datetime.now().isoformat(),
        }

        # 1. MRI (Macro Risk Index) — cached by calculate_mri_job every 15min
        try:
            from app.services.command_center import get_macro_signal_service
            mri_data = get_macro_signal_service().get_cached_mri()
            if mri_data:
                snapshot["mri"] = mri_data.get("mri_score")
                snapshot["mri_regime"] = mri_data.get("regime")
        except Exception as e:
            logger.warning(f"[PresetSelector] MRI unavailable: {e}")

        # 2. Market Regime — cached with 5min TTL
        try:
            from app.services.ai.market_regime import get_regime_detector
            detector = get_regime_detector()
            # Check if cached
            if detector._cache and detector._cache_time:
                from datetime import timedelta
                if datetime.now() - detector._cache_time < timedelta(minutes=5):
                    snapshot["regime"] = detector._cache.get("regime")
                    snapshot["risk_mode"] = detector._cache.get("risk_mode")
                    snapshot["regime_confidence"] = detector._cache.get("confidence")
                else:
                    # Cache stale, fetch fresh (this calls Alpaca for VIX/SPY)
                    import asyncio
                    market_data = await asyncio.to_thread(detector.get_market_data)
                    if not asyncio.iscoroutine(market_data):
                        regime_result = detector.analyze_regime_rules(market_data)
                        snapshot["regime"] = regime_result.get("regime")
                        snapshot["risk_mode"] = regime_result.get("risk_mode")
                        snapshot["regime_confidence"] = regime_result.get("confidence")
            else:
                # No cache at all — do a fresh fetch
                market_data = await detector.get_market_data()
                regime_result = detector.analyze_regime_rules(market_data)
                snapshot["regime"] = regime_result.get("regime")
                snapshot["risk_mode"] = regime_result.get("risk_mode")
                snapshot["regime_confidence"] = regime_result.get("confidence")
        except Exception as e:
            logger.warning(f"[PresetSelector] Regime unavailable: {e}")

        # 3. Fear & Greed Index — cached with 5min TTL
        try:
            from app.services.command_center import get_market_data_service
            fg_data = await get_market_data_service().get_fear_greed_index()
            if fg_data:
                snapshot["fear_greed"] = fg_data.get("value")
        except Exception as e:
            logger.warning(f"[PresetSelector] Fear & Greed unavailable: {e}")

        # 4. Trade Readiness — cached with 90s TTL
        try:
            from app.services.command_center import get_catalyst_service
            readiness = await get_catalyst_service().calculate_trade_readiness(db)
            if readiness:
                snapshot["readiness"] = readiness.get("trade_readiness_score")
                snapshot["readiness_label"] = readiness.get("readiness_label")
        except Exception as e:
            logger.warning(f"[PresetSelector] Trade Readiness unavailable: {e}")

        return snapshot

    def _compute_composite_score(self, snapshot: Dict[str, Any]) -> tuple:
        """
        Compute a weighted composite market score from all intelligence signals.

        Each signal is normalized to a -100 to +100 scale:
          - Positive = bullish sentiment
          - Negative = bearish sentiment

        Returns:
            (composite_score, signal_scores_dict)
        """
        signal_scores = {}
        available_weight = 0.0

        # 1. Market Regime → -100 to +100
        regime = snapshot.get("regime")
        if regime is not None:
            confidence = snapshot.get("regime_confidence")
            conf_multiplier = min(confidence / 100.0, 1.0) if confidence is not None else 0.7
            regime_map = {
                "bullish": 80,
                "neutral": 0,
                "bearish": -80,
            }
            raw = regime_map.get(regime, 0)
            signal_scores["regime"] = raw * conf_multiplier
            available_weight += SIGNAL_WEIGHTS["regime"]
        else:
            signal_scores["regime"] = None

        # 2. MRI → -100 to +100 (INVERTED: low MRI = bullish, high MRI = bearish)
        mri = snapshot.get("mri")
        if mri is not None:
            # MRI 0-100: 0 = max bullish, 50 = neutral, 100 = max bearish
            # Convert to: +100 = bullish, -100 = bearish
            signal_scores["mri"] = (50 - mri) * 2  # MRI=0→+100, MRI=50→0, MRI=100→-100
            available_weight += SIGNAL_WEIGHTS["mri"]
        else:
            signal_scores["mri"] = None

        # 3. Fear & Greed → -100 to +100
        fg = snapshot.get("fear_greed")
        if fg is not None:
            # F&G 0-100: 0 = extreme fear (bearish), 50 = neutral, 100 = extreme greed (bullish)
            signal_scores["fear_greed"] = (fg - 50) * 2  # F&G=0→-100, F&G=50→0, F&G=100→+100
            available_weight += SIGNAL_WEIGHTS["fear_greed"]
        else:
            signal_scores["fear_greed"] = None

        # 4. Trade Readiness → -100 to +100
        readiness = snapshot.get("readiness")
        readiness_label = snapshot.get("readiness_label")
        if readiness is not None:
            # Readiness 0-100: 0 = best (risk-on/green), 100 = worst (risk-off/red)
            # Convert to: +100 = bullish, -100 = bearish
            signal_scores["readiness"] = (50 - readiness) * 2
            available_weight += SIGNAL_WEIGHTS["readiness"]
        elif readiness_label is not None:
            # Fallback: just use the label
            label_map = {"green": 60, "yellow": 0, "red": -60}
            signal_scores["readiness"] = label_map.get(readiness_label, 0)
            available_weight += SIGNAL_WEIGHTS["readiness"]
        else:
            signal_scores["readiness"] = None

        # Compute weighted composite, normalizing by available weight
        if available_weight == 0:
            return 0.0, signal_scores

        composite = 0.0
        for signal_name, weight in SIGNAL_WEIGHTS.items():
            score = signal_scores.get(signal_name)
            if score is not None:
                # Re-normalize weight proportionally to available signals
                normalized_weight = weight / available_weight
                composite += score * normalized_weight

        return composite, signal_scores

    def _classify_condition(self, score: float, snapshot: Dict[str, Any]) -> str:
        """
        Map composite score to a market condition.

        Uses the composite score as primary classifier, with hard overrides
        only for extreme danger signals (MRI > 80 + extreme fear).
        """
        mri = snapshot.get("mri")
        fear_greed = snapshot.get("fear_greed")

        # Hard override: skip ONLY in extreme panic (MRI > 80 AND F&G < 10)
        # This is the ONLY single-signal override — reserved for true emergencies
        if mri is not None and fear_greed is not None:
            if mri > 80 and fear_greed < 10:
                return "skip"

        # Score-based classification (all signals contribute proportionally)
        if score >= CONDITION_THRESHOLDS["aggressive_bull"]:
            return "aggressive_bull"
        elif score >= CONDITION_THRESHOLDS["moderate_bull"]:
            return "moderate_bull"
        elif score >= CONDITION_THRESHOLDS["neutral"]:
            return "neutral"
        elif score >= CONDITION_THRESHOLDS["cautious"]:
            return "cautious"
        elif score >= CONDITION_THRESHOLDS["defensive"]:
            return "defensive"
        else:
            return "skip"

    def _build_reasoning(self, condition: str, composite_score: float,
                         signal_scores: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
        """Build a human-readable explanation of why this condition was selected."""
        parts = []

        # Composite score
        parts.append(f"Composite: {composite_score:+.1f}/100")

        # Individual signals with their contributions
        regime = snapshot.get("regime", "unknown")
        confidence = snapshot.get("regime_confidence", "?")
        regime_score = signal_scores.get("regime")
        regime_str = f"Regime: {regime} ({confidence}%)"
        if regime_score is not None:
            regime_str += f" → {regime_score:+.0f}"
        parts.append(regime_str)

        mri = snapshot.get("mri")
        mri_regime = snapshot.get("mri_regime", "unknown")
        mri_score = signal_scores.get("mri")
        if mri is not None:
            mri_str = f"MRI: {mri:.0f} ({mri_regime})"
            if mri_score is not None:
                mri_str += f" → {mri_score:+.0f}"
            parts.append(mri_str)

        fg = snapshot.get("fear_greed")
        fg_score = signal_scores.get("fear_greed")
        if fg is not None:
            label = "fear" if fg < 30 else "greed" if fg > 70 else "neutral"
            fg_str = f"F&G: {fg:.0f} ({label})"
            if fg_score is not None:
                fg_str += f" → {fg_score:+.0f}"
            parts.append(fg_str)
        else:
            parts.append("F&G: unavailable")

        readiness = snapshot.get("readiness")
        r_label = snapshot.get("readiness_label", "unknown")
        r_score = signal_scores.get("readiness")
        if readiness is not None:
            r_str = f"Readiness: {readiness:.0f} ({r_label})"
            if r_score is not None:
                r_str += f" → {r_score:+.0f}"
            parts.append(r_str)

        desc = MARKET_CONDITIONS[condition]["description"]
        return f"{desc} | {' | '.join(parts)}"


# ---------------------------------------------------------------------------
# Startup validation — verify preset names exist in catalog
# ---------------------------------------------------------------------------

_catalog_validated = False


def _validate_preset_catalog():
    """Verify all preset names in MARKET_CONDITIONS exist in LEAPS_PRESETS.

    In strict mode (PRESET_CATALOG_STRICT=true, default), raises ValueError
    on missing presets. In non-strict mode, logs ERROR.
    """
    global _catalog_validated
    if _catalog_validated:
        return

    try:
        from app.data.presets_catalog import LEAPS_PRESETS
        missing = []
        for condition, mapping in MARKET_CONDITIONS.items():
            for preset_name in mapping["presets"]:
                if preset_name not in LEAPS_PRESETS:
                    missing.append(f"{condition} -> {preset_name}")

        if missing:
            strict = os.environ.get("PRESET_CATALOG_STRICT", "true").lower() == "true"
            msg = f"[PresetSelector] MISSING PRESETS in catalog: {missing}"
            if strict:
                raise ValueError(msg)
            logger.error(msg)
        else:
            logger.info("[PresetSelector] All preset names validated against catalog")
    except ImportError as e:
        logger.warning(f"[PresetSelector] Cannot validate preset catalog: {e}")

    _catalog_validated = True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_preset_selector: Optional[PresetSelector] = None


def get_preset_selector() -> PresetSelector:
    """Get the global PresetSelector instance."""
    global _preset_selector
    if _preset_selector is None:
        _validate_preset_catalog()
        _preset_selector = PresetSelector()
    return _preset_selector
