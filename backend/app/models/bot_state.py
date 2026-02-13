"""
Bot State model — runtime state of the trading bot.

Tracks: current status, daily P&L counters, circuit breaker level,
open position counts, health check timestamps, and error tracking.
Single row — reset daily at market open.
"""
import enum
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
)
from sqlalchemy.sql import func

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BotStatus(str, enum.Enum):
    """Bot operational state."""
    STOPPED = "stopped"       # Not running — no signal processing
    RUNNING = "running"       # Actively processing signals + monitoring positions
    PAUSED = "paused"         # Paused by circuit breaker or user
    HALTED = "halted"         # Critical circuit breaker — requires manual restart


class CircuitBreakerLevel(str, enum.Enum):
    """Escalating circuit breaker levels."""
    NONE = "none"             # All clear
    WARNING = "warning"       # Approaching daily loss limit — log + notify
    PAUSED = "paused"         # Hit pause threshold — stop new trades, keep monitoring
    HALTED = "halted"         # Hit halt threshold — stop everything, require manual restart


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class BotState(Base):
    """
    Singleton runtime state for the trading bot.
    One row — created on first access, reset daily at market open.
    """
    __tablename__ = "bot_state"

    id = Column(Integer, primary_key=True)

    # ── Current Status ────────────────────────────────────────────────────
    status = Column(
        String(20), nullable=False, default=BotStatus.STOPPED.value,
    )

    # ── Daily Tracking (reset at market open) ─────────────────────────────
    daily_pl = Column(Float, nullable=False, default=0.0)
    daily_trades_count = Column(Integer, nullable=False, default=0)
    daily_wins = Column(Integer, nullable=False, default=0)
    daily_losses = Column(Integer, nullable=False, default=0)
    daily_start_equity = Column(Float, nullable=True)   # Snapshot at market open

    # ── Circuit Breaker ───────────────────────────────────────────────────
    circuit_breaker_level = Column(
        String(20), nullable=False, default=CircuitBreakerLevel.NONE.value,
    )
    circuit_breaker_triggered_at = Column(DateTime(timezone=True), nullable=True)
    circuit_breaker_reason = Column(String(255), nullable=True)

    # ── Position Tracking ─────────────────────────────────────────────────
    open_positions_count = Column(Integer, nullable=False, default=0)
    open_stock_positions = Column(Integer, nullable=False, default=0)
    open_option_positions = Column(Integer, nullable=False, default=0)

    # ── Health ────────────────────────────────────────────────────────────
    last_health_check = Column(DateTime(timezone=True), nullable=True)
    last_signal_processed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    consecutive_errors = Column(Integer, nullable=False, default=0)

    # ── Timestamps ────────────────────────────────────────────────────────
    started_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self):
        return (
            f"<BotState(status={self.status}, "
            f"daily_pl={self.daily_pl}, "
            f"positions={self.open_positions_count}, "
            f"cb={self.circuit_breaker_level})>"
        )

    def to_dict(self) -> dict:
        """Serialise for API responses."""
        return {
            "id": self.id,
            "status": self.status,
            # Daily
            "daily_pl": self.daily_pl,
            "daily_trades_count": self.daily_trades_count,
            "daily_wins": self.daily_wins,
            "daily_losses": self.daily_losses,
            "daily_start_equity": self.daily_start_equity,
            "daily_win_rate": (
                round(self.daily_wins / self.daily_trades_count * 100, 1)
                if self.daily_trades_count > 0 else None
            ),
            # Circuit breaker
            "circuit_breaker_level": self.circuit_breaker_level,
            "circuit_breaker_triggered_at": (
                self.circuit_breaker_triggered_at.isoformat()
                if self.circuit_breaker_triggered_at else None
            ),
            "circuit_breaker_reason": self.circuit_breaker_reason,
            # Positions
            "open_positions_count": self.open_positions_count,
            "open_stock_positions": self.open_stock_positions,
            "open_option_positions": self.open_option_positions,
            # Health
            "last_health_check": (
                self.last_health_check.isoformat() if self.last_health_check else None
            ),
            "last_signal_processed_at": (
                self.last_signal_processed_at.isoformat()
                if self.last_signal_processed_at else None
            ),
            "last_error": self.last_error,
            "last_error_at": (
                self.last_error_at.isoformat() if self.last_error_at else None
            ),
            "consecutive_errors": self.consecutive_errors,
            # Timestamps
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def reset_daily(self, start_equity: float):
        """Reset daily counters. Called at market open."""
        self.daily_pl = 0.0
        self.daily_trades_count = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.daily_start_equity = start_equity
        self.circuit_breaker_level = CircuitBreakerLevel.NONE.value
        self.circuit_breaker_triggered_at = None
        self.circuit_breaker_reason = None
        self.consecutive_errors = 0
        self.last_error = None
        self.last_error_at = None
