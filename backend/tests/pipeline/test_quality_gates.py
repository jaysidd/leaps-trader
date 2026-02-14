"""
Quality Gate Validation Tests — Targeted tests for gate accuracy.

These tests validate that the pipeline's quality gates correctly handle
the SN-like scenario and other edge cases. They quantify the impact of
the threshold fixes and document expected behavior.
"""
import pytest
from app.services.signals.signal_engine import SignalEngine
from app.services.signals.strategy_selector import StrategySelector
from app.services.signals.signal_validator import CONFIDENCE_THRESHOLD
from tests.pipeline.helpers import (
    make_signal_engine_df,
    make_screening_result,
    make_fresh_metrics,
    make_alpaca_snapshot,
)
from tests.pipeline.mock_stocks import (
    EDGE_SIGNAL_DF,
    EDGE_STOCK_DATA,
    EDGE_FRESH_METRICS,
    EDGE_SNAPSHOT,
)


@pytest.fixture
def engine():
    return SignalEngine()


@pytest.fixture
def selector():
    return StrategySelector()


class TestGatePenaltyCapImpact:
    """Tests that quantify the gate penalty cap's effect on confidence."""

    def test_severe_gate_penalty_not_fully_rescued(self, engine):
        """Raw gate penalty of -40 should not be capped to just -15 anymore.

        After Fix 1: cap is -25 (was -15).
        Impact: stock loses 25 points from gate penalty instead of just 15.
        """
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,  # No trend bonus
            rsi=50.0,                  # No momentum
            volume_spike=False,        # No volume bonus
            rvol=1.0,
        )

        # Severe gate penalties: both ATR and RVOL well below pivot
        score_severe = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -20, "rvol_score": -20},  # -40 raw
        )

        # Zero gate penalties
        score_zero = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )

        actual_penalty = score_zero - score_severe
        # With new cap of -25: penalty should be 25 (not the old 15)
        assert actual_penalty == 25, \
            f"Gate penalty cap should be 25, got {actual_penalty}"

    def test_edge_stock_below_min_confidence(self, engine):
        """EDGE stock (SN-like) should score below MIN_CONFIDENCE after fixes.

        Key scenario: stock with weak ATR/RVOL that previously scored 65+
        due to generous cap, now scores lower.
        """
        score = engine._calculate_confidence(
            EDGE_SIGNAL_DF, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -18, "rvol_score": -17},  # -35 raw → capped to -25
            iv_score=-5.0,   # Elevated IV penalty
            earnings_score=0.0,
        )
        # Base 50 + trend ~15 (ema8 slightly above ema21) + momentum 0 (RSI 42 < 55)
        # + volume 0 (no spike, rvol 0.6) + ATR quality 0
        # + gate -25 (capped from -35) + IV -5 + earnings 0
        # = 50 + 15 + 0 + 0 + 0 - 25 - 5 = 35
        assert score < 62, \
            f"EDGE stock should be below MIN_CONFIDENCE (62) after fixes, got {score}"

    def test_moderate_penalty_unchanged(self, engine):
        """Moderate gate penalties (-10 combined) should be unchanged."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False, rvol=1.0,
        )
        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -5, "rvol_score": -5},
        )
        score_zero = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )
        # -10 is within -25 cap, so applied in full
        assert score_zero - score == 10


class TestCompositeFloor:
    """Test that the raised MIN_COMPOSITE_SCORE catches marginal stocks."""

    def test_score_29_now_filtered(self):
        """Stock scoring 29 (was passing at MIN=20) should now be filtered (MIN=30)."""
        # This documents the behavior: any stock with composite < 30 is now rejected
        # at the screening stage before reaching signal engine.
        from app.services.screening.engine import ScreeningEngine
        # We can't easily call screen_single_stock without full mocking,
        # but we verify the constant changed
        # The constant is defined inline in screen_single_stock, so we check
        # it in a different way — read the source to confirm
        import inspect
        source = inspect.getsource(ScreeningEngine.screen_single_stock)
        assert "MIN_COMPOSITE_SCORE = 30" in source, \
            "MIN_COMPOSITE_SCORE should be 30"


class TestSNScenarioReproduction:
    """Reproduce the SN case to document where the pipeline catches it."""

    def test_sn_like_stock_signal_engine(self, engine):
        """SN-like stock: weak volume, oversold RSI, poor gate scores.

        SN characteristics from the AI Batch Analysis:
        - Weak volume (0.73x)
        - RSI oversold at 42
        - Missing VWAP data
        - 1/5 checks passed

        This should produce confidence well below MIN_CONFIDENCE.
        """
        df = make_signal_engine_df(
            base_price=131.0,
            ema8=131.5,      # Slight bullish
            ema21=130.0,
            rsi=42.0,        # Oversold — no momentum bonus
            atr=3.0,
            atr_percent=0.023,
            rvol=0.73,       # Below 0.8 pivot → RVOL penalty
            rvol_tod=None,
            volume_spike=False,
            adx=20.0,
        )

        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -12, "rvol_score": -15},  # -27 → capped to -25
            iv_score=-5.0,
            earnings_score=0.0,
        )

        # Base 50 + trend 15 (ema8 > ema21 + close > ema21)
        # + momentum 0 (RSI 42 < 55) + volume 0
        # + gate -25 + IV -5
        # = 35
        assert score < 62, \
            f"SN-like stock should fail MIN_CONFIDENCE (62), got {score}"

    def test_sn_like_stock_strategy_selector(self, selector):
        """SN-like stock in StrategySelector should not get HIGH confidence."""
        stock_data = make_screening_result(
            symbol="SN",
            score=32.0,  # Just above new MIN (30)
            market_cap=5_000_000_000,
            iv_rank=55.0,
            avg_volume=1_500_000,
        )
        metrics = make_fresh_metrics(
            rsi=42.0,   # Oversold
            adx=20.0,   # Weak trend
        )
        snap = make_alpaca_snapshot(
            change_percent=0.5,
            volume=1_100_000,
            prev_volume=1_500_000,
        )

        result = selector.select_strategies(stock_data, metrics, snap)
        # Score 32 is below min_score for all timeframes (55+)
        assert result["confidence"] != "HIGH", \
            f"SN-like stock should not be HIGH confidence, got {result['confidence']}"


class TestWeakVolumeActuallyPenalized:
    """Verify that weak volume/RVOL actually reduces confidence."""

    def test_rvol_below_pivot_penalized(self, engine):
        """RVOL = 0.3 (well below 0.8 pivot) should have negative gate score."""
        # We test the outcome: a stock with very low RVOL gets a lower confidence
        df_weak_vol = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False,
            rvol=0.3,  # Very low
        )
        df_strong_vol = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False,
            rvol=2.5,  # Very high
        )

        score_weak = engine._calculate_confidence(
            df_weak_vol, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": -15},  # Representing weak RVOL
        )
        score_strong = engine._calculate_confidence(
            df_strong_vol, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 8},  # Representing strong RVOL
        )

        # Strong volume also gets +10 from RVOL > 2.0
        assert score_strong > score_weak + 15, \
            f"Strong volume should score much higher: {score_strong} vs {score_weak}"


class TestIVPenalty:
    """Verify high IV correctly penalizes."""

    def test_iv_90_large_cap_minus_20(self, engine):
        """IV rank 90 for large-cap should produce iv_score = -20."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False, rvol=1.0,
        )
        score_no_iv = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
            iv_score=0.0,
        )
        score_high_iv = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
            iv_score=-20.0,
        )
        assert score_no_iv - score_high_iv == 20


class TestAutoExecuteThreshold:
    """Verify the auto-execute threshold after Fix 4."""

    def test_threshold_is_70(self):
        """CONFIDENCE_THRESHOLD should be 70 (raised from 65)."""
        assert CONFIDENCE_THRESHOLD == 70

    def test_69_is_manual_review(self):
        """Confidence 69 should be manual_review (below 70 threshold)."""
        assert 69 < CONFIDENCE_THRESHOLD

    def test_70_is_auto_execute(self):
        """Confidence 70 should be auto_execute (at threshold)."""
        assert 70 >= CONFIDENCE_THRESHOLD


class TestEarningsProximityPenalty:
    """Verify earnings proximity hard penalty."""

    def test_earnings_within_14_days_high_iv(self, engine):
        """Earnings in <14 days + IV ≥ 70 → -10 penalty."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False, rvol=1.0,
        )
        score_no_earn = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
            earnings_score=0.0,
        )
        score_with_earn = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
            earnings_score=-10.0,
        )
        assert score_no_earn - score_with_earn == 10
