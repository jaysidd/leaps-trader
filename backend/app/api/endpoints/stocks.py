"""
Stock data API endpoints
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from loguru import logger

from app.services.data_fetcher.fmp_service import fmp_service
from app.services.data_fetcher.alpaca_service import alpaca_service
from app.services.data_fetcher.tastytrade import get_tastytrade_service

router = APIRouter()


@router.get("/info/{symbol}")
async def get_stock_info(symbol: str):
    """
    Get stock information

    Args:
        symbol: Stock ticker symbol

    Returns:
        Stock info (name, sector, market cap, etc.)
    """
    try:
        info = fmp_service.get_stock_info(symbol)

        if not info:
            raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

        return info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stock info for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price/{symbol}")
async def get_current_price(symbol: str):
    """
    Get current stock price

    Args:
        symbol: Stock ticker symbol

    Returns:
        Current price
    """
    try:
        price = alpaca_service.get_current_price(symbol)

        if price is None:
            raise HTTPException(status_code=404, detail=f"Price not available for {symbol}")

        return {"symbol": symbol, "price": price}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting price for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{symbol}")
async def get_historical_prices(
    symbol: str,
    period: str = "1y",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get historical price data

    Args:
        symbol: Stock ticker symbol
        period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Historical OHLCV data
    """
    try:
        df = alpaca_service.get_historical_prices(symbol, start_date, end_date, period)

        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"No historical data for {symbol}")

        return {
            "symbol": symbol,
            "data": df.to_dict('records')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting historical data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fundamentals/{symbol}")
async def get_fundamentals(symbol: str):
    """
    Get fundamental data

    Args:
        symbol: Stock ticker symbol

    Returns:
        Fundamental metrics
    """
    try:
        fundamentals = fmp_service.get_fundamentals(symbol)

        if not fundamentals:
            raise HTTPException(status_code=404, detail=f"No fundamental data for {symbol}")

        return {
            "symbol": symbol,
            "fundamentals": fundamentals
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting fundamentals for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/options/{symbol}")
async def get_options_chain(symbol: str, expiration_date: Optional[str] = None):
    """
    Get options chain

    Args:
        symbol: Stock ticker symbol
        expiration_date: Specific expiration date (YYYY-MM-DD)

    Returns:
        Options chain with calls and puts
    """
    try:
        options = alpaca_service.get_options_chain(symbol, expiration_date)

        if not options:
            raise HTTPException(status_code=404, detail=f"No options data for {symbol}")

        return {
            "symbol": symbol,
            "calls": options['calls'].to_dict('records'),
            "puts": options['puts'].to_dict('records')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting options for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tastytrade/status")
async def get_tastytrade_status():
    """
    Check TastyTrade API status

    Returns:
        Status of TastyTrade integration
    """
    service = get_tastytrade_service()
    return {
        "available": service.is_available(),
        "message": "TastyTrade API is connected" if service.is_available()
                   else "TastyTrade API not configured or unavailable"
    }


@router.get("/tastytrade/metrics/{symbol}")
async def get_tastytrade_metrics(symbol: str):
    """
    Get enhanced market metrics from TastyTrade

    Includes IV rank, IV percentile, beta, and historical volatility.

    Args:
        symbol: Stock ticker symbol

    Returns:
        Enhanced options metrics from TastyTrade
    """
    service = get_tastytrade_service()

    if not service.is_available():
        raise HTTPException(
            status_code=503,
            detail="TastyTrade API not configured. Add TASTYTRADE_PROVIDER_SECRET and TASTYTRADE_REFRESH_TOKEN to .env"
        )

    try:
        data = service.get_enhanced_options_data(symbol)

        if not data:
            raise HTTPException(status_code=404, detail=f"No TastyTrade data for {symbol}")

        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting TastyTrade metrics for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tastytrade/metrics")
async def get_tastytrade_metrics_batch(symbols: str):
    """
    Get enhanced market metrics for multiple symbols

    Args:
        symbols: Comma-separated list of stock symbols

    Returns:
        Enhanced options metrics for all symbols
    """
    service = get_tastytrade_service()

    if not service.is_available():
        raise HTTPException(
            status_code=503,
            detail="TastyTrade API not configured"
        )

    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        metrics = service.get_market_metrics(symbol_list)

        results = {}
        for symbol, m in metrics.items():
            results[symbol] = {
                "iv_rank": float(m.tw_implied_volatility_index_rank) if m.tw_implied_volatility_index_rank else None,
                "iv_percentile": m.implied_volatility_percentile,
                "iv_30_day": float(m.implied_volatility_30_day) if m.implied_volatility_30_day else None,
                "hv_30_day": float(m.historical_volatility_30_day) if m.historical_volatility_30_day else None,
                "beta": float(m.beta) if m.beta else None,
                "market_cap": float(m.market_cap) if m.market_cap else None,
                "liquidity_rating": m.liquidity_rating
            }

        return {"symbols": symbol_list, "metrics": results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting batch TastyTrade metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tastytrade/leaps/{symbol}")
async def get_tastytrade_leaps(symbol: str, min_dte: int = 365, max_dte: int = 730):
    """
    Get LEAPS expiration dates from TastyTrade

    Args:
        symbol: Stock ticker symbol
        min_dte: Minimum days to expiration (default 365)
        max_dte: Maximum days to expiration (default 730)

    Returns:
        List of LEAPS expiration dates
    """
    service = get_tastytrade_service()

    if not service.is_available():
        raise HTTPException(
            status_code=503,
            detail="TastyTrade API not configured"
        )

    try:
        expirations = service.get_leaps_expirations(symbol, min_dte, max_dte)

        return {
            "symbol": symbol,
            "min_dte": min_dte,
            "max_dte": max_dte,
            "expirations": [d.isoformat() for d in expirations],
            "count": len(expirations)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting LEAPS expirations for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BatchQuotesRequest(BaseModel):
    symbols: List[str]


@router.post("/batch-quotes")
async def get_batch_quotes(request: BatchQuotesRequest):
    """
    Get live quotes for multiple symbols via Alpaca.

    Returns current price, change_percent, volume, etc. for each symbol.
    """
    if not request.symbols:
        return {"quotes": {}, "total": 0, "successful": 0}

    if not alpaca_service.is_available:
        raise HTTPException(status_code=503, detail="Alpaca API not configured")

    try:
        snapshots = alpaca_service.get_multi_snapshots(request.symbols)
        return {
            "quotes": snapshots,
            "total": len(request.symbols),
            "successful": len(snapshots),
        }
    except Exception as e:
        logger.error(f"Error fetching batch quotes: {e}")
        raise HTTPException(status_code=500, detail=str(e))
