"""
Tests for LiquidityDataProvider and CatalystService.

Based on Unit Test Acceptance Criteria from Macro Intelligence spec.
All tests use mocked providers - no live network calls.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from freezegun import freeze_time

from app.services.data_providers.interfaces import DataQuality
from app.services.data_providers.fred.fred_service import FREDService, FRED_SERIES
from app.services.data_providers.liquidity_provider import LiquidityDataProviderImpl
from app.services.command_center.catalyst_service import CatalystService
from app.services.command_center.catalyst_config import CatalystConfig


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def mock_fred_service():
    """Mock FRED service with deterministic data."""
    service = MagicMock(spec=FREDService)
    return service


@pytest.fixture
def normal_fred_data():
    """Normal environment FRED data."""
    return {
        "WALCL": {"value": 7500000, "date": "2026-02-01", "change_1w": -0.3, "change_4w": -1.1, "is_stale": False},
        "RRPONTSYD": {"value": 600, "date": "2026-02-01", "change_1w": -5.0, "change_4w": -15.0, "is_stale": False},
        "WTREGEN": {"value": 700000, "date": "2026-02-01", "change_1w": 2.0, "change_4w": 8.0, "is_stale": False},
        "NFCI": {"value": -0.2, "date": "2026-02-01", "change_1w": -0.05, "change_4w": -0.1, "is_stale": False},
        "DGS10": {"value": 4.2, "date": "2026-02-01", "change_1w": 0.1, "change_4w": 0.2, "is_stale": False},
        "T10YIE": {"value": 2.1, "date": "2026-02-01", "change_1w": 0.05, "change_4w": 0.1, "is_stale": False},
    }


@pytest.fixture
def risk_off_fred_data():
    """Risk-off environment FRED data (contracting liquidity)."""
    return {
        "WALCL": {"value": 7000000, "date": "2026-02-01", "change_1w": -2.0, "change_4w": -5.0, "is_stale": False},
        "RRPONTSYD": {"value": 900, "date": "2026-02-01", "change_1w": 10.0, "change_4w": 25.0, "is_stale": False},
        "WTREGEN": {"value": 900000, "date": "2026-02-01", "change_1w": 15.0, "change_4w": 30.0, "is_stale": False},
        "NFCI": {"value": 0.5, "date": "2026-02-01", "change_1w": 0.2, "change_4w": 0.5, "is_stale": False},
        "DGS10": {"value": 5.5, "date": "2026-02-01", "change_1w": 0.3, "change_4w": 0.8, "is_stale": False},
        "T10YIE": {"value": 2.5, "date": "2026-02-01", "change_1w": 0.1, "change_4w": 0.2, "is_stale": False},
    }


@pytest.fixture
def missing_fields_fred_data():
    """FRED data with missing fields (completeness < 1.0)."""
    return {
        "WALCL": {"value": 7500000, "date": "2026-02-01", "change_1w": -0.3, "change_4w": -1.1, "is_stale": False},
        "RRPONTSYD": {"value": None, "date": None, "change_1w": None, "change_4w": None, "is_stale": True, "error": "Data unavailable"},
        "WTREGEN": {"value": 700000, "date": "2026-02-01", "change_1w": 2.0, "change_4w": 8.0, "is_stale": False},
        "NFCI": {"value": -0.2, "date": "2026-02-01", "change_1w": -0.05, "change_4w": -0.1, "is_stale": False},
        "DGS10": {"value": 4.2, "date": "2026-02-01", "change_1w": 0.1, "change_4w": 0.2, "is_stale": False},
        "T10YIE": {"value": None, "date": None, "change_1w": None, "change_4w": None, "is_stale": True, "error": "Data unavailable"},
    }


@pytest.fixture
def stale_fred_data():
    """FRED data with staleness flags."""
    return {
        "WALCL": {"value": 7500000, "date": "2026-01-20", "change_1w": -0.3, "change_4w": -1.1, "is_stale": True},
        "RRPONTSYD": {"value": 600, "date": "2026-01-20", "change_1w": -5.0, "change_4w": -15.0, "is_stale": True},
        "WTREGEN": {"value": 700000, "date": "2026-01-20", "change_1w": 2.0, "change_4w": 8.0, "is_stale": True},
        "NFCI": {"value": -0.2, "date": "2026-01-20", "change_1w": -0.05, "change_4w": -0.1, "is_stale": True},
        "DGS10": {"value": 4.2, "date": "2026-01-20", "change_1w": 0.1, "change_4w": 0.2, "is_stale": True},
        "T10YIE": {"value": 2.1, "date": "2026-01-20", "change_1w": 0.05, "change_4w": 0.1, "is_stale": True},
    }


# =============================================================================
# A) LIQUIDITY DATA PROVIDER TESTS
# =============================================================================

class TestLiquidityDataProviderAdapter:
    """Tests for LiquidityDataProvider (FRED)."""

    @pytest.mark.asyncio
    async def test_a1_correct_fred_series_requested(self, mock_fred_service, normal_fred_data):
        """A1. Correct FRED series are requested."""
        # Setup mock
        mock_fred_service.get_multiple_series = AsyncMock(return_value=normal_fred_data)

        provider = LiquidityDataProviderImpl(fred_service=mock_fred_service)
        await provider.get_current()

        # Verify get_multiple_series was called
        mock_fred_service.get_multiple_series.assert_called_once()

        # Check that all required series IDs were requested
        call_args = mock_fred_service.get_multiple_series.call_args
        requested_series = call_args[0][0]

        required_series = ["WALCL", "RRPONTSYD", "WTREGEN", "NFCI", "DGS10", "T10YIE"]
        for series_id in required_series:
            assert series_id in requested_series, f"Missing required series: {series_id}"

    @pytest.mark.asyncio
    async def test_a2_real_yield_calculation_correct(self, mock_fred_service):
        """A2. Real yield calculation: real_yield_10y = DGS10 - T10YIE."""
        # Setup specific values for testing
        test_data = {
            "WALCL": {"value": 7500000, "date": "2026-02-01", "change_1w": 0, "change_4w": 0, "is_stale": False},
            "RRPONTSYD": {"value": 600, "date": "2026-02-01", "change_1w": 0, "change_4w": 0, "is_stale": False},
            "WTREGEN": {"value": 700000, "date": "2026-02-01", "change_1w": 0, "change_4w": 0, "is_stale": False},
            "NFCI": {"value": 0, "date": "2026-02-01", "change_1w": 0, "change_4w": 0, "is_stale": False},
            "DGS10": {"value": 4.20, "date": "2026-02-01", "change_1w": 0.1, "change_4w": 0.2, "is_stale": False},
            "T10YIE": {"value": 2.10, "date": "2026-02-01", "change_1w": 0.05, "change_4w": 0.1, "is_stale": False},
        }
        mock_fred_service.get_multiple_series = AsyncMock(return_value=test_data)

        provider = LiquidityDataProviderImpl(fred_service=mock_fred_service)
        result = await provider.get_current()

        # Verify real_yield_10y = 4.20 - 2.10 = 2.10
        real_yield = result["metrics"]["real_yield_10y"]["value"]
        expected = 4.20 - 2.10

        assert abs(real_yield - expected) < 0.0001, f"Real yield {real_yield} != expected {expected}"

    @pytest.mark.asyncio
    async def test_a3_missing_series_handling(self, mock_fred_service, missing_fields_fred_data):
        """A3. Missing series handling - no exceptions, reduced completeness."""
        mock_fred_service.get_multiple_series = AsyncMock(return_value=missing_fields_fred_data)

        provider = LiquidityDataProviderImpl(fred_service=mock_fred_service)

        # Should not throw
        result = await provider.get_current()

        # Verify quality.completeness < 1.0
        assert result["quality"]["completeness"] < 1.0

        # Verify confidence is reduced
        assert result["quality"]["confidence_score"] < 100


# =============================================================================
# B) LIQUIDITY SCORING TESTS (CatalystService)
# =============================================================================

class TestLiquidityScoring:
    """Tests for liquidity score computation in CatalystService."""

    def test_b1_score_clamps_to_0_100(self):
        """B1. Score clamps to 0-100 for extreme inputs."""
        config = CatalystConfig()
        service = CatalystService(config=config)

        # Test extreme bullish inputs (should push score below 0 before clamping)
        extreme_bullish_metrics = {
            "fed_balance_sheet": {"value": 15e12, "available": True},  # Way above baseline
            "rrp": {"value": 0, "available": True},  # Minimal drain
            "tga": {"value": 0, "available": True},  # Minimal drain
            "fci": {"value": -2.0, "available": True},  # Very loose conditions
            "real_yield_10y": {"value": -1.0, "available": True},  # Negative real yields
        }

        result = service._compute_liquidity_score(extreme_bullish_metrics)
        assert 0 <= result["score"] <= 100, f"Score {result['score']} not in [0, 100]"

        # Test extreme bearish inputs (should push score above 100 before clamping)
        extreme_bearish_metrics = {
            "fed_balance_sheet": {"value": 3e12, "available": True},  # Way below baseline
            "rrp": {"value": 2e12, "available": True},  # Massive drain
            "tga": {"value": 1.5e12, "available": True},  # Massive drain
            "fci": {"value": 2.0, "available": True},  # Very tight conditions
            "real_yield_10y": {"value": 4.0, "available": True},  # Very high real yields
        }

        result = service._compute_liquidity_score(extreme_bearish_metrics)
        assert 0 <= result["score"] <= 100, f"Score {result['score']} not in [0, 100]"

    def test_b2_drivers_list_contains_top_contributors(self):
        """B2. Drivers list contains top contributors with name, value, contribution."""
        config = CatalystConfig()
        service = CatalystService(config=config)

        metrics = {
            "fed_balance_sheet": {"value": 7.5e12, "available": True},
            "rrp": {"value": 500e9, "available": True},
            "tga": {"value": 500e9, "available": True},
            "fci": {"value": 0.0, "available": True},
            "real_yield_10y": {"value": 1.5, "available": True},
        }

        result = service._compute_liquidity_score(metrics)

        # Verify drivers exist and have required fields
        assert "drivers" in result
        assert len(result["drivers"]) <= 3  # Top 3

        for driver in result["drivers"]:
            assert "name" in driver, "Driver missing 'name'"
            assert "value" in driver, "Driver missing 'value'"
            assert "contribution" in driver, "Driver missing 'contribution'"

    def test_b3_confidence_decreases_with_missing_inputs(self):
        """B3. Confidence score decreases with missing inputs."""
        config = CatalystConfig()
        service = CatalystService(config=config)

        # Full data
        full_metrics = {
            "fed_balance_sheet": {"value": 7.5e12, "available": True},
            "rrp": {"value": 500e9, "available": True},
            "tga": {"value": 500e9, "available": True},
            "fci": {"value": 0.0, "available": True},
            "real_yield_10y": {"value": 1.5, "available": True},
        }

        # Partial data (2 metrics missing)
        partial_metrics = {
            "fed_balance_sheet": {"value": 7.5e12, "available": True},
            "rrp": {"value": None, "available": False},
            "tga": {"value": 500e9, "available": True},
            "fci": {"value": None, "available": False},
            "real_yield_10y": {"value": 1.5, "available": True},
        }

        full_result = service._compute_liquidity_score(full_metrics)
        partial_result = service._compute_liquidity_score(partial_metrics)

        # Partial should have strictly lower confidence
        assert partial_result["confidence"] < full_result["confidence"], \
            f"Partial confidence ({partial_result['confidence']}) should be less than full ({full_result['confidence']})"


# =============================================================================
# G) STALENESS BEHAVIOR TESTS
# =============================================================================

class TestStalenessBehavior:
    """Tests for staleness handling."""

    @pytest.mark.asyncio
    async def test_g2_stale_score_returned_but_marked(self, mock_fred_service, stale_fred_data):
        """G2. Stale score still returned but marked with data_stale=True."""
        mock_fred_service.get_multiple_series = AsyncMock(return_value=stale_fred_data)

        provider = LiquidityDataProviderImpl(fred_service=mock_fred_service)
        result = await provider.get_current()

        # Should return data (not None)
        assert result is not None

        # Should be marked as stale
        assert result["quality"]["is_stale"] == True

        # Confidence should be capped at 40 for stale data
        assert result["quality"]["confidence_score"] <= 40


# =============================================================================
# I) API PAYLOAD CONTRACT TESTS
# =============================================================================

class TestAPIPayloadContracts:
    """Tests for API response schema compliance."""

    @pytest.mark.asyncio
    async def test_i1_liquidity_response_schema(self, mock_fred_service, normal_fred_data):
        """Liquidity endpoint response must include required fields."""
        mock_fred_service.get_multiple_series = AsyncMock(return_value=normal_fred_data)

        provider = LiquidityDataProviderImpl(fred_service=mock_fred_service)
        result = await provider.get_current()

        # Required top-level fields
        assert "quality" in result
        assert "metrics" in result

        # Quality fields
        quality = result["quality"]
        assert "source" in quality
        assert "as_of" in quality
        assert "is_stale" in quality
        assert "completeness" in quality
        assert "confidence_score" in quality

        # Metrics fields
        metrics = result["metrics"]
        expected_metrics = ["fed_balance_sheet", "rrp", "tga", "fci", "real_yield_10y"]
        for metric_name in expected_metrics:
            assert metric_name in metrics, f"Missing metric: {metric_name}"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
