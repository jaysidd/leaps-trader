"""
Executed Trade model — full lifecycle record for every bot-executed trade.

Tracks: signal link → entry order → exit order → P&L → exit reason.
This is the trade journal's core table.
"""
import enum
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExitReason(str, enum.Enum):
    """Why a position was closed."""
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"                 # EOD close or option expiry approaching
    SIGNAL_INVALIDATED = "signal_invalidated"
    CIRCUIT_BREAKER = "circuit_breaker"
    MANUAL = "manual"                       # User closed via UI/API
    KILL_SWITCH = "kill_switch"             # Emergency stop
    PARTIAL_EXIT = "partial_exit"
    EXPIRED = "expired"                     # Option expired worthless


class TradeStatus(str, enum.Enum):
    """Lifecycle state of an executed trade."""
    PENDING_ENTRY = "pending_entry"         # Entry order submitted, awaiting fill
    PENDING_APPROVAL = "pending_approval"   # Semi-auto: awaiting user approval
    OPEN = "open"                           # Position active, monitoring for exit
    PENDING_EXIT = "pending_exit"           # Exit order submitted, awaiting fill
    CLOSED = "closed"                       # Fully exited
    CANCELLED = "cancelled"                 # Entry order cancelled or rejected
    ERROR = "error"                         # Something went wrong


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class ExecutedTrade(Base):
    """
    One row per bot-executed trade.
    Links back to the originating TradingSignal.
    """
    __tablename__ = "executed_trades"

    id = Column(Integer, primary_key=True)

    # ── Link to originating signal ────────────────────────────────────────
    signal_id = Column(
        Integer, ForeignKey("trading_signals.id", ondelete="SET NULL"),
        nullable=True,  # indexed via idx_exec_trade_signal
    )
    signal = relationship("TradingSignal", foreign_keys=[signal_id])

    # ── What was traded ───────────────────────────────────────────────────
    symbol = Column(String(20), nullable=False)  # indexed via idx_exec_trade_symbol
    asset_type = Column(String(10), nullable=False, default="stock")  # stock, option
    direction = Column(String(10), nullable=False)                    # buy, sell

    # Options-specific fields (null for stock trades)
    option_symbol = Column(String(50), nullable=True)     # Full OCC symbol
    option_type = Column(String(10), nullable=True)       # call, put
    option_strike = Column(Float, nullable=True)
    option_expiry = Column(Date, nullable=True)

    # ── Entry ─────────────────────────────────────────────────────────────
    entry_order_id = Column(String(100), nullable=True)   # Alpaca order ID
    entry_price = Column(Float, nullable=True)
    entry_filled_at = Column(DateTime(timezone=True), nullable=True)
    quantity = Column(Float, nullable=False)               # Shares or contracts
    notional = Column(Float, nullable=True)                # Dollar value at entry
    is_fractional = Column(Boolean, nullable=False, default=False)

    # ── Exit targets (set at entry, may be adjusted) ──────────────────────
    take_profit_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    trailing_stop_pct = Column(Float, nullable=True)
    trailing_stop_high_water = Column(Float, nullable=True)

    # ── Bracket / child order IDs (stocks only) ──────────────────────────
    tp_order_id = Column(String(100), nullable=True)
    sl_order_id = Column(String(100), nullable=True)

    # ── Exit ──────────────────────────────────────────────────────────────
    exit_order_id = Column(String(100), nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_filled_at = Column(DateTime(timezone=True), nullable=True)
    exit_reason = Column(String(30), nullable=True)       # ExitReason enum value

    # ── P&L ───────────────────────────────────────────────────────────────
    realized_pl = Column(Float, nullable=True)             # Dollar P&L
    realized_pl_pct = Column(Float, nullable=True)         # Percentage P&L
    fees = Column(Float, nullable=False, default=0.0)

    # ── Meta ──────────────────────────────────────────────────────────────
    status = Column(String(20), nullable=False, default=TradeStatus.PENDING_ENTRY.value)
    execution_mode = Column(String(20), nullable=True)     # Mode active when trade opened
    hold_duration_minutes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)                    # Circuit breaker reason, etc.

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # ── Indexes ───────────────────────────────────────────────────────────
    __table_args__ = (
        Index("idx_exec_trade_status", "status"),
        Index("idx_exec_trade_symbol", "symbol"),
        Index("idx_exec_trade_signal", "signal_id"),
        Index("idx_exec_trade_created", "created_at"),
        Index("idx_exec_trade_exit_reason", "exit_reason"),
        Index("idx_exec_trade_asset_type", "asset_type"),
        # Composite index for common query pattern: filter by status + order by created_at
        Index("idx_exec_trade_status_created", "status", "created_at"),
    )

    def __repr__(self):
        return (
            f"<ExecutedTrade(id={self.id}, {self.symbol} {self.direction} "
            f"status={self.status} pl={self.realized_pl})>"
        )

    def to_dict(self) -> dict:
        """Full serialisation for API responses."""
        return {
            "id": self.id,
            "signal_id": self.signal_id,
            # What
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "direction": self.direction,
            "option_symbol": self.option_symbol,
            "option_type": self.option_type,
            "option_strike": self.option_strike,
            "option_expiry": self.option_expiry.isoformat() if self.option_expiry else None,
            # Entry
            "entry_order_id": self.entry_order_id,
            "entry_price": self.entry_price,
            "entry_filled_at": self.entry_filled_at.isoformat() if self.entry_filled_at else None,
            "quantity": self.quantity,
            "notional": self.notional,
            "is_fractional": self.is_fractional,
            # Exit targets
            "take_profit_price": self.take_profit_price,
            "stop_loss_price": self.stop_loss_price,
            "trailing_stop_pct": self.trailing_stop_pct,
            "trailing_stop_high_water": self.trailing_stop_high_water,
            # Exit
            "exit_order_id": self.exit_order_id,
            "exit_price": self.exit_price,
            "exit_filled_at": self.exit_filled_at.isoformat() if self.exit_filled_at else None,
            "exit_reason": self.exit_reason,
            # P&L
            "realized_pl": self.realized_pl,
            "realized_pl_pct": self.realized_pl_pct,
            "fees": self.fees,
            # Meta
            "status": self.status,
            "execution_mode": self.execution_mode,
            "hold_duration_minutes": self.hold_duration_minutes,
            "notes": self.notes,
            # Timestamps
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_summary_dict(self) -> dict:
        """Compact version for list views."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "realized_pl": self.realized_pl,
            "realized_pl_pct": self.realized_pl_pct,
            "exit_reason": self.exit_reason,
            "status": self.status,
            "hold_duration_minutes": self.hold_duration_minutes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
