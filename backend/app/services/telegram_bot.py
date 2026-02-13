"""
Telegram Bot integration for LEAPS Trader.

Allows remote stock screening and monitoring via Telegram commands.

Commands:
  /start - Welcome message and help
  /help - Show available commands
  /scan [preset] - Run market scan (conservative/moderate/aggressive)
  /iv [symbol] - Get IV rank and metrics for a symbol
  /leaps [symbol] - Get LEAPS expirations for a symbol
  /quote [symbol] - Get current price and basic info
  /status - Check API connection status
"""
import asyncio
from typing import Optional, List, Set
from loguru import logger

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from app.config import get_settings


class TelegramBotService:
    """Telegram bot service for remote LEAPS screening."""

    def __init__(self):
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self.allowed_users: Set[int] = set()
        self._running = False

    def initialize(self, bot_token: str, allowed_users: str = "") -> bool:
        """
        Initialize the Telegram bot.

        Args:
            bot_token: Telegram bot token from BotFather
            allowed_users: Comma-separated list of allowed user IDs

        Returns:
            True if initialization successful
        """
        if not bot_token:
            logger.warning("Telegram bot token not configured")
            return False

        try:
            # Parse allowed users
            if allowed_users:
                self.allowed_users = {
                    int(uid.strip())
                    for uid in allowed_users.split(",")
                    if uid.strip().isdigit()
                }
                logger.info(f"Telegram bot restricted to {len(self.allowed_users)} users")
            else:
                logger.warning("No allowed users configured - bot will accept all users")

            # Build application
            self.application = (
                Application.builder()
                .token(bot_token)
                .build()
            )

            # Register handlers
            self._register_handlers()

            logger.info("Telegram bot initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            return False

    def _register_handlers(self):
        """Register command handlers."""
        app = self.application

        # Command handlers
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("scan", self._cmd_scan))
        app.add_handler(CommandHandler("iv", self._cmd_iv))
        app.add_handler(CommandHandler("leaps", self._cmd_leaps))
        app.add_handler(CommandHandler("quote", self._cmd_quote))
        app.add_handler(CommandHandler("watchlist", self._cmd_watchlist))
        app.add_handler(CommandHandler("mri", self._cmd_mri))
        app.add_handler(CommandHandler("macro", self._cmd_macro))

        # Handle unknown commands
        app.add_handler(MessageHandler(filters.COMMAND, self._cmd_unknown))

    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot."""
        if not self.allowed_users:
            return True  # No restrictions if no users configured
        return user_id in self.allowed_users

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        user_id = user.id

        if not self._is_authorized(user_id):
            await update.message.reply_text(
                f"Unauthorized. Your user ID is: {user_id}\n"
                "Add this ID to TELEGRAM_ALLOWED_USERS in .env"
            )
            return

        welcome = (
            f"Welcome to LEAPS Trader Bot, {user.first_name}!\n\n"
            "I help you find 5x LEAPS opportunities from anywhere.\n\n"
            "Quick commands:\n"
            "/scan moderate - Run market scan\n"
            "/iv NVDA - Get IV rank for a stock\n"
            "/quote AAPL - Get current price\n\n"
            "Type /help for all commands."
        )
        await update.message.reply_text(welcome)

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._is_authorized(update.effective_user.id):
            return

        help_text = (
            "*LEAPS Trader Commands*\n\n"
            "*Scanning:*\n"
            "/scan `[preset]` - Run market scan\n"
            "  Presets: conservative, moderate, aggressive\n\n"
            "*Analysis:*\n"
            "/iv `[symbol]` - IV rank & volatility metrics\n"
            "/leaps `[symbol]` - LEAPS expiration dates\n"
            "/quote `[symbol]` - Current price & info\n\n"
            "*Macro Signals:*\n"
            "/mri - Macro Risk Index with drivers\n"
            "/macro - Full macro signal summary\n\n"
            "*Watchlists:*\n"
            "/watchlist `[name]` - Scan a watchlist\n"
            "  Names: tech, semis, healthcare, fintech\n\n"
            "*System:*\n"
            "/status - Check API connections\n"
            "/help - Show this message"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._is_authorized(update.effective_user.id):
            return

        from app.services.data_fetcher.tastytrade import get_tastytrade_service
        from app.services.data_fetcher import finviz

        tastytrade = get_tastytrade_service()
        finviz_ok = finviz.finviz_service is not None and finviz.finviz_service.api_token

        status = (
            "*API Status*\n\n"
            f"TastyTrade: {'Connected' if tastytrade.is_available() else 'Not configured'}\n"
            f"Finviz: {'Connected' if finviz_ok else 'Not configured'}\n"
            f"Yahoo Finance: Connected\n"
            f"Telegram Bot: Running\n"
        )
        await update.message.reply_text(status, parse_mode="Markdown")

    async def _cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /scan command with incremental results."""
        if not self._is_authorized(update.effective_user.id):
            return

        # Get preset from args
        preset = "moderate"
        if context.args:
            preset = context.args[0].lower()
            if preset not in ["conservative", "moderate", "aggressive"]:
                await update.message.reply_text(
                    "Invalid preset. Use: conservative, moderate, or aggressive"
                )
                return

        # Send initial status message
        status_msg = await update.message.reply_text(
            f"*{preset.upper()} Scan*\nStarting scan...",
            parse_mode="Markdown"
        )

        try:
            # Import screening engine and stock universe
            from app.services.screening.engine import ScreeningEngine
            from app.data.stock_universe import get_universe_by_criteria

            # Define preset criteria
            PRESETS = {
                "conservative": {
                    "market_cap_min": 5_000_000_000,
                    "market_cap_max": 5_000_000_000_000,
                    "price_min": 10,
                    "price_max": 300,
                    "revenue_growth_min": 5,
                    "earnings_growth_min": 0,
                    "debt_to_equity_max": 150,
                    "rsi_min": 30,
                    "rsi_max": 70,
                    "iv_max": 80
                },
                "moderate": {
                    "market_cap_min": 1_000_000_000,
                    "market_cap_max": 100_000_000_000,
                    "price_min": 5,
                    "price_max": 500,
                    "revenue_growth_min": 10,
                    "earnings_growth_min": 5,
                    "debt_to_equity_max": 200,
                    "rsi_min": 25,
                    "rsi_max": 75,
                    "iv_max": 100
                },
                "aggressive": {
                    "market_cap_min": 500_000_000,
                    "market_cap_max": 50_000_000_000,
                    "price_min": 3,
                    "price_max": 750,
                    "revenue_growth_min": 15,
                    "earnings_growth_min": 10,
                    "debt_to_equity_max": 300,
                    "rsi_min": 20,
                    "rsi_max": 80,
                    "iv_max": 120
                }
            }

            preset_criteria = PRESETS.get(preset, PRESETS["moderate"])
            stock_universe = get_universe_by_criteria(preset_criteria['market_cap_max'])
            total_stocks = len(stock_universe)

            engine = ScreeningEngine()
            all_passed = []
            processed = 0
            batch_size = 15  # Process 15 stocks at a time
            last_update = 0

            # Process stocks in batches
            for i in range(0, total_stocks, batch_size):
                batch = stock_universe[i:i + batch_size]

                # Screen this batch
                batch_results = await asyncio.to_thread(
                    engine.screen_multiple_stocks,
                    batch,
                    preset_criteria
                )

                processed += len(batch)

                # Collect passed stocks
                if batch_results:
                    for r in batch_results:
                        if r.get('passed_all', False):
                            all_passed.append(r)

                # Sort by score
                all_passed.sort(key=lambda x: x.get('score', 0), reverse=True)

                # Update message every batch (if we have new results or every 30 stocks)
                if len(all_passed) > last_update or processed % 30 == 0:
                    last_update = len(all_passed)

                    # Build progress message
                    msg = f"*{preset.upper()} Scan*\n"
                    msg += f"Progress: {processed}/{total_stocks} stocks\n"
                    msg += f"Candidates found: {len(all_passed)}\n\n"

                    if all_passed:
                        msg += "*Top candidates so far:*\n"
                        for j, stock in enumerate(all_passed[:5], 1):
                            symbol = stock.get("symbol", "N/A")
                            score = stock.get("score", 0)
                            msg += f"{j}. *{symbol}* - Score: {score:.0f}\n"

                    msg += "\n_Scanning..._"

                    try:
                        await status_msg.edit_text(msg, parse_mode="Markdown")
                    except Exception:
                        pass  # Ignore edit errors

            # Final results
            msg = f"*{preset.upper()} Scan Complete*\n"
            msg += f"Screened: {processed} stocks\n"
            msg += f"Passed: {len(all_passed)}\n\n"

            if all_passed:
                msg += "*Top 10 Candidates:*\n"
                for j, stock in enumerate(all_passed[:10], 1):
                    symbol = stock.get("symbol", "N/A")
                    score = stock.get("score", 0)
                    price = stock.get("current_price", 0)
                    msg += f"{j}. *{symbol}* - Score: {score:.0f}"
                    if price:
                        msg += f" (${price:.2f})"
                    msg += "\n"
            else:
                msg += "_No stocks passed all filters._"

            await status_msg.edit_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Telegram scan error: {e}")
            try:
                await status_msg.edit_text(f"Scan failed: {str(e)[:100]}")
            except Exception:
                await update.message.reply_text(f"Scan failed: {str(e)[:100]}")

    async def _cmd_iv(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /iv command."""
        if not self._is_authorized(update.effective_user.id):
            return

        if not context.args:
            await update.message.reply_text("Usage: /iv SYMBOL\nExample: /iv NVDA")
            return

        symbol = context.args[0].upper()

        try:
            from app.services.data_fetcher.tastytrade import get_tastytrade_service

            service = get_tastytrade_service()
            if not service.is_available():
                await update.message.reply_text("TastyTrade not configured")
                return

            data = service.get_enhanced_options_data(symbol)

            if not data or data.get("iv_rank") is None:
                await update.message.reply_text(f"No IV data available for {symbol}")
                return

            msg = f"*{symbol} IV Metrics*\n\n"
            msg += f"IV Rank: *{data['iv_rank']:.1%}*\n"
            if data.get("iv_percentile"):
                msg += f"IV Percentile: {float(data['iv_percentile']):.1%}\n"
            if data.get("iv_30_day"):
                msg += f"IV 30-Day: {data['iv_30_day']:.1f}%\n"
            if data.get("hv_30_day"):
                msg += f"HV 30-Day: {data['hv_30_day']:.1f}%\n"
            if data.get("beta"):
                msg += f"Beta: {data['beta']:.2f}\n"

            # IV interpretation
            iv_rank = data["iv_rank"]
            if iv_rank < 0.20:
                msg += "\n_Low IV - Good time to buy options_"
            elif iv_rank < 0.40:
                msg += "\n_Moderate IV - Reasonable pricing_"
            elif iv_rank > 0.70:
                msg += "\n_High IV - Options are expensive_"

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Telegram IV error: {e}")
            await update.message.reply_text(f"Error: {str(e)[:100]}")

    async def _cmd_leaps(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /leaps command."""
        if not self._is_authorized(update.effective_user.id):
            return

        if not context.args:
            await update.message.reply_text("Usage: /leaps SYMBOL\nExample: /leaps AAPL")
            return

        symbol = context.args[0].upper()

        try:
            from app.services.data_fetcher.tastytrade import get_tastytrade_service

            service = get_tastytrade_service()
            if not service.is_available():
                await update.message.reply_text("TastyTrade not configured")
                return

            expirations = service.get_leaps_expirations(symbol)

            if not expirations:
                await update.message.reply_text(f"No LEAPS available for {symbol}")
                return

            msg = f"*{symbol} LEAPS Expirations*\n\n"
            for exp in expirations:
                from datetime import date
                dte = (exp - date.today()).days
                msg += f"- {exp.strftime('%b %d, %Y')} ({dte} days)\n"

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Telegram LEAPS error: {e}")
            await update.message.reply_text(f"Error: {str(e)[:100]}")

    async def _cmd_quote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /quote command."""
        if not self._is_authorized(update.effective_user.id):
            return

        if not context.args:
            await update.message.reply_text("Usage: /quote SYMBOL\nExample: /quote AAPL")
            return

        symbol = context.args[0].upper()

        try:
            from app.services.data_fetcher.fmp_service import fmp_service
            from app.services.data_fetcher.alpaca_service import alpaca_service

            info = fmp_service.get_stock_info(symbol)
            price = alpaca_service.get_current_price(symbol)

            if not info:
                await update.message.reply_text(f"Symbol {symbol} not found")
                return

            msg = f"*{symbol}* - {info.get('name', 'N/A')}\n\n"
            msg += f"Price: *${price:.2f}*\n" if price else ""
            msg += f"Sector: {info.get('sector', 'N/A')}\n"

            market_cap = info.get("market_cap", 0)
            if market_cap:
                if market_cap >= 1e12:
                    msg += f"Market Cap: ${market_cap/1e12:.2f}T\n"
                elif market_cap >= 1e9:
                    msg += f"Market Cap: ${market_cap/1e9:.2f}B\n"
                else:
                    msg += f"Market Cap: ${market_cap/1e6:.0f}M\n"

            if info.get("pe_ratio"):
                msg += f"P/E Ratio: {info['pe_ratio']:.1f}\n"
            if info.get("beta"):
                msg += f"Beta: {info['beta']:.2f}\n"

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Telegram quote error: {e}")
            await update.message.reply_text(f"Error: {str(e)[:100]}")

    async def _cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /watchlist command."""
        if not self._is_authorized(update.effective_user.id):
            return

        watchlists = {
            "tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
            "semis": ["NVDA", "AMD", "INTC", "AVGO", "QCOM", "MU", "AMAT"],
            "healthcare": ["UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY", "TMO"],
            "fintech": ["V", "MA", "PYPL", "SQ", "COIN", "SOFI", "AFRM"]
        }

        if not context.args:
            msg = "*Available Watchlists*\n\n"
            for name, symbols in watchlists.items():
                msg += f"/watchlist {name} - {', '.join(symbols[:3])}...\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

        name = context.args[0].lower()
        if name not in watchlists:
            await update.message.reply_text(f"Unknown watchlist: {name}")
            return

        symbols = watchlists[name]
        await update.message.reply_text(
            f"Scanning {name} watchlist ({len(symbols)} stocks)..."
        )

        try:
            from app.services.data_fetcher.tastytrade import get_tastytrade_service

            service = get_tastytrade_service()
            if service.is_available():
                metrics = service.get_market_metrics(symbols)

                msg = f"*{name.upper()} Watchlist*\n\n"
                for symbol in symbols:
                    m = metrics.get(symbol)
                    if m:
                        iv_rank = float(m.tw_implied_volatility_index_rank) if m.tw_implied_volatility_index_rank else None
                        msg += f"*{symbol}*"
                        if iv_rank is not None:
                            emoji = "" if iv_rank < 0.3 else "" if iv_rank > 0.7 else ""
                            msg += f" - IV: {iv_rank:.0%} {emoji}\n"
                        else:
                            msg += "\n"
                    else:
                        msg += f"*{symbol}* - No data\n"

                await update.message.reply_text(msg, parse_mode="Markdown")
            else:
                await update.message.reply_text("TastyTrade not configured for IV data")

        except Exception as e:
            logger.error(f"Telegram watchlist error: {e}")
            await update.message.reply_text(f"Error: {str(e)[:100]}")

    async def _cmd_mri(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mri command - Show Macro Risk Index."""
        if not self._is_authorized(update.effective_user.id):
            return

        try:
            from app.services.command_center import get_macro_signal_service

            service = get_macro_signal_service()
            mri = await service.calculate_mri()

            if not mri or mri.get('mri_score') is None:
                await update.message.reply_text("MRI data unavailable. Try again later.")
                return

            # Regime emoji
            regime_emoji = {
                'risk_on': '🟢',
                'transition': '🟡',
                'risk_off': '🔴'
            }

            regime = mri.get('regime', 'unknown')
            confidence_indicator = '⚠️' if mri.get('confidence_score', 100) < 50 else ''

            msg = f"*Macro Risk Index (MRI)* {confidence_indicator}\n\n"
            msg += f"Score: *{mri['mri_score']:.0f}* / 100\n"
            msg += f"Regime: {regime_emoji.get(regime, '⚪')} *{mri.get('regime_label', regime)}*\n"
            msg += f"Confidence: {mri.get('confidence_score', 0):.0f}%\n\n"

            if mri.get('shock_flag'):
                msg += "⚡ *SHOCK DETECTED* - Rapid change in last hour\n\n"

            # Show drivers
            drivers = mri.get('drivers', [])
            if drivers:
                msg += "*Top Drivers:*\n"
                for driver in drivers[:3]:
                    direction = '↑' if driver.get('direction') == 'risk_off' else '↓'
                    title = driver.get('title', 'Unknown')[:35]
                    contribution = driver.get('contribution_points', 0)
                    msg += f"  {direction} {title}: +{contribution:.1f}\n"

            # Show changes
            if mri.get('change_1h') is not None:
                msg += f"\n1h: {mri['change_1h']:+.1f}"
            if mri.get('change_24h') is not None:
                msg += f" | 24h: {mri['change_24h']:+.1f}"

            if mri.get('data_stale'):
                msg += "\n\n⚠️ _Data may be stale_"

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Telegram MRI error: {e}")
            await update.message.reply_text(f"Error fetching MRI: {str(e)[:100]}")

    async def _cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /macro command - Show macro signal summary."""
        if not self._is_authorized(update.effective_user.id):
            return

        try:
            from app.services.command_center import get_macro_signal_service, get_polymarket_service

            macro_service = get_macro_signal_service()
            polymarket_service = get_polymarket_service()

            # Get MRI
            mri = await macro_service.calculate_mri()

            # Get category aggregates
            aggregates = await polymarket_service.get_all_category_aggregates()

            # Get divergences
            divergences = await macro_service.detect_divergences()

            msg = "*Macro Signal Summary*\n\n"

            # MRI summary
            if mri and mri.get('mri_score') is not None:
                regime_emoji = {'risk_on': '🟢', 'transition': '🟡', 'risk_off': '🔴'}
                regime = mri.get('regime', 'unknown')
                msg += f"*MRI:* {mri['mri_score']:.0f} {regime_emoji.get(regime, '⚪')} {mri.get('regime_label', '')}\n\n"

            # Category breakdown
            msg += "*Categories:*\n"
            category_emojis = {
                'fed_policy': '🏛️',
                'recession': '📉',
                'elections': '🗳️',
                'trade': '🌐',
                'crypto': '₿'
            }

            for category, agg in aggregates.items():
                prob = agg.get('aggregate_probability')
                if prob is not None:
                    emoji = category_emojis.get(category, '📊')
                    confidence = agg.get('confidence_label', 'low')
                    conf_indicator = '✓' if confidence == 'high' else '~' if confidence == 'medium' else '?'
                    msg += f"  {emoji} {category.replace('_', ' ').title()}: {prob:.0f}% {conf_indicator}\n"

            # Divergences
            if divergences:
                msg += f"\n*Divergences Detected:* {len(divergences)}\n"
                for div in divergences[:2]:
                    div_type = div.get('type', 'unknown')
                    emoji = '📈' if 'bullish' in div_type else '📉'
                    cat = div.get('prediction_category', '').replace('_', ' ')
                    proxy = div.get('proxy_symbol', '')
                    msg += f"  {emoji} {cat} vs {proxy}\n"

            msg += "\n_Use /mri for detailed MRI info_"

            await update.message.reply_text(msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Telegram macro error: {e}")
            await update.message.reply_text(f"Error fetching macro data: {str(e)[:100]}")

    async def _cmd_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle unknown commands."""
        if not self._is_authorized(update.effective_user.id):
            return
        await update.message.reply_text("Unknown command. Type /help for available commands.")

    async def start(self):
        """Start the bot (non-blocking)."""
        if not self.application:
            logger.warning("Telegram bot not initialized")
            return

        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            self._running = True
            logger.info("Telegram bot started")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")

    async def stop(self):
        """Stop the bot."""
        if self.application and self._running:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                self._running = False
                logger.info("Telegram bot stopped")
            except Exception as e:
                logger.error(f"Error stopping Telegram bot: {e}")

    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running

    async def send_message(self, chat_id: str, message: str, parse_mode: str = "Markdown") -> bool:
        """
        Send a message to a specific chat.

        Args:
            chat_id: Telegram chat ID to send to
            message: Message text
            parse_mode: Parse mode (Markdown or HTML)

        Returns:
            True if sent successfully
        """
        if not self.application or not self._running:
            logger.warning("Telegram bot not running, cannot send message")
            return False

        try:
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode
            )
            logger.debug(f"Sent Telegram message to {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_alert_notification(self, chat_id: str, alert_name: str, symbol: str, message: str) -> bool:
        """
        Send an alert notification to Telegram.

        Args:
            chat_id: Telegram chat ID
            alert_name: Name of the alert
            symbol: Stock symbol
            message: Alert message

        Returns:
            True if sent successfully
        """
        formatted_message = (
            f"*ALERT: {alert_name}*\n\n"
            f"*{symbol}*\n"
            f"{message}\n\n"
            f"_Sent by LEAPS Trader_"
        )
        return await self.send_message(chat_id, formatted_message)


# Global instance
_telegram_bot: Optional[TelegramBotService] = None


def get_telegram_bot() -> TelegramBotService:
    """Get the global Telegram bot instance."""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = TelegramBotService()
    return _telegram_bot


def initialize_telegram_bot(bot_token: str, allowed_users: str = "") -> bool:
    """Initialize the global Telegram bot."""
    bot = get_telegram_bot()
    return bot.initialize(bot_token, allowed_users)
