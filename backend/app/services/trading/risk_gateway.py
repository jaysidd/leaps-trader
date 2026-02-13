"""
Risk Gateway — pre-execution risk checks for the trading bot.

Every signal must pass ALL checks before an order is placed.
Checks run fail-fast: the first rejection stops evaluation.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy.orm import Session

from app.models.bot_config import BotConfiguration
from app.models.bot_state import BotState, CircuitBreakerLevel, BotStatus
from app.models.executed_trade import ExecutedTrade, TradeStatus
from app.models.trading_signal import TradingSignal


ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RiskCheckResult:
    """Outcome of running all risk checks on a signal."""
    approved: bool = False
    reason: str = ""                       # Explanation when rejected
    warnings: list = field(default_factory=list)  # Non-blocking warnings


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RiskGateway:
    """
    16-point pre-execution risk check.
    All checks must pass for a signal to be approved.
    """

    def __init__(self, db: Session):
        self.db = db

    # =====================================================================
    # Main entry point
    # =====================================================================

    def check_trade(
        self,
        signal: TradingSignal,
        bot_config: BotConfiguration,
        bot_state: BotState,
        account: dict,
        asset_type: str = "stock",
        option_premium: Optional[float] = None,
        option_oi: Optional[int] = None,
        bid_ask_spread_pct: Optional[float] = None,
        skip_bot_status_check: bool = False,
    ) -> RiskCheckResult:
        """
        Run all risk checks in order. Returns approved/rejected with reason.

        Args:
            signal: The TradingSignal to evaluate
            bot_config: Current bot configuration
            bot_state: Current bot runtime state
            account: Alpaca account dict (from get_account())
            asset_type: "stock" or "option"
            option_premium: Option premium per share (for cost calculation)
            option_oi: Option open interest (for liquidity check)
            bid_ask_spread_pct: Bid-ask spread as % of mid (for options quality check)
            skip_bot_status_check: If True, skip bot-status and circuit-breaker checks
                (used for manual signal execution when bot is not RUNNING)
        """
        result = RiskCheckResult()

        # Each checker returns (passed: bool, reason: str, warning: str|None)
        checks = [
            ("Bot status", lambda: self._check_bot_status(bot_state)),
            ("Circuit breaker", lambda: self._check_circuit_breaker(bot_state)),
            ("Market hours", lambda: self._check_market_hours()),
            ("Daily trade count", lambda: self._check_daily_trades(bot_config, bot_state)),
            ("Daily loss limit", lambda: self._check_daily_loss(bot_config, bot_state)),
            ("Concurrent positions", lambda: self._check_concurrent_positions(bot_config, bot_state)),
            ("Per-trade limit", lambda: self._check_per_trade_limit(
                bot_config, signal, asset_type, option_premium
            )),
            ("Buying power", lambda: self._check_buying_power(
                bot_config, account, asset_type, option_premium
            )),
            ("Portfolio allocation", lambda: self._check_portfolio_allocation(
                bot_config, account, signal, asset_type, option_premium
            )),
            ("Total invested", lambda: self._check_total_invested(bot_config, account)),
            ("Confidence filter", lambda: self._check_confidence(bot_config, signal)),
            ("AI analysis filter", lambda: self._check_ai_analysis(bot_config, signal)),
            ("Strategy filter", lambda: self._check_strategy(bot_config, signal)),
            ("Duplicate position", lambda: self._check_duplicate_position(signal)),
        ]

        # Options-specific checks
        if asset_type == "option":
            checks.extend([
                ("Bid-ask spread", lambda: self._check_bid_ask_spread(
                    bot_config, bid_ask_spread_pct
                )),
                ("Open interest", lambda: self._check_open_interest(
                    bot_config, option_oi
                )),
            ])

        # Manual execution: skip bot-status and circuit-breaker checks
        if skip_bot_status_check:
            checks = [(n, c) for n, c in checks if n not in ("Bot status", "Circuit breaker")]

        # Run checks fail-fast
        for check_name, checker in checks:
            passed, reason, warning = checker()
            if warning:
                result.warnings.append(warning)
            if not passed:
                result.approved = False
                result.reason = f"[{check_name}] {reason}"
                logger.info(f"Risk REJECTED {signal.symbol}: {result.reason}")
                return result

        result.approved = True
        if result.warnings:
            logger.info(
                f"Risk APPROVED {signal.symbol} with warnings: {result.warnings}"
            )
        return result

    # =====================================================================
    # Circuit breaker management
    # =====================================================================

    def update_circuit_breaker(
        self,
        bot_config: BotConfiguration,
        bot_state: BotState,
        account: dict,
    ) -> str:
        """
        Check daily P&L against circuit breaker thresholds.
        Updates bot_state and returns the new level.
        """
        if not bot_state.daily_start_equity or bot_state.daily_start_equity <= 0:
            return bot_state.circuit_breaker_level

        current_equity = account.get("equity", 0)
        drawdown = bot_state.daily_start_equity - current_equity
        drawdown_pct = (drawdown / bot_state.daily_start_equity) * 100

        old_level = bot_state.circuit_breaker_level
        now = datetime.now(ET)

        # Circuit breaker should only ESCALATE within a trading day, never downgrade
        if old_level == CircuitBreakerLevel.HALTED.value:
            return bot_state.circuit_breaker_level  # Never downgrade from HALTED
        if old_level == CircuitBreakerLevel.PAUSED.value and drawdown_pct < bot_config.circuit_breaker_pause_pct:
            # Don't auto-downgrade from PAUSED — requires manual resume
            return bot_state.circuit_breaker_level

        if drawdown_pct >= bot_config.circuit_breaker_halt_pct:
            bot_state.circuit_breaker_level = CircuitBreakerLevel.HALTED.value
            bot_state.status = BotStatus.HALTED.value
            bot_state.circuit_breaker_reason = (
                f"Daily drawdown {drawdown_pct:.1f}% >= halt threshold "
                f"{bot_config.circuit_breaker_halt_pct}%"
            )
        elif drawdown_pct >= bot_config.circuit_breaker_pause_pct:
            bot_state.circuit_breaker_level = CircuitBreakerLevel.PAUSED.value
            bot_state.status = BotStatus.PAUSED.value
            bot_state.circuit_breaker_reason = (
                f"Daily drawdown {drawdown_pct:.1f}% >= pause threshold "
                f"{bot_config.circuit_breaker_pause_pct}%"
            )
        elif drawdown_pct >= bot_config.circuit_breaker_warn_pct:
            bot_state.circuit_breaker_level = CircuitBreakerLevel.WARNING.value
            bot_state.circuit_breaker_reason = (
                f"Daily drawdown {drawdown_pct:.1f}% >= warning threshold "
                f"{bot_config.circuit_breaker_warn_pct}%"
            )
        else:
            bot_state.circuit_breaker_level = CircuitBreakerLevel.NONE.value
            bot_state.circuit_breaker_reason = None

        if bot_state.circuit_breaker_level != old_level:
            bot_state.circuit_breaker_triggered_at = now
            logger.warning(
                f"Circuit breaker changed: {old_level} -> {bot_state.circuit_breaker_level} "
                f"(drawdown={drawdown_pct:.1f}%)"
            )

        self.db.commit()
        return bot_state.circuit_breaker_level

    # =====================================================================
    # Individual checks — each returns (passed, reason, warning)
    # =====================================================================

    def _check_bot_status(self, bot_state: BotState):
        if bot_state.status != BotStatus.RUNNING.value:
            return False, f"Bot is {bot_state.status}, must be running", None
        return True, "", None

    def _check_circuit_breaker(self, bot_state: BotState):
        level = bot_state.circuit_breaker_level
        if level in (CircuitBreakerLevel.PAUSED.value, CircuitBreakerLevel.HALTED.value):
            return False, f"Circuit breaker is {level}: {bot_state.circuit_breaker_reason}", None
        warning = None
        if level == CircuitBreakerLevel.WARNING.value:
            warning = f"Circuit breaker WARNING: {bot_state.circuit_breaker_reason}"
        return True, "", warning

    def _check_market_hours(self):
        """Check if market is currently open (basic check — scheduler also filters)."""
        now = datetime.now(ET)
        # Weekend check
        if now.weekday() >= 5:
            return False, "Market closed (weekend)", None
        # Hours check (9:30 AM - 4:00 PM ET)
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        if now < market_open or now > market_close:
            return False, "Market closed (outside trading hours)", None
        return True, "", None

    def _check_daily_trades(self, config: BotConfiguration, state: BotState):
        if state.daily_trades_count >= config.max_trades_per_day:
            return (
                False,
                f"Daily trade limit reached ({state.daily_trades_count}/{config.max_trades_per_day})",
                None,
            )
        # Warn if approaching limit
        warning = None
        remaining = config.max_trades_per_day - state.daily_trades_count
        if remaining <= 2:
            warning = f"Only {remaining} trades remaining today"
        return True, "", warning

    def _check_daily_loss(self, config: BotConfiguration, state: BotState):
        if state.daily_pl <= -abs(config.max_daily_loss):
            return (
                False,
                f"Daily loss limit reached (${state.daily_pl:.2f} / -${config.max_daily_loss:.2f})",
                None,
            )
        warning = None
        remaining_loss = abs(config.max_daily_loss) - abs(min(state.daily_pl, 0))
        if remaining_loss < config.max_daily_loss * 0.2:  # Within 20% of limit
            warning = f"Approaching daily loss limit (${remaining_loss:.2f} remaining)"
        return True, "", warning

    def _check_concurrent_positions(self, config: BotConfiguration, state: BotState):
        if state.open_positions_count >= config.max_concurrent_positions:
            return (
                False,
                f"Max concurrent positions reached ({state.open_positions_count}/{config.max_concurrent_positions})",
                None,
            )
        return True, "", None

    def _check_per_trade_limit(
        self, config: BotConfiguration, signal: TradingSignal,
        asset_type: str, option_premium: Optional[float],
    ):
        """Verify trade cost doesn't exceed per-trade limit."""
        if asset_type == "option":
            if option_premium is not None:
                cost = option_premium * 100  # 1 contract = 100 shares
                if cost > config.max_per_options_trade:
                    return (
                        False,
                        f"Option premium ${cost:.2f} exceeds max ${config.max_per_options_trade:.2f}",
                        None,
                    )
        # Stock per-trade limit is enforced in the position sizer
        return True, "", None

    def _check_buying_power(
        self, config: BotConfiguration, account: dict,
        asset_type: str, option_premium: Optional[float],
    ):
        buying_power = account.get("buying_power", 0)
        max_trade = (
            config.max_per_options_trade if asset_type == "option"
            else config.max_per_stock_trade
        )
        if buying_power < max_trade:
            return (
                False,
                f"Insufficient buying power (${buying_power:.2f} < ${max_trade:.2f})",
                None,
            )
        return True, "", None

    def _check_portfolio_allocation(
        self, config: BotConfiguration, account: dict,
        signal: TradingSignal, asset_type: str, option_premium: Optional[float],
    ):
        equity = account.get("equity", 0)
        if equity <= 0:
            return False, "Cannot determine equity for allocation check", None

        max_trade = (
            config.max_per_options_trade if asset_type == "option"
            else config.max_per_stock_trade
        )
        allocation_pct = (max_trade / equity) * 100
        if allocation_pct > config.max_portfolio_allocation_pct:
            return (
                False,
                f"Trade ${max_trade:.2f} is {allocation_pct:.1f}% of equity "
                f"(max {config.max_portfolio_allocation_pct}%)",
                None,
            )
        return True, "", None

    def _check_total_invested(self, config: BotConfiguration, account: dict):
        equity = account.get("equity", 0)
        long_value = account.get("long_market_value", 0)
        if equity > 0:
            invested_pct = (long_value / equity) * 100
            if invested_pct >= config.max_total_invested_pct:
                return (
                    False,
                    f"Total invested {invested_pct:.1f}% >= max {config.max_total_invested_pct}%",
                    None,
                )
        return True, "", None

    def _check_confidence(self, config: BotConfiguration, signal: TradingSignal):
        confidence = signal.confidence_score or 0
        if confidence < config.min_confidence_to_execute:
            return (
                False,
                f"Confidence {confidence:.0f} < minimum {config.min_confidence_to_execute:.0f}",
                None,
            )
        return True, "", None

    def _check_ai_analysis(self, config: BotConfiguration, signal: TradingSignal):
        if not config.require_ai_analysis:
            return True, "", None
        if not signal.ai_deep_analysis:
            return False, "AI analysis required but not available", None
        # Check conviction if AI analysis exists
        conviction = (signal.ai_deep_analysis or {}).get("conviction_score", 0)
        if conviction < config.min_ai_conviction:
            return (
                False,
                f"AI conviction {conviction}/10 < minimum {config.min_ai_conviction}/10",
                None,
            )
        return True, "", None

    def _check_strategy(self, config: BotConfiguration, signal: TradingSignal):
        enabled = config.enabled_strategies or []
        # Extract base strategy name (e.g., "orb_breakout" from "orb_breakout_long")
        strategy_base = signal.strategy
        if strategy_base:
            for suffix in ("_long", "_short"):
                if strategy_base.endswith(suffix):
                    strategy_base = strategy_base[: -len(suffix)]
                    break

        if enabled and strategy_base not in enabled:
            return (
                False,
                f"Strategy '{signal.strategy}' not in enabled list: {enabled}",
                None,
            )
        return True, "", None

    def _check_duplicate_position(self, signal: TradingSignal):
        """Prevent opening a duplicate position in the same symbol+direction."""
        existing = (
            self.db.query(ExecutedTrade)
            .filter(
                ExecutedTrade.symbol == signal.symbol,
                ExecutedTrade.direction == signal.direction,
                ExecutedTrade.status == TradeStatus.OPEN.value,
            )
            .first()
        )
        if existing:
            return (
                False,
                f"Already have an open {signal.direction} position in {signal.symbol} (trade #{existing.id})",
                None,
            )
        return True, "", None

    def _check_bid_ask_spread(
        self, config: BotConfiguration, spread_pct: Optional[float],
    ):
        if spread_pct is None:
            return True, "", "Bid-ask spread data unavailable — skipping check"
        if spread_pct > config.max_bid_ask_spread_pct:
            return (
                False,
                f"Bid-ask spread {spread_pct:.1f}% > max {config.max_bid_ask_spread_pct}%",
                None,
            )
        return True, "", None

    def _check_open_interest(
        self, config: BotConfiguration, oi: Optional[int],
    ):
        if oi is None:
            return True, "", "Open interest data unavailable — skipping check"
        if oi < config.min_option_open_interest:
            return (
                False,
                f"Open interest {oi} < minimum {config.min_option_open_interest}",
                None,
            )
        return True, "", None
