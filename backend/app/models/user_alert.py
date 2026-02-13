"""
User Alert model for dynamic, condition-based alerts
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, Enum, Index
from sqlalchemy.sql import func
from app.database import Base
import enum


class AlertType(str, enum.Enum):
    """Types of alerts users can create"""
    # Ticker-level alerts
    IV_RANK_BELOW = "iv_rank_below"          # IV Rank drops below threshold
    IV_RANK_ABOVE = "iv_rank_above"          # IV Rank rises above threshold
    PRICE_ABOVE = "price_above"              # Price crosses above level
    PRICE_BELOW = "price_below"              # Price crosses below level
    PRICE_CROSS_SMA = "price_cross_sma"      # Price crosses SMA (50/200)
    RSI_OVERSOLD = "rsi_oversold"            # RSI drops below threshold
    RSI_OVERBOUGHT = "rsi_overbought"        # RSI rises above threshold
    SCREENING_MATCH = "screening_match"       # Stock passes all screening criteria
    EARNINGS_APPROACHING = "earnings_approaching"  # Earnings within X days
    LEAPS_AVAILABLE = "leaps_available"      # New LEAPS expiration available

    # Macro alert types (Polymarket-driven)
    MRI_REGIME_CHANGE = "mri_regime_change"                # MRI regime transition
    MACRO_NARRATIVE_MOMENTUM = "macro_narrative_momentum"  # Significant odds shift in category
    MACRO_DIVERGENCE_BULLISH = "macro_divergence_bullish"  # Predictions bearish but proxy stable
    MACRO_DIVERGENCE_BEARISH = "macro_divergence_bearish"  # Predictions bullish but proxy stable

    # Catalyst alert types (Macro Intelligence)
    CATALYST_LIQUIDITY_REGIME_CHANGE = "catalyst_liquidity_regime_change"  # Liquidity regime transition
    CATALYST_CREDIT_STRESS_SPIKE = "catalyst_credit_stress_spike"          # Credit stress increase (Tier 2)
    CATALYST_VOL_REGIME_CHANGE = "catalyst_vol_regime_change"              # Volatility regime change (Tier 2)
    CATALYST_EVENT_DENSITY_HIGH = "catalyst_event_density_high"            # High event density week (Tier 2)
    TICKER_EARNINGS_WITHIN_DAYS = "ticker_earnings_within_days"            # Earnings approaching for ticker
    TICKER_OPTIONS_FRAGILE_POSITIONING = "ticker_options_fragile_positioning"  # Options fragility alert


class AlertFrequency(str, enum.Enum):
    """How often to check alert conditions"""
    ONCE = "once"           # Trigger once then deactivate
    DAILY = "daily"         # Check once per day
    CONTINUOUS = "continuous"  # Check every scan cycle


class NotificationChannel(str, enum.Enum):
    """Where to send notifications"""
    IN_APP = "in_app"
    TELEGRAM = "telegram"
    EMAIL = "email"


class UserAlert(Base):
    """
    Model for user-created dynamic alerts
    """
    __tablename__ = "user_alerts"

    id = Column(Integer, primary_key=True)

    # Alert identification
    name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)

    # Target
    symbol = Column(String(20), nullable=True)  # Null = apply to all screened stocks
    watchlist = Column(String(100), nullable=True)  # Optional watchlist name

    # Alert condition
    alert_type = Column(String(50), nullable=False)
    threshold_value = Column(Float, nullable=True)  # e.g., IV Rank < 30
    threshold_value_2 = Column(Float, nullable=True)  # For range conditions
    sma_period = Column(Integer, nullable=True)  # For SMA-based alerts (50, 200)

    # Screening criteria (for screening_match type)
    screening_criteria = Column(JSON, nullable=True)

    # Frequency and status
    frequency = Column(String(20), default="once")
    is_active = Column(Boolean, default=True)

    # Notification settings
    notification_channels = Column(JSON, default=["in_app"])  # List of channels
    telegram_chat_id = Column(String(100), nullable=True)

    # Alert scope and parameters (for macro alerts)
    alert_scope = Column(String(20), default="ticker")  # "ticker" | "macro"
    alert_params = Column(JSON, nullable=True)  # Macro-specific parameters
    # For MRI_REGIME_CHANGE: {"mri_threshold_low": 33, "mri_threshold_high": 67}
    # For MACRO_NARRATIVE_MOMENTUM: {"category": "recession", "threshold_pct": 10.0, "timeframe": "24h"}
    # For MACRO_DIVERGENCE_*: {"proxy_symbol": "SPY", "divergence_threshold": 10.0, "persistence_checks": 2}

    # Alert severity
    severity = Column(String(20), default="warning")  # info | warning | critical

    # Deduplication & cooldown
    cooldown_minutes = Column(Integer, default=60)
    dedupe_key = Column(String(255), nullable=True)  # market_id + direction + window
    last_dedupe_at = Column(DateTime(timezone=True), nullable=True)

    # Tracking
    times_triggered = Column(Integer, default=0)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_triggered_value = Column(Float, nullable=True)  # Value that triggered alert

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration

    # Indexes
    __table_args__ = (
        Index('idx_user_alert_symbol', 'symbol'),
        Index('idx_user_alert_active', 'is_active'),
        Index('idx_user_alert_type', 'alert_type'),
    )

    def __repr__(self):
        return f"<UserAlert(id={self.id}, name={self.name}, type={self.alert_type}, symbol={self.symbol})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "symbol": self.symbol,
            "watchlist": self.watchlist,
            "alert_type": self.alert_type,
            "threshold_value": self.threshold_value,
            "threshold_value_2": self.threshold_value_2,
            "sma_period": self.sma_period,
            "screening_criteria": self.screening_criteria,
            "frequency": self.frequency,
            "is_active": self.is_active,
            "notification_channels": self.notification_channels,
            "alert_scope": self.alert_scope,
            "alert_params": self.alert_params,
            "severity": self.severity,
            "cooldown_minutes": self.cooldown_minutes,
            "times_triggered": self.times_triggered,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "last_triggered_value": self.last_triggered_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class AlertNotification(Base):
    """
    Model for storing triggered alert notifications
    """
    __tablename__ = "alert_notifications"

    id = Column(Integer, primary_key=True)

    # Link to alert
    alert_id = Column(Integer, nullable=False)  # indexed via idx_notification_alert
    alert_name = Column(String(255), nullable=False)

    # Trigger details
    symbol = Column(String(20), nullable=False)
    alert_type = Column(String(50), nullable=False)
    triggered_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)
    message = Column(String(1000), nullable=False)

    # Delivery status
    channels_sent = Column(JSON, default=[])  # Which channels were notified
    is_read = Column(Boolean, default=False)

    # Timestamps
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index('idx_notification_alert', 'alert_id'),
        Index('idx_notification_read', 'is_read'),
        Index('idx_notification_triggered', 'triggered_at'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "alert_name": self.alert_name,
            "symbol": self.symbol,
            "alert_type": self.alert_type,
            "triggered_value": self.triggered_value,
            "threshold_value": self.threshold_value,
            "message": self.message,
            "channels_sent": self.channels_sent,
            "is_read": self.is_read,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
        }
