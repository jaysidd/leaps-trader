"""
Bot Configuration model — user-configurable trading bot settings.

Controls execution mode, per-trade limits, daily limits, exit rules,
signal filters, circuit breakers, and options-specific parameters.
All fields have safe defaults (paper mode, signal-only, conservative limits).
"""
import enum
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, JSON, Index,
)
from sqlalchemy.sql import func

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExecutionMode(str, enum.Enum):
    """How the bot processes trading signals."""
    SIGNAL_ONLY = "signal_only"   # Generate signals only — no auto-trading (default)
    SEMI_AUTO = "semi_auto"       # Signal + user approval → execute
    FULL_AUTO = "full_auto"       # Signal → risk check → execute autonomously


class SizingMode(str, enum.Enum):
    """Position sizing algorithm."""
    FIXED_DOLLAR = "fixed_dollar"     # Use max_per_*_trade as dollar amount
    PCT_PORTFOLIO = "pct_portfolio"   # Percentage of portfolio equity
    RISK_BASED = "risk_based"         # Dollar risk / stop distance = shares


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class BotConfiguration(Base):
    """
    Singleton configuration for the trading bot.
    One row per deployment — created with safe defaults on first access.
    """
    __tablename__ = "bot_configuration"

    id = Column(Integer, primary_key=True)

    # ── Execution Mode ────────────────────────────────────────────────────
    execution_mode = Column(
        String(20), nullable=False, default=ExecutionMode.SIGNAL_ONLY.value,
    )
    paper_mode = Column(Boolean, nullable=False, default=True)  # ALWAYS default True

    # ── Per-Trade Limits (user-configurable) ──────────────────────────────
    max_per_stock_trade = Column(Float, nullable=False, default=500.0)
    max_per_options_trade = Column(Float, nullable=False, default=300.0)
    sizing_mode = Column(
        String(20), nullable=False, default=SizingMode.FIXED_DOLLAR.value,
    )
    risk_pct_per_trade = Column(Float, nullable=False, default=1.0)  # For risk-based sizing

    # ── Daily Limits ──────────────────────────────────────────────────────
    max_daily_loss = Column(Float, nullable=False, default=500.0)
    max_trades_per_day = Column(Integer, nullable=False, default=10)
    max_concurrent_positions = Column(Integer, nullable=False, default=5)

    # ── Portfolio Limits ──────────────────────────────────────────────────
    max_portfolio_allocation_pct = Column(Float, nullable=False, default=10.0)
    max_total_invested_pct = Column(Float, nullable=False, default=80.0)

    # ── Exit Rules ────────────────────────────────────────────────────────
    default_take_profit_pct = Column(Float, nullable=False, default=20.0)
    default_stop_loss_pct = Column(Float, nullable=False, default=10.0)
    trailing_stop_enabled = Column(Boolean, nullable=False, default=False)
    trailing_stop_pct = Column(Float, nullable=False, default=5.0)
    close_positions_eod = Column(Boolean, nullable=False, default=False)
    eod_close_minutes_before = Column(Integer, nullable=False, default=5)  # Minutes before close to exit
    leaps_roll_alert_dte = Column(Integer, nullable=False, default=60)

    # ── Signal Filters ────────────────────────────────────────────────────
    min_confidence_to_execute = Column(Float, nullable=False, default=75.0)
    require_ai_analysis = Column(Boolean, nullable=False, default=False)
    min_ai_conviction = Column(Float, nullable=False, default=7.0)
    enabled_strategies = Column(
        JSON, nullable=False,
        default=["orb_breakout", "vwap_pullback", "range_breakout"],
    )

    # ── Circuit Breakers (% of daily starting equity) ─────────────────────
    circuit_breaker_warn_pct = Column(Float, nullable=False, default=3.0)
    circuit_breaker_pause_pct = Column(Float, nullable=False, default=5.0)
    circuit_breaker_halt_pct = Column(Float, nullable=False, default=10.0)
    auto_resume_next_day = Column(Boolean, nullable=False, default=True)

    # ── Options-Specific ──────────────────────────────────────────────────
    max_bid_ask_spread_pct = Column(Float, nullable=False, default=15.0)
    min_option_open_interest = Column(Integer, nullable=False, default=100)
    min_option_delta = Column(Float, nullable=False, default=0.30)
    options_order_type = Column(String(20), nullable=False, default="limit")

    # ── Autopilot Capital Controls ──────────────────────────────────
    autopilot_max_capital = Column(Float, nullable=False, default=10000.0)
    autopilot_max_candidates = Column(Integer, nullable=False, default=2)
    autopilot_max_trades_per_day = Column(Integer, nullable=False, default=5)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self):
        return (
            f"<BotConfiguration(mode={self.execution_mode}, "
            f"paper={self.paper_mode}, "
            f"max_stock=${self.max_per_stock_trade}, "
            f"max_opt=${self.max_per_options_trade})>"
        )

    def to_dict(self) -> dict:
        """Serialise for API responses."""
        return {
            "id": self.id,
            "execution_mode": self.execution_mode,
            "paper_mode": self.paper_mode,
            # Per-trade
            "max_per_stock_trade": self.max_per_stock_trade,
            "max_per_options_trade": self.max_per_options_trade,
            "sizing_mode": self.sizing_mode,
            "risk_pct_per_trade": self.risk_pct_per_trade,
            # Daily
            "max_daily_loss": self.max_daily_loss,
            "max_trades_per_day": self.max_trades_per_day,
            "max_concurrent_positions": self.max_concurrent_positions,
            # Portfolio
            "max_portfolio_allocation_pct": self.max_portfolio_allocation_pct,
            "max_total_invested_pct": self.max_total_invested_pct,
            # Exit rules
            "default_take_profit_pct": self.default_take_profit_pct,
            "default_stop_loss_pct": self.default_stop_loss_pct,
            "trailing_stop_enabled": self.trailing_stop_enabled,
            "trailing_stop_pct": self.trailing_stop_pct,
            "close_positions_eod": self.close_positions_eod,
            "eod_close_minutes_before": self.eod_close_minutes_before,
            "leaps_roll_alert_dte": self.leaps_roll_alert_dte,
            # Signal filters
            "min_confidence_to_execute": self.min_confidence_to_execute,
            "require_ai_analysis": self.require_ai_analysis,
            "min_ai_conviction": self.min_ai_conviction,
            "enabled_strategies": self.enabled_strategies,
            # Circuit breakers
            "circuit_breaker_warn_pct": self.circuit_breaker_warn_pct,
            "circuit_breaker_pause_pct": self.circuit_breaker_pause_pct,
            "circuit_breaker_halt_pct": self.circuit_breaker_halt_pct,
            "auto_resume_next_day": self.auto_resume_next_day,
            # Options
            "max_bid_ask_spread_pct": self.max_bid_ask_spread_pct,
            "min_option_open_interest": self.min_option_open_interest,
            "min_option_delta": self.min_option_delta,
            "options_order_type": self.options_order_type,
            # Autopilot
            "autopilot_max_capital": self.autopilot_max_capital,
            "autopilot_max_candidates": self.autopilot_max_candidates,
            "autopilot_max_trades_per_day": self.autopilot_max_trades_per_day,
            # Timestamps
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
