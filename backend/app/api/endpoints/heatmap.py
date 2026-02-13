"""
Heat Map API endpoints
Real-time market data for heat map visualization
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
from loguru import logger

from app.services.data_fetcher.alpaca_service import alpaca_service

router = APIRouter()

# Sector configuration for market heat map
SECTORS = {
    'Technology': ['AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA', 'AMD', 'INTC', 'CRM', 'ADBE', 'ORCL'],
    'Healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'LLY', 'BMY', 'AMGN'],
    'Financials': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'C', 'AXP', 'SCHW', 'USB'],
    'Consumer': ['AMZN', 'TSLA', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'COST', 'LOW', 'TJX'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL'],
    'Industrial': ['CAT', 'HON', 'UPS', 'BA', 'GE', 'MMM', 'LMT', 'RTX', 'DE', 'UNP'],
    'Communication': ['GOOG', 'DIS', 'NFLX', 'CMCSA', 'VZ', 'T', 'TMUS', 'CHTR', 'EA', 'TTWO'],
    'Materials': ['LIN', 'APD', 'ECL', 'SHW', 'DD', 'NEM', 'FCX', 'NUE', 'DOW', 'PPG'],
}


@router.get("/market-overview")
async def get_market_overview() -> Dict[str, Any]:
    """
    Get real-time market data for heat map visualization.
    Returns stock data organized by sector with daily change percentages.
    """
    if not alpaca_service.is_available:
        logger.warning("Alpaca service not available, returning error")
        raise HTTPException(
            status_code=503,
            detail="Market data service unavailable. Please configure Alpaca API keys."
        )

    try:
        # Collect all symbols
        all_symbols = []
        for symbols in SECTORS.values():
            all_symbols.extend(symbols)

        # Remove duplicates (GOOGL/GOOG)
        all_symbols = list(set(all_symbols))

        logger.info(f"Fetching market data for {len(all_symbols)} symbols")

        # Get snapshots for all symbols at once
        snapshots = alpaca_service.get_multi_snapshots(all_symbols)

        if not snapshots:
            raise HTTPException(
                status_code=503,
                detail="Failed to fetch market data from Alpaca"
            )

        # Build response organized by sector
        result = {}
        for sector, symbols in SECTORS.items():
            sector_stocks = []
            for symbol in symbols:
                snapshot = snapshots.get(symbol.upper(), {})

                stock_data = {
                    'symbol': symbol,
                    'name': symbol,  # Could be enhanced with company name lookup
                    'change': snapshot.get('change_percent', 0),
                    'price': snapshot.get('current_price'),
                    'volume': snapshot.get('volume'),
                    'high': snapshot.get('high'),
                    'low': snapshot.get('low'),
                    'vwap': snapshot.get('vwap'),
                }

                sector_stocks.append(stock_data)

            result[sector] = sector_stocks

        logger.success(f"Market overview fetched: {len(snapshots)} stocks with data")

        return {
            'sectors': result,
            'total_stocks': len(all_symbols),
            'stocks_with_data': len(snapshots),
            'source': 'alpaca',
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching market overview: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching market data: {str(e)}"
        )


@router.get("/sector/{sector_name}")
async def get_sector_data(sector_name: str) -> Dict[str, Any]:
    """
    Get detailed data for a specific sector.
    """
    if sector_name not in SECTORS:
        raise HTTPException(
            status_code=404,
            detail=f"Sector '{sector_name}' not found. Available: {list(SECTORS.keys())}"
        )

    if not alpaca_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Market data service unavailable"
        )

    try:
        symbols = SECTORS[sector_name]
        snapshots = alpaca_service.get_multi_snapshots(symbols)

        stocks = []
        for symbol in symbols:
            snapshot = snapshots.get(symbol.upper(), {})
            stocks.append({
                'symbol': symbol,
                'name': symbol,
                'change': snapshot.get('change_percent', 0),
                'price': snapshot.get('current_price'),
                'volume': snapshot.get('volume'),
                'high': snapshot.get('high'),
                'low': snapshot.get('low'),
                'vwap': snapshot.get('vwap'),
            })

        return {
            'sector': sector_name,
            'stocks': stocks,
            'count': len(stocks),
        }

    except Exception as e:
        logger.error(f"Error fetching sector data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching sector data: {str(e)}"
        )


@router.get("/sectors")
async def get_available_sectors() -> Dict[str, Any]:
    """
    Get list of available sectors and their stock counts.
    """
    return {
        'sectors': [
            {'name': sector, 'count': len(symbols)}
            for sector, symbols in SECTORS.items()
        ],
        'total_stocks': sum(len(s) for s in SECTORS.values()),
    }


@router.get("/status")
async def get_alpaca_status() -> Dict[str, Any]:
    """
    Get Alpaca service status for diagnostics.
    """
    from app.config import get_settings
    settings = get_settings()

    status = {
        "alpaca_available": alpaca_service.is_available,
        "api_key_configured": bool(settings.ALPACA_API_KEY),
        "api_key_preview": settings.ALPACA_API_KEY[:8] + "..." if settings.ALPACA_API_KEY else "NOT SET",
        "secret_key_configured": bool(settings.ALPACA_SECRET_KEY),
        "data_feed": settings.ALPACA_DATA_FEED,
        "data_client_initialized": alpaca_service._data_client is not None,
    }

    # Test single snapshot if service is available
    if alpaca_service.is_available:
        try:
            test_snapshot = alpaca_service.get_snapshot("AAPL")
            if test_snapshot:
                status["test_snapshot"] = test_snapshot
                status["test_snapshot_status"] = "SUCCESS"
            else:
                status["test_snapshot"] = "EMPTY"
                status["test_snapshot_status"] = "EMPTY_RESPONSE"
        except Exception as e:
            import traceback
            status["test_snapshot_error"] = str(e)
            status["test_snapshot_traceback"] = traceback.format_exc()[:1000]
            status["test_snapshot_status"] = "ERROR"

    return status
