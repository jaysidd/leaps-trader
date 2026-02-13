"""
Scan Processing API — orchestrates the StrategySelector pipeline.

Endpoints:
  POST /process          — Run StrategySelector on a saved scan, auto-queue HIGH confidence
  POST /ai-review        — Send MEDIUM-confidence stocks to Claude for batch AI review
  POST /queue-reviewed   — Queue AI-approved stocks to signal processing
"""

import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from app.database import get_db
from app.models.saved_scan import SavedScanResult
from app.models.signal_queue import SignalQueue
from app.services.signals.strategy_selector import strategy_selector
from app.services.data_fetcher.fmp_service import fmp_service
from app.services.data_fetcher.alpaca_service import alpaca_service
from app.services.ai.claude_service import get_claude_service

router = APIRouter()


# ── Request / Response models ──────────────────────────────────────


class ProcessRequest(BaseModel):
    scan_type: str = Field(..., description="Name of the saved scan to process")


class ReviewStock(BaseModel):
    symbol: str
    concerns: Optional[str] = None
    metrics: Optional[dict] = None
    suggested_timeframes: Optional[List[str]] = None


class AIReviewRequest(BaseModel):
    stocks: List[ReviewStock]


class QueueStock(BaseModel):
    symbol: str
    timeframes: List[str]
    strategy: str = "auto"
    cap_size: Optional[str] = None
    name: Optional[str] = None
    confidence_level: Optional[str] = None
    reasoning: Optional[str] = None


class QueueReviewedRequest(BaseModel):
    stocks: List[QueueStock]


# ── Endpoints ──────────────────────────────────────────────────────


@router.post("/process", response_model=dict)
async def process_scan(request: ProcessRequest, db: Session = Depends(get_db)):
    """
    Run the StrategySelector pipeline on all stocks from a saved scan.

    1. Fetch all stocks from SavedScanResult for the given scan_type
    2. Batch-fetch fresh FMP technical indicators
    3. Batch-fetch Alpaca snapshots
    4. Run StrategySelector on each stock
    5. Auto-queue HIGH confidence stocks to signal queue
    6. Return categorized results
    """
    try:
        # 1. Load saved scan results
        scan_results = (
            db.query(SavedScanResult)
            .filter(SavedScanResult.scan_type == request.scan_type)
            .order_by(SavedScanResult.score.desc())
            .all()
        )

        if not scan_results:
            raise HTTPException(404, f"No saved scan results found for '{request.scan_type}'")

        stocks_data = []
        for sr in scan_results:
            # IMPORTANT: copy the dict to avoid mutating the ORM-tracked JSON
            sd = dict(sr.stock_data or {})
            sd["symbol"] = sr.symbol
            sd["score"] = float(sr.score) if sr.score is not None else sd.get("score", 0)
            sd["market_cap"] = float(sr.market_cap) if sr.market_cap is not None else sd.get("market_cap", 0)
            sd["iv_rank"] = float(sr.iv_rank) if sr.iv_rank is not None else sd.get("iv_rank")
            sd["iv_percentile"] = float(sr.iv_percentile) if sr.iv_percentile is not None else sd.get("iv_percentile")
            sd["name"] = sr.company_name or sd.get("name")
            stocks_data.append(sd)

        symbols = [s["symbol"] for s in stocks_data]
        logger.info(f"[ScanProcessing] Processing {len(symbols)} stocks from '{request.scan_type}'")

        # 2. Fetch fresh FMP indicators (parallel, async)
        bulk_metrics = {}
        try:
            bulk_metrics = await asyncio.to_thread(
                fmp_service.get_bulk_strategy_metrics, symbols
            )
        except Exception as e:
            logger.warning(f"[ScanProcessing] FMP bulk fetch failed, continuing without: {e}")

        # 3. Fetch Alpaca snapshots (sync call, wrap in thread)
        bulk_snapshots = {}
        try:
            bulk_snapshots = await asyncio.to_thread(
                alpaca_service.get_multi_snapshots, symbols
            )
        except Exception as e:
            logger.warning(f"[ScanProcessing] Alpaca snapshot fetch failed, continuing without: {e}")

        # 4. Run StrategySelector
        categorized = strategy_selector.select_strategies_bulk(
            stocks_data, bulk_metrics, bulk_snapshots
        )

        # 5. Auto-queue HIGH confidence stocks
        queued_items = []
        for result in categorized["auto_queued"]:
            symbol = result["symbol"]
            name = next(
                (s.get("name") for s in stocks_data if s["symbol"] == symbol), None
            )
            cap_size = next(
                (s.get("cap_size") for s in stocks_data if s["symbol"] == symbol), None
            )

            for tf_entry in result["timeframes"]:
                tf = tf_entry["tf"]
                # Check if already in active queue for this symbol+timeframe
                existing = db.query(SignalQueue).filter(
                    SignalQueue.symbol == symbol,
                    SignalQueue.timeframe == tf,
                    SignalQueue.status == "active",
                ).first()
                if existing:
                    continue

                queue_item = SignalQueue(
                    symbol=symbol,
                    name=name,
                    timeframe=tf,
                    strategy=tf_entry.get("strategy", "auto"),
                    cap_size=cap_size,
                    source="auto_process",
                    status="active",
                    confidence_level=result["confidence"],
                    strategy_reasoning=result["reasoning"],
                )
                db.add(queue_item)
                queued_items.append({
                    "symbol": symbol,
                    "timeframe": tf,
                    "confidence": result["confidence"],
                })

        db.commit()

        logger.info(
            f"[ScanProcessing] Results: {len(categorized['auto_queued'])} auto-queued, "
            f"{len(categorized['review_needed'])} review, "
            f"{len(categorized['skipped'])} skipped"
        )

        # 6. Return categorized results
        return {
            "success": True,
            "scan_type": request.scan_type,
            "total_stocks": len(stocks_data),
            "auto_queued": [
                {
                    "symbol": r["symbol"],
                    "score": r["score"],
                    "timeframes": [t["tf"] for t in r["timeframes"]],
                    "confidence": r["confidence"],
                    "reasoning": r["reasoning"],
                }
                for r in categorized["auto_queued"]
            ],
            "review_needed": [
                {
                    "symbol": r["symbol"],
                    "score": r["score"],
                    "timeframes": [t["tf"] for t in r["timeframes"]],
                    "confidence": r["confidence"],
                    "reasoning": r["reasoning"],
                    "edge_cases": r["edge_cases"],
                }
                for r in categorized["review_needed"]
            ],
            "skipped": [
                {
                    "symbol": r["symbol"],
                    "score": r["score"],
                    "confidence": r["confidence"],
                    "reasoning": r["reasoning"],
                    "edge_cases": r["edge_cases"],
                }
                for r in categorized["skipped"]
            ],
            "stats": {
                "total": len(stocks_data),
                "auto_queued_count": len(categorized["auto_queued"]),
                "review_count": len(categorized["review_needed"]),
                "skipped_count": len(categorized["skipped"]),
                "queue_entries_created": len(queued_items),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ScanProcessing] Error processing scan: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(500, f"Failed to process scan: {str(e)}")


@router.post("/ai-review", response_model=dict)
async def ai_review_batch(request: AIReviewRequest):
    """
    Send MEDIUM-confidence stocks to Claude for AI-assisted review.
    Returns AI decisions per stock: QUEUE / SKIP / WATCH.
    """
    claude = get_claude_service()
    if not claude or not claude.is_available():
        raise HTTPException(503, "Claude AI service is not available")

    if not request.stocks:
        raise HTTPException(400, "No stocks provided for review")

    if len(request.stocks) > 50:
        raise HTTPException(400, "Maximum 50 stocks per AI review batch")

    try:
        # Build a concise prompt for batch review
        stock_summaries = []
        for s in request.stocks:
            summary = f"- {s.symbol}"
            if s.concerns:
                summary += f" | Concerns: {s.concerns}"
            if s.suggested_timeframes:
                summary += f" | Suggested TFs: {', '.join(s.suggested_timeframes)}"
            if s.metrics:
                score = s.metrics.get("score", "?")
                iv = s.metrics.get("iv_rank", "?")
                summary += f" | Score: {score}, IV Rank: {iv}"
            stock_summaries.append(summary)

        prompt = (
            "You are reviewing stocks that passed screening but have MEDIUM confidence "
            "for strategy assignment. For each stock, decide: QUEUE (proceed to signal "
            "processing), SKIP (not suitable now), or WATCH (add to watchlist for later).\n\n"
            "Consider: current market conditions, the specific concerns listed, whether "
            "the suggested timeframes are appropriate, and risk/reward.\n\n"
            "Stocks to review:\n"
            + "\n".join(stock_summaries)
            + "\n\nRespond with a JSON array of objects, one per stock:\n"
            '[\n  {"symbol": "AAPL", "decision": "QUEUE", "timeframes": ["1h", "1d"], '
            '"reasoning": "Strong trend despite overbought RSI..."}\n]\n'
            "Only use QUEUE, SKIP, or WATCH as decisions. Keep reasoning under 50 words per stock."
        )

        # Use call_claude directly with the strategy review prompt
        # (analyze_batch uses a different prompt template for screening summaries)
        response_text, usage = await claude.call_claude(
            prompt,
            system_prompt="You are a trading strategy analyst. Output valid JSON only.",
            max_tokens=1500,
            temperature=0.3,
        )

        analysis_data = None
        if response_text:
            parsed = claude.parser.extract_json(response_text)
            if parsed:
                analysis_data = parsed
            else:
                # Wrap raw text in a dict to maintain consistent response type
                analysis_data = {"raw_response": response_text, "parse_error": True}

        return {
            "success": True,
            "analysis": analysis_data,
            "stock_count": len(request.stocks),
        }

    except Exception as e:
        logger.error(f"[ScanProcessing] AI review failed: {e}", exc_info=True)
        raise HTTPException(500, f"AI review failed: {str(e)}")


@router.post("/queue-reviewed", response_model=dict)
async def queue_reviewed_stocks(request: QueueReviewedRequest, db: Session = Depends(get_db)):
    """
    Queue AI-reviewed or manually-approved stocks to signal processing.
    Creates SignalQueue entries for each stock+timeframe combination.
    """
    if not request.stocks:
        raise HTTPException(400, "No stocks provided")

    try:
        added = []
        skipped = []

        for stock in request.stocks:
            symbol = stock.symbol.upper().strip()

            for tf in stock.timeframes:
                if tf not in {"5m", "15m", "1h", "1d"}:
                    skipped.append({"symbol": symbol, "timeframe": tf, "reason": "invalid timeframe"})
                    continue

                # Check for existing active entry
                existing = db.query(SignalQueue).filter(
                    SignalQueue.symbol == symbol,
                    SignalQueue.timeframe == tf,
                    SignalQueue.status == "active",
                ).first()

                if existing:
                    skipped.append({"symbol": symbol, "timeframe": tf, "reason": "already active"})
                    continue

                queue_item = SignalQueue(
                    symbol=symbol,
                    name=stock.name,
                    timeframe=tf,
                    strategy=stock.strategy,
                    cap_size=stock.cap_size,
                    source="ai_review",
                    status="active",
                    confidence_level=stock.confidence_level,
                    strategy_reasoning=stock.reasoning,
                )
                db.add(queue_item)
                added.append({"symbol": symbol, "timeframe": tf})

        db.commit()

        logger.info(f"[ScanProcessing] Queued {len(added)} reviewed items, skipped {len(skipped)}")

        return {
            "success": True,
            "added": added,
            "added_count": len(added),
            "skipped": skipped,
            "skipped_count": len(skipped),
        }

    except Exception as e:
        logger.error(f"[ScanProcessing] Error queueing reviewed stocks: {e}")
        db.rollback()
        raise HTTPException(500, f"Failed to queue stocks: {str(e)}")
