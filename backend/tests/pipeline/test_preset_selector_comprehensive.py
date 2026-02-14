"""
Comprehensive PresetSelector test suite.

Tests the market-adaptive preset selector that classifies market conditions
and maps them to screening presets. Covers:

- Boundary classification at exact thresholds (PS-U01)
- Confidence scaling on regime signal (PS-U02)
- Weight re-normalization with missing signals (PS-U03)
- Readiness label fallback when score is unavailable (PS-U04)
- Panic override logic (PS-S01/S02)
- Preset mapping contract tests (PS-C01/C02/C03)
- Cache behavior for _gather_market_snapshot (PS-INT01-04)
- Failure resilience when services raise (PS-R01-04)
- Determinism and stability (PS-T01-03)
- Exact scoring math against hand-verified values (PS-M01-05)
- Reasoning output content (PS-O01-03)
- Edge cases and quirks (PS-E01-07)
- select_presets() end-to-end async orchestration (PS-E2E01-05)
- _validate_preset_catalog() startup validation (PS-VAL01-06)
- get_preset_selector() singleton pattern (PS-SNG01-03)
- _gather_market_snapshot() edge cases (PS-GMS01-08)
- _build_reasoning() edge cases (PS-BR01-06)

Run:  python3 -m pytest tests/pipeline/test_preset_selector_comprehensive.py -v
"""
import os
import copy
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from app.services.automation.preset_selector import (
    PresetSelector,
    CONDITION_THRESHOLDS,
    SIGNAL_WEIGHTS,
    MARKET_CONDITIONS,
    SELECTOR_VERSION,
)
from app.data.presets_catalog import LEAPS_PRESETS, get_catalog_hash

from tests.pipeline.mock_market import (
    BULLISH_MARKET,
    MODERATE_BULL_MARKET,
    NEUTRAL_MARKET,
    BEARISH_MARKET,
    PANIC_MARKET,
    PARTIAL_DATA_MARKET,
    ALL_MISSING_MARKET,
    NEAR_PANIC_MRI_ONLY,
    NEAR_PANIC_FG_ONLY,
    LABEL_FALLBACK_GREEN,
    LABEL_FALLBACK_YELLOW,
    LABEL_FALLBACK_RED,
    MAX_BULLISH_MARKET,
    MAX_BEARISH_MARKET,
    BOUNDARY_AGGRESSIVE,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def selector():
    """Fresh PresetSelector instance for each test."""
    return PresetSelector()


# ---------------------------------------------------------------------------
# Helper: build a minimal snapshot with overrides
# ---------------------------------------------------------------------------

def _snapshot(**overrides):
    """Build a minimal snapshot dict, defaulting everything to None."""
    base = {
        "mri": None,
        "mri_regime": None,
        "regime": None,
        "risk_mode": None,
        "regime_confidence": None,
        "fear_greed": None,
        "readiness": None,
        "readiness_label": None,
        "timestamp": "2026-02-14T10:00:00",
    }
    base.update(overrides)
    return base


# ===========================================================================
# 1. TestBoundaryClassification (PS-U01) — 12 tests
# ===========================================================================

class TestBoundaryClassification:
    """PS-U01: Verify _classify_condition at exact threshold boundaries.

    Uses NEUTRAL_MARKET as the snapshot so panic override never fires
    (MRI=45, F&G=50 are far from panic thresholds).
    """

    @pytest.mark.parametrize(
        "score, expected_condition",
        [
            (100.0, "aggressive_bull"),    # well above
            (50.0, "aggressive_bull"),     # exact threshold (>= 50)
            (49.9, "moderate_bull"),       # just below aggressive
            (20.0, "moderate_bull"),       # exact threshold (>= 20)
            (19.9, "neutral"),            # just below moderate
            (0.0, "neutral"),            # exact threshold (>= 0)
            (-0.1, "cautious"),          # just below neutral
            (-20.0, "cautious"),         # exact threshold (>= -20)
            (-20.1, "defensive"),        # just below cautious
            (-50.0, "defensive"),        # exact threshold (>= -50)
            (-50.1, "skip"),             # just below defensive
            (-100.0, "skip"),            # floor
        ],
        ids=[
            "score_100_aggressive",
            "score_50_aggressive_exact",
            "score_49.9_moderate",
            "score_20_moderate_exact",
            "score_19.9_neutral",
            "score_0_neutral_exact",
            "score_neg0.1_cautious",
            "score_neg20_cautious_exact",
            "score_neg20.1_defensive",
            "score_neg50_defensive_exact",
            "score_neg50.1_skip",
            "score_neg100_skip",
        ],
    )
    def test_boundary(self, selector, score, expected_condition):
        """Each score maps to exactly one condition bucket."""
        result = selector._classify_condition(score, NEUTRAL_MARKET)
        assert result == expected_condition


# ===========================================================================
# 2. TestConfidenceScaling (PS-U02) — 7 tests
# ===========================================================================

class TestConfidenceScaling:
    """PS-U02: Verify how regime_confidence scales the regime signal.

    Formula: regime_signal = regime_raw * min(confidence/100, 1.0)
    - bullish raw = +80, neutral raw = 0, bearish raw = -80
    - confidence=None defaults to 0.7
    """

    @pytest.mark.parametrize(
        "regime, confidence, expected_signal",
        [
            ("bullish", 100, 80.0),      # 80 * 1.0
            ("bullish", 50, 40.0),       # 80 * 0.5
            ("bullish", 0, 0.0),         # 80 * 0.0 — B3 fix: zero confidence kills signal
            ("bullish", None, 56.0),     # 80 * 0.7 default
            ("bullish", 150, 80.0),      # capped at 1.0 → 80 * 1.0
            ("bearish", 80, -64.0),      # -80 * 0.8
            ("neutral", 100, 0.0),       # 0 * 1.0 — neutral regime always zero
        ],
        ids=[
            "full_confidence",
            "half_confidence",
            "zero_confidence_B3",
            "none_defaults_to_0.7",
            "over_100_capped",
            "bearish_80pct",
            "neutral_always_zero",
        ],
    )
    def test_confidence_scales_regime(self, selector, regime, confidence, expected_signal):
        """Regime signal = raw * min(confidence/100, 1.0)."""
        snap = _snapshot(regime=regime, regime_confidence=confidence)
        _, signal_scores = selector._compute_composite_score(snap)
        assert signal_scores["regime"] == pytest.approx(expected_signal, abs=0.1)


# ===========================================================================
# 3. TestWeightRenormalization (PS-U03) — 6 tests
# ===========================================================================

class TestWeightRenormalization:
    """PS-U03: When signals are missing, available weights re-normalize to 1.0.

    With N signals available (weight sum = W), each signal's effective weight
    becomes weight_i / W.
    """

    def test_single_signal_gets_full_weight(self, selector):
        """PS-U03a: With only regime available, it accounts for 100% of composite."""
        snap = _snapshot(regime="bullish", regime_confidence=100)
        # regime signal = 80, weight = 0.35 / 0.35 = 1.0, composite = 80
        score, _ = selector._compute_composite_score(snap)
        assert score == pytest.approx(80.0, abs=0.1)

    def test_two_signals_proportional(self, selector):
        """PS-U03b: Regime + F&G only — weights re-normalize proportionally."""
        snap = _snapshot(
            regime="bullish", regime_confidence=100,  # signal = 80
            fear_greed=100,                            # signal = 100
        )
        # available_weight = 0.35 + 0.20 = 0.55
        # regime contribution = 80 * (0.35/0.55) = 80 * 0.6364 = 50.91
        # fg contribution = 100 * (0.20/0.55) = 100 * 0.3636 = 36.36
        # composite = 87.27
        score, _ = selector._compute_composite_score(snap)
        regime_eff = 0.35 / 0.55
        fg_eff = 0.20 / 0.55
        expected = 80 * regime_eff + 100 * fg_eff
        assert score == pytest.approx(expected, abs=0.1)

    def test_three_signals_proportional(self, selector):
        """PS-U03c: Regime + MRI + Readiness — proportional weights."""
        snap = _snapshot(
            regime="bullish", regime_confidence=100,  # signal = 80
            mri=25,                                    # signal = 50
            readiness=30,                              # signal = 40
        )
        avail = 0.35 + 0.30 + 0.15
        expected = (80 * 0.35 + 50 * 0.30 + 40 * 0.15) / avail
        score, _ = selector._compute_composite_score(snap)
        assert score == pytest.approx(expected, abs=0.1)

    def test_all_four_original_weights(self, selector):
        """PS-U03d: All 4 signals → original weights (sum=1.0, no renormalization)."""
        # Use BULLISH_MARKET — all signals present
        score, signals = selector._compute_composite_score(BULLISH_MARKET)
        # all weights sum to 1.0, no rescaling needed
        expected = (
            signals["regime"] * SIGNAL_WEIGHTS["regime"]
            + signals["mri"] * SIGNAL_WEIGHTS["mri"]
            + signals["fear_greed"] * SIGNAL_WEIGHTS["fear_greed"]
            + signals["readiness"] * SIGNAL_WEIGHTS["readiness"]
        )
        assert score == pytest.approx(expected, abs=0.1)

    def test_only_mri_full_weight(self, selector):
        """PS-U03e: With only MRI, its weight = 1.0."""
        snap = _snapshot(mri=10)  # signal = (50-10)*2 = 80
        score, _ = selector._compute_composite_score(snap)
        assert score == pytest.approx(80.0, abs=0.1)

    def test_regime_plus_fg_exact_weights(self, selector):
        """PS-U03f: Regime + F&G — verify exact weight fractions."""
        snap = _snapshot(
            regime="bullish", regime_confidence=100,  # signal = 80
            fear_greed=75,                             # signal = 50
        )
        avail = 0.35 + 0.20
        regime_w = 0.35 / avail
        fg_w = 0.20 / avail
        assert regime_w == pytest.approx(0.636, abs=0.01)
        assert fg_w == pytest.approx(0.364, abs=0.01)
        expected = 80 * regime_w + 50 * fg_w
        score, _ = selector._compute_composite_score(snap)
        assert score == pytest.approx(expected, abs=0.1)


# ===========================================================================
# 4. TestReadinessLabelFallback (PS-U04) — 5 tests
# ===========================================================================

class TestReadinessLabelFallback:
    """PS-U04: When readiness score is None but label is available,
    use label fallback: green=60, yellow=0, red=-60.
    When score IS available, always use the score.
    """

    def test_green_label_fallback(self, selector):
        """readiness=None, label='green' -> signal=60."""
        snap = _snapshot(readiness=None, readiness_label="green")
        _, signals = selector._compute_composite_score(snap)
        assert signals["readiness"] == pytest.approx(60.0, abs=0.1)

    def test_yellow_label_fallback(self, selector):
        """readiness=None, label='yellow' -> signal=0."""
        snap = _snapshot(readiness=None, readiness_label="yellow")
        _, signals = selector._compute_composite_score(snap)
        assert signals["readiness"] == pytest.approx(0.0, abs=0.1)

    def test_red_label_fallback(self, selector):
        """readiness=None, label='red' -> signal=-60."""
        snap = _snapshot(readiness=None, readiness_label="red")
        _, signals = selector._compute_composite_score(snap)
        assert signals["readiness"] == pytest.approx(-60.0, abs=0.1)

    def test_no_score_no_label_is_none(self, selector):
        """readiness=None, label=None -> signal=None (not available)."""
        snap = _snapshot(readiness=None, readiness_label=None)
        _, signals = selector._compute_composite_score(snap)
        assert signals["readiness"] is None

    def test_score_overrides_label(self, selector):
        """readiness=30, label='red' -> uses score: (50-30)*2=40, NOT label."""
        snap = _snapshot(readiness=30, readiness_label="red")
        _, signals = selector._compute_composite_score(snap)
        assert signals["readiness"] == pytest.approx(40.0, abs=0.1)


# ===========================================================================
# 5. TestPanicOverride (PS-S01/S02) — 10 tests
# ===========================================================================

class TestPanicOverride:
    """PS-S01/S02: Panic override triggers 'skip' only when BOTH
    MRI > 80 AND F&G < 10. Both conditions must be met simultaneously.
    """

    @pytest.mark.parametrize(
        "mri, fear_greed, expect_skip, reason",
        [
            (85, 8, True, "PANIC_MARKET: both thresholds exceeded"),
            (81, 9, True, "barely over both thresholds"),
            (80, 9, False, "MRI must be > 80, not >= 80"),
            (81, 10, False, "F&G must be < 10, not <= 10"),
            (85, 25, False, "NEAR_PANIC_MRI_ONLY: F&G not low enough"),
            (60, 5, False, "NEAR_PANIC_FG_ONLY: MRI not high enough"),
            (None, 5, False, "MRI missing — cannot confirm panic"),
            (85, None, False, "F&G missing — cannot confirm panic"),
            (None, None, False, "both missing — no data, no panic"),
            (85, 5, True, "score=30 but panic overrides positive score"),
        ],
        ids=[
            "panic_market",
            "barely_over_both",
            "mri_80_not_skip",
            "fg_10_not_skip",
            "mri_only_high",
            "fg_only_low",
            "mri_missing",
            "fg_missing",
            "both_missing",
            "positive_score_overridden",
        ],
    )
    def test_panic_override(self, selector, mri, fear_greed, expect_skip, reason):
        """Panic override: MRI>80 AND F&G<10 -> skip regardless of score."""
        # Build a snapshot that would otherwise classify as something positive
        # (bullish regime + high confidence to get a positive composite score)
        snap = _snapshot(
            regime="bullish",
            regime_confidence=100,
            mri=mri,
            fear_greed=fear_greed,
        )
        # For the last case (positive score override), compute score to verify it's positive
        score, _ = selector._compute_composite_score(snap)

        result = selector._classify_condition(score, snap)

        if expect_skip:
            assert result == "skip", f"Expected skip: {reason}"
        else:
            assert result != "skip", f"Should NOT be skip: {reason}"


# ===========================================================================
# 6. TestPresetMapping (PS-C01/C02/C03) — 3 tests
# ===========================================================================

class TestPresetMapping:
    """PS-C01/C02/C03: Verify MARKET_CONDITIONS structure and
    contract with LEAPS_PRESETS catalog.
    """

    def test_market_conditions_structure(self, selector):
        """PS-C01: Every condition has the required keys."""
        required_keys = {"presets", "max_positions", "description"}
        for condition, mapping in MARKET_CONDITIONS.items():
            assert required_keys.issubset(mapping.keys()), (
                f"Condition '{condition}' missing keys: "
                f"{required_keys - set(mapping.keys())}"
            )
            assert isinstance(mapping["presets"], list)
            assert isinstance(mapping["max_positions"], int)
            assert isinstance(mapping["description"], str)

    def test_all_presets_exist_in_catalog(self, selector, monkeypatch):
        """PS-C02 (CONTRACT TEST): Every preset name referenced in
        MARKET_CONDITIONS must exist in LEAPS_PRESETS.

        This is the most critical contract test — if a preset is missing
        from the catalog, the screening engine will crash at runtime.
        """
        monkeypatch.setenv("PRESET_CATALOG_STRICT", "false")
        missing = []
        for condition, mapping in MARKET_CONDITIONS.items():
            for preset_name in mapping["presets"]:
                if preset_name not in LEAPS_PRESETS:
                    missing.append(f"{condition} -> {preset_name}")
        assert missing == [], f"Missing presets in catalog: {missing}"

    def test_all_conditions_are_classifiable(self, selector):
        """PS-C03: Every key in MARKET_CONDITIONS is reachable by
        _classify_condition (i.e., appears in the if/elif chain or
        as a panic override result).
        """
        # All conditions that can be returned by _classify_condition
        classifiable = set()
        # Score-based conditions (from thresholds)
        for condition in CONDITION_THRESHOLDS:
            classifiable.add(condition)
        # Below-defensive fallback
        classifiable.add("skip")

        for condition in MARKET_CONDITIONS:
            assert condition in classifiable, (
                f"Condition '{condition}' in MARKET_CONDITIONS is unreachable "
                f"by _classify_condition"
            )


# ===========================================================================
# 7. TestCacheBehavior (PS-INT01-04) — 4 async tests
# ===========================================================================

class TestCacheBehavior:
    """PS-INT01-04: Test _gather_market_snapshot reads from service caches.

    Note: _gather_market_snapshot uses lazy imports inside try blocks, so we
    must patch at the actual source module paths:
    - app.services.command_center.get_macro_signal_service
    - app.services.ai.market_regime.get_regime_detector
    - app.services.command_center.get_market_data_service
    - app.services.command_center.get_catalyst_service
    """

    @pytest.mark.asyncio
    async def test_all_cached_data(self, selector):
        """PS-INT01: All services return cached data -> fully populated snapshot."""
        with patch("app.services.command_center.get_macro_signal_service") as mock_mri_svc, \
             patch("app.services.ai.market_regime.get_regime_detector") as mock_regime, \
             patch("app.services.command_center.get_market_data_service") as mock_fg_svc, \
             patch("app.services.command_center.get_catalyst_service") as mock_cat_svc:

            # MRI cached
            mock_mri_svc.return_value.get_cached_mri.return_value = {
                "mri_score": 30,
                "regime": "moderate",
            }

            # Regime cached (fresh)
            detector = MagicMock()
            detector._cache = {"regime": "bullish", "risk_mode": "risk_on", "confidence": 85}
            detector._cache_time = datetime.now()  # fresh
            mock_regime.return_value = detector

            # F&G cached
            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = {"value": 65}
            mock_fg_svc.return_value = fg_svc

            # Readiness cached
            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = {
                "trade_readiness_score": 35,
                "readiness_label": "green",
            }
            mock_cat_svc.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())

            assert snapshot["mri"] == 30
            assert snapshot["regime"] == "bullish"
            assert snapshot["regime_confidence"] == 85
            assert snapshot["fear_greed"] == 65
            assert snapshot["readiness"] == 35
            assert snapshot["readiness_label"] == "green"

    @pytest.mark.asyncio
    async def test_all_services_empty(self, selector):
        """PS-INT02: All services return None/empty -> all None values."""
        with patch("app.services.command_center.get_macro_signal_service") as mock_mri_svc, \
             patch("app.services.ai.market_regime.get_regime_detector") as mock_regime, \
             patch("app.services.command_center.get_market_data_service") as mock_fg_svc, \
             patch("app.services.command_center.get_catalyst_service") as mock_cat_svc:

            mock_mri_svc.return_value.get_cached_mri.return_value = None

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            # No cache -> fresh fetch path
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {
                "regime": None,
                "risk_mode": None,
                "confidence": None,
            }
            mock_regime.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            mock_fg_svc.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            mock_cat_svc.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())

            assert snapshot["mri"] is None
            assert snapshot["regime"] is None
            assert snapshot["fear_greed"] is None
            assert snapshot["readiness"] is None

    @pytest.mark.asyncio
    async def test_mixed_availability(self, selector):
        """PS-INT03: Mixed — MRI cached, regime stale, F&G unavailable, readiness cached."""
        with patch("app.services.command_center.get_macro_signal_service") as mock_mri_svc, \
             patch("app.services.ai.market_regime.get_regime_detector") as mock_regime, \
             patch("app.services.command_center.get_market_data_service") as mock_fg_svc, \
             patch("app.services.command_center.get_catalyst_service") as mock_cat_svc:

            # MRI available
            mock_mri_svc.return_value.get_cached_mri.return_value = {
                "mri_score": 40,
                "regime": "moderate",
            }

            # Regime stale cache (>5 min) — triggers fresh fetch via asyncio.to_thread.
            # Use spec=None to avoid MagicMock spec issues with asyncio.to_thread.
            detector = MagicMock(spec=None)
            detector._cache = {"regime": "bullish", "risk_mode": "risk_on", "confidence": 60}
            detector._cache_time = datetime.now() - timedelta(minutes=10)  # stale
            # get_market_data must be a plain callable (not MagicMock with spec)
            # because asyncio.to_thread runs it in a thread executor.
            detector.get_market_data = lambda: {"spy": 500}
            detector.analyze_regime_rules = lambda data: {
                "regime": "neutral",
                "risk_mode": "neutral",
                "confidence": 55,
            }
            mock_regime.return_value = detector

            # F&G unavailable
            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            mock_fg_svc.return_value = fg_svc

            # Readiness available
            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = {
                "trade_readiness_score": 25,
                "readiness_label": "green",
            }
            mock_cat_svc.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())

            assert snapshot["mri"] == 40
            assert snapshot["regime"] == "neutral"  # fresh fetch
            assert snapshot["fear_greed"] is None
            assert snapshot["readiness"] == 25

    @pytest.mark.asyncio
    async def test_stale_regime_triggers_fresh_fetch(self, selector):
        """PS-INT04: Regime cache older than 5 min triggers fresh data fetch."""
        with patch("app.services.command_center.get_macro_signal_service") as mock_mri_svc, \
             patch("app.services.ai.market_regime.get_regime_detector") as mock_regime, \
             patch("app.services.command_center.get_market_data_service") as mock_fg_svc, \
             patch("app.services.command_center.get_catalyst_service") as mock_cat_svc:

            mock_mri_svc.return_value.get_cached_mri.return_value = None

            detector = MagicMock(spec=None)
            detector._cache = {"regime": "bullish", "confidence": 80}
            detector._cache_time = datetime.now() - timedelta(minutes=6)  # >5 min stale

            fresh_data = {"spy": 505, "vix": 18}
            detector.get_market_data = lambda: fresh_data
            detector.analyze_regime_rules = lambda data: {
                "regime": "bearish",
                "risk_mode": "risk_off",
                "confidence": 70,
            }
            mock_regime.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            mock_fg_svc.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            mock_cat_svc.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())

            # Should have used fresh data, not stale cache
            assert snapshot["regime"] == "bearish"
            assert snapshot["regime_confidence"] == 70


# ===========================================================================
# 8. TestFailureResilience (PS-R01-04) — 4 async tests
# ===========================================================================

class TestFailureResilience:
    """PS-R01-04: When individual services raise exceptions,
    _gather_market_snapshot catches them and continues with None values.
    """

    @pytest.mark.asyncio
    async def test_mri_service_raises(self, selector):
        """PS-R01: MRI service raises -> continues, MRI=None in snapshot."""
        with patch("app.services.command_center.get_macro_signal_service") as mock_mri_svc, \
             patch("app.services.ai.market_regime.get_regime_detector") as mock_regime, \
             patch("app.services.command_center.get_market_data_service") as mock_fg_svc, \
             patch("app.services.command_center.get_catalyst_service") as mock_cat_svc:

            mock_mri_svc.side_effect = RuntimeError("MRI service down")

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {
                "regime": "neutral", "risk_mode": "neutral", "confidence": 50
            }
            mock_regime.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = {"value": 50}
            mock_fg_svc.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            mock_cat_svc.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            assert snapshot["mri"] is None
            # Other services should still be populated
            assert snapshot["fear_greed"] == 50

    @pytest.mark.asyncio
    async def test_regime_detector_raises(self, selector):
        """PS-R02: Regime detector raises -> continues, regime=None."""
        with patch("app.services.command_center.get_macro_signal_service") as mock_mri_svc, \
             patch("app.services.ai.market_regime.get_regime_detector") as mock_regime, \
             patch("app.services.command_center.get_market_data_service") as mock_fg_svc, \
             patch("app.services.command_center.get_catalyst_service") as mock_cat_svc:

            mock_mri_svc.return_value.get_cached_mri.return_value = {"mri_score": 30, "regime": "low"}

            mock_regime.side_effect = RuntimeError("Regime detector crashed")

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = {"value": 60}
            mock_fg_svc.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            mock_cat_svc.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            assert snapshot["regime"] is None
            assert snapshot["mri"] == 30

    @pytest.mark.asyncio
    async def test_fear_greed_raises(self, selector):
        """PS-R03: F&G service raises -> continues, fear_greed=None."""
        with patch("app.services.command_center.get_macro_signal_service") as mock_mri_svc, \
             patch("app.services.ai.market_regime.get_regime_detector") as mock_regime, \
             patch("app.services.command_center.get_market_data_service") as mock_fg_svc, \
             patch("app.services.command_center.get_catalyst_service") as mock_cat_svc:

            mock_mri_svc.return_value.get_cached_mri.return_value = None

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {
                "regime": "bullish", "risk_mode": "risk_on", "confidence": 80
            }
            mock_regime.return_value = detector

            mock_fg_svc.side_effect = RuntimeError("CNN API down")

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = {
                "trade_readiness_score": 40, "readiness_label": "yellow"
            }
            mock_cat_svc.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            assert snapshot["fear_greed"] is None
            assert snapshot["readiness"] == 40

    @pytest.mark.asyncio
    async def test_all_services_raise(self, selector):
        """PS-R04: All services raise -> snapshot all None, score=0, condition=neutral."""
        with patch("app.services.command_center.get_macro_signal_service") as mock_mri_svc, \
             patch("app.services.ai.market_regime.get_regime_detector") as mock_regime, \
             patch("app.services.command_center.get_market_data_service") as mock_fg_svc, \
             patch("app.services.command_center.get_catalyst_service") as mock_cat_svc:

            mock_mri_svc.side_effect = RuntimeError("MRI down")
            mock_regime.side_effect = RuntimeError("Regime down")
            mock_fg_svc.side_effect = RuntimeError("F&G down")
            mock_cat_svc.side_effect = RuntimeError("Catalyst down")

            snapshot = await selector._gather_market_snapshot(MagicMock())

            assert snapshot["mri"] is None
            assert snapshot["regime"] is None
            assert snapshot["fear_greed"] is None
            assert snapshot["readiness"] is None

            # With all None, score should be 0.0 and condition neutral
            score, _ = selector._compute_composite_score(snapshot)
            condition = selector._classify_condition(score, snapshot)
            assert score == pytest.approx(0.0, abs=0.1)
            assert condition == "neutral"


# ===========================================================================
# 9. TestStability (PS-T01-03) — 3 tests
# ===========================================================================

class TestStability:
    """PS-T01-03: Determinism and stability of scoring."""

    def test_deterministic_output(self, selector):
        """PS-T01: Same input always produces the same score and condition."""
        results = []
        for _ in range(10):
            score, signals = selector._compute_composite_score(BULLISH_MARKET)
            condition = selector._classify_condition(score, BULLISH_MARKET)
            results.append((score, condition))

        # All iterations must produce identical results
        first = results[0]
        for i, r in enumerate(results[1:], start=1):
            assert r[0] == pytest.approx(first[0], abs=0.001), f"Score changed on iteration {i}"
            assert r[1] == first[1], f"Condition changed on iteration {i}"

    def test_near_boundary_consistency(self, selector):
        """PS-T02: Small score changes near a boundary produce consistent results."""
        # Score just above moderate_bull threshold
        snap_above = _snapshot(
            regime="bullish", regime_confidence=35,  # 80*0.35=28
        )
        score_above, _ = selector._compute_composite_score(snap_above)
        cond_above = selector._classify_condition(score_above, snap_above)

        # Score just below moderate_bull threshold
        snap_below = _snapshot(
            regime="bullish", regime_confidence=24,  # 80*0.24=19.2
        )
        score_below, _ = selector._compute_composite_score(snap_below)
        cond_below = selector._classify_condition(score_below, snap_below)

        # Verify the scores are on different sides of 20
        assert score_above >= 20.0
        assert score_below < 20.0
        assert cond_above == "moderate_bull"
        assert cond_below == "neutral"

    def test_hysteresis_not_yet_implemented(self, selector):
        """PS-T03: Hysteresis (smoothing transitions at boundaries) is not yet
        implemented. Document this as a known limitation.
        """
        pytest.skip(
            "Hysteresis not yet implemented — PresetSelector uses raw thresholds. "
            "Future work: add +/-2 point hysteresis band to prevent oscillation "
            "when composite score hovers near a boundary."
        )


# ===========================================================================
# 10. TestScoringMath (PS-M01-05) — 5 tests
# ===========================================================================

class TestScoringMath:
    """PS-M01-05: Exact scoring verification against hand-calculated values.

    Each test uses a specific mock snapshot and verifies the composite score
    matches the hand-verified expected value.
    """

    def test_bullish_market_score(self, selector):
        """PS-M01: BULLISH_MARKET composite ~53.6.

        regime=80*0.85=68, mri=(50-25)*2=50, fg=(72-50)*2=44, readiness=(50-30)*2=40
        composite = 0.35*68 + 0.30*50 + 0.20*44 + 0.15*40
                  = 23.8 + 15.0 + 8.8 + 6.0 = 53.6
        """
        score, signals = selector._compute_composite_score(BULLISH_MARKET)
        assert signals["regime"] == pytest.approx(68.0, abs=0.1)
        assert signals["mri"] == pytest.approx(50.0, abs=0.1)
        assert signals["fear_greed"] == pytest.approx(44.0, abs=0.1)
        assert signals["readiness"] == pytest.approx(40.0, abs=0.1)
        assert score == pytest.approx(53.6, abs=0.1)

    def test_max_bullish_score(self, selector):
        """PS-M02: MAX_BULLISH_MARKET composite ~93.0.

        regime=80*1.0=80, mri=(50-0)*2=100, fg=(100-50)*2=100, readiness=(50-0)*2=100
        composite = 0.35*80 + 0.30*100 + 0.20*100 + 0.15*100
                  = 28.0 + 30.0 + 20.0 + 15.0 = 93.0
        """
        score, signals = selector._compute_composite_score(MAX_BULLISH_MARKET)
        assert signals["regime"] == pytest.approx(80.0, abs=0.1)
        assert signals["mri"] == pytest.approx(100.0, abs=0.1)
        assert signals["fear_greed"] == pytest.approx(100.0, abs=0.1)
        assert signals["readiness"] == pytest.approx(100.0, abs=0.1)
        assert score == pytest.approx(93.0, abs=0.1)

    def test_max_bearish_score(self, selector):
        """PS-M03: MAX_BEARISH_MARKET composite ~-93.0.

        regime=-80*1.0=-80, mri=(50-100)*2=-100, fg=(0-50)*2=-100, readiness=(50-100)*2=-100
        composite = 0.35*(-80) + 0.30*(-100) + 0.20*(-100) + 0.15*(-100)
                  = -28.0 + -30.0 + -20.0 + -15.0 = -93.0
        """
        score, signals = selector._compute_composite_score(MAX_BEARISH_MARKET)
        assert signals["regime"] == pytest.approx(-80.0, abs=0.1)
        assert signals["mri"] == pytest.approx(-100.0, abs=0.1)
        assert signals["fear_greed"] == pytest.approx(-100.0, abs=0.1)
        assert signals["readiness"] == pytest.approx(-100.0, abs=0.1)
        assert score == pytest.approx(-93.0, abs=0.1)

    def test_neutral_market_score(self, selector):
        """PS-M04: NEUTRAL_MARKET composite ~3.0.

        regime=0*0.6=0, mri=(50-45)*2=10, fg=(50-50)*2=0, readiness=(50-50)*2=0
        composite = 0.35*0 + 0.30*10 + 0.20*0 + 0.15*0
                  = 0 + 3.0 + 0 + 0 = 3.0
        """
        score, signals = selector._compute_composite_score(NEUTRAL_MARKET)
        assert signals["regime"] == pytest.approx(0.0, abs=0.1)
        assert signals["mri"] == pytest.approx(10.0, abs=0.1)
        assert signals["fear_greed"] == pytest.approx(0.0, abs=0.1)
        assert signals["readiness"] == pytest.approx(0.0, abs=0.1)
        assert score == pytest.approx(3.0, abs=0.1)

    def test_boundary_aggressive_score(self, selector):
        """PS-M05: BOUNDARY_AGGRESSIVE composite = 50.0 exactly.

        Only regime available: bullish * 0.625 = 50.0
        Weight renormalized: 0.35 / 0.35 = 1.0
        composite = 50.0 * 1.0 = 50.0
        """
        score, signals = selector._compute_composite_score(BOUNDARY_AGGRESSIVE)
        assert signals["regime"] == pytest.approx(50.0, abs=0.1)
        assert signals["mri"] is None
        assert signals["fear_greed"] is None
        assert signals["readiness"] is None
        assert score == pytest.approx(50.0, abs=0.1)

        # Verify this hits aggressive_bull threshold exactly
        condition = selector._classify_condition(score, BOUNDARY_AGGRESSIVE)
        assert condition == "aggressive_bull"


# ===========================================================================
# 11. TestReasoningOutput (PS-O01-03) — 3 tests
# ===========================================================================

class TestReasoningOutput:
    """PS-O01-03: Verify _build_reasoning produces human-readable explanations
    containing key information.
    """

    def test_reasoning_contains_description(self, selector):
        """PS-O01: Reasoning string includes the condition's description."""
        score, signals = selector._compute_composite_score(BULLISH_MARKET)
        condition = selector._classify_condition(score, BULLISH_MARKET)
        reasoning = selector._build_reasoning(condition, score, signals, BULLISH_MARKET)

        expected_desc = MARKET_CONDITIONS[condition]["description"]
        assert expected_desc in reasoning, (
            f"Reasoning missing description '{expected_desc}': {reasoning}"
        )

    def test_reasoning_contains_composite_score(self, selector):
        """PS-O02: Reasoning string includes the composite score value."""
        score, signals = selector._compute_composite_score(BEARISH_MARKET)
        condition = selector._classify_condition(score, BEARISH_MARKET)
        reasoning = selector._build_reasoning(condition, score, signals, BEARISH_MARKET)

        # Score is formatted as "+X.Y" or "-X.Y" in the reasoning
        assert "Composite:" in reasoning
        # Verify the numeric value appears (formatted to 1 decimal)
        score_str = f"{score:+.1f}"
        assert score_str in reasoning, (
            f"Reasoning missing score '{score_str}': {reasoning}"
        )

    def test_reasoning_contains_signal_labels(self, selector):
        """PS-O03: Reasoning includes signal component labels (F&G, MRI, etc.)."""
        score, signals = selector._compute_composite_score(BULLISH_MARKET)
        condition = selector._classify_condition(score, BULLISH_MARKET)
        reasoning = selector._build_reasoning(condition, score, signals, BULLISH_MARKET)

        # Should mention key signal sources
        assert "Regime:" in reasoning
        assert "MRI:" in reasoning
        assert "F&G:" in reasoning
        assert "Readiness:" in reasoning

    def test_reasoning_fg_unavailable(self, selector):
        """Reasoning gracefully handles missing F&G."""
        score, signals = selector._compute_composite_score(PARTIAL_DATA_MARKET)
        condition = selector._classify_condition(score, PARTIAL_DATA_MARKET)
        reasoning = selector._build_reasoning(condition, score, signals, PARTIAL_DATA_MARKET)

        assert "F&G: unavailable" in reasoning


# ===========================================================================
# 12. TestEdgeCases (PS-E01-07) — 7 tests
# ===========================================================================

class TestEdgeCases:
    """PS-E01-07: Edge cases, boundary values, and documented quirks."""

    def test_mri_midpoint_is_zero(self, selector):
        """PS-E01: MRI=50 -> signal=(50-50)*2=0 (exact midpoint)."""
        snap = _snapshot(mri=50)
        _, signals = selector._compute_composite_score(snap)
        assert signals["mri"] == pytest.approx(0.0, abs=0.1)

    def test_fg_midpoint_is_zero(self, selector):
        """PS-E02: F&G=50 -> signal=(50-50)*2=0 (exact midpoint)."""
        snap = _snapshot(fear_greed=50)
        _, signals = selector._compute_composite_score(snap)
        assert signals["fear_greed"] == pytest.approx(0.0, abs=0.1)

    def test_readiness_midpoint_is_zero(self, selector):
        """PS-E03: Readiness=50 -> signal=(50-50)*2=0 (exact midpoint)."""
        snap = _snapshot(readiness=50)
        _, signals = selector._compute_composite_score(snap)
        assert signals["readiness"] == pytest.approx(0.0, abs=0.1)

    def test_negative_confidence_flips_signal(self, selector):
        """PS-E04: Negative confidence (e.g., -10) -> multiplier = min(-10/100, 1.0) = -0.1.

        DOCUMENTED QUIRK: The formula min(confidence/100, 1.0) does NOT clamp
        negative values. A negative confidence inverts the regime signal direction.
        This is mathematically correct per the formula but semantically questionable.
        A future fix could clamp confidence to max(0, min(confidence/100, 1.0)).
        """
        snap = _snapshot(regime="bullish", regime_confidence=-10)
        _, signals = selector._compute_composite_score(snap)
        # min(-10/100, 1.0) = min(-0.1, 1.0) = -0.1
        # signal = 80 * (-0.1) = -8.0 (bullish signal becomes slightly bearish!)
        assert signals["regime"] == pytest.approx(-8.0, abs=0.1)

    def test_extreme_mri_no_clamping(self, selector):
        """PS-E05: MRI=200 -> signal=(50-200)*2=-300 (no clamping to -100).

        DOCUMENTED QUIRK: The MRI normalization formula (50-mri)*2 does not
        clamp to the -100/+100 range. Extreme MRI values produce signals
        outside the expected range. This can cause composite scores beyond
        the nominal -100 to +100 range when MRI is the only available signal.
        """
        snap = _snapshot(mri=200)
        _, signals = selector._compute_composite_score(snap)
        assert signals["mri"] == pytest.approx(-300.0, abs=0.1)

    def test_selector_version_is_string(self, selector):
        """PS-E06: SELECTOR_VERSION constant exists and is a string."""
        assert isinstance(SELECTOR_VERSION, str)
        assert len(SELECTOR_VERSION) > 0
        # Should follow semver-ish pattern (X.Y.Z)
        parts = SELECTOR_VERSION.split(".")
        assert len(parts) >= 2, f"Version should be semver: {SELECTOR_VERSION}"

    def test_catalog_hash_consistent(self, selector):
        """PS-E07: get_catalog_hash() returns consistent 8-char hex string."""
        hash1 = get_catalog_hash()
        hash2 = get_catalog_hash()

        assert hash1 == hash2, "Catalog hash should be deterministic"
        assert len(hash1) == 8, f"Expected 8 chars, got {len(hash1)}: {hash1}"
        # Verify it's valid hex
        int(hash1, 16)  # raises ValueError if not valid hex


# ===========================================================================
# Additional verification: BEARISH and PANIC hand-calculated scores
# ===========================================================================

class TestAdditionalScoringVerification:
    """Verify composite scores for remaining mock snapshots."""

    def test_moderate_bull_score(self, selector):
        """MODERATE_BULL: regime=80*0.70=56, mri=(50-35)*2=30, fg=(55-50)*2=10,
        readiness=(50-40)*2=20. composite = 0.35*56 + 0.30*30 + 0.20*10 + 0.15*20
        = 19.6 + 9.0 + 2.0 + 3.0 = 33.6
        """
        score, signals = selector._compute_composite_score(MODERATE_BULL_MARKET)
        assert signals["regime"] == pytest.approx(56.0, abs=0.1)
        assert signals["mri"] == pytest.approx(30.0, abs=0.1)
        assert signals["fear_greed"] == pytest.approx(10.0, abs=0.1)
        assert signals["readiness"] == pytest.approx(20.0, abs=0.1)
        assert score == pytest.approx(33.6, abs=0.1)

    def test_bearish_market_score(self, selector):
        """BEARISH: regime=-80*0.80=-64, mri=(50-70)*2=-40, fg=(22-50)*2=-56,
        readiness=(50-70)*2=-40. composite = 0.35*(-64) + 0.30*(-40) + 0.20*(-56) + 0.15*(-40)
        = -22.4 + -12.0 + -11.2 + -6.0 = -51.6
        """
        score, signals = selector._compute_composite_score(BEARISH_MARKET)
        assert signals["regime"] == pytest.approx(-64.0, abs=0.1)
        assert signals["mri"] == pytest.approx(-40.0, abs=0.1)
        assert signals["fear_greed"] == pytest.approx(-56.0, abs=0.1)
        assert signals["readiness"] == pytest.approx(-40.0, abs=0.1)
        assert score == pytest.approx(-51.6, abs=0.1)

    def test_panic_market_score(self, selector):
        """PANIC: regime=-80*0.95=-76, mri=(50-85)*2=-70, fg=(8-50)*2=-84,
        readiness=(50-90)*2=-80. composite = 0.35*(-76) + 0.30*(-70) + 0.20*(-84) + 0.15*(-80)
        = -26.6 + -21.0 + -16.8 + -12.0 = -76.4
        """
        score, signals = selector._compute_composite_score(PANIC_MARKET)
        assert signals["regime"] == pytest.approx(-76.0, abs=0.1)
        assert signals["mri"] == pytest.approx(-70.0, abs=0.1)
        assert signals["fear_greed"] == pytest.approx(-84.0, abs=0.1)
        assert signals["readiness"] == pytest.approx(-80.0, abs=0.1)
        assert score == pytest.approx(-76.4, abs=0.1)

    def test_partial_data_only_regime(self, selector):
        """PARTIAL_DATA: only regime available (bullish, conf=75).
        regime=80*0.75=60, others None.
        available_weight=0.35, renormalized=1.0, composite=60.0
        """
        score, signals = selector._compute_composite_score(PARTIAL_DATA_MARKET)
        assert signals["regime"] == pytest.approx(60.0, abs=0.1)
        assert signals["mri"] is None
        assert signals["fear_greed"] is None
        assert signals["readiness"] is None
        assert score == pytest.approx(60.0, abs=0.1)

    def test_all_missing_score_zero(self, selector):
        """ALL_MISSING: all signals None -> composite=0.0, condition=neutral."""
        score, signals = selector._compute_composite_score(ALL_MISSING_MARKET)
        assert signals["regime"] is None
        assert signals["mri"] is None
        assert signals["fear_greed"] is None
        assert signals["readiness"] is None
        assert score == pytest.approx(0.0, abs=0.1)
        condition = selector._classify_condition(score, ALL_MISSING_MARKET)
        assert condition == "neutral"

    def test_label_fallback_snapshots(self, selector):
        """Verify LABEL_FALLBACK_* snapshots produce expected readiness signals."""
        _, sig_green = selector._compute_composite_score(LABEL_FALLBACK_GREEN)
        assert sig_green["readiness"] == pytest.approx(60.0, abs=0.1)

        _, sig_yellow = selector._compute_composite_score(LABEL_FALLBACK_YELLOW)
        assert sig_yellow["readiness"] == pytest.approx(0.0, abs=0.1)

        _, sig_red = selector._compute_composite_score(LABEL_FALLBACK_RED)
        assert sig_red["readiness"] == pytest.approx(-60.0, abs=0.1)

    def test_near_panic_no_panic_override(self, selector):
        """NEAR_PANIC_MRI_ONLY and NEAR_PANIC_FG_ONLY do NOT trigger panic override.

        Note: These snapshots may still classify as 'skip' due to their very
        negative composite scores (below -50). The key assertion is that panic
        override is not the reason — it is score-based classification.

        To verify no panic override, we test with a positive score and the same
        MRI/F&G values that fail the panic conditions individually.
        """
        # MRI=85 alone (F&G=25 > 10) should NOT trigger panic override
        snap_mri = _snapshot(
            regime="bullish", regime_confidence=100,  # strong bullish to get positive score
            mri=85, fear_greed=25,
        )
        score_mri, _ = selector._compute_composite_score(snap_mri)
        cond_mri = selector._classify_condition(score_mri, snap_mri)
        # With bullish regime pulling score up, condition depends on score, not panic
        assert cond_mri != "skip" or score_mri < -50, (
            "If skip, it must be score-based, not panic override "
            "(F&G=25 > 10, so panic override should not fire)"
        )

        # F&G=5 alone (MRI=60 < 80) should NOT trigger panic override
        snap_fg = _snapshot(
            regime="bullish", regime_confidence=100,
            mri=60, fear_greed=5,
        )
        score_fg, _ = selector._compute_composite_score(snap_fg)
        cond_fg = selector._classify_condition(score_fg, snap_fg)
        assert cond_fg != "skip" or score_fg < -50, (
            "If skip, it must be score-based, not panic override "
            "(MRI=60 < 80, so panic override should not fire)"
        )


# ===========================================================================
# Classification integration: verify each snapshot maps to expected condition
# ===========================================================================

class TestClassificationIntegration:
    """End-to-end: snapshot -> score -> condition for each mock market."""

    def test_bullish_is_aggressive(self, selector):
        """BULLISH_MARKET (score ~53.6) -> aggressive_bull."""
        score, _ = selector._compute_composite_score(BULLISH_MARKET)
        assert selector._classify_condition(score, BULLISH_MARKET) == "aggressive_bull"

    def test_moderate_bull_is_moderate(self, selector):
        """MODERATE_BULL (score ~33.6) -> moderate_bull."""
        score, _ = selector._compute_composite_score(MODERATE_BULL_MARKET)
        assert selector._classify_condition(score, MODERATE_BULL_MARKET) == "moderate_bull"

    def test_neutral_is_neutral(self, selector):
        """NEUTRAL_MARKET (score ~3.0) -> neutral."""
        score, _ = selector._compute_composite_score(NEUTRAL_MARKET)
        assert selector._classify_condition(score, NEUTRAL_MARKET) == "neutral"

    def test_bearish_is_skip(self, selector):
        """BEARISH_MARKET (score ~-51.6) -> skip (below -50)."""
        score, _ = selector._compute_composite_score(BEARISH_MARKET)
        assert selector._classify_condition(score, BEARISH_MARKET) == "skip"

    def test_panic_is_skip(self, selector):
        """PANIC_MARKET -> skip (both panic override AND score < -50)."""
        score, _ = selector._compute_composite_score(PANIC_MARKET)
        assert selector._classify_condition(score, PANIC_MARKET) == "skip"

    def test_partial_data_is_aggressive(self, selector):
        """PARTIAL_DATA (score ~60.0) -> aggressive_bull."""
        score, _ = selector._compute_composite_score(PARTIAL_DATA_MARKET)
        assert selector._classify_condition(score, PARTIAL_DATA_MARKET) == "aggressive_bull"

    def test_all_missing_is_neutral(self, selector):
        """ALL_MISSING (score=0.0) -> neutral."""
        score, _ = selector._compute_composite_score(ALL_MISSING_MARKET)
        assert selector._classify_condition(score, ALL_MISSING_MARKET) == "neutral"

    def test_max_bullish_is_aggressive(self, selector):
        """MAX_BULLISH (score ~93.0) -> aggressive_bull."""
        score, _ = selector._compute_composite_score(MAX_BULLISH_MARKET)
        assert selector._classify_condition(score, MAX_BULLISH_MARKET) == "aggressive_bull"

    def test_max_bearish_is_skip(self, selector):
        """MAX_BEARISH (score ~-93.0) -> skip."""
        score, _ = selector._compute_composite_score(MAX_BEARISH_MARKET)
        assert selector._classify_condition(score, MAX_BEARISH_MARKET) == "skip"


# ===========================================================================
# 14. TestSelectPresetsE2E (PS-E2E01-05) — 5 async end-to-end tests
# ===========================================================================

class TestSelectPresetsE2E:
    """PS-E2E01-05: Test the main select_presets() async orchestrator end-to-end.

    This is the ONLY public method — everything else is internal. Tests verify:
    - Full result structure with all required keys
    - Version breadcrumbs (selector_version, catalog_hash)
    - Correct condition → preset mapping in the result
    - Behavior with fully populated vs. fully degraded market data
    """

    def _mock_all_services(self, mock_mri_svc, mock_regime, mock_fg_svc, mock_cat_svc,
                           mri_data=None, regime_cache=None, fg_value=None, readiness_data=None):
        """Helper to set up all 4 service mocks with configurable return data."""
        # MRI
        mock_mri_svc.return_value.get_cached_mri.return_value = mri_data

        # Regime
        detector = MagicMock()
        if regime_cache:
            detector._cache = regime_cache
            detector._cache_time = datetime.now()  # fresh cache
        else:
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {
                "regime": None, "risk_mode": None, "confidence": None
            }
        mock_regime.return_value = detector

        # F&G
        fg_svc = AsyncMock()
        fg_svc.get_fear_greed_index.return_value = {"value": fg_value} if fg_value is not None else None
        mock_fg_svc.return_value = fg_svc

        # Readiness
        cat_svc = AsyncMock()
        cat_svc.calculate_trade_readiness.return_value = readiness_data
        mock_cat_svc.return_value = cat_svc

    @pytest.mark.asyncio
    async def test_result_has_all_required_keys(self, selector):
        """PS-E2E01: select_presets() returns dict with all required keys."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            self._mock_all_services(m1, m2, m3, m4,
                mri_data={"mri_score": 25, "regime": "low_risk"},
                regime_cache={"regime": "bullish", "risk_mode": "risk_on", "confidence": 85},
                fg_value=72,
                readiness_data={"trade_readiness_score": 30, "readiness_label": "green"},
            )

            result = await selector.select_presets(MagicMock())

            required_keys = {"condition", "presets", "max_positions", "reasoning",
                           "market_snapshot", "selector_version", "catalog_hash"}
            assert required_keys.issubset(result.keys()), (
                f"Missing keys: {required_keys - set(result.keys())}"
            )

    @pytest.mark.asyncio
    async def test_version_breadcrumbs_populated(self, selector):
        """PS-E2E02: select_presets() includes correct version breadcrumbs."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            self._mock_all_services(m1, m2, m3, m4)

            result = await selector.select_presets(MagicMock())

            assert result["selector_version"] == SELECTOR_VERSION
            assert isinstance(result["catalog_hash"], str)
            assert len(result["catalog_hash"]) == 8

    @pytest.mark.asyncio
    async def test_bullish_market_returns_aggressive_presets(self, selector):
        """PS-E2E03: Bullish market → aggressive_bull condition with correct presets."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            self._mock_all_services(m1, m2, m3, m4,
                mri_data={"mri_score": 25, "regime": "low_risk"},
                regime_cache={"regime": "bullish", "risk_mode": "risk_on", "confidence": 85},
                fg_value=72,
                readiness_data={"trade_readiness_score": 30, "readiness_label": "green"},
            )

            result = await selector.select_presets(MagicMock())

            assert result["condition"] == "aggressive_bull"
            assert result["presets"] == MARKET_CONDITIONS["aggressive_bull"]["presets"]
            assert result["max_positions"] == MARKET_CONDITIONS["aggressive_bull"]["max_positions"]

    @pytest.mark.asyncio
    async def test_all_services_down_returns_neutral(self, selector):
        """PS-E2E04: All services failing → neutral condition (score=0)."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            m1.side_effect = RuntimeError("down")
            m2.side_effect = RuntimeError("down")
            m3.side_effect = RuntimeError("down")
            m4.side_effect = RuntimeError("down")

            result = await selector.select_presets(MagicMock())

            assert result["condition"] == "neutral"
            assert result["presets"] == MARKET_CONDITIONS["neutral"]["presets"]
            assert result["market_snapshot"]["composite_score"] == 0.0

    @pytest.mark.asyncio
    async def test_snapshot_includes_composite_score(self, selector):
        """PS-E2E05: market_snapshot in result includes composite_score field."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            self._mock_all_services(m1, m2, m3, m4,
                mri_data={"mri_score": 25, "regime": "low_risk"},
                regime_cache={"regime": "bullish", "risk_mode": "risk_on", "confidence": 85},
                fg_value=72,
                readiness_data={"trade_readiness_score": 30, "readiness_label": "green"},
            )

            result = await selector.select_presets(MagicMock())

            assert "composite_score" in result["market_snapshot"]
            # Should be rounded to 1 decimal
            cs = result["market_snapshot"]["composite_score"]
            assert cs == round(cs, 1)
            # For this bullish setup, score should be ~53.6
            assert cs == pytest.approx(53.6, abs=1.0)


# ===========================================================================
# 15. TestValidatePresetCatalog (PS-VAL01-06) — 6 tests
# ===========================================================================

class TestValidatePresetCatalog:
    """PS-VAL01-06: Test _validate_preset_catalog() startup validation.

    Tests strict mode, non-strict mode, idempotency, and error handling.
    """

    def test_validation_passes_with_current_catalog(self, monkeypatch):
        """PS-VAL01: Current MARKET_CONDITIONS + LEAPS_PRESETS should pass validation."""
        import app.services.automation.preset_selector as ps_module
        # Reset validation flag
        monkeypatch.setattr(ps_module, "_catalog_validated", False)
        monkeypatch.setenv("PRESET_CATALOG_STRICT", "true")

        # Should NOT raise — all preset names exist
        ps_module._validate_preset_catalog()
        assert ps_module._catalog_validated is True

    def test_strict_mode_raises_on_missing_preset(self, monkeypatch):
        """PS-VAL02: Strict mode raises ValueError when a preset name is missing."""
        import app.services.automation.preset_selector as ps_module
        monkeypatch.setattr(ps_module, "_catalog_validated", False)
        monkeypatch.setenv("PRESET_CATALOG_STRICT", "true")

        # Temporarily add a bad preset name to MARKET_CONDITIONS
        original = MARKET_CONDITIONS["neutral"]["presets"].copy()
        MARKET_CONDITIONS["neutral"]["presets"] = ["nonexistent_preset_xyz"]
        try:
            with pytest.raises(ValueError, match="MISSING PRESETS"):
                ps_module._validate_preset_catalog()
        finally:
            MARKET_CONDITIONS["neutral"]["presets"] = original
            monkeypatch.setattr(ps_module, "_catalog_validated", False)

    def test_non_strict_mode_logs_error_on_missing_preset(self, monkeypatch, caplog):
        """PS-VAL03: Non-strict mode logs error but doesn't raise."""
        import app.services.automation.preset_selector as ps_module
        monkeypatch.setattr(ps_module, "_catalog_validated", False)
        monkeypatch.setenv("PRESET_CATALOG_STRICT", "false")

        original = MARKET_CONDITIONS["neutral"]["presets"].copy()
        MARKET_CONDITIONS["neutral"]["presets"] = ["nonexistent_preset_abc"]
        try:
            # Should NOT raise
            ps_module._validate_preset_catalog()
            assert ps_module._catalog_validated is True
        finally:
            MARKET_CONDITIONS["neutral"]["presets"] = original
            monkeypatch.setattr(ps_module, "_catalog_validated", False)

    def test_validation_is_idempotent(self, monkeypatch):
        """PS-VAL04: Calling _validate_preset_catalog() twice only validates once."""
        import app.services.automation.preset_selector as ps_module
        monkeypatch.setattr(ps_module, "_catalog_validated", False)
        monkeypatch.setenv("PRESET_CATALOG_STRICT", "true")

        ps_module._validate_preset_catalog()
        assert ps_module._catalog_validated is True

        # Second call should be a no-op (flag already True)
        ps_module._validate_preset_catalog()
        assert ps_module._catalog_validated is True

    def test_validation_handles_import_error(self, monkeypatch):
        """PS-VAL05: If presets_catalog can't be imported, validation logs warning."""
        import app.services.automation.preset_selector as ps_module
        monkeypatch.setattr(ps_module, "_catalog_validated", False)

        # Patch the import to fail
        with patch.dict("sys.modules", {"app.data.presets_catalog": None}):
            # Monkey-patch the import inside the function
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

            def fake_import(name, *args, **kwargs):
                if name == "app.data.presets_catalog":
                    raise ImportError("Fake import error")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=fake_import):
                # Should NOT raise, but should set _catalog_validated = True
                ps_module._validate_preset_catalog()
                assert ps_module._catalog_validated is True

    def test_strict_env_var_default_is_true(self, monkeypatch):
        """PS-VAL06: Without PRESET_CATALOG_STRICT env var, default behavior is strict."""
        import app.services.automation.preset_selector as ps_module
        monkeypatch.setattr(ps_module, "_catalog_validated", False)
        monkeypatch.delenv("PRESET_CATALOG_STRICT", raising=False)

        # With current valid catalog, it should pass even in strict mode
        ps_module._validate_preset_catalog()
        assert ps_module._catalog_validated is True


# ===========================================================================
# 16. TestGetPresetSelectorSingleton (PS-SNG01-03) — 3 tests
# ===========================================================================

class TestGetPresetSelectorSingleton:
    """PS-SNG01-03: Test the get_preset_selector() singleton factory."""

    def test_returns_preset_selector_instance(self, monkeypatch):
        """PS-SNG01: get_preset_selector() returns a PresetSelector instance."""
        import app.services.automation.preset_selector as ps_module
        monkeypatch.setattr(ps_module, "_preset_selector", None)
        monkeypatch.setattr(ps_module, "_catalog_validated", False)
        monkeypatch.setenv("PRESET_CATALOG_STRICT", "true")

        from app.services.automation.preset_selector import get_preset_selector
        instance = get_preset_selector()
        assert isinstance(instance, PresetSelector)

    def test_returns_same_instance_on_second_call(self, monkeypatch):
        """PS-SNG02: Second call returns the exact same object (singleton)."""
        import app.services.automation.preset_selector as ps_module
        monkeypatch.setattr(ps_module, "_preset_selector", None)
        monkeypatch.setattr(ps_module, "_catalog_validated", False)
        monkeypatch.setenv("PRESET_CATALOG_STRICT", "true")

        from app.services.automation.preset_selector import get_preset_selector
        first = get_preset_selector()
        second = get_preset_selector()
        assert first is second

    def test_triggers_validation_on_first_call(self, monkeypatch):
        """PS-SNG03: First call triggers _validate_preset_catalog()."""
        import app.services.automation.preset_selector as ps_module
        monkeypatch.setattr(ps_module, "_preset_selector", None)
        monkeypatch.setattr(ps_module, "_catalog_validated", False)
        monkeypatch.setenv("PRESET_CATALOG_STRICT", "true")

        from app.services.automation.preset_selector import get_preset_selector
        assert ps_module._catalog_validated is False

        get_preset_selector()
        assert ps_module._catalog_validated is True


# ===========================================================================
# 17. TestGatherSnapshotEdgeCases (PS-GMS01-08) — 8 async tests
# ===========================================================================

class TestGatherSnapshotEdgeCases:
    """PS-GMS01-08: Edge cases for _gather_market_snapshot() service interactions.

    Covers partial return dicts, empty dicts, no-cache paths, and the
    asyncio.to_thread coroutine check.
    """

    @pytest.mark.asyncio
    async def test_mri_returns_dict_without_mri_score_key(self, selector):
        """PS-GMS01: MRI service returns dict but without 'mri_score' key → mri=None."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            # MRI returns dict without mri_score
            m1.return_value.get_cached_mri.return_value = {"regime": "low_risk"}

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {"regime": None, "risk_mode": None, "confidence": None}
            m2.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            m3.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            m4.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            # .get("mri_score") returns None when key is missing
            assert snapshot["mri"] is None
            assert snapshot["mri_regime"] == "low_risk"

    @pytest.mark.asyncio
    async def test_mri_returns_empty_dict(self, selector):
        """PS-GMS02: MRI service returns {} → mri=None, mri_regime=None."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            m1.return_value.get_cached_mri.return_value = {}

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {"regime": None, "risk_mode": None, "confidence": None}
            m2.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            m3.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            m4.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            # Empty dict is truthy, so the `if mri_data:` check passes,
            # but .get() returns None for missing keys
            assert snapshot["mri"] is None
            assert snapshot["mri_regime"] is None

    @pytest.mark.asyncio
    async def test_fg_returns_dict_without_value_key(self, selector):
        """PS-GMS03: F&G service returns dict without 'value' key → fear_greed=None."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            m1.return_value.get_cached_mri.return_value = None

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {"regime": None, "risk_mode": None, "confidence": None}
            m2.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = {"timestamp": "2026-02-14"}  # no "value" key
            m3.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            m4.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            assert snapshot["fear_greed"] is None

    @pytest.mark.asyncio
    async def test_fg_returns_empty_dict(self, selector):
        """PS-GMS04: F&G service returns {} → fear_greed=None."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            m1.return_value.get_cached_mri.return_value = None

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {"regime": None, "risk_mode": None, "confidence": None}
            m2.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = {}
            m3.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            m4.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            # Empty dict is truthy, `fg_data.get("value")` returns None
            assert snapshot["fear_greed"] is None

    @pytest.mark.asyncio
    async def test_readiness_returns_only_score_no_label(self, selector):
        """PS-GMS05: Readiness returns score but no label → readiness set, label=None."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            m1.return_value.get_cached_mri.return_value = None

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {"regime": None, "risk_mode": None, "confidence": None}
            m2.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            m3.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = {
                "trade_readiness_score": 40,
                # No "readiness_label" key
            }
            m4.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            assert snapshot["readiness"] == 40
            assert snapshot["readiness_label"] is None

    @pytest.mark.asyncio
    async def test_readiness_returns_only_label_no_score(self, selector):
        """PS-GMS06: Readiness returns label but no score → readiness=None, label set."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            m1.return_value.get_cached_mri.return_value = None

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {"regime": None, "risk_mode": None, "confidence": None}
            m2.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            m3.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = {
                "readiness_label": "yellow",
                # No "trade_readiness_score" key
            }
            m4.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            assert snapshot["readiness"] is None
            assert snapshot["readiness_label"] == "yellow"

    @pytest.mark.asyncio
    async def test_readiness_returns_empty_dict(self, selector):
        """PS-GMS07: Readiness returns {} → both None."""
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            m1.return_value.get_cached_mri.return_value = None

            detector = MagicMock()
            detector._cache = None
            detector._cache_time = None
            detector.get_market_data = AsyncMock(return_value={})
            detector.analyze_regime_rules.return_value = {"regime": None, "risk_mode": None, "confidence": None}
            m2.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            m3.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = {}
            m4.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())
            # Empty dict is truthy but .get() returns None
            assert snapshot["readiness"] is None
            assert snapshot["readiness_label"] is None

    @pytest.mark.asyncio
    async def test_no_cache_no_cache_time_uses_direct_await(self, selector):
        """PS-GMS08: When detector has no cache AND no cache_time, takes
        the 'else' branch (line 176) and calls await detector.get_market_data().
        """
        with patch("app.services.command_center.get_macro_signal_service") as m1, \
             patch("app.services.ai.market_regime.get_regime_detector") as m2, \
             patch("app.services.command_center.get_market_data_service") as m3, \
             patch("app.services.command_center.get_catalyst_service") as m4:

            m1.return_value.get_cached_mri.return_value = None

            detector = MagicMock()
            detector._cache = None     # No cache
            detector._cache_time = None  # No cache time
            # This path does: await detector.get_market_data() — must be AsyncMock
            detector.get_market_data = AsyncMock(return_value={"spy": 500, "vix": 15})
            detector.analyze_regime_rules.return_value = {
                "regime": "bullish",
                "risk_mode": "risk_on",
                "confidence": 90,
            }
            m2.return_value = detector

            fg_svc = AsyncMock()
            fg_svc.get_fear_greed_index.return_value = None
            m3.return_value = fg_svc

            cat_svc = AsyncMock()
            cat_svc.calculate_trade_readiness.return_value = None
            m4.return_value = cat_svc

            snapshot = await selector._gather_market_snapshot(MagicMock())

            # Should have used fresh fetch path (no cache)
            assert snapshot["regime"] == "bullish"
            assert snapshot["regime_confidence"] == 90
            # Verify get_market_data was actually awaited
            detector.get_market_data.assert_awaited_once()


# ===========================================================================
# 18. TestBuildReasoningEdgeCases (PS-BR01-06) — 6 tests
# ===========================================================================

class TestBuildReasoningEdgeCases:
    """PS-BR01-06: Edge cases for _build_reasoning() formatting.

    Covers boundary F&G labels (fear/neutral/greed), missing signal formatting,
    and unknown label fallbacks.
    """

    def test_fg_exactly_30_is_neutral(self, selector):
        """PS-BR01: F&G=30 → label should be 'neutral' (not 'fear', which requires < 30)."""
        snap = _snapshot(fear_greed=30, regime="neutral", regime_confidence=50, mri=50, readiness=50)
        score, signals = selector._compute_composite_score(snap)
        condition = selector._classify_condition(score, snap)
        reasoning = selector._build_reasoning(condition, score, signals, snap)

        assert "F&G: 30 (neutral)" in reasoning

    def test_fg_29_is_fear(self, selector):
        """PS-BR02: F&G=29 → label should be 'fear' (< 30)."""
        snap = _snapshot(fear_greed=29, regime="neutral", regime_confidence=50, mri=50, readiness=50)
        score, signals = selector._compute_composite_score(snap)
        condition = selector._classify_condition(score, snap)
        reasoning = selector._build_reasoning(condition, score, signals, snap)

        assert "F&G: 29 (fear)" in reasoning

    def test_fg_exactly_70_is_neutral(self, selector):
        """PS-BR03: F&G=70 → label should be 'neutral' (not 'greed', which requires > 70)."""
        snap = _snapshot(fear_greed=70, regime="neutral", regime_confidence=50, mri=50, readiness=50)
        score, signals = selector._compute_composite_score(snap)
        condition = selector._classify_condition(score, snap)
        reasoning = selector._build_reasoning(condition, score, signals, snap)

        assert "F&G: 70 (neutral)" in reasoning

    def test_fg_71_is_greed(self, selector):
        """PS-BR04: F&G=71 → label should be 'greed' (> 70)."""
        snap = _snapshot(fear_greed=71, regime="neutral", regime_confidence=50, mri=50, readiness=50)
        score, signals = selector._compute_composite_score(snap)
        condition = selector._classify_condition(score, snap)
        reasoning = selector._build_reasoning(condition, score, signals, snap)

        assert "F&G: 71 (greed)" in reasoning

    def test_reasoning_with_all_signals_missing(self, selector):
        """PS-BR05: All signals missing → reasoning still includes F&G: unavailable."""
        score, signals = selector._compute_composite_score(ALL_MISSING_MARKET)
        condition = selector._classify_condition(score, ALL_MISSING_MARKET)
        reasoning = selector._build_reasoning(condition, score, signals, ALL_MISSING_MARKET)

        assert "Composite:" in reasoning
        assert "F&G: unavailable" in reasoning
        # Regime should show "unknown" with "?" confidence
        assert "Regime:" in reasoning

    def test_reasoning_confidence_missing_shows_none(self, selector):
        """PS-BR06: When regime_confidence is None, reasoning shows 'None%'.

        Note: snapshot.get("regime_confidence", "?") returns None (not "?")
        because the key EXISTS with value None. The "?" default only fires
        when the key is completely absent from the dict.
        """
        snap = _snapshot(regime="bullish", regime_confidence=None, mri=50, readiness=50)
        score, signals = selector._compute_composite_score(snap)
        condition = selector._classify_condition(score, snap)
        reasoning = selector._build_reasoning(condition, score, signals, snap)

        # Key exists with None → "None%" not "?%"
        assert "Regime: bullish (None%)" in reasoning
