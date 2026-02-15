"""
Synthetic SPY daily bar DataFrames for replay E2E tests.

Each fixture generates a deterministic DataFrame (seeded RNG) with ≥250 rows
of daily close prices. The price patterns are designed to produce specific
market regime classifications when fed through ReplayMarketIntelligence.

All fixtures use lowercase 'close' column name (matching Alpaca's pandas output).
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def _make_date_index(n_days: int, end_date: str = "2026-02-10") -> pd.DatetimeIndex:
    """Generate a business-day DatetimeIndex ending on end_date."""
    end = pd.Timestamp(end_date)
    # Generate more dates than needed, then take last n_days
    dates = pd.bdate_range(end=end, periods=n_days)
    return dates


def make_bull_spy_bars(seed: int = 42) -> pd.DataFrame:
    """Steady uptrend: 400 → ~530 over 300 days with very low volatility.

    Expected indicators after _compute_regime_from_bars():
    - Price well above SMA200 (+14%)
    - VIX proxy: ~8 (very low daily vol, ~0.3% std)
    - RSI: ~65-80 (steady gains)
    - Regime: bullish, confidence=100 (after scale fix)

    This should produce aggressive_bull or moderate_bull from PresetSelector.
    """
    rng = np.random.default_rng(seed)
    n = 300

    # Steady uptrend with tiny noise
    trend = np.linspace(400, 530, n)
    noise = rng.normal(0, 0.003, n)  # ~0.3% daily std
    prices = trend * (1 + noise)
    prices = np.maximum(prices, 1.0)  # floor at $1

    dates = _make_date_index(n)
    return pd.DataFrame({"close": prices}, index=dates)


def make_neutral_spy_bars(seed: int = 123) -> pd.DataFrame:
    """Sideways oscillation around 480 with moderate volatility.

    Expected indicators after _compute_regime_from_bars():
    - Price near SMA200 (oscillates around it)
    - VIX proxy: ~13 (moderate vol, ~0.8% std)
    - RSI: ~45-55 (mixed up/down)
    - Regime: bullish or neutral (depending on final price vs SMA200)

    This should produce neutral, moderate_bull, or aggressive_bull (low vol = greed F&G).
    Should NEVER produce skip or defensive.
    """
    rng = np.random.default_rng(seed)
    n = 300

    # Sideways oscillation
    t = np.linspace(0, 8 * np.pi, n)
    oscillation = 480 + 10 * np.sin(t)
    noise = rng.normal(0, 0.008, n)  # ~0.8% daily std
    prices = oscillation * (1 + noise)
    prices = np.maximum(prices, 1.0)

    dates = _make_date_index(n)
    return pd.DataFrame({"close": prices}, index=dates)


def make_bear_spy_bars(seed: int = 456) -> pd.DataFrame:
    """Downtrend: 520 → ~440 over 300 days with elevated volatility.

    Expected indicators after _compute_regime_from_bars():
    - Price below SMA200 (~-5%)
    - VIX proxy: ~25 (elevated vol, ~1.0% daily std)
    - RSI: ~35-45 (consistent selling)
    - F&G: ~15-35 (Fear, not Extreme Fear)
    - Regime: bearish, confidence=75 (after scale fix)

    This should produce cautious or defensive from PresetSelector.
    Should NEVER produce aggressive_bull.

    Note: Previous version used 1.6% daily std which produced VIX proxy ~52
    (2008-level) and F&G=0 (Extreme Fear), making bear indistinguishable
    from panic. Tuned to 1.0% to produce a realistic bear market (~VIX 25).
    """
    rng = np.random.default_rng(seed)
    n = 300

    # Steady downtrend with moderately elevated noise
    # 1.0% daily std → VIX proxy ~25 (typical bear market)
    # This produces F&G ~15-35 (Fear zone, not floored at 0)
    trend = np.linspace(520, 440, n)
    noise = rng.normal(0, 0.010, n)  # ~1.0% daily std
    prices = trend * (1 + noise)
    prices = np.maximum(prices, 1.0)

    dates = _make_date_index(n)
    return pd.DataFrame({"close": prices}, index=dates)


def make_mild_bull_spy_bars(seed: int = 3) -> pd.DataFrame:
    """Gentle uptrend: 470 → ~510 over 300 days with moderate volatility.

    Expected indicators after _compute_regime_from_bars():
    - Price slightly above SMA200 (~5%)
    - VIX proxy: ~11-14 (moderate vol, ~0.7% daily std)
    - RSI: ~50-60 (mild gains)
    - F&G: ~65-80 (moderate greed from moderate VIX)
    - Regime: bullish, confidence=88 (after scale fix)

    This should produce moderate_bull from PresetSelector.
    The score lands in the 20-50 range (not extreme enough for aggressive_bull).

    Note: Seed 3 with these params was found via systematic scan across
    seeds 1-50 with 4 different parameter sets. Multiple seeds work;
    3 is the most stable (score +41.7, well within 20-50 band).
    """
    rng = np.random.default_rng(seed)
    n = 300

    # Gentle uptrend with moderate noise
    # 0.7% daily std → VIX proxy ~11-14 → F&G ~65-80
    # Price ends ~5% above SMA200 → bullish regime but not extreme
    trend = np.linspace(470, 510, n)
    noise = rng.normal(0, 0.007, n)  # ~0.7% daily std
    prices = trend * (1 + noise)
    prices = np.maximum(prices, 1.0)

    dates = _make_date_index(n)
    return pd.DataFrame({"close": prices}, index=dates)


# ---------------------------------------------------------------------------
# Mid-band discovery candidates: multiple parameterizations to find
# interior-band scores (moderate_bull, cautious) without fragile pinning.
# Used by REPLAY-E2E-06 to prove the pipeline can hit mid-bands.
# ---------------------------------------------------------------------------

MID_BAND_CANDIDATES = [
    # (label, start_price, end_price, noise_std, seed)
    # Mild bull candidates (target: moderate_bull, score 20-50)
    ("mild_bull_a", 470, 510, 0.007, 3),
    ("mild_bull_b", 470, 510, 0.007, 38),
    ("mild_bull_c", 465, 495, 0.006, 20),
    # Mild bear candidates (target: cautious, score -20 to 0)
    ("mild_bear_a", 490, 488, 0.011, 40),
    ("mild_bear_b", 490, 488, 0.011, 15),
    ("mild_bear_c", 490, 485, 0.011, 25),
]


def make_mid_band_spy_bars(
    start_price: float,
    end_price: float,
    noise_std: float,
    seed: int,
    n: int = 300,
) -> pd.DataFrame:
    """Parameterized fixture for mid-band discovery tests.

    Instead of one carefully tuned fixture, the mid-band test tries
    multiple (start, end, noise, seed) combos and asserts that at
    least one lands in each target band. This is robust to minor
    formula changes because:
    - Multiple candidates provide fallback if one drifts out of band
    - Assertions check score-to-condition consistency, not exact values
    """
    rng = np.random.default_rng(seed)
    trend = np.linspace(start_price, end_price, n)
    noise = rng.normal(0, noise_std, n)
    prices = trend * (1 + noise)
    prices = np.maximum(prices, 1.0)

    dates = _make_date_index(n)
    return pd.DataFrame({"close": prices}, index=dates)


def make_panic_spy_bars(seed: int = 789) -> pd.DataFrame:
    """Crash scenario: 270 days flat at ~500, then sharp drop to ~380 in 30 days.

    Expected indicators after _compute_regime_from_bars():
    - Price well below SMA200 (-20%)
    - VIX proxy: ~40 (extreme vol from crash)
    - RSI: < 25 (sustained heavy losses)
    - Regime: bearish, confidence=100 (after scale fix)
    - F&G from bars: < 10 (extreme fear)

    Combined with injected MRI > 80, should trigger panic override → skip.
    """
    rng = np.random.default_rng(seed)
    n = 300

    # Phase 1: 270 days of gentle drift around 500
    phase1 = 500 + rng.normal(0, 0.005, 270).cumsum() * 500 * 0.005
    phase1 = np.clip(phase1, 480, 520)

    # Phase 2: 30 days of crash (500 → 380)
    crash_trend = np.linspace(500, 380, 30)
    crash_noise = rng.normal(0, 0.025, 30)  # ~2.5% daily std during crash
    phase2 = crash_trend * (1 + crash_noise)

    prices = np.concatenate([phase1, phase2])
    prices = np.maximum(prices, 1.0)

    dates = _make_date_index(n)
    return pd.DataFrame({"close": prices}, index=dates)
