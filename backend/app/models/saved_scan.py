"""
Saved scan results model
Stores screening results persistently across sessions
"""
from sqlalchemy import Column, Integer, String, DECIMAL, DateTime, Index, JSON, Text
from sqlalchemy.sql import func
from app.database import Base


class SavedScanResult(Base):
    """
    Stores individual stock results from screener scans.
    Results are grouped by scan_type (preset name).
    """
    __tablename__ = "saved_scan_results"

    id = Column(Integer, primary_key=True, index=True)
    scan_type = Column(String(100), nullable=False, index=True)  # e.g., "LEAPS IV Crush Strategy"
    symbol = Column(String(20), nullable=False, index=True)
    company_name = Column(String(255))

    # Stock metrics at time of scan
    score = Column(DECIMAL(10, 4))  # Composite score for ranking
    current_price = Column(DECIMAL(10, 2))
    market_cap = Column(DECIMAL(20, 2))
    iv_rank = Column(DECIMAL(10, 2))
    iv_percentile = Column(DECIMAL(10, 2))

    # Store full stock data as JSON for flexibility
    stock_data = Column(JSON)  # All metrics, options data, etc.

    # Timestamps
    scanned_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_saved_scan_type_symbol', 'scan_type', 'symbol', unique=True),
        Index('idx_saved_scan_type_score', 'scan_type', 'score'),
        Index('idx_saved_scan_scanned_at', 'scanned_at'),
    )

    def __repr__(self):
        return f"<SavedScanResult(scan_type={self.scan_type}, symbol={self.symbol}, score={self.score})>"

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "scan_type": self.scan_type,
            "symbol": self.symbol,
            "company_name": self.company_name,
            "score": float(self.score) if self.score else None,
            "current_price": float(self.current_price) if self.current_price else None,
            "market_cap": float(self.market_cap) if self.market_cap else None,
            "iv_rank": float(self.iv_rank) if self.iv_rank else None,
            "iv_percentile": float(self.iv_percentile) if self.iv_percentile else None,
            "stock_data": self.stock_data,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SavedScanMetadata(Base):
    """
    Tracks metadata for each scan type (when last run, count, etc.)
    """
    __tablename__ = "saved_scan_metadata"

    id = Column(Integer, primary_key=True, index=True)
    scan_type = Column(String(100), nullable=False, unique=True, index=True)
    display_name = Column(String(255))  # User-friendly name
    description = Column(Text)
    stock_count = Column(Integer, default=0)
    last_run_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SavedScanMetadata(scan_type={self.scan_type}, count={self.stock_count})>"

    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            "id": self.id,
            "scan_type": self.scan_type,
            "display_name": self.display_name or self.scan_type,
            "description": self.description,
            "stock_count": self.stock_count,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
