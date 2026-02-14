"""
Layer 1: PresetSelector — Market condition classification tests.

Tests the weighted composite scoring system that maps market intelligence
signals (MRI, regime, F&G, readiness) to scanning preset selections.
"""
import pytest
from app.services.automation.preset_selector import (
    PresetSelector,
    CONDITION_THRESHOLDS,
    SIGNAL_WEIGHTS,
    MARKET_CONDITIONS,
)
from tests.pipeline.mock_market import (
    BULLISH_MARKET,
    MODERATE_BULL_MARKET,
    NEUTRAL_MARKET,
    BEARISH_MARKET,
    PANIC_MARKET,
    PARTIAL_DATA_MARKET,
    ALL_MISSING_MARKET,
)


@pytest.fixture
def selector():
    return PresetSelector()


class TestCompositeScoreCalculation:
    """Unit tests for _compute_composite_score()."""

    def test_bullish_market_scores_high(self, selector):
        """Bullish regime + low MRI + high F&G + green readiness → high positive score."""
        score, signals = selector._compute_composite_score(BULLISH_MARKET)
        assert score >= 50, f"Bullish market should score ≥50, got {score:.1f}"
        assert signals["regime"] > 0
        assert signals["mri"] > 0
        assert signals["fear_greed"] > 0
        assert signals["readiness"] > 0

    def test_bearish_market_scores_low(self, selector):
        """Bearish regime + high MRI + low F&G + red readiness → negative score."""
        score, signals = selector._compute_composite_score(BEARISH_MARKET)
        assert score < -20, f"Bearish market should score <-20, got {score:.1f}"
        assert signals["regime"] < 0
        assert signals["mri"] < 0
        assert signals["fear_greed"] < 0
        assert signals["readiness"] < 0

    def test_neutral_market_scores_near_zero(self, selector):
        """Neutral regime + mid MRI + mid F&G + yellow readiness → score near 0."""
        score, signals = selector._compute_composite_score(NEUTRAL_MARKET)
        assert -15 <= score <= 15, f"Neutral market should score near 0, got {score:.1f}"

    def test_missing_signals_renormalize_weights(self, selector):
        """When some signals are missing, remaining weights are re-normalized."""
        score, signals = selector._compute_composite_score(PARTIAL_DATA_MARKET)
        # Only regime is available (MRI, F&G, readiness all None)
        assert signals["regime"] is not None
        assert signals["mri"] is None
        assert signals["fear_greed"] is None
        # Score should still be computed from available signals
        assert score > 0, "Bullish regime should produce positive score even alone"

    def test_all_missing_returns_zero(self, selector):
        """When all signals are missing, composite score is 0."""
        score, signals = selector._compute_composite_score(ALL_MISSING_MARKET)
        assert score == 0.0

    def test_mri_inversion(self, selector):
        """MRI is inverted: low MRI (0) = bullish (+100), high MRI (100) = bearish (-100)."""
        # MRI = 0 → signal = (50 - 0) * 2 = +100
        snapshot = {**NEUTRAL_MARKET, "mri": 0}
        _, signals = selector._compute_composite_score(snapshot)
        assert signals["mri"] == 100.0

        # MRI = 100 → signal = (50 - 100) * 2 = -100
        snapshot = {**NEUTRAL_MARKET, "mri": 100}
        _, signals = selector._compute_composite_score(snapshot)
        assert signals["mri"] == -100.0

    def test_fear_greed_direct_mapping(self, selector):
        """F&G maps directly: 0 → -100 (fear), 50 → 0, 100 → +100 (greed)."""
        snapshot = {**NEUTRAL_MARKET, "fear_greed": 0}
        _, signals = selector._compute_composite_score(snapshot)
        assert signals["fear_greed"] == -100.0

        snapshot = {**NEUTRAL_MARKET, "fear_greed": 100}
        _, signals = selector._compute_composite_score(snapshot)
        assert signals["fear_greed"] == 100.0


class TestConditionClassification:
    """Tests for _classify_condition() — score → condition mapping."""

    def test_aggressive_bull_threshold(self, selector):
        """Score ≥ 50 → aggressive_bull."""
        result = selector._classify_condition(50.0, BULLISH_MARKET)
        assert result == "aggressive_bull"
        result = selector._classify_condition(80.0, BULLISH_MARKET)
        assert result == "aggressive_bull"

    def test_moderate_bull_threshold(self, selector):
        """Score 20-49 → moderate_bull."""
        result = selector._classify_condition(20.0, MODERATE_BULL_MARKET)
        assert result == "moderate_bull"
        result = selector._classify_condition(49.9, MODERATE_BULL_MARKET)
        assert result == "moderate_bull"

    def test_neutral_threshold(self, selector):
        """Score 0-19 → neutral."""
        result = selector._classify_condition(0.0, NEUTRAL_MARKET)
        assert result == "neutral"
        result = selector._classify_condition(19.9, NEUTRAL_MARKET)
        assert result == "neutral"

    def test_cautious_threshold(self, selector):
        """Score -20 to -1 → cautious."""
        result = selector._classify_condition(-1.0, BEARISH_MARKET)
        assert result == "cautious"
        result = selector._classify_condition(-20.0, BEARISH_MARKET)
        assert result == "cautious"

    def test_defensive_threshold(self, selector):
        """Score -50 to -21 → defensive."""
        result = selector._classify_condition(-21.0, BEARISH_MARKET)
        assert result == "defensive"
        result = selector._classify_condition(-50.0, BEARISH_MARKET)
        assert result == "defensive"

    def test_skip_below_minus_50(self, selector):
        """Score below -50 → skip."""
        result = selector._classify_condition(-51.0, BEARISH_MARKET)
        assert result == "skip"

    def test_panic_override_mri_and_fg(self, selector):
        """MRI > 80 AND F&G < 10 → skip, regardless of score."""
        # Even with a positive score, panic override kicks in
        result = selector._classify_condition(30.0, PANIC_MARKET)
        assert result == "skip"

    def test_no_panic_when_only_one_extreme(self, selector):
        """Panic requires BOTH MRI > 80 AND F&G < 10."""
        # High MRI but normal F&G → no panic override
        snapshot = {**BEARISH_MARKET, "mri": 85, "fear_greed": 25}
        result = selector._classify_condition(-10.0, snapshot)
        assert result != "skip"  # Should be cautious based on score

        # Low F&G but normal MRI → no panic override
        snapshot = {**BEARISH_MARKET, "mri": 60, "fear_greed": 5}
        result = selector._classify_condition(-10.0, snapshot)
        assert result != "skip"


class TestPresetMapping:
    """Verify conditions map to correct presets."""

    def test_aggressive_bull_presets(self, selector):
        assert "aggressive" in MARKET_CONDITIONS["aggressive_bull"]["presets"]

    def test_moderate_bull_presets(self, selector):
        presets = MARKET_CONDITIONS["moderate_bull"]["presets"]
        assert "moderate" in presets
        assert "blue_chip_leaps" in presets

    def test_cautious_presets(self, selector):
        presets = MARKET_CONDITIONS["cautious"]["presets"]
        assert "conservative" in presets

    def test_skip_has_no_presets(self, selector):
        assert MARKET_CONDITIONS["skip"]["presets"] == []
        assert MARKET_CONDITIONS["skip"]["max_positions"] == 0
