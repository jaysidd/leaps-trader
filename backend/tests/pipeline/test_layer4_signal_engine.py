"""
Layer 4: SignalEngine — Confidence calculation and quality gate tests.

Tests the _calculate_confidence() method and quality gate scoring,
focusing on the gate penalty cap behavior and how it affects final confidence.
"""
import pytest
import pandas as pd
from app.services.signals.signal_engine import SignalEngine
from tests.pipeline.helpers import make_signal_engine_df
from tests.pipeline.mock_stocks import (
    STRONG_SIGNAL_DF,
    WEAK_SIGNAL_DF,
    EDGE_SIGNAL_DF,
)


@pytest.fixture
def engine():
    return SignalEngine()


class TestConfidenceCalculation:
    """Unit tests for _calculate_confidence()."""

    def test_base_score_is_50(self, engine):
        """With minimal indicators, base score should be ~50."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,  # No trend (equal)
            rsi=50.0,                  # Neutral RSI
            volume_spike=False,
            rvol=1.0,                 # Neutral volume
            atr_percent=0.01,         # Below threshold
        )
        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
            iv_score=0.0,
            earnings_score=0.0,
        )
        assert 45 <= score <= 55, f"Neutral signals should give ~50, got {score}"

    def test_trend_alignment_long_bullish(self, engine):
        """EMA8 > EMA21 + close > EMA21 → +20 trend points."""
        df = make_signal_engine_df(
            base_price=105.0,
            ema8=106.0,   # EMA8 > EMA21 → +15
            ema21=103.0,  # Close (105) > EMA21 (103) → +5
            rsi=50.0,
            volume_spike=False,
            rvol=1.0,
        )
        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )
        # Base 50 + trend 20 = 70
        assert score >= 65, f"Bullish trend should add +20, got score {score}"

    def test_momentum_rsi_above_60_long(self, engine):
        """RSI > 60 for long → +15 momentum (10 for >55 + 5 for >60)."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=62.0,
            volume_spike=False,
            rvol=1.0,
        )
        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )
        # Base 50 + momentum 15 = 65
        assert score >= 60, f"RSI > 60 should add momentum, got {score}"

    def test_volume_spike_plus_high_rvol(self, engine):
        """Volume spike + RVOL > 2.0 → +20 volume points."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0,
            volume_spike=True,  # +10
            rvol=2.5,           # +10 (>2.0 tier)
        )
        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )
        # Base 50 + volume 20 = 70
        assert score >= 65, f"Strong volume should add +20, got {score}"

    def test_atr_quality_bonus(self, engine):
        """ATR > min_atr * 1.5 → +5 points."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0,
            volume_spike=False,
            rvol=1.0,
            atr_percent=0.30,  # Well above 0.15 * 1.5 = 0.225
        )
        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )
        # Base 50 + ATR quality 5 = 55
        assert score >= 53, f"Good ATR should add +5, got {score}"

    def test_iv_penalty_applied(self, engine):
        """IV score penalty is applied directly."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False, rvol=1.0,
        )
        score_no_iv = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
            iv_score=0.0,
        )
        score_with_iv = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
            iv_score=-20.0,
        )
        assert score_with_iv == score_no_iv - 20, \
            f"IV penalty should reduce score by 20: {score_no_iv} → {score_with_iv}"

    def test_earnings_penalty_applied(self, engine):
        """Earnings proximity penalty is applied directly."""
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
        assert score_with_earn == score_no_earn - 10

    def test_score_clamped_0_to_100(self, engine):
        """Confidence score is clamped between 0 and 100."""
        # Max everything
        df = make_signal_engine_df(
            base_price=100.0,
            ema8=101.0, ema21=99.0,
            rsi=65.0,
            volume_spike=True,
            rvol=3.0,
            atr_percent=0.30,
        )
        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 5, "rvol_score": 10},
            iv_score=5.0,
            earnings_score=0.0,
        )
        assert 0 <= score <= 100


class TestGatePenaltyCap:
    """Tests for the gate penalty capping behavior (the key SN issue)."""

    def test_gate_penalty_cap_exists(self, engine):
        """Gate penalties are capped (not applied in full when below cap)."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False, rvol=1.0,
        )

        # Severe gate penalties
        score_raw = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -20, "rvol_score": -20},  # -40 raw
        )
        # Without penalties
        score_zero = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )

        actual_penalty = score_zero - score_raw
        # After our fix, cap should be -25 (not the original -15)
        assert actual_penalty <= 26, \
            f"Gate penalty should be capped, actual penalty: {actual_penalty}"
        # But it should still be meaningful (not just -5)
        assert actual_penalty >= 15, \
            f"Gate penalty should be meaningful, actual penalty: {actual_penalty}"

    def test_moderate_gate_penalty_not_capped(self, engine):
        """Moderate gate penalties (-10 combined) are applied in full."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False, rvol=1.0,
        )
        score_moderate = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -5, "rvol_score": -5},  # -10 total
        )
        score_zero = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )
        penalty = score_zero - score_moderate
        assert penalty == 10, f"-10 gate penalty should be applied in full, got {penalty}"

    def test_positive_gate_scores_add(self, engine):
        """Positive gate scores (above pivot) add points."""
        df = make_signal_engine_df(
            ema8=100.0, ema21=100.0,
            rsi=50.0, volume_spike=False, rvol=1.0,
        )
        score = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 5, "rvol_score": 10},  # +15
        )
        score_zero = engine._calculate_confidence(
            df, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 0, "rvol_score": 0},
        )
        assert score > score_zero

    def test_edge_stock_confidence_with_penalties(self, engine):
        """EDGE stock with poor ATR/RVOL should have reduced confidence."""
        score = engine._calculate_confidence(
            EDGE_SIGNAL_DF, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -18, "rvol_score": -17},  # -35 raw
            iv_score=-5.0,  # Elevated IV
            earnings_score=0.0,
        )
        # After fix (cap -25): score should be lower than 60
        # Base 50 + trend ~15 + momentum 0 + vol 0 + cap(-25) + IV(-5) = 35
        assert score < 65, f"EDGE stock should be below MIN_CONFIDENCE, got {score}"


class TestStrongStockConfidence:
    """Tests that strong stocks still get high confidence after threshold fixes."""

    def test_strong_stock_high_confidence(self, engine):
        """STRONG stock should still achieve high confidence."""
        score = engine._calculate_confidence(
            STRONG_SIGNAL_DF, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": 3, "rvol_score": 8},  # Good gates
            iv_score=3.0,   # Good IV
            earnings_score=0.0,
        )
        assert score >= 80, f"STRONG stock should score ≥80, got {score}"

    def test_weak_stock_low_confidence(self, engine):
        """WEAK stock should get low confidence."""
        score = engine._calculate_confidence(
            WEAK_SIGNAL_DF, "long", {"min_atr_percent": 0.15},
            gate_scores={"atr_score": -15, "rvol_score": -15},
            iv_score=-12.0,
            earnings_score=-5.0,
        )
        assert score < 50, f"WEAK stock should score <50, got {score}"
