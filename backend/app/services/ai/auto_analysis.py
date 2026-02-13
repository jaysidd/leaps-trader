"""
Auto AI Analysis Service

Automatically runs AI Deep Analysis on high-confidence trading signals
and sends Telegram alerts for strong buy recommendations.

Flow:
  Signal Engine creates TradingSignal (confidence ≥ threshold)
    → auto_analyze_signal() runs AI deep analysis
    → If conviction ≥ 7 & action = enter_now → send Telegram strong buy alert
    → Store result on TradingSignal.ai_deep_analysis

Budget controls:
  - Only auto-analyzes signals with confidence ≥ AUTO_ANALYSIS_MIN_CONFIDENCE (75%)
  - Max AUTO_ANALYSIS_DAILY_LIMIT analyses per day (20)
  - Respects existing $10/day AI budget
  - Cooldown: 1 alert per symbol per 4 hours
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from loguru import logger


# ── Configuration ──────────────────────────────────────────────────────────────
AUTO_ANALYSIS_MIN_CONFIDENCE = 75       # Minimum signal confidence to trigger auto-analysis
AUTO_ANALYSIS_DAILY_LIMIT = 20          # Max auto-analyses per day
STRONG_BUY_MIN_CONVICTION = 7           # Minimum AI conviction for strong buy alert
STRONG_BUY_ACTIONS = {"enter_now"}      # AI actions that qualify for strong buy alert
SYMBOL_COOLDOWN_HOURS = 4               # Cooldown per symbol for alerts


class AutoAnalysisService:
    """
    Manages automatic AI analysis of high-confidence trading signals.
    """

    def __init__(self):
        self._daily_count = 0
        self._daily_reset_date = None
        self._symbol_cooldowns: Dict[str, datetime] = {}  # symbol → last alert time

    def _reset_daily_if_needed(self):
        """Reset daily counter if it's a new day."""
        today = datetime.now(timezone.utc).date()
        if self._daily_reset_date != today:
            self._daily_count = 0
            self._daily_reset_date = today

    def should_auto_analyze(self, confidence_score: float) -> bool:
        """
        Check if a signal qualifies for auto-analysis.

        Args:
            confidence_score: Signal engine confidence (0-100)

        Returns:
            True if the signal should be auto-analyzed
        """
        self._reset_daily_if_needed()

        if confidence_score < AUTO_ANALYSIS_MIN_CONFIDENCE:
            return False

        if self._daily_count >= AUTO_ANALYSIS_DAILY_LIMIT:
            logger.debug(
                f"Auto-analysis daily limit reached ({AUTO_ANALYSIS_DAILY_LIMIT})"
            )
            return False

        return True

    def _is_symbol_on_cooldown(self, symbol: str) -> bool:
        """Check if a symbol is on alert cooldown."""
        last_alert = self._symbol_cooldowns.get(symbol)
        if last_alert is None:
            return False
        cooldown_until = last_alert + timedelta(hours=SYMBOL_COOLDOWN_HOURS)
        return datetime.now(timezone.utc) < cooldown_until

    async def auto_analyze_signal(
        self,
        signal_id: int,
        signal_dict: Dict[str, Any],
        db_session: Any,
    ) -> Optional[Dict]:
        """
        Run AI Deep Analysis on a newly created trading signal.

        This is called from the signal engine's check_signals_job after a
        high-confidence signal is created. It:
        1. Runs the full AI analysis (regime classification + template)
        2. Stores result on TradingSignal.ai_deep_analysis
        3. If strong buy → sends Telegram alert

        Args:
            signal_id: TradingSignal.id
            signal_dict: TradingSignal.to_dict() output
            db_session: SQLAlchemy session (for updating the signal record)

        Returns:
            Analysis result dict, or None if skipped/failed
        """
        symbol = signal_dict.get("symbol", "UNKNOWN")

        try:
            from app.services.ai.claude_service import get_claude_service
            from app.services.ai.market_regime import get_regime_detector

            claude = get_claude_service()
            if not claude.is_available():
                logger.debug("Auto-analysis skipped: Claude not available")
                return None

            self._reset_daily_if_needed()
            self._daily_count += 1

            logger.info(
                f"🤖 Auto-analyzing signal #{signal_id} {symbol} "
                f"(daily count: {self._daily_count}/{AUTO_ANALYSIS_DAILY_LIMIT})"
            )

            # Get market regime
            regime = None
            try:
                regime = await get_regime_detector().get_regime()
            except Exception as e:
                logger.warning(f"Could not get regime for auto-analysis: {e}")

            # Run AI Deep Analysis
            result = await claude.analyze_signal(
                signal_data=signal_dict,
                market_regime=regime,
            )

            if not result.success:
                logger.warning(f"Auto-analysis failed for {symbol}: {result.error}")
                return None

            analysis = result.data
            conviction = analysis.get("conviction", 0)
            action = analysis.get("action", "skip")

            logger.info(
                f"🤖 Auto-analysis result for {symbol}: "
                f"conviction={conviction}/10, action={action}"
            )

            # Store on DB record
            try:
                from app.models.trading_signal import TradingSignal

                signal_record = db_session.query(TradingSignal).filter(
                    TradingSignal.id == signal_id
                ).first()
                if signal_record:
                    signal_record.ai_deep_analysis = analysis
                    signal_record.ai_deep_analysis_at = datetime.now(timezone.utc)
                    db_session.commit()
                    logger.info(f"💾 AI analysis stored on signal #{signal_id}")
            except Exception as e:
                logger.error(f"Failed to store auto-analysis on signal #{signal_id}: {e}")

            # Check if this qualifies as a strong buy alert
            if (
                conviction >= STRONG_BUY_MIN_CONVICTION
                and action in STRONG_BUY_ACTIONS
                and not self._is_symbol_on_cooldown(symbol)
            ):
                await self._send_strong_buy_alert(signal_dict, analysis)
                self._symbol_cooldowns[symbol] = datetime.now(timezone.utc)

            return analysis

        except Exception as e:
            logger.error(f"Error in auto-analysis for {symbol}: {e}")
            return None

    async def _send_strong_buy_alert(
        self,
        signal_dict: Dict[str, Any],
        analysis: Dict[str, Any],
    ):
        """
        Send a Telegram strong buy alert for a signal with high AI conviction.
        """
        try:
            from app.config import get_settings
            from app.services.telegram_bot import get_telegram_bot

            settings = get_settings()
            allowed_users = settings.TELEGRAM_ALLOWED_USERS
            if not allowed_users:
                return

            chat_ids = [uid.strip() for uid in allowed_users.split(",") if uid.strip()]
            if not chat_ids:
                return

            telegram_bot = get_telegram_bot()
            if not telegram_bot.is_running():
                logger.debug("Telegram not running, skipping strong buy alert")
                return

            # Build the strong buy message
            symbol = signal_dict.get("symbol", "???")
            direction = signal_dict.get("direction", "buy").upper()
            strategy = signal_dict.get("strategy", "").replace("_", " ").title()
            confidence = signal_dict.get("confidence_score", 0)
            entry = signal_dict.get("entry_price", 0)
            stop = signal_dict.get("stop_loss", 0)
            target = signal_dict.get("target_1", 0)
            rr = signal_dict.get("risk_reward_ratio", 0)

            conviction = analysis.get("conviction", 0)
            action = analysis.get("action", "enter_now")
            strategy_match = analysis.get("strategy_match", strategy)
            summary = analysis.get("summary", "")
            fit_score = analysis.get("strategy_fit_score", 0)
            failure_mode = analysis.get("failure_mode", "")

            # Checklist summary
            checklist = analysis.get("checklist", {})
            passed = sum(1 for v in checklist.values() if v is True)
            total = len(checklist) if checklist else 0

            # Options play
            options = analysis.get("options_play", {})
            options_line = ""
            if options and options.get("structure") and options["structure"] != "none":
                options_line = (
                    f"\n📊 *Options:* {options['structure'].replace('_', ' ').title()}"
                    f" ({options.get('iv_assessment', 'N/A')} IV)"
                    f" | {options.get('suggested_dte', 'N/A')} DTE"
                )

            action_emoji = "🟢" if action == "enter_now" else "🟡"
            conviction_bar = "🟩" * conviction + "⬜" * (10 - conviction)

            message = (
                f"🧠 *AI STRONG BUY ALERT*\n"
                f"{'━' * 28}\n\n"
                f"*{symbol}* — {direction}\n"
                f"Strategy: {strategy_match}\n\n"
                f"{action_emoji} *Conviction: {conviction}/10*\n"
                f"{conviction_bar}\n\n"
                f"💰 Entry: ${entry:.2f}\n"
                f"🛑 Stop: ${stop:.2f}\n"
                f"🎯 Target: ${target:.2f}\n"
                f"⚖️ R:R: {rr:.1f}x\n"
                f"📋 Checklist: {passed}/{total} passed"
                f"{options_line}\n\n"
                f"_{summary}_\n\n"
            )

            if failure_mode:
                message += f"⚠️ _Invalidates if: {failure_mode}_\n\n"

            message += (
                f"Engine Confidence: {confidence:.0f}%"
                f" | Fit: {fit_score}%"
                f"\n_Open the app for full analysis_"
            )

            sent = 0
            for chat_id in chat_ids:
                try:
                    await telegram_bot.send_message(chat_id, message)
                    sent += 1
                except Exception as e:
                    logger.error(f"Failed to send strong buy alert to {chat_id}: {e}")

            if sent > 0:
                logger.info(
                    f"🚀 Telegram STRONG BUY alert sent for {symbol} "
                    f"(conviction {conviction}/10) to {sent} user(s)"
                )

        except Exception as e:
            logger.error(f"Error sending strong buy alert: {e}")


# ── Singleton ──────────────────────────────────────────────────────────────────
_auto_analysis_service: Optional[AutoAnalysisService] = None


def get_auto_analysis_service() -> AutoAnalysisService:
    """Get the global AutoAnalysisService instance."""
    global _auto_analysis_service
    if _auto_analysis_service is None:
        _auto_analysis_service = AutoAnalysisService()
    return _auto_analysis_service
