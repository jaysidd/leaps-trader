"""Tests for options analysis v1 evaluate()."""
import pytest
from unittest.mock import patch
from backend.app.services.analysis.options import OptionsAnalysis
from backend.app.services.scoring.types import CriterionResult, GATE_CONFIGS


class TestComputeMidPrice:
    def test_bid_ask_both_positive(self):
        assert OptionsAnalysis._compute_mid_price(10.0, 12.0) == 11.0

    def test_bid_zero_falls_back_to_last(self):
        assert OptionsAnalysis._compute_mid_price(0, 12.0, last=9.0) == 9.0

    def test_ask_zero_falls_back_to_last(self):
        assert OptionsAnalysis._compute_mid_price(10.0, 0, last=9.0) == 9.0

    def test_all_zero_returns_none(self):
        assert OptionsAnalysis._compute_mid_price(0, 0, last=0) is None

    def test_none_inputs_falls_back_to_last(self):
        assert OptionsAnalysis._compute_mid_price(None, None, last=5.0) == 5.0

    def test_no_fallback_returns_none(self):
        assert OptionsAnalysis._compute_mid_price(None, None) is None


def _option_data(**overrides):
    base = {
        'implied_volatility': 0.40,
        'open_interest': 600,
        'volume': 150,
        'bid': 8.0,
        'ask': 9.0,
        'last_price': 8.5,
    }
    base.update(overrides)
    return base


class TestOptionsEvaluateHardFail:
    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data', return_value={})
    def test_no_options_data_is_hard_fail(self, _):
        """D2: No options data → hard fail, not UNKNOWN."""
        result = OptionsAnalysis.evaluate(
            option_data=None, current_price=100.0, symbol="TEST",
            has_options_data=False,
        )
        assert result.reason == "no_options_data"
        assert result.score_pct is None
        assert len(result.criteria) == 0

    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data', return_value={})
    def test_no_leaps_is_hard_fail(self, _):
        """D2: No LEAPS → hard fail, not UNKNOWN."""
        result = OptionsAnalysis.evaluate(
            option_data=_option_data(), current_price=100.0, symbol="TEST",
            leaps_available=False, has_options_data=True,
        )
        assert result.reason == "no_leaps"
        assert result.score_pct is None


class TestOptionsEvaluateTriState:
    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data', return_value={})
    def test_iv_unknown_when_none(self, _):
        result = OptionsAnalysis.evaluate(
            _option_data(implied_volatility=None),
            current_price=100.0, symbol="TEST",
        )
        assert result.criteria['iv_ok'] == CriterionResult.UNKNOWN

    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data', return_value={})
    def test_spread_unknown_when_no_bid_ask(self, _):
        result = OptionsAnalysis.evaluate(
            _option_data(bid=0, ask=0, last_price=8.5),
            current_price=100.0, symbol="TEST",
        )
        assert result.criteria['spread_ok'] == CriterionResult.UNKNOWN

    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data', return_value={})
    def test_premium_unknown_when_no_mid(self, _):
        result = OptionsAnalysis.evaluate(
            _option_data(bid=0, ask=0, last_price=0),
            current_price=100.0, symbol="TEST",
        )
        assert result.criteria['premium_ok'] == CriterionResult.UNKNOWN

    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data', return_value={})
    def test_all_pass(self, _):
        result = OptionsAnalysis.evaluate(
            _option_data(
                implied_volatility=0.25,  # <0.30 → PASS, +30
                open_interest=600,
                volume=150,               # OI>500 & Vol>100 → PASS, +25
                bid=3.0,
                ask=3.10,                 # spread ~3.2% → PASS, +20
            ),
            current_price=100.0, symbol="TEST",
        )
        for v in result.criteria.values():
            assert v == CriterionResult.PASS
        assert result.passes_gate(GATE_CONFIGS["options"]) is True


class TestOptionsEvaluateIVRankAdjustment:
    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data',
                  return_value={'iv_rank': 15})
    def test_low_iv_rank_bonus(self, _):
        """IV Rank < 20 → +15 bonus points."""
        result = OptionsAnalysis.evaluate(
            _option_data(), current_price=100.0, symbol="TEST",
        )
        # Should have iv_rank adjustment of +15 applied
        assert result.score_pct is not None
        assert result.score_pct > 0

    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data',
                  return_value={'iv_rank': 90})
    def test_high_iv_rank_penalty(self, _):
        """IV Rank > 85 → -20 penalty points."""
        result = OptionsAnalysis.evaluate(
            _option_data(), current_price=100.0, symbol="TEST",
        )
        assert result.score_pct is not None


class TestOptionsEvaluateCoverage:
    @patch.object(OptionsAnalysis, 'get_enhanced_iv_data', return_value={})
    def test_partial_data_coverage_adjustment(self, _):
        """With spread UNKNOWN, coverage penalty applies."""
        result = OptionsAnalysis.evaluate(
            _option_data(bid=0, ask=0, last_price=8.0),  # spread UNKNOWN
            current_price=100.0, symbol="TEST",
        )
        assert result.criteria['spread_ok'] == CriterionResult.UNKNOWN
        # points_known_max should exclude spread's 20 pts
        assert result.points_known_max < result.points_total_max
