"""
Shared fixtures for trading pipeline tests.

All mock objects use types.SimpleNamespace so attribute access works
identically to SQLAlchemy model instances (obj.symbol, obj.status, etc.)
without requiring a real database connection.
"""
import types
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Enum value constants (mirror the real model enums)
# ---------------------------------------------------------------------------

# BotStatus
BOT_STOPPED = "stopped"
BOT_RUNNING = "running"
BOT_PAUSED = "paused"
BOT_HALTED = "halted"

# CircuitBreakerLevel
CB_NONE = "none"
CB_WARNING = "warning"
CB_PAUSED = "paused"
CB_HALTED = "halted"

# ExecutionMode
EXEC_SIGNAL_ONLY = "signal_only"
EXEC_SEMI_AUTO = "semi_auto"
EXEC_FULL_AUTO = "full_auto"

# SizingMode
SIZE_FIXED_DOLLAR = "fixed_dollar"
SIZE_PCT_PORTFOLIO = "pct_portfolio"
SIZE_RISK_BASED = "risk_based"

# TradeStatus
TS_PENDING_ENTRY = "pending_entry"
TS_PENDING_APPROVAL = "pending_approval"
TS_OPEN = "open"
TS_PENDING_EXIT = "pending_exit"
TS_CLOSED = "closed"
TS_CANCELLED = "cancelled"
TS_ERROR = "error"


# ---------------------------------------------------------------------------
# Factory functions — return SimpleNamespace objects with safe defaults
# ---------------------------------------------------------------------------

def make_bot_config(**overrides):
    """Create a BotConfiguration-like object with safe defaults."""
    defaults = dict(
        id=1,
        execution_mode=EXEC_FULL_AUTO,
        paper_mode=True,
        # Per-trade limits
        max_per_stock_trade=500.0,
        max_per_options_trade=300.0,
        sizing_mode=SIZE_FIXED_DOLLAR,
        risk_pct_per_trade=1.0,
        # Daily limits
        max_daily_loss=500.0,
        max_trades_per_day=10,
        max_concurrent_positions=5,
        # Portfolio limits
        max_portfolio_allocation_pct=10.0,
        max_total_invested_pct=80.0,
        # Exit rules
        default_take_profit_pct=20.0,
        default_stop_loss_pct=10.0,
        trailing_stop_enabled=False,
        trailing_stop_pct=5.0,
        close_positions_eod=False,
        eod_close_minutes_before=5,
        leaps_roll_alert_dte=60,
        # Signal filters
        min_confidence_to_execute=75.0,
        require_ai_analysis=False,
        min_ai_conviction=7.0,
        enabled_strategies=["orb_breakout", "vwap_pullback", "range_breakout"],
        # Circuit breakers
        circuit_breaker_warn_pct=3.0,
        circuit_breaker_pause_pct=5.0,
        circuit_breaker_halt_pct=10.0,
        auto_resume_next_day=True,
        # Options
        max_bid_ask_spread_pct=15.0,
        min_option_open_interest=100,
        min_option_delta=0.30,
        options_order_type="limit",
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def make_bot_state(**overrides):
    """Create a BotState-like object with safe defaults."""
    defaults = dict(
        id=1,
        status=BOT_RUNNING,
        daily_pl=0.0,
        daily_trades_count=0,
        daily_wins=0,
        daily_losses=0,
        daily_start_equity=100000.0,
        circuit_breaker_level=CB_NONE,
        circuit_breaker_triggered_at=None,
        circuit_breaker_reason=None,
        open_positions_count=0,
        open_stock_positions=0,
        open_option_positions=0,
        last_health_check=None,
        last_signal_processed_at=None,
        last_error=None,
        last_error_at=None,
        consecutive_errors=0,
        started_at=None,
        updated_at=None,
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def make_signal(**overrides):
    """Create a TradingSignal-like object with safe defaults."""
    defaults = dict(
        id=1,
        symbol="AAPL",
        name="Apple Inc.",
        timeframe="5m",
        strategy="orb_breakout_long",
        direction="buy",
        confidence_score=85.0,
        entry_price=150.0,
        entry_zone_low=149.0,
        entry_zone_high=151.0,
        stop_loss=145.0,
        target_1=160.0,
        target_2=170.0,
        risk_reward_ratio=2.0,
        ai_deep_analysis=None,
        ai_deep_analysis_at=None,
        status="active",
        validation_status=None,
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def make_trade(**overrides):
    """Create an ExecutedTrade-like object with safe defaults."""
    defaults = dict(
        id=1,
        signal_id=1,
        symbol="AAPL",
        asset_type="stock",
        direction="buy",
        option_symbol=None,
        option_type=None,
        option_strike=None,
        option_expiry=None,
        entry_order_id="order-123",
        entry_price=150.0,
        entry_filled_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        quantity=10,
        notional=1500.0,
        is_fractional=False,
        take_profit_price=165.0,
        stop_loss_price=140.0,
        trailing_stop_pct=None,
        trailing_stop_high_water=None,
        tp_order_id=None,
        sl_order_id=None,
        exit_order_id=None,
        exit_price=None,
        exit_filled_at=None,
        exit_reason=None,
        realized_pl=None,
        realized_pl_pct=None,
        fees=0.0,
        status=TS_OPEN,
        execution_mode=EXEC_FULL_AUTO,
        hold_duration_minutes=None,
        notes=None,
        created_at=datetime(2025, 1, 15, 9, 30, 0, tzinfo=timezone.utc),
        updated_at=None,
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def make_account(**overrides):
    """Create an Alpaca account dict with safe defaults."""
    defaults = dict(
        equity=100000.0,
        buying_power=50000.0,
        long_market_value=30000.0,
        cash=50000.0,
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """
    MagicMock SQLAlchemy Session.

    Supports query().filter().first()/all()/count() call chains.
    By default returns None/empty to simulate no matching records.
    """
    db = MagicMock()
    # Set up the chain: db.query().filter().first() -> None
    query_mock = MagicMock()
    filter_mock = MagicMock()
    filter_mock.first.return_value = None
    filter_mock.all.return_value = []
    filter_mock.count.return_value = 0
    # filter() can be called multiple times (chained)
    filter_mock.filter.return_value = filter_mock
    query_mock.filter.return_value = filter_mock
    db.query.return_value = query_mock
    return db


@pytest.fixture
def mock_trading_service():
    """MagicMock for AlpacaTradingService."""
    svc = MagicMock()
    svc.get_position.return_value = None
    svc.get_order.return_value = None
    svc.get_all_positions.return_value = []
    svc.get_clock.return_value = {"is_open": True, "next_close": "2025-01-15T16:00:00-05:00"}
    return svc


@pytest.fixture
def mock_data_service():
    """MagicMock for AlpacaService (data service)."""
    svc = MagicMock()
    svc.get_current_price.return_value = 150.0
    return svc
