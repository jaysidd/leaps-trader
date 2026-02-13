"""
Broker Connection model for storing connected broker accounts
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, Index
from sqlalchemy.sql import func
from app.database import Base
import enum


class BrokerType(str, enum.Enum):
    """Supported broker types"""
    ROBINHOOD = "robinhood"
    ALPACA = "alpaca"
    TD_AMERITRADE = "td_ameritrade"
    WEBULL = "webull"
    INTERACTIVE_BROKERS = "interactive_brokers"


class ConnectionStatus(str, enum.Enum):
    """Broker connection status"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING_MFA = "pending_mfa"
    EXPIRED = "expired"
    SESSION_EXPIRED = "session_expired"


class BrokerConnection(Base):
    """
    Model for storing broker account connections.
    Supports multiple brokers per user for portfolio aggregation.
    """
    __tablename__ = "broker_connections"

    id = Column(Integer, primary_key=True, index=True)

    # Broker identification
    broker_type = Column(String(50), nullable=False)  # robinhood, alpaca, etc.
    account_id = Column(String(100), nullable=True)  # Broker's account ID
    account_name = Column(String(255), nullable=True)  # User-friendly name

    # Authentication (encrypted in production)
    access_token = Column(String(1000), nullable=True)
    refresh_token = Column(String(1000), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # For username/password auth (Robinhood)
    username = Column(String(255), nullable=True)
    device_token = Column(String(255), nullable=True)
    encrypted_password = Column(String(1000), nullable=True)  # Fernet-encrypted password for auto re-login

    # Connection status
    status = Column(String(20), default="disconnected")
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(500), nullable=True)

    # Account info (cached)
    account_type = Column(String(50), nullable=True)  # margin, cash, etc.
    buying_power = Column(Float, nullable=True)
    portfolio_value = Column(Float, nullable=True)
    cash_balance = Column(Float, nullable=True)

    # Preferences
    is_primary = Column(Boolean, default=False)  # Primary account for trading
    auto_sync = Column(Boolean, default=True)  # Auto-sync positions

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index('idx_broker_type', 'broker_type'),
        Index('idx_broker_status', 'status'),
        Index('idx_broker_primary', 'is_primary'),
    )

    def __repr__(self):
        return f"<BrokerConnection(broker={self.broker_type}, account={self.account_name}, status={self.status})>"

    def to_dict(self):
        """Convert to dictionary for API responses (excludes sensitive data)"""
        return {
            "id": self.id,
            "broker_type": self.broker_type,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "status": self.status,
            "account_type": self.account_type,
            "buying_power": self.buying_power,
            "portfolio_value": self.portfolio_value,
            "cash_balance": self.cash_balance,
            "is_primary": self.is_primary,
            "auto_sync": self.auto_sync,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PortfolioPosition(Base):
    """
    Model for storing portfolio positions from connected brokers.
    Positions are synced from broker accounts.
    """
    __tablename__ = "portfolio_positions"

    id = Column(Integer, primary_key=True, index=True)

    # Link to broker connection
    broker_connection_id = Column(Integer, nullable=False, index=True)

    # Position details
    symbol = Column(String(20), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    quantity = Column(Float, nullable=False)
    average_cost = Column(Float, nullable=True)

    # Current values (updated on sync)
    current_price = Column(Float, nullable=True)
    market_value = Column(Float, nullable=True)

    # P/L calculations
    unrealized_pl = Column(Float, nullable=True)
    unrealized_pl_percent = Column(Float, nullable=True)
    day_change = Column(Float, nullable=True)
    day_change_percent = Column(Float, nullable=True)

    # Position type
    asset_type = Column(String(20), default="stock")  # stock, option, crypto, etc.

    # Option-specific fields (if asset_type is option)
    option_type = Column(String(10), nullable=True)  # call, put
    strike_price = Column(Float, nullable=True)
    expiration_date = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Indexes
    __table_args__ = (
        Index('idx_position_symbol', 'symbol'),
        Index('idx_position_broker', 'broker_connection_id'),
        Index('idx_position_asset_type', 'asset_type'),
    )

    def __repr__(self):
        return f"<PortfolioPosition(symbol={self.symbol}, qty={self.quantity}, value={self.market_value})>"

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "broker_connection_id": self.broker_connection_id,
            "symbol": self.symbol,
            "name": self.name,
            "quantity": self.quantity,
            "average_cost": self.average_cost,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pl": self.unrealized_pl,
            "unrealized_pl_percent": self.unrealized_pl_percent,
            "day_change": self.day_change,
            "day_change_percent": self.day_change_percent,
            "asset_type": self.asset_type,
            "option_type": self.option_type,
            "strike_price": self.strike_price,
            "expiration_date": self.expiration_date.isoformat() if self.expiration_date else None,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }


class PortfolioHistory(Base):
    """
    Model for tracking portfolio value over time for charts.
    """
    __tablename__ = "portfolio_history"

    id = Column(Integer, primary_key=True, index=True)

    # Link to broker connection (optional - null means aggregated total)
    broker_connection_id = Column(Integer, nullable=True, index=True)

    # Snapshot data
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    portfolio_value = Column(Float, nullable=False)
    cash_balance = Column(Float, nullable=True)
    invested_value = Column(Float, nullable=True)  # Value in positions

    # Daily changes
    day_change = Column(Float, nullable=True)
    day_change_percent = Column(Float, nullable=True)

    # Cumulative performance
    total_return = Column(Float, nullable=True)
    total_return_percent = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index('idx_history_date', 'date'),
        Index('idx_history_broker', 'broker_connection_id'),
    )

    def to_dict(self):
        return {
            "date": self.date.isoformat() if self.date else None,
            "portfolio_value": self.portfolio_value,
            "cash_balance": self.cash_balance,
            "invested_value": self.invested_value,
            "day_change": self.day_change,
            "day_change_percent": self.day_change_percent,
            "total_return": self.total_return,
            "total_return_percent": self.total_return_percent,
        }
