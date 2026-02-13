"""
Polymarket Market Snapshot model for per-market time-series data.
Used for momentum detection and divergence tracking.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Index
from sqlalchemy.sql import func
from app.database import Base


class PolymarketMarketSnapshot(Base):
    """
    Per-market time-series data for momentum and divergence detection.
    Stored every 15-30 minutes for tracked markets.
    """
    __tablename__ = "polymarket_market_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    # Market identification
    market_id = Column(String(100), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    title = Column(String(500), nullable=False)

    # Probability data
    implied_probability = Column(Float, nullable=False)  # 0-100

    # Quality metrics
    quality_score = Column(Float, nullable=False)  # 0-1
    liquidity = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    volume_24h = Column(Float, nullable=True)

    # Time to resolution
    end_date = Column(DateTime(timezone=True), nullable=True)
    days_to_resolution = Column(Integer, nullable=True)

    # Snapshot timestamp
    snapshot_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes for time-series queries
    __table_args__ = (
        # For queries: "get history for market X" - sorted by time DESC
        Index('idx_market_snapshot_market_time', 'market_id', 'snapshot_at'),
        # For queries: "get all markets in category Y at time Z" - sorted by time DESC
        Index('idx_market_snapshot_category_time', 'category', 'snapshot_at'),
    )

    def __repr__(self):
        return f"<PolymarketMarketSnapshot(market_id={self.market_id}, prob={self.implied_probability}, at={self.snapshot_at})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "market_id": self.market_id,
            "category": self.category,
            "title": self.title,
            "implied_probability": self.implied_probability,
            "quality_score": self.quality_score,
            "liquidity": self.liquidity,
            "volume": self.volume,
            "volume_24h": self.volume_24h,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "days_to_resolution": self.days_to_resolution,
            "snapshot_at": self.snapshot_at.isoformat() if self.snapshot_at else None,
        }
