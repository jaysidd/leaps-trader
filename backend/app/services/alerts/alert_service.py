"""
Dynamic Alert Service
Checks alert conditions and triggers notifications
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from loguru import logger
from sqlalchemy.orm import Session

from app.models.user_alert import UserAlert, AlertNotification, AlertType
from app.services.data_fetcher.fmp_service import fmp_service
from app.services.data_fetcher.alpaca_service import alpaca_service
from app.services.analysis.technical import TechnicalAnalysis
from app.services.analysis.options import OptionsAnalysis
from app.services.telegram_bot import get_telegram_bot
from app.config import get_settings


class AlertService:
    """
    Service for managing and checking dynamic alerts
    """

    def __init__(self):
        self.tech_analysis = TechnicalAnalysis()
        self.opt_analysis = OptionsAnalysis()
        self._settings = get_settings()

    def _send_telegram_notification(self, alert: UserAlert, message: str) -> bool:
        """
        Send alert notification via Telegram.

        Args:
            alert: The triggered alert
            message: Alert message

        Returns:
            True if sent successfully
        """
        try:
            # Get chat ID from allowed users (first user as default)
            allowed_users = self._settings.TELEGRAM_ALLOWED_USERS
            if not allowed_users:
                logger.warning("No Telegram users configured for alert notifications")
                return False

            # Use first allowed user as default recipient
            chat_ids = [uid.strip() for uid in allowed_users.split(",") if uid.strip()]
            if not chat_ids:
                return False

            telegram_bot = get_telegram_bot()
            if not telegram_bot.is_running():
                logger.warning("Telegram bot not running, cannot send alert")
                return False

            # Send to all allowed users
            sent_count = 0
            for chat_id in chat_ids:
                try:
                    # Run async send in sync context
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(
                            telegram_bot.send_alert_notification(
                                chat_id=chat_id,
                                alert_name=alert.name,
                                symbol=alert.symbol,
                                message=message
                            )
                        )
                        sent_count += 1
                    else:
                        result = loop.run_until_complete(
                            telegram_bot.send_alert_notification(
                                chat_id=chat_id,
                                alert_name=alert.name,
                                symbol=alert.symbol,
                                message=message
                            )
                        )
                        if result:
                            sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send Telegram notification to {chat_id}: {e}")

            return sent_count > 0

        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return False

    def check_alert(self, alert: UserAlert, db: Session) -> Optional[AlertNotification]:
        """
        Check if an alert's conditions are met

        Args:
            alert: UserAlert model instance
            db: Database session

        Returns:
            AlertNotification if triggered, None otherwise
        """
        if not alert.is_active:
            return None

        # Route based on scope
        if getattr(alert, 'alert_scope', 'ticker') == "macro":
            return self._check_macro_alert(alert, db)

        # Continue with ticker-level alert checking
        # Check if expired
        if alert.expires_at and datetime.now(alert.expires_at.tzinfo) > alert.expires_at:
            alert.is_active = False
            db.commit()
            return None

        try:
            symbol = alert.symbol
            if not symbol:
                return None

            # Get current data for the symbol
            stock_info = fmp_service.get_stock_info(symbol)
            if not stock_info:
                logger.warning(f"Alert {alert.id}: Could not get stock info for {symbol}")
                return None

            current_price = stock_info.get('current_price')

            # Check condition based on alert type
            triggered = False
            triggered_value = None
            message = ""

            if alert.alert_type == AlertType.IV_RANK_BELOW.value:
                triggered, triggered_value, message = self._check_iv_rank_below(
                    symbol, alert.threshold_value, current_price
                )

            elif alert.alert_type == AlertType.IV_RANK_ABOVE.value:
                triggered, triggered_value, message = self._check_iv_rank_above(
                    symbol, alert.threshold_value, current_price
                )

            elif alert.alert_type == AlertType.PRICE_ABOVE.value:
                if current_price and current_price > alert.threshold_value:
                    triggered = True
                    triggered_value = current_price
                    message = f"{symbol} price ${current_price:.2f} crossed above ${alert.threshold_value:.2f}"

            elif alert.alert_type == AlertType.PRICE_BELOW.value:
                if current_price and current_price < alert.threshold_value:
                    triggered = True
                    triggered_value = current_price
                    message = f"{symbol} price ${current_price:.2f} dropped below ${alert.threshold_value:.2f}"

            elif alert.alert_type == AlertType.RSI_OVERSOLD.value:
                triggered, triggered_value, message = self._check_rsi(
                    symbol, alert.threshold_value or 30, "below"
                )

            elif alert.alert_type == AlertType.RSI_OVERBOUGHT.value:
                triggered, triggered_value, message = self._check_rsi(
                    symbol, alert.threshold_value or 70, "above"
                )

            elif alert.alert_type == AlertType.PRICE_CROSS_SMA.value:
                triggered, triggered_value, message = self._check_sma_cross(
                    symbol, alert.sma_period or 200, current_price
                )

            elif alert.alert_type == AlertType.EARNINGS_APPROACHING.value:
                triggered, triggered_value, message = self._check_earnings(
                    symbol, int(alert.threshold_value or 14)
                )

            # Update last checked
            alert.last_checked_at = datetime.utcnow()

            if triggered:
                # Create notification
                channels_sent = []
                notification = AlertNotification(
                    alert_id=alert.id,
                    alert_name=alert.name,
                    symbol=symbol,
                    alert_type=alert.alert_type,
                    triggered_value=triggered_value,
                    threshold_value=alert.threshold_value,
                    message=message,
                    channels_sent=channels_sent
                )

                # Update alert
                alert.times_triggered += 1
                alert.last_triggered_at = datetime.utcnow()
                alert.last_triggered_value = triggered_value

                # Send notifications based on configured channels
                notification_channels = alert.notification_channels or ["app"]

                if "telegram" in notification_channels:
                    if self._send_telegram_notification(alert, message):
                        channels_sent.append("telegram")
                        logger.info(f"Telegram notification sent for alert: {alert.name}")

                # App notification is always recorded
                if "app" in notification_channels:
                    channels_sent.append("app")

                notification.channels_sent = channels_sent

                # Deactivate if frequency is 'once'
                if alert.frequency == "once":
                    alert.is_active = False

                db.add(notification)
                db.commit()

                logger.info(f"Alert triggered: {alert.name} for {symbol} - {message}")
                return notification

            db.commit()
            return None

        except Exception as e:
            logger.error(f"Error checking alert {alert.id}: {e}")
            return None

    def _check_iv_rank_below(
        self, symbol: str, threshold: float, current_price: float
    ) -> tuple[bool, float, str]:
        """Check if IV Rank dropped below threshold"""
        try:
            options_data = alpaca_service.get_options_chain(symbol)
            if not options_data or 'calls' not in options_data:
                return False, None, ""

            enhanced_data = self.opt_analysis.get_enhanced_iv_data(symbol)
            iv_rank = enhanced_data.get('iv_rank') if enhanced_data else None

            if iv_rank is not None and iv_rank < threshold:
                return True, iv_rank, f"{symbol} IV Rank dropped to {iv_rank:.1f}% (below {threshold}%)"

            return False, iv_rank, ""

        except Exception as e:
            logger.error(f"Error checking IV rank for {symbol}: {e}")
            return False, None, ""

    def _check_iv_rank_above(
        self, symbol: str, threshold: float, current_price: float
    ) -> tuple[bool, float, str]:
        """Check if IV Rank rose above threshold"""
        try:
            enhanced_data = self.opt_analysis.get_enhanced_iv_data(symbol)
            iv_rank = enhanced_data.get('iv_rank') if enhanced_data else None

            if iv_rank is not None and iv_rank > threshold:
                return True, iv_rank, f"{symbol} IV Rank rose to {iv_rank:.1f}% (above {threshold}%)"

            return False, iv_rank, ""

        except Exception as e:
            logger.error(f"Error checking IV rank for {symbol}: {e}")
            return False, None, ""

    def _check_rsi(
        self, symbol: str, threshold: float, direction: str
    ) -> tuple[bool, float, str]:
        """Check RSI conditions"""
        try:
            price_data = alpaca_service.get_historical_prices(symbol, period="3mo")
            if price_data is None or price_data.empty:
                return False, None, ""

            price_data = self.tech_analysis.calculate_all_indicators(price_data)
            indicators = self.tech_analysis.get_latest_indicators(price_data)

            rsi = indicators.get('rsi_14')
            if rsi is None:
                return False, None, ""

            if direction == "below" and rsi < threshold:
                return True, rsi, f"{symbol} RSI dropped to {rsi:.1f} (oversold below {threshold})"
            elif direction == "above" and rsi > threshold:
                return True, rsi, f"{symbol} RSI rose to {rsi:.1f} (overbought above {threshold})"

            return False, rsi, ""

        except Exception as e:
            logger.error(f"Error checking RSI for {symbol}: {e}")
            return False, None, ""

    def _check_sma_cross(
        self, symbol: str, sma_period: int, current_price: float
    ) -> tuple[bool, float, str]:
        """Check if price crossed above SMA"""
        try:
            price_data = alpaca_service.get_historical_prices(symbol, period="1y")
            if price_data is None or price_data.empty:
                return False, None, ""

            price_data = self.tech_analysis.calculate_all_indicators(price_data)
            indicators = self.tech_analysis.get_latest_indicators(price_data)

            sma_key = f'sma_{sma_period}'
            sma_value = indicators.get(sma_key)

            if sma_value is None:
                return False, None, ""

            # Check if price just crossed above SMA
            # We look at previous close to detect crossover
            if len(price_data) >= 2:
                prev_close = price_data['close'].iloc[-2]
                prev_sma = price_data[sma_key].iloc[-2] if sma_key in price_data.columns else None

                if prev_sma and prev_close < prev_sma and current_price > sma_value:
                    return True, current_price, f"{symbol} crossed above SMA{sma_period} (${current_price:.2f} > ${sma_value:.2f})"

            return False, current_price, ""

        except Exception as e:
            logger.error(f"Error checking SMA cross for {symbol}: {e}")
            return False, None, ""

    def _check_earnings(
        self, symbol: str, days_threshold: int
    ) -> tuple[bool, float, str]:
        """Check if earnings are approaching within threshold days"""
        try:
            # This would require an earnings calendar API
            # For now, return False - can be enhanced later
            return False, None, ""

        except Exception as e:
            logger.error(f"Error checking earnings for {symbol}: {e}")
            return False, None, ""

    # -------------------------------------------------------------------------
    # MACRO ALERT HANDLING
    # -------------------------------------------------------------------------

    def _check_macro_alert(self, alert: UserAlert, db: Session) -> Optional[AlertNotification]:
        """
        Handle macro-specific alert types.

        Args:
            alert: UserAlert model instance with alert_scope="macro"
            db: Database session

        Returns:
            AlertNotification if triggered, None otherwise
        """
        try:
            from app.services.command_center import get_macro_signal_service

            # Deduplication check
            if not self._passes_deduplication(alert):
                return None

            # Cooldown check
            if not self._passes_cooldown(alert):
                return None

            # Check staleness - suppress alerts if data is stale
            macro_service = get_macro_signal_service()
            staleness = macro_service._check_staleness()
            if staleness.get('suppress_alerts'):
                logger.info(f"Suppressing macro alert {alert.id} - data stale ({staleness.get('stale_minutes')} min)")
                return None

            params = alert.alert_params or {}
            triggered = False
            triggered_value = None
            message = ""

            if alert.alert_type == AlertType.MRI_REGIME_CHANGE.value:
                triggered, triggered_value, message = self._check_mri_regime(alert, params, macro_service)

            elif alert.alert_type == AlertType.MACRO_NARRATIVE_MOMENTUM.value:
                triggered, triggered_value, message = self._check_narrative_momentum(alert, params, macro_service)

            elif alert.alert_type == AlertType.MACRO_DIVERGENCE_BULLISH.value:
                triggered, triggered_value, message = self._check_macro_divergence(alert, params, macro_service, "bullish")

            elif alert.alert_type == AlertType.MACRO_DIVERGENCE_BEARISH.value:
                triggered, triggered_value, message = self._check_macro_divergence(alert, params, macro_service, "bearish")

            # Catalyst alerts (Macro Intelligence)
            elif alert.alert_type == AlertType.CATALYST_LIQUIDITY_REGIME_CHANGE.value:
                triggered, triggered_value, message = self._check_liquidity_regime(alert, params, db)

            # Update last checked
            alert.last_checked_at = datetime.utcnow()

            if triggered:
                # Suppress low-severity alerts when MRI confidence is low
                severity = getattr(alert, 'severity', 'warning')
                cached_mri = macro_service.get_cached_mri()
                if severity == "info" and cached_mri and cached_mri.get('confidence_score', 100) < 40:
                    logger.info(f"Suppressing low-severity macro alert {alert.id} - MRI confidence low")
                    db.commit()
                    return None

                return self._create_macro_notification(alert, triggered_value, message, db)

            db.commit()
            return None

        except Exception as e:
            logger.error(f"Error checking macro alert {alert.id}: {e}")
            return None

    def _passes_deduplication(self, alert: UserAlert) -> bool:
        """Check dedupe key to prevent duplicate alerts."""
        dedupe_key = getattr(alert, 'dedupe_key', None)
        if not dedupe_key:
            return True

        # Check if same dedupe_key fired within window
        window_minutes = 60  # Configurable
        last_dedupe = getattr(alert, 'last_dedupe_at', None)
        if last_dedupe:
            elapsed = (datetime.utcnow() - last_dedupe).total_seconds() / 60
            if elapsed < window_minutes:
                return False
        return True

    def _passes_cooldown(self, alert: UserAlert) -> bool:
        """Check cooldown period since last trigger."""
        cooldown = getattr(alert, 'cooldown_minutes', 60) or 60
        if alert.last_triggered_at:
            elapsed = (datetime.utcnow() - alert.last_triggered_at).total_seconds() / 60
            if elapsed < cooldown:
                return False
        return True

    def _check_mri_regime(
        self,
        alert: UserAlert,
        params: Dict,
        macro_service
    ) -> tuple[bool, float, str]:
        """Check for MRI regime change."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Use cached MRI if available
                mri = macro_service.get_cached_mri()
                if not mri:
                    return False, None, ""
            else:
                mri = loop.run_until_complete(macro_service.calculate_mri())

            if not mri or mri.get('mri_score') is None:
                return False, None, ""

            mri_score = mri['mri_score']
            regime = mri['regime']

            # Check thresholds
            low_threshold = params.get('mri_threshold_low', 33)
            high_threshold = params.get('mri_threshold_high', 67)

            # Check for regime transition
            if mri_score <= low_threshold and regime == 'risk_on':
                return True, mri_score, f"MRI entered Risk-On regime ({mri_score:.0f} <= {low_threshold})"
            elif mri_score >= high_threshold and regime == 'risk_off':
                return True, mri_score, f"MRI entered Risk-Off regime ({mri_score:.0f} >= {high_threshold})"

            return False, mri_score, ""

        except Exception as e:
            logger.error(f"Error checking MRI regime: {e}")
            return False, None, ""

    def _check_liquidity_regime(
        self,
        alert: UserAlert,
        params: Dict,
        db: Session
    ) -> tuple[bool, float, str]:
        """
        Check for liquidity regime change.

        Params:
            threshold_low: Score below which is "expanding" (default 40)
            threshold_high: Score above which is "contracting" (default 60)
            persistence_checks: Number of consecutive checks required (default 2)
        """
        try:
            import asyncio
            from app.services.command_center import get_catalyst_service

            catalyst_service = get_catalyst_service()

            # Get current liquidity data
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in sync context - this will be called from scheduler
                # which is async, so we should be fine
                liquidity = asyncio.ensure_future(catalyst_service.get_liquidity(db))
                # For sync context, we'll skip
                logger.debug("Skipping liquidity alert check in sync context")
                return False, None, ""
            else:
                liquidity = loop.run_until_complete(catalyst_service.get_liquidity(db))

            if not liquidity or liquidity.get('score') is None:
                return False, None, ""

            # Check for staleness - suppress alerts if data is stale
            if liquidity.get('data_stale'):
                logger.info(f"Suppressing liquidity alert {alert.id} - data stale")
                return False, None, ""

            score = liquidity['score']
            regime = liquidity.get('regime', 'transition')

            # Get thresholds from params
            low_threshold = params.get('threshold_low', 40)
            high_threshold = params.get('threshold_high', 60)

            # Check for regime transition
            if score <= low_threshold and regime == 'risk_on':
                return True, score, f"Liquidity regime entered Expanding ({score:.0f} <= {low_threshold}) - Risk-On conditions"
            elif score >= high_threshold and regime == 'risk_off':
                return True, score, f"Liquidity regime entered Contracting ({score:.0f} >= {high_threshold}) - Risk-Off conditions"

            return False, score, ""

        except Exception as e:
            logger.error(f"Error checking liquidity regime: {e}")
            return False, None, ""

    def _check_narrative_momentum(
        self,
        alert: UserAlert,
        params: Dict,
        macro_service
    ) -> tuple[bool, float, str]:
        """Check for narrative momentum in a category."""
        try:
            import asyncio

            category = params.get('category', 'recession')
            threshold = params.get('threshold_pct', 10.0)

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in sync context, skip for now
                return False, None, ""

            momentum = loop.run_until_complete(
                macro_service.detect_narrative_momentum(category, threshold)
            )

            if momentum and momentum.get('markets_moving', 0) > 0:
                direction = momentum.get('overall_direction', 'neutral')
                total_change = momentum.get('total_change', 0)
                return True, abs(total_change), f"{category.replace('_', ' ').title()} narrative shifted {direction} ({total_change:+.1f}% aggregate)"

            return False, None, ""

        except Exception as e:
            logger.error(f"Error checking narrative momentum: {e}")
            return False, None, ""

    def _check_macro_divergence(
        self,
        alert: UserAlert,
        params: Dict,
        macro_service,
        divergence_type: str
    ) -> tuple[bool, float, str]:
        """Check for macro divergence."""
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in sync context, skip for now
                return False, None, ""

            divergences = loop.run_until_complete(macro_service.detect_divergences())

            target_type = f"{divergence_type}_divergence"
            for div in divergences:
                if div.get('type') == target_type:
                    proxy = div.get('proxy_symbol', 'Unknown')
                    category = div.get('prediction_category', 'Unknown')
                    return True, div.get('prediction_change'), f"{divergence_type.title()} divergence: {category} vs {proxy} - {div.get('interpretation', '')}"

            return False, None, ""

        except Exception as e:
            logger.error(f"Error checking macro divergence: {e}")
            return False, None, ""

    def _create_macro_notification(
        self,
        alert: UserAlert,
        triggered_value: float,
        message: str,
        db: Session
    ) -> AlertNotification:
        """Create notification for macro alert."""
        channels_sent = []
        notification = AlertNotification(
            alert_id=alert.id,
            alert_name=alert.name,
            symbol="MACRO",  # Use MACRO as placeholder for macro alerts
            alert_type=alert.alert_type,
            triggered_value=triggered_value,
            threshold_value=alert.threshold_value,
            message=message,
            channels_sent=channels_sent
        )

        # Update alert
        alert.times_triggered += 1
        alert.last_triggered_at = datetime.utcnow()
        alert.last_triggered_value = triggered_value

        # Update dedupe timestamp
        if hasattr(alert, 'last_dedupe_at'):
            alert.last_dedupe_at = datetime.utcnow()

        # Send notifications based on configured channels
        notification_channels = alert.notification_channels or ["app"]

        if "telegram" in notification_channels:
            if self._send_telegram_notification(alert, message):
                channels_sent.append("telegram")
                logger.info(f"Telegram notification sent for macro alert: {alert.name}")

        # App notification is always recorded
        if "app" in notification_channels:
            channels_sent.append("app")

        notification.channels_sent = channels_sent

        # Deactivate if frequency is 'once'
        if alert.frequency == "once":
            alert.is_active = False

        db.add(notification)
        db.commit()

        logger.info(f"Macro alert triggered: {alert.name} - {message}")
        return notification

    def check_all_alerts(self, db: Session) -> List[AlertNotification]:
        """
        Check all active alerts

        Args:
            db: Database session

        Returns:
            List of triggered notifications
        """
        triggered = []

        # Get all active alerts
        alerts = db.query(UserAlert).filter(UserAlert.is_active == True).all()

        for alert in alerts:
            notification = self.check_alert(alert, db)
            if notification:
                triggered.append(notification)

        return triggered

    def get_alert_type_description(self, alert_type: str) -> str:
        """Get human-readable description of alert type"""
        descriptions = {
            # Ticker alerts
            AlertType.IV_RANK_BELOW.value: "IV Rank drops below threshold",
            AlertType.IV_RANK_ABOVE.value: "IV Rank rises above threshold",
            AlertType.PRICE_ABOVE.value: "Price crosses above level",
            AlertType.PRICE_BELOW.value: "Price drops below level",
            AlertType.PRICE_CROSS_SMA.value: "Price crosses above SMA",
            AlertType.RSI_OVERSOLD.value: "RSI indicates oversold",
            AlertType.RSI_OVERBOUGHT.value: "RSI indicates overbought",
            AlertType.SCREENING_MATCH.value: "Stock passes screening criteria",
            AlertType.EARNINGS_APPROACHING.value: "Earnings approaching",
            AlertType.LEAPS_AVAILABLE.value: "New LEAPS expiration available",
            # Macro alerts
            AlertType.MRI_REGIME_CHANGE.value: "MRI regime transition (Risk-On/Off)",
            AlertType.MACRO_NARRATIVE_MOMENTUM.value: "Significant shift in prediction market category",
            AlertType.MACRO_DIVERGENCE_BULLISH.value: "Bullish divergence between predictions and price",
            AlertType.MACRO_DIVERGENCE_BEARISH.value: "Bearish divergence between predictions and price",
        }
        return descriptions.get(alert_type, alert_type)


# Singleton instance
alert_service = AlertService()
