"""
Signal Queue model for tracking stocks being monitored for trading signals
"""
from sqlalchemy import Column, Integer, String, DateTime, Index, Boolean, Text
from sqlalchemy.sql import func
from app.database import Base
import enum


class QueueStatus(str, enum.Enum):
    """Status of queue item"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    EXPIRED = "expired"


class SignalQueue(Base):
    """
    Model for stocks being monitored for trading signals.
    Users add stocks from scan results to this queue for signal processing.
    """
    __tablename__ = "signal_queues"

    id = Column(Integer, primary_key=True)

    # Stock identification
    symbol = Column(String(20), nullable=False)  # indexed via idx_queue_symbol
    name = Column(String(255), nullable=True)

    # Signal configuration
    timeframe = Column(String(10), nullable=False, default="5m")  # 5m, 15m, 1h, 1d
    strategy = Column(String(50), nullable=True)  # orb_breakout, vwap_pullback, range_breakout, trend_following, mean_reversion, auto
    cap_size = Column(String(20), nullable=True)  # large_cap, small_cap

    # Monitoring state
    status = Column(String(20), default="active")
    times_checked = Column(Integer, default=0)
    signals_generated = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Auto-expire after market close

    # Evaluation tracking
    last_eval_bar_key = Column(String(100), nullable=True)  # same-bar short-circuit key

    # Source tracking
    source = Column(String(50), nullable=True)  # scan, manual, watchlist, auto_process

    # Strategy selection metadata (populated by StrategySelector)
    confidence_level = Column(String(10), nullable=True)  # HIGH, MEDIUM, LOW
    strategy_reasoning = Column(Text, nullable=True)  # Why this timeframe was selected

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_queue_symbol', 'symbol'),
        Index('idx_queue_status', 'status'),
        Index('idx_queue_timeframe', 'timeframe'),
        Index('idx_queue_created', 'created_at'),
    )

    def __repr__(self):
        return f"<SignalQueue(symbol={self.symbol}, timeframe={self.timeframe}, status={self.status})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "timeframe": self.timeframe,
            "strategy": self.strategy,
            "cap_size": self.cap_size,
            "status": self.status,
            "times_checked": self.times_checked,
            "signals_generated": self.signals_generated,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source": self.source,
            "last_eval_bar_key": self.last_eval_bar_key,
            "confidence_level": self.confidence_level,
            "strategy_reasoning": self.strategy_reasoning,
        }
