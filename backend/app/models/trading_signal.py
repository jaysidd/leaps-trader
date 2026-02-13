"""
Trading Signal model for storing generated buy/sell signals
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text, Boolean, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class SignalDirection(str, enum.Enum):
    """Trade direction"""
    BUY = "buy"
    SELL = "sell"


class SignalStatus(str, enum.Enum):
    """Status of the signal"""
    ACTIVE = "active"
    EXECUTED = "executed"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class TradingSignal(Base):
    """
    Model for storing generated trading signals with full analysis details.
    Based on SignalAlert.md format.
    """
    __tablename__ = "trading_signals"

    id = Column(Integer, primary_key=True, index=True)

    # Link to queue item (optional - signals can come from webhooks too)
    queue_id = Column(Integer, ForeignKey('signal_queues.id'), nullable=True)

    # Core signal data
    symbol = Column(String(20), nullable=False)  # indexed via idx_signal_symbol
    name = Column(String(255), nullable=True)
    timeframe = Column(String(10), nullable=False)  # 5m, 15m, 1h, 1d
    strategy = Column(String(50), nullable=False)  # orb_breakout_long, vwap_pullback_long, etc.
    direction = Column(String(10), nullable=False)  # buy, sell
    confidence_score = Column(Float, nullable=True)  # 0-100

    # Trade Parameters (from SignalAlert.md)
    entry_price = Column(Float, nullable=True)
    entry_zone_low = Column(Float, nullable=True)
    entry_zone_high = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    target_1 = Column(Float, nullable=True)
    target_2 = Column(Float, nullable=True)
    risk_reward_ratio = Column(Float, nullable=True)

    # AI Journaling - Analysis Details
    ai_reasoning = Column(Text, nullable=True)  # Conversational summary of why signal triggered
    stop_loss_logic = Column(Text, nullable=True)  # Explanation of stop placement
    target_logic = Column(Text, nullable=True)  # Explanation of target placement

    # Invalidation conditions (JSON array of conditions)
    invalidation_conditions = Column(JSON, nullable=True)

    # Institutional Indicators (from SignalAlert.md)
    institutional_data = Column(JSON, nullable=True)
    # Example: {
    #   "vwap": 185.50,
    #   "vwap_position": "above",
    #   "opening_range_high": 186.00,
    #   "opening_range_low": 184.00,
    #   "market_structure": "bullish",
    #   "premium_discount": "discount",
    #   "order_blocks": null,
    #   "fair_value_gap": null,
    #   "liquidity_pools": "below 184.00",
    #   "session": "NY",
    #   "atr": 2.50
    # }

    # Order Flow Analysis
    order_flow_data = Column(JSON, nullable=True)
    # Example: {
    #   "delta": "positive",
    #   "absorption": false,
    #   "imbalances": "buy",
    #   "volume_profile_poc": 185.25,
    #   "tape_flow": "large_lots_buying",
    #   "effort_vs_result": "confirmed"
    # }

    # Technical Snapshot at signal time
    technical_snapshot = Column(JSON, nullable=True)
    # Example: {
    #   "rsi": 62.5,
    #   "macd_histogram": 0.15,
    #   "ema8": 185.30,
    #   "ema21": 184.90,
    #   "sma50": 182.00,
    #   "sma200": 175.00,
    #   "atr_percent": 0.65,
    #   "rvol": 1.45,
    #   "volume_spike": true
    # }

    # AI Deep Analysis (auto or on-demand result from Claude)
    ai_deep_analysis = Column(JSON, nullable=True)
    ai_deep_analysis_at = Column(DateTime(timezone=True), nullable=True)

    # Status tracking
    status = Column(String(20), default="active")
    is_read = Column(Boolean, default=False)
    notification_sent_telegram = Column(Boolean, default=False)
    notification_sent_sound = Column(Boolean, default=False)

    # Trade execution tracking
    trade_executed = Column(Boolean, default=False)
    trade_execution_id = Column(String(100), nullable=True)  # Alpaca order ID

    # Timestamps
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Pre-trade AI validation (Layer 4 of intelligence pipeline)
    validation_status = Column(String(20), nullable=True)  # validated, rejected, pending_validation
    validation_reasoning = Column(Text, nullable=True)  # AI reasoning for go/no-go
    validated_at = Column(DateTime(timezone=True), nullable=True)

    # Source tracking
    source = Column(String(50), default="signal_engine")  # signal_engine, tradingview_webhook

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_signal_symbol', 'symbol'),
        Index('idx_signal_status', 'status'),
        Index('idx_signal_direction', 'direction'),
        Index('idx_signal_generated', 'generated_at'),
        Index('idx_signal_is_read', 'is_read'),
        Index('idx_signal_timeframe', 'timeframe'),
        # Composite: unread active signals (bell icon badge query)
        Index('idx_signal_read_status', 'is_read', 'status'),
    )

    def __repr__(self):
        return f"<TradingSignal(symbol={self.symbol}, direction={self.direction}, confidence={self.confidence_score})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "queue_id": self.queue_id,
            "symbol": self.symbol,
            "name": self.name,
            "timeframe": self.timeframe,
            "strategy": self.strategy,
            "direction": self.direction,
            "confidence_score": self.confidence_score,
            # Trade parameters
            "entry_price": self.entry_price,
            "entry_zone": {
                "low": self.entry_zone_low,
                "high": self.entry_zone_high
            } if self.entry_zone_low else None,
            "stop_loss": self.stop_loss,
            "target_1": self.target_1,
            "target_2": self.target_2,
            "risk_reward_ratio": self.risk_reward_ratio,
            # AI Journaling
            "ai_reasoning": self.ai_reasoning,
            "stop_loss_logic": self.stop_loss_logic,
            "target_logic": self.target_logic,
            "invalidation_conditions": self.invalidation_conditions,
            # Analysis data
            "institutional_data": self.institutional_data,
            "order_flow_data": self.order_flow_data,
            "technical_snapshot": self.technical_snapshot,
            # AI Deep Analysis
            "ai_deep_analysis": self.ai_deep_analysis,
            "ai_deep_analysis_at": self.ai_deep_analysis_at.isoformat() if self.ai_deep_analysis_at else None,
            # Status
            "status": self.status,
            "is_read": self.is_read,
            "notification_sent_telegram": self.notification_sent_telegram,
            "trade_executed": self.trade_executed,
            "trade_execution_id": self.trade_execution_id,
            # Timestamps
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source": self.source,
            # Pre-trade validation
            "validation_status": self.validation_status,
            "validation_reasoning": self.validation_reasoning,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
        }

    def to_summary_dict(self):
        """Compact version for list views"""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "timeframe": self.timeframe,
            "strategy": self.strategy,
            "direction": self.direction,
            "confidence_score": self.confidence_score,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "target_1": self.target_1,
            "risk_reward_ratio": self.risk_reward_ratio,
            "status": self.status,
            "is_read": self.is_read,
            "trade_executed": self.trade_executed,
            "validation_status": self.validation_status,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }
