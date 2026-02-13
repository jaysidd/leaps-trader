"""
Signal Engine - Trading Strategy Detection
Implements strategies from TradingStrategyPlaybook.md
"""
import asyncio
import math
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from loguru import logger
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.signal_queue import SignalQueue
from app.models.trading_signal import TradingSignal
from app.models.user_alert import AlertNotification
from app.services.data_fetcher.alpaca_service import alpaca_service

ET = ZoneInfo("America/New_York")


class SignalEngine:
    """
    Signal Processing Engine that monitors stocks and generates trading signals.
    Implements 5 strategies across 4 timeframes:
      - ORB Breakout (5m, 15m)
      - VWAP Pullback (5m, 15m, 1h)
      - Range Breakout (5m, 15m, 1h, 1d)
      - Trend Following (1h, 1d)
      - Mean Reversion (1d)
    """

    # Minimum confidence to emit a signal (primary tuning dial)
    MIN_CONFIDENCE = 60

    # Per-item cadence gating (seconds between scans per timeframe)
    SCAN_CADENCES_SECONDS = {
        "5m": 300,      # check every 5 min
        "15m": 900,     # check every 15 min
        "1h": 1800,     # check every 30 min
        "1d": 14400,    # check every 4 hours (once near close for daily bars)
    }

    # Liquidity floors: minimum dollar-volume per bar by cap size and timeframe
    LIQUIDITY_FLOORS = {
        "large_cap":  {"5m": 500_000,  "15m": 1_200_000, "1h": 8_000_000,  "1d": 50_000_000},
        "mid_cap":    {"5m": 250_000,  "15m": 600_000,   "1h": 4_000_000,  "1d": 25_000_000},
        "small_cap":  {"5m": 100_000,  "15m": 250_000,   "1h": 2_000_000,  "1d": 10_000_000},
    }

    # Strategy Parameters by Cap Size
    # Thresholds calibrated for realistic intraday ATR%/RVOL values
    # ATR%/RVOL pivots are soft thresholds — below pivot incurs penalty, not hard-fail
    PARAMS = {
        "large_cap": {
            "5m": {
                "skip_bars": 3,  # 15 min
                "min_atr_percent": 0.15,
                "max_atr_percent": 0.80,
                "atr_pivot": 0.15,
                "rvol_pivot": 0.80,
                "min_rvol": 0.80,
                "volume_spike_mult": 1.20,
                "stop_atr_mult": 0.5,
                "rsi_long_min": 50,
                "rsi_short_max": 50,
            },
            "15m": {
                "skip_bars": 2,  # 30 min
                "min_atr_percent": 0.25,
                "max_atr_percent": 1.20,
                "atr_pivot": 0.25,
                "rvol_pivot": 0.70,
                "min_rvol": 0.70,
                "volume_spike_mult": 1.15,
                "stop_atr_mult": 0.6,
                "range_lookback": 30,
                "rsi_long_min": 55,
                "rsi_short_max": 45,
            },
            "1h": {
                "min_atr_percent": 0.35,
                "max_atr_percent": 1.40,
                "atr_pivot": 0.35,
                "rvol_pivot": 0.60,
                "min_rvol": 0.60,
                "min_adx": 20,
                "stop_atr_mult": 0.8,
                "swing_lookback": 40,
                "range_lookback": 24,
                "rsi_long_min": 50,
                "rsi_short_max": 50,
                "volume_spike_mult": 1.10,
            },
            "1d": {
                "min_atr_percent": 1.0,
                "max_atr_percent": 4.0,
                "atr_pivot": 1.0,
                "rvol_pivot": 0.80,
                "min_rvol": 0.80,
                "min_adx": 20,
                "stop_atr_mult": 1.5,
                "swing_lookback": 55,
                "range_lookback": 20,
                "rsi_long_min": 40,
                "rsi_short_max": 60,
                "volume_spike_mult": 1.20,
                "sma_short": 20,
                "sma_mid": 50,
                "sma_long": 200,
                "bb_period": 20,
                "bb_std": 2.0,
            },
        },
        "mid_cap": {
            "5m": {
                "skip_bars": 3,
                "min_atr_percent": 0.18,
                "max_atr_percent": 1.00,
                "atr_pivot": 0.18,
                "rvol_pivot": 0.90,
                "min_rvol": 0.90,
                "volume_spike_mult": 1.30,
                "stop_atr_mult": 0.6,
                "rsi_long_min": 50,
                "rsi_short_max": 50,
            },
            "15m": {
                "skip_bars": 2,
                "min_atr_percent": 0.30,
                "max_atr_percent": 1.60,
                "atr_pivot": 0.30,
                "rvol_pivot": 0.80,
                "min_rvol": 0.80,
                "volume_spike_mult": 1.20,
                "stop_atr_mult": 0.6,
                "range_lookback": 25,
                "rsi_long_min": 55,
                "rsi_short_max": 45,
            },
            "1h": {
                "min_atr_percent": 0.45,
                "max_atr_percent": 1.60,
                "atr_pivot": 0.45,
                "rvol_pivot": 0.65,
                "min_rvol": 0.65,
                "min_adx": 20,
                "stop_atr_mult": 0.8,
                "swing_lookback": 40,
                "range_lookback": 24,
                "rsi_long_min": 50,
                "rsi_short_max": 50,
                "volume_spike_mult": 1.15,
            },
            "1d": {
                "min_atr_percent": 1.2,
                "max_atr_percent": 5.0,
                "atr_pivot": 1.2,
                "rvol_pivot": 0.80,
                "min_rvol": 0.80,
                "min_adx": 20,
                "stop_atr_mult": 1.5,
                "swing_lookback": 55,
                "range_lookback": 20,
                "rsi_long_min": 40,
                "rsi_short_max": 60,
                "volume_spike_mult": 1.25,
                "sma_short": 20,
                "sma_mid": 50,
                "sma_long": 200,
                "bb_period": 20,
                "bb_std": 2.0,
            },
        },
        "small_cap": {
            "5m": {
                "skip_bars": 2,  # 10 min
                "min_atr_percent": 0.22,
                "max_atr_percent": 1.40,
                "atr_pivot": 0.22,
                "rvol_pivot": 1.00,
                "min_rvol": 1.00,
                "volume_spike_mult": 1.60,
                "stop_atr_mult": 0.7,
                "rsi_long_min": 55,
                "rsi_short_max": 45,
            },
            "15m": {
                "skip_bars": 1,  # 15 min
                "min_atr_percent": 0.35,
                "max_atr_percent": 2.20,
                "atr_pivot": 0.35,
                "rvol_pivot": 0.90,
                "min_rvol": 0.90,
                "volume_spike_mult": 1.30,
                "stop_atr_mult": 0.6,
                "range_lookback": 20,
                "rsi_long_min": 55,
                "rsi_short_max": 45,
            },
            "1h": {
                "min_atr_percent": 0.55,
                "max_atr_percent": 2.00,
                "atr_pivot": 0.55,
                "rvol_pivot": 0.70,
                "min_rvol": 0.70,
                "min_adx": 20,
                "stop_atr_mult": 0.9,
                "swing_lookback": 40,
                "range_lookback": 20,
                "rsi_long_min": 50,
                "rsi_short_max": 50,
                "volume_spike_mult": 1.20,
            },
            "1d": {
                "min_atr_percent": 1.5,
                "max_atr_percent": 6.0,
                "atr_pivot": 1.5,
                "rvol_pivot": 0.90,
                "min_rvol": 0.90,
                "min_adx": 20,
                "stop_atr_mult": 1.5,
                "swing_lookback": 55,
                "range_lookback": 15,
                "rsi_long_min": 40,
                "rsi_short_max": 60,
                "volume_spike_mult": 1.40,
                "sma_short": 20,
                "sma_mid": 50,
                "sma_long": 200,
                "bb_period": 20,
                "bb_std": 2.0,
            },
        },
    }

    def get_params(self, cap_size: str, timeframe: str) -> Dict:
        """Get parameters for cap size and timeframe"""
        cap = cap_size or "large_cap"
        tf = timeframe or "5m"
        return self.PARAMS.get(cap, self.PARAMS["large_cap"]).get(tf, self.PARAMS["large_cap"]["5m"])

    def _classify_cap_size(self, market_cap: float) -> str:
        """Classify market cap into large/mid/small tier"""
        if market_cap >= 10_000_000_000:
            return "large_cap"
        if market_cap >= 2_000_000_000:
            return "mid_cap"
        return "small_cap"

    def _resolve_cap_size(self, symbol: str, db: Session) -> str:
        """Resolve cap size for a symbol, fetching from FMP if needed"""
        try:
            from app.services.data_fetcher.fmp_service import fmp_service
            info = fmp_service.get_stock_info(symbol)
            if info and info.get("market_cap"):
                cap_size = self._classify_cap_size(info["market_cap"])
                logger.debug(f"{symbol} classified as {cap_size} (market_cap={info['market_cap']:,.0f})")
                return cap_size
        except Exception as e:
            logger.warning(f"Failed to resolve cap size for {symbol}: {e}")
        return "large_cap"  # safe default

    def _is_item_due(self, item: SignalQueue, now: datetime) -> bool:
        """Check if a queue item is due for evaluation based on its timeframe cadence."""
        interval = self.SCAN_CADENCES_SECONDS.get(item.timeframe, 300)
        if item.last_checked_at is None:
            return True  # never checked → always due
        # Ensure both timestamps are comparable (UTC)
        last_checked = item.last_checked_at
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        elapsed = (now - last_checked).total_seconds()
        return elapsed >= interval

    def process_queue_item(self, item: SignalQueue, db: Session, cycle_stats: Optional[Dict] = None) -> Optional[TradingSignal]:
        """
        Process a single queue item and check for signals.
        Implements the full pipeline: bars → gates → IV → earnings → strategy → confidence → options.

        Returns TradingSignal if triggered, None otherwise.
        """
        stats = cycle_stats or {}

        try:
            symbol = item.symbol
            timeframe = item.timeframe
            strategy = item.strategy or "auto"

            # 1. Classify cap size (fetch from Yahoo if item.cap_size is None)
            cap_size = item.cap_size
            if not cap_size:
                cap_size = self._resolve_cap_size(symbol, db)
                item.cap_size = cap_size  # cache on queue item
                stats['fmp'] = stats.get('fmp', 0) + 1

            logger.debug(f"Processing {symbol} ({timeframe}, {cap_size}, {strategy})")

            # 2. Get bars with enhanced indicators (TOD-RVOL included)
            df, eval_idx = alpaca_service.get_bars_with_enhanced_indicators(symbol, timeframe)
            stats['alpaca'] = stats.get('alpaca', 0) + 1

            if df is None or len(df) < 30:
                logger.warning(f"Insufficient data for {symbol}")
                return None

            params = self.get_params(cap_size, timeframe)

            # Update last_checked_at IMMEDIATELY after Alpaca fetch (before same-bar check)
            item.times_checked += 1
            item.last_checked_at = datetime.now(timezone.utc)

            # 2b. "New eval bar?" short-circuit
            eval_bar = df.iloc[eval_idx]
            eval_bar_dt = eval_bar.get('datetime')

            if eval_bar_dt is not None:
                # Normalize to UTC string
                if hasattr(eval_bar_dt, 'tzinfo') and eval_bar_dt.tzinfo is not None:
                    eval_ts_utc = eval_bar_dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                else:
                    eval_ts_utc = eval_bar_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

                if timeframe == "1d":
                    # Daily: use date only (one bar per day)
                    eval_key = eval_ts_utc[:10]  # "2024-01-15"
                elif timeframe == "1h":
                    # 1h: use timestamp (complete hourly bars)
                    eval_key = eval_ts_utc
                else:
                    # 5m/15m: use timestamp
                    eval_key = eval_ts_utc

                if item.last_eval_bar_key == eval_key:
                    logger.debug(f"{symbol} same eval bar {eval_key} — skipping")
                    stats['same_bar_skip'] = stats.get('same_bar_skip', 0) + 1
                    db.commit()
                    return None

                item.last_eval_bar_key = eval_key

            # Track TOD-RVOL availability
            rvol_tod = eval_bar.get('rvol_tod')
            if rvol_tod is not None and not pd.isna(rvol_tod):
                stats['tod_rvol_available'] = stats.get('tod_rvol_available', 0) + 1

            # 3. Score quality gates (structural fail or soft penalties)
            passes, gate_scores = self._score_quality_gates(df, params, symbol, cap_size, timeframe, eval_idx)
            if not passes:
                stats['structural_fail'] = stats.get('structural_fail', 0) + 1
                db.commit()
                return None

            # Track heavy penalties
            if gate_scores.get('atr_score', 0) <= -15:
                stats['heavy_atr_penalty'] = stats.get('heavy_atr_penalty', 0) + 1
            if gate_scores.get('rvol_score', 0) <= -15:
                stats['heavy_rvol_penalty'] = stats.get('heavy_rvol_penalty', 0) + 1

            # 4. Fetch iv_rank ONCE, pass to both scorers
            iv_rank = self._fetch_iv_rank(symbol)
            stats['tastytrade'] = stats.get('tastytrade', 0) + 1
            iv_score = self._score_iv_quality(iv_rank, cap_size)
            earnings_score = self._score_earnings_risk(symbol, iv_rank)
            stats['catalyst'] = stats.get('catalyst', 0) + 1

            # 5. Check strategies (pass gate_scores, iv_score, earnings_score, eval_idx)
            # Strategy-timeframe applicability:
            #   5m:  ORB, VWAP, Range
            #   15m: ORB, VWAP, Range
            #   1h:  VWAP, Range, Trend Following
            #   1d:  Range, Trend Following, Mean Reversion
            signal = None

            intraday_tf = timeframe in ("5m", "15m")

            if (strategy == "auto" or strategy == "orb_breakout") and intraday_tf:
                signal = self._check_orb_breakout(symbol, df, params, cap_size, timeframe)

            if not signal and (strategy == "auto" or strategy == "vwap_pullback") and timeframe != "1d":
                signal = self._check_vwap_pullback(symbol, df, params, cap_size, timeframe)

            if not signal and (strategy == "auto" or strategy == "range_breakout"):
                signal = self._check_range_breakout(symbol, df, params, cap_size, timeframe)

            if not signal and (strategy == "auto" or strategy == "trend_following") and timeframe in ("1h", "1d"):
                signal = self._check_trend_following(symbol, df, params, cap_size, timeframe)

            if not signal and (strategy == "auto" or strategy == "mean_reversion") and timeframe == "1d":
                signal = self._check_mean_reversion(symbol, df, params, cap_size, timeframe)

            # If a strategy produced a signal, recalculate confidence with full context
            if signal:
                direction = "long" if signal['direction'] == "buy" else "short"
                signal['confidence'] = self._calculate_confidence(
                    df, direction, params,
                    eval_idx=eval_idx,
                    gate_scores=gate_scores,
                    iv_score=iv_score,
                    earnings_score=earnings_score,
                )

                # 6. MIN_CONFIDENCE filter
                if signal['confidence'] < self.MIN_CONFIDENCE:
                    logger.debug(
                        f"{symbol} signal rejected: confidence {signal['confidence']:.0f} < {self.MIN_CONFIDENCE}"
                    )
                    stats['rejected_low_conf'] = stats.get('rejected_low_conf', 0) + 1
                    signal = None

            if signal:
                stats['equity_eligible'] = stats.get('equity_eligible', 0) + 1

                # 7. Check options eligibility (metadata, not a blocker)
                options_info = self._check_options_eligibility(symbol, signal['direction'], cap_size)
                stats['fmp'] = stats.get('fmp', 0) + 1
                signal['options_eligible'] = options_info.get('options_eligible', False)
                signal['options_details'] = options_info
                if signal['options_eligible']:
                    stats['options_eligible'] = stats.get('options_eligible', 0) + 1

                # 8. Check for duplicate — skip if same symbol+strategy+direction already exists and is still active
                existing = db.query(TradingSignal).filter(
                    TradingSignal.symbol == signal['symbol'],
                    TradingSignal.strategy == signal['strategy'],
                    TradingSignal.direction == signal['direction'],
                    TradingSignal.timeframe == item.timeframe,
                    TradingSignal.status == 'active',
                ).first()
                if existing:
                    logger.info(f"Skipping duplicate signal: {signal['symbol']} {signal['strategy']} already active (id={existing.id})")
                    db.commit()
                    return None

                # 9. Create record + notify
                trading_signal = self._create_signal_record(signal, item, db)
                item.signals_generated += 1
                db.commit()
                return trading_signal

            db.commit()
            return None

        except Exception as e:
            logger.error(f"Error processing {item.symbol}: {e}")
            return None

    def _score_quality_gates(
        self, df: pd.DataFrame, params: Dict, symbol: str,
        cap_size: str, timeframe: str, eval_idx: int
    ) -> Tuple[bool, Dict[str, float]]:
        """
        Score quality gates with soft penalties instead of binary pass/fail.

        Structural hard-fails (return (False, {})):
        - Missing/NaN required fields
        - volume <= 0 or atr_percent <= 0
        - Fewer than 30 bars
        - Stale data (5m/15m only)
        - Dollar volume below liquidity floor

        Soft scores (feed into confidence):
        - ATR% relative to pivot: -20 to +5
        - RVOL (effective) relative to pivot: -20 to +10
        """
        try:
            bar = df.iloc[eval_idx]

            # --- Structural hard-fails ---
            close = bar.get('close')
            volume = bar.get('volume')
            atr_percent = bar.get('atr_percent')

            if close is None or pd.isna(close) or volume is None or pd.isna(volume):
                logger.debug(f"{symbol} gate HARD-FAIL: missing close/volume")
                return (False, {})

            if atr_percent is None or pd.isna(atr_percent):
                logger.debug(f"{symbol} gate HARD-FAIL: missing atr_percent")
                return (False, {})

            if volume <= 0 or atr_percent <= 0:
                logger.debug(f"{symbol} gate HARD-FAIL: volume={volume} atr%={atr_percent}")
                return (False, {})

            if len(df) < 30:
                logger.debug(f"{symbol} gate HARD-FAIL: only {len(df)} bars (need >=30)")
                return (False, {})

            # Stale data check (skip for daily — uses completed bars only)
            if timeframe != "1d":
                bar_dt = bar.get('datetime')
                if bar_dt is not None:
                    now = datetime.now(timezone.utc)
                    if hasattr(bar_dt, 'tzinfo') and bar_dt.tzinfo is not None:
                        bar_utc = bar_dt.astimezone(timezone.utc)
                    else:
                        bar_utc = bar_dt.replace(tzinfo=timezone.utc)

                    age_seconds = (now - bar_utc).total_seconds()
                    now_et = now.astimezone(ET)
                    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
                    minutes_since_open = (now_et - market_open).total_seconds() / 60.0

                    # Skip stale check in first 10 min after open
                    if minutes_since_open > 10:
                        # eval_idx is df.iloc[-2] (second-to-last bar), so age includes
                        # the full bar duration. Allow 4 bar widths before marking stale.
                        stale_limits = {"5m": 1200, "15m": 3600, "1h": 7200}  # 20min / 60min / 2hr
                        stale_limit = stale_limits.get(timeframe, 3600)
                        if age_seconds > stale_limit:
                            logger.debug(f"{symbol} gate HARD-FAIL: stale data ({age_seconds:.0f}s old)")
                            return (False, {})

            # Liquidity floor check
            tod_avg_dv = bar.get('tod_avg_dollar_volume')
            if tod_avg_dv is not None and not pd.isna(tod_avg_dv):
                floor = self.LIQUIDITY_FLOORS.get(cap_size, {}).get(timeframe, 0)
                effective_dv = tod_avg_dv

                if effective_dv < floor:
                    logger.debug(
                        f"{symbol} gate HARD-FAIL: liquidity ${effective_dv:,.0f} < floor ${floor:,.0f}"
                    )
                    return (False, {})

            # --- Soft scoring ---
            atr_pivot = params.get('atr_pivot', params.get('min_atr_percent', 0.15))
            max_atr = params.get('max_atr_percent', 1.0)

            # ATR% score
            if atr_percent >= atr_pivot * 1.5:
                atr_score = 5.0
            elif atr_percent >= atr_pivot:
                atr_score = 0.0
            elif atr_percent >= atr_pivot * 0.5:
                # Linear -15 to 0 between 50% and 100% of pivot
                ratio = (atr_percent - atr_pivot * 0.5) / (atr_pivot * 0.5)
                atr_score = -15.0 * (1.0 - ratio)
            else:
                atr_score = -20.0

            # Choppy penalty
            if atr_percent > max_atr:
                atr_score -= 10.0

            # RVOL score (uses effective_rvol = rvol_tod if available, else classic rvol)
            rvol_tod = bar.get('rvol_tod')
            classic_rvol = bar.get('rvol', 1.0)
            effective_rvol = rvol_tod if (rvol_tod is not None and not pd.isna(rvol_tod)) else classic_rvol

            rvol_pivot = params.get('rvol_pivot', params.get('min_rvol', 0.80))

            if effective_rvol >= rvol_pivot * 2.0:
                rvol_score = 10.0
            elif effective_rvol >= rvol_pivot * 1.5:
                rvol_score = 5.0
            elif effective_rvol >= rvol_pivot:
                rvol_score = 0.0
            elif effective_rvol >= rvol_pivot * 0.5:
                ratio = (effective_rvol - rvol_pivot * 0.5) / (rvol_pivot * 0.5)
                rvol_score = -15.0 * (1.0 - ratio)
            else:
                rvol_score = -20.0

            logger.debug(
                f"{symbol} gates PASSED: ATR%={atr_percent:.3f}(score={atr_score:+.0f}) "
                f"eRVOL={effective_rvol:.2f}(score={rvol_score:+.0f}) "
                f"tod_rvol={'yes' if (rvol_tod is not None and not pd.isna(rvol_tod)) else 'no'}"
            )

            return (True, {"atr_score": atr_score, "rvol_score": rvol_score})

        except Exception as e:
            logger.error(f"Error scoring quality gates for {symbol}: {e}")
            return (False, {})

    # ==========================================================================
    # IV, Earnings, and Options Overlays
    # ==========================================================================

    def _fetch_iv_rank(self, symbol: str) -> Optional[float]:
        """Fetch IV rank from TastyTrade (single call, shared by IV and earnings scoring)"""
        try:
            from app.services.data_fetcher.tastytrade import get_tastytrade_service
            service = get_tastytrade_service()
            return service.get_iv_rank(symbol)
        except Exception as e:
            logger.debug(f"Could not fetch IV rank for {symbol}: {e}")
            return None

    def _score_iv_quality(self, iv_rank: Optional[float], cap_size: str) -> float:
        """
        Score IV quality for LEAPS-friendly entries.
        Low IV = cheap vol tailwind (+5), High IV = expensive entries (-20).
        """
        if iv_rank is None:
            return 0.0  # neutral if unavailable

        if cap_size == "small_cap":
            # Small caps tolerate higher baseline IV
            if iv_rank <= 25:
                return 5.0
            elif iv_rank <= 60:
                return 0.0
            elif iv_rank <= 80:
                return -5.0
            elif iv_rank <= 90:
                return -12.0
            else:
                return -20.0
        else:
            # Large/Mid cap
            if iv_rank <= 20:
                return 5.0
            elif iv_rank <= 50:
                return 0.0
            elif iv_rank <= 70:
                return -5.0
            elif iv_rank <= 85:
                return -12.0
            else:
                return -20.0

    def _score_earnings_risk(self, symbol: str, iv_rank: Optional[float]) -> float:
        """
        Penalty for earnings proximity (gap risk + inflated IV).
        """
        try:
            from app.services.analysis.catalyst import get_catalyst_service
            catalyst = get_catalyst_service()

            # get_earnings_date is async — run in current event loop or create one
            earnings_date = None
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        earnings_date = pool.submit(
                            asyncio.run, catalyst.get_earnings_date(symbol)
                        ).result(timeout=5)
                else:
                    earnings_date = loop.run_until_complete(catalyst.get_earnings_date(symbol))
            except Exception:
                # If we can't get earnings date, return neutral
                return 0.0

            if earnings_date is None:
                return 0.0

            now = datetime.now(timezone.utc)
            if hasattr(earnings_date, 'tzinfo') and earnings_date.tzinfo is None:
                earnings_date = earnings_date.replace(tzinfo=timezone.utc)
            days_to_earnings = (earnings_date - now).days

            if days_to_earnings <= 14:
                if iv_rank is not None and iv_rank >= 70:
                    return -10.0  # inflated IV into earnings
                return -5.0  # gap risk

            return 0.0

        except Exception as e:
            logger.debug(f"Could not score earnings risk for {symbol}: {e}")
            return 0.0

    def _check_options_eligibility(self, symbol: str, direction: str, cap_size: str) -> Dict:
        """
        Check options chain for LEAPS eligibility (metadata only, not a blocker).
        Uses strike proximity as delta proxy for 0.30-0.50 delta at 150-210 DTE.
        """
        try:
            from app.services.data_fetcher.alpaca_service import alpaca_service as _alpaca
            chain = _alpaca.get_options_chain(symbol, include_leaps=True)
            if chain is None:
                return {"options_eligible": False, "reason": "no options data"}

            # Find expiration in 150-210 DTE window
            now = datetime.now()
            target_dte_min = 150
            target_dte_max = 210

            # Get current price
            from app.services.data_fetcher.fmp_service import fmp_service as _fmp
            info = _fmp.get_stock_info(symbol)
            if not info or not info.get("current_price"):
                return {"options_eligible": False, "reason": "no price data"}

            spot = info["current_price"]

            # Check ADDV (average daily dollar volume)
            addv_floors = {"large_cap": 150_000_000, "mid_cap": 75_000_000, "small_cap": 30_000_000}
            avg_volume = info.get("average_volume", 0)
            daily_dollar_volume = avg_volume * spot if avg_volume else 0
            if daily_dollar_volume < addv_floors.get(cap_size, 75_000_000):
                return {"options_eligible": False, "reason": f"ADDV ${daily_dollar_volume:,.0f} below floor"}

            # OI and spread caps by cap size
            oi_floors = {"large_cap": 500, "mid_cap": 300, "small_cap": 150}
            spread_caps = {"large_cap": 0.12, "mid_cap": 0.12, "small_cap": 0.18}
            min_oi = oi_floors.get(cap_size, 300)
            max_spread_pct = spread_caps.get(cap_size, 0.12)

            # Determine strike band based on direction
            if direction in ("buy", "long"):
                # Calls: 100-110% of spot
                strike_low = spot * 1.00
                strike_high = spot * 1.10
                option_type = "calls"
            else:
                # Puts: 90-100% of spot
                strike_low = spot * 0.90
                strike_high = spot * 1.00
                option_type = "puts"

            options_df = chain.get(option_type)
            if options_df is None or options_df.empty:
                return {"options_eligible": False, "reason": f"no {option_type} data"}

            # Filter to target DTE and strike band
            best_contract = None
            for _, row in options_df.iterrows():
                # Check expiration
                exp_date = row.get('expiration') or row.get('expirationDate')
                if exp_date is None:
                    continue
                if isinstance(exp_date, str):
                    try:
                        exp_date = datetime.strptime(exp_date, "%Y-%m-%d")
                    except ValueError:
                        continue

                dte = (exp_date - now).days if hasattr(exp_date, 'days') else (exp_date - now).days
                if dte < target_dte_min - 10 or dte > target_dte_max + 30:
                    continue

                strike = row.get('strike', 0)
                if strike < strike_low or strike > strike_high:
                    continue

                # Defensive guardrails
                bid = row.get('bid')
                ask = row.get('ask')
                if bid is None or ask is None or pd.isna(bid) or pd.isna(ask):
                    continue
                if bid <= 0 or ask <= 0:
                    continue

                mid = (bid + ask) / 2.0
                if mid <= 0:
                    continue

                spread = ask - bid
                spread_pct = spread / mid
                if spread_pct > 1.0:  # data anomaly
                    continue
                if spread_pct > max_spread_pct:
                    continue

                oi = row.get('openInterest', 0) or 0
                if oi < min_oi:
                    continue

                # This contract qualifies — pick the one with best OI
                if best_contract is None or oi > best_contract.get('oi', 0):
                    best_contract = {
                        "options_eligible": True,
                        "best_strike": float(strike),
                        "dte": int(dte),
                        "oi": int(oi),
                        "spread_pct": round(spread_pct * 100, 1),
                        "mid_price": round(mid, 2),
                    }

            if best_contract:
                return best_contract

            return {"options_eligible": False, "reason": "no qualifying contracts in strike band"}

        except Exception as e:
            logger.debug(f"Options eligibility check failed for {symbol}: {e}")
            return {"options_eligible": False, "reason": str(e)}

    # ==========================================================================
    # Strategy Checks
    # ==========================================================================

    def _check_orb_breakout(
        self, symbol: str, df: pd.DataFrame, params: Dict, cap_size: str, timeframe: str
    ) -> Optional[Dict]:
        """
        Check for ORB (Opening Range Breakout) signal.

        Buy Signal:
        - Close crosses above ORB High
        - Volume spike = true
        - RVOL >= threshold
        - EMA8 > EMA21 or price above EMA21

        Sell Signal:
        - Close crosses below ORB Low
        - Same volume/RVOL filters
        - EMA8 < EMA21 or close < EMA21
        """
        try:
            skip_bars = params.get('skip_bars', 3)

            # Check if we're past the skip period
            if len(df) <= skip_bars:
                return None

            # Get ORB data
            orb = alpaca_service.get_opening_range(symbol, orb_bars=skip_bars)
            if not orb:
                return None

            orb_high = orb['orb_high']
            orb_low = orb['orb_low']

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            close = latest['close']
            prev_close = prev['close']
            ema8 = latest.get('ema8', close)
            ema21 = latest.get('ema21', close)
            rsi = latest.get('rsi', 50)
            volume_spike = latest.get('volume_spike', False)
            rvol = latest.get('rvol', 1.0)
            atr = latest.get('atr', 0)

            # Check for LONG breakout
            if close > orb_high and prev_close <= orb_high:
                # Confirm with trend and momentum
                trend_ok = ema8 > ema21 or close > ema21
                momentum_ok = rsi >= params.get('rsi_long_min', 50)

                if trend_ok and momentum_ok and (volume_spike or rvol >= params.get('min_rvol', 1.2)):
                    stop_loss = orb_high - (atr * params.get('stop_atr_mult', 0.5))
                    target_1 = close + (close - stop_loss)  # 1R target
                    target_2 = close + (close - stop_loss) * 2  # 2R target

                    return {
                        "symbol": symbol,
                        "direction": "buy",
                        "strategy": "orb_breakout_long",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "long", params),
                        "orb_high": orb_high,
                        "orb_low": orb_low,
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            # Check for SHORT breakdown
            if close < orb_low and prev_close >= orb_low:
                trend_ok = ema8 < ema21 or close < ema21
                momentum_ok = rsi <= params.get('rsi_short_max', 50)

                if trend_ok and momentum_ok and (volume_spike or rvol >= params.get('min_rvol', 1.2)):
                    stop_loss = orb_low + (atr * params.get('stop_atr_mult', 0.5))
                    target_1 = close - (stop_loss - close)
                    target_2 = close - (stop_loss - close) * 2

                    return {
                        "symbol": symbol,
                        "direction": "sell",
                        "strategy": "orb_breakout_short",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "short", params),
                        "orb_high": orb_high,
                        "orb_low": orb_low,
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            return None

        except Exception as e:
            logger.error(f"Error checking ORB breakout for {symbol}: {e}")
            return None

    def _check_vwap_pullback(
        self, symbol: str, df: pd.DataFrame, params: Dict, cap_size: str, timeframe: str
    ) -> Optional[Dict]:
        """
        Check for VWAP Pullback signal.

        Buy Signal:
        - EMA8 > EMA21 and price above EMA21
        - Price tags VWAP during pullback
        - Pullback volume < VolMA20 (contraction)
        - Close reclaims VWAP
        - RSI > 50 or MACD > 0
        """
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            close = latest['close']
            prev_close = prev['close']
            ema8 = latest.get('ema8', close)
            ema21 = latest.get('ema21', close)
            rsi = latest.get('rsi', 50)
            atr = latest.get('atr', 0)
            volume = latest.get('volume', 0)
            volume_ma = latest.get('volume_ma20', volume)

            # Get VWAP from snapshot
            snapshot = alpaca_service.get_snapshot(symbol)
            if not snapshot or 'daily_bar' not in snapshot:
                return None

            vwap = snapshot['daily_bar'].get('vwap')
            if not vwap:
                return None

            # Check for LONG pullback reclaim
            if ema8 > ema21 and close > ema21:
                # Price touched or dipped below VWAP, now reclaiming
                touched_vwap = prev_close <= vwap
                reclaiming = close > vwap

                # Volume contraction during pullback
                volume_contracting = volume < volume_ma

                momentum_ok = rsi >= params.get('rsi_long_min', 50)

                if touched_vwap and reclaiming and volume_contracting and momentum_ok:
                    stop_loss = min(prev['low'], vwap) - (atr * 0.3)
                    target_1 = close + (close - stop_loss)
                    target_2 = close + (close - stop_loss) * 1.5

                    return {
                        "symbol": symbol,
                        "direction": "buy",
                        "strategy": "vwap_pullback_long",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "long", params),
                        "vwap": vwap,
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            # Check for SHORT pullback
            if ema8 < ema21 and close < ema21:
                touched_vwap = prev_close >= vwap
                reclaiming_down = close < vwap
                volume_contracting = volume < volume_ma
                momentum_ok = rsi <= params.get('rsi_short_max', 50)

                if touched_vwap and reclaiming_down and volume_contracting and momentum_ok:
                    stop_loss = max(prev['high'], vwap) + (atr * 0.3)
                    target_1 = close - (stop_loss - close)
                    target_2 = close - (stop_loss - close) * 1.5

                    return {
                        "symbol": symbol,
                        "direction": "sell",
                        "strategy": "vwap_pullback_short",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "short", params),
                        "vwap": vwap,
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            return None

        except Exception as e:
            logger.error(f"Error checking VWAP pullback for {symbol}: {e}")
            return None

    def _check_range_breakout(
        self, symbol: str, df: pd.DataFrame, params: Dict, cap_size: str, timeframe: str
    ) -> Optional[Dict]:
        """
        Check for Range Breakout signal (15m timeframe).

        Buy Signal:
        - Close crosses above range high (last 30 bars)
        - Volume spike = true
        - RVOL >= threshold
        - EMA8 > EMA21
        - RSI >= 55
        """
        try:
            lookback = params.get('range_lookback', 30)

            if len(df) < lookback:
                return None

            # Calculate range
            range_df = df.iloc[-lookback:-1]  # Exclude current bar
            range_high = range_df['high'].max()
            range_low = range_df['low'].min()

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            close = latest['close']
            prev_close = prev['close']
            ema8 = latest.get('ema8', close)
            ema21 = latest.get('ema21', close)
            rsi = latest.get('rsi', 50)
            volume_spike = latest.get('volume_spike', False)
            rvol = latest.get('rvol', 1.0)
            atr = latest.get('atr', 0)

            # Check for LONG breakout
            if close > range_high and prev_close <= range_high:
                trend_ok = ema8 > ema21
                momentum_ok = rsi >= params.get('rsi_long_min', 55)

                if trend_ok and momentum_ok and (volume_spike or rvol >= params.get('min_rvol', 1.15)):
                    stop_loss = range_high - (atr * params.get('stop_atr_mult', 0.6))
                    target_1 = close + (close - stop_loss)
                    target_2 = close + (close - stop_loss) * 2

                    return {
                        "symbol": symbol,
                        "direction": "buy",
                        "strategy": "range_breakout_long",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "long", params),
                        "range_high": range_high,
                        "range_low": range_low,
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            # Check for SHORT breakdown
            if close < range_low and prev_close >= range_low:
                trend_ok = ema8 < ema21
                momentum_ok = rsi <= params.get('rsi_short_max', 45)

                if trend_ok and momentum_ok and (volume_spike or rvol >= params.get('min_rvol', 1.15)):
                    stop_loss = range_low + (atr * params.get('stop_atr_mult', 0.6))
                    target_1 = close - (stop_loss - close)
                    target_2 = close - (stop_loss - close) * 2

                    return {
                        "symbol": symbol,
                        "direction": "sell",
                        "strategy": "range_breakout_short",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "short", params),
                        "range_high": range_high,
                        "range_low": range_low,
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            return None

        except Exception as e:
            logger.error(f"Error checking range breakout for {symbol}: {e}")
            return None

    def _check_trend_following(
        self, symbol: str, df: pd.DataFrame, params: Dict, cap_size: str, timeframe: str
    ) -> Optional[Dict]:
        """
        Check for Trend Following signal (1h and Daily timeframes).

        Buy Signal:
        - SMA20 > SMA50 > SMA200 (uptrend structure)
        - ADX > 25 (strong trend)
        - Price pulls back to SMA20/50 zone, then reclaims SMA20
        - RSI 40-70 (trending, not overbought)

        Sell Signal:
        - SMA20 < SMA50 < SMA200 (downtrend structure)
        - ADX > 25
        - Price rallies to SMA20/50 zone, then rejects below SMA20
        - RSI 30-60
        """
        try:
            if len(df) < 55:
                return None

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            close = latest['close']
            prev_close = prev['close']

            # Get SMAs — use pre-calculated from alpaca_service if available, else compute
            sma20 = latest.get('sma_20') or latest.get('sma20')
            sma50 = latest.get('sma50') or latest.get('sma_50')
            # SMA200 may not exist in intraday data — compute from df if needed
            sma200 = latest.get('sma_200') or latest.get('sma200')
            if sma200 is None and len(df) >= 200:
                sma200 = df['close'].iloc[-200:].mean()

            adx = latest.get('adx', latest.get('adx_14', 0))
            rsi = latest.get('rsi', latest.get('rsi_14', 50))
            atr = latest.get('atr', latest.get('atr_14', 0))

            # Need all SMAs for trend structure
            if sma20 is None or sma50 is None:
                return None

            min_adx = params.get('min_adx', 25)

            # Check for LONG trend following
            uptrend = sma20 > sma50
            if sma200 is not None:
                uptrend = uptrend and sma50 > sma200

            if uptrend and adx >= min_adx:
                # Pullback to SMA20/50 zone: prev was at/below SMA20, now reclaiming
                pullback_zone = prev_close <= sma20 * 1.005  # within 0.5% of SMA20
                reclaiming = close > sma20
                rsi_ok = 40 <= rsi <= 70

                if pullback_zone and reclaiming and rsi_ok:
                    stop_loss = min(sma50, prev['low']) - (atr * params.get('stop_atr_mult', 1.5))
                    risk = close - stop_loss
                    target_1 = close + risk * 1.5  # 1.5R
                    target_2 = close + risk * 2.5  # 2.5R

                    return {
                        "symbol": symbol,
                        "direction": "buy",
                        "strategy": "trend_following_long",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "long", params),
                        "sma20": sma20,
                        "sma50": sma50,
                        "sma200": sma200,
                        "adx": adx,
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            # Check for SHORT trend following
            downtrend = sma20 < sma50
            if sma200 is not None:
                downtrend = downtrend and sma50 < sma200

            if downtrend and adx >= min_adx:
                # Rally to SMA20/50 zone: prev was at/above SMA20, now rejecting
                rally_zone = prev_close >= sma20 * 0.995  # within 0.5% of SMA20
                rejecting = close < sma20
                rsi_ok = 30 <= rsi <= 60

                if rally_zone and rejecting and rsi_ok:
                    stop_loss = max(sma50, prev['high']) + (atr * params.get('stop_atr_mult', 1.5))
                    risk = stop_loss - close
                    target_1 = close - risk * 1.5
                    target_2 = close - risk * 2.5

                    return {
                        "symbol": symbol,
                        "direction": "sell",
                        "strategy": "trend_following_short",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "short", params),
                        "sma20": sma20,
                        "sma50": sma50,
                        "sma200": sma200,
                        "adx": adx,
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            return None

        except Exception as e:
            logger.error(f"Error checking trend following for {symbol}: {e}")
            return None

    def _check_mean_reversion(
        self, symbol: str, df: pd.DataFrame, params: Dict, cap_size: str, timeframe: str
    ) -> Optional[Dict]:
        """
        Check for Mean Reversion signal (Daily timeframe only).

        Buy Signal (oversold bounce):
        - RSI < 30 (oversold)
        - Price at or below lower Bollinger Band
        - Volume spike confirming selling exhaustion
        - Close reclaims above lower BB (reversal candle)

        Sell Signal (overbought reversal):
        - RSI > 70 (overbought)
        - Price at or above upper Bollinger Band
        - Volume spike confirming buying exhaustion
        - Close rejects below upper BB
        """
        try:
            bb_period = params.get('bb_period', 20)
            if len(df) < bb_period + 5:
                return None

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            close = latest['close']
            prev_close = prev['close']
            rsi = latest.get('rsi', latest.get('rsi_14', 50))
            atr = latest.get('atr', latest.get('atr_14', 0))
            volume = latest.get('volume', 0)
            volume_ma = latest.get('volume_ma20', volume)
            volume_spike = volume > volume_ma * params.get('volume_spike_mult', 1.2) if volume_ma > 0 else False

            # Calculate Bollinger Bands from df
            bb_std = params.get('bb_std', 2.0)
            bb_close = df['close'].iloc[-bb_period:]
            bb_mid = bb_close.mean()
            bb_std_val = bb_close.std(ddof=0)  # population std, matches Backtrader/TradingView
            bb_upper = bb_mid + bb_std * bb_std_val
            bb_lower = bb_mid - bb_std * bb_std_val

            # Get SMA20 for target (mean reversion target)
            sma20 = latest.get('sma_20') or latest.get('sma20') or bb_mid

            # Check for LONG mean reversion (oversold bounce)
            if rsi < 30:
                # Price was at/below lower BB, now reclaiming
                touched_lower = prev_close <= bb_lower * 1.005
                reclaiming = close > bb_lower

                if touched_lower and reclaiming and volume_spike:
                    stop_loss = min(prev['low'], bb_lower) - (atr * params.get('stop_atr_mult', 1.5))
                    target_1 = sma20  # revert to mean (SMA20)
                    target_2 = bb_upper  # overshoot to upper band

                    return {
                        "symbol": symbol,
                        "direction": "buy",
                        "strategy": "mean_reversion_long",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "long", params),
                        "bb_upper": round(bb_upper, 2),
                        "bb_mid": round(bb_mid, 2),
                        "bb_lower": round(bb_lower, 2),
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            # Check for SHORT mean reversion (overbought rejection)
            if rsi > 70:
                touched_upper = prev_close >= bb_upper * 0.995
                rejecting = close < bb_upper

                if touched_upper and rejecting and volume_spike:
                    stop_loss = max(prev['high'], bb_upper) + (atr * params.get('stop_atr_mult', 1.5))
                    target_1 = sma20  # revert to mean
                    target_2 = bb_lower  # overshoot to lower band

                    return {
                        "symbol": symbol,
                        "direction": "sell",
                        "strategy": "mean_reversion_short",
                        "entry_price": close,
                        "stop_loss": stop_loss,
                        "target_1": target_1,
                        "target_2": target_2,
                        "confidence": self._calculate_confidence(df, "short", params),
                        "bb_upper": round(bb_upper, 2),
                        "bb_mid": round(bb_mid, 2),
                        "bb_lower": round(bb_lower, 2),
                        "technical_snapshot": self._get_technical_snapshot(df),
                    }

            return None

        except Exception as e:
            logger.error(f"Error checking mean reversion for {symbol}: {e}")
            return None

    def _calculate_confidence(
        self, df: pd.DataFrame, direction: str, params: Dict,
        eval_idx: int = -1,
        gate_scores: Optional[Dict[str, float]] = None,
        iv_score: float = 0.0,
        earnings_score: float = 0.0,
    ) -> float:
        """
        Calculate confidence score (0-100).

        Components:
        - Base: 50
        - Trend alignment (EMA8/EMA21 + price position): 0 to +20
        - Momentum (RSI): 0 to +15
        - Volume confirmation (spike + effective_rvol tiers): 0 to +20
        - ATR quality: 0 to +5
        - Gate: ATR score: -20 to +5
        - Gate: RVOL score: -20 to +10
        - IV quality: -20 to +5
        - Earnings risk: -10 to 0
        """
        try:
            bar = df.iloc[eval_idx]
            score = 50.0  # Base score

            ema8 = bar.get('ema8', 0)
            ema21 = bar.get('ema21', 0)
            rsi = bar.get('rsi', 50)
            volume_spike = bar.get('volume_spike', False)
            atr_percent = bar.get('atr_percent', 0)

            # Use effective_rvol (TOD if available, else classic)
            rvol_tod = bar.get('rvol_tod')
            classic_rvol = bar.get('rvol', 1.0)
            effective_rvol = rvol_tod if (rvol_tod is not None and not pd.isna(rvol_tod)) else classic_rvol

            # Trend alignment (0 to +20)
            if direction == "long":
                if ema8 > ema21:
                    score += 15
                if bar['close'] > ema21:
                    score += 5
            else:
                if ema8 < ema21:
                    score += 15
                if bar['close'] < ema21:
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

            # Volume confirmation (0 to +20) — uses effective_rvol
            if volume_spike:
                score += 10
            if effective_rvol > 2.0:
                score += 10
            elif effective_rvol > 1.5:
                score += 5

            # ATR quality (0 to +5)
            min_atr = params.get('min_atr_percent', 0.15)
            if atr_percent > min_atr * 1.5:
                score += 5

            # Gate scores — cap total negative penalty at -15 to avoid
            # crushing stocks that pass screening but have modest vol/ATR
            if gate_scores:
                atr_s = gate_scores.get('atr_score', 0)
                rvol_s = gate_scores.get('rvol_score', 0)
                combined_gate = atr_s + rvol_s
                score += max(combined_gate, -15.0)

            # IV quality (-20 to +5)
            score += iv_score

            # Earnings risk (-10 to 0)
            score += earnings_score

            return min(max(score, 0), 100)

        except Exception as e:
            logger.error(f"Error calculating confidence: {e}")
            return 50

    def _get_technical_snapshot(self, df: pd.DataFrame) -> Dict:
        """Get current technical indicators for signal record"""
        try:
            latest = df.iloc[-1]
            return {
                "rsi": round(latest.get('rsi', 0), 2),
                "ema8": round(latest.get('ema8', 0), 2),
                "ema21": round(latest.get('ema21', 0), 2),
                "sma50": round(latest.get('sma50', 0), 2) if 'sma50' in latest else None,
                "atr": round(latest.get('atr', 0), 4),
                "atr_percent": round(latest.get('atr_percent', 0), 2),
                "rvol": round(latest.get('rvol', 0), 2),
                "volume_spike": bool(latest.get('volume_spike', False)),
                "close": round(latest.get('close', 0), 2),
                "volume": int(latest.get('volume', 0)),
            }
        except Exception:
            return {}

    def _generate_ai_reasoning(self, signal: Dict, cap_size: str, timeframe: str) -> str:
        """Generate AI Journaling text explaining the signal"""
        direction = "long" if signal['direction'] == "buy" else "short"
        strategy = signal['strategy'].replace("_", " ").title()
        confidence = signal.get('confidence', 50)

        tech = signal.get('technical_snapshot', {})
        rsi = tech.get('rsi', 50)
        rvol = tech.get('rvol', 1.0)
        ema8 = tech.get('ema8', 0)
        ema21 = tech.get('ema21', 0)

        # Build reasoning text
        reasoning = f"Initiating {'high' if confidence >= 75 else 'moderate'}-confidence ({confidence}%) {direction} on {signal['symbol']} "
        reasoning += f"following a {timeframe} {strategy.lower()} at ${signal['entry_price']:.2f}. "

        # Add technical context
        if rvol > 1.5:
            reasoning += f"RVOL at {rvol:.2f} confirms institutional participation. "
        else:
            reasoning += f"Volume is {rvol:.2f}x average. "

        if direction == "long":
            if ema8 > ema21:
                reasoning += "EMA8 > EMA21 confirms bullish trend. "
            if rsi > 55:
                reasoning += f"RSI at {rsi:.0f} shows positive momentum. "
        else:
            if ema8 < ema21:
                reasoning += "EMA8 < EMA21 confirms bearish trend. "
            if rsi < 45:
                reasoning += f"RSI at {rsi:.0f} shows negative momentum. "

        # Add targets
        risk = abs(signal['entry_price'] - signal['stop_loss'])
        reward = abs(signal['target_1'] - signal['entry_price'])
        rr = reward / risk if risk > 0 else 0

        reasoning += f"Primary target: ${signal['target_1']:.2f} ({rr:.1f}R). "
        reasoning += f"Invalidated if price {'closes below' if direction == 'long' else 'closes above'} ${signal['stop_loss']:.2f}."

        return reasoning

    @staticmethod
    def _to_native(val):
        """Convert numpy scalars to Python native types for database storage."""
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            return float(val)
        if isinstance(val, dict):
            return {k: SignalEngine._to_native(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [SignalEngine._to_native(v) for v in val]
        return val

    def _create_signal_record(self, signal: Dict, queue_item: SignalQueue, db: Session) -> TradingSignal:
        """Create TradingSignal database record and send notifications"""
        cap_size = queue_item.cap_size or "large_cap"
        timeframe = queue_item.timeframe

        # Sanitize numpy types for PostgreSQL compatibility
        signal = self._to_native(signal)

        # Calculate R:R ratio
        risk = abs(signal['entry_price'] - signal['stop_loss'])
        reward = abs(signal['target_1'] - signal['entry_price'])
        rr_ratio = reward / risk if risk > 0 else 0

        ai_reasoning = self._generate_ai_reasoning(signal, cap_size, timeframe)

        trading_signal = TradingSignal(
            queue_id=queue_item.id,
            symbol=signal['symbol'],
            name=queue_item.name,
            timeframe=timeframe,
            strategy=signal['strategy'],
            direction=signal['direction'],
            confidence_score=signal.get('confidence', 50),
            entry_price=signal['entry_price'],
            entry_zone_low=signal['entry_price'] * 0.998,
            entry_zone_high=signal['entry_price'] * 1.002,
            stop_loss=signal['stop_loss'],
            target_1=signal['target_1'],
            target_2=signal.get('target_2'),
            risk_reward_ratio=round(rr_ratio, 2),
            ai_reasoning=ai_reasoning,
            stop_loss_logic=f"Stop placed at ${signal['stop_loss']:.2f} based on ATR buffer below entry",
            target_logic=f"TP1 at ${signal['target_1']:.2f} (1R), TP2 at ${signal.get('target_2', 0):.2f} (2R)",
            invalidation_conditions=[
                f"Price {'closes below' if signal['direction'] == 'buy' else 'closes above'} ${signal['stop_loss']:.2f}",
                f"Failed breakout - price returns inside range",
            ],
            technical_snapshot=signal.get('technical_snapshot'),
            institutional_data={
                "vwap": signal.get('vwap'),
                "orb_high": signal.get('orb_high'),
                "orb_low": signal.get('orb_low'),
                "range_high": signal.get('range_high'),
                "range_low": signal.get('range_low'),
                "sma20": signal.get('sma20'),
                "sma50": signal.get('sma50'),
                "sma200": signal.get('sma200'),
                "adx": signal.get('adx'),
                "bb_upper": signal.get('bb_upper'),
                "bb_mid": signal.get('bb_mid'),
                "bb_lower": signal.get('bb_lower'),
                "options_eligible": signal.get('options_eligible', False),
                "options_details": signal.get('options_details'),
            },
            source="signal_engine",
            status="active",
        )

        db.add(trading_signal)
        logger.info(f"🚨 Signal created: {signal['symbol']} {signal['direction']} {signal['strategy']} ({signal.get('confidence', 50)}%)")

        # --- Notification bridge ---
        self._send_signal_notifications(trading_signal, signal, db)

        return trading_signal

    def _send_signal_notifications(self, trading_signal: TradingSignal, signal: Dict, db: Session):
        """
        Send notifications when a trading signal fires.
        Creates an AlertNotification record (visible in Alerts tab) and sends Telegram.
        """
        direction_emoji = "🟢" if signal['direction'] == 'buy' else "🔴"
        strategy_label = signal['strategy'].replace("_", " ").title()
        confidence = signal.get('confidence', 50)

        message = (
            f"{direction_emoji} {signal['direction'].upper()} Signal: {signal['symbol']} "
            f"| {strategy_label} | Entry ${signal['entry_price']:.2f} "
            f"| Stop ${signal['stop_loss']:.2f} | Target ${signal['target_1']:.2f} "
            f"| R:R {trading_signal.risk_reward_ratio:.1f} | Confidence {confidence}%"
        )

        # 1. Create AlertNotification for in-app visibility in Alerts tab
        notification = None
        try:
            notification = AlertNotification(
                alert_id=0,  # 0 = auto-generated from signal engine
                alert_name=f"Signal: {signal['symbol']} {signal['direction'].upper()}",
                symbol=signal['symbol'],
                alert_type=f"signal_{signal['strategy']}",
                triggered_value=signal['entry_price'],
                threshold_value=confidence,
                message=message,
                channels_sent=["app"],
            )
            db.add(notification)
            logger.info(f"📋 AlertNotification created for signal: {signal['symbol']}")
        except Exception as e:
            logger.error(f"Error creating AlertNotification for signal: {e}")

        # 2. Send Telegram notification
        try:
            telegram_sent = self._send_telegram_for_signal(signal, trading_signal)
            if telegram_sent:
                trading_signal.notification_sent_telegram = True
                if notification:
                    notification.channels_sent = ["app", "telegram"]
                logger.info(f"📱 Telegram sent for signal: {signal['symbol']}")
        except Exception as e:
            logger.error(f"Error sending Telegram for signal: {e}")

    def _send_telegram_for_signal(self, signal: Dict, trading_signal: TradingSignal) -> bool:
        """Send a Telegram notification for a trading signal."""
        try:
            from app.config import get_settings
            from app.services.telegram_bot import get_telegram_bot

            settings = get_settings()
            allowed_users = settings.TELEGRAM_ALLOWED_USERS
            if not allowed_users:
                return False

            chat_ids = [uid.strip() for uid in allowed_users.split(",") if uid.strip()]
            if not chat_ids:
                return False

            telegram_bot = get_telegram_bot()
            if not telegram_bot.is_running():
                logger.debug("Telegram bot not running, skipping signal notification")
                return False

            direction_emoji = "🟢" if signal['direction'] == 'buy' else "🔴"
            strategy_label = signal['strategy'].replace("_", " ").title()
            confidence = signal.get('confidence', 50)

            formatted_message = (
                f"*{direction_emoji} TRADING SIGNAL*\n\n"
                f"*{signal['symbol']}* — {signal['direction'].upper()}\n"
                f"Strategy: {strategy_label}\n"
                f"Confidence: {confidence}%\n\n"
                f"Entry: ${signal['entry_price']:.2f}\n"
                f"Stop Loss: ${signal['stop_loss']:.2f}\n"
                f"Target 1: ${signal['target_1']:.2f}\n"
                f"R:R: {trading_signal.risk_reward_ratio:.1f}\n\n"
                f"_{trading_signal.ai_reasoning}_"
            )

            sent_count = 0
            for chat_id in chat_ids:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            telegram_bot.send_message(chat_id, formatted_message)
                        )
                        sent_count += 1
                    else:
                        result = loop.run_until_complete(
                            telegram_bot.send_message(chat_id, formatted_message)
                        )
                        if result:
                            sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send signal Telegram to {chat_id}: {e}")

            return sent_count > 0

        except Exception as e:
            logger.error(f"Error in _send_telegram_for_signal: {e}")
            return False

    def process_all_queue_items(self, db: Session) -> List[TradingSignal]:
        """
        Process all active queue items and return generated signals.
        Called by scheduler job. Applies per-item cadence gating.
        """
        signals = []

        try:
            # Get all active queue items
            active_items = db.query(SignalQueue).filter(SignalQueue.status == "active").all()

            if not active_items:
                return signals

            # Per-item cadence gating — skip items that aren't due yet
            now = datetime.now(timezone.utc)
            items_due = [i for i in active_items if self._is_item_due(i, now)]
            cadence_skipped = len(active_items) - len(items_due)

            if not items_due:
                logger.debug(
                    f"📡 Signal engine: {len(active_items)} items, all cadence-skipped"
                )
                return signals

            # Cycle-level stats for diagnostic logging
            cycle_stats = {
                'alpaca': 0, 'tastytrade': 0, 'fmp': 0, 'catalyst': 0,
                'structural_fail': 0, 'heavy_atr_penalty': 0, 'heavy_rvol_penalty': 0,
                'tod_rvol_available': 0, 'same_bar_skip': 0,
                'equity_eligible': 0, 'options_eligible': 0,
                'rejected_low_conf': 0,
            }

            for item in items_due:
                signal = self.process_queue_item(item, db, cycle_stats)
                if signal:
                    signals.append(signal)

            # Count items that actually ran (not same-bar skipped)
            evaluated = len(items_due) - cycle_stats.get('same_bar_skip', 0)
            tod_avail = cycle_stats.get('tod_rvol_available', 0)
            tod_pct = f"{tod_avail}/{evaluated} ({tod_avail*100//max(evaluated,1)}%)" if evaluated > 0 else "0/0"

            logger.info(
                f"📡 Signal engine cycle: {len(active_items)} items | due: {len(items_due)} | "
                f"cadence_skip: {cadence_skipped} | same_bar_skip: {cycle_stats.get('same_bar_skip', 0)} | "
                f"structural_fail: {cycle_stats.get('structural_fail', 0)} | "
                f"tod_rvol_avail: {tod_pct} | "
                f"heavy_atr_penalty: {cycle_stats.get('heavy_atr_penalty', 0)} | "
                f"heavy_rvol_penalty: {cycle_stats.get('heavy_rvol_penalty', 0)} | "
                f"equity_eligible: {cycle_stats.get('equity_eligible', 0)} | "
                f"options_eligible: {cycle_stats.get('options_eligible', 0)} | "
                f"signals: {len(signals)} | "
                f"rejected_low_conf: {cycle_stats.get('rejected_low_conf', 0)} | "
                f"api_calls: alpaca={cycle_stats.get('alpaca', 0)} tastytrade={cycle_stats.get('tastytrade', 0)} "
                f"fmp={cycle_stats.get('fmp', 0)} catalyst={cycle_stats.get('catalyst', 0)}"
            )

            return signals

        except Exception as e:
            logger.error(f"Error processing queue: {e}")
            return signals


# Singleton instance
signal_engine = SignalEngine()
