"""
Backtesting API Endpoints

POST /run              — Start a backtest (async, returns ID)
GET  /results/{id}     — Get backtest results (poll until completed)
GET  /list             — List recent backtests
DELETE /{id}           — Delete a backtest
"""
import asyncio
import threading
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from loguru import logger

from app.database import get_db, SessionLocal
from app.models.backtest_result import BacktestResult
from app.services.backtesting.engine import backtest_engine

# Limit concurrent backtest threads (Backtrader is CPU+memory intensive)
_BACKTEST_SEMAPHORE = threading.Semaphore(3)
from app.services.backtesting.strategies import STRATEGY_MAP

router = APIRouter()


# ═════════════════════════════════════════════════════════════════════════════
# Request / Response Models
# ═════════════════════════════════════════════════════════════════════════════

class BacktestRequest(BaseModel):
    symbol: str
    strategy: str                         # orb_breakout, vwap_pullback, range_breakout
    timeframe: str = "15m"                # 5m, 15m, 4h
    cap_size: str = "large_cap"           # large_cap, mid_cap, small_cap
    start_date: str                       # YYYY-MM-DD
    end_date: str                         # YYYY-MM-DD
    initial_capital: float = 100000.0
    position_size_pct: float = 10.0

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v):
        if v not in STRATEGY_MAP:
            raise ValueError(f"Unknown strategy: {v}. Options: {list(STRATEGY_MAP.keys())}")
        return v

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v):
        valid = ["5m", "15m", "30m", "1h", "4h", "1d"]
        if v not in valid:
            raise ValueError(f"Invalid timeframe: {v}. Options: {valid}")
        return v

    @field_validator("cap_size")
    @classmethod
    def validate_cap_size(cls, v):
        valid = ["large_cap", "mid_cap", "small_cap"]
        if v not in valid:
            raise ValueError(f"Invalid cap_size: {v}. Options: {valid}")
        return v


# ═════════════════════════════════════════════════════════════════════════════
# Background task runner
# ═════════════════════════════════════════════════════════════════════════════

def _run_backtest_sync(backtest_id: int):
    """Run backtest in a fresh DB session (for background thread).
    Acquires a semaphore slot to limit concurrent backtests to 3."""
    acquired = _BACKTEST_SEMAPHORE.acquire(timeout=300)  # Wait up to 5 min for a slot
    if not acquired:
        logger.warning(f"Backtest {backtest_id}: timed out waiting for semaphore slot")
        db = SessionLocal()
        try:
            record = db.query(BacktestResult).filter(BacktestResult.id == backtest_id).first()
            if record:
                record.status = "failed"
                record.error_message = "Too many concurrent backtests. Try again later."
                db.commit()
        except Exception:
            pass
        finally:
            db.close()
        return

    db = SessionLocal()
    try:
        backtest_engine.run_backtest(backtest_id, db)
    except Exception as e:
        logger.error(f"Background backtest {backtest_id} failed: {e}")
        # Try to mark as failed
        try:
            record = db.query(BacktestResult).filter(BacktestResult.id == backtest_id).first()
            if record and record.status != "completed":
                record.status = "failed"
                record.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        _BACKTEST_SEMAPHORE.release()


# ═════════════════════════════════════════════════════════════════════════════
# Endpoints
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/run")
async def run_backtest(req: BacktestRequest, db: Session = Depends(get_db)):
    """
    Start a new backtest. Returns immediately with backtest ID.
    The backtest runs in a background thread — poll /results/{id} for completion.
    """
    try:
        start_date = date.fromisoformat(req.start_date)
        end_date = date.fromisoformat(req.end_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")

    if end_date <= start_date:
        raise HTTPException(400, "end_date must be after start_date")

    if req.initial_capital < 1000:
        raise HTTPException(400, "initial_capital must be at least $1,000")

    if req.position_size_pct < 1 or req.position_size_pct > 100:
        raise HTTPException(400, "position_size_pct must be between 1 and 100")

    # Create DB record
    record = BacktestResult(
        symbol=req.symbol.upper().strip(),
        strategy=req.strategy,
        timeframe=req.timeframe,
        cap_size=req.cap_size,
        start_date=start_date,
        end_date=end_date,
        initial_capital=req.initial_capital,
        position_size_pct=req.position_size_pct,
        status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Launch in background thread (cerebro.run() is blocking)
    asyncio.get_event_loop().run_in_executor(None, _run_backtest_sync, record.id)

    logger.info(f"Backtest {record.id} started: {req.symbol} {req.strategy} {req.timeframe}")

    return {
        "id": record.id,
        "status": "pending",
        "message": f"Backtest started for {req.symbol} ({req.strategy})",
    }


@router.get("/results/{backtest_id}")
def get_results(backtest_id: int, db: Session = Depends(get_db)):
    """Get backtest results. Poll this until status='completed' or 'failed'."""
    record = db.query(BacktestResult).filter(BacktestResult.id == backtest_id).first()
    if not record:
        raise HTTPException(404, f"Backtest {backtest_id} not found")
    return record.to_dict()


@router.get("/list")
def list_backtests(
    db: Session = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
):
    """List recent backtests, newest first."""
    query = db.query(BacktestResult).order_by(BacktestResult.created_at.desc())

    if symbol:
        query = query.filter(BacktestResult.symbol == symbol.upper())
    if strategy:
        query = query.filter(BacktestResult.strategy == strategy)

    total = query.count()
    records = query.offset(offset).limit(min(limit, 50)).all()

    return {
        "total": total,
        "backtests": [r.to_dict() for r in records],
    }


@router.delete("/{backtest_id}")
def delete_backtest(backtest_id: int, db: Session = Depends(get_db)):
    """Delete a backtest result."""
    record = db.query(BacktestResult).filter(BacktestResult.id == backtest_id).first()
    if not record:
        raise HTTPException(404, f"Backtest {backtest_id} not found")

    db.delete(record)
    db.commit()
    return {"message": f"Backtest {backtest_id} deleted"}
