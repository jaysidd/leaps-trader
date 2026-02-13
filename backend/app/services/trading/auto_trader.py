"""
Auto-Trader Orchestrator — the brain of the trading bot.

State machine: STOPPED → RUNNING → PAUSED → HALTED
Connects: Signal Engine → Risk Gateway → Position Sizer → Order Executor → Position Monitor → Trade Journal

Called from:
  - check_signals_job():  process_new_signals() — route new signals through the pipeline
  - monitor_positions_job(): run_position_monitor() — check open positions every 1 min
  - daily_reset_job():    daily_reset() — reset daily counters at market open
  - health_check_job():   run_health_check() — verify consistency every 5 min
  - API endpoints:        start/stop/emergency_stop/approve_signal
"""
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.models.bot_config import BotConfiguration, ExecutionMode
from app.models.bot_state import BotState, BotStatus, CircuitBreakerLevel
from app.models.executed_trade import ExecutedTrade, TradeStatus, ExitReason
from app.models.trading_signal import TradingSignal

from app.services.trading.risk_gateway import RiskGateway
from app.services.trading.position_sizer import PositionSizer
from app.services.trading.order_executor import OrderExecutor
from app.services.trading.position_monitor import PositionMonitor
from app.services.trading.trade_journal import TradeJournal


class AutoTrader:
    """
    Orchestrates the full automated trading pipeline.
    Singleton — instantiated once, given fresh DB sessions per job.
    """

    def __init__(self):
        self._initialized = False

    # =====================================================================
    # DB Helpers — config & state
    # =====================================================================

    @staticmethod
    def _get_config(db: Session) -> BotConfiguration:
        config = db.query(BotConfiguration).first()
        if not config:
            config = BotConfiguration()
            db.add(config)
            db.commit()
        return config

    @staticmethod
    def _get_or_create_state(db: Session) -> BotState:
        state = db.query(BotState).first()
        if not state:
            state = BotState()
            db.add(state)
            db.commit()
        return state

    # =====================================================================
    # Service Factory — fresh instances per DB session
    # =====================================================================

    def _build_services(self, db: Session):
        """Create service instances with the given DB session."""
        from app.services.trading.alpaca_trading_service import alpaca_trading_service
        from app.services.data_fetcher.alpaca_service import alpaca_service

        risk = RiskGateway(db)
        sizer = PositionSizer()
        executor = OrderExecutor(alpaca_trading_service, db)
        monitor = PositionMonitor(db, alpaca_trading_service, alpaca_service)
        journal = TradeJournal(db)

        return risk, sizer, executor, monitor, journal, alpaca_trading_service, alpaca_service

    # =====================================================================
    # Process New Signals (called from check_signals_job)
    # =====================================================================

    def process_new_signals(
        self, signals: List[TradingSignal], db: Session,
    ) -> List[ExecutedTrade]:
        """
        Main entry point: route new signals through the trading pipeline.

        Signal Only  → return [] (nothing to auto-execute)
        Semi-Auto    → mark signals as pending_approval, send notification
        Full Auto    → risk → size → execute → journal

        Returns list of ExecutedTrades created.
        """
        config = self._get_config(db)

        # Signal-only mode: no auto-trading
        if config.execution_mode == ExecutionMode.SIGNAL_ONLY.value:
            return []

        state = self._get_or_create_state(db)

        # Bot must be RUNNING
        if state.status != BotStatus.RUNNING.value:
            return []

        (
            risk, sizer, executor, monitor, journal,
            trading_svc, data_svc,
        ) = self._build_services(db)

        account = trading_svc.get_account()
        if not account:
            logger.error("AutoTrader: cannot get Alpaca account — skipping signals")
            return []

        executed = []
        for signal in signals:
            try:
                # Skip low-confidence signals
                if (signal.confidence_score or 0) < config.min_confidence_to_execute:
                    logger.debug(
                        f"AutoTrader: skipping {signal.symbol} — "
                        f"confidence {signal.confidence_score} < {config.min_confidence_to_execute}"
                    )
                    continue

                # Semi-auto → queue for user approval
                if config.execution_mode == ExecutionMode.SEMI_AUTO.value:
                    self._mark_pending_approval(signal, db)
                    continue

                # Full-auto → execute
                trade = self._execute_signal(
                    signal, config, state, account,
                    risk, sizer, executor, data_svc, db,
                )
                if trade:
                    executed.append(trade)

                    # Successful trade — reset consecutive error counter
                    if state.consecutive_errors > 0:
                        state.consecutive_errors = 0
                        state.last_error = None

                    # Refresh account after each trade (buying power changed)
                    account = trading_svc.get_account() or account

            except Exception as e:
                logger.error(f"AutoTrader: error processing signal {signal.symbol}: {e}")
                state.last_error = str(e)
                state.last_error_at = datetime.now(timezone.utc)
                state.consecutive_errors += 1
                db.commit()

        # Update circuit breaker after processing all signals
        if executed:
            account = trading_svc.get_account() or account
            risk.update_circuit_breaker(config, state, account)

        state.last_signal_processed_at = datetime.now(timezone.utc)
        db.commit()

        if executed:
            logger.info(f"AutoTrader: executed {len(executed)} trades from {len(signals)} signals")

        return executed

    # =====================================================================
    # Position Monitor (called every 1 min from scheduler)
    # =====================================================================

    def run_position_monitor(self, db: Session) -> dict:
        """
        Check all open positions for exit conditions and execute exits.
        Returns summary of actions taken.
        """
        config = self._get_config(db)
        state = self._get_or_create_state(db)

        # Must be running (or at least have open positions to monitor)
        if state.status not in (BotStatus.RUNNING.value, BotStatus.PAUSED.value):
            return {"status": "bot_not_active", "exits": 0}

        (
            risk, sizer, executor, monitor, journal,
            trading_svc, data_svc,
        ) = self._build_services(db)

        # Run the monitor (pass bot_state for counter reconciliation)
        monitor_result = monitor.check_all_positions(config, bot_state=state)

        exits_executed = 0
        for exit_signal in monitor_result.exit_signals:
            try:
                trade = db.query(ExecutedTrade).get(exit_signal.trade_id)
                if not trade or trade.status != TradeStatus.OPEN.value:
                    continue

                exit_result = executor.execute_exit(
                    trade,
                    exit_signal.reason,
                    current_price=exit_signal.current_price,
                    bot_state=state,
                )

                if exit_result.success:
                    exits_executed += 1
                    # Send exit notification
                    self._send_exit_notification(trade, exit_signal)

            except Exception as e:
                logger.error(
                    f"AutoTrader: error executing exit for trade #{exit_signal.trade_id}: {e}"
                )

        # Update daily stats if we had exits
        if exits_executed:
            journal.update_daily_stats()

            # Successful exits — reset consecutive error counter
            if state.consecutive_errors > 0:
                state.consecutive_errors = 0
                state.last_error = None

            # Refresh circuit breaker
            account = trading_svc.get_account()
            if account:
                risk.update_circuit_breaker(config, state, account)

        return {
            "positions_checked": monitor_result.positions_checked,
            "exits": exits_executed,
            "bracket_exits_reconciled": monitor_result.bracket_exits_reconciled,
            "pending_fills_updated": monitor_result.pending_fills_updated,
            "roll_alerts": monitor_result.roll_alerts_sent,
            "errors": len(monitor_result.errors),
        }

    # =====================================================================
    # Approve Signal (Semi-Auto mode)
    # =====================================================================

    def approve_signal(self, signal_id: int, db: Session) -> Optional[ExecutedTrade]:
        """
        User approved a signal in semi-auto mode. Execute it now.
        """
        signal = db.query(TradingSignal).get(signal_id)
        if not signal:
            logger.warning(f"AutoTrader: approve_signal — signal #{signal_id} not found")
            return None

        config = self._get_config(db)
        state = self._get_or_create_state(db)

        if state.status != BotStatus.RUNNING.value:
            logger.warning("AutoTrader: approve_signal — bot not running")
            return None

        (
            risk, sizer, executor, monitor, journal,
            trading_svc, data_svc,
        ) = self._build_services(db)

        account = trading_svc.get_account()
        if not account:
            return None

        trade = self._execute_signal(
            signal, config, state, account,
            risk, sizer, executor, data_svc, db,
        )

        if trade:
            # Refresh circuit breaker
            risk.update_circuit_breaker(config, state, account)

        return trade

    # =====================================================================
    # Start / Stop / Emergency Stop
    # =====================================================================

    def start(self, db: Session) -> dict:
        """Start the trading bot."""
        from app.services.trading.alpaca_trading_service import alpaca_trading_service

        if not alpaca_trading_service.is_available:
            return {"error": "Alpaca trading service not configured"}

        config = self._get_config(db)
        state = self._get_or_create_state(db)

        if state.status == BotStatus.RUNNING.value:
            return {"status": "already_running", "paper_mode": config.paper_mode}

        # Snapshot starting equity
        account = alpaca_trading_service.get_account()
        if not account:
            return {"error": "Cannot connect to Alpaca account"}

        state.status = BotStatus.RUNNING.value
        state.started_at = datetime.now(timezone.utc)
        state.daily_start_equity = account.get("equity", 0)
        state.daily_pl = 0
        state.daily_trades_count = 0
        state.daily_wins = 0
        state.daily_losses = 0
        state.circuit_breaker_level = CircuitBreakerLevel.NONE.value
        state.consecutive_errors = 0
        state.last_error = None
        db.commit()

        mode_str = "PAPER" if config.paper_mode else "LIVE"
        exec_str = config.execution_mode
        logger.info(
            f"AutoTrader: STARTED ({mode_str}, {exec_str}, "
            f"equity=${state.daily_start_equity:,.2f})"
        )

        # Telegram notification
        self._send_telegram(
            f"🟢 Trading bot started\n"
            f"Mode: {mode_str} / {exec_str}\n"
            f"Equity: ${state.daily_start_equity:,.2f}"
        )

        return {
            "status": "running",
            "paper_mode": config.paper_mode,
            "execution_mode": config.execution_mode,
            "equity": state.daily_start_equity,
        }

    def stop(self, db: Session) -> dict:
        """Graceful stop. Does NOT cancel orders or close positions."""
        state = self._get_or_create_state(db)
        prev_status = state.status
        state.status = BotStatus.STOPPED.value
        db.commit()

        logger.info(f"AutoTrader: STOPPED (was {prev_status})")
        self._send_telegram("🔴 Trading bot stopped (graceful)")

        return {"status": "stopped", "previous_status": prev_status}

    def emergency_stop(self, close_positions: bool, db: Session) -> dict:
        """
        Kill switch: cancel all orders, optionally close all positions.
        """
        state = self._get_or_create_state(db)
        (
            risk, sizer, executor, monitor, journal,
            trading_svc, data_svc,
        ) = self._build_services(db)

        results = executor.kill_switch(state)

        if not close_positions:
            # Kill switch only cancels orders by default
            # If close_positions is False, re-open the position tracking
            pass

        state.status = BotStatus.STOPPED.value
        state.circuit_breaker_level = CircuitBreakerLevel.NONE.value
        db.commit()

        # Update daily stats after emergency
        journal.update_daily_stats()

        self._send_telegram(
            f"🚨 EMERGENCY STOP\n"
            f"Orders cancelled: {results.get('cancelled_orders', 0)}\n"
            f"Positions closed: {results.get('closed_positions', 0)}\n"
            f"Trades marked: {results.get('trades_closed', 0)}"
        )

        return results

    # =====================================================================
    # Daily Reset (called at market open)
    # =====================================================================

    def daily_reset(self, db: Session):
        """Reset daily counters at market open. Snapshot equity."""
        from app.services.trading.alpaca_trading_service import alpaca_trading_service

        state = self._get_or_create_state(db)
        journal = TradeJournal(db)

        # Finalize yesterday's daily stats
        journal.update_daily_stats()

        # Snapshot current equity
        account = alpaca_trading_service.get_account()
        equity = account.get("equity", 0) if account else 0

        state.reset_daily(equity)
        db.commit()

        logger.info(f"AutoTrader: daily reset — equity=${equity:,.2f}")

    # =====================================================================
    # Health Check (called every 5 min)
    # =====================================================================

    def run_health_check(self, db: Session) -> bool:
        """Run health check: position consistency + error monitoring."""
        state = self._get_or_create_state(db)

        if state.status == BotStatus.STOPPED.value:
            return True

        (
            risk, sizer, executor, monitor, journal,
            trading_svc, data_svc,
        ) = self._build_services(db)

        consistent = monitor.health_check(state)

        # Auto-pause on too many consecutive errors
        if state.consecutive_errors >= 5:
            state.status = BotStatus.PAUSED.value
            state.last_error = f"Auto-paused: {state.consecutive_errors} consecutive errors"
            db.commit()
            self._send_telegram(
                f"⚠️ Bot auto-paused: {state.consecutive_errors} consecutive errors\n"
                f"Last error: {state.last_error}"
            )
            return False

        return consistent

    # =====================================================================
    # Status
    # =====================================================================

    def get_status(self, db: Session) -> dict:
        """Get current bot status for the API."""
        from app.services.trading.alpaca_trading_service import alpaca_trading_service

        config = self._get_config(db)
        state = self._get_or_create_state(db)

        # Current account info
        account = alpaca_trading_service.get_account()

        current_equity = account.get("equity", 0) if account else 0
        daily_pl = state.daily_pl or 0
        daily_pl_pct = 0
        if state.daily_start_equity and state.daily_start_equity > 0:
            daily_pl_pct = round((daily_pl / state.daily_start_equity) * 100, 2)

        return {
            # Bot state
            "status": state.status,
            "execution_mode": config.execution_mode,
            "paper_mode": config.paper_mode,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            # Daily stats
            "daily_pl": round(daily_pl, 2),
            "daily_pl_pct": daily_pl_pct,
            "daily_trades": state.daily_trades_count,
            "daily_wins": state.daily_wins,
            "daily_losses": state.daily_losses,
            # Positions
            "open_positions": state.open_positions_count,
            "open_stocks": state.open_stock_positions,
            "open_options": state.open_option_positions,
            # Account
            "equity": round(current_equity, 2) if current_equity else 0,
            "buying_power": round(account.get("buying_power", 0), 2) if account else 0,
            # Circuit breaker
            "circuit_breaker": state.circuit_breaker_level,
            # Health
            "last_health_check": (
                state.last_health_check.isoformat() if state.last_health_check else None
            ),
            "last_error": state.last_error,
            "consecutive_errors": state.consecutive_errors,
        }

    # =====================================================================
    # Manual Signal Execution (from "Trade" button in UI)
    # =====================================================================

    def preview_signal(self, signal_id: int, db: Session) -> dict:
        """
        Preview what would happen if this signal were executed.
        Returns risk check results and sizing info WITHOUT placing any order.
        Used by the SendToBotModal to show the confirmation dialog.
        """
        signal = db.query(TradingSignal).get(signal_id)
        if not signal:
            return {"error": f"Signal #{signal_id} not found"}

        if signal.trade_executed:
            return {"error": f"Signal #{signal_id} has already been executed"}

        config = self._get_config(db)
        state = self._get_or_create_state(db)

        (
            risk, sizer, executor, monitor, journal,
            trading_svc, data_svc,
        ) = self._build_services(db)

        account = trading_svc.get_account()
        if not account:
            return {"error": "Cannot connect to Alpaca account. Check Alpaca configuration."}

        # Risk check (skip bot-status requirement)
        risk_result = risk.check_trade(
            signal, config, state, account,
            skip_bot_status_check=True,
        )

        # Get current price
        current_price = data_svc.get_current_price(signal.symbol)

        # Position sizing preview (even if risk rejected, show what it would be)
        size_result = None
        if current_price and current_price > 0:
            size_result = sizer.calculate_size(
                signal, config, account, current_price,
            )

        return {
            "signal": signal.to_dict(),
            "risk_check": {
                "approved": risk_result.approved,
                "reason": risk_result.reason,
                "warnings": risk_result.warnings,
            },
            "sizing": {
                "quantity": size_result.quantity,
                "notional": round(size_result.notional, 2),
                "asset_type": size_result.asset_type,
                "is_fractional": size_result.is_fractional,
                "is_notional_order": size_result.is_notional_order,
                "capped_reason": size_result.capped_reason,
                "rejected": size_result.rejected,
                "reject_reason": size_result.reject_reason,
            } if size_result else {
                "quantity": 0, "notional": 0, "asset_type": "stock",
                "is_fractional": False, "is_notional_order": False,
                "capped_reason": "", "rejected": True,
                "reject_reason": "No price data available",
            },
            "current_price": current_price,
            "account": {
                "equity": round(account.get("equity", 0), 2),
                "buying_power": round(account.get("buying_power", 0), 2),
            },
            "config": {
                "paper_mode": config.paper_mode,
                "sizing_mode": config.sizing_mode,
                "max_per_stock_trade": config.max_per_stock_trade,
                "max_per_options_trade": config.max_per_options_trade,
                "default_take_profit_pct": config.default_take_profit_pct,
                "default_stop_loss_pct": config.default_stop_loss_pct,
            },
        }

    def execute_manual_signal(self, signal_id: int, db: Session) -> dict:
        """
        Manually execute a signal through the full risk → size → execute pipeline.
        Does NOT require the bot to be in RUNNING state.
        Called from the "Trade" button in the Trading Signals UI.

        Returns dict with either 'trade' key (success) or 'error' key (failure).
        """
        signal = db.query(TradingSignal).get(signal_id)
        if not signal:
            return {"error": f"Signal #{signal_id} not found"}

        if signal.trade_executed:
            return {"error": f"Signal #{signal_id} has already been executed"}

        # Lock the signal row to prevent concurrent execution
        signal = db.query(TradingSignal).filter(TradingSignal.id == signal_id).with_for_update().first()
        if not signal:
            return {"error": f"Signal #{signal_id} not found"}
        if signal.trade_executed:
            return {"error": f"Signal #{signal_id} has already been executed"}

        config = self._get_config(db)
        state = self._get_or_create_state(db)

        (
            risk, sizer, executor, monitor, journal,
            trading_svc, data_svc,
        ) = self._build_services(db)

        account = trading_svc.get_account()
        if not account:
            return {"error": "Cannot connect to Alpaca account. Check Alpaca configuration."}

        # Execute through the full pipeline with bot-status check skipped
        trade = self._execute_signal(
            signal, config, state, account,
            risk, sizer, executor, data_svc, db,
            skip_bot_status_check=True,
        )

        if trade:
            # Mark signal as executed
            signal.trade_executed = True
            signal.trade_execution_id = trade.entry_order_id
            # Record as manual execution
            trade.execution_mode = "manual"
            db.commit()

            logger.info(
                f"AutoTrader: MANUAL execution — {signal.symbol} "
                f"qty={trade.quantity} entry=${trade.entry_price or 'pending'}"
            )

            return {"trade": trade.to_dict()}

        return {
            "error": (
                "Signal was rejected by risk checks or order execution failed. "
                "Check the preview for details."
            )
        }

    # =====================================================================
    # Private — Core Pipeline
    # =====================================================================

    def _execute_signal(
        self,
        signal: TradingSignal,
        config: BotConfiguration,
        state: BotState,
        account: dict,
        risk: RiskGateway,
        sizer: PositionSizer,
        executor: OrderExecutor,
        data_svc,
        db: Session,
        skip_bot_status_check: bool = False,
    ) -> Optional[ExecutedTrade]:
        """Core pipeline for a single signal: risk → size → execute."""

        # 1. Risk check
        risk_result = risk.check_trade(
            signal, config, state, account,
            skip_bot_status_check=skip_bot_status_check,
        )
        if not risk_result.approved:
            logger.info(
                f"AutoTrader: {signal.symbol} rejected — {risk_result.reason}"
            )
            self._send_telegram(
                f"⛔ Signal rejected: {signal.symbol} {signal.direction}\n"
                f"Reason: {risk_result.reason}"
            )
            return None

        # Log warnings
        for warning in risk_result.warnings:
            logger.warning(f"AutoTrader: risk warning for {signal.symbol}: {warning}")

        # 2. Get current price
        current_price = data_svc.get_current_price(signal.symbol)
        if not current_price or current_price <= 0:
            logger.error(f"AutoTrader: no price for {signal.symbol}")
            return None

        # Determine asset type from signal
        # Default to stock; if signal has option-specific data, use option
        asset_type = "stock"
        option_symbol = None
        option_premium = None
        option_type = None
        option_strike = None
        option_expiry = None

        # Check if signal has option chain data (from LEAPS screening)
        if signal.strategy and "leaps" in signal.strategy.lower():
            asset_type = "option"
            # Option details would come from the signal's institutional_data or similar
            # For now, these would be passed in from the screening result

        # 3. Position sizing
        size_result = sizer.calculate_size(
            signal, config, account, current_price, asset_type=asset_type,
        )
        if size_result.rejected:
            logger.info(
                f"AutoTrader: {signal.symbol} sizing rejected — {size_result.reject_reason}"
            )
            return None

        # 4. Execute entry
        trade, order_result = executor.execute_entry(
            signal=signal,
            size_result=size_result,
            bot_config=config,
            bot_state=state,
            current_price=current_price,
            option_symbol=option_symbol,
            option_premium=option_premium,
            option_type=option_type,
            option_strike=option_strike,
            option_expiry=option_expiry,
        )

        if not order_result.success:
            return None

        # 5. Send execution notification
        self._send_execution_notification(signal, trade, order_result)

        return trade

    # =====================================================================
    # Private — Semi-Auto Helpers
    # =====================================================================

    @staticmethod
    def _mark_pending_approval(signal: TradingSignal, db: Session):
        """Mark a signal as awaiting user approval (semi-auto mode)."""
        # Create a pending ExecutedTrade so the UI can show the approval queue
        trade = ExecutedTrade(
            signal_id=signal.id,
            symbol=signal.symbol,
            asset_type="stock",
            direction=signal.direction,
            quantity=0,  # Will be calculated when approved
            status=TradeStatus.PENDING_APPROVAL.value,
        )
        db.add(trade)
        db.commit()

        logger.info(f"AutoTrader: semi-auto — {signal.symbol} queued for approval")

    # =====================================================================
    # Private — Notifications
    # =====================================================================

    @staticmethod
    def _send_telegram(message: str):
        """Best-effort Telegram notification (thread-safe)."""
        try:
            from app.services.telegram_bot import get_telegram_bot
            bot = get_telegram_bot()
            if not bot or not bot._running:
                return

            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return  # No event loop available

            for uid in bot.allowed_users:
                asyncio.run_coroutine_threadsafe(
                    bot.send_message(str(uid), message), loop
                )
        except Exception as e:
            logger.debug(f"AutoTrader: telegram notification failed: {e}")

    def _send_execution_notification(
        self, signal: TradingSignal, trade: ExecutedTrade, order_result=None,
    ):
        """Send trade execution notification."""
        emoji = "📈" if signal.direction == "buy" else "📉"
        self._send_telegram(
            f"{emoji} Trade Executed\n"
            f"Symbol: {trade.symbol} ({trade.asset_type})\n"
            f"Direction: {trade.direction.upper()}\n"
            f"Qty: {trade.quantity}\n"
            f"Entry: ${trade.entry_price or 'pending'}\n"
            f"TP: ${trade.take_profit_price or 'N/A'}\n"
            f"SL: ${trade.stop_loss_price or 'N/A'}\n"
            f"Confidence: {signal.confidence_score or 'N/A'}%"
        )

    def _send_exit_notification(self, trade: ExecutedTrade, exit_signal):
        """Send position exit notification."""
        pl_emoji = "✅" if (trade.realized_pl or 0) >= 0 else "❌"
        self._send_telegram(
            f"{pl_emoji} Position Closed\n"
            f"Symbol: {trade.symbol}\n"
            f"Reason: {exit_signal.reason.value}\n"
            f"Entry: ${trade.entry_price}\n"
            f"Exit: ${exit_signal.current_price}\n"
            f"P&L: ${trade.realized_pl or 0:.2f} ({trade.realized_pl_pct or 0:.1f}%)"
        )


# Singleton
auto_trader = AutoTrader()
