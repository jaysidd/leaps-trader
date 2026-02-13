"""
Technical indicators model
"""
from sqlalchemy import Column, Integer, Date, DECIMAL, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.database import Base


class TechnicalIndicator(Base):
    __tablename__ = "technical_indicators"

    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    sma_20 = Column(DECIMAL(12, 4))
    sma_50 = Column(DECIMAL(12, 4))
    sma_200 = Column(DECIMAL(12, 4))
    ema_12 = Column(DECIMAL(12, 4))
    ema_26 = Column(DECIMAL(12, 4))
    rsi_14 = Column(DECIMAL(10, 4))
    macd = Column(DECIMAL(12, 4))
    macd_signal = Column(DECIMAL(12, 4))
    macd_histogram = Column(DECIMAL(12, 4))
    bollinger_upper = Column(DECIMAL(12, 4))
    bollinger_middle = Column(DECIMAL(12, 4))
    bollinger_lower = Column(DECIMAL(12, 4))
    atr_14 = Column(DECIMAL(12, 4))
    adx_14 = Column(DECIMAL(10, 4))

    # Relationship
    stock = relationship("Stock", back_populates="technical_indicators")

    # Constraints
    __table_args__ = (
        UniqueConstraint('stock_id', 'date', name='uix_stock_date_tech'),
        Index('idx_stock_date_tech', 'stock_id', 'date'),
    )

    def __repr__(self):
        return f"<TechnicalIndicator(stock_id={self.stock_id}, date={self.date}, rsi={self.rsi_14})>"
