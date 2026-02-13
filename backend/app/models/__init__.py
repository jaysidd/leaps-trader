"""
SQLAlchemy models

DOC UPDATE: Adding/removing a model here? Also update:
  ARCHITECTURE.md → "Database Models" table + Changelog
"""
from app.models.stock import Stock
from app.models.price_history import PriceHistory
from app.models.fundamental import Fundamental
from app.models.option import OptionData
from app.models.technical_indicator import TechnicalIndicator
from app.models.screening_result import ScreeningResult
from app.models.watchlist import Watchlist, WatchlistItem
from app.models.settings import AppSettings, ApiKeyStatus
from app.models.webhook_alert import WebhookAlert
from app.models.user_alert import UserAlert, AlertNotification
from app.models.signal_queue import SignalQueue
from app.models.trading_signal import TradingSignal
from app.models.saved_scan import SavedScanResult, SavedScanMetadata
from app.models.broker_connection import BrokerConnection, PortfolioPosition, PortfolioHistory
from app.models.polymarket_snapshot import PolymarketMarketSnapshot
from app.models.mri_snapshot import MRISnapshot
from app.models.sector_macro_mapping import SectorMacroMapping, TickerMacroOverride
from app.models.catalyst_snapshot import CatalystSnapshot
from app.models.ticker_catalyst_snapshot import TickerCatalystSnapshot
from app.models.event_calendar import EventCalendar
from app.models.bot_config import BotConfiguration
from app.models.executed_trade import ExecutedTrade
from app.models.bot_state import BotState
from app.models.daily_bot_performance import DailyBotPerformance
from app.models.backtest_result import BacktestResult
from app.models.autopilot_log import AutopilotLog

__all__ = [
    "Stock",
    "PriceHistory",
    "Fundamental",
    "OptionData",
    "TechnicalIndicator",
    "ScreeningResult",
    "Watchlist",
    "WatchlistItem",
    "AppSettings",
    "ApiKeyStatus",
    "WebhookAlert",
    "UserAlert",
    "AlertNotification",
    "SignalQueue",
    "TradingSignal",
    "SavedScanResult",
    "SavedScanMetadata",
    "BrokerConnection",
    "PortfolioPosition",
    "PortfolioHistory",
    "PolymarketMarketSnapshot",
    "MRISnapshot",
    "SectorMacroMapping",
    "TickerMacroOverride",
    "CatalystSnapshot",
    "TickerCatalystSnapshot",
    "EventCalendar",
    "BotConfiguration",
    "ExecutedTrade",
    "BotState",
    "DailyBotPerformance",
    "BacktestResult",
    "AutopilotLog",
]
