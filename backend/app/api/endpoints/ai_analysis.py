"""
AI Analysis API Endpoints - Claude-powered stock analysis
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from loguru import logger
from sqlalchemy.orm import Session

from app.services.ai.claude_service import get_claude_service
from app.services.ai.market_regime import get_regime_detector
from app.services.screening.engine import screening_engine
from app.services.data_fetcher.fmp_service import fmp_service
from app.database import get_db
from app.models.trading_signal import TradingSignal

router = APIRouter()


class StockInsightsRequest(BaseModel):
    """Request body for stock insights."""
    include_strategy: bool = True


class BatchInsightsRequest(BaseModel):
    """Request body for batch insights."""
    symbols: List[str]


class SignalBatchRequest(BaseModel):
    """Request body for batch signal analysis."""
    signal_ids: List[int]


class RegimeResponse(BaseModel):
    """Market regime response."""
    regime: str
    risk_mode: str
    confidence: int
    vix: float
    vix_sma: float
    vix_trend: str
    spy_rsi: float
    spy_vs_200sma: str
    put_call_ratio: float
    delta_range: List[float]
    dte_range: List[int]
    sectors_favor: List[str]
    sectors_avoid: List[str]
    summary: str
    timestamp: str
    analysis_type: str


@router.get("/status")
async def get_ai_status():
    """
    Check AI service status.

    Returns:
        Status of Claude AI service including usage stats
    """
    claude = get_claude_service()

    status = {
        "available": claude.is_available(),
        "model_primary": claude.settings.CLAUDE_MODEL_PRIMARY if claude.is_available() else None,
        "model_fast": claude.settings.CLAUDE_MODEL_FAST if claude.is_available() else None,
        "model_advanced": claude.settings.CLAUDE_MODEL_ADVANCED if claude.is_available() else None
    }

    # Include usage stats if service is available
    if claude.is_available():
        status["usage"] = claude.get_usage_stats()

    return status


@router.get("/usage")
async def get_ai_usage_stats():
    """
    Get AI API usage statistics.

    Returns:
        Daily cost, requests, tokens, and remaining budget
    """
    claude = get_claude_service()

    if not claude.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not available"
        )

    return claude.get_usage_stats()


@router.post("/cache/clear")
async def clear_ai_cache(cache_type: Optional[str] = Query(None, description="Specific cache type to clear")):
    """
    Clear AI response cache.

    Args:
        cache_type: Optional specific cache type (stock_analysis, market_regime, etc.)

    Returns:
        Confirmation message
    """
    claude = get_claude_service()

    if not claude.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not available"
        )

    claude.clear_cache(cache_type)

    return {
        "status": "success",
        "message": f"Cache cleared{f' for type: {cache_type}' if cache_type else ' (all)'}"
    }


@router.get("/regime", response_model=RegimeResponse)
async def get_market_regime(
    use_ai: bool = Query(False, description="Use AI for enhanced analysis (slower)")
):
    """
    Get current market regime analysis.

    Analyzes VIX, SPY RSI, and breadth indicators to determine:
    - Market regime (bullish/bearish/neutral)
    - Risk mode (risk_on/risk_off/mixed)
    - Recommended delta and DTE ranges
    - Sectors to favor/avoid

    Args:
        use_ai: If True, uses Claude AI for analysis (more nuanced but slower)

    Returns:
        RegimeResponse with market analysis
    """
    try:
        detector = get_regime_detector()
        result = await detector.get_regime(use_ai=use_ai)
        return result

    except Exception as e:
        logger.error(f"Error getting market regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/insights/{symbol}")
async def get_stock_insights(
    symbol: str,
    request: Optional[StockInsightsRequest] = None
):
    """
    Get AI-powered insights for a single stock.

    Runs the full screening analysis and then generates:
    - AI conviction score (1-10)
    - Bull/bear case analysis
    - Recommended options strategy
    - Key risks and catalysts

    Args:
        symbol: Stock ticker symbol
        request: Optional request body with options

    Returns:
        Dict with AI analysis and recommendations
    """
    claude = get_claude_service()
    if not claude.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not available. Check ANTHROPIC_API_KEY in .env"
        )

    symbol = symbol.upper()
    include_strategy = request.include_strategy if request else True

    try:
        # First, run the screening analysis to get full data
        logger.info(f"Running AI analysis for {symbol}")
        stock_result = screening_engine.screen_single_stock(symbol)

        if not stock_result:
            raise HTTPException(status_code=404, detail=f"Could not analyze {symbol}")

        # Get market regime for context
        regime = await get_regime_detector().get_regime()

        # Get AI insights (now returns AnalysisResult)
        insights_result = await claude.analyze_stock(stock_result, market_regime=regime)

        if not insights_result.success:
            raise HTTPException(status_code=500, detail=insights_result.error or "AI analysis failed")

        insights = insights_result.data

        response = {
            "symbol": symbol,
            "name": stock_result.get('name', symbol),
            "current_price": stock_result.get('current_price'),
            "sector": stock_result.get('sector'),
            "composite_score": stock_result.get('score'),
            "passed_screening": stock_result.get('passed_all', False),
            "ai_analysis": insights.get('analysis') or insights.get('summary'),
            "ai_conviction": insights.get('conviction'),
            "bull_case": insights.get('bull_case'),
            "bear_case": insights.get('bear_case'),
            "catalyst": insights.get('catalyst'),
            "cached": insights_result.cached,
            "model_used": insights.get('model')
        }

        # Optionally include strategy recommendation
        if include_strategy:
            strategy_result = await claude.get_strategy_recommendation(stock_result, regime)
            if strategy_result.success and strategy_result.data:
                strategy = strategy_result.data
                response["strategy"] = strategy.get('strategy') or strategy.get('recommendation')
                response["market_regime"] = regime.get('regime')

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AI insights for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-insights")
async def get_batch_insights(request: BatchInsightsRequest):
    """
    Get AI summary for multiple stocks.

    Runs screening on provided symbols and generates:
    - Executive summary of opportunities
    - Top picks with reasoning
    - Common themes
    - Overall quality assessment

    Args:
        request: BatchInsightsRequest with list of symbols

    Returns:
        Dict with batch analysis summary
    """
    claude = get_claude_service()
    if not claude.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not available. Check ANTHROPIC_API_KEY in .env"
        )

    if not request.symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")

    if len(request.symbols) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 symbols per batch")

    try:
        symbols = [s.upper() for s in request.symbols]
        logger.info(f"Running batch AI analysis for {len(symbols)} symbols")

        # Screen all stocks
        results = screening_engine.screen_multiple_stocks(symbols)

        if not results:
            raise HTTPException(status_code=404, detail="No valid results")

        # Filter to passed stocks
        passed = [r for r in results if r.get('passed_all', False)]

        # Get market regime
        regime = await get_regime_detector().get_regime()

        # Get batch analysis (now returns AnalysisResult)
        batch_result = await claude.analyze_batch(passed, regime)

        batch_data = batch_result.data if batch_result.success else {}

        return {
            "total_screened": len(symbols),
            "total_passed": len(passed),
            "market_regime": regime.get('regime'),
            "risk_mode": regime.get('risk_mode'),
            "batch_quality": batch_data.get('batch_quality'),
            "summary": batch_data.get('summary'),
            "top_picks": batch_data.get('top_picks'),
            "themes": batch_data.get('themes'),
            "concerns": batch_data.get('concerns'),
            "top_candidates": [
                {
                    "symbol": r.get('symbol'),
                    "score": r.get('score'),
                    "sector": r.get('sector')
                }
                for r in passed[:5]
            ],
            "cached": batch_result.cached
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain/{symbol}")
async def explain_stock_score(symbol: str):
    """
    Explain why a stock received its screening score.

    Provides plain-English explanation of:
    - What drove the score up
    - What held the score back
    - What would improve the score

    Args:
        symbol: Stock ticker symbol

    Returns:
        Dict with score explanation
    """
    claude = get_claude_service()
    if not claude.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not available"
        )

    symbol = symbol.upper()

    try:
        # Screen the stock
        stock_result = screening_engine.screen_single_stock(symbol)

        if not stock_result:
            raise HTTPException(status_code=404, detail=f"Could not analyze {symbol}")

        # Check if it failed early
        if stock_result.get('failed_at'):
            failure_result = await claude.explain_failure(
                symbol,
                stock_result['failed_at'],
                stock_result
            )
            explanation_data = failure_result.data if failure_result.success else {}
            return {
                "symbol": symbol,
                "passed": False,
                "failed_at": stock_result['failed_at'],
                "explanation": explanation_data.get('failure_reason') or explanation_data.get('explanation'),
                "worth_watching": explanation_data.get('worth_watching'),
                "what_would_pass": explanation_data.get('what_would_pass')
            }

        # Get score explanation (now returns AnalysisResult)
        explain_result = await claude.explain_score(stock_result)
        explanation_data = explain_result.data if explain_result.success else {}

        return {
            "symbol": symbol,
            "passed": stock_result.get('passed_all', False),
            "composite_score": stock_result.get('score'),
            "scores": {
                "fundamental": stock_result.get('fundamental_score'),
                "technical": stock_result.get('technical_score'),
                "options": stock_result.get('options_score'),
                "momentum": stock_result.get('momentum_score')
            },
            "score_drivers": explanation_data.get('score_drivers'),
            "score_detractors": explanation_data.get('score_detractors'),
            "improvement_needed": explanation_data.get('improvement_needed'),
            "bottom_line": explanation_data.get('bottom_line') or explanation_data.get('explanation')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error explaining score for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategy/{symbol}")
async def get_strategy_recommendation(symbol: str):
    """
    Get AI-recommended options strategy for a stock.

    Based on stock analysis and market regime, recommends:
    - Specific options strategy
    - Strike and expiration
    - Position sizing
    - Entry/exit criteria

    Args:
        symbol: Stock ticker symbol

    Returns:
        Dict with strategy recommendation
    """
    claude = get_claude_service()
    if not claude.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not available"
        )

    symbol = symbol.upper()

    try:
        # Screen the stock
        stock_result = screening_engine.screen_single_stock(symbol)

        if not stock_result:
            raise HTTPException(status_code=404, detail=f"Could not analyze {symbol}")

        if not stock_result.get('passed_all', False):
            return {
                "symbol": symbol,
                "recommendation": "This stock did not pass screening filters. Consider other opportunities.",
                "passed_screening": False
            }

        # Get market regime
        regime = await get_regime_detector().get_regime()

        # Get strategy recommendation (now returns AnalysisResult)
        strategy_result = await claude.get_strategy_recommendation(stock_result, regime)

        if not strategy_result.success:
            raise HTTPException(
                status_code=500,
                detail=strategy_result.error or "Strategy analysis failed"
            )

        strategy = strategy_result.data

        return {
            "symbol": symbol,
            "current_price": stock_result.get('current_price'),
            "composite_score": stock_result.get('score'),
            "ai_conviction": strategy.get('conviction'),
            "iv_rank": strategy.get('iv_rank'),
            "trend": strategy.get('trend'),
            "market_regime": regime.get('regime'),
            "strategy": strategy.get('strategy'),
            "strike": strategy.get('strike'),
            "delta": strategy.get('delta'),
            "expiration_dte": strategy.get('expiration_dte'),
            "profit_target_pct": strategy.get('profit_target_pct'),
            "stop_loss_pct": strategy.get('stop_loss_pct'),
            "reasoning": strategy.get('reasoning') or strategy.get('recommendation'),
            "confidence": strategy.get('confidence'),
            "cached": strategy_result.cached
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SIGNAL DEEP ANALYSIS ENDPOINTS (Trading Prompt Library)
# =============================================================================

@router.post("/signal-analysis/{signal_id}")
async def analyze_signal(signal_id: int, db: Session = Depends(get_db)):
    """
    🧠 AI Deep Analysis for a single trading signal.

    Uses a 2-step process:
    1. Classifies regime (Haiku — fast, ~$0.001)
    2. Runs full analysis with matched template (Sonnet — ~$0.02-0.04)

    Returns structured analysis including:
    - Conviction score (1-10)
    - Action verdict (enter_now / wait / skip)
    - Strategy match and fit score
    - 5-point quality checklist
    - Entry/risk/target assessment
    - Options play recommendation
    - Failure mode warning
    - Actionable 2-3 sentence summary

    Args:
        signal_id: ID of the TradingSignal to analyze

    Returns:
        Dict with full AI deep analysis
    """
    claude = get_claude_service()
    if not claude.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not available. Check ANTHROPIC_API_KEY in .env"
        )

    # Load signal from DB
    signal = db.query(TradingSignal).filter(TradingSignal.id == signal_id).first()
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")

    try:
        signal_dict = signal.to_dict()

        # Get market regime (cached 15min)
        regime = None
        try:
            regime = await get_regime_detector().get_regime()
        except Exception as e:
            logger.warning(f"Could not get market regime for signal analysis: {e}")

        # TODO: Fetch IV rank from TastyTrade and earnings proximity from catalyst service
        # For now, pass None — the prompts handle N/A gracefully
        iv_rank = None
        days_to_earnings = None

        # Run AI Deep Analysis
        result = await claude.analyze_signal(
            signal_data=signal_dict,
            market_regime=regime,
            iv_rank=iv_rank,
            days_to_earnings=days_to_earnings,
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=result.error or "Signal analysis failed"
            )

        analysis = result.data

        return {
            "signal_id": signal_id,
            "symbol": signal_dict.get("symbol"),
            "strategy": signal_dict.get("strategy"),
            "timeframe": signal_dict.get("timeframe"),
            "direction": signal_dict.get("direction"),
            # Core analysis output
            "conviction": analysis.get("conviction"),
            "action": analysis.get("action"),
            "strategy_match": analysis.get("strategy_match"),
            "strategy_fit_score": analysis.get("strategy_fit_score"),
            "summary": analysis.get("summary"),
            # Detailed sections
            "entry_assessment": analysis.get("entry_assessment"),
            "risk_assessment": analysis.get("risk_assessment"),
            "targets": analysis.get("targets"),
            "checklist": analysis.get("checklist"),
            "failure_mode": analysis.get("failure_mode"),
            "options_play": analysis.get("options_play"),
            "earnings_warning": analysis.get("earnings_warning"),
            # Meta
            "regime_classification": analysis.get("regime_classification"),
            "analysis_type": analysis.get("analysis_type"),
            "analyzed_at": analysis.get("analyzed_at"),
            "model": analysis.get("model"),
            "cached": result.cached,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in signal deep analysis for signal {signal_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signal-batch-analysis")
async def analyze_signal_batch(request: SignalBatchRequest, db: Session = Depends(get_db)):
    """
    🧠 AI Batch Analysis — rank multiple signals and find the best setup.

    Analyzes up to 5 signals and returns:
    - Ranked list with conviction scores
    - Best setup highlighted with reasoning
    - Signals to skip with explanation
    - Overall quality assessment

    Args:
        request: SignalBatchRequest with list of signal_ids (max 5)

    Returns:
        Dict with ranked batch analysis
    """
    claude = get_claude_service()
    if not claude.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI service not available. Check ANTHROPIC_API_KEY in .env"
        )

    if not request.signal_ids:
        raise HTTPException(status_code=400, detail="No signal IDs provided")

    if len(request.signal_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 signals per batch analysis")

    try:
        # Load signals from DB
        signals = db.query(TradingSignal).filter(
            TradingSignal.id.in_(request.signal_ids)
        ).all()

        if not signals:
            raise HTTPException(status_code=404, detail="No signals found for provided IDs")

        signal_dicts = [s.to_dict() for s in signals]

        # Get market regime
        regime = None
        try:
            regime = await get_regime_detector().get_regime()
        except Exception as e:
            logger.warning(f"Could not get market regime for batch analysis: {e}")

        # Run batch analysis
        result = await claude.analyze_signal_batch(
            signals=signal_dicts,
            market_regime=regime,
        )

        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=result.error or "Batch analysis failed"
            )

        batch_data = result.data

        return {
            "total_analyzed": len(signal_dicts),
            "batch_quality": batch_data.get("batch_quality"),
            "quality_assessment": batch_data.get("quality_assessment"),
            "ranked_signals": batch_data.get("ranked_signals", []),
            "best_setup": batch_data.get("best_setup"),
            "signals_to_skip": batch_data.get("signals_to_skip", []),
            "summary": batch_data.get("summary"),
            "analyzed_at": batch_data.get("analyzed_at"),
            "model": batch_data.get("model"),
            "cached": result.cached,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch signal analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
