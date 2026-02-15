"""
Signal Validator — AI-powered pre-trade validation layer.

This is Layer 4 of the 4-layer intelligence pipeline:
  Screening → Strategy Selection → Signal Engine → **AI Pre-Trade Validation**

Before any signal reaches the trading bot, this service:
  1. Fetches FRESH price/volume/spread from Alpaca
  2. Re-checks whether the setup has changed since signal generation
  3. Sends to Claude AI for final go/no-go decision with confidence score
  4. Returns: auto_execute (confidence >= threshold) or manual_review

The critical safety gate between signal generation and real money.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.models.trading_signal import TradingSignal
from app.services.data_fetcher.alpaca_service import alpaca_service
from app.services.ai.claude_service import get_claude_service


# Confidence threshold: signals at or above this score auto-execute,
# below this score get queued for manual review.
# History: 75 → 65 → 70. Raised back to 70: while stocks have passed
# 3 quality layers, only genuinely strong setups should auto-execute.
# Signals scoring 65-69 go to manual review where the user can decide.
CONFIDENCE_THRESHOLD = 70


class SignalValidator:
    """
    AI-powered pre-trade validation. Reviews generated signals with FRESH
    market data before sending to bot.
    """

    def __init__(self, confidence_threshold: int = CONFIDENCE_THRESHOLD):
        self.confidence_threshold = confidence_threshold

    async def validate_signal(
        self,
        signal: TradingSignal,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Validate a single trading signal.

        1. Fetch FRESH price, volume, spread from Alpaca
        2. Re-check: has the setup changed since signal was generated?
        3. Claude AI review with current market context
        4. Return validation result

        Returns:
            {
                "approved": bool,
                "confidence": int (0-100),
                "reasoning": str,
                "action": "auto_execute" | "manual_review" | "reject",
                "fresh_price": float | None,
                "setup_still_valid": bool,
            }
        """
        symbol = signal.symbol
        logger.info(f"[SignalValidator] Validating signal {signal.id} for {symbol}")

        # 1. Fetch fresh market data
        fresh_data = await self._fetch_fresh_data(symbol)

        # 2. Sanity check: has the setup moved past us?
        setup_check = self._check_setup_validity(signal, fresh_data)

        if not setup_check["valid"]:
            # Setup is clearly invalidated — reject without AI call
            result = {
                "approved": False,
                "confidence": 0,
                "reasoning": setup_check["reason"],
                "action": "reject",
                "fresh_price": fresh_data.get("current_price"),
                "setup_still_valid": False,
            }
            await self._update_signal_validation(signal, result, db)
            return result

        # 3. AI validation (the real intelligence layer)
        ai_result = await self._ai_validate(signal, fresh_data)

        confidence = ai_result.get("confidence", 0)
        approved = confidence >= self.confidence_threshold

        if approved:
            action = "auto_execute"
        elif confidence >= 40:
            action = "manual_review"
        else:
            action = "reject"

        result = {
            "approved": approved,
            "confidence": confidence,
            "reasoning": ai_result.get("reasoning", "AI validation completed"),
            "action": action,
            "fresh_price": fresh_data.get("current_price"),
            "setup_still_valid": True,
        }

        # 4. Persist validation result on the signal
        await self._update_signal_validation(signal, result, db)

        logger.info(
            f"[SignalValidator] {symbol} signal {signal.id}: "
            f"action={action}, confidence={confidence}, approved={approved}"
        )
        return result

    async def validate_batch(
        self,
        signals: List[TradingSignal],
        db: Session,
    ) -> List[Dict[str, Any]]:
        """Validate multiple signals. Returns list of validation results."""
        if not signals:
            return []

        results = []
        for signal in signals:
            try:
                result = await self.validate_signal(signal, db)
                result["signal_id"] = signal.id
                result["symbol"] = signal.symbol
                results.append(result)
            except Exception as e:
                logger.error(f"[SignalValidator] Error validating {signal.symbol}: {e}")
                results.append({
                    "signal_id": signal.id,
                    "symbol": signal.symbol,
                    "approved": False,
                    "confidence": 0,
                    "reasoning": f"Validation error: {str(e)}",
                    "action": "manual_review",
                    "fresh_price": None,
                    "setup_still_valid": None,
                })

        approved_count = sum(1 for r in results if r["approved"])
        logger.info(
            f"[SignalValidator] Batch: {approved_count}/{len(results)} approved"
        )
        return results

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    async def _fetch_fresh_data(self, symbol: str) -> Dict[str, Any]:
        """Fetch current market snapshot from Alpaca."""
        try:
            snapshot = await asyncio.to_thread(alpaca_service.get_snapshot, symbol)
            return snapshot or {}
        except Exception as e:
            logger.warning(f"[SignalValidator] Failed to fetch snapshot for {symbol}: {e}")
            return {}

    def _check_setup_validity(
        self,
        signal: TradingSignal,
        fresh_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Quick sanity check — has the price moved past the signal's entry/stop?

        This catches obvious invalidations without needing an AI call:
        - Price already past target_1 (you missed the move)
        - Price below stop_loss (setup broken)
        - Signal is stale (generated too long ago)
        """
        current_price = fresh_data.get("current_price")
        if current_price is None:
            # Can't verify — let AI decide
            return {"valid": True, "reason": "No fresh price data available"}

        entry = signal.entry_price
        stop = signal.stop_loss
        target1 = signal.target_1
        direction = signal.direction

        if entry is None:
            return {"valid": True, "reason": "No entry price to compare"}

        if direction == "buy":
            # For long signals
            if stop and current_price < stop:
                return {
                    "valid": False,
                    "reason": (
                        f"Price ${current_price:.2f} already below stop ${stop:.2f} — "
                        f"setup invalidated"
                    ),
                }
            if target1 and current_price > target1:
                return {
                    "valid": False,
                    "reason": (
                        f"Price ${current_price:.2f} already past T1 ${target1:.2f} — "
                        f"missed the move"
                    ),
                }
            # Price moved too far above entry (chasing)
            if entry > 0:
                pct_above = ((current_price - entry) / entry) * 100
                if pct_above > 3.0:
                    return {
                        "valid": False,
                        "reason": (
                            f"Price ${current_price:.2f} is {pct_above:.1f}% above entry "
                            f"${entry:.2f} — would be chasing"
                        ),
                    }

        elif direction == "sell":
            # For short signals
            if stop and current_price > stop:
                return {
                    "valid": False,
                    "reason": (
                        f"Price ${current_price:.2f} already above stop ${stop:.2f} — "
                        f"setup invalidated"
                    ),
                }
            if target1 and current_price < target1:
                return {
                    "valid": False,
                    "reason": (
                        f"Price ${current_price:.2f} already past T1 ${target1:.2f} — "
                        f"missed the move"
                    ),
                }
            # Price moved too far below entry (chasing a short)
            if entry > 0:
                pct_below = ((entry - current_price) / entry) * 100
                if pct_below > 3.0:
                    return {
                        "valid": False,
                        "reason": (
                            f"Price ${current_price:.2f} is {pct_below:.1f}% below entry "
                            f"${entry:.2f} — would be chasing short"
                        ),
                    }

        # Check signal age (reject signals older than 2 hours for intraday)
        if signal.generated_at:
            gen_at = signal.generated_at
            if gen_at.tzinfo is None:
                gen_at = gen_at.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - gen_at).total_seconds()
            max_age = 7200  # 2 hours for intraday
            if signal.timeframe in ("1h", "1d"):
                max_age = 28800  # 8 hours for swing/daily
            if age_seconds > max_age:
                return {
                    "valid": False,
                    "reason": (
                        f"Signal is {age_seconds/3600:.1f}h old — too stale "
                        f"(max {max_age/3600:.0f}h for {signal.timeframe})"
                    ),
                }

        return {"valid": True, "reason": "Setup checks passed"}

    async def _ai_validate(
        self,
        signal: TradingSignal,
        fresh_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Call Claude AI for final validation with fresh market context.

        Returns: {confidence: int, reasoning: str}
        """
        claude = get_claude_service()
        if not claude or not claude.is_available():
            logger.warning("[SignalValidator] Claude not available — defaulting to manual review")
            return {
                "confidence": 50,
                "reasoning": "AI service unavailable — defaulting to manual review",
            }

        # Build validation prompt
        current_price = fresh_data.get("current_price", "N/A")
        change_pct = fresh_data.get("change_percent", "N/A")
        volume = fresh_data.get("daily_bar", {}).get("volume", "N/A")
        bid = fresh_data.get("latest_quote", {}).get("bid", "N/A")
        ask = fresh_data.get("latest_quote", {}).get("ask", "N/A")

        prompt = f"""You are a pre-trade validation AI. Review this signal with FRESH market data and decide if it should execute.

SIGNAL:
- Symbol: {signal.symbol}
- Strategy: {signal.strategy}
- Direction: {signal.direction}
- Timeframe: {signal.timeframe}
- Entry: ${signal.entry_price}
- Stop Loss: ${signal.stop_loss}
- Target 1: ${signal.target_1}
- Target 2: ${signal.target_2}
- R:R Ratio: {signal.risk_reward_ratio}
- Confidence: {signal.confidence_score}/100
- Generated: {signal.generated_at}

FRESH MARKET DATA (right now):
- Current Price: ${current_price}
- Change Today: {change_pct}%
- Volume: {volume}
- Bid/Ask: ${bid} / ${ask}

AI REASONING FROM SIGNAL: {signal.ai_reasoning or 'N/A'}

VALIDATE:
1. Is the setup still valid at the current price?
2. Does current volume/momentum confirm the direction?
3. Is risk/reward still favorable?
4. Any red flags? (gap risk, extended move, thin liquidity)

Respond with JSON only:
{{"confidence": <0-100>, "reasoning": "<2-3 sentences max>"}}

Rules:
- confidence >= 70 = auto-execute (high conviction)
- confidence 40-69 = manual review needed
- confidence < 40 = reject the trade
- Evaluate objectively. Consider volume confirmation, momentum alignment, and risk/reward.
- Flag weak setups even if they technically passed prior screening layers.
- Key red flags: weak volume (<1x avg), oversold/overbought RSI, missing VWAP context, wide spreads, earnings proximity."""

        try:
            result = await claude.call_claude(
                prompt,
                system_prompt="You are a precise pre-trade validation system. Output valid JSON only.",
                model=claude.settings.CLAUDE_MODEL_FAST,  # Use Haiku for speed
                max_tokens=200,
                temperature=0.2,
            )

            response_text, usage = result
            if response_text:
                parsed = claude.parser.extract_json(response_text)
                if parsed and "confidence" in parsed:
                    return {
                        "confidence": min(100, max(0, int(parsed["confidence"]))),
                        "reasoning": parsed.get("reasoning", "AI validated"),
                    }

            # Fallback if parsing failed
            return {
                "confidence": 50,
                "reasoning": "AI response could not be parsed — manual review recommended",
            }

        except Exception as e:
            logger.error(f"[SignalValidator] AI validation error for {signal.symbol}: {e}")
            return {
                "confidence": 50,
                "reasoning": f"AI validation error — manual review recommended",
            }

    async def _update_signal_validation(
        self,
        signal: TradingSignal,
        result: Dict[str, Any],
        db: Session,
    ):
        """
        Persist validation result on the TradingSignal record.
        NOTE: Uses flush() not commit() — caller manages the transaction.
        """
        try:
            signal.validation_status = (
                "validated" if result["approved"]
                else "rejected" if result["action"] == "reject"
                else "pending_validation"
            )
            signal.validation_reasoning = result["reasoning"]
            signal.validated_at = datetime.now(timezone.utc)
            db.flush()  # Write to DB without committing
        except Exception as e:
            logger.error(f"[SignalValidator] Failed to update signal {signal.id}: {e}")


# Singleton
signal_validator = SignalValidator()
