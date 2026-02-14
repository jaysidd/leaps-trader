"""
Tests for RiskGateway — the 16-point pre-execution risk check.

These are P0 (must-pass) tests that prevent capital loss by ensuring
the risk gateway correctly approves or rejects trades under various
conditions: bot status, market hours, daily limits, position limits,
buying power, confidence filters, AI checks, strategy filters,
duplicate detection, and option-specific quality checks.
"""
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

from app.services.trading.risk_gateway import RiskGateway
from app.models.bot_state import BotStatus, CircuitBreakerLevel
from app.models.executed_trade import TradeStatus

from tests.trading.conftest import (
    make_bot_config, make_bot_state, make_signal, make_trade, make_account,
    BOT_RUNNING, BOT_STOPPED, BOT_PAUSED,
    CB_NONE, CB_WARNING, CB_PAUSED, CB_HALTED,
    TS_OPEN,
)


# =====================================================================
# 1. Happy path — all checks pass
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 15:00 UTC = 10:00 AM ET
def test_all_checks_pass_stock(mock_db):
    """All risk checks pass for a stock trade during market hours."""
    gw = RiskGateway(mock_db)
    signal = make_signal()
    config = make_bot_config()
    state = make_bot_state()
    account = make_account()

    result = gw.check_trade(signal, config, state, account, asset_type="stock")

    assert result.approved is True
    assert result.reason == ""


# =====================================================================
# 2-3. Bot status checks
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_bot_not_running_rejects(mock_db):
    """Bot status is STOPPED -> trade rejected with [Bot status] reason."""
    gw = RiskGateway(mock_db)
    state = make_bot_state(status=BOT_STOPPED)

    result = gw.check_trade(
        make_signal(), make_bot_config(), state, make_account(),
    )

    assert result.approved is False
    assert "[Bot status]" in result.reason


@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_skip_bot_status_check_manual(mock_db):
    """skip_bot_status_check=True bypasses bot status and circuit breaker checks."""
    gw = RiskGateway(mock_db)
    state = make_bot_state(status=BOT_STOPPED, circuit_breaker_level=CB_PAUSED)

    result = gw.check_trade(
        make_signal(), make_bot_config(), state, make_account(),
        skip_bot_status_check=True,
    )

    assert result.approved is True


# =====================================================================
# 4-5. Circuit breaker checks
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_circuit_breaker_paused_rejects(mock_db):
    """Circuit breaker at PAUSED level rejects new trades."""
    gw = RiskGateway(mock_db)
    state = make_bot_state(
        circuit_breaker_level=CB_PAUSED,
        circuit_breaker_reason="Drawdown exceeded 5%",
    )

    result = gw.check_trade(
        make_signal(), make_bot_config(), state, make_account(),
    )

    assert result.approved is False
    assert "[Circuit breaker]" in result.reason


@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_circuit_breaker_warning_passes_with_warning(mock_db):
    """Circuit breaker at WARNING level approves but adds a warning."""
    gw = RiskGateway(mock_db)
    state = make_bot_state(
        circuit_breaker_level=CB_WARNING,
        circuit_breaker_reason="Approaching daily loss limit",
    )

    result = gw.check_trade(
        make_signal(), make_bot_config(), state, make_account(),
    )

    assert result.approved is True
    assert len(result.warnings) >= 1
    assert any("Circuit breaker WARNING" in w for w in result.warnings)


# =====================================================================
# 6-8. Market hours checks
# =====================================================================

@freeze_time("2025-01-18 15:00:00")  # Saturday 10:00 AM ET
def test_market_closed_weekend(mock_db):
    """Saturday -> market closed, trade rejected."""
    gw = RiskGateway(mock_db)

    result = gw.check_trade(
        make_signal(), make_bot_config(), make_bot_state(), make_account(),
    )

    assert result.approved is False
    assert "Market closed" in result.reason


@freeze_time("2025-01-16 01:00:00")  # 8:00 PM ET (next day UTC)
def test_market_closed_after_hours(mock_db):
    """Weekday 8 PM ET -> outside trading hours, rejected."""
    gw = RiskGateway(mock_db)

    result = gw.check_trade(
        make_signal(), make_bot_config(), make_bot_state(), make_account(),
    )

    assert result.approved is False
    assert "Market closed" in result.reason


@freeze_time("2025-01-15 15:30:00")  # 10:30 AM ET
def test_market_open_hours_passes(mock_db):
    """Weekday 10:30 AM ET -> market open, passes market hours check."""
    gw = RiskGateway(mock_db)

    result = gw.check_trade(
        make_signal(), make_bot_config(), make_bot_state(), make_account(),
    )

    assert result.approved is True


# =====================================================================
# 9-10. Daily trade count checks
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_daily_trade_limit_reached(mock_db):
    """daily_trades_count >= max_trades_per_day -> rejected."""
    gw = RiskGateway(mock_db)
    state = make_bot_state(daily_trades_count=10)
    config = make_bot_config(max_trades_per_day=10)

    result = gw.check_trade(make_signal(), config, state, make_account())

    assert result.approved is False
    assert "[Daily trade count]" in result.reason


@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_daily_trade_approaching_limit_warning(mock_db):
    """2 trades remaining -> approved with warning."""
    gw = RiskGateway(mock_db)
    state = make_bot_state(daily_trades_count=8)
    config = make_bot_config(max_trades_per_day=10)

    result = gw.check_trade(make_signal(), config, state, make_account())

    assert result.approved is True
    assert any("remaining" in w for w in result.warnings)


# =====================================================================
# 11. Daily loss limit
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_daily_loss_limit_reached(mock_db):
    """daily_pl <= -max_daily_loss -> rejected."""
    gw = RiskGateway(mock_db)
    state = make_bot_state(daily_pl=-500.0)
    config = make_bot_config(max_daily_loss=500.0)

    result = gw.check_trade(make_signal(), config, state, make_account())

    assert result.approved is False
    assert "[Daily loss limit]" in result.reason


# =====================================================================
# 12. Concurrent positions
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_concurrent_positions_limit(mock_db):
    """open_positions_count >= max_concurrent_positions -> rejected."""
    gw = RiskGateway(mock_db)
    state = make_bot_state(open_positions_count=5)
    config = make_bot_config(max_concurrent_positions=5)

    result = gw.check_trade(make_signal(), config, state, make_account())

    assert result.approved is False
    assert "[Concurrent positions]" in result.reason


# =====================================================================
# 13. Buying power
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_insufficient_buying_power(mock_db):
    """buying_power < max_per_stock_trade -> rejected."""
    gw = RiskGateway(mock_db)
    account = make_account(buying_power=100.0)
    config = make_bot_config(max_per_stock_trade=500.0)

    result = gw.check_trade(make_signal(), config, make_bot_state(), account)

    assert result.approved is False
    assert "[Buying power]" in result.reason


# =====================================================================
# 14. Portfolio allocation
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_portfolio_allocation_exceeded(mock_db):
    """Trade > max_portfolio_allocation_pct of equity -> rejected."""
    gw = RiskGateway(mock_db)
    # max_per_stock_trade=5000, equity=10000 -> allocation=50% > max 10%
    config = make_bot_config(max_per_stock_trade=5000.0, max_portfolio_allocation_pct=10.0)
    account = make_account(equity=10000.0, buying_power=10000.0)

    result = gw.check_trade(make_signal(), config, make_bot_state(), account)

    assert result.approved is False
    assert "[Portfolio allocation]" in result.reason


# =====================================================================
# 15. Total invested
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_total_invested_exceeded(mock_db):
    """long_market_value/equity >= max_total_invested_pct -> rejected."""
    gw = RiskGateway(mock_db)
    # long_market_value=85000, equity=100000 -> 85% >= 80%
    account = make_account(equity=100000.0, buying_power=50000.0, long_market_value=85000.0)
    config = make_bot_config(max_total_invested_pct=80.0)

    result = gw.check_trade(make_signal(), config, make_bot_state(), account)

    assert result.approved is False
    assert "[Total invested]" in result.reason


# =====================================================================
# 16. Confidence filter
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_low_confidence_rejected(mock_db):
    """Signal confidence 50 < minimum 75 -> rejected."""
    gw = RiskGateway(mock_db)
    signal = make_signal(confidence_score=50.0)
    config = make_bot_config(min_confidence_to_execute=75.0)

    result = gw.check_trade(signal, config, make_bot_state(), make_account())

    assert result.approved is False
    assert "[Confidence filter]" in result.reason


# =====================================================================
# 17-18. AI analysis checks
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_ai_analysis_required_but_missing(mock_db):
    """require_ai_analysis=True, no ai_deep_analysis -> rejected."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(require_ai_analysis=True)
    signal = make_signal(ai_deep_analysis=None)

    result = gw.check_trade(signal, config, make_bot_state(), make_account())

    assert result.approved is False
    assert "[AI analysis filter]" in result.reason
    assert "not available" in result.reason


@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_ai_conviction_too_low(mock_db):
    """AI conviction_score=3 < min_ai_conviction=7 -> rejected."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(require_ai_analysis=True, min_ai_conviction=7.0)
    signal = make_signal(ai_deep_analysis={"conviction_score": 3})

    result = gw.check_trade(signal, config, make_bot_state(), make_account())

    assert result.approved is False
    assert "[AI analysis filter]" in result.reason
    assert "conviction" in result.reason.lower()


# =====================================================================
# 19. Strategy filter
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_strategy_not_enabled(mock_db):
    """Signal strategy not in enabled list -> rejected."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(enabled_strategies=["vwap_pullback", "range_breakout"])
    signal = make_signal(strategy="orb_breakout_long")

    result = gw.check_trade(signal, config, make_bot_state(), make_account())

    assert result.approved is False
    assert "[Strategy filter]" in result.reason


# =====================================================================
# 20. Duplicate position
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_duplicate_position_rejected(mock_db):
    """Existing open trade for same symbol+direction -> rejected."""
    gw = RiskGateway(mock_db)
    # Mock db to return an existing trade
    existing = make_trade(id=99, symbol="AAPL", direction="buy", status=TS_OPEN)
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    signal = make_signal(symbol="AAPL", direction="buy")

    result = gw.check_trade(signal, make_bot_config(), make_bot_state(), make_account())

    assert result.approved is False
    assert "[Duplicate position]" in result.reason
    assert "AAPL" in result.reason


# =====================================================================
# 20b. Opposing position check
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_opposing_position_rejected(mock_db):
    """Cannot open BUY when an opposing SELL position exists -> rejected."""
    gw = RiskGateway(mock_db)

    # First call (duplicate check, direction=buy) -> None (no duplicate)
    # Second call (opposing check, direction=sell) -> existing trade
    existing_sell = make_trade(id=77, symbol="AAPL", direction="sell", status=TS_OPEN)

    call_count = [0]
    def side_effect_first():
        call_count[0] += 1
        if call_count[0] == 1:
            return None  # No duplicate same-direction position
        return existing_sell  # Opposing position exists

    mock_db.query.return_value.filter.return_value.first.side_effect = side_effect_first

    signal = make_signal(symbol="AAPL", direction="buy")

    result = gw.check_trade(signal, make_bot_config(), make_bot_state(), make_account())

    assert result.approved is False
    assert "[Opposing position]" in result.reason
    assert "AAPL" in result.reason


@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_opposing_position_allowed_when_no_conflict(mock_db):
    """No opposing position -> passes this check (approved overall)."""
    gw = RiskGateway(mock_db)
    # Default mock: .first() returns None for all queries
    signal = make_signal(symbol="AAPL", direction="buy")

    result = gw.check_trade(signal, make_bot_config(), make_bot_state(), make_account())

    assert result.approved is True


# =====================================================================
# 21-22. Options-specific: bid-ask spread and open interest
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_option_bid_ask_spread_too_wide(mock_db):
    """Bid-ask spread 20% > max 15% -> rejected for options."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(max_bid_ask_spread_pct=15.0)

    result = gw.check_trade(
        make_signal(), config, make_bot_state(), make_account(),
        asset_type="option",
        option_premium=2.0,
        option_oi=500,
        bid_ask_spread_pct=20.0,
    )

    assert result.approved is False
    assert "[Bid-ask spread]" in result.reason


@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_option_open_interest_too_low(mock_db):
    """Open interest 50 < min 100 -> rejected for options."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(min_option_open_interest=100)

    result = gw.check_trade(
        make_signal(), config, make_bot_state(), make_account(),
        asset_type="option",
        option_premium=2.0,
        option_oi=50,
        bid_ask_spread_pct=5.0,
    )

    assert result.approved is False
    assert "[Open interest]" in result.reason


# =====================================================================
# 23. Option premium exceeds per-trade limit
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_option_premium_exceeds_limit(mock_db):
    """Option premium cost ($500) > max_per_options_trade ($300) -> rejected."""
    gw = RiskGateway(mock_db)
    # premium=5.0 * 100 = $500 > max_per_options_trade=$300
    config = make_bot_config(max_per_options_trade=300.0)

    result = gw.check_trade(
        make_signal(), config, make_bot_state(), make_account(),
        asset_type="option",
        option_premium=5.0,
        option_oi=500,
        bid_ask_spread_pct=5.0,
    )

    assert result.approved is False
    assert "[Per-trade limit]" in result.reason


# =====================================================================
# 24. Per-trade limit for stocks always passes (enforced in sizer)
# =====================================================================

@freeze_time("2025-01-15 15:00:00")  # 10:00 AM ET
def test_per_trade_limit_stock_passes(mock_db):
    """Stock per-trade check always passes in risk gateway (enforced in sizer)."""
    gw = RiskGateway(mock_db)
    config = make_bot_config(max_per_stock_trade=500.0)

    result = gw.check_trade(
        make_signal(), config, make_bot_state(), make_account(),
        asset_type="stock",
    )

    assert result.approved is True
