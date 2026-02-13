"""
Backtrader Strategy Classes — translated from signal_engine.py

Each strategy mirrors the live signal_engine logic:
- Same entry/exit conditions
- Same ATR-based stop losses and targets
- Same confidence scoring (used as minimum threshold gate)
- Parameters imported from SignalEngine.PARAMS to stay in sync
"""
import backtrader as bt
import numpy as np
from loguru import logger


# =============================================================================
# Base Strategy — shared indicators, sizing, trade logging
# =============================================================================

class LEAPSStrategy(bt.Strategy):
    """
    Base class for all LEAPS Trader backtesting strategies.

    Provides:
    - Common indicators (EMA8, EMA21, RSI14, ATR14, volume SMA20)
    - Position sizing (% of portfolio)
    - Trade logging for results extraction
    - Equity curve recording
    """

    params = dict(
        position_size_pct=10.0,   # % of portfolio per trade
        stop_atr_mult=0.5,
        rsi_long_min=50,
        rsi_short_max=50,
        min_atr_percent=0.15,
        max_atr_percent=2.0,
        min_rvol=0.8,
        volume_spike_mult=1.2,
        min_confidence=60,
    )

    def __init__(self):
        # ── Indicators ────────────────────────────────────────────────
        self.ema8 = bt.indicators.ExponentialMovingAverage(self.data.close, period=8)
        self.ema21 = bt.indicators.ExponentialMovingAverage(self.data.close, period=21)
        self.rsi = bt.indicators.RelativeStrengthIndex(self.data.close, period=14)
        self.atr = bt.indicators.AverageTrueRange(self.data, period=14)
        self.vol_sma = bt.indicators.SimpleMovingAverage(self.data.volume, period=20)

        # ── Trade tracking ────────────────────────────────────────────
        self.trade_log = []
        self.equity_curve = []
        self._pending_entry = None    # Track entry info for trade log
        self._entry_bar = 0
        self.order = None             # Pending order reference

    def next(self):
        """Record equity curve every bar."""
        dt = self.data.datetime.datetime(0)
        self.equity_curve.append({
            "date": dt.strftime("%Y-%m-%d %H:%M"),
            "value": round(self.broker.getvalue(), 2),
        })

    def notify_order(self, order):
        """Track order completion."""
        if order.status in [order.Completed]:
            if order.isbuy() or order.issell():
                direction = "buy" if order.isbuy() else "sell"
                # If no pending entry, this is an entry order
                if self._pending_entry is None:
                    self._pending_entry = {
                        "entry_date": self.data.datetime.datetime(0).strftime("%Y-%m-%d %H:%M"),
                        "direction": direction,
                        "entry_price": order.executed.price,
                        "size": abs(order.executed.size),
                    }
                    self._entry_bar = len(self)
                # Otherwise it's an exit order — notify_trade will handle it
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            pass  # Order failed, nothing to track
        self.order = None

    def notify_trade(self, trade):
        """Log completed (closed) trades."""
        if trade.isclosed and self._pending_entry:
            entry = self._pending_entry
            exit_price = self.data.close[0]
            pnl = trade.pnl
            pnl_pct = (pnl / (entry["entry_price"] * entry["size"])) * 100 if entry["entry_price"] else 0
            bars_held = len(self) - self._entry_bar

            self.trade_log.append({
                "entry_date": entry["entry_date"],
                "exit_date": self.data.datetime.datetime(0).strftime("%Y-%m-%d %H:%M"),
                "direction": entry["direction"],
                "entry_price": round(entry["entry_price"], 2),
                "exit_price": round(exit_price, 2),
                "size": entry["size"],
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "bars_held": bars_held,
            })
            self._pending_entry = None

    def calc_size(self):
        """Calculate position size as % of portfolio value."""
        value = self.broker.getvalue()
        risk_amount = value * (self.p.position_size_pct / 100.0)
        price = self.data.close[0]
        if price <= 0:
            return 0
        size = int(risk_amount / price)
        return max(size, 1)  # At least 1 share

    def calc_confidence(self, direction):
        """
        Simplified confidence scoring matching signal_engine._calculate_confidence.
        Returns 0-100 score.
        """
        score = 50.0  # Base

        ema8 = self.ema8[0]
        ema21 = self.ema21[0]
        rsi = self.rsi[0]
        close = self.data.close[0]
        volume = self.data.volume[0]
        vol_ma = self.vol_sma[0]

        # Trend alignment (0 to +20)
        if direction == "long":
            if ema8 > ema21:
                score += 15
            if close > ema21:
                score += 5
        else:
            if ema8 < ema21:
                score += 15
            if close < ema21:
                score += 5

        # Momentum (0 to +15)
        if direction == "long" and rsi > 55:
            score += 10
        elif direction == "short" and rsi < 45:
            score += 10
        if direction == "long" and rsi > 60:
            score += 5
        elif direction == "short" and rsi < 40:
            score += 5

        # Volume confirmation (0 to +20)
        if vol_ma > 0:
            rvol = volume / vol_ma
            if volume > vol_ma * 1.2:  # Volume spike
                score += 10
            if rvol >= 1.5:
                score += 10
            elif rvol >= 1.2:
                score += 5

        return min(score, 100)

    def atr_percent(self):
        """ATR as percentage of price."""
        if self.data.close[0] > 0 and self.atr[0] > 0:
            return (self.atr[0] / self.data.close[0]) * 100
        return 0

    def rvol(self):
        """Relative volume."""
        if self.vol_sma[0] > 0:
            return self.data.volume[0] / self.vol_sma[0]
        return 1.0

    def volume_spike(self):
        """Check if current volume is a spike."""
        return self.data.volume[0] > (self.vol_sma[0] * self.p.volume_spike_mult)


# =============================================================================
# ORB Breakout Strategy
# =============================================================================

class ORBBreakoutStrategy(LEAPSStrategy):
    """
    Opening Range Breakout — mirrors signal_engine._check_orb_breakout.

    Entry:
    - After skip_bars, capture ORB high/low from those bars
    - Buy when close crosses above ORB high + trend/momentum/volume filters
    - Sell when close crosses below ORB low + filters

    Exit:
    - Stop loss: ATR-based below entry
    - Take profit: 2R target
    """

    # Include base params + ORB-specific params
    # (Backtrader dict-style params in subclasses REPLACE parent, so we must include all)
    params = dict(
        position_size_pct=10.0,
        stop_atr_mult=0.5,
        rsi_long_min=50,
        rsi_short_max=50,
        min_atr_percent=0.15,
        max_atr_percent=2.0,
        min_rvol=0.80,
        volume_spike_mult=1.20,
        min_confidence=60,
        skip_bars=3,
    )

    def __init__(self):
        super().__init__()
        self.orb_high = None
        self.orb_low = None
        self._orb_set = False
        self._bar_count = 0
        self._day_bars = 0
        self._current_day = None
        self._stop_price = None
        self._target_price = None

    def next(self):
        super().next()

        dt = self.data.datetime.datetime(0)
        current_day = dt.date()

        # Reset ORB on new day
        if current_day != self._current_day:
            self._current_day = current_day
            self._day_bars = 0
            self._orb_set = False
            self.orb_high = None
            self.orb_low = None

        self._day_bars += 1

        # Build ORB from first N bars of the day
        if self._day_bars <= self.p.skip_bars:
            h = self.data.high[0]
            l = self.data.low[0]
            if self.orb_high is None or h > self.orb_high:
                self.orb_high = h
            if self.orb_low is None or l < self.orb_low:
                self.orb_low = l
            if self._day_bars == self.p.skip_bars:
                self._orb_set = True
            return

        if not self._orb_set or self.orb_high is None:
            return

        # Skip if order pending
        if self.order:
            return

        close = self.data.close[0]
        prev_close = self.data.close[-1]

        # ── Exit logic (check stops/targets) ─────────────────────────
        if self.position:
            if self.position.size > 0:  # Long
                if self._stop_price and close <= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close >= self._target_price:
                    self.order = self.close()
                    return
            elif self.position.size < 0:  # Short
                if self._stop_price and close >= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close <= self._target_price:
                    self.order = self.close()
                    return
            return  # Already in position, don't enter again

        # ── Entry logic ──────────────────────────────────────────────
        atr_pct = self.atr_percent()
        if atr_pct < self.p.min_atr_percent or atr_pct > self.p.max_atr_percent:
            return

        atr_val = self.atr[0]
        rvol = self.rvol()

        # LONG breakout
        if close > self.orb_high and prev_close <= self.orb_high:
            trend_ok = self.ema8[0] > self.ema21[0] or close > self.ema21[0]
            momentum_ok = self.rsi[0] >= self.p.rsi_long_min
            volume_ok = self.volume_spike() or rvol >= self.p.min_rvol

            if trend_ok and momentum_ok and volume_ok:
                confidence = self.calc_confidence("long")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = self.orb_high - (atr_val * self.p.stop_atr_mult)
                    risk = close - self._stop_price
                    self._target_price = close + risk * 2  # 2R target
                    self.order = self.buy(size=size)

        # SHORT breakout
        elif close < self.orb_low and prev_close >= self.orb_low:
            trend_ok = self.ema8[0] < self.ema21[0] or close < self.ema21[0]
            momentum_ok = self.rsi[0] <= self.p.rsi_short_max
            volume_ok = self.volume_spike() or rvol >= self.p.min_rvol

            if trend_ok and momentum_ok and volume_ok:
                confidence = self.calc_confidence("short")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = self.orb_low + (atr_val * self.p.stop_atr_mult)
                    risk = self._stop_price - close
                    self._target_price = close - risk * 2
                    self.order = self.sell(size=size)


# =============================================================================
# VWAP Pullback Strategy
# =============================================================================

class VWAPPullbackStrategy(LEAPSStrategy):
    """
    VWAP Pullback — mirrors signal_engine._check_vwap_pullback.

    Entry:
    - Uptrend: EMA8 > EMA21, price above EMA21
    - Price touches/dips below VWAP, then reclaims it
    - Volume contracting during pullback
    - RSI confirms momentum

    Exit:
    - Stop loss: below VWAP or recent low ∓ 0.3 ATR
    - Take profit: 1.5R target
    """

    # Inherits all base params — no additional params needed

    def __init__(self):
        super().__init__()
        self._current_day = None
        self._cum_vol = 0.0
        self._cum_tp_vol = 0.0   # cumulative (typical_price * volume)
        self._vwap = None
        self._stop_price = None
        self._target_price = None

    def next(self):
        super().next()

        dt = self.data.datetime.datetime(0)
        current_day = dt.date()

        # Reset VWAP on new day
        if current_day != self._current_day:
            self._current_day = current_day
            self._cum_vol = 0.0
            self._cum_tp_vol = 0.0
            self._vwap = None

        # Calculate running VWAP
        typical_price = (self.data.high[0] + self.data.low[0] + self.data.close[0]) / 3.0
        self._cum_tp_vol += typical_price * self.data.volume[0]
        self._cum_vol += self.data.volume[0]
        if self._cum_vol > 0:
            self._vwap = self._cum_tp_vol / self._cum_vol

        if self._vwap is None:
            return

        # Skip if order pending
        if self.order:
            return

        close = self.data.close[0]
        prev_close = self.data.close[-1]
        atr_val = self.atr[0]

        # ── Exit logic ───────────────────────────────────────────────
        if self.position:
            if self.position.size > 0:  # Long
                if self._stop_price and close <= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close >= self._target_price:
                    self.order = self.close()
                    return
            elif self.position.size < 0:  # Short
                if self._stop_price and close >= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close <= self._target_price:
                    self.order = self.close()
                    return
            return

        # ── Entry logic ──────────────────────────────────────────────
        atr_pct = self.atr_percent()
        if atr_pct < self.p.min_atr_percent:
            return

        vwap = self._vwap
        volume = self.data.volume[0]
        vol_ma = self.vol_sma[0]
        volume_contracting = volume < vol_ma if vol_ma > 0 else False

        # LONG: Uptrend, pullback to VWAP, reclaim
        if self.ema8[0] > self.ema21[0] and close > self.ema21[0]:
            touched_vwap = prev_close <= vwap
            reclaiming = close > vwap
            momentum_ok = self.rsi[0] >= self.p.rsi_long_min

            if touched_vwap and reclaiming and volume_contracting and momentum_ok:
                confidence = self.calc_confidence("long")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = min(self.data.low[-1], vwap) - (atr_val * 0.3)
                    risk = close - self._stop_price
                    self._target_price = close + risk * 1.5
                    self.order = self.buy(size=size)

        # SHORT: Downtrend, pullback to VWAP, rejection
        elif self.ema8[0] < self.ema21[0] and close < self.ema21[0]:
            touched_vwap = prev_close >= vwap
            reclaiming_down = close < vwap
            momentum_ok = self.rsi[0] <= self.p.rsi_short_max

            if touched_vwap and reclaiming_down and volume_contracting and momentum_ok:
                confidence = self.calc_confidence("short")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = max(self.data.high[-1], vwap) + (atr_val * 0.3)
                    risk = self._stop_price - close
                    self._target_price = close - risk * 1.5
                    self.order = self.sell(size=size)


# =============================================================================
# Range Breakout Strategy
# =============================================================================

class RangeBreakoutStrategy(LEAPSStrategy):
    """
    Range Breakout — mirrors signal_engine._check_range_breakout.

    Entry:
    - Close crosses above range high (lookback bars) with trend + volume
    - Close crosses below range low with trend + volume

    Exit:
    - Stop loss: ATR-based from breakout level
    - Take profit: 2R target
    """

    # Include base params + Range-specific params
    params = dict(
        position_size_pct=10.0,
        stop_atr_mult=0.5,
        rsi_long_min=50,
        rsi_short_max=50,
        min_atr_percent=0.15,
        max_atr_percent=2.0,
        min_rvol=0.80,
        volume_spike_mult=1.20,
        min_confidence=60,
        range_lookback=30,
    )

    def __init__(self):
        super().__init__()
        self._stop_price = None
        self._target_price = None

    def next(self):
        super().next()

        # Need enough bars for lookback
        if len(self) < self.p.range_lookback + 1:
            return

        # Skip if order pending
        if self.order:
            return

        close = self.data.close[0]
        prev_close = self.data.close[-1]
        atr_val = self.atr[0]

        # Calculate range (lookback bars, excluding current)
        range_high = max(self.data.high[-i] for i in range(1, self.p.range_lookback + 1))
        range_low = min(self.data.low[-i] for i in range(1, self.p.range_lookback + 1))

        # ── Exit logic ───────────────────────────────────────────────
        if self.position:
            if self.position.size > 0:  # Long
                if self._stop_price and close <= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close >= self._target_price:
                    self.order = self.close()
                    return
            elif self.position.size < 0:  # Short
                if self._stop_price and close >= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close <= self._target_price:
                    self.order = self.close()
                    return
            return

        # ── Entry logic ──────────────────────────────────────────────
        atr_pct = self.atr_percent()
        if atr_pct < self.p.min_atr_percent:
            return

        rvol = self.rvol()

        # LONG breakout
        if close > range_high and prev_close <= range_high:
            trend_ok = self.ema8[0] > self.ema21[0]
            momentum_ok = self.rsi[0] >= self.p.rsi_long_min
            volume_ok = self.volume_spike() or rvol >= self.p.min_rvol

            if trend_ok and momentum_ok and volume_ok:
                confidence = self.calc_confidence("long")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = range_high - (atr_val * self.p.stop_atr_mult)
                    risk = close - self._stop_price
                    self._target_price = close + risk * 2
                    self.order = self.buy(size=size)

        # SHORT breakdown
        elif close < range_low and prev_close >= range_low:
            trend_ok = self.ema8[0] < self.ema21[0]
            momentum_ok = self.rsi[0] <= self.p.rsi_short_max
            volume_ok = self.volume_spike() or rvol >= self.p.min_rvol

            if trend_ok and momentum_ok and volume_ok:
                confidence = self.calc_confidence("short")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = range_low + (atr_val * self.p.stop_atr_mult)
                    risk = self._stop_price - close
                    self._target_price = close - risk * 2
                    self.order = self.sell(size=size)


# =============================================================================
# Trend Following Strategy (for 1h and 1d timeframes)
# =============================================================================

class TrendFollowingStrategy(LEAPSStrategy):
    """
    Trend Following — mirrors signal_engine._check_trend_following.

    Entry:
    - SMA20 > SMA50 > SMA200 (uptrend structure)
    - ADX > 25 (strong trend)
    - Price pulls back to SMA20/SMA50 zone
    - RSI 40-70 (trending, not overbought)

    Exit:
    - Stop loss: below SMA50
    - Take profit: 1.5R and 2.5R ATR targets
    """

    # Include base params + Trend Following-specific params
    # Key names match SignalEngine.PARAMS (sma_short, sma_mid, sma_long, min_adx)
    params = dict(
        position_size_pct=10.0,
        stop_atr_mult=1.5,       # Matches signal engine default for daily
        rsi_long_min=40,
        rsi_short_max=60,
        min_atr_percent=1.0,
        max_atr_percent=4.0,
        min_rvol=0.80,
        volume_spike_mult=1.20,
        min_confidence=60,
        sma_short=20,
        sma_mid=50,
        sma_long=200,
        min_adx=20,
        rsi_low=40,
        rsi_high=70,
        pullback_pct=0.5,  # 0.5% — matches signal engine crossover zone
        target_1_atr=1.5,
        target_2_atr=2.5,
    )

    def __init__(self):
        super().__init__()
        self.sma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.sma_short)
        self.sma50 = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.sma_mid)
        self.sma200 = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.sma_long)
        self.adx = bt.indicators.AverageDirectionalMovementIndex(self.data, period=14)
        self._stop_price = None
        self._target_price = None

    def next(self):
        super().next()

        # Need enough bars for SMA200
        if len(self) < self.p.sma_long + 1:
            return

        if self.order:
            return

        close = self.data.close[0]
        atr_val = self.atr[0]

        # ── Exit logic ───────────────────────────────────────────────
        if self.position:
            if self.position.size > 0:
                if self._stop_price and close <= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close >= self._target_price:
                    self.order = self.close()
                    return
            elif self.position.size < 0:
                if self._stop_price and close >= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close <= self._target_price:
                    self.order = self.close()
                    return
            return

        # ── Entry logic ──────────────────────────────────────────────
        sma20 = self.sma20[0]
        sma50 = self.sma50[0]
        sma200 = self.sma200[0]
        adx_val = self.adx[0]
        rsi = self.rsi[0]

        prev_close = self.data.close[-1]

        # LONG: uptrend structure + crossover pullback
        # Matches signal_engine._check_trend_following
        uptrend = sma20 > sma50
        if sma200 > 0:
            uptrend = uptrend and sma50 > sma200

        if uptrend and adx_val >= self.p.min_adx:
            # Pullback-to-crossover: prev was at/below SMA20, now reclaiming
            pullback_zone = prev_close <= sma20 * (1 + self.p.pullback_pct / 100)
            reclaiming = close > sma20
            rsi_ok = self.p.rsi_low <= rsi <= self.p.rsi_high

            if pullback_zone and reclaiming and rsi_ok:
                confidence = self.calc_confidence("long")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = min(sma50, self.data.low[-1]) - (atr_val * self.p.stop_atr_mult)
                    risk = close - self._stop_price
                    self._target_price = close + risk * self.p.target_1_atr
                    self.order = self.buy(size=size)

        # SHORT: downtrend structure + crossover rejection (independent check)
        downtrend = sma20 < sma50
        if sma200 > 0:
            downtrend = downtrend and sma50 < sma200

        if downtrend and adx_val >= self.p.min_adx:
            rally_zone = prev_close >= sma20 * (1 - self.p.pullback_pct / 100)
            rejecting = close < sma20
            rsi_ok = 30 <= rsi <= 60

            if rally_zone and rejecting and rsi_ok:
                confidence = self.calc_confidence("short")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = max(sma50, self.data.high[-1]) + (atr_val * self.p.stop_atr_mult)
                    risk = self._stop_price - close
                    self._target_price = close - risk * self.p.target_1_atr
                    self.order = self.sell(size=size)


# =============================================================================
# Mean Reversion Strategy (for 1d timeframe)
# =============================================================================

class MeanReversionStrategy(LEAPSStrategy):
    """
    Mean Reversion — mirrors signal_engine._check_mean_reversion.

    Entry:
    - RSI < 30 (oversold) or RSI > 70 (overbought)
    - Price at Bollinger Band extremes
    - Volume spike confirming exhaustion

    Exit:
    - Stop loss: beyond Bollinger Band + ATR buffer
    - Target: middle band (SMA20)
    """

    # Include base params + Mean Reversion-specific params
    # Key names match SignalEngine.PARAMS (bb_period, bb_std)
    params = dict(
        position_size_pct=10.0,
        stop_atr_mult=1.5,       # Matches signal engine default for daily
        rsi_long_min=40,
        rsi_short_max=60,
        min_atr_percent=1.0,
        max_atr_percent=4.0,
        min_rvol=0.80,
        volume_spike_mult=1.20,
        min_confidence=60,
        bb_period=20,
        bb_std=2.0,
        rsi_oversold=30,
        rsi_overbought=70,
    )

    def __init__(self):
        super().__init__()
        self.bb = bt.indicators.BollingerBands(self.data.close, period=self.p.bb_period, devfactor=self.p.bb_std)
        self.sma20 = bt.indicators.SimpleMovingAverage(self.data.close, period=20)
        self._stop_price = None
        self._target_price = None

    def next(self):
        super().next()

        if len(self) < self.p.bb_period + 1:
            return

        if self.order:
            return

        close = self.data.close[0]
        atr_val = self.atr[0]
        rsi = self.rsi[0]

        # ── Exit logic ───────────────────────────────────────────────
        if self.position:
            if self.position.size > 0:
                if self._stop_price and close <= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close >= self._target_price:
                    self.order = self.close()
                    return
            elif self.position.size < 0:
                if self._stop_price and close >= self._stop_price:
                    self.order = self.close()
                    return
                if self._target_price and close <= self._target_price:
                    self.order = self.close()
                    return
            return

        # ── Entry logic ──────────────────────────────────────────────
        # Matches signal_engine._check_mean_reversion crossover pattern
        bb_top = self.bb.lines.top[0]
        bb_bot = self.bb.lines.bot[0]
        bb_mid = self.bb.lines.mid[0]
        prev_close = self.data.close[-1]

        # LONG: Oversold + prev touched lower BB, now reclaiming above it
        if rsi <= self.p.rsi_oversold:
            touched_lower = prev_close <= bb_bot * 1.005  # within 0.5% of lower BB
            reclaiming = close > bb_bot

            if touched_lower and reclaiming and self.volume_spike():
                confidence = self.calc_confidence("long")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = min(self.data.low[-1], bb_bot) - (atr_val * self.p.stop_atr_mult)
                    self._target_price = self.sma20[0]  # Mean reversion to SMA20
                    self.order = self.buy(size=size)

        # SHORT: Overbought + prev touched upper BB, now rejecting below it
        elif rsi >= self.p.rsi_overbought:
            touched_upper = prev_close >= bb_top * 0.995  # within 0.5% of upper BB
            rejecting = close < bb_top

            if touched_upper and rejecting and self.volume_spike():
                confidence = self.calc_confidence("short")
                if confidence >= self.p.min_confidence:
                    size = self.calc_size()
                    self._stop_price = max(self.data.high[-1], bb_top) + (atr_val * self.p.stop_atr_mult)
                    self._target_price = self.sma20[0]  # Mean reversion to SMA20
                    self.order = self.sell(size=size)


# =============================================================================
# Strategy Registry
# =============================================================================

STRATEGY_MAP = {
    "orb_breakout": ORBBreakoutStrategy,
    "vwap_pullback": VWAPPullbackStrategy,
    "range_breakout": RangeBreakoutStrategy,
    "trend_following": TrendFollowingStrategy,
    "mean_reversion": MeanReversionStrategy,
}
