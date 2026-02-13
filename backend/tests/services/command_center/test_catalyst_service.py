"""
Tests for CatalystService - Trade Readiness and Catalyst Scoring.

Covers:
- A) Readiness is full (not partial) with all providers available
- B) Tier 2 availability and regime wiring
- C) Fallback behavior when Tier 2 provider fails
- D) Event density polarity (no inversion)
- E) Driver contract: direction + regime
- F) Liquidity provider does not request credit series
- G) Staleness behavior
- H) Catalyst summary required fields
- I) Liquidity score calculation
- J) Confidence calculation

All tests use mocked providers - no live network calls.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.command_center.catalyst_service import CatalystService
from app.services.command_center.catalyst_config import CatalystConfig


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def mock_liquidity_provider():
    """Mock liquidity provider."""
    provider = MagicMock()
    return provider


@pytest.fixture
def mock_credit_provider():
    """Mock credit provider."""
    provider = MagicMock()
    return provider


@pytest.fixture
def mock_volatility_provider():
    """Mock volatility provider."""
    provider = MagicMock()
    return provider


@pytest.fixture
def mock_event_density_provider():
    """Mock event density provider."""
    provider = MagicMock()
    return provider


@pytest.fixture
def mock_macro_signal_service():
    """Mock macro signal service for MRI."""
    service = MagicMock()
    return service


@pytest.fixture
def normal_liquidity_response():
    """Normal liquidity response."""
    return {
        "quality": {
            "source": "fred",
            "as_of": "2026-02-01T00:00:00Z",
            "is_stale": False,
            "completeness": 1.0,
            "confidence_score": 85.0,
        },
        "metrics": {
            "fed_balance_sheet": {"value": 7.5e12, "unit": "usd", "change_1w": -0.3, "change_4w": -1.1, "available": True},
            "rrp": {"value": 500e9, "unit": "usd", "change_1w": -5.0, "change_4w": -15.0, "available": True},
            "tga": {"value": 600e9, "unit": "usd", "change_1w": 2.0, "change_4w": 8.0, "available": True},
            "fci": {"value": -0.1, "unit": "index", "change_1w": -0.02, "change_4w": -0.05, "available": True},
            "real_yield_10y": {"value": 1.8, "unit": "pct", "change_1w": 0.05, "change_4w": 0.1, "available": True},
        }
    }


@pytest.fixture
def stale_liquidity_response():
    """Stale liquidity response."""
    return {
        "quality": {
            "source": "fred",
            "as_of": "2026-01-15T00:00:00Z",
            "is_stale": True,
            "stale_reason": "Data older than 48 hours",
            "completeness": 1.0,
            "confidence_score": 40.0,
        },
        "metrics": {
            "fed_balance_sheet": {"value": 7.5e12, "unit": "usd", "available": True},
            "rrp": {"value": 500e9, "unit": "usd", "available": True},
            "tga": {"value": 600e9, "unit": "usd", "available": True},
            "fci": {"value": -0.1, "unit": "index", "available": True},
            "real_yield_10y": {"value": 1.8, "unit": "pct", "available": True},
        }
    }


@pytest.fixture
def normal_mri_response():
    """Normal MRI response."""
    return {
        "mri_score": 45.0,
        "regime": "transition",
        "confidence_score": 75.0,
        "data_stale": False,
    }


@pytest.fixture
def normal_credit_response():
    """Normal credit stress provider response."""
    return {
        "quality": {
            "source": "fred",
            "as_of": "2026-02-01T00:00:00Z",
            "is_stale": False,
            "completeness": 1.0,
            "confidence_score": 90.0,
        },
        "metrics": {
            "high_yield_oas": {"value": 3.50, "unit": "pct", "available": True},
            "investment_grade_oas": {"value": 1.20, "unit": "pct", "available": True},
            "hy_oas_change_4w": {"value": 0.10, "unit": "pct", "available": True},
        }
    }


@pytest.fixture
def normal_volatility_response():
    """Normal volatility provider response."""
    return {
        "quality": {
            "source": "yfinance",
            "as_of": "2026-02-01T00:00:00Z",
            "is_stale": False,
            "completeness": 1.0,
            "confidence_score": 85.0,
        },
        "metrics": {
            "vix": {"value": 17.0, "unit": "index", "available": True},
            "term_slope": {"value": 1.5, "unit": "points", "available": True},
            "vvix": {"value": 85.0, "unit": "index", "available": True},
        }
    }


@pytest.fixture
def normal_event_density_response():
    """Normal event density provider response."""
    return {
        "quality": {
            "source": "finnhub",
            "as_of": "2026-02-01T00:00:00Z",
            "is_stale": False,
            "completeness": 1.0,
            "confidence_score": 100.0,
        },
        "metrics": {
            "total_points": 10.0,
            "high_impact_count": 2,
            "economic_event_count": 5,
            "earnings_count": 3,
            "events": [],
        }
    }


@pytest.fixture
def stressed_credit_response():
    """Stressed credit response (high spreads)."""
    return {
        "quality": {
            "source": "fred",
            "as_of": "2026-02-01T00:00:00Z",
            "is_stale": False,
            "completeness": 1.0,
            "confidence_score": 90.0,
        },
        "metrics": {
            "high_yield_oas": {"value": 6.0, "unit": "pct", "available": True},
            "investment_grade_oas": {"value": 2.0, "unit": "pct", "available": True},
            "hy_oas_change_4w": {"value": 1.5, "unit": "pct", "available": True},
        }
    }


def _build_service(
    liq_provider, credit_provider, vol_provider, event_provider, macro_service,
    liq_response, mri_response, credit_response, vol_response, event_response,
):
    """Helper: build a CatalystService with all providers mocked."""
    liq_provider.get_current = AsyncMock(return_value=liq_response)
    credit_provider.get_current = AsyncMock(return_value=credit_response)
    vol_provider.get_current = AsyncMock(return_value=vol_response)
    event_provider.get_current = AsyncMock(return_value=event_response)
    macro_service.calculate_mri = AsyncMock(return_value=mri_response)

    service = CatalystService(
        liquidity_provider=liq_provider,
        credit_provider=credit_provider,
        volatility_provider=vol_provider,
        event_density_provider=event_provider,
    )
    service._macro_signal_service = macro_service
    # Clear any cached results
    service._cache.clear()
    return service


# =============================================================================
# A) READINESS IS FULL (NOT PARTIAL)
# =============================================================================

class TestReadinessFullState:
    """A) With all providers returning valid data, readiness is not partial."""

    @pytest.mark.asyncio
    async def test_a_readiness_is_not_partial(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        assert result["readiness_is_partial"] is False
        assert result.get("partial_reason") is None


# =============================================================================
# B) TIER 2 AVAILABILITY AND REGIME WIRING
# =============================================================================

class TestTier2AvailabilityAndRegime:
    """B) Tier 2 components are available and have valid regime strings."""

    @pytest.mark.asyncio
    async def test_b_credit_stress_available_with_valid_regime(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        credit = result["components"]["credit_stress"]
        assert credit["available"] is True
        assert credit["regime"] in ("low_stress", "elevated", "high_stress")

    @pytest.mark.asyncio
    async def test_b_vol_structure_available_with_valid_regime(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        vol = result["components"]["vol_structure"]
        assert vol["available"] is True
        assert vol["regime"] in ("calm", "elevated", "stressed")

    @pytest.mark.asyncio
    async def test_b_event_density_available_with_valid_regime(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        events = result["components"]["event_density"]
        assert events["available"] is True
        assert events["regime"] in ("light", "moderate", "heavy")


# =============================================================================
# C) FALLBACK BEHAVIOR WHEN TIER 2 PROVIDER FAILS
# =============================================================================

class TestTier2Fallback:
    """C) When a Tier 2 provider raises an exception, component falls back gracefully."""

    @pytest.mark.asyncio
    async def test_c_credit_provider_failure_fallback(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        # Credit provider raises an exception
        mock_credit_provider.get_current = AsyncMock(side_effect=Exception("FRED API down"))

        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )
        # Re-apply the exception after _build_service overwrote it
        mock_credit_provider.get_current = AsyncMock(side_effect=Exception("FRED API down"))

        result = await service.calculate_trade_readiness()

        # Request should not crash
        assert "trade_readiness_score" in result

        # Credit should be unavailable with default score
        credit = result["components"]["credit_stress"]
        assert credit["available"] is False
        assert credit["score"] == 50  # default

        # unavailable_components should include credit_stress
        assert "credit_stress" in result.get("unavailable_components", [])

    @pytest.mark.asyncio
    async def test_c_vol_provider_failure_fallback(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        mock_volatility_provider.get_current = AsyncMock(side_effect=Exception("yfinance timeout"))

        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )
        mock_volatility_provider.get_current = AsyncMock(side_effect=Exception("yfinance timeout"))

        result = await service.calculate_trade_readiness()

        vol = result["components"]["vol_structure"]
        assert vol["available"] is False
        assert vol["score"] == 50
        assert "vol_structure" in result.get("unavailable_components", [])

    @pytest.mark.asyncio
    async def test_c_event_density_failure_fallback(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        mock_event_density_provider.get_current = AsyncMock(side_effect=Exception("Finnhub down"))

        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )
        mock_event_density_provider.get_current = AsyncMock(side_effect=Exception("Finnhub down"))

        result = await service.calculate_trade_readiness()

        events = result["components"]["event_density"]
        assert events["available"] is False
        assert events["score"] == 50
        assert "event_density" in result.get("unavailable_components", [])


# =============================================================================
# D) EVENT DENSITY POLARITY (NO INVERSION)
# =============================================================================

class TestEventDensityPolarity:
    """D) Higher event density score -> higher trade readiness (more risk-off)."""

    @pytest.mark.asyncio
    async def test_d_higher_event_density_raises_readiness(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response,
    ):
        # Low event density
        low_event_response = {
            "quality": {"source": "finnhub", "as_of": "2026-02-01", "is_stale": False, "completeness": 1.0, "confidence_score": 100.0},
            "metrics": {"total_points": 5.0, "high_impact_count": 1, "economic_event_count": 3, "earnings_count": 1, "events": []},
        }
        service_low = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, low_event_response,
        )
        result_low = await service_low.calculate_trade_readiness()

        # High event density
        high_event_response = {
            "quality": {"source": "finnhub", "as_of": "2026-02-01", "is_stale": False, "completeness": 1.0, "confidence_score": 100.0},
            "metrics": {"total_points": 20.0, "high_impact_count": 5, "economic_event_count": 8, "earnings_count": 5, "events": []},
        }
        service_high = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, high_event_response,
        )
        result_high = await service_high.calculate_trade_readiness()

        # Higher event density should raise readiness score (more risk-off)
        assert result_high["trade_readiness_score"] > result_low["trade_readiness_score"], \
            f"High event density ({result_high['trade_readiness_score']}) should be > " \
            f"low event density ({result_low['trade_readiness_score']})"


# =============================================================================
# E) DRIVER CONTRACT: DIRECTION + REGIME
# =============================================================================

class TestDriverContract:
    """E) Driver objects have standardized direction and regime fields."""

    @pytest.mark.asyncio
    async def test_e_driver_direction_is_standardized(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        for driver in result["drivers"]:
            assert driver["direction"] in ("risk_on", "risk_off", "neutral"), \
                f"Driver '{driver['name']}' has invalid direction: '{driver['direction']}'"

    @pytest.mark.asyncio
    async def test_e_driver_has_regime_field(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        for driver in result["drivers"]:
            assert "regime" in driver, \
                f"Driver '{driver['name']}' missing 'regime' field"

    @pytest.mark.asyncio
    async def test_e_direction_matches_score_vs_50(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        stressed_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        """Direction should be risk_off when score > 51, risk_on when score < 49."""
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            stressed_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        # Find credit_stress driver (stressed inputs should score high)
        # Note: drivers are top-3 sorted by contribution, credit may or may not appear
        # We use the full readiness result to check all drivers
        # Re-run without cache to get all drivers
        service._cache.clear()
        full_result = await service.calculate_trade_readiness()

        for driver in full_result["drivers"]:
            value = driver["value"]
            direction = driver["direction"]
            if value > 51:
                assert direction == "risk_off", \
                    f"Driver '{driver['name']}' value={value} but direction='{direction}' (expected risk_off)"
            elif value < 49:
                assert direction == "risk_on", \
                    f"Driver '{driver['name']}' value={value} but direction='{direction}' (expected risk_on)"
            else:
                assert direction == "neutral", \
                    f"Driver '{driver['name']}' value={value} but direction='{direction}' (expected neutral)"


# =============================================================================
# F) LIQUIDITY PROVIDER DOES NOT REQUEST CREDIT SERIES
# =============================================================================

class TestLiquidityProviderIsolation:
    """F) Liquidity provider only fetches liquidity FRED series."""

    @pytest.mark.asyncio
    async def test_f_liquidity_provider_uses_only_liquidity_series(self):
        """get_current() should not include credit FRED series."""
        from app.services.data_providers.liquidity_provider import LIQUIDITY_FRED_SERIES

        # Verify LIQUIDITY_FRED_SERIES does not include credit series
        assert "hy_oas" not in LIQUIDITY_FRED_SERIES
        assert "ig_oas" not in LIQUIDITY_FRED_SERIES

        # Verify it includes only the 6 liquidity series
        expected_keys = {"fed_balance_sheet", "rrp", "tga", "fci", "dgs10", "t10yie"}
        assert set(LIQUIDITY_FRED_SERIES.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_f_liquidity_get_current_fetches_only_liquidity(self):
        """Mock FRED client and verify only liquidity series are requested."""
        from app.services.data_providers.liquidity_provider import LiquidityDataProviderImpl, LIQUIDITY_FRED_SERIES

        mock_fred = MagicMock()
        # Return valid data for all series
        mock_result = {}
        for series_id in LIQUIDITY_FRED_SERIES.values():
            mock_result[series_id] = {
                "value": 1.0,
                "date": "2026-02-01",
                "change_1w": 0.0,
                "change_4w": 0.0,
                "is_stale": False,
            }
        mock_fred.get_multiple_series = AsyncMock(return_value=mock_result)

        provider = LiquidityDataProviderImpl(fred_service=mock_fred)
        await provider.get_current()

        # Verify get_multiple_series was called with only liquidity series IDs
        call_args = mock_fred.get_multiple_series.call_args
        series_requested = call_args[0][0]  # first positional arg

        expected_series = set(LIQUIDITY_FRED_SERIES.values())
        actual_series = set(series_requested)
        assert actual_series == expected_series, \
            f"Expected {expected_series}, got {actual_series}"

        # Credit series should NOT be included
        assert "BAMLH0A0HYM2" not in actual_series
        assert "BAMLC0A0CM" not in actual_series


# =============================================================================
# G) STALENESS BEHAVIOR
# =============================================================================

class TestCatalystStaleness:
    """Tests for staleness handling in CatalystService."""

    @pytest.mark.asyncio
    async def test_g_stale_liquidity_marks_overall_stale(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        stale_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        """Stale provider data marks overall result as stale."""
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            stale_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        assert result["data_stale"] is True
        assert "liquidity" in result.get("stale_components", [])


# =============================================================================
# H) CATALYST SUMMARY
# =============================================================================

class TestCatalystSummary:
    """Tests for catalyst summary endpoint."""

    @pytest.mark.asyncio
    async def test_h_catalyst_summary_includes_required_fields(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.get_catalyst_summary()

        assert "trade_readiness" in result
        assert "components" in result
        assert "drivers" in result
        assert "confidence_by_component" in result
        assert "overall_confidence" in result
        assert "data_stale" in result
        assert "calculated_at" in result

        tr = result["trade_readiness"]
        assert "score" in tr
        assert "label" in tr
        assert "is_partial" in tr
        assert tr["is_partial"] is False


# =============================================================================
# I) LIQUIDITY SCORE CALCULATION
# =============================================================================

class TestLiquidityScoreCalculation:
    """Tests for liquidity score calculation specifics."""

    @pytest.mark.asyncio
    async def test_i_liquidity_regime_classification(
        self, mock_liquidity_provider, normal_liquidity_response
    ):
        mock_liquidity_provider.get_current = AsyncMock(return_value=normal_liquidity_response)

        service = CatalystService(liquidity_provider=mock_liquidity_provider)

        result = await service.get_liquidity()

        assert isinstance(result["score"], (int, float))
        assert result["regime"] in ["risk_on", "transition", "risk_off"]

        score = result["score"]
        regime = result["regime"]

        if score < 35:
            assert regime == "risk_on"
        elif score > 65:
            assert regime == "risk_off"
        else:
            assert regime == "transition"

    @pytest.mark.asyncio
    async def test_i_liquidity_drivers_sorted_by_contribution(
        self, mock_liquidity_provider, normal_liquidity_response
    ):
        mock_liquidity_provider.get_current = AsyncMock(return_value=normal_liquidity_response)

        service = CatalystService(liquidity_provider=mock_liquidity_provider)

        result = await service.get_liquidity()

        drivers = result.get("drivers", [])
        if len(drivers) > 1:
            contributions = [abs(d["contribution"]) for d in drivers]
            assert contributions == sorted(contributions, reverse=True), \
                "Drivers not sorted by absolute contribution"


# =============================================================================
# J) CONFIDENCE CALCULATION
# =============================================================================

class TestConfidenceCalculation:
    """Tests for confidence score calculation."""

    @pytest.mark.asyncio
    async def test_j_overall_confidence_is_minimum_of_available(
        self,
        mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
        mock_event_density_provider, mock_macro_signal_service,
        normal_liquidity_response, normal_mri_response,
        normal_credit_response, normal_volatility_response, normal_event_density_response,
    ):
        service = _build_service(
            mock_liquidity_provider, mock_credit_provider, mock_volatility_provider,
            mock_event_density_provider, mock_macro_signal_service,
            normal_liquidity_response, normal_mri_response,
            normal_credit_response, normal_volatility_response, normal_event_density_response,
        )

        result = await service.calculate_trade_readiness()

        overall = result["overall_confidence"]
        by_component = result["confidence_by_component"]

        # Overall should be <= minimum of all available component confidences
        available_confidences = [
            v for k, v in by_component.items()
            if result["components"].get(k, {}).get("available", False) and v > 0
        ]

        if available_confidences:
            expected_min = min(available_confidences)
            assert overall <= expected_min + 0.1, \
                f"Overall confidence {overall} should be <= min of available components {expected_min}"


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
