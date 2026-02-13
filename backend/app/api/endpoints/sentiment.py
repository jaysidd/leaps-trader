"""
Sentiment and Catalyst API endpoints

Phase 2: Smart Scoring
- Sentiment analysis (news, analyst, insider)
- Catalyst calendar (earnings, events)
- Enhanced screening with sentiment
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from loguru import logger

from app.services.analysis.sentiment import get_sentiment_analyzer
from app.services.analysis.catalyst import get_catalyst_service
from app.services.screening.engine import screening_engine


router = APIRouter()


# Request/Response models
class SentimentRequest(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    current_price: Optional[float] = None


class BatchSentimentRequest(BaseModel):
    symbols: List[str]


# -------------------------------------------------------------------------
# Sentiment Endpoints
# -------------------------------------------------------------------------

@router.get("/sentiment/{symbol}")
async def get_sentiment(
    symbol: str,
    company_name: Optional[str] = Query(None, description="Company name for news search")
):
    """
    Get comprehensive sentiment analysis for a stock.

    Returns:
        - Overall sentiment score (0-100)
        - Component scores (news, analyst, insider, catalyst)
        - Bullish/bearish signals
        - Recommendations
    """
    try:
        analyzer = get_sentiment_analyzer()
        sentiment_score = await analyzer.analyze(
            symbol.upper(),
            company_name
        )

        return analyzer.get_sentiment_summary(sentiment_score)

    except Exception as e:
        logger.error(f"Error getting sentiment for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sentiment/batch")
async def get_batch_sentiment(request: BatchSentimentRequest):
    """
    Get sentiment analysis for multiple stocks.

    Returns:
        List of sentiment summaries for each stock
    """
    try:
        analyzer = get_sentiment_analyzer()
        results = []

        for symbol in request.symbols[:20]:  # Limit to 20 stocks
            try:
                sentiment_score = await analyzer.analyze(symbol.upper())
                results.append(analyzer.get_sentiment_summary(sentiment_score))
            except Exception as e:
                logger.error(f"Error getting sentiment for {symbol}: {e}")
                results.append({
                    'symbol': symbol,
                    'error': str(e)
                })

        return {'results': results}

    except Exception as e:
        logger.error(f"Error in batch sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Catalyst Endpoints
# -------------------------------------------------------------------------

@router.get("/catalysts/{symbol}")
async def get_catalysts(symbol: str):
    """
    Get catalyst calendar for a stock.

    Returns:
        - Upcoming catalysts (earnings, dividends, events)
        - Days to each catalyst
        - Risk level assessment
        - Timing recommendations
    """
    try:
        catalyst_service = get_catalyst_service()
        calendar = await catalyst_service.get_catalyst_calendar(symbol.upper())

        return {
            'symbol': symbol.upper(),
            'next_earnings_date': (
                calendar.next_earnings_date.isoformat()
                if calendar.next_earnings_date else None
            ),
            'days_to_earnings': calendar.days_to_earnings,
            'next_dividend_date': (
                calendar.next_dividend_date.isoformat()
                if calendar.next_dividend_date else None
            ),
            'days_to_dividend': calendar.days_to_dividend,
            'catalyst_score': calendar.catalyst_score,
            'risk_level': calendar.risk_level,
            'recommendation': calendar.recommendation,
            'catalysts': [
                {
                    'type': c.catalyst_type.value,
                    'date': c.date.isoformat(),
                    'description': c.description,
                    'impact': c.impact.value,
                    'expected_move_pct': c.expected_move_pct
                }
                for c in calendar.catalysts
            ]
        }

    except Exception as e:
        logger.error(f"Error getting catalysts for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalysts/{symbol}/earnings-move")
async def get_historical_earnings_move(symbol: str):
    """
    Get historical average earnings move for a stock.

    Returns:
        Average absolute percentage move on earnings dates
    """
    try:
        catalyst_service = get_catalyst_service()
        avg_move = await catalyst_service.get_historical_earnings_move(symbol.upper())

        return {
            'symbol': symbol.upper(),
            'avg_earnings_move_pct': avg_move,
            'description': (
                f"Stock typically moves {avg_move:.1f}% on earnings"
                if avg_move else "Insufficient data"
            )
        }

    except Exception as e:
        logger.error(f"Error getting earnings move for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro-calendar")
async def get_macro_calendar():
    """
    Get upcoming macro economic events.

    Returns:
        List of macro events (Fed, CPI, jobs, etc.)
    """
    try:
        catalyst_service = get_catalyst_service()
        events = await catalyst_service.get_macro_calendar()
        return {'events': events}

    except Exception as e:
        logger.error(f"Error getting macro calendar: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Enhanced Screening Endpoints
# -------------------------------------------------------------------------

@router.get("/screen-enhanced/{symbol}")
async def screen_with_sentiment(
    symbol: str,
    include_sentiment: bool = Query(True, description="Include sentiment analysis")
):
    """
    Screen a stock with full sentiment and catalyst analysis.

    This is the Phase 2 enhanced screening that includes:
    - All original screening stages
    - Sentiment scoring (news, analyst, insider)
    - Catalyst timing analysis
    """
    try:
        if include_sentiment:
            result = await screening_engine.screen_with_sentiment(symbol.upper())
        else:
            result = screening_engine.screen_single_stock(symbol.upper())

        if not result:
            raise HTTPException(status_code=404, detail=f"Could not screen {symbol}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error screening {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/screen-enhanced/batch")
async def screen_batch_with_sentiment(
    symbols: List[str] = Query(..., description="List of stock symbols"),
    include_sentiment: bool = Query(True, description="Include sentiment analysis"),
    top_n: int = Query(15, description="Number of top results to return")
):
    """
    Screen multiple stocks with sentiment analysis.

    Returns top N candidates sorted by enhanced composite score.
    """
    try:
        if include_sentiment:
            results = await screening_engine.screen_multiple_with_sentiment(
                [s.upper() for s in symbols[:50]]  # Limit to 50 symbols
            )
        else:
            results = screening_engine.screen_multiple_stocks(
                [s.upper() for s in symbols[:50]]
            )

        # Filter to passed stocks and return top N
        passed = [r for r in results if r.get('passed_all', False)]

        return {
            'total_screened': len(symbols),
            'total_passed': len(passed),
            'results': passed[:top_n]
        }

    except Exception as e:
        logger.error(f"Error in batch screening: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# News Endpoints
# -------------------------------------------------------------------------

@router.get("/news/{symbol}")
async def get_stock_news(
    symbol: str,
    limit: int = Query(10, description="Number of news items to return")
):
    """
    Get recent news for a stock.

    Returns:
        List of news headlines with sentiment scores
    """
    try:
        from app.services.data_fetcher.sentiment import get_sentiment_fetcher

        fetcher = get_sentiment_fetcher()
        news_items = await fetcher.fetch_company_news(symbol.upper())

        # Score each headline
        scored_news = []
        for item in news_items[:limit]:
            sentiment = fetcher.score_headline_sentiment(item.title)
            scored_news.append({
                'title': item.title,
                'source': item.source,
                'published': item.published.isoformat() if item.published else None,
                'url': item.url,
                'sentiment_score': sentiment,
                'sentiment_label': (
                    'bullish' if sentiment > 0.2 else
                    'bearish' if sentiment < -0.2 else
                    'neutral'
                )
            })

        return {
            'symbol': symbol.upper(),
            'news_count': len(scored_news),
            'news': scored_news
        }

    except Exception as e:
        logger.error(f"Error getting news for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Insider Trading Endpoints
# -------------------------------------------------------------------------

@router.get("/insiders/{symbol}")
async def get_insider_trades(symbol: str):
    """
    Get recent insider trading activity for a stock.

    Returns:
        List of insider transactions with buy/sell analysis
    """
    try:
        from app.services.data_fetcher.sentiment import get_sentiment_fetcher

        fetcher = get_sentiment_fetcher()
        trades = await fetcher.fetch_insider_trades(symbol.upper())

        # Summarize
        buys = [t for t in trades if t.trade_type == 'buy']
        sells = [t for t in trades if t.trade_type == 'sell']

        total_buy_value = sum(t.value for t in buys)
        total_sell_value = sum(t.value for t in sells)

        return {
            'symbol': symbol.upper(),
            'summary': {
                'total_buys': len(buys),
                'total_sells': len(sells),
                'buy_value': total_buy_value,
                'sell_value': total_sell_value,
                'net_activity': 'buying' if total_buy_value > total_sell_value else 'selling',
                'signal': (
                    'bullish' if len(buys) > len(sells) * 2 else
                    'bearish' if len(sells) > len(buys) * 2 else
                    'neutral'
                )
            },
            'trades': [
                {
                    'insider_name': t.insider_name,
                    'title': t.title,
                    'trade_type': t.trade_type,
                    'shares': t.shares,
                    'price': t.price,
                    'value': t.value,
                    'date': t.date.isoformat() if hasattr(t.date, 'isoformat') else str(t.date)
                }
                for t in trades
            ]
        }

    except Exception as e:
        logger.error(f"Error getting insider trades for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
