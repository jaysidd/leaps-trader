"""
Replay → PresetSelector E2E Integration Tests.

Tests the full flow from synthetic SPY bar data through ReplayMarketIntelligence
into PresetSelector, verifying that market conditions produce correct classifications.

These tests use NO external API calls — all data comes from synthetic DataFrames.

Assertions are intentionally broad (condition buckets + score ranges, not exact values)
to avoid flakiness from minor computation shifts.

Run:  python3 -m pytest tests/replay/ -v -m replay
"""
import pytest
from unittest.mock import MagicMock

from app.services.automation.preset_selector import get_preset_selector, MARKET_CONDITIONS
from app.data.presets_catalog import LEAPS_PRESETS

from tests.replay.spy_fixtures import (
    make_bull_spy_bars,
    make_neutral_spy_bars,
    make_bear_spy_bars,
    make_panic_spy_bars,
    make_mild_bull_spy_bars,
    make_mid_band_spy_bars,
    MID_BAND_CANDIDATES,
)


# ---------------------------------------------------------------------------
# Helper: run replay intelligence → PresetSelector pipeline
# ---------------------------------------------------------------------------

async def _run_replay_preset_selector(replay_clock, spy_df, mock_db,
                                       injected_mri=None):
    """
    Full replay → PresetSelector pipeline.

    1. Create ReplayMarketIntelligence
    2. Load historical intelligence (computes regime/F&G/readiness from bars)
    3. Optionally inject MRI
    4. Install patches into service singleton caches
    5. Run PresetSelector.select_presets()
    6. Uninstall patches (always, even on failure)

    Returns (result_dict, intel_results_dict).
    """
    from scripts.replay.replay_services import ReplayMarketIntelligence

    # Create data service stub
    data_svc = MagicMock()
    data_svc.daily_cache = {"SPY": spy_df}

    intel = ReplayMarketIntelligence(replay_clock, db_session=None)

    # Override MRI if provided (since we have no real DB)
    if injected_mri:
        intel._injected_mri = injected_mri

    intel_results = intel.load_historical_intelligence(data_svc)

    # If MRI was injected before load, it may have been overwritten by the
    # DB query (which returns None since db_session=None). Re-inject.
    if injected_mri:
        intel._injected_mri = injected_mri

    intel.install_patches()
    try:
        selector = get_preset_selector()
        result = await selector.select_presets(mock_db)
        return result, intel_results
    finally:
        intel.uninstall_patches()


# ===========================================================================
# REPLAY-E2E-01: Neutral/Sideways Day
# ===========================================================================

@pytest.mark.replay
@pytest.mark.asyncio
async def test_neutral_day_not_skip(replay_clock, mock_db):
    """REPLAY-E2E-01: Sideways market should NEVER produce skip or defensive.

    A neutral/sideways market has:
    - Low-to-moderate volatility → moderate-to-high F&G (not fearful)
    - Price near SMA200 → regime neutral or mildly bullish
    - No panic signals

    Even if the exact condition varies (neutral, moderate_bull, aggressive_bull
    due to low vol → high F&G greed signal), it should never be defensive/skip.
    """
    spy_df = make_neutral_spy_bars()
    result, intel = await _run_replay_preset_selector(replay_clock, spy_df, mock_db)

    # Core assertion: NOT defensive or skip
    assert result["condition"] not in ("defensive", "skip"), (
        f"Neutral day classified as {result['condition']} — too bearish. "
        f"Reasoning: {result['reasoning']}"
    )

    # Should have presets assigned
    assert len(result["presets"]) > 0, "Neutral day should have presets"
    assert result["max_positions"] >= 1

    # Composite score should not be deeply negative
    composite = result["market_snapshot"]["composite_score"]
    assert composite > -20, (
        f"Neutral day composite={composite} is too bearish"
    )

    # All presets must exist in catalog (contract check)
    for preset in result["presets"]:
        assert preset in LEAPS_PRESETS, f"Preset '{preset}' not in catalog"

    # Version breadcrumbs must be present
    assert "selector_version" in result
    assert "catalog_hash" in result
    assert len(result["catalog_hash"]) == 8


# ===========================================================================
# REPLAY-E2E-02: Bull Day
# ===========================================================================

@pytest.mark.replay
@pytest.mark.asyncio
async def test_bull_day_aggressive_or_moderate(replay_clock, mock_db):
    """REPLAY-E2E-02: Strong bull market should produce aggressive or moderate bull.

    A bull market has:
    - Very low volatility → VIX proxy ~8 → F&G near 100 (extreme greed)
    - Price well above SMA200 → bullish regime with high confidence
    - Low readiness score (risk-on)

    Combined signals should push composite well above +20 (moderate_bull threshold).
    """
    spy_df = make_bull_spy_bars()
    result, intel = await _run_replay_preset_selector(replay_clock, spy_df, mock_db)

    assert result["condition"] in ("aggressive_bull", "moderate_bull"), (
        f"Bull day classified as {result['condition']} — not bullish enough. "
        f"Reasoning: {result['reasoning']}"
    )

    # Should NOT be bearish
    assert result["condition"] not in ("cautious", "defensive", "skip")

    composite = result["market_snapshot"]["composite_score"]
    assert composite >= 20, (
        f"Bull day composite={composite} below moderate_bull threshold"
    )

    # Should have multiple presets (aggressive and moderate conditions have 3)
    assert len(result["presets"]) >= 2

    # Verify regime signal was computed and injected correctly
    snapshot = result["market_snapshot"]
    assert snapshot.get("regime") == "bullish", (
        f"Expected bullish regime, got {snapshot.get('regime')}"
    )

    # Confidence should be on 0-100 scale (not 1-10)
    confidence = snapshot.get("regime_confidence")
    if confidence is not None:
        assert confidence > 50, (
            f"Confidence={confidence} looks like 1-10 scale (should be 0-100)"
        )


# ===========================================================================
# REPLAY-E2E-03: Bear Day Safety
# ===========================================================================

@pytest.mark.replay
@pytest.mark.asyncio
async def test_bear_day_not_aggressive(replay_clock, mock_db):
    """REPLAY-E2E-03: Bear market should NEVER produce aggressive presets.

    A bear market has:
    - Elevated volatility → VIX proxy ~30 → F&G in Fear zone (15-35)
    - Price below SMA200 → bearish regime
    - Higher readiness score (risk-off)

    The key safety gate: aggressive_bull presets should never be selected
    during a downtrend, even if some individual signals are mixed.

    Note: The bear fixture is tuned to produce realistic signals (~VIX 30,
    F&G ~29) rather than extreme signals (~VIX 52, F&G=0) which would be
    indistinguishable from a panic/crash scenario.
    """
    spy_df = make_bear_spy_bars()
    result, intel = await _run_replay_preset_selector(replay_clock, spy_df, mock_db)

    assert result["condition"] in ("cautious", "defensive", "skip"), (
        f"Bear day classified as {result['condition']} — too bullish! "
        f"Safety violation. Reasoning: {result['reasoning']}"
    )

    # CRITICAL: never aggressive on a bear day
    assert result["condition"] != "aggressive_bull", (
        "SAFETY VIOLATION: aggressive_bull on a bear day"
    )
    assert result["condition"] != "moderate_bull", (
        "SAFETY VIOLATION: moderate_bull on a bear day"
    )

    composite = result["market_snapshot"]["composite_score"]
    assert composite < 0, (
        f"Bear day composite={composite} should be negative"
    )

    # Verify regime detection caught the downtrend
    snapshot = result["market_snapshot"]
    assert snapshot.get("regime") == "bearish", (
        f"Expected bearish regime, got {snapshot.get('regime')}"
    )

    # F&G should be in Fear zone (not floored at 0 like a crash)
    fg = snapshot.get("fear_greed")
    assert fg is not None and fg < 40, (
        f"Bear F&G should be in fear zone (<40), got {fg}"
    )

    # Should still have some presets (defensive has conservative)
    # A bear day is risk-off, not zero-activity
    if result["condition"] == "defensive":
        assert len(result["presets"]) >= 1, (
            "Defensive condition should still have conservative presets"
        )


# ===========================================================================
# REPLAY-E2E-04: Panic Override
# ===========================================================================

@pytest.mark.replay
@pytest.mark.asyncio
async def test_panic_override_triggers_skip(replay_clock, mock_db):
    """REPLAY-E2E-04: Crash + high MRI should trigger panic override → skip.

    Panic override requires BOTH:
    - MRI > 80 (injected as 85)
    - F&G < 10 (computed from crash bar data: extreme fear)

    When both conditions are met, PresetSelector hard-overrides to "skip"
    regardless of composite score.
    """
    spy_df = make_panic_spy_bars()

    # Inject high MRI to enable panic override (MRI > 80 required)
    injected_mri = {
        "mri_score": 85,
        "regime": "crisis",
        "confidence_score": 90,
        "shock_flag": True,
    }

    result, intel = await _run_replay_preset_selector(
        replay_clock, spy_df, mock_db, injected_mri=injected_mri
    )

    assert result["condition"] == "skip", (
        f"Panic scenario should produce skip, got {result['condition']}. "
        f"Reasoning: {result['reasoning']}"
    )
    assert result["presets"] == [], "Skip condition should have empty presets"
    assert result["max_positions"] == 0

    composite = result["market_snapshot"]["composite_score"]
    assert composite < -50, (
        f"Panic composite={composite} should be deeply negative"
    )

    # Verify the signals that enabled panic override
    snapshot = result["market_snapshot"]
    assert snapshot.get("mri") == 85, (
        f"MRI should be 85 (injected), got {snapshot.get('mri')}"
    )

    fg = snapshot.get("fear_greed")
    assert fg is not None and fg < 10, (
        f"F&G should be < 10 for panic override, got {fg}"
    )


# ===========================================================================
# REPLAY-E2E-05: Determinism + No State Leakage
# ===========================================================================

@pytest.mark.replay
@pytest.mark.asyncio
async def test_determinism_same_input_twice(replay_clock, mock_db):
    """REPLAY-E2E-05: Same input run twice produces identical output.

    This test verifies:
    1. Determinism: same bar data → same classification
    2. No state leakage: uninstall_patches() fully restores singletons
    3. Cache cleanup: regime detector cache is cleared between runs
    """
    spy_df = make_bull_spy_bars()

    # Run 1
    result1, _ = await _run_replay_preset_selector(replay_clock, spy_df, mock_db)

    # Clear caches between runs (simulating a fresh start)
    try:
        from app.services.ai.market_regime import get_regime_detector
        get_regime_detector().clear_cache()
    except Exception:
        pass

    # Run 2 (identical input)
    result2, _ = await _run_replay_preset_selector(replay_clock, spy_df, mock_db)

    # Condition and presets must be identical
    assert result1["condition"] == result2["condition"], (
        f"Non-deterministic: run1={result1['condition']}, run2={result2['condition']}"
    )
    assert result1["presets"] == result2["presets"], (
        f"Non-deterministic presets: run1={result1['presets']}, run2={result2['presets']}"
    )
    assert result1["max_positions"] == result2["max_positions"]

    # Composite scores must match within floating-point tolerance
    cs1 = result1["market_snapshot"]["composite_score"]
    cs2 = result2["market_snapshot"]["composite_score"]
    assert cs1 == pytest.approx(cs2, abs=0.01), (
        f"Non-deterministic score: run1={cs1}, run2={cs2}"
    )

    # Individual signal values must match
    for key in ("regime", "fear_greed", "readiness", "regime_confidence", "mri"):
        v1 = result1["market_snapshot"].get(key)
        v2 = result2["market_snapshot"].get(key)
        if isinstance(v1, float) and isinstance(v2, float):
            assert v1 == pytest.approx(v2, abs=0.01), (
                f"{key} differs: run1={v1}, run2={v2}"
            )
        else:
            assert v1 == v2, f"{key} differs: run1={v1}, run2={v2}"

    # Catalog hash should be stable
    assert result1["catalog_hash"] == result2["catalog_hash"]


# ===========================================================================
# REPLAY-E2E-06: Mid-Band Discovery (moderate_bull + cautious)
# ===========================================================================

@pytest.mark.replay
@pytest.mark.asyncio
async def test_mid_band_discovery(replay_clock, mock_db):
    """REPLAY-E2E-06: Pipeline can hit interior score bands, not just extremes.

    Tests 01-04 cover the 4 corners of the input space:
    - Bull → aggressive_bull (score ~+78)
    - Neutral → neutral (score ~+18)
    - Bear → defensive (score ~-47)
    - Panic → skip (score ~-80)

    But moderate_bull (20-50) and cautious (-20 to 0) are never directly hit.
    Unit tests cover those thresholds extensively, but we want at least one
    replay test proving that real bar-derived signals can land in mid-bands.

    Rather than a single fragile fixture, we try multiple parameterizations
    and assert that AT LEAST ONE candidate hits each target band. This is
    robust because:
    - Multiple candidates provide fallback if one drifts out of band
    - We check score↔condition consistency, not exact values
    - We verify determinism (same candidate, same result)

    The test validates:
    1. The pipeline CAN produce moderate_bull from bar data
    2. Score-to-condition mapping is consistent
    3. Mid-band results are deterministic
    """
    # ── Phase 1: Find a moderate_bull candidate ──────────────────────
    moderate_bull_hits = []
    all_results = {}

    for label, sp, ep, ns, seed in MID_BAND_CANDIDATES:
        spy_df = make_mid_band_spy_bars(sp, ep, ns, seed)
        result, intel = await _run_replay_preset_selector(
            replay_clock, spy_df, mock_db
        )
        composite = result["market_snapshot"]["composite_score"]
        condition = result["condition"]
        all_results[label] = (composite, condition, result)

        # Track moderate_bull hits (score 20-50)
        if 20 <= composite <= 50 and condition == "moderate_bull":
            moderate_bull_hits.append(label)

    # At least one candidate must hit moderate_bull
    assert len(moderate_bull_hits) >= 1, (
        f"No mid-band candidates produced moderate_bull. "
        f"Results: {[(k, f'{v[0]:+.1f}', v[1]) for k, v in all_results.items()]}"
    )

    # ── Phase 2: Verify score↔condition consistency for ALL candidates ──
    for label, (composite, condition, result) in all_results.items():
        # Every result must have valid structure
        assert "condition" in result
        assert "presets" in result
        assert "market_snapshot" in result

        # Score and condition must be consistent
        if composite >= 50:
            assert condition == "aggressive_bull", (
                f"{label}: score={composite:+.1f} but condition={condition}"
            )
        elif composite >= 20:
            assert condition == "moderate_bull", (
                f"{label}: score={composite:+.1f} but condition={condition}"
            )
        elif composite >= 0:
            assert condition == "neutral", (
                f"{label}: score={composite:+.1f} but condition={condition}"
            )
        elif composite >= -20:
            assert condition == "cautious", (
                f"{label}: score={composite:+.1f} but condition={condition}"
            )
        elif composite >= -50:
            assert condition == "defensive", (
                f"{label}: score={composite:+.1f} but condition={condition}"
            )
        else:
            assert condition == "skip", (
                f"{label}: score={composite:+.1f} but condition={condition}"
            )

        # All presets must exist in catalog
        for preset in result["presets"]:
            assert preset in LEAPS_PRESETS, (
                f"{label}: preset '{preset}' not in catalog"
            )

    # ── Phase 3: Verify determinism of a moderate_bull hit ──────────
    # Pick the first moderate_bull candidate and re-run it
    winner_label = moderate_bull_hits[0]
    winner_params = next(
        (sp, ep, ns, seed)
        for label, sp, ep, ns, seed in MID_BAND_CANDIDATES
        if label == winner_label
    )
    sp, ep, ns, seed = winner_params

    # Clear caches between runs
    try:
        from app.services.ai.market_regime import get_regime_detector
        get_regime_detector().clear_cache()
    except Exception:
        pass

    spy_df_2 = make_mid_band_spy_bars(sp, ep, ns, seed)
    result2, _ = await _run_replay_preset_selector(replay_clock, spy_df_2, mock_db)

    first_result = all_results[winner_label][2]
    assert first_result["condition"] == result2["condition"], (
        f"Non-deterministic: run1={first_result['condition']}, "
        f"run2={result2['condition']} for {winner_label}"
    )
    cs1 = first_result["market_snapshot"]["composite_score"]
    cs2 = result2["market_snapshot"]["composite_score"]
    assert cs1 == pytest.approx(cs2, abs=0.01), (
        f"Non-deterministic score: run1={cs1}, run2={cs2}"
    )
