"""
Daily Bot Performance model — one row per trading day.

Aggregated stats from ExecutedTrades: win rate, P&L, drawdown, etc.
Used for the performance dashboard and equity curve.
"""
from sqlalchemy import (
    Column, Integer, Float, Boolean, Date, DateTime,
)
from sqlalchemy.sql import func

from app.database import Base


class DailyBotPerformance(Base):
    """
    Daily aggregation of trading bot performance.
    One row per calendar date the bot was active.
    """
    __tablename__ = "daily_bot_performance"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True, index=True)

    # ── Trade Counts ──────────────────────────────────────────────────────
    trades_count = Column(Integer, nullable=False, default=0)
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    win_rate = Column(Float, nullable=True)                 # 0-100 percentage

    # ── P&L ───────────────────────────────────────────────────────────────
    gross_pl = Column(Float, nullable=False, default=0.0)
    net_pl = Column(Float, nullable=False, default=0.0)     # After fees
    total_fees = Column(Float, nullable=False, default=0.0)

    # ── Trade Stats ───────────────────────────────────────────────────────
    best_trade_pl = Column(Float, nullable=True)
    worst_trade_pl = Column(Float, nullable=True)
    avg_trade_pl = Column(Float, nullable=True)
    avg_hold_minutes = Column(Float, nullable=True)
    max_drawdown_pct = Column(Float, nullable=True)         # Intraday max drawdown

    # ── Equity ────────────────────────────────────────────────────────────
    start_equity = Column(Float, nullable=True)
    end_equity = Column(Float, nullable=True)

    # ── Breakdown ─────────────────────────────────────────────────────────
    stocks_traded = Column(Integer, nullable=False, default=0)
    options_traded = Column(Integer, nullable=False, default=0)
    circuit_breaker_triggered = Column(Boolean, nullable=False, default=False)

    # ── Timestamp ─────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return (
            f"<DailyBotPerformance(date={self.date}, "
            f"trades={self.trades_count}, "
            f"net_pl={self.net_pl}, "
            f"win_rate={self.win_rate})>"
        )

    def to_dict(self) -> dict:
        """Serialise for API responses."""
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            # Counts
            "trades_count": self.trades_count,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            # P&L
            "gross_pl": self.gross_pl,
            "net_pl": self.net_pl,
            "total_fees": self.total_fees,
            # Stats
            "best_trade_pl": self.best_trade_pl,
            "worst_trade_pl": self.worst_trade_pl,
            "avg_trade_pl": self.avg_trade_pl,
            "avg_hold_minutes": self.avg_hold_minutes,
            "max_drawdown_pct": self.max_drawdown_pct,
            # Equity
            "start_equity": self.start_equity,
            "end_equity": self.end_equity,
            # Breakdown
            "stocks_traded": self.stocks_traded,
            "options_traded": self.options_traded,
            "circuit_breaker_triggered": self.circuit_breaker_triggered,
        }
