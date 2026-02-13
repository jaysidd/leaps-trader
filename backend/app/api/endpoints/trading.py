"""
Trading API endpoints
Order execution and position management via Alpaca
"""
from enum import Enum

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel, field_validator
from loguru import logger
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.trading.alpaca_trading_service import alpaca_trading_service
from app.models.trading_signal import TradingSignal
from app.api.auth import require_trading_auth

router = APIRouter(dependencies=[Depends(require_trading_auth)])


# =============================================================================
# Request/Response Models
# =============================================================================

VALID_SIDES = {"buy", "sell"}
VALID_ORDER_TYPES = {"market", "limit"}
VALID_TIF = {"day", "gtc", "ioc", "fok"}


class PlaceOrderRequest(BaseModel):
    """Request to place an order"""
    symbol: str
    qty: float
    side: str  # buy, sell
    order_type: str = "market"  # market, limit
    limit_price: Optional[float] = None
    time_in_force: str = "day"  # day, gtc, ioc, fok
    signal_id: Optional[int] = None  # Link to trading signal

    @field_validator("side")
    @classmethod
    def validate_side(cls, v):
        if v.lower().strip() not in VALID_SIDES:
            raise ValueError(f"side must be 'buy' or 'sell', got '{v}'")
        return v.lower().strip()

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, v):
        if v <= 0:
            raise ValueError(f"qty must be positive, got {v}")
        return v

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v):
        if v.lower().strip() not in VALID_ORDER_TYPES:
            raise ValueError(f"order_type must be 'market' or 'limit', got '{v}'")
        return v.lower().strip()

    @field_validator("time_in_force")
    @classmethod
    def validate_tif(cls, v):
        if v.lower().strip() not in VALID_TIF:
            raise ValueError(f"time_in_force must be one of {VALID_TIF}, got '{v}'")
        return v.lower().strip()


class ClosePositionRequest(BaseModel):
    """Request to close a position"""
    qty: Optional[float] = None  # Shares to close
    percentage: Optional[float] = None  # Percentage to close (0-100)

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, v):
        if v is not None and v <= 0:
            raise ValueError(f"qty must be positive, got {v}")
        return v

    @field_validator("percentage")
    @classmethod
    def validate_percentage(cls, v):
        if v is not None and (v <= 0 or v > 100):
            raise ValueError(f"percentage must be between 0 and 100, got {v}")
        return v


class SetTradingModeRequest(BaseModel):
    """Request to set trading mode"""
    paper_mode: bool


# =============================================================================
# Account & Mode Endpoints
# =============================================================================

@router.get("/account", response_model=dict)
async def get_account():
    """
    Get Alpaca account information.
    Returns: equity, buying_power, cash, portfolio_value, etc.
    """
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available. Check Alpaca API keys.")

    account = alpaca_trading_service.get_account()
    if not account:
        raise HTTPException(status_code=500, detail="Failed to get account info")

    return account


@router.get("/mode", response_model=dict)
async def get_trading_mode():
    """Get current trading mode (paper vs live)"""
    return {
        "paper_mode": alpaca_trading_service.is_paper_mode,
        "mode": "paper" if alpaca_trading_service.is_paper_mode else "live",
        "is_available": alpaca_trading_service.is_available
    }


@router.put("/mode", response_model=dict)
async def set_trading_mode(request: SetTradingModeRequest):
    """
    Switch between paper and live trading modes.
    WARNING: Live mode uses real money!
    """
    old_mode = alpaca_trading_service.is_paper_mode

    try:
        alpaca_trading_service.set_paper_mode(request.paper_mode)

        new_mode = "PAPER" if request.paper_mode else "LIVE"
        old_mode_str = "PAPER" if old_mode else "LIVE"

        logger.info(f"Trading mode changed from {old_mode_str} to {new_mode}")

        return {
            "success": True,
            "paper_mode": request.paper_mode,
            "mode": "paper" if request.paper_mode else "live",
            "message": f"Switched to {new_mode} trading mode",
            "warning": "Live trading uses REAL money!" if not request.paper_mode else None
        }

    except Exception as e:
        logger.error(f"Error setting trading mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Order Endpoints
# =============================================================================

@router.post("/order", response_model=dict)
async def place_order(request: PlaceOrderRequest, db: Session = Depends(get_db)):
    """
    Place a market or limit order.

    If signal_id is provided, links the order to the trading signal.
    """
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available")

    try:
        # Place order based on type
        if request.order_type == "market":
            result = alpaca_trading_service.place_market_order(
                symbol=request.symbol,
                qty=request.qty,
                side=request.side,
                time_in_force=request.time_in_force
            )
        elif request.order_type == "limit":
            if not request.limit_price:
                raise HTTPException(status_code=400, detail="Limit price required for limit orders")

            result = alpaca_trading_service.place_limit_order(
                symbol=request.symbol,
                qty=request.qty,
                side=request.side,
                limit_price=request.limit_price,
                time_in_force=request.time_in_force
            )
        else:
            raise HTTPException(status_code=400, detail=f"Invalid order type: {request.order_type}")

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        # Link to trading signal if provided
        if request.signal_id:
            signal = db.query(TradingSignal).filter(TradingSignal.id == request.signal_id).first()
            if signal:
                signal.trade_executed = True
                signal.trade_execution_id = result.get("order_id")
                signal.status = "executed"
                db.commit()

        return {
            "success": True,
            "order": result,
            "paper_mode": alpaca_trading_service.is_paper_mode,
            "message": f"Order placed: {request.side.upper()} {request.qty} {request.symbol}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders", response_model=dict)
async def get_orders(
    status: str = "open",
    limit: int = 50,
    symbol: Optional[str] = None
):
    """
    Get orders with optional filters.

    Args:
        status: 'open', 'closed', 'all'
        limit: Max number of orders
        symbol: Filter by symbol (optional)
    """
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available")

    symbols = [symbol.upper()] if symbol else None
    orders = alpaca_trading_service.get_orders(status=status, limit=limit, symbols=symbols)

    return {
        "orders": orders,
        "count": len(orders),
        "status_filter": status
    }


@router.get("/orders/{order_id}", response_model=dict)
async def get_order(order_id: str):
    """Get details for a specific order"""
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available")

    order = alpaca_trading_service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


@router.delete("/orders/{order_id}", response_model=dict)
async def cancel_order(order_id: str):
    """Cancel an open order"""
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available")

    result = alpaca_trading_service.cancel_order(order_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


# =============================================================================
# Position Endpoints
# =============================================================================

@router.get("/positions", response_model=dict)
async def get_all_positions():
    """Get all open positions with P/L"""
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available")

    positions = alpaca_trading_service.get_all_positions()

    # Calculate totals
    total_value = sum(p.get("market_value", 0) for p in positions)
    total_pl = sum(p.get("unrealized_pl", 0) for p in positions)

    return {
        "positions": positions,
        "count": len(positions),
        "total_market_value": total_value,
        "total_unrealized_pl": total_pl,
        "paper_mode": alpaca_trading_service.is_paper_mode
    }


@router.get("/positions/{symbol}", response_model=dict)
async def get_position(symbol: str):
    """
    Get position for a specific symbol with P/L.

    Returns unrealized P/L in dollars and percentage.
    """
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available")

    position = alpaca_trading_service.get_position(symbol)
    if not position:
        return {
            "symbol": symbol.upper(),
            "has_position": False,
            "message": f"No open position for {symbol}"
        }

    return {
        "symbol": symbol.upper(),
        "has_position": True,
        "position": position
    }


@router.post("/positions/{symbol}/close", response_model=dict)
async def close_position(symbol: str, request: ClosePositionRequest = None):
    """
    Close a position (full or partial).

    If no qty or percentage specified, closes entire position.
    """
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available")

    qty = request.qty if request else None
    percentage = request.percentage if request else None

    result = alpaca_trading_service.close_position(
        symbol=symbol,
        qty=qty,
        percentage=percentage
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    close_type = "partial" if qty or percentage else "full"

    return {
        "success": True,
        "close_type": close_type,
        "order": result,
        "message": f"Position closed: {symbol}"
    }


# =============================================================================
# Quick Actions
# =============================================================================

@router.post("/quick-buy/{symbol}", response_model=dict)
async def quick_buy(
    symbol: str,
    qty: float,
    signal_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Quick market buy order"""
    request = PlaceOrderRequest(
        symbol=symbol,
        qty=qty,
        side="buy",
        order_type="market",
        signal_id=signal_id
    )
    return await place_order(request, db)


@router.post("/quick-sell/{symbol}", response_model=dict)
async def quick_sell(symbol: str, qty: Optional[float] = None):
    """
    Quick market sell order.
    If qty not specified, sells entire position.
    """
    if not alpaca_trading_service.is_available:
        raise HTTPException(status_code=503, detail="Trading service not available")

    if qty:
        # Specific quantity
        result = alpaca_trading_service.place_market_order(
            symbol=symbol,
            qty=qty,
            side="sell",
            time_in_force="day"
        )
    else:
        # Close entire position
        result = alpaca_trading_service.close_position(symbol)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "success": True,
        "order": result,
        "message": f"Sold {symbol}"
    }
