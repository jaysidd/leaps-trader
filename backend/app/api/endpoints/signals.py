"""
Signal Processing API endpoints
Manage signal queue and trading signals
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models.signal_queue import SignalQueue
from app.models.trading_signal import TradingSignal

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

VALID_TIMEFRAMES = {"5m", "15m", "1h", "1d"}
VALID_STRATEGIES = {"auto", "orb_breakout", "vwap_pullback", "range_breakout", "trend_following", "mean_reversion"}
VALID_CAP_SIZES = {"large_cap", "mid_cap", "small_cap", None}
VALID_QUEUE_STATUSES = {"active", "paused", "completed", "removed"}

import re
_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")


class AddToQueueRequest(BaseModel):
    """Request to add stocks to signal queue"""
    symbols: List[str]
    timeframe: str = "5m"  # 5m, 15m, 1h, 1d
    strategy: Optional[str] = "auto"  # auto, orb_breakout, vwap_pullback, range_breakout
    cap_size: Optional[str] = None  # large_cap, small_cap
    source: Optional[str] = "manual"


class AddToQueueItem(BaseModel):
    """Single item to add to queue"""
    symbol: str
    name: Optional[str] = None
    timeframe: str = "5m"
    strategy: Optional[str] = "auto"
    cap_size: Optional[str] = None


class UpdateQueueItemRequest(BaseModel):
    """Request to update a queue item"""
    timeframe: Optional[str] = None
    strategy: Optional[str] = None
    status: Optional[str] = None


class QueueItemResponse(BaseModel):
    """Response for a queue item"""
    id: int
    symbol: str
    name: Optional[str]
    timeframe: str
    strategy: Optional[str]
    cap_size: Optional[str]
    status: str
    times_checked: int
    signals_generated: int
    created_at: str
    last_checked_at: Optional[str]


class SignalSummaryResponse(BaseModel):
    """Compact signal for list views"""
    id: int
    symbol: str
    name: Optional[str]
    timeframe: str
    strategy: str
    direction: str
    confidence_score: Optional[float]
    entry_price: Optional[float]
    stop_loss: Optional[float]
    target_1: Optional[float]
    risk_reward_ratio: Optional[float]
    status: str
    is_read: bool
    trade_executed: bool
    generated_at: str


# =============================================================================
# Signal Queue Endpoints
# =============================================================================

@router.post("/queue/add", response_model=dict)
async def add_to_queue(request: AddToQueueRequest, db: Session = Depends(get_db)):
    """
    Add multiple stocks to the signal processing queue.
    Used when user selects stocks from scan results.
    """
    # ── Input validation ──────────────────────────────────────────
    if not request.symbols:
        raise HTTPException(400, "symbols list cannot be empty")
    if len(request.symbols) > 100:
        raise HTTPException(400, "Cannot add more than 100 symbols at once")
    if request.timeframe not in VALID_TIMEFRAMES:
        raise HTTPException(400, f"Invalid timeframe. Must be one of: {sorted(VALID_TIMEFRAMES)}")
    if request.strategy and request.strategy not in VALID_STRATEGIES:
        raise HTTPException(400, f"Invalid strategy. Must be one of: {sorted(VALID_STRATEGIES)}")
    for sym in request.symbols:
        if not _SYMBOL_RE.match(sym.upper().strip()):
            raise HTTPException(400, f"Invalid symbol: '{sym}'. Must be 1-5 uppercase letters.")

    try:
        added = []
        skipped = []

        for symbol in request.symbols:
            symbol = symbol.upper().strip()

            # Check if already in active queue
            existing = db.query(SignalQueue).filter(
                SignalQueue.symbol == symbol,
                SignalQueue.timeframe == request.timeframe,
                SignalQueue.status == "active"
            ).first()

            if existing:
                skipped.append(symbol)
                continue

            # Add to queue
            queue_item = SignalQueue(
                symbol=symbol,
                timeframe=request.timeframe,
                strategy=request.strategy,
                cap_size=request.cap_size,
                source=request.source,
                status="active"
            )
            db.add(queue_item)
            added.append(symbol)

        db.commit()

        logger.info(f"Added {len(added)} symbols to signal queue: {added}")

        return {
            "success": True,
            "added": added,
            "added_count": len(added),
            "skipped": skipped,
            "skipped_count": len(skipped),
            "message": f"Added {len(added)} stocks to signal processing queue"
        }

    except Exception as e:
        logger.error(f"Error adding to queue: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/add-single", response_model=dict)
async def add_single_to_queue(request: AddToQueueItem, db: Session = Depends(get_db)):
    """Add a single stock to the signal processing queue with name"""
    # ── Input validation ──────────────────────────────────────────
    if not _SYMBOL_RE.match(request.symbol.upper().strip()):
        raise HTTPException(400, f"Invalid symbol: '{request.symbol}'. Must be 1-5 uppercase letters.")
    if request.timeframe not in VALID_TIMEFRAMES:
        raise HTTPException(400, f"Invalid timeframe. Must be one of: {sorted(VALID_TIMEFRAMES)}")
    if request.strategy and request.strategy not in VALID_STRATEGIES:
        raise HTTPException(400, f"Invalid strategy. Must be one of: {sorted(VALID_STRATEGIES)}")

    try:
        symbol = request.symbol.upper().strip()

        # Check if already in active queue
        existing = db.query(SignalQueue).filter(
            SignalQueue.symbol == symbol,
            SignalQueue.timeframe == request.timeframe,
            SignalQueue.status == "active"
        ).first()

        if existing:
            return {
                "success": False,
                "message": f"{symbol} already in queue for {request.timeframe}",
                "existing_id": existing.id
            }

        # Add to queue
        queue_item = SignalQueue(
            symbol=symbol,
            name=request.name,
            timeframe=request.timeframe,
            strategy=request.strategy,
            cap_size=request.cap_size,
            source="manual",
            status="active"
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)

        logger.info(f"Added {symbol} to signal queue")

        return {
            "success": True,
            "queue_item": queue_item.to_dict(),
            "message": f"Added {symbol} to signal processing queue"
        }

    except Exception as e:
        logger.error(f"Error adding to queue: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue", response_model=dict)
async def list_queue(
    status: Optional[str] = None,
    timeframe: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """List signal queue items with optional filters"""
    try:
        query = db.query(SignalQueue)

        if status:
            query = query.filter(SignalQueue.status == status)
        if timeframe:
            query = query.filter(SignalQueue.timeframe == timeframe)

        total = query.count()
        items = query.order_by(SignalQueue.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # Get stats
        active_count = db.query(SignalQueue).filter(SignalQueue.status == "active").count()
        paused_count = db.query(SignalQueue).filter(SignalQueue.status == "paused").count()

        return {
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "stats": {
                "active": active_count,
                "paused": paused_count,
                "total": total
            }
        }

    except Exception as e:
        logger.error(f"Error listing queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/{item_id}", response_model=dict)
async def get_queue_item(item_id: int, db: Session = Depends(get_db)):
    """Get a single queue item"""
    item = db.query(SignalQueue).filter(SignalQueue.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    return item.to_dict()


@router.patch("/queue/{item_id}", response_model=dict)
async def update_queue_item(item_id: int, request: UpdateQueueItemRequest, db: Session = Depends(get_db)):
    """Update a queue item"""
    item = db.query(SignalQueue).filter(SignalQueue.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    # ── Input validation ──────────────────────────────────────────
    if request.timeframe and request.timeframe not in VALID_TIMEFRAMES:
        raise HTTPException(400, f"Invalid timeframe. Must be one of: {sorted(VALID_TIMEFRAMES)}")
    if request.strategy and request.strategy not in VALID_STRATEGIES:
        raise HTTPException(400, f"Invalid strategy. Must be one of: {sorted(VALID_STRATEGIES)}")
    if request.status and request.status not in VALID_QUEUE_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {sorted(VALID_QUEUE_STATUSES)}")

    try:
        if request.timeframe:
            item.timeframe = request.timeframe
        if request.strategy:
            item.strategy = request.strategy
        if request.status:
            item.status = request.status

        db.commit()
        db.refresh(item)

        return {
            "success": True,
            "queue_item": item.to_dict(),
            "message": "Queue item updated"
        }

    except Exception as e:
        logger.error(f"Error updating queue item: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/queue/clear", response_model=dict)
async def clear_queue(
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Clear queue items (also removes related trading signals to avoid FK violations)"""
    try:
        queue_query = db.query(SignalQueue)
        if status:
            queue_query = queue_query.filter(SignalQueue.status == status)

        # Get IDs of queue items to be deleted
        queue_ids = [item.id for item in queue_query.all()]

        # Delete related trading signals first to avoid FK constraint
        signals_deleted = 0
        if queue_ids:
            signals_deleted = db.query(TradingSignal).filter(
                TradingSignal.queue_id.in_(queue_ids)
            ).delete(synchronize_session=False)

        count = queue_query.delete(synchronize_session=False)
        db.commit()

        return {
            "success": True,
            "deleted_count": count,
            "signals_deleted": signals_deleted,
            "message": f"Cleared {count} items from queue (and {signals_deleted} related signals)"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/queue/{item_id}", response_model=dict)
async def remove_from_queue(item_id: int, db: Session = Depends(get_db)):
    """Remove a stock from the signal queue (also removes related signals)"""
    item = db.query(SignalQueue).filter(SignalQueue.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    try:
        symbol = item.symbol
        # Delete related trading signals first to avoid FK constraint
        db.query(TradingSignal).filter(TradingSignal.queue_id == item_id).delete(synchronize_session=False)
        db.delete(item)
        db.commit()

        return {
            "success": True,
            "message": f"Removed {symbol} from signal queue"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error removing from queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/{item_id}/pause", response_model=dict)
async def pause_queue_item(item_id: int, db: Session = Depends(get_db)):
    """Pause monitoring for a queue item"""
    item = db.query(SignalQueue).filter(SignalQueue.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    item.status = "paused"
    db.commit()

    return {
        "success": True,
        "message": f"Paused monitoring for {item.symbol}",
        "status": "paused"
    }


@router.post("/queue/{item_id}/resume", response_model=dict)
async def resume_queue_item(item_id: int, db: Session = Depends(get_db)):
    """Resume monitoring for a paused queue item"""
    item = db.query(SignalQueue).filter(SignalQueue.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    item.status = "active"
    db.commit()

    return {
        "success": True,
        "message": f"Resumed monitoring for {item.symbol}",
        "status": "active"
    }


# =============================================================================
# Trading Signals Endpoints
# =============================================================================

@router.get("/", response_model=dict)
async def list_signals(
    status: Optional[str] = None,
    direction: Optional[str] = None,
    timeframe: Optional[str] = None,
    symbol: Optional[str] = None,
    is_read: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """List trading signals with optional filters"""
    try:
        query = db.query(TradingSignal)

        if status:
            query = query.filter(TradingSignal.status == status)
        if direction:
            query = query.filter(TradingSignal.direction == direction)
        if timeframe:
            query = query.filter(TradingSignal.timeframe == timeframe)
        if symbol:
            query = query.filter(TradingSignal.symbol == symbol.upper())
        if is_read is not None:
            query = query.filter(TradingSignal.is_read == is_read)

        total = query.count()
        signals = query.order_by(TradingSignal.generated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return {
            "signals": [s.to_summary_dict() for s in signals],
            "total": total,
            "page": page,
            "page_size": page_size
        }

    except Exception as e:
        logger.error(f"Error listing signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/unread-count", response_model=dict)
async def get_unread_count(db: Session = Depends(get_db)):
    """Get count of unread signals - used for bell icon badge"""
    try:
        count = db.query(TradingSignal).filter(
            TradingSignal.is_read == False,
            TradingSignal.status == "active"
        ).count()

        return {
            "unread_count": count
        }

    except Exception as e:
        logger.error(f"Error getting unread count: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{signal_id}", response_model=dict)
async def get_signal(signal_id: int, db: Session = Depends(get_db)):
    """Get full signal details"""
    signal = db.query(TradingSignal).filter(TradingSignal.id == signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    return signal.to_dict()


@router.post("/{signal_id}/read", response_model=dict)
async def mark_signal_read(signal_id: int, db: Session = Depends(get_db)):
    """Mark a signal as read"""
    signal = db.query(TradingSignal).filter(TradingSignal.id == signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal.is_read = True
    signal.read_at = datetime.utcnow()
    db.commit()

    return {
        "success": True,
        "message": "Signal marked as read"
    }


@router.post("/mark-all-read", response_model=dict)
async def mark_all_signals_read(db: Session = Depends(get_db)):
    """Mark all signals as read"""
    count = db.query(TradingSignal).filter(
        TradingSignal.is_read == False
    ).update({
        "is_read": True,
        "read_at": datetime.utcnow()
    })
    db.commit()

    return {
        "success": True,
        "marked_count": count,
        "message": f"Marked {count} signals as read"
    }


@router.post("/{signal_id}/invalidate", response_model=dict)
async def invalidate_signal(signal_id: int, db: Session = Depends(get_db)):
    """Invalidate a signal (conditions no longer met)"""
    signal = db.query(TradingSignal).filter(TradingSignal.id == signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal.status = "invalidated"
    db.commit()

    return {
        "success": True,
        "message": f"Signal for {signal.symbol} invalidated"
    }


@router.delete("/clear", response_model=dict)
async def clear_signals(
    status: Optional[str] = None,
    is_read: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Clear signals with optional filters"""
    try:
        query = db.query(TradingSignal)
        if status:
            query = query.filter(TradingSignal.status == status)
        if is_read is not None:
            query = query.filter(TradingSignal.is_read == is_read)

        count = query.delete()
        db.commit()

        return {
            "success": True,
            "deleted_count": count,
            "message": f"Cleared {count} signals"
        }

    except Exception as e:
        logger.error(f"Error clearing signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{signal_id}", response_model=dict)
async def delete_signal(signal_id: int, db: Session = Depends(get_db)):
    """Delete a signal"""
    signal = db.query(TradingSignal).filter(TradingSignal.id == signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    try:
        db.delete(signal)
        db.commit()

        return {
            "success": True,
            "message": "Signal deleted"
        }

    except Exception as e:
        logger.error(f"Error deleting signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Stats Endpoints
# =============================================================================

@router.get("/stats/summary", response_model=dict)
async def get_signal_stats(db: Session = Depends(get_db)):
    """Get signal processing statistics (consolidated queries)"""
    try:
        from sqlalchemy import case, literal

        # Single query for queue stats (replaces 2 COUNT queries)
        queue_row = db.query(
            func.sum(case((SignalQueue.status == "active", 1), else_=0)).label("active"),
            func.sum(case((SignalQueue.status == "paused", 1), else_=0)).label("paused"),
        ).one()
        queue_active = int(queue_row.active or 0)
        queue_paused = int(queue_row.paused or 0)

        # Single query for signal stats (replaces 5 COUNT queries)
        sig_row = db.query(
            func.sum(case(
                (func.date(TradingSignal.generated_at) == func.current_date(), 1),
                else_=0,
            )).label("today"),
            func.sum(case(
                ((TradingSignal.is_read == False) & (TradingSignal.status == "active"), 1),
                else_=0,
            )).label("unread"),
            func.sum(case(
                (TradingSignal.trade_executed == True, 1), else_=0,
            )).label("executed"),
            func.sum(case(
                (TradingSignal.direction == "buy", 1), else_=0,
            )).label("buy"),
            func.sum(case(
                (TradingSignal.direction == "sell", 1), else_=0,
            )).label("sell"),
        ).one()

        return {
            "queue": {
                "active": queue_active,
                "paused": queue_paused,
                "total": queue_active + queue_paused,
            },
            "signals": {
                "today": int(sig_row.today or 0),
                "unread": int(sig_row.unread or 0),
                "executed": int(sig_row.executed or 0),
                "by_direction": {
                    "buy": int(sig_row.buy or 0),
                    "sell": int(sig_row.sell or 0),
                },
            },
        }

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
