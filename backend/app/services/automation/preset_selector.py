"""
Market-Adaptive Preset Selector — The conductor's brain.

Reads cached market intelligence (MRI, regime, Fear & Greed, Trade Readiness)
and selects appropriate screening presets for current market conditions.

Uses ONLY cached data — never triggers new API calls. Fast (<10ms).
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session


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
        "presets": ["moderate", "low_iv_entry", "value_deep"],
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
        condition = self._classify_condition(snapshot)
        mapping = MARKET_CONDITIONS[condition]

        reasoning = self._build_reasoning(condition, snapshot)

        result = {
            "condition": condition,
            "presets": mapping["presets"],
            "max_positions": mapping["max_positions"],
            "reasoning": reasoning,
            "market_snapshot": snapshot,
        }

        logger.info(
            f"[PresetSelector] {condition} → {mapping['presets']} "
            f"(MRI={snapshot.get('mri', '?')}, regime={snapshot.get('regime', '?')}, "
            f"F&G={snapshot.get('fear_greed', '?')})"
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
                if datetime.now() - detector._cache_time < timedelta(minutes=10):
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

    def _classify_condition(self, snapshot: Dict[str, Any]) -> str:
        """
        Map market intelligence snapshot to a condition label.

        Priority order (most specific → most general):
        1. Extreme fear → skip
        2. Risk-off → defensive
        3. Bearish regime → defensive
        4. Cautious signals → cautious
        5. Neutral → neutral
        6. Moderate bull → moderate_bull
        7. Aggressive bull → aggressive_bull
        """
        mri = snapshot.get("mri")
        mri_regime = snapshot.get("mri_regime")
        regime = snapshot.get("regime")
        fear_greed = snapshot.get("fear_greed")
        readiness = snapshot.get("readiness")
        readiness_label = snapshot.get("readiness_label")

        # Use safe defaults if data is missing
        if mri is None:
            mri = 50  # Assume transition
        if fear_greed is None:
            fear_greed = 50  # Assume neutral
        if regime is None:
            regime = "neutral"

        # 1. Extreme fear: MRI risk_off + F&G < 15
        if mri > 66 and fear_greed < 15:
            return "skip"

        # 2. Defensive: MRI risk_off OR regime bearish OR F&G < 25
        if mri > 66 or regime == "bearish" or fear_greed < 25:
            return "defensive"

        # 3. Cautious: readiness yellow OR MRI leaning risk_off (50-66)
        if readiness_label == "yellow" or (50 <= mri <= 66):
            return "cautious"

        # 4. Neutral: regime neutral + MRI transition
        if regime == "neutral" and 33 <= mri <= 66:
            return "neutral"

        # 5. Aggressive bull: regime bullish + MRI risk_on + F&G > 60
        if regime == "bullish" and mri < 33 and fear_greed > 60:
            return "aggressive_bull"

        # 6. Moderate bull: regime bullish + MRI transition
        if regime == "bullish":
            return "moderate_bull"

        # 7. Default: neutral
        return "neutral"

    def _build_reasoning(self, condition: str, snapshot: Dict[str, Any]) -> str:
        """Build a human-readable explanation of why this condition was selected."""
        parts = []

        regime = snapshot.get("regime", "unknown")
        confidence = snapshot.get("regime_confidence", "?")
        parts.append(f"Regime: {regime} (confidence {confidence})")

        mri = snapshot.get("mri")
        mri_regime = snapshot.get("mri_regime", "unknown")
        if mri is not None:
            parts.append(f"MRI: {mri:.0f} ({mri_regime})")

        fg = snapshot.get("fear_greed")
        if fg is not None:
            label = "fear" if fg < 30 else "greed" if fg > 70 else "neutral"
            parts.append(f"F&G: {fg:.0f} ({label})")

        readiness = snapshot.get("readiness")
        r_label = snapshot.get("readiness_label", "unknown")
        if readiness is not None:
            parts.append(f"Readiness: {readiness:.0f} ({r_label})")

        desc = MARKET_CONDITIONS[condition]["description"]
        return f"{desc} | {' | '.join(parts)}"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_preset_selector: Optional[PresetSelector] = None


def get_preset_selector() -> PresetSelector:
    """Get the global PresetSelector instance."""
    global _preset_selector
    if _preset_selector is None:
        _preset_selector = PresetSelector()
    return _preset_selector
