"""
Technical analysis module - Calculate technical indicators
"""
import pandas as pd
import numpy as np
from ta.trend import SMAIndicator, EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from typing import Dict, Any, Optional
from loguru import logger


class TechnicalAnalysis:
    """Calculate technical indicators from price data"""

    @staticmethod
    def has_sufficient_data(df: pd.DataFrame, min_trading_days: int = 200) -> bool:
        """Check if DataFrame has enough trading days for reliable indicators."""
        return df is not None and not df.empty and len(df) >= min_trading_days

    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all technical indicators

        Args:
            df: DataFrame with OHLCV data (must have 'close', 'high', 'low', 'volume' columns)

        Returns:
            DataFrame with all indicators added
        """
        if df.empty or len(df) < 200:  # Need at least 200 periods for SMA200
            logger.warning("Insufficient data for technical indicators")
            return df

        try:
            # Make a copy to avoid modifying original
            df = df.copy()

            # Simple Moving Averages
            df['sma_20'] = SMAIndicator(close=df['close'], window=20).sma_indicator()
            df['sma_50'] = SMAIndicator(close=df['close'], window=50).sma_indicator()
            df['sma_200'] = SMAIndicator(close=df['close'], window=200).sma_indicator()

            # Exponential Moving Averages
            df['ema_12'] = EMAIndicator(close=df['close'], window=12).ema_indicator()
            df['ema_26'] = EMAIndicator(close=df['close'], window=26).ema_indicator()

            # RSI
            rsi = RSIIndicator(close=df['close'], window=14)
            df['rsi_14'] = rsi.rsi()

            # MACD
            macd = MACD(close=df['close'])
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            df['macd_histogram'] = macd.macd_diff()

            # Bollinger Bands
            bb = BollingerBands(close=df['close'], window=20, window_dev=2)
            df['bollinger_upper'] = bb.bollinger_hband()
            df['bollinger_middle'] = bb.bollinger_mavg()
            df['bollinger_lower'] = bb.bollinger_lband()

            # ATR (Average True Range)
            atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
            df['atr_14'] = atr.average_true_range()

            # ADX (Average Directional Index) - trend strength
            adx = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14)
            df['adx_14'] = adx.adx()

            return df

        except Exception as e:
            logger.error(f"Error calculating technical indicators: {e}")
            return df

    @staticmethod
    def get_latest_indicators(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get latest values of all indicators

        Args:
            df: DataFrame with calculated indicators

        Returns:
            Dict with latest indicator values
        """
        if df.empty:
            return {}

        latest = df.iloc[-1]

        return {
            'sma_20': float(latest.get('sma_20', 0)) if pd.notna(latest.get('sma_20')) else None,
            'sma_50': float(latest.get('sma_50', 0)) if pd.notna(latest.get('sma_50')) else None,
            'sma_200': float(latest.get('sma_200', 0)) if pd.notna(latest.get('sma_200')) else None,
            'ema_12': float(latest.get('ema_12', 0)) if pd.notna(latest.get('ema_12')) else None,
            'ema_26': float(latest.get('ema_26', 0)) if pd.notna(latest.get('ema_26')) else None,
            'rsi_14': float(latest.get('rsi_14', 0)) if pd.notna(latest.get('rsi_14')) else None,
            'macd': float(latest.get('macd', 0)) if pd.notna(latest.get('macd')) else None,
            'macd_signal': float(latest.get('macd_signal', 0)) if pd.notna(latest.get('macd_signal')) else None,
            'macd_histogram': float(latest.get('macd_histogram', 0)) if pd.notna(latest.get('macd_histogram')) else None,
            'bollinger_upper': float(latest.get('bollinger_upper', 0)) if pd.notna(latest.get('bollinger_upper')) else None,
            'bollinger_middle': float(latest.get('bollinger_middle', 0)) if pd.notna(latest.get('bollinger_middle')) else None,
            'bollinger_lower': float(latest.get('bollinger_lower', 0)) if pd.notna(latest.get('bollinger_lower')) else None,
            'atr_14': float(latest.get('atr_14', 0)) if pd.notna(latest.get('atr_14')) else None,
            'adx_14': float(latest.get('adx_14', 0)) if pd.notna(latest.get('adx_14')) else None,
            'current_price': float(latest.get('close', 0)) if pd.notna(latest.get('close')) else None,
            'volume': int(latest.get('volume', 0)) if pd.notna(latest.get('volume')) else None,
            'price_change_percent': TechnicalAnalysis._calculate_price_change_percent(df),
        }

    @staticmethod
    def _calculate_price_change_percent(df: pd.DataFrame) -> Optional[float]:
        """Calculate daily price change percentage from the previous trading day"""
        if df is None or df.empty or len(df) < 2:
            return None

        try:
            current_close = df.iloc[-1].get('close')
            prev_close = df.iloc[-2].get('close')

            if pd.notna(current_close) and pd.notna(prev_close) and prev_close > 0:
                return float(((current_close - prev_close) / prev_close) * 100)
            return None
        except Exception:
            return None

    @staticmethod
    def check_macd_crossover(df: pd.DataFrame, lookback_periods: int = 20) -> Optional[int]:
        """
        Check if MACD has crossed above signal line recently

        Args:
            df: DataFrame with MACD indicators
            lookback_periods: How many periods to look back

        Returns:
            Number of periods ago when crossover occurred, or None
        """
        if df.empty or len(df) < lookback_periods:
            return None

        try:
            # Get last N periods
            recent = df.tail(lookback_periods).copy()

            # Check for crossover (MACD crosses above signal)
            recent['crossover'] = (recent['macd'] > recent['macd_signal']) & \
                                  (recent['macd'].shift(1) <= recent['macd_signal'].shift(1))

            # Find most recent crossover
            crossovers = recent[recent['crossover'] == True]

            if not crossovers.empty:
                # Return how many periods ago
                periods_ago = len(recent) - crossovers.index[-1] - 1
                return int(periods_ago)

            return None

        except Exception as e:
            logger.error(f"Error checking MACD crossover: {e}")
            return None

    @staticmethod
    def calculate_avg_volume(df: pd.DataFrame, window: int = 50) -> Optional[float]:
        """
        Calculate average volume over window

        Args:
            df: DataFrame with volume data
            window: Window size for average

        Returns:
            Average volume
        """
        if df.empty or len(df) < window:
            return None

        try:
            return float(df['volume'].tail(window).mean())
        except Exception as e:
            logger.error(f"Error calculating average volume: {e}")
            return None

    @staticmethod
    def detect_breakout(df: pd.DataFrame, lookback: int = 60) -> bool:
        """
        Detect if there was a recent breakout (price broke above resistance)

        Args:
            df: DataFrame with price data
            lookback: Periods to look back for resistance level

        Returns:
            True if breakout detected
        """
        if df.empty or len(df) < lookback:
            return False

        try:
            recent = df.tail(lookback)

            # Calculate resistance (highest high in lookback period, excluding last 5 days)
            resistance = recent['high'].iloc[:-5].max()

            # Check if current price broke above resistance in last 5 days
            recent_high = recent['high'].tail(5).max()

            return recent_high > resistance * 1.01  # 1% above resistance

        except Exception as e:
            logger.error(f"Error detecting breakout: {e}")
            return False

    @staticmethod
    def calculate_returns(df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate returns over different periods

        Args:
            df: DataFrame with price data

        Returns:
            Dict with 1m, 3m, 6m, 1y returns
        """
        if df.empty:
            return {}

        try:
            current_price = df['close'].iloc[-1]
            returns = {}

            # 1 month (21 trading days)
            if len(df) >= 21:
                price_1m = df['close'].iloc[-21]
                returns['return_1m'] = (current_price - price_1m) / price_1m

            # 3 months (63 trading days)
            if len(df) >= 63:
                price_3m = df['close'].iloc[-63]
                returns['return_3m'] = (current_price - price_3m) / price_3m

            # 6 months (126 trading days)
            if len(df) >= 126:
                price_6m = df['close'].iloc[-126]
                returns['return_6m'] = (current_price - price_6m) / price_6m

            # 1 year (252 trading days)
            if len(df) >= 252:
                price_1y = df['close'].iloc[-252]
                returns['return_1y'] = (current_price - price_1y) / price_1y

            return returns

        except Exception as e:
            logger.error(f"Error calculating returns: {e}")
            return {}
