"""
Alpaca Market Data Service
Real-time and historical data for signal processing
"""
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from loguru import logger
import numpy as np
import pandas as pd

from app.config import get_settings

ET = ZoneInfo("America/New_York")

settings = get_settings()

# Alpaca SDK imports (with fallback for when not installed)
try:
    from alpaca.data import StockHistoricalDataClient
    from alpaca.data.historical.crypto import CryptoHistoricalDataClient
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.live import StockDataStream
    from alpaca.data.requests import (
        StockBarsRequest,
        StockQuotesRequest,
        StockSnapshotRequest,
        StockTradesRequest,
        CryptoSnapshotRequest,
    )
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    ALPACA_AVAILABLE = True
except ImportError as e:
    ALPACA_AVAILABLE = False
    logger.warning(f"alpaca-py data module import failed: {e}")
except Exception as e:
    ALPACA_AVAILABLE = False
    logger.error(f"alpaca-py data module unexpected error during import: {e}")


class AlpacaService:
    """
    Alpaca Market Data Service for real-time and historical data.
    Used by the signal engine for intraday analysis.
    """

    def __init__(self):
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_SECRET_KEY
        self.data_feed = settings.ALPACA_DATA_FEED  # 'iex' (free) or 'sip' (paid)

        self._data_client = None
        self._crypto_client = None
        self._option_client = None
        self._trading_client = None  # For option contract lookups (reused)
        self._stream = None

        self._try_init()

    def _try_init(self):
        """Attempt to initialize Alpaca clients. Safe to call multiple times."""
        if self._data_client is not None:
            return  # Already initialized

        if not ALPACA_AVAILABLE:
            logger.error("Alpaca SDK not available")
            return

        # Re-read keys from settings in case they were set after module import
        self.api_key = settings.ALPACA_API_KEY
        self.secret_key = settings.ALPACA_SECRET_KEY

        if not self.api_key or not self.secret_key:
            logger.warning("Alpaca API keys not configured")
            return

        try:
            # Initialize stock data client
            self._data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key
            )
            # Initialize crypto data client (no auth required, but keys increase rate limit)
            self._crypto_client = CryptoHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key
            )
            # Initialize options data client
            self._option_client = OptionHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key
            )
            # Initialize trading client for option contract lookups (reused)
            from alpaca.trading.client import TradingClient
            self._trading_client = TradingClient(
                self.api_key, self.secret_key, paper=True
            )
            logger.info(f"Alpaca data client initialized (feed: {self.data_feed})")
        except Exception as e:
            logger.error(f"Failed to initialize Alpaca client: {e}")

    def reinitialize(self, api_key: str = None, secret_key: str = None):
        """
        Reinitialize with new credentials. Called when API keys are updated
        via the Settings UI at runtime.
        """
        if api_key:
            self.api_key = api_key
        if secret_key:
            self.secret_key = secret_key

        # Reset clients so _try_init will recreate them
        self._data_client = None
        self._crypto_client = None
        self._option_client = None
        self._trading_client = None

        self._try_init()
        return self.is_available

    @property
    def is_available(self) -> bool:
        """Check if Alpaca service is properly configured. Tries lazy init if not yet ready."""
        if self._data_client is None and ALPACA_AVAILABLE:
            self._try_init()  # Lazy retry in case keys were set after module import
        return ALPACA_AVAILABLE and self._data_client is not None

    def _get_timeframe(self, timeframe: str) -> Any:
        """Convert string timeframe to Alpaca TimeFrame"""
        if not ALPACA_AVAILABLE:
            return None

        tf_map = {
            "1m": TimeFrame(1, TimeFrameUnit.Minute),
            "5m": TimeFrame(5, TimeFrameUnit.Minute),
            "15m": TimeFrame(15, TimeFrameUnit.Minute),
            "30m": TimeFrame(30, TimeFrameUnit.Minute),
            "1h": TimeFrame(1, TimeFrameUnit.Hour),
            "4h": TimeFrame(4, TimeFrameUnit.Hour),
            "1d": TimeFrame(1, TimeFrameUnit.Day),
        }
        return tf_map.get(timeframe.lower(), TimeFrame(5, TimeFrameUnit.Minute))

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "5m",
        limit: int = 100,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> Optional[pd.DataFrame]:
        """
        Get historical bars for a symbol.

        Args:
            symbol: Stock ticker
            timeframe: Bar timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d)
            limit: Number of bars to fetch
            start: Start datetime (optional)
            end: End datetime (optional)

        Returns:
            DataFrame with columns: open, high, low, close, volume, vwap, trade_count
        """
        if not self.is_available:
            logger.warning("Alpaca service not available")
            return None

        try:
            tf = self._get_timeframe(timeframe)

            # Default to last trading day if no dates specified
            if not end:
                end = datetime.now(timezone.utc)
            if not start:
                # Go back enough time to get requested bars (account for weekends/holidays)
                # Use at least 7 days to ensure we capture trading day data
                if "m" in timeframe:
                    minutes = int(timeframe.replace("m", ""))
                    # At least 7 days back for intraday data
                    start = end - timedelta(days=max(7, (minutes * limit * 2) // 1440 + 1))
                elif "h" in timeframe:
                    hours = int(timeframe.replace("h", ""))
                    start = end - timedelta(days=max(7, (hours * limit * 2) // 24 + 1))
                else:
                    start = end - timedelta(days=limit * 2)

            request = StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=tf,
                start=start,
                end=end,
                limit=limit,
                feed=self.data_feed
            )

            bars = self._data_client.get_stock_bars(request)

            # Check if data exists (handle both old and new API formats)
            symbol_upper = symbol.upper()
            if hasattr(bars, 'data') and symbol_upper in bars.data:
                bar_list = bars.data[symbol_upper]
            elif symbol_upper in bars:
                bar_list = bars[symbol_upper]
            else:
                logger.warning(f"No bars returned for {symbol}")
                return None

            if not bar_list:
                logger.warning(f"Empty bars list for {symbol}")
                return None

            # Convert list of bar objects to DataFrame
            df = pd.DataFrame([{
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume,
                'vwap': bar.vwap,
                'trade_count': bar.trade_count,
                'timestamp': bar.timestamp
            } for bar in bar_list])

            # Rename columns for consistency
            df = df.rename(columns={
                'timestamp': 'datetime',
                'trade_count': 'trades'
            })

            # Sort by datetime
            df = df.sort_values('datetime')

            return df.tail(limit)

        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return None

    def get_snapshot(self, symbol: str) -> Optional[Dict]:
        """
        Get current snapshot (quote + daily bar) for a symbol.

        Returns dict with:
            - latest_trade: price, size, timestamp
            - latest_quote: bid, ask, bid_size, ask_size
            - daily_bar: open, high, low, close, volume, vwap
            - prev_daily_bar: previous day's OHLCV
        """
        if not self.is_available:
            logger.warning(f"Alpaca service not available for snapshot request: {symbol}")
            return None

        try:
            logger.debug(f"Fetching snapshot for {symbol} with feed={self.data_feed}")

            # Create request object for new API format
            request = StockSnapshotRequest(
                symbol_or_symbols=symbol.upper(),
                feed=self.data_feed
            )
            snapshots = self._data_client.get_stock_snapshot(request)

            # get_stock_snapshot returns a dict of {symbol: snapshot}
            snapshot = snapshots.get(symbol.upper())

            if not snapshot:
                logger.warning(f"Empty snapshot returned for {symbol}")
                return None

            logger.debug(f"Snapshot received for {symbol}: {type(snapshot)}")

            result = {
                "symbol": symbol.upper(),
                "timestamp": datetime.now().isoformat(),
            }

            # Latest trade
            if snapshot.latest_trade:
                result["latest_trade"] = {
                    "price": float(snapshot.latest_trade.price),
                    "size": snapshot.latest_trade.size,
                    "timestamp": snapshot.latest_trade.timestamp.isoformat()
                }
                result["current_price"] = float(snapshot.latest_trade.price)

            # Latest quote
            if snapshot.latest_quote:
                result["latest_quote"] = {
                    "bid": float(snapshot.latest_quote.bid_price),
                    "ask": float(snapshot.latest_quote.ask_price),
                    "bid_size": snapshot.latest_quote.bid_size,
                    "ask_size": snapshot.latest_quote.ask_size,
                    "spread": float(snapshot.latest_quote.ask_price - snapshot.latest_quote.bid_price)
                }

            # Daily bar
            if snapshot.daily_bar:
                result["daily_bar"] = {
                    "open": float(snapshot.daily_bar.open),
                    "high": float(snapshot.daily_bar.high),
                    "low": float(snapshot.daily_bar.low),
                    "close": float(snapshot.daily_bar.close),
                    "volume": snapshot.daily_bar.volume,
                    "vwap": float(snapshot.daily_bar.vwap) if snapshot.daily_bar.vwap else None,
                }

            # Previous day bar
            if snapshot.previous_daily_bar:
                result["prev_daily_bar"] = {
                    "open": float(snapshot.previous_daily_bar.open),
                    "high": float(snapshot.previous_daily_bar.high),
                    "low": float(snapshot.previous_daily_bar.low),
                    "close": float(snapshot.previous_daily_bar.close),
                    "volume": snapshot.previous_daily_bar.volume,
                    "vwap": float(snapshot.previous_daily_bar.vwap) if snapshot.previous_daily_bar.vwap else None,
                }

                # Calculate change
                prev_close = float(snapshot.previous_daily_bar.close)
                if result.get("current_price") and prev_close > 0:
                    result["change"] = result["current_price"] - prev_close
                    result["change_percent"] = ((result["current_price"] - prev_close) / prev_close) * 100

            return result

        except Exception as e:
            logger.error(f"Error fetching snapshot for {symbol}: {e}")
            return None

    def get_multi_snapshots(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get snapshots for multiple symbols at once"""
        if not self.is_available:
            return {}

        try:
            # Create request object for new API format
            request = StockSnapshotRequest(
                symbol_or_symbols=[s.upper() for s in symbols],
                feed=self.data_feed
            )
            snapshots = self._data_client.get_stock_snapshot(request)

            results = {}
            for symbol, snapshot in snapshots.items():
                result = {"symbol": symbol}

                if snapshot.latest_trade:
                    result["current_price"] = float(snapshot.latest_trade.price)

                if snapshot.daily_bar:
                    result["vwap"] = float(snapshot.daily_bar.vwap) if snapshot.daily_bar.vwap else None
                    result["volume"] = snapshot.daily_bar.volume
                    result["high"] = float(snapshot.daily_bar.high)
                    result["low"] = float(snapshot.daily_bar.low)

                if snapshot.previous_daily_bar:
                    prev_close = float(snapshot.previous_daily_bar.close)
                    if result.get("current_price") and prev_close > 0:
                        result["change_percent"] = ((result["current_price"] - prev_close) / prev_close) * 100

                results[symbol] = result

            return results

        except Exception as e:
            logger.error(f"Error fetching multi snapshots: {e}")
            return {}

    def get_crypto_snapshots(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Get snapshots for crypto symbols via Alpaca Crypto Data API.

        Args:
            symbols: List of crypto symbols as traded on Robinhood (e.g. ["BTC", "ETH"]).
                     Automatically converted to Alpaca format ("BTC/USD", "ETH/USD").

        Returns:
            Dict keyed by the original Robinhood symbol (e.g. "BTC") with price data.
        """
        if not self._crypto_client:
            return {}

        try:
            # Convert Robinhood-style symbols (BTC) to Alpaca format (BTC/USD)
            alpaca_symbols = [f"{s.upper()}/USD" for s in symbols]

            request = CryptoSnapshotRequest(symbol_or_symbols=alpaca_symbols)
            snapshots = self._crypto_client.get_crypto_snapshot(request)

            results = {}
            for alpaca_sym, snapshot in snapshots.items():
                # Map back to Robinhood symbol (BTC/USD -> BTC)
                rh_symbol = alpaca_sym.split("/")[0]
                result = {"symbol": rh_symbol}

                if snapshot.latest_trade:
                    result["current_price"] = float(snapshot.latest_trade.price)

                if snapshot.daily_bar:
                    result["vwap"] = float(snapshot.daily_bar.vwap) if snapshot.daily_bar.vwap else None
                    result["volume"] = snapshot.daily_bar.volume

                if snapshot.previous_daily_bar:
                    prev_close = float(snapshot.previous_daily_bar.close)
                    if result.get("current_price") and prev_close > 0:
                        result["change_percent"] = ((result["current_price"] - prev_close) / prev_close) * 100

                results[rh_symbol] = result

            return results

        except Exception as e:
            logger.error(f"Error fetching crypto snapshots: {e}")
            return {}

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators on bar data.
        Adds: EMA8, EMA21, SMA20, SMA50, SMA200, RSI, ATR, ADX, RVOL, volume_ma
        """
        if df is None or df.empty:
            return df

        try:
            # EMA calculations
            df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
            df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()

            # SMA20 (needed for trend following + mean reversion)
            if len(df) >= 20:
                df['sma20'] = df['close'].rolling(window=20).mean()

            # SMA50 (if enough data)
            if len(df) >= 50:
                df['sma50'] = df['close'].rolling(window=50).mean()

            # SMA200 (for daily trend structure)
            if len(df) >= 200:
                df['sma200'] = df['close'].rolling(window=200).mean()

            # RSI (14-period)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))

            # ATR (14-period)
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['atr'] = tr.rolling(window=14).mean()

            # ATR% (ATR as percentage of price)
            df['atr_percent'] = (df['atr'] / df['close']) * 100

            # ADX (14-period) — needed for trend following
            if len(df) >= 28:  # Need 2x period for smoothing
                plus_dm = df['high'].diff()
                minus_dm = -df['low'].diff()
                plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
                minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
                smoothed_tr = tr.rolling(window=14).sum()
                smoothed_tr = smoothed_tr.replace(0, float('nan'))
                plus_di = 100 * (plus_dm.rolling(window=14).sum() / smoothed_tr)
                minus_di = 100 * (minus_dm.rolling(window=14).sum() / smoothed_tr)
                di_sum = plus_di + minus_di
                di_sum = di_sum.replace(0, float('nan'))
                dx = 100 * ((plus_di - minus_di).abs() / di_sum)
                df['adx'] = dx.rolling(window=14).mean()

            # Volume MA (20-period)
            df['volume_ma20'] = df['volume'].rolling(window=20).mean()

            # RVOL (relative volume)
            if df['volume_ma20'].iloc[-1] > 0:
                df['rvol'] = df['volume'] / df['volume_ma20']
            else:
                df['rvol'] = 1.0

            # Volume spike (current volume vs MA)
            df['volume_spike'] = df['volume'] > (df['volume_ma20'] * 1.2)

            return df

        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return df

    def get_bars_with_indicators(
        self,
        symbol: str,
        timeframe: str = "5m",
        limit: int = 100
    ) -> Optional[pd.DataFrame]:
        """Get bars with technical indicators calculated"""
        df = self.get_bars(symbol, timeframe, limit)
        if df is not None:
            df = self.calculate_indicators(df)
        return df

    # Bar limits per timeframe to get >=10 trading days of history for TOD-RVOL
    TOD_BAR_LIMITS = {"5m": 900, "15m": 300, "1h": 250, "1d": 300}

    def get_time_of_day_rvol(
        self, df: pd.DataFrame, timeframe: str
    ) -> Optional[Tuple[int, float, float]]:
        """
        Calculate Time-of-Day RVOL by comparing the evaluation bar's volume
        to the median volume of the same time-of-day across prior days.

        For 5m/15m/1h: evaluation bar = last closed bar (iloc[-2])
        For 1d: evaluation bar = latest bar (iloc[-1]), even if partial

        Returns:
            (eval_bar_index, rvol_tod, tod_median_volume) or None if insufficient data
        """
        if df is None or len(df) < 30:
            return None

        try:
            # Determine evaluation bar index
            if timeframe == "1d":
                eval_idx = len(df) - 1  # daily: use current bar
            else:
                # 5m/15m/1h: use last closed bar
                if len(df) < 2:
                    return None
                eval_idx = len(df) - 2

            eval_bar = df.iloc[eval_idx]
            eval_volume = eval_bar.get('volume', 0)
            if eval_volume <= 0:
                return None

            # Convert evaluation bar timestamp to ET
            eval_dt = eval_bar.get('datetime')
            if eval_dt is None:
                return None

            if hasattr(eval_dt, 'tzinfo') and eval_dt.tzinfo is not None:
                eval_et = eval_dt.astimezone(ET)
            else:
                # Assume UTC if naive
                from datetime import timezone as tz
                eval_et = eval_dt.replace(tzinfo=tz.utc).astimezone(ET)

            eval_hour = eval_et.hour
            eval_minute = eval_et.minute
            eval_date = eval_et.date()

            # Filter df to bars matching same hour:minute on prior days
            matching_volumes = []
            for i in range(len(df)):
                if i == eval_idx:
                    continue
                bar = df.iloc[i]
                bar_dt = bar.get('datetime')
                if bar_dt is None:
                    continue

                if hasattr(bar_dt, 'tzinfo') and bar_dt.tzinfo is not None:
                    bar_et = bar_dt.astimezone(ET)
                else:
                    from datetime import timezone as tz
                    bar_et = bar_dt.replace(tzinfo=tz.utc).astimezone(ET)

                # Must be a different day
                if bar_et.date() == eval_date:
                    continue

                # Same time of day
                if bar_et.hour == eval_hour and bar_et.minute == eval_minute:
                    vol = bar.get('volume', 0)
                    if vol > 0:
                        matching_volumes.append(vol)

            # Require >= 5 matching bars
            if len(matching_volumes) < 5:
                return None

            tod_median_volume = float(np.median(matching_volumes))
            if tod_median_volume <= 0:
                return None

            # For 4h partial bar: pace-adjust volume
            actual_volume = eval_volume
            if timeframe == "4h":
                now_et = datetime.now(ET)
                bar_open_et = eval_et
                elapsed_minutes = (now_et - bar_open_et).total_seconds() / 60.0
                elapsed_fraction = elapsed_minutes / 240.0  # 4h = 240 min
                if elapsed_fraction < 0.10:
                    # Too early into bar to judge pace — return None for TOD
                    return None
                elapsed_fraction = min(elapsed_fraction, 1.0)
                actual_volume = eval_volume / elapsed_fraction

            rvol_tod = actual_volume / tod_median_volume
            return (eval_idx, rvol_tod, tod_median_volume)

        except Exception as e:
            logger.error(f"Error calculating TOD-RVOL: {e}")
            return None

    def get_bars_with_enhanced_indicators(
        self, symbol: str, timeframe: str
    ) -> Tuple[Optional[pd.DataFrame], int]:
        """
        Get bars with indicators + TOD-RVOL metrics.
        Auto-selects bar limit based on timeframe for TOD history.
        Stores rvol_tod and tod_avg_dollar_volume on the evaluation bar.

        Returns:
            (df, eval_bar_index) — all gates/strategies should read from df.iloc[eval_bar_index]
        """
        limit = self.TOD_BAR_LIMITS.get(timeframe, 900)
        df = self.get_bars(symbol, timeframe, limit)
        if df is None or len(df) < 30:
            return (None, -1)

        df = self.calculate_indicators(df)

        # Determine default eval bar index
        if timeframe == "4h":
            eval_idx = len(df) - 1
        else:
            eval_idx = len(df) - 2 if len(df) >= 2 else len(df) - 1

        # Calculate TOD-RVOL
        tod_result = self.get_time_of_day_rvol(df, timeframe)
        if tod_result is not None:
            tod_eval_idx, rvol_tod, tod_median_vol = tod_result
            eval_idx = tod_eval_idx
            eval_close = df.iloc[eval_idx]['close']
            df.at[df.index[eval_idx], 'rvol_tod'] = rvol_tod
            df.at[df.index[eval_idx], 'tod_avg_dollar_volume'] = eval_close * tod_median_vol
        else:
            # Fallback: use close * volume_ma20
            eval_bar = df.iloc[eval_idx]
            eval_close = eval_bar.get('close', 0)
            vol_ma = eval_bar.get('volume_ma20', 0)
            if eval_close > 0 and vol_ma > 0:
                df.at[df.index[eval_idx], 'tod_avg_dollar_volume'] = eval_close * vol_ma
            # rvol_tod stays NaN — downstream uses effective_rvol = rvol

        return (df, eval_idx)

    # ------------------------------------------------------------------
    # Historical prices wrapper (replaces Yahoo get_historical_prices)
    # ------------------------------------------------------------------

    def get_historical_prices(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "1y",
    ) -> Optional[pd.DataFrame]:
        """
        Get historical daily OHLCV data, returning a DataFrame matching
        the format that Yahoo Finance used to return.

        Columns after reset_index: date, open, high, low, close, volume
        (all lowercase, date column — matches Yahoo's reset_index output).

        Args:
            symbol: Stock ticker
            start_date: Start date string YYYY-MM-DD (optional)
            end_date: End date string YYYY-MM-DD (optional)
            period: Lookback period if no dates given (1d,5d,1mo,3mo,6mo,1y,2y,5y)

        Returns:
            DataFrame with OHLCV data or None
        """
        if not self.is_available:
            logger.warning("Alpaca service not available for historical prices")
            return None

        try:
            # Convert period string to timedelta
            period_map = {
                "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
                "1y": 365, "2y": 730, "5y": 1825, "10y": 3650,
                "ytd": (datetime.now() - datetime(datetime.now().year, 1, 1)).days,
                "max": 7300,
            }

            end_dt = datetime.now(timezone.utc)
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                days_back = period_map.get(period, 365)
                start_dt = end_dt - timedelta(days=days_back)

            request = StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=TimeFrame(1, TimeFrameUnit.Day),
                start=start_dt,
                end=end_dt,
                feed=self.data_feed,
            )

            bars = self._data_client.get_stock_bars(request)

            symbol_upper = symbol.upper()
            if hasattr(bars, "data") and symbol_upper in bars.data:
                bar_list = bars.data[symbol_upper]
            elif symbol_upper in bars:
                bar_list = bars[symbol_upper]
            else:
                logger.warning(f"No historical bars for {symbol}")
                return None

            if not bar_list:
                return None

            df = pd.DataFrame([{
                "date": bar.timestamp,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
            } for bar in bar_list])

            df = df.sort_values("date").reset_index(drop=True)
            return df

        except Exception as e:
            logger.error(f"Error fetching historical prices for {symbol}: {e}")
            return None

    # ------------------------------------------------------------------
    # Options chain methods (replaces Yahoo get_options_chain)
    # ------------------------------------------------------------------

    def get_available_expirations(self, symbol: str) -> Optional[list]:
        """
        Get available option expiration dates via Alpaca.

        Returns list of date strings YYYY-MM-DD or None.
        """
        if not self.is_available:
            return None

        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import GetOptionContractsRequest

            trading_client = TradingClient(self.api_key, self.secret_key, paper=True)
            req = GetOptionContractsRequest(
                underlying_symbols=[symbol.upper()],
                status="active",
            )
            contracts = trading_client.get_option_contracts(req)

            expirations = set()
            if contracts and hasattr(contracts, "option_contracts"):
                for c in contracts.option_contracts:
                    if hasattr(c, "expiration_date"):
                        expirations.add(str(c.expiration_date))
            elif isinstance(contracts, list):
                for c in contracts:
                    exp = c.expiration_date if hasattr(c, "expiration_date") else c.get("expiration_date")
                    if exp:
                        expirations.add(str(exp))

            result = sorted(expirations)
            return result if result else None

        except Exception as e:
            logger.error(f"Error fetching expirations for {symbol}: {e}")
            return None

    def get_options_chain(
        self,
        symbol: str,
        expiration_date: Optional[str] = None,
        include_leaps: bool = True,
    ) -> Optional[Dict[str, pd.DataFrame]]:
        """
        Get options chain data from Alpaca, returning a dict matching
        Yahoo's format: {'calls': DataFrame, 'puts': DataFrame}.

        DataFrame columns: contractSymbol, strike, lastPrice, bid, ask,
            volume, openInterest, impliedVolatility, expiration, inTheMoney

        Args:
            symbol: Underlying stock ticker
            expiration_date: Specific expiration YYYY-MM-DD (if None, fetch LEAPS)
            include_leaps: If True, only fetch expirations ≥300 days out
        """
        if not self.is_available:
            return None

        try:
            from alpaca.trading.requests import GetOptionContractsRequest

            if not self._trading_client:
                from alpaca.trading.client import TradingClient
                self._trading_client = TradingClient(
                    self.api_key, self.secret_key, paper=True
                )

            req_params = {
                "underlying_symbols": [symbol.upper()],
                "status": "active",
            }

            if expiration_date:
                req_params["expiration_date"] = expiration_date
            elif include_leaps:
                # Fetch options with 250+ days to expiry (LEAPS territory)
                leaps_start = (datetime.now() + timedelta(days=250)).strftime("%Y-%m-%d")
                req_params["expiration_date_gte"] = leaps_start

            req = GetOptionContractsRequest(**req_params)
            contracts_resp = self._trading_client.get_option_contracts(req)

            contract_list = []
            if contracts_resp and hasattr(contracts_resp, "option_contracts"):
                contract_list = contracts_resp.option_contracts or []
            elif isinstance(contracts_resp, list):
                contract_list = contracts_resp

            if not contract_list:
                logger.debug(f"No options contracts found for {symbol}")
                return None

            # Try to get market data snapshots for these contracts
            contract_symbols = [c.symbol for c in contract_list if hasattr(c, "symbol")]

            # Build calls and puts lists
            calls_data = []
            puts_data = []

            for c in contract_list:
                contract_type = getattr(c, "type", None) or getattr(c, "option_type", "")
                strike = float(getattr(c, "strike_price", 0))
                exp = str(getattr(c, "expiration_date", ""))
                sym = getattr(c, "symbol", "")

                row = {
                    "contractSymbol": sym,
                    "strike": strike,
                    "lastPrice": 0.0,
                    "bid": 0.0,
                    "ask": 0.0,
                    "volume": 0,
                    "openInterest": int(getattr(c, "open_interest", 0) or 0),
                    "impliedVolatility": 0.0,
                    "expiration": exp,
                    "inTheMoney": False,
                }

                # Alpaca SDK returns ContractType enum; use .value if available
                ct_str = (getattr(contract_type, "value", None) or str(contract_type)).lower()
                if ct_str in ("call", "c") or "call" in ct_str:
                    calls_data.append(row)
                else:
                    puts_data.append(row)

            # Try to enrich with market data snapshots (bid/ask/IV)
            if contract_symbols and self._option_client:
                try:
                    from alpaca.data.requests import OptionSnapshotRequest
                    snap_req = OptionSnapshotRequest(
                        symbol_or_symbols=contract_symbols[:100],  # limit batch size
                        feed="opra",
                    )
                    snapshots = self._option_client.get_option_snapshot(snap_req)

                    snap_map = {}
                    if isinstance(snapshots, dict):
                        snap_map = snapshots

                    for row_list in (calls_data, puts_data):
                        for row in row_list:
                            snap = snap_map.get(row["contractSymbol"])
                            if snap:
                                if hasattr(snap, "latest_quote") and snap.latest_quote:
                                    row["bid"] = float(snap.latest_quote.bid_price or 0)
                                    row["ask"] = float(snap.latest_quote.ask_price or 0)
                                if hasattr(snap, "latest_trade") and snap.latest_trade:
                                    row["lastPrice"] = float(snap.latest_trade.price or 0)
                                if hasattr(snap, "implied_volatility"):
                                    row["impliedVolatility"] = float(snap.implied_volatility or 0)
                                if hasattr(snap, "greeks") and snap.greeks:
                                    row["delta"] = float(snap.greeks.delta or 0)
                                    row["gamma"] = float(snap.greeks.gamma or 0)
                                    row["theta"] = float(snap.greeks.theta or 0)
                                    row["vega"] = float(snap.greeks.vega or 0)
                except Exception as e:
                    logger.debug(f"Could not fetch options snapshots for {symbol}: {e}")

            if not calls_data and not puts_data:
                return None

            return {
                "calls": pd.DataFrame(calls_data),
                "puts": pd.DataFrame(puts_data),
            }

        except ImportError:
            logger.warning("Alpaca trading client not available for options")
            return None
        except Exception as e:
            logger.error(f"Error fetching options chain for {symbol}: {e}")
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from Alpaca snapshot (replaces Yahoo get_current_price)."""
        snapshot = self.get_snapshot(symbol)
        if snapshot:
            return snapshot.get("current_price")
        return None

    def get_opening_range(self, symbol: str, orb_bars: int = 3) -> Optional[Dict]:
        """
        Get Opening Range (first N bars of the day).

        Args:
            symbol: Stock ticker
            orb_bars: Number of bars for ORB (default 3 = 15 minutes for 5m bars)

        Returns:
            Dict with orb_high, orb_low, orb_range
        """
        if not self.is_available:
            return None

        try:
            # Get today's 5m bars
            today = datetime.now().replace(hour=9, minute=30, second=0, microsecond=0)
            df = self.get_bars(symbol, "5m", limit=50, start=today)

            if df is None or len(df) < orb_bars:
                return None

            # First N bars
            orb_df = df.head(orb_bars)

            return {
                "symbol": symbol.upper(),
                "orb_high": float(orb_df['high'].max()),
                "orb_low": float(orb_df['low'].min()),
                "orb_range": float(orb_df['high'].max() - orb_df['low'].min()),
                "orb_bars": orb_bars,
                "orb_start": orb_df['datetime'].iloc[0].isoformat() if 'datetime' in orb_df.columns else None,
                "orb_end": orb_df['datetime'].iloc[-1].isoformat() if 'datetime' in orb_df.columns else None,
            }

        except Exception as e:
            logger.error(f"Error getting ORB for {symbol}: {e}")
            return None


# Singleton instance
alpaca_service = AlpacaService()
