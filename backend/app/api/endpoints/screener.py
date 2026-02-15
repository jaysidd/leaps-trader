"""
Screening API endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional, Any, Dict, AsyncGenerator
from pydantic import BaseModel
from loguru import logger
import numpy as np
import json
import asyncio
import time

from app.services.screening.engine import screening_engine
from app.services.data_fetcher.finviz import finviz_service
from app.services.analysis.options import OptionsAnalysis
from app.data.stock_universe import get_universe_by_criteria, get_dynamic_universe, FULL_UNIVERSE
from app.data.presets_catalog import LEAPS_PRESETS, _PRESET_DISPLAY_NAMES
from app.schemas.screening import ScreenResponse, ScreeningResultV1

router = APIRouter()


def convert_numpy_types(obj: Any) -> Any:
    """
    Recursively convert numpy types to native Python types for JSON serialization
    """
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif hasattr(obj, 'item'):  # Catch any other numpy scalar types
        return obj.item()
    # Handle any remaining numpy types by checking module (catches deprecated numpy.bool, etc.)
    elif type(obj).__module__ == 'numpy':
        type_name = type(obj).__name__.lower()
        if 'bool' in type_name:
            return bool(obj)
        elif 'int' in type_name:
            return int(obj)
        elif 'float' in type_name:
            return float(obj)
        else:
            return str(obj)  # Fallback to string representation
    else:
        return obj


class ScreeningCriteria(BaseModel):
    """Custom screening criteria"""
    # --- Original fields (backward-compatible) ---
    market_cap_min: Optional[int] = 500_000_000
    market_cap_max: Optional[int] = None  # No upper limit by default — presets control this
    price_min: Optional[float] = 5.0  # Min stock price
    price_max: Optional[float] = 500.0  # Max stock price
    revenue_growth_min: Optional[float] = 20.0  # Percentage
    earnings_growth_min: Optional[float] = 15.0  # Percentage
    debt_to_equity_max: Optional[float] = 150.0
    current_ratio_min: Optional[float] = 1.2
    rsi_min: Optional[float] = 40.0
    rsi_max: Optional[float] = 70.0
    iv_max: Optional[float] = 100.0  # Max implied volatility
    dte_min: Optional[int] = 365  # Days to expiration min
    dte_max: Optional[int] = 730  # Days to expiration max

    # --- New valuation & style filters (Phase 1.1) ---
    pe_min: Optional[float] = None          # Min P/E (profitability guard, e.g. >0)
    pe_max: Optional[float] = None          # Max P/E (value filter)
    peg_max: Optional[float] = None         # Max PEG ratio (GARP filter)
    pb_max: Optional[float] = None          # Max price-to-book
    ps_max: Optional[float] = None          # Max price-to-sales
    dividend_yield_min: Optional[float] = None  # Min yield as decimal (0.025 = 2.5%)
    dividend_yield_max: Optional[float] = None  # Max yield (cap high-risk yields)
    roe_min: Optional[float] = None         # Min return on equity (decimal)
    profit_margin_min: Optional[float] = None   # Min profit margin (decimal)
    beta_min: Optional[float] = None        # Min beta
    beta_max: Optional[float] = None        # Max beta (low-vol filter)
    forward_pe_max: Optional[float] = None  # Max forward P/E
    skip_sector_filter: Optional[bool] = None   # Bypass growth-sector gate


class ScreenRequest(BaseModel):
    """Request model for screening"""
    symbols: List[str]
    top_n: Optional[int] = 15
    criteria: Optional[ScreeningCriteria] = None


@router.post("/screen", response_model=ScreenResponse)
async def screen_stocks(request: ScreenRequest):
    """
    Screen multiple stocks for LEAPS opportunities

    Args:
        request: ScreenRequest with list of symbols and optional custom criteria

    Returns:
        ScreenResponse with screening results
    """
    try:
        logger.info(f"Screening {len(request.symbols)} stocks...")

        # Convert criteria to dict if provided
        custom_criteria = request.criteria.dict() if request.criteria else None

        # Run screening with custom criteria (blocking I/O - run off event loop)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, screening_engine.screen_multiple_stocks, request.symbols, custom_criteria
        )

        # Convert numpy types to native Python types
        results = convert_numpy_types(results)

        # Count how many passed all filters
        passed_count = sum(1 for r in results if r.get('passed_all', False))

        logger.info(f"Screening complete: {passed_count}/{len(results)} passed all filters")

        return ScreenResponse(
            results=results[:request.top_n],
            total_screened=len(results),
            total_passed=passed_count
        )

    except Exception as e:
        logger.error(f"Error in screening endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screen/single/{symbol}", response_model=ScreeningResultV1)
async def screen_single_stock(symbol: str):
    """
    Screen a single stock

    Args:
        symbol: Stock ticker symbol

    Returns:
        Screening result for the stock
    """
    try:
        logger.info(f"Screening {symbol}...")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, screening_engine.screen_single_stock, symbol
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"Unable to screen {symbol}")

        # Convert numpy types to native Python types
        result = convert_numpy_types(result)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error screening {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BatchScoresRequest(BaseModel):
    """Request model for batch scoring"""
    symbols: List[str]


@router.post("/batch-scores")
async def batch_scores(request: BatchScoresRequest):
    """
    Calculate composite scores for multiple stocks without filter gates.

    Unlike the screening endpoints, this always computes all 4 sub-scores
    (fundamental, technical, options, momentum) regardless of whether
    the stock would pass screening filters.

    Args:
        request: BatchScoresRequest with list of symbols (max 50)

    Returns:
        Dict of symbol -> scores
    """
    try:
        symbols = request.symbols[:50]  # Cap at 50
        if not symbols:
            return {"scores": {}, "total": 0, "scored": 0}

        logger.info(f"Batch scoring {len(symbols)} stocks...")

        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None, screening_engine.calculate_batch_scores, symbols
        )

        # Convert numpy types
        scores = convert_numpy_types(scores)

        return {
            "scores": scores,
            "total": len(symbols),
            "scored": len(scores)
        }

    except Exception as e:
        logger.error(f"Error in batch scoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screen/top")
async def get_top_candidates(
    symbols: List[str] = Query(..., description="List of symbols to screen"),
    top_n: int = Query(15, description="Number of top candidates to return")
):
    """
    Get top N LEAPS candidates

    Args:
        symbols: List of stock ticker symbols
        top_n: Number of top candidates to return

    Returns:
        List of top candidates
    """
    try:
        logger.info(f"Getting top {top_n} candidates from {len(symbols)} stocks...")

        loop = asyncio.get_event_loop()
        top_candidates = await loop.run_in_executor(
            None, screening_engine.get_top_candidates, symbols, top_n
        )

        # Convert numpy types to native Python types
        top_candidates = convert_numpy_types(top_candidates)

        return {
            "candidates": top_candidates,
            "count": len(top_candidates)
        }

    except Exception as e:
        logger.error(f"Error getting top candidates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class FinvizScreenRequest(BaseModel):
    """Request model for Finviz pre-screening"""
    finviz_filters: Optional[Dict[str, str]] = None  # Finviz filter codes
    market_cap_min: Optional[int] = 500_000_000
    market_cap_max: Optional[int] = None  # No upper limit by default — presets control this
    revenue_growth_min: Optional[float] = 20.0
    eps_growth_min: Optional[float] = 15.0
    sector: Optional[str] = None
    top_n: Optional[int] = 15
    criteria: Optional[ScreeningCriteria] = None


@router.post("/screen/finviz", response_model=ScreenResponse)
async def screen_with_finviz(request: FinvizScreenRequest):
    """
    Use Finviz Elite API to pre-screen stocks, then run detailed LEAPS screening

    This endpoint:
    1. Uses Finviz filters to get a universe of candidate stocks
    2. Runs detailed LEAPS screening on those candidates
    3. Returns top results

    Requires: Finviz Elite subscription and API token configured

    Args:
        request: FinvizScreenRequest with Finviz filters and screening criteria

    Returns:
        ScreenResponse with screening results
    """
    try:
        if not finviz_service or not finviz_service.api_token:
            raise HTTPException(
                status_code=503,
                detail="Finviz Elite API not configured. Please set FINVIZ_API_TOKEN environment variable."
            )

        logger.info("Running Finviz pre-screening...")
        loop = asyncio.get_event_loop()

        # Use Finviz to get stock universe (blocking I/O - run off event loop)
        if request.finviz_filters:
            # Use custom Finviz filter codes
            finviz_results = await loop.run_in_executor(
                None, lambda: finviz_service.screen_stocks(
                    custom_filters=request.finviz_filters
                )
            )
        else:
            # Use mapped criteria
            finviz_results = await loop.run_in_executor(
                None, lambda: finviz_service.screen_stocks(
                    market_cap_min=request.market_cap_min,
                    market_cap_max=request.market_cap_max,
                    revenue_growth_min=request.revenue_growth_min,
                    eps_growth_min=request.eps_growth_min,
                    sector=request.sector
                )
            )

        if not finviz_results:
            logger.warning("Finviz returned no results")
            return ScreenResponse(
                results=[],
                total_screened=0,
                total_passed=0
            )

        # Extract symbols
        symbols = [stock['symbol'] for stock in finviz_results if stock.get('symbol')]
        logger.info(f"Finviz pre-screening returned {len(symbols)} stocks")

        # Convert criteria to dict if provided
        custom_criteria = request.criteria.dict() if request.criteria else None

        # Run detailed LEAPS screening on Finviz results (blocking I/O)
        logger.info(f"Running detailed LEAPS screening on {len(symbols)} stocks...")
        results = await loop.run_in_executor(
            None, screening_engine.screen_multiple_stocks, symbols, custom_criteria
        )

        # Convert numpy types to native Python types
        results = convert_numpy_types(results)

        # Count how many passed all filters
        passed_count = sum(1 for r in results if r.get('passed_all', False))

        logger.info(f"Screening complete: {passed_count}/{len(results)} passed all filters")

        return ScreenResponse(
            results=results[:request.top_n],
            total_screened=len(results),
            total_passed=passed_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in Finviz screening endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan/market", response_model=ScreenResponse)
async def scan_market(criteria: Optional[ScreeningCriteria] = None):
    """
    Automated Market Scanner - Scans hundreds of stocks automatically

    This endpoint performs automated market-wide screening without requiring
    manual symbol input. Perfect for discovering new 5x LEAPS opportunities.

    How it works:
    1. Selects appropriate stock universe based on your criteria (400+ stocks)
    2. Runs 4-stage LEAPS screening on entire universe
    3. Returns top candidates sorted by composite score

    Args:
        criteria: Optional screening criteria (uses moderate defaults if not provided)

    Returns:
        ScreenResponse with top LEAPS candidates
    """
    try:
        # Convert criteria to dict
        custom_criteria = criteria.dict() if criteria else None

        # Debug: Log received criteria
        logger.info(f"Market scan criteria received: {custom_criteria}")
        if custom_criteria:
            logger.info(f"Price range: ${custom_criteria.get('price_min')} - ${custom_criteria.get('price_max')}")

        # Determine which universe to scan based on market cap criteria
        if custom_criteria and custom_criteria.get('market_cap_max'):
            stock_universe = get_universe_by_criteria(custom_criteria['market_cap_max'])
            universe_name = "targeted"
        else:
            # Use full universe for comprehensive scan
            stock_universe = FULL_UNIVERSE
            universe_name = "full"

        logger.info(f"Starting automated market scan ({universe_name} universe: {len(stock_universe)} stocks)...")

        # Run screening on entire universe (blocking I/O - run off event loop)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, screening_engine.screen_multiple_stocks, stock_universe, custom_criteria
        )

        # Convert numpy types
        results = convert_numpy_types(results)

        # Count passed
        passed_count = sum(1 for r in results if r.get('passed_all', False))

        logger.success(f"Market scan complete: {passed_count}/{len(results)} passed all filters")

        # Return top 25 by default for market scans
        top_n = 25

        return ScreenResponse(
            results=results[:top_n],
            total_screened=len(results),
            total_passed=passed_count
        )

    except Exception as e:
        logger.error(f"Error in market scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class QuickScanRequest(BaseModel):
    """Request for quick preset-based scanning"""
    preset: str = "moderate"  # conservative, moderate, aggressive, low_iv_entry, cheap_leaps, momentum, etc.
    max_results: Optional[int] = 25


@router.post("/scan/quick", response_model=ScreenResponse)
async def quick_scan(request: QuickScanRequest):
    """
    Quick Market Scan with Presets

    One-click scanning with predefined criteria presets.
    No configuration needed - just select a preset and scan!

    Standard Presets:
    - conservative: Large caps ($5B+), stable growth, low risk
    - moderate: Mid caps ($1B+), good growth, balanced (DEFAULT)
    - aggressive: Small/mid caps ($500M+), high growth, high reward potential

    LEAPS-Specific Presets:
    - iv_crush: Low IV rank - cheap options, ideal for LEAPS entry
    - cheap_leaps: Premium <10% of stock price, high liquidity
    - momentum: Strong fundamentals + RSI recovering + MACD bullish
    - turnaround: Oversold RSI + above SMA200 - potential reversal plays
    - growth_leaps: High growth companies ideal for long-term LEAPS
    - blue_chip_leaps: Mega caps with stable returns - conservative LEAPS

    Args:
        request: QuickScanRequest with preset selection

    Returns:
        Top LEAPS candidates from market scan
    """
    try:
        preset_criteria = LEAPS_PRESETS.get(request.preset)
        if not preset_criteria:
            logger.warning(f"[QuickScan] Unknown preset '{request.preset}', falling back to 'moderate'")
            preset_criteria = LEAPS_PRESETS["moderate"]
        preset_description = preset_criteria.get("description", "")

        # Remove description from criteria dict (not a screening parameter)
        criteria_for_screening = {k: v for k, v in preset_criteria.items() if k != "description"}

        logger.info(f"Starting quick scan with '{request.preset}' preset: {preset_description}")

        # Get appropriate universe for this preset
        stock_universe = get_universe_by_criteria(criteria_for_screening['market_cap_max'])

        # Run screening (blocking I/O - run off event loop)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, screening_engine.screen_multiple_stocks, stock_universe, criteria_for_screening
        )

        # Convert numpy types
        results = convert_numpy_types(results)

        # Count passed
        passed_count = sum(1 for r in results if r.get('passed_all', False))

        logger.success(f"Quick scan ({request.preset}) complete: {passed_count}/{len(results)} passed")

        return ScreenResponse(
            results=results[:request.max_results],
            total_screened=len(results),
            total_passed=passed_count
        )

    except Exception as e:
        logger.error(f"Error in quick scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets")
async def get_available_presets():
    """
    Get all available scanning presets with descriptions organized by category.

    Returns presets for LEAPS, swing, weekly, earnings, value, dividend,
    small cap, sentiment, options income, and options directional strategies.
    """
    # New category-aware mapping (explicit "category" key takes priority)
    _CATEGORY_MAP = {
        "swing": "swing",
        "weekly": "weekly",
        "earnings": "earnings",
        "value": "value",
        "dividend": "dividend",
        "small_cap": "small_cap",
        "sentiment": "sentiment",
        "options_income": "options_income",
        "options_directional": "options_directional",
    }

    presets = []
    seen = set()  # Avoid listing iv_crush alias twice
    for name, criteria in LEAPS_PRESETS.items():
        if name in seen:
            continue
        # Skip backward-compat alias (iv_crush is alias of low_iv_entry)
        if name == "iv_crush":
            continue
        seen.add(name)

        # Determine category
        explicit_cat = criteria.get("category")
        if name in ["conservative", "moderate", "aggressive"]:
            category = "standard"
        elif explicit_cat and explicit_cat in _CATEGORY_MAP:
            category = _CATEGORY_MAP[explicit_cat]
        else:
            category = "leaps_strategy"

        presets.append({
            "name": name,
            "description": criteria.get("description", ""),
            "category": category,
            "dte_range": f"{criteria.get('dte_min', 365)}-{criteria.get('dte_max', 730)} days",
            "delta_range": f"{criteria.get('delta_min', 0.55):.2f}-{criteria.get('delta_max', 0.80):.2f}" if criteria.get('delta_min') else "0.55-0.80"
        })

    # Group by category for easier frontend consumption
    grouped = {
        "standard": [],
        "leaps_strategy": [],
        "swing": [],
        "weekly": [],
        "earnings": [],
        "value": [],
        "dividend": [],
        "small_cap": [],
        "sentiment": [],
        "options_income": [],
        "options_directional": [],
    }
    for preset in presets:
        cat = preset["category"]
        if cat in grouped:
            grouped[cat].append(preset)

    return {
        "presets": presets,
        "grouped": grouped,
        "categories": [
            {"id": "standard", "name": "Standard Risk Levels", "icon": "⚖️"},
            {"id": "leaps_strategy", "name": "LEAPS Strategies", "icon": "📈"},
            {"id": "swing", "name": "Swing Trading (4-8 weeks)", "icon": "⚡"},
            {"id": "weekly", "name": "Weekly Plays", "icon": "🎯"},
            {"id": "earnings", "name": "Earnings Plays", "icon": "💼"},
            {"id": "value", "name": "Value Investing", "icon": "💎"},
            {"id": "dividend", "name": "Dividend & Income", "icon": "💰"},
            {"id": "small_cap", "name": "Small Cap", "icon": "🔬"},
            {"id": "sentiment", "name": "Sentiment Plays", "icon": "📊"},
            {"id": "options_income", "name": "Options Income", "icon": "🏦"},
            {"id": "options_directional", "name": "Options Directional", "icon": "🎯"},
        ]
    }


@router.get("/scan/stream/{preset}")
async def stream_scan(preset: str = "moderate"):
    """
    Streaming Market Scan with Server-Sent Events

    Returns incremental results as stocks are processed.
    Use EventSource on the frontend to consume this endpoint.

    Args:
        preset: Any preset from LEAPS_PRESETS (conservative, moderate, aggressive,
                iv_crush, cheap_leaps, momentum, turnaround, growth_leaps, blue_chip_leaps)

    Returns:
        SSE stream with progress updates and results
    """
    async def generate_events() -> AsyncGenerator[str, None]:
        try:
            preset_data = LEAPS_PRESETS.get(preset)
            if not preset_data:
                logger.warning(f"[StreamScan] Unknown preset '{preset}', falling back to 'moderate'")
                preset_data = LEAPS_PRESETS["moderate"]
            preset_criteria = {k: v for k, v in preset_data.items() if k != "description"}
            stock_universe = get_dynamic_universe(preset_criteria)
            total_stocks = len(stock_universe)

            # Send initial status
            yield f"data: {json.dumps({'type': 'start', 'total': total_stocks, 'preset': preset})}\n\n"

            all_passed = []
            processed = 0
            batch_size = 15

            # Process in batches
            for i in range(0, total_stocks, batch_size):
                batch = stock_universe[i:i + batch_size]

                # Run screening for batch (in thread to not block)
                loop = asyncio.get_event_loop()
                batch_results = await loop.run_in_executor(
                    None,
                    screening_engine.screen_multiple_stocks,
                    batch,
                    preset_criteria
                )

                processed += len(batch)

                # Collect passed stocks
                if batch_results:
                    batch_results = convert_numpy_types(batch_results)
                    for r in batch_results:
                        if r.get('passed_all', False):
                            all_passed.append(r)

                # Sort by score
                all_passed.sort(key=lambda x: x.get('composite_score', 0), reverse=True)

                # Send progress update
                progress_data = {
                    'type': 'progress',
                    'processed': processed,
                    'total': total_stocks,
                    'passed': len(all_passed),
                    'top_candidates': all_passed[:20]  # Send top 20 so far
                }
                yield f"data: {json.dumps(progress_data)}\n\n"

                # Small delay to prevent overwhelming the client
                await asyncio.sleep(0.1)

            # Send final results (no artificial cap — return all passing stocks)
            final_data = {
                'type': 'complete',
                'processed': processed,
                'total': total_stocks,
                'passed': len(all_passed),
                'results': all_passed
            }
            yield f"data: {json.dumps(final_data)}\n\n"

        except Exception as e:
            logger.error(f"Error in streaming scan: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*"
        }
    )


# ============================================================================
# Scan-All-Presets helpers
# ============================================================================

# Most permissive criteria union across ALL presets — ensures every stock that
# could match *any* preset gets through the initial screening gate.
_ALL_PRESETS_CRITERIA = {
    "market_cap_min": 300_000_000,       # small_cap presets
    "market_cap_max": 10_000_000_000_000, # ultra permissive for mega-caps
    "price_min": 3,                      # aggressive / small_cap
    "price_max": 600,                    # blue_chip_leaps
    "revenue_growth_min": -20,           # turnaround (allow negative)
    "earnings_growth_min": -20,          # turnaround
    "debt_to_equity_max": 300,           # aggressive / turnaround
    "rsi_min": 20,                       # turnaround / swing_oversold
    "rsi_max": 80,                       # aggressive
    "iv_max": 150,                       # short_squeeze
    "skip_sector_filter": True,          # value/dividend presets need all sectors
}

# _PRESET_DISPLAY_NAMES imported from app.data.presets_catalog


def _matches_preset(result: dict, preset_id: str) -> bool:
    """Check if a screened stock result satisfies a specific preset's criteria.

    Handles graceful missing-data:
      - PEG None or 0 → skip (unreliable)
      - Dividend yield None with min set → treat as 0 → FAIL
      - All other None fields with filter → skip
    """
    preset = LEAPS_PRESETS.get(preset_id)
    if not preset:
        return False

    market_cap = result.get('market_cap') or 0
    price = result.get('current_price') or 0
    rsi = (result.get('technical_indicators') or {}).get('rsi_14')
    iv_rank = result.get('iv_rank')

    # Market cap check
    if market_cap < preset.get('market_cap_min', 0):
        return False
    if market_cap > preset.get('market_cap_max', float('inf')):
        return False

    # Price check
    if price < preset.get('price_min', 0):
        return False
    if price > preset.get('price_max', float('inf')):
        return False

    # RSI check (only if RSI data available and preset specifies range)
    if rsi is not None:
        if 'rsi_min' in preset and rsi < preset['rsi_min']:
            return False
        if 'rsi_max' in preset and rsi > preset['rsi_max']:
            return False

    # IV check (iv_max in preset means options IV, approximate with iv_rank)
    if iv_rank is not None and 'iv_max' in preset:
        if iv_rank > preset['iv_max']:
            return False

    # --- New valuation / style checks (Phase 1.5) ---

    # P/E range
    trailing_pe = result.get('trailing_pe')
    if trailing_pe is not None:
        if 'pe_min' in preset and trailing_pe < preset['pe_min']:
            return False
        if 'pe_max' in preset and trailing_pe > preset['pe_max']:
            return False

    # PEG — skip when None or 0 (unreliable from Yahoo)
    peg_ratio = result.get('peg_ratio')
    if 'peg_max' in preset and peg_ratio is not None and peg_ratio > 0:
        if peg_ratio > preset['peg_max']:
            return False

    # Price-to-Book
    price_to_book = result.get('price_to_book')
    if 'pb_max' in preset and price_to_book is not None:
        if price_to_book > preset['pb_max']:
            return False

    # Dividend yield — None treated as 0 when min is set
    dividend_yield = result.get('dividend_yield')
    if 'dividend_yield_min' in preset:
        effective_yield = dividend_yield if dividend_yield is not None else 0.0
        if effective_yield < preset['dividend_yield_min']:
            return False
    if 'dividend_yield_max' in preset and dividend_yield is not None:
        if dividend_yield > preset['dividend_yield_max']:
            return False

    # ROE
    roe = result.get('roe')
    if 'roe_min' in preset and roe is not None:
        if roe < preset['roe_min']:
            return False

    # Profit margin
    profit_margins = result.get('profit_margins')
    if 'profit_margin_min' in preset and profit_margins is not None:
        if profit_margins < preset['profit_margin_min']:
            return False

    # Beta range
    beta = result.get('beta')
    if beta is not None:
        if 'beta_min' in preset and beta < preset['beta_min']:
            return False
        if 'beta_max' in preset and beta > preset['beta_max']:
            return False

    return True


@router.get("/scan/stream/all")
async def stream_scan_all():
    """
    Scan-All-Presets via SSE.

    Screens the full stock universe ONCE with the most permissive criteria,
    then tags each passing stock with the presets it matches.
    Result stocks include a ``matched_presets`` list.
    """
    async def generate_events() -> AsyncGenerator[str, None]:
        try:
            start_time = time.time()
            stock_universe = get_dynamic_universe(_ALL_PRESETS_CRITERIA)
            total_stocks = len(stock_universe)

            yield f"data: {json.dumps({'type': 'start', 'total': total_stocks, 'preset': 'all'})}\n\n"

            all_passed = []
            processed = 0
            batch_size = 15
            preset_ids = list(LEAPS_PRESETS.keys())

            for i in range(0, total_stocks, batch_size):
                batch = stock_universe[i:i + batch_size]

                loop = asyncio.get_event_loop()
                batch_results = await loop.run_in_executor(
                    None,
                    screening_engine.screen_multiple_stocks,
                    batch,
                    _ALL_PRESETS_CRITERIA
                )

                processed += len(batch)

                if batch_results:
                    batch_results = convert_numpy_types(batch_results)
                    for r in batch_results:
                        if r.get('passed_all', False):
                            # Tag with matching presets
                            matched = [pid for pid in preset_ids if _matches_preset(r, pid)]
                            r['matched_presets'] = matched
                            r['matched_preset_names'] = [
                                _PRESET_DISPLAY_NAMES.get(p, p) for p in matched
                            ]
                            if matched:
                                all_passed.append(r)

                all_passed.sort(key=lambda x: x.get('composite_score', 0), reverse=True)

                progress_data = {
                    'type': 'progress',
                    'processed': processed,
                    'total': total_stocks,
                    'passed': len(all_passed),
                    'top_candidates': all_passed[:20],
                }
                yield f"data: {json.dumps(progress_data)}\n\n"

                await asyncio.sleep(0.1)

            # Build per-preset hit counts
            preset_summary = {}
            for pid in preset_ids:
                count = sum(1 for r in all_passed if pid in r.get('matched_presets', []))
                preset_summary[pid] = {
                    'name': _PRESET_DISPLAY_NAMES.get(pid, pid),
                    'count': count,
                }

            # No artificial cap — return all passing stocks
            final_data = {
                'type': 'complete',
                'processed': processed,
                'total': total_stocks,
                'passed': len(all_passed),
                'results': all_passed,
                'preset_summary': preset_summary,
                'duration_seconds': round(time.time() - start_time, 1),
            }
            yield f"data: {json.dumps(final_data)}\n\n"

        except Exception as e:
            logger.error(f"Error in scan-all streaming: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )


# ============================================================================
# LEAPS Calculator Endpoints
# ============================================================================

class ReturnCalculatorRequest(BaseModel):
    """Request for 5x return calculator"""
    current_price: float
    strike: float
    premium: float
    dte: int
    target_multipliers: Optional[List[float]] = None  # Default: [2, 3, 5, 10]


@router.post("/calculator/5x-return")
async def calculate_5x_return(request: ReturnCalculatorRequest):
    """
    5x Return Calculator for LEAPS

    Calculate exactly what stock price is needed for various return multiples
    on a LEAPS call option.

    This is the core LEAPS planning tool - shows:
    - Break-even price and % move needed
    - Stock price needed for 2x, 3x, 5x, 10x returns
    - Annualized return requirements
    - Feasibility assessment
    - Time decay profile

    Args:
        request: ReturnCalculatorRequest with option details

    Returns:
        Comprehensive return analysis
    """
    try:
        result = OptionsAnalysis.calculate_5x_return_analysis(
            current_price=request.current_price,
            strike=request.strike,
            premium=request.premium,
            dte=request.dte,
            target_multipliers=request.target_multipliers
        )

        return convert_numpy_types(result)

    except Exception as e:
        logger.error(f"Error in 5x return calculator: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PLTableRequest(BaseModel):
    """Request for P/L table calculation"""
    strike: float
    premium: float
    current_price: float
    price_range_percent: Optional[float] = 50.0
    num_points: Optional[int] = 15


@router.post("/calculator/pl-table")
async def calculate_pl_table(request: PLTableRequest):
    """
    P/L Table Calculator for Options

    Generate a profit/loss table showing outcomes at various stock prices.
    Perfect for visualizing risk/reward of a LEAPS position.

    Args:
        request: PLTableRequest with option details

    Returns:
        P/L table with profit at each price point
    """
    try:
        result = OptionsAnalysis.calculate_profit_loss_table(
            strike=request.strike,
            premium=request.premium,
            current_price=request.current_price,
            price_range_percent=request.price_range_percent,
            num_points=request.num_points
        )

        return convert_numpy_types(result)

    except Exception as e:
        logger.error(f"Error in P/L table calculator: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class StrikeSelectionRequest(BaseModel):
    """Request for strike selection recommendation"""
    symbol: str
    current_price: float
    target_return: Optional[float] = 5.0  # Default 5x
    risk_tolerance: Optional[str] = "moderate"  # conservative, moderate, aggressive


@router.post("/calculator/strike-selection")
async def recommend_strike(request: StrikeSelectionRequest):
    """
    Strike Selection Wizard

    Recommends optimal strike price based on target return and risk tolerance.

    Guidelines:
    - Conservative: Deep ITM (delta 0.70-0.80), lower leverage, higher probability
    - Moderate: Slightly ITM/ATM (delta 0.50-0.70), balanced risk/reward
    - Aggressive: ATM/OTM (delta 0.30-0.50), higher leverage, lower probability

    Args:
        request: StrikeSelectionRequest with preferences

    Returns:
        Strike recommendation with rationale
    """
    try:
        # Delta targets based on risk tolerance
        delta_ranges = {
            "conservative": {"min": 0.70, "max": 0.85, "description": "Deep ITM - Higher probability, lower leverage"},
            "moderate": {"min": 0.50, "max": 0.70, "description": "ATM to slightly ITM - Balanced approach"},
            "aggressive": {"min": 0.30, "max": 0.50, "description": "OTM - Higher leverage, lower probability"}
        }

        risk_profile = delta_ranges.get(request.risk_tolerance, delta_ranges["moderate"])

        # Calculate recommended strikes based on delta approximation
        # Delta ~ N(d1) for calls, roughly: ATM delta = 0.50
        # ITM: delta > 0.50, OTM: delta < 0.50

        # Simplified strike calculation based on delta targets
        # For a rough approximation: strike = price * (1 - (delta - 0.5) * 0.4)
        min_delta = risk_profile["min"]
        max_delta = risk_profile["max"]

        # Calculate strike range
        # Higher delta = lower strike (more ITM)
        recommended_strike_low = request.current_price * (1 - (max_delta - 0.5) * 0.5)
        recommended_strike_high = request.current_price * (1 - (min_delta - 0.5) * 0.5)

        # Round to nearest $5 for typical option strikes
        def round_to_strike(price):
            if price < 50:
                return round(price / 2.5) * 2.5
            elif price < 200:
                return round(price / 5) * 5
            else:
                return round(price / 10) * 10

        recommendation = {
            "symbol": request.symbol,
            "current_price": request.current_price,
            "target_return": f"{request.target_return}x",
            "risk_tolerance": request.risk_tolerance,
            "delta_range": f"{min_delta:.2f} - {max_delta:.2f}",
            "strategy_description": risk_profile["description"],
            "recommended_strikes": {
                "ideal_strike": round_to_strike((recommended_strike_low + recommended_strike_high) / 2),
                "strike_range_low": round_to_strike(recommended_strike_low),
                "strike_range_high": round_to_strike(recommended_strike_high)
            },
            "guidance": [
                f"For {request.target_return}x return with {request.risk_tolerance} risk:",
                f"Look for strikes between ${round_to_strike(recommended_strike_low):.0f} - ${round_to_strike(recommended_strike_high):.0f}",
                "Prefer 400-500 DTE for optimal time value",
                "Check IV rank < 40% for better entry",
                "Ensure open interest > 100 for liquidity"
            ]
        }

        return recommendation

    except Exception as e:
        logger.error(f"Error in strike selection: {e}")
        raise HTTPException(status_code=500, detail=str(e))
