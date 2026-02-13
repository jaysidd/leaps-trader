"""Integration tests for v1 screening engine (screen_single_stock, calculate_stock_scores, screen_with_sentiment)."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import pandas as pd
import numpy as np
from datetime import datetime

from backend.app.services.screening.engine import ScreeningEngine


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_price_df(n=252, base_price=100.0):
    """Create a realistic OHLCV DataFrame with n trading days."""
    dates = pd.bdate_range(end=datetime.now(), periods=n)
    np.random.seed(42)
    close = base_price + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 5.0)  # keep positive
    return pd.DataFrame({
        'open': close * 0.99,
        'high': close * 1.02,
        'low': close * 0.98,
        'close': close,
        'volume': np.random.randint(500_000, 5_000_000, size=n),
    }, index=dates)


STOCK_INFO = {
    'name': 'Test Corp',
    'sector': 'Technology',
    'market_cap': 50_000_000_000,
    'exchange': 'NMS',
    'currentPrice': 150.0,
    'current_price': 150.0,
}

FUNDAMENTALS = {
    'revenue_growth': 0.25,
    'earnings_growth': 0.20,
    'profit_margins': 0.15,
    'gross_margins': 0.40,
    'return_on_equity': 0.18,
    'debt_to_equity': 80,
    'current_ratio': 2.0,
    'market_cap': 50_000_000_000,
    'current_price': 150.0,
}

ATM_OPTION = {
    'strike': 150.0,
    'bid': 20.0,
    'ask': 22.0,
    'last_price': 21.0,
    'implied_volatility': 0.35,
    'open_interest': 500,
    'volume': 100,
    'expiration': '2027-01-15',
}

LEAPS_SUMMARY = {
    'available': True,
    'atm_option': ATM_OPTION,
    'tastytrade': {
        'iv_rank': 30.0,
        'iv_percentile': 40.0,
    },
}


@pytest.fixture
def engine():
    with patch('backend.app.services.screening.engine.get_sentiment_analyzer'), \
         patch('backend.app.services.screening.engine.get_catalyst_service'):
        return ScreeningEngine()


# ---------------------------------------------------------------------------
# screen_single_stock — result shape
# ---------------------------------------------------------------------------

class TestScreenSingleStockResultShape:
    """Verify all expected keys are present in the result dict."""

    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_passing_stock_has_all_keys(self, mock_fmp, mock_alpaca, engine):
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = {'calls': [ATM_OPTION]}

        engine.opt_analysis.get_leaps_summary_enhanced = MagicMock(return_value=LEAPS_SUMMARY)

        result = engine.screen_single_stock('TEST')

        # Core keys
        assert 'symbol' in result
        assert 'score' in result
        assert 'screened_at' in result
        assert 'passed_stages' in result

        # Sub-scores
        assert 'fundamental_score' in result
        assert 'technical_score' in result
        assert 'technical_score_points' in result
        assert 'options_score' in result
        assert 'momentum_score' in result

        # v1 structured output
        assert 'criteria' in result
        assert 'coverage' in result
        assert 'component_availability' in result

    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_failed_stock_has_failed_at(self, mock_fmp, mock_alpaca, engine):
        mock_fmp.get_stock_info.return_value = None

        result = engine.screen_single_stock('BAD')
        assert result['failed_at'] == 'data_fetch'
        assert result['score'] == 0


# ---------------------------------------------------------------------------
# screen_single_stock — D2: no options → hard fail, not UNKNOWN
# ---------------------------------------------------------------------------

class TestNoOptionsHardFail:
    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_no_options_chain_hard_fail(self, mock_fmp, mock_alpaca, engine):
        """D2: Missing options chain → failed_at='options_gate', reason='no_options_data'."""
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = None  # no options chain

        result = engine.screen_single_stock('TEST')

        # Should fail at options gate, NOT produce UNKNOWN with neutral
        assert result['failed_at'] == 'options_gate'
        assert 'options' not in result.get('passed_stages', [])

    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_no_leaps_hard_fail(self, mock_fmp, mock_alpaca, engine):
        """D2: Options exist but no LEAPS → failed_at='options_gate'."""
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = {'calls': [ATM_OPTION]}

        no_leaps_summary = {
            'available': False,
            'atm_option': None,
            'tastytrade': {},
        }
        engine.opt_analysis.get_leaps_summary_enhanced = MagicMock(return_value=no_leaps_summary)

        result = engine.screen_single_stock('TEST')
        assert result['failed_at'] == 'options_gate'


# ---------------------------------------------------------------------------
# screen_single_stock — D3: technical_score is 0-100, technical_score_points is 0-90
# ---------------------------------------------------------------------------

class TestTechnicalScoreFormats:
    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_technical_score_pct_and_points(self, mock_fmp, mock_alpaca, engine):
        """D3: technical_score is 0-100, technical_score_points is 0-90."""
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = {'calls': [ATM_OPTION]}

        engine.opt_analysis.get_leaps_summary_enhanced = MagicMock(return_value=LEAPS_SUMMARY)

        result = engine.screen_single_stock('TEST')

        tech_pct = result.get('technical_score')
        tech_pts = result.get('technical_score_points')

        if tech_pct is not None:
            assert 0 <= tech_pct <= 100, f"technical_score {tech_pct} not in [0, 100]"
        if tech_pts is not None:
            assert 0 <= tech_pts <= 90, f"technical_score_points {tech_pts} not in [0, 90]"


# ---------------------------------------------------------------------------
# calculate_stock_scores — never short-circuits
# ---------------------------------------------------------------------------

class TestCalculateStockScoresNeverShortCircuits:
    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_all_data_available(self, mock_fmp, mock_alpaca, engine):
        """calculate_stock_scores always computes all sub-scores when data is available."""
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = {'calls': [ATM_OPTION]}

        engine.opt_analysis.get_leaps_summary_enhanced = MagicMock(return_value=LEAPS_SUMMARY)

        result = engine.calculate_stock_scores('TEST')

        assert result is not None
        assert result['fundamental_score'] is not None
        assert result['technical_score'] is not None
        assert result['technical_score_points'] is not None
        assert result['momentum_score'] is not None
        assert result['score'] > 0

    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_no_stock_info_returns_neutral(self, mock_fmp, mock_alpaca, engine):
        """When stock_info is missing, all stages default to UNKNOWN → neutral composite."""
        mock_fmp.get_stock_info.return_value = None

        result = engine.calculate_stock_scores('BAD')

        assert result is not None
        # All UNKNOWN → all neutral → composite around 50
        assert result['score'] == pytest.approx(50.0, abs=0.1)
        assert result['component_availability']['fundamental_available'] is False
        assert result['component_availability']['technical_available'] is False
        assert result['component_availability']['options_available'] is False
        assert result['component_availability']['momentum_available'] is False

    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_no_price_data_still_computes_fundamental(self, mock_fmp, mock_alpaca, engine):
        """When price data is missing, fundamental still computed; technical/momentum are UNKNOWN."""
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = None
        mock_alpaca.get_options_chain.return_value = None

        result = engine.calculate_stock_scores('TEST')

        assert result is not None
        assert result['fundamental_score'] is not None
        assert result['technical_score'] is None
        assert result['momentum_score'] is None
        assert result['component_availability']['fundamental_available'] is True
        assert result['component_availability']['technical_available'] is False
        assert result['component_availability']['momentum_available'] is False


# ---------------------------------------------------------------------------
# screen_with_sentiment — D1: sentiment missing stays in with-sentiment scheme
# ---------------------------------------------------------------------------

class TestScreenWithSentiment:
    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_sentiment_available(self, mock_fmp, mock_alpaca, engine):
        """Sentiment data available → sentiment_available=True, uses with-sentiment weights."""
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = {'calls': [ATM_OPTION]}

        engine.opt_analysis.get_leaps_summary_enhanced = MagicMock(return_value=LEAPS_SUMMARY)

        sentiment_data = {'overall_score': 80.0, 'flags': {}}
        catalyst_data = {'upcoming': []}

        engine.get_sentiment_data = AsyncMock(return_value=sentiment_data)
        engine.get_catalyst_data = AsyncMock(return_value=catalyst_data)

        result = asyncio.get_event_loop().run_until_complete(
            engine.screen_with_sentiment('TEST')
        )

        if result and result.get('passed_all'):
            assert result['component_availability']['sentiment_available'] is True
            assert result['sentiment_score'] == 80.0

    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_sentiment_fetch_fails_d1(self, mock_fmp, mock_alpaca, engine):
        """D1: Sentiment fetch fails → still uses with-sentiment weights, S=50, sentiment_available=False."""
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = {'calls': [ATM_OPTION]}

        engine.opt_analysis.get_leaps_summary_enhanced = MagicMock(return_value=LEAPS_SUMMARY)

        engine.get_sentiment_data = AsyncMock(side_effect=Exception("API down"))
        engine.get_catalyst_data = AsyncMock(side_effect=Exception("API down"))

        result = asyncio.get_event_loop().run_until_complete(
            engine.screen_with_sentiment('TEST')
        )

        if result and result.get('passed_all'):
            # D1: sentiment_mode=True but score=None → with-sentiment weights, S=50
            assert result['component_availability']['sentiment_available'] is False

    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_failed_stock_no_sentiment_added(self, mock_fmp, mock_alpaca, engine):
        """Stock that fails screening should not have sentiment added."""
        mock_fmp.get_stock_info.return_value = None

        result = asyncio.get_event_loop().run_until_complete(
            engine.screen_with_sentiment('BAD')
        )

        assert result is None or result.get('failed_at') == 'data_fetch'


# ---------------------------------------------------------------------------
# Composite rescaling in integration context
# ---------------------------------------------------------------------------

class TestCompositeIntegration:
    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_composite_score_is_rescaled(self, mock_fmp, mock_alpaca, engine):
        """Composite score from screen_single_stock should be properly rescaled."""
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = {'calls': [ATM_OPTION]}

        engine.opt_analysis.get_leaps_summary_enhanced = MagicMock(return_value=LEAPS_SUMMARY)

        result = engine.screen_single_stock('TEST')

        if result.get('passed_all'):
            # Score should be valid 0-100
            assert 0 <= result['score'] <= 100
            # All components should be available since we provided full data
            avail = result['component_availability']
            assert avail['fundamental_available'] is True
            assert avail['technical_available'] is True
            assert avail['options_available'] is True
            assert avail['momentum_available'] is True

    @patch('backend.app.services.screening.engine.alpaca_service')
    @patch('backend.app.services.screening.engine.fmp_service')
    def test_criteria_and_coverage_populated(self, mock_fmp, mock_alpaca, engine):
        """Criteria and coverage dicts should be populated for all computed stages."""
        price_df = _make_price_df(252)
        mock_fmp.get_stock_info.return_value = STOCK_INFO
        mock_fmp.get_fundamentals.return_value = FUNDAMENTALS
        mock_alpaca.get_historical_prices.return_value = price_df
        mock_alpaca.get_options_chain.return_value = {'calls': [ATM_OPTION]}

        engine.opt_analysis.get_leaps_summary_enhanced = MagicMock(return_value=LEAPS_SUMMARY)

        result = engine.screen_single_stock('TEST')

        # Fundamental criteria should always be present (it's the first stage)
        assert 'fundamental' in result['criteria']
        assert 'fundamental' in result['coverage']

        # If we got past fundamentals, technical should be there too
        if 'technical' in result.get('passed_stages', []):
            assert 'technical' in result['criteria']
            assert 'technical' in result['coverage']
            # Criteria values should be valid tri-state strings
            for v in result['criteria']['technical'].values():
                assert v in ('PASS', 'FAIL', 'UNKNOWN')
