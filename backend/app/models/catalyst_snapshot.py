"""
CatalystSnapshot model for macro-level catalyst time-series data.
Stores computed catalyst outputs for audit, charts, and Trade Readiness calculation.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, Index
from sqlalchemy.sql import func
from app.database import Base


class CatalystSnapshot(Base):
    """
    Macro-level catalyst time-series data.

    Stores computed catalyst scores from all tiers:
    - Tier 1: Liquidity, (Earnings aggregated), Options Positioning (index)
    - Tier 2: Credit Stress, Volatility Structure, Event Density
    - Tier 3: Cross-Asset Confirmation

    Also stores the computed Trade Readiness Score.
    """
    __tablename__ = "catalyst_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # ==========================================================================
    # Component Scores (0-100)
    # ==========================================================================

    # Tier 1
    liquidity_score = Column(Float, nullable=True)
    options_positioning_score = Column(Float, nullable=True)  # Index-level (SPY/QQQ)

    # Tier 2 (future phases)
    credit_stress_score = Column(Float, nullable=True)
    vol_structure_score = Column(Float, nullable=True)
    event_density_score = Column(Float, nullable=True)

    # Tier 3 (future phases)
    cross_asset_confirmation_score = Column(Float, nullable=True)

    # ==========================================================================
    # Trade Readiness Rollup
    # ==========================================================================

    trade_readiness_score = Column(Float, nullable=True)  # 0-100
    readiness_label = Column(String(20), nullable=True)  # green/yellow/red
    readiness_is_partial = Column(Boolean, default=True)  # True until all Tiers implemented

    # ==========================================================================
    # Explainability (Non-Negotiable per spec)
    # ==========================================================================

    # Confidence scores per component (JSON dict)
    # {
    #     "liquidity": 85.0,
    #     "options_positioning": 72.0,
    #     ...
    # }
    confidence_by_component = Column(JSON, nullable=True)

    # Top drivers for each component (JSON dict of lists)
    # {
    #     "liquidity": [
    #         {"name": "fed_balance_sheet", "value": -1.2, "contribution": 12.5, "direction": "bearish"},
    #         ...
    #     ],
    #     "trade_readiness": [
    #         {"name": "MRI", "value": 45.0, "contribution": 18.0, "direction": "bullish"},
    #         ...
    #     ]
    # }
    drivers = Column(JSON, nullable=True)

    # ==========================================================================
    # Raw Metrics (for audit and debugging)
    # ==========================================================================

    # Raw liquidity metrics from provider
    # {
    #     "fed_balance_sheet": {"value": 7.53e12, "change_1w": -0.3, ...},
    #     "rrp": {...},
    #     ...
    # }
    liquidity_metrics = Column(JSON, nullable=True)

    # ==========================================================================
    # Data Quality
    # ==========================================================================

    data_stale = Column(Boolean, default=False)
    stale_components = Column(JSON, nullable=True)  # List of stale component names
    last_api_success = Column(DateTime(timezone=True), nullable=True)

    # Overall data quality
    completeness = Column(Float, nullable=True)  # 0-1, proportion of data available
    overall_confidence = Column(Float, nullable=True)  # 0-100, minimum of key confidences

    # ==========================================================================
    # Change Tracking
    # ==========================================================================

    liquidity_change_6h = Column(Float, nullable=True)
    readiness_change_6h = Column(Float, nullable=True)

    __table_args__ = (
        Index('idx_catalyst_timestamp_desc', timestamp.desc()),
    )

    def __repr__(self):
        return (
            f"<CatalystSnapshot("
            f"liquidity={self.liquidity_score}, "
            f"readiness={self.trade_readiness_score} ({self.readiness_label}), "
            f"at={self.timestamp})>"
        )

    def to_dict(self):
        """Convert model to dictionary for API responses."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,

            # Component scores
            "components": {
                "liquidity": self.liquidity_score,
                "options_positioning": self.options_positioning_score,
                "credit_stress": self.credit_stress_score,
                "vol_structure": self.vol_structure_score,
                "event_density": self.event_density_score,
                "cross_asset_confirmation": self.cross_asset_confirmation_score,
            },

            # Trade Readiness
            "trade_readiness": {
                "score": self.trade_readiness_score,
                "label": self.readiness_label,
                "label_display": self._get_readiness_label_display(),
                "is_partial": self.readiness_is_partial,
            },

            # Explainability
            "confidence_by_component": self.confidence_by_component,
            "drivers": self.drivers,

            # Data quality
            "data_stale": self.data_stale,
            "stale_components": self.stale_components,
            "completeness": self.completeness,
            "overall_confidence": self.overall_confidence,
            "last_api_success": self.last_api_success.isoformat() if self.last_api_success else None,

            # Changes
            "changes": {
                "liquidity_6h": self.liquidity_change_6h,
                "readiness_6h": self.readiness_change_6h,
            },
        }

    def _get_readiness_label_display(self) -> str:
        """Get human-readable readiness label."""
        labels = {
            "green": "Risk-On",
            "yellow": "Transition",
            "red": "Risk-Off",
        }
        return labels.get(self.readiness_label, self.readiness_label or "Unknown")

    def get_summary(self) -> dict:
        """Get compact summary for Command Center widget."""
        return {
            "trade_readiness_score": self.trade_readiness_score,
            "readiness_label": self.readiness_label,
            "readiness_label_display": self._get_readiness_label_display(),
            "is_partial": self.readiness_is_partial,
            "liquidity_score": self.liquidity_score,
            "data_stale": self.data_stale,
            "overall_confidence": self.overall_confidence,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
