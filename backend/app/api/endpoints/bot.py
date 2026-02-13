"""
Trading Bot API endpoints
Configuration, control, trade journal, and performance analytics
"""
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from loguru import logger
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.auth import require_trading_auth
from app.models.bot_config import BotConfiguration, ExecutionMode, SizingMode
from app.models.bot_state import BotState
from app.models.executed_trade import ExecutedTrade, TradeStatus
from app.services.trading.auto_trader import auto_trader
from app.services.trading.trade_journal import TradeJournal

router = APIRouter(dependencies=[Depends(require_trading_auth)])


# =============================================================================
# Request / Response Models
# =============================================================================

class BotConfigUpdate(BaseModel):
    """Partial update for bot configuration."""
    execution_mode: Optional[str] = None
    paper_mode: Optional[bool] = None
    max_per_stock_trade: Optional[float] = None
    max_per_options_trade: Optional[float] = None
    sizing_mode: Optional[str] = None
    risk_pct_per_trade: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    max_concurrent_positions: Optional[int] = None
    max_portfolio_allocation_pct: Optional[float] = None
    max_total_invested_pct: Optional[float] = None
    default_take_profit_pct: Optional[float] = None
    default_stop_loss_pct: Optional[float] = None
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_pct: Optional[float] = None
    close_positions_eod: Optional[bool] = None
    eod_close_minutes_before: Optional[int] = None
    leaps_roll_alert_dte: Optional[int] = None
    min_confidence_to_execute: Optional[float] = None
    require_ai_analysis: Optional[bool] = None
    min_ai_conviction: Optional[float] = None
    enabled_strategies: Optional[list] = None
    circuit_breaker_warn_pct: Optional[float] = None
    circuit_breaker_pause_pct: Optional[float] = None
    circuit_breaker_halt_pct: Optional[float] = None
    max_bid_ask_spread_pct: Optional[float] = None
    min_option_open_interest: Optional[int] = None
    min_option_volume: Optional[int] = None


class EmergencyStopRequest(BaseModel):
    close_positions: bool = True


# =============================================================================
# Configuration
# =============================================================================

@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    """Get current bot configuration."""
    config = auto_trader._get_config(db)
    return config.to_dict()


@router.put("/config")
def update_config(update: BotConfigUpdate, db: Session = Depends(get_db)):
    """Update bot configuration. Only provided fields are updated."""
    config = auto_trader._get_config(db)

    # Validate execution_mode
    if update.execution_mode:
        valid_modes = [e.value for e in ExecutionMode]
        if update.execution_mode not in valid_modes:
            raise HTTPException(400, f"Invalid execution_mode. Must be one of: {valid_modes}")

    # Validate sizing_mode
    if update.sizing_mode:
        valid_sizes = [s.value for s in SizingMode]
        if update.sizing_mode not in valid_sizes:
            raise HTTPException(400, f"Invalid sizing_mode. Must be one of: {valid_sizes}")

    # Validate numeric fields — must be positive where applicable
    _POSITIVE_FIELDS = {
        "max_per_stock_trade", "max_per_options_trade", "risk_pct_per_trade",
        "max_daily_loss", "default_take_profit_pct", "default_stop_loss_pct",
        "trailing_stop_pct", "max_bid_ask_spread_pct",
    }
    _NON_NEGATIVE_INT_FIELDS = {
        "max_trades_per_day", "max_concurrent_positions", "eod_close_minutes_before",
        "leaps_roll_alert_dte", "min_option_open_interest", "min_option_volume",
    }
    _PERCENTAGE_FIELDS = {
        "max_portfolio_allocation_pct", "max_total_invested_pct",
        "min_confidence_to_execute", "min_ai_conviction",
        "circuit_breaker_warn_pct", "circuit_breaker_pause_pct", "circuit_breaker_halt_pct",
    }
    update_data_raw = update.model_dump(exclude_unset=True)
    for field, value in update_data_raw.items():
        if value is None:
            continue
        if field in _POSITIVE_FIELDS and (not isinstance(value, (int, float)) or value <= 0):
            raise HTTPException(400, f"{field} must be a positive number")
        if field in _NON_NEGATIVE_INT_FIELDS and (not isinstance(value, (int, float)) or value < 0):
            raise HTTPException(400, f"{field} must be a non-negative number")
        if field in _PERCENTAGE_FIELDS and (not isinstance(value, (int, float)) or value < 0 or value > 100):
            raise HTTPException(400, f"{field} must be between 0 and 100")

    # Check if bot is running — block dangerous config changes
    state = auto_trader._get_or_create_state(db)
    if state.status == "running":
        if update.paper_mode is not None:
            raise HTTPException(400, "Cannot change paper_mode while bot is running. Stop the bot first.")
        if update.execution_mode is not None:
            raise HTTPException(400, "Cannot change execution_mode while bot is running. Stop the bot first.")

    # Apply updates
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(config, field):
            setattr(config, field, value)

    db.commit()
    logger.info(f"Bot config updated: {list(update_data.keys())}")

    return config.to_dict()


# =============================================================================
# Bot Control
# =============================================================================

@router.post("/start")
def start_bot(db: Session = Depends(get_db)):
    """Start the trading bot. Validates config and snapshots equity."""
    result = auto_trader.start(db)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result


@router.post("/stop")
def stop_bot(db: Session = Depends(get_db)):
    """Graceful stop. Does NOT cancel orders or close positions."""
    return auto_trader.stop(db)


@router.post("/pause")
def pause_bot(db: Session = Depends(get_db)):
    """Pause the bot. Stops processing new signals but keeps monitoring positions."""
    state = auto_trader._get_or_create_state(db)
    if state.status != "running":
        raise HTTPException(400, f"Bot is not running (current: {state.status})")
    state.status = "paused"
    db.commit()
    return {"status": "paused"}


@router.post("/resume")
def resume_bot(db: Session = Depends(get_db)):
    """Resume from paused or halted state."""
    state = auto_trader._get_or_create_state(db)
    if state.status not in ("paused", "halted"):
        raise HTTPException(400, f"Bot is not paused or halted (current: {state.status})")

    # Don't allow resume if circuit breaker was triggered and conditions still hold
    if state.circuit_breaker_level in ("paused", "halted"):
        config = auto_trader._get_config(db)
        from app.services.trading.alpaca_trading_service import alpaca_trading_service
        account = alpaca_trading_service.get_account()
        if account and state.daily_start_equity:
            current_equity = account.get("equity", 0)
            drawdown_pct = ((state.daily_start_equity - current_equity) / state.daily_start_equity) * 100
            if drawdown_pct >= config.circuit_breaker_pause_pct:
                raise HTTPException(400,
                    f"Cannot resume: drawdown still at {drawdown_pct:.1f}% "
                    f"(pause threshold: {config.circuit_breaker_pause_pct}%). "
                    f"Wait for next trading day or use /start for fresh session."
                )

    state.status = "running"
    state.circuit_breaker_level = "none"
    db.commit()
    return {"status": "running"}


@router.post("/emergency-stop")
def emergency_stop(request: EmergencyStopRequest, db: Session = Depends(get_db)):
    """
    Kill switch: cancel all open orders.
    If close_positions=true, also close all positions.
    """
    return auto_trader.emergency_stop(request.close_positions, db)


# =============================================================================
# Status
# =============================================================================

@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Get current bot status, account summary, and active config snapshot."""
    return auto_trader.get_status(db)


# =============================================================================
# Signal Approval (Semi-Auto)
# =============================================================================

@router.post("/approve/{signal_id}")
def approve_signal(signal_id: int, db: Session = Depends(get_db)):
    """Approve a pending signal for execution (semi-auto mode)."""
    trade = auto_trader.approve_signal(signal_id, db)
    if not trade:
        raise HTTPException(400, "Signal could not be executed")
    return trade.to_dict()


@router.post("/reject/{signal_id}")
def reject_signal(signal_id: int, db: Session = Depends(get_db)):
    """Reject a pending signal (semi-auto mode)."""
    # Find the pending trade for this signal
    pending = (
        db.query(ExecutedTrade)
        .filter(
            ExecutedTrade.signal_id == signal_id,
            ExecutedTrade.status == TradeStatus.PENDING_APPROVAL.value,
        )
        .first()
    )
    if not pending:
        raise HTTPException(404, "No pending trade found for this signal")

    pending.status = TradeStatus.CANCELLED.value
    pending.notes = "Rejected by user"
    db.commit()

    return {"status": "rejected", "signal_id": signal_id}


@router.get("/pending-approvals")
def get_pending_approvals(db: Session = Depends(get_db)):
    """Get all signals awaiting user approval (semi-auto mode)."""
    pending = (
        db.query(ExecutedTrade)
        .filter(ExecutedTrade.status == TradeStatus.PENDING_APPROVAL.value)
        .order_by(ExecutedTrade.created_at.desc())
        .all()
    )
    return [t.to_dict() for t in pending]


# =============================================================================
# Manual Signal Execution (Trade button in UI)
# =============================================================================

@router.post("/preview-signal/{signal_id}")
def preview_signal(signal_id: int, db: Session = Depends(get_db)):
    """
    Preview what would happen if a signal were executed through the bot pipeline.
    Returns risk check results, sizing preview, and account info — no order placed.
    """
    result = auto_trader.preview_signal(signal_id, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/execute-signal/{signal_id}")
def execute_signal(signal_id: int, db: Session = Depends(get_db)):
    """
    Manually execute a signal through the full risk → size → execute pipeline.
    Does NOT require the bot to be in RUNNING state.
    Called from the "Trade" button in the Trading Signals UI.
    """
    result = auto_trader.execute_manual_signal(signal_id, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# =============================================================================
# Trade Journal
# =============================================================================

@router.get("/trades")
def list_trades(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    asset_type: Optional[str] = None,
    exit_reason: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List executed trades with filters."""
    query = db.query(ExecutedTrade)

    if status:
        query = query.filter(ExecutedTrade.status == status)
    if symbol:
        query = query.filter(ExecutedTrade.symbol == symbol.upper())
    if asset_type:
        query = query.filter(ExecutedTrade.asset_type == asset_type)
    if exit_reason:
        query = query.filter(ExecutedTrade.exit_reason == exit_reason)
    if start_date:
        try:
            sd = date.fromisoformat(start_date)
            query = query.filter(ExecutedTrade.created_at >= datetime(sd.year, sd.month, sd.day))
        except ValueError:
            pass
    if end_date:
        try:
            ed = date.fromisoformat(end_date)
            query = query.filter(
                ExecutedTrade.created_at < datetime.combine(ed + timedelta(days=1), datetime.min.time())
            )
        except ValueError:
            pass

    total = query.count()
    trades = (
        query.order_by(ExecutedTrade.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "trades": [t.to_summary_dict() for t in trades],
    }


@router.get("/trades/active")
def get_active_trades(db: Session = Depends(get_db)):
    """Get currently open/pending trades."""
    journal = TradeJournal(db)
    return journal.get_open_trades()


@router.get("/trades/{trade_id}")
def get_trade_detail(trade_id: int, db: Session = Depends(get_db)):
    """Get full trade detail with linked signal."""
    journal = TradeJournal(db)
    trade = journal.get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(404, f"Trade #{trade_id} not found")
    return trade


# =============================================================================
# Performance
# =============================================================================

@router.get("/performance")
def get_performance(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Performance summary over a date range (default: last 30 days)."""
    journal = TradeJournal(db)

    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None

    return journal.get_performance_summary(sd, ed)


@router.get("/performance/daily")
def get_daily_performance(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=30, le=365),
    db: Session = Depends(get_db),
):
    """List daily bot performance records."""
    from app.models.daily_bot_performance import DailyBotPerformance

    query = db.query(DailyBotPerformance)

    if start_date:
        query = query.filter(DailyBotPerformance.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.filter(DailyBotPerformance.date <= date.fromisoformat(end_date))

    records = (
        query.order_by(DailyBotPerformance.date.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "date": r.date.isoformat(),
            "trades_count": r.trades_count,
            "wins": r.wins,
            "losses": r.losses,
            "win_rate": r.win_rate,
            "gross_pl": r.gross_pl,
            "net_pl": r.net_pl,
            "total_fees": r.total_fees,
            "best_trade_pl": r.best_trade_pl,
            "worst_trade_pl": r.worst_trade_pl,
            "avg_trade_pl": r.avg_trade_pl,
            "avg_hold_minutes": r.avg_hold_minutes,
            "max_drawdown_pct": r.max_drawdown_pct,
            "stocks_traded": r.stocks_traded,
            "options_traded": r.options_traded,
        }
        for r in records
    ]


@router.get("/performance/today")
def get_today_performance(db: Session = Depends(get_db)):
    """Today's live stats from BotState."""
    state = auto_trader._get_or_create_state(db)
    config = auto_trader._get_config(db)

    return {
        "date": date.today().isoformat(),
        "status": state.status,
        "daily_pl": state.daily_pl or 0,
        "daily_trades": state.daily_trades_count,
        "daily_wins": state.daily_wins,
        "daily_losses": state.daily_losses,
        "win_rate": (
            round((state.daily_wins / state.daily_trades_count) * 100, 1)
            if state.daily_trades_count > 0 else 0
        ),
        "open_positions": state.open_positions_count,
        "circuit_breaker": state.circuit_breaker_level,
        "max_daily_loss_limit": config.max_daily_loss,
        "max_trades_limit": config.max_trades_per_day,
        "daily_start_equity": state.daily_start_equity,
    }


@router.get("/performance/exit-reasons")
def get_exit_reason_breakdown(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Breakdown of trade exits by reason."""
    journal = TradeJournal(db)

    sd = date.fromisoformat(start_date) if start_date else None
    ed = date.fromisoformat(end_date) if end_date else None

    return journal.get_exit_reason_breakdown(sd, ed)
