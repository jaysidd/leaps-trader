"""
Archetypal mock stock data for pipeline tests.

4 stock archetypes with complete data at every pipeline layer:
- STRONG ("BULL"): Passes all gates with HIGH confidence
- WEAK ("BEAR"): Fails fundamentals early
- EDGE ("EDGE"): Barely passes, exploits gate penalty cap
- NODATA ("NODATA"): Missing data, tests graceful degradation
"""
from tests.pipeline.helpers import (
    make_signal_engine_df,
    make_screening_result,
    make_fresh_metrics,
    make_alpaca_snapshot,
)


# =========================================================================
# STRONG STOCK — "BULL"
# Should pass all gates, reach HIGH confidence, and execute a trade.
# =========================================================================
STRONG_FUNDAMENTALS = {
    "revenue_growth": 0.35,
    "earnings_growth": 0.30,
    "profit_margins": 0.22,
    "gross_margins": 0.55,
    "return_on_equity": 0.25,
    "debt_to_equity": 50.0,
    "current_ratio": 2.5,
    "quick_ratio": 2.0,
    "operating_margins": 0.20,
    "market_cap": 80_000_000_000,
    "current_price": 150.0,
    "trailing_pe": 25.0,
    "forward_pe": 20.0,
    "peg_ratio": 1.2,
    "price_to_book": 8.0,
    "dividend_yield": 0.005,
    "beta": 1.1,
    "roe": 0.25,
}

STRONG_STOCK_DATA = make_screening_result(
    symbol="BULL",
    score=72.0,
    passed_all=True,
    market_cap=80_000_000_000,
    iv_rank=35.0,
    avg_volume=5_000_000,
    current_price=150.0,
    fundamental_score=85.0,
    technical_score=75.0,
    options_score=70.0,
    momentum_score=65.0,
)

STRONG_FRESH_METRICS = make_fresh_metrics(
    rsi=58.0,
    sma20=148.0,
    sma50=145.0,
    sma200=135.0,
    adx=32.0,
    atr=3.5,
)

STRONG_SNAPSHOT = make_alpaca_snapshot(
    current_price=150.0,
    change_percent=2.1,
    volume=7_500_000,
    prev_volume=5_000_000,
    bid=149.95,
    ask=150.05,
)

STRONG_SIGNAL_DF = make_signal_engine_df(
    n=100,
    base_price=150.0,
    ema8=151.0,      # EMA8 > EMA21 (bullish)
    ema21=148.5,
    rsi=62.0,        # Above 60 = strong momentum (+15)
    atr=3.5,
    atr_percent=0.023,  # Above min_atr * 1.5 (+5)
    rvol=2.2,        # Strong relative volume (+10)
    volume_spike=True,  # Volume spike (+10)
    adx=32.0,
    trend="bullish",
)


# =========================================================================
# WEAK STOCK — "BEAR"
# Should fail at the fundamental gate in screening.
# Weak revenue, negative earnings, high debt.
# =========================================================================
WEAK_FUNDAMENTALS = {
    "revenue_growth": 0.02,
    "earnings_growth": -0.15,
    "profit_margins": 0.03,
    "gross_margins": 0.25,
    "return_on_equity": 0.04,
    "debt_to_equity": 250.0,
    "current_ratio": 0.8,
    "quick_ratio": 0.5,
    "operating_margins": 0.02,
    "market_cap": 3_000_000_000,
    "current_price": 25.0,
    "trailing_pe": 55.0,
    "forward_pe": 40.0,
    "peg_ratio": 5.0,
    "price_to_book": 1.5,
    "dividend_yield": 0.0,
    "beta": 1.8,
    "roe": 0.04,
}

WEAK_STOCK_DATA = make_screening_result(
    symbol="BEAR",
    score=18.0,  # Below MIN_COMPOSITE_SCORE (20 or 30)
    passed_all=False,
    market_cap=3_000_000_000,
    iv_rank=75.0,
    avg_volume=800_000,
    current_price=25.0,
    fundamental_score=25.0,
    technical_score=30.0,
    options_score=40.0,
    momentum_score=15.0,
)

WEAK_FRESH_METRICS = make_fresh_metrics(
    rsi=38.0,
    sma20=26.0,
    sma50=28.0,    # SMA50 > SMA20 (bearish)
    sma200=32.0,   # SMA200 > SMA50 (bearish)
    adx=18.0,      # Below minimum
    atr=0.8,
)

WEAK_SNAPSHOT = make_alpaca_snapshot(
    current_price=25.0,
    change_percent=-1.5,
    volume=400_000,
    prev_volume=800_000,
    bid=24.90,
    ask=25.15,  # Wide spread
)

WEAK_SIGNAL_DF = make_signal_engine_df(
    n=100,
    base_price=25.0,
    ema8=24.8,       # EMA8 < EMA21 (bearish for long)
    ema21=25.5,
    rsi=38.0,        # Below 40 (no long momentum bonus)
    atr=0.8,
    atr_percent=0.032,
    rvol=0.5,        # Below 0.8 pivot
    volume_spike=False,
    adx=18.0,
    trend="bearish",
)


# =========================================================================
# EDGE CASE STOCK — "EDGE"
# Barely passes screening gates, exploits the gate penalty cap.
# This is the SN-like stock: technically passes but quality is weak.
# =========================================================================
EDGE_FUNDAMENTALS = {
    "revenue_growth": 0.08,
    "earnings_growth": 0.05,
    "profit_margins": 0.10,
    "gross_margins": 0.35,
    "return_on_equity": 0.12,
    "debt_to_equity": 80.0,
    "current_ratio": 1.3,
    "quick_ratio": 1.0,
    "operating_margins": 0.08,
    "market_cap": 5_000_000_000,
    "current_price": 45.0,
    "trailing_pe": 22.0,
    "forward_pe": 18.0,
    "peg_ratio": 2.5,
    "price_to_book": 3.0,
    "dividend_yield": 0.01,
    "beta": 1.3,
    "roe": 0.12,
}

EDGE_STOCK_DATA = make_screening_result(
    symbol="EDGE",
    score=32.0,  # Just above new MIN_COMPOSITE_SCORE (30)
    passed_all=True,
    market_cap=5_000_000_000,
    iv_rank=62.0,  # Elevated IV
    avg_volume=1_500_000,
    current_price=45.0,
    fundamental_score=55.0,
    technical_score=45.0,
    options_score=50.0,
    momentum_score=30.0,
)

EDGE_FRESH_METRICS = make_fresh_metrics(
    rsi=42.0,       # Oversold territory — edge case
    sma20=44.5,
    sma50=44.0,
    sma200=43.0,
    adx=22.0,       # Barely above minimum
    atr=1.2,
)

EDGE_SNAPSHOT = make_alpaca_snapshot(
    current_price=45.0,
    change_percent=0.5,
    volume=1_200_000,
    prev_volume=1_500_000,
    bid=44.90,
    ask=45.10,
)

# Key: ATR% and RVOL both well below pivots → raw gate penalty = ~-35 to -40
EDGE_SIGNAL_DF = make_signal_engine_df(
    n=100,
    base_price=45.0,
    ema8=45.2,       # EMA8 slightly above EMA21 (weak bullish)
    ema21=44.8,
    rsi=42.0,        # Below 55 — no momentum bonus
    atr=1.2,
    atr_percent=0.027,  # Below optimal pivot
    rvol=0.6,        # Well below 0.8 pivot → large RVOL penalty
    rvol_tod=None,
    volume_spike=False,  # No volume confirmation
    adx=22.0,
    trend="bullish",
)


# =========================================================================
# MISSING DATA STOCK — "NODATA"
# Partially missing data to test graceful degradation.
# =========================================================================
NODATA_FUNDAMENTALS = {
    "revenue_growth": None,
    "earnings_growth": None,
    "profit_margins": None,
    "gross_margins": None,
    "return_on_equity": None,
    "debt_to_equity": None,
    "current_ratio": None,
    "quick_ratio": None,
    "operating_margins": None,
    "market_cap": None,
    "current_price": None,
}

NODATA_STOCK_DATA = make_screening_result(
    symbol="NODATA",
    score=0.0,
    passed_all=False,
    market_cap=0,
    iv_rank=None,
    avg_volume=0,
    current_price=0.0,
    fundamental_score=0.0,
    technical_score=0.0,
    options_score=0.0,
    momentum_score=0.0,
)

NODATA_FRESH_METRICS = {}  # No FMP data available

NODATA_SNAPSHOT = {}  # No Alpaca snapshot available
