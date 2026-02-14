"""Tests for skip_sector_filter in fundamental evaluate()."""
import pytest
from backend.app.services.analysis.fundamental import FundamentalAnalysis
from backend.app.services.scoring.types import CriterionResult, GATE_CONFIGS


def _stock_info(**overrides):
    base = {
        'name': 'Test Corp',
        'sector': 'Technology',
        'market_cap': 5_000_000_000,
        'current_price': 100.0,
        'exchange': 'NASDAQ',
    }
    base.update(overrides)
    return base


def _fundamentals(**overrides):
    base = {
        'revenue_growth': 0.30,
        'earnings_growth': 0.25,
        'profit_margins': 0.15,
        'debt_to_equity': 80,
        'current_ratio': 1.8,
        'roe': 0.18,
    }
    base.update(overrides)
    return base


class TestFundamentalSectorBypass:
    """Tests for skip_sector_filter custom criteria."""

    def test_non_growth_sector_fails_without_bypass(self):
        """Utilities is not in GROWTH_SECTORS and should FAIL normally."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(sector='Utilities'),
        )
        assert result.criteria['sector_ok'] == CriterionResult.FAIL

    def test_non_growth_sector_passes_with_bypass(self):
        """skip_sector_filter=True should make sector_ok=PASS for any sector."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(sector='Financial Services'),
            custom_criteria={'skip_sector_filter': True},
        )
        assert result.criteria['sector_ok'] == CriterionResult.PASS

    def test_growth_sector_still_passes_with_bypass(self):
        """skip_sector_filter should not break growth-sector stocks."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(sector='Technology'),
            custom_criteria={'skip_sector_filter': True},
        )
        assert result.criteria['sector_ok'] == CriterionResult.PASS

    def test_no_sector_data_unknown_without_bypass(self):
        """sector=None → UNKNOWN when bypass is absent."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(sector=None),
        )
        assert result.criteria['sector_ok'] == CriterionResult.UNKNOWN

    def test_no_sector_data_passes_with_bypass(self):
        """skip_sector_filter=True should PASS even when sector is None."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(sector=None),
            custom_criteria={'skip_sector_filter': True},
        )
        assert result.criteria['sector_ok'] == CriterionResult.PASS

    def test_bypass_absent_defaults_to_existing_behavior(self):
        """When skip_sector_filter is not in custom_criteria, existing behavior."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(sector='Real Estate'),
            custom_criteria={'market_cap_min': 500_000_000},  # No skip_sector_filter
        )
        assert result.criteria['sector_ok'] == CriterionResult.FAIL

    def test_bypass_false_keeps_existing_behavior(self):
        """skip_sector_filter=False is same as absent."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(sector='Utilities'),
            custom_criteria={'skip_sector_filter': False},
        )
        assert result.criteria['sector_ok'] == CriterionResult.FAIL

    def test_bypass_with_gate_passes(self):
        """Full gate should pass for non-growth sector when bypass + other criteria pass."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(
                revenue_growth=0.35,
                earnings_growth=0.20,
                debt_to_equity=60,
                current_ratio=2.0,
            ),
            _stock_info(sector='Financial Services'),
            custom_criteria={'skip_sector_filter': True},
        )
        # All 5 criteria should pass
        assert result.criteria['sector_ok'] == CriterionResult.PASS
        assert result.criteria['revenue_growth_ok'] == CriterionResult.PASS
        assert result.criteria['earnings_growth_ok'] == CriterionResult.PASS
        assert result.criteria['debt_ok'] == CriterionResult.PASS
        assert result.criteria['liquidity_ok'] == CriterionResult.PASS
        assert result.passes_gate(GATE_CONFIGS["fundamental"])
