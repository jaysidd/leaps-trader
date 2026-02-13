"""
Screening results model
"""
from sqlalchemy import Column, Integer, String, DECIMAL, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class ScreeningResult(Base):
    __tablename__ = "screening_results"

    id = Column(Integer, primary_key=True, index=True)
    screen_name = Column(String(255))
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    score = Column(DECIMAL(10, 4))  # Composite score for ranking
    screened_at = Column(DateTime(timezone=True), server_default=func.now())
    criteria_met = Column(JSON)  # Store which criteria were met
    metrics = Column(JSON)  # Store all calculated metrics

    # Relationship
    stock = relationship("Stock", back_populates="screening_results")

    # Indexes
    __table_args__ = (
        Index('idx_screen_date', 'screen_name', 'screened_at'),
        Index('idx_score', 'score', postgresql_ops={'score': 'DESC'}),
    )

    def __repr__(self):
        return f"<ScreeningResult(screen={self.screen_name}, stock_id={self.stock_id}, score={self.score})>"
