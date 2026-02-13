"""
AutopilotLog — Activity log for the autopilot conductor.

Records scan events, preset selections, market conditions, signal generation,
and trade execution for the Autopilot monitoring dashboard.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.sql import func

from app.database import Base


class AutopilotLog(Base):
    """
    Activity log entry for the autopilot system.
    Each row is one event (scan started, presets selected, scan complete, etc.).
    """
    __tablename__ = "autopilot_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Event classification
    event_type = Column(String(30), nullable=False, index=True)
    # Values: scan_started, presets_selected, scan_complete, scan_skipped,
    #         signal_generated, trade_executed, capital_exceeded, error

    # Market state at event time
    market_condition = Column(String(30))  # aggressive_bull, moderate_bull, neutral, etc.
    market_snapshot = Column(JSON)         # Full snapshot: MRI, regime, F&G, readiness

    # Scan details
    presets_selected = Column(JSON)        # List of preset IDs selected
    candidates_found = Column(Integer, default=0)
    signals_generated = Column(Integer, default=0)
    trades_executed = Column(Integer, default=0)

    # Freeform details
    details = Column(JSON)  # Top candidates, reasoning, errors, etc.

    def __repr__(self):
        return (
            f"<AutopilotLog(id={self.id}, type={self.event_type}, "
            f"condition={self.market_condition}, ts={self.timestamp})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "market_condition": self.market_condition,
            "market_snapshot": self.market_snapshot,
            "presets_selected": self.presets_selected,
            "candidates_found": self.candidates_found,
            "signals_generated": self.signals_generated,
            "trades_executed": self.trades_executed,
            "details": self.details,
        }
