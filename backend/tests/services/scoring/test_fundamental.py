"""Tests for fundamental analysis v1 evaluate()."""
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


class TestFundamentalEvaluatePreGates:
    def test_market_cap_too_low_fails(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(market_cap=100_000_000),  # $100M < $500M min
        )
        assert result.reason == "market_cap_ok_failed"
        assert result.score_pct is None

    def test_market_cap_unknown_fails(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(market_cap=None),
        )
        assert result.reason == "market_cap_ok_unknown"

    def test_price_too_high_fails(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(current_price=600.0),  # $600 > $500 max
        )
        assert result.reason == "price_ok_failed"

    def test_price_unknown_fails(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(current_price=None),
        )
        assert result.reason == "price_ok_unknown"


class TestFundamentalEvaluateTriState:
    def test_all_known_all_pass(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(
                revenue_growth=0.55,
                earnings_growth=0.55,
                profit_margins=0.25,
                debt_to_equity=40,
                current_ratio=2.5,
                roe=0.25,
            ),
            _stock_info(),
        )
        assert result.criteria['revenue_growth_ok'] == CriterionResult.PASS
        assert result.criteria['earnings_growth_ok'] == CriterionResult.PASS
        assert result.criteria['debt_ok'] == CriterionResult.PASS
        assert result.criteria['liquidity_ok'] == CriterionResult.PASS
        assert result.criteria['sector_ok'] == CriterionResult.PASS
        assert result.coverage.pass_count == 5
        assert result.coverage.known_count == 5
        assert result.passes_gate(GATE_CONFIGS["fundamental"]) is True

    def test_revenue_growth_none_is_unknown(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(revenue_growth=None),
            _stock_info(),
        )
        assert result.criteria['revenue_growth_ok'] == CriterionResult.UNKNOWN

    def test_debt_none_is_unknown(self):
        """D5: debt_to_equity None should be UNKNOWN, not PASS (old behavior)."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(debt_to_equity=None),
            _stock_info(),
        )
        assert result.criteria['debt_ok'] == CriterionResult.UNKNOWN

    def test_current_ratio_none_is_unknown(self):
        """D5: current_ratio None should be UNKNOWN, not PASS (old behavior)."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(current_ratio=None),
            _stock_info(),
        )
        assert result.criteria['liquidity_ok'] == CriterionResult.UNKNOWN

    def test_sector_none_is_unknown(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(),
            _stock_info(sector=None),
        )
        assert result.criteria['sector_ok'] == CriterionResult.UNKNOWN

    def test_earnings_fallback_to_margins(self):
        """If earnings_growth is None but profit_margins > 0, earnings = PASS."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(earnings_growth=None, profit_margins=0.15),
            _stock_info(),
        )
        assert result.criteria['earnings_growth_ok'] == CriterionResult.PASS

    def test_earnings_fully_unknown(self):
        """If both earnings_growth and profit_margins are None, earnings = UNKNOWN."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(earnings_growth=None, profit_margins=None),
            _stock_info(),
        )
        assert result.criteria['earnings_growth_ok'] == CriterionResult.UNKNOWN


class TestFundamentalEvaluateGate:
    def test_gate_passes_4_of_5_with_5_known(self):
        """Gate requires min_pass=4, min_known=4. 4 pass, 5 known → passes."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(
                revenue_growth=0.25,    # PASS (>0.20)
                earnings_growth=0.20,   # PASS (>0.15)
                debt_to_equity=100,     # PASS (<150)
                current_ratio=1.8,      # PASS (>1.2)
            ),
            _stock_info(sector='FinancialServices'),  # FAIL (not in growth list)
        )
        assert result.coverage.known_count == 5
        assert result.coverage.pass_count == 4
        assert result.passes_gate(GATE_CONFIGS["fundamental"]) is True

    def test_gate_fails_3_of_5_pass(self):
        """Gate requires min_pass=4. 3 pass is not enough."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(
                revenue_growth=0.25,    # PASS (>0.20)
                earnings_growth=0.20,   # PASS (>0.15)
                debt_to_equity=100,     # PASS (<150)
                current_ratio=1.0,      # FAIL (<1.2)
            ),
            _stock_info(sector='FinancialServices'),  # FAIL (not in growth list)
        )
        assert result.coverage.known_count == 5
        assert result.coverage.pass_count == 3
        assert result.passes_gate(GATE_CONFIGS["fundamental"]) is False

    def test_gate_fails_3_pass_but_only_3_known(self):
        """3 pass but only 3 known (2 UNKNOWN) → fails coverage threshold."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(
                revenue_growth=0.25,     # PASS
                earnings_growth=0.20,    # PASS
                debt_to_equity=None,     # UNKNOWN
                current_ratio=None,      # UNKNOWN
            ),
            _stock_info(),               # sector PASS
        )
        assert result.coverage.pass_count == 3
        assert result.coverage.known_count == 3
        # Gate requires ≥4 known
        assert result.passes_gate(GATE_CONFIGS["fundamental"]) is False


class TestFundamentalEvaluateScore:
    def test_perfect_score(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(
                revenue_growth=0.55,
                earnings_growth=0.55,
                profit_margins=0.25,
                debt_to_equity=40,
                current_ratio=2.5,
                roe=0.25,
            ),
            _stock_info(),
        )
        assert result.score_pct == 100.0
        assert result.score_points == 100.0

    def test_zero_score(self):
        result = FundamentalAnalysis.evaluate(
            _fundamentals(
                revenue_growth=0.05,
                earnings_growth=0.05,
                profit_margins=0.05,
                debt_to_equity=200,
                current_ratio=1.0,
                roe=0.05,
            ),
            _stock_info(),
        )
        assert result.score_pct == 0.0
        assert result.score_points == 0.0

    def test_partial_data_coverage_adjustment(self):
        """With 2 of 5 buckets unknown, coverage penalty should apply."""
        result = FundamentalAnalysis.evaluate(
            _fundamentals(
                revenue_growth=0.55,     # 30 pts earned, 30 known
                earnings_growth=0.55,    # 30 pts earned, 30 known
                profit_margins=0.25,     # 20 pts earned, 20 known
                debt_to_equity=None,     # UNKNOWN — 0 known
                current_ratio=None,      # UNKNOWN — 0 known (balance sheet bucket skipped)
                roe=None,                # UNKNOWN — 0 known
            ),
            _stock_info(),
        )
        # points_earned=80, points_known_max=80, points_total_max=100
        # pct_raw = 100 * (80/80) = 100
        # coverage = 80/100 = 0.8
        # pct = 100 * (0.85 + 0.15*0.8) = 100 * 0.97 = 97.0
        assert result.score_pct == pytest.approx(97.0)
        assert result.score_points == pytest.approx(97.0)
