"""Tests for expanded _matches_preset() function."""
import pytest

# Import directly — the function and LEAPS_PRESETS are module-level
from backend.app.data.presets_catalog import LEAPS_PRESETS
from backend.app.api.endpoints.screener import _matches_preset


def _result(**overrides):
    """Build a stock result dict with defaults that pass most presets."""
    base = {
        'market_cap': 5_000_000_000,
        'current_price': 100.0,
        'technical_indicators': {'rsi_14': 50.0},
        'iv_rank': 40.0,
        # Valuation metrics
        'trailing_pe': 18.0,
        'peg_ratio': 1.3,
        'price_to_book': 2.5,
        'dividend_yield': 0.02,
        'beta': 1.0,
        'roe': 0.15,
        'profit_margins': 0.12,
    }
    base.update(overrides)
    return base


class TestExistingBehavior:
    """Existing preset checks still work."""

    def test_moderate_passes(self):
        assert _matches_preset(_result(), 'moderate')

    def test_market_cap_too_low_fails(self):
        assert not _matches_preset(_result(market_cap=100_000_000), 'moderate')

    def test_price_too_high_fails(self):
        assert not _matches_preset(_result(current_price=999.0), 'moderate')

    def test_unknown_preset_returns_false(self):
        assert not _matches_preset(_result(), 'nonexistent_preset')


class TestDeepValuePreset:
    """deep_value: pe_max=15, pb_max=1.5, pe_min=0."""

    def test_high_pe_fails(self):
        """Stock with P/E=30 does NOT match deep_value (pe_max=15)."""
        result = _result(trailing_pe=30.0, market_cap=5_000_000_000)
        assert not _matches_preset(result, 'deep_value')

    def test_low_pe_low_pb_passes(self):
        result = _result(
            trailing_pe=10.0,
            price_to_book=1.2,
            market_cap=5_000_000_000,
            current_price=50.0,
            technical_indicators={'rsi_14': 40.0},
        )
        assert _matches_preset(result, 'deep_value')

    def test_no_pe_data_still_matches(self):
        """Stock with no P/E data still matches (graceful skip on None)."""
        result = _result(
            trailing_pe=None,
            price_to_book=1.2,
            market_cap=5_000_000_000,
            current_price=50.0,
            technical_indicators={'rsi_14': 40.0},
        )
        assert _matches_preset(result, 'deep_value')


class TestDividendIncomePreset:
    """dividend_income: dividend_yield_min=0.025."""

    def test_no_dividend_fails(self):
        """Stock with no dividend does NOT match dividend_income."""
        result = _result(
            dividend_yield=None,
            market_cap=10_000_000_000,
            current_price=100.0,
            trailing_pe=15.0,
            profit_margins=0.10,
            technical_indicators={'rsi_14': 50.0},
        )
        assert not _matches_preset(result, 'dividend_income')

    def test_good_dividend_passes(self):
        """Stock with 3% yield matches dividend_income."""
        result = _result(
            dividend_yield=0.03,
            market_cap=10_000_000_000,
            current_price=100.0,
            trailing_pe=15.0,
            profit_margins=0.10,
            technical_indicators={'rsi_14': 50.0},
        )
        assert _matches_preset(result, 'dividend_income')

    def test_low_dividend_fails(self):
        """Stock with 1% yield fails dividend_income (min 2.5%)."""
        result = _result(
            dividend_yield=0.01,
            market_cap=10_000_000_000,
            current_price=100.0,
            trailing_pe=15.0,
            profit_margins=0.10,
            technical_indicators={'rsi_14': 50.0},
        )
        assert not _matches_preset(result, 'dividend_income')


class TestGARPPreset:
    """garp: peg_max=1.5, pe_max=25, roe_min=0.12."""

    def test_high_peg_fails(self):
        result = _result(peg_ratio=2.5, trailing_pe=20.0, roe=0.15)
        assert not _matches_preset(result, 'garp')

    def test_peg_none_skips(self):
        """PEG None should be gracefully skipped (stock can still match)."""
        result = _result(
            peg_ratio=None,
            trailing_pe=20.0,
            roe=0.15,
            market_cap=5_000_000_000,
            current_price=100.0,
            technical_indicators={'rsi_14': 50.0},
        )
        assert _matches_preset(result, 'garp')

    def test_good_garp_passes(self):
        result = _result(
            peg_ratio=1.2,
            trailing_pe=18.0,
            roe=0.15,
            market_cap=5_000_000_000,
            current_price=100.0,
            technical_indicators={'rsi_14': 50.0},
        )
        assert _matches_preset(result, 'garp')


class TestCoveredCallPreset:
    """covered_call: beta_max=1.2, dividend_yield_min=0.005."""

    def test_high_beta_fails(self):
        result = _result(
            beta=1.8,
            dividend_yield=0.02,
            market_cap=15_000_000_000,
            current_price=100.0,
            technical_indicators={'rsi_14': 50.0},
        )
        assert not _matches_preset(result, 'covered_call')

    def test_low_beta_with_dividend_passes(self):
        result = _result(
            beta=0.9,
            dividend_yield=0.02,
            market_cap=15_000_000_000,
            current_price=100.0,
            technical_indicators={'rsi_14': 50.0},
        )
        assert _matches_preset(result, 'covered_call')


class TestIVCrushAlias:
    """iv_crush should still work as a backward-compat alias."""

    def test_iv_crush_alias_exists(self):
        assert 'iv_crush' in LEAPS_PRESETS
        assert LEAPS_PRESETS['iv_crush'] is LEAPS_PRESETS['low_iv_entry']

    def test_iv_crush_matches_same_as_low_iv_entry(self):
        result = _result(
            market_cap=5_000_000_000,
            current_price=100.0,
            technical_indicators={'rsi_14': 50.0},
            iv_rank=30.0,
        )
        assert _matches_preset(result, 'iv_crush') == _matches_preset(result, 'low_iv_entry')
