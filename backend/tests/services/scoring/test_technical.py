"""Tests for technical analysis v1 _evaluate_technical()."""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from backend.app.services.screening.engine import ScreeningEngine
from backend.app.services.scoring.types import CriterionResult, GATE_CONFIGS


@pytest.fixture
def engine():
    """Create engine with mocked dependencies to avoid network calls."""
    with patch('backend.app.services.screening.engine.get_sentiment_analyzer'), \
         patch('backend.app.services.screening.engine.get_catalyst_service'):
        return ScreeningEngine()


def _make_price_data(n_days=260):
    """Create synthetic price DataFrame."""
    dates = pd.date_range(end='2025-01-01', periods=n_days, freq='B')
    return pd.DataFrame({
        'close': np.linspace(90, 110, n_days),
        'high': np.linspace(92, 112, n_days),
        'low': np.linspace(88, 108, n_days),
        'volume': [1_000_000] * n_days,
    }, index=dates)


def _indicators(**overrides):
    base = {
        'current_price': 110.0,
        'sma_20': 108.0,
        'sma_50': 105.0,
        'sma_200': 100.0,
        'rsi_14': 55.0,
        'macd': 1.5,
        'macd_signal': 1.0,
        'macd_histogram': 0.5,
        'volume': 1_200_000,
        'atr_14': 4.0,
        'adx_14': 30.0,
    }
    base.update(overrides)
    return base


class TestDataSufficiency:
    def test_insufficient_data_returns_all_unknown(self, engine):
        """< 200 trading days → all UNKNOWN, score=None."""
        short_data = _make_price_data(199)  # Below 200-day minimum
        result = engine._evaluate_technical(_indicators(), short_data)
        assert result.reason == "insufficient_price_history"
        assert result.score_pct is None
        assert result.score_points is None
        for v in result.criteria.values():
            assert v == CriterionResult.UNKNOWN

    def test_sufficient_data_evaluates(self, engine):
        result = engine._evaluate_technical(
            _indicators(), _make_price_data(260), avg_volume=1_000_000
        )
        assert result.reason is None
        assert result.score_pct is not None


class TestTechnicalTriState:
    def test_uptrend_pass(self, engine):
        result = engine._evaluate_technical(
            _indicators(current_price=110, sma_50=105, sma_200=100),
            _make_price_data(), avg_volume=1_000_000,
        )
        assert result.criteria['uptrend'] == CriterionResult.PASS

    def test_uptrend_fail(self, engine):
        result = engine._evaluate_technical(
            _indicators(current_price=95, sma_50=105, sma_200=100),
            _make_price_data(), avg_volume=1_000_000,
        )
        assert result.criteria['uptrend'] == CriterionResult.FAIL

    def test_uptrend_unknown(self, engine):
        result = engine._evaluate_technical(
            _indicators(sma_200=None),
            _make_price_data(), avg_volume=1_000_000,
        )
        assert result.criteria['uptrend'] == CriterionResult.UNKNOWN

    def test_rsi_unknown(self, engine):
        result = engine._evaluate_technical(
            _indicators(rsi_14=None),
            _make_price_data(), avg_volume=1_000_000,
        )
        assert result.criteria['rsi_ok'] == CriterionResult.UNKNOWN

    def test_breakout_is_never_unknown(self, engine):
        """Breakout is always PASS or FAIL, never UNKNOWN."""
        result = engine._evaluate_technical(
            _indicators(), _make_price_data(),
            avg_volume=1_000_000, is_breakout=False,
        )
        assert result.criteria['breakout'] == CriterionResult.FAIL


class TestTechnicalScorePoints:
    def test_rsi_max_is_15(self, engine):
        """RSI max should be 15, not 20 (v1 spec)."""
        result = engine._evaluate_technical(
            _indicators(
                current_price=0,  # fail trend
                sma_20=0, sma_50=0, sma_200=0,  # fail trend
                rsi_14=55,         # RSI sweet spot (50-65) → 15 pts
                macd=0, macd_signal=1, macd_histogram=-1,  # fail MACD
                volume=0,          # fail volume
                atr_14=0,          # fail volatility
                adx_14=0,          # fail trend strength
            ),
            _make_price_data(),
            avg_volume=1_000_000, is_breakout=False,
        )
        # Only RSI contributes: 15 earned, 90 known_max (all known), 90 total
        assert result.points_earned == 15.0

    def test_macd_max_is_15(self, engine):
        """MACD max should be 15, not 20 (v1 spec)."""
        result = engine._evaluate_technical(
            _indicators(
                current_price=0, sma_20=0, sma_50=0, sma_200=0,
                rsi_14=30,  # outside sweet spot → 0
                macd=2.0, macd_signal=1.0, macd_histogram=1.0,  # perfect MACD → 15
                volume=0, atr_14=0, adx_14=0,
            ),
            _make_price_data(),
            avg_volume=1_000_000, is_breakout=False,
        )
        assert result.points_earned == 15.0

    def test_non_breakout_perfect_is_75(self, engine):
        """Non-breakout perfect = 25(trend) + 15(RSI) + 15(MACD) + 20(vol) = 75."""
        result = engine._evaluate_technical(
            _indicators(
                current_price=110, sma_20=108, sma_50=105, sma_200=100,  # +25
                rsi_14=55,  # +15
                macd=2.0, macd_signal=1.0, macd_histogram=1.0,  # +15
                volume=2_000_000,  # > 1.5x avg → +20
                atr_14=4.0, adx_14=30,
            ),
            _make_price_data(),
            avg_volume=1_000_000, is_breakout=False,
        )
        assert result.points_earned == 75.0

    def test_breakout_adds_15_to_90(self, engine):
        """With breakout: 75 + 15 = 90 max."""
        result = engine._evaluate_technical(
            _indicators(
                current_price=110, sma_20=108, sma_50=105, sma_200=100,
                rsi_14=55, macd=2.0, macd_signal=1.0, macd_histogram=1.0,
                volume=2_000_000, atr_14=4.0, adx_14=30,
            ),
            _make_price_data(),
            avg_volume=1_000_000, is_breakout=True,
        )
        assert result.points_earned == 90.0
        assert result.score_pct == 100.0
        assert result.score_points == 90.0

    def test_total_max_is_90(self, engine):
        result = engine._evaluate_technical(
            _indicators(), _make_price_data(), avg_volume=1_000_000,
        )
        assert result.points_total_max == 90.0
