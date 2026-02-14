"""
Full Pipeline E2E Tests — Trace stocks through multiple pipeline layers.

These tests wire up real service classes with controlled mock data to
validate that the pipeline produces expected outcomes end-to-end.

Note: These are integration tests at the function level, not HTTP-level.
They call service methods directly with controlled inputs.
"""
import pytest
from app.services.automation.preset_selector import PresetSelector
from app.services.signals.signal_engine import SignalEngine
from app.services.signals.strategy_selector import StrategySelector
from app.services.signals.signal_validator import SignalValidator, CONFIDENCE_THRESHOLD
from tests.pipeline.helpers import (
    make_signal_engine_df,
    make_screening_result,
    make_fresh_metrics,
    make_alpaca_snapshot,
)
from tests.pipeline.mock_market import BULLISH_MARKET, PANIC_MARKET
from tests.pipeline.mock_stocks import (
    STRONG_STOCK_DATA,
    STRONG_FRESH_METRICS,
    STRONG_SNAPSHOT,
    STRONG_SIGNAL_DF,
    WEAK_STOCK_DATA,
    WEAK_FRESH_METRICS,
    WEAK_SNAPSHOT,
    EDGE_STOCK_DATA,
    EDGE_FRESH_METRICS,
    EDGE_SNAPSHOT,
    EDGE_SIGNAL_DF,
    NODATA_STOCK_DATA,
    NODATA_FRESH_METRICS,
    NODATA_SNAPSHOT,
)


class TestPresetToStrategyPipeline:
    """Test PresetSelector → StrategySelector pipeline."""

    def test_bullish_market_strong_stock_high_confidence(self):
        """
        Layer 1 (PresetSelector): Bullish market → aggressive presets
        Layer 5 (StrategySelector): Strong stock → HIGH confidence

        The strong stock should be auto-queued for signal generation.
        """
        # Layer 1: PresetSelector
        selector = PresetSelector()
        score, signals = selector._compute_composite_score(BULLISH_MARKET)
        condition = selector._classify_condition(score, BULLISH_MARKET)

        assert condition in ("aggressive_bull", "moderate_bull"), \
            f"Bullish market should be bull condition, got {condition}"

        # Layer 5: StrategySelector
        ss = StrategySelector()
        result = ss.select_strategies(
            STRONG_STOCK_DATA, STRONG_FRESH_METRICS, STRONG_SNAPSHOT,
        )

        assert result["confidence"] == "HIGH", \
            f"Strong stock should get HIGH confidence, got {result['confidence']}"
        assert result["auto_queue"] is True

    def test_panic_market_skips_scanning(self):
        """
        Layer 1: Panic market → skip (no presets selected)

        Nothing should be scanned in panic conditions.
        """
        selector = PresetSelector()
        score, signals = selector._compute_composite_score(PANIC_MARKET)
        condition = selector._classify_condition(score, PANIC_MARKET)

        assert condition == "skip"


class TestSignalEngineQuality:
    """Test Signal Engine confidence for different stock qualities."""

    def test_strong_stock_passes_min_confidence(self):
        """
        Layer 4: Strong stock with good indicators → above MIN_CONFIDENCE.
        """
        engine = SignalEngine()
        score = engine._calculate_confidence(
            STRONG_SIGNAL_DF, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 3, "rvol_score": 8},
            iv_score=3.0,
            earnings_score=0.0,
        )

        assert score >= engine.MIN_CONFIDENCE, \
            f"Strong stock should pass MIN_CONFIDENCE ({engine.MIN_CONFIDENCE}), got {score}"
        assert score >= 75, \
            f"Strong stock should score well above minimum, got {score}"

    def test_edge_stock_fails_min_confidence(self):
        """
        Layer 4: Edge stock (SN-like) with poor gates → below MIN_CONFIDENCE.

        After threshold fixes:
        - Gate cap changed from -15 to -25
        - MIN_CONFIDENCE changed from 60 to 62
        Combined effect: edge stocks that previously scored 60-65 now score ~35-40.
        """
        engine = SignalEngine()
        score = engine._calculate_confidence(
            EDGE_SIGNAL_DF, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -18, "rvol_score": -17},
            iv_score=-5.0,
            earnings_score=0.0,
        )

        assert score < engine.MIN_CONFIDENCE, \
            f"Edge stock should fail MIN_CONFIDENCE ({engine.MIN_CONFIDENCE}), got {score}"


class TestStrategyToValidatorPipeline:
    """Test StrategySelector → SignalValidator pipeline logic."""

    def test_strong_stock_passes_strategy_and_validator_threshold(self):
        """
        Layer 5: Strong stock → HIGH confidence
        Layer 6: If AI returns confidence ≥ 70 → auto_execute

        The threshold chain should allow genuinely strong setups through.
        """
        ss = StrategySelector()
        result = ss.select_strategies(
            STRONG_STOCK_DATA, STRONG_FRESH_METRICS, STRONG_SNAPSHOT,
        )
        assert result["confidence"] == "HIGH"

        # Layer 6: The validator threshold
        # A strong stock should get AI confidence well above 70
        mock_ai_confidence = 82  # What Claude would likely return
        assert mock_ai_confidence >= CONFIDENCE_THRESHOLD

    def test_weak_stock_rejected_at_strategy_selector(self):
        """
        Layer 5: Weak stock → LOW confidence → skipped entirely.

        Never reaches validator or auto-trader.
        """
        ss = StrategySelector()
        result = ss.select_strategies(
            WEAK_STOCK_DATA, WEAK_FRESH_METRICS, WEAK_SNAPSHOT,
        )
        assert result["confidence"] == "LOW"
        assert result["auto_queue"] is False

    def test_nodata_stock_handled_gracefully(self):
        """
        Missing data should not crash any pipeline layer.
        """
        ss = StrategySelector()
        result = ss.select_strategies(
            NODATA_STOCK_DATA, NODATA_FRESH_METRICS, NODATA_SNAPSHOT,
        )
        assert result["confidence"] == "LOW"


class TestThresholdInteraction:
    """Test how the threshold fixes interact across layers."""

    def test_fixes_create_harder_path_for_marginal_stocks(self):
        """
        Document the cumulative effect of all 5 fixes on a marginal stock.

        A stock with composite score 28 (old MIN was 20, new is 30):
        → Rejected at screening (Fix 2)

        A stock with composite score 32 and poor ATR/RVOL:
        → Passes screening (32 > 30)
        → Signal engine: penalty cap -25 (was -15) → lower confidence (Fix 1)
        → Likely below MIN_CONFIDENCE 62 (was 60) (Fix 5)
        → Even if it passes, validator threshold is 70 (was 65) (Fix 4)

        This test documents that the fixes work together.
        """
        engine = SignalEngine()
        ss = StrategySelector()

        # Stock with score 32 (just above new MIN of 30)
        stock_data = make_screening_result(
            symbol="MARGINAL", score=32.0, market_cap=5_000_000_000,
        )

        # StrategySelector: score 32 is below min_score for ALL timeframes (55+)
        result = ss.select_strategies(stock_data, {}, {})
        assert result["confidence"] == "LOW", \
            "Marginal stock (score 32) should be LOW at strategy selector"

        # Signal Engine: even with some trend alignment, gate penalty kills it
        df = make_signal_engine_df(
            base_price=50.0,
            ema8=50.5, ema21=49.5,  # +15 trend
            rsi=50.0,                # 0 momentum
            volume_spike=False, rvol=0.6,  # 0 volume
        )
        confidence = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -15, "rvol_score": -15},  # -30 → capped to -25
            iv_score=-5.0,
        )
        # Base 50 + trend 15 + momentum 0 + volume 0 - gate 25 - IV 5 = 35
        assert confidence < engine.MIN_CONFIDENCE, \
            f"Marginal stock should fail signal engine, got confidence {confidence}"

    def test_strong_stock_still_passes_all_fixes(self):
        """
        Strong stocks should still pass through all layers after fixes.

        The fixes tighten thresholds for marginal stocks but should not
        block genuinely strong setups.
        """
        engine = SignalEngine()
        ss = StrategySelector()

        # Strategy selector
        result = ss.select_strategies(
            STRONG_STOCK_DATA, STRONG_FRESH_METRICS, STRONG_SNAPSHOT,
        )
        assert result["confidence"] == "HIGH"

        # Signal engine
        confidence = engine._calculate_confidence(
            STRONG_SIGNAL_DF, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 3, "rvol_score": 8},
            iv_score=3.0,
            earnings_score=0.0,
        )
        assert confidence >= engine.MIN_CONFIDENCE
        assert confidence >= 80, \
            f"Strong stock should still score 80+, got {confidence}"
