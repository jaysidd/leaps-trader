"""
Configuration for Catalyst Service.

All weights, thresholds, and settings are externalized here
to allow easy tuning without code changes.
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class CatalystConfig:
    """
    Externalized configuration for catalyst calculations.

    Adjust these values to tune the scoring behavior.
    """

    # =========================================================================
    # LIQUIDITY SCORE WEIGHTS
    # =========================================================================

    # Weights for each liquidity metric (must sum to 1.0)
    LIQUIDITY_WEIGHTS: Dict[str, float] = field(default_factory=lambda: {
        "fed_balance_sheet": 0.25,  # QE/QT direction
        "rrp": 0.20,                 # Reverse repo (liquidity drain)
        "tga": 0.15,                 # Treasury General Account
        "fci": 0.25,                 # Financial Conditions Index
        "real_yield_10y": 0.15,      # Real yields
    })

    # Direction of each metric (True = higher value is bullish/risk-on)
    LIQUIDITY_DIRECTIONS: Dict[str, bool] = field(default_factory=lambda: {
        "fed_balance_sheet": True,   # Higher = more liquidity = bullish
        "rrp": False,                # Higher = more liquidity drain = bearish
        "tga": False,                # Higher = more drain = bearish
        "fci": False,                # Higher = tighter conditions = bearish
        "real_yield_10y": False,     # Higher = more restrictive = bearish
    })

    # Baseline values for z-score calculations (approximately neutral)
    # These should be updated periodically based on historical averages
    LIQUIDITY_BASELINES: Dict[str, float] = field(default_factory=lambda: {
        "fed_balance_sheet": 7.5e12,  # $7.5T
        "rrp": 500e9,                  # $500B
        "tga": 500e9,                  # $500B
        "fci": 0.0,                    # Neutral is 0
        "real_yield_10y": 1.5,         # 1.5% real yield
    })

    # Standard deviations for z-score normalization
    LIQUIDITY_STDEVS: Dict[str, float] = field(default_factory=lambda: {
        "fed_balance_sheet": 1e12,    # $1T std
        "rrp": 300e9,                  # $300B std
        "tga": 200e9,                  # $200B std
        "fci": 0.5,                    # 0.5 std
        "real_yield_10y": 0.75,        # 0.75% std
    })

    # =========================================================================
    # LIQUIDITY REGIME THRESHOLDS
    # =========================================================================

    # Score thresholds for regime labels
    # Note: Higher score = more risk-off (contracting liquidity)
    LIQUIDITY_RISK_ON_THRESHOLD: float = 35.0   # Score < 35 = expanding liquidity
    LIQUIDITY_RISK_OFF_THRESHOLD: float = 65.0  # Score > 65 = contracting liquidity

    # =========================================================================
    # CREDIT STRESS SCORE WEIGHTS
    # =========================================================================
    # All scores: 0 = calm, 100 = stressed (risk-off polarity)

    CREDIT_STRESS_WEIGHTS: Dict[str, float] = field(default_factory=lambda: {
        "hy_oas": 0.45,             # High-yield OAS level
        "ig_oas": 0.25,             # Investment-grade OAS level
        "hy_oas_change_4w": 0.30,   # 4-week change in HY OAS (early warning)
    })

    CREDIT_STRESS_DIRECTIONS: Dict[str, bool] = field(default_factory=lambda: {
        "hy_oas": False,            # Higher spreads = risk-off
        "ig_oas": False,            # Higher spreads = risk-off
        "hy_oas_change_4w": False,  # Widening = risk-off
    })

    CREDIT_STRESS_BASELINES: Dict[str, float] = field(default_factory=lambda: {
        "hy_oas": 3.50,             # 5-year median HY OAS (%)
        "ig_oas": 1.20,             # 5-year median IG OAS (%)
        "hy_oas_change_4w": 0.0,    # Neutral = no change
    })

    CREDIT_STRESS_STDEVS: Dict[str, float] = field(default_factory=lambda: {
        "hy_oas": 1.20,
        "ig_oas": 0.35,
        "hy_oas_change_4w": 0.40,
    })

    CREDIT_LOW_STRESS_THRESHOLD: float = 35.0   # Score < 35 = low stress
    CREDIT_HIGH_STRESS_THRESHOLD: float = 65.0   # Score > 65 = high stress

    # =========================================================================
    # VOLATILITY STRUCTURE SCORE WEIGHTS
    # =========================================================================

    VOL_STRUCTURE_WEIGHTS: Dict[str, float] = field(default_factory=lambda: {
        "vix": 0.40,               # VIX spot level
        "term_slope": 0.35,        # VIX3M - VIX (contango/backwardation)
        "vvix": 0.25,              # Volatility of volatility
    })

    VOL_STRUCTURE_DIRECTIONS: Dict[str, bool] = field(default_factory=lambda: {
        "vix": False,              # Higher VIX = risk-off
        "term_slope": True,        # Positive contango = bullish (reduces risk-off score)
        "vvix": False,             # Higher VVIX = risk-off
    })

    VOL_STRUCTURE_BASELINES: Dict[str, float] = field(default_factory=lambda: {
        "vix": 17.0,
        "term_slope": 1.5,         # Normal contango ~1.5 points
        "vvix": 85.0,
    })

    VOL_STRUCTURE_STDEVS: Dict[str, float] = field(default_factory=lambda: {
        "vix": 6.0,
        "term_slope": 2.5,
        "vvix": 15.0,
    })

    VOL_CALM_THRESHOLD: float = 35.0      # Score < 35 = calm
    VOL_STRESSED_THRESHOLD: float = 65.0   # Score > 65 = stressed

    # =========================================================================
    # EVENT DENSITY SCORE (max-points normalization)
    # =========================================================================

    EVENT_DENSITY_MAX_POINTS: float = 25.0    # Score = 100 * total_points / max_points
    EVENT_POINT_WEIGHTS: Dict[str, int] = field(default_factory=lambda: {
        "high": 3,
        "medium": 2,
        "low": 1,
    })
    EVENT_EARNINGS_CAP: float = 5.0           # Max points from earnings events
    EVENT_LIGHT_THRESHOLD: float = 35.0       # Score < 35 = light week
    EVENT_HEAVY_THRESHOLD: float = 65.0       # Score > 65 = heavy week

    # =========================================================================
    # TRADE READINESS WEIGHTS
    # =========================================================================

    # Weights for Trade Readiness Score (must sum to 1.0)
    # All component scores: 0 = calm/good, 100 = stressed/bad (risk-off polarity)
    # No inversion in aggregation — all scores feed directly into weighted sum
    READINESS_WEIGHTS: Dict[str, float] = field(default_factory=lambda: {
        "mri": 0.40,                    # Macro Risk Index
        "liquidity": 0.20,              # Liquidity Score
        "credit_stress": 0.15,          # Credit Stress
        "vol_structure": 0.15,          # Volatility Structure
        "event_density": 0.10,          # Event Density
    })

    # Default values for unimplemented components (neutral = 50)
    READINESS_DEFAULTS: Dict[str, float] = field(default_factory=lambda: {
        "mri": 50.0,
        "liquidity": 50.0,
        "credit_stress": 50.0,
        "vol_structure": 50.0,
        "event_density": 50.0,
    })

    # Trade Readiness regime thresholds
    READINESS_GREEN_THRESHOLD: float = 33.0   # Score <= 33 = green (risk-on)
    READINESS_YELLOW_THRESHOLD: float = 66.0  # 34-66 = yellow (transition)
    # Score > 66 = red (risk-off)

    # =========================================================================
    # DATA QUALITY
    # =========================================================================

    # Staleness thresholds (hours)
    STALE_THRESHOLD_HOURS: int = 48  # Data older than 48h is stale
    STALE_CONFIDENCE_CAP: float = 40.0  # Max confidence for stale data

    # Minimum data completeness for valid scores
    MIN_COMPLETENESS_FOR_SCORE: float = 0.5  # Need at least 50% of metrics

    # =========================================================================
    # ALERT SETTINGS
    # =========================================================================

    # Alert persistence (requires N consecutive detections)
    ALERT_PERSISTENCE_MIN_CHECKS: int = 2
    ALERT_PERSISTENCE_WINDOW_MINUTES: int = 30

    # Alert cooldown (don't re-fire same alert within this window)
    ALERT_COOLDOWN_MINUTES: int = 60

    # Regime change thresholds (need to cross these to trigger alert)
    LIQUIDITY_REGIME_ALERT_LOW: float = 40.0   # Alert when drops below
    LIQUIDITY_REGIME_ALERT_HIGH: float = 60.0  # Alert when rises above

    # =========================================================================
    # SCHEDULER SETTINGS
    # =========================================================================

    # How often to refresh catalysts
    REFRESH_INTERVAL_MINUTES: int = 60  # Hourly default

    # Smart cadence: skip storage if data unchanged
    SMART_CADENCE_ENABLED: bool = True
    SMART_CADENCE_CHANGE_THRESHOLD: float = 1.0  # Only store if score changed by >1 point

    # =========================================================================
    # SECTOR MACRO WEIGHT DEFAULTS
    # =========================================================================
    # Different sectors have different sensitivities to macro factors.
    # These weights are used when computing per-ticker macro_bias_score.
    # All weights per sector must sum to 1.0.

    SECTOR_MACRO_WEIGHTS: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "Technology": {
            "liquidity": 0.30,            # High sensitivity to liquidity
            "fed_policy": 0.25,           # Rate sensitive (growth stocks)
            "earnings": 0.20,             # Earnings important
            "options_positioning": 0.15,  # Options activity significant
            "event_risk": 0.10,
        },
        "Financials": {
            "liquidity": 0.35,            # Very sensitive to liquidity
            "fed_policy": 0.30,           # Directly impacted by rates
            "earnings": 0.15,
            "options_positioning": 0.10,
            "event_risk": 0.10,
        },
        "Healthcare": {
            "liquidity": 0.20,            # Less rate sensitive
            "fed_policy": 0.15,
            "earnings": 0.30,             # Earnings/drug approvals key
            "options_positioning": 0.15,
            "event_risk": 0.20,           # FDA events, etc.
        },
        "Consumer Discretionary": {
            "liquidity": 0.25,
            "fed_policy": 0.20,
            "earnings": 0.25,             # Consumer spending signals
            "options_positioning": 0.15,
            "event_risk": 0.15,
        },
        "Consumer Staples": {
            "liquidity": 0.15,            # Defensive, less sensitive
            "fed_policy": 0.15,
            "earnings": 0.30,
            "options_positioning": 0.20,
            "event_risk": 0.20,
        },
        "Energy": {
            "liquidity": 0.20,
            "fed_policy": 0.15,
            "earnings": 0.25,
            "options_positioning": 0.15,
            "event_risk": 0.25,           # Geopolitical, OPEC events
        },
        "Industrials": {
            "liquidity": 0.25,
            "fed_policy": 0.25,
            "earnings": 0.20,
            "options_positioning": 0.15,
            "event_risk": 0.15,
        },
        "Materials": {
            "liquidity": 0.25,
            "fed_policy": 0.20,
            "earnings": 0.20,
            "options_positioning": 0.15,
            "event_risk": 0.20,           # Commodity prices, China
        },
        "Real Estate": {
            "liquidity": 0.30,
            "fed_policy": 0.35,           # Very rate sensitive
            "earnings": 0.15,
            "options_positioning": 0.10,
            "event_risk": 0.10,
        },
        "Utilities": {
            "liquidity": 0.20,
            "fed_policy": 0.30,           # Bond proxy, rate sensitive
            "earnings": 0.20,
            "options_positioning": 0.15,
            "event_risk": 0.15,
        },
        "Communication Services": {
            "liquidity": 0.25,
            "fed_policy": 0.20,
            "earnings": 0.25,
            "options_positioning": 0.15,
            "event_risk": 0.15,
        },
        # Default for unknown sectors
        "Unknown": {
            "liquidity": 0.25,
            "fed_policy": 0.25,
            "earnings": 0.20,
            "options_positioning": 0.15,
            "event_risk": 0.15,
        },
    })

    # =========================================================================
    # TRADE COMPATIBILITY THRESHOLDS
    # =========================================================================
    # Trade compatibility is an INFO flag, NOT a gate.
    # Values: Favorable, Mixed, Unfavorable

    # Favorable: readiness > threshold AND earnings_risk < threshold
    TRADE_COMPAT_FAVORABLE_READINESS_MIN: float = 60.0
    TRADE_COMPAT_FAVORABLE_EARNINGS_RISK_MAX: float = 50.0

    # Unfavorable: readiness < threshold OR earnings imminent
    TRADE_COMPAT_UNFAVORABLE_READINESS_MAX: float = 40.0
    TRADE_COMPAT_EARNINGS_IMMINENT_DAYS: int = 2

    # =========================================================================
    # MACRO BIAS THRESHOLDS
    # =========================================================================
    # Maps macro_bias_score to labels

    MACRO_BIAS_BEARISH_THRESHOLD: float = 33.0   # Score 0-33 = Bearish
    MACRO_BIAS_BULLISH_THRESHOLD: float = 67.0   # Score 67-100 = Bullish
    # Score 34-66 = Neutral


# Singleton config instance
_catalyst_config: CatalystConfig = CatalystConfig()


def get_catalyst_config() -> CatalystConfig:
    """Get the catalyst configuration."""
    return _catalyst_config
