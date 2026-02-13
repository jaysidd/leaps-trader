"""
Tests for Macro Overlay functionality.

Tests sector macro weight defaults and trade compatibility flags.
Key constraint: Macro overlay INFORMS, does NOT gate trades.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.command_center.catalyst_service import CatalystService
from app.services.command_center.catalyst_config import CatalystConfig


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def config():
    """Default catalyst config."""
    return CatalystConfig()


@pytest.fixture
def service(config):
    """CatalystService with mock providers."""
    mock_liquidity = MagicMock()
    return CatalystService(liquidity_provider=mock_liquidity, config=config)


# =============================================================================
# SECTOR MACRO WEIGHT TESTS
# =============================================================================

class TestSectorMacroWeights:
    """Tests for sector → macro weight defaults."""

    def test_technology_sector_has_correct_weights(self, service):
        """Technology sector has expected weight distribution."""
        weights = service.get_sector_macro_weights("Technology")

        assert weights["liquidity"] == 0.30
        assert weights["fed_policy"] == 0.25
        assert weights["earnings"] == 0.20
        assert weights["options_positioning"] == 0.15
        assert weights["event_risk"] == 0.10

        # Weights must sum to 1.0
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001, f"Technology weights sum to {total}, not 1.0"

    def test_financials_sector_has_higher_liquidity_weight(self, service):
        """Financials sector has higher liquidity and fed_policy weights."""
        weights = service.get_sector_macro_weights("Financials")

        assert weights["liquidity"] == 0.35
        assert weights["fed_policy"] == 0.30

        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001

    def test_real_estate_sector_most_rate_sensitive(self, service):
        """Real Estate has highest fed_policy weight (rate sensitive)."""
        weights = service.get_sector_macro_weights("Real Estate")

        assert weights["fed_policy"] == 0.35  # Highest among all sectors
        assert weights["liquidity"] == 0.30

    def test_healthcare_sector_earnings_focused(self, service):
        """Healthcare sector emphasizes earnings and event risk."""
        weights = service.get_sector_macro_weights("Healthcare")

        assert weights["earnings"] == 0.30  # Higher than most
        assert weights["event_risk"] == 0.20  # FDA events etc.
        assert weights["fed_policy"] == 0.15  # Less rate sensitive

    def test_unknown_sector_uses_defaults(self, service):
        """Unknown sector returns balanced default weights."""
        weights = service.get_sector_macro_weights("SomeUnknownSector")

        assert weights == service.get_sector_macro_weights("Unknown")
        assert weights["liquidity"] == 0.25
        assert weights["fed_policy"] == 0.25

    def test_sector_name_normalized(self, service):
        """Sector names are normalized (case-insensitive, trimmed)."""
        weights1 = service.get_sector_macro_weights("technology")
        weights2 = service.get_sector_macro_weights("TECHNOLOGY")
        weights3 = service.get_sector_macro_weights("  Technology  ")

        assert weights1 == weights2 == weights3

    def test_all_configured_sectors_sum_to_one(self, config):
        """All configured sector weights sum to 1.0."""
        for sector, weights in config.SECTOR_MACRO_WEIGHTS.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.001, f"{sector} weights sum to {total}"


# =============================================================================
# MACRO BIAS SCORE TESTS
# =============================================================================

class TestMacroBiasScore:
    """Tests for macro bias score computation."""

    def test_bullish_conditions_produce_high_score(self, service):
        """Bullish macro conditions produce score > 67."""
        # Low scores = risk-on = bullish
        result = service._compute_macro_bias_score(
            sector="Technology",
            liquidity_score=20,  # Risk-on (expanding)
            mri_score=25,        # Risk-on
            earnings_risk_score=20,
            options_positioning_score=30,
            event_risk_score=20,
        )

        assert result["score"] >= 67, f"Expected bullish (>=67), got {result['score']}"
        assert result["label"] == "bullish"

    def test_bearish_conditions_produce_low_score(self, service):
        """Bearish macro conditions produce score <= 33."""
        # High scores = risk-off = bearish
        result = service._compute_macro_bias_score(
            sector="Technology",
            liquidity_score=80,  # Risk-off (contracting)
            mri_score=75,        # Risk-off
            earnings_risk_score=80,
            options_positioning_score=70,
            event_risk_score=80,
        )

        assert result["score"] <= 33, f"Expected bearish (<=33), got {result['score']}"
        assert result["label"] == "bearish"

    def test_neutral_conditions_produce_middle_score(self, service):
        """Neutral conditions produce score between 34-66."""
        result = service._compute_macro_bias_score(
            sector="Technology",
            liquidity_score=50,
            mri_score=50,
            earnings_risk_score=50,
            options_positioning_score=50,
            event_risk_score=50,
        )

        assert 34 <= result["score"] <= 66, f"Expected neutral (34-66), got {result['score']}"
        assert result["label"] == "neutral"

    def test_score_clamped_to_0_100(self, service):
        """Score is always clamped to 0-100 range."""
        # Extreme bullish
        result = service._compute_macro_bias_score(
            sector="Technology",
            liquidity_score=0,
            mri_score=0,
        )
        assert 0 <= result["score"] <= 100

        # Extreme bearish
        result = service._compute_macro_bias_score(
            sector="Technology",
            liquidity_score=100,
            mri_score=100,
        )
        assert 0 <= result["score"] <= 100

    def test_sector_weights_applied_correctly(self, service):
        """Different sectors produce different scores for same inputs."""
        inputs = {
            "liquidity_score": 60,
            "mri_score": 40,
        }

        tech_result = service._compute_macro_bias_score(sector="Technology", **inputs)
        fin_result = service._compute_macro_bias_score(sector="Financials", **inputs)

        # Scores should differ because weights differ
        assert tech_result["score"] != fin_result["score"]
        assert tech_result["sector_weights"] != fin_result["sector_weights"]

    def test_component_contributions_included(self, service):
        """Response includes component contribution breakdown."""
        result = service._compute_macro_bias_score(
            sector="Technology",
            liquidity_score=50,
            mri_score=50,
        )

        assert "component_contributions" in result
        contributions = result["component_contributions"]

        assert "liquidity" in contributions
        assert "fed_policy" in contributions
        assert "value" in contributions["liquidity"]
        assert "weight" in contributions["liquidity"]
        assert "contribution" in contributions["liquidity"]


# =============================================================================
# TRADE COMPATIBILITY TESTS
# =============================================================================

class TestTradeCompatibility:
    """Tests for trade compatibility indicator.

    IMPORTANT: Compatibility is an INFO flag, NOT a gate.
    """

    def test_favorable_when_readiness_low_and_no_earnings_risk(self, service):
        """Favorable when readiness favorable and earnings risk low."""
        result = service.compute_trade_compatibility(
            readiness_score=30,  # Below 40 threshold
            earnings_risk_score=30,  # Below 50 threshold
            earnings_days_out=None,
            options_positioning_score=None,
        )

        assert result["compatibility"] == "favorable"
        assert result["macro_headwind"] == False

    def test_unfavorable_when_readiness_high(self, service):
        """Unfavorable when readiness score too high (risk-off)."""
        result = service.compute_trade_compatibility(
            readiness_score=70,  # Above 60 threshold
            earnings_risk_score=None,
            earnings_days_out=None,
            options_positioning_score=None,
        )

        assert result["compatibility"] == "unfavorable"
        assert result["macro_headwind"] == True

    def test_unfavorable_when_earnings_imminent(self, service):
        """Unfavorable when earnings within 2 days."""
        result = service.compute_trade_compatibility(
            readiness_score=50,
            earnings_risk_score=None,
            earnings_days_out=2,  # Imminent
            options_positioning_score=None,
        )

        assert result["compatibility"] == "unfavorable"
        assert result["flags"]["earnings_imminent"] == True

    def test_mixed_when_moderate_conditions(self, service):
        """Mixed when conditions are moderate."""
        result = service.compute_trade_compatibility(
            readiness_score=50,  # Between thresholds
            earnings_risk_score=55,  # Slightly elevated
            earnings_days_out=10,  # Not imminent
            options_positioning_score=50,
        )

        assert result["compatibility"] == "mixed"

    def test_reasons_explain_compatibility(self, service):
        """Reasons list explains the compatibility determination."""
        result = service.compute_trade_compatibility(
            readiness_score=75,
            earnings_risk_score=60,
            earnings_days_out=1,
            options_positioning_score=70,
        )

        assert len(result["reasons"]) > 0
        # Should mention elevated readiness and imminent earnings
        reasons_text = " ".join(result["reasons"]).lower()
        assert "readiness" in reasons_text or "earnings" in reasons_text

    def test_flags_detail_each_condition(self, service):
        """Flags dict provides detailed condition breakdown."""
        result = service.compute_trade_compatibility(
            readiness_score=75,
            earnings_risk_score=60,
            earnings_days_out=1,
            options_positioning_score=70,
        )

        flags = result["flags"]
        assert "readiness_favorable" in flags
        assert "readiness_unfavorable" in flags
        assert "earnings_imminent" in flags
        assert "earnings_elevated" in flags
        assert "options_fragile" in flags
        assert "macro_headwind" in flags

    def test_options_fragile_flag_set_above_66(self, service):
        """Options fragile flag set when positioning score > 66."""
        result = service.compute_trade_compatibility(
            readiness_score=50,
            earnings_risk_score=None,
            earnings_days_out=None,
            options_positioning_score=70,  # Above 66
        )

        assert result["flags"]["options_fragile"] == True


# =============================================================================
# MACRO OVERLAY INTEGRATION TESTS
# =============================================================================

class TestMacroOverlay:
    """Tests for the full macro overlay endpoint logic.

    Key principle: Overlay provides CONTEXT, not a gatekeeper.
    """

    @pytest.mark.asyncio
    async def test_overlay_returns_required_fields(self, service):
        """Macro overlay returns all required fields per spec."""
        # Mock the internal methods
        service.calculate_trade_readiness = AsyncMock(return_value={
            "trade_readiness_score": 45,
            "readiness_label": "yellow",
            "data_stale": False,
            "components": {"mri": {"score": 45, "regime": "transition"}},
            "overall_confidence": 70,
        })
        service.get_liquidity = AsyncMock(return_value={
            "score": 50,
            "regime": "transition",
            "data_stale": False,
            "drivers": [{"name": "rrp", "contribution": 5, "direction": "bearish"}],
        })

        result = await service.get_ticker_macro_overlay(symbol="AAPL", sector="Technology")

        # Required fields per spec
        assert "symbol" in result
        assert result["symbol"] == "AAPL"
        assert "macro_bias" in result
        assert "macro_bias_score" in result
        assert "confidence_score" in result
        assert "data_stale" in result
        assert "trade_compatibility" in result
        assert "macro_headwind" in result
        assert "drivers" in result
        assert "links" in result
        assert result["links"]["macro_intelligence"] == "/macro-intelligence"

    @pytest.mark.asyncio
    async def test_overlay_gracefully_degrades_on_error(self, service):
        """Overlay returns partial data on error, never blocks."""
        service.calculate_trade_readiness = AsyncMock(side_effect=Exception("Test error"))
        service.get_liquidity = AsyncMock(side_effect=Exception("Test error"))

        result = await service.get_ticker_macro_overlay(symbol="AAPL")

        # Should return degraded response, not raise
        assert result["symbol"] == "AAPL"
        assert result["macro_bias"] == "unknown"
        assert result["data_stale"] == True
        assert result["trade_compatibility"] == "mixed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_overlay_uses_sector_specific_weights(self, service):
        """Overlay applies sector-specific weights to macro bias calculation."""
        service.calculate_trade_readiness = AsyncMock(return_value={
            "trade_readiness_score": 50,
            "readiness_label": "yellow",
            "data_stale": False,
            "components": {"mri": {"score": 50}},
            "overall_confidence": 70,
        })
        service.get_liquidity = AsyncMock(return_value={
            "score": 50,
            "regime": "transition",
            "data_stale": False,
            "drivers": [],
        })

        tech_result = await service.get_ticker_macro_overlay(symbol="AAPL", sector="Technology")
        fin_result = await service.get_ticker_macro_overlay(symbol="JPM", sector="Financials")

        # Sector should be reflected in details
        assert tech_result["sector"] == "Technology"
        assert fin_result["sector"] == "Financials"
        assert tech_result["details"]["sector_weights"] != fin_result["details"]["sector_weights"]

    @pytest.mark.asyncio
    async def test_overlay_drivers_human_readable(self, service):
        """Overlay drivers are human-readable, not numeric."""
        service.calculate_trade_readiness = AsyncMock(return_value={
            "trade_readiness_score": 50,
            "readiness_label": "yellow",
            "data_stale": False,
            "components": {"mri": {"score": 50, "regime": "transition"}},
            "overall_confidence": 70,
            "drivers": [{"name": "MRI", "value": 50, "direction": "transition"}],
        })
        service.get_liquidity = AsyncMock(return_value={
            "score": 50,
            "regime": "transition",
            "data_stale": False,
            "drivers": [{"name": "rrp", "contribution": 5, "direction": "bearish"}],
        })

        result = await service.get_ticker_macro_overlay(symbol="AAPL")

        # Drivers should be strings, not dicts with raw values
        assert isinstance(result["drivers"], list)
        for driver in result["drivers"]:
            assert isinstance(driver, str)

    @pytest.mark.asyncio
    async def test_overlay_never_blocks_trading_signals(self, service):
        """Overlay data should never block trading signals.

        Even in worst case (all errors), compatibility should be 'mixed' not 'blocked'.
        """
        service.calculate_trade_readiness = AsyncMock(side_effect=Exception("Error"))
        service.get_liquidity = AsyncMock(side_effect=Exception("Error"))

        result = await service.get_ticker_macro_overlay(symbol="AAPL")

        # Should NEVER be "blocked" or similar gating value
        assert result["trade_compatibility"] in ["favorable", "mixed", "unfavorable"]
        # macro_headwind should be false on error (benefit of doubt)
        assert result["macro_headwind"] == False


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
