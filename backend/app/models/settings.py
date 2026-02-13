"""
Application settings model - stores non-sensitive configuration in database
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.database import Base


class AppSettings(Base):
    """
    Stores application settings that can be modified via UI.

    Sensitive data (API keys) are stored in .env file, not here.
    This table stores:
    - Screening defaults
    - Rate limits
    - Cache TTLs
    - Feature flags
    - UI preferences
    """
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)  # Stored as JSON string for complex values
    value_type = Column(String(20), default="string")  # string, int, float, bool, json
    category = Column(String(50), index=True)  # screening, cache, rate_limit, feature, ui
    description = Column(Text)
    is_sensitive = Column(Boolean, default=False)  # If true, value is masked in UI
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AppSettings(key='{self.key}', category='{self.category}')>"


class ApiKeyStatus(Base):
    """
    Tracks API key configuration status without storing actual keys.

    Actual keys are in .env file. This just tracks:
    - Whether a key is configured
    - Last validation time
    - Usage statistics
    """
    __tablename__ = "api_key_status"

    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String(50), unique=True, nullable=False, index=True)  # yahoo, finviz, tastytrade, anthropic, telegram
    is_configured = Column(Boolean, default=False)
    is_valid = Column(Boolean, default=False)
    last_validated = Column(DateTime(timezone=True))
    last_used = Column(DateTime(timezone=True))
    usage_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text)
    daily_usage = Column(Integer, default=0)
    daily_limit = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ApiKeyStatus(service='{self.service_name}', configured={self.is_configured})>"
