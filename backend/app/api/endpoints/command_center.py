"""
Command Center API Endpoints
Provides market data, news, prediction markets, and AI copilot functionality
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from loguru import logger

from app.services.command_center import (
    get_market_data_service,
    get_polymarket_service,
    get_news_feed_service,
    get_news_service,
    get_copilot_service,
)

router = APIRouter()


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ChatMessage(BaseModel):
    """Chat message model"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Request model for copilot chat"""
    message: str = Field(..., description="User message")
    context: Optional[Dict[str, Any]] = Field(None, description="Current context (selected stock, page, etc.)")
    conversation_history: Optional[List[ChatMessage]] = Field(None, description="Previous messages")


class ExplainMetricRequest(BaseModel):
    """Request model for metric explanation"""
    metric_name: str = Field(..., description="Name of the metric to explain")
    metric_value: Any = Field(..., description="Current value of the metric")
    context: Optional[str] = Field(None, description="Additional context")


class StockAnalysisRequest(BaseModel):
    """Request model for stock detail analysis"""
    stock_data: Dict[str, Any] = Field(..., description="Stock data from the detail page")
    market_context: Optional[Dict[str, Any]] = Field(None, description="Current market context")


# =============================================================================
# MARKET DATA ENDPOINTS
# =============================================================================

@router.get("/market/summary")
async def get_market_summary():
    """
    Get complete market summary for the Command Center.
    Includes indices, volatility, Fear & Greed, and sector performance.
    """
    try:
        service = get_market_data_service()
        summary = await service.get_market_summary()
        return summary
    except Exception as e:
        logger.error(f"Error getting market summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/indices")
async def get_market_indices():
    """
    Get current market indices (SPY, QQQ, DIA, IWM).
    """
    try:
        service = get_market_data_service()
        indices = await service.get_market_indices()
        return {"indices": indices, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting market indices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/volatility")
async def get_volatility_metrics():
    """
    Get VIX and volatility metrics.
    """
    try:
        service = get_market_data_service()
        volatility = await service.get_volatility_metrics()
        return {"volatility": volatility, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting volatility metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/fear-greed")
async def get_fear_greed():
    """
    Get CNN Fear & Greed Index.
    """
    try:
        service = get_market_data_service()
        fear_greed = await service.get_fear_greed_index()
        if fear_greed:
            return fear_greed
        else:
            raise HTTPException(status_code=503, detail="Fear & Greed data unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Fear & Greed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/sectors")
async def get_sector_performance():
    """
    Get sector ETF performance for rotation analysis.
    """
    try:
        service = get_market_data_service()
        sectors = await service.get_sector_performance()
        return {"sectors": sectors, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting sector performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# POLYMARKET ENDPOINTS
# =============================================================================

@router.get("/polymarket/dashboard")
async def get_polymarket_dashboard():
    """
    Get Polymarket data formatted for the dashboard widget.
    Includes key markets and significant changes.
    """
    try:
        service = get_polymarket_service()
        dashboard = await service.get_dashboard_summary()
        return dashboard
    except Exception as e:
        logger.error(f"Error getting Polymarket dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/polymarket/markets")
async def get_trading_markets(
    limit: int = Query(20, ge=1, le=50, description="Number of markets to return"),
):
    """
    Get all trading-relevant prediction markets.
    """
    try:
        service = get_polymarket_service()
        markets = await service.get_trading_markets(limit=limit)
        return {"markets": markets, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting Polymarket markets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/polymarket/changes")
async def get_significant_changes(
    threshold: float = Query(5.0, ge=1.0, le=20.0, description="Minimum change percentage"),
):
    """
    Get markets with significant odds changes for alerts.
    """
    try:
        service = get_polymarket_service()
        changes = await service.get_significant_changes(threshold=threshold)
        return {"changes": changes, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting Polymarket changes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/polymarket/key-markets")
async def get_key_markets():
    """
    Get curated key markets by category.
    """
    try:
        service = get_polymarket_service()
        key_markets = await service.get_key_markets()
        return key_markets
    except Exception as e:
        logger.error(f"Error getting key markets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# NEWS FEED ENDPOINTS
# =============================================================================

@router.get("/news/market")
async def get_market_news(
    limit: int = Query(20, ge=1, le=50, description="Number of news items"),
):
    """
    Get general market news aggregated from multiple sources.
    """
    try:
        service = get_news_feed_service()
        news = await service.get_market_news(limit=limit)
        return {"news": news, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting market news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/company/{symbol}")
async def get_company_news(
    symbol: str,
    limit: int = Query(10, ge=1, le=30, description="Number of news items"),
):
    """
    Get news for a specific company/symbol.
    """
    try:
        service = get_news_feed_service()
        news = await service.get_company_news(symbol=symbol.upper(), limit=limit)
        return {"symbol": symbol.upper(), "news": news, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting company news for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/economic-calendar")
async def get_economic_calendar(
    days_ahead: int = Query(7, ge=1, le=30, description="Days to look ahead"),
):
    """
    Get upcoming economic events.
    """
    try:
        service = get_news_feed_service()
        events = await service.get_economic_calendar(days_ahead=days_ahead)
        return {"events": events, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting economic calendar: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/earnings-calendar")
async def get_earnings_calendar(
    days_ahead: int = Query(14, ge=1, le=30, description="Days to look ahead"),
):
    """
    Get upcoming earnings announcements.
    """
    try:
        service = get_news_feed_service()
        earnings = await service.get_earnings_calendar(days_ahead=days_ahead)
        return {"earnings": earnings, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting earnings calendar: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/catalyst-feed")
async def get_catalyst_feed(
    limit: int = Query(20, ge=1, le=50, description="Number of items"),
):
    """
    Get combined catalyst feed for the Command Center.
    Combines news, economic events, and earnings into prioritized feed.
    """
    try:
        service = get_news_feed_service()
        feed = await service.get_catalyst_feed(limit=limit)
        return feed
    except Exception as e:
        logger.error(f"Error getting catalyst feed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# RSS NEWS FEED ENDPOINTS (Free - No API Key Required)
# =============================================================================

@router.get("/news/rss")
async def get_rss_news(
    limit: int = Query(20, ge=1, le=50, description="Number of news items"),
    category: Optional[str] = Query(None, description="Filter by category: markets, investing, stocks, general"),
):
    """
    Get aggregated financial news from RSS feeds (CNBC, Yahoo Finance, MarketWatch, etc.).
    No API key required.
    """
    try:
        service = get_news_service()
        news = await service.get_news(limit=limit, category=category)
        return {"news": news, "timestamp": datetime.now().isoformat(), "source": "rss_feeds"}
    except Exception as e:
        logger.error(f"Error getting RSS news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/rss/market")
async def get_rss_market_news(
    limit: int = Query(15, ge=1, le=50, description="Number of news items"),
):
    """
    Get market-focused news filtered by financial keywords.
    Sources: CNBC, Yahoo Finance, MarketWatch, Reuters, Investing.com
    """
    try:
        service = get_news_service()
        news = await service.get_market_news(limit=limit)
        return {"news": news, "timestamp": datetime.now().isoformat(), "source": "rss_feeds"}
    except Exception as e:
        logger.error(f"Error getting RSS market news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/news/rss/sources")
async def get_rss_sources():
    """
    Get list of available RSS news sources.
    """
    try:
        service = get_news_service()
        sources = service.get_available_sources()
        return {"sources": sources, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error getting RSS sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# AI COPILOT ENDPOINTS
# =============================================================================

@router.get("/copilot/morning-brief")
async def get_morning_brief():
    """
    Get AI-generated morning brief based on current market conditions.
    """
    try:
        copilot = get_copilot_service()
        market_service = get_market_data_service()
        polymarket_service = get_polymarket_service()
        news_service = get_news_feed_service()

        # Gather data for brief
        market_data = await market_service.get_market_summary()
        polymarket_data = await polymarket_service.get_dashboard_summary()
        news_data = await news_service.get_catalyst_feed(limit=10)

        # Generate brief
        brief = await copilot.generate_morning_brief(
            market_data=market_data,
            polymarket_data=polymarket_data,
            news_data=news_data,
        )

        return brief

    except Exception as e:
        logger.error(f"Error generating morning brief: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/copilot/explain")
async def explain_metric(request: ExplainMetricRequest):
    """
    Get AI explanation for a specific metric.
    Used for hover tooltips and learning features.
    """
    try:
        copilot = get_copilot_service()
        explanation = await copilot.explain_metric(
            metric_name=request.metric_name,
            metric_value=request.metric_value,
            context=request.context or "",
        )
        return explanation

    except Exception as e:
        logger.error(f"Error explaining metric: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/copilot/chat")
async def copilot_chat(request: ChatRequest):
    """
    Interactive chat with the AI copilot.
    Supports context-aware conversations about market data.
    """
    try:
        copilot = get_copilot_service()

        # Convert Pydantic models to dicts for conversation history
        history = None
        if request.conversation_history:
            history = [{"role": m.role, "content": m.content} for m in request.conversation_history]

        response = await copilot.chat(
            message=request.message,
            context=request.context,
            conversation_history=history,
        )

        return response

    except Exception as e:
        logger.error(f"Error in copilot chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/copilot/analyze-stock")
async def analyze_stock_detail(request: StockAnalysisRequest):
    """
    Generate comprehensive AI analysis for a stock detail page.
    """
    try:
        copilot = get_copilot_service()
        analysis = await copilot.analyze_stock_detail(
            stock_data=request.stock_data,
            market_context=request.market_context,
        )
        return analysis

    except Exception as e:
        logger.error(f"Error analyzing stock: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/copilot/status")
async def get_copilot_status():
    """
    Get AI copilot status and usage statistics.
    """
    try:
        copilot = get_copilot_service()

        return {
            "available": copilot.is_available(),
            "usage": copilot.get_usage_stats(),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting copilot status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# COMBINED DASHBOARD ENDPOINT
# =============================================================================

@router.get("/dashboard")
async def get_full_dashboard():
    """
    Get all Command Center data in a single request.
    Optimized for initial page load.
    """
    try:
        market_service = get_market_data_service()
        polymarket_service = get_polymarket_service()
        news_service = get_news_feed_service()
        rss_news_service = get_news_service()
        copilot = get_copilot_service()

        # Fetch all data concurrently
        import asyncio

        market_task = asyncio.create_task(market_service.get_market_summary())
        polymarket_task = asyncio.create_task(polymarket_service.get_dashboard_summary())
        catalyst_task = asyncio.create_task(news_service.get_catalyst_feed(limit=15))
        rss_news_task = asyncio.create_task(rss_news_service.get_market_news(limit=15))

        market_data = await market_task
        polymarket_data = await polymarket_task
        catalyst_data = await catalyst_task
        rss_news_data = await rss_news_task

        # Generate morning brief (if AI available)
        brief = None
        if copilot.is_available():
            try:
                brief_result = await copilot.generate_morning_brief(
                    market_data=market_data,
                    polymarket_data=polymarket_data,
                    news_data=catalyst_data,
                )
                if brief_result.get('success'):
                    brief = brief_result.get('brief')
            except Exception as e:
                logger.warning(f"Could not generate morning brief: {e}")

        return {
            "timestamp": datetime.now().isoformat(),
            "market": market_data,
            "polymarket": polymarket_data,
            "catalysts": catalyst_data,
            "rss_news": rss_news_data,
            "morning_brief": brief,
            "copilot_available": copilot.is_available(),
        }

    except Exception as e:
        logger.error(f"Error getting full dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))
