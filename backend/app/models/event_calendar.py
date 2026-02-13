"""
EventCalendar model for unified macro and earnings events.
Supports Event Density calculation and per-ticker earnings risk.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base


class EventCalendar(Base):
    """
    Unified calendar for macro events and earnings.

    Event types:
    - Macro: CPI, PPI, FOMC, Jobs, TreasuryAuction, GDP, etc.
    - Corporate: Earnings, ExDividend, Split, etc.

    Used for:
    - Event Density Score (macro-level)
    - Earnings Risk Score (ticker-level)
    - Timeline displays
    """
    __tablename__ = "event_calendar"

    id = Column(Integer, primary_key=True, index=True)

    # Event identification
    event_type = Column(String(50), nullable=False)
    # Macro types: CPI, PPI, FOMC, FOMC_MINUTES, JOBS, GDP, RETAIL_SALES,
    #              TREASURY_AUCTION, ISM, HOUSING, PCE, CONSUMER_SENTIMENT
    # Corporate: EARNINGS, EX_DIVIDEND, SPLIT

    # Symbol (NULL for macro events)
    symbol = Column(String(20), nullable=True)

    # Timing
    event_datetime = Column(DateTime(timezone=True), nullable=False)

    # Importance for Event Density weighting
    # high = 3 points, med = 2 points, low = 1 point
    importance = Column(String(10), nullable=False)  # low, med, high

    # Optional estimated volatility impact (0-100)
    estimated_vol_impact = Column(Float, nullable=True)

    # Data source
    source = Column(String(100), nullable=True)

    # Additional notes (e.g., "YoY, MoM headline/core" for CPI)
    notes = Column(String(500), nullable=True)

    # Region (for filtering)
    region = Column(String(20), default="US")

    # For earnings: session timing
    session = Column(String(20), nullable=True)  # pre_market, after_market, during_market

    # Timestamp of when this event was added/updated
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('idx_event_datetime', 'event_datetime'),
        Index('idx_event_symbol_datetime', 'symbol', 'event_datetime'),
        Index('idx_event_type_datetime', 'event_type', 'event_datetime'),
    )

    def __repr__(self):
        if self.symbol:
            return f"<EventCalendar({self.event_type} for {self.symbol} at {self.event_datetime})>"
        return f"<EventCalendar({self.event_type} at {self.event_datetime})>"

    def to_dict(self):
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "event_type": self.event_type,
            "event_type_display": self._get_event_type_display(),
            "symbol": self.symbol,
            "event_datetime": self.event_datetime.isoformat() if self.event_datetime else None,
            "importance": self.importance,
            "importance_points": self._get_importance_points(),
            "estimated_vol_impact": self.estimated_vol_impact,
            "source": self.source,
            "notes": self.notes,
            "region": self.region,
            "session": self.session,
        }

    def _get_event_type_display(self) -> str:
        """Get human-readable event type."""
        displays = {
            # Macro
            "CPI": "CPI (Inflation)",
            "PPI": "PPI (Producer Prices)",
            "FOMC": "FOMC Rate Decision",
            "FOMC_MINUTES": "FOMC Minutes",
            "JOBS": "Jobs Report",
            "GDP": "GDP",
            "RETAIL_SALES": "Retail Sales",
            "TREASURY_AUCTION": "Treasury Auction",
            "ISM": "ISM Manufacturing",
            "ISM_SERVICES": "ISM Services",
            "HOUSING": "Housing Data",
            "PCE": "PCE (Fed's Inflation)",
            "CONSUMER_SENTIMENT": "Consumer Sentiment",
            "JOBLESS_CLAIMS": "Jobless Claims",
            # Corporate
            "EARNINGS": "Earnings Report",
            "EX_DIVIDEND": "Ex-Dividend",
            "SPLIT": "Stock Split",
        }
        return displays.get(self.event_type, self.event_type)

    def _get_importance_points(self) -> int:
        """Get importance points for Event Density calculation."""
        points = {
            "high": 3,
            "med": 2,
            "low": 1,
        }
        return points.get(self.importance, 1)

    @classmethod
    def get_importance_for_type(cls, event_type: str) -> str:
        """Get default importance for an event type."""
        high_importance = {
            "CPI", "FOMC", "JOBS", "GDP", "PCE", "EARNINGS"
        }
        medium_importance = {
            "PPI", "FOMC_MINUTES", "RETAIL_SALES", "ISM", "ISM_SERVICES",
            "CONSUMER_SENTIMENT", "HOUSING"
        }

        if event_type in high_importance:
            return "high"
        if event_type in medium_importance:
            return "med"
        return "low"
