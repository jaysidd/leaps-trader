"""
Backtest Result model — stores configuration, status, and results of backtests.

Each row represents one backtest run: strategy + symbol + date range → performance metrics.
"""
from sqlalchemy import (
    Column, Integer, Float, String, Text, Date, DateTime, JSON,
)
from sqlalchemy.sql import func

from app.database import Base


class BacktestResult(Base):
    """
    Persisted backtest result.
    Created with status='pending', updated to 'running'/'completed'/'failed'.
    """
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, index=True)

    # ── Configuration ────────────────────────────────────────────────────
    symbol = Column(String(10), nullable=False, index=True)
    strategy = Column(String(50), nullable=False)          # orb_breakout, vwap_pullback, range_breakout
    timeframe = Column(String(10), nullable=False)          # 5m, 15m, 4h
    cap_size = Column(String(20), default="large_cap")      # large_cap, mid_cap, small_cap
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    initial_capital = Column(Float, default=100000.0)
    position_size_pct = Column(Float, default=10.0)         # % of portfolio per trade

    # ── Status ───────────────────────────────────────────────────────────
    status = Column(String(20), default="pending", index=True)  # pending, running, completed, failed
    error_message = Column(Text, nullable=True)

    # ── Results (populated on completion) ────────────────────────────────
    final_value = Column(Float, nullable=True)
    total_return_pct = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    total_trades = Column(Integer, nullable=True)
    winning_trades = Column(Integer, nullable=True)
    losing_trades = Column(Integer, nullable=True)
    avg_win_pct = Column(Float, nullable=True)
    avg_loss_pct = Column(Float, nullable=True)
    best_trade_pct = Column(Float, nullable=True)
    worst_trade_pct = Column(Float, nullable=True)
    avg_trade_duration = Column(String(50), nullable=True)  # human-readable

    # ── Data (JSON columns) ──────────────────────────────────────────────
    equity_curve = Column(JSON, nullable=True)     # [{date, value}, ...]
    trade_log = Column(JSON, nullable=True)        # [{entry_date, exit_date, direction, pnl, pnl_pct, ...}, ...]
    parameters = Column(JSON, nullable=True)       # Strategy params used

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return (
            f"<BacktestResult(id={self.id}, symbol={self.symbol}, "
            f"strategy={self.strategy}, status={self.status})>"
        )

    def to_dict(self) -> dict:
        """Serialise for API responses."""
        return {
            "id": self.id,
            # Config
            "symbol": self.symbol,
            "strategy": self.strategy,
            "timeframe": self.timeframe,
            "cap_size": self.cap_size,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "initial_capital": self.initial_capital,
            "position_size_pct": self.position_size_pct,
            # Status
            "status": self.status,
            "error_message": self.error_message,
            # Results
            "final_value": self.final_value,
            "total_return_pct": self.total_return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_win_pct": self.avg_win_pct,
            "avg_loss_pct": self.avg_loss_pct,
            "best_trade_pct": self.best_trade_pct,
            "worst_trade_pct": self.worst_trade_pct,
            "avg_trade_duration": self.avg_trade_duration,
            # Data
            "equity_curve": self.equity_curve,
            "trade_log": self.trade_log,
            "parameters": self.parameters,
            # Timestamps
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
