"""
Position Monitor — runs every minute during market hours.

Checks all OPEN ExecutedTrades for exit conditions:
  1. Stop loss hit
  2. Take profit hit
  3. Trailing stop triggered (+ high-water-mark update)
  4. EOD forced close
  5. LEAPS roll alert (DTE warning for options — alert only, no auto-exit)

Also performs:
  - Pending entry fill reconciliation
  - Health check (bot_state vs Alpaca positions consistency)
"""
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.models.bot_config import BotConfiguration
from app.models.bot_state import BotState, BotStatus
from app.models.executed_trade import ExecutedTrade, ExitReason, TradeStatus


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ExitSignal:
    """Represents a detected exit condition for a single trade."""
    trade_id: int
    symbol: str
    reason: ExitReason
    current_price: float
    trigger_price: float


@dataclass
class MonitorResult:
    """Summary of one full monitoring cycle."""
    positions_checked: int = 0
    exit_signals: List[ExitSignal] = None
    pending_fills_updated: int = 0
    bracket_exits_reconciled: int = 0
    roll_alerts_sent: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.exit_signals is None:
            self.exit_signals = []
        if self.errors is None:
            self.errors = []


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PositionMonitor:
    """
    Monitors all open bot-managed positions for exit conditions.
    Called every ~1 minute by the scheduler during market hours.
    """

    # Close positions this many minutes before market close (for EOD close)
    EOD_CLOSE_MINUTES_BEFORE = 5

    def __init__(self, db: Session, trading_service, data_service):
        """
        Args:
            db: SQLAlchemy session
            trading_service: AlpacaTradingService (for get_position, get_clock, get_order)
            data_service: AlpacaService (for get_current_price)
        """
        self.db = db
        self.trading = trading_service
        self.data = data_service

    # =====================================================================
    # Main Entry Point
    # =====================================================================

    def check_all_positions(
        self, bot_config: BotConfiguration, bot_state: Optional[BotState] = None,
    ) -> MonitorResult:
        """
        Run a full monitoring cycle over all open ExecutedTrades.

        Returns:
            MonitorResult with exit signals that the Auto-Trader should execute.
        """
        result = MonitorResult()

        # 1. Reconcile pending entry orders (fill updates)
        result.pending_fills_updated = self._reconcile_pending_entries(bot_state)

        # 1b. Reconcile bracket exits (Alpaca-managed SL/TP fills we don't know about)
        result.bracket_exits_reconciled = self._reconcile_bracket_exits(bot_state)
        if result.bracket_exits_reconciled:
            logger.info(f"PositionMonitor: {result.bracket_exits_reconciled} bracket exit(s) reconciled")

        # 2. Check all open trades for exit conditions
        open_trades = (
            self.db.query(ExecutedTrade)
            .filter(ExecutedTrade.status == TradeStatus.OPEN.value)
            .all()
        )
        result.positions_checked = len(open_trades)

        if not open_trades:
            return result

        # Pre-fetch market clock for EOD check
        is_near_close = False
        if bot_config.close_positions_eod:
            eod_minutes = getattr(bot_config, "eod_close_minutes_before", self.EOD_CLOSE_MINUTES_BEFORE) or self.EOD_CLOSE_MINUTES_BEFORE
            is_near_close = self._is_near_market_close(eod_minutes)

        for trade in open_trades:
            try:
                signal = self._check_single_position(trade, bot_config, is_near_close)
                if signal:
                    result.exit_signals.append(signal)

                # LEAPS roll alert (non-blocking, sent at most once per trade)
                if (
                    trade.asset_type == "option"
                    and trade.option_expiry
                    and bot_config.leaps_roll_alert_dte
                ):
                    dte = (trade.option_expiry - date.today()).days
                    already_sent = (trade.notes or "").find("[ROLL_ALERT_SENT]") >= 0
                    if 0 < dte <= bot_config.leaps_roll_alert_dte and not already_sent:
                        self._send_roll_alert(trade, dte)
                        # Tag the trade so we don't send the alert again
                        trade.notes = (trade.notes or "") + " [ROLL_ALERT_SENT]"
                        self.db.flush()
                        result.roll_alerts_sent += 1

            except Exception as e:
                err_msg = f"Error checking {trade.symbol} (trade #{trade.id}): {e}"
                logger.error(f"PositionMonitor: {err_msg}")
                result.errors.append(err_msg)

        if result.exit_signals:
            logger.info(
                f"PositionMonitor: {len(result.exit_signals)} exit signal(s) from "
                f"{result.positions_checked} positions"
            )

        return result

    # =====================================================================
    # Single Position Check
    # =====================================================================

    def _check_single_position(
        self,
        trade: ExecutedTrade,
        config: BotConfiguration,
        is_near_close: bool,
    ) -> Optional[ExitSignal]:
        """Check one open trade for exit conditions. Returns ExitSignal or None."""
        current_price = self._get_current_price(trade)
        if current_price is None or current_price <= 0:
            logger.warning(
                f"PositionMonitor: no price for {trade.symbol} "
                f"({'option' if trade.asset_type == 'option' else 'stock'}), skipping"
            )
            return None

        is_long = trade.direction == "buy"

        # 1. Stop loss
        if trade.stop_loss_price and trade.stop_loss_price > 0:
            if is_long and current_price <= trade.stop_loss_price:
                return ExitSignal(
                    trade.id, trade.symbol,
                    ExitReason.STOP_LOSS, current_price, trade.stop_loss_price,
                )
            if not is_long and current_price >= trade.stop_loss_price:
                return ExitSignal(
                    trade.id, trade.symbol,
                    ExitReason.STOP_LOSS, current_price, trade.stop_loss_price,
                )

        # 2. Take profit
        if trade.take_profit_price and trade.take_profit_price > 0:
            if is_long and current_price >= trade.take_profit_price:
                return ExitSignal(
                    trade.id, trade.symbol,
                    ExitReason.TAKE_PROFIT, current_price, trade.take_profit_price,
                )
            if not is_long and current_price <= trade.take_profit_price:
                return ExitSignal(
                    trade.id, trade.symbol,
                    ExitReason.TAKE_PROFIT, current_price, trade.take_profit_price,
                )

        # 3. Trailing stop
        if trade.trailing_stop_pct and trade.trailing_stop_pct > 0:
            # Need a valid anchor (high water or entry price) to calculate trailing stop
            if not trade.trailing_stop_high_water and not trade.entry_price:
                logger.warning(
                    f"PositionMonitor: skipping trailing stop for {trade.symbol} — "
                    f"no entry_price or high_water (trade #{trade.id})"
                )
                # Initialize high water from current price so future cycles work
                trade.trailing_stop_high_water = current_price
                self.db.flush()
            high_water = trade.trailing_stop_high_water or trade.entry_price or current_price

            # Update high water mark if price moved in our favor
            if is_long and current_price > high_water:
                trade.trailing_stop_high_water = current_price
                high_water = current_price
                self.db.flush()
            elif not is_long and current_price < high_water:
                trade.trailing_stop_high_water = current_price
                high_water = current_price
                self.db.flush()

            # Check trailing stop trigger
            if is_long:
                trail_price = high_water * (1 - trade.trailing_stop_pct / 100)
                if current_price <= trail_price:
                    return ExitSignal(
                        trade.id, trade.symbol,
                        ExitReason.TRAILING_STOP, current_price, round(trail_price, 2),
                    )
            else:
                trail_price = high_water * (1 + trade.trailing_stop_pct / 100)
                if current_price >= trail_price:
                    return ExitSignal(
                        trade.id, trade.symbol,
                        ExitReason.TRAILING_STOP, current_price, round(trail_price, 2),
                    )

        # 4. EOD forced close (skip for option positions — LEAPS should be held)
        if is_near_close and trade.asset_type != "option":
            return ExitSignal(
                trade.id, trade.symbol,
                ExitReason.TIME_EXIT, current_price, 0,
            )

        # 5. Option expiry approaching (< 1 day) — auto-exit to avoid assignment
        if trade.asset_type == "option" and trade.option_expiry:
            dte = (trade.option_expiry - date.today()).days
            if dte <= 0:
                return ExitSignal(
                    trade.id, trade.symbol,
                    ExitReason.EXPIRED, current_price, 0,
                )

        return None

    # =====================================================================
    # Pending Entry Reconciliation
    # =====================================================================

    def _reconcile_pending_entries(self, bot_state: Optional[BotState] = None) -> int:
        """
        Check pending_entry trades for order fill updates.
        Transitions them to OPEN when filled, or CANCELLED if rejected.
        Decrements bot_state counters when entries are cancelled/expired/rejected.
        """
        pending = (
            self.db.query(ExecutedTrade)
            .filter(ExecutedTrade.status == TradeStatus.PENDING_ENTRY.value)
            .all()
        )

        updated = 0
        for trade in pending:
            if not trade.entry_order_id:
                continue

            try:
                order_info = self.trading.get_order(trade.entry_order_id)
                if not order_info:
                    continue

                status = order_info.get("status", "")

                if status == "filled":
                    trade.entry_price = order_info.get("filled_avg_price") or trade.entry_price
                    trade.entry_filled_at = datetime.now(timezone.utc)
                    trade.status = TradeStatus.OPEN.value
                    if order_info.get("filled_qty"):
                        trade.quantity = float(order_info["filled_qty"])
                    # Set trailing stop high water mark
                    if trade.trailing_stop_pct and trade.entry_price:
                        trade.trailing_stop_high_water = trade.entry_price
                    updated += 1
                    logger.info(
                        f"PositionMonitor: pending entry filled — "
                        f"{trade.symbol} @ ${trade.entry_price} (trade #{trade.id})"
                    )

                elif status in ("canceled", "cancelled", "expired", "rejected"):
                    trade.status = TradeStatus.CANCELLED.value
                    trade.notes = (trade.notes or "") + f"\nEntry order {status}"
                    updated += 1

                    # Decrement bot_state counters — this position never opened
                    if bot_state:
                        bot_state.open_positions_count = max(0, bot_state.open_positions_count - 1)
                        if trade.asset_type == "option":
                            bot_state.open_option_positions = max(0, bot_state.open_option_positions - 1)
                        else:
                            bot_state.open_stock_positions = max(0, bot_state.open_stock_positions - 1)

                    logger.info(
                        f"PositionMonitor: pending entry {status} — "
                        f"{trade.symbol} (trade #{trade.id})"
                    )

            except Exception as e:
                logger.error(
                    f"PositionMonitor: error reconciling trade #{trade.id}: {e}"
                )

        if updated:
            self.db.commit()

        return updated

    # =====================================================================
    # Bracket Exit Reconciliation
    # =====================================================================

    def _reconcile_bracket_exits(self, bot_state: Optional[BotState] = None) -> int:
        """
        Check open trades that have bracket orders (TP/SL managed by Alpaca).
        If either the TP or SL child order has been filled, mark the trade as CLOSED
        and record the P&L. This catches exits that Alpaca executed automatically.
        """
        bracket_trades = (
            self.db.query(ExecutedTrade)
            .filter(
                ExecutedTrade.status == TradeStatus.OPEN.value,
                (ExecutedTrade.tp_order_id.isnot(None)) | (ExecutedTrade.sl_order_id.isnot(None)),
            )
            .all()
        )

        reconciled = 0
        for trade in bracket_trades:
            try:
                # Check take-profit order
                if trade.tp_order_id:
                    tp_info = self.trading.get_order(trade.tp_order_id)
                    if tp_info and tp_info.get("status") == "filled":
                        self._close_bracket_trade(
                            trade, tp_info, ExitReason.TAKE_PROFIT, bot_state,
                        )
                        reconciled += 1
                        continue

                # Check stop-loss order
                if trade.sl_order_id:
                    sl_info = self.trading.get_order(trade.sl_order_id)
                    if sl_info and sl_info.get("status") == "filled":
                        self._close_bracket_trade(
                            trade, sl_info, ExitReason.STOP_LOSS, bot_state,
                        )
                        reconciled += 1
                        continue

            except Exception as e:
                logger.error(
                    f"PositionMonitor: error reconciling bracket for trade #{trade.id}: {e}"
                )

        if reconciled:
            self.db.commit()

        return reconciled

    def _close_bracket_trade(
        self,
        trade: ExecutedTrade,
        filled_order: dict,
        exit_reason: ExitReason,
        bot_state: Optional[BotState],
    ):
        """Mark a bracket-managed trade as closed with P&L from the filled child order."""
        fill_price = filled_order.get("filled_avg_price")
        if fill_price:
            fill_price = float(fill_price)
        else:
            fill_price = trade.take_profit_price if exit_reason == ExitReason.TAKE_PROFIT else trade.stop_loss_price

        trade.exit_price = fill_price
        trade.exit_reason = exit_reason.value
        trade.exit_filled_at = datetime.now(timezone.utc)
        trade.status = TradeStatus.CLOSED.value
        trade.exit_order_id = filled_order.get("id", "")

        # Calculate P&L
        if trade.entry_price and fill_price:
            if trade.direction == "buy":
                pl = (fill_price - trade.entry_price) * trade.quantity
            else:
                pl = (trade.entry_price - fill_price) * trade.quantity

            if trade.asset_type == "option":
                pl *= 100

            trade.realized_pl = round(pl, 2)
            if trade.entry_price > 0:
                multiplier = 100 if trade.asset_type == "option" else 1
                cost_basis = trade.entry_price * trade.quantity * multiplier
                trade.realized_pl_pct = round((pl / cost_basis) * 100, 2) if cost_basis else 0

        # Calculate hold duration
        if trade.entry_filled_at:
            entry_time = trade.entry_filled_at
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - entry_time
            trade.hold_duration_minutes = int(delta.total_seconds() / 60)

        # Update bot state
        if bot_state:
            bot_state.open_positions_count = max(0, bot_state.open_positions_count - 1)
            if trade.asset_type == "option":
                bot_state.open_option_positions = max(0, bot_state.open_option_positions - 1)
            else:
                bot_state.open_stock_positions = max(0, bot_state.open_stock_positions - 1)

            if trade.realized_pl is not None:
                bot_state.daily_pl = (bot_state.daily_pl or 0) + trade.realized_pl
                if trade.realized_pl > 0:
                    bot_state.daily_wins = (bot_state.daily_wins or 0) + 1
                elif trade.realized_pl < 0:
                    bot_state.daily_losses = (bot_state.daily_losses or 0) + 1

        logger.info(
            f"PositionMonitor: bracket exit reconciled — {trade.symbol} "
            f"{exit_reason.value} @ ${fill_price} pl=${trade.realized_pl or 0:.2f} "
            f"(trade #{trade.id})"
        )

    # =====================================================================
    # Health Check
    # =====================================================================

    def health_check(self, bot_state: BotState) -> bool:
        """
        Verify bot_state position counts match reality.
        Returns True if consistent, False if mismatch detected.
        """
        # Count open trades in DB
        db_open = (
            self.db.query(ExecutedTrade)
            .filter(ExecutedTrade.status == TradeStatus.OPEN.value)
            .count()
        )
        db_stocks = (
            self.db.query(ExecutedTrade)
            .filter(
                ExecutedTrade.status == TradeStatus.OPEN.value,
                ExecutedTrade.asset_type == "stock",
            )
            .count()
        )
        db_options = (
            self.db.query(ExecutedTrade)
            .filter(
                ExecutedTrade.status == TradeStatus.OPEN.value,
                ExecutedTrade.asset_type == "option",
            )
            .count()
        )

        # Get actual Alpaca positions
        alpaca_positions = self.trading.get_all_positions()
        alpaca_count = len(alpaca_positions)

        # Compare
        consistent = True
        issues = []

        if bot_state.open_positions_count != db_open:
            issues.append(
                f"bot_state.open_positions_count={bot_state.open_positions_count} "
                f"but DB has {db_open} open trades"
            )
            bot_state.open_positions_count = db_open
            consistent = False

        if bot_state.open_stock_positions != db_stocks:
            bot_state.open_stock_positions = db_stocks
            consistent = False

        if bot_state.open_option_positions != db_options:
            bot_state.open_option_positions = db_options
            consistent = False

        # Warn if Alpaca position count doesn't match DB
        # (There may be manually opened positions, so this is informational)
        if alpaca_count != db_open:
            issues.append(
                f"Alpaca has {alpaca_count} positions but DB has {db_open} open trades "
                f"(may include manual positions)"
            )

        if issues:
            msg = "; ".join(issues)
            logger.warning(f"PositionMonitor health check: {msg}")
            bot_state.last_error = f"Health check mismatch: {msg}"
            bot_state.last_error_at = datetime.now(timezone.utc)
        else:
            bot_state.consecutive_errors = 0

        bot_state.last_health_check = datetime.now(timezone.utc)
        self.db.commit()

        return consistent

    # =====================================================================
    # Private Helpers
    # =====================================================================

    def _get_current_price(self, trade: ExecutedTrade) -> Optional[float]:
        """Get current market price for a trade's asset."""
        try:
            if trade.asset_type == "option" and trade.option_symbol:
                # For options, try to get live position data from Alpaca
                position = self.trading.get_position(trade.option_symbol)
                if position and position.get("current_price"):
                    return float(position["current_price"])
                # Don't fall back to stock price for options — would trigger false exits
                return None
            else:
                # For stocks, use the data service snapshot
                price = self.data.get_current_price(trade.symbol)
                if price:
                    return float(price)
                # Fallback: try Alpaca position data
                position = self.trading.get_position(trade.symbol)
                if position:
                    return float(position.get("current_price", 0))
                return None
        except Exception as e:
            logger.error(f"PositionMonitor: error getting price for {trade.symbol}: {e}")
            return None

    def _is_near_market_close(self, minutes_before: int = None) -> bool:
        """Check if we're within `minutes_before` minutes of market close."""
        if minutes_before is None:
            minutes_before = self.EOD_CLOSE_MINUTES_BEFORE
        try:
            clock = self.trading.get_clock()
            if not clock or not clock.get("is_open"):
                return False

            next_close_str = clock.get("next_close")
            if not next_close_str:
                return False

            # Parse ISO timestamp
            if isinstance(next_close_str, str):
                # Strip timezone info for simple comparison
                next_close = datetime.fromisoformat(next_close_str.replace("Z", "+00:00"))
                now = datetime.now(next_close.tzinfo)
            else:
                next_close = next_close_str
                now = datetime.now(timezone.utc)

            minutes_to_close = (next_close - now).total_seconds() / 60
            return 0 < minutes_to_close <= minutes_before

        except Exception as e:
            logger.error(f"PositionMonitor: error checking market close: {e}")
            return False

    def _send_roll_alert(self, trade: ExecutedTrade, dte: int):
        """Send LEAPS roll alert via Telegram (non-blocking, best-effort)."""
        try:
            from app.services.telegram_bot import get_telegram_bot
            import asyncio

            bot = get_telegram_bot()
            if not bot or not bot._running:
                return

            message = (
                f"⚠️ LEAPS Roll Alert\n"
                f"Symbol: {trade.symbol}\n"
                f"Option: {trade.option_symbol}\n"
                f"DTE: {dte} days\n"
                f"Strike: ${trade.option_strike}\n"
                f"Consider rolling to a later expiry."
            )

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return

            for uid in bot.allowed_users:
                asyncio.run_coroutine_threadsafe(
                    bot.send_message(str(uid), message), loop
                )
            logger.info(f"PositionMonitor: roll alert sent for {trade.symbol} (DTE={dte})")
        except Exception as e:
            logger.debug(f"PositionMonitor: could not send roll alert: {e}")
