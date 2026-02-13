"""
MRI Snapshot model for historical Macro Risk Index data.
Stores calculated MRI values with confidence, drivers, and component scores.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from app.database import Base


class MRISnapshot(Base):
    """
    Historical MRI (Macro Risk Index) data.
    Captures calculated MRI scores with full explainability.
    """
    __tablename__ = "mri_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    # Core MRI score
    mri_score = Column(Float, nullable=False)  # 0-100
    regime = Column(String(20), nullable=False)  # risk_on, transition, risk_off

    # Confidence & Explainability
    confidence_score = Column(Float, nullable=False)  # 0-100
    shock_flag = Column(Boolean, default=False)  # Rapid change detected

    # Top 3 drivers (JSON array) - sorted by contribution_points desc
    # Each driver includes:
    # - market_id: Polymarket market ID
    # - title: Market question text
    # - category: fed_policy, recession, elections, trade, crypto
    # - probability: Current implied probability (0-100)
    # - weight: This market's weight in category aggregate
    # - contribution_points: Absolute contribution to final MRI score
    # - direction: "risk_on" or "risk_off" (how this market affects MRI)
    drivers = Column(JSON, nullable=True)

    # Component scores (per category)
    fed_policy_score = Column(Float, nullable=True)
    recession_score = Column(Float, nullable=True)
    elections_score = Column(Float, nullable=True)
    trade_score = Column(Float, nullable=True)
    crypto_score = Column(Float, nullable=True)

    # Metadata
    markets_included = Column(Integer, nullable=True)  # Count of markets used
    total_liquidity = Column(Float, nullable=True)  # Aggregate liquidity
    market_data = Column(JSON, nullable=True)  # Raw data for audit

    # Change tracking
    change_1h = Column(Float, nullable=True)
    change_24h = Column(Float, nullable=True)

    # Staleness tracking
    data_stale = Column(Boolean, default=False)
    last_api_success = Column(DateTime(timezone=True), nullable=True)

    # Timestamp
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    def __repr__(self):
        return f"<MRISnapshot(mri={self.mri_score}, regime={self.regime}, confidence={self.confidence_score}, at={self.calculated_at})>"

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "id": self.id,
            "mri_score": self.mri_score,
            "regime": self.regime,
            "regime_label": self._get_regime_label(),
            "confidence_score": self.confidence_score,
            "confidence_label": self._get_confidence_label(),
            "shock_flag": self.shock_flag,
            "drivers": self.drivers,
            "components": {
                "fed_policy": self.fed_policy_score,
                "recession": self.recession_score,
                "elections": self.elections_score,
                "trade": self.trade_score,
                "crypto": self.crypto_score,
            },
            "markets_included": self.markets_included,
            "total_liquidity": self.total_liquidity,
            "change_1h": self.change_1h,
            "change_24h": self.change_24h,
            "data_stale": self.data_stale,
            "last_api_success": self.last_api_success.isoformat() if self.last_api_success else None,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
        }

    def _get_regime_label(self) -> str:
        """Get human-readable regime label"""
        labels = {
            "risk_on": "Risk-On",
            "transition": "Transition",
            "risk_off": "Risk-Off",
        }
        return labels.get(self.regime, self.regime)

    def _get_confidence_label(self) -> str:
        """Get confidence label from numeric score"""
        if self.confidence_score >= 70:
            return "high"
        elif self.confidence_score >= 40:
            return "medium"
        else:
            return "low"
