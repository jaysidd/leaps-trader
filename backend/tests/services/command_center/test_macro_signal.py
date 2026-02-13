"""
Tests for Macro Signal Service - MRI Calculation and Divergence Detection
"""
import pytest
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.command_center.polymarket import (
    PolymarketService,
    MacroConfig,
    _macro_config,
)
from app.services.command_center.macro_signal import (
    MacroSignalService,
    DivergencePersistence,
    CATEGORY_SCALING,
    MRI_REGIME_THRESHOLDS,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def macro_config():
    """Default macro configuration for tests."""
    return MacroConfig()


@pytest.fixture
def polymarket_service():
    """PolymarketService instance for tests."""
    return PolymarketService()


@pytest.fixture
def macro_signal_service():
    """MacroSignalService instance for tests."""
    return MacroSignalService()


@pytest.fixture
def sample_market_high_quality():
    """Sample high-quality market data."""
    return {
        'id': 'market_1',
        'title': 'Will there be a US recession in 2025?',
        'question': 'Will there be a US recession in 2025?',
        'liquidity': 150000,
        'volume': 500000,
        'endDate': (datetime.now(timezone.utc) + timedelta(days=60)).isoformat(),
        'primary_odds': 35.0,
        'category': 'recession',
    }


@pytest.fixture
def sample_market_low_quality():
    """Sample low-quality market data."""
    return {
        'id': 'market_2',
        'title': 'Some obscure prediction',
        'question': 'Some obscure prediction',
        'liquidity': 5000,
        'volume': 1000,
        'endDate': (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        'primary_odds': 50.0,
        'category': 'other',
    }


@pytest.fixture
def sample_markets_for_aggregation():
    """Sample markets for category aggregation tests."""
    return [
        {
            'id': 'market_1',
            'title': 'Recession probability market 1',
            'liquidity': 100000,
            'volume': 200000,
            'quality_score': 0.8,
            'implied_probability': 30,
            'category': 'recession',
        },
        {
            'id': 'market_2',
            'title': 'Recession probability market 2',
            'liquidity': 50000,
            'volume': 100000,
            'quality_score': 0.7,
            'implied_probability': 40,
            'category': 'recession',
        },
        {
            'id': 'market_3',
            'title': 'Recession probability market 3',
            'liquidity': 200000,
            'volume': 300000,
            'quality_score': 0.9,
            'implied_probability': 35,
            'category': 'recession',
        },
    ]


# =============================================================================
# MARKET QUALITY SCORING TESTS
# =============================================================================

class TestMarketQualityScoring:
    """Tests for market quality score calculation."""

    def test_high_liquidity_market_scores_high(self, polymarket_service, sample_market_high_quality):
        """High liquidity markets should score higher."""
        score = polymarket_service.calculate_market_quality_score(sample_market_high_quality)
        assert score >= 0.7, f"High quality market should score >= 0.7, got {score}"

    def test_low_liquidity_market_scores_low(self, polymarket_service, sample_market_low_quality):
        """Low liquidity markets should score lower."""
        score = polymarket_service.calculate_market_quality_score(sample_market_low_quality)
        assert score < 0.5, f"Low quality market should score < 0.5, got {score}"

    def test_quality_score_range(self, polymarket_service):
        """Quality score should always be between 0 and 1."""
        test_markets = [
            {'liquidity': 0, 'volume': 0},
            {'liquidity': 1000000, 'volume': 10000000, 'endDate': (datetime.now(timezone.utc) + timedelta(days=100)).isoformat()},
            {'liquidity': 50000, 'volume': 50000, 'question': 'Will X happen by 2026?'},
        ]

        for market in test_markets:
            score = polymarket_service.calculate_market_quality_score(market)
            assert 0 <= score <= 1, f"Score {score} out of range for market {market}"

    def test_expiry_decay_curve(self, polymarket_service, macro_config):
        """Time to expiry should follow decay curve, not hard cliffs."""
        base_market = {'liquidity': 100000, 'volume': 50000, 'question': 'Will X happen?'}

        # Test different expiry times
        scores = []
        for days in [35, 30, 20, 14, 10, 7, 5, 3, 1]:
            market = {
                **base_market,
                'endDate': (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            }
            score = polymarket_service.calculate_market_quality_score(market, macro_config)
            scores.append((days, score))

        # Verify decay is monotonic (longer expiry = higher score)
        for i in range(len(scores) - 1):
            days_curr, score_curr = scores[i]
            days_next, score_next = scores[i + 1]
            assert score_curr >= score_next, f"Score should decay: {days_curr}d={score_curr} should be >= {days_next}d={score_next}"

    def test_days_to_resolution_computation(self, polymarket_service):
        """Test days to resolution handles various date formats."""
        # Future date
        future_market = {
            'endDate': (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        }
        days = polymarket_service._compute_days_to_resolution(future_market)
        assert 29 <= days <= 31, f"Expected ~30 days, got {days}"

        # Past date
        past_market = {
            'endDate': (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        }
        days = polymarket_service._compute_days_to_resolution(past_market)
        assert days == 0, f"Past date should return 0, got {days}"

        # No date
        no_date_market = {}
        days = polymarket_service._compute_days_to_resolution(no_date_market)
        assert days == 0, f"No date should return 0, got {days}"


# =============================================================================
# CATEGORY AGGREGATION TESTS
# =============================================================================

class TestCategoryAggregation:
    """Tests for category probability aggregation."""

    @pytest.mark.asyncio
    async def test_log_normalized_liquidity_prevents_whale_dominance(self, polymarket_service):
        """One mega-liquidity market shouldn't overwhelm aggregation."""
        # Mock get_markets_by_category to return controlled test data
        with patch.object(polymarket_service, 'get_markets_by_category') as mock_markets:
            mock_markets.return_value = [
                {'id': 'whale', 'implied_probability': 30, 'liquidity': 10_000_000, 'quality_score': 0.7},
                {'id': 'normal1', 'implied_probability': 70, 'liquidity': 100_000, 'quality_score': 0.8},
                {'id': 'normal2', 'implied_probability': 65, 'liquidity': 80_000, 'quality_score': 0.75},
            ]

            result = await polymarket_service.get_category_aggregate('recession')

            # Without log normalization, whale would dominate (prob ~30)
            # With log normalization, result should be closer to consensus (prob ~50-60)
            prob = result['aggregate_probability']
            assert 45 < prob < 65, f"Log normalization should prevent whale dominance, got {prob}"

    @pytest.mark.asyncio
    async def test_dispersion_stats_computed(self, polymarket_service):
        """Category aggregate should include dispersion stats."""
        with patch.object(polymarket_service, 'get_markets_by_category') as mock_markets:
            mock_markets.return_value = [
                {'id': 'm1', 'implied_probability': 30, 'liquidity': 100000, 'quality_score': 0.8},
                {'id': 'm2', 'implied_probability': 50, 'liquidity': 100000, 'quality_score': 0.8},
                {'id': 'm3', 'implied_probability': 70, 'liquidity': 100000, 'quality_score': 0.8},
            ]

            result = await polymarket_service.get_category_aggregate('recession')

            assert 'dispersion' in result
            assert result['dispersion'] is not None
            assert 'min' in result['dispersion']
            assert 'max' in result['dispersion']
            assert 'stddev' in result['dispersion']
            assert result['dispersion']['min'] == 30
            assert result['dispersion']['max'] == 70

    @pytest.mark.asyncio
    async def test_key_market_is_top_contributor(self, polymarket_service):
        """key_market should be highest weight, not first in list."""
        with patch.object(polymarket_service, 'get_markets_by_category') as mock_markets:
            mock_markets.return_value = [
                {'id': 'a', 'title': 'Market A', 'implied_probability': 30, 'liquidity': 50_000, 'quality_score': 0.5},
                {'id': 'b', 'title': 'Market B', 'implied_probability': 40, 'liquidity': 200_000, 'quality_score': 0.9},  # Top
                {'id': 'c', 'title': 'Market C', 'implied_probability': 35, 'liquidity': 100_000, 'quality_score': 0.7},
            ]

            result = await polymarket_service.get_category_aggregate('recession')

            assert result['key_market'] is not None
            assert result['key_market']['id'] == 'b', f"Expected 'b' as key market, got {result['key_market']['id']}"

    @pytest.mark.asyncio
    async def test_confidence_numeric_not_string(self, polymarket_service):
        """Category confidence should be numeric (0-100), not string label."""
        with patch.object(polymarket_service, 'get_markets_by_category') as mock_markets:
            mock_markets.return_value = [
                {'id': 'm1', 'implied_probability': 50, 'liquidity': 100000, 'quality_score': 0.8},
            ]

            result = await polymarket_service.get_category_aggregate('recession')

            assert isinstance(result['confidence_score'], (int, float))
            assert 0 <= result['confidence_score'] <= 100
            # Label is separate field
            assert result['confidence_label'] in ['none', 'low', 'medium', 'high']

    @pytest.mark.asyncio
    async def test_empty_category_returns_none_probability(self, polymarket_service):
        """Empty category should return None for probability."""
        with patch.object(polymarket_service, 'get_markets_by_category') as mock_markets:
            mock_markets.return_value = []

            result = await polymarket_service.get_category_aggregate('nonexistent')

            assert result['aggregate_probability'] is None
            assert result['confidence_score'] == 0
            assert result['markets_used'] == 0

    @pytest.mark.asyncio
    async def test_low_quality_markets_excluded(self, polymarket_service):
        """Low quality markets should not impact aggregation."""
        with patch.object(polymarket_service, 'get_markets_by_category') as mock_markets:
            mock_markets.return_value = [
                {'id': 'm1', 'implied_probability': 50, 'liquidity': 100000, 'quality_score': 0.8},
                {'id': 'm2', 'implied_probability': 90, 'liquidity': 5000, 'quality_score': 0.3},  # Should be excluded
            ]

            result = await polymarket_service.get_category_aggregate('recession')

            # Only 1 market should be included (the one with quality_score >= 0.5)
            assert result['markets_used'] == 1
            # Result should be close to 50, not skewed by the 90% low-quality market
            assert 45 <= result['aggregate_probability'] <= 55


# =============================================================================
# MRI CALCULATION TESTS
# =============================================================================

class TestMRICalculation:
    """Tests for MRI calculation logic."""

    def test_risk_conversion_inversion(self, macro_signal_service):
        """Test that fed_policy and crypto categories are inverted."""
        # Fed policy: high rate cut odds = bullish = low risk
        fed_score = macro_signal_service._convert_to_risk_score(80, 'fed_policy')
        assert fed_score < 50, f"High fed_policy odds should result in low risk score, got {fed_score}"

        # Recession: high recession odds = bearish = high risk
        recession_score = macro_signal_service._convert_to_risk_score(80, 'recession')
        assert recession_score > 50, f"High recession odds should result in high risk score, got {recession_score}"

    def test_risk_conversion_scaling(self, macro_signal_service):
        """Test per-category scaling parameters."""
        # Elections should be dampened (alpha=0.8, beta=10)
        elections_score = macro_signal_service._convert_to_risk_score(50, 'elections')
        expected = 0.8 * 50 + 10  # = 50
        assert abs(elections_score - expected) < 1, f"Elections scaling incorrect: {elections_score} vs {expected}"

        # Crypto should be dampened AND inverted
        crypto_score = macro_signal_service._convert_to_risk_score(80, 'crypto')
        # Inverted: 100 - 80 = 20, then scaled: 0.5 * 20 = 10
        expected = 0.5 * (100 - 80)  # = 10
        assert abs(crypto_score - expected) < 1, f"Crypto scaling incorrect: {crypto_score} vs {expected}"

    def test_regime_classification(self, macro_signal_service):
        """Test regime classification based on MRI score."""
        assert macro_signal_service._get_regime(20) == 'risk_on'
        assert macro_signal_service._get_regime(33) == 'risk_on'
        assert macro_signal_service._get_regime(50) == 'transition'
        assert macro_signal_service._get_regime(66) == 'transition'
        assert macro_signal_service._get_regime(80) == 'risk_off'
        assert macro_signal_service._get_regime(100) == 'risk_off'

    def test_shock_detection(self, macro_signal_service):
        """Fast MRI changes should set shock_flag."""
        # History averaging 45, current is 62 (+17 points)
        history_1h = [45, 46, 47, 44, 45]
        current = 62

        assert macro_signal_service._detect_shock(current, history_1h) == True

        # Small change should not trigger shock
        current_small = 48
        assert macro_signal_service._detect_shock(current_small, history_1h) == False

    def test_mri_calculation_deterministic(self, macro_signal_service):
        """Fixed inputs should produce consistent MRI output."""
        # Test conversion for known inputs
        # Fed policy: 65% rate cut odds -> inverted -> 35 risk
        fed_risk = macro_signal_service._convert_to_risk_score(65, 'fed_policy')
        assert abs(fed_risk - 35) < 1

        # Recession: 25% recession odds -> 25 risk
        recession_risk = macro_signal_service._convert_to_risk_score(25, 'recession')
        assert abs(recession_risk - 25) < 1


# =============================================================================
# DIVERGENCE DETECTION TESTS
# =============================================================================

class TestDivergenceDetection:
    """Tests for divergence detection logic."""

    def test_divergence_requires_persistence(self):
        """Single divergence detection should NOT trigger alert."""
        persistence = DivergencePersistence()
        key = "recession:SPY:+"

        # First detection
        persistence.record_detection(key)
        assert persistence.check_persistence(key, min_checks=2) == False

        # Second detection (within window)
        persistence.record_detection(key)
        assert persistence.check_persistence(key, min_checks=2) == True

    def test_persistence_window_expires(self):
        """Detections outside window should not count."""
        persistence = DivergencePersistence()
        key = "recession:SPY:+"

        # Record old detection (simulate by manipulating internal state)
        old_time = datetime.utcnow() - timedelta(hours=2)
        persistence._detections[key] = [old_time]

        # New detection
        persistence.record_detection(key)

        # Old detection should be cleaned up, only 1 recent
        assert persistence.check_persistence(key, min_checks=2, window_minutes=30) == False

    def test_persistence_clear_old_detections(self):
        """Clear old detections should remove stale entries."""
        persistence = DivergencePersistence()

        # Add some detections
        persistence._detections['key1'] = [datetime.utcnow()]
        persistence._detections['key2'] = [datetime.utcnow() - timedelta(hours=5)]

        # Clear old (>2 hours)
        persistence.clear_old_detections(max_age_hours=2)

        assert 'key1' in persistence._detections
        assert 'key2' not in persistence._detections


# =============================================================================
# STALENESS HANDLING TESTS
# =============================================================================

class TestStalenessHandling:
    """Tests for data staleness detection and alert suppression."""

    def test_staleness_suppresses_alerts(self, macro_signal_service):
        """Stale data should suppress alert firing."""
        # Set last API success to 45 minutes ago
        macro_signal_service._last_api_success = datetime.utcnow() - timedelta(minutes=45)

        staleness = macro_signal_service._check_staleness()

        assert staleness['stale'] == True
        assert staleness['suppress_alerts'] == True
        assert staleness['stale_minutes'] > 40

    def test_fresh_data_allows_alerts(self, macro_signal_service):
        """Fresh data should allow alerts."""
        # Set last API success to 5 minutes ago
        macro_signal_service._last_api_success = datetime.utcnow() - timedelta(minutes=5)

        staleness = macro_signal_service._check_staleness()

        assert staleness['stale'] == False
        assert staleness['suppress_alerts'] == False

    def test_no_api_success_is_stale(self, macro_signal_service):
        """No API success recorded should be treated as stale."""
        macro_signal_service._last_api_success = None

        staleness = macro_signal_service._check_staleness()

        assert staleness['stale'] == True
        assert staleness['suppress_alerts'] == True


# =============================================================================
# CONFIDENCE CALCULATION TESTS
# =============================================================================

class TestConfidenceCalculation:
    """Tests for confidence score calculation."""

    def test_confidence_increases_with_markets(self, polymarket_service):
        """More markets should increase confidence."""
        # 1 market
        conf_1 = polymarket_service._calculate_category_confidence(
            markets_used=1, total_liquidity=100000, dispersion_stddev=5
        )

        # 5 markets
        conf_5 = polymarket_service._calculate_category_confidence(
            markets_used=5, total_liquidity=100000, dispersion_stddev=5
        )

        assert conf_5 > conf_1, f"More markets should increase confidence: {conf_5} vs {conf_1}"

    def test_confidence_increases_with_liquidity(self, polymarket_service):
        """More liquidity should increase confidence."""
        # Low liquidity
        conf_low = polymarket_service._calculate_category_confidence(
            markets_used=3, total_liquidity=10000, dispersion_stddev=5
        )

        # High liquidity
        conf_high = polymarket_service._calculate_category_confidence(
            markets_used=3, total_liquidity=500000, dispersion_stddev=5
        )

        assert conf_high > conf_low, f"More liquidity should increase confidence: {conf_high} vs {conf_low}"

    def test_confidence_decreases_with_dispersion(self, polymarket_service):
        """Higher dispersion (disagreement) should decrease confidence."""
        # Low dispersion (agreement)
        conf_agree = polymarket_service._calculate_category_confidence(
            markets_used=3, total_liquidity=100000, dispersion_stddev=3
        )

        # High dispersion (disagreement)
        conf_disagree = polymarket_service._calculate_category_confidence(
            markets_used=3, total_liquidity=100000, dispersion_stddev=20
        )

        assert conf_agree > conf_disagree, f"Agreement should increase confidence: {conf_agree} vs {conf_disagree}"


# =============================================================================
# INTEGRATION TESTS (with mocking)
# =============================================================================

class TestMRIIntegration:
    """Integration tests for full MRI calculation flow."""

    @pytest.mark.asyncio
    async def test_mri_calculation_returns_all_fields(self, macro_signal_service):
        """MRI calculation should return all required fields."""
        # Mock the polymarket service
        with patch.object(macro_signal_service._polymarket, 'get_all_category_aggregates') as mock_agg:
            mock_agg.return_value = {
                'fed_policy': {
                    'aggregate_probability': 60,
                    'confidence_score': 70,
                    'markets_used': 3,
                    'total_liquidity': 200000,
                    'key_market': {'id': 'fed1', 'title': 'Fed Rate Cut'},
                },
                'recession': {
                    'aggregate_probability': 30,
                    'confidence_score': 65,
                    'markets_used': 2,
                    'total_liquidity': 150000,
                    'key_market': {'id': 'rec1', 'title': 'US Recession'},
                },
                'elections': {
                    'aggregate_probability': 50,
                    'confidence_score': 60,
                    'markets_used': 4,
                    'total_liquidity': 300000,
                    'key_market': {'id': 'elec1', 'title': 'Election'},
                },
                'trade': {
                    'aggregate_probability': 40,
                    'confidence_score': 55,
                    'markets_used': 2,
                    'total_liquidity': 100000,
                    'key_market': {'id': 'trade1', 'title': 'Trade War'},
                },
                'crypto': {
                    'aggregate_probability': 70,
                    'confidence_score': 75,
                    'markets_used': 3,
                    'total_liquidity': 250000,
                    'key_market': {'id': 'crypto1', 'title': 'Bitcoin'},
                },
            }

            result = await macro_signal_service.calculate_mri()

            # Check required fields
            assert 'mri_score' in result
            assert 'regime' in result
            assert 'regime_label' in result
            assert 'confidence_score' in result
            assert 'confidence_label' in result
            assert 'shock_flag' in result
            assert 'drivers' in result
            assert 'components' in result
            assert 'data_stale' in result

            # Check score is in valid range
            assert 0 <= result['mri_score'] <= 100

            # Check regime is valid
            assert result['regime'] in ['risk_on', 'transition', 'risk_off']

            # Check drivers are present
            assert len(result['drivers']) <= 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
