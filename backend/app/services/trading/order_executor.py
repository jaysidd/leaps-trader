"""
Order Executor — bridge between position sizing and Alpaca order placement.

Takes a sized position (SizeResult) and places the appropriate order type:
  - Stocks (whole shares): bracket order with built-in TP + SL
  - Stocks (fractional):   notional order, SL/TP managed by Position Monitor
  - Options:               limit order at mid-price, SL/TP managed by Position Monitor

Also handles exit orders and kill-switch operations.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.models.bot_config import BotConfiguration
from app.models.bot_state import BotState
from app.models.executed_trade import ExecutedTrade, TradeStatus, ExitReason
from app.models.trading_signal import TradingSignal
from app.services.trading.position_sizer import SizeResult


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class OrderResult:
    """Outcome of an order execution attempt."""
    success: bool = False
    order_id: str = ""
    tp_order_id: str = ""          # Bracket take-profit child order
    sl_order_id: str = ""          # Bracket stop-loss child order
    fill_price: Optional[float] = None
    fill_qty: Optional[float] = None
    error: str = ""
    needs_monitor: bool = False    # True if Position Monitor must handle SL/TP


@dataclass
class ExitResult:
    """Outcome of an exit order."""
    success: bool = False
    order_id: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class OrderExecutor:
    """
    Places entry and exit orders via AlpacaTradingService.
    Creates ExecutedTrade records and updates BotState counters.
    """

    def __init__(self, trading_service, db: Session):
        """
        Args:
            trading_service: AlpacaTradingService instance
            db: SQLAlchemy session for persisting ExecutedTrade records
        """
        self.trading = trading_service
        self.db = db

    # =====================================================================
    # Entry Orders
    # =====================================================================

    def execute_entry(
        self,
        signal: TradingSignal,
        size_result: SizeResult,
        bot_config: BotConfiguration,
        bot_state: BotState,
        current_price: float,
        option_symbol: Optional[str] = None,
        option_premium: Optional[float] = None,
        option_type: Optional[str] = None,
        option_strike: Optional[float] = None,
        option_expiry=None,
    ) -> tuple[ExecutedTrade, OrderResult]:
        """
        Place an entry order and create the ExecutedTrade record.

        Returns:
            (ExecutedTrade, OrderResult) — trade record + order outcome.
        """
        # Calculate exit targets
        entry_price = signal.entry_price or current_price
        tp_price = self._calc_take_profit(signal, entry_price, bot_config)
        sl_price = self._calc_stop_loss(signal, entry_price, bot_config)

        # Create the ExecutedTrade record (status = PENDING_ENTRY)
        trade = ExecutedTrade(
            signal_id=signal.id,
            symbol=signal.symbol,
            asset_type=size_result.asset_type,
            direction=signal.direction,
            quantity=size_result.quantity,
            notional=size_result.notional,
            is_fractional=size_result.is_fractional,
            take_profit_price=tp_price,
            stop_loss_price=sl_price,
            trailing_stop_pct=(
                bot_config.trailing_stop_pct if bot_config.trailing_stop_enabled else None
            ),
            execution_mode=bot_config.execution_mode,
            status=TradeStatus.PENDING_ENTRY.value,
        )

        # Option-specific fields
        if size_result.asset_type == "option":
            trade.option_symbol = option_symbol
            trade.option_type = option_type
            trade.option_strike = option_strike
            trade.option_expiry = option_expiry

        self.db.add(trade)
        self.db.flush()  # Get the trade.id before placing order

        logger.info(
            f"OrderExecutor: entry for {signal.symbol} "
            f"({size_result.asset_type}, qty={size_result.quantity}, "
            f"notional=${size_result.notional:.2f})"
        )

        # Place the order
        if size_result.asset_type == "option":
            order_result = self._place_option_entry(
                trade, option_symbol, size_result, option_premium, bot_config,
            )
        elif size_result.is_notional_order:
            order_result = self._place_notional_entry(
                trade, size_result, signal.direction,
            )
        else:
            order_result = self._place_bracket_entry(
                trade, size_result, signal.direction,
                tp_price, sl_price, bot_config,
            )

        # Update the trade record based on order result
        if order_result.success:
            trade.entry_order_id = order_result.order_id
            trade.tp_order_id = order_result.tp_order_id or None
            trade.sl_order_id = order_result.sl_order_id or None

            # If we got a fill price already (market orders fill instantly on paper)
            if order_result.fill_price:
                trade.entry_price = order_result.fill_price
                trade.entry_filled_at = datetime.now(timezone.utc)
                trade.status = TradeStatus.OPEN.value
                # Update high water mark for trailing stop
                if trade.trailing_stop_pct:
                    trade.trailing_stop_high_water = order_result.fill_price
            else:
                # Order accepted but not filled yet — keep PENDING_ENTRY
                trade.entry_price = entry_price  # Expected price
                trade.status = TradeStatus.PENDING_ENTRY.value

            # Update bot state counters
            bot_state.daily_trades_count += 1
            bot_state.open_positions_count += 1
            if size_result.asset_type == "option":
                bot_state.open_option_positions += 1
            else:
                bot_state.open_stock_positions += 1

            # Mark the signal as executed
            signal.trade_executed = True
            signal.trade_execution_id = order_result.order_id
            signal.status = "executed"

            logger.info(
                f"OrderExecutor: ✅ entry placed for {signal.symbol} "
                f"order_id={order_result.order_id} "
                f"{'(needs monitor)' if order_result.needs_monitor else '(bracket SL/TP)'}"
            )
        else:
            trade.status = TradeStatus.ERROR.value
            trade.notes = f"Entry order failed: {order_result.error}"

            # Track error in bot state
            bot_state.last_error = order_result.error
            bot_state.last_error_at = datetime.now(timezone.utc)
            bot_state.consecutive_errors += 1

            logger.error(
                f"OrderExecutor: ❌ entry failed for {signal.symbol}: {order_result.error}"
            )

        self.db.commit()
        return trade, order_result

    # =====================================================================
    # Exit Orders
    # =====================================================================

    def execute_exit(
        self,
        trade: ExecutedTrade,
        reason: ExitReason,
        current_price: Optional[float] = None,
        bot_state: Optional[BotState] = None,
    ) -> ExitResult:
        """
        Exit an open position.

        Args:
            trade: The ExecutedTrade to close
            reason: Why we're exiting
            current_price: Current price (for option mid-price sell)
            bot_state: BotState to update counters
        """
        logger.info(
            f"OrderExecutor: exiting {trade.symbol} "
            f"(trade #{trade.id}, reason={reason.value})"
        )

        trade.status = TradeStatus.PENDING_EXIT.value
        self.db.flush()

        if trade.asset_type == "option":
            result = self._exit_option(trade, current_price)
        else:
            result = self._exit_stock(trade)

        if result.success:
            trade.exit_order_id = result.order_id
            trade.exit_reason = reason.value

            # Update P&L if we have fill info
            # (Real P&L calculation happens when fill is confirmed in Position Monitor)
            if current_price and trade.entry_price:
                if trade.direction == "buy":
                    pl = (current_price - trade.entry_price) * trade.quantity
                else:
                    pl = (trade.entry_price - current_price) * trade.quantity

                if trade.asset_type == "option":
                    pl *= 100  # Options are per-share, multiply by 100

                trade.realized_pl = round(pl, 2)
                if trade.entry_price > 0:
                    multiplier = 100 if trade.asset_type == "option" else 1
                    cost_basis = trade.entry_price * trade.quantity * multiplier
                    trade.realized_pl_pct = round((pl / cost_basis) * 100, 2)

                trade.exit_price = current_price
                trade.exit_filled_at = datetime.now(timezone.utc)

                # Calculate hold duration
                if trade.entry_filled_at:
                    delta = datetime.now(timezone.utc) - trade.entry_filled_at.replace(tzinfo=None)
                    trade.hold_duration_minutes = int(delta.total_seconds() / 60)

            trade.status = TradeStatus.CLOSED.value

            # Update bot state
            if bot_state:
                bot_state.open_positions_count = max(0, bot_state.open_positions_count - 1)
                if trade.asset_type == "option":
                    bot_state.open_option_positions = max(0, bot_state.open_option_positions - 1)
                else:
                    bot_state.open_stock_positions = max(0, bot_state.open_stock_positions - 1)

                # Update daily P&L
                if trade.realized_pl is not None:
                    bot_state.daily_pl += trade.realized_pl
                    if trade.realized_pl > 0:
                        bot_state.daily_wins += 1
                    elif trade.realized_pl < 0:
                        bot_state.daily_losses += 1

            logger.info(
                f"OrderExecutor: ✅ exit for {trade.symbol} "
                f"reason={reason.value} pl=${trade.realized_pl or 0:.2f}"
            )
        else:
            trade.status = TradeStatus.OPEN.value  # Revert to OPEN
            trade.notes = (trade.notes or "") + f"\nExit failed: {result.error}"
            logger.error(
                f"OrderExecutor: ❌ exit failed for {trade.symbol}: {result.error}"
            )

        self.db.commit()
        return result

    # =====================================================================
    # Kill Switch
    # =====================================================================

    def kill_switch(self, bot_state: BotState) -> dict:
        """
        Emergency stop: cancel all orders + close all positions.
        Updates all open ExecutedTrades to CLOSED with kill_switch reason.
        """
        logger.warning("🚨 KILL SWITCH ACTIVATED")

        results = {
            "cancelled_orders": 0,
            "closed_positions": 0,
            "errors": [],
        }

        # 1. Cancel all open orders
        cancel_result = self.trading.cancel_all_orders()
        if cancel_result.get("error"):
            results["errors"].append(f"Cancel orders: {cancel_result['error']}")
        else:
            results["cancelled_orders"] = cancel_result.get("count", 0)

        # 2. Close all positions
        close_result = self.trading.close_all_positions()
        if close_result.get("error"):
            results["errors"].append(f"Close positions: {close_result['error']}")
        else:
            results["closed_positions"] = close_result.get("count", 0)

        # 3. Mark all open ExecutedTrades as closed
        open_trades = (
            self.db.query(ExecutedTrade)
            .filter(ExecutedTrade.status.in_([
                TradeStatus.OPEN.value,
                TradeStatus.PENDING_ENTRY.value,
                TradeStatus.PENDING_EXIT.value,
            ]))
            .all()
        )

        for trade in open_trades:
            trade.status = TradeStatus.CLOSED.value
            trade.exit_reason = ExitReason.KILL_SWITCH.value
            trade.exit_filled_at = datetime.now(timezone.utc)
            if trade.entry_filled_at:
                now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                entry_naive = trade.entry_filled_at.replace(tzinfo=None)
                delta = now_naive - entry_naive
                trade.hold_duration_minutes = int(delta.total_seconds() / 60)
            trade.notes = (trade.notes or "") + "\nKill switch activated"

            # Calculate P&L for trades with entry prices
            if trade.entry_price:
                try:
                    # Try to get current price from Alpaca position
                    current_price = None
                    symbol = trade.option_symbol if trade.asset_type == "option" and trade.option_symbol else trade.symbol
                    position = self.trading.get_position(symbol)
                    if position and position.get("current_price"):
                        current_price = float(position["current_price"])

                    if current_price and current_price > 0:
                        if trade.direction == "buy":
                            pl = (current_price - trade.entry_price) * trade.quantity
                        else:
                            pl = (trade.entry_price - current_price) * trade.quantity

                        if trade.asset_type == "option":
                            pl *= 100  # Options are per-share, multiply by 100

                        trade.exit_price = current_price
                        trade.realized_pl = round(pl, 2)
                        if trade.entry_price > 0:
                            multiplier = 100 if trade.asset_type == "option" else 1
                            cost_basis = trade.entry_price * trade.quantity * multiplier
                            trade.realized_pl_pct = round((pl / cost_basis) * 100, 2)

                        # Update bot_state daily P&L
                        bot_state.daily_pl = (bot_state.daily_pl or 0) + trade.realized_pl
                        if trade.realized_pl > 0:
                            bot_state.daily_wins = (bot_state.daily_wins or 0) + 1
                        elif trade.realized_pl < 0:
                            bot_state.daily_losses = (bot_state.daily_losses or 0) + 1
                except Exception as e:
                    logger.warning(f"Kill switch: could not calculate P&L for {trade.symbol}: {e}")

        results["trades_closed"] = len(open_trades)

        # 4. Update bot state
        bot_state.open_positions_count = 0
        bot_state.open_stock_positions = 0
        bot_state.open_option_positions = 0

        self.db.commit()

        logger.warning(
            f"🚨 Kill switch complete: cancelled={results['cancelled_orders']}, "
            f"closed={results['closed_positions']}, "
            f"trades_marked={results['trades_closed']}"
        )
        return results

    # =====================================================================
    # Private — Order Placement Helpers
    # =====================================================================

    def _place_bracket_entry(
        self,
        trade: ExecutedTrade,
        size: SizeResult,
        direction: str,
        tp_price: float,
        sl_price: float,
        config: BotConfiguration,
    ) -> OrderResult:
        """Place a bracket order for whole-share stock trades."""
        result = self.trading.place_bracket_order(
            symbol=trade.symbol,
            qty=int(size.quantity),
            side=direction,
            take_profit_price=tp_price,
            stop_loss_price=sl_price,
            time_in_force="gtc",
        )

        if result.get("error"):
            return OrderResult(success=False, error=result["error"])

        return OrderResult(
            success=True,
            order_id=result.get("order_id", ""),
            tp_order_id=result.get("tp_order_id", ""),
            sl_order_id=result.get("sl_order_id", ""),
            fill_price=result.get("filled_avg_price"),
            fill_qty=result.get("filled_qty"),
            needs_monitor=False,  # Bracket handles SL/TP
        )

    def _place_notional_entry(
        self,
        trade: ExecutedTrade,
        size: SizeResult,
        direction: str,
    ) -> OrderResult:
        """Place a notional (dollar amount) order for fractional stock trades."""
        result = self.trading.place_notional_order(
            symbol=trade.symbol,
            notional=size.notional,
            side=direction,
            time_in_force="day",  # Fractional shares require DAY
        )

        if result.get("error"):
            return OrderResult(success=False, error=result["error"])

        return OrderResult(
            success=True,
            order_id=result.get("order_id", ""),
            fill_price=result.get("filled_avg_price"),
            fill_qty=result.get("filled_qty"),
            needs_monitor=True,  # No bracket — Position Monitor handles SL/TP
        )

    def _place_option_entry(
        self,
        trade: ExecutedTrade,
        option_symbol: str,
        size: SizeResult,
        option_premium: Optional[float],
        config: BotConfiguration,
    ) -> OrderResult:
        """Place a limit order for option trades."""
        if not option_symbol:
            return OrderResult(success=False, error="No option symbol provided")

        if not option_premium or option_premium <= 0:
            return OrderResult(success=False, error="Invalid option premium for limit price")

        # Use mid-price as limit (option_premium is already mid or ask)
        limit_price = round(option_premium, 2)

        result = self.trading.place_option_order(
            option_symbol=option_symbol,
            qty=int(size.quantity),
            side="buy",
            limit_price=limit_price,
            time_in_force="day",  # Options must be DAY on Alpaca
        )

        if result.get("error"):
            return OrderResult(success=False, error=result["error"])

        return OrderResult(
            success=True,
            order_id=result.get("order_id", ""),
            fill_price=result.get("filled_avg_price"),
            fill_qty=result.get("filled_qty"),
            needs_monitor=True,  # Options always need Position Monitor for SL/TP
        )

    def _exit_stock(self, trade: ExecutedTrade) -> ExitResult:
        """Exit a stock position by closing through Alpaca."""
        # First cancel any existing bracket child orders
        if trade.tp_order_id:
            try:
                self.trading.cancel_order(trade.tp_order_id)
            except Exception:
                pass  # May already be filled/cancelled
        if trade.sl_order_id:
            try:
                self.trading.cancel_order(trade.sl_order_id)
            except Exception:
                pass

        result = self.trading.close_position(
            symbol=trade.symbol,
            qty=trade.quantity if not trade.is_fractional else None,
        )

        if result and result.get("error"):
            return ExitResult(success=False, error=result["error"])

        return ExitResult(
            success=True,
            order_id=result.get("order_id", "") if result else "",
        )

    def _exit_option(
        self, trade: ExecutedTrade, current_price: Optional[float],
    ) -> ExitResult:
        """Exit an option position with a sell limit order."""
        if not trade.option_symbol:
            return ExitResult(success=False, error="No option symbol on trade record")

        # Use current premium or a very low limit to ensure fill
        limit_price = current_price if current_price and current_price > 0 else 0.01

        result = self.trading.place_option_order(
            option_symbol=trade.option_symbol,
            qty=int(trade.quantity),
            side="sell",
            limit_price=round(limit_price, 2),
            time_in_force="day",
        )

        if result.get("error"):
            return ExitResult(success=False, error=result["error"])

        return ExitResult(
            success=True,
            order_id=result.get("order_id", ""),
        )

    # =====================================================================
    # Private — Price Calculation Helpers
    # =====================================================================

    @staticmethod
    def _calc_take_profit(
        signal: TradingSignal,
        entry_price: float,
        config: BotConfiguration,
    ) -> float:
        """Calculate take-profit price from signal targets or config default."""
        # Prefer signal's target_1
        if signal.target_1 and signal.target_1 > 0:
            return round(signal.target_1, 2)

        # Fallback to config default
        if signal.direction == "buy":
            return round(entry_price * (1 + config.default_take_profit_pct / 100), 2)
        else:
            return round(entry_price * (1 - config.default_take_profit_pct / 100), 2)

    @staticmethod
    def _calc_stop_loss(
        signal: TradingSignal,
        entry_price: float,
        config: BotConfiguration,
    ) -> float:
        """Calculate stop-loss price from signal or config default."""
        # Prefer signal's stop_loss
        if signal.stop_loss and signal.stop_loss > 0:
            return round(signal.stop_loss, 2)

        # Fallback to config default
        if signal.direction == "buy":
            return round(entry_price * (1 - config.default_stop_loss_pct / 100), 2)
        else:
            return round(entry_price * (1 + config.default_stop_loss_pct / 100), 2)
