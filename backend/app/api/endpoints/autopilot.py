"""
Autopilot API endpoints

Status dashboard, activity log, market state, and position calculator
for the autopilot monitoring UI.
"""
import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.autopilot_log import AutopilotLog
from app.models.bot_config import BotConfiguration
from app.models.bot_state import BotState
from app.models.executed_trade import ExecutedTrade
from app.models.signal_queue import SignalQueue
from app.models.trading_signal import TradingSignal
from app.services.automation.preset_selector import get_preset_selector
from app.services.settings_service import settings_service


router = APIRouter()


# =============================================================================
# Request / Response Models
# =============================================================================

class PositionCalcRequest(BaseModel):
    """Input for the position size calculator."""
    account_size: float = Field(..., gt=0)
    risk_per_position_pct: float = Field(..., gt=0, le=100)
    max_position_size: float = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: float = Field(..., gt=0)
    symbol: str = ""


# =============================================================================
# GET /status — Full autopilot dashboard state
# =============================================================================

@router.get("/status")
async def get_autopilot_status(db: Session = Depends(get_db)):
    """
    Return the current autopilot state for the dashboard.

    Includes configuration, market condition, pipeline counts,
    capital usage, and scan timing.
    """
    try:
        # ── Settings ──────────────────────────────────────────────────
        smart_scan_enabled = settings_service.get_setting(
            "automation.smart_scan_enabled"
        ) or False

        auto_scan_enabled = settings_service.get_setting(
            "automation.auto_scan_enabled"
        ) or False
        auto_scan_presets_raw = settings_service.get_setting(
            "automation.auto_scan_presets"
        ) or []
        # Ensure it's a list (could be a JSON string from settings)
        if isinstance(auto_scan_presets_raw, str):
            import json as _json
            try:
                auto_scan_presets = _json.loads(auto_scan_presets_raw)
            except (ValueError, TypeError):
                auto_scan_presets = []
        else:
            auto_scan_presets = auto_scan_presets_raw if isinstance(auto_scan_presets_raw, list) else []

        # ── Bot Configuration (singleton) ─────────────────────────────
        config = db.query(BotConfiguration).first()
        config_data = {}
        if config:
            config_data = {
                "execution_mode": config.execution_mode,
                "paper_mode": config.paper_mode,
                "autopilot_max_capital": config.autopilot_max_capital,
                "autopilot_max_candidates": config.autopilot_max_candidates,
                "autopilot_max_trades_per_day": config.autopilot_max_trades_per_day,
            }

        # ── Market condition from PresetSelector ─────────────────────
        condition = None
        active_presets = None
        reasoning = None
        market_snapshot = None

        try:
            selector = get_preset_selector()
            result = await selector.select_presets(db)
            condition = result.get("condition")
            active_presets = result.get("presets")
            reasoning = result.get("reasoning")
            market_snapshot = result.get("market_snapshot")
        except Exception as e:
            logger.warning(f"PresetSelector failed in status endpoint: {e}")

        # ── Scan timing ──────────────────────────────────────────────
        last_scan_log = (
            db.query(AutopilotLog)
            .filter(AutopilotLog.event_type == "scan_complete")
            .order_by(AutopilotLog.timestamp.desc())
            .first()
        )
        last_scan_at = (
            last_scan_log.timestamp.isoformat() if last_scan_log else None
        )

        next_scan_at = None
        if last_scan_log and last_scan_log.timestamp:
            interval_minutes = (
                settings_service.get_setting(
                    "automation.auto_scan_interval_minutes"
                )
                or 30
            )
            next_scan_dt = last_scan_log.timestamp + timedelta(
                minutes=int(interval_minutes)
            )
            next_scan_at = next_scan_dt.isoformat()

        # ── Pipeline counts ──────────────────────────────────────────
        bot_state = db.query(BotState).first()
        queue_count = (
            db.query(SignalQueue)
            .filter(SignalQueue.status == "active")
            .count()
        )
        active_signals = (
            db.query(TradingSignal)
            .filter(TradingSignal.status == "active")
            .count()
        )
        open_positions = (
            bot_state.open_positions_count if bot_state else 0
        )
        today_pl = bot_state.daily_pl if bot_state else 0.0

        # ── Capital used (sum of open position values) ───────────────
        capital_used = (
            db.query(
                sql_func.sum(
                    ExecutedTrade.entry_price * ExecutedTrade.quantity
                )
            )
            .filter(ExecutedTrade.status == "OPEN")
            .scalar()
            or 0
        )

        return {
            "smart_scan_enabled": smart_scan_enabled,
            "auto_scan_enabled": auto_scan_enabled,
            "auto_scan_presets": auto_scan_presets,
            **config_data,
            "current_condition": condition,
            "active_presets": active_presets,
            "reasoning": reasoning,
            "market_snapshot": market_snapshot,
            "last_scan_at": last_scan_at,
            "next_scan_at": next_scan_at,
            "pipeline": {
                "candidates_in_queue": queue_count,
                "active_signals": active_signals,
                "open_positions": open_positions,
                "today_pl": today_pl,
            },
            "capital_used": round(float(capital_used), 2),
        }

    except Exception as e:
        logger.error(f"Autopilot status error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to fetch autopilot status: {str(e)}"},
        )


# =============================================================================
# GET /activity — Recent autopilot log entries
# =============================================================================

@router.get("/activity")
async def get_autopilot_activity(
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Return paginated AutopilotLog entries from the last N hours."""
    try:
        cutoff = datetime.now() - timedelta(hours=hours)
        logs = (
            db.query(AutopilotLog)
            .filter(AutopilotLog.timestamp >= cutoff)
            .order_by(AutopilotLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [log.to_dict() for log in logs]

    except Exception as e:
        logger.error(f"Autopilot activity error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to fetch autopilot activity: {str(e)}"},
        )


# =============================================================================
# GET /market-state — Current market intelligence snapshot
# =============================================================================

@router.get("/market-state")
async def get_market_state(db: Session = Depends(get_db)):
    """
    Return current market intelligence from all 4 sources
    (MRI, regime, Fear & Greed, Trade Readiness) plus the
    classified condition.
    """
    try:
        selector = get_preset_selector()
        snapshot = await selector._gather_market_snapshot(db)
        score, signal_scores = selector._compute_composite_score(snapshot)
        condition = selector._classify_condition(score, snapshot)
        return {
            "condition": condition,
            "composite_score": round(score, 1),
            "signal_scores": {k: round(v, 1) if v is not None else None for k, v in signal_scores.items()},
            "snapshot": snapshot,
        }

    except Exception as e:
        logger.error(f"Market state error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to fetch market state: {str(e)}"},
        )


# =============================================================================
# POST /calculate-position — Position size calculator
# =============================================================================

@router.post("/calculate-position")
async def calculate_position(req: PositionCalcRequest):
    """
    Calculate position size, risk/reward, and potential outcomes
    given account parameters and trade levels.
    """
    try:
        risk_amount = req.account_size * (req.risk_per_position_pct / 100)
        stop_distance = abs(req.entry_price - req.stop_loss_price)

        if stop_distance <= 0:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Stop loss price must differ from entry price"
                },
            )

        shares = math.floor(risk_amount / stop_distance)
        position_dollars = shares * req.entry_price

        # Cap to max position size
        capped = False
        capped_reason = ""
        if position_dollars > req.max_position_size:
            shares = math.floor(req.max_position_size / req.entry_price)
            position_dollars = shares * req.entry_price
            capped = True
            uncapped_value = risk_amount / stop_distance * req.entry_price
            capped_reason = (
                f"Capped from ${uncapped_value:.0f} "
                f"to max ${req.max_position_size:.0f}"
            )

        if shares <= 0:
            return JSONResponse(
                status_code=400,
                content={
                    "error": (
                        "Calculated share count is 0 — risk amount is too "
                        "small relative to stop distance or entry price"
                    )
                },
            )

        reward_distance = abs(req.take_profit_price - req.entry_price)
        risk_per_share = stop_distance
        reward_per_share = reward_distance
        risk_reward_ratio = (
            reward_per_share / risk_per_share if risk_per_share > 0 else 0
        )

        return {
            "symbol": req.symbol,
            "position_size_dollars": round(position_dollars, 2),
            "shares": shares,
            "risk_amount": round(risk_amount, 2),
            "risk_per_share": round(risk_per_share, 2),
            "reward_per_share": round(reward_per_share, 2),
            "risk_reward_ratio": round(risk_reward_ratio, 2),
            "potential_loss": round(-shares * risk_per_share, 2),
            "potential_profit": round(shares * reward_per_share, 2),
            "potential_loss_pct": round(
                -shares * risk_per_share / req.account_size * 100, 2
            ),
            "potential_profit_pct": round(
                shares * reward_per_share / req.account_size * 100, 2
            ),
            "position_pct_of_account": round(
                position_dollars / req.account_size * 100, 2
            ),
            "capped": capped,
            "capped_reason": capped_reason,
        }

    except Exception as e:
        logger.error(f"Position calc error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Failed to calculate position: {str(e)}"
            },
        )


# =============================================================================
# POST /test-scan — Manual trigger (bypasses market-hours check)
# =============================================================================

@router.post("/test-scan")
async def test_scan(db: Session = Depends(get_db)):
    """
    Manually trigger a smart scan cycle, bypassing market-hours check.

    Use this to test the autopilot pipeline after hours or on weekends.
    Requires automation.auto_scan_enabled=true and presets configured
    (either smart_scan or manual presets).
    """
    try:
        from app.main import auto_scan_job

        logger.info("[Autopilot] Manual test-scan triggered (market hours bypassed)")
        await auto_scan_job(skip_market_check=True)

        # Return latest activity log entries from this run
        recent = db.query(AutopilotLog).order_by(
            AutopilotLog.timestamp.desc()
        ).limit(10).all()

        return {
            "status": "completed",
            "message": "Test scan executed (market hours bypassed)",
            "recent_activity": [log.to_dict() for log in recent],
        }

    except Exception as e:
        logger.error(f"Test scan error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Test scan failed: {str(e)}"},
        )
