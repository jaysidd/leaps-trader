"""Tests for ScreeningEngine._check_valuation_filters()."""
import pytest
from backend.app.services.screening.engine import ScreeningEngine


def _fundamentals(**overrides):
    """Build a base fundamentals dict with common valuation fields."""
    base = {
        'trailing_pe': 20.0,
        'forward_pe': 18.0,
        'peg_ratio': 1.5,
        'price_to_book': 3.0,
        'price_to_sales': 5.0,
        'dividend_yield': 0.02,
        'roe': 0.15,
        'profit_margins': 0.12,
        'beta': 1.1,
    }
    base.update(overrides)
    return base


class TestValuationFiltersNone:
    """All filters pass when not set (None criteria)."""

    def test_no_criteria_passes(self):
        result = ScreeningEngine._check_valuation_filters(_fundamentals(), None)
        assert result is None

    def test_empty_criteria_passes(self):
        result = ScreeningEngine._check_valuation_filters(_fundamentals(), {})
        assert result is None


class TestPEFilters:
    def test_pe_max_blocks_high_pe(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(trailing_pe=30.0),
            {'pe_max': 15},
        )
        assert result is not None
        assert 'pe_max' in result

    def test_pe_max_passes_low_pe(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(trailing_pe=12.0),
            {'pe_max': 15},
        )
        assert result is None

    def test_pe_min_blocks_negative_earnings(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(trailing_pe=-5.0),
            {'pe_min': 0},
        )
        assert result is not None
        assert 'pe_min' in result

    def test_pe_none_skips_check(self):
        """P/E None → skip (negative-earnings stocks have no P/E)."""
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(trailing_pe=None),
            {'pe_max': 15, 'pe_min': 0},
        )
        assert result is None


class TestForwardPE:
    def test_forward_pe_max_blocks(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(forward_pe=40.0),
            {'forward_pe_max': 25},
        )
        assert result is not None
        assert 'forward_pe' in result

    def test_forward_pe_none_skips(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(forward_pe=None),
            {'forward_pe_max': 25},
        )
        assert result is None


class TestPEGFilter:
    def test_peg_max_blocks_high(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(peg_ratio=3.0),
            {'peg_max': 1.5},
        )
        assert result is not None
        assert 'peg_max' in result

    def test_peg_none_skips(self):
        """PEG None → skip (unreliable from Yahoo, 60-70% None)."""
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(peg_ratio=None),
            {'peg_max': 1.5},
        )
        assert result is None

    def test_peg_zero_skips(self):
        """PEG 0 → skip (invalid)."""
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(peg_ratio=0),
            {'peg_max': 1.5},
        )
        assert result is None

    def test_peg_passes_when_valid(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(peg_ratio=1.2),
            {'peg_max': 1.5},
        )
        assert result is None


class TestDividendYield:
    def test_min_fails_when_no_dividend(self):
        """Dividend yield None with min set → treat as 0 → FAIL."""
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(dividend_yield=None),
            {'dividend_yield_min': 0.025},
        )
        assert result is not None
        assert 'dividend_yield_min' in result

    def test_min_passes_when_yield_exceeds(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(dividend_yield=0.03),
            {'dividend_yield_min': 0.025},
        )
        assert result is None

    def test_max_blocks_high_yield(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(dividend_yield=0.08),
            {'dividend_yield_max': 0.06},
        )
        assert result is not None
        assert 'dividend_yield_max' in result

    def test_max_none_skips(self):
        """No dividend yield data + max set → skip (max only checks known values)."""
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(dividend_yield=None),
            {'dividend_yield_max': 0.06},
        )
        assert result is None


class TestPBFilter:
    def test_pb_max_blocks(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(price_to_book=5.0),
            {'pb_max': 1.5},
        )
        assert result is not None
        assert 'pb_max' in result

    def test_pb_none_skips(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(price_to_book=None),
            {'pb_max': 1.5},
        )
        assert result is None


class TestROEFilter:
    def test_roe_min_blocks(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(roe=0.08),
            {'roe_min': 0.12},
        )
        assert result is not None
        assert 'roe_min' in result

    def test_roe_none_skips(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(roe=None),
            {'roe_min': 0.12},
        )
        assert result is None


class TestProfitMarginFilter:
    def test_pm_min_blocks(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(profit_margins=0.05),
            {'profit_margin_min': 0.08},
        )
        assert result is not None
        assert 'profit_margin_min' in result


class TestBetaFilter:
    def test_beta_max_blocks(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(beta=1.5),
            {'beta_max': 1.2},
        )
        assert result is not None
        assert 'beta_max' in result

    def test_beta_min_blocks(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(beta=0.5),
            {'beta_min': 0.8},
        )
        assert result is not None
        assert 'beta_min' in result

    def test_beta_none_skips(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(beta=None),
            {'beta_max': 1.2, 'beta_min': 0.8},
        )
        assert result is None


class TestMultipleFilters:
    def test_multiple_pass(self):
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(trailing_pe=12.0, peg_ratio=1.0, dividend_yield=0.03),
            {'pe_max': 15, 'peg_max': 1.5, 'dividend_yield_min': 0.025},
        )
        assert result is None

    def test_first_failing_filter_returns_reason(self):
        """When multiple filters set, first failure is returned."""
        result = ScreeningEngine._check_valuation_filters(
            _fundamentals(trailing_pe=30.0, peg_ratio=3.0),
            {'pe_max': 15, 'peg_max': 1.5},
        )
        # P/E is checked first
        assert result is not None
        assert 'pe_max' in result
