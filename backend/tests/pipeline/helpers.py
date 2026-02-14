"""
DataFrame builders and helpers for pipeline tests.

Provides factory functions for creating realistic market data DataFrames
that the signal engine and screening engine expect.
"""
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta


def make_price_df(
    n: int = 252,
    base_price: float = 100.0,
    trend: str = "bullish",
    volatility: float = 0.02,
    avg_volume: int = 2_000_000,
) -> pd.DataFrame:
    """
    Create a realistic OHLCV DataFrame for screening engine.

    Args:
        n: Number of trading days
        base_price: Starting price
        trend: "bullish", "bearish", or "flat"
        volatility: Daily volatility (std of returns)
        avg_volume: Average daily volume

    Returns:
        DataFrame with columns: open, high, low, close, volume
        Index: DatetimeIndex
    """
    np.random.seed(42)  # Reproducible

    # Daily returns with trend bias
    trend_bias = {"bullish": 0.0005, "bearish": -0.0005, "flat": 0.0}
    drift = trend_bias.get(trend, 0.0)

    returns = np.random.normal(drift, volatility, n)
    prices = base_price * np.cumprod(1 + returns)

    # Generate OHLC from close
    closes = prices
    opens = np.roll(closes, 1)
    opens[0] = base_price
    highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.005, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.005, n)))
    volumes = np.random.normal(avg_volume, avg_volume * 0.3, n).astype(int)
    volumes = np.maximum(volumes, 100_000)  # Floor

    dates = pd.date_range(end=datetime.now(timezone.utc), periods=n, freq="B")

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    }, index=dates)


def make_signal_engine_df(
    n: int = 100,
    base_price: float = 100.0,
    ema8: float = None,
    ema21: float = None,
    rsi: float = 55.0,
    atr: float = 2.0,
    atr_percent: float = 0.02,
    rvol: float = 1.5,
    rvol_tod: float = None,
    volume_spike: bool = True,
    adx: float = 30.0,
    macd: float = 0.5,
    macd_signal: float = 0.3,
    avg_volume: int = 2_000_000,
    trend: str = "bullish",
) -> pd.DataFrame:
    """
    Create a DataFrame with all columns the SignalEngine._calculate_confidence() expects.

    The LAST row (df.iloc[-1]) is the evaluation row — its indicator values
    are set to the specified parameters. Prior rows have realistic but
    less important values.

    Args:
        n: Number of bars
        base_price: Price for the evaluation bar
        ema8, ema21: EMA values (defaults derived from base_price and trend)
        rsi: RSI value (0-100)
        atr: ATR absolute value
        atr_percent: ATR as percentage of price
        rvol: Classic relative volume
        rvol_tod: Time-of-day adjusted relative volume
        volume_spike: Boolean volume spike flag
        adx: ADX trend strength
        macd, macd_signal: MACD values
        avg_volume: Average bar volume
        trend: "bullish" or "bearish" (for default EMA positions)
    """
    # Default EMA positions based on trend
    if ema8 is None:
        ema8 = base_price * (1.01 if trend == "bullish" else 0.99)
    if ema21 is None:
        ema21 = base_price * (0.995 if trend == "bullish" else 1.005)

    # Build DataFrame with n rows
    df_data = {
        "open": np.full(n, base_price),
        "high": np.full(n, base_price * 1.01),
        "low": np.full(n, base_price * 0.99),
        "close": np.full(n, base_price),
        "volume": np.full(n, avg_volume, dtype=int),
        "ema8": np.full(n, ema8),
        "ema21": np.full(n, ema21),
        "rsi": np.full(n, rsi),
        "atr": np.full(n, atr),
        "atr_percent": np.full(n, atr_percent),
        "rvol": np.full(n, rvol),
        "rvol_tod": np.full(n, rvol_tod if rvol_tod is not None else np.nan),
        "volume_spike": np.full(n, volume_spike),
        "adx": np.full(n, adx),
        "macd": np.full(n, macd),
        "macd_signal": np.full(n, macd_signal),
        "sma_20": np.full(n, base_price * 0.98),
        "sma_50": np.full(n, base_price * 0.95),
        "sma_200": np.full(n, base_price * 0.90),
        "bb_upper": np.full(n, base_price * 1.05),
        "bb_lower": np.full(n, base_price * 0.95),
        "vwap": np.full(n, base_price * 1.001),
    }

    dates = pd.date_range(end=datetime.now(timezone.utc), periods=n, freq="5min")
    df = pd.DataFrame(df_data, index=dates)

    # Set the evaluation row (last row) with exact specified values
    last = df.index[-1]
    df.loc[last, "close"] = base_price
    df.loc[last, "ema8"] = ema8
    df.loc[last, "ema21"] = ema21
    df.loc[last, "rsi"] = rsi
    df.loc[last, "atr"] = atr
    df.loc[last, "atr_percent"] = atr_percent
    df.loc[last, "rvol"] = rvol
    if rvol_tod is not None:
        df.loc[last, "rvol_tod"] = rvol_tod
    df.loc[last, "volume_spike"] = volume_spike
    df.loc[last, "adx"] = adx
    df.loc[last, "macd"] = macd
    df.loc[last, "macd_signal"] = macd_signal

    return df


def make_screening_result(
    symbol: str = "TEST",
    score: float = 45.0,
    passed_all: bool = True,
    market_cap: float = 10_000_000_000,
    iv_rank: float = 35.0,
    avg_volume: int = 3_000_000,
    **overrides,
) -> dict:
    """
    Create a stock_data dict as stored in SavedScanResult.stock_data.

    This is the format consumed by StrategySelector.select_strategies().
    """
    result = {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "score": score,
        "passed_all": passed_all,
        "market_cap": market_cap,
        "sector": "Technology",
        "iv_rank": iv_rank,
        "iv_percentile": iv_rank,
        "current_price": 100.0,
        "technical_indicators": {
            "avg_volume": avg_volume,
            "current_price": 100.0,
            "sma_50": 98.0,
            "sma_200": 95.0,
            "rsi_14": 55.0,
        },
        "fundamental_score": 70.0,
        "technical_score": 60.0,
        "options_score": 55.0,
        "momentum_score": 50.0,
    }
    result.update(overrides)
    return result


def make_fresh_metrics(
    rsi: float = 55.0,
    sma20: float = 100.0,
    sma50: float = 98.0,
    sma200: float = 95.0,
    adx: float = 28.0,
    atr: float = 2.5,
    **overrides,
) -> dict:
    """
    Create a fresh_metrics dict as returned by fmp_service.get_strategy_metrics().

    Used by StrategySelector for timeframe qualification.
    """
    result = {
        "rsi": rsi,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "adx": adx,
        "atr": atr,
    }
    result.update(overrides)
    return result


def make_alpaca_snapshot(
    current_price: float = 100.0,
    change_percent: float = 1.5,
    volume: int = 3_000_000,
    prev_volume: int = 2_000_000,
    bid: float = 99.95,
    ask: float = 100.05,
) -> dict:
    """
    Create a snapshot dict as returned by alpaca_service.get_snapshot().

    Used by StrategySelector for volume ratio, spread, and price checks.
    """
    return {
        "current_price": current_price,
        "change_percent": change_percent,
        "volume": volume,
        "daily_bar": {
            "open": current_price * 0.99,
            "high": current_price * 1.02,
            "low": current_price * 0.98,
            "close": current_price,
            "volume": volume,
        },
        "prev_daily_bar": {
            "close": current_price * (1 - change_percent / 100),
            "volume": prev_volume,
        },
        "latest_quote": {
            "bid": bid,
            "ask": ask,
        },
    }
