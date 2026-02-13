"""
Price history model
"""
from sqlalchemy import Column, Integer, Date, DECIMAL, BigInteger, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.database import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    open = Column(DECIMAL(12, 4))
    high = Column(DECIMAL(12, 4))
    low = Column(DECIMAL(12, 4))
    close = Column(DECIMAL(12, 4))
    adjusted_close = Column(DECIMAL(12, 4))
    volume = Column(BigInteger)

    # Relationship
    stock = relationship("Stock", back_populates="price_history")

    # Constraints
    __table_args__ = (
        UniqueConstraint('stock_id', 'date', name='uix_stock_date'),
        Index('idx_stock_date', 'stock_id', 'date'),
    )

    def __repr__(self):
        return f"<PriceHistory(stock_id={self.stock_id}, date={self.date}, close={self.close})>"
