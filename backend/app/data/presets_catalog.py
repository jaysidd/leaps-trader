"""
LEAPS Presets Catalog — Single source of truth for all screening presets.

Extracted from screener.py to eliminate circular import issues and enable
clean validation from preset_selector.py and other automation modules.

Each preset is a flat dict of screening thresholds. The screening engine
treats these as optional overrides to its defaults.

Usage:
    from app.data.presets_catalog import LEAPS_PRESETS, resolve_preset, get_catalog_hash
"""
import os
import hashlib
from typing import Dict, Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# LEAPS_PRESETS — All screening preset configurations
# ---------------------------------------------------------------------------

LEAPS_PRESETS: Dict[str, Dict[str, Any]] = {
    # ==========================================================================
    # STANDARD RISK-BASED PRESETS
    # ==========================================================================
    "conservative": {
        "description": "Large caps ($5B+), stable growth, low risk",
        "market_cap_min": 5_000_000_000,
        "market_cap_max": 5_000_000_000_000,
        "price_min": 10,
        "price_max": 300,
        "revenue_growth_min": 5,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 150,
        "rsi_min": 30,
        "rsi_max": 70,
        "iv_max": 80,
        "skip_sector_filter": True,  # Large-caps across ALL sectors are valid LEAPS targets
    },
    "moderate": {
        "description": "Mid caps ($1B+), good growth, balanced risk",
        "market_cap_min": 1_000_000_000,
        "market_cap_max": 100_000_000_000,
        "price_min": 5,
        "price_max": 500,
        "revenue_growth_min": 10,
        "earnings_growth_min": 5,
        "debt_to_equity_max": 200,
        "rsi_min": 25,
        "rsi_max": 75,
        "iv_max": 100
    },
    "aggressive": {
        "description": "Small/mid caps ($500M+), high growth, high reward potential",
        "market_cap_min": 500_000_000,
        "market_cap_max": 50_000_000_000,
        "price_min": 3,
        "price_max": 500,
        "revenue_growth_min": 15,
        "earnings_growth_min": 10,
        "debt_to_equity_max": 300,
        "rsi_min": 20,
        "rsi_max": 80,
        "iv_max": 120
    },

    # ==========================================================================
    # LEAPS-SPECIFIC STRATEGY PRESETS
    # ==========================================================================
    "low_iv_entry": {
        "description": "Low IV rank — cheap options, ideal for LEAPS entry",
        "market_cap_min": 2_000_000_000,
        "market_cap_max": 200_000_000_000,
        "price_min": 10,
        "price_max": 400,
        "revenue_growth_min": 5,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 200,
        "rsi_min": 35,
        "rsi_max": 65,
        "iv_max": 40  # Very low IV - key filter
    },
    "cheap_leaps": {
        "description": "Premium <10% of stock price, high liquidity",
        "market_cap_min": 5_000_000_000,
        "market_cap_max": 300_000_000_000,
        "price_min": 20,
        "price_max": 300,
        "revenue_growth_min": 0,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 250,
        "rsi_min": 30,
        "rsi_max": 70,
        "iv_max": 50
    },
    "momentum": {
        "description": "Strong fundamentals + RSI recovering + MACD bullish",
        "market_cap_min": 1_000_000_000,
        "market_cap_max": 100_000_000_000,
        "price_min": 10,
        "price_max": 500,
        "revenue_growth_min": 20,
        "earnings_growth_min": 15,
        "debt_to_equity_max": 150,
        "rsi_min": 40,  # RSI recovering from oversold
        "rsi_max": 70,  # Fix: was 60, momentum stocks often RSI 50-70
        "iv_max": 80
    },
    "turnaround": {
        "description": "Oversold RSI + above SMA200 - potential reversal plays",
        "market_cap_min": 2_000_000_000,
        "market_cap_max": 150_000_000_000,
        "price_min": 10,
        "price_max": 400,
        "revenue_growth_min": 0,
        "earnings_growth_min": -20,  # Allow negative earnings (turnaround)
        "debt_to_equity_max": 300,
        "rsi_min": 20,  # Oversold
        "rsi_max": 40,
        "iv_max": 100
    },
    "growth_leaps": {
        "description": "High growth companies ideal for long-term LEAPS",
        "market_cap_min": 500_000_000,
        "market_cap_max": 50_000_000_000,
        "price_min": 5,
        "price_max": 300,
        "revenue_growth_min": 30,  # High growth requirement
        "earnings_growth_min": 25,
        "debt_to_equity_max": 200,
        "rsi_min": 30,
        "rsi_max": 70,
        "iv_max": 100,
        "peg_max": 2.5  # Valuation guard — growth without overpaying
    },
    "blue_chip_leaps": {
        "description": "Mega caps with stable returns - conservative LEAPS",
        "market_cap_min": 50_000_000_000,
        "market_cap_max": 10_000_000_000_000,
        "price_min": 50,
        "price_max": 600,
        "revenue_growth_min": 0,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 150,
        "rsi_min": 35,
        "rsi_max": 65,
        "iv_max": 60,
        "dte_min": 365,
        "dte_max": 730,
        "skip_sector_filter": True,  # Mega-caps across ALL sectors are valid LEAPS targets
    },

    # ==========================================================================
    # SWING TRADING PRESETS (4-8 weeks, Delta 0.40-0.55)
    # ==========================================================================
    "swing_momentum": {
        "description": "4-8 week momentum plays - ride the trend",
        "category": "swing",
        "market_cap_min": 1_000_000_000,
        "market_cap_max": 200_000_000_000,
        "price_min": 10,
        "price_max": 500,
        "revenue_growth_min": 10,
        "earnings_growth_min": 5,
        "debt_to_equity_max": 200,
        "rsi_min": 45,  # Not oversold - confirming momentum
        "rsi_max": 65,  # Not overbought yet
        "iv_max": 80,
        "dte_min": 30,
        "dte_max": 60,
        "delta_min": 0.40,
        "delta_max": 0.55
    },
    "swing_breakout": {
        "description": "Technical breakout setups - RSI recovering",
        "category": "swing",
        "market_cap_min": 500_000_000,
        "market_cap_max": 100_000_000_000,
        "price_min": 5,
        "price_max": 400,
        "revenue_growth_min": 5,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 250,
        "rsi_min": 35,  # Coming out of oversold
        "rsi_max": 60,  # Fix: was 55, recovery breakouts reach 55-65
        "iv_max": 90,
        "dte_min": 21,
        "dte_max": 45,
        "delta_min": 0.35,
        "delta_max": 0.50
    },
    "swing_oversold": {
        "description": "Oversold bounce plays - quick recovery potential",
        "category": "swing",
        "market_cap_min": 2_000_000_000,
        "market_cap_max": 150_000_000_000,
        "price_min": 15,
        "price_max": 350,
        "revenue_growth_min": 0,
        "earnings_growth_min": -10,
        "debt_to_equity_max": 200,
        "rsi_min": 20,  # Deeply oversold
        "rsi_max": 35,
        "iv_max": 100,
        "dte_min": 30,
        "dte_max": 60,
        "delta_min": 0.40,
        "delta_max": 0.55
    },
    "swing_iv_play": {
        "description": "Low IV entry for swing trades - maximize leverage",
        "category": "swing",
        "market_cap_min": 5_000_000_000,
        "market_cap_max": 300_000_000_000,
        "price_min": 20,
        "price_max": 400,
        "revenue_growth_min": 5,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 180,
        "rsi_min": 35,
        "rsi_max": 65,
        "iv_max": 35,  # Very low IV - cheap options
        "dte_min": 30,
        "dte_max": 60,
        "delta_min": 0.45,
        "delta_max": 0.55
    },

    # ==========================================================================
    # WEEKLY/SHORT-TERM PRESETS (1-3 weeks)
    # ==========================================================================
    "weekly_momentum": {
        "description": "Weekly momentum plays - quick profits",
        "category": "weekly",
        "market_cap_min": 5_000_000_000,
        "market_cap_max": 5_000_000_000_000,
        "price_min": 20,
        "price_max": 500,
        "revenue_growth_min": 0,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 200,
        "rsi_min": 50,  # Strong momentum
        "rsi_max": 70,
        "iv_max": 70,
        "dte_min": 7,
        "dte_max": 21,
        "delta_min": 0.50,
        "delta_max": 0.65
    },
    "pre_earnings_iv": {
        "description": "Pre-earnings IV expansion plays (days_to_earnings best-effort)",
        "category": "earnings",
        "market_cap_min": 2_000_000_000,
        "market_cap_max": 200_000_000_000,
        "price_min": 15,
        "price_max": 400,
        "revenue_growth_min": 10,
        "earnings_growth_min": 5,
        "debt_to_equity_max": 200,
        "rsi_min": 35,
        "rsi_max": 65,
        "iv_max": 60,  # IV still low, room to expand
        "dte_min": 14,
        "dte_max": 45,
        "delta_min": 0.45,
        "delta_max": 0.55,
        "days_to_earnings_max": 14  # Within 2 weeks of earnings
    },

    # ==========================================================================
    # VALUE INVESTING PRESETS
    # ==========================================================================
    "deep_value": {
        "description": "Benjamin Graham style — P/E<15, P/B<1.5, low debt",
        "category": "value",
        "market_cap_min": 500_000_000,
        "market_cap_max": 50_000_000_000,
        "price_min": 5,
        "price_max": 300,
        "revenue_growth_min": -10,   # Value stocks may have flat/slow growth
        "earnings_growth_min": -10,
        "debt_to_equity_max": 100,
        "current_ratio_min": 1.5,
        "rsi_min": 20,
        "rsi_max": 65,
        "iv_max": 100,
        "pe_min": 0,       # Must be profitable
        "pe_max": 15,
        "pb_max": 1.5,
        "skip_sector_filter": True,
    },
    "garp": {
        "description": "Growth at Reasonable Price — PEG<1.5, P/E<25, ROE>12%",
        "category": "value",
        "market_cap_min": 1_000_000_000,
        "market_cap_max": 100_000_000_000,
        "price_min": 5,
        "price_max": 400,
        "revenue_growth_min": 10,
        "earnings_growth_min": 5,
        "debt_to_equity_max": 200,
        "rsi_min": 25,
        "rsi_max": 70,
        "iv_max": 100,
        "pe_min": 0,
        "pe_max": 25,
        "peg_max": 1.5,
        "roe_min": 0.12,
        "skip_sector_filter": True,
    },
    "undervalued_large_cap": {
        "description": "Large caps at a discount — pulled back from highs",
        "category": "value",
        "market_cap_min": 10_000_000_000,
        "market_cap_max": 5_000_000_000_000,
        "price_min": 20,
        "price_max": 500,
        "revenue_growth_min": 0,
        "earnings_growth_min": -5,
        "debt_to_equity_max": 200,
        "rsi_min": 25,     # Oversold / pullback
        "rsi_max": 55,
        "iv_max": 80,
        "pe_max": 20,
        "peg_max": 2.0,
        "roe_min": 0.10,
        "skip_sector_filter": True,
    },

    # ==========================================================================
    # DIVIDEND & INCOME PRESETS
    # ==========================================================================
    "dividend_income": {
        "description": "High yield income — 2.5%+ yield, sustainable margins",
        "category": "dividend",
        "market_cap_min": 5_000_000_000,
        "market_cap_max": 5_000_000_000_000,
        "price_min": 10,
        "price_max": 300,
        "revenue_growth_min": -5,
        "earnings_growth_min": -10,
        "debt_to_equity_max": 200,
        "rsi_min": 25,
        "rsi_max": 70,
        "iv_max": 80,
        "pe_min": 0,
        "pe_max": 25,
        "dividend_yield_min": 0.025,  # 2.5%
        "profit_margin_min": 0.08,
        "skip_sector_filter": True,
    },
    "dividend_growth": {
        "description": "Growing dividends + capital appreciation",
        "category": "dividend",
        "market_cap_min": 2_000_000_000,
        "market_cap_max": 300_000_000_000,
        "price_min": 10,
        "price_max": 400,
        "revenue_growth_min": 5,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 200,
        "rsi_min": 25,
        "rsi_max": 70,
        "iv_max": 80,
        "pe_min": 0,
        "pe_max": 30,
        "dividend_yield_min": 0.01,   # 1%
        "dividend_yield_max": 0.06,   # 6% cap — yields >6% often signal trouble
        "roe_min": 0.12,
        "skip_sector_filter": True,
    },

    # ==========================================================================
    # SMALL CAP PRESETS
    # ==========================================================================
    "small_cap_growth": {
        "description": "High growth small caps — multi-bagger potential",
        "category": "small_cap",
        "market_cap_min": 300_000_000,
        "market_cap_max": 3_000_000_000,
        "price_min": 3,
        "price_max": 100,
        "revenue_growth_min": 20,
        "earnings_growth_min": 15,
        "debt_to_equity_max": 200,
        "rsi_min": 25,
        "rsi_max": 75,
        "iv_max": 120,
    },
    "small_cap_value": {
        "description": "Undervalued small caps with solid fundamentals",
        "category": "small_cap",
        "market_cap_min": 300_000_000,
        "market_cap_max": 3_000_000_000,
        "price_min": 3,
        "price_max": 100,
        "revenue_growth_min": -5,
        "earnings_growth_min": -10,
        "debt_to_equity_max": 150,
        "rsi_min": 20,
        "rsi_max": 65,
        "iv_max": 100,
        "pe_min": 0,
        "pe_max": 18,
        "pb_max": 2.0,
        "skip_sector_filter": True,
    },

    # ==========================================================================
    # SENTIMENT PLAYS PRESETS
    # ==========================================================================
    "insider_buying": {
        "description": "Beaten-down quality — smart money accumulation profile",
        "category": "sentiment",
        "market_cap_min": 500_000_000,
        "market_cap_max": 100_000_000_000,
        "price_min": 5,
        "price_max": 300,
        "revenue_growth_min": -10,
        "earnings_growth_min": -15,
        "debt_to_equity_max": 200,
        "rsi_min": 20,     # Often beaten down when insiders buy
        "rsi_max": 65,
        "iv_max": 100,
        "skip_sector_filter": True,
    },
    "short_squeeze": {
        "description": "Squeeze candidates — recovering momentum, elevated IV",
        "category": "sentiment",
        "market_cap_min": 300_000_000,
        "market_cap_max": 50_000_000_000,
        "price_min": 3,
        "price_max": 200,
        "revenue_growth_min": -10,
        "earnings_growth_min": -15,
        "debt_to_equity_max": 300,
        "rsi_min": 40,     # Recovering
        "rsi_max": 75,
        "iv_max": 150,
    },

    # ==========================================================================
    # OPTIONS INCOME PRESETS
    # ==========================================================================
    "covered_call": {
        "description": "Sell calls against holdings — range-bound, low beta",
        "category": "options_income",
        "market_cap_min": 10_000_000_000,
        "market_cap_max": 5_000_000_000_000,
        "price_min": 20,
        "price_max": 400,
        "revenue_growth_min": 0,
        "earnings_growth_min": -5,
        "debt_to_equity_max": 150,
        "rsi_min": 35,     # Range-bound ideal
        "rsi_max": 65,
        "iv_max": 80,
        "beta_max": 1.2,
        "dividend_yield_min": 0.005,  # 0.5%
        "skip_sector_filter": True,
    },
    "wheel_strategy": {
        "description": "Sell puts then covered calls — quality at fair price",
        "category": "options_income",
        "market_cap_min": 5_000_000_000,
        "market_cap_max": 200_000_000_000,
        "price_min": 15,     # Manageable 100-share lots
        "price_max": 200,
        "revenue_growth_min": 0,
        "earnings_growth_min": -5,
        "debt_to_equity_max": 200,
        "rsi_min": 30,
        "rsi_max": 65,
        "iv_max": 80,
        "pe_min": 0,
        "pe_max": 30,
        "skip_sector_filter": True,
    },

    # ==========================================================================
    # OPTIONS DIRECTIONAL PRESETS
    # ==========================================================================
    "bull_call_spread": {
        "description": "Defined-risk bullish — 30-90 DTE, delta 0.40-0.60",
        "category": "options_directional",
        "market_cap_min": 2_000_000_000,
        "market_cap_max": 200_000_000_000,
        "price_min": 10,
        "price_max": 400,
        "revenue_growth_min": 5,
        "earnings_growth_min": 0,
        "debt_to_equity_max": 200,
        "rsi_min": 35,
        "rsi_max": 60,
        "iv_max": 80,
        "dte_min": 30,
        "dte_max": 90,
        "delta_min": 0.40,
        "delta_max": 0.60,
    },
    "leaps_deep_itm": {
        "description": "Stock replacement LEAPS — delta 0.70-0.90, low extrinsic",
        "category": "options_directional",
        "market_cap_min": 10_000_000_000,
        "market_cap_max": 5_000_000_000_000,
        "price_min": 20,
        "price_max": 500,
        "revenue_growth_min": 0,
        "earnings_growth_min": -5,
        "debt_to_equity_max": 150,
        "rsi_min": 30,
        "rsi_max": 70,
        "iv_max": 50,      # Low extrinsic
        "dte_min": 365,
        "dte_max": 730,
        "delta_min": 0.70,
        "delta_max": 0.90,
    },
}

# Backward-compat alias: "iv_crush" -> "low_iv_entry"
LEAPS_PRESETS["iv_crush"] = LEAPS_PRESETS["low_iv_entry"]


# ---------------------------------------------------------------------------
# Preset display names for frontend labelling
# ---------------------------------------------------------------------------

_PRESET_DISPLAY_NAMES: Dict[str, str] = {}
for _cat_presets in [
    [("conservative", "Conservative"), ("moderate", "Moderate"), ("aggressive", "Aggressive")],
    [("low_iv_entry", "Low IV Entry"), ("iv_crush", "Low IV Entry"),  # alias
     ("cheap_leaps", "Cheap LEAPS"), ("momentum", "Momentum"),
     ("turnaround", "Turnaround"), ("growth_leaps", "Growth LEAPS"), ("blue_chip_leaps", "Blue Chip LEAPS")],
    [("swing_momentum", "Swing Momentum"), ("swing_breakout", "Swing Breakout"),
     ("swing_oversold", "Swing Oversold"), ("swing_iv_play", "Swing IV Play")],
    [("weekly_momentum", "Weekly Momentum"), ("pre_earnings_iv", "Pre-Earnings IV")],
    [("deep_value", "Deep Value"), ("garp", "GARP"), ("undervalued_large_cap", "Undervalued Large Cap")],
    [("dividend_income", "High Yield Income"), ("dividend_growth", "Dividend Growth")],
    [("small_cap_growth", "Small Cap Growth"), ("small_cap_value", "Small Cap Value")],
    [("insider_buying", "Insider Buying"), ("short_squeeze", "Short Squeeze")],
    [("covered_call", "Covered Call"), ("wheel_strategy", "Wheel Strategy")],
    [("bull_call_spread", "Bull Call Spread"), ("leaps_deep_itm", "LEAPS Deep ITM")],
]:
    for _pid, _pname in _cat_presets:
        _PRESET_DISPLAY_NAMES[_pid] = _pname


# ---------------------------------------------------------------------------
# Preset resolution helper — single gatekeeper for automation paths
# ---------------------------------------------------------------------------

def resolve_preset(
    preset_name: str,
    source: str = "unknown",
    strict: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """Resolve a preset name to its config dict.

    In strict mode (default in CI/replay/auto), raises ValueError on unknown preset.
    In non-strict mode, logs error and returns None.

    Args:
        preset_name: The preset key to look up in LEAPS_PRESETS.
        source: Caller identifier for logging ("auto_scan", "replay", "manual_ui").
        strict: If True, raise on missing. If None, reads PRESET_CATALOG_STRICT env var
                (defaults to "true" — fail-fast by default).
    """
    config = LEAPS_PRESETS.get(preset_name)
    if config is not None:
        return config

    if strict is None:
        strict = os.environ.get("PRESET_CATALOG_STRICT", "true").lower() == "true"

    if strict:
        raise ValueError(
            f"[{source}] Unknown preset '{preset_name}' — not found in preset catalog "
            f"(available: {sorted(k for k in LEAPS_PRESETS.keys() if k != 'iv_crush')})"
        )
    else:
        logger.error(f"[{source}] Unknown preset '{preset_name}' — skipping")
        return None


def get_catalog_hash() -> str:
    """Deterministic hash of preset catalog keys.

    Changes whenever a preset is added, removed, or renamed.
    Useful for audit trails and replay debugging.
    """
    keys = sorted(LEAPS_PRESETS.keys())
    return hashlib.sha256(",".join(keys).encode()).hexdigest()[:8]
