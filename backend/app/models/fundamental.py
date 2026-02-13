"""
Fundamental data model
"""
from sqlalchemy import Column, Integer, Date, DECIMAL, BigInteger, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Fundamental(Base):
    __tablename__ = "fundamentals"

    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    quarter_end_date = Column(Date)
    revenue = Column(BigInteger)
    net_income = Column(BigInteger)
    eps = Column(DECIMAL(10, 4))
    pe_ratio = Column(DECIMAL(10, 2))
    peg_ratio = Column(DECIMAL(10, 2))
    revenue_growth_yoy = Column(DECIMAL(10, 4))  # Year-over-year growth
    earnings_growth_yoy = Column(DECIMAL(10, 4))
    debt_to_equity = Column(DECIMAL(10, 4))
    current_ratio = Column(DECIMAL(10, 4))
    roa = Column(DECIMAL(10, 4))  # Return on assets
    roe = Column(DECIMAL(10, 4))  # Return on equity
    last_updated = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    stock = relationship("Stock", back_populates="fundamentals")

    # Constraints
    __table_args__ = (
        UniqueConstraint('stock_id', 'quarter_end_date', name='uix_stock_quarter'),
        Index('idx_stock_quarter', 'stock_id', 'quarter_end_date'),
    )

    def __repr__(self):
        return f"<Fundamental(stock_id={self.stock_id}, quarter={self.quarter_end_date}, revenue={self.revenue})>"
