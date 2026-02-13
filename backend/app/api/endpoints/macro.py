"""
Macro Signal API Endpoints
Provides MRI, divergence detection, and ticker macro bias functionality
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.command_center import (
    get_macro_signal_service,
    get_polymarket_service,
)

router = APIRouter()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class MRIResponse(BaseModel):
    """Response model for MRI data"""
    mri_score: Optional[float] = Field(None, description="MRI score from 0-100")
    regime: str = Field(..., description="Current regime: risk_on, transition, risk_off")
    regime_label: str = Field(..., description="Human-readable regime label")
    confidence_score: float = Field(..., description="Confidence score from 0-100")
    confidence_label: str = Field(..., description="Confidence label: low, medium, high")
    shock_flag: bool = Field(False, description="Whether a shock was detected")
    drivers: Optional[List[Dict]] = Field(None, description="Top 3 drivers")
    components: Optional[Dict] = Field(None, description="Component scores by category")
    change_1h: Optional[float] = Field(None, description="1-hour change")
    change_24h: Optional[float] = Field(None, description="24-hour change")
    data_stale: bool = Field(False, description="Whether data is stale")
    calculated_at: Optional[str] = Field(None, description="Calculation timestamp")


class CategoryAggregateResponse(BaseModel):
    """Response model for category aggregate"""
    category: str
    aggregate_probability: Optional[float]
    confidence_score: float
    confidence_label: str
    markets_used: int
    total_liquidity: float
    dispersion: Optional[Dict]
    key_market: Optional[Dict]


class DivergenceResponse(BaseModel):
    """Response model for divergence"""
    type: str = Field(..., description="bullish_divergence or bearish_divergence")
    prediction_category: str
    prediction_change: float
    proxy_symbol: str
    proxy_name: str
    proxy_change: float
    proxy_atr: float
    interpretation: str
    severity: str


class TickerBiasResponse(BaseModel):
    """Response model for ticker macro bias"""
    symbol: str
    sector: Optional[str]
    bias_score: Optional[float]
    bias_label: str
    bias_color: Optional[str]
    weights: Optional[Dict]
    category_contributions: Optional[List[Dict]]
    top_driver: Optional[Dict]
    calculated_at: Optional[str]


class HealthResponse(BaseModel):
    """Response model for macro health status"""
    status: str
    stale: bool
    stale_minutes: Optional[float]
    last_api_success: Optional[str]
    suppress_alerts: bool


# =============================================================================
# MRI ENDPOINTS
# =============================================================================

@router.get("/mri", response_model=MRIResponse)
async def get_mri(db: Session = Depends(get_db)):
    """
    Get current Macro Risk Index (MRI) with confidence, drivers, and shock detection.
    """
    try:
        service = get_macro_signal_service()
        mri = await service.calculate_mri(db=db)
        return MRIResponse(**mri)
    except Exception as e:
        logger.error(f"Error getting MRI: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mri/history")
async def get_mri_history(
    hours: int = Query(24, ge=1, le=168, description="Hours of history to retrieve"),
    db: Session = Depends(get_db)
):
    """
    Get historical MRI data.
    """
    try:
        from app.models.mri_snapshot import MRISnapshot
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        snapshots = db.query(MRISnapshot).filter(
            MRISnapshot.calculated_at >= cutoff
        ).order_by(MRISnapshot.calculated_at.desc()).all()

        return {
            "hours": hours,
            "snapshots": [s.to_dict() for s in snapshots],
            "count": len(snapshots),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting MRI history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mri/components")
async def get_mri_components():
    """
    Get detailed MRI component breakdown with category aggregates.
    """
    try:
        service = get_macro_signal_service()
        polymarket = get_polymarket_service()

        # Get all category aggregates
        aggregates = await polymarket.get_all_category_aggregates()

        # Get current MRI for context
        mri = await service.calculate_mri()

        return {
            "mri_score": mri.get('mri_score'),
            "regime": mri.get('regime'),
            "components": mri.get('components'),
            "category_aggregates": aggregates,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting MRI components: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# EVENT/MARKET ENDPOINTS
# =============================================================================

@router.get("/events")
async def get_all_events(
    limit: int = Query(50, ge=1, le=100, description="Number of markets to return"),
):
    """
    Get all prediction markets with quality scores.
    """
    try:
        polymarket = get_polymarket_service()
        markets = await polymarket.get_trading_markets(limit=limit)

        # Add quality scores
        for market in markets:
            market['quality_score'] = polymarket.calculate_market_quality_score(market)

        return {
            "markets": markets,
            "count": len(markets),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/category/{category}")
async def get_events_by_category(
    category: str,
):
    """
    Get prediction markets for a specific category.

    Categories: fed_policy, recession, elections, trade, crypto, markets
    """
    try:
        polymarket = get_polymarket_service()

        # Validate category
        valid_categories = ['fed_policy', 'recession', 'elections', 'trade', 'crypto', 'markets']
        if category not in valid_categories:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category. Must be one of: {valid_categories}"
            )

        # Get markets by category
        markets = await polymarket.get_markets_by_category(category)

        # Get category aggregate
        aggregate = await polymarket.get_category_aggregate(category)

        return {
            "category": category,
            "aggregate": aggregate,
            "markets": markets,
            "count": len(markets),
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting events for category {category}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/{market_id}")
async def get_event_detail(market_id: str):
    """
    Get detailed data for a specific market.
    """
    try:
        polymarket = get_polymarket_service()
        markets = await polymarket.get_trading_markets(limit=100)

        # Find the market
        market = next((m for m in markets if m.get('id') == market_id), None)
        if not market:
            raise HTTPException(status_code=404, detail="Market not found")

        # Add quality score
        market['quality_score'] = polymarket.calculate_market_quality_score(market)

        return {
            "market": market,
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting event detail for {market_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/{market_id}/history")
async def get_event_history(
    market_id: str,
    hours: int = Query(24, ge=1, le=168, description="Hours of history"),
    db: Session = Depends(get_db)
):
    """
    Get probability time-series history for a specific market.
    """
    try:
        from app.models.polymarket_snapshot import PolymarketMarketSnapshot
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(hours=hours)
        snapshots = db.query(PolymarketMarketSnapshot).filter(
            PolymarketMarketSnapshot.market_id == market_id,
            PolymarketMarketSnapshot.snapshot_at >= cutoff
        ).order_by(PolymarketMarketSnapshot.snapshot_at.asc()).all()

        return {
            "market_id": market_id,
            "hours": hours,
            "snapshots": [s.to_dict() for s in snapshots],
            "count": len(snapshots),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting event history for {market_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MOMENTUM & DIVERGENCE ENDPOINTS
# =============================================================================

@router.get("/momentum")
async def get_narrative_momentum(
    category: Optional[str] = Query(None, description="Filter by category"),
    threshold: float = Query(10.0, ge=1.0, le=30.0, description="Minimum change threshold"),
):
    """
    Get current narrative momentum shifts across categories.
    """
    try:
        service = get_macro_signal_service()

        if category:
            # Single category
            momentum = await service.detect_narrative_momentum(
                category=category,
                threshold_pct=threshold
            )
            return {
                "category": category,
                "momentum": momentum,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            # All categories
            categories = ['fed_policy', 'recession', 'elections', 'trade', 'crypto']
            all_momentum = {}

            for cat in categories:
                momentum = await service.detect_narrative_momentum(
                    category=cat,
                    threshold_pct=threshold
                )
                if momentum:
                    all_momentum[cat] = momentum

            return {
                "momentum": all_momentum,
                "categories_with_signals": list(all_momentum.keys()),
                "timestamp": datetime.now().isoformat(),
            }
    except Exception as e:
        logger.error(f"Error getting momentum: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/divergences")
async def get_divergences(db: Session = Depends(get_db)):
    """
    Get current divergences between prediction markets and price proxies.
    Only returns divergences that have persisted across multiple checks.
    """
    try:
        service = get_macro_signal_service()
        divergences = await service.detect_divergences(db=db)

        return {
            "divergences": divergences,
            "count": len(divergences),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting divergences: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TICKER BIAS ENDPOINTS
# =============================================================================

@router.get("/ticker/{symbol}/bias", response_model=TickerBiasResponse)
async def get_ticker_bias(
    symbol: str,
    db: Session = Depends(get_db)
):
    """
    Get macro bias for a specific ticker based on sector weights.
    """
    try:
        service = get_macro_signal_service()
        bias = await service.get_ticker_macro_bias(
            symbol=symbol.upper(),
            db=db
        )
        return TickerBiasResponse(**bias)
    except Exception as e:
        logger.error(f"Error getting ticker bias for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HEALTH & STATUS ENDPOINTS
# =============================================================================

@router.get("/health", response_model=HealthResponse)
async def get_macro_health():
    """
    Get macro signal service health status including data freshness.
    """
    try:
        service = get_macro_signal_service()
        staleness = service._check_staleness()

        return HealthResponse(
            status="healthy" if not staleness['stale'] else "degraded",
            stale=staleness['stale'],
            stale_minutes=staleness.get('stale_minutes'),
            last_api_success=staleness.get('last_api_success'),
            suppress_alerts=staleness['suppress_alerts'],
        )
    except Exception as e:
        logger.error(f"Error getting macro health: {e}")
        return HealthResponse(
            status="error",
            stale=True,
            stale_minutes=None,
            last_api_success=None,
            suppress_alerts=True,
        )
