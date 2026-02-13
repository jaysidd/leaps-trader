"""
Macro Intelligence API Endpoints

Provides catalyst data, Trade Readiness scores, and ticker overlays.
All endpoints under: /api/v1/command-center/macro-intelligence/*
"""

import time

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.command_center import get_catalyst_service
from app.models.stock import Stock

router = APIRouter()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class TradeReadinessResponse(BaseModel):
    """Response model for Trade Readiness data."""
    score: Optional[float] = Field(None, description="Trade Readiness score from 0-100")
    label: str = Field(..., description="Readiness label: green, yellow, red")
    label_display: str = Field(..., description="Human-readable label")
    is_partial: bool = Field(True, description="Whether score is partial (missing components)")
    partial_reason: Optional[str] = Field(None, description="Reason for partial score")


class LiquidityResponse(BaseModel):
    """Response model for Liquidity catalyst."""
    score: Optional[float] = Field(None, description="Liquidity score from 0-100")
    confidence_score: float = Field(..., description="Confidence score from 0-100")
    regime: str = Field(..., description="Regime: risk_on, transition, risk_off")
    regime_label: str = Field(..., description="Human-readable regime label")
    drivers: Optional[List[Dict]] = Field(None, description="Top 3 drivers")
    metrics: Optional[Dict] = Field(None, description="Raw liquidity metrics")
    data_stale: bool = Field(False, description="Whether data is stale")
    stale_reason: Optional[str] = Field(None, description="Reason for staleness")
    as_of: Optional[str] = Field(None, description="Data timestamp")
    completeness: Optional[float] = Field(None, description="Data completeness 0-1")


class CatalystSummaryResponse(BaseModel):
    """Response model for full catalyst summary."""
    trade_readiness: TradeReadinessResponse
    components: Dict[str, Any] = Field(..., description="Component scores")
    drivers: Optional[List[Dict]] = Field(None, description="Top drivers")
    confidence_by_component: Optional[Dict[str, float]] = Field(None, description="Confidence per component")
    overall_confidence: Optional[float] = Field(None, description="Overall confidence score")
    data_stale: bool = Field(False, description="Whether any data is stale")
    stale_components: Optional[List[str]] = Field(None, description="List of stale components")
    calculated_at: Optional[str] = Field(None, description="Calculation timestamp")


class CatalystHistoryItem(BaseModel):
    """Response model for catalyst history item."""
    timestamp: str
    liquidity_score: Optional[float]
    trade_readiness_score: Optional[float]
    readiness_label: Optional[str]
    data_stale: bool


class TickerCatalystResponse(BaseModel):
    """Response model for ticker catalyst overlay."""
    symbol: str
    earnings_risk: Optional[Dict] = Field(None, description="Earnings risk score and details")
    options_positioning: Optional[Dict] = Field(None, description="Options positioning score")
    macro_bias: Optional[Dict] = Field(None, description="Macro bias modifier")
    next_known_events: Optional[List[Dict]] = Field(None, description="Upcoming events")
    data_stale: bool = Field(False)
    calculated_at: Optional[str] = None


class MacroOverlayResponse(BaseModel):
    """
    Response model for ticker macro overlay.

    IMPORTANT: This overlay provides CONTEXT, not a gatekeeper.
    Trade compatibility is an INFO flag, NOT a gate.
    """
    symbol: str
    sector: Optional[str] = Field(None, description="Ticker's sector")

    # Macro Bias
    macro_bias: str = Field(..., description="Macro bias label: bearish, neutral, bullish")
    macro_bias_score: Optional[float] = Field(None, description="Macro bias score 0-100")

    # Confidence
    confidence_score: float = Field(..., description="Overall confidence score 0-100")
    data_stale: bool = Field(False, description="Whether any macro data is stale")

    # Trade Compatibility (INFO flag, NOT a gate)
    trade_compatibility: str = Field(..., description="Values: favorable, mixed, unfavorable")
    macro_headwind: bool = Field(False, description="Flag indicating macro headwind")
    compatibility_flags: Optional[Dict[str, bool]] = Field(None, description="Detailed compatibility flags")
    compatibility_reasons: Optional[List[str]] = Field(None, description="Human-readable reasons")

    # Drivers (human-readable, max 3)
    drivers: List[str] = Field(..., description="Top 3 human-readable drivers")

    # Earnings (optional, Phase 2)
    earnings: Optional[Dict] = Field(None, description="Earnings risk if within 10 days")

    # Detailed breakdown (for expanded view)
    details: Optional[Dict] = Field(None, description="Detailed score breakdown")

    # Navigation
    links: Optional[Dict[str, str]] = Field(None, description="Related page links")

    # Timestamp
    calculated_at: Optional[str] = Field(None, description="Calculation timestamp")


class BatchMacroOverlayRequest(BaseModel):
    """Request model for batch macro overlay."""
    symbols: List[str] = Field(..., description="List of ticker symbols", max_length=100)


class BatchMacroOverlayResponse(BaseModel):
    """Response model for batch macro overlay."""
    overlays: Dict[str, MacroOverlayResponse] = Field(..., description="Map of symbol -> overlay")
    count: int = Field(..., description="Number of overlays returned")


# =============================================================================
# SUMMARY ENDPOINTS
# =============================================================================

@router.get("/catalysts/summary", response_model=CatalystSummaryResponse)
async def get_catalyst_summary(
    db: Session = Depends(get_db)
):
    """
    Get full catalyst summary including Trade Readiness score.

    Returns:
        - Trade Readiness score and label
        - All component scores (liquidity, credit, vol, etc.)
        - Top drivers with contributions
        - Confidence scores per component
        - Data staleness information
    """
    try:
        service = get_catalyst_service()
        result = await service.get_catalyst_summary(db)

        return CatalystSummaryResponse(
            trade_readiness=TradeReadinessResponse(
                score=result["trade_readiness"]["score"],
                label=result["trade_readiness"]["label"],
                label_display=result["trade_readiness"]["label_display"],
                is_partial=result["trade_readiness"]["is_partial"],
                partial_reason=result["trade_readiness"].get("partial_reason"),
            ),
            components=result["components"],
            drivers=result["drivers"],
            confidence_by_component=result["confidence_by_component"],
            overall_confidence=result["overall_confidence"],
            data_stale=result["data_stale"],
            stale_components=result.get("stale_components"),
            calculated_at=result["calculated_at"],
        )
    except Exception as e:
        logger.error(f"Error getting catalyst summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# LIQUIDITY ENDPOINTS
# =============================================================================

@router.get("/catalysts/liquidity", response_model=LiquidityResponse)
async def get_liquidity_catalyst(
    db: Session = Depends(get_db)
):
    """
    Get liquidity regime score with full metrics and drivers.

    Returns:
        - Liquidity score (0-100, higher = contracting/risk-off)
        - Regime classification (risk_on, transition, risk_off)
        - Top 3 drivers with contributions
        - Raw metrics (Fed BS, RRP, TGA, FCI, Real Yield)
    """
    try:
        service = get_catalyst_service()
        result = await service.get_liquidity(db)

        return LiquidityResponse(
            score=result["score"],
            confidence_score=result["confidence_score"],
            regime=result["regime"],
            regime_label=result["regime_label"],
            drivers=result["drivers"],
            metrics=result["metrics"],
            data_stale=result["data_stale"],
            stale_reason=result.get("stale_reason"),
            as_of=result.get("as_of"),
            completeness=result.get("completeness"),
        )
    except Exception as e:
        logger.error(f"Error getting liquidity catalyst: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalysts/liquidity/history")
async def get_liquidity_history(
    hours: int = Query(168, ge=1, le=720, description="Hours of history to fetch"),
    db: Session = Depends(get_db)
):
    """
    Get historical liquidity scores for charting.

    Args:
        hours: Number of hours of history (default 168 = 7 days)

    Returns:
        List of historical liquidity data points.
    """
    try:
        service = get_catalyst_service()
        history = await service.get_history(db, hours)

        # Extract just liquidity data
        liquidity_history = [
            {
                "timestamp": item["timestamp"],
                "score": item["components"]["liquidity"],
                "data_stale": item["data_stale"],
            }
            for item in history
            if item["components"].get("liquidity") is not None
        ]

        return {
            "hours": hours,
            "count": len(liquidity_history),
            "history": liquidity_history,
        }
    except Exception as e:
        logger.error(f"Error getting liquidity history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HISTORY ENDPOINTS
# =============================================================================

@router.get("/catalysts/history")
async def get_catalyst_history(
    hours: int = Query(168, ge=1, le=720, description="Hours of history to fetch"),
    db: Session = Depends(get_db)
):
    """
    Get full catalyst history including Trade Readiness.

    Args:
        hours: Number of hours of history (default 168 = 7 days)

    Returns:
        List of historical catalyst snapshots.
    """
    try:
        service = get_catalyst_service()
        history = await service.get_history(db, hours)

        return {
            "hours": hours,
            "count": len(history),
            "history": history,
        }
    except Exception as e:
        logger.error(f"Error getting catalyst history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# TICKER ENDPOINTS
# =============================================================================

@router.post("/macro-overlay/batch", response_model=BatchMacroOverlayResponse)
async def get_batch_macro_overlay(
    request: BatchMacroOverlayRequest,
    db: Session = Depends(get_db)
):
    """
    Batch fetch macro overlays for multiple symbols in a single request.

    Performance optimization: fetches market-wide data (liquidity, MRI, trade readiness)
    ONCE, then applies per-symbol sector weights. Reduces N API calls to 1.

    Max 100 symbols per request.
    """
    t_start = time.monotonic()
    symbols = [s.upper() for s in request.symbols[:100]]
    batch_size = len(symbols)
    errors = []

    try:
        service = get_catalyst_service()

        # Fetch market-wide data ONCE (the expensive part, server-cached ~90s)
        try:
            readiness_result = await service.calculate_trade_readiness(db)
            liquidity_result = await service.get_liquidity(db)
        except Exception as e:
            logger.error(f"Batch overlay: error fetching market data: {e}")
            # Return degraded response for all symbols
            degraded = {}
            for sym in symbols:
                degraded[sym] = MacroOverlayResponse(
                    symbol=sym,
                    macro_bias="unknown",
                    macro_bias_score=None,
                    confidence_score=0,
                    data_stale=True,
                    trade_compatibility="mixed",
                    macro_headwind=False,
                    drivers=["Macro data temporarily unavailable"],
                    links={"macro_intelligence": "/macro-intelligence"},
                    calculated_at=datetime.utcnow().isoformat() + "Z",
                )
            elapsed_ms = (time.monotonic() - t_start) * 1000
            logger.warning(f"Batch overlay DEGRADED: {batch_size} symbols, {elapsed_ms:.0f}ms (market data unavailable)")
            return BatchMacroOverlayResponse(overlays=degraded, count=len(degraded))

        # Batch lookup sectors from Stock table
        sector_map = {}
        try:
            stocks = db.query(Stock.symbol, Stock.sector).filter(
                Stock.symbol.in_(symbols)
            ).all()
            sector_map = {s.symbol: s.sector for s in stocks if s.sector}
        except Exception as e:
            logger.debug(f"Batch overlay: could not lookup sectors: {e}")

        # Extract shared market data
        readiness_score = readiness_result.get("trade_readiness_score", 50)
        liquidity_score = liquidity_result.get("score", 50)
        mri_component = readiness_result.get("components", {}).get("mri", {})
        mri_score = mri_component.get("score", 50)
        data_stale = readiness_result.get("data_stale", False) or liquidity_result.get("data_stale", False)
        overall_confidence = readiness_result.get("overall_confidence", 0)
        raw_drivers = readiness_result.get("drivers", [])
        human_drivers = service._format_drivers_human_readable(raw_drivers, liquidity_result)

        # Build overlay for each symbol (cheap per-symbol computation)
        # Partial failure: if one symbol fails, skip it and continue
        overlays = {}
        for sym in symbols:
            try:
                effective_sector = sector_map.get(sym, "Unknown")

                macro_bias_result = service._compute_macro_bias_score(
                    sector=effective_sector,
                    liquidity_score=liquidity_score,
                    mri_score=mri_score,
                )

                compat_result = service.compute_trade_compatibility(
                    readiness_score=readiness_score,
                    earnings_risk_score=None,
                    earnings_days_out=None,
                    options_positioning_score=None,
                )

                overlays[sym] = MacroOverlayResponse(
                    symbol=sym,
                    sector=effective_sector,
                    macro_bias=macro_bias_result["label"],
                    macro_bias_score=macro_bias_result["score"],
                    confidence_score=overall_confidence,
                    data_stale=data_stale,
                    trade_compatibility=compat_result["compatibility"],
                    macro_headwind=compat_result["macro_headwind"],
                    compatibility_flags=compat_result["flags"],
                    compatibility_reasons=compat_result["reasons"],
                    drivers=human_drivers[:3],
                    earnings=None,
                    details={
                        "trade_readiness_score": readiness_score,
                        "readiness_label": readiness_result.get("readiness_label"),
                        "liquidity_score": liquidity_score,
                        "liquidity_regime": liquidity_result.get("regime"),
                        "mri_score": mri_score,
                        "mri_regime": mri_component.get("regime"),
                        "sector_weights": macro_bias_result.get("sector_weights"),
                    },
                    links={"macro_intelligence": "/macro-intelligence"},
                    calculated_at=datetime.utcnow().isoformat() + "Z",
                )
            except Exception as sym_err:
                errors.append(sym)
                logger.debug(f"Batch overlay: failed for {sym}: {sym_err}")

        elapsed_ms = (time.monotonic() - t_start) * 1000
        cache_info = getattr(service, '_cache', None)
        cache_size = cache_info.size if cache_info else 'N/A'
        logger.info(
            f"Batch overlay: {len(overlays)}/{batch_size} symbols, "
            f"{elapsed_ms:.0f}ms, cache_entries={cache_size}"
            f"{f', errors={errors}' if errors else ''}"
        )

        return BatchMacroOverlayResponse(overlays=overlays, count=len(overlays))

    except Exception as e:
        elapsed_ms = (time.monotonic() - t_start) * 1000
        logger.error(f"Batch overlay error: {e} ({elapsed_ms:.0f}ms)")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ticker/{symbol}/macro-overlay", response_model=MacroOverlayResponse)
async def get_ticker_macro_overlay(
    symbol: str,
    sector: Optional[str] = Query(None, description="Ticker's sector (auto-detected if not provided)"),
    db: Session = Depends(get_db)
):
    """
    Get macro overlay for a specific ticker.

    **IMPORTANT**: This overlay provides CONTEXT, not a gatekeeper.
    - Trade compatibility is an INFO flag, NOT a gate
    - Macro informs the trade, it never replaces the trader
    - If macro is unclear, show uncertainty — do not hide the signal

    Returns:
        - macro_bias: bearish/neutral/bullish (sector-weighted)
        - macro_bias_score: 0-100 (higher = more bullish)
        - trade_compatibility: favorable/mixed/unfavorable (INFO only)
        - macro_headwind: boolean flag
        - drivers: top 3 human-readable drivers
        - earnings: earnings callout if within 10 days
        - details: expanded breakdown for drill-down

    Response time target: <100ms (uses cached data)
    """
    symbol = symbol.upper()

    # Auto-detect sector from Stock table if not provided
    if not sector and db:
        try:
            stock = db.query(Stock).filter(Stock.symbol == symbol).first()
            if stock and stock.sector:
                sector = stock.sector
        except Exception as e:
            logger.debug(f"Could not auto-detect sector for {symbol}: {e}")

    try:
        service = get_catalyst_service()
        result = await service.get_ticker_macro_overlay(
            symbol=symbol,
            sector=sector,
            db=db,
        )

        return MacroOverlayResponse(
            symbol=result["symbol"],
            sector=result.get("sector"),
            macro_bias=result["macro_bias"],
            macro_bias_score=result.get("macro_bias_score"),
            confidence_score=result.get("confidence_score", 0),
            data_stale=result.get("data_stale", False),
            trade_compatibility=result["trade_compatibility"],
            macro_headwind=result.get("macro_headwind", False),
            compatibility_flags=result.get("compatibility_flags"),
            compatibility_reasons=result.get("compatibility_reasons"),
            drivers=result.get("drivers", []),
            earnings=result.get("earnings"),
            details=result.get("details"),
            links=result.get("links"),
            calculated_at=result.get("calculated_at"),
        )

    except Exception as e:
        logger.error(f"Error getting macro overlay for {symbol}: {e}")
        # Gracefully degrade - return partial data, don't block
        return MacroOverlayResponse(
            symbol=symbol,
            macro_bias="unknown",
            macro_bias_score=None,
            confidence_score=0,
            data_stale=True,
            trade_compatibility="mixed",
            macro_headwind=False,
            drivers=["Macro data temporarily unavailable"],
            links={"macro_intelligence": "/macro-intelligence"},
            calculated_at=datetime.utcnow().isoformat() + "Z",
        )


@router.get("/ticker/{symbol}/catalysts", response_model=TickerCatalystResponse)
async def get_ticker_catalysts(
    symbol: str,
    db: Session = Depends(get_db)
):
    """
    Get catalyst overlay for a specific ticker.

    Returns:
        - Earnings risk score and days until earnings
        - Options positioning score (Phase 3)
        - Macro bias modifier
        - Upcoming events

    Note: Full implementation in Phase 2 (Earnings) and Phase 3 (Options).
    """
    symbol = symbol.upper()

    try:
        service = get_catalyst_service()

        # For Phase 1, return placeholder with macro bias only
        # Full implementation comes in Phase 2 (Earnings) and Phase 3 (Options)

        return TickerCatalystResponse(
            symbol=symbol,
            earnings_risk={
                "score": None,
                "days_until": None,
                "available": False,
                "reason": "Earnings risk implementation pending (Phase 2)",
            },
            options_positioning={
                "score": None,
                "available": False,
                "reason": "Options positioning implementation pending (Phase 3)",
            },
            macro_bias={
                "score": None,
                "modifier": "N/A",
                "available": False,
                "reason": "Ticker macro bias pending integration",
            },
            next_known_events=None,
            data_stale=False,
            calculated_at=datetime.utcnow().isoformat() + "Z",
        )

    except Exception as e:
        logger.error(f"Error getting ticker catalysts for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PLACEHOLDER ENDPOINTS (Future Phases)
# =============================================================================

@router.get("/catalysts/credit")
async def get_credit_catalyst(db: Session = Depends(get_db)):
    """
    Get credit stress score.

    Returns HY OAS, IG OAS levels, 4-week change, and regime classification.
    Score: 0=calm, 100=stressed (risk-off polarity).
    """
    try:
        service = get_catalyst_service()
        result = await service.get_credit_stress(db)
        return result
    except Exception as e:
        logger.error(f"Error getting credit stress: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalysts/volatility")
async def get_volatility_catalyst(db: Session = Depends(get_db)):
    """
    Get volatility structure score.

    Returns VIX, term slope (VIX3M-VIX), VVIX, and regime classification.
    Score: 0=calm, 100=stressed (risk-off polarity).
    """
    try:
        service = get_catalyst_service()
        result = await service.get_vol_structure(db)
        return result
    except Exception as e:
        logger.error(f"Error getting volatility structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalysts/event-density")
async def get_event_density_catalyst(db: Session = Depends(get_db)):
    """
    Get event density score with upcoming events list.

    Returns weighted event points, high-impact count, and top 10 events.
    Score: 0=light week, 100=heavy week (risk-off polarity).
    """
    try:
        service = get_catalyst_service()
        result = await service.get_event_density(db)
        return result
    except Exception as e:
        logger.error(f"Error getting event density: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalysts/cross-asset")
async def get_cross_asset_catalyst():
    """
    Get cross-asset confirmation score (Tier 3 - not yet implemented).
    """
    return {
        "score": None,
        "available": False,
        "reason": "Cross-asset confirmation implementation pending (Tier 3)",
        "expected_assets": ["SPY", "TLT", "DXY", "GLD", "USO"],
    }


@router.get("/catalysts/options-positioning")
async def get_options_positioning_catalyst():
    """
    Get index-level options positioning score (Phase 3 - not yet implemented).
    """
    return {
        "score": None,
        "available": False,
        "reason": "Options positioning implementation pending (Phase 3)",
        "expected_metrics": ["put_call_ratio", "iv_rank", "gex", "oi_walls"],
    }


@router.get("/ticker/{symbol}/options-positioning")
async def get_ticker_options_positioning(symbol: str):
    """
    Get ticker-level options positioning (Phase 3 - not yet implemented).
    """
    return {
        "symbol": symbol.upper(),
        "score": None,
        "available": False,
        "reason": "Ticker options positioning implementation pending (Phase 3)",
    }


@router.get("/ticker/{symbol}/events")
async def get_ticker_events(symbol: str):
    """
    Get upcoming events for a ticker (Phase 2 - not yet implemented).
    """
    return {
        "symbol": symbol.upper(),
        "events": [],
        "available": False,
        "reason": "Ticker events implementation pending (Phase 2)",
    }


@router.get("/ticker/{symbol}/earnings-risk")
async def get_ticker_earnings_risk(symbol: str):
    """
    Get earnings risk score for a ticker (Phase 2 - not yet implemented).
    """
    return {
        "symbol": symbol.upper(),
        "score": None,
        "days_until": None,
        "available": False,
        "reason": "Earnings risk implementation pending (Phase 2)",
    }
