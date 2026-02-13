"""
Webhook Alert model for storing trading signals from external providers
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Enum, Index
from sqlalchemy.sql import func
from app.database import Base
import enum


class AlertEventType(str, enum.Enum):
    """Event types for webhook alerts"""
    NEW_SETUP = "new_setup"
    TRIGGER = "trigger"


class AlertDirection(str, enum.Enum):
    """Trade direction for alerts"""
    BUY = "buy"
    SELL = "sell"


class AlertStatus(str, enum.Enum):
    """Status of the alert"""
    ACTIVE = "active"
    TRIGGERED = "triggered"
    EXPIRED = "expired"
    DISMISSED = "dismissed"


class WebhookAlert(Base):
    """
    Model for storing trading signals received via webhooks
    """
    __tablename__ = "webhook_alerts"

    id = Column(Integer, primary_key=True)

    # Webhook provider identification
    provider = Column(String(100), nullable=False, default="default")

    # Core alert data from webhook payload
    setup_id = Column(String(255), nullable=False, unique=True)
    event_type = Column(String(50), nullable=False)  # new_setup or trigger
    symbol = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)  # buy or sell

    # Price levels
    entry_zone_min = Column(Float, nullable=True)
    entry_zone_max = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    tp1 = Column(Float, nullable=True)
    tp2 = Column(Float, nullable=True)
    current_price = Column(Float, nullable=True)

    # Timestamps
    alert_timestamp = Column(DateTime(timezone=True), nullable=False)  # From webhook payload
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Status tracking
    status = Column(String(20), default="active")

    # Store the original raw payload for reference
    raw_payload = Column(JSON, nullable=True)

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_alert_symbol', 'symbol'),
        Index('idx_alert_provider', 'provider'),
        Index('idx_alert_status', 'status'),
        Index('idx_alert_received', 'received_at'),
        Index('idx_alert_event_type', 'event_type'),
    )

    def __repr__(self):
        return f"<WebhookAlert(setup_id={self.setup_id}, symbol={self.symbol}, direction={self.direction})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "provider": self.provider,
            "setup_id": self.setup_id,
            "event_type": self.event_type,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_zone": [self.entry_zone_min, self.entry_zone_max] if self.entry_zone_min else None,
            "stop_loss": self.stop_loss,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "current_price": self.current_price,
            "alert_timestamp": self.alert_timestamp.isoformat() if self.alert_timestamp else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "status": self.status,
        }
