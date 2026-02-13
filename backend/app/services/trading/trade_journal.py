"""
Trade Journal — aggregation, analytics, and daily performance tracking.

The OrderExecutor handles creating/updating ExecutedTrade records.
The TradeJournal focuses on:
  - Daily stats rollup (upsert into DailyBotPerformance)
  - Performance summary over date ranges
  - Trade history queries
"""
from datetime import date, datetime, timedelta
from typing import Optional, List

from loguru import logger
from sqlalchemy import func as sa_func, and_, extract
from sqlalchemy.orm import Session

from app.models.executed_trade import ExecutedTrade, TradeStatus
from app.models.daily_bot_performance import DailyBotPerformance


class TradeJournal:
    """Analytics and daily performance tracking for bot trades."""

    def __init__(self, db: Session):
        self.db = db

    # =====================================================================
    # Daily Stats
    # =====================================================================

    def update_daily_stats(self, target_date: Optional[date] = None) -> DailyBotPerformance:
        """
        Aggregate all closed trades for a date into DailyBotPerformance.
        Creates or updates the row for that date.
        """
        target_date = target_date or date.today()

        # Query closed trades for the target date
        trades = (
            self.db.query(ExecutedTrade)
            .filter(
                ExecutedTrade.status == TradeStatus.CLOSED.value,
                sa_func.date(ExecutedTrade.exit_filled_at) == target_date,
            )
            .all()
        )

        # Get or create daily record
        daily = (
            self.db.query(DailyBotPerformance)
            .filter(DailyBotPerformance.date == target_date)
            .first()
        )
        if not daily:
            daily = DailyBotPerformance(date=target_date)
            self.db.add(daily)

        if not trades:
            self.db.commit()
            return daily

        # Aggregate
        pls = [t.realized_pl or 0 for t in trades]
        fees = [t.fees or 0 for t in trades]
        hold_mins = [t.hold_duration_minutes for t in trades if t.hold_duration_minutes]

        wins = [pl for pl in pls if pl > 0]
        losses = [pl for pl in pls if pl < 0]

        daily.trades_count = len(trades)
        daily.wins = len(wins)
        daily.losses = len(losses)
        daily.win_rate = round((len(wins) / len(trades)) * 100, 1) if trades else 0
        daily.gross_pl = round(sum(pls), 2)
        daily.total_fees = round(sum(fees), 2)
        daily.net_pl = round(daily.gross_pl - daily.total_fees, 2)
        daily.best_trade_pl = round(max(pls), 2) if pls else 0
        daily.worst_trade_pl = round(min(pls), 2) if pls else 0
        daily.avg_trade_pl = round(sum(pls) / len(pls), 2) if pls else 0
        daily.avg_hold_minutes = round(sum(hold_mins) / len(hold_mins), 1) if hold_mins else None

        # Count by asset type
        daily.stocks_traded = sum(1 for t in trades if t.asset_type == "stock")
        daily.options_traded = sum(1 for t in trades if t.asset_type == "option")

        # Circuit breaker check
        daily.circuit_breaker_triggered = any(
            t.exit_reason == "circuit_breaker" for t in trades
        )

        # Max drawdown: worst running P&L through the day
        running_pl = 0.0
        max_dd = 0.0  # dollar drawdown (negative or zero)
        # Sort by exit time for chronological running P&L
        sorted_trades = sorted(trades, key=lambda t: t.exit_filled_at or datetime.min)
        for t in sorted_trades:
            running_pl += (t.realized_pl or 0)
            if running_pl < max_dd:
                max_dd = running_pl
        # Convert dollar drawdown to percentage if start equity is available
        if max_dd < 0 and daily.start_equity and daily.start_equity > 0:
            daily.max_drawdown_pct = round((max_dd / daily.start_equity) * 100, 2)
        elif max_dd < 0:
            # Fallback: store dollar amount (legacy behavior) when no equity data
            daily.max_drawdown_pct = round(max_dd, 2)
        else:
            daily.max_drawdown_pct = 0

        self.db.commit()

        logger.info(
            f"TradeJournal: daily stats for {target_date} — "
            f"{daily.trades_count} trades, "
            f"W/L={daily.wins}/{daily.losses}, "
            f"net P&L=${daily.net_pl}"
        )

        return daily

    # =====================================================================
    # Performance Summary
    # =====================================================================

    def get_performance_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """
        Performance analytics over a date range.
        Defaults to last 30 days if no dates provided.
        """
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Get daily performance records
        daily_records = (
            self.db.query(DailyBotPerformance)
            .filter(
                DailyBotPerformance.date >= start_date,
                DailyBotPerformance.date <= end_date,
            )
            .order_by(DailyBotPerformance.date)
            .all()
        )

        # Get individual closed trades for detailed breakdown
        trades = (
            self.db.query(ExecutedTrade)
            .filter(
                ExecutedTrade.status == TradeStatus.CLOSED.value,
                sa_func.date(ExecutedTrade.exit_filled_at) >= start_date,
                sa_func.date(ExecutedTrade.exit_filled_at) <= end_date,
            )
            .all()
        )

        if not trades:
            return {
                "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "total_trades": 0,
                "total_pl": 0,
                "win_rate": 0,
                "by_strategy": {},
                "by_asset_type": {},
                "equity_curve": [],
                "daily_records": [],
            }

        pls = [t.realized_pl or 0 for t in trades]
        wins = [pl for pl in pls if pl > 0]
        losses = [pl for pl in pls if pl < 0]
        hold_mins = [t.hold_duration_minutes for t in trades if t.hold_duration_minutes]

        # Strategy breakdown
        by_strategy = {}
        for t in trades:
            strategy = t.notes or "unknown"  # Could parse from signal
            # Try getting strategy from the linked signal
            if t.signal and hasattr(t.signal, "strategy"):
                strategy = t.signal.strategy
            if strategy not in by_strategy:
                by_strategy[strategy] = {"count": 0, "pl": 0, "wins": 0, "losses": 0}
            by_strategy[strategy]["count"] += 1
            by_strategy[strategy]["pl"] = round(by_strategy[strategy]["pl"] + (t.realized_pl or 0), 2)
            if (t.realized_pl or 0) > 0:
                by_strategy[strategy]["wins"] += 1
            elif (t.realized_pl or 0) < 0:
                by_strategy[strategy]["losses"] += 1

        # Asset type breakdown
        by_asset_type = {}
        for t in trades:
            at = t.asset_type or "stock"
            if at not in by_asset_type:
                by_asset_type[at] = {"count": 0, "pl": 0, "wins": 0, "losses": 0}
            by_asset_type[at]["count"] += 1
            by_asset_type[at]["pl"] = round(by_asset_type[at]["pl"] + (t.realized_pl or 0), 2)
            if (t.realized_pl or 0) > 0:
                by_asset_type[at]["wins"] += 1
            elif (t.realized_pl or 0) < 0:
                by_asset_type[at]["losses"] += 1

        # Equity curve from daily records
        equity_curve = []
        for d in daily_records:
            equity_curve.append({
                "date": d.date.isoformat(),
                "net_pl": d.net_pl or 0,
                "trades": d.trades_count or 0,
                "start_equity": d.start_equity,
                "end_equity": d.end_equity,
            })

        # Max drawdown (consecutive losing streak in $)
        running = 0.0
        peak = 0.0
        max_dd = 0.0
        for d in daily_records:
            running += (d.net_pl or 0)
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round((len(wins) / len(trades)) * 100, 1) if trades else 0,
            "total_pl": round(sum(pls), 2),
            "avg_pl_per_trade": round(sum(pls) / len(pls), 2) if pls else 0,
            "best_trade": round(max(pls), 2) if pls else 0,
            "worst_trade": round(min(pls), 2) if pls else 0,
            "avg_hold_minutes": round(sum(hold_mins) / len(hold_mins), 1) if hold_mins else 0,
            "max_drawdown": round(max_dd, 2),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
            "profit_factor": round(abs(sum(wins) / sum(losses)), 2) if losses and sum(losses) != 0 else 0,
            "by_strategy": by_strategy,
            "by_asset_type": by_asset_type,
            "equity_curve": equity_curve,
            "daily_records": [
                {
                    "date": d.date.isoformat(),
                    "trades": d.trades_count,
                    "wins": d.wins,
                    "losses": d.losses,
                    "win_rate": d.win_rate,
                    "net_pl": d.net_pl,
                    "best_trade": d.best_trade_pl,
                    "worst_trade": d.worst_trade_pl,
                }
                for d in daily_records
            ],
        }

    # =====================================================================
    # Trade History Queries
    # =====================================================================

    def get_recent_trades(self, limit: int = 50, asset_type: Optional[str] = None) -> List[dict]:
        """Get recent trades with optional asset type filter."""
        query = self.db.query(ExecutedTrade).filter(
            ExecutedTrade.status == TradeStatus.CLOSED.value,
        )
        if asset_type:
            query = query.filter(ExecutedTrade.asset_type == asset_type)

        trades = (
            query.order_by(ExecutedTrade.exit_filled_at.desc())
            .limit(limit)
            .all()
        )
        return [t.to_summary_dict() for t in trades]

    def get_open_trades(self) -> List[dict]:
        """Get all currently open trades."""
        trades = (
            self.db.query(ExecutedTrade)
            .filter(ExecutedTrade.status.in_([
                TradeStatus.OPEN.value,
                TradeStatus.PENDING_ENTRY.value,
                TradeStatus.PENDING_EXIT.value,
            ]))
            .order_by(ExecutedTrade.created_at.desc())
            .all()
        )
        return [t.to_dict() for t in trades]

    def get_trade_by_id(self, trade_id: int) -> Optional[dict]:
        """Get full trade details by ID."""
        trade = self.db.query(ExecutedTrade).get(trade_id)
        return trade.to_dict() if trade else None

    def get_trades_by_symbol(self, symbol: str, limit: int = 20) -> List[dict]:
        """Get trade history for a specific symbol."""
        trades = (
            self.db.query(ExecutedTrade)
            .filter(ExecutedTrade.symbol == symbol.upper())
            .order_by(ExecutedTrade.created_at.desc())
            .limit(limit)
            .all()
        )
        return [t.to_summary_dict() for t in trades]

    def get_exit_reason_breakdown(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Breakdown of trade exits by reason."""
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        trades = (
            self.db.query(ExecutedTrade)
            .filter(
                ExecutedTrade.status == TradeStatus.CLOSED.value,
                sa_func.date(ExecutedTrade.exit_filled_at) >= start_date,
                sa_func.date(ExecutedTrade.exit_filled_at) <= end_date,
            )
            .all()
        )

        breakdown = {}
        for t in trades:
            reason = t.exit_reason or "unknown"
            if reason not in breakdown:
                breakdown[reason] = {"count": 0, "total_pl": 0}
            breakdown[reason]["count"] += 1
            breakdown[reason]["total_pl"] = round(
                breakdown[reason]["total_pl"] + (t.realized_pl or 0), 2
            )

        return breakdown
