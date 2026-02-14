"""
Replay Audit Log — captures every pipeline decision during historical replay.

Each row represents one decision point:
  - preset_selection: What condition was detected + which presets were chosen
  - screening: Which stocks passed/failed each gate
  - signal_generation: Signal details, confidence, strategy
  - risk_check: Risk gateway pass/fail with reasons
  - trade_execution: Fill details, sizing, timing
  - position_exit: SL/TP/EOD exit with realized P/L

Enables post-replay analysis: "Was the AI right about market conditions?"
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, Text
from sqlalchemy.sql import func
from app.database import Base


class ReplayAuditLog(Base):
    """
    Audit log for historical replay pipeline decisions.
    One row per decision point, tagged by replay session.
    """
    __tablename__ = "replay_audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    # ── Session identification ──
    replay_session_id = Column(String(36), nullable=False, index=True)  # UUID per replay run
    replay_date = Column(String(10), nullable=False, index=True)        # YYYY-MM-DD
    simulated_time = Column(DateTime(timezone=True), nullable=True)     # Clock time at decision

    # ── Decision categorization ──
    stage = Column(String(30), nullable=False, index=True)
    # Values: "preset_selection", "screening", "signal_generation",
    #         "risk_check", "trade_execution", "position_exit", "summary"

    symbol = Column(String(20), nullable=True, index=True)  # Null for market-level stages

    # ── Decision data (JSON blob — schema varies by stage) ──
    decision = Column(JSON, nullable=False)
    # preset_selection: {condition, presets, composite_score, signal_scores, snapshot, reasoning}
    # screening: {symbol, passed, gate_results, composite_score, ...}
    # signal_generation: {symbol, strategy, confidence, entry, sl, tp, rr, direction, ...}
    # risk_check: {symbol, passed, checks_failed, reasons, ...}
    # trade_execution: {symbol, side, qty, price, notional, ...}
    # position_exit: {symbol, reason, entry_price, exit_price, qty, realized_pl, hold_time_min, ...}
    # summary: {total_signals, trades, wins, losses, gross_pl, max_drawdown, ...}

    # ── Quick-access fields for analysis queries ──
    passed = Column(Boolean, nullable=True)         # Did this step succeed/pass?
    score = Column(Float, nullable=True)            # Numeric score (confidence, composite, etc.)
    reasoning = Column(Text, nullable=True)         # Human-readable explanation

    # ── Timestamps ──
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return (
            f"<ReplayAuditLog(session={self.replay_session_id[:8]}, "
            f"stage={self.stage}, symbol={self.symbol}, "
            f"passed={self.passed}, score={self.score})>"
        )
