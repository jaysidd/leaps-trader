"""
TickerCatalystSnapshot model for per-ticker catalyst overlay data.
Stores ticker-specific event risk and catalyst scores.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, Index
from sqlalchemy.sql import func
from app.database import Base


class TickerCatalystSnapshot(Base):
    """
    Per-ticker catalyst overlay data.

    Stores ticker-specific scores:
    - Earnings risk (days to earnings, guidance)
    - Options positioning (ticker-level)
    - Macro bias (from sector mapping)
    - Optional: Insider flows, crowding
    """
    __tablename__ = "ticker_catalyst_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # ==========================================================================
    # Ticker-Level Scores (0-100)
    # ==========================================================================

    # Earnings risk based on days-to-earnings and guidance
    earnings_risk_score = Column(Float, nullable=True)

    # Options positioning at ticker level
    options_positioning_score = Column(Float, nullable=True)

    # Macro bias from sector/ticker weights
    macro_bias_score = Column(Float, nullable=True)

    # Optional Tier 3
    insider_flow_score = Column(Float, nullable=True)
    crowding_score = Column(Float, nullable=True)

    # ==========================================================================
    # Explainability
    # ==========================================================================

    # Confidence per component
    # {
    #     "earnings_risk": 90.0,
    #     "options_positioning": 75.0,
    #     "macro_bias": 85.0
    # }
    confidence_by_component = Column(JSON, nullable=True)

    # Drivers per component
    # {
    #     "earnings_risk": [
    #         {"name": "days_to_earnings", "value": 3, "contribution": 25.0, "direction": "bearish"},
    #         {"name": "iv_percentile", "value": 85, "contribution": 15.0, "direction": "bearish"}
    #     ],
    #     ...
    # }
    drivers = Column(JSON, nullable=True)

    # ==========================================================================
    # Event Information
    # ==========================================================================

    # Next known events (earnings, ex-dividend, etc.)
    # [
    #     {
    #         "type": "earnings",
    #         "datetime": "2026-02-10T21:00:00Z",
    #         "session": "after_market",
    #         "confirmed": true,
    #         "days_until": 8
    #     },
    #     {
    #         "type": "ex_dividend",
    #         "datetime": "2026-02-15T00:00:00Z",
    #         "days_until": 13
    #     }
    # ]
    next_known_events = Column(JSON, nullable=True)

    # Earnings-specific details
    earnings_datetime = Column(DateTime(timezone=True), nullable=True)
    earnings_confirmed = Column(Boolean, nullable=True)
    earnings_session = Column(String(20), nullable=True)  # pre_market, after_market
    guidance_trend = Column(String(10), nullable=True)  # up, flat, down

    # ==========================================================================
    # Options Details (for display)
    # ==========================================================================

    # OI walls
    # {
    #     "calls": [{"strike": 200, "open_interest": 185000}, ...],
    #     "puts": [{"strike": 180, "open_interest": 161000}, ...]
    # }
    oi_walls = Column(JSON, nullable=True)

    # Key options metrics
    put_call_ratio = Column(Float, nullable=True)
    iv_rank = Column(Float, nullable=True)
    iv_percentile = Column(Float, nullable=True)

    # ==========================================================================
    # Data Quality
    # ==========================================================================

    data_stale = Column(Boolean, default=False)
    stale_reason = Column(String(200), nullable=True)

    __table_args__ = (
        Index('idx_ticker_catalyst_symbol_ts', 'symbol', timestamp.desc()),
    )

    def __repr__(self):
        return (
            f"<TickerCatalystSnapshot("
            f"symbol={self.symbol}, "
            f"earnings_risk={self.earnings_risk_score}, "
            f"options={self.options_positioning_score}, "
            f"at={self.timestamp})>"
        )

    def to_dict(self):
        """Convert model to dictionary for API responses."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,

            # Scores
            "scores": {
                "earnings_risk": self.earnings_risk_score,
                "options_positioning": self.options_positioning_score,
                "macro_bias": self.macro_bias_score,
                "insider_flow": self.insider_flow_score,
                "crowding": self.crowding_score,
            },

            # Explainability
            "confidence_by_component": self.confidence_by_component,
            "drivers": self.drivers,

            # Events
            "next_known_events": self.next_known_events,
            "earnings": {
                "datetime": self.earnings_datetime.isoformat() if self.earnings_datetime else None,
                "confirmed": self.earnings_confirmed,
                "session": self.earnings_session,
                "guidance_trend": self.guidance_trend,
            } if self.earnings_datetime else None,

            # Options
            "options": {
                "oi_walls": self.oi_walls,
                "put_call_ratio": self.put_call_ratio,
                "iv_rank": self.iv_rank,
                "iv_percentile": self.iv_percentile,
            },

            # Quality
            "data_stale": self.data_stale,
            "stale_reason": self.stale_reason,
        }

    def get_overlay_summary(self) -> dict:
        """Get compact summary for Ticker Detail overlay card."""
        # Calculate days until earnings
        days_until_earnings = None
        if self.next_known_events:
            for event in self.next_known_events:
                if event.get("type") == "earnings":
                    days_until_earnings = event.get("days_until")
                    break

        return {
            "symbol": self.symbol,
            "earnings_risk": {
                "score": self.earnings_risk_score,
                "days_until": days_until_earnings,
                "label": self._get_earnings_risk_label(),
            },
            "options_fragility": {
                "score": self.options_positioning_score,
                "label": self._get_options_label(),
            },
            "macro_bias": {
                "score": self.macro_bias_score,
                "modifier": self._get_macro_modifier(),
            },
            "data_stale": self.data_stale,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def _get_earnings_risk_label(self) -> str:
        """Get earnings risk label."""
        if self.earnings_risk_score is None:
            return "Unknown"
        if self.earnings_risk_score >= 75:
            return "High"
        if self.earnings_risk_score >= 50:
            return "Elevated"
        if self.earnings_risk_score >= 30:
            return "Moderate"
        return "Low"

    def _get_options_label(self) -> str:
        """Get options fragility label."""
        if self.options_positioning_score is None:
            return "Unknown"
        if self.options_positioning_score >= 67:
            return "Fragile"
        if self.options_positioning_score >= 34:
            return "Mixed"
        return "Supportive"

    def _get_macro_modifier(self) -> str:
        """Get macro bias modifier string."""
        if self.macro_bias_score is None:
            return "N/A"
        # Positive modifier if macro favors the ticker
        if self.macro_bias_score >= 60:
            return f"+{round((self.macro_bias_score - 50) / 5)}%"
        if self.macro_bias_score <= 40:
            return f"-{round((50 - self.macro_bias_score) / 5)}%"
        return "0%"
