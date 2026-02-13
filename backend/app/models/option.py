"""
Options data model
"""
from sqlalchemy import Column, Integer, Date, DECIMAL, String, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.database import Base


class OptionData(Base):
    __tablename__ = "options_data"

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    expiration_date = Column(Date, nullable=False)  # indexed via idx_exp_date
    strike = Column(DECIMAL(12, 4), nullable=False)
    option_type = Column(String(4), nullable=False)  # 'call' or 'put'
    last_price = Column(DECIMAL(12, 4))
    bid = Column(DECIMAL(12, 4))
    ask = Column(DECIMAL(12, 4))
    volume = Column(Integer)
    open_interest = Column(Integer)
    implied_volatility = Column(DECIMAL(10, 6))
    delta = Column(DECIMAL(10, 6))
    gamma = Column(DECIMAL(10, 6))
    theta = Column(DECIMAL(10, 6))
    vega = Column(DECIMAL(10, 6))
    rho = Column(DECIMAL(10, 6))
    data_date = Column(Date, nullable=False, index=True)

    # Relationship
    stock = relationship("Stock", back_populates="options_data")

    # Constraints
    __table_args__ = (
        UniqueConstraint('stock_id', 'expiration_date', 'strike', 'option_type', 'data_date',
                        name='uix_stock_exp_strike_type_date'),
        Index('idx_stock_exp', 'stock_id', 'expiration_date'),
        Index('idx_exp_date', 'expiration_date'),
    )

    def __repr__(self):
        return f"<OptionData(stock_id={self.stock_id}, exp={self.expiration_date}, strike={self.strike}, type={self.option_type})>"
