"""
User Alerts API endpoints
Create, manage, and check dynamic alerts
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_alert import UserAlert, AlertNotification, AlertType, AlertFrequency
from app.services.alerts.alert_service import alert_service

router = APIRouter()


# Request/Response Models
class CreateAlertRequest(BaseModel):
    """Request to create a new alert"""
    name: str
    description: Optional[str] = None
    symbol: Optional[str] = None
    watchlist: Optional[str] = None
    alert_type: str
    threshold_value: Optional[float] = None
    threshold_value_2: Optional[float] = None
    sma_period: Optional[int] = None
    screening_criteria: Optional[dict] = None
    frequency: str = "once"
    notification_channels: List[str] = ["in_app"]
    telegram_chat_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class UpdateAlertRequest(BaseModel):
    """Request to update an alert"""
    name: Optional[str] = None
    description: Optional[str] = None
    threshold_value: Optional[float] = None
    threshold_value_2: Optional[float] = None
    frequency: Optional[str] = None
    notification_channels: Optional[List[str]] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


class AlertResponse(BaseModel):
    """Alert response model"""
    id: int
    name: str
    description: Optional[str]
    symbol: Optional[str]
    watchlist: Optional[str]
    alert_type: str
    alert_type_description: str
    threshold_value: Optional[float]
    threshold_value_2: Optional[float]
    sma_period: Optional[int]
    frequency: str
    is_active: bool
    notification_channels: List[str]
    times_triggered: int
    last_triggered_at: Optional[str]
    last_triggered_value: Optional[float]
    created_at: str
    expires_at: Optional[str]


class NotificationResponse(BaseModel):
    """Notification response model"""
    id: int
    alert_id: int
    alert_name: str
    symbol: str
    alert_type: str
    triggered_value: Optional[float]
    threshold_value: Optional[float]
    message: str
    is_read: bool
    triggered_at: str


# Endpoints
@router.get("/types")
async def get_alert_types():
    """Get available alert types with descriptions"""
    return {
        "alert_types": [
            {
                "value": AlertType.IV_RANK_BELOW.value,
                "label": "IV Rank Below",
                "description": "Alert when IV Rank drops below threshold",
                "requires_threshold": True,
                "threshold_label": "IV Rank (%)",
                "default_threshold": 30
            },
            {
                "value": AlertType.IV_RANK_ABOVE.value,
                "label": "IV Rank Above",
                "description": "Alert when IV Rank rises above threshold",
                "requires_threshold": True,
                "threshold_label": "IV Rank (%)",
                "default_threshold": 70
            },
            {
                "value": AlertType.PRICE_ABOVE.value,
                "label": "Price Above",
                "description": "Alert when price crosses above level",
                "requires_threshold": True,
                "threshold_label": "Price ($)"
            },
            {
                "value": AlertType.PRICE_BELOW.value,
                "label": "Price Below",
                "description": "Alert when price drops below level",
                "requires_threshold": True,
                "threshold_label": "Price ($)"
            },
            {
                "value": AlertType.RSI_OVERSOLD.value,
                "label": "RSI Oversold",
                "description": "Alert when RSI indicates oversold conditions",
                "requires_threshold": True,
                "threshold_label": "RSI Level",
                "default_threshold": 30
            },
            {
                "value": AlertType.RSI_OVERBOUGHT.value,
                "label": "RSI Overbought",
                "description": "Alert when RSI indicates overbought conditions",
                "requires_threshold": True,
                "threshold_label": "RSI Level",
                "default_threshold": 70
            },
            {
                "value": AlertType.PRICE_CROSS_SMA.value,
                "label": "Price Cross SMA",
                "description": "Alert when price crosses above moving average",
                "requires_threshold": False,
                "requires_sma_period": True,
                "sma_options": [20, 50, 100, 200]
            },
            {
                "value": AlertType.EARNINGS_APPROACHING.value,
                "label": "Earnings Approaching",
                "description": "Alert when earnings are within X days",
                "requires_threshold": True,
                "threshold_label": "Days Before Earnings",
                "default_threshold": 14
            },
        ],
        "frequencies": [
            {"value": "once", "label": "Once", "description": "Trigger once then deactivate"},
            {"value": "daily", "label": "Daily", "description": "Check once per day"},
            {"value": "continuous", "label": "Continuous", "description": "Check every scan cycle"},
        ],
        "notification_channels": [
            {"value": "in_app", "label": "In-App", "description": "Show in notifications panel"},
            {"value": "telegram", "label": "Telegram", "description": "Send to Telegram bot"},
        ]
    }


@router.post("/", response_model=dict)
async def create_alert(request: CreateAlertRequest, db: Session = Depends(get_db)):
    """Create a new user alert"""
    try:
        # Validate alert type
        valid_types = [t.value for t in AlertType]
        if request.alert_type not in valid_types:
            raise HTTPException(status_code=400, detail=f"Invalid alert type: {request.alert_type}")

        # Validate frequency
        valid_frequencies = [f.value for f in AlertFrequency]
        if request.frequency not in valid_frequencies:
            raise HTTPException(status_code=400, detail=f"Invalid frequency: {request.frequency}")

        # Create alert
        alert = UserAlert(
            name=request.name,
            description=request.description,
            symbol=request.symbol.upper() if request.symbol else None,
            watchlist=request.watchlist,
            alert_type=request.alert_type,
            threshold_value=request.threshold_value,
            threshold_value_2=request.threshold_value_2,
            sma_period=request.sma_period,
            screening_criteria=request.screening_criteria,
            frequency=request.frequency,
            notification_channels=request.notification_channels,
            telegram_chat_id=request.telegram_chat_id,
            expires_at=request.expires_at,
        )

        db.add(alert)
        db.commit()
        db.refresh(alert)

        logger.info(f"Created alert: {alert.name} (ID: {alert.id})")

        return {
            "success": True,
            "message": f"Alert '{alert.name}' created successfully",
            "alert": alert.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=dict)
async def list_alerts(
    is_active: Optional[bool] = None,
    alert_type: Optional[str] = None,
    symbol: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List user alerts with optional filters"""
    try:
        query = db.query(UserAlert)

        if is_active is not None:
            query = query.filter(UserAlert.is_active == is_active)
        if alert_type:
            query = query.filter(UserAlert.alert_type == alert_type)
        if symbol:
            query = query.filter(UserAlert.symbol == symbol.upper())

        total = query.count()
        alerts = query.order_by(UserAlert.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return {
            "alerts": [
                {
                    **a.to_dict(),
                    "alert_type_description": alert_service.get_alert_type_description(a.alert_type)
                }
                for a in alerts
            ],
            "total": total,
            "page": page,
            "page_size": page_size
        }

    except Exception as e:
        logger.error(f"Error listing alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{alert_id}", response_model=dict)
async def get_alert(alert_id: int, db: Session = Depends(get_db)):
    """Get a single alert by ID"""
    alert = db.query(UserAlert).filter(UserAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {
        **alert.to_dict(),
        "alert_type_description": alert_service.get_alert_type_description(alert.alert_type)
    }


@router.patch("/{alert_id}", response_model=dict)
async def update_alert(alert_id: int, request: UpdateAlertRequest, db: Session = Depends(get_db)):
    """Update an existing alert"""
    alert = db.query(UserAlert).filter(UserAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    try:
        if request.name is not None:
            alert.name = request.name
        if request.description is not None:
            alert.description = request.description
        if request.threshold_value is not None:
            alert.threshold_value = request.threshold_value
        if request.threshold_value_2 is not None:
            alert.threshold_value_2 = request.threshold_value_2
        if request.frequency is not None:
            alert.frequency = request.frequency
        if request.notification_channels is not None:
            alert.notification_channels = request.notification_channels
        if request.is_active is not None:
            alert.is_active = request.is_active
        if request.expires_at is not None:
            alert.expires_at = request.expires_at

        db.commit()
        db.refresh(alert)

        return {
            "success": True,
            "message": "Alert updated successfully",
            "alert": alert.to_dict()
        }

    except Exception as e:
        logger.error(f"Error updating alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{alert_id}", response_model=dict)
async def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """Delete an alert"""
    alert = db.query(UserAlert).filter(UserAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    try:
        # Also delete associated notifications
        db.query(AlertNotification).filter(AlertNotification.alert_id == alert_id).delete()
        db.delete(alert)
        db.commit()

        return {"success": True, "message": "Alert deleted successfully"}

    except Exception as e:
        logger.error(f"Error deleting alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/toggle", response_model=dict)
async def toggle_alert(alert_id: int, db: Session = Depends(get_db)):
    """Toggle an alert's active status"""
    alert = db.query(UserAlert).filter(UserAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_active = not alert.is_active
    db.commit()

    status = "activated" if alert.is_active else "deactivated"
    return {"success": True, "message": f"Alert {status}", "is_active": alert.is_active}


@router.post("/{alert_id}/check", response_model=dict)
async def check_alert_now(alert_id: int, db: Session = Depends(get_db)):
    """Manually check an alert's conditions"""
    alert = db.query(UserAlert).filter(UserAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    notification = alert_service.check_alert(alert, db)

    if notification:
        return {
            "triggered": True,
            "notification": notification.to_dict()
        }

    return {
        "triggered": False,
        "message": "Alert conditions not met",
        "last_checked_at": alert.last_checked_at.isoformat() if alert.last_checked_at else None
    }


@router.post("/check-all", response_model=dict)
async def check_all_alerts(db: Session = Depends(get_db)):
    """Check all active alerts"""
    notifications = alert_service.check_all_alerts(db)

    return {
        "checked": db.query(UserAlert).filter(UserAlert.is_active == True).count(),
        "triggered": len(notifications),
        "notifications": [n.to_dict() for n in notifications]
    }


# Notification endpoints
@router.get("/notifications/", response_model=dict)
async def list_notifications(
    is_read: Optional[bool] = None,
    alert_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List triggered notifications"""
    query = db.query(AlertNotification)

    if is_read is not None:
        query = query.filter(AlertNotification.is_read == is_read)
    if alert_id:
        query = query.filter(AlertNotification.alert_id == alert_id)

    total = query.count()
    notifications = query.order_by(AlertNotification.triggered_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "notifications": [n.to_dict() for n in notifications],
        "total": total,
        "page": page,
        "page_size": page_size,
        "unread_count": db.query(AlertNotification).filter(AlertNotification.is_read == False).count()
    }


@router.post("/notifications/{notification_id}/read", response_model=dict)
async def mark_notification_read(notification_id: int, db: Session = Depends(get_db)):
    """Mark a notification as read"""
    notification = db.query(AlertNotification).filter(AlertNotification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    db.commit()

    return {"success": True, "message": "Notification marked as read"}


@router.post("/notifications/mark-all-read", response_model=dict)
async def mark_all_notifications_read(db: Session = Depends(get_db)):
    """Mark all notifications as read"""
    count = db.query(AlertNotification).filter(AlertNotification.is_read == False).update({"is_read": True})
    db.commit()

    return {"success": True, "message": f"Marked {count} notifications as read"}


@router.delete("/notifications/clear", response_model=dict)
async def clear_notifications(
    is_read: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Clear notifications"""
    query = db.query(AlertNotification)
    if is_read is not None:
        query = query.filter(AlertNotification.is_read == is_read)

    count = query.delete()
    db.commit()

    return {"success": True, "deleted_count": count}
