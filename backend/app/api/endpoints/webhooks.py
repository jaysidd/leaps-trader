"""
Webhook endpoints for receiving trading signals from external providers
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from loguru import logger

from app.database import get_db
from app.models.webhook_alert import WebhookAlert

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class WebhookPayload(BaseModel):
    """
    Schema for incoming webhook payload from trading bot signal provider

    Matches the documentation format:
    - event_type: "new_setup" or "trigger"
    - setup_id: Unique identifier for the setup
    - symbol: Trading pair (e.g., "BTCUSD", "EURUSD")
    - direction: "buy" or "sell"
    - entry_zone: [min_entry, max_entry]
    - stop_loss: Stop Loss price
    - tp1: Take Profit 1 price
    - tp2: Take Profit 2 price
    - current_price: Live price at the time of the event
    - timestamp: UTC timestamp (ISO 8601)
    """
    event_type: str = Field(..., description="Event type: 'new_setup' or 'trigger'")
    setup_id: str = Field(..., description="Unique identifier for the setup")
    symbol: str = Field(..., description="Trading pair symbol")
    direction: str = Field(..., description="Trade direction: 'buy' or 'sell'")
    entry_zone: List[float] = Field(..., description="[min_entry, max_entry] price range")
    stop_loss: float = Field(..., description="Stop loss price")
    tp1: float = Field(..., description="Take profit 1 price")
    tp2: float = Field(..., description="Take profit 2 price")
    current_price: float = Field(..., description="Current market price")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")


class AlertResponse(BaseModel):
    """Response schema for a single alert"""
    id: int
    provider: str
    setup_id: str
    event_type: str
    symbol: str
    direction: str
    entry_zone: Optional[List[float]]
    stop_loss: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    current_price: Optional[float]
    alert_timestamp: Optional[str]
    received_at: Optional[str]
    status: str

    class Config:
        from_attributes = True


class AlertsListResponse(BaseModel):
    """Response schema for list of alerts"""
    alerts: List[AlertResponse]
    total: int
    page: int
    page_size: int


class WebhookConfigRequest(BaseModel):
    """Request schema for saving webhook configuration"""
    provider: str = Field(..., description="Provider name/identifier")
    new_setup_endpoint: Optional[str] = Field(None, description="Endpoint URL for new setup notifications")
    trigger_endpoint: Optional[str] = Field(None, description="Endpoint URL for trigger notifications")


# =============================================================================
# Webhook Receiver Endpoints
# =============================================================================

@router.post("/receive/{provider}")
async def receive_webhook(
    provider: str,
    payload: WebhookPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receive webhook notification from trading signal provider

    This endpoint receives trading signals and stores them for display in the Alerts tab.

    Path Parameters:
        provider: Identifier for the webhook provider (e.g., "tradingbot", "signals")

    Request Body:
        WebhookPayload with trading signal data

    Returns:
        Confirmation of receipt with alert ID
    """
    try:
        logger.info(f"Received webhook from provider '{provider}': {payload.event_type} for {payload.symbol}")

        # Parse timestamp
        try:
            alert_timestamp = datetime.fromisoformat(payload.timestamp.replace('Z', '+00:00'))
        except ValueError:
            alert_timestamp = datetime.utcnow()

        # Check if this setup_id already exists for this provider
        existing_alert = db.query(WebhookAlert).filter(
            WebhookAlert.setup_id == payload.setup_id,
            WebhookAlert.provider == provider
        ).first()

        if existing_alert:
            # Update existing alert (e.g., new_setup -> trigger)
            existing_alert.event_type = payload.event_type
            existing_alert.current_price = payload.current_price
            existing_alert.alert_timestamp = alert_timestamp
            existing_alert.raw_payload = payload.model_dump()

            if payload.event_type == "trigger":
                existing_alert.status = "triggered"

            db.commit()
            db.refresh(existing_alert)

            logger.info(f"Updated existing alert {existing_alert.id} for setup {payload.setup_id}")

            return {
                "status": "updated",
                "alert_id": existing_alert.id,
                "setup_id": payload.setup_id,
                "event_type": payload.event_type,
                "message": f"Alert updated for {payload.symbol}"
            }

        # Create new alert
        alert = WebhookAlert(
            provider=provider,
            setup_id=payload.setup_id,
            event_type=payload.event_type,
            symbol=payload.symbol.upper(),
            direction=payload.direction.lower(),
            entry_zone_min=payload.entry_zone[0] if len(payload.entry_zone) > 0 else None,
            entry_zone_max=payload.entry_zone[1] if len(payload.entry_zone) > 1 else None,
            stop_loss=payload.stop_loss,
            tp1=payload.tp1,
            tp2=payload.tp2,
            current_price=payload.current_price,
            alert_timestamp=alert_timestamp,
            status="active" if payload.event_type == "new_setup" else "triggered",
            raw_payload=payload.model_dump()
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        logger.info(f"Created new alert {alert.id} for {payload.symbol} ({payload.direction})")

        return {
            "status": "created",
            "alert_id": alert.id,
            "setup_id": payload.setup_id,
            "event_type": payload.event_type,
            "message": f"Alert created for {payload.symbol}"
        }

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/receive")
async def receive_webhook_default(
    payload: WebhookPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receive webhook notification (default provider)

    Same as /receive/{provider} but uses 'default' as provider name.
    """
    return await receive_webhook("default", payload, request, db)


# =============================================================================
# Alert Management Endpoints
# =============================================================================

@router.get("/alerts", response_model=AlertsListResponse)
async def get_alerts(
    provider: Optional[str] = Query(None, description="Filter by provider"),
    status: Optional[str] = Query(None, description="Filter by status: active, triggered, expired, dismissed"),
    event_type: Optional[str] = Query(None, description="Filter by event type: new_setup, trigger"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    Get list of webhook alerts

    Returns paginated list of alerts with optional filters.
    """
    try:
        query = db.query(WebhookAlert)

        # Apply filters
        if provider:
            query = query.filter(WebhookAlert.provider == provider)
        if status:
            query = query.filter(WebhookAlert.status == status)
        if event_type:
            query = query.filter(WebhookAlert.event_type == event_type)
        if symbol:
            query = query.filter(WebhookAlert.symbol == symbol.upper())

        # Get total count
        total = query.count()

        # Apply ordering and pagination
        alerts = query.order_by(desc(WebhookAlert.received_at)).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        # Convert to response format
        alert_responses = []
        for alert in alerts:
            alert_responses.append(AlertResponse(
                id=alert.id,
                provider=alert.provider,
                setup_id=alert.setup_id,
                event_type=alert.event_type,
                symbol=alert.symbol,
                direction=alert.direction,
                entry_zone=[alert.entry_zone_min, alert.entry_zone_max] if alert.entry_zone_min else None,
                stop_loss=alert.stop_loss,
                tp1=alert.tp1,
                tp2=alert.tp2,
                current_price=alert.current_price,
                alert_timestamp=alert.alert_timestamp.isoformat() if alert.alert_timestamp else None,
                received_at=alert.received_at.isoformat() if alert.received_at else None,
                status=alert.status
            ))

        return AlertsListResponse(
            alerts=alert_responses,
            total=total,
            page=page,
            page_size=page_size
        )

    except Exception as e:
        logger.error(f"Error fetching alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a single alert by ID

    Returns full alert details including raw payload.
    """
    try:
        alert = db.query(WebhookAlert).filter(WebhookAlert.id == alert_id).first()

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        return {
            **alert.to_dict(),
            "raw_payload": alert.raw_payload
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/alerts/{alert_id}/status")
async def update_alert_status(
    alert_id: int,
    status: str = Query(..., description="New status: active, triggered, expired, dismissed"),
    db: Session = Depends(get_db)
):
    """
    Update alert status

    Valid statuses: active, triggered, expired, dismissed
    """
    valid_statuses = ["active", "triggered", "expired", "dismissed"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    try:
        alert = db.query(WebhookAlert).filter(WebhookAlert.id == alert_id).first()

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        alert.status = status
        db.commit()

        logger.info(f"Updated alert {alert_id} status to {status}")

        return {
            "alert_id": alert_id,
            "status": status,
            "message": "Status updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating alert {alert_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete an alert

    Permanently removes the alert from the database.
    """
    try:
        alert = db.query(WebhookAlert).filter(WebhookAlert.id == alert_id).first()

        if not alert:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

        db.delete(alert)
        db.commit()

        logger.info(f"Deleted alert {alert_id}")

        return {
            "alert_id": alert_id,
            "message": "Alert deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting alert {alert_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts")
async def clear_alerts(
    provider: Optional[str] = Query(None, description="Clear only alerts from specific provider"),
    status: Optional[str] = Query(None, description="Clear only alerts with specific status"),
    db: Session = Depends(get_db)
):
    """
    Clear multiple alerts

    Can filter by provider and/or status.
    Without filters, clears ALL alerts.
    """
    try:
        query = db.query(WebhookAlert)

        if provider:
            query = query.filter(WebhookAlert.provider == provider)
        if status:
            query = query.filter(WebhookAlert.status == status)

        count = query.count()
        query.delete(synchronize_session=False)
        db.commit()

        logger.info(f"Cleared {count} alerts")

        return {
            "deleted_count": count,
            "message": f"Cleared {count} alerts"
        }

    except Exception as e:
        logger.error(f"Error clearing alerts: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Provider Management
# =============================================================================

@router.get("/providers")
async def get_providers(db: Session = Depends(get_db)):
    """
    Get list of unique webhook providers

    Returns list of providers that have sent webhooks.
    """
    try:
        providers = db.query(WebhookAlert.provider).distinct().all()

        return {
            "providers": [p[0] for p in providers]
        }

    except Exception as e:
        logger.error(f"Error fetching providers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_webhook_stats(
    provider: Optional[str] = Query(None, description="Filter by provider"),
    db: Session = Depends(get_db)
):
    """
    Get webhook statistics

    Returns count of alerts by status and event type.
    """
    try:
        query = db.query(WebhookAlert)

        if provider:
            query = query.filter(WebhookAlert.provider == provider)

        total = query.count()

        # Count by status
        active = query.filter(WebhookAlert.status == "active").count()
        triggered = query.filter(WebhookAlert.status == "triggered").count()
        expired = query.filter(WebhookAlert.status == "expired").count()
        dismissed = query.filter(WebhookAlert.status == "dismissed").count()

        # Count by event type
        new_setups = db.query(WebhookAlert).filter(
            WebhookAlert.event_type == "new_setup"
        )
        triggers = db.query(WebhookAlert).filter(
            WebhookAlert.event_type == "trigger"
        )

        if provider:
            new_setups = new_setups.filter(WebhookAlert.provider == provider)
            triggers = triggers.filter(WebhookAlert.provider == provider)

        return {
            "total": total,
            "by_status": {
                "active": active,
                "triggered": triggered,
                "expired": expired,
                "dismissed": dismissed
            },
            "by_event_type": {
                "new_setup": new_setups.count(),
                "trigger": triggers.count()
            }
        }

    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TradingView Webhook Integration
# =============================================================================

class TradingViewPayload(BaseModel):
    """
    Flexible schema for TradingView webhook alerts.

    TradingView can send either:
    1. Simple text message: "LC SP500 5m ORB BREAKOUT LONG | AAPL | Close=150.25"
    2. JSON payload with custom fields

    We support both formats.
    """
    # Text message format (primary)
    message: Optional[str] = Field(None, description="Alert message text")

    # JSON format fields (alternative)
    ticker: Optional[str] = Field(None, description="Stock ticker symbol")
    strategy: Optional[str] = Field(None, description="Strategy name (e.g., 'LC 5m ORB Breakout')")
    direction: Optional[str] = Field(None, description="LONG or SHORT")
    timeframe: Optional[str] = Field(None, description="Timeframe (e.g., '5m', '15m', '4H')")
    playbook: Optional[str] = Field(None, description="Playbook type (e.g., 'Breakout', 'Pullback')")
    close: Optional[float] = Field(None, description="Close price")

    # Optional enrichment fields
    volume: Optional[float] = Field(None, description="Volume at trigger")
    atr: Optional[float] = Field(None, description="ATR value")
    rvol: Optional[float] = Field(None, description="Relative volume")
    rsi: Optional[float] = Field(None, description="RSI value")

    class Config:
        extra = "allow"  # Allow additional fields from TradingView


def parse_tradingview_message(message: str) -> dict:
    """
    Parse TradingView alert message into structured data.

    Expected formats:
    - "LC SP500 5m ORB BREAKOUT LONG | AAPL | Close=150.25"
    - "SC600 15m PULLBACK SHORT | XYZ | Close=25.50"

    Returns dict with: strategy, direction, ticker, close, timeframe, playbook
    """
    result = {
        "strategy": None,
        "direction": None,
        "ticker": None,
        "close": None,
        "timeframe": None,
        "playbook": None,
        "universe": None,
    }

    if not message:
        return result

    # Split by pipe delimiter
    parts = [p.strip() for p in message.split("|")]

    if len(parts) >= 1:
        # First part: strategy info (e.g., "LC SP500 5m ORB BREAKOUT LONG")
        strategy_part = parts[0].upper()
        result["strategy"] = parts[0].strip()

        # Extract direction
        if "LONG" in strategy_part:
            result["direction"] = "buy"
        elif "SHORT" in strategy_part:
            result["direction"] = "sell"

        # Extract timeframe
        for tf in ["1m", "5m", "15m", "30m", "1H", "4H", "1D"]:
            if tf.upper() in strategy_part or tf.lower() in strategy_part:
                result["timeframe"] = tf
                break

        # Extract playbook
        if "BREAKOUT" in strategy_part:
            result["playbook"] = "Breakout"
        elif "PULLBACK" in strategy_part:
            result["playbook"] = "Pullback"
        elif "ORB" in strategy_part:
            result["playbook"] = "ORB Breakout"

        # Extract universe
        if "SP500" in strategy_part or "LC " in strategy_part:
            result["universe"] = "S&P 500"
        elif "SC600" in strategy_part or "SP600" in strategy_part:
            result["universe"] = "S&P 600"

    if len(parts) >= 2:
        # Second part: ticker (e.g., "AAPL")
        result["ticker"] = parts[1].strip().upper()

    if len(parts) >= 3:
        # Third part: Close price (e.g., "Close=150.25")
        close_part = parts[2].strip()
        if "=" in close_part:
            try:
                result["close"] = float(close_part.split("=")[1].strip())
            except (ValueError, IndexError):
                pass

    return result


@router.post("/tradingview")
async def receive_tradingview_webhook(
    payload: TradingViewPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receive webhook notification from TradingView.

    TradingView Webhook Setup:
    1. Create your alert in TradingView
    2. Set Webhook URL to: http://your-server:8000/api/v1/webhooks/tradingview
    3. Set Alert Message using this format:
       {{strategy.order.action}} | {{ticker}} | Close={{close}}

       Or use custom format:
       LC SP500 5m ORB BREAKOUT LONG | {{ticker}} | Close={{close}}

    Alternatively, use JSON format in alert message:
    {
        "ticker": "{{ticker}}",
        "strategy": "LC 5m ORB Breakout",
        "direction": "LONG",
        "close": {{close}},
        "timeframe": "5m",
        "playbook": "Breakout"
    }

    Returns:
        Confirmation of receipt with alert ID
    """
    try:
        logger.info(f"Received TradingView webhook: {payload}")

        # Parse the message if provided
        parsed = {}
        if payload.message:
            parsed = parse_tradingview_message(payload.message)

        # Use parsed values or direct payload fields
        ticker = payload.ticker or parsed.get("ticker") or "UNKNOWN"
        direction = payload.direction or parsed.get("direction") or "buy"
        close_price = payload.close or parsed.get("close")
        strategy = payload.strategy or parsed.get("strategy") or "TradingView Alert"
        timeframe = payload.timeframe or parsed.get("timeframe") or ""
        playbook = payload.playbook or parsed.get("playbook") or ""

        # Normalize direction
        direction = direction.lower()
        if direction in ["long", "buy"]:
            direction = "buy"
        elif direction in ["short", "sell"]:
            direction = "sell"

        # Generate unique setup_id
        import uuid
        setup_id = f"tv-{uuid.uuid4().hex[:8]}"

        # Build strategy description
        strategy_desc = strategy
        if timeframe and timeframe not in strategy:
            strategy_desc = f"{strategy} ({timeframe})"

        # Create the alert
        alert = WebhookAlert(
            provider="TradingView",
            setup_id=setup_id,
            event_type="trigger",  # TradingView alerts are always triggers
            symbol=ticker.upper(),
            direction=direction,
            entry_zone_min=close_price,
            entry_zone_max=close_price,
            stop_loss=None,  # TradingView doesn't send this typically
            tp1=None,
            tp2=None,
            current_price=close_price,
            alert_timestamp=datetime.utcnow(),
            status="triggered",
            raw_payload={
                "message": payload.message,
                "strategy": strategy_desc,
                "timeframe": timeframe,
                "playbook": playbook,
                "universe": parsed.get("universe"),
                "volume": payload.volume,
                "atr": payload.atr,
                "rvol": payload.rvol,
                "rsi": payload.rsi,
                **payload.model_dump(exclude_none=True)
            }
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        logger.info(f"Created TradingView alert {alert.id}: {ticker} {direction} @ {close_price}")

        return {
            "status": "created",
            "alert_id": alert.id,
            "setup_id": setup_id,
            "symbol": ticker,
            "direction": direction,
            "strategy": strategy_desc,
            "message": f"TradingView alert received for {ticker}"
        }

    except Exception as e:
        logger.error(f"Error processing TradingView webhook: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tradingview/text")
async def receive_tradingview_text(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receive raw text webhook from TradingView.

    Some TradingView setups send plain text instead of JSON.
    This endpoint handles that case.

    Expected format:
        LC SP500 5m ORB BREAKOUT LONG | AAPL | Close=150.25
    """
    try:
        # Read raw body
        body = await request.body()
        message = body.decode("utf-8").strip()

        logger.info(f"Received TradingView text webhook: {message}")

        # Parse the message
        parsed = parse_tradingview_message(message)

        if not parsed.get("ticker"):
            raise HTTPException(
                status_code=400,
                detail="Could not parse ticker from message. Expected format: 'STRATEGY | TICKER | Close=PRICE'"
            )

        # Generate unique setup_id
        import uuid
        setup_id = f"tv-{uuid.uuid4().hex[:8]}"

        # Create the alert
        alert = WebhookAlert(
            provider="TradingView",
            setup_id=setup_id,
            event_type="trigger",
            symbol=parsed["ticker"],
            direction=parsed.get("direction", "buy"),
            entry_zone_min=parsed.get("close"),
            entry_zone_max=parsed.get("close"),
            stop_loss=None,
            tp1=None,
            tp2=None,
            current_price=parsed.get("close"),
            alert_timestamp=datetime.utcnow(),
            status="triggered",
            raw_payload={
                "message": message,
                "strategy": parsed.get("strategy"),
                "timeframe": parsed.get("timeframe"),
                "playbook": parsed.get("playbook"),
                "universe": parsed.get("universe"),
            }
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        logger.info(f"Created TradingView alert {alert.id}: {parsed['ticker']} {parsed.get('direction')} @ {parsed.get('close')}")

        return {
            "status": "created",
            "alert_id": alert.id,
            "setup_id": setup_id,
            "parsed": parsed,
            "message": f"TradingView alert received for {parsed['ticker']}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing TradingView text webhook: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
