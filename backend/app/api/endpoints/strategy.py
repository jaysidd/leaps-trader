"""
Strategy Recommendation API endpoints

Phase 3: Strategy Selector
- Strategy recommendations based on market regime, IV rank, conviction
- Position sizing with Kelly Criterion
- Delta/DTE optimization
- Risk/reward analysis
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger
from enum import Enum

from app.services.strategy import (
    get_strategy_engine,
    get_position_sizer,
    get_delta_dte_optimizer,
    StrategyType,
    RiskLevel,
    SizingMethod
)
from app.services.ai.market_regime import get_regime_detector
from app.services.screening.engine import screening_engine


router = APIRouter()


# -------------------------------------------------------------------------
# Request/Response Models
# -------------------------------------------------------------------------

class RiskToleranceEnum(str, Enum):
    conservative = "conservative"
    moderate = "moderate"
    aggressive = "aggressive"


class StrategyRequest(BaseModel):
    symbol: str
    conviction_score: int = Field(5, ge=1, le=10, description="AI conviction score 1-10")
    risk_tolerance: RiskToleranceEnum = RiskToleranceEnum.moderate
    portfolio_value: Optional[float] = Field(None, description="Portfolio value for sizing")
    existing_positions: Optional[List[Dict[str, Any]]] = None


class PositionSizeRequest(BaseModel):
    portfolio_value: float = Field(..., gt=0, description="Total portfolio value in dollars")
    conviction_score: int = Field(5, ge=1, le=10, description="Conviction score 1-10")
    win_probability: float = Field(0.55, ge=0, le=1, description="Estimated win probability")
    profit_target_pct: float = Field(100, description="Target profit as % of premium")
    stop_loss_pct: float = Field(40, description="Stop loss as % of premium")
    option_premium: Optional[float] = Field(None, description="Option premium per contract")
    market_regime: str = "neutral"
    days_to_earnings: Optional[int] = None
    sector: Optional[str] = None
    sizing_method: str = "kelly"


class DeltaDTERequest(BaseModel):
    strategy_type: str = "long_call"
    market_regime: str = "neutral"
    risk_tolerance: RiskToleranceEnum = RiskToleranceEnum.moderate
    iv_rank: float = Field(50, ge=0, le=100, description="IV Rank 0-100")
    conviction: int = Field(5, ge=1, le=10, description="Conviction score")
    days_to_earnings: Optional[int] = None


class BatchStrategyRequest(BaseModel):
    symbols: List[str]
    conviction_scores: Optional[Dict[str, int]] = None
    risk_tolerance: RiskToleranceEnum = RiskToleranceEnum.moderate


# -------------------------------------------------------------------------
# Strategy Recommendation Endpoints
# -------------------------------------------------------------------------

@router.get("/recommend/{symbol}")
async def get_strategy_recommendation(
    symbol: str,
    conviction_score: int = Query(5, ge=1, le=10, description="AI conviction score 1-10"),
    risk_tolerance: str = Query("moderate", description="Risk tolerance level"),
    portfolio_value: Optional[float] = Query(None, description="Portfolio value for sizing")
):
    """
    Get strategy recommendation for a stock.

    Returns:
        - Primary strategy recommendation with delta/DTE targets
        - Alternative strategies
        - Position sizing suggestion
        - Entry/exit parameters
    """
    try:
        engine = get_strategy_engine()

        # Get stock data from screening engine
        stock_data = screening_engine.screen_single_stock(symbol.upper())
        if not stock_data:
            raise HTTPException(status_code=404, detail=f"Could not find data for {symbol}")

        # Map risk tolerance
        risk_level = RiskLevel.MODERATE
        if risk_tolerance.lower() == "conservative":
            risk_level = RiskLevel.CONSERVATIVE
        elif risk_tolerance.lower() == "aggressive":
            risk_level = RiskLevel.AGGRESSIVE

        # Get recommendation
        recommendation = await engine.recommend_strategy(
            stock_data=stock_data,
            conviction_score=conviction_score,
            risk_tolerance=risk_level,
            portfolio_context={'value': portfolio_value} if portfolio_value else None
        )

        # Format response
        return {
            'symbol': symbol.upper(),
            'recommendation': {
                'strategy': recommendation.strategy.strategy_type.value,
                'confidence': recommendation.strategy.confidence,
                'rationale': recommendation.strategy.rationale,
                'key_factors': recommendation.strategy.key_factors,
                'risks': recommendation.strategy.risks
            },
            'parameters': {
                'target_delta': recommendation.strategy.target_delta,
                'delta_range': recommendation.strategy.delta_range,
                'target_dte': recommendation.strategy.target_dte,
                'dte_range': recommendation.strategy.dte_range,
                'max_position_pct': recommendation.strategy.max_position_pct,
                'max_risk_pct': recommendation.strategy.max_risk_pct
            },
            'entry_exit': {
                'entry_type': recommendation.strategy.entry_type,
                'profit_target_pct': recommendation.strategy.profit_target_pct,
                'stop_loss_pct': recommendation.strategy.stop_loss_pct,
                'time_stop_dte': recommendation.strategy.time_stop_dte
            },
            'alternatives': [
                {
                    'strategy': alt.strategy_type.value,
                    'confidence': alt.confidence,
                    'rationale': alt.rationale,
                    'target_delta': alt.target_delta,
                    'target_dte': alt.target_dte
                }
                for alt in recommendation.alternatives
            ],
            'context': {
                'market_regime': recommendation.market_regime,
                'iv_rank': recommendation.iv_rank,
                'conviction_score': recommendation.conviction_score,
                'days_to_earnings': recommendation.days_to_earnings,
                'trend_direction': recommendation.trend_direction
            },
            'suggested_contract': recommendation.suggested_contract
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommend/batch")
async def get_batch_strategy_recommendations(request: BatchStrategyRequest):
    """
    Get strategy recommendations for multiple stocks.

    Returns:
        List of strategy recommendations for each stock
    """
    try:
        engine = get_strategy_engine()
        results = []

        for symbol in request.symbols[:20]:  # Limit to 20
            try:
                stock_data = screening_engine.screen_single_stock(symbol.upper())
                if not stock_data:
                    continue

                conviction = (
                    request.conviction_scores.get(symbol, 5)
                    if request.conviction_scores else 5
                )

                risk_level = RiskLevel(request.risk_tolerance.value)

                recommendation = await engine.recommend_strategy(
                    stock_data=stock_data,
                    conviction_score=conviction,
                    risk_tolerance=risk_level
                )

                results.append({
                    'symbol': symbol.upper(),
                    'strategy': recommendation.strategy.strategy_type.value,
                    'confidence': recommendation.strategy.confidence,
                    'target_delta': recommendation.strategy.target_delta,
                    'target_dte': recommendation.strategy.target_dte,
                    'rationale': recommendation.strategy.rationale[:100] + '...' if len(recommendation.strategy.rationale) > 100 else recommendation.strategy.rationale,
                    'iv_rank': recommendation.iv_rank,
                    'market_regime': recommendation.market_regime
                })

            except Exception as e:
                logger.error(f"Error getting strategy for {symbol}: {e}")

        return {
            'count': len(results),
            'results': results
        }

    except Exception as e:
        logger.error(f"Error in batch strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Position Sizing Endpoints
# -------------------------------------------------------------------------

@router.post("/position-size")
async def calculate_position_size(request: PositionSizeRequest):
    """
    Calculate optimal position size using Kelly Criterion.

    Returns:
        - Recommended position size (% and dollars)
        - Maximum contracts
        - Maximum risk
        - Size multipliers applied
        - Warnings/limits hit
    """
    try:
        sizer = get_position_sizer()

        method = SizingMethod.KELLY
        if request.sizing_method.lower() == "risk_based":
            method = SizingMethod.RISK_BASED
        elif request.sizing_method.lower() == "fixed_percent":
            method = SizingMethod.FIXED_PERCENT

        result = sizer.calculate_position_size(
            portfolio_value=request.portfolio_value,
            conviction_score=request.conviction_score,
            win_probability=request.win_probability,
            profit_target_pct=request.profit_target_pct,
            stop_loss_pct=request.stop_loss_pct,
            option_premium=request.option_premium or 0,
            market_regime=request.market_regime,
            days_to_earnings=request.days_to_earnings,
            sector=request.sector,
            method=method
        )

        return {
            'recommended_size': {
                'percent': result.recommended_size_pct,
                'dollars': result.recommended_size_dollars,
                'max_contracts': result.max_contracts
            },
            'risk': {
                'max_risk_dollars': result.max_risk_dollars,
                'risk_percent': round(result.max_risk_dollars / request.portfolio_value * 100, 2)
            },
            'multipliers': {
                'base_size_pct': result.base_size_pct,
                'conviction': result.conviction_multiplier,
                'regime': result.regime_multiplier,
                'catalyst': result.catalyst_multiplier,
                'correlation': result.correlation_multiplier
            },
            'limits_hit': {
                'max_position': result.hit_max_position,
                'max_sector': result.hit_max_sector,
                'max_concentration': result.hit_max_concentration
            },
            'rationale': result.rationale,
            'warnings': result.warnings
        }

    except Exception as e:
        logger.error(f"Error calculating position size: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/position-size/quick")
async def quick_position_size(
    portfolio_value: float = Query(..., gt=0, description="Portfolio value"),
    conviction: int = Query(5, ge=1, le=10, description="Conviction score"),
    regime: str = Query("neutral", description="Market regime"),
    days_to_earnings: Optional[int] = Query(None, description="Days to earnings")
):
    """
    Quick position size calculation with minimal inputs.
    """
    try:
        sizer = get_position_sizer()

        result = sizer.calculate_position_size(
            portfolio_value=portfolio_value,
            conviction_score=conviction,
            market_regime=regime,
            days_to_earnings=days_to_earnings
        )

        return {
            'size_pct': result.recommended_size_pct,
            'size_dollars': result.recommended_size_dollars,
            'max_risk': result.max_risk_dollars,
            'rationale': result.rationale
        }

    except Exception as e:
        logger.error(f"Error in quick position size: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Delta/DTE Optimization Endpoints
# -------------------------------------------------------------------------

@router.post("/optimize-delta-dte")
async def optimize_delta_dte(request: DeltaDTERequest):
    """
    Optimize delta and DTE selection based on market conditions.

    Returns:
        - Target delta and acceptable range
        - Target DTE and acceptable range
        - Reasoning for selections
    """
    try:
        optimizer = get_delta_dte_optimizer()

        # Map strategy type
        try:
            strategy_type = StrategyType(request.strategy_type.lower())
        except ValueError:
            strategy_type = StrategyType.LONG_CALL

        risk_level = RiskLevel(request.risk_tolerance.value)

        result = optimizer.optimize(
            strategy_type=strategy_type,
            market_regime=request.market_regime,
            risk_tolerance=risk_level,
            iv_rank=request.iv_rank,
            days_to_earnings=request.days_to_earnings,
            conviction=request.conviction
        )

        return {
            'delta': {
                'target': result['target_delta'],
                'min': result['delta_range'][0],
                'max': result['delta_range'][1]
            },
            'dte': {
                'target': result['target_dte'],
                'min': result['dte_range'][0],
                'max': result['dte_range'][1]
            },
            'reasoning': result['reasoning'],
            'inputs': {
                'strategy': request.strategy_type,
                'regime': request.market_regime,
                'risk_tolerance': request.risk_tolerance.value,
                'iv_rank': request.iv_rank
            }
        }

    except Exception as e:
        logger.error(f"Error optimizing delta/DTE: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimize-delta-dte/quick")
async def quick_delta_dte(
    strategy: str = Query("long_call", description="Strategy type"),
    regime: str = Query("neutral", description="Market regime"),
    iv_rank: float = Query(50, ge=0, le=100, description="IV Rank")
):
    """
    Quick delta/DTE optimization with minimal inputs.
    """
    try:
        optimizer = get_delta_dte_optimizer()

        try:
            strategy_type = StrategyType(strategy.lower())
        except ValueError:
            strategy_type = StrategyType.LONG_CALL

        result = optimizer.optimize(
            strategy_type=strategy_type,
            market_regime=regime,
            risk_tolerance=RiskLevel.MODERATE,
            iv_rank=iv_rank
        )

        return {
            'target_delta': result['target_delta'],
            'target_dte': result['target_dte'],
            'delta_range': result['delta_range'],
            'dte_range': result['dte_range']
        }

    except Exception as e:
        logger.error(f"Error in quick delta/DTE: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Market Regime Endpoint
# -------------------------------------------------------------------------

@router.get("/market-regime")
async def get_current_market_regime():
    """
    Get current market regime assessment.

    Returns:
        - Overall regime (bullish/bearish/neutral/volatile)
        - VIX level and percentile
        - SPY technical indicators
        - Market breadth
        - Risk mode recommendation
    """
    try:
        detector = get_regime_detector()
        regime = await detector.get_regime()

        return regime

    except Exception as e:
        logger.error(f"Error getting market regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Strategy Types Reference
# -------------------------------------------------------------------------

@router.get("/strategy-types")
async def list_strategy_types():
    """
    List all available strategy types with descriptions.
    """
    strategies = {
        'long_call': {
            'name': 'Long Call',
            'bias': 'Bullish',
            'risk': 'Limited to premium',
            'reward': 'Unlimited',
            'best_for': 'Strong bullish conviction with fair IV'
        },
        'long_put': {
            'name': 'Long Put',
            'bias': 'Bearish',
            'risk': 'Limited to premium',
            'reward': 'Limited (stock to zero)',
            'best_for': 'Bearish conviction or portfolio hedge'
        },
        'leaps_call': {
            'name': 'LEAPS Call',
            'bias': 'Bullish',
            'risk': 'Limited to premium',
            'reward': 'Unlimited',
            'best_for': 'High conviction with cheap IV, long-term outlook'
        },
        'leaps_put': {
            'name': 'LEAPS Put',
            'bias': 'Bearish',
            'risk': 'Limited to premium',
            'reward': 'Limited',
            'best_for': 'Long-term bearish view or hedge'
        },
        'bull_call_spread': {
            'name': 'Bull Call Spread',
            'bias': 'Bullish',
            'risk': 'Limited to spread width minus credit',
            'reward': 'Limited to spread width',
            'best_for': 'Bullish view with expensive IV'
        },
        'bear_put_spread': {
            'name': 'Bear Put Spread',
            'bias': 'Bearish',
            'risk': 'Limited to spread width minus credit',
            'reward': 'Limited to spread width',
            'best_for': 'Bearish view with expensive IV'
        },
        'iron_condor': {
            'name': 'Iron Condor',
            'bias': 'Neutral',
            'risk': 'Limited to spread width minus credit',
            'reward': 'Limited to credit received',
            'best_for': 'Range-bound with high IV'
        },
        'cash_secured_put': {
            'name': 'Cash Secured Put',
            'bias': 'Neutral to Bullish',
            'risk': 'Assignment at strike price',
            'reward': 'Limited to premium',
            'best_for': 'Generating income, willing to own stock'
        },
        'covered_call': {
            'name': 'Covered Call',
            'bias': 'Neutral to Bullish',
            'risk': 'Stock ownership risk',
            'reward': 'Limited to strike + premium',
            'best_for': 'Income on existing positions'
        },
        'calendar_spread': {
            'name': 'Calendar Spread',
            'bias': 'Neutral',
            'risk': 'Limited to debit paid',
            'reward': 'Limited',
            'best_for': 'Stable stock with high near-term IV'
        },
        'diagonal_spread': {
            'name': 'Diagonal Spread',
            'bias': 'Directional',
            'risk': 'Limited to debit paid',
            'reward': 'Limited',
            'best_for': 'Directional view with income'
        },
        'straddle': {
            'name': 'Long Straddle',
            'bias': 'Neutral (volatility)',
            'risk': 'Limited to premium',
            'reward': 'Unlimited',
            'best_for': 'Expected big move, direction unknown'
        }
    }

    return {'strategies': strategies}
