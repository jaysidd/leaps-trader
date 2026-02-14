"""
Replay service classes — ReplayClock, ReplayDataService, ReplayTradingService.

These classes monkey-patch the real service singletons to serve historical data
from a pre-fetched bar cache, advancing a simulated clock bar-by-bar.
"""
import sys
import os
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple, Any
from loguru import logger
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

ET = ZoneInfo("America/New_York")


# ═══════════════════════════════════════════════════════════════════════════════
# ReplayClock — simulated time controller
# ═══════════════════════════════════════════════════════════════════════════════

class ReplayClock:
    """Controls simulated time for the replay session."""

    def __init__(self, replay_date: datetime, start_hour: int = 9, start_minute: int = 30):
        """
        Args:
            replay_date: The date to replay (date object or datetime)
            start_hour: Start hour in ET (default 9)
            start_minute: Start minute in ET (default 30)
        """
        if isinstance(replay_date, datetime):
            d = replay_date.date()
        else:
            d = replay_date

        self.replay_date = d
        self.current_time_et = datetime(
            d.year, d.month, d.day, start_hour, start_minute,
            tzinfo=ET,
        )
        self.market_open_et = datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)
        self.market_close_et = datetime(d.year, d.month, d.day, 16, 0, tzinfo=ET)

    @property
    def current_time_utc(self) -> datetime:
        return self.current_time_et.astimezone(timezone.utc)

    @property
    def is_market_open(self) -> bool:
        return self.market_open_et <= self.current_time_et <= self.market_close_et

    def now(self, tz=None) -> datetime:
        """Drop-in replacement for datetime.now(tz)."""
        if tz is None:
            return self.current_time_et.replace(tzinfo=None)
        return self.current_time_et.astimezone(tz)

    def advance(self, minutes: int):
        self.current_time_et += timedelta(minutes=minutes)

    def time_str(self) -> str:
        return self.current_time_et.strftime("%H:%M")

    def __repr__(self):
        return f"ReplayClock({self.current_time_et.isoformat()})"


# ═══════════════════════════════════════════════════════════════════════════════
# DatetimeProxy — intercepts datetime.now() in target modules
# ═══════════════════════════════════════════════════════════════════════════════

class DatetimeProxy:
    """
    Proxy that intercepts datetime.now() calls but delegates everything else
    to the real datetime class.

    Used to patch module-level `datetime` name in signal_engine.py and
    risk_gateway.py where they do `from datetime import datetime`.
    """

    def __init__(self, clock: ReplayClock, real_datetime):
        self._clock = clock
        self._real = real_datetime

    def now(self, tz=None):
        return self._clock.now(tz)

    def __call__(self, *args, **kwargs):
        """Allow datetime(2026, 1, 1) constructor calls."""
        return self._real(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __instancecheck__(cls, inst):
        return isinstance(inst, cls._real)


# ═══════════════════════════════════════════════════════════════════════════════
# ReplayDataService — patches AlpacaService with historical bar data
# ═══════════════════════════════════════════════════════════════════════════════

class ReplayDataService:
    """
    Pre-fetches historical bars and patches AlpacaService methods to serve
    them filtered by simulated clock time.
    """

    def __init__(self, clock: ReplayClock, symbols: List[str], timeframes: List[str] = None):
        self.clock = clock
        self.symbols = [s.upper() for s in symbols]
        self.timeframes = timeframes or ["5m", "1h", "1d"]
        self.bar_cache: Dict[Tuple[str, str], pd.DataFrame] = {}
        self.daily_cache: Dict[str, pd.DataFrame] = {}
        self._originals: Dict[str, Any] = {}

        # Opening range cache (computed once after bars are loaded)
        self._opening_ranges: Dict[str, Dict] = {}

    def prefetch_bars(self) -> int:
        """
        Pre-fetch all bars from Alpaca Historical API.
        Returns total bar count.
        """
        from app.services.data_fetcher.alpaca_service import alpaca_service

        total = 0
        replay_eod_utc = datetime(
            self.clock.replay_date.year, self.clock.replay_date.month,
            self.clock.replay_date.day, 21, 0, tzinfo=timezone.utc,
        )  # 4 PM ET = 9 PM UTC (EST) or 8 PM UTC (EDT)

        for symbol in self.symbols:
            for tf in self.timeframes:
                if tf == "1d":
                    lookback_days = 500  # 2 years of trading days for SMA200
                else:
                    lookback_days = 10   # ~5 trading days for TOD-RVOL

                start = replay_eod_utc - timedelta(days=lookback_days)
                bars = alpaca_service.get_bars(
                    symbol, tf,
                    limit=10000,
                    start=start,
                    end=replay_eod_utc,
                )
                if bars is not None and len(bars) > 0:
                    self.bar_cache[(symbol, tf)] = bars
                    total += len(bars)
                    logger.debug(f"Prefetched {len(bars)} {tf} bars for {symbol}")
                else:
                    logger.warning(f"No {tf} bars for {symbol}")

            # Also prefetch daily bars for screening (via get_historical_prices)
            try:
                daily = alpaca_service.get_historical_prices(
                    symbol,
                    end_date=self.clock.replay_date.isoformat(),
                    period="2y",
                )
                if daily is not None:
                    self.daily_cache[symbol] = daily
                    logger.debug(f"Prefetched {len(daily)} daily bars for {symbol}")
            except Exception as e:
                logger.warning(f"Daily bars for {symbol}: {e}")

        # Compute opening ranges from 5m bars
        self._compute_opening_ranges()

        return total

    def _compute_opening_ranges(self):
        """Compute ORB from first 3 5m bars of the replay day."""
        market_open_utc = self.clock.market_open_et.astimezone(timezone.utc)

        for symbol in self.symbols:
            bars = self.bar_cache.get((symbol, "5m"))
            if bars is None:
                continue

            # Filter to replay day only, first 3 bars (15 min)
            day_start = market_open_utc
            day_end = market_open_utc + timedelta(minutes=15)

            mask = (bars["datetime"] >= day_start) & (bars["datetime"] < day_end)
            orb_bars = bars[mask]

            if len(orb_bars) >= 1:
                self._opening_ranges[symbol] = {
                    "orb_high": float(orb_bars["high"].max()),
                    "orb_low": float(orb_bars["low"].min()),
                }

    def _get_visible_bars(self, symbol: str, timeframe: str, limit: int = 100) -> Optional[pd.DataFrame]:
        """Return bars up to the current simulated time."""
        key = (symbol.upper(), timeframe)
        all_bars = self.bar_cache.get(key)
        if all_bars is None:
            return None

        now_utc = self.clock.current_time_utc
        visible = all_bars[all_bars["datetime"] <= now_utc]
        if len(visible) == 0:
            return None

        return visible.tail(limit).copy()

    def _get_last_bar(self, symbol: str, timeframe: str = "5m") -> Optional[pd.Series]:
        """Get the last visible bar for a symbol."""
        bars = self._get_visible_bars(symbol, timeframe, limit=1)
        if bars is not None and len(bars) > 0:
            return bars.iloc[-1]
        return None

    def _make_snapshot(self, symbol: str) -> Optional[Dict]:
        """Build a synthetic snapshot from the last visible bar."""
        # Try 5m first, fall back to 1h, then 1d
        last_bar = None
        for tf in ["5m", "1h", "1d"]:
            last_bar = self._get_last_bar(symbol, tf)
            if last_bar is not None:
                break

        if last_bar is None:
            return None

        price = float(last_bar.get("close", 0))
        volume = int(last_bar.get("volume", 0))
        vwap = float(last_bar.get("vwap", price))

        # Get daily-level data from the replay day
        daily_bars = self.bar_cache.get((symbol, "1d"))
        daily_bar_data = {}
        prev_daily = {}
        if daily_bars is not None and len(daily_bars) >= 2:
            # Last daily bar on or before replay date
            replay_utc = self.clock.market_open_et.astimezone(timezone.utc)
            daily_vis = daily_bars[daily_bars["datetime"] <= replay_utc]
            if len(daily_vis) >= 2:
                d = daily_vis.iloc[-1]
                p = daily_vis.iloc[-2]
                daily_bar_data = {
                    "open": float(d.get("open", 0)),
                    "high": float(d.get("high", 0)),
                    "low": float(d.get("low", 0)),
                    "close": float(d.get("close", 0)),
                    "volume": int(d.get("volume", 0)),
                    "vwap": float(d.get("vwap", 0)),
                }
                prev_daily = {
                    "open": float(p.get("open", 0)),
                    "high": float(p.get("high", 0)),
                    "low": float(p.get("low", 0)),
                    "close": float(p.get("close", 0)),
                    "volume": int(p.get("volume", 0)),
                    "vwap": float(p.get("vwap", 0)),
                }

        prev_close = prev_daily.get("close", price)
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        return {
            "current_price": price,
            "change": round(change, 4),
            "change_percent": round(change_pct, 4),
            "volume": volume,
            "daily_bar": daily_bar_data,
            "prev_daily_bar": prev_daily,
            "latest_trade": {
                "price": price,
                "size": 100,
                "timestamp": self.clock.current_time_utc.isoformat(),
            },
            "latest_quote": {
                "bid": round(price * 0.999, 2),
                "ask": round(price * 1.001, 2),
                "bid_size": 100,
                "ask_size": 100,
                "spread": round(price * 0.002, 4),
            },
        }

    def install_patches(self):
        """Monkey-patch AlpacaService methods with replay versions."""
        from app.services.data_fetcher.alpaca_service import alpaca_service

        # Save originals for restoration
        self._originals["get_bars"] = alpaca_service.get_bars
        self._originals["get_snapshot"] = alpaca_service.get_snapshot
        self._originals["get_historical_prices"] = alpaca_service.get_historical_prices
        self._originals["get_options_chain"] = alpaca_service.get_options_chain
        self._originals["get_opening_range"] = alpaca_service.get_opening_range

        this = self  # closure reference

        def replay_get_bars(symbol, timeframe="5m", limit=100, start=None, end=None):
            return this._get_visible_bars(symbol, timeframe, limit)

        def replay_get_snapshot(symbol):
            return this._make_snapshot(symbol)

        def replay_get_historical_prices(symbol, start_date=None, end_date=None, period="1y"):
            cached = this.daily_cache.get(symbol.upper())
            if cached is not None:
                return cached.copy()
            # Fallback to original (capped to replay date)
            return this._originals["get_historical_prices"](
                symbol, start_date,
                end_date=this.clock.replay_date.isoformat(),
                period=period,
            )

        def replay_get_options_chain(symbol, *args, **kwargs):
            """
            Return a synthetic options chain with a single LEAPS call.

            This triggers the screening engine's soft-pass path:
            - has_options_data=True, leaps_available=True
            - atm_option has no market data (IV=0, OI=0)
            - All 4 options criteria become UNKNOWN → known_count=0
            - Soft-pass: "LEAPS available, no market data"
            """
            import pandas as pd
            from datetime import timedelta

            # Get current price from snapshot to set ATM strike
            snap = this._make_snapshot(symbol)
            if snap is None:
                return None
            price = snap.get("current_price", 100)
            strike = round(price, 0)

            # LEAPS expiration: 300 days out (> 250 min_dte threshold)
            expiry = this.clock.replay_date + timedelta(days=300)

            calls_df = pd.DataFrame([{
                "symbol": f"{symbol}260101C{int(strike * 1000):08d}",
                "expiration": expiry.isoformat(),
                "strike": strike,
                "option_type": "call",
                # Market data intentionally absent/zero → UNKNOWN criteria
                "implied_volatility": 0.0,  # Treated as UNKNOWN (not populated)
                "open_interest": 0,          # Treated as UNKNOWN
                "bid": 0.0,
                "ask": 0.0,
                "last_price": 0.0,
                "volume": 0,
            }])

            return {"calls": calls_df, "puts": pd.DataFrame()}

        def replay_get_opening_range(symbol, orb_bars=3):
            return this._opening_ranges.get(symbol.upper())

        alpaca_service.get_bars = replay_get_bars
        alpaca_service.get_snapshot = replay_get_snapshot
        alpaca_service.get_historical_prices = replay_get_historical_prices
        alpaca_service.get_options_chain = replay_get_options_chain
        alpaca_service.get_opening_range = replay_get_opening_range

    def uninstall_patches(self):
        """Restore original AlpacaService methods."""
        from app.services.data_fetcher.alpaca_service import alpaca_service
        for name, original in self._originals.items():
            setattr(alpaca_service, name, original)
        self._originals.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# ReplayTradingService — virtual account + simulated fills
# ═══════════════════════════════════════════════════════════════════════════════

class ReplayTradingService:
    """
    Simulates order execution and account tracking for replay.
    Patches AlpacaTradingService methods.
    """

    def __init__(self, clock: ReplayClock, initial_equity: float = 100_000):
        self.clock = clock
        self.initial_equity = initial_equity
        self.cash = initial_equity
        self.positions: Dict[str, Dict] = {}   # symbol → {qty, avg_price, side, market_value}
        self.pending_orders: List[Dict] = []    # orders waiting for fill
        self.fills: List[Dict] = []             # completed fills
        self.all_orders: List[Dict] = []        # all orders (for get_orders)
        self._originals: Dict[str, Any] = {}

    @property
    def equity(self) -> float:
        """Total equity = cash + sum of position market values."""
        pos_value = sum(p.get("market_value", 0) for p in self.positions.values())
        return self.cash + pos_value

    def get_account(self) -> Dict:
        """Simulated account info."""
        eq = self.equity
        return {
            "id": "replay-account",
            "status": "ACTIVE",
            "currency": "USD",
            "cash": round(self.cash, 2),
            "buying_power": round(self.cash * 2, 2),  # 2x margin
            "equity": round(eq, 2),
            "portfolio_value": round(eq, 2),
            "long_market_value": round(sum(
                p["market_value"] for p in self.positions.values()
                if p["side"] == "long"
            ), 2),
            "short_market_value": 0,
            "daytrade_count": len(self.fills),
            "pattern_day_trader": False,
            "trading_blocked": False,
            "transfers_blocked": False,
            "account_blocked": False,
            "paper_mode": True,
            "last_equity": round(self.initial_equity, 2),
        }

    def get_clock(self) -> Dict:
        """Simulated market clock."""
        return {
            "is_open": self.clock.is_market_open,
            "next_open": self.clock.market_open_et.isoformat(),
            "next_close": self.clock.market_close_et.isoformat(),
            "timestamp": self.clock.current_time_et.isoformat(),
        }

    def get_all_positions(self) -> List[Dict]:
        """Return all open positions."""
        result = []
        for sym, pos in self.positions.items():
            result.append({
                "symbol": sym,
                "qty": str(pos["qty"]),
                "side": pos["side"],
                "avg_entry_price": str(pos["avg_price"]),
                "current_price": str(pos.get("current_price", pos["avg_price"])),
                "market_value": str(pos.get("market_value", 0)),
                "unrealized_pl": str(round(pos.get("unrealized_pl", 0), 2)),
                "unrealized_plpc": str(round(pos.get("unrealized_plpc", 0), 4)),
                "cost_basis": str(round(pos["qty"] * pos["avg_price"], 2)),
            })
        return result

    def get_open_position(self, symbol: str) -> Optional[Dict]:
        """Get position for a specific symbol."""
        pos = self.positions.get(symbol.upper())
        if pos:
            return {
                "symbol": symbol.upper(),
                "qty": str(pos["qty"]),
                "side": pos["side"],
                "avg_entry_price": str(pos["avg_price"]),
                "current_price": str(pos.get("current_price", pos["avg_price"])),
                "market_value": str(pos.get("market_value", 0)),
                "unrealized_pl": str(round(pos.get("unrealized_pl", 0), 2)),
                "unrealized_plpc": str(round(pos.get("unrealized_plpc", 0), 4)),
            }
        return None

    def get_orders(self, status="all", limit=50, symbols=None) -> List[Dict]:
        """Return order history."""
        orders = self.all_orders[-limit:]
        if status != "all":
            orders = [o for o in orders if o.get("status") == status]
        return orders

    def place_market_order(self, symbol: str, qty: float, side: str) -> Optional[Dict]:
        """Queue a market order — fills at next bar's open."""
        order_id = str(uuid.uuid4())[:8]
        order = {
            "id": order_id,
            "symbol": symbol.upper(),
            "qty": qty,
            "side": side,
            "type": "market",
            "status": "pending_fill",
            "submitted_at": self.clock.current_time_et.isoformat(),
            "time_in_force": "day",
        }
        self.pending_orders.append(order)
        self.all_orders.append(order)
        return order

    def place_limit_order(self, symbol: str, qty: float, side: str,
                          limit_price: float) -> Optional[Dict]:
        """Queue a limit order — fills when price crosses."""
        order_id = str(uuid.uuid4())[:8]
        order = {
            "id": order_id,
            "symbol": symbol.upper(),
            "qty": qty,
            "side": side,
            "type": "limit",
            "limit_price": limit_price,
            "status": "pending_fill",
            "submitted_at": self.clock.current_time_et.isoformat(),
            "time_in_force": "day",
        }
        self.pending_orders.append(order)
        self.all_orders.append(order)
        return order

    def tick(self, data_service: "ReplayDataService") -> List[Dict]:
        """
        Process pending orders against current bars.
        Called each time the clock advances.
        Returns list of fills that occurred.
        """
        new_fills = []
        still_pending = []

        for order in self.pending_orders:
            symbol = order["symbol"]
            bar = data_service._get_last_bar(symbol, "5m")
            if bar is None:
                still_pending.append(order)
                continue

            fill_price = None

            if order["type"] == "market":
                # Market orders fill at the bar's open
                fill_price = float(bar.get("open", bar.get("close", 0)))
            elif order["type"] == "limit":
                limit = order["limit_price"]
                if order["side"] == "buy" and float(bar.get("low", 999999)) <= limit:
                    fill_price = limit
                elif order["side"] == "sell" and float(bar.get("high", 0)) >= limit:
                    fill_price = limit

            if fill_price and fill_price > 0:
                fill = self._execute_fill(order, fill_price)
                new_fills.append(fill)
            else:
                still_pending.append(order)

        self.pending_orders = still_pending
        return new_fills

    def _execute_fill(self, order: Dict, fill_price: float) -> Dict:
        """Execute a fill and update positions/cash."""
        symbol = order["symbol"]
        qty = order["qty"]
        side = order["side"]
        notional = qty * fill_price

        if side == "buy":
            self.cash -= notional
            if symbol in self.positions:
                pos = self.positions[symbol]
                total_qty = pos["qty"] + qty
                pos["avg_price"] = (pos["avg_price"] * pos["qty"] + fill_price * qty) / total_qty
                pos["qty"] = total_qty
            else:
                self.positions[symbol] = {
                    "qty": qty,
                    "avg_price": fill_price,
                    "side": "long",
                    "current_price": fill_price,
                    "market_value": notional,
                    "unrealized_pl": 0,
                    "unrealized_plpc": 0,
                }
        elif side == "sell":
            self.cash += notional
            if symbol in self.positions:
                pos = self.positions[symbol]
                realized_pl = (fill_price - pos["avg_price"]) * qty
                pos["qty"] -= qty
                if pos["qty"] <= 0.001:  # effectively zero
                    del self.positions[symbol]

        # Update order status
        order["status"] = "filled"
        order["filled_at"] = self.clock.current_time_et.isoformat()
        order["filled_avg_price"] = str(fill_price)
        order["filled_qty"] = str(qty)

        fill = {
            "order_id": order["id"],
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": fill_price,
            "notional": round(notional, 2),
            "time": self.clock.time_str(),
            "realized_pl": round(
                (fill_price - self.positions.get(symbol, {}).get("avg_price", fill_price)) * qty
                if side == "sell" else 0, 2
            ),
        }
        self.fills.append(fill)
        return fill

    def update_positions(self, data_service: "ReplayDataService"):
        """Mark all positions to market using current bar data."""
        for symbol, pos in self.positions.items():
            bar = data_service._get_last_bar(symbol, "5m")
            if bar is None:
                continue
            current_price = float(bar.get("close", pos["avg_price"]))
            pos["current_price"] = current_price
            pos["market_value"] = round(pos["qty"] * current_price, 2)
            pos["unrealized_pl"] = round((current_price - pos["avg_price"]) * pos["qty"], 2)
            if pos["avg_price"] > 0:
                pos["unrealized_plpc"] = round(
                    (current_price - pos["avg_price"]) / pos["avg_price"], 4
                )

    def close_all_positions(self, data_service: "ReplayDataService") -> List[Dict]:
        """Close all open positions at current price (EOD)."""
        closes = []
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            bar = data_service._get_last_bar(symbol, "5m")
            close_price = float(bar.get("close", pos["current_price"])) if bar is not None else pos["current_price"]

            order = {
                "id": str(uuid.uuid4())[:8],
                "symbol": symbol,
                "qty": pos["qty"],
                "side": "sell",
                "type": "market",
                "status": "pending_fill",
            }
            fill = self._execute_fill(order, close_price)
            fill["reason"] = "EOD_CLOSE"
            closes.append(fill)
            self.all_orders.append(order)

        return closes

    def install_patches(self):
        """Patch AlpacaTradingService methods."""
        from app.services.trading.alpaca_trading_service import alpaca_trading_service

        self._originals["get_account"] = alpaca_trading_service.get_account
        self._originals["get_clock"] = alpaca_trading_service.get_clock
        self._originals["get_all_positions"] = alpaca_trading_service.get_all_positions
        self._originals["get_position"] = alpaca_trading_service.get_position
        self._originals["get_orders"] = alpaca_trading_service.get_orders
        self._originals["place_market_order"] = alpaca_trading_service.place_market_order
        self._originals["place_limit_order"] = alpaca_trading_service.place_limit_order

        alpaca_trading_service.get_account = self.get_account
        alpaca_trading_service.get_clock = self.get_clock
        alpaca_trading_service.get_all_positions = self.get_all_positions
        alpaca_trading_service.get_position = self.get_open_position
        alpaca_trading_service.get_orders = self.get_orders
        alpaca_trading_service.place_market_order = self.place_market_order
        alpaca_trading_service.place_limit_order = self.place_limit_order

    def uninstall_patches(self):
        """Restore original AlpacaTradingService methods."""
        from app.services.trading.alpaca_trading_service import alpaca_trading_service
        for name, original in self._originals.items():
            setattr(alpaca_trading_service, name, original)
        self._originals.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# ReplayMarketIntelligence — patches market intelligence services for replay
# ═══════════════════════════════════════════════════════════════════════════════

class ReplayMarketIntelligence:
    """
    Patches the four market intelligence sources used by PresetSelector
    to serve historical data from the replay date.

    Data sources:
    1. MRI (Macro Risk Index) — from DB snapshots (mri_snapshots table)
    2. Market Regime — computed from VIX/SPY historical data (via patched Alpaca)
    3. Fear & Greed — VIX-based fallback (historical VIX from patched Alpaca)
    4. Trade Readiness — computed from available historical components

    The key insight: since ReplayDataService already patches alpaca_service
    to serve historical data, any service that calls alpaca_service.get_historical_prices()
    or alpaca_service.get_snapshot() will automatically get replay-date data.

    We just need to:
    - Pre-load MRI from DB if available for the replay date
    - Inject it into the MacroSignalService cache
    - Ensure the MarketRegimeDetector re-computes from historical VIX/SPY
    - Let Fear & Greed fall through to VIX-based fallback
    - Let CatalystService compute from the (already-patched) data sources
    """

    def __init__(self, clock: ReplayClock, db_session=None):
        self.clock = clock
        self.db = db_session
        self._originals: Dict[str, Any] = {}
        self._injected_mri: Optional[Dict] = None
        self._injected_regime: Optional[Dict] = None
        self._injected_fg: Optional[Dict] = None
        self._injected_readiness: Optional[Dict] = None

    # ── Computation helpers (derive market intel from bar data) ──────────

    def _compute_regime_from_bars(self, data_svc: "ReplayDataService") -> Optional[Dict]:
        """
        Compute market regime from SPY daily bars — same logic as
        MarketRegimeDetector.analyze_regime_rules() but using prefetched data.
        """
        spy_daily = data_svc.daily_cache.get("SPY")
        if spy_daily is None or len(spy_daily) < 20:
            return None

        # Get SPY close prices — handle both 'Close' and 'close' column names
        close_col = "Close" if "Close" in spy_daily.columns else "close"
        spy_close = spy_daily[close_col]
        spy_price = float(spy_close.iloc[-1])

        # RSI calculation (14-period)
        delta = spy_close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta.clip(upper=0))
        avg_gain = gain.rolling(14, min_periods=14).mean()
        avg_loss = loss.rolling(14, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, float('nan'))
        rsi = 100 - (100 / (1 + rs))
        spy_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

        # SPY vs 200 SMA
        spy_above_200 = True
        spy_vs_200 = "N/A"
        if len(spy_close) >= 200:
            sma_200 = float(spy_close.tail(200).mean())
            pct_diff = ((spy_price - sma_200) / sma_200) * 100
            spy_above_200 = spy_price > sma_200
            spy_vs_200 = f"{pct_diff:+.1f}%"

        # VIX proxy: use SPY's recent volatility as a VIX estimate
        # Historical volatility of last 20 days, annualized
        returns = spy_close.pct_change().dropna()
        if len(returns) >= 20:
            recent_vol = float(returns.tail(20).std() * (252 ** 0.5) * 100)
        else:
            recent_vol = 20.0  # default

        vix = recent_vol  # Proxy: realized vol ≈ VIX
        vix_sma = vix  # Simplified

        # 5-day VIX trend proxy
        if len(returns) >= 25:
            vol_5d_ago = float(returns.iloc[-25:-5].tail(20).std() * (252 ** 0.5) * 100)
            if vix < vol_5d_ago * 0.95:
                vix_trend = "falling"
            elif vix > vol_5d_ago * 1.05:
                vix_trend = "rising"
            else:
                vix_trend = "stable"
        else:
            vix_trend = "unknown"

        # Apply same rules as MarketRegimeDetector.analyze_regime_rules()
        regime = "neutral"
        risk_mode = "mixed"
        confidence = 5

        if vix < 15 and spy_rsi > 50 and spy_above_200 and vix_trend in ["falling", "stable"]:
            regime, risk_mode, confidence = "bullish", "risk_on", 8
        elif vix < 20 and spy_rsi > 45 and spy_above_200:
            regime, risk_mode, confidence = "bullish", "risk_on", 7
        elif vix > 30 and spy_rsi < 40 and not spy_above_200 and vix_trend == "rising":
            regime, risk_mode, confidence = "bearish", "risk_off", 8
        elif vix > 25 or (spy_rsi < 35 and not spy_above_200):
            regime, risk_mode, confidence = "bearish", "risk_off", 6
        elif vix > 20 and vix > vix_sma:
            regime, risk_mode, confidence = "neutral", "mixed", 5
        elif spy_above_200:
            regime, risk_mode, confidence = "bullish", "mixed", 5

        return {
            "regime": regime,
            "risk_mode": risk_mode,
            "confidence": confidence,
            "vix_proxy": round(vix, 1),
            "spy_rsi": round(spy_rsi, 1),
            "spy_price": round(spy_price, 2),
            "spy_above_200sma": spy_above_200,
            "spy_vs_200sma": spy_vs_200,
            "vix_trend": vix_trend,
        }

    def _compute_fear_greed_from_bars(self, data_svc: "ReplayDataService") -> Optional[Dict]:
        """
        Compute Fear & Greed proxy from SPY data.
        Same logic as MarketDataService._get_fear_greed_fallback().
        """
        spy_daily = data_svc.daily_cache.get("SPY")
        if spy_daily is None or len(spy_daily) < 20:
            return None

        close_col = "Close" if "Close" in spy_daily.columns else "close"
        spy_close = spy_daily[close_col]

        # VIX proxy from realized volatility
        returns = spy_close.pct_change().dropna()
        if len(returns) >= 20:
            vix_proxy = float(returns.tail(20).std() * (252 ** 0.5) * 100)
        else:
            vix_proxy = 20.0

        # VIX to F&G score (same formula as MarketDataService._get_fear_greed_fallback)
        score = max(0, min(100, 100 - ((vix_proxy - 10) * 3)))

        # Adjust by recent SPY performance
        if len(spy_close) >= 2:
            spy_change_pct = ((float(spy_close.iloc[-1]) - float(spy_close.iloc[-2]))
                              / float(spy_close.iloc[-2])) * 100
            score = score + (spy_change_pct * 2)

        score = max(0, min(100, score))
        score = round(score)

        if score <= 25:
            rating = "Extreme Fear"
        elif score <= 45:
            rating = "Fear"
        elif score <= 55:
            rating = "Neutral"
        elif score <= 75:
            rating = "Greed"
        else:
            rating = "Extreme Greed"

        return {
            "value": score,
            "rating": rating,
            "color": "#eab308",
            "previous_close": score,
            "one_week_ago": score,
            "one_month_ago": score,
            "one_year_ago": score,
            "updated_at": self.clock.current_time_et.isoformat(),
            "is_fallback": True,
            "is_replay": True,
            "indicators": None,
        }

    def _compute_readiness_proxy(self) -> Optional[Dict]:
        """
        Compute Trade Readiness proxy from MRI + regime.
        The full CatalystService needs FRED/Polymarket APIs we can't replay.
        We approximate using: MRI (40%) + regime-derived proxy (60%).
        """
        mri_score = None
        if self._injected_mri:
            mri_score = self._injected_mri.get("mri_score")

        regime_data = self._injected_regime
        if regime_data is None and mri_score is None:
            return None

        # Start with MRI as base (40% weight) — MRI 0-100 (higher = riskier)
        if mri_score is not None:
            base_score = mri_score * 0.4
        else:
            base_score = 50 * 0.4  # Neutral default

        # Add regime-derived proxy (60% weight)
        if regime_data:
            regime = regime_data.get("regime", "neutral")
            vix_proxy = regime_data.get("vix_proxy", 20)
            regime_map = {"bullish": 25, "neutral": 50, "bearish": 75}
            regime_score = regime_map.get(regime, 50)

            # Blend regime classification with VIX proxy
            # VIX < 15 → 20 (risk-on), VIX > 30 → 80 (risk-off)
            vix_readiness = max(0, min(100, (vix_proxy - 10) * 3))
            proxy_score = (regime_score * 0.5 + vix_readiness * 0.5) * 0.6
        else:
            proxy_score = 50 * 0.6

        total_score = base_score + proxy_score
        total_score = max(0, min(100, total_score))

        if total_score <= 33:
            label = "green"
        elif total_score >= 67:
            label = "red"
        else:
            label = "yellow"

        return {
            "trade_readiness_score": round(total_score, 1),
            "readiness_label": label,
            "is_proxy": True,
        }

    def load_historical_intelligence(self, data_svc: "ReplayDataService" = None) -> Dict[str, Any]:
        """
        Load historical market intelligence for the replay date.

        Args:
            data_svc: ReplayDataService with prefetched bar cache (for computing
                      regime, F&G, and readiness from historical SPY data)

        Returns dict with what was found/computed for logging.
        """
        results = {
            "mri": None,
            "regime": None,
            "fear_greed": None,
            "readiness": None,
        }

        # 1. Load MRI from database (closest snapshot to market open on replay date)
        if self.db:
            try:
                from app.models.mri_snapshot import MRISnapshot
                from datetime import timedelta as td

                replay_start = self.clock.market_open_et
                replay_end = self.clock.market_close_et

                # Find MRI snapshot closest to market open on replay date
                snapshot = (
                    self.db.query(MRISnapshot)
                    .filter(
                        MRISnapshot.calculated_at >= replay_start - td(hours=12),
                        MRISnapshot.calculated_at <= replay_end + td(hours=4),
                    )
                    .order_by(MRISnapshot.calculated_at.desc())
                    .first()
                )

                if snapshot:
                    self._injected_mri = {
                        "mri_score": snapshot.mri_score,
                        "regime": snapshot.regime,
                        "confidence_score": snapshot.confidence_score,
                        "shock_flag": snapshot.shock_flag,
                        "drivers": snapshot.drivers,
                        "components": {
                            "fed_policy": snapshot.fed_policy_score,
                            "recession": snapshot.recession_score,
                            "elections": snapshot.elections_score,
                            "trade": snapshot.trade_score,
                            "crypto": snapshot.crypto_score,
                        },
                        "markets_included": snapshot.markets_included,
                        "total_liquidity": snapshot.total_liquidity,
                        "change_1h": snapshot.change_1h,
                        "change_24h": snapshot.change_24h,
                        "data_stale": False,
                        "calculated_at": snapshot.calculated_at.isoformat() if snapshot.calculated_at else None,
                        "source": "db_snapshot",
                    }
                    results["mri"] = {
                        "score": snapshot.mri_score,
                        "regime": snapshot.regime,
                        "source": "db_snapshot",
                        "calculated_at": str(snapshot.calculated_at),
                    }
                    logger.info(
                        f"[ReplayIntel] MRI from DB: score={snapshot.mri_score}, "
                        f"regime={snapshot.regime} (at {snapshot.calculated_at})"
                    )
                else:
                    logger.warning(f"[ReplayIntel] No MRI snapshot found for {self.clock.replay_date}")
                    results["mri"] = {"score": None, "source": "not_found"}
            except Exception as e:
                logger.error(f"[ReplayIntel] MRI load error: {e}")
                results["mri"] = {"error": str(e)}

        # 2. Market Regime — compute from SPY daily bars in the data_svc bar cache.
        #    ^VIX is NOT a valid Alpaca symbol, so the regime detector's
        #    get_market_data() fails. We compute VIX proxy and SPY indicators
        #    directly from prefetched data and inject into the regime cache.
        try:
            from app.services.ai.market_regime import get_regime_detector

            detector = get_regime_detector()
            detector.clear_cache()

            # Compute regime from prefetched SPY daily data
            regime_result = self._compute_regime_from_bars(data_svc) if data_svc else None
            if regime_result:
                self._injected_regime = regime_result
                results["regime"] = {
                    "regime": regime_result["regime"],
                    "risk_mode": regime_result["risk_mode"],
                    "confidence": regime_result["confidence"],
                    "spy_rsi": regime_result.get("spy_rsi"),
                    "source": "computed_from_historical_spy",
                }
                logger.info(
                    f"[ReplayIntel] Regime from SPY bars: {regime_result['regime']} "
                    f"(confidence={regime_result['confidence']})"
                )
            else:
                results["regime"] = {"source": "computation_failed"}
                logger.warning("[ReplayIntel] Could not compute regime from historical data")
        except Exception as e:
            logger.error(f"[ReplayIntel] Regime setup error: {e}")

        # 3. Fear & Greed — CNN API won't have historical data for past dates,
        #    and the VIX fallback breaks because ^VIX isn't a valid Alpaca symbol.
        #    Compute directly from SPY daily bars as a proxy.
        try:
            fg_result = self._compute_fear_greed_from_bars(data_svc) if data_svc else None
            if fg_result:
                self._injected_fg = fg_result
                results["fear_greed"] = {
                    "value": fg_result["value"],
                    "rating": fg_result["rating"],
                    "source": "computed_from_historical_spy",
                }
                logger.info(
                    f"[ReplayIntel] F&G from SPY bars: {fg_result['value']} ({fg_result['rating']})"
                )
            else:
                results["fear_greed"] = {"source": "computation_failed"}
        except Exception as e:
            logger.error(f"[ReplayIntel] F&G computation error: {e}")

        # 4. Trade Readiness — compute a simplified version from available data.
        #    Full CatalystService depends on FRED/Polymarket APIs we can't replay.
        #    Use MRI (40%) + a regime-derived proxy for the other 60%.
        try:
            readiness_result = self._compute_readiness_proxy()
            if readiness_result:
                self._injected_readiness = readiness_result
                results["readiness"] = {
                    "score": readiness_result["trade_readiness_score"],
                    "label": readiness_result["readiness_label"],
                    "source": "proxy_from_mri_and_regime",
                }
                logger.info(
                    f"[ReplayIntel] Readiness proxy: {readiness_result['trade_readiness_score']:.0f} "
                    f"({readiness_result['readiness_label']})"
                )
            else:
                results["readiness"] = {"source": "computation_failed"}
        except Exception as e:
            logger.error(f"[ReplayIntel] Readiness computation error: {e}")

        return results

    def install_patches(self):
        """
        Patch market intelligence services to serve historical data.

        Strategy:
        - Inject cached MRI into MacroSignalService
        - Inject computed regime into MarketRegimeDetector cache
        - Return pre-computed F&G directly (skip CNN API + broken VIX fallback)
        - Return pre-computed readiness directly (skip FRED/Polymarket)
        """
        # Patch 1: MRI — inject cached value into MacroSignalService
        if self._injected_mri:
            try:
                from app.services.command_center import get_macro_signal_service
                mri_svc = get_macro_signal_service()
                self._originals["mri_cached"] = mri_svc._cached_mri
                mri_svc._cached_mri = self._injected_mri
                logger.info(f"[ReplayIntel] Patched MRI cache: score={self._injected_mri['mri_score']}")
            except Exception as e:
                logger.error(f"[ReplayIntel] MRI patch error: {e}")

        # Patch 2: Market Regime — inject computed result into detector cache
        #
        # PresetSelector reads from detector._cache like this:
        #   detector._cache.get("regime")  → reads top-level key "regime"
        #   detector._cache.get("risk_mode")
        #   detector._cache.get("confidence")
        # So we inject the regime data as TOP-LEVEL keys in the cache dict.
        if self._injected_regime:
            try:
                from app.services.ai.market_regime import get_regime_detector
                detector = get_regime_detector()
                self._originals["regime_cache"] = dict(detector._cache) if detector._cache else {}
                self._originals["regime_cache_time"] = detector._cache_time

                # Inject as top-level keys (matching what PresetSelector expects)
                detector._cache = self._injected_regime.copy()
                detector._cache_time = datetime.now()  # Mark as fresh
                logger.info(f"[ReplayIntel] Patched regime cache: {self._injected_regime['regime']}")
            except Exception as e:
                logger.error(f"[ReplayIntel] Regime patch error: {e}")

        # Patch 3: Fear & Greed — return pre-computed value (skip CNN + VIX fallback)
        if self._injected_fg:
            try:
                from app.services.command_center import get_market_data_service
                mds = get_market_data_service()
                self._originals["get_fear_greed_index"] = mds.get_fear_greed_index

                injected = self._injected_fg

                async def replay_fear_greed():
                    return injected

                mds.get_fear_greed_index = replay_fear_greed
                logger.info(f"[ReplayIntel] Patched F&G: value={injected['value']}")
            except Exception as e:
                logger.error(f"[ReplayIntel] F&G patch error: {e}")

        # Patch 4: Trade Readiness — return pre-computed value (skip FRED/Polymarket)
        if self._injected_readiness:
            try:
                from app.services.command_center import get_catalyst_service
                catalyst = get_catalyst_service()
                self._originals["calculate_trade_readiness"] = catalyst.calculate_trade_readiness

                injected_readiness = self._injected_readiness

                async def replay_readiness(db=None):
                    return injected_readiness

                catalyst.calculate_trade_readiness = replay_readiness
                logger.info(
                    f"[ReplayIntel] Patched readiness: "
                    f"score={injected_readiness['trade_readiness_score']}"
                )
            except Exception as e:
                logger.error(f"[ReplayIntel] Readiness patch error: {e}")

    def uninstall_patches(self):
        """Restore original market intelligence services."""
        # Restore MRI
        if "mri_cached" in self._originals:
            try:
                from app.services.command_center import get_macro_signal_service
                get_macro_signal_service()._cached_mri = self._originals["mri_cached"]
            except Exception:
                pass

        # Restore readiness
        if "calculate_trade_readiness" in self._originals:
            try:
                from app.services.command_center import get_catalyst_service
                get_catalyst_service().calculate_trade_readiness = self._originals["calculate_trade_readiness"]
            except Exception:
                pass

        # Restore F&G
        if "get_fear_greed_index" in self._originals:
            try:
                from app.services.command_center import get_market_data_service
                get_market_data_service().get_fear_greed_index = self._originals["get_fear_greed_index"]
            except Exception:
                pass

        # Restore regime cache
        if "regime_cache" in self._originals:
            try:
                from app.services.ai.market_regime import get_regime_detector
                detector = get_regime_detector()
                detector._cache = self._originals["regime_cache"]
                detector._cache_time = self._originals.get("regime_cache_time")
            except Exception:
                pass

        self._originals.clear()

    async def run_preset_selector(self, db_session) -> Dict[str, Any]:
        """
        Run the PresetSelector with historical market data and return full results.

        Returns dict with:
            condition, presets, max_positions, reasoning, market_snapshot,
            composite_score, signal_scores
        """
        from app.services.automation.preset_selector import get_preset_selector

        selector = get_preset_selector()
        result = await selector.select_presets(db_session)

        # Also extract the detailed signal scores for auditing
        snapshot = result.get("market_snapshot", {})
        composite = snapshot.get("composite_score", 0)

        return {
            "condition": result["condition"],
            "presets": result["presets"],
            "max_positions": result["max_positions"],
            "reasoning": result["reasoning"],
            "market_snapshot": snapshot,
            "composite_score": composite,
        }
